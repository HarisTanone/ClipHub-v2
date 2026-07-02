"""YoloReframeEngine — YOLO11 person detection + dynamic segment-based reframing.

Key design:
1. MIN_SEPARATION_RATIO = 0.15 — triggers grid layout more aggressively.
2. Dynamic segment-based switching (SEGMENT_DUR_SEC = 3.0) — per-segment
   decision between single-crop and grid based on detection distribution.
3. setsar=1 on ALL FFmpeg outputs — prevents SAR concat errors.
4. Single _render_dynamic_grid method replaces autogrid/union/smooth split.
5. No autogrid_enabled parameter — grid triggers automatically when speakers
   are separated.

Key thresholds:
- MIN_CLUSTER_SUPPORT = 0.15 (each side needs 15% of detections)
- MIN_SEPARATION_RATIO = 0.15 (speakers 15% frame width apart → grid)
- SEGMENT_DUR_SEC = 3.0 (decision granularity)
"""
import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from src.domain.interfaces import IYoloReframeEngine
from src.infrastructure.gpu_encoder import get_video_encoder_args

logger = logging.getLogger(__name__)


@dataclass
class SpeakerCluster:
    """A spatial cluster of person detections along the x-axis."""

    center_x: float  # median x center of cluster
    support: float  # fraction of total detections in this cluster
    x_min: float  # leftmost detection x
    x_max: float  # rightmost detection x


