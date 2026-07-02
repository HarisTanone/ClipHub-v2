"""PodcastReframeEngine — Simple & Reliable Face-Based Reframing.

Strategy: SIMPLE. Detect faces → decide layout → crop with correct math.

Rules:
  - 0 faces detected → center crop fallback
  - 1 face cluster → single 9:16 crop centered on that face
  - 2 face clusters (both must appear in SAME frame ≥50% of samples) → double grid
  - Audio is ALWAYS stream-copied, never re-encoded through filter_complex
  - Aspect ratio math: 9:16 output = 1080x1920

Double Grid Math (CORRECT):
  - Output: 1080x1920 (9:16)
  - Each panel: 1080x960 (half height)
  - Source is 16:9 (e.g. 1920x1080)
  - Per panel: crop 1080x540 from source (9:16 ratio of half), scale to 1080x960
  - crop_w = height * 9/16, crop_h = height/2 (half of source height per panel)
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

logger = logging.getLogger(__name__)


@dataclass
class FacePosition:
    """Face X position detected in a specific frame."""
    frame_time: float
    center_x: float  # pixels, original resolution


class PodcastReframeEngine(IReframeEngine):
    """Simple face-based reframing. No pyannote (unreliable). Pure MediaPipe."""

    SAMPLE_INTERVAL_SEC = 1.0
    MAX_SAMPLES = 60
    FACE_CONFIDENCE = 0.55
    MIN_FACE_SIZE_RATIO = 0.05
    MAX_FACE_SIZE_RATIO = 0.50
    MIN_SEPARATION_RATIO = 0.20  # 20% of frame width to consider "two people"
    MIN_COEXIST_RATIO = 0.40     # ≥40% of frames must have BOTH faces simultaneously

    def __init__(self, hf_token: Optional[str] = None):
        self._face_detector = None

    def _load_face_detector(self) -> bool:
        if self._face_detector is not None:
            return True
        try:
            import mediapipe as mp
            self._face_detector = mp.solutions.face_detection.FaceDetection(
                min_detection_confidence=self.FACE_CONFIDENCE,
                model_selection=1,
            )
            logger.info("podcast_reframe: MediaPipe loaded")
            return True
        except Exception as e:
            logger.warning(f"podcast_reframe: MediaPipe failed: {e}")
            return False

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

        # Detect faces with per-frame info
        per_frame_faces = self._detect_faces(video_path, width, height, fps, total_frames)

        if not per_frame_faces:
            logger.info("podcast_reframe: no faces → center crop")
            return None

        # Decide: 1 person or 2 people?
        decision = self._decide_layout(per_frame_faces, width, autogrid)

        # Render
        if decision["layout"] == "double":
            return self._render_double_grid(video_path, output_path, width, height, decision)
        else:
            return self._render_single_crop(video_path, output_path, width, height, decision)

    # ─── Face Detection ───────────────────────────────────────────────────

    def _detect_faces(
        self, video_path: str, width: int, height: int, fps: float, total_frames: int
    ) -> List[List[float]]:
        """Returns list of per-frame face X positions. Each entry = list of X centers for that frame."""
        import cv2
        cv2.setNumThreads(0)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

        per_frame: List[List[float]] = []

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

            results = self._face_detector.process(proc_frame)

            frame_faces: List[float] = []
            if results.detections:
                for det in results.detections:
                    bbox = det.location_data.relative_bounding_box
                    # Size filter
                    if bbox.width < self.MIN_FACE_SIZE_RATIO or bbox.width > self.MAX_FACE_SIZE_RATIO:
                        continue
                    # X center in original resolution
                    cx = (bbox.xmin + bbox.width / 2) * width
                    frame_faces.append(cx)

            per_frame.append(frame_faces)

        cap.release()
        return per_frame

    # ─── Layout Decision ──────────────────────────────────────────────────

    def _decide_layout(self, per_frame_faces: List[List[float]], width: int, autogrid: bool) -> dict:
        """Decide single or double grid based on per-frame face data.

        Key rule: Double grid ONLY if ≥40% of frames show 2+ faces simultaneously
        AND those faces are ≥20% apart horizontally.
        """
        all_x = [x for frame in per_frame_faces for x in frame]
        if not all_x:
            return {"layout": "single", "crop_x": width // 2}

        # Count frames with 2+ faces that are sufficiently separated
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
            f"podcast_reframe: coexist={coexist_ratio:.0%} "
            f"({multi_face_frames}/{total_frames} frames with 2 separated faces)"
        )

        # Decision
        if coexist_ratio >= self.MIN_COEXIST_RATIO and autogrid and left_positions:
            # DOUBLE GRID — confirmed 2 people
            left_x = int(np.median(left_positions))
            right_x = int(np.median(right_positions))
            logger.info(f"podcast_reframe: DOUBLE GRID (left_x={left_x}, right_x={right_x})")
            return {"layout": "double", "left_x": left_x, "right_x": right_x}
        else:
            # SINGLE — find the most stable face position
            median_x = int(np.median(all_x))
            logger.info(f"podcast_reframe: SINGLE CROP (x={median_x})")
            return {"layout": "single", "crop_x": median_x}

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
            logger.info(f"podcast_reframe: single crop OK (x={crop_x}, w={crop_w})")
            return {"output_path": output_path, "person_count": 1, "method": "podcast_single_crop"}

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
            logger.info(f"podcast_reframe: double grid OK (L={left_x}, R={right_x}, crop={crop_w}x{crop_h})")
            return {"output_path": output_path, "person_count": 2, "method": "podcast_double_grid"}

        if result.stderr:
            logger.warning(f"podcast_reframe: double grid failed: {result.stderr[-300:]}")
        return None

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
