"""Automated Tests for Hermes Autopilot Service, Daily Quota (1 video/day), and Auto-Post Pipeline."""
import pytest
import datetime as dt
from unittest.mock import patch, AsyncMock, MagicMock

from src.infrastructure.autopilot_service import AutopilotService, autopilot_service
from src.infrastructure.db_connection import get_dict_connection


@pytest.fixture(autouse=True)
def clean_autopilot_tables():
    """Ensure clean state for autopilot tests in SQLite."""
    conn = get_dict_connection()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS autopilot_runs (id INTEGER PRIMARY KEY, user_id INTEGER, run_date TEXT, youtube_url TEXT, video_title TEXT, virality_score REAL, job_id TEXT, status TEXT, clips_count INTEGER, posts_scheduled INTEGER, trigger_source TEXT, error_message TEXT, created_at DATETIME)")
        conn.execute("DELETE FROM autopilot_runs")
        conn.execute("DELETE FROM autopilot_settings WHERE user_id = 99")
        conn.commit()
    finally:
        conn.close()


def test_autopilot_settings_crud():
    """Test getting and updating autopilot settings."""
    service = AutopilotService()
    user_id = 99

    # 1. Update settings
    updated = service.update_settings(user_id=user_id, data={
        "enabled": 1,
        "niche_query": "podcast motivasi indonesia",
        "preset_slug": "gaming-vibe-01",
        "target_platforms": "tiktok,instagram",
        "target_account_ids": ["acc_tt_1", "acc_ig_1"],
        "schedule_mode": "ai",
        "run_time": "09:30",
        "min_duration_sec": 600,
        "max_duration_sec": 2400,
    })

    assert updated["enabled"] is True
    assert updated["niche_query"] == "podcast motivasi indonesia"
    assert updated["preset_slug"] == "gaming-vibe-01"
    assert updated["target_platforms"] == "tiktok,instagram"
    assert updated["target_account_ids"] == ["acc_tt_1", "acc_ig_1"]
    assert updated["run_time"] == "09:30"
    assert updated["max_daily_videos"] == 1

    # 2. Get settings
    fetched = service.get_settings(user_id=user_id)
    assert fetched["niche_query"] == "podcast motivasi indonesia"
    assert fetched["preset_slug"] == "gaming-vibe-01"


def test_strict_daily_quota_one_video_per_day():
    """Test strict 1-video/day quota enforcement."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={"enabled": 1, "max_daily_videos": 1})

    today_str = dt.date.today().isoformat()

    # Before any run today
    can_run, reason, info = service.can_run_today(user_id=user_id)
    assert can_run is True
    assert info["today_runs"] == 0
    assert info["max_daily_videos"] == 1

    # Simulate 1 completed run today
    conn = get_dict_connection()
    try:
        conn.execute("""
            INSERT INTO autopilot_runs (user_id, run_date, youtube_url, video_title, job_id, status)
            VALUES (?, ?, 'https://youtube.com/watch?v=vid123', 'Test Video 1', 'job_001', 'submitted')
        """, (user_id, today_str))
        conn.commit()
    finally:
        conn.close()

    # Check quota again on same day
    can_run_after, reason_after, info_after = service.can_run_today(user_id=user_id)
    assert can_run_after is False
    assert "Kuota harian terpenuhi" in reason_after
    assert info_after["today_runs"] == 1


def test_candidate_selection_and_deduplication():
    """Test candidate picking with duration filtering and deduplication."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={
        "niche_query": "gym motivation",
        "min_duration_sec": 600,  # 10 min
        "max_duration_sec": 3000, # 50 min
    })

    sample_search_results = [
        # Video 1: Too short (5 min = 300s)
        {"id": "v_short", "title": "Short Video", "url": "https://youtube.com/watch?v=v_short", "uploader": "Ch1", "duration_sec": 300, "views": 100000, "virality_score": 95.0},
        # Video 2: Already processed in past
        {"id": "v_processed", "title": "Old Processed", "url": "https://youtube.com/watch?v=v_processed", "uploader": "Ch2", "duration_sec": 1200, "views": 80000, "virality_score": 90.0},
        # Video 3: Valid fresh candidate
        {"id": "v_valid", "title": "Fresh Gym Podcast", "url": "https://youtube.com/watch?v=v_valid", "uploader": "Ch3", "duration_sec": 1500, "views": 60000, "virality_score": 85.0},
    ]

    with patch.object(service, "search_viral_videos", return_value=sample_search_results), \
         patch.object(service, "get_processed_urls", return_value={"https://youtube.com/watch?v=v_processed", "v_processed"}):

        candidate = service.pick_best_candidate(user_id=user_id)
        assert candidate is not None
        assert candidate["id"] == "v_valid"
        assert candidate["title"] == "Fresh Gym Podcast"


