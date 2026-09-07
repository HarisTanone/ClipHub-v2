"""Native Hook still rendering, dispatched strictly by canonical manifest engine."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from typing import Any, Awaitable, Callable, Mapping

from src.infrastructure.hook_manifest import HOOK_RENDERER_VERSION, hook_render_spec_hash
from src.infrastructure.skia_hook_renderer import SkiaHookRenderer


class NativeHookPreviewService:
    def __init__(self, cache_dir: str, font_dir: str = "assets/fonts") -> None:
        self.cache_dir = os.path.abspath(cache_dir)
        self.font_dir = font_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self._renderers: dict[str, Callable[..., Awaitable[None]]] = {
            "remotion": self._render_remotion,
            "hyperframes": self._render_hyperframes,
            "skia": self._render_skia,
            "ffmpeg": self._render_ffmpeg,
        }

    async def render(self, manifest: Mapping[str, Any], text: str, frame: int = 30) -> dict[str, Any]:
        clean_text = str(text or "").strip()
        if not clean_text:
            raise ValueError("Hook text is empty")
        engine = str(manifest.get("engine") or "")
        renderer = self._renderers.get(engine)
        if renderer is None:
            raise ValueError(f"Unsupported Hook preview engine: {engine or '<empty>'}")
        cache_hash = hook_render_spec_hash({**dict(manifest), "preview_text": clean_text}, frame=frame)
        path = os.path.join(self.cache_dir, f"{cache_hash}.png")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return {"path": path, "hash": cache_hash, "cache_hit": True, "engine": engine, "renderer_version": HOOK_RENDERER_VERSION}
        await renderer(manifest, clean_text, frame, path)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError(f"{engine} native Hook preview produced no artifact")
        return {"path": path, "hash": cache_hash, "cache_hit": False, "engine": engine, "renderer_version": HOOK_RENDERER_VERSION}

    @staticmethod
    def _synthetic_video(path: str, duration: float) -> None:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"color=c=#111827:s=1080x1920:r=30:d={max(1.0, duration)}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
        ], check=True, capture_output=True, timeout=60)

    @staticmethod
    def _extract_frame(video: str, path: str, frame: int) -> None:
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(max(0, frame) / 30), "-i", video,
            "-frames:v", "1", path,
        ], check=True, capture_output=True, timeout=60)

    async def _render_skia(self, manifest: Mapping[str, Any], text: str, frame: int, path: str) -> None:
        renderer = SkiaHookRenderer(font_dir=self.font_dir)
        image = renderer.generate_hook_frame(text, hook_style=str(manifest["hook_id"]), style_config=dict(manifest["config"]))
        image.save(path, format="PNG")

    async def _render_ffmpeg(self, manifest: Mapping[str, Any], text: str, frame: int, path: str) -> None:
        from src.infrastructure.unified_ffmpeg_compositor import UnifiedFFmpegCompositor
        with tempfile.TemporaryDirectory(prefix="hook-preview-ffmpeg-") as tmp:
            base = os.path.join(tmp, "base.mp4")
            out = os.path.join(tmp, "hook.mp4")
            self._synthetic_video(base, float(manifest["duration"]))
            compositor = UnifiedFFmpegCompositor(font_dir=self.font_dir)
            ok = await compositor.render_single_pass(
                input_video=base, output_video=out, hook_text=text,
                hook_style_config=dict(manifest["config"]), words=[], subtitle_style_config={"enabled": False},
            )
            if not ok:
                raise RuntimeError("ffmpeg Hook preview render failed")
            self._extract_frame(out, path, frame)

    async def _render_hyperframes(self, manifest: Mapping[str, Any], text: str, frame: int, path: str) -> None:
        from src.infrastructure.hyperframes_adapter import get_hyperframes_adapter
        from src.infrastructure.hf_style_catalog import hook_events_from_text
        with tempfile.TemporaryDirectory(prefix="hook-preview-hf-") as tmp:
            base = os.path.join(tmp, "base.mp4")
            out = os.path.join(tmp, "hook.mp4")
            self._synthetic_video(base, float(manifest["duration"]))
            result = await get_hyperframes_adapter().render_polish(
                base_video=base, events=hook_events_from_text(text, float(manifest["duration"])),
                output_path=out, template=str(manifest["template"]), duration=float(manifest["duration"]),
                job_id="preview", clip_id=str(frame), force=True,
            )
            if not (result.get("ok") and result.get("mode") == "hyperframes"):
                raise RuntimeError(f"hyperframes Hook preview failed: {result}")
            self._extract_frame(out, path, frame)

    async def _render_remotion(self, manifest: Mapping[str, Any], text: str, frame: int, path: str) -> None:
        from src.domain.interfaces_remotion import RemotionRenderConfig
        from src.infrastructure.remotion_adapter import RemotionAdapter
        with tempfile.TemporaryDirectory(prefix="hook-preview-remotion-") as tmp:
            base = os.path.join(tmp, "base.mp4")
            jpg = os.path.join(tmp, "still.jpg")
            self._synthetic_video(base, float(manifest["duration"]))
            adapter = RemotionAdapter()
            try:
                if not await adapter.health_check():
                    raise RuntimeError("remotion Hook preview unavailable")
                result = await adapter.render_still(
                    scene_graph={"clip_rank": 0, "duration": float(manifest["duration"]), "layers": []},
                    creative_direction={"hook_style_config": dict(manifest["config"]), "subtitle_style_config": {"enabled": False}},
                    video_path=base, output_path=jpg, frame=frame, config=RemotionRenderConfig(),
                    words=[], hook_text=text, hook_style=str(manifest["animation"]),
                )
                if not result.get("success"):
                    raise RuntimeError(f"remotion Hook preview failed: {result.get('error')}")
                image = str(result.get("image") or "")
                if image.startswith("data:image"):
                    import base64
                    with open(path, "wb") as fh:
                        fh.write(base64.b64decode(image.split(",", 1)[1]))
                elif os.path.exists(jpg):
                    shutil.copy2(jpg, path)
                else:
                    raise RuntimeError("remotion still response contains no image")
            finally:
                await adapter.close()
