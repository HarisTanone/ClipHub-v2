"""PodcastReframeEngine — Speaker-Aware Face-Based Reframing.

Strategy: Detect faces → Track persons → Detect active speaker → Smart layout.

Pipeline:
  1. MediaPipe Face Detection → find faces per frame
  2. IoU Person Tracker → consistent person IDs across frames
  3. Active Speaker Detection (lip movement via Face Mesh) → who is talking
  4. Layout decision based on speaker analysis:
     - 1 dominant speaker (≥75% talk time) → single crop on that speaker
     - 2 balanced speakers → speaker-aware double grid (60/40 emphasis)
     - 0 faces → center crop fallback

Rules:
  - Audio is ALWAYS stream-copied, never re-encoded through filter_complex
  - Aspect ratio math: 9:16 output = 1080x1920
  - Double grid: active speaker gets 60% height (1080×1152), listener 40% (1080×768)
  - Hysteresis prevents rapid speaker switching (0.3s hold)
  - Person IDs are IoU-tracked, not X-sorted (no swap on movement)
"""
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.domain.interfaces import IReframeEngine
from src.infrastructure.gpu_encoder import get_video_encoder_args
from src.infrastructure.active_speaker_detector import ActiveSpeakerDetector, ActiveSpeakerResult
from src.infrastructure.person_tracker import SimpleIoUTracker, BBox, TrackedDetection
from src.infrastructure.speaker_diarizer import SpeakerDiarizer, DiarizationResult
from src.infrastructure.speaker_face_mapper import SpeakerFaceMapper, MappingResult
from src.infrastructure.diarization_result_builder import DiarizationResultBuilder

logger = logging.getLogger(__name__)


@dataclass
class FaceDetection:
    """Face detection with bounding box for tracking."""
    center_x: float    # pixels, original resolution
    center_y: float    # pixels, original resolution
    bbox: BBox         # bounding box for IoU tracking
    rel_width: float   # relative width (for size filter)