@pytest.mark.asyncio
async def test_run_autopilot_step_success():
    """Test full execution of autopilot step submitting job with preset and auto-post flags."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={
        "enabled": 1,
        "niche_query": "podcast bisnis",
        "preset_slug": "podcast-epic-v1",
        "target_platforms": "tiktok,youtube",
        "schedule_mode": "ai",
    })

    candidate_video = {
        "id": "v_biz_01",
        "title": "Bisnis Anak Muda Viral",
        "url": "https://youtube.com/watch?v=v_biz_01",
        "uploader": "Podcast Channel",
        "duration_sec": 1800,
        "views": 250000,
        "virality_score": 92.0,
    }

    mock_job = MagicMock()
    mock_job.id = "job_autopilot_777"

    mock_job_service = MagicMock()
    mock_job_service.create_job = AsyncMock(return_value=mock_job)

    with patch.object(service, "pick_best_candidate", return_value=candidate_video), \
         patch("src.infrastructure.preset_resolver.resolve_preset", return_value={
             "hook_style_config": {"font": "Impact", "color": "#FF0000"},
             "subtitle_style_config": {"stylePreset": "bold_black"},
             "text_emphasis_style_config": {"effect": "hero_punch"},
             "text_emphasis_enabled": True,
             "watermark_config": {"text": "@cliphub"},
             "cta_config": {"template": "subscribe_cta"},
         }), \
         patch("src.presentation.dependencies.get_job_service", return_value=mock_job_service), \
         patch("src.infrastructure.telegram_service.TelegramService.send_message", new=AsyncMock()):

        # 1. First run should succeed
        res = await service.run_autopilot_step(
            user_id=user_id,
            force=False,
            trigger_source="cron",
            notify_telegram=False,
        )

        assert res["success"] is True
        assert res["job_id"] == "job_autopilot_777"
        assert res["video"]["title"] == "Bisnis Anak Muda Viral"

        # 2. Second run on same day without force should be blocked
        res2 = await service.run_autopilot_step(
            user_id=user_id,
            force=False,
            trigger_source="cron",
            notify_telegram=False,
        )
        assert res2["success"] is False
        assert res2["status"] == "quota_exceeded"
        assert "Kuota harian terpenuhi" in res2["message"]


def test_hermes_cli_script_integration():
    """Test ops/hermes/bin/ac_autopilot.py helper methods."""
    import sys
    import importlib.util
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    hermes_bin = str(repo_root / "ops" / "hermes" / "bin")
    if hermes_bin not in sys.path:
        sys.path.insert(0, hermes_bin)

    cli_path = str(repo_root / "ops" / "hermes" / "bin" / "ac_autopilot.py")
    spec = importlib.util.spec_from_file_location("ac_autopilot", cli_path)
    cli_mod = importlib.util.module_from_spec(spec)

    with patch("ac_auth.api_get", return_value={"success": True, "data": {"enabled": True}}), \
         patch("ac_auth.api_post", return_value={"success": True, "job_id": "job_123"}):
        spec.loader.exec_module(cli_mod)
        status_res = cli_mod.get_status()
        assert status_res["success"] is True

        run_res = cli_mod.trigger_run(force=False)
        assert run_res["success"] is True


@pytest.mark.asyncio
async def test_autopilot_user_isolation_and_busy_check():
    """Test user isolation and pipeline busy deferral."""
    service = AutopilotService()
    
    # 1. User 100 has not configured autopilot -> must be disabled by default
    user_100_settings = service.get_settings(user_id=100)
    assert user_100_settings["enabled"] is False
    assert user_100_settings["user_id"] == 100

    # 2. Disabled user cannot run unless force=True
    res_disabled = await service.run_autopilot_step(user_id=100, force=False)
    assert res_disabled["success"] is False
    assert res_disabled["status"] == "disabled"

    # 3. User 101 enables autopilot
    service.update_settings(user_id=101, data={"enabled": 1, "niche_query": "sains"})
    user_101_settings = service.get_settings(user_id=101)
    assert user_101_settings["enabled"] is True

    # 4. Pipeline busy check -> defers execution
    with patch.object(service, "is_pipeline_busy", return_value=True):
        res_busy = await service.run_autopilot_step(user_id=101, force=False)
        assert res_busy["success"] is False
        assert res_busy["status"] == "pipeline_busy"
        assert "Server sedang memproses video lain" in res_busy["message"]


@pytest.mark.asyncio
async def test_autopilot_resolves_active_preset():
    """Test that autopilot automatically resolves user's active preset from user_settings/user_presets."""
    from src.infrastructure.preset_resolver import resolve_preset
    from src.infrastructure.db_connection import get_dict_connection

    # Setup a mock custom preset in user_presets for user 2
    conn = get_dict_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO user_presets (id, user_id, name, slug, hook_style, subtitle_style, broll_style)
            VALUES (888, 2, 'Active Niche Style', 'active-niche-style', '{"animation":"fade"}', '{"position":"top"}', '{"enabled":true,"autogrid_enabled":false}')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO user_settings (user_id, default_style_preset)
            VALUES (2, 'active-niche-style')
        """)
        conn.commit()
    finally:
        conn.close()

    # 1. Resolving 'active' or 'default' for user 2 returns the active preset
    resolved = resolve_preset("active", user_id=2)
    assert resolved is not None
    assert resolved["slug"] == "active-niche-style"
    assert resolved["name"] == "Active Niche Style"
    assert resolved["broll_enabled"] is True
    assert resolved["autogrid_enabled"] is False

    # 2. Run autopilot step with preset_override='active' passes resolved preset configs
    service = AutopilotService()
    service.update_settings(user_id=2, data={"enabled": 1, "preset_slug": "active"})

    mock_candidate = {
        "url": "https://www.youtube.com/watch?v=mock_active_pres",
        "title": "Mock Video Active Preset",
        "duration_sec": 600,
        "id": "mock_active_pres",
        "virality_score": 85.0,
    }

    mock_job = MagicMock()
    mock_job.id = "job_active_pres_999"

    mock_job_service = AsyncMock()
    mock_job_service.create_job.return_value = (mock_job, False)

    with patch.object(service, "pick_best_candidate", return_value=mock_candidate), \
         patch("src.presentation.dependencies.get_job_service", return_value=mock_job_service):

        res = await service.run_autopilot_step(user_id=2, force=True, notify_telegram=False)
        assert res["success"] is True
        assert res["preset_slug"] == "active-niche-style"

        # Check create_job call args
        _, kwargs = mock_job_service.create_job.call_args
        assert kwargs["style_preset"] == "active-niche-style"
        assert kwargs["broll_enabled"] is True
        assert kwargs["autogrid_enabled"] is False


@pytest.mark.asyncio
async def test_autopilot_global_preset_resolution_across_users():
    """Test that Autopilot (run as user 1 / admin) can resolve presets created by other users (e.g. user 2)."""
    from src.infrastructure.preset_resolver import resolve_preset
    from src.infrastructure.db_connection import get_dict_connection

    conn = get_dict_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO user_presets (id, user_id, name, slug, hook_style, subtitle_style, broll_style)
            VALUES (909, 2, 'Cross User Style', 'cross-user-style-909', '{"animation":"slide_up"}', '{"stylePreset":"neon_pulse"}', '{"enabled":true}')
        """)
        conn.commit()
    finally:
        conn.close()

    # User 1 resolves preset owned by user 2 -> must succeed via global fallback
    resolved = resolve_preset("cross-user-style-909", user_id=1)
    assert resolved is not None
    assert resolved["slug"] == "cross-user-style-909"
    assert resolved["name"] == "Cross User Style"
    assert resolved["hook_style_config"]["animation"] == "slide_up"
    assert resolved["subtitle_style_config"]["stylePreset"] == "neon_pulse"
    assert resolved["broll_enabled"] is True


