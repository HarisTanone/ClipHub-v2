import asyncio
import json
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
    assert updated["post_clips_count"] == 5

    # 2. Update post_clips_count specifically
    updated_qty = service.update_settings(user_id=user_id, data={"post_clips_count": 7})
    assert updated_qty["post_clips_count"] == 7

    # 3. Get settings
    fetched = service.get_settings(user_id=user_id)
    assert fetched["niche_query"] == "podcast motivasi indonesia"
    assert fetched["preset_slug"] == "gaming-vibe-01"
    assert fetched["post_clips_count"] == 7


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
         patch("src.infrastructure.hook_manifest.resolve_preset", return_value={
             "slug": "podcast-epic-v1",
             "source": "user_preset",
             "hook_style_config": {"font": "Impact", "color": "#FF0000", "engine": "remotion"},
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

@pytest.mark.asyncio
async def test_concurrent_autopilot_triggers_blocked_by_lock_and_reservation():
    """Verify that concurrent calls to run_autopilot_step are serialized and only 1 succeeds."""
    service = AutopilotService()
    user_id = 999
    service.update_settings(user_id=user_id, data={
        "enabled": 1,
        "niche_query": "bisnis",
        "preset_slug": "default",
    })

    candidate_video = {
        "id": "v_concurrent_01",
        "title": "Video Bisnis",
        "url": "https://youtube.com/watch?v=v_concurrent_01",
        "duration_sec": 600,
        "views": 10000,
        "virality_score": 85.0,
    }

    mock_job = MagicMock()
    mock_job.id = "job_concurrent_123"
    mock_job_service = MagicMock()

    # Simulate a slow creation so race window would occur without lock/reservation
    async def slow_create_job(*args, **kwargs):
        await asyncio.sleep(0.1)
        return mock_job

    mock_job_service.create_job = AsyncMock(side_effect=slow_create_job)

    with patch.object(service, "pick_best_candidate", return_value=candidate_video), \
         patch("src.infrastructure.preset_resolver.resolve_preset", return_value={"hook_style_config": {}}), \
         patch("src.presentation.dependencies.get_job_service", return_value=mock_job_service), \
         patch("src.infrastructure.telegram_service.TelegramService.send_message", new=AsyncMock()):

        # Fire 2 concurrent autopilot steps simultaneously
        res1, res2 = await asyncio.gather(
            service.run_autopilot_step(user_id=user_id, force=False, trigger_source="concurrent_1", notify_telegram=False),
            service.run_autopilot_step(user_id=user_id, force=False, trigger_source="concurrent_2", notify_telegram=False),
        )

        successes = [r for r in (res1, res2) if r.get("success")]
        failures = [r for r in (res1, res2) if not r.get("success")]

        # Exactly 1 should succeed, and 1 should be blocked by quota_exceeded
        assert len(successes) == 1
        assert len(failures) == 1
        assert failures[0].get("status") == "quota_exceeded"


def test_channel_playlist_settings_crud():
    """Test saving and retrieving channel/playlist specific autopilot settings."""
    service = AutopilotService()
    user_id = 99

    updated = service.update_settings(user_id=user_id, data={
        "source_mode": "channel_playlist",
        "channel_url": "https://www.youtube.com/@tempovideochannel",
        "channel_title": "Tempodotco",
        "source_type": "playlist",
        "selected_playlist_id": "PLkiSnq8pdz9T3QQVbczz4XVgsHjjJK3vd",
        "selected_playlist_title": "Bocor Alus Politik",
        "video_selection_strategy": "latest_2",
    })

    assert updated["source_mode"] == "channel_playlist"
    assert updated["channel_url"] == "https://www.youtube.com/@tempovideochannel"
    assert updated["channel_title"] == "Tempodotco"
    assert updated["source_type"] == "playlist"
    assert updated["selected_playlist_id"] == "PLkiSnq8pdz9T3QQVbczz4XVgsHjjJK3vd"
    assert updated["selected_playlist_title"] == "Bocor Alus Politik"
    assert updated["video_selection_strategy"] == "latest_2"

    fetched = service.get_settings(user_id=user_id)
    assert fetched["source_mode"] == "channel_playlist"
    assert fetched["selected_playlist_id"] == "PLkiSnq8pdz9T3QQVbczz4XVgsHjjJK3vd"
    assert fetched["selected_playlist_title"] == "Bocor Alus Politik"
    assert fetched["video_selection_strategy"] == "latest_2"


def test_normalize_youtube_input():
    """Test URL and handle normalization for channels and playlists."""
    service = AutopilotService()

    # Raw username handle
    r1 = service.normalize_youtube_input("tempovideochannel")
    assert r1["type"] == "channel_handle"
    assert r1["handle"] == "@tempovideochannel"
    assert r1["url"] == "https://www.youtube.com/@tempovideochannel"

    # Handle with @
    r2 = service.normalize_youtube_input("@tempovideochannel")
    assert r2["type"] == "channel_handle"
    assert r2["handle"] == "@tempovideochannel"

    # Full channel URL
    r3 = service.normalize_youtube_input("https://www.youtube.com/@tempovideochannel/playlists")
    assert r3["type"] == "channel_url"
    assert r3["handle"] == "@tempovideochannel"

    # Direct playlist URL
    r4 = service.normalize_youtube_input("https://www.youtube.com/playlist?list=PLkiSnq8pdz9T3QQVbczz4XVgsHjjJK3vd")
    assert r4["type"] == "playlist"
    assert r4["playlist_id"] == "PLkiSnq8pdz9T3QQVbczz4XVgsHjjJK3vd"

    # Watch URL with list param
    r5 = service.normalize_youtube_input("https://www.youtube.com/watch?v=xEWpw4UEN0o&list=PLkiSnq8pdz9T3QQVbczz4XVgsHjjJK3vd")
    assert r5["type"] == "playlist"
    assert r5["playlist_id"] == "PLkiSnq8pdz9T3QQVbczz4XVgsHjjJK3vd"


def test_inspect_channel_or_playlist_rejects_non_youtube_url():
    """"Channel URL" input is otherwise passed straight into a yt-dlp target
    with no domain restriction, which supports hundreds of sites plus a
    generic scraper. An authenticated user must not be able to make the
    server's yt-dlp subprocess fetch an arbitrary internal/external URL
    (SSRF via a seemingly-innocuous "inspect channel" feature)."""
    service = AutopilotService()
    for evil_url in (
        "https://169.254.169.254/latest/meta-data/",
        "http://internal-admin.local/secret",
        "https://evil.example.com/@fakehandle",
    ):
        with pytest.raises(ValueError, match="YouTube"):
            service.inspect_channel_or_playlist(evil_url)


def test_get_playlist_or_channel_videos_rejects_non_youtube_channel_url():
    """Defense in depth: channel_url also reaches this function directly from
    stored settings on every daily autopilot run (not just the one-off
    inspect step), so it must independently reject non-YouTube hosts too."""
    service = AutopilotService()
    result = service.get_playlist_or_channel_videos(channel_url="https://evil.example.com/channel")
    assert result["videos"] == []
    assert result["target_url"] == ""


def test_channel_playlist_candidate_selection_latest_2():
    """Test buffer 2 video strategy (processes vid 2 on day 1, then vid 1 on day 2)."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={
        "source_mode": "channel_playlist",
        "source_type": "playlist",
        "selected_playlist_id": "PL_sample_01",
        "video_selection_strategy": "latest_2",
        "min_duration_sec": 300,
        "max_duration_sec": 3600,
    })

    # Mock playlist of 10 videos (index 0 is vid1/newest, index 1 is vid2, ...)
    mock_videos = [
        {"id": f"vid{i}", "title": f"Video Title {i}", "url": f"https://www.youtube.com/watch?v=vid{i}", "duration_sec": 1200}
        for i in range(1, 11)
    ]

    # Day 1: Clean state -> should select vid2 (index 1) to build buffer
    with patch.object(service, "get_playlist_or_channel_videos", return_value={"videos": mock_videos, "title": "Mock Show"}), \
         patch.object(service, "get_processed_urls", return_value=set()):
        c1 = service.pick_best_candidate(user_id=user_id)
        assert c1 is not None
        assert c1["id"] == "vid2"

    # Day 2: vid2 was processed yesterday -> should now select vid1
    with patch.object(service, "get_playlist_or_channel_videos", return_value={"videos": mock_videos, "title": "Mock Show"}), \
         patch.object(service, "get_processed_urls", return_value={"vid2", "https://www.youtube.com/watch?v=vid2"}):
        c2 = service.pick_best_candidate(user_id=user_id)
        assert c2 is not None
        assert c2["id"] == "vid1"

    # Day 3: vid1 and vid2 both processed, no new uploads -> returns None (waits for fresh upload)
    with patch.object(service, "get_playlist_or_channel_videos", return_value={"videos": mock_videos, "title": "Mock Show"}), \
         patch.object(service, "get_processed_urls", return_value={"vid1", "vid2"}):
        c3 = service.pick_best_candidate(user_id=user_id)
        assert c3 is None

    # Day 4: Channel uploads vid0! Newest videos are now [vid0, vid1, vid2, ...]
    mock_videos_updated = [
        {"id": "vid0", "title": "Video 0 (Fresh)", "url": "https://www.youtube.com/watch?v=vid0", "duration_sec": 1200}
    ] + mock_videos

    with patch.object(service, "get_playlist_or_channel_videos", return_value={"videos": mock_videos_updated, "title": "Mock Show"}), \
         patch.object(service, "get_processed_urls", return_value={"vid1", "vid2"}):
        c4 = service.pick_best_candidate(user_id=user_id)
        assert c4 is not None
        assert c4["id"] == "vid0"


def test_all_playlist_strategy_fetches_deeper_pool_than_latest_strategies():
    """"all_playlist" (Antrean Backlog) processes the oldest unprocessed video
    across the WHOLE backlog, so it must fetch a deeper pool than the
    latest/latest_2 strategies (which only ever need the newest 1-2 videos).
    A shallow fetch here was the root cause of a reported bug where the
    client's "Target Hari Ini" preview (which mirrors this same fetch depth)
    showed a completely different video than what autopilot actually
    processed — the true oldest unprocessed video simply wasn't in the
    shallow window either side fetched."""
    service = AutopilotService()
    user_id = 99

    mock_fetch = MagicMock(return_value={"videos": [
        {"id": f"vid{i}", "title": f"Video {i}", "url": f"https://www.youtube.com/watch?v=vid{i}", "duration_sec": 1200}
        for i in range(1, 11)
    ], "title": "Mock Show"})

    with patch.object(service, "get_playlist_or_channel_videos", mock_fetch), \
         patch.object(service, "get_processed_urls", return_value=set()):
        service.update_settings(user_id=user_id, data={
            "source_mode": "channel_playlist", "source_type": "playlist",
            "selected_playlist_id": "PL_sample_01", "video_selection_strategy": "all_playlist",
        })
        service.pick_best_candidate(user_id=user_id)
        assert mock_fetch.call_args.kwargs["limit"] == 200

        service.update_settings(user_id=user_id, data={"video_selection_strategy": "latest_2"})
        service.pick_best_candidate(user_id=user_id)
        assert mock_fetch.call_args.kwargs["limit"] == 100


def test_channel_playlist_candidate_selection_latest_1():
    """Test always take latest video strategy (vid1 directly)."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={
        "source_mode": "channel_playlist",
        "source_type": "playlist",
        "selected_playlist_id": "PL_sample_01",
        "video_selection_strategy": "latest_1",
    })

    mock_videos = [
        {"id": f"vid{i}", "title": f"Video Title {i}", "url": f"https://www.youtube.com/watch?v=vid{i}", "duration_sec": 1200}
        for i in range(1, 11)
    ]

    # Day 1: directly selects vid1
    with patch.object(service, "get_playlist_or_channel_videos", return_value={"videos": mock_videos, "title": "Mock Show"}), \
         patch.object(service, "get_processed_urls", return_value=set()):
        c1 = service.pick_best_candidate(user_id=user_id)
        assert c1 is not None
        assert c1["id"] == "vid1"

    # Day 2: vid1 is processed -> returns None (waits for fresh release)
    with patch.object(service, "get_playlist_or_channel_videos", return_value={"videos": mock_videos, "title": "Mock Show"}), \
         patch.object(service, "get_processed_urls", return_value={"vid1"}):
        c2 = service.pick_best_candidate(user_id=user_id)
        assert c2 is None