class PodcastReframeEngine(IReframeEngine):
    """Speaker-aware face-based reframing with person tracking and lip analysis."""

    SAMPLE_INTERVAL_SEC = 0.333  # 3fps sampling (3× more precise than 1fps)
    MAX_SAMPLES = 180  # 3fps × 60s = 180 samples per clip
    FACE_CONFIDENCE = 0.55
    MIN_FACE_SIZE_RATIO = 0.05
    MAX_FACE_SIZE_RATIO = 0.50
    MIN_SEPARATION_RATIO = 0.20  # 20% of frame width to consider "two people"
    MIN_COEXIST_RATIO = 0.40     # ≥40% of frames must have BOTH faces simultaneously

    # Speaker-aware rendering
    SPEAKER_EMPHASIS_RATIO = 0.60    # Active speaker gets 60% of output height
    LISTENER_RATIO = 0.40            # Listener gets 40%
    DOMINANCE_SINGLE_CROP = 0.75     # If dominant ≥75% → use single crop instead of grid

    def __init__(self, hf_token: Optional[str] = None):
        self._face_detector = None
        self._use_legacy_api = False
        self._speaker_detector = ActiveSpeakerDetector()
        self._tracker: Optional[SimpleIoUTracker] = None

        # Diarization components (lazy-init)
        self._hf_token = hf_token
        self._diarizer: Optional[SpeakerDiarizer] = None
        self._face_mapper: Optional[SpeakerFaceMapper] = None
        self._result_builder = DiarizationResultBuilder()

    def _load_face_detector(self) -> bool:
        if self._face_detector is not None:
            return True
        try:
            import mediapipe as mp
            # Try legacy API first (mediapipe ≤0.10.21)
            if hasattr(mp, 'solutions') and hasattr(mp.solutions, 'face_detection'):
                self._face_detector = mp.solutions.face_detection.FaceDetection(
                    min_detection_confidence=self.FACE_CONFIDENCE,
                    model_selection=1,
                )
                self._use_legacy_api = True
                logger.info("podcast_reframe: MediaPipe loaded (legacy API)")
                return True
            else:
                # Task API (mediapipe ≥0.10.30)
                try:
                    from mediapipe.tasks.vision import FaceDetector, FaceDetectorOptions
                    from mediapipe.tasks.vision.core.vision_task_running_mode import VisionTaskRunningMode
                    from mediapipe.tasks import BaseOptions

                    model_path = self._find_face_detection_model()
                    base_options = BaseOptions(model_asset_path=model_path)
                    options = FaceDetectorOptions(
                        base_options=base_options,
                        running_mode=VisionTaskRunningMode.IMAGE,
                        min_detection_confidence=self.FACE_CONFIDENCE,
                    )
                    self._face_detector = FaceDetector.create_from_options(options)
                    self._use_legacy_api = False
                    logger.info("podcast_reframe: MediaPipe FaceDetector loaded (task API)")
                    return True
                except (ImportError, ModuleNotFoundError) as e:
                    logger.warning(f"podcast_reframe: Task API not available: {e}")
                    return False
        except Exception as e:
            logger.warning(f"podcast_reframe: MediaPipe failed: {e}")
            return False

    def _find_face_detection_model(self) -> str:
        """Find or download the face detection model for task API."""
        model_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, 'blaze_face_short_range.tflite')

        if not os.path.exists(model_path):
            import urllib.request
            url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
            logger.info("podcast_reframe: downloading face detection model...")
            urllib.request.urlretrieve(url, model_path)
            logger.info(f"podcast_reframe: model saved to {model_path}")

        return model_path

    # ─── Public API ───────────────────────────────────────────────────────

    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
        autogrid_enabled: bool = False,
        **kwargs,
    ) -> dict:
        if not os.path.exists(video_path):
            return {"output_path": video_path, "person_count": 0, "method": "error"}

        if target_aspect != "9:16":
            success = await self._simple_crop(video_path, output_path, target_aspect)
            return {"output_path": output_path if success else video_path, "person_count": 0, "method": "simple_crop"}

        if not self._load_face_detector():
            success = await self._center_crop(video_path, output_path)
            return {"output_path": output_path if success else video_path, "person_count": 0, "method": "center_crop"}

        try:
            result = await asyncio.to_thread(self._pipeline, video_path, output_path, autogrid_enabled)
            if result:
                return result
        except Exception as e:
            logger.warning(f"podcast_reframe: pipeline error: {e}")

        success = await self._center_crop(video_path, output_path)
        return {"output_path": output_path if success else video_path, "person_count": 0, "method": "center_crop_fallback"}

    # ─── Pipeline ─────────────────────────────────────────────────────────

    def _pipeline(self, video_path: str, output_path: str, autogrid: bool) -> Optional[dict]:
        import cv2
        cv2.setNumThreads(0)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        if width <= 0 or height <= 0:
            return None

        # Initialize person tracker
        self._tracker = SimpleIoUTracker(frame_width=width, frame_height=height)

        # Step 1: Detect faces with bounding boxes + tracking (per-frame)
        tracked_data = self._detect_and_track_faces(video_path, width, height, fps, total_frames)

        if not tracked_data["per_frame_faces"]:
            logger.info("podcast_reframe: no faces → center crop")
            return None

        person_count = tracked_data["person_count"]
        stable_positions = tracked_data["stable_positions"]

        # Step 2: Active Speaker Detection (only if 2+ people)
        speaker_result: Optional[ActiveSpeakerResult] = None
        if person_count >= 2:
            # 2a. Try PyAnnote diarization FIRST (more accurate for speaker identity)
            speaker_result = self._try_diarization(
                video_path, tracked_data, fps, total_frames
            )

            # 2b. Fallback: lip+head+VAD (existing method)
            if speaker_result is None:
                try:
                    vad_segments = self._get_vad_segments(video_path)
                    speaker_result = self._speaker_detector.detect(
                        video_path=video_path,
                        fps=fps,
                        total_frames=total_frames,
                        width=width,
                        height=height,
                        vad_segments=vad_segments,
                        position_targets=tracked_data.get("position_targets"),
                    )
                except Exception as e:
                    logger.warning(f"podcast_reframe: lip+head fallback failed (non-fatal): {e}")

        # Step 3: Dynamic Panning — single FFmpeg pass with smooth crop tracking
        # Builds a time-based crop X expression that follows the active face.
        # No concat, no trim, no desync. Audio always stream-copied.
        result = self._render_dynamic_panning(
            video_path, output_path, width, height, fps,
            tracked_data, speaker_result,
        )
        if result:
            return result

        # Step 4: Fallback to static layout (if panning fails)
        decision = self._decide_layout_v2(
            tracked_data=tracked_data,
            speaker_result=speaker_result,
            width=width,
            autogrid=autogrid,
        )

        if decision["layout"] == "speaker_emphasis":
            return self._render_speaker_emphasis_grid(
                video_path, output_path, width, height, decision
            )
        elif decision["layout"] == "double":
            return self._render_double_grid(video_path, output_path, width, height, decision)
        else:
            return self._render_single_crop(video_path, output_path, width, height, decision)

    # ─── Diarization ──────────────────────────────────────────────────────

    def _init_diarizer(self) -> Optional[SpeakerDiarizer]:
        """Lazy-init diarizer (only if enabled and token available)."""
        if self._diarizer is not None:
            return self._diarizer

        from src.config import settings

        if not settings.DIARIZATION_ENABLED:
            return None
        
        hf_token = self._hf_token or settings.HF_TOKEN
        if not hf_token:
            logger.info("podcast_reframe: diarization skipped (no HF_TOKEN)")
            return None

        self._diarizer = SpeakerDiarizer(
            hf_token=hf_token,
            model_name=settings.DIARIZATION_MODEL,
            timeout_sec=settings.DIARIZATION_TIMEOUT_SEC,
            min_speakers=settings.DIARIZATION_MIN_SPEAKERS,
            max_speakers=settings.DIARIZATION_MAX_SPEAKERS,
        )
        self._face_mapper = SpeakerFaceMapper(
            confidence_threshold=settings.DIARIZATION_MAPPING_CONFIDENCE_THRESHOLD,
        )
        return self._diarizer

    def _try_diarization(
        self,
        video_path: str,
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> Optional[ActiveSpeakerResult]:
        """Attempt PyAnnote diarization + face mapping.

        Returns ActiveSpeakerResult if successful, None to trigger fallback.
        Reuses existing per_frame_tracked data — no additional video processing.
        """
        diarizer = self._init_diarizer()
        if diarizer is None or not diarizer.is_available:
            return None

        try:
            # Run diarization synchronously (already in thread via _pipeline)
            import asyncio

            # Create new event loop since we're in a thread
            loop = asyncio.new_event_loop()
            try:
                diarization_result = loop.run_until_complete(
                    diarizer.diarize(video_path)
                )
            finally:
                loop.close()

            if diarization_result is None:
                logger.info("podcast_reframe: diarization returned None → fallback to lip+head")
                return None

            logger.info(
                f"podcast_reframe: diarization OK — {diarization_result.speaker_count} speakers, "
                f"{len(diarization_result.segments)} segments"
            )

            # Build speaker-face mapping using EXISTING tracker data
            sample_timestamps = tracked_data.get("sample_timestamps") or [
                i * self.SAMPLE_INTERVAL_SEC
                for i in range(len(tracked_data["per_frame_tracked"]))
            ]

            mapping_result = self._face_mapper.build_mapping(
                diarization_segments=diarization_result.segments,
                per_frame_tracked=tracked_data["per_frame_tracked"],
                sample_timestamps=sample_timestamps,
                stable_positions=tracked_data["stable_positions"],
            )

            # Check mapping reliability
            if not mapping_result.is_reliable:
                logger.info(
                    f"podcast_reframe: mapping unreliable "
                    f"(confidence={mapping_result.overall_confidence:.2f}) → fallback to lip+head"
                )
                return None

            # Convert to ActiveSpeakerResult (same interface as lip-based)
            speaker_result = self._result_builder.build(
                diarization=diarization_result,
                mapping=mapping_result,
                fps=fps,
                total_frames=total_frames,
                stable_positions=tracked_data["stable_positions"],
                sample_interval_sec=self.SAMPLE_INTERVAL_SEC,
                track_to_position=tracked_data.get("track_to_position"),
            )

            logger.info("podcast_reframe: ✓ using DIARIZATION-based speaker detection")
            # Store stable_positions for N-position targeting in panning
            self._diarization_stable_positions = tracked_data["stable_positions"]
            return speaker_result

        except Exception as e:
            logger.warning(f"podcast_reframe: diarization pipeline failed: {e}")
            return None

    # ─── Face Detection + Tracking ───────────────────────────────────────

    def _detect_and_track_faces(
        self, video_path: str, width: int, height: int, fps: float, total_frames: int
    ) -> dict:
        """Detect faces AND track them with IoU for consistent IDs.

        Returns:
            {
                "per_frame_faces": List[List[float]],  # legacy: X positions per frame
                "per_frame_tracked": List[List[TrackedDetection]],
                "person_count": int,
                "stable_positions": Dict[int, float],  # track_id → median X
                "position_targets": Dict[int, float],  # position_id → median X
                "track_to_position": Dict[int, int],   # track_id → position_id
            }
        """
        import cv2
        cv2.setNumThreads(0)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {
                "per_frame_faces": [],
                "per_frame_tracked": [],
                "sample_frame_indices": [],
                "sample_timestamps": [],
                "person_count": 0,
                "stable_positions": {},
                "position_targets": {},
                "track_to_position": {},
            }

        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

        per_frame_faces: List[List[float]] = []
        per_frame_tracked: List[List[TrackedDetection]] = []
        sample_frame_indices: List[int] = []
        sample_timestamps: List[float] = []

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Downscale for speed
            proc_frame = frame_rgb
            if frame_rgb.shape[1] > 1280:
                scale = 1280 / frame_rgb.shape[1]
                proc_frame = cv2.resize(frame_rgb, (int(frame_rgb.shape[1] * scale), int(frame_rgb.shape[0] * scale)))

            frame_faces: List[float] = []
            frame_bboxes: List[BBox] = []

            if self._use_legacy_api:
                # Legacy API: mp.solutions.face_detection
                results = self._face_detector.process(proc_frame)
                if results.detections:
                    for det in results.detections:
                        bbox = det.location_data.relative_bounding_box
                        if bbox.width < self.MIN_FACE_SIZE_RATIO or bbox.width > self.MAX_FACE_SIZE_RATIO:
                            continue
                        cx = (bbox.xmin + bbox.width / 2) * width
                        frame_faces.append(cx)
                        face_bbox = BBox.from_relative(
                            bbox.xmin, bbox.ymin, bbox.width, bbox.height,
                            width, height,
                        )
                        frame_bboxes.append(face_bbox)
            else:
                # Task API: mp.tasks.vision.FaceDetector
                import mediapipe as mp
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=proc_frame)
                result = self._face_detector.detect(mp_image)
                if result.detections:
                    for det in result.detections:
                        bbox = det.bounding_box
                        # Task API returns pixel coordinates (origin_x, origin_y, width, height)
                        # Need to convert to relative for size filter
                        proc_h, proc_w = proc_frame.shape[:2]
                        rel_w = bbox.width / proc_w
                        rel_h = bbox.height / proc_h
                        if rel_w < self.MIN_FACE_SIZE_RATIO or rel_w > self.MAX_FACE_SIZE_RATIO:
                            continue
                        # Convert to original resolution
                        scale_to_orig = width / proc_w
                        x1 = bbox.origin_x * scale_to_orig
                        y1 = bbox.origin_y * (height / proc_h)
                        w_px = bbox.width * scale_to_orig
                        h_px = bbox.height * (height / proc_h)
                        cx = x1 + w_px / 2
                        frame_faces.append(cx)
                        face_bbox = BBox(x1, y1, x1 + w_px, y1 + h_px)
                        frame_bboxes.append(face_bbox)

            # Update tracker with this frame's detections
            # First: filter overlapping faces (NMS) to prevent 1 person → 2 detections
            frame_faces = self._filter_overlapping_faces(frame_faces, width)
            # Also filter bboxes to match (keep only unique faces)
            if len(frame_bboxes) > len(frame_faces):
                # Re-filter bboxes by keeping those whose center_x matches filtered faces
                filtered_bboxes = []
                for bbox in frame_bboxes:
                    cx = bbox.center_x
                    if any(abs(cx - fx) < width * 0.05 for fx in frame_faces):
                        filtered_bboxes.append(bbox)
                frame_bboxes = filtered_bboxes[:len(frame_faces)]

            tracked = self._tracker.update(frame_bboxes, frame_idx)

            per_frame_faces.append(frame_faces)
            per_frame_tracked.append(tracked)
            sample_frame_indices.append(frame_idx)
            sample_timestamps.append(frame_idx / fps)

        cap.release()

        position_model = self._build_position_model(per_frame_tracked, width)
        person_count = position_model["person_count"]
        stable_positions = position_model["stable_positions"]
        position_targets = position_model["position_targets"]
        track_to_position = position_model["track_to_position"]

        logger.info(
            f"podcast_reframe: tracked {len(stable_positions)} unique tracks, "
            f"person_count={person_count}, "
            f"tracks={{{', '.join(f'T{k}:{v:.0f}' for k, v in stable_positions.items())}}}, "
            f"positions={{{', '.join(f'P{k}:{v:.0f}' for k, v in position_targets.items())}}}"
        )

        return {
            "per_frame_faces": per_frame_faces,
            "per_frame_tracked": per_frame_tracked,
            "sample_frame_indices": sample_frame_indices,
            "sample_timestamps": sample_timestamps,
            "person_count": person_count,
            "stable_positions": stable_positions,
            "position_targets": position_targets,
            "track_to_position": track_to_position,
        }

    def _build_position_model(
        self,
        per_frame_tracked: List[List[TrackedDetection]],
        width: int,
    ) -> dict:
        """Build stable person positions from all sampled tracker output.

        The tracker may prune a track if a face disappears near the end of a
        clip. This model keeps historical observations and clusters re-created
        tracks that land in the same seat, producing stable positional IDs for
        speaker detection and centering.
        """
        track_positions: Dict[int, List[float]] = defaultdict(list)

        for frame_tracked in per_frame_tracked:
            for detection in frame_tracked:
                track_positions[detection.track_id].append(detection.bbox.center_x)

        if not track_positions:
            return {
                "person_count": 0,
                "stable_positions": {},
                "position_targets": {},
                "track_to_position": {},
            }

        min_hits = 2 if len(per_frame_tracked) >= 6 else 1
        filtered = {
            track_id: xs
            for track_id, xs in track_positions.items()
            if len(xs) >= min_hits
        }
        if not filtered:
            filtered = dict(track_positions)

        stable_positions = {
            track_id: float(np.median(xs))
            for track_id, xs in filtered.items()
        }

        clusters: List[dict] = []
        cluster_threshold = max(width * self.MIN_FACE_DISTANCE_RATIO, 80.0)

        for track_id, median_x in sorted(stable_positions.items(), key=lambda kv: kv[1]):
            if clusters and abs(median_x - clusters[-1]["center"]) <= cluster_threshold:
                clusters[-1]["track_ids"].append(track_id)
                clusters[-1]["positions"].extend(filtered[track_id])
                clusters[-1]["center"] = float(np.median(clusters[-1]["positions"]))
            else:
                clusters.append({
                    "track_ids": [track_id],
                    "positions": list(filtered[track_id]),
                    "center": median_x,
                })

        position_targets: Dict[int, float] = {}
        track_to_position: Dict[int, int] = {}
        for position_id, cluster in enumerate(clusters):
            position_targets[position_id] = float(np.median(cluster["positions"]))
            for track_id in cluster["track_ids"]:
                track_to_position[track_id] = position_id

        return {
            "person_count": len(position_targets),
            "stable_positions": stable_positions,
            "position_targets": position_targets,
            "track_to_position": track_to_position,
        }

    # ─── Layout Decision (Speaker-Aware) ─────────────────────────────────

    def _decide_layout_v2(
        self,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        width: int,
        autogrid: bool,
    ) -> dict:
        """Speaker-aware layout decision.

        Priority:
          1. If speaker detected and one person dominates (≥75%) → single crop on them
          2. If 2 speakers balanced + autogrid → speaker_emphasis grid (60/40)
          3. Fallback to legacy logic (X-position based)
        """
        per_frame_faces = tracked_data["per_frame_faces"]
        stable_positions = tracked_data["stable_positions"]
        position_targets = tracked_data.get("position_targets") or {}
        person_count = tracked_data["person_count"]

        all_x = [x for frame in per_frame_faces for x in frame]
        if not all_x:
            return {"layout": "single", "crop_x": width // 2, "person_count": 0}

        # ─── Speaker-aware path ───────────────────────────────────────────
        if speaker_result and person_count >= 2 and (position_targets or stable_positions):
            dominant_id = speaker_result.dominant_speaker_id
            dominant_ratio = speaker_result.dominant_ratio
            sorted_positions = sorted(
                (int(pos_id), float(x)) for pos_id, x in position_targets.items()
            )
            if not sorted_positions:
                sorted_positions = [
                    (idx, float(x))
                    for idx, (_, x) in enumerate(sorted(stable_positions.items(), key=lambda kv: kv[1]))
                ]
            position_to_x = dict(sorted_positions)

            # Case 1: One dominant speaker → single crop on them
            if dominant_ratio >= self.DOMINANCE_SINGLE_CROP:
                dominant_x = position_to_x.get(dominant_id)
                if dominant_x is not None:
                    crop_x = int(dominant_x)
                    logger.info(
                        f"podcast_reframe: DOMINANT SPEAKER (ID={dominant_id}, "
                        f"ratio={dominant_ratio:.0%}) → single crop at x={crop_x}"
                    )
                    return {
                        "layout": "single",
                        "crop_x": crop_x,
                        "person_count": person_count,
                        "method_detail": "dominant_speaker_single",
                    }
                else:
                    # stable_positions incomplete — fallback to per-frame cluster
                    # dominant_id 0=left, 1=right
                    midpoint = width / 2.0
                    if dominant_id == 0:
                        cluster = [x for frame in per_frame_faces for x in frame if x < midpoint]
                    else:
                        cluster = [x for frame in per_frame_faces for x in frame if x >= midpoint]
                    if cluster:
                        crop_x = int(np.median(cluster))
                        logger.info(
                            f"podcast_reframe: DOMINANT SPEAKER (ID={dominant_id}, "
                            f"ratio={dominant_ratio:.0%}) → cluster crop at x={crop_x}"
                        )
                        return {
                            "layout": "single",
                            "crop_x": crop_x,
                            "person_count": person_count,
                            "method_detail": "dominant_speaker_single",
                        }

            # Case 2: Balanced speakers → 60/40 emphasis grid
            if autogrid and len(sorted_positions) >= 2:
                left_position_id, left_x = sorted_positions[0]
                right_position_id, right_x = sorted_positions[1]
                separation = right_x - left_x

                if separation >= width * self.MIN_SEPARATION_RATIO:
                    # Determine who is currently the active speaker for emphasis
                    # Use the speaker who spoke most recently (last segment)
                    active_speaker_id = dominant_id if dominant_id is not None else 0

                    # Active speaker X position
                    active_x = position_to_x.get(active_speaker_id, left_x)
                    # Listener X position
                    listener_position_id = (
                        right_position_id
                        if active_speaker_id == left_position_id
                        else left_position_id
                    )
                    listener_x = position_to_x.get(listener_position_id, right_x)

                    logger.info(
                        f"podcast_reframe: SPEAKER EMPHASIS GRID "
                        f"(active=P{active_speaker_id} x={active_x:.0f}, "
                        f"listener=P{listener_position_id} x={listener_x:.0f}, "
                        f"dominance={dominant_ratio:.0%})"
                    )
                    return {
                        "layout": "speaker_emphasis",
                        "active_x": int(active_x),
                        "listener_x": int(listener_x),
                        "active_track_id": active_speaker_id,
                        "listener_track_id": listener_position_id,
                        "person_count": person_count,
                    }

        # ─── Legacy fallback (no speaker detection) ───────────────────────
        return self._decide_layout_legacy(per_frame_faces, width, autogrid, person_count)

    def _decide_layout_legacy(
        self, per_frame_faces: List[List[float]], width: int, autogrid: bool, person_count: int
    ) -> dict:
        """Legacy layout decision (X-position based, no speaker info)."""
        all_x = [x for frame in per_frame_faces for x in frame]
        if not all_x:
            return {"layout": "single", "crop_x": width // 2, "person_count": 0}

        multi_face_frames = 0
        left_positions: List[float] = []
        right_positions: List[float] = []

        for frame_faces in per_frame_faces:
            if len(frame_faces) >= 2:
                sorted_faces = sorted(frame_faces)
                leftmost = sorted_faces[0]
                rightmost = sorted_faces[-1]
                separation = rightmost - leftmost

                if separation >= width * self.MIN_SEPARATION_RATIO:
                    multi_face_frames += 1
                    left_positions.append(leftmost)
                    right_positions.append(rightmost)

        total_frames = len(per_frame_faces)
        coexist_ratio = multi_face_frames / total_frames if total_frames > 0 else 0

        logger.info(
            f"podcast_reframe: legacy coexist={coexist_ratio:.0%} "
            f"({multi_face_frames}/{total_frames} frames)"
        )

        if coexist_ratio >= self.MIN_COEXIST_RATIO and autogrid and left_positions:
            left_x = int(np.median(left_positions))
            right_x = int(np.median(right_positions))
            return {"layout": "double", "left_x": left_x, "right_x": right_x, "person_count": person_count}

        # ─── FORCED GRID: 2 people detected but never in same frame ──────
        # When coexist=0% but person_count>=2, faces alternate frames.
        # Instead of single crop (which lands on empty middle), force grid
        # using left/right cluster positions from per-frame detections.
        if person_count >= 2 and autogrid and len(all_x) > 5:
            midpoint = width / 2.0
            left_cluster = [x for x in all_x if x < midpoint]
            right_cluster = [x for x in all_x if x >= midpoint]

            # Both clusters must have meaningful detections
            if left_cluster and right_cluster:
                left_x = int(np.median(left_cluster))
                right_x = int(np.median(right_cluster))
                separation = right_x - left_x

                if separation >= width * self.MIN_SEPARATION_RATIO:
                    logger.info(
                        f"podcast_reframe: FORCED GRID (coexist={coexist_ratio:.0%} but 2 clusters found, "
                        f"L={left_x} [{len(left_cluster)} dets], R={right_x} [{len(right_cluster)} dets])"
                    )
                    return {"layout": "double", "left_x": left_x, "right_x": right_x, "person_count": person_count}

        # ─── True single person fallback ──────────────────────────────────
        # Only reach here if genuinely 1 person or clusters too close
        if person_count >= 2 and len(all_x) > 5:
            # Still avoid empty middle: pick dominant cluster
            midpoint = width / 2.0
            left_cluster = [x for x in all_x if x < midpoint]
            right_cluster = [x for x in all_x if x >= midpoint]
            if len(left_cluster) >= len(right_cluster):
                crop_x = int(np.median(left_cluster)) if left_cluster else int(np.median(all_x))
            else:
                crop_x = int(np.median(right_cluster)) if right_cluster else int(np.median(all_x))
            logger.info(f"podcast_reframe: cluster-based single (L={len(left_cluster)}, R={len(right_cluster)}) → x={crop_x}")
        else:
            crop_x = int(np.median(all_x))

        return {"layout": "single", "crop_x": crop_x, "person_count": person_count}

    # ─── Render: Dynamic Panning (Single Pass, Zero Desync) ─────────────

    PAN_DEAD_ZONE_PX = 150     # Reduced from 250 — denser sampling allows tighter tracking
    PAN_HOLD_MIN_SEC = 2.0     # Reduced from 5.0 — respond faster to speaker changes
    PAN_CLUSTER_THRESHOLD = 200  # If all detections within 200px spread → lock position
    PAN_MAX_KEYFRAMES = 25     # Increased for denser sampling (more movement allowed)
    PAN_TRANSITION_SEC = 0.4       # Smooth transition seconds (lerp between positions)
    SPEAKER_TARGET_MISMATCH_RATIO = 0.18  # Keep known speaker seat if one visible face is far away.

    def _choose_panning_target_x(
        self,
        frame_faces: List[float],
        frame_tracked: List[TrackedDetection],
        speaker_result: Optional[ActiveSpeakerResult],
        frame_idx_approx: int,
        position_targets: Dict[int, float],
        track_to_position: Dict[int, int],
        frame_width: int,
        last_center: Optional[float] = None,
    ) -> Tuple[Optional[int], Optional[TrackedDetection]]:
        """Pick the crop center, preferring the active speaker's stable seat."""
        active_speaker: Optional[int] = None
        target_x_hint: Optional[float] = None

        if speaker_result and speaker_result.per_frame_speaker:
            closest_frame = min(
                speaker_result.per_frame_speaker.keys(),
                key=lambda f: abs(f - frame_idx_approx),
                default=None,
            )
            if closest_frame is not None:
                active_speaker = speaker_result.per_frame_speaker[closest_frame]
                target_x_hint = position_targets.get(active_speaker)

        if active_speaker is not None:
            matching_detections = [
                detection for detection in frame_tracked
                if track_to_position.get(detection.track_id) == active_speaker
            ]
            if matching_detections:
                target_detection = min(
                    matching_detections,
                    key=lambda d: abs(
                        d.bbox.center_x
                        - (target_x_hint if target_x_hint is not None else d.bbox.center_x)
                    ),
                )
                return int(target_detection.bbox.center_x), target_detection

            if target_x_hint is not None:
                if not frame_faces:
                    return int(target_x_hint), None

                nearest_face = float(min(frame_faces, key=lambda x: abs(x - target_x_hint)))
                mismatch_threshold = frame_width * self.SPEAKER_TARGET_MISMATCH_RATIO

                if len(frame_faces) == 1 and abs(nearest_face - target_x_hint) > mismatch_threshold:
                    logger.debug(
                        "podcast_reframe: single visible face is far from active speaker "
                        "target (face=%.1f, target=%.1f); holding speaker seat",
                        nearest_face,
                        target_x_hint,
                    )
                    return int(target_x_hint), None

                return int(nearest_face), None

            if frame_faces:
                sorted_faces = sorted(frame_faces)
                if 0 <= active_speaker < len(sorted_faces):
                    return int(sorted_faces[active_speaker]), None

        if not frame_faces:
            return None, None

        if last_center is not None:
            return int(min(frame_faces, key=lambda x: abs(x - last_center))), None

        return int(np.median(frame_faces)), None

    def _render_dynamic_panning(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
    ) -> Optional[dict]:
        """Render with dynamic crop panning — smooth tracking of active face.

        Single FFmpeg command, NO concat, audio stream-copied = zero desync.

        Approach:
          1. Build per-second target crop X from face detections
          2. Generate FFmpeg crop expression with time-based interpolation
          3. Crop smoothly pans from face to face as they appear

        Result: camera "follows" the speaker, smooth panning transitions.
        """
        per_frame_faces = tracked_data["per_frame_faces"]
        if not per_frame_faces or len(per_frame_faces) < 3:
            return None

        crop_w = min(int(height * 9 / 16), width)
        max_crop_x = width - crop_w

        # 1. Build target crop X per second
        # For each sample, determine where crop should be centered
        keyframes: List[Tuple[float, int]] = []  # (time_sec, target_crop_x)
        per_frame_tracked = tracked_data.get("per_frame_tracked", [])
        sample_frame_indices = tracked_data.get("sample_frame_indices", [])
        sample_timestamps = tracked_data.get("sample_timestamps", [])
        position_targets = {
            int(k): float(v)
            for k, v in (tracked_data.get("position_targets") or {}).items()
        }
        track_to_position = {
            int(k): int(v)
            for k, v in (tracked_data.get("track_to_position") or {}).items()
        }

        for i, frame_faces in enumerate(per_frame_faces):
            t = sample_timestamps[i] if i < len(sample_timestamps) else i * self.SAMPLE_INTERVAL_SEC
            frame_idx_approx = (
                sample_frame_indices[i]
                if i < len(sample_frame_indices)
                else int(t * fps)
            )
            frame_tracked = per_frame_tracked[i] if i < len(per_frame_tracked) else []
            last_center = keyframes[-1][1] + crop_w / 2 if keyframes else None

            cx, target_detection = self._choose_panning_target_x(
                frame_faces=frame_faces,
                frame_tracked=frame_tracked,
                speaker_result=speaker_result,
                frame_idx_approx=frame_idx_approx,
                position_targets=position_targets,
                track_to_position=track_to_position,
                frame_width=width,
                last_center=last_center,
            )

            if cx is None:
                # No reliable face or speaker target → hold previous position
                if keyframes:
                    keyframes.append((t, keyframes[-1][1]))
                continue

            # BBOX-AWARE CENTERING: ensure face + margin fits in crop window
            # Use face width from stable detection data to prevent head cutoff
            face_margin_applied = False
            if frame_tracked:
                # Find the tracked detection closest to our target cx
                best_det = target_detection or min(
                    frame_tracked,
                    key=lambda d: abs(d.bbox.center_x - cx),
                )
                mismatch_threshold = width * self.SPEAKER_TARGET_MISMATCH_RATIO
                if target_detection or abs(best_det.bbox.center_x - cx) <= mismatch_threshold:
                    face_w = best_det.bbox.width
                    margin = face_w * 0.6  # 60% extra space around face

                    desired_left = best_det.bbox.x1 - margin
                    desired_right = best_det.bbox.x2 + margin

                    if (desired_right - desired_left) <= crop_w:
                        # Face + margin fits in crop → center it properly
                        crop_x = int((desired_left + desired_right) / 2 - crop_w / 2)
                        crop_x = max(0, min(crop_x, max_crop_x))
                        face_margin_applied = True

            if not face_margin_applied:
                # Standard centering: place face center in middle of crop
                crop_x = max(0, min(cx - crop_w // 2, max_crop_x))

            keyframes.append((t, crop_x))

        if not keyframes:
            return None

        # Stabilize with cluster lock + dead zone + hold minimum
        # 1. Cluster lock: if all positions within PAN_CLUSTER_THRESHOLD → lock camera
        all_kf_x = [x for _, x in keyframes]
        x_spread = max(all_kf_x) - min(all_kf_x) if all_kf_x else 0

        if x_spread < self.PAN_CLUSTER_THRESHOLD:
            # All detections in same area — lock to median (home position)
            home_x = int(np.median(all_kf_x))
            logger.info(
                f"podcast_reframe: CLUSTER LOCK (spread={x_spread}px < {self.PAN_CLUSTER_THRESHOLD}px) "
                f"→ locked at x={home_x}"
            )
            stabilized = [(0.0, home_x)]
        else:
            # 2. Dead zone + hold minimum
            stabilized: List[Tuple[float, int]] = [keyframes[0]]
            for t, x in keyframes[1:]:
                last_t, last_x = stabilized[-1]
                movement = abs(x - last_x)
                time_since_last = t - last_t

                if movement >= self.PAN_DEAD_ZONE_PX and time_since_last >= self.PAN_HOLD_MIN_SEC:
                    stabilized.append((t, x))

            # Ensure last position captured
            if stabilized[-1][0] < keyframes[-1][0]:
                stabilized.append(keyframes[-1])

            # Limit to max keyframes
            if len(stabilized) > self.PAN_MAX_KEYFRAMES:
                step = len(stabilized) // (self.PAN_MAX_KEYFRAMES - 2)
                reduced = [stabilized[0]]
                for i in range(step, len(stabilized) - 1, step):
                    reduced.append(stabilized[i])
                reduced.append(stabilized[-1])
                stabilized = reduced

        logger.info(
            f"podcast_reframe: panning {len(keyframes)} raw → {len(stabilized)} stabilized "
            f"(dead_zone={self.PAN_DEAD_ZONE_PX}px, hold={self.PAN_HOLD_MIN_SEC}s)"
        )

        # 2. Build FFmpeg crop X expression
        if len(stabilized) <= 1 or all(s[1] == stabilized[0][1] for s in stabilized):
            crop_x_expr = str(stabilized[0][1])
            logger.info(f"podcast_reframe: static crop at x={stabilized[0][1]}")
        else:
            crop_x_expr = self._build_panning_expression(stabilized, 0)
            for i, (t, x) in enumerate(stabilized):
                logger.info(f"  pan[{i}] t={t:.1f}s → x={x}")

        # 3. Render with single FFmpeg command
        vf = (
            f"crop={crop_w}:{height}:{crop_x_expr}:0,"
            f"scale=1080:1920,format=yuv420p,setsar=1"
        )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            *get_video_encoder_args("medium"),
            "-c:a", "copy",  # NEVER re-encode audio → zero desync
            "-movflags", "+faststart",
            output_path,
        ]

        logger.info(
            f"podcast_reframe: DYNAMIC PANNING ({len(stabilized)} keyframes, "
            f"crop_w={crop_w})"
        )

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.info(f"podcast_reframe: dynamic panning OK")
            return {
                "output_path": output_path,
                "person_count": tracked_data["person_count"],
                "method": "podcast_dynamic_panning",
                "keyframes": len(stabilized),
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: dynamic panning failed: {result.stderr[-300:]}")
        return None

    def _build_panning_expression(
        self, keyframes: List[Tuple[float, int]], transition_sec: float = 0.0
    ) -> str:
        """Build FFmpeg time-based crop X expression.

        If transition_sec > 0, generates smooth lerp between positions.
        Otherwise, generates instant snap (original behavior).

        Smooth transition formula:
          lerp(a, b, progress) where progress = (t - t_start) / duration
          In FFmpeg: a + (b - a) * min(1, (t - t_start) / duration)
        """
        if len(keyframes) <= 1:
            return str(keyframes[0][1] if keyframes else 0)

        # Use configured transition time
        from src.config import settings
        trans = getattr(settings, 'CENTERING_TRANSITION_SEC', 0.4)

        if trans <= 0:
            # Original behavior: instant snap
            expr = str(keyframes[-1][1])
            for i in range(len(keyframes) - 2, -1, -1):
                _, x_current = keyframes[i]
                t_next, _ = keyframes[i + 1]
                expr = f"if(lt(t\\,{t_next:.2f})\\,{x_current}\\,{expr})"
            return f"'{expr}'"

        # Smooth transition: lerp between keyframes during transition window
        # Structure: for each segment, if within transition → lerp, else → hold
        expr = str(keyframes[-1][1])  # Final position

        for i in range(len(keyframes) - 2, -1, -1):
            _, x_current = keyframes[i]
            t_next, x_next = keyframes[i + 1]
            t_trans_start = t_next - trans  # Transition starts `trans` seconds before keyframe

            if t_trans_start <= (keyframes[i][0] if i > 0 else 0):
                # Not enough room for transition — snap
                expr = f"if(lt(t\\,{t_next:.2f})\\,{x_current}\\,{expr})"
            else:
                # Smooth: hold → lerp → next
                # lerp formula: x_current + (x_next - x_current) * min(1, (t - t_trans_start) / trans)
                delta = x_next - x_current
                lerp_expr = f"{x_current}+{delta}*min(1\\,(t-{t_trans_start:.2f})/{trans:.2f})"
                # if t < t_trans_start → hold x_current
                # elif t < t_next → lerp
                # else → next expression
                inner = f"if(lt(t\\,{t_trans_start:.2f})\\,{x_current}\\,if(lt(t\\,{t_next:.2f})\\,{lerp_expr}\\,{expr}))"
                expr = inner

        return f"'{expr}'"

    # ─── Render: Single Crop ──────────────────────────────────────────────

    def _render_single_crop(
        self, video_path: str, output_path: str, width: int, height: int, decision: dict
    ) -> Optional[dict]:
        """Simple 9:16 crop centered on detected face. Audio stream-copied."""
        crop_w = min(int(height * 9 / 16), width)
        crop_x = self._clamp_x(decision["crop_x"], crop_w, width)

        vf = f"crop={crop_w}:{height}:{crop_x}:0,scale=1080:1920,format=yuv420p,setsar=1"

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            *get_video_encoder_args("medium"),
            "-c:a", "copy",  # NEVER re-encode audio
            "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            pc = decision.get("person_count", 1)
            method_detail = decision.get("method_detail", "podcast_single_crop")
            logger.info(f"podcast_reframe: single crop OK (x={crop_x}, w={crop_w}, method={method_detail})")
            return {"output_path": output_path, "person_count": pc, "method": method_detail}

        if result.stderr:
            logger.warning(f"podcast_reframe: single crop failed: {result.stderr[-300:]}")
        return None

    # ─── Render: Double Grid ──────────────────────────────────────────────

    def _render_double_grid(
        self, video_path: str, output_path: str, width: int, height: int, decision: dict
    ) -> Optional[dict]:
        """Double grid: top=left speaker, bottom=right speaker.

        CORRECT MATH:
          - Output: 1080x1920 (9:16)
          - Each panel: 1080x960
          - Per panel aspect = 1080/960 = 9/8
          - From source: crop_w = height/2 * 9/8 (to maintain 9:8 ratio per panel)
          - crop_h = height/2 (each person gets half the vertical source)
          - NO SQUISH: scale maintains aspect because crop ratio = output ratio

        Wait — podcast speakers sit side-by-side in a 16:9 frame.
        We want to show each person FULL HEIGHT but cropped horizontally.
        Correct approach: crop a 9:16 column per person, then stack them.

        Per panel: crop (height*9/32) wide x (height/2) tall? No...

        SIMPLEST CORRECT approach for podcast (2 people side-by-side):
          - Each panel shows one person from full-height source
          - crop_w per panel = some width centered on face
          - crop_h per panel = full height
          - Scale each crop to 1080x960
          - This WILL cause slight vertical compression (height → 960)
            but 1080/height ratio must equal 1080/960 ratio for no distortion
          - For no distortion: crop must be (crop_w)x(crop_w * 960/1080) = crop_w x (crop_w * 8/9)

        FINAL CORRECT: each panel crop = W x H where W:H = 9:8 (= 1080:960)
          - crop_h = height (full height)
          - crop_w = height * 9 / 8 (from full height)
          - If crop_w > width, clamp to width and adjust crop_h = width * 8 / 9
          - Scale to 1080x960
          - Stack = 1080x1920 ✓
          - Aspect ratio preserved ✓
        """
        # Each panel: 9:8 aspect ratio
        crop_w = int(height * 9 / 8)
        crop_h = height

        if crop_w > width:
            # Source too narrow — adjust
            crop_w = width
            crop_h = int(width * 8 / 9)

        left_x = self._clamp_x(decision["left_x"], crop_w, width)
        right_x = self._clamp_x(decision["right_x"], crop_w, width)

        # Y offset for crop (center vertically if crop_h < height)
        crop_y = max(0, (height - crop_h) // 2)

        vf = (
            f"split=2[top][bot];"
            f"[top]crop={crop_w}:{crop_h}:{left_x}:{crop_y},scale=1080:960,format=yuv420p[t];"
            f"[bot]crop={crop_w}:{crop_h}:{right_x}:{crop_y},scale=1080:960,format=yuv420p[b];"
            f"[t][b]vstack=inputs=2,setsar=1[vout]"
        )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", vf,
            "-map", "[vout]", "-map", "0:a?",
            *get_video_encoder_args("medium"),
            "-c:a", "copy",  # NEVER re-encode audio
            "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            pc = decision.get("person_count", 2)
            logger.info(f"podcast_reframe: double grid OK (L={left_x}, R={right_x}, crop={crop_w}x{crop_h})")
            return {"output_path": output_path, "person_count": pc, "method": "podcast_double_grid"}

        if result.stderr:
            logger.warning(f"podcast_reframe: double grid failed: {result.stderr[-300:]}")
        return None

    # ─── Render: Speaker Emphasis Grid (60/40) ──────────────────────────

    def _render_speaker_emphasis_grid(
        self, video_path: str, output_path: str, width: int, height: int, decision: dict
    ) -> Optional[dict]:
        """Speaker-aware double grid: active speaker 60% height, listener 40%.

        Output: 1080x1920 (9:16)
        - Active speaker panel: 1080x1152 (60% of 1920)
        - Listener panel: 1080x768 (40% of 1920)

        Math for no-distortion:
        - Active panel: W:H = 1080:1152 → ratio 15:16
          crop_w = height * 15/16, crop_h = height
          If crop_w > width → crop_w = width, crop_h = width * 16/15
        - Listener panel: W:H = 1080:768 → ratio 45:32
          crop_w = height * 45/32, crop_h = height
          If crop_w > width → crop_w = width, crop_h = width * 32/45
        """
        active_x = decision["active_x"]
        listener_x = decision["listener_x"]

        # Panel dimensions in output
        active_h_out = 1152   # 60% of 1920
        listener_h_out = 768  # 40% of 1920

        # Active panel crop (aspect = 1080:1152 = 15:16)
        active_crop_w = int(height * 15 / 16)
        active_crop_h = height
        if active_crop_w > width:
            active_crop_w = width
            active_crop_h = int(width * 16 / 15)

        # Listener panel crop (aspect = 1080:768 = 45:32)
        listener_crop_w = int(height * 45 / 32)
        listener_crop_h = height
        if listener_crop_w > width:
            listener_crop_w = width
            listener_crop_h = int(width * 32 / 45)

        # Clamp X positions
        active_crop_x = self._clamp_x(active_x, active_crop_w, width)
        listener_crop_x = self._clamp_x(listener_x, listener_crop_w, width)

        # Y offset (center vertically)
        active_crop_y = max(0, (height - active_crop_h) // 2)
        listener_crop_y = max(0, (height - listener_crop_h) // 2)

        # FFmpeg filter: crop each panel, scale to output size, stack
        vf = (
            f"split=2[active][listener];"
            f"[active]crop={active_crop_w}:{active_crop_h}:{active_crop_x}:{active_crop_y},"
            f"scale=1080:{active_h_out},format=yuv420p[a];"
            f"[listener]crop={listener_crop_w}:{listener_crop_h}:{listener_crop_x}:{listener_crop_y},"
            f"scale=1080:{listener_h_out},format=yuv420p,"
            f"eq=brightness=-0.05[l];"  # Slight dim on listener (-5%)
            f"[a][l]vstack=inputs=2,setsar=1[vout]"
        )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", vf,
            "-map", "[vout]", "-map", "0:a?",
            *get_video_encoder_args("medium"),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            pc = decision.get("person_count", 2)
            logger.info(
                f"podcast_reframe: speaker emphasis grid OK "
                f"(active=x{active_x}, listener=x{listener_x}, "
                f"active_panel={active_crop_w}x{active_crop_h}→1080x{active_h_out})"
            )
            return {
                "output_path": output_path,
                "person_count": pc,
                "method": "podcast_speaker_emphasis",
                "active_speaker_track": decision.get("active_track_id"),
            }

        # Fallback: try equal 50/50 grid if emphasis fails
        if result.stderr:
            logger.warning(f"podcast_reframe: emphasis grid failed, trying 50/50: {result.stderr[-200:]}")

        fallback_decision = {
            "left_x": min(active_x, listener_x),
            "right_x": max(active_x, listener_x),
            "person_count": decision.get("person_count", 2),
        }
        return self._render_double_grid(video_path, output_path, width, height, fallback_decision)

    # ─── Utilities ────────────────────────────────────────────────────────

    MIN_FACE_DISTANCE_RATIO = 0.10  # Minimum 10% frame width between 2 faces to be different people

    def _filter_overlapping_faces(self, faces: List[float], width: int) -> List[float]:
        """Remove overlapping face detections (NMS for X positions).

        Prevents false positives where 1 person is detected as 2 faces
        (e.g. face + jaw, or face + ear area).

        Rule: if 2 face X positions are within 10% of frame width,
        they're the same person → keep only one.
        """
        if len(faces) < 2:
            return faces

        faces_sorted = sorted(faces)
        unique: List[float] = [faces_sorted[0]]
        min_distance = width * self.MIN_FACE_DISTANCE_RATIO

        for x in faces_sorted[1:]:
            if x - unique[-1] >= min_distance:
                unique.append(x)
            # else: skip — too close to previous, same person

        return unique

    def _get_vad_segments(self, video_path: str) -> Optional[List[Dict]]:
        """Extract speech segments using Silero VAD (if available).

        Returns list of {'start': float, 'end': float} for speech regions,
        or None if VAD unavailable (fallback: assume continuous speech).
        """
        try:
            from src.infrastructure.silero_vad import SileroVADProcessor
            vad = SileroVADProcessor()
            segments = vad.get_speech_timestamps(video_path)
            if segments:
                logger.info(f"podcast_reframe: VAD found {len(segments)} speech segments")
                return segments
        except Exception as e:
            logger.debug(f"podcast_reframe: VAD not available ({e}), using continuous speech assumption")
        return None

    def _clamp_x(self, face_x: int, crop_w: int, frame_w: int) -> int:
        """Clamp crop X so it stays within frame bounds."""
        x = face_x - crop_w // 2
        x = max(0, min(x, frame_w - crop_w))
        return x

    async def _center_crop(self, video_path: str, output_path: str) -> bool:
        """Center crop to 9:16."""
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", "crop=ih*9/16:ih,scale=1080:1920,format=yuv420p,setsar=1",
            *get_video_encoder_args("medium"),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000

    async def _simple_crop(self, video_path: str, output_path: str, target_aspect: str) -> bool:
        """Simple crop for non-9:16."""
        if target_aspect == "1:1":
            vf = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
        else:
            shutil.copy2(video_path, output_path)
            return True

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            *get_video_encoder_args("medium"),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000
