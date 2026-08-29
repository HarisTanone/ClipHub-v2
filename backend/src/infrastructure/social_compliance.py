"""Social Media Format Compliance & Sanitizer.

Ensures video and image files strictly conform to TikTok, Instagram Reels,
YouTube Shorts, and Facebook Reels API requirements:
- Video: MP4 container, H.264 (AVC) high/main profile, yuv420p SDR pixel format,
  even dimensions (e.g. 1080x1920), constant frame rate, AAC audio, and +faststart moov atom.
- Thumbnail: JPEG format, maximum 1080x1920, <= 20 MB.
"""
import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def probe_media(file_path: str) -> Dict[str, Any]:
    """Run ffprobe on media file and return streams & format metadata."""
    if not file_path or not os.path.exists(file_path):
        return {}
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "stream=index,codec_type,codec_name,pix_fmt,width,height,r_frame_rate,sample_rate,channels",
        "-show_entries", "format=format_name,duration,size,bit_rate",
        "-of", "json",
        file_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception as e:
        logger.warning(f"ffprobe failed for {file_path}: {e}")
    return {}


def is_video_social_compliant(file_path: str) -> bool:
    """Check if video satisfies TikTok & Instagram Reels technical constraints."""
    info = probe_media(file_path)
    streams = info.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not v_stream:
        return False

    v_codec = str(v_stream.get("codec_name", "")).lower()
    pix_fmt = str(v_stream.get("pix_fmt", "")).lower()
    width = int(v_stream.get("width") or 0)
    height = int(v_stream.get("height") or 0)

    # Must be H.264 / AVC
    if v_codec not in ("h264", "avc1"):
        return False

    # Must be yuv420p standard 8-bit SDR
    if pix_fmt not in ("yuv420p", "yuvj420p"):
        return False

    # Dimensions must be even
    if width % 2 != 0 or height % 2 != 0:
        return False

    # Must have AAC audio stream (or stereo AAC)
    if a_stream:
        a_codec = str(a_stream.get("codec_name", "")).lower()
        if a_codec not in ("aac", "mp4a"):
            return False

    return True


def ensure_social_compliant_video(
    video_path: str,
    output_path: Optional[str] = None,
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    """Ensure a video file strictly adheres to Instagram/TikTok specs.
    
    If already compliant and has faststart, returns the original path.
    Otherwise transcodes into a pristine MP4 with H.264 + AAC + yuv420p + faststart.
    """
    if not video_path or not os.path.exists(video_path):
        return video_path


    # Check if existing video is already compliant
    if is_video_social_compliant(video_path) and not output_path:
        # Fast-path: quickly verify faststart / moov atom placement
        try:
            with open(video_path, "rb") as f:
                header = f.read(1024 * 64)
                if b"moov" in header:
                    return video_path
        except Exception:
            pass

    out_file = output_path or (os.path.splitext(video_path)[0] + "_compliant.mp4")
    if out_file == video_path:
        out_file = os.path.splitext(video_path)[0] + "_c_temp.mp4"

    logger.info(f"Transcoding video to social compliant format: {video_path} -> {out_file}")

    info = probe_media(video_path)
    streams = info.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    # Base ffmpeg command with H.264 High profile, yuv420p, +faststart
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
    ]

    # If missing audio stream, generate a silent AAC audio track to satisfy Instagram/TikTok
    if not has_audio:
        cmd.extend([
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-shortest",
        ])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.1",
        "-preset", "fast",
        "-crf", "19",
        "-maxrate", "12M",
        "-bufsize", "24M",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        "-movflags", "+faststart",
        out_file,
    ])

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if res.returncode != 0 or not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
        logger.error(f"Failed to transcode compliant video: {res.stderr}")
        return video_path

    # If we created a temp output and wanted in-place replacement
    if output_path is None and out_file.endswith("_c_temp.mp4"):
        shutil.move(out_file, video_path)
        return video_path

    return out_file


def ensure_social_compliant_thumbnail(
    thumb_path: Optional[str],
    video_path: Optional[str] = None,
    output_path: Optional[str] = None,
    seek: float = 1.5,
    max_width: int = 1080,
    max_height: int = 1920,
) -> Optional[str]:
    """Ensure a compliant JPEG thumbnail (meeting TikTok/Instagram photo constraints: JPG/JPEG/WebP, max 1080x1920, <= 20MB).
    
    If thumb_path exists and is valid JPEG/WebP <= 20MB, returns it.
    If not, extracts frame from video_path.
    """
    if thumb_path and os.path.exists(thumb_path):
        size_mb = os.path.getsize(thumb_path) / (1024 * 1024)
        ext = os.path.splitext(thumb_path)[1].lower()
        if size_mb <= 20 and ext in (".jpg", ".jpeg", ".webp"):
            return thumb_path

    if not video_path or not os.path.exists(video_path):
        return thumb_path if (thumb_path and os.path.exists(thumb_path)) else None

    out_file = output_path
    if not out_file:
        out_file = os.path.splitext(video_path)[0] + "_thumb.jpg"

    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.2, float(seek)):.2f}",
        "-i", video_path,
        "-frames:v", "1",
        "-vf", f"scale='min({max_width},iw)':-2",
        "-q:v", "2",
        out_file,
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 0:
            return out_file
    except Exception as e:
        logger.warning(f"Failed to generate compliant thumbnail from video: {e}")

    return thumb_path if (thumb_path and os.path.exists(thumb_path)) else None
