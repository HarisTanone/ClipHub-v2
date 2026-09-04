"""GPU Encoder Utilities — NVENC auto-detection for FFmpeg commands.

Provides helper functions to get the correct encoder arguments.
Auto-detects NVENC availability at module load. Falls back to libx264 if unavailable.

Usage:
    from src.infrastructure.gpu_encoder import get_video_encoder_args

    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", "...", *get_video_encoder_args(), output_path]
"""
import logging
import subprocess

logger = logging.getLogger(__name__)

# ─── Module-level NVENC detection (runs once at import) ───────────────────────

_nvenc_available: bool = False


def _detect_nvenc() -> bool:
    """Check if h264_nvenc is available in FFmpeg."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        if getattr(result, "returncode", 1) == 0 and "h264_nvenc" in (getattr(result, "stdout", "") or ""):
            return True
    except Exception:
        pass
    return False


_nvenc_available = _detect_nvenc()
if _nvenc_available:
    logger.info("gpu_encoder: NVENC (h264_nvenc) detected [OK]")
else:
    logger.info("gpu_encoder: NVENC not available, using libx264")


# ─── Public API ───────────────────────────────────────────────────────────────

def is_nvenc_available() -> bool:
    """Check if GPU encoding is available."""
    return _nvenc_available


def get_video_encoder_args(quality: str = "medium") -> list[str]:
    """Get FFmpeg video encoder arguments (NVENC if available, else libx264).

    Args:
        quality: "low" | "medium" | "high"
            - low: fast encode, larger file (preview)
            - medium: balanced (default, production)
            - high: slow encode, smaller file

    Returns:
        List of FFmpeg args: ["-c:v", "h264_nvenc", "-preset", ...]
    """
    if _nvenc_available:
        # NVENC presets: p1 (fastest) → p7 (slowest/best quality)
        # CQ: lower = better quality (12-28 typical range)
        presets = {
            "low": ("p3", "18"),
            "fast": ("p4", "16"),
            "medium": ("p5", "14"),   # Ultra crisp 1080p studio HD master
            "high": ("p6", "12"),     # Near-lossless studio master
        }
        preset, cq = presets.get(quality, ("p5", "14"))
        return [
            "-c:v", "h264_nvenc",
            "-preset", preset,
            "-cq", cq,
            "-b:v", "0",
            "-maxrate", "35M",
            "-bufsize", "50M",
            "-pix_fmt", "yuv420p",
        ]
    else:
        # libx264 fallback with pristine CRF and generous bitrate headroom
        presets = {
            "low": ("veryfast", "17"),
            "fast": ("fast", "15"),
            "medium": ("medium", "14"),  # Sharp HD studio master
            "high": ("slow", "12"),
        }
        preset, crf = presets.get(quality, ("medium", "14"))
        return [
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", crf,
            "-maxrate", "35M",
            "-bufsize", "50M",
            "-pix_fmt", "yuv420p",
        ]


def get_encoder_name() -> str:
    """Get current encoder name for logging."""
    return "h264_nvenc" if _nvenc_available else "libx264"
