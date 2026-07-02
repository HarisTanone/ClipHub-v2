"""YoloReframeEngine — YOLO11 person detection + smooth tracking crop.

Professional video editor approach:
- Samples frames throughout entire clip (not just first 10s)
- Smooth exponential moving average (EMA) for crop position
- Auto-detects single vs multi speaker
- Generates smooth pan that follows the active speaker
- Avoids jitter with deadzone (only moves if person moves significantly)
"""
import asyncio
import logging
import os
import shutil
import subprocess
from typing import Optional

import numpy as np

from src.domain.interfaces import IYoloReframeEngine
from src.infrastructure.gpu_encoder import get_video_encoder_args

logger = logging.getLogger(__name__)


class YoloReframeEngine(IYoloReframeEngine):
    """YOLO-based person-aware reframing with smooth tracking."""

    # Tuning constants (professional editor settings)
    SMOOTHING_ALPHA = 0.08  # EMA smoothing (lower = smoother, 0.05-0.15 range)
    DEADZONE_PIXELS = 30    # Don't move crop unless person moves > this many pixels
    SAMPLE_INTERVAL_SEC = 1.0  # Sample every 1 second
    MAX_SAMPLES = 60        # Max frames to analyze (60 = covers 60s of video)
    CONFIDENCE_THRESHOLD = 0.45  # Person detection confidence
    MULTI_SPEAKER_THRESHOLD = 0.35  # Lowered: podcast often has intermittent 2-person detection
    MIN_MULTI_SPEAKER_FRAMES = 3  # Minimum absolute frames with 2+ persons to trigger grid

    def __init__(self, model_path: str = ""):
        self._model_path = model_path or "yolo11n.pt"
        self._model = None

    def _load_model(self):
        """Lazy-load YOLO model (GPU if available)."""
        if self._model is not None:
            return True
        try:
            from ultralytics import YOLO
            self._model = YOLO(self._model_path)
            # Force GPU if available
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

    async def process(
        self,
        video_path: str,
        output_path: str,
        target_aspect: str = "9:16",
        autogrid_enabled: bool = False,
    ) -> dict:
        """Reframe video with smooth person tracking."""
        if not os.path.exists(video_path):
            logger.error(f"yolo_reframe: input not found {video_path}")
            return {"output_path": video_path, "person_count": 0, "masks_available": False}

        if target_aspect != "9:16":
            # YOLO + autogrid only for 9:16 portrait. Others: simple passthrough or center crop.
            if target_aspect == "1:1":
                success = await self._center_crop_fallback(video_path, output_path, target_aspect)
                return {"output_path": output_path if success else video_path, "person_count": 0, "masks_available": False}
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

        # Fallback: center crop
        success = await self._center_crop_fallback(video_path, output_path, target_aspect)
        return {
            "output_path": output_path if success else video_path,
            "person_count": 0,
            "masks_available": False,
            "method": "center_crop_fallback",
        }

    def _smooth_track_and_crop(
        self, video_path: str, output_path: str, target_aspect: str, autogrid: bool
    ) -> Optional[dict]:
        """Core tracking: detect persons throughout video, generate smooth crop."""
        import cv2

        # Ensure H264 for OpenCV compatibility
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
        """Detect persons across full video, compute smooth crop trajectory."""
        import cv2

        cap = cv2.VideoCapture(detect_path)
        if not cap.isOpened():
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        # Get original video dimensions (may differ from transcoded)
        orig_cap = cv2.VideoCapture(original_path)
        orig_width = int(orig_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(orig_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        orig_fps = orig_cap.get(cv2.CAP_PROP_FPS) or 30
        orig_cap.release()

        scale_x = orig_width / width if width > 0 else 1.0

        # Sample frames evenly throughout the entire clip
        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

        # Collect person centers per sample frame
        frame_centers = []  # list of (frame_idx, [center_x1, center_x2, ...])
        multi_speaker_count = 0

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            results = self._model(frame, classes=[0], verbose=False)
            centers = []
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        if conf > self.CONFIDENCE_THRESHOLD:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            cx = ((x1 + x2) / 2) * scale_x
                            centers.append(cx)

            if len(centers) >= 2:
                multi_speaker_count += 1

            frame_centers.append((frame_idx, centers))

        cap.release()

        if not frame_centers or all(len(c) == 0 for _, c in frame_centers):
            logger.info("yolo_reframe: no persons detected in any frame")
            return None

        # Determine mode: single speaker vs multi-speaker (dual trigger)
        total_with_detection = sum(1 for _, c in frame_centers if len(c) > 0)
        multi_ratio = multi_speaker_count / max(1, total_with_detection)
        is_multi_speaker = (
            multi_ratio >= self.MULTI_SPEAKER_THRESHOLD
            or multi_speaker_count >= self.MIN_MULTI_SPEAKER_FRAMES
        )

        logger.info(
            f"yolo_reframe: {len(frame_centers)} samples, "
            f"multi_speaker_count={multi_speaker_count}, "
            f"multi_ratio={multi_ratio:.2f}, "
            f"is_multi_speaker={is_multi_speaker}"
        )

        logger.info(
            f"yolo_reframe: autogrid_param={autogrid} (type={type(autogrid).__name__}), "
            f"multi_speaker_count={multi_speaker_count}, threshold={self.MIN_MULTI_SPEAKER_FRAMES}"
        )
        if is_multi_speaker and multi_speaker_count >= self.MIN_MULTI_SPEAKER_FRAMES:
            # Multi-speaker: always try autogrid first (no frontend toggle needed)
            grid_result = self._render_autogrid_smooth(
                original_path, output_path, orig_width, orig_height, frame_centers
            )
            if grid_result:
                return grid_result
            # If autogrid failed (speakers too close, etc.) → try union crop
            return self._render_union_crop(
                original_path, output_path, orig_width, orig_height, frame_centers, target_aspect
            )

        # Single speaker: smooth tracking crop
        return self._render_smooth_crop(
            original_path, output_path, orig_width, orig_height, orig_fps, frame_centers, target_aspect
        )

    def _render_union_crop(
        self, video_path: str, output_path: str,
        width: int, height: int,
        frame_centers: list, target_aspect: str,
    ) -> Optional[dict]:
        """Union bbox crop for multi-speaker: crop includes ALL detected persons.

        Strategy:
        - Compute union bounding box of all persons across sampled frames
        - If union is too wide (>80% frame) → skip reframe (safer)
        - Otherwise → crop to union center with generous padding
        """
        import cv2

        # Re-detect to get actual bounding boxes (not just centers)
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

        all_x1 = []
        all_x2 = []

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            results = self._model(frame, classes=[0], verbose=False)
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        if conf > self.CONFIDENCE_THRESHOLD:
                            x1, _, x2, _ = box.xyxy[0].cpu().numpy()
                            all_x1.append(float(x1))
                            all_x2.append(float(x2))

        cap.release()

        if not all_x1:
            logger.info("yolo_reframe: union_crop — no valid detections")
            return None

        # Compute union bbox (average of extremes for stability)
        union_x1 = np.percentile(all_x1, 10)  # 10th percentile (ignore outliers)
        union_x2 = np.percentile(all_x2, 90)  # 90th percentile
        union_w = union_x2 - union_x1
        union_ratio = union_w / width

        UNION_WIDTH_MAX_RATIO = 0.80
        PADDING_RATIO = 0.15

        if union_ratio > UNION_WIDTH_MAX_RATIO:
            # Speakers too far apart — switch to 2-grid layout automatically
            logger.info(
                f"yolo_reframe: union too wide ({union_ratio:.0%}) → auto-switching to 2-grid"
            )
            return self._render_autogrid_smooth(
                video_path, output_path, width, height, frame_centers
            )

        # Calculate crop dimensions (target 9:16)
        target_crop_w = int(height * 9 / 16)
        union_center = (union_x1 + union_x2) / 2

        # Add padding to union
        padded_w = int(union_w * (1 + 2 * PADDING_RATIO))
        crop_w = max(target_crop_w, padded_w)  # At least target width, or padded union
        crop_w = min(crop_w, width)  # Don't exceed frame

        # Center crop on union center
        crop_x = int(max(0, min(width - crop_w, union_center - crop_w / 2)))

        crop_filter = f"crop={crop_w}:{height}:{crop_x}:0,scale=1080:1920"
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", crop_filter,
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(
                f"yolo_reframe: union_crop OK — union_ratio={union_ratio:.0%}, "
                f"crop_w={crop_w}, crop_x={crop_x}, center={union_center:.0f}"
            )
            return {"output_path": output_path, "person_count": 2, "masks_available": False, "method": "yolo_union_crop"}
        return None

    def _render_smooth_crop(
        self, video_path: str, output_path: str,
        width: int, height: int, fps: float,
        frame_centers: list, target_aspect: str,
    ) -> Optional[dict]:
        """Render with smooth EMA-tracked crop position."""
        # Target crop width for 9:16
        crop_w = int(height * 9 / 16)
        max_crop_x = width - crop_w

        # Build smooth trajectory using EMA
        # Start from first detected person (not center) for immediate lock-on
        smooth_x = None
        for _, centers in frame_centers:
            if centers:
                smooth_x = centers[0]
                break
        if smooth_x is None:
            smooth_x = width / 2.0
        crop_positions = []  # (frame_idx, crop_x)

        for frame_idx, centers in frame_centers:
            if centers:
                # Use the most prominent person (closest to current smooth_x for stability)
                target_x = min(centers, key=lambda cx: abs(cx - smooth_x))

                # Deadzone: only update if movement exceeds threshold
                if abs(target_x - smooth_x) > self.DEADZONE_PIXELS:
                    smooth_x += (target_x - smooth_x) * self.SMOOTHING_ALPHA
            # else: keep previous position (person temporarily not visible)

            crop_x = int(max(0, min(max_crop_x, smooth_x - crop_w / 2)))
            crop_positions.append((frame_idx, crop_x))

        if not crop_positions:
            return None

        # Check if crop position is mostly static (within 50px range)
        crop_xs = [pos for _, pos in crop_positions]
        crop_range = max(crop_xs) - min(crop_xs)

        if crop_range < 50:
            # Static crop — use median (not mean) to avoid empty-center for 2-person content
            avg_crop_x = int(np.median(crop_xs))
            crop_filter = f"crop={crop_w}:{height}:{avg_crop_x}:0,scale=1080:1920"
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vf", crop_filter,
                *get_video_encoder_args("medium"),
                "-c:a", "copy", "-movflags", "+faststart",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"yolo_reframe: static person-center crop (x={avg_crop_x}, range={crop_range}px)")
                return {"output_path": output_path, "person_count": 1, "masks_available": False, "method": "yolo_static_center"}
            return None
        else:
            # Dynamic tracking — generate crop keyframes using sendcmd
            # Use zoompan filter with smooth keyframes for professional-looking pan
            # Simplification: interpolate between sampled crop positions

            # For FFmpeg, use a smooth pan via crop with expression
            # Calculate initial and average crop X for a gentle pan
            start_x = crop_positions[0][1]
            end_x = crop_positions[-1][1]
            mid_x = int(np.median(crop_xs))  # Median avoids empty-center for 2-person content

            # Smooth pan: start → middle (gentle, professional look)
            # Use linear interpolation over time via FFmpeg expression
            total_dur = crop_positions[-1][0] / fps if fps > 0 else 30

            # Expression: smoothly pan from start_x to mid_x over first 3s, then stay
            # This avoids jerky movement — single smooth motion then stable
            # Minimum 3s pan for smooth transition (user requirement: no fast perpindahan)
            pan_duration = max(3.0, total_dur * 0.3)  # Minimum 3s, no maximum cap

            # Ease-out cubic: starts fast, decelerates smoothly
            # Formula: start + (end-start) * (1 - (1 - t/dur)^3)
            # In FFmpeg expression syntax:
            crop_expr = (
                f"if(lt(t,{pan_duration}),"
                f"{start_x}+({mid_x}-{start_x})*(1-pow(1-t/{pan_duration},3)),"
                f"{mid_x})"
            )

            crop_filter = f"crop={crop_w}:{height}:'{crop_expr}':0,scale=1080:1920"
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vf", crop_filter,
                *get_video_encoder_args("medium"),
                "-c:a", "copy", "-movflags", "+faststart",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"yolo_reframe: smooth tracking pan ({start_x}→{mid_x}, range={crop_range}px, pan={pan_duration:.1f}s)")
                return {"output_path": output_path, "person_count": 1, "masks_available": False, "method": "yolo_smooth_track"}
            return None

    def _render_autogrid_smooth(
        self, video_path: str, output_path: str,
        width: int, height: int,
        frame_centers: list,
    ) -> Optional[dict]:
        """Render dynamic split-grid: first 4s = normal crop, then split when 2+ persons.
        
        Design principles:
        - First 4 seconds: NO split grid (hook period, show full frame)
        - After 4s: split ONLY if 2+ persons clearly separated in frame
        - Each grid shows a DIFFERENT person (left vs right of frame)
        - Dynamic: number of grids based on detected persons
        """
        import cv2

        # Get video FPS for time-based gating
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        
        # Only use frames AFTER 4 seconds for person detection (skip hook period)
        min_frame_for_grid = int(fps * 4.0)
        
        # Collect centers ONLY from frames after 4s
        post_hook_centers = []
        for frame_idx, centers in frame_centers:
            if frame_idx >= min_frame_for_grid and len(centers) >= 2:
                post_hook_centers.extend(centers)

        if len(post_hook_centers) < 3:
            logger.info(f"yolo_reframe: too few multi-person centers after 4s ({len(post_hook_centers)}), skipping grid")
            return None

        centers_array = np.array(post_hook_centers)

        # Use simple 2-cluster split: sort centers, find the largest gap
        sorted_centers = np.sort(centers_array)
        gaps = np.diff(sorted_centers)
        if len(gaps) == 0:
            return None

        # Find the biggest gap between consecutive centers — that's where to split
        split_idx = np.argmax(gaps)
        left_centers = sorted_centers[:split_idx + 1]
        right_centers = sorted_centers[split_idx + 1:]

        if len(left_centers) < 1 or len(right_centers) < 1:
            return None

        left_avg = np.mean(left_centers)
        right_avg = np.mean(right_centers)

        # Minimum separation: 10% of frame width (lowered from 20%)
        min_separation = width * 0.10
        if abs(right_avg - left_avg) < min_separation:
            logger.info(f"yolo_reframe: speakers too close ({abs(right_avg - left_avg):.0f}px < {min_separation:.0f}px), skipping grid")
            return None

        # Each speaker crop dimensions
        crop_w_person = int(height * 9 / 16)
        half_h = 960  # Each speaker gets 1080x960 in output

        left_x = int(max(0, min(width - crop_w_person, left_avg - crop_w_person / 2)))
        right_x = int(max(0, min(width - crop_w_person, right_avg - crop_w_person / 2)))

        # Verify crops don't overlap
        if abs(left_x - right_x) < crop_w_person * 0.3:
            logger.info(f"yolo_reframe: grid crops overlap too much, skipping")
            return None

        # Time-gated filter: first 4s shows prominent speaker, then switches to split grid
        grid_start_time = 4.0
        total_duration = total_frames / fps if fps > 0 else 60

        # Show the speaker with MORE detections during hook (not center between them)
        if len(left_centers) >= len(right_centers):
            primary_x = left_x
        else:
            primary_x = right_x
        primary_x = max(0, min(width - crop_w_person, primary_x))

        # Complex filter: trim into 2 parts, process differently, then concat
        filter_complex = (
            # Part 1: First 4s — normal center crop (1080x1920)
            f"[0:v]trim=0:{grid_start_time},setpts=PTS-STARTPTS,"
            f"crop={crop_w_person}:{height}:{primary_x}:0,scale=1080:1920[v1];"
            # Part 2: After 4s — split grid (2 speakers stacked)
            f"[0:v]trim={grid_start_time},setpts=PTS-STARTPTS,split=2[top][bot];"
            f"[top]crop={crop_w_person}:{height}:{left_x}:0,scale=1080:{half_h}[t];"
            f"[bot]crop={crop_w_person}:{height}:{right_x}:0,scale=1080:{half_h}[b];"
            f"[t][b]vstack=inputs=2[v2];"
            # Concat part1 + part2
            f"[v1][v2]concat=n=2:v=1:a=0[v]"
        )

        # Audio: also split and concat to keep sync
        audio_filter = (
            f"[0:a]atrim=0:{grid_start_time},asetpts=PTS-STARTPTS[a1];"
            f"[0:a]atrim={grid_start_time},asetpts=PTS-STARTPTS[a2];"
            f"[a1][a2]concat=n=2:v=0:a=1[a]"
        )

        full_filter = f"{filter_complex};{audio_filter}"

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", full_filter,
            "-map", "[v]", "-map", "[a]",
            *get_video_encoder_args("medium"),
            "-c:a", "aac", "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(
                f"yolo_reframe: autogrid 2-speaker (left_x={left_x}, right_x={right_x}, "
                f"grid_after={grid_start_time}s, separation={abs(right_avg - left_avg):.0f}px)"
            )
            return {"output_path": output_path, "person_count": 2, "masks_available": False, "method": "autogrid_timed"}
        
        # Fallback: try without audio filter (in case audio stream missing)
        cmd_no_audio = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd_no_audio, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"yolo_reframe: autogrid 2-speaker (no audio filter fallback)")
            return {"output_path": output_path, "person_count": 2, "masks_available": False, "method": "autogrid_timed"}
        return None

    def _ensure_h264(self, video_path: str, transcode_path: str) -> str:
        """Transcode to H264 if video is AV1/VP9 (OpenCV can't decode reliably)."""
        try:
            cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                   "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path]
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
                    logger.info(f"yolo_reframe: transcoded {codec}→h264 for detection")
                    return transcode_path

            return video_path
        except Exception:
            return video_path

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
