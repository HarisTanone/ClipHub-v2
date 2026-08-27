"""Comprehensive test suite for Preset Slug, Style Persistence, and Social Auto-Post Features."""
import json
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
try:
    import pytest
except ImportError:
    class DummyPytest:
        @staticmethod
        def fixture(*args, **kwargs):
            return lambda fn: fn
        class mark:
            @staticmethod
            def asyncio(fn):
                return fn
    pytest = DummyPytest()
from src.infrastructure.db_connection import get_dict_connection
from src.presentation.routes.presets import _ensure_presets_table, slugify, _generate_unique_slug
from src.infrastructure.preset_resolver import resolve_preset
from src.infrastructure.social_auto_post_service import social_auto_post_service
from src.infrastructure.gdrive_uploader import GoogleDriveUploader


@pytest.fixture(autouse=True)
def setup_db():
    conn = get_dict_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                hashed_password TEXT,
                full_name TEXT,
                is_active INTEGER DEFAULT 1,
                is_superadmin INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Check column names in users
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "hashed_password" not in columns and "password_hash" in columns:
            conn.execute("INSERT OR IGNORE INTO users (id, email, password_hash, full_name) VALUES (1, 'test@example.com', 'hash', 'Test User')")
        else:
            conn.execute("INSERT OR IGNORE INTO users (id, email, hashed_password, full_name) VALUES (1, 'test@example.com', 'hash', 'Test User')")
        conn.commit()
    finally:
        conn.close()
    _ensure_presets_table()
    yield


def test_slugify_helper():
    assert slugify("Gaming Vibe 01") == "gaming-vibe-01"
    assert slugify("Style @ Special #1!") == "style-special-1"
    assert slugify("  slug_test__name  ") == "slug-test-name"
    assert slugify("") == "preset"


def test_preset_create_and_slug_generation():
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        name = "Test Preset Slug Unique"
        base_slug = slugify(name)
        slug_1 = _generate_unique_slug(conn, base_slug)
        assert slug_1 == base_slug

        cur.execute(
            "INSERT INTO user_presets (user_id, name, slug, hook_style, subtitle_style, text_emphasis_style, watermark_style, cta_style) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                name,
                slug_1,
                json.dumps({"animation": "zoom_in", "fontFamily": "Inter"}),
                json.dumps({"stylePreset": "glassmorphism", "highlightColor": "#FFCC00"}),
                json.dumps({"effectMode": "hero_punch"}),
                json.dumps({"enabled": True, "type": "text", "text": "@ClipHub"}),
                json.dumps({"enabled": True, "template": "modern", "duration": 3.0}),
            ),
        )
        conn.commit()
        inserted_id = cur.lastrowid

        # Second preset with same base slug must receive suffix
        slug_2 = _generate_unique_slug(conn, base_slug)
        assert slug_2 == f"{base_slug}-02"

        # Cleanup
        cur.execute("DELETE FROM user_presets WHERE id = ?", (inserted_id,))
        conn.commit()
    finally:
        conn.close()


def test_preset_resolver_all_layers():
    conn = get_dict_connection()
    try:
        cur = conn.cursor()
        test_slug = "my-full-layer-slug-test"
        cur.execute("DELETE FROM user_presets WHERE slug = ?", (test_slug,))
        cur.execute(
            "INSERT INTO user_presets (user_id, name, slug, hook_style, subtitle_style, text_emphasis_style, watermark_style, cta_style) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "Full Layer Test",
                test_slug,
                json.dumps({"animation": "kinetic_words", "fontSize": 72}),
                json.dumps({"stylePreset": "podcast_pro", "highlightColor": "#00FFCC"}),
                json.dumps({"effectMode": "neon_pulse", "highlightMode": "gradient"}),
                json.dumps({"enabled": True, "type": "text", "text": "WatermarkPro"}),
                json.dumps({"enabled": True, "template": "social_card", "accountName": "MyAccount"}),
            ),
        )
        conn.commit()
        inserted_id = cur.lastrowid

        # Resolve by slug
        resolved = resolve_preset(test_slug, user_id=1)
        assert resolved is not None
        assert resolved["source"] == "user_preset"
        assert resolved["name"] == "Full Layer Test"
        assert resolved["slug"] == test_slug
        assert resolved["hook_style_config"]["animation"] == "kinetic_words"
        assert resolved["subtitle_style_config"]["stylePreset"] == "podcast_pro"
        assert resolved["text_emphasis_style_config"]["effectMode"] == "neon_pulse"
        assert resolved["text_emphasis_enabled"] is True
        assert resolved["watermark_config"]["text"] == "WatermarkPro"
        assert resolved["cta_config"]["template"] == "social_card"

        # Resolve by ID
        resolved_by_id = resolve_preset(str(inserted_id), user_id=1)
        assert resolved_by_id is not None
        assert resolved_by_id["slug"] == test_slug

        # Resolve by 'user:ID'
        resolved_by_user_id = resolve_preset(f"user:{inserted_id}", user_id=1)
        assert resolved_by_user_id is not None
        assert resolved_by_user_id["slug"] == test_slug

        # Cleanup
        cur.execute("DELETE FROM user_presets WHERE id = ?", (inserted_id,))
        conn.commit()
    finally:
        conn.close()


