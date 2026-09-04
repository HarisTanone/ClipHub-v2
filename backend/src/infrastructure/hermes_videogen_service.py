"""Hermes Video Generator Auto-Post Service.

Autonomous daily trending discovery (3-5 videos/day) for Indonesia or Worldwide,
high-retention video generation with Hook, Subtitles, AI Text, Thumbnail, Watermark,
Transitions, and CTA, followed by autonomous social media scheduling & publishing.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection
from src.infrastructure.hermes_trending_service import hermes_trending_service

logger = logging.getLogger(__name__)


class HermesVideoGenService:
    """Service to discover daily trending topics, generate videos, and auto-post."""

    WIB = dt.timezone(dt.timedelta(hours=7))

    def __init__(self):
        self._run_lock = asyncio.Lock()
        self._last_scheduled_runs: dict[tuple[int, str], bool] = {}
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure SQLite tables for hermes_videogen_settings and hermes_videogen_runs exist."""
        conn = get_dict_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hermes_videogen_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    target_region TEXT NOT NULL DEFAULT 'ID',
                    daily_video_count INTEGER NOT NULL DEFAULT 3,
                    trending_sources TEXT NOT NULL DEFAULT 'google,youtube,tiktok,gemini',
                    niche_focus TEXT NOT NULL DEFAULT '',
                    voice TEXT NOT NULL DEFAULT 'Kore',
                    tts_provider TEXT NOT NULL DEFAULT 'gemini',
                    tts_model TEXT NOT NULL DEFAULT 'gemini-3.1-flash-tts-preview',
                    target_duration INTEGER NOT NULL DEFAULT 65,
                    aspect_ratio TEXT NOT NULL DEFAULT '9:16',
                    preset_slug TEXT NOT NULL DEFAULT 'default',
                    hook_enabled INTEGER NOT NULL DEFAULT 1,
                    subtitles_enabled INTEGER NOT NULL DEFAULT 1,
                    ai_text_enabled INTEGER NOT NULL DEFAULT 1,
                    thumbnail_enabled INTEGER NOT NULL DEFAULT 1,
                    watermark_enabled INTEGER NOT NULL DEFAULT 0,
                    watermark_text TEXT NOT NULL DEFAULT '',
                    transition_style TEXT NOT NULL DEFAULT 'dissolve',
                    cta_enabled INTEGER NOT NULL DEFAULT 1,
                    cta_headline TEXT NOT NULL DEFAULT 'Follow for more',
                    cta_button_text TEXT NOT NULL DEFAULT 'FOLLOW',
                    target_platforms TEXT NOT NULL DEFAULT 'tiktok,instagram,youtube',
                    target_account_ids TEXT NOT NULL DEFAULT '[]',
                    schedule_mode TEXT NOT NULL DEFAULT 'ai',
                    run_time TEXT NOT NULL DEFAULT '06:00',
                    today_videos_created INTEGER NOT NULL DEFAULT 0,
                    last_run_date TEXT DEFAULT NULL,
                    last_run_at TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS hermes_videogen_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    run_date TEXT NOT NULL,
                    trending_topic TEXT NOT NULL,
                    trending_source TEXT NOT NULL,
                    video_job_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    video_url TEXT DEFAULT NULL,
                    thumbnail_url TEXT DEFAULT NULL,
                    social_posts_scheduled INTEGER DEFAULT 0,
                    trigger_source TEXT DEFAULT 'daemon',
                    error_message TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Seed default settings for user 1 if not exists
            cur = conn.cursor()
            cur.execute("SELECT id FROM hermes_videogen_settings WHERE user_id = 1")
            if not cur.fetchone():
                conn.execute("""
                    INSERT INTO hermes_videogen_settings (
                        user_id, enabled, target_region, daily_video_count,
                        trending_sources, niche_focus, voice, tts_provider,
                        preset_slug, hook_enabled, subtitles_enabled, ai_text_enabled,
                        thumbnail_enabled, watermark_enabled, watermark_text,
                        transition_style, cta_enabled, cta_headline, cta_button_text,
                        target_platforms, target_account_ids, schedule_mode, run_time
                    ) VALUES (
                        1, 0, 'ID', 3,
                        'google,youtube,tiktok,gemini', '', 'Kore', 'gemini',
                        'default', 1, 1, 1,
                        1, 0, '',
                        'dissolve', 1, 'Follow for more', 'FOLLOW',
                        'tiktok,instagram,youtube', '[]', 'ai', '06:00'
                    )
                """)
            conn.commit()
        except Exception as e:
            logger.error(f"hermes_videogen: failed ensuring tables: {e}")
        finally:
            conn.close()

    def get_settings(self, user_id: int = 1) -> dict[str, Any]:
        """Fetch settings for a user with default fallback."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM hermes_videogen_settings WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                d = dict(row)
                try:
                    d["target_account_ids"] = json.loads(d.get("target_account_ids") or "[]")
                except Exception:
                    d["target_account_ids"] = []
                d["cta_text"] = d.get("cta_headline", "")
                return d
        finally:
            conn.close()

        return {
            "user_id": user_id,
            "enabled": False,
            "target_region": "ID",
            "daily_video_count": 3,
            "trending_sources": "google,youtube,tiktok,gemini",
            "niche_focus": "",
            "voice": "Kore",
            "tts_provider": "gemini",
            "tts_model": "gemini-3.1-flash-tts-preview",
            "target_duration": 65,
            "aspect_ratio": "9:16",
            "preset_slug": "default",
            "hook_enabled": True,
            "subtitles_enabled": True,
            "ai_text_enabled": True,
            "thumbnail_enabled": True,
            "watermark_enabled": False,
            "watermark_text": "",
            "transition_style": "dissolve",
            "cta_enabled": True,
            "cta_headline": "Follow for more",
            "cta_button_text": "FOLLOW",
            "cta_text": "Follow for more",
            "target_platforms": "tiktok,instagram,youtube",
            "target_account_ids": [],
            "schedule_mode": "ai",
            "run_time": "06:00",
            "today_videos_created": 0,
            "last_run_date": None,
            "last_run_at": None,
        }

    def update_settings(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update settings for a user."""
        self._ensure_tables()
        current = self.get_settings(user_id)
        if "cta_text" in data and "cta_headline" not in data:
            data["cta_headline"] = data["cta_text"]
        current.update(data)

        # Normalize target_account_ids
        target_accs = current.get("target_account_ids")
        if isinstance(target_accs, list):
            target_accs_json = json.dumps(target_accs)
        else:
            target_accs_json = "[]"

        # Constrain daily_video_count between 3 and 5
        daily_count = max(3, min(int(current.get("daily_video_count") or 3), 5))

        conn = get_dict_connection()
        try:
            conn.execute("""
                INSERT INTO hermes_videogen_settings (
                    user_id, enabled, target_region, daily_video_count,
                    trending_sources, niche_focus, voice, tts_provider, tts_model,
                    target_duration, aspect_ratio, preset_slug, hook_enabled,
                    subtitles_enabled, ai_text_enabled, thumbnail_enabled,
                    watermark_enabled, watermark_text, transition_style,
                    cta_enabled, cta_headline, cta_button_text, target_platforms,
                    target_account_ids, schedule_mode, run_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    target_region=excluded.target_region,
                    daily_video_count=excluded.daily_video_count,
                    trending_sources=excluded.trending_sources,
                    niche_focus=excluded.niche_focus,
                    voice=excluded.voice,
                    tts_provider=excluded.tts_provider,
                    tts_model=excluded.tts_model,
                    target_duration=excluded.target_duration,
                    aspect_ratio=excluded.aspect_ratio,
                    preset_slug=excluded.preset_slug,
                    hook_enabled=excluded.hook_enabled,
                    subtitles_enabled=excluded.subtitles_enabled,
                    ai_text_enabled=excluded.ai_text_enabled,
                    thumbnail_enabled=excluded.thumbnail_enabled,
                    watermark_enabled=excluded.watermark_enabled,
                    watermark_text=excluded.watermark_text,
                    transition_style=excluded.transition_style,
                    cta_enabled=excluded.cta_enabled,
                    cta_headline=excluded.cta_headline,
                    cta_button_text=excluded.cta_button_text,
                    target_platforms=excluded.target_platforms,
                    target_account_ids=excluded.target_account_ids,
                    schedule_mode=excluded.schedule_mode,
                    run_time=excluded.run_time,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                user_id,
                1 if current.get("enabled") else 0,
                current.get("target_region") or "ID",
                daily_count,
                current.get("trending_sources") or "google,youtube,tiktok,gemini",
                current.get("niche_focus") or "",
                current.get("voice") or "Kore",
                current.get("tts_provider") or "gemini",
                current.get("tts_model") or "gemini-3.1-flash-tts-preview",
                int(current.get("target_duration") or 65),
                current.get("aspect_ratio") or "9:16",
                current.get("preset_slug") or "default",
                1 if current.get("hook_enabled") else 0,
                1 if current.get("subtitles_enabled") else 0,
                1 if current.get("ai_text_enabled") else 0,
                1 if current.get("thumbnail_enabled") else 0,
                1 if current.get("watermark_enabled") else 0,
                current.get("watermark_text") or "",
                current.get("transition_style") or "dissolve",
                1 if current.get("cta_enabled") else 0,
                current.get("cta_headline") or "Follow for more",
                current.get("cta_button_text") or "FOLLOW",
                current.get("target_platforms") or "tiktok,instagram,youtube",
                target_accs_json,
                current.get("schedule_mode") or "ai",
                current.get("run_time") or "06:00",
            ))
            conn.commit()
        finally:
            conn.close()

        return self.get_settings(user_id)

    def can_run_today(self, user_id: int = 1) -> Tuple[bool, str, dict[str, Any]]:
        """Verify if the daily video quota (3-5 videos) has not been exceeded for today."""
        settings_dict = self.get_settings(user_id)
        today_date = dt.datetime.now(self.WIB).date().isoformat()
        daily_target = int(settings_dict.get("daily_video_count") or 3)

        # Count runs today in hermes_videogen_runs
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as count FROM hermes_videogen_runs
                WHERE user_id = ? AND run_date = ? AND status = 'completed'
            """, (user_id, today_date))
            row = cur.fetchone()
            today_count = row["count"] if row else 0
        finally:
            conn.close()

        remaining = max(0, daily_target - today_count)
        quota_info = {
            "today_created": today_count,
            "daily_target": daily_target,
            "remaining": remaining,
            "used_today": today_count,
            "daily_limit": daily_target,
            "remaining_today": remaining,
            "run_date": today_date,
        }

        if today_count >= daily_target:
            return False, f"Kuota harian Hermes Video Gen ({daily_target} video/hari) sudah tercapai hari ini ({today_count}/{daily_target}).", quota_info

        return True, f"Tersedia kuota {remaining} video lagi hari ini ({today_count}/{daily_target}).", quota_info

    async def run_daily_batch(
        self,
        user_id: int = 1,
        count: Optional[int] = None,
        force: bool = False,
        trigger_source: str = "web_dashboard",
        notify_telegram: bool = True,
        region_override: Optional[str] = None,
        count_override: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute daily trending video generation cycle."""
        async with self._run_lock:
            settings_dict = self.get_settings(user_id)
            if not settings_dict.get("enabled") and not force:
                return {
                    "success": False,
                    "status": "disabled",
                    "message": "Hermes Video Generator Auto-Post sedang dinonaktifkan di Settings.",
                }

            can_run, reason, quota = self.can_run_today(user_id)
            if not can_run and not force:
                return {
                    "success": False,
                    "status": "quota_exceeded",
                    "message": reason,
                    "quota": quota,
                }

            today_date = dt.datetime.now(self.WIB).date().isoformat()
            target_region = region_override or settings_dict.get("target_region") or "ID"
            sources_list = [s.strip() for s in (settings_dict.get("trending_sources") or "google,youtube,tiktok,gemini").split(",")]

            effective_count = count_override or count
            needed_count = effective_count or (quota["remaining"] if not force else int(settings_dict.get("daily_video_count") or 3))
            needed_count = max(1, min(needed_count, 5))

            logger.info(f"hermes_videogen: Fetching top {needed_count} trending topics for region {target_region}...")

            # 1. Fetch multi-source trending topics
            topics = await hermes_trending_service.get_trending_topics(
                region=target_region,
                count=needed_count,
                sources=sources_list,
                niche_focus=settings_dict.get("niche_focus") or "",
                use_cache=False,  # Fresh real-time data for generator run
            )

            if not topics:
                return {
                    "success": False,
                    "status": "no_topics",
                    "message": f"Tidak ditemukan topik trending baru untuk region {target_region}.",
                }

            from src.application.video_generator import get_video_generator
            vg = get_video_generator()

            # Resolve preset styles if configured
            preset_slug = settings_dict.get("preset_slug") or "default"
            hook_style = {"animation": "skia_impact_badge", "fontSize": 54, "bgColor": "#FACC15", "color": "#000000"}
            subtitle_style = {"fontFamily": "Montserrat", "fontSize": 52, "fontWeight": "800", "positionY": 84}

            preset = None
            try:
                from src.presentation.routes.presets import _get_preset_by_slug
                preset = _get_preset_by_slug(user_id, preset_slug)
                if preset:
                    if preset.get("hook_style"):
                        hook_style = preset["hook_style"]
                    if preset.get("subtitle_style"):
                        subtitle_style = preset["subtitle_style"]
            except Exception as pe:
                logger.debug(f"hermes_videogen: preset resolution skipped: {pe}")

            # Prepare Watermark Config (manual settings take precedence, otherwise fallback to existing preset)
            watermark_config = None
            if settings_dict.get("watermark_enabled") and settings_dict.get("watermark_text"):
                watermark_config = {
                    "enabled": True,
                    "type": "text",
                    "text": settings_dict["watermark_text"].strip(),
                    "position": "top-right",
                    "fontSize": 24,
                    "color": "#FFFFFF",
                    "opacity": 75,
                }
            elif preset and preset.get("watermark_style") and preset["watermark_style"].get("enabled"):
                wm = preset["watermark_style"]
                watermark_config = {
                    "enabled": True,
                    "type": wm.get("type", "text"),
                    "text": (wm.get("text") or "").strip(),
                    "position": wm.get("position", "top-right"),
                    "fontSize": wm.get("fontSize", 24),
                    "color": wm.get("color", "#FFFFFF"),
                    "opacity": wm.get("opacity", 75),
                }

            # Prepare CTA Config (manual settings take precedence, otherwise fallback to existing preset)
            cta_config = None
            if settings_dict.get("cta_enabled"):
                cta_config = {
                    "enabled": True,
                    "headline": settings_dict.get("cta_headline") or "Follow for more",
                    "buttonText": settings_dict.get("cta_button_text") or "FOLLOW",
                    "ctaType": "card",
                    "duration": 3.0,
                }
            elif preset and preset.get("cta_style") and preset["cta_style"].get("enabled"):
                cs = preset["cta_style"]
                cta_config = {
                    "enabled": True,
                    "headline": cs.get("headline") or "Follow for more",
                    "buttonText": cs.get("buttonText") or "FOLLOW",
                    "ctaType": cs.get("ctaType", "card"),
                    "duration": float(cs.get("duration", 3.0)),
                }

            created_jobs = []
            successful_runs = []

            for item in topics[:needed_count]:
                topic_title = item.get("topic", "")
                hook_text = item.get("hook", "")
                custom_instructions = (
                    f"Topik trending: {topic_title}. "
                    f"Sudut pandang: {item.get('angle', '')}. "
                    f"Poin penting: {', '.join(item.get('key_points', []))}. "
                    f"CTA: {item.get('recommended_cta', '')}."
                )

                logger.info(f"hermes_videogen: Creating video job for trending topic: '{topic_title}'")

                job = vg.create_job(
                    topic=topic_title,
                    target_duration=int(settings_dict.get("target_duration") or 65),
                    tts_provider=settings_dict.get("tts_provider") or "gemini",
                    tts_model=settings_dict.get("tts_model") or "gemini-3.1-flash-tts-preview",
                    voice=settings_dict.get("voice") or "Kore",
                    instructions=custom_instructions,
                    num_scenes=5,
                    subtitles_enabled=bool(settings_dict.get("subtitles_enabled", True)),
                    subtitle_style=subtitle_style,
                    hook_enabled=bool(settings_dict.get("hook_enabled", True)),
                    custom_hook=hook_text if hook_text else None,
                    hook_style=hook_style,
                    include_bgm=True,
                    bgm_volume=0.15,
                    watermark_config=watermark_config,
                    transition=settings_dict.get("transition_style") or "dissolve",
                    cta_config=cta_config,
                    ai_text_config={"enabled": bool(settings_dict.get("ai_text_enabled", True))},
                    aspect_ratio=settings_dict.get("aspect_ratio") or "9:16",
                    user_id=user_id,
                )

                created_jobs.append(job.job_id)

                # Execute pipeline synchronously for this batch item
                try:
                    await vg.run_pipeline(job.job_id)
                    fresh_job = vg.get_job(job.job_id)
                    if fresh_job and fresh_job.status.value == "completed":
                        # Auto-post to Social Media if platforms configured
                        scheduled_posts = await self._dispatch_social_autopost(
                            fresh_job, settings_dict, user_id, trending_item=item
                        )

                        # Record successful run in database
                        self._record_run(
                            user_id=user_id,
                            run_date=today_date,
                            topic=topic_title,
                            source=item.get("source", "Multi-source Trending"),
                            job_id=job.job_id,
                            video_url=f"/api/video-generator/jobs/{job.job_id}/video",
                            thumbnail_url=fresh_job.thumbnail_url,
                            social_posts_count=scheduled_posts,
                            trigger_source=trigger_source,
                        )

                        successful_runs.append({
                            "job_id": job.job_id,
                            "topic": topic_title,
                            "output_path": fresh_job.output_path,
                            "thumbnail_url": fresh_job.thumbnail_url,
                            "social_posts": scheduled_posts,
                        })
                    else:
                        err_msg = fresh_job.error if fresh_job else "Pipeline execution failed"
                        self._record_run(
                            user_id=user_id,
                            run_date=today_date,
                            topic=topic_title,
                            source=item.get("source", "Multi-source Trending"),
                            job_id=job.job_id,
                            status="failed",
                            error_message=err_msg,
                            trigger_source=trigger_source,
                        )
                except Exception as run_err:
                    logger.error(f"hermes_videogen: error generating video for {topic_title}: {run_err}", exc_info=True)

            # Update last run date in settings
            now_iso = dt.datetime.now(self.WIB).isoformat()
            conn = get_dict_connection()
            try:
                conn.execute("""
                    UPDATE hermes_videogen_settings
                    SET last_run_date = ?, last_run_at = ?
                    WHERE user_id = ?
                """, (today_date, now_iso, user_id))
                conn.commit()
            finally:
                conn.close()

            # Telegram Notification if enabled
            if notify_telegram and successful_runs:
                await self._notify_telegram_batch(successful_runs, target_region)

            _, _, updated_quota = self.can_run_today(user_id)
            return {
                "success": len(successful_runs) > 0,
                "status": "completed" if successful_runs else "failed",
                "message": f"Berhasil memproses {len(successful_runs)} video trending dari {len(topics)} topik.",
                "runs": successful_runs,
                "quota": updated_quota,
            }

    def _generate_dynamic_post_metadata(
        self,
        job: Any,
        trending_item: Optional[dict[str, Any]] = None,
        region: str = "ID",
    ) -> tuple[str, str, list[str]]:
        """Generate dynamic title, viral caption, and contextual hashtags from topic analysis."""
        topic = job.topic or "Trending Topic"
        hook = job.custom_hook or (job.story or {}).get("hook") or topic
        title = (job.story or {}).get("title") or topic

        # Extract dynamic keywords for hashtags
        keywords: list[str] = []
        if trending_item:
            if trending_item.get("category"):
                keywords.append(trending_item["category"].replace(" ", ""))
            for kw in trending_item.get("search_keywords", []):
                cleaned = re.sub(r"[^A-Za-z0-9]", "", kw)
                if cleaned and len(cleaned) > 2:
                    keywords.append(cleaned)

        # Also extract keywords from topic title
        topic_words = re.findall(r"\b[A-Za-z0-9]{3,}\b", topic)
        stopwords = {"yang", "pada", "dalam", "untuk", "dari", "ini", "itu", "dan", "dengan", "akan", "the", "and", "for", "with"}
        for w in topic_words:
            if w.lower() not in stopwords:
                keywords.append(w.capitalize())

        # Deduplicate and build dynamic hashtag list
        seen = set()
        dynamic_tags: list[str] = []
        for kw in keywords:
            tag = kw if kw.startswith("#") else f"#{kw}"
            clean_tag = tag.lower()
            if clean_tag not in seen:
                seen.add(clean_tag)
                dynamic_tags.append(tag)
            if len(dynamic_tags) >= 5:
                break

        # Standard viral discovery tag according to region
        if region == "ID":
            dynamic_tags.extend(["#TrendingHariIni", "#FYP", "#ViralIndonesia"])
        else:
            dynamic_tags.extend(["#Trending", "#Viral", "#FYP"])

        # Deduplicate final list
        final_tags: list[str] = []
        final_seen = set()
        for t in dynamic_tags:
            cl = t.lower()
            if cl not in final_seen:
                final_seen.add(cl)
                final_tags.append(t)
            if len(final_tags) >= 6:
                break

        hashtags_str = " ".join(final_tags)

        # Dynamic caption composition
        angle_desc = ""
        if trending_item and trending_item.get("angle"):
            angle_desc = f"{trending_item['angle']}\n\n"

        cta_phrase = (
            trending_item.get("recommended_cta")
            if trending_item and trending_item.get("recommended_cta")
            else "Komen pendapat kamu di bawah dan follow untuk update seru berikutnya!" if region == "ID" else "Share your thoughts in the comments and follow for more!"
        )

        caption = f"{hook}\n\n{angle_desc}{cta_phrase}\n\n{hashtags_str}"
        return title[:100], caption, [t.lstrip("#") for t in final_tags]

    async def _dispatch_social_autopost(
        self,
        job: Any,
        settings_dict: dict[str, Any],
        user_id: int,
        trending_item: Optional[dict[str, Any]] = None,
    ) -> int:
        """Schedule or post the generated video to configured social accounts with dynamic cover and captions."""
        target_platforms = (settings_dict.get("target_platforms") or "").split(",")
        target_platforms = [p.strip().lower() for p in target_platforms if p.strip()]
        target_account_ids = settings_dict.get("target_account_ids") or []

        if not target_platforms:
            return 0

        try:
            from src.infrastructure.social_auto_post_service import SocialAutoPostService
            from src.infrastructure.social_compliance import resolve_public_media_base_url
            from src.presentation.routes.social.helpers import repliz_post
            from src.infrastructure.gdrive_uploader import gdrive_uploader

            auto_post = SocialAutoPostService()
            user_accounts = await auto_post.get_connected_accounts(user_id=user_id)
            if not user_accounts:
                logger.info(f"hermes_videogen: No active social accounts found for user {user_id}. Skipping auto-post.")
                return 0

            # Calculate smart schedule time
            schedule_mode = settings_dict.get("schedule_mode") or "ai"
            scheduled_times = auto_post.calculate_ai_schedule_times(clip_count=1)
            scheduled_at = scheduled_times[0].isoformat() if scheduled_times and schedule_mode == "ai" else None

            # Resolve public URLs for media
            public_backend = resolve_public_media_base_url()
            video_url = f"{public_backend}/api/video-generator/jobs/{job.job_id}/video" if public_backend else ""
            thumb_url = f"{public_backend}/api/video-generator/jobs/{job.job_id}/thumbnail" if public_backend else ""

            # Fallback to Google Drive if configured and public_backend is missing
            if not video_url and gdrive_uploader.is_configured and job.output_path and os.path.exists(job.output_path):
                try:
                    drive_res = gdrive_uploader.upload_video(job.output_path, filename=f"{job.job_id}_video.mp4")
                    video_url = drive_res.get("direct_link", "") or drive_res.get("web_view_link", "")
                    thumb_path = os.path.join(settings.VIDEO_GEN_OUTPUT_DIR, job.job_id, f"thumbnail_{job.job_id}.jpg")
                    if os.path.exists(thumb_path):
                        th_res = gdrive_uploader.upload_image(thumb_path, filename=f"{job.job_id}_thumb.jpg")
                        thumb_url = th_res.get("direct_link", "") or th_res.get("web_view_link", "")
                except Exception as g_err:
                    logger.warning(f"hermes_videogen: GDrive upload failed for job {job.job_id}: {g_err}")

            if not video_url:
                logger.warning(f"hermes_videogen: No public video URL for job {job.job_id}. Auto-post dispatch requires AUTOCLIPER_PUBLIC_URL, Cloudflare Tunnel, or Google Drive.")
                return 0

            target_region = settings_dict.get("target_region") or "ID"
            title, caption, tags = self._generate_dynamic_post_metadata(job, trending_item=trending_item, region=target_region)

            posts_count = 0
            for acc in user_accounts:
                acc_plat = (acc.get("platform") or "").lower().strip()
                acc_id = acc.get("account_id") or acc.get("id")
                if not acc_id:
                    continue

                if acc_plat in target_platforms:
                    if target_account_ids and str(acc_id) not in [str(x) for x in target_account_ids]:
                        continue

                    post_type = "reel" if acc_plat == "facebook" else "video"
                    media_item = {
                        "alt": title,
                        "customThumbnail": bool(thumb_url),
                        "type": "video",
                        "thumbnail": thumb_url or "",
                        "coverUrl": thumb_url or "",
                        "cover": thumb_url or "",
                        "url": video_url,
                    }

                    payload = {
                        "title": title[:100],
                        "description": caption,
                        "topic": (job.topic or title)[:50],
                        "type": post_type,
                        "medias": [media_item],
                        "meta": {"title": "", "description": "", "url": ""},
                        "additionalInfo": {
                            "isAiGenerated": False,
                            "isDraft": False,
                            "coverTimestampMs": 1200,
                            "coverTimestamp": 1.2,
                            "tags": tags if acc_plat == "youtube" else [],
                        },
                        "accountId": acc_id,
                    }
                    if scheduled_at:
                        payload["scheduleAt"] = scheduled_at

                    try:
                        res = await repliz_post("/public/schedule", json_body=payload)
                        logger.info(f"hermes_videogen: Scheduled/posted job {job.job_id} to {acc_plat} ({acc_id}): {res}")
                        posts_count += 1
                    except Exception as post_err:
                        logger.warning(f"hermes_videogen: failed posting to {acc_plat} ({acc_id}): {post_err}")

            return posts_count
        except Exception as e:
            logger.warning(f"hermes_videogen: social dispatch failed: {e}")
            return 0

    def _record_run(
        self,
        user_id: int,
        run_date: str,
        topic: str,
        source: str,
        job_id: str,
        status: str = "completed",
        video_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        social_posts_count: int = 0,
        trigger_source: str = "daemon",
        error_message: Optional[str] = None,
    ) -> None:
        """Record execution run in hermes_videogen_runs table."""
        conn = get_dict_connection()
        try:
            conn.execute("""
                INSERT INTO hermes_videogen_runs (
                    user_id, run_date, trending_topic, trending_source,
                    video_job_id, status, video_url, thumbnail_url,
                    social_posts_scheduled, trigger_source, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, run_date, topic, source, job_id, status,
                video_url, thumbnail_url, social_posts_count, trigger_source, error_message,
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"hermes_videogen: failed recording run: {e}")
        finally:
            conn.close()

    async def _notify_telegram_batch(self, successful_runs: list[dict], region: str) -> None:
        """Send a summary notification to Telegram if configured."""
        try:
            from src.infrastructure.telegram_service import telegram_service
            if not telegram_service.is_enabled():
                return

            text = (
                f"<b>[Hermes Video Generator] Trending Batch Selesai</b>\n\n"
                f"<b>Region Target:</b> {region}\n"
                f"<b>Total Video Dibuat:</b> {len(successful_runs)}\n\n"
            )
            for i, r in enumerate(successful_runs, 1):
                text += f"{i}. <b>{r['topic']}</b>\n"
                if r.get("social_posts", 0) > 0:
                    text += f"   Auto-post dijadwalkan ke {r['social_posts']} platform sosial.\n"

            await telegram_service.send_message(text)
        except Exception as e:
            logger.debug(f"hermes_videogen: Telegram notification failed: {e}")

    def get_history(self, user_id: int = 1, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch history of hermes video generator runs."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM hermes_videogen_runs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (user_id, limit))
            rows = []
            for r in cur.fetchall():
                d = dict(r)
                d["topic"] = d.get("trending_topic")
                d["source"] = d.get("trending_source")
                rows.append(d)
            return rows
        finally:
            conn.close()


    async def start_scheduler_loop(self) -> None:
        """Background loop executing daily scheduled runs at user configured run_time (WIB)."""
        logger.info("hermes_videogen_scheduler: Started background daemon loop")
        while True:
            try:
                await self._check_and_run_scheduled_videogens()
            except asyncio.CancelledError:
                logger.info("hermes_videogen_scheduler: Stopped daemon loop")
                break
            except Exception as e:
                logger.error(f"hermes_videogen_scheduler: Loop error: {e}", exc_info=True)
            await asyncio.sleep(45)

    async def _check_and_run_scheduled_videogens(self) -> None:
        """Check users with enabled Hermes Video Generator and execute at run_time."""
        self._ensure_tables()
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT s.* FROM hermes_videogen_settings s
                JOIN users u ON s.user_id = u.id
                WHERE s.enabled = 1 AND u.is_active = 1
                ORDER BY s.id ASC
            """)
            rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return

        now_wib = dt.datetime.now(self.WIB)
        current_hm = now_wib.strftime("%H:%M")
        today_date = now_wib.date().isoformat()

        for row in rows:
            r = dict(row)
            user_id = r.get("user_id")
            if not user_id or not bool(r.get("enabled")):
                continue

            raw_time = str(r.get("run_time") or "06:00").strip()
            try:
                parts = raw_time.split(":")
                norm_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            except Exception:
                norm_time = "06:00"

            if current_hm == norm_time:
                if self._last_scheduled_runs.get((user_id, today_date)):
                    continue

                can_run, _, _ = self.can_run_today(user_id)
                if can_run:
                    self._last_scheduled_runs[(user_id, today_date)] = True
                    logger.info(f"hermes_videogen_scheduler: Triggering scheduled daily batch for user {user_id} at {current_hm} WIB...")
                    try:
                        await self.run_daily_batch(
                            user_id=user_id,
                            trigger_source="daemon_scheduler",
                            notify_telegram=True,
                        )
                    except Exception as err:
                        logger.error(f"hermes_videogen_scheduler: Run error for user {user_id}: {err}", exc_info=True)

    # Aliases
    run_daily_cycle = run_daily_batch
    get_runs = get_history


# Singleton instance


hermes_videogen_service = HermesVideoGenService()