def test_processed_urls_ignores_failed_jobs():
    """Verify failed or timeout jobs do not falsely mark videos as processed."""
    service = AutopilotService()
    conn = get_dict_connection()
    try:
        # Insert a completed job and a failed job
        conn.execute("""
            INSERT OR REPLACE INTO jobs (
                job_id, youtube_url, status, clips_total, clips_success, clips_failed,
                style_preset, target_aspect_ratio, hook_engine, hook_style, broll_enabled, autogrid_enabled, created_at, updated_at
            ) VALUES (
                'job_pass_01', 'https://www.youtube.com/watch?v=goodvid1234', 'completed', 0, 0, 0,
                'default', '9:16', 'v3', '', 1, 0, datetime('now'), datetime('now')
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO jobs (
                job_id, youtube_url, status, clips_total, clips_success, clips_failed,
                style_preset, target_aspect_ratio, hook_engine, hook_style, broll_enabled, autogrid_enabled, created_at, updated_at
            ) VALUES (
                'job_fail_01', 'https://www.youtube.com/watch?v=badvid12345', 'failed', 0, 0, 0,
                'default', '9:16', 'v3', '', 1, 0, datetime('now'), datetime('now')
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO jobs (
                job_id, youtube_url, status, clips_total, clips_success, clips_failed,
                style_preset, target_aspect_ratio, hook_engine, hook_style, broll_enabled, autogrid_enabled, created_at, updated_at
            ) VALUES (
                'job_time_01', 'https://www.youtube.com/watch?v=timevid1234', 'timeout', 0, 0, 0,
                'default', '9:16', 'v3', '', 1, 0, datetime('now'), datetime('now')
            )
        """)
        conn.commit()

        processed = service.get_processed_urls()
        assert "goodvid1234" in processed
        assert "badvid12345" not in processed
        assert "timevid1234" not in processed
    finally:
        conn.execute("DELETE FROM jobs WHERE job_id IN ('job_pass_01', 'job_fail_01', 'job_time_01')")
        conn.commit()
        conn.close()


