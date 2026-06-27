"""YoloReframeEngine — YOLO11 person detection + smart crop + autogrid.

Uses ultralytics YOLO11n for person detection:
- Single speaker: center crop on detected person
- Multi-speaker (autogrid): side-by-side split
- Fallback: center crop if no person detected
"""
import asyncio
import logging
import os
import shutil
import subprocess
from typing import Optional

from src.domain.interfaces import IYoloReframeEngine

logger = logging.getLogger(__name__)


class YoloReframeEngine(IYoloReframeEngine):
    """YOLO-based person-aware reframing for 9:16 clips."""

    def __init__(self, model_path: str = ""):
        self._model_path = model_path or "yolo11n.pt"
        self._model = None

    def _load_model(self):
        """Lazy-load YOLO model."""
        if self._model is not None:
            return True
        try:
            from ultralytics import YOLO
            self._model = YOLO(self._model_path)
            logger.info(f"yolo_reframe: model loaded ({self._model_path})")
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
        """Reframe video with person detection."""
        if not os.path.exists(video_path):
            logger.error(f"yolo_reframe: input not found {video_path}")
            return {"output_path": video_path, "person_count": 0, "masks_available": False}

        if target_aspect == "16:9":
            shutil.copy2(video_path, output_path)
            return {"output_path": output_path, "person_count": 0, "masks_available": False}

        # Try YOLO detection
        if self._load_model():
            try:
                result = await asyncio.to_thread(self._detect_and_crop, video_path, output_path, target_aspect, autogrid_enabled)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"yolo_reframe: detection failed, falling back: {e}")

        # Fallback: center crop
        success = await self._center_crop_fallback(video_path, output_path, target_aspect)
        return {
            "output_path": output_path if success else video_path,
            "person_count": 0,
            "masks_available": False,
            "method": "center_crop_fallback",
        }

    def _detect_and_crop(self, video_path: str, output_path: str, target_aspect: str, autogrid: bool) -> Optional[dict]:
        """Detect persons in first few frames to determine crop region."""
        import cv2
        import numpy as np

        # Transcode to H264 if needed (fixes AV1 decode issues with OpenCV)
        transcode_path = video_path.rsplit(".", 1)[0] + "_h264_temp.mp4"
        actual_path = self._ensure_h264(video_path, transcode_path)

        try:
            return self._detect_and_crop_impl(actual_path, video_path, output_path, target_aspect, autogrid)
        finally:
            # Cleanup transcode temp
            if actual_path != video_path and os.path.exists(transcode_path):
                os.remove(transcode_path)

    def _ensure_h264(self, video_path: str, transcode_path: str) -> str:
        """Transcode to H264 if video is AV1/VP9 (OpenCV can't decode reliably)."""
        try:
            # Check codec using ffprobe
            cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                   "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            codec = result.stdout.strip().lower()

            if codec in ("av1", "vp9", "vp8", "hevc"):
                # Transcode to H264 (fast, for detection only)
                cmd = [
                    "ffmpeg", "-y", "-i", video_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-an",  # No audio needed for detection
                    "-t", "15",  # Only first 15 seconds needed for sampling
                    transcode_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and os.path.exists(transcode_path):
                    logger.info(f"yolo_reframe: transcoded {codec}→h264 for detection")
                    return transcode_path

            return video_path
        except Exception:
            return video_path

    def _detect_and_crop_impl(self, detect_path: str, original_path: str, output_path: str, target_aspect: str, autogrid: bool) -> Optional[dict]:
        """Core detection logic using transcoded (or original) video."""
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(detect_path)
        if not cap.isOpened():
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Sample frames for detection (every 2 seconds, max 5 samples)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        sample_interval = int(fps * 2)
        sample_frames = list(range(0, min(total_frames, int(fps * 10)), sample_interval))[:5]

        all_person_boxes = []
        for frame_idx in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            results = self._model(frame, classes=[0], verbose=False)  # class 0 = person
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0])
                        if conf > 0.4:
                            all_person_boxes.append((x1, y1, x2, y2, conf))

        cap.release()

        if not all_person_boxes:
            logger.info("yolo_reframe: no persons detected, using center crop")
            return None

        # Calculate average person region
        boxes_array = np.array(all_person_boxes)

        # Get original video dimensions for crop (may differ from transcoded)
        orig_cap = cv2.VideoCapture(original_path)
        orig_width = int(orig_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(orig_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        orig_cap.release()

        # Scale detection coordinates if transcoded dimensions differ
        scale_x = orig_width / width if width > 0 else 1.0
        scale_y = orig_height / height if height > 0 else 1.0

        # Determine crop based on single vs multi speaker
        if autogrid and len(all_person_boxes) >= 4:
            return self._render_autogrid(original_path, output_path, orig_width, orig_height, boxes_array * scale_x)
        else:
            # Single speaker — crop around person center
            avg_center_x = np.mean((boxes_array[:, 0] + boxes_array[:, 2]) / 2) * scale_x

            # Target crop width for 9:16
            crop_w = int(orig_height * 9 / 16)
            crop_x = int(max(0, min(orig_width - crop_w, avg_center_x - crop_w / 2)))

            crop_filter = f"crop={crop_w}:{orig_height}:{crop_x}:0,scale=1080:1920"
            cmd = [
                "ffmpeg", "-y", "-i", original_path,
                "-vf", crop_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "copy", "-movflags", "+faststart",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"yolo_reframe: person-centered crop (center_x={avg_center_x:.0f}, crop_x={crop_x})")
                return {"output_path": output_path, "person_count": 1, "masks_available": False, "method": "yolo_person_center"}

        return None

    def _render_autogrid(self, video_path: str, output_path: str, width: int, height: int, boxes: "np.ndarray") -> Optional[dict]:
        """Render side-by-side grid for multiple speakers."""
        import numpy as np

        # Find 2 most prominent person regions (leftmost and rightmost)
        centers_x = (boxes[:, 0] + boxes[:, 2]) / 2
        left_mask = centers_x < width / 2
        right_mask = centers_x >= width / 2

        if not np.any(left_mask) or not np.any(right_mask):
            return None

        # Crop left person and right person, stack vertically
        left_center = np.mean(centers_x[left_mask])
        right_center = np.mean(centers_x[right_mask])

        crop_w = int(height * 9 / 16)  # width for 9:16 from full height
        half_h = height // 2

        # Top half: left speaker, Bottom half: right speaker
        left_x = int(max(0, min(width - crop_w, left_center - crop_w / 2)))
        right_x = int(max(0, min(width - crop_w, right_center - crop_w / 2)))

        filter_complex = (
            f"[0:v]split=2[top][bot];"
            f"[top]crop={crop_w}:{height}:{left_x}:0,scale=1080:{half_h}[t];"
            f"[bot]crop={crop_w}:{height}:{right_x}:0,scale=1080:{half_h}[b];"
            f"[t][b]vstack=inputs=2[v]"
        )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info("yolo_reframe: autogrid (2 speakers stacked)")
            return {"output_path": output_path, "person_count": 2, "masks_available": False, "method": "autogrid"}
        return None

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
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        # Cleanup failed output
        if os.path.exists(output_path):
            os.remove(output_path)
        return False
