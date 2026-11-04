"""Hermes Autopilot Service — Autonomous Daily Video Discovery & Auto-Post.

Enforces:
- Strict 1 video URL per calendar day quota per user.
- Autonomous viral search and virality-based candidate selection.
- Deduplication against previous jobs and autopilot runs.
- Automatic submission with complete 5-layer visual preset.
- Social media auto-post scheduling at Peak Hours or custom time.
- Rich Telegram reporting.
"""
import os
import re
import json
import logging
import asyncio
import datetime as dt
import subprocess
from typing import Any, Optional

from src.infrastructure.db_connection import get_dict_connection

logger = logging.getLogger(__name__)

YTDLP_TIMEOUT = int(os.environ.get("YTDLP_SEARCH_TIMEOUT", "45"))


class AutopilotService:
    def __init__(self):
        self._run_lock = asyncio.Lock()
        self._last_scheduled_runs: dict[tuple[int, str], bool] = {}
        self._ensure_tables()


    def _ensure_tables(self):
        """Ensure autopilot_settings and autopilot_runs tables exist."""
        conn = get_dict_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    source_mode TEXT NOT NULL DEFAULT 'ai',
                    channel_url TEXT DEFAULT '',
                    channel_title TEXT DEFAULT '',
                    source_type TEXT DEFAULT 'channel_videos',
                    selected_playlist_id TEXT DEFAULT '',
                    selected_playlist_title TEXT DEFAULT '',
                    video_selection_strategy TEXT NOT NULL DEFAULT 'latest_2',
                    niche_query TEXT NOT NULL DEFAULT 'podcast bisnis',
                    preset_slug TEXT NOT NULL DEFAULT 'default',
                    target_platforms TEXT NOT NULL DEFAULT 'tiktok,instagram,youtube',
                    target_account_ids TEXT NOT NULL DEFAULT '[]',
                    schedule_mode TEXT NOT NULL DEFAULT 'ai',
                    custom_schedule_time TEXT DEFAULT '',
                    run_time TEXT NOT NULL DEFAULT '05:00',
                    min_duration_sec INTEGER NOT NULL DEFAULT 480,
                    max_duration_sec INTEGER NOT NULL DEFAULT 3600,
                    max_daily_videos INTEGER NOT NULL DEFAULT 1,
                    post_clips_count INTEGER NOT NULL DEFAULT 5,
                    last_run_at TEXT DEFAULT NULL,
                    last_job_id TEXT DEFAULT NULL,
                    last_video_url TEXT DEFAULT NULL,
                    last_video_title TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migrations: ensure columns exist in existing databases
            for col_name, col_def in [
                ("post_clips_count", "INTEGER NOT NULL DEFAULT 5"),
                ("source_mode", "TEXT NOT NULL DEFAULT 'ai'"),
                ("channel_url", "TEXT DEFAULT ''"),
                ("channel_title", "TEXT DEFAULT ''"),
                ("source_type", "TEXT DEFAULT 'channel_videos'"),
                ("selected_playlist_id", "TEXT DEFAULT ''"),
                ("selected_playlist_title", "TEXT DEFAULT ''"),
                ("video_selection_strategy", "TEXT NOT NULL DEFAULT 'latest_2'"),
                ("manual_target_video_id", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE autopilot_settings ADD COLUMN {col_name} {col_def}")
                    conn.commit()
                except Exception:
                    pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    run_date TEXT NOT NULL,
                    youtube_url TEXT NOT NULL,
                    video_title TEXT NOT NULL,
                    virality_score REAL DEFAULT 0,
                    job_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    clips_count INTEGER DEFAULT 0,
                    posts_scheduled INTEGER DEFAULT 0,
                    trigger_source TEXT DEFAULT 'cron',
                    error_message TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Seed default settings for user 1 if not exists
            cur = conn.cursor()
            cur.execute("SELECT id FROM autopilot_settings WHERE user_id = 1")
            if not cur.fetchone():
                conn.execute("""
                    INSERT INTO autopilot_settings (
                        user_id, enabled, niche_query, preset_slug, target_platforms,
                        target_account_ids, schedule_mode, run_time, max_daily_videos
                    ) VALUES (
                        1, 0, 'podcast bisnis', 'default', 'tiktok,instagram,youtube',
                        '[]', 'ai', '08:00', 1
                    )
                """)
            conn.commit()
        except Exception as e:
            logger.error(f"Failed ensuring autopilot tables: {e}")
        finally:
            conn.close()

    def is_pipeline_busy(self) -> bool:
        """Check if any video clipping/rendering job is currently in progress across the system."""
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as active_cnt
                FROM jobs
                WHERE status NOT IN ('completed', 'failed', 'timeout')
            """)
            row = cur.fetchone()
            return bool(row and (row.get("active_cnt") or 0) > 0)
        except Exception as e:
            logger.debug(f"is_pipeline_busy check error: {e}")
            return False
        finally:
            conn.close()

    def get_settings(self, user_id: int = 1) -> dict:
        """Get autopilot configuration for specific user (strict user isolation)."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM autopilot_settings WHERE user_id = ?", (user_id,))
            row = cur.fetchone()

            if not row:
                # Strictly return default disabled settings for this specific user
                return {
                    "id": None,
                    "user_id": user_id,
                    "enabled": False,
                    "source_mode": "ai",
                    "channel_url": "",
                    "channel_title": "",
                    "source_type": "channel_videos",
                    "selected_playlist_id": "",
                    "selected_playlist_title": "",
                    "video_selection_strategy": "latest_2",
                    "manual_target_video_id": "",
                    "niche_query": "podcast bisnis",
                    "preset_slug": "default",
                    "target_platforms": "tiktok,instagram,youtube",
                    "target_account_ids": [],
                    "schedule_mode": "ai",
                    "custom_schedule_time": "",
                    "run_time": "05:00",
                    "min_duration_sec": 480,
                    "max_duration_sec": 3600,
                    "max_daily_videos": 1,
                    "post_clips_count": 5,
                    "last_run_at": None,
                    "last_job_id": None,
                    "last_video_url": None,
                    "last_video_title": None,
                    "updated_at": None,
                }

            r = dict(row)
            try:
                acc_ids = json.loads(r.get("target_account_ids") or "[]")
            except Exception:
                acc_ids = []

            return {
                "id": r.get("id"),
                "user_id": r.get("user_id", user_id),
                "enabled": bool(r.get("enabled")),
                "source_mode": str(r.get("source_mode") or "ai"),
                "channel_url": str(r.get("channel_url") or ""),
                "channel_title": str(r.get("channel_title") or ""),
                "source_type": str(r.get("source_type") or "channel_videos"),
                "selected_playlist_id": str(r.get("selected_playlist_id") or ""),
                "selected_playlist_title": str(r.get("selected_playlist_title") or ""),
                "video_selection_strategy": str(r.get("video_selection_strategy") or "latest_2"),
                "manual_target_video_id": str(r.get("manual_target_video_id") or ""),
                "niche_query": r.get("niche_query", "podcast bisnis"),
                "preset_slug": r.get("preset_slug", "default"),
                "target_platforms": r.get("target_platforms", "tiktok,instagram,youtube"),
                "target_account_ids": acc_ids,
                "schedule_mode": r.get("schedule_mode", "ai"),
                "custom_schedule_time": r.get("custom_schedule_time") or "",
                "run_time": r.get("run_time", "05:00"),
                "min_duration_sec": r.get("min_duration_sec", 480),
                "max_duration_sec": r.get("max_duration_sec", 3600),
                "max_daily_videos": r.get("max_daily_videos", 1),
                "post_clips_count": int(r.get("post_clips_count", 5) or 5),
                "last_run_at": r.get("last_run_at"),
                "last_job_id": r.get("last_job_id"),
                "last_video_url": r.get("last_video_url"),
                "last_video_title": r.get("last_video_title"),
                "updated_at": r.get("updated_at"),
            }
        finally:
            conn.close()

    def update_settings(self, user_id: int, data: dict) -> dict:
        """Update autopilot configuration for user with safe partial updates."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM autopilot_settings WHERE user_id = ?", (user_id,))
            exists_row = cur.fetchone()

            now_str = dt.datetime.now(dt.timezone.utc).isoformat()

            if exists_row:
                curr = dict(exists_row)
                enabled = int(data["enabled"]) if "enabled" in data else int(curr.get("enabled", 0))
                source_mode = str(data.get("source_mode", curr.get("source_mode", "ai"))).strip() or "ai"
                channel_url = str(data.get("channel_url", curr.get("channel_url", ""))).strip()
                channel_title = str(data.get("channel_title", curr.get("channel_title", ""))).strip()
                source_type = str(data.get("source_type", curr.get("source_type", "channel_videos"))).strip() or "channel_videos"
                selected_playlist_id = str(data.get("selected_playlist_id", curr.get("selected_playlist_id", ""))).strip()
                selected_playlist_title = str(data.get("selected_playlist_title", curr.get("selected_playlist_title", ""))).strip()
                video_selection_strategy = str(data.get("video_selection_strategy", curr.get("video_selection_strategy", "latest_2"))).strip() or "latest_2"
                manual_target_video_id = str(data.get("manual_target_video_id", curr.get("manual_target_video_id", ""))).strip()

                niche = str(data.get("niche_query", curr.get("niche_query", "podcast bisnis"))).strip() or "podcast bisnis"
                preset = str(data.get("preset_slug", curr.get("preset_slug", "default"))).strip() or "default"
                platforms = str(data.get("target_platforms", curr.get("target_platforms", "tiktok,instagram,youtube"))).strip()
                if "target_account_ids" in data:
                    acc_ids_val = data["target_account_ids"]
                    acc_ids_str = json.dumps(acc_ids_val if isinstance(acc_ids_val, list) else [])
                else:
                    acc_ids_str = curr.get("target_account_ids", "[]")
                sched_mode = str(data.get("schedule_mode", curr.get("schedule_mode", "ai"))).strip()
                custom_time = str(data.get("custom_schedule_time", curr.get("custom_schedule_time", ""))).strip()
                run_time = str(data.get("run_time", curr.get("run_time", "05:00"))).strip()
                min_dur = int(data.get("min_duration_sec", curr.get("min_duration_sec", 480)))
                max_dur = int(data.get("max_duration_sec", curr.get("max_duration_sec", 3600)))
                max_daily = 1
                post_clips = max(1, min(50, int(data.get("post_clips_count", curr.get("post_clips_count", 5)))))

                conn.execute("""
                    UPDATE autopilot_settings SET
                        enabled = ?, niche_query = ?, preset_slug = ?, target_platforms = ?,
                        target_account_ids = ?, schedule_mode = ?, custom_schedule_time = ?,
                        run_time = ?, min_duration_sec = ?, max_duration_sec = ?,
                        max_daily_videos = ?, post_clips_count = ?,
                        source_mode = ?, channel_url = ?, channel_title = ?, source_type = ?,
                        selected_playlist_id = ?, selected_playlist_title = ?, video_selection_strategy = ?,
                        manual_target_video_id = ?,
                        updated_at = ?
                    WHERE user_id = ?
                """, (
                    enabled, niche, preset, platforms, acc_ids_str, sched_mode,
                    custom_time, run_time, min_dur, max_dur, max_daily, post_clips,
                    source_mode, channel_url, channel_title, source_type,
                    selected_playlist_id, selected_playlist_title, video_selection_strategy,
                    manual_target_video_id,
                    now_str, user_id
                ))
            else:
                enabled = int(data.get("enabled", 0))
                source_mode = str(data.get("source_mode", "ai")).strip() or "ai"
                channel_url = str(data.get("channel_url", "")).strip()
                channel_title = str(data.get("channel_title", "")).strip()
                source_type = str(data.get("source_type", "channel_videos")).strip() or "channel_videos"
                selected_playlist_id = str(data.get("selected_playlist_id", "")).strip()
                selected_playlist_title = str(data.get("selected_playlist_title", "")).strip()
                video_selection_strategy = str(data.get("video_selection_strategy", "latest_2")).strip() or "latest_2"
                manual_target_video_id = str(data.get("manual_target_video_id", "")).strip()

                niche = str(data.get("niche_query", "podcast bisnis")).strip() or "podcast bisnis"
                preset = str(data.get("preset_slug", "default")).strip() or "default"
                platforms = str(data.get("target_platforms", "tiktok,instagram,youtube")).strip()
                acc_ids_val = data.get("target_account_ids", [])
                acc_ids_str = json.dumps(acc_ids_val if isinstance(acc_ids_val, list) else [])
                sched_mode = str(data.get("schedule_mode", "ai")).strip()
                custom_time = str(data.get("custom_schedule_time", "")).strip()
                run_time = str(data.get("run_time", "05:00")).strip()
                min_dur = int(data.get("min_duration_sec", 480))
                max_dur = int(data.get("max_duration_sec", 3600))
                max_daily = 1
                post_clips = max(1, min(50, int(data.get("post_clips_count", 5))))

                conn.execute("""
                    INSERT INTO autopilot_settings (
                        user_id, enabled, niche_query, preset_slug, target_platforms,
                        target_account_ids, schedule_mode, custom_schedule_time,
                        run_time, min_duration_sec, max_duration_sec, max_daily_videos, post_clips_count,
                        source_mode, channel_url, channel_title, source_type,
                        selected_playlist_id, selected_playlist_title, video_selection_strategy,
                        manual_target_video_id,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, enabled, niche, preset, platforms, acc_ids_str, sched_mode,
                    custom_time, run_time, min_dur, max_dur, max_daily, post_clips,
                    source_mode, channel_url, channel_title, source_type,
                    selected_playlist_id, selected_playlist_title, video_selection_strategy,
                    manual_target_video_id,
                    now_str
                ))

            conn.commit()
            return self.get_settings(user_id=user_id)
        finally:
            conn.close()

    def can_run_today(self, user_id: int = 1) -> tuple[bool, str, dict]:
        """Check if autopilot is eligible to run today under the strict 1-video/day rule.

        Returns: (can_run: bool, reason: str, info: dict)
        """
        # Always calculate daily run date based on WIB (Asia/Jakarta, UTC+7)
        now_wib = dt.datetime.now(dt.timezone(dt.timedelta(hours=7)))
        today_date = now_wib.date().isoformat()
        settings = self.get_settings(user_id)
        max_daily = settings.get("max_daily_videos", 1)

        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            # 1. Expire abandoned reservations older than 15 minutes
            fifteen_mins_ago = (now_wib - dt.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
            try:
                cur.execute("""
                    UPDATE autopilot_runs
                    SET status = 'failed', video_title = '[TIMEOUT] Waktu pencarian video habis'
                    WHERE status = 'reserving' AND created_at < ?
                """, (fifteen_mins_ago,))
                conn.commit()
            except Exception:
                pass

            # 2. Count active runs and pending reservations for today
            cur.execute("""
                SELECT COUNT(*) as run_count
                FROM autopilot_runs
                WHERE user_id = ? AND run_date = ? AND status IN ('reserving', 'in_progress', 'submitted', 'completed')
            """, (user_id, today_date))
            row = cur.fetchone()
            today_runs = row["run_count"] if row else 0


            cur.execute("""
                SELECT * FROM autopilot_runs
                WHERE user_id = ? AND run_date = ?
                ORDER BY id DESC LIMIT 1
            """, (user_id, today_date))
            last_today_run = cur.fetchone()

            info = {
                "today_date": today_date,
                "today_runs": today_runs,
                "max_daily_videos": max_daily,
                "last_run": dict(last_today_run) if last_today_run else None,
            }

            if today_runs >= max_daily:
                return (
                    False,
                    f"Kuota harian terpenuhi ({today_runs}/{max_daily} video untuk tanggal {today_date}).",
                    info,
                )

            return (True, f"Siap berjalan ({today_runs}/{max_daily} video hari ini).", info)
        finally:
            conn.close()

    def search_viral_videos(self, query: str, limit: int = 8) -> list[dict]:
        """Search viral videos on YouTube using yt-dlp search."""
        search_query = f"ytsearch{limit}:{query}"
        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--dump-json",
                    "--no-playlist",
                    "--flat-playlist",
                    "--extractor-args", "youtube:lang=id",
                    "--add-header", "Accept-Language: id,id-ID;q=0.9,en;q=0.8",
                    "--no-warnings",
                    search_query,
                ],
                capture_output=True,
                text=True,
                timeout=YTDLP_TIMEOUT,
            )
            if result.returncode != 0:
                logger.warning(f"yt-dlp search warning: {result.stderr.strip()[:200]}")
                return []

            videos = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    vid_id = item.get("id", "")
                    if not vid_id:
                        continue

                    views = int(item.get("view_count") or 0)
                    duration = int(item.get("duration") or 0)
                    title = item.get("title", "")
                    url = item.get("url") or f"https://www.youtube.com/watch?v={vid_id}"
                    uploader = item.get("uploader") or item.get("channel", "")

                    # Virality score calculation
                    score = min(100.0, (views / 20000.0) * 50.0 + 20.0) if views > 0 else 50.0

                    videos.append({
                        "id": vid_id,
                        "title": title,
                        "url": url,
                        "uploader": uploader,
                        "duration_sec": duration,
                        "views": views,
                        "virality_score": round(score, 1),
                    })
                except Exception:
                    continue

            # Sort by virality score descending
            videos.sort(key=lambda x: (x["virality_score"], x["views"]), reverse=True)
            return videos
        except Exception as e:
            logger.error(f"search_viral_videos error: {e}")
            return []

    def normalize_youtube_input(self, raw: str) -> dict:
        """Normalize user query to identify whether it's a playlist or channel handle/url."""
        q = raw.strip()
        # 1. Direct playlist detection
        list_match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', q)
        if list_match:
            playlist_id = list_match.group(1)
            return {
                "type": "playlist",
                "playlist_id": playlist_id,
                "url": f"https://www.youtube.com/playlist?list={playlist_id}",
                "raw": q,
            }

        # 2. Channel URL
        if q.startswith("http://") or q.startswith("https://"):
            clean_url = q.rstrip("/")
            handle_match = re.search(r'@([a-zA-Z0-9_.-]+)', clean_url)
            handle = f"@{handle_match.group(1)}" if handle_match else ""
            return {
                "type": "channel_url",
                "url": clean_url,
                "handle": handle,
                "raw": q,
            }

        # 3. Channel handle or username
        clean_handle = q.lstrip("@")
        return {
            "type": "channel_handle",
            "handle": f"@{clean_handle}",
            "url": f"https://www.youtube.com/@{clean_handle}",
            "raw": q,
        }

    def inspect_channel_or_playlist(self, query: str) -> dict:
        """Inspect a YouTube channel or playlist and return channel info, playlists, and podcasts."""
        norm = self.normalize_youtube_input(query)
        target_type = norm.get("type")

        channel_info = {
            "channel_title": "",
            "channel_url": "",
            "channel_handle": norm.get("handle") or "",
            "is_direct_playlist": False,
            "direct_playlist": None,
            "playlists": [],
            "has_channel_videos": True,
        }

        # If direct playlist
        if target_type == "playlist":
            pl_id = norm.get("playlist_id")
            pl_url = norm.get("url")
            try:
                res = subprocess.run(
                    [
                        "yt-dlp",
                        "--dump-json",
                        "--flat-playlist",
                        "--playlist-end", "1",
                        "--extractor-args", "youtube:lang=id",
                        "--add-header", "Accept-Language: id,id-ID;q=0.9,en;q=0.8",
                        "--no-warnings",
                        "--no-update",
                        pl_url,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res.returncode == 0 and res.stdout.strip():
                    first_line = res.stdout.strip().split("\n")[0]
                    item = json.loads(first_line)
                    pl_title = item.get("playlist_title") or item.get("playlist") or f"Playlist {pl_id}"
                    chan_title = item.get("playlist_channel") or item.get("playlist_uploader") or "YouTube Channel"
                    uploader_id = item.get("playlist_uploader_id") or ""
                    channel_info["channel_title"] = chan_title
                    channel_info["channel_handle"] = uploader_id if uploader_id.startswith("@") else (f"@{uploader_id}" if uploader_id else "")
                    channel_info["channel_url"] = f"https://www.youtube.com/{uploader_id}" if uploader_id else pl_url
                    channel_info["is_direct_playlist"] = True
                    direct_pl = {
                        "id": pl_id,
                        "title": pl_title,
                        "type": "playlist",
                        "url": pl_url,
                        "thumbnail": item.get("thumbnails", [{}])[-1].get("url") if item.get("thumbnails") else f"https://i.ytimg.com/vi/{item.get('id', '')}/hqdefault.jpg",
                    }
                    channel_info["direct_playlist"] = direct_pl
                    channel_info["playlists"].append(direct_pl)
            except Exception as e:
                logger.warning(f"inspect_channel_or_playlist direct playlist error: {e}")

            if channel_info.get("channel_handle"):
                norm["url"] = f"https://www.youtube.com/{channel_info['channel_handle']}"
            else:
                return channel_info

        base_url = norm.get("url", "").rstrip("/")
        for sub_tab in ["/videos", "/playlists", "/podcasts", "/featured"]:
            if base_url.endswith(sub_tab):
                base_url = base_url[:-len(sub_tab)]
                break

        channel_info["channel_url"] = base_url

        collections = []
        seen_ids = set()
        if channel_info.get("direct_playlist"):
            seen_ids.add(channel_info["direct_playlist"]["id"])

        for tab_name, item_type in [("playlists", "playlist"), ("podcasts", "podcast")]:
            tab_url = f"{base_url}/{tab_name}"
            try:
                res = subprocess.run(
                    [
                        "yt-dlp",
                        "--dump-json",
                        "--flat-playlist",
                        "--playlist-end", "40",
                        "--extractor-args", "youtube:lang=id",
                        "--add-header", "Accept-Language: id,id-ID;q=0.9,en;q=0.8",
                        "--no-warnings",
                        "--no-update",
                        tab_url,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res.returncode == 0:
                    for line in res.stdout.strip().split("\n"):
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                            item_id = item.get("id") or item.get("url")
                            if not item_id or item_id in seen_ids:
                                continue
                            seen_ids.add(item_id)

                            if not channel_info["channel_title"]:
                                channel_info["channel_title"] = item.get("playlist_channel") or item.get("playlist_uploader") or ""
                            if not channel_info["channel_handle"]:
                                up_id = item.get("playlist_uploader_id") or ""
                                channel_info["channel_handle"] = up_id if up_id.startswith("@") else (f"@{up_id}" if up_id else "")

                            thumbs = item.get("thumbnails") or []
                            best_thumb = thumbs[-1].get("url") if thumbs else ""

                            collections.append({
                                "id": item.get("id"),
                                "title": item.get("title") or item.get("playlist_title") or "Untitled Collection",
                                "type": item_type,
                                "url": item.get("url") or f"https://www.youtube.com/playlist?list={item.get('id')}",
                                "thumbnail": best_thumb,
                            })
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"Failed fetching tab {tab_name} for {base_url}: {e}")

        # If channel title is still empty, fetch 1 item from /videos
        if not channel_info["channel_title"]:
            try:
                res = subprocess.run(
                    [
                        "yt-dlp",
                        "--dump-json",
                        "--flat-playlist",
                        "--playlist-end", "1",
                        "--no-warnings",
                        "--no-update",
                        f"{base_url}/videos",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res.returncode == 0 and res.stdout.strip():
                    first_item = json.loads(res.stdout.strip().split("\n")[0])
                    channel_info["channel_title"] = first_item.get("playlist_channel") or first_item.get("playlist_uploader") or norm.get("handle") or "YouTube Channel"
            except Exception:
                pass

        if not channel_info["channel_title"]:
            channel_info["channel_title"] = norm.get("handle") or "YouTube Channel"

        channel_info["playlists"].extend(collections)
        return channel_info

    def get_playlist_or_channel_videos(
        self,
        playlist_id: Optional[str] = None,
        channel_url: Optional[str] = None,
        limit: int = 50,
        user_id: Optional[int] = None,
    ) -> dict:
        """Fetch videos for preview from a playlist or channel uploads."""
        if playlist_id:
            target_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        elif channel_url:
            c_url = channel_url.rstrip("/")
            target_url = c_url if c_url.endswith("/videos") else f"{c_url}/videos"
        else:
            return {"title": "", "target_url": "", "videos": [], "total": 0, "playlist_count": 0}

        processed_urls = self.get_processed_urls(user_id=user_id)
        videos = []
        coll_title = ""
        playlist_count = None

        fetch_limit = max(1, min(200, limit))

        try:
            res = subprocess.run(
                [
                    "yt-dlp",
                    "--dump-json",
                    "--flat-playlist",
                    "--playlist-end", str(fetch_limit),
                    "--extractor-args", "Youtube:lang=id;youtubetab:lang=id;youtube:lang=id",
                    "--add-header", "Accept-Language: id,id-ID;q=0.9,en;q=0.8",
                    "--no-warnings",
                    "--no-update",
                    target_url,
                ],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if res.returncode == 0:
                for line in res.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        vid_id = item.get("id")
                        if not vid_id:
                            continue
                        if not coll_title:
                            coll_title = item.get("playlist_title") or item.get("playlist") or ""
                        if playlist_count is None and item.get("playlist_count"):
                            try:
                                playlist_count = int(item.get("playlist_count"))
                            except (ValueError, TypeError):
                                pass

                        title = item.get("title", "")
                        url = item.get("url") or f"https://www.youtube.com/watch?v={vid_id}"

                        raw_dur = item.get("duration")
                        live_status = item.get("live_status")
                        is_upcoming = live_status == "is_upcoming" or (raw_dur is None and not item.get("duration_string"))

                        # Parse duration safely across Indonesian dot-time format (e.g. 36.36 = 36 min 36 sec)
                        dur = 0
                        if isinstance(raw_dur, (int, float)) and raw_dur > 0:
                            if isinstance(raw_dur, float) and not raw_dur.is_integer() and raw_dur < 1000:
                                mins = int(raw_dur)
                                secs = round((raw_dur - mins) * 100)
                                dur = mins * 60 + secs
                            else:
                                dur = int(raw_dur)
                        elif item.get("duration_string"):
                            d_str = str(item.get("duration_string")).strip().replace(".", ":")
                            parts = d_str.split(":")
                            try:
                                if len(parts) == 3:
                                    dur = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                                elif len(parts) == 2:
                                    dur = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 1:
                                    dur = int(parts[0])
                            except Exception:
                                dur = 0

                        thumbs = item.get("thumbnails") or []
                        best_thumb = thumbs[-1].get("url") if thumbs else f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

                        if is_upcoming:
                            dur_fmt = "Premiere"
                        elif dur >= 3600:
                            dur_fmt = f"{dur // 3600}:{(dur % 3600) // 60:02d}:{dur % 60:02d}"
                        elif dur > 0:
                            dur_fmt = f"{dur // 60}:{dur % 60:02d}"
                        else:
                            dur_fmt = "--:--"

                        is_processed = (vid_id in processed_urls) or (url in processed_urls)

                        videos.append({
                            "id": vid_id,
                            "title": title,
                            "url": url,
                            "duration_sec": dur,
                            "duration_formatted": dur_fmt,
                            "thumbnail": best_thumb,
                            "is_processed": is_processed,
                            "is_upcoming": is_upcoming,
                            "index": len(videos) + 1,
                        })
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"get_playlist_or_channel_videos error for {target_url}: {e}")

        return {
            "title": coll_title,
            "target_url": target_url,
            "videos": videos,
            "total": len(videos),
            "playlist_count": playlist_count or len(videos),
        }

    def _format_candidate_from_video(self, v: dict) -> dict:
        """Format candidate dictionary for AutoCliper job submission."""
        return {
            "id": v["id"],
            "title": v["title"],
            "url": v["url"],
            "uploader": v.get("uploader", ""),
            "duration_sec": v.get("duration_sec", 0),
            "views": v.get("views", 0),
            "virality_score": 85.0,
        }

    def pick_candidate_from_channel_or_playlist(
        self,
        settings: dict,
        processed_urls: set[str],
        user_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Pick video candidate from user-selected channel or playlist according to strategy.
        
        Strategies:
        - 'latest_2' / 'second_latest_buffer': Monitor latest 2 videos in playlist/channel;
          processes vid 2 first, then vid 1 on next day to maintain stock buffer.
        - 'latest' / 'latest_1': Always process newest unprocessed video immediately.
        - 'all_playlist': Process oldest unprocessed video first (sequential backlog).
        """
        source_type = settings.get("source_type", "channel_videos")
        playlist_id = str(settings.get("selected_playlist_id") or "").strip()
        channel_url = str(settings.get("channel_url") or "").strip()
        strategy = settings.get("video_selection_strategy", "latest_2")
        min_dur = settings.get("min_duration_sec", 480)
        max_dur = settings.get("max_duration_sec", 3600)
        manual_target_id = str(settings.get("manual_target_video_id") or "").strip()

        # 1. Fetch playlist or channel videos
        data = self.get_playlist_or_channel_videos(
            playlist_id=playlist_id if source_type == "playlist" else None,
            channel_url=channel_url if source_type != "playlist" or not playlist_id else None,
            limit=100,
            user_id=user_id,
        )
        videos = data.get("videos") or []
        if not videos:
            logger.warning(
                f"autopilot: No videos returned from source (source_type={source_type}, "
                f"playlist_id={playlist_id}, channel_url={channel_url})"
            )
            return None

        # Prioritize manual target selection if configured by user
        if manual_target_id:
            for v in videos:
                if v.get("id") == manual_target_id:
                    return self._format_candidate_from_video(v)

        # 2. Exclude upcoming premiere videos and filter by duration
        playable_videos = [v for v in videos if not v.get("is_upcoming")]
        if not playable_videos:
            logger.warning("autopilot: No playable videos available (all upcoming or premieres)")
            return None

        def duration_ok(v):
            d = v.get("duration_sec", 0)
            return d <= 0 or (min_dur <= d <= max_dur)

        filtered_videos = [v for v in playable_videos if duration_ok(v)]
        eligible_pool = filtered_videos if filtered_videos else playable_videos

        # 3. Strategy evaluation
        # Strategy 1: 'latest' or 'latest_1' (Selalu ambil video terbaru / vid 1 di index 0)
        if strategy in ("latest", "latest_1"):
            if len(eligible_pool) >= 1:
                v1 = eligible_pool[0]
                if v1["id"] not in processed_urls and v1["url"] not in processed_urls:
                    return self._format_candidate_from_video(v1)
            return None

        # Strategy 2: 'latest_2' or 'second_latest_buffer' (Buffer 2 video terakhir: vid 2 dulu, lalu vid 1)
        elif strategy in ("latest_2", "second_latest_buffer"):
            window = eligible_pool[:2]
            # Check vid 2 (index 1) first if it exists and unprocessed
            if len(window) >= 2:
                v2 = window[1]
                if v2["id"] not in processed_urls and v2["url"] not in processed_urls:
                    return self._format_candidate_from_video(v2)
            # If vid 2 already processed or only 1 video in window, check vid 1 (index 0)
            if len(window) >= 1:
                v1 = window[0]
                if v1["id"] not in processed_urls and v1["url"] not in processed_urls:
                    return self._format_candidate_from_video(v1)
            return None

        # Strategy 3: 'all_playlist' (Seluruh video di playlist secara bertahap dari terlama ke terbaru)
        else:
            unprocessed = [
                v for v in eligible_pool
                if v["id"] not in processed_urls and v["url"] not in processed_urls
            ]
            if unprocessed:
                return self._format_candidate_from_video(unprocessed[-1])
            return None

    def get_processed_urls(self, user_id: Optional[int] = None) -> set[str]:
        """Get set of all YouTube URLs previously processed in completed jobs or autopilot_runs."""
        urls = set()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            # 1. From jobs table - only completed jobs with clips or actively processing jobs
            try:
                query = (
                    "SELECT DISTINCT youtube_url FROM jobs "
                    "WHERE youtube_url IS NOT NULL "
                    "AND ("
                    "  status = 'completed' "
                    "  OR (status IN ('processing', 'rendering', 'queued') AND updated_at >= datetime('now', '-3 hours'))"
                    ")"
                )
                params: list[Any] = []
                if user_id is not None:
                    query += " AND (user_id = ? OR user_id IS NULL)"
                    params.append(user_id)
                cur.execute(query, tuple(params))
                for r in cur.fetchall():
                    u = str(r["youtube_url"]).strip()
                    if u:
                        urls.add(u)
                        vid_m = re.search(r'(?:v=|\/|be\/|shorts\/)([a-zA-Z0-9_-]{11})', u)
                        if vid_m:
                            urls.add(vid_m.group(1))
            except Exception:
                pass

            # 2. From autopilot_runs table - only successful runs
            try:
                query2 = "SELECT DISTINCT youtube_url FROM autopilot_runs WHERE status != 'failed'"
                params2: list[Any] = []
                if user_id is not None:
                    query2 += " AND (user_id = ? OR user_id IS NULL)"
                    params2.append(user_id)
                cur.execute(query2, tuple(params2))
                for r in cur.fetchall():
                    u = str(r["youtube_url"]).strip()
                    if u:
                        urls.add(u)
                        vid_m = re.search(r'(?:v=|\/|be\/|shorts\/)([a-zA-Z0-9_-]{11})', u)
                        if vid_m:
                            urls.add(vid_m.group(1))
            except Exception:
                pass

            return urls
        finally:
            conn.close()

    def reset_video_processed(self, user_id: int, video_id: str) -> bool:
        """Reset processed status for a video so it can be re-processed by autopilot."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM autopilot_runs
                WHERE user_id = ? AND (youtube_url LIKE ? OR youtube_url LIKE ?)
            """, (user_id, f"%{video_id}%", f"%youtu.be/{video_id}%"))
            cur.execute("""
                UPDATE jobs
                SET status = 'archived'
                WHERE (user_id = ? OR user_id IS NULL) AND youtube_url LIKE ?
            """, (user_id, f"%{video_id}%"))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"reset_video_processed error: {e}")
            return False
        finally:
            conn.close()
            conn.close()

    def pick_best_candidate(self, user_id: int = 1) -> Optional[dict]:
        """Search and pick the #1 best viral candidate matching settings that hasn't been clipped."""
        settings = self.get_settings(user_id)
        source_mode = settings.get("source_mode", "ai")
        processed_urls = self.get_processed_urls(user_id=user_id)

        # If user configured channel / playlist source mode
        if source_mode == "channel_playlist":
            return self.pick_candidate_from_channel_or_playlist(settings, processed_urls, user_id=user_id)

        # AI Discovery mode
        niche = settings.get("niche_query", "podcast bisnis")
        min_dur = settings.get("min_duration_sec", 480)
        max_dur = settings.get("max_duration_sec", 3600)

        attempts = [
            (niche, 10),
            (f"{niche} viral shorts", 10),
            (f"{niche} full", 15),
            (f"{niche} terbaru", 15),
        ]

        total_searched = 0
        unprocessed: list[dict] = []
        for query, limit in attempts:
            videos = self.search_viral_videos(query, limit=limit)
            if not videos:
                continue
            total_searched += len(videos)
            for v in videos:
                if v["url"] in processed_urls or v["id"] in processed_urls:
                    continue
                dur = v["duration_sec"]
                if dur > 0 and (dur < min_dur or dur > max_dur):
                    unprocessed.append(v)
                    continue
                return v

        if unprocessed:
            # Legacy leniency: better a slightly-off-length video than a failed run.
            v = unprocessed[0]
            logger.warning(
                f"autopilot: no in-range candidate; falling back to '{v['title'][:60]}' "
                f"({v['duration_sec']}s, wanted {min_dur}s..{max_dur}s)"
            )
            return v

        if total_searched:
            logger.info(
                f"autopilot: {total_searched} candidates searched across "
                f"{len(attempts)} query variants — all already processed for niche "
                f"'{niche}' ({len(processed_urls)} processed URLs total)"
            )
        return None

    async def run_autopilot_step(
        self,
        user_id: int = 1,
        force: bool = False,
        preset_override: Optional[str] = None,
        trigger_source: str = "cron",
        notify_telegram: bool = True,
    ) -> dict:
        """Execute autonomous discovery, clipping, and auto-post pipeline.

        Enforces enabled check, pipeline availability check, and strict atomic max 1 video/day quota unless force=True.
        """
        async with self._run_lock:
            self._ensure_tables()
            settings = self.get_settings(user_id)

            # 0. Check if user enabled autopilot
            if not force and not settings.get("enabled"):
                logger.info(f"autopilot: Skipped run for user {user_id}. Autopilot is disabled for this user.")
                return {
                    "success": False,
                    "status": "disabled",
                    "message": f"Hermes Autopilot belum diaktifkan untuk pengguna ini.",
                }

            # 1. Check if server pipeline is already busy with another video
            if not force and self.is_pipeline_busy():
                logger.info(f"autopilot: Pipeline is currently busy processing another job. Deferring run for user {user_id}.")
                return {
                    "success": False,
                    "status": "pipeline_busy",
                    "message": "Server sedang memproses video lain. Antrean autopilot akan menunggu hingga proses yang sedang berjalan selesai.",
                }

            # 2. Check daily quota
            can_run, reason, quota_info = self.can_run_today(user_id)
            if not can_run and not force:
                logger.info(f"autopilot: Skipped run for user {user_id}. {reason}")
                return {
                    "success": False,
                    "status": "quota_exceeded",
                    "message": reason,
                    "quota": quota_info,
                }

            now_wib = dt.datetime.now(dt.timezone(dt.timedelta(hours=7)))
            today_date = now_wib.date().isoformat()
            now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

            # Immediate Atomic Quota Reservation at second 0 to prevent concurrent race conditions
            reservation_id = None
            if not force:
                conn = get_dict_connection()
                try:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO autopilot_runs (
                            user_id, run_date, youtube_url, video_title, virality_score,
                            job_id, status, trigger_source, created_at
                        ) VALUES (?, ?, 'pending_discovery', 'Mencari video viral YouTube...', 0, 'reserving', 'reserving', ?, ?)
                    """, (user_id, today_date, trigger_source, now_iso))

                    conn.commit()
                    reservation_id = cur.lastrowid
                finally:
                    conn.close()

            try:
                # 3. Pick candidate video
                candidate = self.pick_best_candidate(user_id)
                if not candidate:
                    source_mode = settings.get("source_mode", "ai")
                    if source_mode == "channel_playlist":
                        src_name = settings.get("selected_playlist_title") or settings.get("channel_title") or settings.get("channel_url") or "playlist / channel"
                        strat = settings.get("video_selection_strategy", "latest_2")
                        strat_desc = "2 video terakhir" if strat == "latest_2" else ("video terbaru" if strat in ("latest", "latest_1") else "playlist")
                        err_msg = f"Semua video ({strat_desc}) pada '{src_name}' sudah diproses atau belum ada video baru yang dirilis."
                    else:
                        err_msg = f"Tidak ditemukan video baru yang belum pernah diproses untuk topik '{settings.get('niche_query')}'."

                    if reservation_id:
                        conn = get_dict_connection()
                        try:
                            conn.execute("UPDATE autopilot_runs SET status='failed', video_title=? WHERE id=?", (err_msg[:200], reservation_id))
                            conn.commit()
                        finally:
                            conn.close()
                    logger.warning(f"autopilot: {err_msg}")
                    return {
                        "success": False,
                        "status": "no_candidate_found",
                        "message": err_msg,
                    }

                video_url = candidate["url"]
                video_title = candidate["title"]
                virality_score = candidate.get("virality_score", 75.0)
                logger.info(
                    f"autopilot: Selected video '{video_title}' ({video_url}) score={virality_score} for user {user_id} via {trigger_source}"
                )

                # 4. Resolve preset style layers
                from src.infrastructure.preset_resolver import resolve_preset
                from src.infrastructure.hook_manifest import resolve_hook_preset
                preset_slug = str(preset_override or settings.get("preset_slug", "default")).strip() or "default"
                resolved_preset = resolve_preset(preset_slug, user_id=user_id)
                hook_manifest = resolve_hook_preset(user_id, preset_slug, None)
                if resolved_preset:
                    preset_slug = resolved_preset.get("slug") or preset_slug

                # 5. Prepare AutoCliper job options
                target_platforms = [p.strip().lower() for p in settings.get("target_platforms", "tiktok,instagram,youtube").split(",") if p.strip()]
                target_accounts = settings.get("target_account_ids", [])
                if not target_accounts and resolved_preset and resolved_preset.get("auto_post_account_ids"):
                    target_accounts = resolved_preset.get("auto_post_account_ids")

                schedule_mode = settings.get("schedule_mode", "ai")
                custom_schedule_time = settings.get("custom_schedule_time") if schedule_mode == "custom" else None
                broll_style = resolved_preset.get("broll_config") or resolved_preset.get("broll_style_config") or {}
                broll_motion_style = broll_style.get("motion_style") if isinstance(broll_style, dict) else None

                job_options = {
                    "youtube_url": video_url,
                    "target_aspect_ratio": "9:16",
                    "style_preset": preset_slug,
                    "force_reprocess": False,
                    "use_remotion": True,
                    "pipeline_version": "v2",
                    "hook_style": resolved_preset.get("hook_style_config", {}).get("animation") if resolved_preset else None,
                    "ai_layer_enabled": True,
                    # B-roll & Auto-Grid layers from resolved preset
                    "broll_enabled": resolved_preset.get("broll_enabled", False) if resolved_preset else False,
                    "broll_image_overlay": resolved_preset.get("broll_image_overlay", False) if resolved_preset else False,
                    "broll_behind_person": resolved_preset.get("broll_behind_person", False) if resolved_preset else False,
                    "broll_video_footage": resolved_preset.get("broll_video_footage", False) if resolved_preset else False,
                    "broll_motion_style": broll_motion_style,
                    "autogrid_enabled": resolved_preset.get("autogrid_enabled", False) if resolved_preset else False,
                    # Text & Hook & Subtitle layers from resolved preset
                    "text_emphasis_enabled": resolved_preset.get("text_emphasis_enabled", False) if resolved_preset else False,
                    "hook_style_config": hook_manifest["config"],
                    "subtitle_style_config": resolved_preset.get("subtitle_style_config", {}) if resolved_preset else {},
                    "text_emphasis_style_config": resolved_preset.get("text_emphasis_style_config", {}) if resolved_preset else {},
                    "watermark_config": resolved_preset.get("watermark_config", {}) if resolved_preset else {},
                    "cta_config": resolved_preset.get("cta_config", {}) if resolved_preset else {},
                    # AI Auto-Post configurations
                    "auto_post_social": True,
                    "auto_post_platforms": ",".join(target_platforms),
                    "auto_post_account_ids": target_accounts,
                    "auto_post_schedule_mode": schedule_mode,
                    "auto_post_custom_time": custom_schedule_time,
                    "auto_post_clips_count": int(settings.get("post_clips_count", 5) or 5),
                }

                # 6. Submit job to AutoCliper service
                from src.presentation.dependencies import get_job_service
                job_service = get_job_service()
                hook_cfg = dict(job_options.get("hook_style_config") or {})
                if hook_cfg and not hook_cfg.get("engine"):
                    hook_cfg["engine"] = resolved_preset.get("hook_engine", "remotion") if resolved_preset else "remotion"

                sub_cfg = dict(job_options.get("subtitle_style_config") or {})
                if sub_cfg and not sub_cfg.get("engine"):
                    sub_cfg["engine"] = resolved_preset.get("subtitle_engine", "remotion") if resolved_preset else "remotion"

                created_res = await job_service.create_job(
                    youtube_url=video_url,
                    user_id=user_id,
                    target_aspect_ratio=job_options.get("target_aspect_ratio", "9:16"),
                    style_preset=job_options.get("style_preset", "default"),
                    force_reprocess=job_options.get("force_reprocess", False),
                    use_remotion=job_options.get("use_remotion", True),
                    ai_layer_enabled=job_options.get("ai_layer_enabled", True),
                    hook_engine="v3",
                    hook_style=job_options.get("hook_style") or "",
                    broll_enabled=job_options.get("broll_enabled", False),
                    broll_image_overlay=job_options.get("broll_image_overlay", False),
                    broll_behind_person=job_options.get("broll_behind_person", False),
                    broll_video_footage=job_options.get("broll_video_footage", False),
                    broll_motion_style=job_options.get("broll_motion_style"),
                    autogrid_enabled=job_options.get("autogrid_enabled", False),
                    text_emphasis_enabled=job_options.get("text_emphasis_enabled", False),
                    hook_style_config=hook_cfg,
                    subtitle_style_config=sub_cfg,
                    text_emphasis_style_config=job_options.get("text_emphasis_style_config"),
                    watermark_config=job_options.get("watermark_config"),
                    cta_config=job_options.get("cta_config"),
                    auto_post_social=job_options.get("auto_post_social", False),
                    auto_post_platforms=job_options.get("auto_post_platforms", ""),
                    auto_post_account_ids=job_options.get("auto_post_account_ids", []),
                    auto_post_schedule_mode=job_options.get("auto_post_schedule_mode", "ai"),
                    auto_post_custom_time=job_options.get("auto_post_custom_time"),
                    auto_post_clips_count=job_options.get("auto_post_clips_count", 5),
                )

                job = created_res[0] if isinstance(created_res, tuple) else created_res
                job_id = getattr(job, "id", None) or getattr(job, "job_id", str(job))

                # 7. Finalize run in database
                conn = get_dict_connection()
                run_id = reservation_id
                try:
                    cur = conn.cursor()
                    if reservation_id:
                        cur.execute("""
                            UPDATE autopilot_runs SET
                                youtube_url = ?,
                                video_title = ?,
                                virality_score = ?,
                                job_id = ?,
                                status = 'submitted'
                            WHERE id = ?
                        """, (video_url, video_title, virality_score, job_id, reservation_id))
                    else:
                        cur.execute("""
                            INSERT INTO autopilot_runs (
                                user_id, run_date, youtube_url, video_title, virality_score,
                                job_id, status, trigger_source, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
                        """, (
                            user_id, today_date, video_url, video_title, virality_score,
                            job_id, trigger_source, now_iso
                        ))
                        run_id = cur.lastrowid

                    conn.execute("""
                        UPDATE autopilot_settings SET
                            last_run_at = ?,
                            last_job_id = ?,
                            last_video_url = ?,
                            last_video_title = ?,
                            updated_at = ?
                        WHERE user_id = ?
                    """, (now_iso, job_id, video_url, video_title, now_iso, user_id))
                    conn.commit()
                except Exception as e:
                    logger.error(f"autopilot: Failed to record run in database: {e}")
                finally:
                    conn.close()

                # 8. Notify Telegram if enabled
                if notify_telegram:
                    try:
                        from src.infrastructure.telegram_notifier import send_telegram_broadcast
                        sched_desc = "Optimal AI Posting" if schedule_mode == "ai" else f"Mulai {custom_schedule_time or '09:00'}"
                        source_mode = settings.get("source_mode", "ai")
                        if source_mode == "channel_playlist":
                            strat = settings.get("video_selection_strategy", "latest_2")
                            strat_label = "Buffer 2 Video Terakhir" if strat == "latest_2" else ("Video Terbaru" if strat in ("latest", "latest_1") else "Seluruh Playlist")
                            src_info = f"<b>Sumber:</b> {settings.get('selected_playlist_title') or settings.get('channel_title') or 'Channel/Playlist'} ({strat_label})\n"
                        else:
                            src_info = f"<b>Niche AI:</b> {settings.get('niche_query', 'podcast bisnis')}\n"

                        caption_text = (
                            f"<b>[AUTOPILOT] Hermes Autopilot — Job Hari Ini Dijalankan!</b>\n\n"
                            f"<b>User ID:</b> {user_id}\n"
                            f"{src_info}"
                            f"<b>Judul:</b> {video_title}\n"
                            f"<b>Virality Score:</b> {virality_score}/100\n"
                            f"<b>Preset:</b> {preset_slug}\n"
                            f"<b>Target Platform:</b> {','.join(target_platforms).upper()}\n"
                            f"<b>Jadwal:</b> {sched_desc}\n"
                            f"<b>Job ID:</b> <code>{job_id}</code>\n\n"
                            f"<i>Sistem sedang memproses video YouTube menjadi Shorts/TikTok portrait dan akan otomatis dijadwalkan ke Repliz setelah selesai.</i>"
                        )
                        await send_telegram_broadcast(caption_text)
                    except Exception as e:
                        logger.warning(f"autopilot: Failed to send Telegram report: {e}")

                return {
                    "success": True,
                    "status": "submitted",
                    "job_id": job_id,
                    "run_id": run_id,
                    "video": candidate,
                    "video_url": video_url,
                    "video_title": video_title,
                    "virality_score": virality_score,
                    "preset_slug": preset_slug,
                    "preset_name": resolved_preset.get("name") if resolved_preset else preset_slug,
                    "platforms": target_platforms,
                    "message": f"Autopilot berhasil memproses video '{video_title}' (Job ID: {job_id})",
                }
            except Exception as exc:
                if reservation_id:
                    conn = get_dict_connection()
                    try:
                        conn.execute("UPDATE autopilot_runs SET status='failed', video_title=? WHERE id=?", (f"Gagal: {str(exc)[:100]}", reservation_id))
                        conn.commit()
                    finally:
                        conn.close()
                raise

    def get_history(self, user_id: int = 1, limit: int = 20) -> list[dict]:
        """Get recent autopilot execution history."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM autopilot_runs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (user_id, limit))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def start_scheduler_loop(self):
        """Continuous background loop that checks autopilot_settings every 30 seconds.
        
        When enabled=1, current time matches run_time (WIB), and can_run_today is True,
        it automatically executes 1 autonomous daily discovery & auto-post cycle.
        """
        logger.info("autopilot_scheduler: Started background daemon loop")
        while True:
            try:
                await self._check_and_run_scheduled_autopilots()
            except asyncio.CancelledError:
                logger.info("autopilot_scheduler: Stopped background daemon loop")
                break
            except Exception as e:
                logger.error(f"autopilot_scheduler: Loop iteration error: {e}", exc_info=True)
            await asyncio.sleep(30)

    async def _check_and_run_scheduled_autopilots(self):
        """Check all active users with enabled autopilot settings and execute sequentially."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT s.* FROM autopilot_settings s
                JOIN users u ON s.user_id = u.id
                WHERE s.enabled = 1 AND u.is_active = 1
                ORDER BY s.id ASC
            """)
            rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return

        # Check if the pipeline is already busy with another video processing
        if self.is_pipeline_busy():
            logger.info("autopilot_daemon: Pipeline is currently busy processing a video. Deferring scheduled check until current job finishes.")
            return

        # Current time in WIB (UTC+7)
        now_wib = dt.datetime.now(dt.timezone(dt.timedelta(hours=7)))
        current_hm = now_wib.strftime("%H:%M")

        for row in rows:
            r_dict = dict(row)
            user_id = r_dict.get("user_id")
            if not user_id:
                continue

            if not bool(r_dict.get("enabled")):
                continue

            raw_run_time = str(r_dict.get("run_time") or "05:00").strip()
            # Normalize to HH:MM format
            try:
                parts = raw_run_time.split(":")
                norm_run_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            except Exception:
                norm_run_time = "05:00"

            today_date = now_wib.date().isoformat()
            if current_hm == norm_run_time:
                # Prevent duplicate daemon runs within the same calendar day for the same user
                if self._last_scheduled_runs.get((user_id, today_date)):
                    continue

                if self.is_pipeline_busy():
                    logger.info(f"autopilot_daemon: Server pipeline is busy. Waiting before processing user {user_id}.")
                    return

                can_run, reason, _ = self.can_run_today(user_id)
                if can_run:
                    self._last_scheduled_runs[(user_id, today_date)] = True
                    logger.info(f"autopilot_daemon: Triggering scheduled daily run for user {user_id} at {current_hm} WIB...")
                    try:
                        res = await self.run_autopilot_step(
                            user_id=user_id,
                            trigger_source="daemon_scheduler",
                            notify_telegram=True,
                        )
                        logger.info(f"autopilot_daemon: Run result for user {user_id}: {res.get('message')}")
                        # If a job was launched, break so we process one user at a time
                        if res.get("success"):
                            break
                    except Exception as step_err:
                        logger.error(f"autopilot_daemon: Error running autopilot step for user {user_id}: {step_err}", exc_info=True)



# Singleton instance
autopilot_service = AutopilotService()
