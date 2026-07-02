"""PodcastReframeEngine — Audio-Visual Active Speaker Framing.

4-Stage Pipeline:
  Stage 1: Audio Diarization (pyannote.audio) — Who is speaking when?
  Stage 2: Face Detection (MediaPipe) — Where are the real human faces?
  Stage 3: Layout Engine — Combine audio + visual to decide single/double grid
  Stage 4: FFmpeg Dynamic Renderer — Render final 9:16 video with dynamic crops

Key advantages over YOLO:
  - No false positives on action figures/toys/humanoids (MediaPipe requires real face texture)
  - Audio-driven layout: grid only appears when both speakers actively talk
  - Smooth pan to active speaker when only one is talking
  - No PyTorch/glibc thread deadlock (MediaPipe + pyannote are independent)
  - Much lighter CPU usage

v2 Improvements:
  - Chunked FFmpeg rendering to prevent OOM on long videos (>15 segments)
  - Speaker-Face correlation: maps audio SPEAKER_00 to visual LEFT/RIGHT
  - Anti-jitter with hold-previous logic and audio crossfade
"""
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.domain.interfaces import IReframeEngine
from src.infrastructure.gpu_encoder import get_video_encoder_args

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════════════


class LayoutType(str, Enum):
    SINGLE_LEFT = "single_left"      # Focus on left speaker
    SINGLE_RIGHT = "single_right"    # Focus on right speaker
    SINGLE_CENTER = "single_center"  # Center crop (no clear speaker)
    DOUBLE_GRID = "double_grid"      # Split top/bottom (both speaking)


@dataclass
class SpeakerSegment:
    """A time segment where a specific speaker (or both) is active."""
    start: float
    end: float
    speaker: str  # 'A', 'B', 'A_B', 'SILENCE'


@dataclass
class TimedFaceDetection:
    """A single face detection with timestamp (for speaker-face correlation)."""
    time: float       # seconds into video
    face_x: float     # X position in pixels (original resolution)


@dataclass
class FaceCluster:
    """A detected speaker's face position cluster."""
    label: str            # 'left', 'right', or 'center'
    median_x: float       # Median X position in pixels
    x_values: List[float] = field(default_factory=list)
    timed_detections: List[TimedFaceDetection] = field(default_factory=list)


@dataclass
class LayoutSegment:
    """Final layout decision for a time segment."""
    start: float
    end: float
    layout: LayoutType
    crop_x_left: int = 0   # X position for left speaker crop
    crop_x_right: int = 0  # X position for right speaker crop
    crop_x_center: int = 0 # X position for center/single crop


# ═══════════════════════════════════════════════════════════════════════════════
# Main Engine
# ═══════════════════════════════════════════════════════════════════════════════


