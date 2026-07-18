"""PersonFirstReframeEngine — Person-body-first detection pipeline for reframing.

Pipeline:
  1. RF-DETR (Person Detection) → full body bboxes per frame
  2. ByteTrack / BoT-SORT → persistent person track IDs
  3. FaceOnCrop (RetinaFace/SCRFD) → face detection in head region only
  4. Speaker Mapping (Hungarian, keyed by person_track_id)
  5. Auto Grid / Camera Planner → same logic as legacy, better input
  6. FFmpeg Render (single pass, zero desync)

Key difference from PodcastReframeEngine:
  - Anchors on PERSON body, not face — track persists when face is occluded
  - Face detection is secondary: runs only in top 35% of tracked person crop
  - Ghost elimination simplified (BoT-SORT handles identity via ReID)
  - Same render output format — drop-in replacement

This engine implements IReframeEngine with the same process() contract.
"""
import asyncio
import logging
import os
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.config import settings
from src.domain.interfaces import IReframeEngine
from src.infrastructure.gpu_encoder import get_video_encoder_args
from src.infrastructure.active_speaker_detector import (
    ActiveSpeakerDetector,
    ActiveSpeakerResult,
    SpeakerSegment,
)
from src.infrastructure.person_detector import PersonDetector, PersonDetection
from src.infrastructure.person_tracker import BBox, TrackedDetection
from src.infrastructure.person_tracker_v2 import PersonTrackerV2, TrackedPerson
from src.infrastructure.face_on_crop_detector import FaceOnCropDetector, FaceDetectionResult
from src.infrastructure.speaker_diarizer import SpeakerDiarizer, DiarizationResult
from src.infrastructure.speaker_face_mapper import SpeakerFaceMapper, MappingResult
from src.infrastructure.diarization_result_builder import DiarizationResultBuilder
from src.infrastructure.media_timeline import timeline_is_safe

logger = logging.getLogger(__name__)


