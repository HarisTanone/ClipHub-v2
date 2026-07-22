"""PodcastReframeEngine — Speaker-Aware Face-Based Reframing.

Strategy: Detect faces → Track persons → Detect active speaker → Smart crop.

Pipeline:
  1. MediaPipe Face Detection → find faces per frame
  2. IoU Person Tracker → consistent person IDs across frames
  3. Active Speaker Detection (lip movement via Face Mesh) → who is talking
  4. Dynamic panning keeps the active speaker centered.

Rules:
  - Video and audio are normalized to the same zero-based timeline
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
from src.infrastructure.media_timeline import timeline_is_safe

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

    SAMPLE_INTERVAL_SEC = 0.333  # target 3fps sampling
    # 720 samples covers a four-minute highlight at roughly 3fps. When a clip
    # is longer, samples are spread across the entire timeline instead of only
    # inspecting its first minute.
    MAX_SAMPLES = 720
    FACE_CONFIDENCE = 0.55
    MIN_FACE_SIZE_RATIO = 0.10
    MAX_FACE_SIZE_RATIO = 0.50
    MIN_SEPARATION_RATIO = 0.05  # [FIX] Turunkan dari 0.20 → face-to-face setup orang sangat dekat horizontal
    # User rule: 1 person → single, ≥2 co-visible → grid immediately.
    MIN_COEXIST_RATIO = 0.10

    # Every grid panel is exactly half of the 1080x1920 output.
    GRID_PANEL_HEIGHT = 960
    DOMINANCE_SINGLE_CROP = 0.75     # If dominant ≥75% → use single crop instead of grid
    GRID_BASE_ZOOM = 1.08            # Gentle default crop; avoids excessive background.
    GRID_MAX_ZOOM = 2.20             # Head+shoulders framing for face-to-face podcast grid
    GRID_FACE_MARGIN = 0.35          # Minimum face-side breathing room inside a panel.
    GRID_ENTER_SAMPLES = 1           # Grid on first co-visible sample (≥2 people).
    GRID_EXIT_SAMPLES = 2            # Brief miss still holds grid open.
    MIN_GRID_SEGMENT_SECONDS = 0.50  # Allow short multi-person sections.

    VALID_TRANSITIONS = {"cut", "fade", "slide", "zoom"}

    # Ghost detection constants
    MIN_FACE_AREA_PX = 4_000            # [FIX] Turunkan dari 12_000 -> Wajah jauh di studio radio tetap kebaca
    MIN_AREA_RATIO_TO_MAX = 0.25        # [FIX] Turunkan dari 0.40 -> Orang di belakang tidak dianggap ghost
    MIN_FRAME_RATIO = 0.15              # Track must appear in ≥15% of sampled frames
    GHOST_IOU_THRESHOLD = 0.25          # IoU overlap indicating same-person duplicate
    GHOST_CENTER_DIST_RATIO = 0.08      # Normalized center distance for ghost proximity
    GHOST_CENTER_DIST_BROAD = 0.20      # Broader center distance for ghost with area similarity
    MIN_PAIR_SIZE_RATIO = 0.18          # [FIX] Turunkan dari 0.30 -> Bisa pasangkan wajah besar & wajah kecil
    AUDIO_FILTER = "aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS"

    def __init__(self, hf_token: Optional[str] = None, tuning_override: Optional[dict] = None):
        self._face_detector = None
        self._use_legacy_api = False
        self._speaker_detector = ActiveSpeakerDetector()
        self._tracker: Optional[SimpleIoUTracker] = None

        # Diarization components (lazy-init)
        self._hf_token = hf_token
        self._diarizer: Optional[SpeakerDiarizer] = None
        self._face_mapper: Optional[SpeakerFaceMapper] = None
        self._result_builder = DiarizationResultBuilder()

        # Dynamic tuning overrides — replace hardcoded class constants at instance level
        self._apply_tuning(tuning_override)

    def _apply_tuning(self, tuning_override: Optional[dict]) -> None:
        """Override class-level tuning constants with values from DB or caller.

        Ponytail: keeps class constants as defaults for backward compat; instance attrs override.
        Upgrade path: remove class constants entirely once all callers pass tuning_override.
        """
        if not tuning_override:
            return
        # Mapping: DB column -> class constant attr name
        _ATTR_MAP = {
            "sample_interval_sec": "SAMPLE_INTERVAL_SEC",
            "max_samples": "MAX_SAMPLES",
            "face_confidence": "FACE_CONFIDENCE",
            "min_face_size_ratio": "MIN_FACE_SIZE_RATIO",
            "max_face_size_ratio": "MAX_FACE_SIZE_RATIO",
            "min_separation_ratio": "MIN_SEPARATION_RATIO",
            "min_coexist_ratio": "MIN_COEXIST_RATIO",
            "dominance_single_crop": "DOMINANCE_SINGLE_CROP",
            "grid_base_zoom": "GRID_BASE_ZOOM",
            "grid_max_zoom": "GRID_MAX_ZOOM",
            "grid_face_margin": "GRID_FACE_MARGIN",
            "grid_enter_samples": "GRID_ENTER_SAMPLES",
            "grid_exit_samples": "GRID_EXIT_SAMPLES",
            "min_grid_segment_seconds": "MIN_GRID_SEGMENT_SECONDS",
            "min_face_area_px": "MIN_FACE_AREA_PX",
            "min_area_ratio_to_max": "MIN_AREA_RATIO_TO_MAX",
            "min_frame_ratio": "MIN_FRAME_RATIO",
            "ghost_iou_threshold": "GHOST_IOU_THRESHOLD",
            "ghost_center_dist_ratio": "GHOST_CENTER_DIST_RATIO",
            "ghost_center_dist_broad": "GHOST_CENTER_DIST_BROAD",
            "min_pair_size_ratio": "MIN_PAIR_SIZE_RATIO",
        }
        for db_key, attr_name in _ATTR_MAP.items():
            if db_key in tuning_override and tuning_override[db_key] is not None:
                setattr(self, attr_name, tuning_override[db_key])

    def _reload_tuning_from_db(self) -> None:
        """Reload tuning config from DB before each process() call.

        This ensures settings saved via the UI take effect immediately
        without requiring a service restart.
        """
        try:
            from src.presentation.routes.settings import get_reframe_tuning
            tuning = get_reframe_tuning(user_id=None)
            if tuning:
                self._apply_tuning(tuning)
        except Exception as e:
            # Non-fatal: if DB read fails, keep current values
            logger.debug(f"podcast_reframe: tuning reload failed (using current): {e}")

    def _load_face_detector(self) -> bool:
        if self._face_detector is not None:
            return True
        try:
            import mediapipe as mp

            # Coba Task API baru (mediapipe ≥0.10.14)
            try:
                # FIX: Path import diubah dari mediapipe.tasks.vision -> mediapipe.tasks.python.vision
                from mediapipe.tasks.python import vision
                from mediapipe.tasks.python import BaseOptions
                model_path = self._find_face_detection_model()
                base_options = BaseOptions(model_asset_path=model_path)
                options = vision.FaceDetectorOptions(
                    base_options=base_options,
                    running_mode=vision.RunningMode.IMAGE,
                    min_detection_confidence=self.FACE_CONFIDENCE,
                )
                self._face_detector = vision.FaceDetector.create_from_options(options)
                self._use_legacy_api = False
                logger.info("podcast_reframe: MediaPipe FaceDetector loaded (Task API)")
                return True
            except (ImportError, ModuleNotFoundError, AttributeError) as e:
                logger.debug(f"podcast_reframe: Task API not available: {e}. Trying legacy API...")

            # Fallback ke Legacy API (mediapipe ≤0.10.21)
            if hasattr(mp, 'solutions') and hasattr(mp.solutions, 'face_detection'):
                self._face_detector = mp.solutions.face_detection.FaceDetection(
                    min_detection_confidence=self.FACE_CONFIDENCE,
                    model_selection=1,
                )
                self._use_legacy_api = True
                logger.info("podcast_reframe: MediaPipe loaded (Legacy API)")
                return True

            logger.error("podcast_reframe: No valid MediaPipe Face Detector API found.")
            return False

        except Exception as e:
            logger.warning(f"podcast_reframe: MediaPipe failed to load: {e}")
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

    def _load_person_detector(self) -> bool:
        """Lazy-load PersonDetector (RF-DETR with YOLO fallback).

        Uses the canonical PersonDetector class so detection logic (class
        filtering, duplicate suppression) lives in one place.
        """
        if hasattr(self, "_person_detector_instance") and self._person_detector_instance is not None:
            return True
        try:
            from src.config import settings
            from src.infrastructure.person_detector import PersonDetector

            self._person_detector_instance = PersonDetector(
                model_variant=settings.PERSON_DETECTOR,
                confidence_threshold=settings.PERSON_CONF_THRESHOLD,
            )
            if self._person_detector_instance.is_available or not self._person_detector_instance._load_attempted:
                logger.info(f"podcast_reframe: PersonDetector ready ({settings.PERSON_DETECTOR})")
                return True
            else:
                logger.error("podcast_reframe: PersonDetector unavailable after load attempt")
                self._person_detector_instance = None
                return False
        except Exception as e:
            logger.error(f"podcast_reframe: PersonDetector init failed: {e}")
            self._person_detector_instance = None
            return False

    def _load_crop_face_detector(self) -> bool:
        """Lazy-load RetinaFace / SCRFD face detector for person crop."""
        if hasattr(self, "_crop_face_detector") and self._crop_face_detector is not None:
            return True
        try:
            from src.config import settings
            detector_type = settings.FACE_DETECTOR
            if detector_type == "retinaface":
                try:
                    from retinaface.pre_trained_models import get_model
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                    self._crop_face_detector = get_model("resnet50_2020-07-20", max_size=2048, device=device)
                    self._crop_face_detector.eval()
                    self._crop_face_detector_type = "retinaface"
                    logger.info("podcast_reframe: RetinaFace face detector loaded (PyTorch)")
                    return True
                except Exception as e_retina:
                    logger.warning(f"podcast_reframe: RetinaFace load failed: {e_retina}, trying SCRFD fallback")
                    detector_type = "scrfd"
            
            if detector_type == "scrfd":
                try:
                    from scrfd import SCRFD
                    onnx_path = self._find_scrfd_model()
                    self._crop_face_detector = SCRFD.from_path(onnx_path)
                    self._crop_face_detector_type = "scrfd"
                    logger.info("podcast_reframe: SCRFD face detector loaded")
                    return True
                except Exception as e_scrfd:
                    logger.warning(f"podcast_reframe: SCRFD load failed: {e_scrfd}, falling back to MediaPipe")
                    self._load_face_detector()
                    self._crop_face_detector = self._face_detector
                    self._crop_face_detector_type = "mediapipe"
                    logger.info("podcast_reframe: MediaPipe face detector loaded as crop face detector fallback")
                    return True
            else:
                self._load_face_detector()
                self._crop_face_detector = self._face_detector
                self._crop_face_detector_type = "mediapipe"
                logger.info("podcast_reframe: MediaPipe face detector loaded as crop face detector fallback")
                return True
        except Exception as e:
            logger.error(f"podcast_reframe: failed to load crop face detector: {e}")
            return False

    def _find_scrfd_model(self) -> str:
        """Find or download the SCRFD ONNX face detection model."""
        model_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, 'scrfd_500m_bnkps.onnx')

        if not os.path.exists(model_path):
            import urllib.request
            url = "https://huggingface.co/ykk648/face_lib/resolve/main/scrfd_500m_bnkps.onnx"
            logger.info("podcast_reframe: downloading SCRFD ONNX model...")
            urllib.request.urlretrieve(url, model_path)
            logger.info(f"podcast_reframe: SCRFD model saved to {model_path}")

        return model_path

    def _init_person_tracker(self, fps: float) -> bool:
        """Initialize the person tracker (supervision.ByteTrack or SimpleIoUTracker)."""
        from src.config import settings
        tracker_type = settings.PERSON_TRACKER
        max_lost_frames = settings.TRACKER_MAX_LOST_FRAMES

        try:
            import supervision as sv
            self._person_tracker = sv.ByteTrack(
                lost_track_buffer=max_lost_frames,
                frame_rate=int(max(1.0, fps))
            )
            self._person_tracker_type = "bytetrack"
            logger.info(f"podcast_reframe: supervision ByteTrack initialized (max_lost_frames={max_lost_frames})")
            return True
        except Exception as e:
            logger.warning(f"podcast_reframe: supervision ByteTrack initialization failed: {e}. Falling back to SimpleIoUTracker.")
            self._person_tracker = SimpleIoUTracker(
                frame_width=self._tracker._frame_width if self._tracker else 1920,
                frame_height=self._tracker._frame_height if self._tracker else 1080
            )
            self._person_tracker.MAX_LOST_FRAMES = max_lost_frames
            self._person_tracker_type = "simple_iou"
            logger.info("podcast_reframe: SimpleIoUTracker initialized for person tracking")
            return True

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

        # Reload tuning from DB (picks up UI changes without restart)
        self._reload_tuning_from_db()

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

        from src.config import settings
        pipeline_mode = settings.REFRAME_PIPELINE_MODE

        if pipeline_mode == "legacy":
            tracked_data = self._detect_and_track_faces(video_path, width, height, fps, total_frames)
        elif pipeline_mode == "shadow":
            logger.info("podcast_reframe: running in SHADOW mode (legacy + person_first)")
            import time
            t0 = time.perf_counter()
            tracked_data = self._detect_and_track_faces(video_path, width, height, fps, total_frames)
            t1 = time.perf_counter()
            legacy_time = t1 - t0

            try:
                t2 = time.perf_counter()
                shadow_data = self._detect_and_track_persons_first(video_path, width, height, fps, total_frames)
                t3 = time.perf_counter()
                person_first_time = t3 - t2
                
                logger.info(
                    f"podcast_reframe [SHADOW METRICS]: "
                    f"legacy_time={legacy_time:.2f}s, person_first_time={person_first_time:.2f}s | "
                    f"legacy_tracks={len(tracked_data.get('stable_positions', {}))}, "
                    f"person_first_tracks={len(shadow_data.get('stable_positions', {}))} | "
                    f"legacy_person_count={tracked_data.get('person_count')}, "
                    f"person_first_person_count={shadow_data.get('person_count')}"
                )
            except Exception as shadow_err:
                logger.warning(f"podcast_reframe [SHADOW ERROR]: person_first pipeline failed: {shadow_err}")
        else: # person_first
            logger.info("podcast_reframe: running in PERSON_FIRST mode")
            tracked_data = self._detect_and_track_persons_first(video_path, width, height, fps, total_frames)

        if not tracked_data or not tracked_data["per_frame_faces"]:
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
        # Keep the UI toggle as a hard safety gate. In particular, do not let
        # the legacy fallback or a stale layout decision turn grid back on.
        if autogrid:
            from src.config import settings
            is_person_first = settings.REFRAME_PIPELINE_MODE == "person_first"
            grid_decision = self._decide_autogrid_layout(
                tracked_data=tracked_data,
                speaker_result=speaker_result,
                width=width,
                height=height,
                skip_ghost_pair_check=is_person_first,
            )

            # Fix #4: Diarization fallback safety guard
            if grid_decision["layout"] == "double":
                valid_track_count = len([
                    tid for tid in (tracked_data.get("track_to_position") or {}).keys()
                    if int(tid) in (tracked_data.get("stable_positions") or {})
                ])
                if valid_track_count <= 1:
                    logger.info(
                        "podcast_reframe: ghost elimination reduced to 1 valid track; "
                        "overriding to single layout"
                    )
                    grid_decision = {"layout": "single", "person_count": person_count}

            if grid_decision["layout"] == "double":
                grid_decision["transition_style"] = transition_style
                grid_decision["transition_duration"] = transition_duration
                layout_events = self._normalise_layout_events(
                    grid_decision.get("layout_events") or []
                )
                grid_decision["layout_events"] = layout_events

                # Reject same-person panels before any render path.
                top_tid = grid_decision.get("top_track_id")
                bottom_tid = grid_decision.get("bottom_track_id")
                if top_tid is not None and bottom_tid is not None and int(top_tid) == int(bottom_tid):
                    logger.info(
                        "podcast_reframe: autogrid rejected duplicate panel identity "
                        f"(P{top_tid})"
                    )
                    grid_decision = {"layout": "single", "person_count": person_count}
                else:
                    layouts = {str(e.get("layout")) for e in layout_events}
                    needs_dynamic = (
                        len(layout_events) > 1
                        or (layouts == {"double"} and layout_events and float(layout_events[0].get("time", 0.0)) > 0)
                        or layouts == {"single", "double"}
                    )
                    if needs_dynamic:
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
                        # A valid, identity-safe grid decision must remain a grid
                        # even when FFmpeg rejects the dynamic transition graph.
                        # Falling through to single-person panning makes the UI
                        # Auto Grid toggle appear to do nothing.
                        logger.warning(
                            "podcast_reframe: dynamic grid unavailable; "
                            "falling back to static double grid"
                        )
                        static_grid = self._render_double_grid(
                            video_path, output_path, width, height, grid_decision
                        )
                        if static_grid:
                            return static_grid
                        logger.warning(
                            "podcast_reframe: static grid fallback also failed; "
                            "continuing with safe single-person framing"
                        )
                    if layout_events and layout_events[0].get("layout") == "double" and layouts == {"double"}:
                        return self._render_double_grid(
                            video_path, output_path, width, height, grid_decision
                        )

        # Step 4: Dynamic Panning — single FFmpeg pass with smooth crop tracking
        # Builds a time-based crop X expression that follows the active face.
        # No concat and no source-timeline discontinuity.
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
        map_thresh = settings.MAPPING_MARGIN_THRESHOLD if settings.REFRAME_PIPELINE_MODE != "legacy" else settings.DIARIZATION_MAPPING_CONFIDENCE_THRESHOLD
        self._face_mapper = SpeakerFaceMapper(
            confidence_threshold=map_thresh,
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

        sample_indices = self._sample_frame_indices(total_frames, fps)

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
                        # Fix #1: Absolute area floor
                        face_area_px = (bbox.width * width) * (bbox.height * height)
                        if face_area_px < self.MIN_FACE_AREA_PX:
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
                        # Fix #1: Absolute area floor
                        face_area_px = w_px * h_px
                        if face_area_px < self.MIN_FACE_AREA_PX:
                            continue
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
            f"coverage=0.0-{(sample_timestamps[-1] if sample_timestamps else 0.0):.1f}s, "
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

    def _sample_frame_indices(self, total_frames: int, fps: float) -> List[int]:
        """Sample the complete clip while keeping face detection bounded."""
        if total_frames <= 0:
            return []
        sample_interval = max(1, int(round(float(fps) * self.SAMPLE_INTERVAL_SEC)))
        natural_indices = list(range(0, total_frames, sample_interval))
        if len(natural_indices) <= self.MAX_SAMPLES:
            if natural_indices and natural_indices[-1] != total_frames - 1:
                if len(natural_indices) < self.MAX_SAMPLES:
                    natural_indices.append(total_frames - 1)
                else:
                    natural_indices[-1] = total_frames - 1
            return natural_indices

        # A hard slice used to make every clip longer than 60 seconds blind
        # after its first minute. Preserve the cap, but distribute it over the
        # complete source timeline so later camera cuts are inspected.
        distributed = np.linspace(
            0,
            max(0, total_frames - 1),
            num=self.MAX_SAMPLES,
            dtype=int,
        ).tolist()
        return list(dict.fromkeys(distributed))

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
                # Capture real face bbox when the tracker provides one
                # (person-first mode) so grid-Y framing can use the actual face
                # instead of a body→face estimate.
                if detection.face_bbox is not None:
                    profile["face_x"].append(detection.face_bbox.center_x)
                    profile["face_y"].append(detection.face_bbox.center_y)
                    profile["face_width"].append(detection.face_bbox.width)
                    profile["face_height"].append(detection.face_bbox.height)

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

        # Ghost elimination pass (Fix #2)
        if stable_position_profiles:
            max_area = max(
                p.get("area", p.get("width", 0) * p.get("height", 0))
                for p in stable_position_profiles.values()
            )
            total_sampled = len(per_frame_tracked)

            # Count frames each track appears in
            track_frame_counts: Dict[int, int] = defaultdict(int)
            for frame_tracked in per_frame_tracked:
                for det in frame_tracked:
                    track_frame_counts[det.track_id] += 1

            ghost_track_ids: set = set()
            sorted_by_area = sorted(
                stable_position_profiles.items(),
                key=lambda kv: kv[1].get("area", kv[1].get("width", 0) * kv[1].get("height", 0)),
                reverse=True,
            )

            for track_id, profile in sorted_by_area:
                if track_id in ghost_track_ids:
                    continue

                track_area = profile.get("area", profile.get("width", 0) * profile.get("height", 0))
                frame_count = track_frame_counts.get(track_id, 0)

                # Filter: area ratio too small compared to largest track
                if max_area > 0 and track_area / max_area < self.MIN_AREA_RATIO_TO_MAX:
                    ghost_track_ids.add(track_id)
                    continue

                # Filter: flicker track (too few frames)
                if total_sampled > 0 and frame_count / total_sampled < self.MIN_FRAME_RATIO:
                    ghost_track_ids.add(track_id)
                    continue

                # Filter: ghost pair with a larger track already validated
                for valid_id, valid_profile in sorted_by_area:
                    if valid_id == track_id or valid_id in ghost_track_ids:
                        continue
                    valid_area = valid_profile.get("area", valid_profile.get("width", 0) * valid_profile.get("height", 0))
                    if valid_area <= track_area:
                        continue  # Only compare against larger tracks
                    if self._is_ghost_pair(profile, valid_profile, width, height):
                        ghost_track_ids.add(track_id)
                        break

            # Remove ghost tracks
            if ghost_track_ids:
                logger.info(f"podcast_reframe: ghost elimination removed tracks: {ghost_track_ids}")
                stable_position_profiles = {
                    tid: prof for tid, prof in stable_position_profiles.items()
                    if tid not in ghost_track_ids
                }
                stable_positions = {
                    tid: profile["x"]
                    for tid, profile in stable_position_profiles.items()
                }
                filtered = {
                    tid: vals for tid, vals in filtered.items()
                    if tid not in ghost_track_ids
                }

        clusters: List[dict] = []
        # Clustering threshold to merge similar positions
        # Use 0.15 to properly merge tracks from the same person who moves slightly
        # Higher threshold = more aggressive merging (reduces false "multiple people" detection)
        cluster_threshold = 0.15

        logger.info(
            f"podcast_reframe: clustering {len(stable_position_profiles)} position profiles "
            f"with threshold={cluster_threshold}"
        )

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

    def _frame_has_distinct_people(
        self,
        first_detections: List[TrackedDetection],
        second_detections: List[TrackedDetection],
        width: int,
        height: int,
    ) -> bool:
        """Return true only with frame-level evidence of two physical people.

        Track/seat IDs alone are insufficient because one person can receive two
        detector IDs. A valid pair must have low overlap and meaningful 2-D
        separation relative to the detections' own size. The 2-D check still
        permits front/back podcast seating where X coordinates are similar.

        Nested tight/loose body boxes for one subject (low IoU, high containment)
        are treated as the same person even when face evidence is missing.
        """
        frame_diagonal = max(1.0, float(np.hypot(width, height)))
        for first in first_detections:
            for second in second_detections:
                if int(first.track_id) == int(second.track_id):
                    continue
                # Prefer face boxes when both exist — one subject can get two
                # differently-sized body boxes but only one real head.
                if first.face_bbox is not None and second.face_bbox is not None:
                    first_box = first.face_bbox
                    second_box = second.face_bbox
                else:
                    first_box = first.person_bbox or first.bbox
                    second_box = second.person_bbox or second.bbox
                intersection_w = max(
                    0.0,
                    min(first_box.x2, second_box.x2) - max(first_box.x1, second_box.x1),
                )
                intersection_h = max(
                    0.0,
                    min(first_box.y2, second_box.y2) - max(first_box.y1, second_box.y1),
                )
                intersection = intersection_w * intersection_h
                union = max(1.0, first_box.area + second_box.area - intersection)
                iou = intersection / union
                containment = intersection / max(
                    1.0,
                    min(first_box.area, second_box.area),
                )
                distance = float(np.hypot(
                    first_box.center_x - second_box.center_x,
                    first_box.center_y - second_box.center_y,
                ))
                larger_diagonal = max(
                    1.0,
                    float(
                        np.hypot(
                            max(first_box.width, second_box.width),
                            max(first_box.height, second_box.height),
                        )
                    ),
                )
                # Same person: high IoU OR nested box with close centers.
                if iou >= self.GHOST_IOU_THRESHOLD or (
                    containment >= 0.88
                    and distance / larger_diagonal <= 0.22
                ):
                    continue
                own_scale = max(
                    1.0,
                    min(
                        max(first_box.width, first_box.height),
                        max(second_box.width, second_box.height),
                    ),
                )
                if (
                    distance >= own_scale * 0.45
                    or distance / frame_diagonal >= self.MIN_SEPARATION_RATIO
                ):
                    return True
        return False

    def _decide_autogrid_layout(
        self,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        width: int,
        height: int = 1080,
        skip_ghost_pair_check: bool = False,
    ) -> dict:
        """Detect-then-switch auto grid (v2 — robust distinct & no head crop).

        Rules:
          1. 1 person visible  -> single layout (no grid forced)
          2. >=2 distinct people co-visible in same frame -> double layout after hysteresis
          3. Grid panels MUST have different identities (position_id AND track_id)
          4. Layout timeline always starts single at t=0, then switches to double when
             second person enters and is confirmed via GRID_ENTER_SAMPLES. Transisi
             single -> grid menggunakan style yang dipilih user (handled in renderer).
          5. Face crop Y uses headroom-aware _clamp_grid_y to avoid top clipping.

        Raw face counts not sufficient: duplicate detections / ByteTrack re-IDs
        must still count as one seat via stable position clustering.
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
        # Auto Grid counts visual people, not audio speakers. Diarization may
        # report one speaker while several people are visible (for example one
        # host talking while a guest listens). Speaker data is used below only
        # to choose panel ordering; it must not veto a visually valid grid.

        if not per_frame_tracked or person_count < 2 or len(position_targets) < 2:
            return {"layout": "single", "person_count": person_count}

        # ─── Person-first / detect-then-switch path ───────────────────────
        # Never force grid from t=0. Use stable seat positions so ByteTrack
        # re-IDs of the same person still count as one seat. Require co-visible
        # samples before switching, so timeline always starts single.
        if skip_ghost_pair_check and len(position_targets) >= 2:
            # Generate candidate seat pairs. Do not reject a pair merely because
            # one tracker ID appeared near both seats at different timestamps:
            # re-identification and cross-seat movement make that historical
            # signal unreliable. The frame-level validation below is the hard
            # gate and requires two distinct physical detections concurrently.
            candidate_pairs = []
            position_ids = sorted(position_targets.keys())
            # Generate pairs sorted by separation (descending)
            for i, pid_a in enumerate(position_ids):
                for pid_b in position_ids[i + 1:]:
                    if pid_a == pid_b:
                        continue
                    sep = abs(position_targets[pid_a] - position_targets[pid_b])
                    if sep >= width * self.MIN_SEPARATION_RATIO:
                        candidate_pairs.append((pid_a, pid_b, sep))
            
            # Sort by separation descending
            candidate_pairs.sort(key=lambda x: x[2], reverse=True)
            
            if not candidate_pairs:
                logger.info(
                    "podcast_reframe: person-first grid skipped (no sufficiently separated seat pairs)"
                )
                return {"layout": "single", "person_count": person_count}
            
            # Try each candidate pair until one succeeds
            for first_id, second_id, best_separation in candidate_pairs:
                logger.info(
                    f"podcast_reframe: trying grid pair P{first_id}/P{second_id} (sep={best_separation:.0f}px)"
                )

                geometry = self._calculate_grid_geometry(
                    first_id=first_id,
                    second_id=second_id,
                    position_targets=position_targets,
                    position_profiles=position_profiles,
                    width=width,
                    height=height,
                    skip_separation_check=True,
                )
                if not geometry:
                    logger.info(
                        f"podcast_reframe: person-first grid failed geometry "
                        f"(pair=P{first_id}/P{second_id}, sep={best_separation:.0f}px)"
                    )
                    continue  # Try next pair

                # Reject identical crop windows (would duplicate one person into both panels).
                same_crop = (
                    int(geometry.get("first_crop_x", -1)) == int(geometry.get("second_crop_x", -2))
                    and int(geometry.get("first_crop_y", -1)) == int(geometry.get("second_crop_y", -2))
                )
                if same_crop:
                    logger.info(
                        f"podcast_reframe: person-first grid rejected identical crops "
                        f"(pair=P{first_id}/P{second_id})"
                    )
                    continue  # Try next pair

                # Enforce distinct seats (no ghost duplicate)
                if first_id == second_id:
                    continue  # Try next pair
                pf = position_profiles.get(first_id, {})
                ps = position_profiles.get(second_id, {})
                if pf and ps and self._is_ghost_pair(pf, ps, width, height):
                    logger.info(f"podcast_reframe: person-first ghost pair rejected P{first_id}/P{second_id}")
                    continue  # Try next pair

                latest_speaker_id: Optional[int] = None
                if speaker_result and speaker_result.per_frame_speaker:
                    latest_frame = max(speaker_result.per_frame_speaker)
                    latest_speaker_id = int(speaker_result.per_frame_speaker[latest_frame])
                elif speaker_result and speaker_result.dominant_speaker_id is not None:
                    latest_speaker_id = int(speaker_result.dominant_speaker_id)

                if latest_speaker_id == second_id:
                    top_id, bottom_id = second_id, first_id
                else:
                    top_id, bottom_id = first_id, second_id

                if top_id == bottom_id:
                    continue  # Try next pair

                top_x = int(position_targets[top_id])
                bottom_x = int(position_targets[bottom_id])

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
                    i * self.SAMPLE_INTERVAL_SEC
                    for i in range(len(per_frame_tracked))
                ]

                # Detect-then-switch co-visibility with strict frame-level
                # physical-person validation. Historical track IDs are not a
                # valid identity veto because ByteTrack can re-identify a person
                # after motion or occlusion.
                seat_match_radius = max(
                    width * 0.12,
                    abs(position_targets[first_id] - position_targets[second_id]) * 0.45,
                )
                raw_double: List[bool] = []
                pair_hit_count = 0
                consecutive_pair_hits = 0
                max_consecutive_pair_hits = 0
                valid_frame_count = 0
                for frame_tracked in per_frame_tracked:
                    seats_hit: set[int] = set()
                    detections_per_seat: Dict[int, List[TrackedDetection]] = {
                        first_id: [],
                        second_id: [],
                    }
                    for detection in frame_tracked:
                        mapped = track_to_position.get(int(detection.track_id))
                        if mapped in (first_id, second_id):
                            seats_hit.add(int(mapped))
                            detections_per_seat[int(mapped)].append(detection)
                            continue
                        cx = float(detection.bbox.center_x)
                        best_seat = None
                        best_dist = seat_match_radius
                        for seat_id in (first_id, second_id):
                            dist = abs(cx - float(position_targets[seat_id]))
                            if dist <= best_dist:
                                best_dist = dist
                                best_seat = seat_id
                        if best_seat is not None:
                            seats_hit.add(int(best_seat))
                            detections_per_seat[int(best_seat)].append(detection)

                    if seats_hit:
                        valid_frame_count += 1
                    both = (
                        first_id in seats_hit
                        and second_id in seats_hit
                        and self._frame_has_distinct_people(
                            detections_per_seat[first_id],
                            detections_per_seat[second_id],
                            width,
                            height,
                        )
                    )
                    raw_double.append(both)
                    if both:
                        pair_hit_count += 1
                        consecutive_pair_hits += 1
                        max_consecutive_pair_hits = max(
                            max_consecutive_pair_hits,
                            consecutive_pair_hits,
                        )
                    else:
                        consecutive_pair_hits = 0

                if (
                    valid_frame_count <= 0
                    or max_consecutive_pair_hits < self.GRID_ENTER_SAMPLES
                ):
                    logger.info(
                        f"podcast_reframe: person-first grid skipped "
                        f"(pair=P{first_id}/P{second_id}, co-visible={pair_hit_count}, "
                        f"consecutive={max_consecutive_pair_hits}, need>={self.GRID_ENTER_SAMPLES})"
                    )
                    continue  # Try next pair

                coexist_ratio = pair_hit_count / max(valid_frame_count, 1)
                raw_ev = self._build_layout_events(raw_double, sample_timestamps)
                # _build_layout_events already backdates to t=0 when double is
                # valid from the start. Do not force-prepend a single event —
                # that adds an artificial delay before grid activates.
                layout_events = self._normalise_layout_events([
                    {"time": float(e.get("time", 0.0)), "layout": "double" if e.get("layout") == "double" else "single"}
                    for e in raw_ev
                ])

                if not any(e.get("layout") == "double" for e in layout_events):
                    continue  # Try next pair

                # SUCCESS! This pair passed all validations
                logger.info(
                    f"podcast_reframe: PERSON-FIRST GRID detect_then_switch "
                    f"(top=P{top_id}@{top_x}, bottom=P{bottom_id}@{bottom_x}, "
                    f"sep={best_separation:.0f}px, zoom={geometry['grid_zoom']:.2f}, "
                    f"coexist={coexist_ratio:.0%}, changes={max(0, len(layout_events) - 1)})"
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
            
            # All candidate pairs failed
            logger.info(
                f"podcast_reframe: person-first grid skipped (all {len(candidate_pairs)} candidate pairs failed)"
            )
            return {"layout": "single", "person_count": person_count}
        # ─── End person-first path ───

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
                    if not skip_ghost_pair_check:
                        separation = abs(position_targets.get(second_id, 0) - position_targets.get(first_id, 0))
                        if separation < width * self.MIN_SEPARATION_RATIO:
                            continue

                        # Fix #3: Ghost pair validation
                        prof_first = position_profiles.get(first_id, {})
                        prof_second = position_profiles.get(second_id, {})

                        # 3a: Comparable size check
                        area_first = prof_first.get("area", prof_first.get("width", 0) * prof_first.get("height", 0))
                        area_second = prof_second.get("area", prof_second.get("width", 0) * prof_second.get("height", 0))
                        if area_first > 0 and area_second > 0:
                            pair_size_ratio = min(area_first, area_second) / max(area_first, area_second)
                            if pair_size_ratio < self.MIN_PAIR_SIZE_RATIO:
                                continue

                        # 3b: Ghost pair check (IoU + center proximity)
                        if prof_first and prof_second:
                            if self._is_ghost_pair(prof_first, prof_second, width, height):
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
                            skip_separation_check=skip_ghost_pair_check,
                        )
                        if geometry:
                            pair_geometry[pair] = geometry
                    if geometry:
                        if skip_ghost_pair_check:
                            # Person-first mode: trust ByteTrack IDs, just check both are visible
                            first_visible = any(
                                track_to_position.get(int(d.track_id)) == first_id
                                for d in frame_tracked
                            )
                            second_visible = any(
                                track_to_position.get(int(d.track_id)) == second_id
                                for d in frame_tracked
                            )
                            if first_visible and second_visible:
                                pair_hits[pair] += 1
                        elif self._grid_frame_is_safe(
                            frame_tracked,
                            geometry,
                            first_id=first_id,
                            second_id=second_id,
                            track_to_position=track_to_position,
                        ):
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
        pair_visible = [
            first_id in positions and second_id in positions
            for positions in per_frame_positions
        ]
        if skip_ghost_pair_check:
            # Person-first mode: all frames where both are visible are safe
            frame_is_safe = list(pair_visible)
        else:
            frame_is_safe = [
                self._grid_frame_is_safe(
                    frame_tracked,
                    geometry,
                    first_id=first_id,
                    second_id=second_id,
                    track_to_position=track_to_position,
                )
                for frame_tracked in per_frame_tracked
            ]
        # A face entering both panels is unsafe and closes the grid immediately.
        # An ordinary detector miss still uses exit hysteresis so one bad sample
        # cannot make the layout flicker.
        unsafe_frames = [
            pair_visible[index] and not frame_is_safe[index]
            for index in range(len(per_frame_positions))
        ]
        raw_double = [
            pair_visible[index] and frame_is_safe[index]
            for index in range(len(per_frame_positions))
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


    def _normalise_layout_events(self, layout_events: List[dict]) -> List[dict]:
        """Normalize layout event payloads to {time, layout}."""
        cleaned: List[dict] = []
        for event in layout_events or []:
            layout = "double" if str(event.get("layout", "single")) == "double" else "single"
            if "time" in event:
                t = float(event.get("time", 0.0))
            elif "start_time" in event:
                t = float(event.get("start_time", 0.0))
            else:
                t = 0.0
            item = {"time": max(0.0, t), "layout": layout}
            if cleaned and abs(cleaned[-1]["time"] - item["time"]) <= 1e-3:
                cleaned[-1] = item
            elif not cleaned or cleaned[-1]["layout"] != item["layout"]:
                cleaned.append(item)
        if not cleaned:
            return [{"time": 0.0, "layout": "single"}]
        if cleaned[0]["time"] > 0.0:
            # Preserve leading single if first switch is later.
            if cleaned[0]["layout"] == "double":
                cleaned.insert(0, {"time": 0.0, "layout": "single"})
            else:
                cleaned[0]["time"] = 0.0
        return cleaned

    def _build_layout_events(
        self,
        raw_double: List[bool],
        timestamps: List[float],
        force_single: Optional[List[bool]] = None,
    ) -> List[dict]:
        """Turn noisy per-sample people counts into a stable layout timeline."""
        if not raw_double:
            return [{"time": 0.0, "layout": "single"}]

        # Always require confirmation, including at t=0. Once confirmed we
        # backdate the event to the start of the stable run, so a valid opening
        # two-shot does not have an artificial single-frame blind spot.
        state = False
        events = [{"time": 0.0, "layout": "single"}]
        pending_state: Optional[bool] = None
        pending_count = 0
        pending_start = 0

        def timestamp_at(index: int) -> float:
            return (
                float(timestamps[index])
                if index < len(timestamps)
                else index * self.SAMPLE_INTERVAL_SEC
            )

        def append_event(event_time: float, next_state: bool) -> None:
            event = {
                "time": max(0.0, float(event_time)),
                "layout": "double" if next_state else "single",
            }
            if events and event["time"] <= float(events[-1]["time"]) + 1e-3:
                events[-1] = event
            elif not events or events[-1]["layout"] != event["layout"]:
                events.append(event)

        for index in range(len(raw_double)):
            candidate = bool(raw_double[index])
            if force_single and index < len(force_single) and force_single[index]:
                if state:
                    state = False
                    append_event(timestamp_at(index), False)
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
                pending_start = index
            else:
                pending_count += 1

            threshold = (
                self.GRID_ENTER_SAMPLES if candidate else self.GRID_EXIT_SAMPLES
            )
            if pending_count < threshold:
                continue

            state = candidate
            append_event(timestamp_at(pending_start), state)
            pending_state = None
            pending_count = 0

        # Remove confirmed-but-too-short grid bursts. These are normally caused
        # by a cutaway, detector duplicate, or a person briefly crossing frame.
        if len(events) > 1:
            if len(timestamps) >= 2:
                deltas = [
                    float(timestamps[index]) - float(timestamps[index - 1])
                    for index in range(1, len(timestamps))
                    if float(timestamps[index]) > float(timestamps[index - 1])
                ]
                sample_step = float(np.median(deltas)) if deltas else self.SAMPLE_INTERVAL_SEC
            else:
                sample_step = self.SAMPLE_INTERVAL_SEC
            timeline_end = timestamp_at(len(raw_double) - 1) + sample_step
            filtered: List[dict] = []
            for index, event in enumerate(events):
                next_time = (
                    float(events[index + 1]["time"])
                    if index + 1 < len(events)
                    else timeline_end
                )
                if (
                    event["layout"] == "double"
                    and next_time - float(event["time"]) < self.MIN_GRID_SEGMENT_SECONDS
                ):
                    continue
                if filtered and filtered[-1]["layout"] == event["layout"]:
                    continue
                filtered.append(event)
            events = filtered or [{"time": 0.0, "layout": "single"}]

        return events

    def _grid_frame_is_safe(
        self,
        frame_tracked: List[TrackedDetection],
        geometry: dict,
        first_id: Optional[int] = None,
        second_id: Optional[int] = None,
        track_to_position: Optional[Dict[int, int]] = None,
    ) -> bool:
        """Require one exclusive, distinct face inside each source crop."""
        crop_w = int(geometry.get("crop_w", 0))
        crop_h = int(geometry.get("crop_h", 0))
        if crop_w <= 0 or crop_h <= 0:
            return False

        first_rect = (
            int(geometry.get("first_crop_x", geometry.get("top_crop_x", 0))),
            int(geometry.get("first_crop_y", geometry.get("top_crop_y", 0))),
        )
        second_rect = (
            int(geometry.get("second_crop_x", geometry.get("bottom_crop_x", 0))),
            int(geometry.get("second_crop_y", geometry.get("bottom_crop_y", 0))),
        )

        def intersects(bbox: BBox, crop_x: int, crop_y: int) -> bool:
            return not (
                bbox.x2 <= crop_x
                or bbox.x1 >= crop_x + crop_w
                or bbox.y2 <= crop_y
                or bbox.y1 >= crop_y + crop_h
            )

        if any(
            intersects(detection.bbox, *first_rect)
            and intersects(detection.bbox, *second_rect)
            for detection in frame_tracked
        ):
            return False

        if first_id is None or second_id is None or track_to_position is None:
            return bool(frame_tracked)

        first_detections = [
            detection
            for detection in frame_tracked
            if track_to_position.get(int(detection.track_id)) == int(first_id)
        ]
        second_detections = [
            detection
            for detection in frame_tracked
            if track_to_position.get(int(detection.track_id)) == int(second_id)
        ]
        if not first_detections or not second_detections:
            return False

        first_detection = max(first_detections, key=lambda item: item.bbox.area)
        second_detection = max(second_detections, key=lambda item: item.bbox.area)
        first_only = (
            intersects(first_detection.bbox, *first_rect)
            and not intersects(first_detection.bbox, *second_rect)
        )
        second_only = (
            intersects(second_detection.bbox, *second_rect)
            and not intersects(second_detection.bbox, *first_rect)
        )
        if not first_only or not second_only:
            return False

        # A detector duplicate can survive tracking with a different ID. Never
        # approve it as a second panel when the live boxes still overlap.
        return self._compute_iou(first_detection.bbox, second_detection.bbox) < 0.10

    def _calculate_grid_geometry(
        self,
        first_id: int,
        second_id: int,
        position_targets: Dict[int, float],
        position_profiles: Dict[int, Dict[str, float]],
        width: int,
        height: int,
        skip_separation_check: bool = False,
    ) -> Optional[dict]:
        """Find the mildest crop that isolates each person from the other.

        If isolation would require zooming past ``GRID_MAX_ZOOM``, the pair is
        rejected and auto-grid falls back to the centered single-speaker view.
        """
        if first_id == second_id:
            return None

        # Convert body profiles to face profiles for proper grid geometry.
        # Prefer real face_* fields when present (person-first detector).
        # Body bbox is used for horizontal seat separation; face for Y framing.
        def body_to_face_profile(body_profile: dict) -> dict:
            """Estimate face from body, or pass through real face measurements."""
            body_height = float(body_profile.get("height", height * 0.8))
            body_width = float(body_profile.get("width", width * 0.3))
            body_y = float(body_profile.get("y", height * 0.5))
            body_x = float(body_profile.get("x", width * 0.5))

            # Real face from person-first crop detector (preferred).
            if body_profile.get("face_y") is not None:
                face_y = float(body_profile["face_y"])
                face_h = float(body_profile.get("face_height") or max(body_height * 0.18, 40.0))
                face_w = float(body_profile.get("face_width") or max(body_width * 0.22, 40.0))
                face_x = float(body_profile.get("face_x") or body_x)
                return {
                    "x": body_x,  # keep body X for left/right isolation
                    "y": face_y,
                    "width": face_w,
                    "height": face_h,
                    "area": face_w * face_h,
                    "face_x": face_x,
                }

            # Already face-sized profile (legacy face-tracker path) — do not re-shrink.
            looks_like_face = (
                body_height > 0
                and body_height <= height * 0.35
                and body_width <= width * 0.28
                and body_height <= body_width * 1.6
            )
            if looks_like_face:
                return {
                    "x": body_x,
                    "y": body_y,
                    "width": body_width,
                    "height": body_height,
                    "area": body_width * body_height,
                }

            # Estimate face at the TOP of the body. The head sits at the top
            # of a person bbox, so the face center is face_height/2 below the
            # body top — NOT 10% into the body (that lands near the neck and
            # causes the "nose-only" grid crop). Keep the size generous so the
            # headroom clamp in _clamp_grid_y keeps the forehead in frame even
            # when the detector box starts at the shoulders.
            face_height = max(body_height * 0.18, body_width * 0.28, 48.0)
            face_width = max(body_width * 0.22, face_height * 0.75, 40.0)
            body_top = body_y - body_height / 2
            # Face center = top of body + half face height (head fully inside body).
            face_y = body_top + face_height / 2

            return {
                "x": body_x,
                "y": face_y,
                "width": face_width,
                "height": face_height,
                "area": face_width * face_height,
            }

        all_profiles = {
            position_id: body_to_face_profile({
                "x": float(target_x),
                "width": width * 0.3,
                "height": height * 0.8,
                **position_profiles.get(position_id, {}),
            })
            for position_id, target_x in position_targets.items()
        }
        first_profile = all_profiles.get(first_id, body_to_face_profile({
            "x": width / 3,
            "y": height * 0.5,
            "width": width * 0.3,
            "height": height * 0.8,
        }))
        second_profile = all_profiles.get(second_id, body_to_face_profile({
            "x": width * 2 / 3,
            "y": height * 0.5,
            "width": width * 0.3,
            "height": height * 0.8,
        }))
        separation = abs(first_profile["x"] - second_profile["x"])
        if not skip_separation_check and separation < width * self.MIN_SEPARATION_RATIO:
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
                # Profile already contains face position (converted from body bbox above)
                first_crop_y = self._clamp_grid_y(
                    first_profile["y"], first_profile["height"], crop_h, height
                )
                second_crop_y = self._clamp_grid_y(
                    second_profile["y"], second_profile["height"], crop_h, height
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

        # Fallback for face-to-face: isolation impossible — avoid over-zoom.
        # Use mildest possible crop that still keeps full head (no kejauhan zoom).
        # Pilih zoom minimal yang masih izolasi parsial, bukan langsung MAX.
        best_zoom = self.GRID_BASE_ZOOM
        target_crop_w = min(width, max(2, int(base_crop_w / best_zoom)))
        target_crop_h = min(height, max(2, int(target_crop_w * 8 / 9)))
        # Clamp agar face full height tetap muat dengan headroom
        needed_h = max(
            first_profile["height"], second_profile["height"], 1.0
        ) * (1 + self.GRID_FACE_MARGIN + 0.25)  # + headroom extra
        if target_crop_h < needed_h:
            target_crop_h = int(needed_h)
            target_crop_w = int(target_crop_h * 9 / 8)
            target_crop_w = min(width, target_crop_w)

        crop_w_fallback = min(width, target_crop_w)
        crop_h_fallback = min(height, max(2, int(crop_w_fallback * 8 / 9)))
        # Jika masih ketinggian kurang, sesuaikan
        if crop_h_fallback < needed_h and needed_h <= height:
            crop_h_fallback = int(min(height, needed_h))
            crop_w_fallback = min(width, int(crop_h_fallback * 9 / 8))

        first_crop_x_fb = self._clamp_x(first_profile["x"], crop_w_fallback, width)
        second_crop_x_fb = self._clamp_x(second_profile["x"], crop_w_fallback, width)
        # Profile already contains face position (converted from body bbox above)
        first_crop_y_fb = self._clamp_grid_y(first_profile["y"], first_profile["height"], crop_h_fallback, height)
        second_crop_y_fb = self._clamp_grid_y(second_profile["y"], second_profile["height"], crop_h_fallback, height)

        final_zoom = base_crop_w / max(1, crop_w_fallback)
        logger.info(
            f"podcast_reframe: grid pair accepted (fallback no-overzoom, headroom fix) "
            f"(P{first_id}/P{second_id}, separation={separation:.0f}px, "
            f"zoom={final_zoom:.2f} (was {self.GRID_MAX_ZOOM}), crop={crop_w_fallback}x{crop_h_fallback})"
        )
        return {
            "first_id": first_id,
            "second_id": second_id,
            "crop_w": crop_w_fallback,
            "crop_h": crop_h_fallback,
            "first_crop_x": first_crop_x_fb,
            "second_crop_x": second_crop_x_fb,
            "first_crop_y": first_crop_y_fb,
            "second_crop_y": second_crop_y_fb,
            "grid_zoom": round(final_zoom, 3),
        }

    @staticmethod
    def _clamp_grid_y(face_y: float, face_height: float, crop_h: int, frame_h: int) -> int:
        """Place face in panel with forehead + eyes visible (not nose-only).

        Talking-head framing: eyes sit ~38% down the panel. Two hard guarantees:

          * floor  (keep head in):  crop_top <= face_top - headroom
            → forehead / hair never clipped, even when grid zoom tightens.
          * ceiling (keep eyes in): crop_top <= face_top + face_h * 0.30
            → eyes are NEVER above the crop top (prevents the "nose-only" cut
              that happens when a body-estimated face_y lands too low).

        When both cannot hold simultaneously (crop too short for the head),
        the floor wins — keeping the full head inside is more important than
        hitting the exact 38% line.
        """
        if crop_h >= frame_h:
            return 0

        face_h = max(float(face_height), 1.0)
        face_top = float(face_y) - face_h / 2
        face_bottom = float(face_y) + face_h / 2

        # Headroom: forehead + hair. Prefer face-relative, floor by panel fraction.
        headroom = max(face_h * 1.05, crop_h * 0.18)
        chin_margin = max(face_h * 0.55, crop_h * 0.10)

        # Ideal: eyes ~38% down the panel (natural talking-head framing).
        eyes_y = float(face_y) - face_h * 0.10
        target_y = int(eyes_y - crop_h * 0.38)

        # Hard floor: face_top - headroom must stay inside crop.
        floor_y = int(face_top - headroom)
        # Hard ceiling: eyes must stay inside crop (crop_top <= face_top + 30% face).
        ceiling_y = int(face_top + face_h * 0.30)

        # Apply ceiling first — this is the guarantee that fixes "nose-only" cuts.
        target_y = min(target_y, ceiling_y)
        # Then apply floor (keep head in). Floor wins on conflict.
        target_y = min(target_y, floor_y)

        # If room remains, also try to keep the chin inside.
        min_y_for_chin = int(face_bottom + chin_margin - crop_h)
        if min_y_for_chin <= floor_y:
            target_y = max(target_y, min_y_for_chin)

        max_y = max(0, frame_h - crop_h)
        return max(0, min(int(target_y), max_y))

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
        recent_live_positions: Optional[Dict[int, List[float]]] = None,
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
                # Prefer recent live position average over the static whole-clip
                # median. This eliminates snap-back jitter when the hold fallback
                # disagrees with where the person actually is now.
                if (
                    recent_live_positions
                    and active_speaker in recent_live_positions
                    and recent_live_positions[active_speaker]
                ):
                    target_x_hint = float(np.mean(recent_live_positions[active_speaker]))
                else:
                    target_x_hint = position_targets.get(active_speaker)
                target_profile = position_target_profiles.get(active_speaker)
                if target_x_hint is None and target_profile:
                    target_x_hint = target_profile.get("x")

        def get_det_cx(d: TrackedDetection) -> float:
            return d.face_bbox.center_x if getattr(d, 'face_bbox', None) is not None else d.bbox.center_x

        def get_det_profile_distance(d: TrackedDetection, prof: dict) -> float:
            box = d.face_bbox if getattr(d, 'face_bbox', None) is not None else d.bbox
            return self._bbox_profile_distance(box, prof, frame_width, frame_height)

        # A single visible person is the strongest possible visual signal. Do
        # not hold a stale diarization seat in this case: doing so leaves the
        # only person off-centre until a later pan event is accepted.
        if len(frame_tracked) == 1 and len(position_targets) <= 1:
            only_detection = frame_tracked[0]
            only_position = track_to_position.get(only_detection.track_id)
            return (
                int(get_det_cx(only_detection)),
                only_detection,
                only_position,
                "only_visible_person",
            )
        if len(frame_faces) == 1 and not frame_tracked and len(position_targets) <= 1:
            return int(frame_faces[0]), None, None, "only_visible_face"

        if active_speaker is not None:
            matching_detections = [
                detection for detection in frame_tracked
                if track_to_position.get(detection.track_id) == active_speaker
            ]
            if matching_detections:
                target_detection = min(
                    matching_detections,
                    key=lambda d: abs(
                        get_det_cx(d)
                        - (target_x_hint if target_x_hint is not None else get_det_cx(d))
                    ),
                )
                return int(get_det_cx(target_detection)), target_detection, active_speaker, "track"

            if target_profile and frame_tracked:
                target_detection = min(
                    frame_tracked,
                    key=lambda d: get_det_profile_distance(d, target_profile),
                )
                profile_distance = get_det_profile_distance(target_detection, target_profile)
                if profile_distance <= self.SPEAKER_TARGET_PROFILE_MISMATCH:
                    return int(get_det_cx(target_detection)), target_detection, active_speaker, "profile"

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

        # Recent live position buffer: tracks the last N live observations per
        # position_id so that hold/fallback uses recent truth, not the static
        # whole-clip median which causes snap-back jitter.
        RECENT_LIVE_WINDOW = 8  # ~2.6s at 3fps sampling
        recent_live_positions: Dict[int, List[float]] = defaultdict(list)

        for i, frame_faces in enumerate(per_frame_faces):
            t = sample_timestamps[i] if i < len(sample_timestamps) else i * self.SAMPLE_INTERVAL_SEC
            frame_idx_approx = (
                sample_frame_indices[i]
                if i < len(sample_frame_indices)
                else int(t * fps)
            )
            frame_tracked = per_frame_tracked[i] if i < len(per_frame_tracked) else []
            last_center = keyframes[-1][1] + crop_w / 2 if keyframes else None

            # Update recent live positions from current frame's tracked detections
            for det in frame_tracked:
                pos_id = track_to_position.get(int(det.track_id))
                if pos_id is not None:
                    det_cx = det.face_bbox.center_x if getattr(det, 'face_bbox', None) is not None else det.bbox.center_x
                    buf = recent_live_positions[pos_id]
                    buf.append(float(det_cx))
                    if len(buf) > RECENT_LIVE_WINDOW:
                        buf.pop(0)

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
                recent_live_positions=dict(recent_live_positions),
            )

            if cx is None:
                # No reliable face or speaker target → hold previous position
                if keyframes:
                    keyframes.append((t, keyframes[-1][1], keyframes[-1][2], "hold"))
                continue

            # BBOX-AWARE CENTERING: ensure face + margin fits in crop window
            face_margin_applied = False
            if frame_tracked:
                # Find the tracked detection closest to our target cx
                best_det = target_detection or min(
                    frame_tracked,
                    key=lambda d: abs((d.face_bbox.center_x if getattr(d, 'face_bbox', None) is not None else d.bbox.center_x) - cx),
                )
                mismatch_threshold = width * self.SPEAKER_TARGET_MISMATCH_RATIO
                best_det_cx = best_det.face_bbox.center_x if getattr(best_det, 'face_bbox', None) is not None else best_det.bbox.center_x
                if target_detection or abs(best_det_cx - cx) <= mismatch_threshold:
                    box_to_use = best_det.face_bbox if getattr(best_det, 'face_bbox', None) is not None else best_det.bbox
                    # Fallback headroom estimation from person box if face is not found
                    if getattr(best_det, 'face_bbox', None) is None:
                        # Estimate head bbox from person bbox: top 35% of person height
                        p_h = box_to_use.height
                        head_y = box_to_use.y1 + 0.175 * p_h
                        head_w = 0.25 * box_to_use.width
                        box_to_use = BBox(
                            box_to_use.center_x - head_w/2,
                            head_y - head_w/2,
                            box_to_use.center_x + head_w/2,
                            head_y + head_w/2
                        )
                    face_w = box_to_use.width
                    try:
                        from src.config import settings
                        margin_ratio = getattr(
                            settings, "CENTERING_FACE_MARGIN_RATIO", 0.6
                        )
                    except (ImportError, ModuleNotFoundError):
                        margin_ratio = 0.6
                    margin = face_w * max(0.0, float(margin_ratio))

                    desired_left = box_to_use.x1 - margin
                    desired_right = box_to_use.x2 + margin

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

        # ─── Pre-stabilization: rolling median smoothing ─────────────────
        # Noise from per-frame detection jitter creates spurious keyframe
        # candidates. A small rolling median (window=5) absorbs single-frame
        # outliers before the dead-zone filter sees them.
        SMOOTH_WINDOW = 5
        if len(keyframes) >= SMOOTH_WINDOW:
            smoothed_keyframes: List[Tuple[float, int, Optional[int], str]] = []
            half_w = SMOOTH_WINDOW // 2
            xs = [kf[1] for kf in keyframes]
            for i, (t, _x, spk, src) in enumerate(keyframes):
                window_start = max(0, i - half_w)
                window_end = min(len(xs), i + half_w + 1)
                median_x = int(np.median(xs[window_start:window_end]))
                smoothed_keyframes.append((t, median_x, spk, src))
            keyframes = smoothed_keyframes

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
            # 2. Dead zone + hold minimum + consecutive speaker-change guard
            SPEAKER_CHANGE_CONFIRM_SAMPLES = 3  # require 3 consecutive samples confirming new speaker
            stabilized: List[Tuple[float, int, Optional[int], str]] = [keyframes[0]]
            # Track consecutive samples with same new speaker to confirm a real change
            pending_speaker_change: Optional[int] = None
            pending_speaker_count: int = 0

            for t, x, speaker_id, source in keyframes[1:]:
                last_t, last_x, last_speaker_id, _ = stabilized[-1]
                movement = abs(x - last_x)
                time_since_last = t - last_t

                # Speaker change requires consecutive confirmation to avoid
                # single-sample diarization noise causing immediate pan.
                speaker_confirmed = False
                if (
                    speaker_id is not None
                    and last_speaker_id is not None
                    and speaker_id != last_speaker_id
                ):
                    if pending_speaker_change == speaker_id:
                        pending_speaker_count += 1
                    else:
                        pending_speaker_change = speaker_id
                        pending_speaker_count = 1
                    if pending_speaker_count >= SPEAKER_CHANGE_CONFIRM_SAMPLES:
                        speaker_confirmed = True
                        pending_speaker_change = None
                        pending_speaker_count = 0
                else:
                    # Same speaker or unknown — reset pending
                    pending_speaker_change = None
                    pending_speaker_count = 0

                if (
                    movement >= self.PAN_DEAD_ZONE_PX
                    and (time_since_last >= self.PAN_HOLD_MIN_SEC or speaker_confirmed)
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
            # Layout cuts and camera movement are separate concerns.  A hard
            # layout cut is fine, but snapping the crop between noisy detector
            # samples creates visible left/right jumps.  Interpolate crop X on
            # every output frame even when the selected layout style is `cut`.
            camera_style = "slide" if transition_style == "cut" else transition_style
            camera_transition = max(0.45, transition_duration)
            crop_x_expr = self._build_panning_expression(
                [(t, x) for t, x, _, _ in stabilized],
                camera_transition,
                camera_style,
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
        fps_value = max(1.0, float(fps))
        vf = (
            f"setpts=PTS-STARTPTS,crop={crop_w}:{height}:{crop_x_expr}:0,"
            f"scale=1080:1920,format=yuv420p,setsar=1,"
            f"fps={fps_value:.6f},settb=AVTB"
        )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-af", self.AUDIO_FILTER,
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-b:a", "192k",
            "-fps_mode", "cfr",
            "-movflags", "+faststart",
            output_path,
        ]

        logger.info(
            f"podcast_reframe: DYNAMIC PANNING ({len(stabilized)} keyframes, "
            f"crop_w={crop_w})"
        )

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
            and timeline_is_safe(output_path)
        ):
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
            "[0:v]setpts=PTS-STARTPTS,split=3[single_src][top_src][bottom_src]",
            (
                f"[single_src]crop={single_crop_w}:{height}:{single_x_expr}:0,"
                f"scale=1080:1920:flags=lanczos,format=yuv420p,setsar=1,"
                f"fps={fps_value:.6f},settb=AVTB,setpts=PTS-STARTPTS[single]"
            ),
            (
                f"[top_src]crop={crop_w}:{crop_h}:{top_x}:{top_y},"
                f"scale=1080:{self.GRID_PANEL_HEIGHT}:flags=lanczos,"
                "format=yuv420p,setsar=1[top]"
            ),
            (
                f"[bottom_src]crop={crop_w}:{crop_h}:{bottom_x}:{bottom_y},"
                f"scale=1080:{self.GRID_PANEL_HEIGHT}:flags=lanczos,"
                "format=yuv420p,setsar=1[bottom]"
            ),
            (
                f"[top][bottom]vstack=inputs=2,scale=1080:1920:flags=lanczos,"
                f"format=yuv420p,setsar=1,fps={fps_value:.6f},"
                "settb=AVTB,setpts=PTS-STARTPTS[grid]"
            ),
            transition_graph,
        ]
        filter_complex = ";".join(filters)
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", f"[{output_label}]", "-map", "0:a?",
            "-af", self.AUDIO_FILTER,
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-b:a", "192k",
            "-fps_mode", "cfr",
            "-movflags", "+faststart",
            output_path,
        ]

        logger.info(
            "podcast_reframe: DYNAMIC AUTO GRID "
            f"(events={len(layout_events)}, transition={transition_style}/"
            f"{transition_duration:.2f}s, zoom={decision.get('grid_zoom', 1.0):.2f})"
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if (
            result.returncode != 0
            or not os.path.exists(output_path)
            or os.path.getsize(output_path) <= 1000
            or not timeline_is_safe(output_path, expected_duration=duration)
        ):
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
                "setpts=PTS-STARTPTS,format=yuv420p,setsar=1,settb=AVTB"
                f"[layout_seg_{index}]"
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
        """Simple 9:16 crop centered on detected face with a clean A/V clock."""
        crop_w = min(int(height * 9 / 16), width)
        crop_x = self._clamp_x(decision["crop_x"], crop_w, width)

        vf = (
            f"setpts=PTS-STARTPTS,crop={crop_w}:{height}:{crop_x}:0,"
            "scale=1080:1920,format=yuv420p,setsar=1"
        )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-af", self.AUDIO_FILTER,
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
            and timeline_is_safe(output_path)
        ):
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
            logger.info(
                f"podcast_reframe: grid speakers close together "
                f"(separation={abs(float(top_center_x) - float(bottom_center_x)):.0f}px, "
                f"threshold={width * self.MIN_SEPARATION_RATIO:.0f}px) — proceeding anyway"
            )

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
            f"setpts=PTS-STARTPTS,split=2[top][bot];"
            f"[top]crop={crop_w}:{crop_h}:{top_x}:{top_y},scale=1080:{self.GRID_PANEL_HEIGHT},format=yuv420p[t];"
            f"[bot]crop={crop_w}:{crop_h}:{bottom_x}:{bottom_y},scale=1080:{self.GRID_PANEL_HEIGHT},format=yuv420p[b];"
            f"[t][b]vstack=inputs=2,setsar=1[vout]"
        )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", vf,
            "-map", "[vout]", "-map", "0:a?",
            "-af", self.AUDIO_FILTER,
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
            and timeline_is_safe(output_path)
        ):
            pc = decision.get("person_count", 2)
            logger.info(
                f"podcast_reframe: 50/50 grid OK "
                f"(top={top_x},{top_y}, bottom={bottom_x},{bottom_y}, "
                f"crop={crop_w}x{crop_h}, zoom={grid_zoom:.2f})"
            )
            logger.info(
                f"podcast_reframe: grid regions — "
                f"TOP panel: source[x={top_x}..{top_x + crop_w}, y={top_y}..{top_y + crop_h}] "
                f"(person P{decision.get('top_track_id','?')} center@{top_center_x}), "
                f"BOTTOM panel: source[x={bottom_x}..{bottom_x + crop_w}, y={bottom_y}..{bottom_y + crop_h}] "
                f"(person P{decision.get('bottom_track_id','?')} center@{bottom_center_x}), "
                f"source_frame={width}x{height}, output=1080x1920 (2×960px panels)"
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

    def _filter_duplicate_person_detections(
        self,
        detections: List[Tuple[float, float, float, float, float]],
    ) -> List[Tuple[float, float, float, float, float]]:
        """Suppress duplicate body detections before they create tracker IDs.

        Shared with PersonDetector so both the legacy and person-first paths
        use the same nested/tight-loose suppression rules.
        """
        from src.infrastructure.person_detector import filter_duplicate_person_boxes

        return filter_duplicate_person_boxes(detections)

    @staticmethod
    def _compute_iou(box_a: 'BBox', box_b: 'BBox') -> float:
        """Compute IoU between two BBox instances."""
        x1 = max(box_a.x1, box_b.x1)
        y1 = max(box_a.y1, box_b.y1)
        x2 = min(box_a.x2, box_b.x2)
        y2 = min(box_a.y2, box_b.y2)
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = box_a.area
        area_b = box_b.area
        union = area_a + area_b - intersection
        return intersection / union if union > 0 else 0.0

    def _is_ghost_pair(
        self,
        prof_a: dict,
        prof_b: dict,
        width: int,
        height: int,
    ) -> bool:
        """Check if two position profiles represent the same person (ghost pair).

        Uses IoU, nested containment, and center distance proximity.
        Profile values are in PIXELS (center_x, center_y, width, height).
        """
        ax, ay = prof_a.get("x", 0), prof_a.get("y", 0)
        aw, ah = prof_a.get("width", 0), prof_a.get("height", 0)
        bx, by = prof_b.get("x", 0), prof_b.get("y", 0)
        bw, bh = prof_b.get("width", 0), prof_b.get("height", 0)

        box_a = BBox(ax - aw / 2, ay - ah / 2, ax + aw / 2, ay + ah / 2)
        box_b = BBox(bx - bw / 2, by - bh / 2, bx + bw / 2, by + bh / 2)

        # IoU check
        iou = self._compute_iou(box_a, box_b)
        if iou > self.GHOST_IOU_THRESHOLD:
            return True

        # Nested tight/loose body boxes: low IoU but high containment.
        intersection_w = max(0.0, min(box_a.x2, box_b.x2) - max(box_a.x1, box_b.x1))
        intersection_h = max(0.0, min(box_a.y2, box_b.y2) - max(box_a.y1, box_b.y1))
        intersection = intersection_w * intersection_h
        containment = intersection / max(1.0, min(box_a.area, box_b.area))
        larger_diagonal = max(
            1.0,
            float(np.hypot(max(box_a.width, box_b.width), max(box_a.height, box_b.height))),
        )
        center_dist = float(np.hypot(ax - bx, ay - by))
        if containment >= 0.88 and center_dist / larger_diagonal <= 0.22:
            return True

        # Shared face evidence: two body tracks resolving to one head.
        if (
            "face_x" in prof_a
            and "face_y" in prof_a
            and "face_x" in prof_b
            and "face_y" in prof_b
        ):
            face_dist = float(
                np.hypot(
                    float(prof_a["face_x"]) - float(prof_b["face_x"]),
                    float(prof_a["face_y"]) - float(prof_b["face_y"]),
                )
            )
            face_scale = max(
                1.0,
                min(
                    max(float(prof_a.get("face_width", 0)), float(prof_a.get("face_height", 0))),
                    max(float(prof_b.get("face_width", 0)), float(prof_b.get("face_height", 0))),
                ),
            )
            if face_dist <= face_scale * 0.55:
                return True

        # Center distance proximity check
        frame_diag = (width**2 + height**2) ** 0.5
        if frame_diag > 0:
            dist_ratio = center_dist / frame_diag
            # Tight threshold: unconditional ghost
            if dist_ratio < self.GHOST_CENTER_DIST_RATIO:
                return True
            # Broader threshold: ghost if areas are very similar (same person duplicate)
            if dist_ratio < self.GHOST_CENTER_DIST_BROAD:
                area_a = prof_a.get("area", aw * ah)
                area_b = prof_b.get("area", bw * bh)
                if area_a > 0 and area_b > 0:
                    area_ratio = min(area_a, area_b) / max(area_a, area_b)
                    if area_ratio > 0.65:
                        return True

        return False

    @staticmethod
    def _median_profile(values: Dict[str, List[float]]) -> Dict[str, float]:
        """Return a median face profile for one tracker ID.

        Always carries the body bbox (x/y/width/height/area). When the tracker
        provided real face boxes (person-first mode), also carries face_x /
        face_y / face_width / face_height so grid-Y framing can use the actual
        face instead of a body→face estimate.
        """
        result = {
            "x": float(np.median(values.get("x") or [0.0])),
            "y": float(np.median(values.get("y") or [0.0])),
            "width": float(np.median(values.get("width") or [0.0])),
            "height": float(np.median(values.get("height") or [0.0])),
            "area": float(np.median(values.get("area") or [0.0])),
        }
        face_x = values.get("face_x") or []
        face_y = values.get("face_y") or []
        if face_x and face_y:
            result["face_x"] = float(np.median(face_x))
            result["face_y"] = float(np.median(face_y))
            result["face_width"] = float(np.median(values.get("face_width") or [0.0]))
            result["face_height"] = float(np.median(values.get("face_height") or [0.0]))
        return result

    @staticmethod
    def _merge_profiles(profiles: List[Dict[str, float]]) -> Dict[str, float]:
        """Merge multiple track profiles that represent the same seat/person."""
        result = {
            "x": float(np.median([p.get("x", 0.0) for p in profiles])),
            "y": float(np.median([p.get("y", 0.0) for p in profiles])),
            "width": float(np.median([p.get("width", 0.0) for p in profiles])),
            "height": float(np.median([p.get("height", 0.0) for p in profiles])),
            "area": float(np.median([p.get("area", 0.0) for p in profiles])),
        }
        return result

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
            "-vf", "setpts=PTS-STARTPTS,crop=ih*9/16:ih,scale=1080:1920,format=yuv420p,setsar=1",
            "-af", self.AUDIO_FILTER,
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        return (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
            and timeline_is_safe(output_path)
        )

    async def _simple_crop(self, video_path: str, output_path: str, target_aspect: str) -> bool:
        """Simple crop for non-9:16."""
        if target_aspect == "1:1":
            vf = "setpts=PTS-STARTPTS,crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
        else:
            shutil.copy2(video_path, output_path)
            return True

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-af", self.AUDIO_FILTER,
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        return (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
            and timeline_is_safe(output_path)
        )

    def _detect_and_track_persons_first(
        self, video_path: str, width: int, height: int, fps: float, total_frames: int
    ) -> dict:
        """Detect persons using RF-DETR and track them with ByteTrack/SimpleIoU.
        Detect faces only inside the person crops using RetinaFace/SCRFD/MediaPipe.
        """
        import cv2
        cv2.setNumThreads(0)
        
        analytics_crops_processed = 0
        analytics_faces_found = 0
        analytics_id_switch_sets = set()

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

        sample_indices = self._sample_frame_indices(total_frames, fps)
        from src.config import settings
        person_conf_thresh = settings.PERSON_CONF_THRESHOLD
        face_conf_thresh = settings.FACE_CONFIDENCE
        head_ratio = settings.FACE_REGION_HEAD_RATIO

        self._load_person_detector()
        self._load_crop_face_detector()
        self._init_person_tracker(fps)

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
            h_frame, w_frame = frame_rgb.shape[:2]

            # 1. Person Detection — delegate to PersonDetector which handles
            # class filtering (PERSON_CLASS_ID=0 only) and duplicate suppression.
            person_bboxes: List[Tuple[float, float, float, float, float]] = []

            if hasattr(self, "_person_detector_instance") and self._person_detector_instance is not None:
                detections = self._person_detector_instance.detect(
                    frame_rgb, confidence_override=person_conf_thresh
                )
                person_bboxes = [det.to_box_tuple() for det in detections]

                # DEBUG: low-threshold probe — first 10 samples only.
                # Separates "RF-DETR never saw person 2" from "cut by PERSON_CONF_THRESHOLD".
                if len(sample_frame_indices) < 10:
                    try:
                        det = self._person_detector_instance
                        if det._model is not None and getattr(det, "_use_supervision", False):
                            import supervision as sv
                            raw = det._model.predict(frame_rgb, threshold=0.1)
                            confs = []
                            if isinstance(raw, sv.Detections) and raw.confidence is not None:
                                for i in range(len(raw)):
                                    cid = int(raw.class_id[i]) if raw.class_id is not None else -1
                                    if cid == det.PERSON_CLASS_ID:
                                        confs.append(round(float(raw.confidence[i]), 2))
                            logger.info(
                                f"podcast_reframe: DEBUG low-thresh frame={frame_idx} "
                                f"raw_person_count={len(confs)} confs={confs} "
                                f"prod_count={len(person_bboxes)} "
                                f"prod_thresh={person_conf_thresh}"
                            )
                        else:
                            low = det.detect(frame_rgb, confidence_override=0.1)
                            logger.info(
                                f"podcast_reframe: DEBUG low-thresh frame={frame_idx} "
                                f"count={len(low)} "
                                f"confs={[round(d.confidence, 2) for d in low]} "
                                f"prod_count={len(person_bboxes)} "
                                f"prod_thresh={person_conf_thresh}"
                            )
                    except Exception as dbg_err:
                        logger.debug(f"podcast_reframe: low-thresh debug failed: {dbg_err}")

            if not person_bboxes:

                self._load_face_detector()
                if self._use_legacy_api:
                    results = self._face_detector.process(frame_rgb)
                    if results.detections:
                        for det in results.detections:
                            bbox = det.location_data.relative_bounding_box
                            x1 = bbox.xmin * w_frame
                            y1 = bbox.ymin * h_frame
                            x2 = (bbox.xmin + bbox.width) * w_frame
                            y2 = (bbox.ymin + bbox.height) * h_frame
                            person_bboxes.append((x1, y1, x2, y2, 0.99))
                else:
                    import mediapipe as mp
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                    result = self._face_detector.detect(mp_image)
                    if result.detections:
                        for det in result.detections:
                            bbox = det.bounding_box
                            person_bboxes.append((bbox.origin_x, bbox.origin_y, bbox.origin_x + bbox.width, bbox.origin_y + bbox.height, 0.99))

            # Duplicate suppression for MediaPipe face fallback path only.
            # PersonDetector.detect() already handles this internally, but
            # the MediaPipe fallback adds raw boxes that still need filtering.
            if not (hasattr(self, "_person_detector_instance") and self._person_detector_instance is not None):
                person_bboxes = self._filter_duplicate_person_detections(person_bboxes)

            # Log first frame detection details for debugging
            if len(sample_frame_indices) == 0 and person_bboxes:
                logger.info(
                    f"podcast_reframe: person detection frame[0] — "
                    f"{len(person_bboxes)} persons found: "
                    + ", ".join(
                        f"({b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f} conf={b[4]:.2f} cx={((b[0]+b[2])/2):.0f})"
                        for b in person_bboxes
                    )
                )

            # 2. Update Person Tracker
            tracked_detections: List[TrackedDetection] = []
            if self._person_tracker_type == "bytetrack":
                import supervision as sv
                if person_bboxes:
                    xyxy = np.array([[b[0], b[1], b[2], b[3]] for b in person_bboxes], dtype=np.float32)
                    confidence = np.array([b[4] for b in person_bboxes], dtype=np.float32)
                    class_id = np.array([0] * len(person_bboxes), dtype=np.int32)
                    detections = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
                    tracked = self._person_tracker.update_with_detections(detections)
                    
                    for idx in range(len(tracked)):
                        track_id = int(tracked.tracker_id[idx])
                        box = tracked.xyxy[idx].tolist()
                        bbox_obj = BBox(box[0], box[1], box[2], box[3])
                        tracked_detections.append(TrackedDetection(
                            track_id=track_id,
                            bbox=bbox_obj,
                            frame_idx=frame_idx,
                            is_new=False
                        ))
            else:
                bboxes = [BBox(b[0], b[1], b[2], b[3]) for b in person_bboxes]
                tracked_detections = self._person_tracker.update(bboxes, frame_idx)

            # 3. Face Detection inside head region of person crops
            frame_faces: List[float] = []
            frame_track_detections: List[TrackedDetection] = []
            for det in tracked_detections:
                p_x1, p_y1, p_x2, p_y2 = det.bbox.x1, det.bbox.y1, det.bbox.x2, det.bbox.y2
                p_h = p_y2 - p_y1
                p_w = p_x2 - p_x1

                head_x1 = max(0, int(p_x1))
                head_y1 = max(0, int(p_y1))
                head_x2 = min(w_frame, int(p_x2))
                head_y2 = min(h_frame, int(p_y1 + head_ratio * p_h))

                analytics_crops_processed += 1

                crop = frame_rgb[head_y1:head_y2, head_x1:head_x2]
                if crop.size == 0:
                    frame_track_detections.append(det)
                    continue

                face_found = None
                
                if self._crop_face_detector_type == "retinaface":
                    faces = self._crop_face_detector.predict_jsons(crop)
                    if faces:
                        best_face = max(faces, key=lambda f: f.get('score', 0.0) if f.get('score') is not None else 1.0)
                        if best_face.get('bbox') and len(best_face['bbox']) == 4:
                            f_box = best_face['bbox']
                            face_found = BBox(
                                f_box[0] + head_x1,
                                f_box[1] + head_y1,
                                f_box[2] + head_x1,
                                f_box[3] + head_y1
                            )
                elif self._crop_face_detector_type == "scrfd":
                    from scrfd import Threshold
                    faces = self._crop_face_detector.detect(crop, threshold=Threshold(probability=face_conf_thresh))
                    if faces:
                        best_face = max(faces, key=lambda f: f.probability)
                        f_box = best_face.bbox
                        face_found = BBox(
                            f_box[0] + head_x1,
                            f_box[1] + head_y1,
                            f_box[2] + head_x1,
                            f_box[3] + head_y1
                        )
                elif self._crop_face_detector_type == "mediapipe":
                    if self._use_legacy_api:
                        results = self._face_detector.process(crop)
                        if results.detections:
                            best_det = max(results.detections, key=lambda d: d.score[0] if d.score else 0.0)
                            bbox = best_det.location_data.relative_bounding_box
                            crop_h, crop_w = crop.shape[:2]
                            fx1 = bbox.xmin * crop_w + head_x1
                            fy1 = bbox.ymin * crop_h + head_y1
                            fx2 = (bbox.xmin + bbox.width) * crop_w + head_x1
                            fy2 = (bbox.ymin + bbox.height) * crop_h + head_y1
                            face_found = BBox(fx1, fy1, fx2, fy2)
                    else:
                        import mediapipe as mp
                        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop)
                        result = self._face_detector.detect(mp_image)
                        if result.detections:
                            best_det = max(result.detections, key=lambda d: d.categories[0].score if d.categories else 0.0)
                            bbox = best_det.bounding_box
                            fx1 = bbox.origin_x + head_x1
                            fy1 = bbox.origin_y + head_y1
                            fx2 = bbox.origin_x + bbox.width + head_x1
                            fy2 = bbox.origin_y + bbox.height + head_y1
                            face_found = BBox(fx1, fy1, fx2, fy2)

                if face_found:
                    analytics_faces_found += 1
                    det.face_bbox = face_found
                    frame_faces.append(face_found.center_x)
                else:
                    fallback_face_x = det.bbox.center_x
                    fallback_face_y = p_y1 + 0.15 * p_h
                    fallback_face_w = 0.20 * p_w
                    fallback_face_h = 0.20 * p_h
                    det.face_bbox = BBox(
                        fallback_face_x - fallback_face_w/2,
                        fallback_face_y - fallback_face_h/2,
                        fallback_face_x + fallback_face_w/2,
                        fallback_face_y + fallback_face_h/2
                    )
                    frame_faces.append(det.face_bbox.center_x)

            per_frame_faces.append(frame_faces)
            per_frame_tracked.append(tracked_detections)
            frame_face_counts.append(len(frame_faces))
            sample_frame_indices.append(frame_idx)
            sample_timestamps.append(frame_idx / fps)

        cap.release()

        # Collect analytics
        for frame_detections in per_frame_tracked:
            for det in frame_detections:
                analytics_id_switch_sets.add(det.track_id)
        
        logger.info(f"podcast_reframe: [ANALYTICS] Face recall on crop: {analytics_faces_found}/{max(1, analytics_crops_processed)} ({(analytics_faces_found / max(1, analytics_crops_processed))*100:.1f}%)")
        logger.info(f"podcast_reframe: [ANALYTICS] Unique person track IDs: {len(analytics_id_switch_sets)}")

        position_model = self._build_position_model_person_first(per_frame_tracked, width, height)
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
            "podcast_reframe (person-first): scan completed. "
            f"samples={len(frame_face_counts)}, "
            f"coverage=0.0-{(sample_timestamps[-1] if sample_timestamps else 0.0):.1f}s, "
            f"frames_with_faces={frames_with_faces}/{len(frame_face_counts)}, "
            f"faces_per_frame=min/median/max="
            f"{(min(frame_face_counts) if frame_face_counts else 0)}/"
            f"{median_faces_in_frame:.1f}/{max_faces_in_frame}"
        )

        tracks_str = ", ".join(
            f"T{tid}:({int(p['x'])},{int(p['y'])},{int(p['width'])}x{int(p['height'])})"
            for tid, p in stable_position_profiles.items()
        )
        positions_str = ", ".join(
            f"P{pid}:({int(position_target_profiles[pid]['x'])},{int(position_target_profiles[pid]['y'])},{int(position_target_profiles[pid]['width'])}x{int(position_target_profiles[pid]['height'])})"
            for pid in position_target_profiles
        )
        logger.info(
            f"podcast_reframe: tracked {len(stable_position_profiles)} unique tracks, "
            f"person_count={person_count}, "
            f"tracks={{{tracks_str}}}, "
            f"positions={{{positions_str}}}"
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

    def _build_position_model_person_first(
        self,
        per_frame_tracked: List[List[TrackedDetection]],
        width: int,
        height: int,
    ) -> dict:
        """Build stable person positions using BODY bbox for grid geometry separation."""
        track_profiles: Dict[int, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for frame_tracked in per_frame_tracked:
            for detection in frame_tracked:
                # Use BODY bbox for position model (determines grid crop separation).
                # Face bbox is too centered (both speakers face toward middle),
                # body bbox reflects actual left/right position in frame.
                body_box = detection.bbox
                profile = track_profiles[detection.track_id]
                profile["x"].append(body_box.center_x)
                profile["y"].append(body_box.center_y)
                profile["width"].append(body_box.width)
                profile["height"].append(body_box.height)
                profile["area"].append(body_box.area)
                # Capture the real face bbox (person-first detector provides it)
                # so grid-Y framing centers the actual face, not a body estimate.
                if detection.face_bbox is not None:
                    profile["face_x"].append(detection.face_bbox.center_x)
                    profile["face_y"].append(detection.face_bbox.center_y)
                    profile["face_width"].append(detection.face_bbox.width)
                    profile["face_height"].append(detection.face_bbox.height)

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

        # Ghost elimination for person-first mode:
        # 1) Drop tiny noise tracks by size.
        # 2) Collapse nested tight/loose body boxes and same-face track fragments.
        # Do NOT use broad proximity merges that would fuse face-to-face speakers.
        if len(stable_position_profiles) >= 2:
            max_area = max(
                p.get("area", p.get("width", 0) * p.get("height", 0))
                for p in stable_position_profiles.values()
            )

            ghost_track_ids: set = set()
            sorted_by_area = sorted(
                stable_position_profiles.items(),
                key=lambda kv: kv[1].get(
                    "area", kv[1].get("width", 0) * kv[1].get("height", 0)
                ),
                reverse=True,
            )

            for track_id, profile in sorted_by_area:
                track_area = profile.get(
                    "area", profile.get("width", 0) * profile.get("height", 0)
                )
                # Size filter only when 3+ tracks (noise fragments).
                if (
                    len(stable_position_profiles) > 2
                    and max_area > 0
                    and track_area / max_area < 0.25
                ):
                    ghost_track_ids.add(track_id)
                    continue

                # Nested / same-face duplicates against a larger surviving track.
                for valid_id, valid_profile in sorted_by_area:
                    if valid_id == track_id or valid_id in ghost_track_ids:
                        continue
                    valid_area = valid_profile.get(
                        "area",
                        valid_profile.get("width", 0) * valid_profile.get("height", 0),
                    )
                    if valid_area < track_area:
                        continue
                    if self._is_ghost_pair(profile, valid_profile, width, height):
                        ghost_track_ids.add(track_id)
                        break

            if ghost_track_ids:
                logger.info(
                    f"podcast_reframe: person-first ghost elimination removed tracks: "
                    f"{ghost_track_ids}"
                )
                stable_position_profiles = {
                    tid: prof
                    for tid, prof in stable_position_profiles.items()
                    if tid not in ghost_track_ids
                }
                stable_positions = {
                    tid: profile["x"]
                    for tid, profile in stable_position_profiles.items()
                }
                filtered = {
                    tid: vals
                    for tid, vals in filtered.items()
                    if tid not in ghost_track_ids
                }

        # Person-first mode: surviving track IDs map 1:1 to seats. Nested
        # duplicates are already collapsed above so we do not re-cluster seats
        # (which can merge two face-to-face speakers from a center camera).
        clusters: List[dict] = []
        for track_id, profile in sorted(
            stable_position_profiles.items(),
            key=lambda kv: (kv[1]["x"], kv[1]["y"]),
        ):
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
