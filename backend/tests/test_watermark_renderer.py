"""Unit tests for the server-side FFmpeg watermark renderer."""
import asyncio
from unittest.mock import patch

from src.infrastructure.watermark_renderer import (
    _overlay_x_expr,
    _overlay_y_expr,
    _text_x_expr,
    _text_y_expr,
    apply_watermark,
    apply_watermark_if_configured,
    normalise_watermark_config,
)


def test_normalise_defaults():
    cfg = normalise_watermark_config(None)
    assert cfg["enabled"] is False
    assert cfg["type"] == "text"
    assert cfg["position"] == "bottom-right"
    assert cfg["opacity"] == 60
    assert cfg["sizePct"] == 20
    assert cfg["marginPct"] == 3


def test_normalise_clamps():
    cfg = normalise_watermark_config({
        "enabled": True,
        "type": "bogus",
        "position": "somewhere",
        "opacity": 999,
        "sizePct": -5,
        "marginPct": 99,
    })
    assert cfg["type"] == "text"
    assert cfg["position"] == "bottom-right"
    assert cfg["opacity"] == 100
    assert cfg["sizePct"] == 1
    assert cfg["marginPct"] == 40


def test_position_expressions():
    assert _text_x_expr("top-left").format(m="0.03") == "w*0.03"
    assert _text_x_expr("bottom-center").format(m="0.03") == "(w-text_w)/2"
    assert _text_x_expr("top-right").format(m="0.03") == "w-text_w-w*0.03"
    assert _text_y_expr("top-left").format(m="0.03") == "h*0.03"
    assert _text_y_expr("center-right").format(m="0.03") == "(h-text_h)/2"
    assert _text_y_expr("bottom-left").format(m="0.03") == "h-text_h-h*0.03"
    assert _overlay_x_expr("top-center").format(m="0.03") == "(main_w-overlay_w)/2"
    assert _overlay_x_expr("center-right").format(m="0.03") == "main_w-overlay_w-main_w*0.03"
    assert _overlay_y_expr("bottom-right").format(m="0.03") == "main_h-overlay_h-main_h*0.03"
    assert _overlay_y_expr("center-left").format(m="0.03") == "(main_h-overlay_h)/2"


def test_disabled_is_noop():
    assert apply_watermark("x.mp4", {"enabled": False}, "out.mp4") is False


def test_text_without_text_is_noop():
    assert apply_watermark("x.mp4", {"enabled": True, "type": "text", "text": "   "}, "out.mp4") is False


def test_image_without_image_is_noop():
    assert apply_watermark("x.mp4", {"enabled": True, "type": "image", "imageDataUrl": None}, "out.mp4") is False


def test_image_bad_data_url_is_noop():
    assert apply_watermark("x.mp4", {"enabled": True, "type": "image", "imageDataUrl": "not-a-data-url"}, "out.mp4") is False


def test_apply_if_configured_disabled_is_noop():
    asyncio.run(apply_watermark_if_configured({"enabled": False}, "/tmp/wm", 1, "/x.mp4"))


@patch("src.infrastructure.watermark_renderer.subprocess.run")
def test_text_watermark_builds_drawtext(mock_run, tmp_path):
    mock_run.return_value = type("P", (), {"returncode": 0, "stderr": ""})()
    out = str(tmp_path / "out.mp4")
    # Pre-create the output so the success check passes (subprocess is mocked).
    with open(out, "w", encoding="utf-8") as f:
        f.write("dummy")
    with patch("src.infrastructure.watermark_renderer._resolve_font", return_value="/fonts/Poppins.ttf"):
        ok = apply_watermark("/in.mp4", {
            "enabled": True,
            "type": "text",
            "text": "hello",
            "fontFamily": "Poppins",
            "fontSize": 32,
            "color": "#FFFFFF",
            "opacity": 60,
            "position": "bottom-right",
            "marginPct": 3,
        }, out, fonts_dir="/fonts")
    assert ok is True
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "ffmpeg"
    vf = cmd[cmd.index("-vf") + 1]
    assert "drawtext=" in vf
    assert "fontsize=32" in vf
    assert "fontcolor=#FFFFFF@0.60" in vf
    assert "x=w-text_w-w*0.0300" in vf
    assert "y=h-text_h-h*0.0300" in vf


@patch("src.infrastructure.watermark_renderer.subprocess.run")
def test_image_watermark_builds_overlay(mock_run, tmp_path):
    mock_run.return_value = type("P", (), {"returncode": 0, "stderr": ""})()
    out = str(tmp_path / "out.mp4")
    # Pre-create the output so the success check passes (subprocess is mocked).
    with open(out, "w", encoding="utf-8") as f:
        f.write("dummy")
    ok = apply_watermark("/in.mp4", {
        "enabled": True,
        "type": "image",
        "imageDataUrl": "data:image/png;base64,iVBORw0KGgo=",
        "sizePct": 20,
        "opacity": 50,
        "position": "top-center",
        "marginPct": 3,
    }, out)
    assert ok is True
    cmd = mock_run.call_args.args[0]
    assert "-filter_complex" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "scale2ref=w='max(2,trunc(main_w*0.2000/2)*2)':h=-2" in fc
    assert "lut=a='floor(val*0.50)'" in fc
    assert "x=(main_w-overlay_w)/2" in fc
    assert "y=main_h*0.0300" in fc
    assert "colorchannelmixer" not in fc
