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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.domain.interfaces import IReframeEngine
from src.infrastructure.gpu_encoder import get_video_encoder_args
from src.infrastructure.active_speaker_detector import ActiveSpeakerDetector, ActiveSpeakerResult
from src.infrastructure.person_tracker import SimpleIoUTracker, BBox, TrackedDetection

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

    SAMPLE_INTERVAL_SEC = 1.0
    MAX_SAMPLES = 60
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
            try:
                speaker_result = self._speaker_detector.detect(
                    video_path=video_path,
                    fps=fps,
                    total_frames=total_frames,
                    width=width,
                    height=height,
                )
            except Exception as e:
                logger.warning(f"podcast_reframe: speaker detection failed (non-fatal): {e}")

        # Step 3: Dynamic segment-based layout (auto-switch single↔grid per segment)
        if autogrid and person_count >= 2:
            result = self._render_dynamic_segments(
                video_path, output_path, width, height, fps,
                tracked_data, speaker_result,
            )
            if result:
                return result

        # Step 4: Fallback to static layout (whole clip = 1 layout)
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
            }
        """
        import cv2
        cv2.setNumThreads(0)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {"per_frame_faces": [], "per_frame_tracked": [], "person_count": 0, "stable_positions": {}}

        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

        per_frame_faces: List[List[float]] = []
        per_frame_tracked: List[List[TrackedDetection]] = []

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
            tracked = self._tracker.update(frame_bboxes, frame_idx)

            per_frame_faces.append(frame_faces)
            per_frame_tracked.append(tracked)

        cap.release()

        person_count = self._tracker.person_count
        # Also check historical: max unique tracks seen across all time
        all_track_ids = set()
        for frame_tracked in per_frame_tracked:
            for td in frame_tracked:
                all_track_ids.add(td.track_id)
        # Use the max of current active or total unique (capped at active to avoid counting transients)
        person_count = max(person_count, min(len(all_track_ids), 3))

        stable_positions = self._tracker.get_stable_positions()

        logger.info(
            f"podcast_reframe: tracked {len(all_track_ids)} unique faces, "
            f"person_count={person_count}, "
            f"positions={{{', '.join(f'T{k}:{v:.0f}' for k, v in stable_positions.items())}}}"
        )

        return {
            "per_frame_faces": per_frame_faces,
            "per_frame_tracked": per_frame_tracked,
            "person_count": person_count,
            "stable_positions": stable_positions,
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
        person_count = tracked_data["person_count"]

        all_x = [x for frame in per_frame_faces for x in frame]
        if not all_x:
            return {"layout": "single", "crop_x": width // 2, "person_count": 0}

        # ─── Speaker-aware path ───────────────────────────────────────────
        if speaker_result and person_count >= 2 and stable_positions:
            dominant_id = speaker_result.dominant_speaker_id
            dominant_ratio = speaker_result.dominant_ratio

            # Map speaker IDs to stable X positions
            # ActiveSpeakerDetector uses 0=left, 1=right
            # Tracker uses track_ids — map by X position ordering
            sorted_tracks = sorted(stable_positions.items(), key=lambda kv: kv[1])
            # sorted_tracks[0] = leftmost track, sorted_tracks[1] = rightmost track
            # ActiveSpeaker ID 0 = left, ID 1 = right
            track_to_speaker = {}
            for i, (track_id, _) in enumerate(sorted_tracks[:2]):
                track_to_speaker[i] = track_id  # speaker_id i → track_id

            # Case 1: One dominant speaker → single crop on them
            if dominant_ratio >= self.DOMINANCE_SINGLE_CROP:
                # Get the dominant speaker's track position
                dominant_track_id = track_to_speaker.get(dominant_id)
                if dominant_track_id is not None and dominant_track_id in stable_positions:
                    crop_x = int(stable_positions[dominant_track_id])
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
            if autogrid and len(sorted_tracks) >= 2:
                left_track_id, left_x = sorted_tracks[0]
                right_track_id, right_x = sorted_tracks[1]
                separation = right_x - left_x

                if separation >= width * self.MIN_SEPARATION_RATIO:
                    # Determine who is currently the active speaker for emphasis
                    # Use the speaker who spoke most recently (last segment)
                    active_speaker_id = dominant_id if dominant_id is not None else 0
                    active_track_id = track_to_speaker.get(active_speaker_id, left_track_id)

                    # Active speaker X position
                    active_x = stable_positions.get(active_track_id, left_x)
                    # Listener X position
                    listener_track_id = right_track_id if active_track_id == left_track_id else left_track_id
                    listener_x = stable_positions.get(listener_track_id, right_x)

                    logger.info(
                        f"podcast_reframe: SPEAKER EMPHASIS GRID "
                        f"(active=T{active_track_id} x={active_x:.0f}, "
                        f"listener=T{listener_track_id} x={listener_x:.0f}, "
                        f"dominance={dominant_ratio:.0%})"
                    )
                    return {
                        "layout": "speaker_emphasis",
                        "active_x": int(active_x),
                        "listener_x": int(listener_x),
                        "active_track_id": active_track_id,
                        "listener_track_id": listener_track_id,
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

    # ─── Render: Dynamic Segment-Based (Auto-Switch Single↔Grid) ─────────

    SEGMENT_MIN_DURATION = 2.0  # Minimum segment duration (seconds) to prevent rapid flicker

    def _render_dynamic_segments(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
    ) -> Optional[dict]:
        """Render with dynamic per-segment layout switching.

        Automatically switches between single crop (1 person) and double grid (2 people)
        based on how many faces are detected in each time segment.

        Flow:
          1. Classify each sample point as 'single' or 'double' by face count
          2. Build time segments with minimum duration (anti-flicker)
          3. Build FFmpeg filter_complex: trim+crop per segment, then concat
        """
        per_frame_faces = tracked_data["per_frame_faces"]
        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, int(fps * len(per_frame_faces) * self.SAMPLE_INTERVAL_SEC), sample_interval))

        if not per_frame_faces:
            return None

        # 1. Classify each sample as single/double
        midpoint = width / 2.0
        classifications: List[Tuple[float, str, List[float]]] = []  # (time_sec, layout, face_xs)

        for i, frame_faces in enumerate(per_frame_faces):
            t = i * self.SAMPLE_INTERVAL_SEC

            if len(frame_faces) >= 2:
                sorted_x = sorted(frame_faces)
                separation = sorted_x[-1] - sorted_x[0]
                if separation >= width * self.MIN_SEPARATION_RATIO:
                    classifications.append((t, 'double', frame_faces))
                    continue

            classifications.append((t, 'single', frame_faces))

        if not classifications:
            return None

        # 2. Build segments with minimum duration
        segments: List[Tuple[float, float, str]] = []  # (start, end, layout)
        current_layout = classifications[0][1]
        segment_start = 0.0

        for i, (t, layout, _) in enumerate(classifications[1:], 1):
            if layout != current_layout:
                segments.append((segment_start, t, current_layout))
                current_layout = layout
                segment_start = t

        # Close last segment
        total_duration = len(per_frame_faces) * self.SAMPLE_INTERVAL_SEC
        segments.append((segment_start, total_duration + 0.5, current_layout))

        # Merge short segments into neighbors (anti-flicker)
        merged: List[List] = []
        for seg in segments:
            if not merged:
                merged.append(list(seg))
            else:
                seg_dur = seg[1] - seg[0]
                if seg_dur < self.SEGMENT_MIN_DURATION:
                    merged[-1][1] = seg[1]  # Extend previous segment
                elif merged[-1][2] == seg[2]:
                    merged[-1][1] = seg[1]  # Merge same layout
                else:
                    merged.append(list(seg))

        # Ensure last segment covers full duration
        if merged:
            merged[-1][1] = max(merged[-1][1], total_duration)

        # Check if dynamic switching is needed
        layouts_used = set(s[2] for s in merged)
        if len(layouts_used) <= 1:
            # All segments same layout — skip dynamic, use static path
            logger.info(f"podcast_reframe: all {len(merged)} segments are '{merged[0][2]}', using static render")
            return None

        logger.info(
            f"podcast_reframe: DYNAMIC SEGMENTS ({len(merged)} segments: "
            f"{sum(1 for s in merged if s[2]=='single')} single, "
            f"{sum(1 for s in merged if s[2]=='double')} double)"
        )
        for i, (start, end, layout) in enumerate(merged):
            logger.info(f"  seg[{i}] {start:.1f}s → {end:.1f}s ({end-start:.1f}s) = {layout}")

        # 3. Compute crop positions per segment
        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = int(height * 9 / 8)
        crop_h_double = height
        if crop_w_double > width:
            crop_w_double = width
            crop_h_double = int(width * 8 / 9)
        crop_y_double = max(0, (height - crop_h_double) // 2)

        # Get face X positions per time range for crop calculation
        video_filters = []
        audio_filters = []
        v_labels = []
        a_labels = []

        for i, (start_t, end_t, layout) in enumerate(merged):
            if end_t <= start_t:
                continue

            v_out = f"v{i}"
            a_out = f"a{i}"

            # Get face detections for this segment
            seg_start_idx = int(start_t / self.SAMPLE_INTERVAL_SEC)
            seg_end_idx = int(end_t / self.SAMPLE_INTERVAL_SEC)
            seg_faces = per_frame_faces[seg_start_idx:seg_end_idx + 1]
            seg_all_x = [x for frame in seg_faces for x in frame]

            if layout == 'double' and seg_all_x:
                left_cluster = [x for x in seg_all_x if x < midpoint]
                right_cluster = [x for x in seg_all_x if x >= midpoint]

                left_x = int(np.median(left_cluster)) if left_cluster else width // 4
                right_x = int(np.median(right_cluster)) if right_cluster else width * 3 // 4

                lx = self._clamp_x(left_x, crop_w_double, width)
                rx = self._clamp_x(right_x, crop_w_double, width)

                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,split=2[s{i}_a][s{i}_b];"
                    f"[s{i}_a]crop={crop_w_double}:{crop_h_double}:{lx}:{crop_y_double},scale=1080:960,format=yuv420p[s{i}_ta];"
                    f"[s{i}_b]crop={crop_w_double}:{crop_h_double}:{rx}:{crop_y_double},scale=1080:960,format=yuv420p[s{i}_tb];"
                    f"[s{i}_ta][s{i}_tb]vstack=inputs=2,setsar=1,format=yuv420p[{v_out}]"
                )
            else:
                # Single crop — center on dominant face cluster
                if seg_all_x:
                    crop_center = int(np.median(seg_all_x))
                else:
                    crop_center = width // 2
                crop_x = self._clamp_x(crop_center, crop_w_single, width)

                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,"
                    f"crop={crop_w_single}:{height}:{crop_x}:0,scale=1080:1920,setsar=1,format=yuv420p[{v_out}]"
                )

            audio_filters.append(f"[0:a]atrim={start_t}:{end_t},asetpts=PTS-STARTPTS[{a_out}]")
            v_labels.append(f"[{v_out}]")
            a_labels.append(f"[{a_out}]")

        if not v_labels:
            return None

        # 4. Build FFmpeg concat command
        concat_v = "".join(v_labels) + f"concat=n={len(v_labels)}:v=1:a=0[vout]"
        concat_a = "".join(a_labels) + f"concat=n={len(a_labels)}:v=0:a=1[aout]"
        filter_complex = ";".join(video_filters + audio_filters + [concat_v, concat_a])

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-movflags", "+faststart",
            output_path,
        ]

        logger.info(f"podcast_reframe: rendering {len(merged)} dynamic segments...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.info(f"podcast_reframe: dynamic segments OK ({len(merged)} segments)")
            return {
                "output_path": output_path,
                "person_count": tracked_data["person_count"],
                "method": "podcast_dynamic_grid",
                "segments": len(merged),
            }

        # Fallback: try without audio filter (some videos have audio issues)
        if result.stderr:
            logger.warning(f"podcast_reframe: dynamic segments failed (trying no-audio): {result.stderr[-200:]}")

        filter_complex_no_audio = ";".join(video_filters + [concat_v])
        cmd_fallback = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex_no_audio,
            "-map", "[vout]", "-map", "0:a?",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=600)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.info(f"podcast_reframe: dynamic segments OK (no-audio fallback)")
            return {
                "output_path": output_path,
                "person_count": tracked_data["person_count"],
                "method": "podcast_dynamic_grid",
                "segments": len(merged),
            }

        logger.warning(f"podcast_reframe: dynamic segments FAILED, falling back to static")
        return None

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