def test_channel_playlist_manual_target_override():
    """Verify user can explicitly set a manual target video."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={
        "source_mode": "channel_playlist",
        "source_type": "playlist",
        "selected_playlist_id": "PL_sample_01",
        "video_selection_strategy": "latest_2",
        "manual_target_video_id": "vid5",
    })

    mock_videos = [
        {"id": f"vid{i}", "title": f"Video Title {i}", "url": f"https://www.youtube.com/watch?v=vid{i}", "duration_sec": 1200}
        for i in range(1, 11)
    ]

    with patch.object(service, "get_playlist_or_channel_videos", return_value={"videos": mock_videos, "title": "Mock Show"}), \
         patch.object(service, "get_processed_urls", return_value=set()):
        cand = service.pick_best_candidate(user_id=user_id)
        assert cand is not None
        assert cand["id"] == "vid5"


@pytest.mark.asyncio
async def test_manual_target_video_id_cleared_after_successful_run():
    """A manual target is a one-shot pin: pick_candidate_from_channel_or_playlist
    returns it unconditionally, bypassing processed_urls dedup entirely. If it
    is never cleared after the pinned video is actually submitted as a job,
    every future run keeps re-picking (and re-bypassing dedup for) that same
    video forever instead of resuming the configured strategy."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={
        "enabled": 1,
        "source_mode": "channel_playlist",
        "source_type": "playlist",
        "selected_playlist_id": "PL_sample_01",
        "video_selection_strategy": "latest_2",
        "manual_target_video_id": "vid_pinned",
    })

    candidate_video = {
        "id": "vid_pinned",
        "title": "Manually Pinned Video",
        "url": "https://www.youtube.com/watch?v=vid_pinned",
        "uploader": "Podcast Channel",
        "duration_sec": 1200,
        "views": 10000,
        "virality_score": 85.0,
    }

    mock_job = MagicMock()
    mock_job.id = "job_pinned_123"
    mock_job_service = MagicMock()
    mock_job_service.create_job = AsyncMock(return_value=mock_job)

    with patch.object(service, "pick_best_candidate", return_value=candidate_video), \
         patch("src.infrastructure.preset_resolver.resolve_preset", return_value={
             "hook_style_config": {}, "subtitle_style_config": {},
             "text_emphasis_style_config": {}, "text_emphasis_enabled": False,
             "watermark_config": {}, "cta_config": {},
         }), \
         patch("src.infrastructure.hook_manifest.resolve_preset", return_value={
             "slug": "default", "source": "user_preset",
             "hook_style_config": {"engine": "remotion"},
         }), \
         patch("src.presentation.dependencies.get_job_service", return_value=mock_job_service), \
         patch("src.infrastructure.telegram_service.TelegramService.send_message", new=AsyncMock()):
        res = await service.run_autopilot_step(
            user_id=user_id, force=False, trigger_source="cron", notify_telegram=False,
        )
        assert res["success"] is True

    settings_after = service.get_settings(user_id)
    assert settings_after["manual_target_video_id"] == ""


