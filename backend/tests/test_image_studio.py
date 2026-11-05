"""Unit tests for AI Image & Visual Post Studio."""
import pytest
from src.infrastructure.ai_image_typography import (
    TypographyContent,
    typography_engine,
)
from src.infrastructure.ai_image_studio_service import ai_image_studio_service


def test_typography_templates_metadata():
    templates = typography_engine.get_template_metadata()
    assert len(templates) >= 12
    ids = [t["id"] for t in templates]
    assert "minimal_quote" in ids
    assert "bold_editorial" in ids
    assert "skena_magazine" in ids
    assert "brutalist_poster" in ids
    assert "luxury_gold" in ids
    assert "cyberpunk_neon" in ids
    assert "aesthetic_carousel_card" in ids
    assert "news_bulletin" in ids
    assert "poetic_whisper" in ids
    assert "modern_business" in ids
    assert "cinematic_film" in ids
    assert "daily_stoic" in ids


def test_typography_rendering_all_templates():
    for t in typography_engine.TEMPLATES:
        content = TypographyContent(
            hook="INSIGHT",
            headline="Discipline equals freedom in every aspect of life.",
            body="Focus on the daily actions rather than distant outcomes.",
            author="Jocko Willink",
            handle="@cliperhub",
            template=t["id"],
            aspect_ratio="9:16",
        )
        img = typography_engine.render_overlay(None, content)
        assert img is not None
        assert img.size == (1080, 1920)


def test_typography_aspect_ratios():
    cases = [
        ("9:16", (1080, 1920)),
        ("1:1", (1080, 1080)),
        ("4:5", (1080, 1350)),
        ("16:9", (1920, 1080)),
    ]
    for ar, expected in cases:
        content = TypographyContent(
            hook="TEST",
            headline="Test Headline",
            template="minimal_quote",
            aspect_ratio=ar,
        )
        img = typography_engine.render_overlay(None, content)
        assert img.size == expected


def test_image_studio_settings_crud():
    s = ai_image_studio_service.get_settings(user_id=1)
    assert "daily_slots" in s
    assert "topics" in s

    # Update settings
    updated = ai_image_studio_service.update_settings(
        user_id=1,
        data={
            "enabled": True,
            "images_per_session": 3,
            "aspect_ratio": "9:16",
        },
    )
    assert updated["enabled"] is True
    assert updated["images_per_session"] == 3

    # Reset
    ai_image_studio_service.update_settings(user_id=1, data={"enabled": False})


def test_dynamic_gateway_settings_resolution():
    endpoint = ai_image_studio_service.get_image_api_endpoint()
    assert endpoint.endswith("/images/generations")
    assert "/v1/" in endpoint

    key = ai_image_studio_service.get_image_api_key()
    assert isinstance(key, str)

    default_model = ai_image_studio_service.get_image_model()
    assert "image" in default_model or default_model == "ag/gemini-3.1-flash-image"

    custom_model = ai_image_studio_service.get_image_model("gemini-2.5-flash-image")
    assert custom_model == "gemini-2.5-flash-image"


def test_suggest_quote_content_fallback_structure():
    content = ai_image_studio_service.suggest_quote_content("Bisnis Modern")
    assert isinstance(content, dict)
    assert "hook" in content
    assert "headline" in content
    assert "body" in content
    assert "author" in content
    assert "prompt" in content


def test_typography_db_store_crud():
    from src.infrastructure.image_typography_store import (
        get_all_typography_templates,
        create_typography_template,
        update_typography_template,
        delete_typography_template,
        get_typography_template,
    )
    initial_count = len(get_all_typography_templates())
    assert initial_count >= 12

    created = create_typography_template({
        "id": "pytest_custom_tpl",
        "name": "Pytest Custom Aesthetic",
        "vibe": "Ultra clean minimal modern vibe",
        "primary_font": "Inter",
        "secondary_font": "Roboto",
        "recommended_accent": "#10B981",
        "layout_type": "minimal_quote",
    })
    assert created["id"] == "pytest_custom_tpl"
    assert created["name"] == "Pytest Custom Aesthetic"

    # Verify rendering with custom template from DB
    content = TypographyContent(
        hook="TEST HOOK",
        headline="Testing Custom DB Template",
        template="pytest_custom_tpl",
    )
    img = typography_engine.render_overlay(None, content)
    assert img is not None

    # Update template
    updated = update_typography_template("pytest_custom_tpl", {"name": "Updated Custom Aesthetic"})
    assert updated["name"] == "Updated Custom Aesthetic"

    # Delete template
    ok = delete_typography_template("pytest_custom_tpl")
    assert ok is True
    assert get_typography_template("pytest_custom_tpl") is None


