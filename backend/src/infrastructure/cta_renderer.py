"""Server-side CTA (Call to Action) end-card rendering via FFmpeg.

Applies a user-configured Call to Action end-card (badge/card with headline,
subhead, button, and optional social handle) at the final seconds of a clip
(default: 3s, range: 1s to 6s).

Config shape (mirrors frontend CtaStyle):
    {
        "enabled": bool,
        "template": "follow_badge" | "like_share" | "link_bio" | "subscribe_pill" | "comment_prompt" | "custom_card",
        "duration": float,            # 1.0 .. 6.0 seconds (default: 3.0)
        "headline": str,              # e.g. "Follow For More", "Cek Link di Bio"
        "subhead": str,               # e.g. "@yourchannel", "Tips edukasi harian"
        "buttonText": str,            # e.g. "FOLLOW", "KLIK LINK", "SUBSCRIBE"
        "socialPlatform": str,        # "tiktok" | "instagram" | "youtube" | "general" | "custom"
        "socialHandle": str,          # e.g. "@yourchannel"
        "position": str,              # "bottom" | "center" | "lower-third"
        "animation": str,             # "slide_up" | "pop_in" | "fade_bounce" | "glow_pulse" | "glitch"
        "primaryColor": str,          # hex e.g. "#10B981"
        "textColor": str,             # hex e.g. "#FFFFFF"
        "backgroundColor": str,       # hex e.g. "#0F172A"
        "bgOpacity": int,             # 0 .. 100 (default: 90)
        "fontSize": int,              # px (default: 28)
        "fontFamily": str,            # font family (default: "Poppins")
        "fontWeight": str,            # "600", "700", "800", "900"
        "showIcon": bool,             # default: True
        "showArrow": bool,            # default: True
        "avatarUrl": str | None,
    }
"""
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CTA_CONFIG = {
    "enabled": False,
    "ctaType": "card",
    "template": "follow_badge",
    "duration": 3.0,
    "text": "Jangan lupa follow untuk tips berikutnya!",
    "headline": "Follow For More",
    "subhead": "@yourchannel",
    "buttonText": "FOLLOW",
    "selectedIcon": "tiktok",
    "socialPlatform": "tiktok",
    "socialHandle": "@yourchannel",
    "position": "bottom",
    "bgBox": True,
    "animation": "slide_up",
    "primaryColor": "#10B981",
    "textColor": "#FFFFFF",
    "backgroundColor": "#0F172A",
    "bgOpacity": 90,
    "fontSize": 28,
    "fontFamily": "Poppins",
    "fontWeight": "700",
    "showIcon": True,
    "showArrow": True,
    "avatarUrl": None,
}