def test_inspect_channel_or_playlist_single_entry_not_multi():
    """A single (no-comma) query must keep behaving exactly as before: is_multi=False
    and a 1-item "channels" mirror that does NOT self-reference the outer dict (which
    would break JSON serialization of the API response)."""
    service = AutopilotService()
    fake_result = {
        "channel_title": "Solo Channel", "channel_url": "https://www.youtube.com/@solo",
        "channel_handle": "@solo", "is_direct_playlist": False, "direct_playlist": None,
        "playlists": [{"id": "p1", "title": "PL 1", "type": "playlist", "url": "u", "thumbnail": ""}],
        "has_channel_videos": True,
    }
    with patch.object(service, "_inspect_single_channel_or_playlist", return_value=fake_result) as mock_single:
        result = service.inspect_channel_or_playlist("@solo")

    mock_single.assert_called_once_with("@solo")
    assert result["is_multi"] is False
    assert len(result["channels"]) == 1
    assert result["channels"][0]["channel_title"] == "Solo Channel"
    assert result["channels"][0] is not result  # no self-reference / circular dict
    assert result["playlists"] == fake_result["playlists"]
    json.dumps(result)  # must not raise on circular reference


def test_inspect_channel_or_playlist_multi_aggregates():
    """Comma-separated channels are each inspected independently and aggregated;
    the first channel's info is mirrored at the top level for backward compatibility,
    and playlist drill-down is intentionally empty since it doesn't carry meaning
    across several distinct channels at once."""
    service = AutopilotService()

    def fake_single(query):
        if query == "@chanA":
            return {
                "channel_title": "Channel A", "channel_url": "https://www.youtube.com/@chanA",
                "channel_handle": "@chanA", "is_direct_playlist": False, "direct_playlist": None,
                "playlists": [{"id": "p1", "title": "PL A", "type": "playlist", "url": "u", "thumbnail": ""}],
                "has_channel_videos": True,
            }
        if query == "@chanB":
            return {
                "channel_title": "Channel B", "channel_url": "https://www.youtube.com/@chanB",
                "channel_handle": "@chanB", "is_direct_playlist": False, "direct_playlist": None,
                "playlists": [], "has_channel_videos": True,
            }
        raise ValueError("URL harus berupa link channel atau playlist YouTube yang valid")

    with patch.object(service, "_inspect_single_channel_or_playlist", side_effect=fake_single):
        result = service.inspect_channel_or_playlist("@chanA, @chanB")

    assert result["is_multi"] is True
    assert len(result["channels"]) == 2
    assert result["channel_title"] == "Channel A, Channel B"
    assert result["channel_url"] == "https://www.youtube.com/@chanA, https://www.youtube.com/@chanB"
    assert result["playlists"] == []
    json.dumps(result)