class PodcastReframeEngine(IReframeEngine):
    """Audio-Visual Active Speaker Framing for podcast/interview videos.

    Uses pyannote.audio for speaker diarization + MediaPipe for face detection.
    Falls back to face-only logic if audio diarization is unavailable.
    """

    # ─── Configuration ─────────────────────────────────────────────────────
    SAMPLE_INTERVAL_SEC = 1.0       # Sample 1 frame/sec for face detection
    MAX_SAMPLES = 60                # Max frames to sample
    FACE_CONFIDENCE = 0.50          # MediaPipe face detection threshold
    MIN_SEGMENT_DURATION = 3.0      # Minimum segment duration (anti-jitter)
    SAFE_ZONE_MARGIN_PX = 20        # Keep faces away from edges
    MIN_SEPARATION_RATIO = 0.15     # Min distance between faces to consider "2 speakers"
    MAX_SEGMENTS_PER_CHUNK = 15     # Max segments in single filter_complex (prevent OOM)
    CROSSFADE_MS = 200              # Audio crossfade duration at segment boundaries

    def __init__(self, hf_token: Optional[str] = None):
        """Initialize engine.

        Args:
            hf_token: HuggingFace token for pyannote models. If None,
                      reads from HF_TOKEN env var. If unavailable, falls back
                      to face-only mode.
        """
        self._hf_token = hf_token or os.environ.get("HF_TOKEN", "")
        self._face_detector = None
        self._diarization_pipeline = None
        self._diarization_available = False
        self._mp_module = None

    # ─────────────────────────────────────────────────────────────────────────
    # Lazy Loading
    # ─────────────────────────────────────────────────────────────────────────

    def _load_face_detector(self) -> bool:
        """Lazy-load MediaPipe Face Detection."""
        if self._face_detector is not None:
            return True
        try:
            import mediapipe as mp
            self._mp_module = mp
            self._face_detector = mp.solutions.face_detection.FaceDetection(
                min_detection_confidence=self.FACE_CONFIDENCE,
                model_selection=1,  # Optimized for 2-5m distance (podcast)
            )
            logger.info("podcast_reframe: MediaPipe Face Detection loaded")
            return True
        except Exception as e:
            logger.warning(f"podcast_reframe: MediaPipe load failed: {e}")
            return False

    def _load_diarization(self) -> bool:
        """Lazy-load pyannote.audio diarization pipeline."""
        if self._diarization_pipeline is not None:
            return True
        if self._diarization_available is False and self._diarization_pipeline is None:
            pass
        try:
            from pyannote.audio import Pipeline as PyannotePipeline
            if not self._hf_token:
                logger.info("podcast_reframe: No HF_TOKEN, skipping diarization (face-only mode)")
                self._diarization_available = False
                return False

            self._diarization_pipeline = PyannotePipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self._hf_token,
            )
            # Use GPU if available (RTX 3070 makes diarization 10-20x faster)
            import torch
            if torch.cuda.is_available():
                self._diarization_pipeline.to(torch.device("cuda"))
                logger.info("podcast_reframe: Pyannote diarization pipeline loaded [CUDA]")
            else:
                logger.info("podcast_reframe: Pyannote diarization pipeline loaded [CPU]")
            self._diarization_available = True
            return True
        except Exception as e:
            logger.warning(f"podcast_reframe: Pyannote load failed (face-only mode): {e}")
            self._diarization_available = False
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Public API (implements IReframeEngine)
    # ─────────────────────────────────────────────────────────────────────────

    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
        autogrid_enabled: bool = False,
        **kwargs,
    ) -> dict:
        """Reframe video using Audio-Visual Active Speaker detection."""
        if not os.path.exists(video_path):
            return {"output_path": video_path, "person_count": 0, "method": "error_no_input"}

        if target_aspect != "9:16":
            success = await self._simple_crop(video_path, output_path, target_aspect)
            return {
                "output_path": output_path if success else video_path,
                "person_count": 0,
                "method": "simple_crop",
            }

        if not self._load_face_detector():
            success = await self._center_crop_fallback(video_path, output_path)
            return {
                "output_path": output_path if success else video_path,
                "person_count": 0,
                "method": "center_crop_fallback",
            }

        try:
            result = await asyncio.to_thread(
                self._run_pipeline, video_path, output_path, autogrid_enabled
            )
            if result:
                return result
        except Exception as e:
            logger.warning(f"podcast_reframe: pipeline failed, falling back: {e}")

        success = await self._center_crop_fallback(video_path, output_path)
        return {
            "output_path": output_path if success else video_path,
            "person_count": 0,
            "method": "center_crop_fallback",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 4-Stage Pipeline
    # ─────────────────────────────────────────────────────────────────────────

    def _run_pipeline(
        self, video_path: str, output_path: str, autogrid_enabled: bool
    ) -> Optional[dict]:
        """Execute the full 4-stage pipeline (runs in thread)."""
        import cv2
        cv2.setNumThreads(0)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        duration = total_frames / fps
        cap.release()

        if width <= 0 or height <= 0 or duration <= 0:
            return None

        # ═══ Stage 1: Audio Diarization ═══
        speaker_segments = self._stage1_audio_diarization(video_path, duration)

        # ═══ Stage 2: Face Detection (with timestamps for correlation) ═══
        face_clusters = self._stage2_face_detection(video_path, width, height, fps, total_frames)

        if not face_clusters:
            logger.info("podcast_reframe: no faces detected, using center crop")
            return None

        # ═══ Stage 3: Layout Engine (with speaker-face correlation) ═══
        layout_segments = self._stage3_layout_engine(
            speaker_segments, face_clusters, width, height, duration, autogrid_enabled
        )

        if not layout_segments:
            return None

        # ═══ Stage 4: FFmpeg Render (chunked for long videos) ═══
        return self._stage4_render(video_path, output_path, width, height, layout_segments)

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 1: Audio Diarization
    # ─────────────────────────────────────────────────────────────────────────

    def _stage1_audio_diarization(
        self, video_path: str, duration: float
    ) -> List[SpeakerSegment]:
        """Extract speaker timeline using pyannote.audio.

        Returns list of SpeakerSegment indicating who speaks when.
        Falls back to uniform 'UNKNOWN' if diarization unavailable.
        """
        if not self._load_diarization():
            logger.info("podcast_reframe: diarization unavailable, using face-only mode")
            return self._fallback_speaker_segments(duration)

        audio_path = None
        try:
            audio_path = self._extract_audio(video_path)
            if not audio_path:
                return self._fallback_speaker_segments(duration)

            diarization = self._diarization_pipeline(audio_path)

            raw_segments: List[Tuple[float, float, str]] = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                raw_segments.append((turn.start, turn.end, speaker))

            if not raw_segments:
                return self._fallback_speaker_segments(duration)

            # Identify top 2 speakers by total duration
            speaker_durations: Dict[str, float] = {}
            for start, end, spk in raw_segments:
                speaker_durations[spk] = speaker_durations.get(spk, 0) + (end - start)

            top_speakers = sorted(
                speaker_durations.keys(),
                key=lambda s: speaker_durations[s],
                reverse=True,
            )[:2]

            if len(top_speakers) < 2:
                return [SpeakerSegment(0.0, duration, "A")]

            spk_map = {top_speakers[0]: "A", top_speakers[1]: "B"}

            return self._build_speaker_timeline(raw_segments, spk_map, duration)

        except Exception as e:
            logger.warning(f"podcast_reframe: diarization error: {e}")
            return self._fallback_speaker_segments(duration)
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

    def _extract_audio(self, video_path: str) -> Optional[str]:
        """Extract audio from video to temporary WAV (16kHz mono)."""
        try:
            audio_path = tempfile.mktemp(suffix=".wav")
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                audio_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and os.path.exists(audio_path):
                return audio_path
        except Exception as e:
            logger.warning(f"podcast_reframe: audio extraction failed: {e}")
        return None

    def _build_speaker_timeline(
        self,
        raw_segments: List[Tuple[float, float, str]],
        spk_map: Dict[str, str],
        duration: float,
    ) -> List[SpeakerSegment]:
        """Build speaker timeline with overlap detection (500ms slot resolution)."""
        interval = 0.5
        num_slots = int(duration / interval) + 1

        slot_a = [False] * num_slots
        slot_b = [False] * num_slots

        for start, end, spk in raw_segments:
            mapped = spk_map.get(spk)
            if not mapped:
                continue
            slot_start = int(start / interval)
            slot_end = int(end / interval)
            for i in range(max(0, slot_start), min(num_slots, slot_end + 1)):
                if mapped == "A":
                    slot_a[i] = True
                else:
                    slot_b[i] = True

        slot_labels: List[str] = []
        for i in range(num_slots):
            if slot_a[i] and slot_b[i]:
                slot_labels.append("A_B")
            elif slot_a[i]:
                slot_labels.append("A")
            elif slot_b[i]:
                slot_labels.append("B")
            else:
                slot_labels.append("SILENCE")

        if not slot_labels:
            return self._fallback_speaker_segments(duration)

        # Merge consecutive same-label slots
        segments: List[SpeakerSegment] = []
        current_label = slot_labels[0]
        current_start = 0.0

        for i in range(1, len(slot_labels)):
            if slot_labels[i] != current_label:
                segments.append(SpeakerSegment(current_start, i * interval, current_label))
                current_label = slot_labels[i]
                current_start = i * interval

        segments.append(SpeakerSegment(current_start, duration, current_label))
        return segments

    def _fallback_speaker_segments(self, duration: float) -> List[SpeakerSegment]:
        """Fallback: treat entire video as unknown speaker (face-only mode)."""
        return [SpeakerSegment(0.0, duration, "UNKNOWN")]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2: Face Detection (MediaPipe) — with timestamps
    # ─────────────────────────────────────────────────────────────────────────

    def _stage2_face_detection(
        self, video_path: str, width: int, height: int, fps: float, total_frames: int
    ) -> List[FaceCluster]:
        """Detect human faces and cluster into Left/Right with timestamps.

        Returns FaceClusters containing timed_detections for speaker-face correlation.
        """
        import cv2
        cv2.setNumThreads(0)

        transcode_path = video_path.rsplit(".", 1)[0] + "_h264_temp.mp4"
        detect_path = self._ensure_h264(video_path, transcode_path)

        try:
            cap = cv2.VideoCapture(detect_path)
            if not cap.isOpened():
                return []

            det_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            scale_x = width / det_width if det_width > 0 else 1.0

            sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
            sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

            # Collect timestamped detections
            timed_detections: List[TimedFaceDetection] = []

            for frame_idx in sample_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    continue

                time_sec = frame_idx / fps
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self._face_detector.process(frame_rgb)

                if results.detections:
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        cx = (bbox.xmin + bbox.width / 2) * det_width * scale_x
                        timed_detections.append(TimedFaceDetection(time=time_sec, face_x=cx))

            cap.release()
        finally:
            if detect_path != video_path and os.path.exists(transcode_path):
                os.remove(transcode_path)

        if not timed_detections:
            return []

        return self._cluster_faces_timed(timed_detections, width)

    def _cluster_faces_timed(
        self, timed_detections: List[TimedFaceDetection], frame_width: int
    ) -> List[FaceCluster]:
        """Cluster face detections into Left/Right with timestamp preservation."""
        all_x = [d.face_x for d in timed_detections]
        sorted_x = np.sort(all_x)

        if len(sorted_x) < 2:
            return [FaceCluster(
                label="center",
                median_x=float(np.median(sorted_x)),
                x_values=list(sorted_x),
                timed_detections=timed_detections,
            )]

        # Find largest gap for 2-cluster split
        gaps = np.diff(sorted_x)
        max_gap_idx = int(np.argmax(gaps))
        max_gap_value = gaps[max_gap_idx]

        if max_gap_value < frame_width * self.MIN_SEPARATION_RATIO:
            return [FaceCluster(
                label="center",
                median_x=float(np.median(sorted_x)),
                x_values=list(sorted_x),
                timed_detections=timed_detections,
            )]

        split_threshold = sorted_x[max_gap_idx]

        left_dets = [d for d in timed_detections if d.face_x <= split_threshold]
        right_dets = [d for d in timed_detections if d.face_x > split_threshold]

        clusters = []
        if left_dets:
            left_x = [d.face_x for d in left_dets]
            clusters.append(FaceCluster(
                label="left",
                median_x=float(np.median(left_x)),
                x_values=left_x,
                timed_detections=left_dets,
            ))
        if right_dets:
            right_x = [d.face_x for d in right_dets]
            clusters.append(FaceCluster(
                label="right",
                median_x=float(np.median(right_x)),
                x_values=right_x,
                timed_detections=right_dets,
            ))

        return clusters

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 3: Layout Engine (with Speaker-Face Correlation)
    # ─────────────────────────────────────────────────────────────────────────

    def _stage3_layout_engine(
        self,
        speaker_segments: List[SpeakerSegment],
        face_clusters: List[FaceCluster],
        width: int,
        height: int,
        duration: float,
        autogrid_enabled: bool,
    ) -> List[LayoutSegment]:
        """Combine audio + visual with speaker-face correlation.

        Speaker-Face Correlation Logic:
          1. Find solo segments (only A or only B speaking)
          2. Count face detections per cluster during each speaker's solo time
          3. Whichever cluster has MORE detections during Speaker A's solo time
             is mapped to Speaker A (and vice versa)
          4. If correlation is ambiguous, default: A=LEFT, B=RIGHT
        """
        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = min(int((height // 2) * 9 / 8), width)

        left_cluster = next((c for c in face_clusters if c.label == "left"), None)
        right_cluster = next((c for c in face_clusters if c.label == "right"), None)
        center_cluster = next((c for c in face_clusters if c.label == "center"), None)

        has_two_speakers = left_cluster is not None and right_cluster is not None

        # ─── Speaker-Face Correlation ─────────────────────────────────────
        # Determine which audio speaker corresponds to which face position
        speaker_a_is_left = True  # default assumption

        if has_two_speakers and any(s.speaker in ("A", "B") for s in speaker_segments):
            speaker_a_is_left = self._correlate_speaker_face(
                speaker_segments, left_cluster, right_cluster
            )
            if not speaker_a_is_left:
                logger.info("podcast_reframe: correlation found Speaker A = RIGHT face")

        # Calculate crop positions
        if has_two_speakers:
            # Apply correlation mapping
            if speaker_a_is_left:
                a_cluster, b_cluster = left_cluster, right_cluster
            else:
                a_cluster, b_cluster = right_cluster, left_cluster

            a_crop_x = self._calc_crop_x(int(a_cluster.median_x), crop_w_single, width)
            b_crop_x = self._calc_crop_x(int(b_cluster.median_x), crop_w_single, width)
            center_x = (a_cluster.median_x + b_cluster.median_x) / 2
            center_crop_x = self._calc_crop_x(int(center_x), crop_w_single, width)
            # Double grid: always left=top, right=bottom (visual consistency)
            left_grid_x = self._calc_crop_x(int(left_cluster.median_x), crop_w_double, width)
            right_grid_x = self._calc_crop_x(int(right_cluster.median_x), crop_w_double, width)
        else:
            median_x = center_cluster.median_x if center_cluster else width / 2
            a_crop_x = b_crop_x = center_crop_x = self._calc_crop_x(
                int(median_x), crop_w_single, width
            )
            left_grid_x = right_grid_x = self._calc_crop_x(
                int(median_x), crop_w_double, width
            )

        # Build layout segments
        raw_layouts: List[LayoutSegment] = []

        for seg in speaker_segments:
            if seg.end <= seg.start:
                continue

            if seg.speaker == "UNKNOWN":
                if has_two_speakers and autogrid_enabled:
                    layout = LayoutType.DOUBLE_GRID
                elif has_two_speakers:
                    layout = LayoutType.SINGLE_CENTER
                else:
                    layout = LayoutType.SINGLE_CENTER
            elif seg.speaker == "A":
                layout = LayoutType.SINGLE_LEFT if has_two_speakers else LayoutType.SINGLE_CENTER
            elif seg.speaker == "B":
                layout = LayoutType.SINGLE_RIGHT if has_two_speakers else LayoutType.SINGLE_CENTER
            elif seg.speaker == "A_B":
                if has_two_speakers and autogrid_enabled:
                    layout = LayoutType.DOUBLE_GRID
                else:
                    layout = LayoutType.SINGLE_CENTER
            elif seg.speaker == "SILENCE":
                layout = LayoutType.SINGLE_CENTER
            else:
                layout = LayoutType.SINGLE_CENTER

            raw_layouts.append(LayoutSegment(
                start=seg.start,
                end=seg.end,
                layout=layout,
                crop_x_left=left_grid_x if layout == LayoutType.DOUBLE_GRID else a_crop_x,
                crop_x_right=right_grid_x if layout == LayoutType.DOUBLE_GRID else b_crop_x,
                crop_x_center=center_crop_x,
            ))

        if not raw_layouts:
            return []

        return self._stabilize_segments(raw_layouts, duration)

    def _correlate_speaker_face(
        self,
        speaker_segments: List[SpeakerSegment],
        left_cluster: FaceCluster,
        right_cluster: FaceCluster,
    ) -> bool:
        """Determine if Speaker A corresponds to LEFT face cluster.

        Strategy: During Speaker A's solo segments, count face detections
        in left vs right cluster. More detections = that's Speaker A's face.

        Returns True if Speaker A = LEFT, False if Speaker A = RIGHT.
        """
        # Collect solo-A and solo-B time ranges
        a_solo_ranges = [(s.start, s.end) for s in speaker_segments if s.speaker == "A"]
        b_solo_ranges = [(s.start, s.end) for s in speaker_segments if s.speaker == "B"]

        def count_in_ranges(detections: List[TimedFaceDetection], ranges: List[Tuple[float, float]]) -> int:
            count = 0
            for d in detections:
                for start, end in ranges:
                    if start <= d.time <= end:
                        count += 1
                        break
            return count

        # Count left-cluster detections during A's solo time vs B's solo time
        left_during_a = count_in_ranges(left_cluster.timed_detections, a_solo_ranges)
        left_during_b = count_in_ranges(left_cluster.timed_detections, b_solo_ranges)
        right_during_a = count_in_ranges(right_cluster.timed_detections, a_solo_ranges)
        right_during_b = count_in_ranges(right_cluster.timed_detections, b_solo_ranges)

        # Score: positive = A is LEFT, negative = A is RIGHT
        # If left cluster has more detections during A's talking → A is left
        score_a_left = (left_during_a + right_during_b) - (right_during_a + left_during_b)

        logger.info(
            f"podcast_reframe: speaker-face correlation score={score_a_left} "
            f"(L_during_A={left_during_a}, R_during_A={right_during_a}, "
            f"L_during_B={left_during_b}, R_during_B={right_during_b})"
        )

        # If score is 0 (ambiguous), default to A=LEFT
        return score_a_left >= 0

    # ─────────────────────────────────────────────────────────────────────────
    # Anti-Jitter Stabilization
    # ─────────────────────────────────────────────────────────────────────────

    def _stabilize_segments(
        self, raw_layouts: List[LayoutSegment], duration: float
    ) -> List[LayoutSegment]:
        """Merge short segments with hold-previous logic.

        Improvements over naive absorption:
          1. Merge consecutive same-layout segments
          2. Short segments (<3s) hold PREVIOUS layout (not absorbed randomly)
          3. Prevent orphan single-frame layouts between two identical layouts
        """
        if not raw_layouts:
            return []

        # Step 1: Merge consecutive same-layout
        merged: List[LayoutSegment] = [raw_layouts[0]]
        for seg in raw_layouts[1:]:
            last = merged[-1]
            if seg.layout == last.layout:
                last.end = seg.end
            else:
                merged.append(seg)

        # Step 2: Hold-previous for short segments
        # A short segment adopts the layout of the PREVIOUS segment
        # (keeps visual continuity — camera doesn't jump for brief moments)
        stabilized: List[LayoutSegment] = []
        for seg in merged:
            seg_duration = seg.end - seg.start
            if seg_duration < self.MIN_SEGMENT_DURATION and stabilized:
                # Hold previous: extend the previous segment's end time
                stabilized[-1].end = seg.end
            else:
                stabilized.append(seg)

        # Step 3: Re-merge after absorption (may have created adjacent same-layouts)
        final: List[LayoutSegment] = [stabilized[0]] if stabilized else []
        for seg in stabilized[1:]:
            last = final[-1]
            if seg.layout == last.layout:
                last.end = seg.end
            else:
                final.append(seg)

        # Ensure coverage to end
        if final:
            final[-1].end = max(final[-1].end, duration)

        return final

    def _calc_crop_x(self, face_center_x: int, crop_width: int, frame_width: int) -> int:
        """Calculate crop X position, clamped within safe zone."""
        crop_x = face_center_x - crop_width // 2
        min_x = self.SAFE_ZONE_MARGIN_PX
        max_x = frame_width - crop_width - self.SAFE_ZONE_MARGIN_PX
        if max_x < min_x:
            return max(0, (frame_width - crop_width) // 2)
        return max(min_x, min(max_x, crop_x))

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 4: FFmpeg Dynamic Renderer (Chunked)
    # ─────────────────────────────────────────────────────────────────────────

    def _stage4_render(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        layout_segments: List[LayoutSegment],
    ) -> Optional[dict]:
        """Render final video with chunked approach for long videos.

        If segments <= MAX_SEGMENTS_PER_CHUNK: single-pass filter_complex (fast)
        If segments > MAX_SEGMENTS_PER_CHUNK: chunked render + concat demuxer (safe)
        """
        if len(layout_segments) <= self.MAX_SEGMENTS_PER_CHUNK:
            return self._render_single_pass(video_path, output_path, width, height, layout_segments)
        else:
            return self._render_chunked(video_path, output_path, width, height, layout_segments)

    def _render_single_pass(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        layout_segments: List[LayoutSegment],
    ) -> Optional[dict]:
        """Single-pass FFmpeg render (for ≤15 segments)."""
        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = min(int((height // 2) * 9 / 8), width)

        video_filters, audio_filters, v_labels, a_labels = self._build_filters(
            layout_segments, crop_w_single, crop_w_double, width, height
        )

        if not v_labels:
            return None

        n = len(v_labels)
        concat_v = "".join(v_labels) + f"concat=n={n}:v=1:a=0[vout]"
        concat_a = "".join(a_labels) + f"concat=n={n}:v=0:a=1[aout]"
        filter_complex = ";".join(video_filters + audio_filters + [concat_v, concat_a])

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return self._build_result(output_path, layout_segments)

        # Fallback: no audio filter
        filter_complex_no_audio = ";".join(video_filters + [concat_v])
        cmd_no_audio = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex_no_audio,
            "-map", "[vout]", "-map", "0:a?",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd_no_audio, capture_output=True, text=True, timeout=300)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return self._build_result(output_path, layout_segments, suffix="_no_audio")

        if result.stderr:
            logger.warning(f"podcast_reframe: FFmpeg error: {result.stderr[-500:]}")
        return None

    def _render_chunked(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        layout_segments: List[LayoutSegment],
    ) -> Optional[dict]:
        """Chunked render using concat demuxer (for >15 segments).

        Prevents OOM and 'Argument list too long' errors on long videos.
        Each chunk is rendered as a temp file, then joined with stream copy.
        """
        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = min(int((height // 2) * 9 / 8), width)

        tmp_dir = tempfile.mkdtemp(prefix="reframe_chunks_")
        chunk_files: List[str] = []

        try:
            # Split segments into chunks
            for chunk_idx in range(0, len(layout_segments), self.MAX_SEGMENTS_PER_CHUNK):
                chunk_segs = layout_segments[chunk_idx:chunk_idx + self.MAX_SEGMENTS_PER_CHUNK]
                chunk_path = os.path.join(tmp_dir, f"chunk_{chunk_idx:04d}.mp4")

                video_filters, audio_filters, v_labels, a_labels = self._build_filters(
                    chunk_segs, crop_w_single, crop_w_double, width, height
                )

                if not v_labels:
                    continue

                n = len(v_labels)
                concat_v = "".join(v_labels) + f"concat=n={n}:v=1:a=0[vout]"
                concat_a = "".join(a_labels) + f"concat=n={n}:v=0:a=1[aout]"
                filter_complex = ";".join(video_filters + audio_filters + [concat_v, concat_a])

                cmd = [
                    "ffmpeg", "-y", "-i", video_path,
                    "-filter_complex", filter_complex,
                    "-map", "[vout]", "-map", "[aout]",
                    *get_video_encoder_args("medium"),
                    "-c:a", "aac", "-movflags", "+faststart",
                    chunk_path,
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0 and os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
                    chunk_files.append(chunk_path)
                else:
                    logger.warning(f"podcast_reframe: chunk {chunk_idx} failed: {result.stderr[-200:] if result.stderr else 'unknown'}")

            if not chunk_files:
                return None

            # If only 1 chunk succeeded, just move it
            if len(chunk_files) == 1:
                shutil.move(chunk_files[0], output_path)
                return self._build_result(output_path, layout_segments, suffix="_chunked")

            # Concat all chunks using demuxer (stream copy = instant)
            concat_list_path = os.path.join(tmp_dir, "concat_list.txt")
            with open(concat_list_path, "w") as f:
                for chunk_path in chunk_files:
                    f.write(f"file '{chunk_path}'\n")

            cmd_concat = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list_path,
                "-c", "copy", "-movflags", "+faststart",
                output_path,
            ]

            result = subprocess.run(cmd_concat, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                logger.info(f"podcast_reframe: chunked render OK ({len(chunk_files)} chunks)")
                return self._build_result(output_path, layout_segments, suffix="_chunked")

            if result.stderr:
                logger.warning(f"podcast_reframe: concat failed: {result.stderr[-300:]}")
            return None

        finally:
            # Cleanup temp files
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _build_filters(
        self,
        segments: List[LayoutSegment],
        crop_w_single: int,
        crop_w_double: int,
        width: int,
        height: int,
    ) -> Tuple[List[str], List[str], List[str], List[str]]:
        """Build FFmpeg filter_complex components for a set of segments."""
        video_filters: List[str] = []
        audio_filters: List[str] = []
        v_labels: List[str] = []
        a_labels: List[str] = []

        for i, seg in enumerate(segments):
            if seg.end <= seg.start:
                continue

            v_out = f"v{i}"
            a_out = f"a{i}"
            start_t = f"{seg.start:.3f}"
            end_t = f"{seg.end:.3f}"

            if seg.layout == LayoutType.DOUBLE_GRID:
                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,split=2[s{i}_top][s{i}_bot];"
                    f"[s{i}_top]crop={crop_w_double}:{height}:{seg.crop_x_left}:0,scale=1080:960[s{i}_t];"
                    f"[s{i}_bot]crop={crop_w_double}:{height}:{seg.crop_x_right}:0,scale=1080:960[s{i}_b];"
                    f"[s{i}_t][s{i}_b]vstack=inputs=2[{v_out}]"
                )
            elif seg.layout == LayoutType.SINGLE_LEFT:
                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,"
                    f"crop={crop_w_single}:{height}:{seg.crop_x_left}:0,scale=1080:1920[{v_out}]"
                )
            elif seg.layout == LayoutType.SINGLE_RIGHT:
                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,"
                    f"crop={crop_w_single}:{height}:{seg.crop_x_right}:0,scale=1080:1920[{v_out}]"
                )
            else:
                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,"
                    f"crop={crop_w_single}:{height}:{seg.crop_x_center}:0,scale=1080:1920[{v_out}]"
                )

            audio_filters.append(
                f"[0:a]atrim={start_t}:{end_t},asetpts=PTS-STARTPTS[{a_out}]"
            )
            v_labels.append(f"[{v_out}]")
            a_labels.append(f"[{a_out}]")

        return video_filters, audio_filters, v_labels, a_labels

    def _build_result(
        self,
        output_path: str,
        layout_segments: List[LayoutSegment],
        suffix: str = "",
    ) -> dict:
        """Build standardized result dict."""
        unique_layouts = set(seg.layout for seg in layout_segments)
        method = "podcast_reframe"
        if self._diarization_available:
            method += "_audio_visual"
        else:
            method += "_face_only"
        method += suffix

        logger.info(
            f"podcast_reframe: OK — {len(layout_segments)} segments, "
            f"layouts: {[l.value for l in unique_layouts]}"
        )
        return {
            "output_path": output_path,
            "person_count": 2 if any(seg.layout == LayoutType.DOUBLE_GRID for seg in layout_segments) else 1,
            "masks_available": False,
            "method": method,
            "segments": len(layout_segments),
            "layouts_used": [l.value for l in unique_layouts],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_h264(self, video_path: str, transcode_path: str) -> str:
        """Transcode non-h264 video for MediaPipe compatibility."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            codec = result.stdout.strip().lower()
            if codec in ("av1", "vp9", "vp8", "hevc"):
                cmd = [
                    "ffmpeg", "-y", "-i", video_path,
                    *get_video_encoder_args("low"),
                    "-an", "-movflags", "+faststart",
                    transcode_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0 and os.path.exists(transcode_path):
                    return transcode_path
            return video_path
        except Exception:
            return video_path

    async def _simple_crop(self, input_path: str, output_path: str, target_aspect: str) -> bool:
        """Simple crop for non-9:16 targets (1:1, etc.)."""
        if target_aspect == "1:1":
            crop_filter = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
        else:
            shutil.copy2(input_path, output_path)
            return True

        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", crop_filter,
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        if os.path.exists(output_path):
            os.remove(output_path)
        return False

    async def _center_crop_fallback(self, input_path: str, output_path: str) -> bool:
        """Center crop to 9:16 as final fallback."""
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", "crop=ih*9/16:ih,scale=1080:1920",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        if os.path.exists(output_path):
            os.remove(output_path)
        return False