def test_social_auto_post_custom_schedule_times():
    times = social_auto_post_service.calculate_custom_schedule_times(
        clip_count=3,
        custom_time_str="18:30",
        interval_hours=2,
    )
    assert len(times) == 3
    # Check that second time is 2 hours after first
    diff_sec = (times[1] - times[0]).total_seconds()
    assert diff_sec == 7200  # 2 hours

    diff_sec_3 = (times[2] - times[1]).total_seconds()
    assert diff_sec_3 == 7200


def test_social_auto_post_caption_extraction():
    clip = {
        "rank": 1,
        "hook": "Cara Cepat Viral di TikTok",
        "reason": "Momen ini memiliki hook yang kuat",
        "captions": {
            "tiktok": "Tips rahasia FYP 2026! Tonton sampai habis.",
            "youtube": "Trik rahasia Shorts.",
        },
    }

    tt_caption = social_auto_post_service.extract_clip_caption(clip, platform="tiktok", include_hashtags=True)
    assert "Tips rahasia FYP" in tt_caption
    assert "#fyp" in tt_caption

    yt_caption = social_auto_post_service.extract_clip_caption(clip, platform="youtube", include_hashtags=True)
    assert "Trik rahasia Shorts" in yt_caption
    assert "#Shorts" in yt_caption


@pytest.mark.asyncio
async def test_get_platforms_status_structure():
    status = await social_auto_post_service.get_platforms_status(user_id=1)
    assert "platforms" in status
    assert "tiktok" in status["platforms"]
    assert "instagram" in status["platforms"]
    assert "youtube" in status["platforms"]
    assert "facebook" in status["platforms"]
    assert "threads" in status["platforms"]
    assert "linkedin" in status["platforms"]
    for plat, info in status["platforms"].items():
        assert "connected" in info
        assert "count" in info
        assert "accounts" in info


@pytest.mark.asyncio
async def test_auto_schedule_job_clips_with_account_filtering():
    sample_clips = [
        {"rank": 1, "start": 10.0, "end": 40.0, "hook": "Hook 1", "video_path": "/tmp/clip1.mp4"},
        {"rank": 2, "start": 50.0, "end": 80.0, "hook": "Hook 2", "video_path": "/tmp/clip2.mp4"},
    ]

    mock_accounts = [
        {"id": "acc_tt_1", "account_id": "acc_tt_1", "platform": "tiktok", "name": "TikTok Primary"},
        {"id": "acc_tt_2", "account_id": "acc_tt_2", "platform": "tiktok", "name": "TikTok Secondary"},
        {"id": "acc_yt_1", "account_id": "acc_yt_1", "platform": "youtube", "name": "YouTube Shorts"},
    ]

    with patch.object(social_auto_post_service, "get_connected_accounts", new=AsyncMock(return_value=mock_accounts)), \
         patch("src.infrastructure.social_auto_post_service.find_final_clip", return_value="/tmp/test_clip.mp4"), \
         patch("src.infrastructure.social_auto_post_service.os.path.exists", return_value=True), \
         patch("src.infrastructure.social_auto_post_service.repliz_post", new=AsyncMock(return_value={"id": "post_123"})), \
         patch.object(GoogleDriveUploader, "is_configured", new_callable=PropertyMock(return_value=True)), \
         patch("src.infrastructure.social_auto_post_service.gdrive_uploader.upload_video", return_value={"direct_link": "https://drive.google.com/test.mp4"}):

        # Scenario 1: Filter specifically for acc_tt_2 only
        result = await social_auto_post_service.auto_schedule_job_clips(
            job_id="test_job_001",
            output_dir="/tmp",
            clips=sample_clips,
            target_platforms=["tiktok"],
            user_id=1,
            target_account_ids=["acc_tt_2"],
            schedule_mode="custom",
            custom_schedule_time="2026-08-25T18:00:00",
            notify_telegram=False,
        )

        assert result["scheduled_count"] == 2
        for post in result["records"]:
            assert post["account_name"] == "TikTok Secondary"
            assert post["platform"] == "tiktok"

        # Scenario 2: Post to all platforms without specific account filter
        result_all = await social_auto_post_service.auto_schedule_job_clips(
            job_id="test_job_002",
            output_dir="/tmp",
            clips=sample_clips,
            target_platforms=["tiktok", "youtube"],
            user_id=1,
            target_account_ids=[],
            schedule_mode="ai",
            notify_telegram=False,
        )
        assert result_all["scheduled_count"] == 6  # 2 clips * (2 tiktok accounts + 1 youtube account)


