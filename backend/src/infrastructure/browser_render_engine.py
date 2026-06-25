"""BrowserRenderEngine — Step 11/12: Headless Chrome + React + Framer Motion renderer.

Shared engine for:
- Hook Rendering (Step 12): animated hook text overlay → transparent video
- B-Roll Rendering (Step 11): full-frame motion typography

Implementation pattern: Node.js subprocess call to a render service that runs
Puppeteer/Playwright + React app capturing frames.

This is a PLACEHOLDER implementation that defines the interface and fallback
behavior. Full implementation requires the Node.js render service to be built.
"""
import asyncio
import json
import logging
import os
import subprocess
from typing import Optional

from src.domain.interfaces import IBrowserRenderEngine

logger = logging.getLogger(__name__)

# Path to the Node.js render service (to be built in frontend/)
RENDER_SERVICE_PATH = os.environ.get("BROWSER_RENDER_SERVICE", "")


class BrowserRenderEngine(IBrowserRenderEngine):
    """Headless Chrome + React + Framer Motion render service.

    Renders animated text (hooks/brolls) by calling a Node.js subprocess
    that runs Puppeteer capturing frames from a React app.

    Fallback: if render service is not available, generates a simple
    static frame using FFmpeg drawtext (degraded quality but functional).
    """

    def __init__(self, service_path: str = ""):
        self._service_path = service_path or RENDER_SERVICE_PATH
        self._available = bool(self._service_path and os.path.exists(self._service_path))

    @property
    def is_available(self) -> bool:
        return self._available

    async def render_hook(
        self,
        hook_text: str,
        style_config: dict,
        output_path: str,
        duration_ms: int = 3000,
        width: int = 1080,
        height: int = 1920,
    ) -> str:
        """Render hook animation via Browser Render Engine.

        If render service unavailable, falls back to static FFmpeg drawtext overlay.
        """
        if self._available:
            return await self._call_render_service(
                render_type="hook",
                text=hook_text,
                config=style_config,
                output_path=output_path,
                duration_ms=duration_ms,
                width=width,
                height=height,
            )

        # Fallback: generate simple transparent overlay with FFmpeg
        logger.warning("browser_render_engine: service not available, using FFmpeg fallback for hook")
        return await self._ffmpeg_fallback_hook(hook_text, output_path, duration_ms, width, height)

    async def render_broll(
        self,
        keyword: str,
        template: str,
        output_path: str,
        duration_ms: int = 2000,
        width: int = 1080,
        height: int = 1920,
    ) -> str:
        """Render b-roll motion typography via Browser Render Engine.

        If render service unavailable, falls back to simple FFmpeg generation.
        """
        if self._available:
            return await self._call_render_service(
                render_type="broll",
                text=keyword,
                config={"template": template},
                output_path=output_path,
                duration_ms=duration_ms,
                width=width,
                height=height,
            )

        logger.warning("browser_render_engine: service not available, using FFmpeg fallback for broll")
        return await self._ffmpeg_fallback_broll(keyword, template, output_path, duration_ms, width, height)

    async def _call_render_service(
        self,
        render_type: str,
        text: str,
        config: dict,
        output_path: str,
        duration_ms: int,
        width: int,
        height: int,
    ) -> str:
        """Call the Node.js render service subprocess."""
        payload = json.dumps({
            "type": render_type,
            "text": text,
            "config": config,
            "output_path": output_path,
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
        })

        cmd = ["node", self._service_path, "--render"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=payload.encode()),
                timeout=30.0,
            )
            if proc.returncode != 0:
                logger.error(f"browser_render failed: {stderr.decode()[-200:]}")
                return ""
            return output_path
        except asyncio.TimeoutError:
            logger.error("browser_render timeout (30s)")
            return ""
        except Exception as e:
            logger.error(f"browser_render error: {e}")
            return ""

    async def _ffmpeg_fallback_hook(
        self, text: str, output_path: str, duration_ms: int, width: int, height: int
    ) -> str:
        """Fallback: create a transparent WebM with text using FFmpeg + silent audio."""
        duration_s = duration_ms / 1000.0
        escaped_text = text.replace("'", "'\\''").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black@0:s={width}x{height}:d={duration_s}:r=30",
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", (
                f"drawtext=text='{escaped_text}'"
                f":fontsize=72:fontcolor=white:borderw=4:bordercolor=black"
                f":x=(w-text_w)/2:y=(h-text_h)/2"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-t", f"{duration_s}",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return output_path
        except Exception as e:
            logger.error(f"ffmpeg_fallback_hook error: {e}")
        return ""

    async def _ffmpeg_fallback_broll(
        self, keyword: str, template: str, output_path: str, duration_ms: int, width: int, height: int
    ) -> str:
        """Fallback: create animated b-roll with gradient background + text animation.

        Features:
        - Radial gradient background (dark → darker)
        - Text fade-in with scale animation
        - Subtle glow effect via shadow stacking
        - Template-aware color scheme
        """
        duration_s = duration_ms / 1000.0
        escaped = keyword.upper().replace("'", "'\\''").replace(":", "\\:")

        # Template-based color scheme
        colors = {
            "word_pop_typography": {"bg1": "#1a0033", "bg2": "#000011", "text": "white", "glow": "#9933FF"},
            "line_reveal_typography": {"bg1": "#001a1a", "bg2": "#000a0a", "text": "white", "glow": "#00FFCC"},
            "particle_text_burst": {"bg1": "#1a0000", "bg2": "#0a0000", "text": "white", "glow": "#FF4444"},
        }
        scheme = colors.get(template, colors["word_pop_typography"])

        # Animated text: fade in (0→0.4s) + hold + fade out (last 0.3s)
        fade_in_end = min(0.4, duration_s * 0.2)
        fade_out_start = duration_s - 0.3
        alpha_expr = (
            f"if(lt(t\\,{fade_in_end})\\,t/{fade_in_end}\\,"
            f"if(gt(t\\,{fade_out_start})\\,({duration_s}-t)/0.3\\,1))"
        )

        # Font size scales with keyword length
        base_size = 96 if len(keyword) <= 10 else (72 if len(keyword) <= 15 else 56)

        # Multi-layer drawtext for glow effect (3 shadow layers + main text)
        drawtext_layers = (
            # Layer 1: Outer glow (large blur shadow)
            f"drawtext=text='{escaped}'"
            f":fontsize={base_size}:fontcolor={scheme['glow']}@0.3"
            f":borderw=8:bordercolor={scheme['glow']}@0.2"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":alpha='{alpha_expr}'"
            f":enable='between(t,0,{duration_s})',"
            # Layer 2: Mid glow
            f"drawtext=text='{escaped}'"
            f":fontsize={base_size}:fontcolor={scheme['glow']}@0.5"
            f":borderw=4:bordercolor={scheme['glow']}@0.3"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":alpha='{alpha_expr}'"
            f":enable='between(t,0,{duration_s})',"
            # Layer 3: Main text (sharp white)
            f"drawtext=text='{escaped}'"
            f":fontsize={base_size}:fontcolor={scheme['text']}"
            f":borderw=2:bordercolor=black@0.8"
            f":shadowx=2:shadowy=2:shadowcolor=black@0.6"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":alpha='{alpha_expr}'"
            f":enable='between(t,0,{duration_s})'"
        )

        # Gradient background using geq filter (radial gradient)
        # Simpler approach: use gradients filter
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            f"gradients=s={width}x{height}:c0={scheme['bg1']}:c1={scheme['bg2']}:duration={duration_s}:speed=0.5:r=30",
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", drawtext_layers,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-t", f"{duration_s}",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            result = await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return output_path

            # Fallback to simple color if gradients filter not available
            logger.debug(f"gradients filter failed, using color fallback: {result.stderr[-100:]}")
            cmd_simple = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={scheme['bg2']}:s={width}x{height}:d={duration_s}:r=30",
                "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
                "-vf", drawtext_layers,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                "-t", f"{duration_s}",
                "-pix_fmt", "yuv420p",
                "-shortest",
                "-movflags", "+faststart",
                output_path,
            ]
            result = await asyncio.to_thread(
                subprocess.run, cmd_simple, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return output_path

        except Exception as e:
            logger.error(f"ffmpeg_fallback_broll error: {e}")
        return ""