def test_inspect_channel_or_playlist_multi_skips_invalid_entries():
    """One bad entry among several comma-separated channels shouldn't fail the whole
    request — it's skipped (reported in "errors") and the valid ones still aggregate."""
    service = AutopilotService()

    def fake_single(query):
        if query == "@good":
            return {
                "channel_title": "Good Channel", "channel_url": "https://www.youtube.com/@good",
                "channel_handle": "@good", "is_direct_playlist": False, "direct_playlist": None,
                "playlists": [], "has_channel_videos": True,
            }
        raise ValueError("URL harus berupa link channel atau playlist YouTube yang valid")

    with patch.object(service, "_inspect_single_channel_or_playlist", side_effect=fake_single):
        result = service.inspect_channel_or_playlist("@good, https://evil.example.com/channel")

    assert result["is_multi"] is True
    assert len(result["channels"]) == 1
    assert result["channel_title"] == "Good Channel"
    assert len(result["errors"]) == 1
    assert result["errors"][0]["query"] == "https://evil.example.com/channel"


def test_get_playlist_or_channel_videos_dispatches_to_multi_channel_on_comma():
    """channel_url with a comma must delegate to the multi-channel merge path instead
    of being treated (and rejected) as a single malformed URL."""
    service = AutopilotService()
    with patch.object(service, "_get_multi_channel_videos", return_value={"videos": [], "is_multi": True}) as mock_multi:
        service.get_playlist_or_channel_videos(
            channel_url="https://www.youtube.com/@a, https://www.youtube.com/@b", limit=50,
        )
    mock_multi.assert_called_once()
    called_urls = mock_multi.call_args.args[0]
    assert called_urls == ["https://www.youtube.com/@a", "https://www.youtube.com/@b"]
    assert mock_multi.call_args.kwargs["limit"] == 50


