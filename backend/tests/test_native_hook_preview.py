import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.hook_preview import NativeHookPreviewService


def manifest(engine="skia"):
    return {
        "preset_id": "p", "hook_id": "skia_impact_badge", "engine": engine,
        "text_source": "custom", "duration": 3.0, "position_y": 50.0,
        "font_family": "Anton", "font_size": 54.0, "font_weight": "700",
        "color": "#fff", "background": {}, "stroke": {}, "shadow": {},
        "animation": "skia_impact_badge" if engine != "hyperframes" else "",
        "template": "hook_cyber_hud" if engine == "hyperframes" else "",
        "version": "1.0.0",
        "config": {"engine": engine, "animation": "skia_impact_badge", "duration": 3, "positionY": 50},
    }


@pytest.mark.asyncio
async def test_skia_preview_calls_only_skia_and_caches(tmp_path, monkeypatch):
    renderer = MagicMock()
    image = MagicMock()
    image.save.side_effect = lambda path, **_: open(path, "wb").write(b"png")
    renderer.generate_hook_frame.return_value = image
    monkeypatch.setattr("src.infrastructure.hook_preview.SkiaHookRenderer", lambda **_: renderer)
    svc = NativeHookPreviewService(str(tmp_path))
    first = await svc.render(manifest("skia"), "DUA\nBARIS", 30)
    image.save.assert_called_once()
    second = await svc.render(manifest("skia"), "DUA\nBARIS", 30)
    assert second["cache_hit"] is True
    assert renderer.generate_hook_frame.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["remotion", "hyperframes", "skia", "ffmpeg"])
async def test_unavailable_selected_engine_fails_without_dispatching_another(tmp_path, engine):
    svc = NativeHookPreviewService(str(tmp_path))
    svc._renderers = {name: AsyncMock(side_effect=RuntimeError(name)) for name in ("remotion", "hyperframes", "skia", "ffmpeg")}
    with pytest.raises(RuntimeError, match=engine):
        await svc.render(manifest(engine), "HOOK", 30)
    for name, renderer in svc._renderers.items():
        assert renderer.await_count == (1 if name == engine else 0)


@pytest.mark.asyncio
async def test_empty_hook_text_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        await NativeHookPreviewService(str(tmp_path)).render(manifest(), "  ", 30)
