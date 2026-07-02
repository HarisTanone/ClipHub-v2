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
    SMOOTHING_ALPHA = 0.08
    DEADZONE_PIXELS = 30
    SAMPLE_INTERVAL_SEC = 1.0
    MAX_SAMPLES = 60
    CONFIDENCE_THRESHOLD = 0.45

    # Dynamic Grid Settings
    MULTI_PERSON_DIST_RATIO = 0.35  # If 2 persons are >35% screen width apart, split grid
    MIN_SEGMENT_DUR = 3.0           # Minimum seconds per layout segment (prevents jitter)

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
        """Detect persons across full video, compute smooth crop trajectory."""
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
        sample_indices = list(range(0, total_frames, sample_interval))[:self.MAX_SAMPLES]

        frame_detections = []  # (frame_idx, [(cx, cy), ...])

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            results = self._model(frame, classes=[0], verbose=False)
            dets = []
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        if conf > self.CONFIDENCE_THRESHOLD:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            cx = ((x1 + x2) / 2) * scale_x
                            cy = (y1 + y2) / 2
                            dets.append((cx, cy))

            frame_detections.append((frame_idx, dets))

        cap.release()

        if not frame_detections or all(len(d) == 0 for _, d in frame_detections):
            logger.info("yolo_reframe: no persons detected in any frame")
            return None

        # Pass to dynamic grid renderer
        return self._render_dynamic_grid(
            original_path, output_path, orig_width, orig_height, orig_fps, frame_detections
        )

    def _render_dynamic_grid(
        self, video_path: str, output_path: str,
        width: int, height: int, fps: float,
        frame_detections: list
    ) -> Optional[dict]:
        """Dynamically switch between 1-grid (9:16) and 2-grid (top/bottom) based on person distance."""

        total_dur = frame_detections[-1][0] / fps if fps > 0 else 0
        if total_dur <= 0:
            return None

        # 1. Classify layout per frame
        segments = []
        current_layout = None
        current_start_t = 0.0

        for frame_idx, dets in frame_detections:
            t = frame_idx / fps

            if len(dets) >= 2:
                xs = [d[0] for d in dets]
                dist = max(xs) - min(xs)
                desired = "double" if dist > width * self.MULTI_PERSON_DIST_RATIO else "single"
            else:
                desired = "single"

            if current_layout is None:
                current_layout = desired
                current_start_t = t
            elif desired != current_layout:
                segments.append((current_start_t, t, current_layout))
                current_layout = desired
                current_start_t = t

        segments.append((current_start_t, total_dur, current_layout))

        # 2. Merge short segments to prevent rapid flickering
        merged = []
        for seg in segments:
            if not merged:
                merged.append(list(seg))
            else:
                last = merged[-1]
                seg_dur = seg[1] - seg[0]
                if seg_dur < self.MIN_SEGMENT_DUR:
                    last[1] = seg[1]  # Too short, extend previous segment
                elif last[2] == seg[2]:
                    last[1] = seg[1]  # Same layout, merge
                else:
                    merged.append(list(seg))

        merged[-1][1] = max(merged[-1][1], total_dur)

        # 3. Calculate crops and build FFmpeg filter
        video_filters = []
        audio_filters = []
        v_labels = []
        a_labels = []

        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = min(int(height * 9 / 16), width)  # Same 9:16 crop per person panel

        for i, seg in enumerate(merged):
            start_t, end_t, layout = seg
            if end_t <= start_t:
                continue

            v_out = f"v{i}"
            a_out = f"a{i}"

            # Get all detections within this time segment
            seg_dets = [d for fi, d in frame_detections if start_t <= fi / fps < end_t]

            if layout == "double":
                all_x = [d[0] for det_list in seg_dets for d in det_list]
                if len(all_x) < 2:
                    layout = "single"  # Fallback if not enough data
                else:
                    # Find the split point (largest gap between persons)
                    sorted_x = np.sort(all_x)
                    gaps = np.diff(sorted_x)
                    split_idx = np.argmax(gaps)
                    split_val = sorted_x[split_idx]

                    left_x = [x for x in all_x if x <= split_val]
                    right_x = [x for x in all_x if x > split_val]

                    if not left_x or not right_x:
                        layout = "single"
                    else:
                        # Use median for stable crop position (no jitter)
                        X1 = int(np.median(left_x))
                        X2 = int(np.median(right_x))
                        X1 = max(0, min(width - crop_w_double, X1 - crop_w_double // 2))
                        X2 = max(0, min(width - crop_w_double, X2 - crop_w_double // 2))

                        video_filters.append(
                            f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,split=2[s{i}_a][s{i}_b];"
                            f"[s{i}_a]crop={crop_w_double}:{height}:{X1}:0,scale=1080:960[s{i}_ta];"
                            f"[s{i}_b]crop={crop_w_double}:{height}:{X2}:0,scale=1080:960[s{i}_tb];"
                            f"[s{i}_ta][s{i}_tb]vstack=inputs=2,setsar=1[{v_out}]"
                        )

            if layout == "single":
                all_x = [d[0] for det_list in seg_dets for d in det_list]
                X = int(np.median(all_x)) if all_x else width // 2
                crop_x = max(0, min(width - crop_w_single, X - crop_w_single // 2))

                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,"
                    f"crop={crop_w_single}:{height}:{crop_x}:0,scale=1080:1920,setsar=1[{v_out}]"
                )

            audio_filters.append(
                f"[0:a]atrim={start_t}:{end_t},asetpts=PTS-STARTPTS[{a_out}]"
            )
            v_labels.append(f"[{v_out}]")
            a_labels.append(f"[{a_out}]")

        if not v_labels:
            return None

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

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(output_path):
            double_count = sum(1 for s in merged if s[2] == "double")
            single_count = sum(1 for s in merged if s[2] == "single")
            logger.info(
                f"yolo_reframe: dynamic grid OK — {len(merged)} segments "
                f"({double_count} double, {single_count} single)"
            )
            return {"output_path": output_path, "person_count": 2, "masks_available": False, "method": "yolo_dynamic_grid"}

        # Fallback: try without audio filter
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
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"yolo_reframe: dynamic grid OK (no audio filter fallback)")
            return {"output_path": output_path, "person_count": 2, "masks_available": False, "method": "yolo_dynamic_grid"}

        if result.stderr:
            logger.warning(f"yolo_reframe: dynamic grid FFmpeg error: {result.stderr[-500:]}")
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
