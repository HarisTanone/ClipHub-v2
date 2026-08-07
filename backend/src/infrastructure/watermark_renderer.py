"""Server-side watermark rendering via FFmpeg.

Applies a user-configured watermark (image overlay or text drawtext) to a
finished clip video. Used by both V1 and V2 pipelines as a final
post-processing pass so the watermark always sits on top of hook, b-roll and
subtitles.

Config shape (mirrors the frontend ``WatermarkStyle``):

    {
        "enabled": bool,
        "type": "image" | "text",
        "imageDataUrl": str | None,   # data:image/png;base64,... (image type)
        "text": str,                  # text content (text type)
        "fontFamily": str,            # text font
        "fontSize": int,              # px (text type)
        "fontWeight": str,            # "400".."900"
        "color": str,                 # hex color (text type)
        "sizePct": int,               # image width as % of video width
        "opacity": int,               # 0..100
        "position": "top-left" | "top-center" | ... | "bottom-right",
        "marginPct": int,             # margin from edges, % of video dimension
    }
"""
import asyncio
import base64
import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

POSITIONS = {
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
}


def _is_enabled(value) -> bool:
    """Truthy check that also treats strings like "false"/"0"/"" as disabled."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def normalise_watermark_config(config) -> dict:
    """Coerce any raw watermark config into a safe, defaulted dict."""
    cfg = config or {}
    wtype = cfg.get("type")
    position = cfg.get("position")
    try:
        size_pct = int(cfg.get("sizePct") or 20)
    except (TypeError, ValueError):
        size_pct = 20
    try:
        opacity = int(cfg.get("opacity") if cfg.get("opacity") is not None else 60)
    except (TypeError, ValueError):
        opacity = 60
    try:
        font_size = int(cfg.get("fontSize") or 32)
    except (TypeError, ValueError):
        font_size = 32
    try:
        margin_pct = int(cfg.get("marginPct") or 3)
    except (TypeError, ValueError):
        margin_pct = 3
    return {
        "enabled": _is_enabled(cfg.get("enabled")),
        "type": wtype if wtype in ("image", "text") else "text",
        "imageDataUrl": cfg.get("imageDataUrl") or None,
        "text": str(cfg.get("text") or "").strip(),
        "fontFamily": str(cfg.get("fontFamily") or "Poppins"),
        "fontSize": max(8, min(200, font_size)),
        "fontWeight": str(cfg.get("fontWeight") or "700"),
        "color": str(cfg.get("color") or "#FFFFFF"),
        "sizePct": max(1, min(100, size_pct)),
        "opacity": max(0, min(100, opacity)),
        "position": position if position in POSITIONS else "bottom-right",
        "marginPct": max(0, min(40, margin_pct)),
    }


# ─── Position helpers ────────────────────────────────────────────────────────


def _overlay_x_expr(position: str) -> str:
    """Overlay filter x expression (main_w / overlay_w available)."""
    if position.endswith("left"):
        return "main_w*{m}"
    if position.endswith("center") and position.startswith(("top", "bottom")):
        return "(main_w-overlay_w)/2"
    if position == "center":
        return "(main_w-overlay_w)/2"
    if position.endswith("right"):
        return "main_w-overlay_w-main_w*{m}"
    return "(main_w-overlay_w)/2"


def _overlay_y_expr(position: str) -> str:
    if position.startswith("top"):
        return "main_h*{m}"
    if position == "center":
        return "(main_h-overlay_h)/2"
    if position.startswith("center"):
        return "(main_h-overlay_h)/2"
    return "main_h-overlay_h-main_h*{m}"


def _text_x_expr(position: str) -> str:
    """drawtext x expression (w / text_w available)."""
    if position.endswith("left"):
        return "w*{m}"
    if position.endswith("right"):
        return "w-text_w-w*{m}"
    return "(w-text_w)/2"


def _text_y_expr(position: str) -> str:
    if position.startswith("top"):
        return "h*{m}"
    if position.startswith("bottom"):
        return "h-text_h-h*{m}"
    return "(h-text_h)/2"


# ─── Font + image helpers ────────────────────────────────────────────────────


def _resolve_font(fonts_dir: str, family: str) -> str:
    """Resolve a font file path (mirrors services._resolve_hook_font)."""
    font_dir = fonts_dir or "assets/fonts"
    clean = re.sub(r"[^a-zA-Z0-9-]", "", str(family))
    candidates: list[str] = []
    if clean:
        for suffix in (".ttf", "-Bold.ttf", "-Regular.ttf", "-Medium.ttf",
                       "-SemiBold.ttf", "-ExtraBold.ttf"):
            candidates.append(clean + suffix)
        candidates.append(clean + ".otf")
    candidates += [
        "Poppins-Bold.ttf", "Poppins-Regular.ttf", "Poppins-Medium.ttf",
        "Inter-Bold.ttf", "Inter-Regular.ttf", "Montserrat-Bold.ttf",
        "NotoSans-Variable.ttf",
    ]
    for name in candidates:
        path = os.path.join(font_dir, name)
        if os.path.exists(path):
            resolved = os.path.abspath(path)
            return resolved
    if os.path.isdir(font_dir):
        for f in sorted(os.listdir(font_dir)):
            if f.endswith((".ttf", ".otf")):
                resolved = os.path.abspath(os.path.join(font_dir, f))
                logger.warning(
                    "watermark: font '%s' tidak ditemukan, fallback ke '%s'",
                    family, os.path.basename(resolved),
                )
                return resolved
    logger.warning("watermark: tidak ada font tersedia di '%s'", font_dir)
    return ""


def _probe_video_width(video_path: str) -> Optional[int]:
    """Return the main video stream width, or None if probing fails."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width", "-of", "csv=p=0", video_path,
            ],
            capture_output=True, text=True, timeout=20,
        )
        text = (out.stdout or "").strip()
        if text:
            return int(text.splitlines()[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("watermark: ffprobe width failed: %s", e)
    return None


def _decode_image_data_url(data_url: str):
    """Decode a data:image/*;base64 URL into (bytes, extension)."""
    match = re.match(r"^data:image/(png|jpe?g|webp);base64,(.+)$", data_url, re.DOTALL)
    if not match:
        return None, None
    kind = match.group(1)
    ext = "png" if kind == "png" else ("jpg" if kind.startswith("jpeg") else "webp")
    try:
        return base64.b64decode(match.group(2)), ext
    except Exception:  # noqa: BLE001
        return None, None


# ─── Main renderers ──────────────────────────────────────────────────────────


def apply_watermark(
    video_path: str,
    config: dict,
    output_path: str,
    fonts_dir: str = "assets/fonts",
) -> bool:
    """Apply a watermark to ``video_path`` producing ``output_path``.

    Returns True when the watermarked file was written successfully.
    """
    cfg = normalise_watermark_config(config)
    if not cfg["enabled"]:
        return False

    opacity = max(0.02, min(1.0, cfg["opacity"] / 100.0))
    margin = cfg["marginPct"] / 100.0

    if cfg["type"] == "text":
        return _render_text_watermark(video_path, cfg, output_path, fonts_dir, opacity, margin)

    if cfg["type"] == "image":
        return _render_image_watermark(video_path, cfg, output_path, opacity, margin)

    return False


def _render_text_watermark(
    video_path: str, cfg: dict, output_path: str, fonts_dir: str,
    opacity: float, margin: float,
) -> bool:
    text = cfg["text"]
    if not text:
        return False

    # textfile= approach avoids all ffmpeg text-escaping issues. Use a unique
    # name so concurrent renders (pipeline vs restyle) never collide.
    tmp_dir = os.path.dirname(output_path) or "."
    try:
        fd, text_file = tempfile.mkstemp(dir=tmp_dir, prefix="wm_text_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        logger.warning("watermark: cannot write textfile: %s", e)
        return False

    font_path = _resolve_font(fonts_dir, cfg["fontFamily"])
    font_opt = f":fontfile='{font_path}'" if font_path else ""
    fontcolor = f"{cfg['color']}@{opacity:.2f}"
    x_expr = _text_x_expr(cfg["position"]).format(m=f"{margin:.4f}")
    y_expr = _text_y_expr(cfg["position"]).format(m=f"{margin:.4f}")

    drawtext = (
        f"drawtext=textfile='{text_file}'"
        f":fontsize={cfg['fontSize']}"
        f"{font_opt}"
        f":fontcolor={fontcolor}"
        f":x={x_expr}"
        f":y={y_expr}"
    )
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", drawtext,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        output_path,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("watermark: ffmpeg failed: %s", e)
        return False
    finally:
        try:
            if os.path.exists(text_file):
                os.remove(text_file)
        except OSError:
            pass

    if proc.returncode != 0:
        logger.warning(
            "watermark: ffmpeg text error (%s): %s", proc.returncode, proc.stderr[-500:]
        )
        return False
    return os.path.exists(output_path) and os.path.getsize(output_path) > 0


def _render_image_watermark(
    video_path: str, cfg: dict, output_path: str, opacity: float, margin: float,
) -> bool:
    data_url = cfg["imageDataUrl"]
    if not data_url:
        return False

    data, ext = _decode_image_data_url(data_url)
    if data is None:
        logger.warning("watermark: image data URL tidak valid")
        return False

    width = _probe_video_width(video_path)
    if not width:
        logger.warning("watermark: tidak bisa probe video width, skip watermark")
        return False

    image_path = ""
    fd, image_path = tempfile.mkstemp(suffix=f".{ext}")
    os.close(fd)
    try:
        with open(image_path, "wb") as f:
            f.write(data)

        target_w = max(2, int(width * cfg["sizePct"] / 100))
        x_expr = _overlay_x_expr(cfg["position"]).format(m=f"{margin:.4f}")
        y_expr = _overlay_y_expr(cfg["position"]).format(m=f"{margin:.4f}")

        filter_complex = (
            f"[1:v]scale={target_w}:-2,format=rgba,"
            f"colorchannelmixer=aa={opacity:.2f}[wm];"
            f"[0:v][wm]overlay=x={x_expr}:y={y_expr}:format=auto,setsar=1[v]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", image_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            output_path,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=240,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("watermark: ffmpeg failed: %s", e)
            return False

        if proc.returncode != 0:
            logger.warning(
                "watermark: ffmpeg image error (%s): %s",
                proc.returncode, proc.stderr[-500:],
            )
            return False
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    finally:
        try:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
        except OSError:
            pass


# ─── Async convenience for the pipeline ──────────────────────────────────────


async def apply_watermark_if_configured(
    config: Optional[dict],
    output_dir: str,
    clip_rank: int,
    final_path: str,
    fonts_dir: str = "assets/fonts",
    job_id: str = "",
) -> None:
    """Apply a watermark to a finished clip in place (via a temp file).

    Safe no-op when the config is missing/disabled. Never raises — failures
    are logged so rendering keeps going.
    """
    cfg = normalise_watermark_config(config)
    if not cfg["enabled"]:
        return
    if cfg["type"] == "text" and not cfg["text"]:
        return
    if cfg["type"] == "image" and not cfg["imageDataUrl"]:
        return

    tmp = f"{output_dir}/clip_{clip_rank:02d}_wm_tmp.mp4"
    try:
        ok = await asyncio.to_thread(
            apply_watermark, final_path, cfg, tmp, fonts_dir
        )
        if ok and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, final_path)
            logger.info("[%s] watermark applied clip %s", job_id, clip_rank)
        elif os.path.exists(tmp):
            os.remove(tmp)
    except Exception as e:  # noqa: BLE001
        logger.warning("[%s] watermark failed clip %s: %s", job_id, clip_rank, e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


async def apply_watermark_for_job(
    job,
    clip_rank: int,
    output_dir: str,
    final_path: str,
    fonts_dir: str = "assets/fonts",
    job_id: str = "",
) -> None:
    """Read ``watermark_config`` from ``job.clips_data`` and apply it in place.

    Shared by V1/V2 pipelines and the restyle route. Never raises.
    """
    config = (getattr(job, "clips_data", None) or {}).get("watermark_config")
    await apply_watermark_if_configured(
        config, output_dir, clip_rank, final_path,
        fonts_dir=fonts_dir, job_id=job_id,
    )