def test_preset_default_style_parity_with_preview():
    """Verify that even sparse preset JSON gets merged with full visual defaults matching AutopilotPresetPreview."""
    from src.infrastructure.preset_resolver import resolve_preset, DEFAULT_HOOK_STYLE, DEFAULT_SUBTITLE_STYLE
    from src.infrastructure.db_connection import get_dict_connection

    conn = get_dict_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO user_presets (id, user_id, name, slug, hook_style, subtitle_style)
            VALUES (910, 1, 'Sparse Preset', 'sparse-preset-910', '{"animation":"glitch"}', '{"highlightColor":"#FF0055"}')
        """)
        conn.commit()
    finally:
        conn.close()

    resolved = resolve_preset("sparse-preset-910", user_id=1)
    assert resolved is not None
    # Overridden values
    assert resolved["hook_style_config"]["animation"] == "glitch"
    assert resolved["subtitle_style_config"]["highlightColor"] == "#FF0055"
    # Merged default values (100% parity with preview)
    assert resolved["hook_style_config"]["fontFamily"] == DEFAULT_HOOK_STYLE["fontFamily"]
    assert resolved["hook_style_config"]["fontSize"] == DEFAULT_HOOK_STYLE["fontSize"]
    assert resolved["hook_style_config"]["badgeText"] == DEFAULT_HOOK_STYLE["badgeText"]
    assert resolved["subtitle_style_config"]["fontFamily"] == DEFAULT_SUBTITLE_STYLE["fontFamily"]
    assert resolved["subtitle_style_config"]["fontSize"] == DEFAULT_SUBTITLE_STYLE["fontSize"]
    assert resolved["subtitle_style_config"]["strokeWidth"] == DEFAULT_SUBTITLE_STYLE["strokeWidth"]
    assert resolved["subtitle_style_config"]["shadowBlur"] == DEFAULT_SUBTITLE_STYLE["shadowBlur"]
    assert resolved["subtitle_style_config"]["bgRadius"] == DEFAULT_SUBTITLE_STYLE["bgRadius"]


def test_hermes_cli_set_preset():
    """Test ac_autopilot.set_preset helper."""
    import importlib.util
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    cli_path = str(repo_root / "ops" / "hermes" / "bin" / "ac_autopilot.py")
    spec = importlib.util.spec_from_file_location("ac_autopilot_set", cli_path)
    cli_mod = importlib.util.module_from_spec(spec)

    with patch("ac_auth.api_post", return_value={"success": True, "data": {"preset_slug": "neon-glow-01"}}):
        spec.loader.exec_module(cli_mod)
        res = cli_mod.set_preset("neon-glow-01")
        assert res["success"] is True
        assert res["data"]["preset_slug"] == "neon-glow-01"