def test_get_multi_channel_videos_round_robin_merge():
    """Multiple channels' uploads must interleave (not concatenate), since per-channel
    order reflects upload recency but there's no shared timestamp to sort globally."""
    service = AutopilotService()

    def fake_fetch(channel_url=None, playlist_id=None, limit=50, user_id=None):
        if channel_url == "https://www.youtube.com/@chanA":
            videos = [
                {"id": f"a{i}", "url": f"https://www.youtube.com/watch?v=a{i}", "duration_sec": 100}
                for i in range(3)
            ]
            return {"title": "Channel A", "videos": videos, "total": 3}
        if channel_url == "https://www.youtube.com/@chanB":
            videos = [
                {"id": f"b{i}", "url": f"https://www.youtube.com/watch?v=b{i}", "duration_sec": 100}
                for i in range(2)
            ]
            return {"title": "Channel B", "videos": videos, "total": 2}
        return {"title": "", "videos": [], "total": 0}

    with patch.object(service, "get_playlist_or_channel_videos", side_effect=fake_fetch):
        result = service._get_multi_channel_videos(
            ["https://www.youtube.com/@chanA", "https://www.youtube.com/@chanB"], limit=50,
        )

    assert [v["id"] for v in result["videos"]] == ["a0", "b0", "a1", "b1", "a2"]
    assert result["is_multi"] is True
    assert result["total"] == 5
    assert result["title"] == "Channel A, Channel B"


def test_pick_best_candidate_ai_discovery_multi_keyword_searches_each_keyword():
    """niche_query with several comma-separated keywords must search each one and
    merge results into a single candidate pool: once the first keyword's only video
    is already processed, the second keyword must still be tried instead of giving up."""
    service = AutopilotService()
    user_id = 99
    service.update_settings(user_id=user_id, data={
        "niche_query": "podcast politik, podcast humor",
    })

    def fake_search(query, limit=8):
        if query.startswith("podcast politik"):
            return [{
                "id": "vid_politik", "title": "Politik Terbaru",
                "url": "https://youtube.com/watch?v=vid_politik", "uploader": "ChP",
                "duration_sec": 1200, "views": 50000, "virality_score": 80.0,
            }]
        if query.startswith("podcast humor"):
            return [{
                "id": "vid_humor", "title": "Humor Segar",
                "url": "https://youtube.com/watch?v=vid_humor", "uploader": "ChH",
                "duration_sec": 1200, "views": 70000, "virality_score": 90.0,
            }]
        return []

    searched_queries = []

    def tracking_search(query, limit=8):
        searched_queries.append(query)
        return fake_search(query, limit)

    with patch.object(service, "search_viral_videos", side_effect=tracking_search), \
         patch.object(service, "get_processed_urls", return_value={"vid_politik"}):
        candidate = service.pick_best_candidate(user_id=user_id)

    assert candidate is not None
    assert candidate["id"] == "vid_humor"
    assert any(q.startswith("podcast politik") for q in searched_queries)
    assert any(q.startswith("podcast humor") for q in searched_queries)







