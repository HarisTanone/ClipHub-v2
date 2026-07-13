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

    # Every grid panel is exactly half of the 1080x1920 output.
    GRID_PANEL_HEIGHT = 960
    DOMINANCE_SINGLE_CROP = 0.75     # If dominant ≥75% → use single crop instead of grid
    GRID_BASE_ZOOM = 1.08            # Gentle default crop; avoids excessive background.
    GRID_MAX_ZOOM = 1.40             # Hard ceiling so faces never become uncomfortably large.
    GRID_FACE_MARGIN = 0.35          # Minimum face-side breathing room inside a panel.
    GRID_ENTER_SAMPLES = 2           # Confirm a second person before opening the grid.
    GRID_EXIT_SAMPLES = 3            # Tolerate short detector misses before closing the grid.
    VALID_TRANSITIONS = {"cut", "fade", "slide", "zoom"}

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
        transition_style = str(kwargs.get("transition_style") or "cut").lower()
        if transition_style not in self.VALID_TRANSITIONS:
            transition_style = "cut"
        try:
            transition_duration = float(kwargs.get("transition_duration", 0.35))
        except (TypeError, ValueError):
            transition_duration = 0.35
        transition_duration = max(0.0, min(1.0, transition_duration))

        try:
            result = await asyncio.to_thread(
                self._pipeline,
                video_path,
                output_path,
                autogrid_enabled,
                content_profile,
                transition_style,
                transition_duration,
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
        transition_style: str = "cut",
        transition_duration: float = 0.35,
    ) -> Optional[dict]:
        import cv2
        cv2.setNumThreads(0)
        content_profile = content_profile or {}

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

        # Step 3: Auto Grid decisions. Grid is only allowed for two distinct,
        # concurrently visible tracked identities. Content classification alone
        # (for example a false "gaming" label) must never duplicate one person.
        if autogrid:
            grid_decision = self._decide_autogrid_layout(
                tracked_data=tracked_data,
                speaker_result=speaker_result,
                width=width,
                height=height,
            )
            if grid_decision["layout"] == "double":
                grid_decision["transition_style"] = transition_style
                grid_decision["transition_duration"] = transition_duration
                layout_events = grid_decision.get("layout_events") or []
                if len(layout_events) > 1:
                    dynamic_grid = self._render_dynamic_auto_grid(
                        video_path=video_path,
                        output_path=output_path,
                        width=width,
                        height=height,
                        fps=fps,
                        duration=(total_frames / fps if fps > 0 else 0.0),
                        tracked_data=tracked_data,
                        speaker_result=speaker_result,
                        decision=grid_decision,
                    )
                    if dynamic_grid:
                        return dynamic_grid
                elif layout_events and layout_events[0].get("layout") == "double":
                    return self._render_double_grid(
                        video_path, output_path, width, height, grid_decision
                    )

        # Step 4: Dynamic Panning — single FFmpeg pass with smooth crop tracking
        # Builds a time-based crop X expression that follows the active face.
        # No concat, no trim, no desync. Audio always stream-copied.
        result = self._render_dynamic_panning(
            video_path, output_path, width, height, fps,
            tracked_data, speaker_result,
            transition_style=transition_style,
            transition_duration=transition_duration,
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
        height: int = 1080,
    ) -> dict:
        """Choose and schedule a 50:50 grid for two stable identities.

        Raw face counts are not sufficient: a detector can emit a duplicate
        box or recreate a track for the same person. We therefore count unique
        stable position IDs that coexist in the *same sampled frames*. A pair
        is accepted only when each crop can exclude the other face without
        exceeding the safe zoom ceiling.
        """
        per_frame_tracked = tracked_data.get("per_frame_tracked") or []
        track_to_position = {
            int(track_id): int(position_id)
            for track_id, position_id in (tracked_data.get("track_to_position") or {}).items()
        }
        position_targets = {
            int(pos_id): float(x)
            for pos_id, x in (tracked_data.get("position_targets") or {}).items()
        }
        position_profiles = self._normalise_position_profiles(
            tracked_data.get("position_target_profiles") or {}
        )
        person_count = int(tracked_data.get("person_count") or 0)

        if not per_frame_tracked or person_count < 2 or len(position_targets) < 2:
            return {"layout": "single", "person_count": person_count}

        pair_hits: Dict[Tuple[int, int], int] = defaultdict(int)
        pair_geometry: Dict[Tuple[int, int], dict] = {}
        per_frame_positions: List[set[int]] = []
        valid_frames = 0
        for frame_tracked in per_frame_tracked:
            visible_positions = sorted({
                track_to_position[int(detection.track_id)]
                for detection in frame_tracked
                if int(detection.track_id) in track_to_position
            })
            per_frame_positions.append(set(visible_positions))
            if not visible_positions:
                continue
            valid_frames += 1
            for index, first_id in enumerate(visible_positions):
                for second_id in visible_positions[index + 1:]:
                    separation = abs(position_targets.get(second_id, 0) - position_targets.get(first_id, 0))
                    if separation < width * self.MIN_SEPARATION_RATIO:
                        continue
                    pair = (first_id, second_id)
                    geometry = pair_geometry.get(pair)
                    if geometry is None:
                        geometry = self._calculate_grid_geometry(
                            first_id=first_id,
                            second_id=second_id,
                            position_targets=position_targets,
                            position_profiles=position_profiles,
                            width=width,
                            height=height,
                        )
                        if geometry:
                            pair_geometry[pair] = geometry
                    if geometry:
                        pair_hits[pair] += 1

        if not pair_hits or valid_frames <= 0:
            logger.info("podcast_reframe: autogrid skipped (no distinct co-visible identity pair)")
            return {"layout": "single", "person_count": person_count}

        best_pair, best_hits = max(
            pair_hits.items(),
            key=lambda item: (
                item[1],
                abs(position_targets[item[0][1]] - position_targets[item[0][0]]),
            ),
        )
        coexist_ratio = best_hits / valid_frames
        if best_hits < self.GRID_ENTER_SAMPLES:
            logger.info(
                "podcast_reframe: autogrid skipped "
                f"(distinct_pair=P{best_pair[0]}/P{best_pair[1]}, "
                f"co-visible-samples={best_hits}, visible_people={person_count})"
            )
            return {"layout": "single", "person_count": person_count}

        latest_speaker_id: Optional[int] = None
        if speaker_result and speaker_result.per_frame_speaker:
            latest_frame = max(speaker_result.per_frame_speaker)
            latest_speaker_id = int(speaker_result.per_frame_speaker[latest_frame])
        elif speaker_result and speaker_result.dominant_speaker_id is not None:
            latest_speaker_id = int(speaker_result.dominant_speaker_id)

        first_id, second_id = best_pair
        if latest_speaker_id == second_id:
            top_id, bottom_id = second_id, first_id
        else:
            top_id, bottom_id = first_id, second_id
        top_x = int(position_targets[top_id])
        bottom_x = int(position_targets[bottom_id])
        geometry = dict(pair_geometry[best_pair])
        if top_id != geometry["first_id"]:
            geometry = {
                **geometry,
                "top_crop_x": geometry["second_crop_x"],
                "bottom_crop_x": geometry["first_crop_x"],
                "top_crop_y": geometry["second_crop_y"],
                "bottom_crop_y": geometry["first_crop_y"],
            }
        else:
            geometry = {
                **geometry,
                "top_crop_x": geometry["first_crop_x"],
                "bottom_crop_x": geometry["second_crop_x"],
                "top_crop_y": geometry["first_crop_y"],
                "bottom_crop_y": geometry["second_crop_y"],
            }

        sample_timestamps = tracked_data.get("sample_timestamps") or [
            index * self.SAMPLE_INTERVAL_SEC
            for index in range(len(per_frame_positions))
        ]
        unsafe_frames = [
            not self._grid_frame_is_safe(frame_tracked, geometry)
            for frame_tracked in per_frame_tracked
        ]
        raw_double = [
            first_id in positions and second_id in positions and not unsafe_frames[index]
            for index, positions in enumerate(per_frame_positions)
        ]
        layout_events = self._build_layout_events(
            raw_double, sample_timestamps, force_single=unsafe_frames
        )
        if not any(event["layout"] == "double" for event in layout_events):
            logger.info(
                "podcast_reframe: autogrid skipped after visibility hysteresis "
                f"(pair=P{first_id}/P{second_id})"
            )
            return {"layout": "single", "person_count": person_count}

        logger.info(
            "podcast_reframe: AUTO 50/50 GRID "
            f"(top=P{top_id}@{top_x}, bottom=P{bottom_id}@{bottom_x}, "
            f"coexist={coexist_ratio:.0%}, zoom={geometry['grid_zoom']:.2f}, "
            f"layout_changes={max(0, len(layout_events) - 1)})"
        )
        return {
            "layout": "double",
            "top_x": top_x,
            "bottom_x": bottom_x,
            "top_track_id": top_id,
            "bottom_track_id": bottom_id,
            "person_count": person_count,
            "coexist_ratio": coexist_ratio,
            "layout_events": layout_events,
            **geometry,
        }

    def _build_layout_events(
        self,
        raw_double: List[bool],
        timestamps: List[float],
        force_single: Optional[List[bool]] = None,
    ) -> List[dict]:
        """Turn noisy per-sample people counts into a stable layout timeline."""
        if not raw_double:
            return [{"time": 0.0, "layout": "single"}]

        state = bool(raw_double[0])
        events = [{"time": 0.0, "layout": "double" if state else "single"}]
        pending_state: Optional[bool] = None
        pending_count = 0

        for index in range(1, len(raw_double)):
            candidate = bool(raw_double[index])
            if force_single and index < len(force_single) and force_single[index]:
                if state:
                    event_time = (
                        float(timestamps[index])
                        if index < len(timestamps)
                        else index * self.SAMPLE_INTERVAL_SEC
                    )
                    state = False
                    events.append({"time": max(0.0, event_time), "layout": "single"})
                pending_state = None
                pending_count = 0
                continue
            if candidate == state:
                pending_state = None
                pending_count = 0
                continue

            if pending_state != candidate:
                pending_state = candidate
                pending_count = 1
            else:
                pending_count += 1

            threshold = (
                self.GRID_ENTER_SAMPLES if candidate else self.GRID_EXIT_SAMPLES
            )
            if pending_count < threshold:
                continue

            state = candidate
            event_time = (
                float(timestamps[index])
                if index < len(timestamps)
                else index * self.SAMPLE_INTERVAL_SEC
            )
            events.append({
                "time": max(0.0, event_time),
                "layout": "double" if state else "single",
            })
            pending_state = None
            pending_count = 0

        return events

    @staticmethod
    def _grid_frame_is_safe(
        frame_tracked: List[TrackedDetection],
        geometry: dict,
    ) -> bool:
        """Reject a grid frame if any detected face enters both source crops."""
        crop_w = int(geometry.get("crop_w", 0))
        crop_h = int(geometry.get("crop_h", 0))
        if crop_w <= 0 or crop_h <= 0:
            return False

        first_rect = (
            int(geometry.get("top_crop_x", geometry.get("first_crop_x", 0))),
            int(geometry.get("top_crop_y", geometry.get("first_crop_y", 0))),
        )
        second_rect = (
            int(geometry.get("bottom_crop_x", geometry.get("second_crop_x", 0))),
            int(geometry.get("bottom_crop_y", geometry.get("second_crop_y", 0))),
        )

        def intersects(bbox: BBox, crop_x: int, crop_y: int) -> bool:
            return not (
                bbox.x2 <= crop_x
                or bbox.x1 >= crop_x + crop_w
                or bbox.y2 <= crop_y
                or bbox.y1 >= crop_y + crop_h
            )

        return not any(
            intersects(detection.bbox, *first_rect)
            and intersects(detection.bbox, *second_rect)
            for detection in frame_tracked
        )

    def _calculate_grid_geometry(
        self,
        first_id: int,
        second_id: int,
        position_targets: Dict[int, float],
        position_profiles: Dict[int, Dict[str, float]],
        width: int,
        height: int,
    ) -> Optional[dict]:
        """Find the mildest crop that isolates each person from the other.

        If isolation would require zooming past ``GRID_MAX_ZOOM``, the pair is
        rejected and auto-grid falls back to the centered single-speaker view.
        """
        if first_id == second_id:
            return None

        all_profiles = {
            position_id: {
                "x": float(target_x),
                "y": height * 0.38,
                "width": width * 0.08,
                "height": height * 0.16,
                **position_profiles.get(position_id, {}),
            }
            for position_id, target_x in position_targets.items()
        }
        first_profile = all_profiles.get(first_id, {
            "x": width / 3,
            "y": height * 0.38,
            "width": width * 0.08,
            "height": height * 0.16,
        })
        second_profile = all_profiles.get(second_id, {
            "x": width * 2 / 3,
            "y": height * 0.38,
            "width": width * 0.08,
            "height": height * 0.16,
        })
        separation = abs(first_profile["x"] - second_profile["x"])
        if separation < width * self.MIN_SEPARATION_RATIO:
            return None

        base_crop_w = min(float(width), float(height) * 9 / 8)
        max_face_w = max(
            [float(profile.get("width", 0.0)) for profile in all_profiles.values()]
            + [first_profile["width"], second_profile["width"], 1.0]
        )
        face_gutter = max(width * 0.015, max_face_w * 0.18)

        zoom = self.GRID_BASE_ZOOM
        while zoom <= self.GRID_MAX_ZOOM + 1e-6:
            crop_w = min(width, max(2, int(base_crop_w / zoom)))
            crop_h = min(height, max(2, int(crop_w * 8 / 9)))

            # Leave enough room around the selected face even at max zoom.
            own_face_min_w = max_face_w * (1 + self.GRID_FACE_MARGIN * 2)
            own_face_min_h = max(
                first_profile["height"], second_profile["height"], 1.0
            ) * (1 + self.GRID_FACE_MARGIN)
            if crop_w < own_face_min_w or crop_h < own_face_min_h:
                break

            first_crop_x = self._clamp_x(first_profile["x"], crop_w, width)
            second_crop_x = self._clamp_x(second_profile["x"], crop_w, width)
            first_isolated = all(
                first_crop_x + crop_w
                <= profile["x"] - profile["width"] / 2 - face_gutter
                or first_crop_x
                >= profile["x"] + profile["width"] / 2 + face_gutter
                for position_id, profile in all_profiles.items()
                if position_id != first_id
            )
            second_isolated = all(
                second_crop_x + crop_w
                <= profile["x"] - profile["width"] / 2 - face_gutter
                or second_crop_x
                >= profile["x"] + profile["width"] / 2 + face_gutter
                for position_id, profile in all_profiles.items()
                if position_id != second_id
            )
            if first_isolated and second_isolated:
                first_crop_y = self._clamp_grid_y(
                    first_profile["y"], crop_h, height
                )
                second_crop_y = self._clamp_grid_y(
                    second_profile["y"], crop_h, height
                )
                return {
                    "first_id": first_id,
                    "second_id": second_id,
                    "crop_w": crop_w,
                    "crop_h": crop_h,
                    "first_crop_x": first_crop_x,
                    "second_crop_x": second_crop_x,
                    "first_crop_y": first_crop_y,
                    "second_crop_y": second_crop_y,
                    "grid_zoom": round(base_crop_w / crop_w, 3),
                }

            zoom += 0.02

        logger.info(
            "podcast_reframe: grid pair rejected; isolation needs overzoom "
            f"(P{first_id}/P{second_id}, separation={separation:.0f}px, "
            f"max_zoom={self.GRID_MAX_ZOOM:.2f})"
        )
        return None

    @staticmethod
    def _clamp_grid_y(face_y: float, crop_h: int, frame_h: int) -> int:
        """Place eyes slightly above panel center while keeping the crop valid."""
        if crop_h >= frame_h:
            return 0
        target_y = int(float(face_y) - crop_h * 0.38)
        return max(0, min(target_y, frame_h - crop_h))

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
        # ─── Legacy fallback (no speaker detection) ───────────────────────
        # Auto-grid was already decided with stable identity mappings above.
        # Never re-enable it here using raw face counts.
        return self._decide_layout_legacy(per_frame_faces, width, False, person_count)

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

    def _build_panning_plan(
        self,
        width: int,
        height: int,
        fps: float,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        transition_style: str,
        transition_duration: float,
    ) -> Optional[dict]:
        """Build a bbox-aware, speaker-centered crop expression."""
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
                    try:
                        from src.config import settings
                        margin_ratio = getattr(
                            settings, "CENTERING_FACE_MARGIN_RATIO", 0.6
                        )
                    except (ImportError, ModuleNotFoundError):
                        margin_ratio = 0.6
                    margin = face_w * max(0.0, float(margin_ratio))

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

        # Build FFmpeg crop X expression.
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
                transition_duration,
                transition_style,
            )
            for i, (t, x, speaker_id, source) in enumerate(stabilized):
                logger.info(
                    f"  pan[{i}] t={t:.1f}s → x={x}, "
                    f"speaker={self._format_position_id(speaker_id)}, source={source}"
                )

        return {
            "crop_w": crop_w,
            "crop_x_expr": crop_x_expr,
            "keyframes": stabilized,
            "framing_events": self._speaker_change_events(stabilized),
        }

    def _render_dynamic_panning(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        transition_style: str = "slide",
        transition_duration: float = 0.4,
    ) -> Optional[dict]:
        """Render a single vertical crop that follows the active speaker."""
        plan = self._build_panning_plan(
            width=width,
            height=height,
            fps=fps,
            tracked_data=tracked_data,
            speaker_result=speaker_result,
            transition_style=transition_style,
            transition_duration=transition_duration,
        )
        if not plan:
            return None

        crop_w = plan["crop_w"]
        crop_x_expr = plan["crop_x_expr"]
        stabilized = plan["keyframes"]

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
                "layout": "single",
                "layout_events": [{"time": 0.0, "layout": "single"}],
                "framing_events": plan["framing_events"],
                "transition_style": transition_style,
                "transition_duration": transition_duration,
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: dynamic panning failed: {result.stderr[-300:]}")
        return None

    def _render_dynamic_auto_grid(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        duration: float,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        decision: dict,
    ) -> Optional[dict]:
        """Auto-switch between centered single view and identity-safe grid."""
        transition_style = str(decision.get("transition_style") or "cut")
        transition_duration = float(decision.get("transition_duration") or 0.0)
        plan = self._build_panning_plan(
            width=width,
            height=height,
            fps=fps,
            tracked_data=tracked_data,
            speaker_result=speaker_result,
            transition_style=transition_style,
            transition_duration=transition_duration,
        )
        if not plan or duration <= 0:
            return None

        layout_events = decision.get("layout_events") or []
        if len(layout_events) < 2:
            return None

        crop_w = int(decision["crop_w"])
        crop_h = int(decision["crop_h"])
        top_x = int(decision["top_crop_x"])
        bottom_x = int(decision["bottom_crop_x"])
        top_y = int(decision["top_crop_y"])
        bottom_y = int(decision["bottom_crop_y"])
        single_crop_w = int(plan["crop_w"])
        single_x_expr = plan["crop_x_expr"]

        transition_graph, output_label = self._build_layout_transition_graph(
            layout_events=layout_events,
            duration=duration,
            transition_style=transition_style,
            transition_duration=transition_duration,
        )
        if not transition_graph:
            return None

        fps_value = max(1.0, float(fps))
        filters = [
            "[0:v]split=3[single_src][top_src][bottom_src]",
            (
                f"[single_src]crop={single_crop_w}:{height}:{single_x_expr}:0,"
                f"scale=1080:1920:flags=lanczos,format=yuv420p,"
                f"fps={fps_value:.6f},settb=AVTB[single]"
            ),
            (
                f"[top_src]crop={crop_w}:{crop_h}:{top_x}:{top_y},"
                f"scale=1080:{self.GRID_PANEL_HEIGHT}:flags=lanczos,"
                "format=yuv420p[top]"
            ),
            (
                f"[bottom_src]crop={crop_w}:{crop_h}:{bottom_x}:{bottom_y},"
                f"scale=1080:{self.GRID_PANEL_HEIGHT}:flags=lanczos,"
                "format=yuv420p[bottom]"
            ),
            (
                f"[top][bottom]vstack=inputs=2,format=yuv420p,"
                f"fps={fps_value:.6f},settb=AVTB[grid]"
            ),
            transition_graph,
        ]
        filter_complex = ";".join(filters)
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", f"[{output_label}]", "-map", "0:a?",
            *get_video_encoder_args("medium"),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        logger.info(
            "podcast_reframe: DYNAMIC AUTO GRID "
            f"(events={len(layout_events)}, transition={transition_style}/"
            f"{transition_duration:.2f}s, zoom={decision.get('grid_zoom', 1.0):.2f})"
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 1000:
            if result.stderr:
                logger.warning(
                    f"podcast_reframe: dynamic auto grid failed: {result.stderr[-500:]}"
                )
            return None

        def layout_at(time_sec: float) -> str:
            current = "single"
            for event in layout_events:
                if float(event.get("time", 0.0)) > time_sec:
                    break
                current = str(event.get("layout", "single"))
            return current

        framing_events = [
            event
            for event in plan["framing_events"]
            if layout_at(float(event.get("time", 0.0))) == "single"
        ]
        framing_events.extend(
            {
                "time": float(event["time"]),
                "kind": "layout",
                "to": event["layout"],
            }
            for event in layout_events[1:]
        )
        framing_events.sort(key=lambda event: float(event.get("time", 0.0)))
        logger.info("podcast_reframe: dynamic auto grid OK")
        return {
            "output_path": output_path,
            "person_count": int(decision.get("person_count", 2)),
            "method": "podcast_dynamic_auto_grid",
            # Keep `double` for subtitle safe-zone compatibility; layout_mode
            # carries the fact that the encoded video switches over time.
            "layout": "double",
            "layout_mode": "dynamic",
            "layout_events": layout_events,
            "framing_events": framing_events,
            "transition_style": transition_style,
            "transition_duration": transition_duration,
            "grid_zoom": decision.get("grid_zoom"),
            "grid_panel_height": self.GRID_PANEL_HEIGHT,
            "subtitle_position_y": 50,
            "top_track_id": decision.get("top_track_id"),
            "bottom_track_id": decision.get("bottom_track_id"),
        }

    def _build_layout_transition_graph(
        self,
        layout_events: List[dict],
        duration: float,
        transition_style: str,
        transition_duration: float,
    ) -> Tuple[str, str]:
        """Build trim/concat or xfade graph without changing video duration."""
        cleaned: List[dict] = []
        for event in sorted(layout_events, key=lambda item: float(item.get("time", 0.0))):
            layout = "double" if event.get("layout") == "double" else "single"
            event_time = max(0.0, min(float(duration), float(event.get("time", 0.0))))
            if cleaned and layout == cleaned[-1]["layout"]:
                continue
            if cleaned and event_time <= cleaned[-1]["time"] + 1e-3:
                cleaned[-1] = {"time": event_time, "layout": layout}
            else:
                cleaned.append({"time": event_time, "layout": layout})

        if not cleaned:
            return "", ""
        if cleaned[0]["time"] > 0:
            cleaned.insert(0, {"time": 0.0, "layout": cleaned[0]["layout"]})
        else:
            cleaned[0]["time"] = 0.0
        cleaned = [event for event in cleaned if event["time"] < duration]
        if len(cleaned) < 2:
            return "", ""

        use_xfade = transition_style in {"fade", "slide", "zoom"} and transition_duration > 0
        transition_durations: List[float] = []
        for index in range(1, len(cleaned)):
            previous_gap = cleaned[index]["time"] - cleaned[index - 1]["time"]
            next_time = cleaned[index + 1]["time"] if index + 1 < len(cleaned) else duration
            next_gap = next_time - cleaned[index]["time"]
            safe_duration = min(
                max(0.0, transition_duration),
                max(0.0, previous_gap * 0.8),
                max(0.0, next_gap * 0.8),
            )
            transition_durations.append(safe_duration if safe_duration >= 0.04 else 0.0)
        if not all(value > 0 for value in transition_durations):
            use_xfade = False

        layout_counts = {
            "single": sum(1 for event in cleaned if event["layout"] == "single"),
            "double": sum(1 for event in cleaned if event["layout"] == "double"),
        }
        parts: List[str] = []
        source_labels: Dict[str, List[str]] = {"single": [], "double": []}
        for layout, source in (("single", "single"), ("double", "grid")):
            count = layout_counts[layout]
            labels = [f"{layout}_copy_{index}" for index in range(count)]
            source_labels[layout] = labels
            if count == 1:
                parts.append(f"[{source}]null[{labels[0]}]")
            elif count > 1:
                joined = "".join(f"[{label}]" for label in labels)
                parts.append(f"[{source}]split={count}{joined}")

        source_offsets = {"single": 0, "double": 0}
        segment_durations: List[float] = []
        for index, event in enumerate(cleaned):
            left_overlap = transition_durations[index - 1] / 2 if use_xfade and index > 0 else 0.0
            right_overlap = transition_durations[index] / 2 if use_xfade and index < len(cleaned) - 1 else 0.0
            segment_start = max(0.0, event["time"] - left_overlap)
            next_boundary = cleaned[index + 1]["time"] if index + 1 < len(cleaned) else duration
            segment_end = min(duration, next_boundary + right_overlap)
            layout = event["layout"]
            source_index = source_offsets[layout]
            source_offsets[layout] += 1
            source_label = source_labels[layout][source_index]
            parts.append(
                f"[{source_label}]trim=start={segment_start:.6f}:end={segment_end:.6f},"
                f"setpts=PTS-STARTPTS[layout_seg_{index}]"
            )
            segment_durations.append(max(0.0, segment_end - segment_start))

        if not use_xfade:
            inputs = "".join(f"[layout_seg_{index}]" for index in range(len(cleaned)))
            parts.append(f"{inputs}concat=n={len(cleaned)}:v=1:a=0[layout_out]")
            return ";".join(parts), "layout_out"

        accumulated = segment_durations[0]
        current_label = "layout_seg_0"
        for index in range(1, len(cleaned)):
            trans_duration = transition_durations[index - 1]
            offset = max(0.0, accumulated - trans_duration)
            if transition_style == "slide":
                transition_name = (
                    "slideup" if cleaned[index]["layout"] == "double" else "slidedown"
                )
            elif transition_style == "zoom":
                transition_name = "zoomin"
            else:
                transition_name = "fade"
            next_label = f"layout_mix_{index}"
            parts.append(
                f"[{current_label}][layout_seg_{index}]"
                f"xfade=transition={transition_name}:duration={trans_duration:.6f}:"
                f"offset={offset:.6f}[{next_label}]"
            )
            accumulated += segment_durations[index] - trans_duration
            current_label = next_label

        parts.append(f"[{current_label}]null[layout_out]")
        return ";".join(parts), "layout_out"

    def _build_panning_expression(
        self,
        keyframes: List[Tuple[float, int]],
        transition_sec: float = 0.0,
        transition_style: str = "slide",
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

        # Respect the style selected in the editor. Cut snaps immediately;
        # the other styles keep the crop motion smooth while Remotion applies
        # the corresponding fade/slide/zoom accent at the same event time.
        if transition_sec > 0:
            trans = transition_sec
        else:
            try:
                from src.config import settings
                trans = getattr(settings, 'CENTERING_TRANSITION_SEC', 0.4)
            except (ImportError, ModuleNotFoundError):
                trans = 0.4
        if transition_style == "cut":
            trans = 0.0
        trans = max(0.0, min(1.0, float(trans)))

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

    @staticmethod
    def _speaker_change_events(
        keyframes: List[Tuple[float, int, Optional[int], str]],
    ) -> List[dict]:
        """Expose stable speaker changes to the final transition renderer."""
        events: List[dict] = []
        previous_speaker: Optional[int] = None
        for time_sec, _, speaker_id, _ in keyframes:
            if speaker_id is None:
                continue
            if previous_speaker is None:
                previous_speaker = int(speaker_id)
                continue
            if int(speaker_id) == previous_speaker:
                continue
            events.append({
                "time": max(0.0, float(time_sec)),
                "kind": "speaker",
                "from": previous_speaker,
                "to": int(speaker_id),
            })
            previous_speaker = int(speaker_id)
        return events

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
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: single crop failed: {result.stderr[-300:]}")
        return None

    # ─── Render: Double Grid ──────────────────────────────────────────────

    def _render_double_grid(
        self, video_path: str, output_path: str, width: int, height: int, decision: dict
    ) -> Optional[dict]:
        """Equal grid: one unique person in each 1080x960 panel.

        Each source crop uses a 9:8 ratio, so scaling it to 1080x960
        preserves aspect ratio. The two panels then stack to 1080x1920.
        """
        top_center_x = decision.get("top_x", decision.get("left_x", width // 3))
        bottom_center_x = decision.get("bottom_x", decision.get("right_x", width * 2 // 3))
        top_track_id = decision.get("top_track_id")
        bottom_track_id = decision.get("bottom_track_id")
        if top_track_id is not None and top_track_id == bottom_track_id:
            logger.warning("podcast_reframe: rejected grid with duplicate identity")
            return None
        if abs(float(top_center_x) - float(bottom_center_x)) < width * self.MIN_SEPARATION_RATIO:
            logger.warning("podcast_reframe: rejected grid with visually overlapping people")
            return None

        # Auto-grid decisions normally provide identity-safe geometry. Rebuild
        # it for older callers so even the compatibility path has disjoint crops.
        if decision.get("crop_w") is None and top_track_id is not None and bottom_track_id is not None:
            fallback_geometry = self._calculate_grid_geometry(
                first_id=int(top_track_id),
                second_id=int(bottom_track_id),
                position_targets={
                    int(top_track_id): float(top_center_x),
                    int(bottom_track_id): float(bottom_center_x),
                },
                position_profiles={},
                width=width,
                height=height,
            )
            if not fallback_geometry:
                logger.warning("podcast_reframe: rejected grid without safe crop geometry")
                return None
            decision = {
                **decision,
                "crop_w": fallback_geometry["crop_w"],
                "crop_h": fallback_geometry["crop_h"],
                "grid_zoom": fallback_geometry["grid_zoom"],
                "top_crop_x": fallback_geometry["first_crop_x"],
                "bottom_crop_x": fallback_geometry["second_crop_x"],
                "top_crop_y": fallback_geometry["first_crop_y"],
                "bottom_crop_y": fallback_geometry["second_crop_y"],
            }

        grid_zoom = float(decision.get("grid_zoom", self.GRID_MAX_ZOOM))
        crop_w = int(decision.get("crop_w", (height * 9 / 8) / grid_zoom))
        crop_h = int(decision.get("crop_h", crop_w * 8 / 9))
        if crop_w > width:
            crop_w = width
            crop_h = int(width * 8 / 9)

        top_x = int(decision.get("top_crop_x", self._clamp_x(top_center_x, crop_w, width)))
        bottom_x = int(decision.get("bottom_crop_x", self._clamp_x(bottom_center_x, crop_w, width)))

        # Center each person independently; front/back rows can have different Y.
        fallback_y = max(0, (height - crop_h) // 2)
        top_y = int(decision.get("top_crop_y", fallback_y))
        bottom_y = int(decision.get("bottom_crop_y", fallback_y))

        vf = (
            f"split=2[top][bot];"
            f"[top]crop={crop_w}:{crop_h}:{top_x}:{top_y},scale=1080:{self.GRID_PANEL_HEIGHT},format=yuv420p[t];"
            f"[bot]crop={crop_w}:{crop_h}:{bottom_x}:{bottom_y},scale=1080:{self.GRID_PANEL_HEIGHT},format=yuv420p[b];"
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
            logger.info(
                "podcast_reframe: 50/50 grid OK "
                f"(top={top_x},{top_y}, bottom={bottom_x},{bottom_y}, "
                f"crop={crop_w}x{crop_h}, zoom={grid_zoom:.2f})"
            )
            return {
                "output_path": output_path,
                "person_count": pc,
                "method": "podcast_double_grid",
                "layout": "double",
                "grid_zoom": grid_zoom,
                "subtitle_position_y": 50,
                "grid_panel_height": self.GRID_PANEL_HEIGHT,
                "top_track_id": decision.get("top_track_id"),
                "bottom_track_id": decision.get("bottom_track_id"),
                "layout_events": decision.get("layout_events", [{"time": 0.0, "layout": "double"}]),
                "framing_events": [],
                "transition_style": decision.get("transition_style", "cut"),
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: double grid failed: {result.stderr[-300:]}")
        return None

    # ─── Utilities ────────────────────────────────────────────────────────

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