class PersonFirstReframeEngine(IReframeEngine):
    """Person-body-first reframing with persistent tracking and face-on-crop.

    Same interface as PodcastReframeEngine — implements process() async method
    returning {output_path, person_count, method, ...}.
    """

    SAMPLE_INTERVAL_SEC = 0.333
    MAX_SAMPLES = 720
    MIN_SEPARATION_RATIO = 0.05  # [FIX] Turunkan dari 0.20 → face-to-face podcast support
    MIN_COEXIST_RATIO = 0.40
    DOMINANCE_SINGLE_CROP = 0.75
    GRID_PANEL_HEIGHT = 960
    GRID_BASE_ZOOM = 1.08
    GRID_MAX_ZOOM = 2.20  # Head+shoulders framing for face-to-face podcast grid
    GRID_FACE_MARGIN = 0.35
    GRID_ENTER_SAMPLES = 4
    GRID_EXIT_SAMPLES = 2
    MIN_GRID_SEGMENT_SECONDS = 1.20

    PAN_DEAD_ZONE_PX = 150
    PAN_HOLD_MIN_SEC = 2.0
    PAN_CLUSTER_THRESHOLD = 200
    PAN_MAX_KEYFRAMES = 25

    AUDIO_FILTER = "aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS"
    VALID_TRANSITIONS = {"cut", "fade", "slide", "zoom"}

    def __init__(self, hf_token: Optional[str] = None):
        # Person detection (RF-DETR)
        self._person_detector = PersonDetector(
            model_variant=settings.PERSON_DETECTOR,
            confidence_threshold=settings.PERSON_CONF_THRESHOLD,
        )

        # Person tracking (BoT-SORT / ByteTrack)
        self._person_tracker: Optional[PersonTrackerV2] = None

        # Face-on-crop detection
        self._face_detector = FaceOnCropDetector(
            backend=settings.FACE_DETECTOR,
            head_ratio=settings.FACE_REGION_HEAD_RATIO,
            confidence_threshold=settings.FACE_CONFIDENCE,
        )

        # Active speaker detector (lip + head motion — unchanged)
        self._speaker_detector = ActiveSpeakerDetector()

        # Diarization (unchanged from legacy)
        self._hf_token = hf_token
        self._diarizer: Optional[SpeakerDiarizer] = None
        self._face_mapper: Optional[SpeakerFaceMapper] = None
        self._result_builder = DiarizationResultBuilder()

    # ─── Public API (IReframeEngine) ──────────────────────────────────────

    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
        autogrid_enabled: bool = False,
        **kwargs,
    ) -> dict:
        """Reframe video using person-first pipeline.

        Same contract as PodcastReframeEngine.process().
        """
        if not os.path.exists(video_path):
            return {"output_path": video_path, "person_count": 0, "method": "error"}

        if target_aspect != "9:16":
            success = await self._simple_crop(video_path, output_path, target_aspect)
            return {
                "output_path": output_path if success else video_path,
                "person_count": 0,
                "method": "simple_crop",
            }

        # Parse transition settings
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
                transition_style,
                transition_duration,
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"person_first_reframe: pipeline error: {e}")

        # Fallback: center crop
        success = await self._center_crop(video_path, output_path)
        return {
            "output_path": output_path if success else video_path,
            "person_count": 0,
            "method": "center_crop_fallback",
        }

    # ─── Main Pipeline ────────────────────────────────────────────────────

    def _pipeline(
        self,
        video_path: str,
        output_path: str,
        autogrid: bool,
        transition_style: str,
        transition_duration: float,
    ) -> Optional[dict]:
        """Person-first pipeline: detect persons → track → face-on-crop → speaker → render."""
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

        # Initialize tracker
        self._person_tracker = PersonTrackerV2(
            tracker_type=settings.PERSON_TRACKER,
            model_path=settings.YOLO_MODEL_PATH,
            max_lost_frames=settings.TRACKER_MAX_LOST_FRAMES,
            frame_width=width,
            frame_height=height,
        )

        # Step 1+2+3: Detect persons, track, and find faces
        tracked_data = self._detect_track_and_face(
            video_path, width, height, fps, total_frames
        )

        if not tracked_data["per_frame_tracked"]:
            logger.info("person_first_reframe: no persons detected → center crop")
            return None

        person_count = tracked_data["person_count"]

        # Step 4: Active Speaker Detection
        speaker_result: Optional[ActiveSpeakerResult] = None
        if person_count > 1:
            speaker_result = self._try_diarization(
                video_path, tracked_data, fps, total_frames
            )
            if speaker_result is None:
                speaker_result = self._try_lip_head_detection(
                    video_path, tracked_data, fps, total_frames, width, height
                )
            if speaker_result is None:
                speaker_result = self._build_visual_fallback(
                    tracked_data, fps, total_frames
                )
        elif person_count == 1:
            speaker_result = self._build_single_speaker_result(
                tracked_data, fps, total_frames
            )

        self._log_speaker_summary(speaker_result, tracked_data, fps, total_frames)

        # Step 5: Auto Grid (same logic as legacy, better input)
        if autogrid and person_count >= 2:
            grid_result = self._try_auto_grid(
                video_path, output_path, width, height, fps, total_frames,
                tracked_data, speaker_result, transition_style, transition_duration,
            )
            if grid_result:
                return grid_result

        # Step 6: Dynamic Panning
        panning_result = self._render_dynamic_panning(
            video_path, output_path, width, height, fps,
            tracked_data, speaker_result, transition_style, transition_duration,
        )
        if panning_result:
            return panning_result

        # Step 7: Static single crop fallback
        return self._render_single_crop(
            video_path, output_path, width, height,
            tracked_data, speaker_result,
        )

    # ─── Step 1+2+3: Detect + Track + Face ────────────────────────────────

    def _detect_track_and_face(
        self,
        video_path: str,
        width: int,
        height: int,
        fps: float,
        total_frames: int,
    ) -> dict:
        """Unified detection: persons → tracking → face-on-crop per frame.

        Returns data structure compatible with legacy pipeline downstream.
        """
        import cv2
        cv2.setNumThreads(0)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return self._empty_tracked_data()

        sample_indices = self._sample_frame_indices(total_frames, fps)

        per_frame_faces: List[List[float]] = []
        per_frame_tracked: List[List[TrackedDetection]] = []
        per_frame_persons: List[List[TrackedPerson]] = []
        frame_face_counts: List[int] = []
        sample_frame_indices: List[int] = []
        sample_timestamps: List[float] = []

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            # Step 1: Detect persons (RF-DETR)
            person_detections = self._person_detector.detect(frame)

            # Step 2: Track persons (BoT-SORT)
            tracked_persons = self._person_tracker.update(
                frame, frame_idx, detections=person_detections
            )

            # Step 3: Face-on-crop for each tracked person
            person_bboxes = {
                tp.track_id: tp.bbox for tp in tracked_persons
            }
            face_results = self._face_detector.detect_faces_for_persons(
                frame, person_bboxes
            )

            # Build compatibility layer: face X positions + TrackedDetection
            frame_face_x: List[float] = []
            frame_tracked_compat: List[TrackedDetection] = []

            for face in face_results:
                frame_face_x.append(face.center_x)
                # Map face detection to TrackedDetection for legacy compatibility
                frame_tracked_compat.append(TrackedDetection(
                    track_id=face.person_track_id,
                    bbox=face.bbox,
                    frame_idx=frame_idx,
                    is_new=False,
                ))

            # Also include persons without face detection (body-only anchor)
            detected_face_track_ids = {f.person_track_id for f in face_results}
            for tp in tracked_persons:
                if tp.track_id not in detected_face_track_ids:
                    # Use person center as face position proxy
                    frame_face_x.append(tp.bbox.center_x)
                    frame_tracked_compat.append(TrackedDetection(
                        track_id=tp.track_id,
                        bbox=tp.bbox,
                        frame_idx=frame_idx,
                        is_new=tp.is_new,
                    ))

            per_frame_faces.append(frame_face_x)
            per_frame_tracked.append(frame_tracked_compat)
            per_frame_persons.append(tracked_persons)
            frame_face_counts.append(len(tracked_persons))
            sample_frame_indices.append(frame_idx)
            sample_timestamps.append(frame_idx / fps)

        cap.release()

        # Build position model from tracker
        position_model = self._person_tracker.build_position_model()

        person_count = position_model["person_count"]
        logger.info(
            f"person_first_reframe: detection complete — "
            f"samples={len(sample_frame_indices)}, "
            f"persons_detected={person_count}, "
            f"face_backend={self._face_detector.active_backend}"
        )

        return {
            "per_frame_faces": per_frame_faces,
            "per_frame_tracked": per_frame_tracked,
            "per_frame_persons": per_frame_persons,
            "frame_face_counts": frame_face_counts,
            "sample_frame_indices": sample_frame_indices,
            "sample_timestamps": sample_timestamps,
            "person_count": person_count,
            "stable_positions": position_model["stable_positions"],
            "stable_position_profiles": position_model["stable_position_profiles"],
            "position_targets": position_model["position_targets"],
            "position_target_profiles": position_model["position_target_profiles"],
            "track_to_position": position_model["track_to_position"],
        }

    # ─── Speaker Detection ────────────────────────────────────────────────

    def _try_diarization(
        self,
        video_path: str,
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> Optional[ActiveSpeakerResult]:
        """Try PyAnnote diarization + face mapping (same as legacy)."""
        diarizer = self._init_diarizer()
        if diarizer is None or not diarizer.is_available:
            return None

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                visual_person_count = int(tracked_data.get("person_count") or 0)
                dynamic_max_speakers = (
                    visual_person_count if visual_person_count > 1 else None
                )
                diarization_result = loop.run_until_complete(
                    diarizer.diarize(
                        video_path,
                        min_speakers=None,
                        max_speakers=dynamic_max_speakers,
                    )
                )
            finally:
                loop.close()

            if diarization_result is None:
                return None

            logger.info(
                f"person_first_reframe: diarization OK — "
                f"{diarization_result.speaker_count} speakers"
            )

            # Map speakers to person tracks
            sample_timestamps = tracked_data.get("sample_timestamps") or []
            mapping_result = self._face_mapper.build_mapping(
                diarization_segments=diarization_result.segments,
                per_frame_tracked=tracked_data["per_frame_tracked"],
                sample_timestamps=sample_timestamps,
                stable_positions=tracked_data["stable_positions"],
            )

            if not mapping_result.is_reliable:
                logger.info(
                    f"person_first_reframe: mapping unreliable "
                    f"(conf={mapping_result.overall_confidence:.2f}) → fallback"
                )
                return None

            speaker_result = self._result_builder.build(
                diarization=diarization_result,
                mapping=mapping_result,
                fps=fps,
                total_frames=total_frames,
                stable_positions=tracked_data["stable_positions"],
                sample_interval_sec=self.SAMPLE_INTERVAL_SEC,
                track_to_position=tracked_data.get("track_to_position"),
            )

            logger.info("person_first_reframe: ✓ using DIARIZATION speaker detection")
            return speaker_result

        except Exception as e:
            logger.warning(f"person_first_reframe: diarization failed: {e}")
            return None

    def _try_lip_head_detection(
        self,
        video_path: str,
        tracked_data: dict,
        fps: float,
        total_frames: int,
        width: int,
        height: int,
    ) -> Optional[ActiveSpeakerResult]:
        """Fallback: lip + head motion analysis via Face Mesh."""
        try:
            vad_segments = self._get_vad_segments(video_path)
            return self._speaker_detector.detect(
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
            logger.warning(f"person_first_reframe: lip+head fallback failed: {e}")
            return None

    def _build_single_speaker_result(
        self,
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> ActiveSpeakerResult:
        """Single person visible — always the active speaker."""
        duration = total_frames / fps if fps > 0 else 0.0
        sample_frame_indices = tracked_data.get("sample_frame_indices") or [0]
        per_frame_speaker = {int(fi): 0 for fi in sample_frame_indices}
        return ActiveSpeakerResult(
            segments=[SpeakerSegment(
                speaker_id=0, start_time=0.0, end_time=duration, confidence=1.0,
            )],
            dominant_speaker_id=0,
            dominant_ratio=1.0,
            per_frame_speaker=per_frame_speaker,
            total_speakers=1,
        )

    def _build_visual_fallback(
        self,
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> Optional[ActiveSpeakerResult]:
        """Fallback: pick most-visible person as speaker target."""
        track_to_position = {
            int(k): int(v)
            for k, v in (tracked_data.get("track_to_position") or {}).items()
        }
        per_frame_tracked = tracked_data.get("per_frame_tracked") or []
        sample_frame_indices = tracked_data.get("sample_frame_indices") or []

        if not track_to_position or not per_frame_tracked:
            return None

        position_hits: Dict[int, int] = defaultdict(int)
        for frame_tracked in per_frame_tracked:
            for det in frame_tracked:
                pos_id = track_to_position.get(int(det.track_id))
                if pos_id is not None:
                    position_hits[pos_id] += 1

        if not position_hits:
            return None

        fallback_position = max(position_hits, key=position_hits.get)
        duration = total_frames / fps if fps > 0 else 0.0
        per_frame_speaker = {int(fi): fallback_position for fi in sample_frame_indices}

        return ActiveSpeakerResult(
            segments=[SpeakerSegment(
                speaker_id=fallback_position,
                start_time=0.0,
                end_time=duration,
                confidence=0.25,
            )],
            dominant_speaker_id=fallback_position,
            dominant_ratio=1.0,
            per_frame_speaker=per_frame_speaker,
            total_speakers=1,
        )

    # ─── Auto Grid ────────────────────────────────────────────────────────

    def _try_auto_grid(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        total_frames: int,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        transition_style: str,
        transition_duration: float,
    ) -> Optional[dict]:
        """Attempt auto grid layout for 2+ persons.

        Uses same geometry calculation as legacy but with more stable input.
        Delegates to PodcastReframeEngine._decide_autogrid_layout logic.
        """
        position_targets = {
            int(k): float(v)
            for k, v in (tracked_data.get("position_targets") or {}).items()
        }
        if len(position_targets) < 2:
            return None

        # Check separation
        positions_sorted = sorted(position_targets.values())
        max_separation = positions_sorted[-1] - positions_sorted[0]
        if max_separation < width * self.MIN_SEPARATION_RATIO:
            logger.info("person_first_reframe: persons too close for grid")
            return None

        # Check co-visibility
        per_frame_tracked = tracked_data.get("per_frame_tracked") or []
        track_to_position = {
            int(k): int(v)
            for k, v in (tracked_data.get("track_to_position") or {}).items()
        }
        covisible_frames = 0
        valid_frames = 0
        for frame_tracked in per_frame_tracked:
            visible_positions = {
                track_to_position.get(int(det.track_id))
                for det in frame_tracked
                if int(det.track_id) in track_to_position
            }
            visible_positions.discard(None)
            if visible_positions:
                valid_frames += 1
                if len(visible_positions) >= 2:
                    covisible_frames += 1

        coexist_ratio = covisible_frames / max(valid_frames, 1)
        if coexist_ratio < self.MIN_COEXIST_RATIO:
            logger.info(
                f"person_first_reframe: coexist_ratio={coexist_ratio:.0%} < "
                f"{self.MIN_COEXIST_RATIO:.0%}, skipping grid"
            )
            return None

        # Dominance check: if one speaker dominates, single crop is better
        if speaker_result and speaker_result.dominant_ratio >= self.DOMINANCE_SINGLE_CROP:
            logger.info(
                f"person_first_reframe: dominant speaker "
                f"({speaker_result.dominant_ratio:.0%}) → single crop preferred"
            )
            return None

        # Pick top 2 most-visible positions for grid
        position_ids = sorted(position_targets.keys())
        if len(position_ids) < 2:
            return None

        # Use speaker info to decide top/bottom
        top_id, bottom_id = position_ids[0], position_ids[1]
        if speaker_result and speaker_result.dominant_speaker_id is not None:
            if speaker_result.dominant_speaker_id == bottom_id:
                top_id, bottom_id = bottom_id, top_id

        top_x = int(position_targets[top_id])
        bottom_x = int(position_targets[bottom_id])

        # Grid geometry
        crop_w = min(width, int(height * 9 / 8 / self.GRID_BASE_ZOOM))
        crop_h = min(height, int(crop_w * 8 / 9))
        top_crop_x = max(0, min(top_x - crop_w // 2, width - crop_w))
        bottom_crop_x = max(0, min(bottom_x - crop_w // 2, width - crop_w))

        # Render double grid
        return self._render_double_grid(
            video_path, output_path, width, height,
            crop_w, crop_h, top_crop_x, bottom_crop_x,
            tracked_data.get("person_count", 2),
            top_id, bottom_id,
        )

    def _render_double_grid(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        crop_w: int,
        crop_h: int,
        top_crop_x: int,
        bottom_crop_x: int,
        person_count: int,
        top_track_id: int,
        bottom_track_id: int,
    ) -> Optional[dict]:
        """Render 50/50 grid (top/bottom panels)."""
        top_y = max(0, (height - crop_h) // 2)
        bottom_y = top_y

        vf = (
            f"setpts=PTS-STARTPTS,split=2[top][bot];"
            f"[top]crop={crop_w}:{crop_h}:{top_crop_x}:{top_y},"
            f"scale=1080:{self.GRID_PANEL_HEIGHT},format=yuv420p[t];"
            f"[bot]crop={crop_w}:{crop_h}:{bottom_crop_x}:{bottom_y},"
            f"scale=1080:{self.GRID_PANEL_HEIGHT},format=yuv420p[b];"
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
            logger.info(
                f"person_first_reframe: 50/50 grid OK "
                f"(top=P{top_track_id}, bottom=P{bottom_track_id})"
            )
            return {
                "output_path": output_path,
                "person_count": person_count,
                "method": "person_first_double_grid",
                "layout": "double",
                "grid_panel_height": self.GRID_PANEL_HEIGHT,
                "top_track_id": top_track_id,
                "bottom_track_id": bottom_track_id,
                "layout_events": [{"time": 0.0, "layout": "double"}],
                "framing_events": [],
            }

        if result.stderr:
            logger.warning(f"person_first_reframe: grid render failed: {result.stderr[-300:]}")
        return None

    # ─── Dynamic Panning ──────────────────────────────────────────────────

    def _render_dynamic_panning(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
        transition_style: str,
        transition_duration: float,
    ) -> Optional[dict]:
        """Dynamic panning: smooth crop follows active speaker."""
        per_frame_faces = tracked_data["per_frame_faces"]
        if not per_frame_faces or len(per_frame_faces) < 3:
            return None

        crop_w = min(int(height * 9 / 16), width)
        max_crop_x = width - crop_w

        position_targets = {
            int(k): float(v)
            for k, v in (tracked_data.get("position_targets") or {}).items()
        }
        track_to_position = {
            int(k): int(v)
            for k, v in (tracked_data.get("track_to_position") or {}).items()
        }
        sample_timestamps = tracked_data.get("sample_timestamps") or []
        sample_frame_indices = tracked_data.get("sample_frame_indices") or []
        per_frame_tracked = tracked_data.get("per_frame_tracked") or []

        # Build keyframes: (time, crop_x, speaker_id)
        keyframes: List[Tuple[float, int, Optional[int]]] = []

        for i, frame_faces in enumerate(per_frame_faces):
            t = sample_timestamps[i] if i < len(sample_timestamps) else i * self.SAMPLE_INTERVAL_SEC
            frame_idx = (
                sample_frame_indices[i]
                if i < len(sample_frame_indices)
                else int(t * fps)
            )

            # Determine target X from speaker
            target_x: Optional[float] = None
            active_speaker: Optional[int] = None

            if speaker_result and speaker_result.per_frame_speaker:
                closest_frame = min(
                    speaker_result.per_frame_speaker.keys(),
                    key=lambda f: abs(f - frame_idx),
                    default=None,
                )
                if closest_frame is not None:
                    active_speaker = speaker_result.per_frame_speaker[closest_frame]
                    target_x = position_targets.get(active_speaker)

            if target_x is None and frame_faces:
                target_x = float(np.median(frame_faces))

            if target_x is None:
                if keyframes:
                    keyframes.append((t, keyframes[-1][1], keyframes[-1][2]))
                continue

            crop_x = max(0, min(int(target_x) - crop_w // 2, max_crop_x))
            keyframes.append((t, crop_x, active_speaker))

        if not keyframes:
            return None

        # Stabilize (cluster lock + dead zone + hold minimum)
        stabilized = self._stabilize_keyframes(keyframes)

        # Build FFmpeg expression
        if len(stabilized) <= 1 or all(s[1] == stabilized[0][1] for s in stabilized):
            crop_x_expr = str(stabilized[0][1])
        else:
            crop_x_expr = self._build_panning_expression(
                [(t, x) for t, x, _ in stabilized],
                transition_duration,
                transition_style,
            )

        # Render
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
            f"person_first_reframe: DYNAMIC PANNING "
            f"({len(stabilized)} keyframes, crop_w={crop_w})"
        )

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
            and timeline_is_safe(output_path)
        ):
            logger.info("person_first_reframe: dynamic panning OK")
            return {
                "output_path": output_path,
                "person_count": tracked_data["person_count"],
                "method": "person_first_dynamic_panning",
                "keyframes": len(stabilized),
                "layout": "single",
                "layout_events": [{"time": 0.0, "layout": "single"}],
                "framing_events": self._speaker_change_events(stabilized),
                "transition_style": transition_style,
                "transition_duration": transition_duration,
            }

        if result.stderr:
            logger.warning(f"person_first_reframe: panning failed: {result.stderr[-300:]}")
        return None

    # ─── Static Single Crop ───────────────────────────────────────────────

    def _render_single_crop(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        tracked_data: dict,
        speaker_result: Optional[ActiveSpeakerResult],
    ) -> Optional[dict]:
        """Static single crop on dominant speaker or visual center."""
        position_targets = {
            int(k): float(v)
            for k, v in (tracked_data.get("position_targets") or {}).items()
        }

        # Determine crop center
        crop_center_x = width // 2
        if speaker_result and speaker_result.dominant_speaker_id is not None:
            target_x = position_targets.get(speaker_result.dominant_speaker_id)
            if target_x is not None:
                crop_center_x = int(target_x)
        elif position_targets:
            crop_center_x = int(np.median(list(position_targets.values())))

        crop_w = min(int(height * 9 / 16), width)
        crop_x = max(0, min(crop_center_x - crop_w // 2, width - crop_w))

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
            logger.info(f"person_first_reframe: single crop OK (x={crop_x})")
            return {
                "output_path": output_path,
                "person_count": tracked_data["person_count"],
                "method": "person_first_single_crop",
            }

        return None

    # ─── Utilities ────────────────────────────────────────────────────────

    def _stabilize_keyframes(
        self,
        keyframes: List[Tuple[float, int, Optional[int]]],
    ) -> List[Tuple[float, int, Optional[int]]]:
        """Stabilize raw keyframes with cluster lock + dead zone + hold min."""
        if not keyframes:
            return []

        all_x = [x for _, x, _ in keyframes]
        x_spread = max(all_x) - min(all_x) if all_x else 0

        # Cluster lock
        if x_spread < self.PAN_CLUSTER_THRESHOLD:
            home_x = int(np.median(all_x))
            return [(0.0, home_x, keyframes[0][2])]

        # Dead zone + hold minimum
        stabilized: List[Tuple[float, int, Optional[int]]] = [keyframes[0]]
        for t, x, speaker_id in keyframes[1:]:
            last_t, last_x, last_speaker = stabilized[-1]
            movement = abs(x - last_x)
            time_since = t - last_t
            speaker_changed = (
                speaker_id is not None
                and last_speaker is not None
                and speaker_id != last_speaker
            )
            if movement >= self.PAN_DEAD_ZONE_PX and (
                time_since >= self.PAN_HOLD_MIN_SEC or speaker_changed
            ):
                stabilized.append((t, x, speaker_id))

        # Ensure last captured
        if stabilized[-1][0] < keyframes[-1][0]:
            stabilized.append(keyframes[-1])

        # Limit keyframes
        if len(stabilized) > self.PAN_MAX_KEYFRAMES:
            step = len(stabilized) // (self.PAN_MAX_KEYFRAMES - 2)
            reduced = [stabilized[0]]
            for i in range(step, len(stabilized) - 1, step):
                reduced.append(stabilized[i])
            reduced.append(stabilized[-1])
            stabilized = reduced

        return stabilized

    def _build_panning_expression(
        self,
        keyframes: List[Tuple[float, int]],
        transition_sec: float,
        transition_style: str,
    ) -> str:
        """Build FFmpeg time-based crop X expression with smooth lerp."""
        if len(keyframes) <= 1:
            return str(keyframes[0][1] if keyframes else 0)

        trans = transition_sec if transition_sec > 0 else settings.CENTERING_TRANSITION_SEC
        if transition_style == "cut":
            trans = 0.0
        trans = max(0.0, min(1.0, float(trans)))

        if trans <= 0:
            # Instant snap
            expr = str(keyframes[-1][1])
            for i in range(len(keyframes) - 2, -1, -1):
                _, x_current = keyframes[i]
                t_next, _ = keyframes[i + 1]
                expr = f"if(lt(t\\,{t_next:.2f})\\,{x_current}\\,{expr})"
            return f"'{expr}'"

        # Smooth lerp
        expr = str(keyframes[-1][1])
        for i in range(len(keyframes) - 2, -1, -1):
            _, x_current = keyframes[i]
            t_next, x_next = keyframes[i + 1]
            t_trans_start = t_next - trans

            if t_trans_start <= (keyframes[i][0] if i > 0 else 0):
                expr = f"if(lt(t\\,{t_next:.2f})\\,{x_current}\\,{expr})"
            else:
                delta = x_next - x_current
                lerp_expr = f"{x_current}+{delta}*min(1\\,(t-{t_trans_start:.2f})/{trans:.2f})"
                inner = (
                    f"if(lt(t\\,{t_trans_start:.2f})\\,{x_current}\\,"
                    f"if(lt(t\\,{t_next:.2f})\\,{lerp_expr}\\,{expr}))"
                )
                expr = inner

        return f"'{expr}'"

    @staticmethod
    def _speaker_change_events(
        keyframes: List[Tuple[float, int, Optional[int]]],
    ) -> List[dict]:
        """Extract speaker change events from stabilized keyframes."""
        events: List[dict] = []
        prev_speaker: Optional[int] = None
        for t, _, speaker_id in keyframes:
            if speaker_id is None:
                continue
            if prev_speaker is None:
                prev_speaker = speaker_id
                continue
            if speaker_id != prev_speaker:
                events.append({
                    "time": max(0.0, float(t)),
                    "kind": "speaker",
                    "from": prev_speaker,
                    "to": speaker_id,
                })
                prev_speaker = speaker_id
        return events

    def _sample_frame_indices(self, total_frames: int, fps: float) -> List[int]:
        """Sample frames across the full clip."""
        if total_frames <= 0:
            return []
        sample_interval = max(1, int(round(float(fps) * self.SAMPLE_INTERVAL_SEC)))
        natural_indices = list(range(0, total_frames, sample_interval))
        if len(natural_indices) <= self.MAX_SAMPLES:
            return natural_indices
        distributed = np.linspace(0, max(0, total_frames - 1), num=self.MAX_SAMPLES, dtype=int)
        return list(dict.fromkeys(distributed.tolist()))

    def _init_diarizer(self) -> Optional[SpeakerDiarizer]:
        """Lazy-init diarizer."""
        if self._diarizer is not None:
            return self._diarizer

        if not settings.DIARIZATION_ENABLED:
            return None

        hf_token = self._hf_token or settings.HF_TOKEN
        if not hf_token:
            return None

        self._diarizer = SpeakerDiarizer(
            hf_token=hf_token,
            model_name=settings.DIARIZATION_MODEL,
            timeout_sec=settings.DIARIZATION_TIMEOUT_SEC,
        )
        self._face_mapper = SpeakerFaceMapper(
            confidence_threshold=settings.DIARIZATION_MAPPING_CONFIDENCE_THRESHOLD,
        )
        return self._diarizer

    def _get_vad_segments(self, video_path: str) -> Optional[List[Dict]]:
        """Get VAD segments for speaker detection gating."""
        try:
            from src.infrastructure.silero_vad import SileroVADProcessor
            vad = SileroVADProcessor()
            segments = vad.get_speech_timestamps(video_path)
            if segments:
                return segments
        except Exception:
            pass
        return None

    def _log_speaker_summary(
        self,
        speaker_result: Optional[ActiveSpeakerResult],
        tracked_data: dict,
        fps: float,
        total_frames: int,
    ) -> None:
        """Log speaker detection summary."""
        if speaker_result is None:
            logger.info("person_first_reframe: no speaker detection available")
            return
        duration = total_frames / fps if fps > 0 else 0.0
        logger.info(
            f"person_first_reframe: speakers={speaker_result.total_speakers}, "
            f"dominant=P{speaker_result.dominant_speaker_id} "
            f"({speaker_result.dominant_ratio:.0%}), "
            f"duration={duration:.1f}s"
        )

    @staticmethod
    def _empty_tracked_data() -> dict:
        """Return empty tracking data structure."""
        return {
            "per_frame_faces": [],
            "per_frame_tracked": [],
            "per_frame_persons": [],
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

    async def _center_crop(self, video_path: str, output_path: str) -> bool:
        """Center crop fallback."""
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", "setpts=PTS-STARTPTS,crop=ih*9/16:ih,scale=1080:1920,format=yuv420p,setsar=1",
            "-af", self.AUDIO_FILTER,
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=120
        )
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
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=120
        )
        return (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 1000
            and timeline_is_safe(output_path)
        )