def test_telegram_submit_lookup_slug_integration():
    import sys
    import os
    hermes_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../ops/hermes/bin"))
    if hermes_bin not in sys.path:
        sys.path.insert(0, hermes_bin)

    from ac_submit_job import lookup_preset_by_name

    # Mock user presets and style presets returned by ac_auth.api_get
    mock_presets = [
        {"id": 10, "name": "Gaming Pro", "slug": "gaming-pro-v1"},
        {"id": 11, "name": "Story Minimal", "slug": "story-minimal"},
    ]

    mock_style_presets = [
        {"id": "glassmorphism", "name": "Glassmorphism"},
    ]

    def mock_api_get(path):
        if path == "/presets":
            return mock_presets
        elif path == "/style-presets":
            return mock_style_presets
        return []

    with patch("ac_submit_job.ac_auth.api_get", side_effect=mock_api_get):
        # Test finding by slug
        found_slug = lookup_preset_by_name("gaming-pro-v1")
        assert found_slug == "gaming-pro-v1"

        # Test finding by display name
        found_name = lookup_preset_by_name("Gaming Pro")
        assert found_name == "gaming-pro-v1"

        # Test finding system preset
        found_sys = lookup_preset_by_name("glassmorphism")
        assert found_sys == "glassmorphism"


@pytest.mark.asyncio
async def test_list_and_get_presets_endpoint_sqlite_row_safety():
    """Verify list_presets and get_preset_by_slug_or_id work without AttributeError on sqlite3.Row."""
    from src.presentation.routes.presets import list_presets, get_preset_by_slug_or_id, create_preset, CreatePresetRequest
    from src.presentation.auth_deps import CurrentUser

    conn = get_dict_connection()
    try:
        conn.execute("DELETE FROM user_presets WHERE slug LIKE 'kopi-itam-01%'")
        conn.commit()
    finally:
        conn.close()

    dummy_user = CurrentUser(user_id=1, email="test@example.com", role="superadmin", permissions=["*"])

    # 1. Create a preset
    req = CreatePresetRequest(
        name="kopi itam 01",
        slug="",  # empty slug should auto-generate kopi-itam-01
        hook_style={"engine": "remotion", "animation": "hook_punch_center", "fontFamily": "Impact", "transitionStyle": "zoom"},
        subtitle_style={"engine": "remotion", "stylePreset": "bold_black", "highlightColor": "#FFE500"},
        text_emphasis_style={"effectMode": "hero_punch", "color": "#FFCC00"},
        watermark_style={"type": "text", "text": "@kopihitam", "opacity": 0.8},
        cta_style={"enabled": True, "template": "subscribe_cta", "duration": 4.0},
        broll_style={"enabled": True, "image_overlay": True, "behind_person": True, "video_footage": True, "autogrid_enabled": True},
    )

    create_res = await create_preset(req, user=dummy_user)
    assert create_res["success"] is True
    assert create_res["slug"] == "kopi-itam-01"
    preset_id = create_res["id"]

    # 2. Call list_presets (verifies sqlite3.Row has no .get() error)
    list_res = await list_presets(user=dummy_user)
    assert list_res["success"] is True
    assert any(p["slug"] == "kopi-itam-01" for p in list_res["data"])

    # 3. Call get_preset_by_slug_or_id with slug
    get_res = await get_preset_by_slug_or_id("kopi-itam-01", user=dummy_user)
    assert get_res["success"] is True
    data = get_res["data"]
    assert data["name"] == "kopi itam 01"
    assert data["slug"] == "kopi-itam-01"
    assert data["hook_style"]["transitionStyle"] == "zoom"
    assert data["broll_style"]["autogrid_enabled"] is True

    # 4. Resolve preset via preset_resolver
    resolved = resolve_preset("kopi-itam-01", user_id=1)
    assert resolved is not None
    assert resolved["transition_style"] == "zoom"
    assert resolved["broll_enabled"] is True
    assert resolved["autogrid_enabled"] is True
    assert resolved["hook_engine"] == "remotion"
    assert resolved["subtitle_engine"] == "remotion"

    # Cleanup
    conn = get_dict_connection()
    try:
        conn.execute("DELETE FROM user_presets WHERE slug LIKE 'kopi-itam-01%'")
        conn.commit()
    finally:
        conn.close()

