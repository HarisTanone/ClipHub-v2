"""YoloReframeEngine — MediaPipe Face Detection + Dynamic Segment-Based Grid.

Fixes:
- Replaced YOLO with MediaPipe Face Detection (Opsi A).
- Prevents false positives on action figures/humanoids/toys on podcast desks.
- Eliminates PyTorch/OpenCV glibc thread deadlock (Fatal glibc error).
- Dynamic Segment-Based Grid: Auto switches 1-grid and 2-grid per 3s segment.
- Grid triggers based on face count and distance.
- Added format=yuv420p and setsar=1 to fix FFmpeg concat SAR error.
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
    center_x: float
    support: float
    x_min: float
    x_max: float


class YoloReframeEngine(IYoloReframeEngine):
    """MediaPipe-based person-aware reframing with dynamic cluster-based face detection."""

    SAMPLE_INTERVAL_SEC = 1.0
    MAX_SAMPLES = 60
    CONFIDENCE_THRESHOLD = 0.50  # MediaPipe face confidence

    MIN_SEPARATION_RATIO = 0.15
    MIN_CLUSTER_SUPPORT = 0.15
    SEGMENT_DUR_SEC = 3.0
    SAFE_ZONE_MARGIN_PX = 20

    def __init__(self, model_path: str = ""):
        # model_path is ignored in MediaPipe, kept for interface compatibility
        self._model_path = model_path
        self._model = None

    def _load_model(self) -> bool:
        """Lazy-load MediaPipe Face Detection model."""
        if self._model is not None:
            return True
        try:
            import mediapipe as mp
            # model_selection=1 is best for faces within 2-5 meters (podcast distance)
            self._mp_face_detection = mp.solutions.face_detection
            self._model = self._mp_face_detection.FaceDetection(
                min_detection_confidence=self.CONFIDENCE_THRESHOLD,
                model_selection=1
            )
            logger.info("yolo_reframe: MediaPipe Face Detection model loaded [CPU/GPU Optimized]")
            return True
        except Exception as e:
            logger.warning(f"yolo_reframe: failed to load MediaPipe model: {e}")
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
        autocenter: bool = True,
        **kwargs
    ) -> dict:
        if not os.path.exists(video_path):
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
        return {"output_path": output_path if success else video_path, "person_count": 0, "masks_available": False, "method": "center_crop_fallback"}

    # ─────────────────────────────────────────────────────────────────────
    # Internal pipeline
    # ─────────────────────────────────────────────────────────────────────

    def _smooth_track_and_crop(self, video_path: str, output_path: str, target_aspect: str, autogrid: bool) -> Optional[dict]:
        import cv2
        transcode_path = video_path.rsplit(".", 1)[0] + "_h264_temp.mp4"
        detect_path = self._ensure_h264(video_path, transcode_path)
        try:
            return self._track_impl(detect_path, video_path, output_path, autogrid)
        finally:
            if detect_path != video_path and os.path.exists(transcode_path):
                os.remove(transcode_path)

    def _track_impl(self, detect_path: str, original_path: str, output_path: str, autogrid: bool) -> Optional[dict]:
        """Detect faces using MediaPipe, divide video into time segments, render dynamic grid."""
        import cv2
        # FIX: Prevent glibc mutex crash
        cv2.setNumThreads(0)
        
        cap = cv2.VideoCapture(detect_path)
        if not cap.isOpened(): return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30

        orig_cap = cv2.VideoCapture(original_path)
        orig_width = int(orig_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_height = int(orig_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        orig_cap.release()

        scale_x = orig_width / width if width > 0 else 1.0
        sample_interval = max(1, int(fps * self.SAMPLE_INTERVAL_SEC))
        sample_indices = list(range(0, total_frames, sample_interval))[: self.MAX_SAMPLES]

        frame_detections: List[Tuple[float, List[Tuple[float, float]]]] = []

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret: continue

            # MediaPipe requires RGB input
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._model.process(frame_rgb)
            
            dets = []
            if results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    # MediaPipe returns normalized coords (0.0 to 1.0)
                    # Convert to absolute pixels
                    x_min = bbox.xmin * width
                    w = bbox.width * width
                    
                    # Calculate center X
                    cx = (x_min + (w / 2)) * scale_x
                    cy = 0.0 # Not strictly needed for X-axis grid, but kept for tuple structure
                    dets.append((cx, cy))
                    
            frame_detections.append((frame_idx / fps, dets))

        cap.release()
        if not frame_detections or all(len(d) == 0 for _, d in frame_detections): return None

        return self._render_dynamic_grid(
            original_path, output_path, orig_width, orig_height, fps,
            frame_detections, autogrid,
        )

    def _clamp_crop_x(self, crop_x: int, crop_w: int, frame_width: int) -> int:
        min_x = self.SAFE_ZONE_MARGIN_PX
        max_x = frame_width - crop_w - self.SAFE_ZONE_MARGIN_PX
        if max_x < min_x: return max(0, (frame_width - crop_w) // 2)
        return max(min_x, min(max_x, crop_x))

    def _render_dynamic_grid(
        self, video_path: str, output_path: str, width: int, height: int, fps: float,
        frame_detections: List[Tuple[float, List[Tuple[float, float]]]],
        autogrid: bool,
    ) -> Optional[dict]:
        """Dynamically switches between 1-grid (9:16) and 2-grid (top/bottom) per time segment."""
        
        total_dur = frame_detections[-1][0] if frame_detections else 0
        if total_dur <= 0: return None

        # 1. Classify layout per sample point
        segments = []
        current_layout = None
        current_start_t = 0.0

        for t, dets in frame_detections:
            desired = 'single'
            if autogrid and len(dets) >= 2:
                xs = [d[0] for d in dets]
                dist = max(xs) - min(xs)
                if dist > width * self.MIN_SEPARATION_RATIO:
                    desired = 'double'

            if current_layout is None:
                current_layout = desired
                current_start_t = t
            elif desired != current_layout:
                segments.append((current_start_t, t, current_layout))
                current_layout = desired
                current_start_t = t

        segments.append((current_start_t, total_dur + 0.1, current_layout))

        # 2. Merge short segments to prevent rapid flickering
        merged = []
        for seg in segments:
            if not merged:
                merged.append(list(seg))
            else:
                last = merged[-1]
                seg_dur = seg[1] - seg[0]
                if seg_dur < self.SEGMENT_DUR_SEC:
                    last[1] = seg[1]  # Extend previous
                elif last[2] == seg[2]:
                    last[1] = seg[1]  # Merge same layout
                else:
                    merged.append(list(seg))
        merged[-1][1] = max(merged[-1][1], total_dur)

        # 3. Calculate crop coordinates per segment and build FFmpeg filter
        video_filters = []
        audio_filters = []
        v_labels = []
        a_labels = []

        crop_w_single = min(int(height * 9 / 16), width)
        crop_w_double = min(int(height * 9 / 8), width)

        for i, seg in enumerate(merged):
            start_t, end_t, layout = seg
            if end_t <= start_t: continue

            v_out = f"v{i}"
            a_out = f"a{i}"
            seg_dets = [d for t, d in frame_detections if start_t <= t < end_t]

            if layout == 'double':
                all_x = [d[0] for det_list in seg_dets for d in det_list]
                if len(all_x) < 2:
                    layout = 'single'
                else:
                    sorted_x = np.sort(all_x)
                    gaps = np.diff(sorted_x)
                    split_idx = np.argmax(gaps)
                    split_val = sorted_x[split_idx]

                    left_x = [x for x in all_x if x <= split_val]
                    right_x = [x for x in all_x if x > split_val]

                    if not left_x or not right_x:
                        layout = 'single'
                    else:
                        X1 = int(np.median(left_x))
                        X2 = int(np.median(right_x))
                        X1 = self._clamp_crop_x(X1 - crop_w_double / 2, crop_w_double, width)
                        X2 = self._clamp_crop_x(X2 - crop_w_double / 2, crop_w_double, width)

                        # FIX: Added format=yuv420p and setsar=1 to prevent concat SAR error
                        video_filters.append(
                            f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,split=2[s{i}_a][s{i}_b];"
                            f"[s{i}_a]crop={crop_w_double}:{height}:{X1}:0,scale=1080:960,format=yuv420p[s{i}_ta];"
                            f"[s{i}_b]crop={crop_w_double}:{height}:{X2}:0,scale=1080:960,format=yuv420p[s{i}_tb];"
                            f"[s{i}_ta][s{i}_tb]vstack=inputs=2,setsar=1,format=yuv420p[{v_out}]"
                        )

            if layout == 'single':
                all_x = [d[0] for det_list in seg_dets for d in det_list]
                X = int(np.median(all_x)) if all_x else width // 2
                crop_x = self._clamp_crop_x(X - crop_w_single / 2, crop_w_single, width)

                # FIX: Added setsar=1,format=yuv420p
                video_filters.append(
                    f"[0:v]trim={start_t}:{end_t},setpts=PTS-STARTPTS,"
                    f"crop={crop_w_single}:{height}:{crop_x}:0,scale=1080:1920,setsar=1,format=yuv420p[{v_out}]"
                )

            audio_filters.append(f"[0:a]atrim={start_t}:{end_t},asetpts=PTS-STARTPTS[{a_out}]")
            v_labels.append(f"[{v_out}]")
            a_labels.append(f"[{a_out}]")

        if not v_labels: return None

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
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            # Compute actual person_count from detections (not hardcoded)
            detected_counts = [len(dets) for _, dets in frame_detections if dets]
            actual_person_count = int(np.median(detected_counts)) if detected_counts else 1
            logger.info(f"yolo_reframe: dynamic grid OK ({len(merged)} segments)")
            return {"output_path": output_path, "person_count": actual_person_count, "masks_available": False, "method": "yolo_dynamic_grid"}
        
        # Fallback: try without audio filter
        cmd_no_audio = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", ";".join(video_filters + [concat_v]),
            "-map", "[vout]", "-map", "0:a?",
            *get_video_encoder_args("medium"),
            "-c:a", "copy", "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd_no_audio, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            detected_counts = [len(dets) for _, dets in frame_detections if dets]
            actual_person_count = int(np.median(detected_counts)) if detected_counts else 1
            logger.info(f"yolo_reframe: dynamic grid OK (no audio fallback)")
            return {"output_path": output_path, "person_count": actual_person_count, "masks_available": False, "method": "yolo_dynamic_grid"}
        
        if result.stderr:
            logger.warning(f"yolo_reframe: FFmpeg error: {result.stderr[-500:]}")
        return None

    def _ensure_h264(self, video_path: str, transcode_path: str) -> str:
        """Transcode to H264 if video is AV1/VP9 (OpenCV can't decode reliably)."""
        try:
            cmd = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            codec = result.stdout.strip().lower()
            if codec in ("av1", "vp9", "vp8", "hevc"):
                cmd = ["ffmpeg", "-y", "-i", video_path, *get_video_encoder_args("low"), "-an", "-movflags", "+faststart", transcode_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0 and os.path.exists(transcode_path): return transcode_path
            return video_path
        except Exception:
            return video_path

    async def _center_crop_fallback(self, input_path: str, output_path: str, target_aspect: str) -> bool:
        """Simple center crop when MediaPipe unavailable or no persons found."""
        if target_aspect == "9:16": crop_filter = "crop=ih*9/16:ih,scale=1080:1920"
        elif target_aspect == "1:1": crop_filter = "crop=min(iw\\,ih):min(iw\\,ih),scale=1080:1080"
        else: shutil.copy2(input_path, output_path); return True

        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", crop_filter, *get_video_encoder_args("medium"), "-c:a", "copy", "-movflags", "+faststart", output_path]
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000: return True
        if os.path.exists(output_path): os.remove(output_path)
        return False
