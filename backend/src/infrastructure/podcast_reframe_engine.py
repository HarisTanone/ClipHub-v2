"""PodcastReframeEngine — Speaker-Aware Face-Based Reframing.

Strategy: Detect faces → Track persons → Detect active speaker → Smart crop.

Pipeline:
  1. MediaPipe Face Detection → find faces per frame
  2. IoU Person Tracker → consistent person IDs across frames
  3. Active Speaker Detection (lip movement via Face Mesh) → who is talking
  4. Dynamic panning keeps the active speaker centered.

Rules:
  - Audio is ALWAYS stream-copied, never re-encoded through filter_complex
  - Aspect ratio math: 9:16 output = 1080x1920
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
from src.infrastructure.active_speaker_detector import ActiveSpeakerDetector, ActiveSpeakerResult, SpeakerSegment
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

        content_profile = kwargs.get("content_profile") or {}

        try:
            result = await asyncio.to_thread(
                self._pipeline,
                video_path,
                output_path,
                autogrid_enabled,
                content_profile,
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"podcast_reframe: pipeline error: {e}")

        success = await self._center_crop(video_path, output_path)
        return {"output_path": output_path if success else video_path, "person_count": 0, "method": "center_crop_fallback"}

    # ─── Pipeline ─────────────────────────────────────────────────────────

    def _pipeline(
        self,
        video_path: str,
        output_path: str,
        autogrid: bool,
        content_profile: Optional[dict] = None,
    ) -> Optional[dict]:
        import cv2
        cv2.setNumThreads(0)
        content_profile = content_profile or {}
        grid_strategy = str(
            content_profile.get("grid_strategy")
            or ("visual_auto" if autogrid else "disabled")
        )

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

        # Step 2: Active Speaker Detection. A single detected person is already
        # the active visual target; multiple people require disambiguation.
        speaker_result: Optional[ActiveSpeakerResult] = None
        if person_count > 1:
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
                        position_target_profiles=tracked_data.get("position_target_profiles"),
                    )
                except Exception as e:
                    logger.warning(f"podcast_reframe: lip+head fallback failed (non-fatal): {e}")
            if speaker_result is None:
                speaker_result = self._build_visual_fallback_speaker_result(
                    tracked_data=tracked_data,
                    fps=fps,
                    total_frames=total_frames,
                )
        elif person_count == 1:
            speaker_result = self._build_single_speaker_result(
                tracked_data=tracked_data,
                fps=fps,
                total_frames=total_frames,
            )

        self._log_active_speaker_summary(
            speaker_result=speaker_result,
            tracked_data=tracked_data,
            fps=fps,
            total_frames=total_frames,
        )

        # Step 3: Auto Grid decisions. These run before panning because Auto Grid
        # means "show multiple visual subjects at once", while panning follows
        # a single subject over time.
        if autogrid and grid_strategy == "gaming_gameplay_facecam":
            result = self._render_gaming_gameplay_facecam_grid(
                video_path, output_path, width, height, tracked_data
            )
            if result:
                return result

        if autogrid:
            grid_decision = self._decide_autogrid_layout(
                tracked_data=tracked_data,
                speaker_result=speaker_result,
                width=width,
            )
            if grid_decision["layout"] == "group":
                return self._render_group_grid(
                    video_path, output_path, width, height, grid_decision
                )
            if grid_decision["layout"] == "speaker_emphasis":
                return self._render_speaker_emphasis_grid(
                    video_path, output_path, width, height, grid_decision
                )
            if grid_decision["layout"] == "double":
                return self._render_double_grid(video_path, output_path, width, height, grid_decision)

        # Step 4: Dynamic Panning — single FFmpeg pass with smooth crop tracking
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
            min_speakers=None,
            max_speakers=None,
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
                visual_person_count = int(tracked_data.get("person_count") or 0)
                dynamic_min_speakers = None
                dynamic_max_speakers = (
                    visual_person_count if visual_person_count > 1 else None
                )
                logger.info(
                    "podcast_reframe: diarization speaker bounds "
                    f"min={dynamic_min_speakers or 'auto'}, "
                    f"max={dynamic_max_speakers or 'auto'} "
                    f"(visible_people={visual_person_count})"
                )
                diarization_result = loop.run_until_complete(
                    diarizer.diarize(
                        video_path,
                        min_speakers=dynamic_min_speakers,
                        max_speakers=dynamic_max_speakers,
                    )
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

    def _build_single_speaker_result(
        self,
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> ActiveSpeakerResult:
        """Build a speaker result when only one stable person is visible."""
        duration = total_frames / fps if fps > 0 else 0.0
        sample_frame_indices = tracked_data.get("sample_frame_indices") or [0]
        per_frame_speaker = {int(frame_idx): 0 for frame_idx in sample_frame_indices}
        logger.info(
            "podcast_reframe: single visible person detected → "
            "speaker=P0, centering target=P0"
        )
        return ActiveSpeakerResult(
            segments=[
                SpeakerSegment(
                    speaker_id=0,
                    start_time=0.0,
                    end_time=duration,
                    confidence=1.0,
                )
            ],
            dominant_speaker_id=0,
            dominant_ratio=1.0,
            per_frame_speaker=per_frame_speaker,
            total_speakers=1,
        )

    def _build_visual_fallback_speaker_result(
        self,
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> Optional[ActiveSpeakerResult]:
        """Build a conservative visual target when speaker scoring is unavailable."""
        track_to_position = {
            int(track_id): int(position_id)
            for track_id, position_id in (tracked_data.get("track_to_position") or {}).items()
        }
        per_frame_tracked = tracked_data.get("per_frame_tracked") or []
        sample_frame_indices = tracked_data.get("sample_frame_indices") or []

        if not track_to_position or not per_frame_tracked:
            return None

        position_hits: Dict[int, int] = defaultdict(int)
        position_areas: Dict[int, List[float]] = defaultdict(list)

        for frame_tracked in per_frame_tracked:
            for detection in frame_tracked:
                position_id = track_to_position.get(int(detection.track_id))
                if position_id is None:
                    continue
                position_hits[position_id] += 1
                position_areas[position_id].append(float(detection.bbox.area))

        if not position_hits:
            return None

        fallback_position = max(
            position_hits,
            key=lambda position_id: (
                position_hits[position_id],
                float(np.median(position_areas[position_id]))
                if position_areas[position_id]
                else 0.0,
            ),
        )
        duration = total_frames / fps if fps > 0 else 0.0
        per_frame_speaker = {
            int(frame_idx): fallback_position
            for frame_idx in sample_frame_indices
        }
        median_area = (
            float(np.median(position_areas[fallback_position]))
            if position_areas[fallback_position]
            else 0.0
        )

        logger.info(
            "podcast_reframe: active speaker visual fallback → "
            f"target=P{fallback_position}, "
            f"hits={position_hits[fallback_position]}, "
            f"median_face_area={median_area:.0f}"
        )

        return ActiveSpeakerResult(
            segments=[
                SpeakerSegment(
                    speaker_id=fallback_position,
                    start_time=0.0,
                    end_time=duration,
                    confidence=0.25,
                )
            ],
            dominant_speaker_id=fallback_position,
            dominant_ratio=1.0,
            per_frame_speaker=per_frame_speaker,
            total_speakers=1,
        )

    def _log_active_speaker_summary(
        self,
        speaker_result: Optional[ActiveSpeakerResult],
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> None:
        """Log who the reframe stage thinks is speaking."""
        if speaker_result is None:
            logger.info(
                "podcast_reframe: active speaker unavailable → "
                "centering will follow visible face motion"
            )
            return

        position_profiles = self._normalise_position_profiles(
            tracked_data.get("position_target_profiles") or {}
        )
        frame_counts: Dict[int, int] = {}
        for speaker_id in speaker_result.per_frame_speaker.values():
            frame_counts[int(speaker_id)] = frame_counts.get(int(speaker_id), 0) + 1

        counts_log = ", ".join(
            f"P{speaker_id}:{count}"
            for speaker_id, count in sorted(frame_counts.items())
        )
        positions_log = ", ".join(
            self._format_profile_log(f"P{speaker_id}", position_profiles[speaker_id])
            for speaker_id in sorted(position_profiles)
        )
        segment_log = ", ".join(
            f"P{s.speaker_id}@{s.start_time:.1f}-{s.end_time:.1f}s"
            for s in speaker_result.segments[:10]
        )
        if len(speaker_result.segments) > 10:
            segment_log += ", ..."

        duration = total_frames / fps if fps > 0 else 0.0
        logger.info(
            "podcast_reframe: active speaker summary "
            f"duration={duration:.1f}s, "
            f"visible_people={tracked_data.get('person_count', 0)}, "
            f"speakers={speaker_result.total_speakers}, "
            f"dominant={self._format_position_id(speaker_result.dominant_speaker_id)} "
            f"({speaker_result.dominant_ratio:.0%}), "
            f"frame_targets={{{counts_log}}}, "
            f"positions={{{positions_log}}}, "
            f"segments=[{segment_log}]"
        )

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
                "stable_position_profiles": Dict[int, dict],  # track_id → X/Y/size
                "position_targets": Dict[int, float],  # position_id → median X
                "position_target_profiles": Dict[int, dict],  # position_id → X/Y/size
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
                "frame_face_counts": [],
                "sample_frame_indices": [],
                "sample_timestamps": [],
                "person_count": 0,
                "stable_positions": {},
                "stable_position_profiles": {},
                "position_targets": {},
                "position_target_profiles": {},
                "track_to_position": {},
            }

        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

        per_frame_faces: List[List[float]] = []
        per_frame_tracked: List[List[TrackedDetection]] = []
        frame_face_counts: List[int] = []
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

            # Update tracker with this frame's detections. Duplicate detector
            # hits should be removed by actual box overlap, not by X-position
            # alone; front/back speakers can share almost the same X position.
            frame_bboxes = self._filter_overlapping_bboxes(frame_bboxes, width, height)
            frame_faces = [bbox.center_x for bbox in frame_bboxes]

            tracked = self._tracker.update(frame_bboxes, frame_idx)

            per_frame_faces.append(frame_faces)
            per_frame_tracked.append(tracked)
            frame_face_counts.append(len(frame_bboxes))
            sample_frame_indices.append(frame_idx)
            sample_timestamps.append(frame_idx / fps)

        cap.release()

        position_model = self._build_position_model(per_frame_tracked, width, height)
        person_count = position_model["person_count"]
        stable_positions = position_model["stable_positions"]
        stable_position_profiles = position_model["stable_position_profiles"]
        position_targets = position_model["position_targets"]
        position_target_profiles = position_model["position_target_profiles"]
        track_to_position = position_model["track_to_position"]
        max_faces_in_frame = max(frame_face_counts) if frame_face_counts else 0
        median_faces_in_frame = float(np.median(frame_face_counts)) if frame_face_counts else 0.0
        frames_with_faces = sum(1 for count in frame_face_counts if count > 0)

        logger.info(
            "podcast_reframe: face scan "
            f"samples={len(frame_face_counts)}, "
            f"frames_with_faces={frames_with_faces}/{len(frame_face_counts)}, "
            f"faces_per_frame=min/median/max="
            f"{(min(frame_face_counts) if frame_face_counts else 0)}/"
            f"{median_faces_in_frame:.1f}/{max_faces_in_frame}"
        )

        logger.info(
            f"podcast_reframe: tracked {len(stable_positions)} unique tracks, "
            f"person_count={person_count}, "
            f"tracks={{{', '.join(self._format_profile_log(f'T{k}', stable_position_profiles.get(k, {'x': v})) for k, v in stable_positions.items())}}}, "
            f"positions={{{', '.join(self._format_profile_log(f'P{k}', position_target_profiles.get(k, {'x': v})) for k, v in position_targets.items())}}}"
        )

        return {
            "per_frame_faces": per_frame_faces,
            "per_frame_tracked": per_frame_tracked,
            "frame_face_counts": frame_face_counts,
            "max_faces_in_frame": max_faces_in_frame,
            "median_faces_in_frame": median_faces_in_frame,
            "sample_frame_indices": sample_frame_indices,
            "sample_timestamps": sample_timestamps,
            "person_count": person_count,
            "stable_positions": stable_positions,
            "stable_position_profiles": stable_position_profiles,
            "position_targets": position_targets,
            "position_target_profiles": position_target_profiles,
            "track_to_position": track_to_position,
        }

    def _build_position_model(
        self,
        per_frame_tracked: List[List[TrackedDetection]],
        width: int,
        height: int,
    ) -> dict:
        """Build stable person positions from all sampled tracker output.

        The tracker may prune a track if a face disappears near the end of a
        clip. This model keeps historical observations and clusters re-created
        tracks that land in the same seat. It uses X, Y, and face size so
        front/back panelists with similar horizontal positions remain distinct.
        """
        track_profiles: Dict[int, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for frame_tracked in per_frame_tracked:
            for detection in frame_tracked:
                profile = track_profiles[detection.track_id]
                profile["x"].append(detection.bbox.center_x)
                profile["y"].append(detection.bbox.center_y)
                profile["width"].append(detection.bbox.width)
                profile["height"].append(detection.bbox.height)
                profile["area"].append(detection.bbox.area)

        if not track_profiles:
            return {
                "person_count": 0,
                "stable_positions": {},
                "stable_position_profiles": {},
                "position_targets": {},
                "position_target_profiles": {},
                "track_to_position": {},
            }

        min_hits = 2 if len(per_frame_tracked) >= 6 else 1
        filtered = {
            track_id: values
            for track_id, values in track_profiles.items()
            if len(values.get("x", [])) >= min_hits
        }
        if not filtered:
            filtered = dict(track_profiles)

        stable_position_profiles = {
            track_id: self._median_profile(values)
            for track_id, values in filtered.items()
        }
        stable_positions = {
            track_id: profile["x"]
            for track_id, profile in stable_position_profiles.items()
        }

        clusters: List[dict] = []
        cluster_threshold = 0.11

        for track_id, profile in sorted(
            stable_position_profiles.items(),
            key=lambda kv: (kv[1]["x"], kv[1]["y"]),
        ):
            best_cluster_idx: Optional[int] = None
            best_distance = float("inf")
            for idx, cluster in enumerate(clusters):
                distance = self._profile_distance(
                    profile, cluster["profile"], width, height
                )
                if distance < best_distance:
                    best_distance = distance
                    best_cluster_idx = idx

            if best_cluster_idx is not None and best_distance <= cluster_threshold:
                cluster = clusters[best_cluster_idx]
                cluster["track_ids"].append(track_id)
                cluster["profiles"].append(profile)
                cluster["profile"] = self._merge_profiles(cluster["profiles"])
            else:
                clusters.append({
                    "track_ids": [track_id],
                    "profiles": [profile],
                    "profile": dict(profile),
                })

        position_targets: Dict[int, float] = {}
        position_target_profiles: Dict[int, Dict[str, float]] = {}
        track_to_position: Dict[int, int] = {}
        for position_id, cluster in enumerate(
            sorted(clusters, key=lambda cluster: (cluster["profile"]["x"], cluster["profile"]["y"]))
        ):
            position_target_profiles[position_id] = cluster["profile"]
            position_targets[position_id] = cluster["profile"]["x"]
            for track_id in cluster["track_ids"]:
                track_to_position[track_id] = position_id

        return {
            "person_count": len(position_targets),
            "stable_positions": stable_positions,
            "stable_position_profiles": stable_position_profiles,
            "position_targets": position_targets,
            "position_target_profiles": position_target_profiles,
            "track_to_position": track_to_position,
        }

    # ─── Layout Decision (Speaker-Aware) ─────────────────────────────────

    def _decide_autogrid_layout(
        self,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        width: int,
    ) -> dict:
        """Choose grid only when multiple people are visible in-frame.

        This matches the product rule: if the edit focuses one person at a
        time, keep a single smart camera. If 2+ people are simultaneously
        visible, use grid so viewers can read both/all reactions.
        """
        per_frame_faces = tracked_data.get("per_frame_faces") or []
        position_targets = {
            int(pos_id): float(x)
            for pos_id, x in (tracked_data.get("position_targets") or {}).items()
        }
        person_count = int(tracked_data.get("person_count") or 0)

        if not per_frame_faces or person_count < 2:
            return {"layout": "single", "person_count": person_count}

        multi_face_frames = 0
        left_positions: List[float] = []
        right_positions: List[float] = []

        for frame_faces in per_frame_faces:
            if len(frame_faces) < 2:
                continue
            sorted_faces = sorted(frame_faces)
            leftmost = sorted_faces[0]
            rightmost = sorted_faces[-1]
            separation = rightmost - leftmost
            if separation >= width * self.MIN_SEPARATION_RATIO:
                multi_face_frames += 1
                left_positions.append(leftmost)
                right_positions.append(rightmost)

        coexist_ratio = multi_face_frames / len(per_frame_faces) if per_frame_faces else 0.0
        if coexist_ratio < self.MIN_COEXIST_RATIO or not left_positions or not right_positions:
            logger.info(
                "podcast_reframe: autogrid skipped "
                f"(coexist={coexist_ratio:.0%}, visible_people={person_count})"
            )
            return {"layout": "single", "person_count": person_count}

        sorted_positions = sorted(position_targets.items(), key=lambda item: item[1])
        if len(sorted_positions) < 2:
            left_x = int(np.median(left_positions))
            right_x = int(np.median(right_positions))
            sorted_positions = [(0, left_x), (1, right_x)]

        latest_speaker_id: Optional[int] = None
        if speaker_result and speaker_result.per_frame_speaker:
            latest_frame = max(speaker_result.per_frame_speaker)
            latest_speaker_id = int(speaker_result.per_frame_speaker[latest_frame])
        elif speaker_result and speaker_result.dominant_speaker_id is not None:
            latest_speaker_id = int(speaker_result.dominant_speaker_id)

        position_to_x = dict(sorted_positions)
        if latest_speaker_id in position_to_x:
            active_id = latest_speaker_id
            active_x = position_to_x[active_id]
        else:
            active_id, active_x = sorted_positions[0]

        if person_count >= 3 and len(sorted_positions) >= 3:
            xs = [x for _, x in sorted_positions]
            logger.info(
                "podcast_reframe: AUTO GROUP GRID "
                f"(people={person_count}, coexist={coexist_ratio:.0%}, active=P{active_id})"
            )
            return {
                "layout": "group",
                "active_x": int(active_x),
                "group_x": int(np.median(xs)),
                "person_count": person_count,
                "active_track_id": active_id,
            }

        listener_candidates = [
            (pos_id, x)
            for pos_id, x in sorted_positions
            if pos_id != active_id
        ]
        listener_id, listener_x = max(
            listener_candidates or sorted_positions,
            key=lambda item: abs(item[1] - active_x),
        )

        if speaker_result:
            logger.info(
                "podcast_reframe: AUTO SPEAKER GRID "
                f"(active=P{active_id}, listener=P{listener_id}, coexist={coexist_ratio:.0%})"
            )
            return {
                "layout": "speaker_emphasis",
                "active_x": int(active_x),
                "listener_x": int(listener_x),
                "active_track_id": active_id,
                "listener_track_id": listener_id,
                "person_count": person_count,
            }

        left_x = int(min(x for _, x in sorted_positions))
        right_x = int(max(x for _, x in sorted_positions))
        logger.info(
            "podcast_reframe: AUTO DOUBLE GRID "
            f"(L={left_x}, R={right_x}, coexist={coexist_ratio:.0%})"
        )
        return {
            "layout": "double",
            "left_x": left_x,
            "right_x": right_x,
            "person_count": person_count,
        }

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
          2. If no speaker target is available → fallback to visual face clusters
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
        if speaker_result and person_count > 1 and (position_targets or stable_positions):
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

            # Dynamic panning should handle speaker changes. If it fails and we
            # still have speaker data, use the latest active speaker as a static
            # fallback instead of assuming a two-person layout.
            latest_speaker_id: Optional[int] = None
            if speaker_result.per_frame_speaker:
                latest_frame = max(speaker_result.per_frame_speaker)
                latest_speaker_id = speaker_result.per_frame_speaker[latest_frame]
            static_speaker_id = (
                latest_speaker_id
                if latest_speaker_id is not None
                else dominant_id
            )
            static_speaker_x = position_to_x.get(static_speaker_id)
            if static_speaker_x is not None:
                logger.info(
                    "podcast_reframe: STATIC SPEAKER FALLBACK "
                    f"(speaker=P{static_speaker_id}, x={static_speaker_x:.0f}, "
                    f"dominance={dominant_ratio:.0%})"
                )
                return {
                    "layout": "single",
                    "crop_x": int(static_speaker_x),
                    "person_count": person_count,
                    "method_detail": "speaker_static_single",
                }

            # Legacy visual grid fallback. Normally dynamic panning handles
            # speaker switching before this path is reached.
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

        # ─── True single person fallback ──────────────────────────────────
        # Only reach here if genuinely 1 person or clusters too close
        if person_count > 1 and len(all_x) > 5:
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
    SPEAKER_TARGET_PROFILE_MISMATCH = 0.18  # Normalized X/Y/size mismatch limit for 2D seat matching.

    def _choose_panning_target_x(
        self,
        frame_faces: List[float],
        frame_tracked: List[TrackedDetection],
        speaker_result: Optional[ActiveSpeakerResult],
        frame_idx_approx: int,
        position_targets: Dict[int, float],
        position_target_profiles: Dict[int, Dict[str, float]],
        track_to_position: Dict[int, int],
        frame_width: int,
        frame_height: int,
        last_center: Optional[float] = None,
    ) -> Tuple[Optional[int], Optional[TrackedDetection], Optional[int], str]:
        """Pick the crop center, preferring the active speaker's stable seat."""
        active_speaker: Optional[int] = None
        target_x_hint: Optional[float] = None
        target_profile: Optional[Dict[str, float]] = None

        if speaker_result and speaker_result.per_frame_speaker:
            closest_frame = min(
                speaker_result.per_frame_speaker.keys(),
                key=lambda f: abs(f - frame_idx_approx),
                default=None,
            )
            if closest_frame is not None:
                active_speaker = speaker_result.per_frame_speaker[closest_frame]
                target_x_hint = position_targets.get(active_speaker)
                target_profile = position_target_profiles.get(active_speaker)
                if target_x_hint is None and target_profile:
                    target_x_hint = target_profile.get("x")

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
                return int(target_detection.bbox.center_x), target_detection, active_speaker, "track"

            if target_profile and frame_tracked:
                target_detection = min(
                    frame_tracked,
                    key=lambda d: self._bbox_profile_distance(
                        d.bbox, target_profile, frame_width, frame_height
                    ),
                )
                profile_distance = self._bbox_profile_distance(
                    target_detection.bbox, target_profile, frame_width, frame_height
                )
                if profile_distance <= self.SPEAKER_TARGET_PROFILE_MISMATCH:
                    return int(target_detection.bbox.center_x), target_detection, active_speaker, "profile"

                if target_x_hint is not None:
                    logger.debug(
                        "podcast_reframe: visible faces do not match active speaker "
                        "profile P%s (distance=%.3f); holding target seat x=%.1f",
                        active_speaker,
                        profile_distance,
                        target_x_hint,
                    )
                    return int(target_x_hint), None, active_speaker, "profile_hold"

            if target_x_hint is not None:
                if not frame_faces:
                    return int(target_x_hint), None, active_speaker, "seat_hold"

                nearest_face = float(min(frame_faces, key=lambda x: abs(x - target_x_hint)))
                mismatch_threshold = frame_width * self.SPEAKER_TARGET_MISMATCH_RATIO

                if len(frame_faces) == 1 and abs(nearest_face - target_x_hint) > mismatch_threshold:
                    logger.debug(
                        "podcast_reframe: single visible face is far from active speaker "
                        "target (face=%.1f, target=%.1f); holding speaker seat",
                        nearest_face,
                        target_x_hint,
                    )
                    return int(target_x_hint), None, active_speaker, "seat_hold"

                return int(nearest_face), None, active_speaker, "nearest_x"

            if frame_faces:
                sorted_faces = sorted(frame_faces)
                if 0 <= active_speaker < len(sorted_faces):
                    return int(sorted_faces[active_speaker]), None, active_speaker, "visible_index"

        if not frame_faces:
            return None, None, active_speaker, "no_face"

        if last_center is not None:
            return int(min(frame_faces, key=lambda x: abs(x - last_center))), None, None, "last_center"

        return int(np.median(frame_faces)), None, None, "median_face"

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
        keyframes: List[Tuple[float, int, Optional[int], str]] = []
        # (time_sec, target_crop_x, active_position_id, target_source)
        per_frame_tracked = tracked_data.get("per_frame_tracked", [])
        sample_frame_indices = tracked_data.get("sample_frame_indices", [])
        sample_timestamps = tracked_data.get("sample_timestamps", [])
        position_targets = {
            int(k): float(v)
            for k, v in (tracked_data.get("position_targets") or {}).items()
        }
        position_target_profiles = self._normalise_position_profiles(
            tracked_data.get("position_target_profiles") or {}
        )
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

            cx, target_detection, active_position_id, target_source = self._choose_panning_target_x(
                frame_faces=frame_faces,
                frame_tracked=frame_tracked,
                speaker_result=speaker_result,
                frame_idx_approx=frame_idx_approx,
                position_targets=position_targets,
                position_target_profiles=position_target_profiles,
                track_to_position=track_to_position,
                frame_width=width,
                frame_height=height,
                last_center=last_center,
            )

            if cx is None:
                # No reliable face or speaker target → hold previous position
                if keyframes:
                    keyframes.append((t, keyframes[-1][1], keyframes[-1][2], "hold"))
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

            keyframes.append((t, crop_x, active_position_id, target_source))

        if not keyframes:
            return None

        # Stabilize with cluster lock + dead zone + hold minimum
        # 1. Cluster lock: if all positions within PAN_CLUSTER_THRESHOLD → lock camera
        all_kf_x = [x for _, x, _, _ in keyframes]
        x_spread = max(all_kf_x) - min(all_kf_x) if all_kf_x else 0

        if x_spread < self.PAN_CLUSTER_THRESHOLD:
            # All detections in same area — lock to median (home position)
            home_x = int(np.median(all_kf_x))
            logger.info(
                f"podcast_reframe: CLUSTER LOCK (spread={x_spread}px < {self.PAN_CLUSTER_THRESHOLD}px) "
                f"→ locked at x={home_x}"
            )
            first_speaker = keyframes[0][2] if keyframes else None
            stabilized = [(0.0, home_x, first_speaker, "cluster_lock")]
        else:
            # 2. Dead zone + hold minimum
            stabilized: List[Tuple[float, int, Optional[int], str]] = [keyframes[0]]
            for t, x, speaker_id, source in keyframes[1:]:
                last_t, last_x, last_speaker_id, _ = stabilized[-1]
                movement = abs(x - last_x)
                time_since_last = t - last_t

                speaker_changed = (
                    speaker_id is not None
                    and last_speaker_id is not None
                    and speaker_id != last_speaker_id
                )
                if (
                    movement >= self.PAN_DEAD_ZONE_PX
                    and (time_since_last >= self.PAN_HOLD_MIN_SEC or speaker_changed)
                ):
                    stabilized.append((t, x, speaker_id, source))

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
            logger.info(
                "podcast_reframe: static crop at "
                f"x={stabilized[0][1]}, "
                f"speaker={self._format_position_id(stabilized[0][2])}, "
                f"source={stabilized[0][3]}"
            )
        else:
            crop_x_expr = self._build_panning_expression(
                [(t, x) for t, x, _, _ in stabilized],
                0,
            )
            for i, (t, x, speaker_id, source) in enumerate(stabilized):
                logger.info(
                    f"  pan[{i}] t={t:.1f}s → x={x}, "
                    f"speaker={self._format_position_id(speaker_id)}, source={source}"
                )

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
            pc = tracked_data["person_count"]
            return {
                "output_path": output_path,
                "person_count": pc,
                "method": "podcast_dynamic_panning",
                "keyframes": len(stabilized),
                "subtitle_position_y": 85.0,
                "subtitle_max_width_pct": 82.0 if pc >= 2 else 90.0,
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
            return {
                "output_path": output_path,
                "person_count": pc,
                "method": method_detail,
                "subtitle_position_y": 85.0,
                "subtitle_max_width_pct": 90.0,
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: single crop failed: {result.stderr[-300:]}")
        return None

    # ─── Render: Gaming Gameplay + Facecam Grid ────────────────────────

    def _render_gaming_gameplay_facecam_grid(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        tracked_data: dict,
    ) -> Optional[dict]:
        """Gaming grid: gameplay on top, detected person/facecam below."""
        profile = self._primary_face_profile(tracked_data)
        if not profile:
            logger.info("podcast_reframe: gaming grid needs a face → fallback to normal framing")
            return None

        top_h_out = 1248
        face_h_out = 672
        face_crop_x, face_crop_y, face_crop_w, face_crop_h = self._face_panel_crop(
            profile=profile,
            frame_w=width,
            frame_h=height,
            panel_w=1080,
            panel_h=face_h_out,
            face_height_fraction=0.38,
        )

        vf = (
            f"split=3[topbg][game][face];"
            f"[topbg]scale=1080:{top_h_out}:force_original_aspect_ratio=increase,"
            f"crop=1080:{top_h_out},gblur=sigma=18,eq=brightness=-0.10[bg];"
            f"[game]scale=1080:{top_h_out}:force_original_aspect_ratio=decrease,"
            f"format=rgba,pad=1080:{top_h_out}:(ow-iw)/2:(oh-ih)/2:color=black@0[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[top];"
            f"[face]crop={face_crop_w}:{face_crop_h}:{face_crop_x}:{face_crop_y},"
            f"scale=1080:{face_h_out},format=yuv420p[person];"
            f"[top][person]vstack=inputs=2,setsar=1[vout]"
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
            logger.info(
                "podcast_reframe: gaming gameplay/facecam grid OK "
                f"(face_crop={face_crop_w}x{face_crop_h}@{face_crop_x},{face_crop_y})"
            )
            return {
                "output_path": output_path,
                "person_count": int(tracked_data.get("person_count") or 1),
                "method": "gaming_gameplay_facecam_grid",
                "grid_layout": "gaming",
                "subtitle_position_y": 58.0,
                "subtitle_max_width_pct": 88.0,
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: gaming grid failed: {result.stderr[-300:]}")
        return None

    # ─── Render: Group Grid (3+ visible people) ────────────────────────

    def _render_group_grid(
        self, video_path: str, output_path: str, width: int, height: int, decision: dict
    ) -> Optional[dict]:
        """Group grid: active speaker top, wider group context below."""
        active_x = decision["active_x"]
        group_x = decision["group_x"]

        active_h_out = 1152
        group_h_out = 768

        active_crop_w = int(height * 15 / 16)
        active_crop_h = height
        if active_crop_w > width:
            active_crop_w = width
            active_crop_h = int(width * 16 / 15)

        group_crop_w = int(height * 45 / 32)
        group_crop_h = height
        if group_crop_w > width:
            group_crop_w = width
            group_crop_h = int(width * 32 / 45)

        active_crop_x = self._clamp_x(active_x, active_crop_w, width)
        group_crop_x = self._clamp_x(group_x, group_crop_w, width)
        active_crop_y = max(0, (height - active_crop_h) // 2)
        group_crop_y = max(0, (height - group_crop_h) // 2)

        vf = (
            f"split=2[active][group];"
            f"[active]crop={active_crop_w}:{active_crop_h}:{active_crop_x}:{active_crop_y},"
            f"scale=1080:{active_h_out},format=yuv420p[a];"
            f"[group]crop={group_crop_w}:{group_crop_h}:{group_crop_x}:{group_crop_y},"
            f"scale=1080:{group_h_out},format=yuv420p,eq=brightness=-0.04[g];"
            f"[a][g]vstack=inputs=2,setsar=1[vout]"
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
            pc = decision.get("person_count", 3)
            logger.info(
                f"podcast_reframe: group grid OK (people={pc}, active=x{active_x}, group=x{group_x})"
            )
            return {
                "output_path": output_path,
                "person_count": pc,
                "method": "podcast_group_grid",
                "active_speaker_track": decision.get("active_track_id"),
                "subtitle_position_y": 52.0,
                "subtitle_max_width_pct": 84.0,
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: group grid failed: {result.stderr[-300:]}")
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

        SIMPLEST CORRECT approach for side-by-side podcast framing:
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
            return {
                "output_path": output_path,
                "person_count": pc,
                "method": "podcast_double_grid",
                "subtitle_position_y": 43.0,
                "subtitle_max_width_pct": 85.0,
            }

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
                "subtitle_position_y": 52.0,
                "subtitle_max_width_pct": 85.0,
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

    def _primary_face_profile(self, tracked_data: dict) -> Optional[dict]:
        """Pick the most useful face profile for a person/facecam panel."""
        profiles = self._normalise_position_profiles(
            tracked_data.get("position_target_profiles") or {}
        )
        if not profiles:
            profiles = self._normalise_position_profiles(
                tracked_data.get("stable_position_profiles") or {}
            )
        if not profiles:
            return None
        return max(
            profiles.values(),
            key=lambda profile: float(profile.get("area", 0.0)),
        )

    def _face_panel_crop(
        self,
        profile: dict,
        frame_w: int,
        frame_h: int,
        panel_w: int,
        panel_h: int,
        face_height_fraction: float,
    ) -> Tuple[int, int, int, int]:
        """Compute a tight crop around a face while preserving panel aspect."""
        aspect = panel_w / panel_h
        face_h = max(1.0, float(profile.get("height", frame_h * 0.2)))
        crop_h = max(face_h / max(0.2, face_height_fraction), frame_h * 0.18)
        crop_h = min(float(frame_h), crop_h)
        crop_w = crop_h * aspect
        if crop_w > frame_w:
            crop_w = float(frame_w)
            crop_h = crop_w / aspect

        crop_w_i = self._even(crop_w)
        crop_h_i = self._even(crop_h)
        center_x = float(profile.get("x", frame_w / 2))
        center_y = float(profile.get("y", frame_h / 2))

        # Slight upward bias: eyes sit above center, so leave more room below.
        crop_x = int(center_x - crop_w_i / 2)
        crop_y = int(center_y - crop_h_i * 0.42)
        crop_x = max(0, min(frame_w - crop_w_i, crop_x))
        crop_y = max(0, min(frame_h - crop_h_i, crop_y))
        return self._even(crop_x), self._even(crop_y), crop_w_i, crop_h_i

    def _even(self, value: float) -> int:
        return max(2, int(value) // 2 * 2)

    MIN_FACE_DISTANCE_RATIO = 0.10  # Minimum 10% frame width between 2 faces to be different people

    def _filter_overlapping_bboxes(
        self,
        bboxes: List[BBox],
        width: int,
        height: int,
    ) -> List[BBox]:
        """Remove duplicate face detections using 2D overlap.

        X-only filtering breaks four-person panels where front/back speakers
        share a similar horizontal position. This keeps boxes unless they are
        genuinely overlapping or nearly identical in X/Y/size.
        """
        if len(bboxes) < 2:
            return bboxes

        selected: List[BBox] = []
        center_x_threshold = width * 0.04
        center_y_threshold = height * 0.06

        for bbox in sorted(bboxes, key=lambda b: b.area, reverse=True):
            is_duplicate = False
            for existing in selected:
                iou = SimpleIoUTracker._compute_iou(bbox, existing)
                area_ratio = min(bbox.area, existing.area) / max(bbox.area, existing.area, 1.0)
                center_close = (
                    abs(bbox.center_x - existing.center_x) <= center_x_threshold
                    and abs(bbox.center_y - existing.center_y) <= center_y_threshold
                )
                if iou >= 0.35 or (center_close and area_ratio >= 0.45):
                    is_duplicate = True
                    break
            if not is_duplicate:
                selected.append(bbox)

        return sorted(selected, key=lambda b: (b.center_x, b.center_y))

    @staticmethod
    def _median_profile(values: Dict[str, List[float]]) -> Dict[str, float]:
        """Return a median face profile for one tracker ID."""
        return {
            "x": float(np.median(values.get("x") or [0.0])),
            "y": float(np.median(values.get("y") or [0.0])),
            "width": float(np.median(values.get("width") or [0.0])),
            "height": float(np.median(values.get("height") or [0.0])),
            "area": float(np.median(values.get("area") or [0.0])),
        }

    @staticmethod
    def _merge_profiles(profiles: List[Dict[str, float]]) -> Dict[str, float]:
        """Merge multiple track profiles that represent the same seat/person."""
        return {
            "x": float(np.median([p.get("x", 0.0) for p in profiles])),
            "y": float(np.median([p.get("y", 0.0) for p in profiles])),
            "width": float(np.median([p.get("width", 0.0) for p in profiles])),
            "height": float(np.median([p.get("height", 0.0) for p in profiles])),
            "area": float(np.median([p.get("area", 0.0) for p in profiles])),
        }

    @staticmethod
    def _profile_distance(
        a: Dict[str, float],
        b: Dict[str, float],
        width: int,
        height: int,
    ) -> float:
        """Weighted normalized distance between two stable face profiles."""
        frame_w = max(float(width), 1.0)
        frame_h = max(float(height), 1.0)
        frame_diag = max((frame_w * frame_w + frame_h * frame_h) ** 0.5, 1.0)
        size_a = max(a.get("area", 0.0), 0.0) ** 0.5
        size_b = max(b.get("area", 0.0), 0.0) ** 0.5
        dx = abs(a.get("x", 0.0) - b.get("x", 0.0)) / frame_w
        dy = (
            abs(a["y"] - b["y"]) / frame_h
            if "y" in a and "y" in b
            else 0.0
        )
        ds = (
            abs(size_a - size_b) / frame_diag
            if "area" in a and "area" in b
            else 0.0
        )
        return dx + dy * 0.85 + ds * 0.90

    def _bbox_profile_distance(
        self,
        bbox: BBox,
        profile: Dict[str, float],
        width: int,
        height: int,
    ) -> float:
        """Distance between a live detection box and a stable speaker profile."""
        return self._profile_distance(
            {
                "x": bbox.center_x,
                "y": bbox.center_y,
                "width": bbox.width,
                "height": bbox.height,
                "area": bbox.area,
            },
            profile,
            width,
            height,
        )

    @staticmethod
    def _normalise_position_profiles(
        profiles: Dict[int, Dict[str, float]]
    ) -> Dict[int, Dict[str, float]]:
        """Coerce serialized profile keys/values back to numeric form."""
        cleaned: Dict[int, Dict[str, float]] = {}
        for key, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            try:
                position_id = int(key)
                cleaned[position_id] = {
                    field: float(profile[field])
                    for field in ("x", "y", "width", "height", "area")
                    if field in profile
                }
            except (TypeError, ValueError):
                continue
        return cleaned

    @staticmethod
    def _format_profile_log(label: str, profile: Dict[str, float]) -> str:
        """Compact log format for 2D face-position debugging."""
        x = float(profile.get("x", 0.0))
        y = float(profile.get("y", 0.0))
        w = float(profile.get("width", 0.0))
        h = float(profile.get("height", 0.0))
        if w and h:
            return f"{label}:({x:.0f},{y:.0f},{w:.0f}x{h:.0f})"
        return f"{label}:{x:.0f}"

    @staticmethod
    def _format_position_id(position_id: Optional[int]) -> str:
        """Log-friendly active speaker/position label."""
        return f"P{position_id}" if position_id is not None else "auto"

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
