"""NVENCEncoder — GPU-accelerated H.264 encoding with software fallback."""
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class NVENCEncoder:
    """GPU-accelerated H.264 encoding with libx264 fallback.
    
    NVENC: h264_nvenc, preset p4, CQ 23
    Fallback: libx264, preset fast, CRF 18
    """

    NVENC_PRESET = "p4"
    NVENC_CQ = "23"
    LIBX264_PRESET = "fast"
    LIBX264_CRF = "18"

    def __init__(self, use_nvenc: Optional[bool] = None):
        env_val = os.getenv("USE_NVENC", "false").lower()
        self._requested = use_nvenc if use_nvenc is not None else (env_val == "true")
        self._nvenc_available = self._requested and self._check_nvenc()
        
        if self._requested and not self._nvenc_available:
            logger.warning("nvenc_unavailable", extra={"fallback": "libx264"})
        elif self._nvenc_available:
            logger.info("nvenc_enabled", extra={"preset": self.NVENC_PRESET, "cq": self.NVENC_CQ})

    @property
    def using_nvenc(self) -> bool:
        return self._nvenc_available

    def encode(self, input_path: str, output_path: str, extra_filters: str = "") -> bool:
        """Encode video with NVENC or libx264 fallback.
        
        Args:
            input_path: Source video file.
            output_path: Destination encoded file.
            extra_filters: Additional FFmpeg filter string (optional).
            
        Returns:
            True if encoding succeeded.
        """
        if self._nvenc_available:
            success = self._encode_nvenc(input_path, output_path, extra_filters)
            if success:
                return True
            # NVENC failed mid-encode — fallback
            logger.warning("nvenc_encode_failed", extra={
                "input": input_path, "fallback": "libx264"
            })

        return self._encode_libx264(input_path, output_path, extra_filters)

    def _encode_nvenc(self, input_path: str, output_path: str, extra_filters: str) -> bool:
        """Encode using NVENC."""
        cmd = ["ffmpeg", "-i", input_path]
        if extra_filters:
            cmd.extend(["-vf", extra_filters])
        cmd.extend([
            "-c:v", "h264_nvenc",
            "-preset", self.NVENC_PRESET,
            "-cq", self.NVENC_CQ,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "copy",
            "-y",
            output_path,
        ])
        return self._run_ffmpeg(cmd)

    def _encode_libx264(self, input_path: str, output_path: str, extra_filters: str) -> bool:
        """Encode using libx264 software encoder."""
        cmd = ["ffmpeg", "-i", input_path]
        if extra_filters:
            cmd.extend(["-vf", extra_filters])
        cmd.extend([
            "-c:v", "libx264",
            "-preset", self.LIBX264_PRESET,
            "-crf", self.LIBX264_CRF,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "copy",
            "-y",
            output_path,
        ])
        return self._run_ffmpeg(cmd)

    def _run_ffmpeg(self, cmd: list) -> bool:
        """Execute FFmpeg command."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                logger.error("ffmpeg_encode_error", extra={"stderr": result.stderr[-300:]})
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg_encode_timeout")
            return False
        except FileNotFoundError:
            logger.error("ffmpeg_not_found")
            return False

    def _check_nvenc(self) -> bool:
        """Check if NVENC encoder is available via ffmpeg -encoders."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and "h264_nvenc" in result.stdout:
                logger.info("nvenc_detected")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False