def test_typography_store_active_only_kwarg_compatibility():
    """Verify get_all_typography_templates supports both include_inactive and active_only."""
    from src.infrastructure.image_typography_store import (
        get_all_typography_templates,
        get_all_typography_fonts,
        get_all_aspect_ratios,
    )
    from src.infrastructure.ai_image_studio_service import AIImageStudioService

    # Test kwarg compatibility on all store functions
    tpls_default = get_all_typography_templates()
    tpls_active = get_all_typography_templates(active_only=True)
    tpls_all = get_all_typography_templates(include_inactive=True)
    assert len(tpls_active) > 0
    assert len(tpls_active) <= len(tpls_all)
    assert len(tpls_default) == len(tpls_active)

    fonts_active = get_all_typography_fonts(active_only=True)
    assert len(fonts_active) > 0

    aspects_active = get_all_aspect_ratios(active_only=True)
    assert len(aspects_active) > 0

    # Test resolve_template_and_font runs without any unexpected keyword argument error
    studio = AIImageStudioService()
    tpl_id, font = studio._resolve_template_and_font("auto", "auto", "Kecerdasan Buatan")
    assert tpl_id is not None
    assert font is not None


@pytest.mark.asyncio
async def test_social_dispatch_album_and_music(monkeypatch):
    """Verify _dispatch_social_post formats album type for multi-image and handles music parameters."""
    from src.infrastructure.ai_image_studio_service import AIImageStudioService
    from unittest.mock import AsyncMock

    captured_payloads = []

    async def mock_repliz_post(path, json_body=None):
        captured_payloads.append((path, json_body))
        return {"status": "ok", "scheduleId": "sch_123"}

    monkeypatch.setattr("src.presentation.routes.social.helpers.repliz_post", mock_repliz_post)

    studio = AIImageStudioService()

    # Case 1: Multi-image (album / carousel bulking) with custom TikTok music
    status, details = await studio._dispatch_social_post(
        account_ids=["acc_tiktok_1"],
        media_urls=["https://storage.com/img1.png", "https://storage.com/img2.png", "https://storage.com/img3.png"],
        title="Album Inspirasi Motivasi Pagi",
        caption="Headline\n\nBody content",
        media_type="image",
        music_enabled=True,
        music_id="7123456789",
        music_name="Trending Beat",
        music_artist="Top Producer",
        music_thumbnail="https://p16.tiktokcdn.com/thumb.jpg",
    )

    assert status == "scheduled"
    assert details["post_type"] == "album"
    assert details["media_count"] == 3
    assert details["music_enabled"] is True

    assert len(captured_payloads) == 1
    path, payload = captured_payloads[0]
    assert path == "/public/schedule"
    assert payload["type"] == "album"
    assert len(payload["medias"]) == 3
    assert payload["medias"][0]["url"] == "https://storage.com/img1.png"
    assert payload["medias"][1]["url"] == "https://storage.com/img2.png"
    assert payload["additionalInfo"]["isAiGenerated"] is False
    assert payload["additionalInfo"]["music"]["id"] == "7123456789"
    assert payload["additionalInfo"]["music"]["name"] == "Trending Beat"
    assert payload["additionalInfo"]["isAutoAddMusic"] is False

    # Case 2: Single image with auto-trending music
    captured_payloads.clear()
    status2, details2 = await studio._dispatch_social_post(
        account_ids=["acc_ig_1"],
        media_urls=["https://storage.com/single.png"],
        title="Single Quote Post",
        caption="Quote caption",
        media_type="image",
        music_enabled=True,
    )

    assert status2 == "scheduled"
    assert details2["post_type"] == "image"
    assert details2["media_count"] == 1
    assert len(captured_payloads) == 1
    _, payload2 = captured_payloads[0]
    assert payload2["type"] == "image"
    assert payload2["additionalInfo"]["isAutoAddMusic"] is True





