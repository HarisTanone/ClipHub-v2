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
    font_dirs = [
        fonts_dir or "assets/fonts",
        "assets/fonts",
        "backend/assets/fonts",
        "/usr/share/fonts/truetype",
        "/System/Library/Fonts",
        "/Library/Fonts",
    ]
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
    for fdir in font_dirs:
        if not fdir or not os.path.isdir(fdir):
            continue
        for name in candidates:
            path = os.path.join(fdir, name)
            if os.path.exists(path):
                return os.path.abspath(path)
        try:
            for f in sorted(os.listdir(fdir)):
                if f.endswith((".ttf", ".otf")):
                    return os.path.abspath(os.path.join(fdir, f))
        except OSError:
            pass
    return ""


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
    from src.infrastructure.gpu_encoder import get_video_encoder_args
    encoder_args = get_video_encoder_args("high")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", drawtext,
        "-map", "0:v:0", "-map", "0:a?",
        *encoder_args,
        "-c:a", "copy", "-movflags", "+faststart",
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

    image_path = ""
    fd, image_path = tempfile.mkstemp(suffix=f".{ext}")
    os.close(fd)
    try:
        with open(image_path, "wb") as f:
            f.write(data)

        x_expr = _overlay_x_expr(cfg["position"]).format(m=f"{margin:.4f}")
        y_expr = _overlay_y_expr(cfg["position"]).format(m=f"{margin:.4f}")

        # scale2ref sizes the overlay relative to the main video width (no
        # ffprobe needed) and lut=a applies the opacity — both work on every
        # FFmpeg since 4.0. The previous approach probed the video width and
        # used colorchannelmixer=aa= which requires FFmpeg >= 4.3 (Ubuntu
        # 20.04 ships 4.2.x), silently dropping image watermarks there.
        # max(2, ...) guards the scale-family magic value w=0 ("keep original
        # width") for tiny clips / small sizePct, and keeps width even for
        # yuv420p.
        w_expr = f"max(2,trunc(main_w*{cfg['sizePct'] / 100.0:.4f}/2)*2)"
        filter_complex = (
            f"[1:v]setsar=1[wm_in];"
            f"[wm_in][0:v]scale2ref=w='{w_expr}':h=-2[wm][base];"
            f"[wm]format=rgba,lut=a='floor(val*{opacity:.2f})'[wm2];"
            f"[base][wm2]overlay=x={x_expr}:y={y_expr}:format=auto,setsar=1[v]"
        )
        from src.infrastructure.gpu_encoder import get_video_encoder_args
        encoder_args = get_video_encoder_args("high")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", image_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            *encoder_args,
            "-c:a", "copy", "-movflags", "+faststart",
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
