"""BRollInjector v2 — Multi-format overlay (video/image/gif/lottie/text).

Strategy:
- If ALL suggestions are fallback → use existing drawtext-only path (fast)
- If ANY suggestion has a real asset → use filter_complex with overlay for assets + drawtext for fallbacks
- Each video/image asset becomes an additional -i input to FFmpeg
- Drawtext filters coexist with overlay filters in the same filter_complex

Supported formats:
- video: FFmpeg scale+crop+overlay with fade enable/between
- png/svg: centered image overlay with fade-in/out
- gif: animated overlay preserving alpha
- lottie: fallback to drawtext for now (renderer is placeholder)
- text (fallback): existing drawtext filter (unchanged)
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional

from src.domain.entities import AssetResult, BRollSuggestion
from src.domain.interfaces import IBRollInjector, IBrowserRenderEngine

logger = logging.getLogger(__name__)

MAX_BROLLS_PER_CLIP = 3

# Template color schemes
TEMPLATE_STYLES = {
    "word_pop_typography": {
        "text_color": "white",
        "border_color": "black",
        "border_w": 3,
        "shadow_color": "black@0.8",
        "box_color": "black@0.6",
        "font_size_factor": 1.0,
    },
    "line_reveal_typography": {
        "text_color": "#00FFCC",
        "border_color": "#002222",
        "border_w": 3,
        "shadow_color": "black@0.7",
        "box_color": "#001a1a@0.7",
        "font_size_factor": 0.95,
    },
    "particle_text_burst": {
        "text_color": "#FF6B6B",
        "border_color": "#1a0000",
        "border_w": 3,
        "shadow_color": "black@0.9",
        "box_color": "#1a0000@0.7",
        "font_size_factor": 1.05,
    },
}


class BRollInjector(IBRollInjector):
    """Burns motion typography or visual assets onto video at specified timestamps.

    v2: Supports video/image/gif overlays in addition to drawtext fallback.
    Speaker remains visible. Assets appear as styled overlay with animation.
    """

    def __init__(self, render_engine: IBrowserRenderEngine, max_brolls: int = MAX_BROLLS_PER_CLIP):
        self._render_engine = render_engine
        self._max_brolls = max_brolls
        self._font_dir = "assets/fonts"

    async def inject(
        self,
        clip_path: str,
        suggestions: list[BRollSuggestion],
        output_path: str,
    ) -> str:
        """Overlay visual assets or burn typography onto video.

        Logic:
        - If ALL suggestions are fallback (no real asset) → drawtext-only path
        - If ANY suggestion has a real asset → filter_complex with overlays + drawtext

        Args:
            clip_path: Path to the input clip video.
            suggestions: List of BRollSuggestion with optional asset_result.
            output_path: Final output path.

        Returns:
            Output path on success, original clip_path on failure.
        """
        if not suggestions:
            logger.info("broll_injector: no suggestions, skipping")
            return clip_path

        if not os.path.exists(clip_path):
            logger.warning(f"broll_injector: clip not found {clip_path}")
            return clip_path

        # Limit and sort
        selected = sorted(suggestions, key=lambda s: s.at_time)[:self._max_brolls]

        # Separate into text-only (fallback) and asset-based
        fallback_suggestions = []
        asset_suggestions = []

        for s in selected:
            if s.asset_result is None or s.asset_result.is_fallback:
                fallback_suggestions.append(s)
            elif s.asset_result.asset_format == "lottie":
                # Lottie → fallback to drawtext for now (renderer is placeholder)
                fallback_suggestions.append(s)
            else:
                asset_suggestions.append(s)

        # Route to appropriate rendering path
        if not asset_suggestions:
            # ALL are fallback → use fast drawtext-only path (existing behavior)
            return await self._render_drawtext_only(clip_path, fallback_suggestions, output_path)
        else:
            # Mixed or all-asset → use filter_complex with overlays + drawtext
            return await self._render_mixed(clip_path, asset_suggestions, fallback_suggestions, output_path)

    # ─── Drawtext-Only Path (Original Behavior) ──────────────────────────────

    async def _render_drawtext_only(
        self,
        clip_path: str,
        suggestions: list[BRollSuggestion],
        output_path: str,
    ) -> str:
        """Original drawtext-only rendering. Used when all suggestions are fallback."""
        if not suggestions:
            return clip_path

        logger.info(f"broll_injector: burning {len(suggestions)} text overlays (drawtext-only)")

        filter_parts = []
        font_path = self._resolve_font()

        for suggestion in suggestions:
            text = suggestion.keyword.upper()
            at_time = suggestion.at_time
            duration = suggestion.duration
            end_time = at_time + duration
            template = suggestion.template

            style = TEMPLATE_STYLES.get(template, TEMPLATE_STYLES["word_pop_typography"])
            parts = self._build_drawtext_filter(
                text=text,
                start=at_time,
                end=end_time,
                duration=duration,
                style=style,
                font_path=font_path,
            )
            filter_parts.extend(parts)

        if not filter_parts:
            return clip_path

        filter_chain = ",".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", clip_path,
            "-vf", filter_chain,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"broll_injector: text burned → {os.path.basename(output_path)}")
                return output_path

            logger.error(f"broll_injector drawtext failed: {result.stderr[-300:]}")
            return clip_path

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"broll_injector drawtext exception: {e}")
            return clip_path

    # ─── Mixed Mode (Overlay + Drawtext) ─────────────────────────────────────

    async def _render_mixed(
        self,
        clip_path: str,
        asset_suggestions: list[BRollSuggestion],
        fallback_suggestions: list[BRollSuggestion],
        output_path: str,
    ) -> str:
        """Render using filter_complex: overlay assets + drawtext for fallbacks."""
        logger.info(
            f"broll_injector: mixed mode — {len(asset_suggestions)} assets, "
            f"{len(fallback_suggestions)} drawtext"
        )

        # Validate all asset files exist
        valid_assets = []
        for s in asset_suggestions:
            if s.asset_result and os.path.exists(s.asset_result.local_path):
                valid_assets.append(s)
            else:
                # Asset file missing → demote to fallback
                fallback_suggestions.append(s)

        if not valid_assets:
            # All assets invalid → fall back to drawtext-only
            return await self._render_drawtext_only(clip_path, fallback_suggestions, output_path)

        # Build FFmpeg command with multiple inputs
        inputs = ["-i", clip_path]
        for s in valid_assets:
            inputs.extend(["-i", s.asset_result.local_path])

        # Build filter_complex
        filter_complex = self._build_filter_complex(valid_assets, fallback_suggestions)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=180
            )
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"broll_injector: mixed overlay → {os.path.basename(output_path)}")
                return output_path

            logger.error(f"broll_injector mixed failed: {result.stderr[-500:]}")
            # Fallback: try drawtext-only with all suggestions
            all_suggestions = valid_assets + fallback_suggestions
            return await self._render_drawtext_only(clip_path, all_suggestions, output_path)

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"broll_injector mixed exception: {e}")
            return clip_path

    def _build_filter_complex(
        self,
        asset_suggestions: list[BRollSuggestion],
        fallback_suggestions: list[BRollSuggestion],
    ) -> str:
        """Build a complete filter_complex string for overlay + drawtext.

        Input layout:
        - [0:v] = main video
        - [1:v], [2:v], ... = asset inputs (one per valid_assets)

        Chain: overlay each asset sequentially, then apply drawtext filters.
        """
        filters = []
        current_label = "0:v"
        font_path = self._resolve_font()

        for i, suggestion in enumerate(asset_suggestions):
            input_idx = i + 1  # 0 is the main video
            asset_result = suggestion.asset_result
            out_label = f"ov{i}"

            # Build overlay filter based on asset format
            if asset_result.asset_format == "video":
                overlay_filter = self._build_video_overlay(
                    input_idx, suggestion, current_label, out_label
                )
            elif asset_result.asset_format in ("png", "svg"):
                overlay_filter = self._build_image_overlay(
                    input_idx, suggestion, current_label, out_label
                )
            elif asset_result.asset_format == "gif":
                overlay_filter = self._build_gif_overlay(
                    input_idx, suggestion, current_label, out_label
                )
            else:
                # Unknown format → skip this asset
                out_label = current_label
                overlay_filter = None

            if overlay_filter:
                filters.append(overlay_filter)
                current_label = f"[{out_label}]"
            else:
                current_label = f"[{current_label}]" if not current_label.startswith("[") else current_label

        # Apply drawtext filters for fallback suggestions
        drawtext_parts = []
        for suggestion in fallback_suggestions:
            text = suggestion.keyword.upper()
            at_time = suggestion.at_time
            duration = suggestion.duration
            end_time = at_time + duration
            template = suggestion.template
            style = TEMPLATE_STYLES.get(template, TEMPLATE_STYLES["word_pop_typography"])
            parts = self._build_drawtext_filter(
                text=text,
                start=at_time,
                end=end_time,
                duration=duration,
                style=style,
                font_path=font_path,
            )
            drawtext_parts.extend(parts)

        # Combine: overlays chain → drawtext chain → output label
        if drawtext_parts:
            # Current label needs to feed into drawtext
            drawtext_chain = ",".join(drawtext_parts)
            # Strip brackets for filter graph label
            clean_label = current_label.strip("[]")
            filters.append(f"{current_label}{drawtext_chain}[vout]")
        else:
            # No drawtext, final overlay output is [vout]
            # Rename last overlay output to [vout]
            if filters:
                # Replace the last out_label with vout
                last_filter = filters[-1]
                last_out = f"[ov{len(asset_suggestions) - 1}]"
                filters[-1] = last_filter.replace(last_out, "[vout]")
            else:
                # No filters at all (shouldn't happen)
                filters.append(f"[0:v]null[vout]")

        return ";".join(filters)

    # ─── Asset Overlay Builders ───────────────────────────────────────────────

    def _build_video_overlay(
        self,
        input_idx: int,
        suggestion: BRollSuggestion,
        base_label: str,
        out_label: str,
    ) -> str:
        """Build FFmpeg filter for video asset overlay.

        Scales video to max 648px width (60% of 1080), maintains AR, applies fade,
        enables between timestamps.
        """
        at_time = suggestion.at_time
        duration = suggestion.duration
        end_time = at_time + duration
        fade_dur = 0.3

        # Scale asset to max 648px width (60% of 1080), maintain AR, decrease only
        base = base_label.strip("[]")
        scaled_label = f"s{input_idx}"

        filter_str = (
            f"[{input_idx}:v]scale=648:-1:force_original_aspect_ratio=decrease,format=yuva420p,"
            f"fade=t=in:st={at_time:.3f}:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={end_time - fade_dur:.3f}:d={fade_dur}:alpha=1"
            f"[{scaled_label}];"
            f"[{base}][{scaled_label}]overlay=(W-w)/2:(H-h)/2"
            f":enable='between(t,{at_time:.3f},{end_time:.3f})'"
            f"[{out_label}]"
        )
        return filter_str

    def _build_image_overlay(
        self,
        input_idx: int,
        suggestion: BRollSuggestion,
        base_label: str,
        out_label: str,
    ) -> str:
        """Build FFmpeg filter for PNG/SVG image overlay.

        Centers image with fade-in/out. Image scaled to max 432px width (40% of 1080).
        """
        at_time = suggestion.at_time
        duration = suggestion.duration
        end_time = at_time + duration
        fade_dur = 0.3

        base = base_label.strip("[]")
        scaled_label = f"img{input_idx}"

        filter_str = (
            f"[{input_idx}:v]scale=432:-1:force_original_aspect_ratio=decrease,format=yuva420p,"
            f"fade=t=in:st={at_time:.3f}:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={end_time - fade_dur:.3f}:d={fade_dur}:alpha=1"
            f"[{scaled_label}];"
            f"[{base}][{scaled_label}]overlay=(W-w)/2:(H-h)/2"
            f":enable='between(t,{at_time:.3f},{end_time:.3f})'"
            f"[{out_label}]"
        )
        return filter_str

    def _build_gif_overlay(
        self,
        input_idx: int,
        suggestion: BRollSuggestion,
        base_label: str,
        out_label: str,
    ) -> str:
        """Build FFmpeg filter for animated GIF overlay.

        Preserves alpha channel, scales to max 432px width (40% of 1080), enables between timestamps.
        """
        at_time = suggestion.at_time
        duration = suggestion.duration
        end_time = at_time + duration
        fade_dur = 0.3

        base = base_label.strip("[]")
        scaled_label = f"gif{input_idx}"

        filter_str = (
            f"[{input_idx}:v]scale=432:-1:force_original_aspect_ratio=decrease,format=yuva420p,"
            f"fade=t=in:st={at_time:.3f}:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={end_time - fade_dur:.3f}:d={fade_dur}:alpha=1"
            f"[{scaled_label}];"
            f"[{base}][{scaled_label}]overlay=(W-w)/2:(H-h)/2"
            f":shortest=1"
            f":enable='between(t,{at_time:.3f},{end_time:.3f})'"
            f"[{out_label}]"
        )
        return filter_str

    # ─── Drawtext Filter Builder (Original) ───────────────────────────────────

    def _build_drawtext_filter(
        self,
        text: str,
        start: float,
        end: float,
        duration: float,
        style: dict,
        font_path: Optional[str],
    ) -> list[str]:
        """Build drawtext filter parts for one b-roll text overlay.

        Renders a modern keyword overlay with:
        1. Compact pill-shaped background at top-center
        2. Crisp text with border
        3. Fade-in/fade-out animation

        Positioned at top 20% of screen to avoid blocking speaker and subtitles.
        """
        # Clean and escape text
        clean_text = text.replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")
        font_opt = f":fontfile='{font_path}'" if font_path else ""

        # Adaptive font size based on text length (smaller = less intrusive)
        base_size = 42
        if len(text) > 15:
            base_size = 32
        elif len(text) > 10:
            base_size = 36
        font_size = int(base_size * style.get("font_size_factor", 1.0))

        # Fade animation: fade in 0.2s, hold, fade out 0.2s
        fade_in = 0.2
        fade_out = 0.2
        alpha_expr = (
            f"if(lt(t-{start:.3f}\\,{fade_in})\\,(t-{start:.3f})/{fade_in}\\,"
            f"if(gt(t\\,{end - fade_out:.3f})\\,({end:.3f}-t)/{fade_out}\\,1))"
        )

        parts = []

        # Layer 1: Compact background pill (top 20% of frame, not blocking speaker)
        box_color = style.get("box_color", "black@0.6")
        pill_h = font_size + 24
        parts.append(
            f"drawbox="
            f"x=(iw-text_w-40)/2:y=ih*0.15-{pill_h // 2}"
            f":w=text_w+40:h={pill_h}"
            f":color={box_color}:t=fill"
            f":enable='between(t,{start:.3f},{end:.3f})'"
        )

        # Layer 2: Main text with strong border (positioned at top 15%)
        text_color = style.get("text_color", "white")
        border_color = style.get("border_color", "black")
        border_w = style.get("border_w", 3)
        parts.append(
            f"drawtext=text='{clean_text}'"
            f":fontsize={font_size}{font_opt}"
            f":fontcolor={text_color}"
            f":borderw={border_w}:bordercolor={border_color}"
            f":x=(w-text_w)/2:y=h*0.15-text_h/2"
            f":alpha='{alpha_expr}'"
            f":enable='between(t,{start:.3f},{end:.3f})'"
        )

        return parts

    # ─── Font Resolution ──────────────────────────────────────────────────────

    def _resolve_font(self) -> Optional[str]:
        """Find a bold font for b-roll text."""
        if not os.path.isdir(self._font_dir):
            return None
        # Prefer impactful/bold fonts
        candidates = [
            "Poppins-Bold.ttf",
            "Montserrat-Bold.ttf",
            "Inter-Bold.ttf",
            "BebasNeue-Regular.ttf",
            "Anton-Regular.ttf",
        ]
        for name in candidates:
            path = os.path.join(self._font_dir, name)
            if os.path.exists(path):
                return os.path.abspath(path)
        # Any ttf
        for f in os.listdir(self._font_dir):
            if f.endswith(".ttf"):
                return os.path.abspath(os.path.join(self._font_dir, f))
        return None
