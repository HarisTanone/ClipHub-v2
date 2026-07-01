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
        if result.returncode == 0 and "h264_nvenc" in result.stdout:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return False


_nvenc_available = _detect_nvenc()
if _nvenc_available:
    logger.info("gpu_encoder: NVENC (h264_nvenc) detected ✓")
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
        # CQ: lower = better quality (18-28 typical range)
        presets = {
            "low": ("p1", "28"),
            "medium": ("p4", "22"),
            "high": ("p6", "18"),
        }
        preset, cq = presets.get(quality, ("p4", "22"))
        return [
            "-c:v", "h264_nvenc",
            "-preset", preset,
            "-cq", cq,
            "-pix_fmt", "yuv420p",
        ]
    else:
        # libx264 fallback
        presets = {
            "low": ("ultrafast", "23"),
            "medium": ("fast", "18"),
            "high": ("slow", "15"),
        }
        preset, crf = presets.get(quality, ("fast", "18"))
        return [
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", crf,
        ]


def get_encoder_name() -> str:
    """Get current encoder name for logging."""
    return "h264_nvenc" if _nvenc_available else "libx264"