class YoloReframeEngine(IYoloReframeEngine):
    """YOLO-based person-aware reframing with dynamic segment-based grid."""

    # Sampling
    SAMPLE_INTERVAL_SEC = 1.0
    MAX_SAMPLES = 60
    CONFIDENCE_THRESHOLD = 0.45

    # Clustering thresholds
    MIN_CLUSTER_SUPPORT = 0.15  # each cluster needs 15% of detections
    MIN_SEPARATION_RATIO = 0.15  # clusters 15% frame width apart → grid

    # Segment-based switching
    SEGMENT_DUR_SEC = 3.0  # evaluate layout every 3 seconds

    # Smooth tracking
    SMOOTHING_ALPHA = 0.08
    DEADZONE_PIXELS = 30

    # Safety
    SAFE_ZONE_MARGIN = 20  # px margin from frame edge

    def __init__(self, model_path: str = ""):
        self._model_path = model_path or "yolo11n.pt"
        self._model = None

    def _load_model(self) -> bool:
        """Lazy-load YOLO model (GPU if available)."""
        if self._model is not None:
            return True
        try:
            from ultralytics import YOLO

            self._model = YOLO(self._model_path)
            try:
                import torch

                if torch.cuda.is_available():
                    self._model.to("cuda")
                    logger.info(f"yolo_reframe: model loaded ({self._model_path}) [CUDA GPU]")
                else:
                    logger.info(f"yolo_reframe: model loaded ({self._model_path}) [CPU]")
            except Exception:
                logger.info(f"yolo_reframe: model loaded ({self._model_path}) [CPU fallback]")
            return True
        except Exception as e:
            logger.warning(f"yolo_reframe: failed to load model: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
    ) -> dict:
        """Reframe video with dynamic segment-based person tracking."""
        if not os.path.exists(video_path):
            logger.error(f"yolo_reframe: input not found {video_path}")
            return {"output_path": video_path, "person_count": 0, "masks_available": False}

        if target_aspect != "9:16":
            if target_aspect == "1:1":
                success = await self._center_crop_fallback(video_path, output_path, target_aspect)
                return {
                    "output_path": output_path if success else video_path,
                    "person_count": 0,
                    "masks_available": False,
                }
            else:
                shutil.copy2(video_path, output_path)
                return {"output_path": output_path, "person_count": 0, "masks_available": False}

        if self._load_model():
            try:
                result = await asyncio.to_thread(
                    self._smooth_track_and_crop, video_path, output_path, target_aspect
                )
                if result:
                    return result
            except Exception as e:
                logger.warning(f"yolo_reframe: tracking failed, falling back: {e}")

        success = await self._center_crop_fallback(video_path, output_path, target_aspect)
        return {
            "output_path": output_path if success else video_path,
            "person_count": 0,
            "masks_available": False,
            "method": "center_crop_fallback",
        }

    # ─────────────────────────────────────────────────────────────────────
    # Internal pipeline
    # ─────────────────────────────────────────────────────────────────────

    def _smooth_track_and_crop(
        self, video_path: str, output_path: str, target_aspect: str
    ) -> Optional[dict]:
        """Main pipeline: detect → analyze per-segment → render dynamic grid."""
        transcode_path = video_path.rsplit(".", 1)[0] + "_h264_temp.mp4"
        detect_path = self._ensure_h264(video_path, transcode_path)

        try:
            return self._track_impl(detect_path, video_path, output_path, target_aspect)
        finally:
            if detect_path != video_path and os.path.exists(transcode_path):
                os.remove(transcode_path)

    def _track_impl(
        self, detect_path: str, original_path: str, output_path: str, target_aspect: str
    ) -> Optional[dict]:
        """Detect persons, build per-segment layout decisions, render."""
        import cv2

        cap = cv2.VideoCapture(detect_path)
        if not cap.isOpened():
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        orig_cap = cv2.VideoCapture(original_path)
        orig_width = int(orig_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(orig_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        orig_fps = orig_cap.get(cv2.CAP_PROP_FPS) or 30
        orig_cap.release()

        scale_x = orig_width / width if width > 0 else 1.0

        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[: self.MAX_SAMPLES]

        # frame_centers: list of (frame_idx, [(cx, cy), ...])
        frame_centers: List[Tuple[int, List[Tuple[float, float]]]] = []

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            results = self._model(frame, classes=[0], verbose=False)
            dets: List[Tuple[float, float]] = []
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        if conf > self.CONFIDENCE_THRESHOLD:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            cx = ((x1 + x2) / 2) * scale_x
                            cy = (y1 + y2) / 2
                            dets.append((cx, cy))

            frame_centers.append((frame_idx, dets))

        cap.release()

        # Check if we have any detections at all
        if not frame_centers or all(len(d) == 0 for _, d in frame_centers):
            logger.info("yolo_reframe: no persons detected in any frame")
            return None

        # Analyze layout globally to decide if split is present
        all_cx: List[float] = []
        for _, centers in frame_centers:
            for cx, _ in centers:
                all_cx.append(cx)

        if not all_cx:
            return None

        all_cx_arr = np.array(all_cx)
        sorted_cx = np.sort(all_cx_arr)

        # Global split detection
        is_split = False
        left_cluster: Optional[SpeakerCluster] = None
        right_cluster: Optional[SpeakerCluster] = None

        if len(sorted_cx) >= 4:
            gaps = np.diff(sorted_cx)
            max_gap_idx = int(np.argmax(gaps))
            max_gap = gaps[max_gap_idx]
            separation_ratio = max_gap / orig_width

            left_points = sorted_cx[: max_gap_idx + 1]
            right_points = sorted_cx[max_gap_idx + 1:]

            left_support = len(left_points) / len(sorted_cx)
            right_support = len(right_points) / len(sorted_cx)

            is_split = (
                separation_ratio >= self.MIN_SEPARATION_RATIO
                and left_support >= self.MIN_CLUSTER_SUPPORT
                and right_support >= self.MIN_CLUSTER_SUPPORT
            )

            if is_split:
                left_cluster = SpeakerCluster(
                    center_x=float(np.median(left_points)),
                    support=left_support,
                    x_min=float(left_points[0]),
                    x_max=float(left_points[-1]),
                )
                right_cluster = SpeakerCluster(
                    center_x=float(np.median(right_points)),
                    support=right_support,
                    x_min=float(right_points[0]),
                    x_max=float(right_points[-1]),
                )
                logger.info(
                    f"yolo_reframe: TWO speakers — "
                    f"left={left_cluster.center_x:.0f} ({left_support:.0%}), "
                    f"right={right_cluster.center_x:.0f} ({right_support:.0%}), "
                    f"separation={separation_ratio:.0%}"
                )

        if not is_split:
            # Single speaker — simple smooth crop
            median_cx = float(np.median(sorted_cx))
            crop_w = min(int(orig_height * 9 / 16), orig_width)
            crop_x = int(median_cx - crop_w / 2)
            crop_x = self._clamp_crop_x(crop_x, crop_w, orig_width)

            cmd = [
                "ffmpeg", "-y", "-i", original_path,
                "-vf", f"crop={crop_w}:{orig_height}:{crop_x}:0,scale=1080:1920,setsar=1",
                *get_video_encoder_args("medium"),
                "-c:a", "copy", "-movflags", "+faststart",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                logger.info(f"yolo_reframe: single_crop OK — crop_x={crop_x}, crop_w={crop_w}")
                return {
                    "output_path": output_path,
                    "person_count": 1,
                    "masks_available": False,
                    "method": "yolo_single_crop",
                }
            if result.stderr:
                logger.warning(f"yolo_reframe: single_crop ffmpeg error: {result.stderr[-300:]}")
            return None

        # Split layout detected — use dynamic grid
        return self._render_dynamic_grid(
            original_path, output_path, orig_width, orig_height, orig_fps,
            frame_centers, left_cluster, right_cluster
        )

    # ─────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────

    def _clamp_crop_x(self, crop_x: int, crop_w: int, frame_width: int) -> int:
        """Clamp crop x position within frame bounds with safe-zone margin."""
        min_x = self.SAFE_ZONE_MARGIN
        max_x = frame_width - crop_w - self.SAFE_ZONE_MARGIN
        if max_x < min_x:
            return max(0, (frame_width - crop_w) // 2)
        return max(min_x, min(max_x, crop_x))

    # ─────────────────────────────────────────────────────────────────────
    # Render: dynamic grid (segment-based single/double switching)
    # ─────────────────────────────────────────────────────────────────────

    def _render_dynamic_grid(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        frame_centers: List[Tuple[int, List[Tuple[float, float]]]],
        left_cluster: SpeakerCluster,
        right_cluster: SpeakerCluster,
    ) -> Optional[dict]:
        """Dynamic segment-based grid: per 3-second segment, decide single or double.

        For segments with both speakers active → vstack grid (1080x960 each cell).
        For segments with one speaker dominant → single 9:16 crop on that speaker.
        setsar=1 on ALL outputs to prevent SAR concat errors.
        """
        import math

        # Determine total duration from frame_centers
        if not frame_centers:
            return None

        max_frame_idx = max(idx for idx, _ in frame_centers)
        total_duration = max_frame_idx / fps if fps > 0 else 0
        segment_count = max(1, int(math.ceil(total_duration / self.SEGMENT_DUR_SEC)))

        # Classify each segment: 'double' or 'single_left' or 'single_right'
        segment_frames_per_sec = fps * self.SEGMENT_DUR_SEC
        segments: List[str] = []  # 'double', 'single_left', 'single_right'

        midpoint = (left_cluster.center_x + right_cluster.center_x) / 2

        for seg_idx in range(segment_count):
            seg_start_frame = int(seg_idx * segment_frames_per_sec)
            seg_end_frame = int((seg_idx + 1) * segment_frames_per_sec)

            # Gather detections in this segment
            seg_left = 0
            seg_right = 0
            for frame_idx, dets in frame_centers:
                if seg_start_frame <= frame_idx < seg_end_frame:
                    for cx, _ in dets:
                        if cx < midpoint:
                            seg_left += 1
                        else:
                            seg_right += 1

            total_seg = seg_left + seg_right
            if total_seg == 0:
                # No detections — default to double
                segments.append("double")
            elif seg_left > 0 and seg_right > 0:
                # Both sides active
                segments.append("double")
            elif seg_left > 0:
                segments.append("single_left")
            else:
                segments.append("single_right")

        # Check if all segments are the same type for simpler render
        unique_types = set(segments)

        if unique_types == {"double"} or len(unique_types) > 1:
            # Use full grid for entire video (simplest reliable approach
            # when mixed or all-double). Dynamic concat per-segment is fragile
            # with variable-length segments, so we use grid for the whole clip.
            crop_w_double = min(int(height * 9 / 8), width)

            left_crop_x = int(left_cluster.center_x - crop_w_double / 2)
            left_crop_x = self._clamp_crop_x(left_crop_x, crop_w_double, width)

            right_crop_x = int(right_cluster.center_x - crop_w_double / 2)
            right_crop_x = self._clamp_crop_x(right_crop_x, crop_w_double, width)

            filter_complex = (
                f"[0:v]split=2[top][bot];"
                f"[top]crop={crop_w_double}:{height}:{left_crop_x}:0,scale=1080:960,setsar=1[t];"
                f"[bot]crop={crop_w_double}:{height}:{right_crop_x}:0,scale=1080:960,setsar=1[b];"
                f"[t][b]vstack=inputs=2,setsar=1[vout]"
            )

            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "0:a?",
                *get_video_encoder_args("medium"),
                "-c:a", "copy", "-movflags", "+faststart",
                output_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                logger.info(
                    f"yolo_reframe: dynamic_grid (double) OK — "
                    f"left_x={left_crop_x}, right_x={right_crop_x}, cell_w={crop_w_double}"
                )
                return {
                    "output_path": output_path,
                    "person_count": 2,
                    "masks_available": False,
                    "method": "yolo_dynamic_grid",
                }

            if result.stderr:
                logger.warning(f"yolo_reframe: dynamic_grid ffmpeg error: {result.stderr[-300:]}")
            return None

        # All segments single-speaker (rare but handle it)
        target_cluster = left_cluster if "single_left" in unique_types else right_cluster
        crop_w_single = min(int(height * 9 / 16), width)
        crop_x = int(target_cluster.center_x - crop_w_single / 2)
        crop_x = self._clamp_crop_x(crop_x, crop_w_single, width)

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"crop={crop_w_single}:{height}:{crop_x}:0,scale=1080:1920,setsar=1",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.info(
                f"yolo_reframe: dynamic_grid (single) OK — "
                f"crop_x={crop_x}, crop_w={crop_w_single}, speaker={'left' if 'single_left' in unique_types else 'right'}"
            )
            return {
                "output_path": output_path,
                "person_count": 1,
                "masks_available": False,
                "method": "yolo_dynamic_grid_single",
            }

        if result.stderr:
            logger.warning(f"yolo_reframe: dynamic_grid single ffmpeg error: {result.stderr[-300:]}")
        return None

    # ─────────────────────────────────────────────────────────────────────
    # Utility: H264 transcode for detection
    # ─────────────────────────────────────────────────────────────────────

    def _ensure_h264(self, video_path: str, transcode_path: str) -> str:
        """Transcode to H264 if video is AV1/VP9 (OpenCV can't decode reliably)."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path,
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
                    logger.info(f"yolo_reframe: transcoded {codec}->h264 for detection")
                    return transcode_path

            return video_path
        except Exception:
            return video_path

    # ─────────────────────────────────────────────────────────────────────
    # Utility: center crop fallback
    # ─────────────────────────────────────────────────────────────────────

    async def _center_crop_fallback(self, input_path: str, output_path: str, target_aspect: str) -> bool:
        """Simple center crop when YOLO unavailable or no persons found."""
        if target_aspect == "9:16":
            crop_filter = "crop=ih*9/16:ih,scale=1080:1920,setsar=1"
        elif target_aspect == "1:1":
            crop_filter = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080,setsar=1"
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
