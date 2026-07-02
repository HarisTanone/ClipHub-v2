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
class FaceCluster:
    """A detected speaker's face position cluster."""
    label: str            # 'left' or 'right'
    median_x: float       # Median X position in pixels
    x_values: List[float] = field(default_factory=list)


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
    OVERLAP_THRESHOLD = 0.5         # Seconds of overlap to trigger double grid

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
            # Already tried and failed
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
            self._diarization_available = True
            logger.info("podcast_reframe: Pyannote diarization pipeline loaded")
            return True
        except Exception as e:
            logger.warning(f"podcast_reframe: Pyannote load failed (face-only mode): {e}")
            self._diarization_available = False
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Public API (implements IYoloReframeEngine interface)
    # ─────────────────────────────────────────────────────────────────────────

    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
        autogrid_enabled: bool = False,
        **kwargs,
    ) -> dict:
        """Reframe video using Audio-Visual Active Speaker detection.

        Args:
            video_path: Input video (typically 16:9 podcast recording)
            output_path: Output path for reframed 9:16 video
            target_aspect: Target aspect ratio (only '9:16' triggers smart reframe)
            autogrid_enabled: Whether to allow double-grid layout

        Returns:
            Dict with output_path, person_count, method, etc.
        """
        if not os.path.exists(video_path):
            return {"output_path": video_path, "person_count": 0, "method": "error_no_input"}

        # Non-9:16 targets get simple crop
        if target_aspect != "9:16":
            success = await self._simple_crop(video_path, output_path, target_aspect)
            return {
                "output_path": output_path if success else video_path,
                "person_count": 0,
                "method": "simple_crop",
            }

        # Load face detector (required)
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

        # Final fallback
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
        cv2.setNumThreads(0)  # Prevent glibc mutex crash

        # Get video metadata
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

        # ═══ Stage 2: Face Detection ═══
        face_clusters = self._stage2_face_detection(video_path, width, height, fps, total_frames)

        if not face_clusters:
            logger.info("podcast_reframe: no faces detected, using center crop")
            return None

        # ═══ Stage 3: Layout Engine ═══
        layout_segments = self._stage3_layout_engine(
            speaker_segments, face_clusters, width, height, duration, autogrid_enabled
        )

        if not layout_segments:
            return None

        # ═══ Stage 4: FFmpeg Render ═══
        return self._stage4_render(video_path, output_path, width, height, layout_segments)

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 1: Audio Diarization
    # ─────────────────────────────────────────────────────────────────────────

    def _stage1_audio_diarization(
        self, video_path: str, duration: float
    ) -> List[SpeakerSegment]:
        """Extract speaker timeline using pyannote.audio.

        Returns list of SpeakerSegment indicating who speaks when.
        Falls back to uniform 'A_B' if diarization unavailable.
        """
        # Try loading diarization (non-blocking if HF_TOKEN missing)
        if not self._load_diarization():
            logger.info("podcast_reframe: diarization unavailable, using face-only mode")
            return self._fallback_speaker_segments(duration)

        # Extract audio to temp WAV
        audio_path = None
        try:
            audio_path = self._extract_audio(video_path)
            if not audio_path:
                return self._fallback_speaker_segments(duration)

            # Run diarization
            diarization = self._diarization_pipeline(audio_path)

            # Parse diarization output into SpeakerSegments
            raw_segments: List[Tuple[float, float, str]] = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                raw_segments.append((turn.start, turn.end, speaker))

            if not raw_segments:
                return self._fallback_speaker_segments(duration)

            # Identify the 2 most prominent speakers
            speaker_durations: Dict[str, float] = {}
            for start, end, spk in raw_segments:
                speaker_durations[spk] = speaker_durations.get(spk, 0) + (end - start)

            # Sort by total speaking time, take top 2
            top_speakers = sorted(speaker_durations.keys(), key=lambda s: speaker_durations[s], reverse=True)[:2]

            if len(top_speakers) < 2:
                # Only 1 speaker detected → single framing throughout
                return [SpeakerSegment(0.0, duration, "A")]

            spk_map = {top_speakers[0]: "A", top_speakers[1]: "B"}

            # Build timeline with overlap detection
            return self._build_speaker_timeline(raw_segments, spk_map, duration)

        except Exception as e:
            logger.warning(f"podcast_reframe: diarization error: {e}")
            return self._fallback_speaker_segments(duration)
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

    def _extract_audio(self, video_path: str) -> Optional[str]:
        """Extract audio from video to temporary WAV file."""
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
        """Build speaker timeline with overlap detection.

        Divides time into fixed intervals and classifies each as A, B, A_B, or SILENCE.
        """
        interval = 0.5  # 500ms resolution
        num_slots = int(duration / interval) + 1

        # Track activity per slot
        slot_a = [False] * num_slots
        slot_b = [False] * num_slots

        for start, end, spk in raw_segments:
            mapped = spk_map.get(spk)
            if not mapped:
                continue  # Skip minor speakers
            slot_start = int(start / interval)
            slot_end = int(end / interval)
            for i in range(max(0, slot_start), min(num_slots, slot_end + 1)):
                if mapped == "A":
                    slot_a[i] = True
                else:
                    slot_b[i] = True

        # Classify each slot
        slot_labels: List[str] = []
        for i in range(num_slots):
            a_active = slot_a[i]
            b_active = slot_b[i]
            if a_active and b_active:
                slot_labels.append("A_B")
            elif a_active:
                slot_labels.append("A")
            elif b_active:
                slot_labels.append("B")
            else:
                slot_labels.append("SILENCE")

        # Merge consecutive same-label slots into segments
        segments: List[SpeakerSegment] = []
        if not slot_labels:
            return self._fallback_speaker_segments(duration)

        current_label = slot_labels[0]
        current_start = 0.0

        for i in range(1, len(slot_labels)):
            if slot_labels[i] != current_label:
                segments.append(SpeakerSegment(current_start, i * interval, current_label))
                current_label = slot_labels[i]
                current_start = i * interval

        # Final segment
        segments.append(SpeakerSegment(current_start, duration, current_label))

        return segments

    def _fallback_speaker_segments(self, duration: float) -> List[SpeakerSegment]:
        """Fallback: treat entire video as both speakers active (face-only mode)."""
        return [SpeakerSegment(0.0, duration, "UNKNOWN")]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2: Face Detection (MediaPipe)
    # ─────────────────────────────────────────────────────────────────────────

    def _stage2_face_detection(
        self, video_path: str, width: int, height: int, fps: float, total_frames: int
    ) -> List[FaceCluster]:
        """Detect human faces and cluster them into Left/Right positions.

        MediaPipe Face Detection is strict about real human face texture,
        so action figures, toys, and posters on the desk won't trigger false positives.
        """
        import cv2
        cv2.setNumThreads(0)

        # Handle non-h264 codecs
        transcode_path = video_path.rsplit(".", 1)[0] + "_h264_temp.mp4"
        detect_path = self._ensure_h264(video_path, transcode_path)

        try:
            cap = cv2.VideoCapture(detect_path)
            if not cap.isOpened():
                return []

            det_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            det_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            scale_x = width / det_width if det_width > 0 else 1.0

            sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
            sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

            all_face_x: List[float] = []

            for frame_idx in sample_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self._face_detector.process(frame_rgb)

                if results.detections:
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        # Center X in original video coordinates
                        cx = (bbox.xmin + bbox.width / 2) * det_width * scale_x
                        all_face_x.append(cx)

            cap.release()
        finally:
            if detect_path != video_path and os.path.exists(transcode_path):
                os.remove(transcode_path)

        if not all_face_x:
            return []

        # Cluster faces into Left/Right using gap-based splitting
        return self._cluster_faces(all_face_x, width)

    def _cluster_faces(self, all_face_x: List[float], frame_width: int) -> List[FaceCluster]:
        """Cluster detected face X positions into Left/Right speakers.

        Uses largest-gap splitting: find the biggest gap between sorted X values.
        If gap is significant (>15% of frame width), we have 2 speakers.
        """
        sorted_x = np.sort(all_face_x)

        if len(sorted_x) < 2:
            # Only one face position detected → single speaker
            return [FaceCluster(
                label="center",
                median_x=float(np.median(sorted_x)),
                x_values=list(sorted_x),
            )]

        # Find largest gap
        gaps = np.diff(sorted_x)
        max_gap_idx = int(np.argmax(gaps))
        max_gap_value = gaps[max_gap_idx]

        if max_gap_value < frame_width * self.MIN_SEPARATION_RATIO:
            # All faces are clustered together → single speaker or same person
            return [FaceCluster(
                label="center",
                median_x=float(np.median(sorted_x)),
                x_values=list(sorted_x),
            )]

        # Split into left and right clusters
        split_threshold = sorted_x[max_gap_idx]
        left_x = [x for x in all_face_x if x <= split_threshold]
        right_x = [x for x in all_face_x if x > split_threshold]

        clusters = []
        if left_x:
            clusters.append(FaceCluster(
                label="left",
                median_x=float(np.median(left_x)),
                x_values=left_x,
            ))
        if right_x:
            clusters.append(FaceCluster(
                label="right",
                median_x=float(np.median(right_x)),
                x_values=right_x,
            ))

        return clusters

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 3: Layout Engine
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
        """Combine audio diarization + face positions to produce layout timeline.

        Decision logic:
          - Speaker A only → SINGLE_LEFT (crop to left face)
          - Speaker B only → SINGLE_RIGHT (crop to right face)
          - Both speaking  → DOUBLE_GRID (if autogrid enabled, else SINGLE_CENTER)
          - Silence        → SINGLE_CENTER
          - UNKNOWN        → Use face count to decide (face-only fallback mode)
        """
        # Calculate crop dimensions
        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = min(int((height // 2) * 9 / 8), width)

        # Map speaker labels to face clusters
        # Convention: Speaker A = leftmost face, Speaker B = rightmost face
        left_cluster = next((c for c in face_clusters if c.label == "left"), None)
        right_cluster = next((c for c in face_clusters if c.label == "right"), None)
        center_cluster = next((c for c in face_clusters if c.label == "center"), None)

        # If only 1 cluster (single speaker), use center logic
        has_two_speakers = left_cluster is not None and right_cluster is not None

        # Calculate crop X positions
        if has_two_speakers:
            left_crop_x = self._calc_crop_x(int(left_cluster.median_x), crop_w_single, width)
            right_crop_x = self._calc_crop_x(int(right_cluster.median_x), crop_w_single, width)
            center_x = (left_cluster.median_x + right_cluster.median_x) / 2
            center_crop_x = self._calc_crop_x(int(center_x), crop_w_single, width)
            # Double grid crops (wider per panel)
            left_grid_x = self._calc_crop_x(int(left_cluster.median_x), crop_w_double, width)
            right_grid_x = self._calc_crop_x(int(right_cluster.median_x), crop_w_double, width)
        else:
            # Single speaker or center only
            median_x = center_cluster.median_x if center_cluster else width / 2
            left_crop_x = right_crop_x = center_crop_x = self._calc_crop_x(
                int(median_x), crop_w_single, width
            )
            left_grid_x = right_grid_x = self._calc_crop_x(
                int(median_x), crop_w_double, width
            )

        # Build layout segments from speaker timeline
        raw_layouts: List[LayoutSegment] = []

        for seg in speaker_segments:
            if seg.end <= seg.start:
                continue

            if seg.speaker == "UNKNOWN":
                # Face-only fallback mode: use face count to decide
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
                crop_x_left=left_grid_x if layout == LayoutType.DOUBLE_GRID else left_crop_x,
                crop_x_right=right_grid_x if layout == LayoutType.DOUBLE_GRID else right_crop_x,
                crop_x_center=center_crop_x,
            ))

        if not raw_layouts:
            return []

        # Merge and stabilize segments (anti-jitter)
        return self._stabilize_segments(raw_layouts, duration)

    def _stabilize_segments(
        self, raw_layouts: List[LayoutSegment], duration: float
    ) -> List[LayoutSegment]:
        """Merge short segments and prevent rapid layout flickering.

        Rules:
          - Segments shorter than MIN_SEGMENT_DURATION get absorbed into neighbors
          - Consecutive same-layout segments get merged
        """
        if not raw_layouts:
            return []

        # Step 1: Merge consecutive same-layout segments
        merged: List[LayoutSegment] = [raw_layouts[0]]
        for seg in raw_layouts[1:]:
            last = merged[-1]
            if seg.layout == last.layout:
                # Extend previous segment
                last.end = seg.end
            else:
                merged.append(seg)

        # Step 2: Absorb short segments into their neighbors
        stabilized: List[LayoutSegment] = []
        for seg in merged:
            seg_duration = seg.end - seg.start
            if seg_duration < self.MIN_SEGMENT_DURATION and stabilized:
                # Absorb into previous segment
                stabilized[-1].end = seg.end
            else:
                stabilized.append(seg)

        # Ensure last segment covers to end
        if stabilized:
            stabilized[-1].end = max(stabilized[-1].end, duration)

        return stabilized

    def _calc_crop_x(self, face_center_x: int, crop_width: int, frame_width: int) -> int:
        """Calculate crop X position, clamped within safe zone."""
        crop_x = face_center_x - crop_width // 2
        min_x = self.SAFE_ZONE_MARGIN_PX
        max_x = frame_width - crop_width - self.SAFE_ZONE_MARGIN_PX
        if max_x < min_x:
            return max(0, (frame_width - crop_width) // 2)
        return max(min_x, min(max_x, crop_x))

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 4: FFmpeg Dynamic Renderer
    # ─────────────────────────────────────────────────────────────────────────

    def _stage4_render(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        layout_segments: List[LayoutSegment],
    ) -> Optional[dict]:
        """Render final video with dynamic crops per layout segment.

        Uses FFmpeg filter_complex to trim/crop/scale/concat segments.
        """
        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = min(int((height // 2) * 9 / 8), width)

        video_filters: List[str] = []
        audio_filters: List[str] = []
        v_labels: List[str] = []
        a_labels: List[str] = []

        for i, seg in enumerate(layout_segments):
            if seg.end <= seg.start:
                continue

            v_out = f"v{i}"
            a_out = f"a{i}"

            start_t = f"{seg.start:.3f}"
            end_t = f"{seg.end:.3f}"

            if seg.layout == LayoutType.DOUBLE_GRID:
                # Split screen: top = left speaker, bottom = right speaker
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
                # SINGLE_CENTER
                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,"
                    f"crop={crop_w_single}:{height}:{seg.crop_x_center}:0,scale=1080:1920[{v_out}]"
                )

            audio_filters.append(
                f"[0:a]atrim={start_t}:{end_t},asetpts=PTS-STARTPTS[{a_out}]"
            )
            v_labels.append(f"[{v_out}]")
            a_labels.append(f"[{a_out}]")

        if not v_labels:
            return None

        # Build concat filters
        n = len(v_labels)
        concat_v = "".join(v_labels) + f"concat=n={n}:v=1:a=0[vout]"
        concat_a = "".join(a_labels) + f"concat=n={n}:v=0:a=1[aout]"

        filter_complex = ";".join(video_filters + audio_filters + [concat_v, concat_a])

        # Render with GPU encoder if available
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
            # Count unique layout types used
            unique_layouts = set(seg.layout for seg in layout_segments)
            method = "podcast_reframe"
            if self._diarization_available:
                method += "_audio_visual"
            else:
                method += "_face_only"

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

        # Fallback: try without audio filters (some videos have no audio stream)
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
            logger.info("podcast_reframe: OK (no-audio fallback)")
            return {
                "output_path": output_path,
                "person_count": 1,
                "masks_available": False,
                "method": "podcast_reframe_no_audio",
            }

        if result.stderr:
            logger.warning(f"podcast_reframe: FFmpeg error: {result.stderr[-500:]}")
        return None

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
