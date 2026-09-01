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
                    last_run_at TEXT DEFAULT NULL,
                    last_job_id TEXT DEFAULT NULL,
                    last_video_url TEXT DEFAULT NULL,
                    last_video_title TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

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

                conn.execute("""
                    UPDATE autopilot_settings SET
                        enabled = ?, niche_query = ?, preset_slug = ?, target_platforms = ?,
                        target_account_ids = ?, schedule_mode = ?, custom_schedule_time = ?,
                        run_time = ?, min_duration_sec = ?, max_duration_sec = ?,
                        max_daily_videos = ?, updated_at = ?
                    WHERE user_id = ?
                """, (
                    enabled, niche, preset, platforms, acc_ids_str, sched_mode,
                    custom_time, run_time, min_dur, max_dur, max_daily, now_str, user_id
                ))
            else:
                enabled = int(data.get("enabled", 0))
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

                conn.execute("""
                    INSERT INTO autopilot_settings (
                        user_id, enabled, niche_query, preset_slug, target_platforms,
                        target_account_ids, schedule_mode, custom_schedule_time,
                        run_time, min_duration_sec, max_duration_sec, max_daily_videos, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, enabled, niche, preset, platforms, acc_ids_str, sched_mode,
                    custom_time, run_time, min_dur, max_dur, max_daily, now_str
                ))

            conn.commit()
            return self.get_settings(user_id=user_id)
        finally:
            conn.close()

    def can_run_today(self, user_id: int = 1) -> tuple[bool, str, dict]:
        """Check if autopilot is eligible to run today under the strict 1-video/day rule.

        Returns: (can_run: bool, reason: str, info: dict)
        """
        today_date = dt.date.today().isoformat()
        settings = self.get_settings(user_id)
        max_daily = settings.get("max_daily_videos", 1)

        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as run_count
                FROM autopilot_runs
                WHERE user_id = ? AND run_date = ? AND status IN ('submitted', 'completed')
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

    def get_processed_urls(self) -> set[str]:
        """Get set of all YouTube URLs previously processed in jobs or autopilot_runs."""
        urls = set()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            # 1. From jobs table
            try:
                cur.execute("SELECT DISTINCT youtube_url FROM jobs WHERE youtube_url IS NOT NULL")
                for r in cur.fetchall():
                    u = str(r["youtube_url"]).strip()
                    if u:
                        urls.add(u)
                        # also add video id if present
                        if "v=" in u:
                            urls.add(u.split("v=")[-1].split("&")[0])
            except Exception:
                pass

            # 2. From autopilot_runs table
            try:
                cur.execute("SELECT DISTINCT youtube_url FROM autopilot_runs")
                for r in cur.fetchall():
                    u = str(r["youtube_url"]).strip()
                    if u:
                        urls.add(u)
                        if "v=" in u:
                            urls.add(u.split("v=")[-1].split("&")[0])
            except Exception:
                pass

            return urls
        finally:
            conn.close()

    def pick_best_candidate(self, user_id: int = 1) -> Optional[dict]:
        """Search and pick the #1 best viral candidate matching niche & duration that hasn't been clipped."""
        settings = self.get_settings(user_id)
        niche = settings.get("niche_query", "podcast bisnis")
        min_dur = settings.get("min_duration_sec", 480)
        max_dur = settings.get("max_duration_sec", 3600)

        videos = self.search_viral_videos(niche, limit=10)
        if not videos:
            # Fallback search with broader terms
            videos = self.search_viral_videos(f"{niche} viral shorts", limit=10)

        if not videos:
            return None

        processed_urls = self.get_processed_urls()

        for v in videos:
            vid_url = v["url"]
            vid_id = v["id"]
            dur = v["duration_sec"]

            # Check if processed
            if vid_url in processed_urls or vid_id in processed_urls:
                continue

            # Check duration range (if duration metadata is available)
            if dur > 0 and (dur < min_dur or dur > max_dur):
                continue

            return v

        # If all candidates filtered by duration, return highest score candidate that hasn't been processed
        for v in videos:
            if v["url"] not in processed_urls and v["id"] not in processed_urls:
                return v

        return None

    async def run_autopilot_step(
        self,
        user_id: int = 1,
        force: bool = False,
        trigger_source: str = "cron",
        notify_telegram: bool = True,
    ) -> dict:
        """Execute autonomous discovery, clipping, and auto-post pipeline.

        Enforces enabled check, pipeline availability check, and max 1 video/day quota unless force=True.
        """
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

        # 3. Pick candidate video
        candidate = self.pick_best_candidate(user_id)
        if not candidate:
            logger.warning(f"autopilot: No fresh candidate video found for niche '{settings.get('niche_query')}'.")
            return {
                "success": False,
                "status": "no_candidate_found",
                "message": f"Tidak ditemukan video baru yang belum pernah diproses untuk topik '{settings.get('niche_query')}'.",
            }

        video_url = candidate["url"]
        video_title = candidate["title"]
        virality_score = candidate.get("virality_score", 75.0)
        today_date = dt.date.today().isoformat()

        logger.info(
            f"autopilot: Selected video '{video_title}' ({video_url}) score={virality_score} for user {user_id} via {trigger_source}"
        )

        # 4. Resolve preset style layers
        from src.infrastructure.preset_resolver import resolve_preset
        preset_slug = settings.get("preset_slug", "default")
        resolved_preset = resolve_preset(preset_slug, user_id=user_id)
        # If preset is default or fallback to builtin_default, automatically check if user has custom user_presets
        if not resolved_preset or resolved_preset.get("source") == "builtin_default":
            fallback_p = resolve_preset("", user_id=user_id)
            if fallback_p and fallback_p.get("source") != "builtin_default":
                resolved_preset = fallback_p
                preset_slug = resolved_preset.get("slug") or preset_slug
                logger.info(f"autopilot: Automatically resolved active user preset '{resolved_preset.get('name')}' ({preset_slug})")

        # 5. Prepare AutoCliper job options
        target_platforms = [p.strip().lower() for p in settings.get("target_platforms", "tiktok,instagram,youtube").split(",") if p.strip()]
        target_accounts = settings.get("target_account_ids", [])
        schedule_mode = settings.get("schedule_mode", "ai")
        custom_schedule_time = settings.get("custom_schedule_time") if schedule_mode == "custom" else None

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
            "broll_image_overlay": resolved_preset.get("broll_image_overlay", True) if resolved_preset else True,
            "broll_behind_person": resolved_preset.get("broll_behind_person", True) if resolved_preset else True,
            "broll_video_footage": resolved_preset.get("broll_video_footage", True) if resolved_preset else True,
            "autogrid_enabled": resolved_preset.get("autogrid_enabled", False) if resolved_preset else False,
            # Text & Hook & Subtitle layers from resolved preset
            "text_emphasis_enabled": resolved_preset.get("text_emphasis_enabled", True) if resolved_preset else True,
            "hook_style_config": resolved_preset.get("hook_style_config", {}) if resolved_preset else {},
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
        }

        # 6. Submit job to AutoCliper service
        from src.presentation.dependencies import get_job_service
        job_service = get_job_service()
        created_res = await job_service.create_job(
            youtube_url=video_url,
            user_id=user_id,
            target_aspect_ratio=job_options.get("target_aspect_ratio", "9:16"),
            style_preset=job_options.get("style_preset", "default"),
            force_reprocess=job_options.get("force_reprocess", False),
            use_remotion=job_options.get("use_remotion", True),
            ai_layer_enabled=job_options.get("ai_layer_enabled", True),
            broll_enabled=job_options.get("broll_enabled", False),
            broll_image_overlay=job_options.get("broll_image_overlay", True),
            broll_behind_person=job_options.get("broll_behind_person", True),
            broll_video_footage=job_options.get("broll_video_footage", True),
            autogrid_enabled=job_options.get("autogrid_enabled", False),
            text_emphasis_enabled=job_options.get("text_emphasis_enabled", True),
            hook_style_config=job_options.get("hook_style_config"),
            subtitle_style_config=job_options.get("subtitle_style_config"),
            text_emphasis_style_config=job_options.get("text_emphasis_style_config"),
            watermark_config=job_options.get("watermark_config"),
            cta_config=job_options.get("cta_config"),
            auto_post_social=job_options.get("auto_post_social", False),
            auto_post_platforms=job_options.get("auto_post_platforms", ""),
            auto_post_account_ids=job_options.get("auto_post_account_ids", []),
            auto_post_schedule_mode=job_options.get("auto_post_schedule_mode", "ai"),
            auto_post_custom_time=job_options.get("auto_post_custom_time"),
        )

        job = created_res[0] if isinstance(created_res, tuple) else created_res
        job_id = getattr(job, "id", None) or getattr(job, "job_id", str(job))

        # 7. Record run in database
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        conn = get_dict_connection()
        run_id = None
        try:
            cur = conn.cursor()
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
                caption_text = (
                    f"🤖 <b>Hermes Autopilot — Job Hari Ini Dijalankan!</b>\n\n"
                    f"👤 <b>User ID:</b> {user_id}\n"
                    f"🎬 <b>Judul:</b> {video_title}\n"
                    f"📈 <b>Virality Score:</b> {virality_score}/100\n"
                    f"🎨 <b>Preset:</b> {preset_slug}\n"
                    f"📱 <b>Target Platform:</b> {','.join(target_platforms).upper()}\n"
                    f"⏰ <b>Jadwal:</b> {sched_desc}\n"
                    f"🆔 <b>Job ID:</b> <code>{job_id}</code>\n\n"
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
            "platforms": target_platforms,
            "message": f"Autopilot berhasil memproses video '{video_title}' (Job ID: {job_id})",
        }

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

            if current_hm == norm_run_time:
                if self.is_pipeline_busy():
                    logger.info(f"autopilot_daemon: Server pipeline is busy. Waiting before processing user {user_id}.")
                    return

                can_run, reason, _ = self.can_run_today(user_id)
                if can_run:
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
