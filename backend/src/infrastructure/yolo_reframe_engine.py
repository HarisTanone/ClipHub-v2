"""YoloReframeEngine — YOLO11 person detection + cluster-based speaker reframing.

Root-cause fix for empty-background crops:
1. _analyze_speaker_layout() pools ALL centers across timeline (no same-frame
   co-occurrence required), uses gap-based clustering with support ratio +
   separation ratio thresholds.
2. _render_smooth_crop() anchors tracking to dominant speaker cluster (not
   current crop position), adds coverage safety check.
3. _render_autogrid_smooth() grid cell crop width matches actual cell aspect
   ratio (9:8 for 1080x960), prevents face distortion.
4. _clamp_crop_x() shared helper with safe-zone margin.
5. Fallback chain: autogrid → union_crop → smooth_crop → union_crop.

Key thresholds:
- MIN_CLUSTER_SUPPORT = 0.15 (each side needs 15% of detections)
- MIN_SEPARATION_RATIO = 0.25 (speakers 25% frame width apart)
- MIN_SMOOTH_CROP_COVERAGE = 0.5 (crop must contain person 50% of time)
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


@dataclass
class LayoutAnalysis:
    """Result of speaker layout analysis."""

    is_split: bool  # True = two-speaker split layout
    clusters: List[SpeakerCluster]
    all_centers_x: np.ndarray  # all x centers pooled


class YoloReframeEngine(IYoloReframeEngine):
    """YOLO-based person-aware reframing with cluster-based speaker detection."""

    # Sampling
    SAMPLE_INTERVAL_SEC = 1.0
    MAX_SAMPLES = 60
    CONFIDENCE_THRESHOLD = 0.45

    # Clustering thresholds
    MIN_CLUSTER_SUPPORT = 0.15  # each cluster needs 15% of detections
    MIN_SEPARATION_RATIO = 0.25  # clusters must be 25% frame width apart

    # Smooth tracking
    SMOOTHING_ALPHA = 0.08
    DEADZONE_PIXELS = 30
    MIN_SMOOTH_CROP_COVERAGE = 0.5  # crop must contain person 50% of time

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
        autogrid_enabled: bool = False,
    ) -> dict:
        """Reframe video with cluster-based person tracking."""
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
                    self._smooth_track_and_crop, video_path, output_path, target_aspect, autogrid_enabled
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
        self, video_path: str, output_path: str, target_aspect: str, autogrid: bool
    ) -> Optional[dict]:
        """Main pipeline: detect → analyze layout → render."""
        import cv2

        transcode_path = video_path.rsplit(".", 1)[0] + "_h264_temp.mp4"
        detect_path = self._ensure_h264(video_path, transcode_path)

        try:
            return self._track_impl(detect_path, video_path, output_path, target_aspect, autogrid)
        finally:
            if detect_path != video_path and os.path.exists(transcode_path):
                os.remove(transcode_path)

    def _track_impl(
        self, detect_path: str, original_path: str, output_path: str, target_aspect: str, autogrid: bool
    ) -> Optional[dict]:
        """Detect persons, analyze speaker layout, render appropriate crop."""
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
                            x1, _, x2, _ = box.xyxy[0].cpu().numpy()
                            cx = ((x1 + x2) / 2) * scale_x
                            cy = float(box.xyxy[0].cpu().numpy()[1] + box.xyxy[0].cpu().numpy()[3]) / 2
                            dets.append((cx, cy))

            frame_centers.append((frame_idx, dets))

        cap.release()

        # Check if we have any detections at all
        if not frame_centers or all(len(d) == 0 for _, d in frame_centers):
            logger.info("yolo_reframe: no persons detected in any frame")
            return None

        # Analyze speaker layout using ALL pooled centers
        layout = self._analyze_speaker_layout(frame_centers, orig_width)

        # Render based on layout
        if layout.is_split and autogrid:
            # Try autogrid first for split layout
            result = self._render_autogrid_smooth(
                original_path, output_path, orig_width, orig_height, orig_fps,
                frame_centers, layout
            )
            if result:
                return result
            logger.info("yolo_reframe: autogrid failed, trying union_crop")

        if layout.is_split:
            # Two speakers but autogrid disabled or failed — union crop
            result = self._render_union_crop(
                original_path, output_path, orig_width, orig_height, layout
            )
            if result:
                return result
            logger.info("yolo_reframe: union_crop failed, trying smooth_crop")

        # Single speaker or fallback — smooth tracking crop
        result = self._render_smooth_crop(
            original_path, output_path, orig_width, orig_height, orig_fps,
            frame_centers, layout
        )
        if result:
            return result

        # Final fallback — union crop (even for single speaker)
        logger.info("yolo_reframe: smooth_crop failed, final union_crop fallback")
        return self._render_union_crop(
            original_path, output_path, orig_width, orig_height, layout
        )

    # ─────────────────────────────────────────────────────────────────────
    # Speaker layout analysis (cluster-based)
    # ─────────────────────────────────────────────────────────────────────

    def _analyze_speaker_layout(
        self,
        frame_centers: List[Tuple[int, List[Tuple[float, float]]]],
        frame_width: int,
    ) -> LayoutAnalysis:
        """Pool ALL x-centers across timeline, cluster by gap analysis.

        Does NOT require same-frame co-occurrence. A single person switching
        between left and right positions will be detected as two clusters if
        the gap is large enough and both sides have sufficient support.
        """
        # Pool all x-centers from all frames
        all_cx: List[float] = []
        for _, centers in frame_centers:
            for cx, _ in centers:
                all_cx.append(cx)

        if not all_cx:
            return LayoutAnalysis(is_split=False, clusters=[], all_centers_x=np.array([]))

        all_cx_arr = np.array(all_cx)
        sorted_cx = np.sort(all_cx_arr)

        # Gap-based clustering: find largest gap
        if len(sorted_cx) < 4:
            # Too few detections for reliable clustering
            cluster = SpeakerCluster(
                center_x=float(np.median(sorted_cx)),
                support=1.0,
                x_min=float(sorted_cx[0]),
                x_max=float(sorted_cx[-1]),
            )
            return LayoutAnalysis(is_split=False, clusters=[cluster], all_centers_x=all_cx_arr)

        gaps = np.diff(sorted_cx)
        max_gap_idx = int(np.argmax(gaps))
        max_gap = gaps[max_gap_idx]

        # Check separation ratio
        separation_ratio = max_gap / frame_width

        # Split into two candidate clusters
        left_points = sorted_cx[: max_gap_idx + 1]
        right_points = sorted_cx[max_gap_idx + 1 :]

        left_support = len(left_points) / len(sorted_cx)
        right_support = len(right_points) / len(sorted_cx)

        # Decide if this is a genuine two-speaker split
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
            clusters = [left_cluster, right_cluster]
            logger.info(
                f"yolo_reframe: TWO speakers detected — "
                f"left={left_cluster.center_x:.0f} ({left_support:.0%}), "
                f"right={right_cluster.center_x:.0f} ({right_support:.0%}), "
                f"separation={separation_ratio:.0%}"
            )
        else:
            cluster = SpeakerCluster(
                center_x=float(np.median(sorted_cx)),
                support=1.0,
                x_min=float(sorted_cx[0]),
                x_max=float(sorted_cx[-1]),
            )
            clusters = [cluster]
            logger.info(
                f"yolo_reframe: SINGLE speaker — "
                f"center={cluster.center_x:.0f}, "
                f"gap_ratio={separation_ratio:.0%} (threshold={self.MIN_SEPARATION_RATIO:.0%})"
            )

        return LayoutAnalysis(is_split=is_split, clusters=clusters, all_centers_x=all_cx_arr)

    # ─────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────

    def _clamp_crop_x(self, crop_x: int, crop_w: int, frame_width: int) -> int:
        """Clamp crop x position within frame bounds with safe-zone margin."""
        min_x = self.SAFE_ZONE_MARGIN
        max_x = frame_width - crop_w - self.SAFE_ZONE_MARGIN
        if max_x < min_x:
            # Crop wider than frame minus margins — just center it
            return max(0, (frame_width - crop_w) // 2)
        return max(min_x, min(max_x, crop_x))

    # ─────────────────────────────────────────────────────────────────────
    # Render: union crop (both speakers in single wide crop)
    # ─────────────────────────────────────────────────────────────────────

    def _render_union_crop(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        layout: LayoutAnalysis,
    ) -> Optional[dict]:
        """Crop a 9:16 region that covers all speaker clusters."""
        crop_w = min(int(height * 9 / 16), width)

        if layout.clusters:
            # Center crop on the midpoint between all clusters
            all_center = float(np.mean([c.center_x for c in layout.clusters]))
        else:
            all_center = width / 2

        crop_x = int(all_center - crop_w / 2)
        crop_x = self._clamp_crop_x(crop_x, crop_w, width)

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"crop={crop_w}:{height}:{crop_x}:0,scale=1080:1920,setsar=1",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            person_count = len(layout.clusters)
            logger.info(f"yolo_reframe: union_crop OK — crop_x={crop_x}, crop_w={crop_w}")
            return {
                "output_path": output_path,
                "person_count": person_count,
                "masks_available": False,
                "method": "yolo_union_crop",
            }

        if result.stderr:
            logger.warning(f"yolo_reframe: union_crop ffmpeg error: {result.stderr[-300:]}")
        return None

    # ─────────────────────────────────────────────────────────────────────
    # Render: smooth single-speaker crop (EMA tracking)
    # ─────────────────────────────────────────────────────────────────────

    def _render_smooth_crop(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        frame_centers: List[Tuple[int, List[Tuple[float, float]]]],
        layout: LayoutAnalysis,
    ) -> Optional[dict]:
        """Smooth EMA-tracked crop anchored to dominant speaker cluster.

        Coverage safety: if the crop contains a person in < MIN_SMOOTH_CROP_COVERAGE
        of sampled frames, this method returns None (caller should use union_crop).
        """
        crop_w = min(int(height * 9 / 16), width)

        # Determine anchor (dominant cluster center)
        if layout.clusters:
            dominant = max(layout.clusters, key=lambda c: c.support)
            anchor_x = dominant.center_x
        else:
            anchor_x = width / 2

        # Build per-frame target x using EMA
        current_x = anchor_x
        crop_positions: List[Tuple[int, int]] = []  # (frame_idx, crop_x)
        covered_frames = 0
        total_frames_with_dets = 0

        for frame_idx, dets in frame_centers:
            if dets:
                total_frames_with_dets += 1
                # Find closest detection to current anchor
                closest_cx = min(dets, key=lambda d: abs(d[0] - current_x))[0]

                # Deadzone: only update if movement exceeds threshold
                if abs(closest_cx - current_x) > self.DEADZONE_PIXELS:
                    current_x = current_x + self.SMOOTHING_ALPHA * (closest_cx - current_x)

                # Check if detection falls within crop
                crop_x = int(current_x - crop_w / 2)
                crop_x = self._clamp_crop_x(crop_x, crop_w, width)
                if any(crop_x <= cx <= crop_x + crop_w for cx, _ in dets):
                    covered_frames += 1
            else:
                crop_x = int(current_x - crop_w / 2)
                crop_x = self._clamp_crop_x(crop_x, crop_w, width)

            crop_positions.append((frame_idx, crop_x))

        # Coverage safety check
        if total_frames_with_dets > 0:
            coverage = covered_frames / total_frames_with_dets
            if coverage < self.MIN_SMOOTH_CROP_COVERAGE:
                logger.warning(
                    f"yolo_reframe: smooth_crop coverage too low ({coverage:.0%} < "
                    f"{self.MIN_SMOOTH_CROP_COVERAGE:.0%}), rejecting"
                )
                return None

        # Use median crop position for static crop (most stable)
        if crop_positions:
            median_crop_x = int(np.median([pos for _, pos in crop_positions]))
        else:
            median_crop_x = self._clamp_crop_x(int(anchor_x - crop_w / 2), crop_w, width)

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"crop={crop_w}:{height}:{median_crop_x}:0,scale=1080:1920,setsar=1",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.info(
                f"yolo_reframe: smooth_crop OK — crop_x={median_crop_x}, "
                f"coverage={covered_frames}/{total_frames_with_dets}"
            )
            return {
                "output_path": output_path,
                "person_count": 1,
                "masks_available": False,
                "method": "yolo_smooth_crop",
            }

        if result.stderr:
            logger.warning(f"yolo_reframe: smooth_crop ffmpeg error: {result.stderr[-300:]}")
        return None

    # ─────────────────────────────────────────────────────────────────────
    # Render: autogrid smooth (top/bottom split for two speakers)
    # ─────────────────────────────────────────────────────────────────────

    def _render_autogrid_smooth(
        self,
        video_path: str,
        output_path: str,
        width: int,
        height: int,
        fps: float,
        frame_centers: List[Tuple[int, List[Tuple[float, float]]]],
        layout: LayoutAnalysis,
    ) -> Optional[dict]:
        """Two-speaker grid: each speaker gets a 1080x960 cell (9:8 aspect).

        Grid cell crop width matches the actual cell aspect ratio:
        - Output cell: 1080x960 → aspect 9:8
        - Source crop per cell: height * 9/8 wide (NOT 9/16)
        This prevents face distortion from incorrect aspect ratio scaling.
        """
        if len(layout.clusters) < 2:
            return None

        # Each grid cell is 1080x960 → aspect ratio 9:8
        # Source crop per cell: full height, width = height * 9 / 8
        cell_crop_w = min(int(height * 9 / 8), width)

        left_cluster = layout.clusters[0]
        right_cluster = layout.clusters[1]

        # Compute crop x for each speaker (centered on cluster median)
        left_crop_x = int(left_cluster.center_x - cell_crop_w / 2)
        left_crop_x = self._clamp_crop_x(left_crop_x, cell_crop_w, width)

        right_crop_x = int(right_cluster.center_x - cell_crop_w / 2)
        right_crop_x = self._clamp_crop_x(right_crop_x, cell_crop_w, width)

        # FFmpeg filter: crop each speaker, scale to 1080x960, vstack
        filter_complex = (
            f"[0:v]split=2[top][bot];"
            f"[top]crop={cell_crop_w}:{height}:{left_crop_x}:0,scale=1080:960[t];"
            f"[bot]crop={cell_crop_w}:{height}:{right_crop_x}:0,scale=1080:960[b];"
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
                f"yolo_reframe: autogrid_smooth OK — "
                f"left_x={left_crop_x}, right_x={right_crop_x}, cell_w={cell_crop_w}"
            )
            return {
                "output_path": output_path,
                "person_count": 2,
                "masks_available": False,
                "method": "yolo_autogrid_smooth",
            }

        if result.stderr:
            logger.warning(f"yolo_reframe: autogrid ffmpeg error: {result.stderr[-300:]}")
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
            crop_filter = "crop=ih*9/16:ih,scale=1080:1920"
        elif target_aspect == "1:1":
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