def _is_enabled(value) -> bool:
    """Truthy check that also handles string representations."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def _resolve_font_path(font_family: str, fonts_dir: str = "assets/fonts") -> Optional[str]:
    """Find TTF/OTF font file across assets and system fonts."""
    search_dirs = [
        fonts_dir,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../assets/fonts")),
        os.path.abspath("assets/fonts"),
        os.path.abspath("backend/assets/fonts"),
        "/usr/share/fonts/truetype",
        "/usr/share/fonts",
        "/opt/homebrew/share/fonts",
        "/Library/Fonts",
    ]
    family_clean = (font_family or "Poppins").replace(" ", "")
    candidates = [
        f"{family_clean}-Bold.ttf",
        f"{family_clean}-Regular.ttf",
        f"{family_clean}-Variable.ttf",
        f"{family_clean}.ttf",
        f"{font_family}-Bold.ttf",
        f"{font_family}-Regular.ttf",
        f"{font_family}.ttf",
    ]
    for d in search_dirs:
        if d and os.path.isdir(d):
            for cand in candidates:
                p = os.path.join(d, cand)
                if os.path.exists(p):
                    return p
    return None


def normalise_cta_config(config: Optional[dict]) -> dict:
    """Coerce raw CTA config dictionary into safe, validated dict supporting camelCase & snake_case."""
    cfg = config or {}
    try:
        dur = float(
            cfg.get("duration")
            if cfg.get("duration") is not None
            else (cfg.get("duration_sec") if cfg.get("duration_sec") is not None else 3.0)
        )
    except (TypeError, ValueError):
        dur = 3.0
    dur = max(1.0, min(6.0, dur))

    try:
        font_size = int(cfg.get("fontSize") or cfg.get("font_size") or 28)
    except (TypeError, ValueError):
        font_size = 28
    font_size = max(16, min(60, font_size))

    try:
        raw_opacity = cfg.get("bgOpacity") if cfg.get("bgOpacity") is not None else cfg.get("bg_opacity")
        bg_opacity = int(raw_opacity if raw_opacity is not None else 90)
    except (TypeError, ValueError):
        bg_opacity = 90
    bg_opacity = max(0, min(100, bg_opacity))

    cta_type = str(cfg.get("ctaType") or cfg.get("cta_type") or cfg.get("mode") or "card").strip().lower()
    if cta_type not in ("card", "text", "both"):
        cta_type = "card"

    text_msg = str(cfg.get("text") or cfg.get("headline") or DEFAULT_CTA_CONFIG["text"]).strip()
    headline = str(cfg.get("headline") or cfg.get("text") or DEFAULT_CTA_CONFIG["headline"]).strip()
    subhead = str(cfg.get("subhead") or "").strip()
    button_text = str(cfg.get("buttonText") or cfg.get("button_text") or DEFAULT_CTA_CONFIG["buttonText"]).strip()
    social_handle = str(cfg.get("socialHandle") or cfg.get("social_handle") or cfg.get("handle") or "").strip()

    template = str(cfg.get("template") or "follow_badge")
    if template not in ("follow_badge", "like_share", "link_bio", "subscribe_pill", "comment_prompt", "custom_card"):
        template = "follow_badge"

    position = str(cfg.get("position") or "bottom")
    if position not in ("bottom", "center", "lower-third", "top"):
        position = "bottom"

    animation = str(cfg.get("animation") or "slide_up")
    if animation not in ("slide_up", "pop_in", "fade_bounce", "glow_pulse", "glitch"):
        animation = "slide_up"

    selected_icon = str(cfg.get("selectedIcon") or cfg.get("selected_icon") or "tiktok")
    if selected_icon not in ("tiktok", "instagram", "youtube", "bell", "link", "share", "message", "zap", "user_plus", "heart", "star"):
        selected_icon = "tiktok"

    bg_box = cfg.get("bgBox") if cfg.get("bgBox") is not None else cfg.get("bg_box")
    if bg_box is not None:
        bg_box = _is_enabled(bg_box)
    else:
        bg_box = True

    return {
        "enabled": _is_enabled(cfg.get("enabled")),
        "ctaType": cta_type,
        "template": template,
        "duration": dur,
        "text": text_msg,
        "headline": headline,
        "subhead": subhead,
        "buttonText": button_text,
        "selectedIcon": selected_icon,
        "socialPlatform": str(cfg.get("socialPlatform") or cfg.get("social_platform") or cfg.get("type") or "tiktok"),
        "socialHandle": social_handle,
        "position": position,
        "bgBox": bg_box,
        "animation": animation,
        "primaryColor": str(cfg.get("primaryColor") or cfg.get("primary_color") or "#10B981"),
        "textColor": str(cfg.get("textColor") or cfg.get("text_color") or "#FFFFFF"),
        "backgroundColor": str(cfg.get("backgroundColor") or cfg.get("background_color") or "#0F172A"),
        "bgOpacity": bg_opacity,
        "fontSize": font_size,
        "fontFamily": str(cfg.get("fontFamily") or cfg.get("font_family") or "Poppins"),
        "fontWeight": str(cfg.get("fontWeight") or cfg.get("font_weight") or "700"),
        "showIcon": bool(cfg.get("showIcon", cfg.get("show_icon", True))),
        "showArrow": bool(cfg.get("showArrow", cfg.get("show_arrow", True))),
        "avatarUrl": cfg.get("avatarUrl") or cfg.get("avatar_url") or None,
    }


def escape_drawtext(text: str) -> str:
    """Escape text safely for FFmpeg drawtext filter."""
    if not text:
        return ""
    t = str(text).replace("\\", "\\\\")
    t = t.replace(":", "\\:")
    t = t.replace("'", "'\\\\''")
    t = t.replace("%", "\\%")
    return t


def build_cta_drawtext_filters(
    cta_config: Optional[dict],
    clip_duration: float,
    font_path: Optional[str] = None,
) -> list[str]:
    """Construct FFmpeg drawtext filter lines for the CTA end-card.

    Supports Plain Text, Creator Card, and Text+Icon modes.
    Enables display only in the range [clip_duration - cta_duration, clip_duration].
    """
    cfg = normalise_cta_config(cta_config)
    if not cfg["enabled"]:
        return []

    dur = cfg["duration"]
    start_t = max(0.0, clip_duration - dur)
    end_t = clip_duration

    enable_expr = f"between(t,{start_t:.3f},{end_t:.3f})"
    font_opt = f":fontfile='{font_path}'" if font_path else ""

    filters = []
    pos = cfg["position"]
    # Position Y computation for 1080x1920 portrait
    if pos == "top":
        base_y = "h*0.08"
    elif pos == "center":
        base_y = "h/2 - 60"
    elif pos == "lower-third":
        base_y = "h*0.75"
    else:  # bottom
        base_y = "h*0.84"

    bg_opacity_hex = f"{cfg['bgOpacity'] / 100.0:.2f}"
    box_color = f"{cfg['backgroundColor']}@{bg_opacity_hex}"
    box_enabled = ":box=1:boxcolor=" + box_color + ":boxborderw=16" if cfg["bgBox"] else ":box=0"

    cta_type = cfg["ctaType"]

    if cta_type in ("text", "both"):
        # Single text message
        msg_escaped = escape_drawtext(cfg["text"])
        text_filter = (
            f"drawtext=text='{msg_escaped}'"
            f"{font_opt}"
            f":fontsize={cfg['fontSize']}"
            f":fontcolor={cfg['textColor']}"
            f"{box_enabled}"
            f":borderw=2:bordercolor=black@0.6"
            f":shadowx=2:shadowy=3:shadowcolor=black@0.5"
            f":x=(w-text_w)/2:y={base_y}"
            f":enable='{enable_expr}'"
        )
        filters.append(text_filter)
        return filters

    # Card Mode
    headline_escaped = escape_drawtext(cfg["headline"])
    button_escaped = escape_drawtext(f"[{cfg['buttonText']}]") if cfg["buttonText"] else ""

    # Main Headline with background card box
    headline_filter = (
        f"drawtext=text='{headline_escaped}'"
        f"{font_opt}"
        f":fontsize={cfg['fontSize']}"
        f":fontcolor={cfg['textColor']}"
        f":box=1:boxcolor={box_color}:boxborderw=16"
        f":borderw=2:bordercolor=black@0.6"
        f":shadowx=2:shadowy=3:shadowcolor=black@0.5"
        f":x=(w-text_w)/2:y={base_y}"
        f":enable='{enable_expr}'"
    )
    filters.append(headline_filter)

    # Optional Button text underneath headline
    if button_escaped:
        button_filter = (
            f"drawtext=text='{button_escaped}'"
            f"{font_opt}"
            f":fontsize={max(16, cfg['fontSize'] - 4)}"
            f":fontcolor={cfg['primaryColor']}"
            f":borderw=2:bordercolor=black@0.8"
            f":shadowx=1:shadowy=2:shadowcolor=black@0.5"
            f":x=(w-text_w)/2:y={base_y} + {cfg['fontSize'] + 22}"
            f":enable='{enable_expr}'"
        )
        filters.append(button_filter)

    return filters


def _probe_duration(video_path: str) -> float:
    """Probe video duration in seconds via ffprobe."""
    import subprocess
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(res.stdout.strip())
    except Exception:
        return 30.0


def apply_cta(
    input_video: str,
    cta_config: dict,
    output_video: str,
    fonts_dir: str = "assets/fonts",
) -> bool:
    """Apply CTA end-card to video in a standalone pass."""
    import subprocess
    cfg = normalise_cta_config(cta_config)
    if not cfg["enabled"]:
        return False

    duration = _probe_duration(input_video)
    font_path = _resolve_font_path(cfg["fontFamily"], fonts_dir=fonts_dir)

    filters = build_cta_drawtext_filters(cfg, duration, font_path)
    if not filters:
        return False

    filter_str = ",".join(filters)
    from src.infrastructure.gpu_encoder import get_video_encoder_args
    encoder_args = get_video_encoder_args("high")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", filter_str,
        "-map", "0:v:0", "-map", "0:a?",
        *encoder_args,
        "-c:a", "copy", "-movflags", "+faststart",
        output_video,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if proc.returncode != 0:
            logger.warning("cta_renderer: ffmpeg failed (rc=%s): %s", proc.returncode, proc.stderr[-300:] if proc.stderr else "")
        return proc.returncode == 0 and os.path.exists(output_video) and os.path.getsize(output_video) > 0
    except Exception as e:
        logger.warning("cta_renderer: ffmpeg exception: %s", e)
        return False


async def apply_cta_if_configured(
    config: Optional[dict],
    output_dir: str,
    clip_rank: int,
    final_path: str,
    fonts_dir: str = "assets/fonts",
    job_id: str = "",
) -> None:
    """Apply a CTA to a finished clip in place (via a temp file). Safe no-op if disabled."""
    import asyncio
    cfg = normalise_cta_config(config)
    if not cfg["enabled"]:
        logger.debug("[%s] CTA disabled for clip %s", job_id, clip_rank)
        return

    logger.info(
        "[%s] Applying CTA end-card to clip %s: headline='%s', template=%s, dur=%.1fs",
        job_id, clip_rank, cfg.get("headline"), cfg.get("template"), cfg.get("duration")
    )
    tmp = f"{output_dir}/clip_{clip_rank:02d}_cta_tmp.mp4"
    try:
        ok = await asyncio.to_thread(apply_cta, final_path, cfg, tmp, fonts_dir)
        if ok and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, final_path)
            logger.info("[%s] CTA applied successfully to clip %s -> %s", job_id, clip_rank, final_path)
        elif os.path.exists(tmp):
            os.remove(tmp)
            logger.warning("[%s] CTA render returned false for clip %s", job_id, clip_rank)
    except Exception as e:
        logger.warning("[%s] CTA application failed clip %s: %s", job_id, clip_rank, e)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


async def apply_cta_for_job(
    job,
    clip_rank: int,
    output_dir: str,
    final_path: str,
    fonts_dir: str = "assets/fonts",
    job_id: str = "",
) -> None:
    """Read ``cta_config`` from ``job.clips_data`` and apply it in place."""
    config = (getattr(job, "clips_data", None) or {}).get("cta_config") or getattr(job, "cta_config", None)
    await apply_cta_if_configured(
        config, output_dir, clip_rank, final_path,
        fonts_dir=fonts_dir, job_id=job_id,
    )
