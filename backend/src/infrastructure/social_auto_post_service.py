"""SocialAutoPostService — AI Smart Scheduling & Auto-Publishing to Social Media via Repliz API."""
import asyncio
import datetime as dt
import logging
import os
import random
import re
from typing import Any, Dict, List, Optional

from src.config import settings
from src.infrastructure.clip_outputs import find_final_clip
from src.infrastructure.db_connection import get_dict_connection
from src.infrastructure.gdrive_uploader import gdrive_uploader
from src.infrastructure.social_compliance import (
    ensure_social_compliant_video,
    ensure_social_compliant_thumbnail,
    validate_social_media_constraints,
)
from src.presentation.routes.social.helpers import repliz_get, repliz_post

logger = logging.getLogger(__name__)


class SocialAutoPostService:
    """Service to automatically schedule and post video clips to social media via AI and Repliz."""

    WIB = dt.timezone(dt.timedelta(hours=7))
    DEFAULT_PEAK_HOURS = ["07:30", "09:00", "11:30", "13:30", "15:00", "17:00", "18:30", "20:00", "21:30"]

    def calculate_ai_schedule_times(
        self,
        clip_count: int,
        peak_hours_str: str = "",
        interval_hours: int = 2,
        start_time: Optional[dt.datetime] = None,
        same_day: bool = True,
    ) -> List[dt.datetime]:
        """Calculate smart AI scheduled posting timestamps for a series of clips.

        Rule:
        - Active posting window is strictly 07:00 WIB to 22:00 WIB (07:00 AM - 10:00 PM).
        - When processing in the morning (e.g. Hermes 05:00/06:00 AM), all generated clips
          are scheduled on the SAME DAY across distinct, evenly-spaced hours in the 07:00 - 22:00 window.
        - Spaced evenly with human jitter (±1.5 minutes) and minimum 15-minute gap.
        - Returns timestamps in UTC for Repliz API compatibility.
        """
        if clip_count <= 0:
            return []

        # Reference time in WIB (UTC+7)
        if start_time:
            now_wib = start_time if start_time.tzinfo else start_time.replace(tzinfo=dt.timezone.utc)
            now_wib = now_wib.astimezone(self.WIB)
        else:
            now_wib = dt.datetime.now(self.WIB)

        # Minimum margin: TikTok & Repliz require scheduleAt to be >= 15 minutes in the future
        min_start_wib = now_wib + dt.timedelta(minutes=15)

        target_date = now_wib.date()
        window_start_wib = dt.datetime(target_date.year, target_date.month, target_date.day, 7, 0, tzinfo=self.WIB)
        window_end_wib = dt.datetime(target_date.year, target_date.month, target_date.day, 22, 0, tzinfo=self.WIB)

        # Earliest possible slot today: at least 07:00 WIB, and at least now + 15 mins
        day_start_wib = max(window_start_wib, min_start_wib)

        # If current time is already too late today (< 20 mins before 22:00 WIB), target tomorrow 07:00 - 22:00 WIB
        if day_start_wib >= window_end_wib - dt.timedelta(minutes=20):
            target_date = target_date + dt.timedelta(days=1)
            window_start_wib = dt.datetime(target_date.year, target_date.month, target_date.day, 7, 0, tzinfo=self.WIB)
            window_end_wib = dt.datetime(target_date.year, target_date.month, target_date.day, 22, 0, tzinfo=self.WIB)
            day_start_wib = window_start_wib

        available_minutes = (window_end_wib - day_start_wib).total_seconds() / 60.0

        schedule_times: List[dt.datetime] = []

        if clip_count == 1:
            # 1 clip: pick middle or day_start_wib
            slot = day_start_wib + dt.timedelta(minutes=min(30, int(available_minutes / 2)))
            schedule_times.append(min(slot, window_end_wib))
        else:
            # Distribute all N clips evenly across the range [day_start_wib, window_end_wib]
            buffer_min = 20.0 if available_minutes > 60 else 5.0
            effective_span = max(15.0 * (clip_count - 1), available_minutes - buffer_min)
            step_minutes = effective_span / float(clip_count - 1)

            for i in range(clip_count):
                offset_min = i * step_minutes
                base_slot = day_start_wib + dt.timedelta(minutes=offset_min)
                jitter_sec = random.randint(-90, 90)
                slot_with_jitter = base_slot + dt.timedelta(seconds=jitter_sec)
                clamped_slot = max(day_start_wib, min(slot_with_jitter, window_end_wib))
                schedule_times.append(clamped_slot)

            # Ensure strict chronological order with at least 15 mins gap
            sorted_times: List[dt.datetime] = []
            for t in sorted(schedule_times):
                if sorted_times and t < sorted_times[-1] + dt.timedelta(minutes=15):
                    t = sorted_times[-1] + dt.timedelta(minutes=15)
                if t > window_end_wib:
                    t = window_end_wib
                sorted_times.append(t)

            schedule_times = sorted_times

        # Return all scheduled times converted to UTC
        return [t.astimezone(dt.timezone.utc) for t in schedule_times]

    def calculate_custom_schedule_times(
        self,
        clip_count: int,
        custom_time_str: str = "",
        interval_hours: int = 2,
        start_time: Optional[dt.datetime] = None,
    ) -> List[dt.datetime]:
        """Calculate schedule timestamps starting from a user-specified custom time/datetime."""
        now = start_time or dt.datetime.now(dt.timezone.utc)
        min_start = now + dt.timedelta(minutes=2)

        base_dt: Optional[dt.datetime] = None
        if custom_time_str:
            try:
                # Try ISO format first (e.g. 2026-08-25T15:30:00)
                if "T" in custom_time_str or "-" in custom_time_str:
                    clean_str = custom_time_str.replace("Z", "+00:00")
                    base_dt = dt.datetime.fromisoformat(clean_str)
                    if base_dt.tzinfo is None:
                        base_dt = base_dt.replace(tzinfo=dt.timezone.utc)
                # Try HH:MM format (e.g. 15:30)
                elif ":" in custom_time_str:
                    parts = custom_time_str.strip().split(":")
                    hour = int(parts[0])
                    minute = int(parts[1]) if len(parts) > 1 else 0
                    today = now.date()
                    candidate = dt.datetime(today.year, today.month, today.day, hour, minute, tzinfo=dt.timezone.utc)
                    if candidate <= min_start:
                        # Schedule for tomorrow if time has already passed today
                        candidate += dt.timedelta(days=1)
                    base_dt = candidate
            except Exception as e:
                logger.warning(f"Failed to parse custom schedule time '{custom_time_str}': {e}")

        if not base_dt or base_dt < min_start:
            base_dt = min_start

        schedule_times: List[dt.datetime] = []
        for i in range(clip_count):
            slot = base_dt + dt.timedelta(hours=i * max(1, interval_hours))
            schedule_times.append(slot)

        return schedule_times

    async def get_connected_accounts(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch active connected social accounts from DB and Repliz."""
        local_accounts = []
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            query = "SELECT sa.*, u.email as owner_email, u.full_name as owner_name FROM social_accounts sa LEFT JOIN users u ON sa.user_id = u.id"
            params = []
            if user_id is not None:
                query += " WHERE sa.user_id = ?"
                params.append(user_id)
            cur.execute(query, tuple(params))
            for row in cur.fetchall():
                local_accounts.append(dict(row))
        except Exception as e:
            logger.warning(f"Failed to fetch accounts from DB: {e}")
        finally:
            conn.close()

        # Fetch live accounts from Repliz
        repliz_map = {}
        try:
            live_res = await repliz_get("/public/account?page=1&limit=100")
            if isinstance(live_res, dict) and "docs" in live_res:
                for acc in live_res["docs"]:
                    acc_id = str(acc.get("_id") or acc.get("id") or "")
                    if acc_id:
                        repliz_map[acc_id] = acc
        except Exception as e:
            logger.warning(f"Failed to fetch live Repliz accounts: {e}")

        # Merge local metadata with Repliz live data
        merged_accounts = []
        for la in local_accounts:
            acc_id = str(la.get("account_id", ""))
            live_data = repliz_map.get(acc_id, {})
            is_connected = live_data.get("isConnected", True) if repliz_map else True
            if is_connected:
                merged_accounts.append({
                    "account_id": acc_id,
                    "platform": (live_data.get("type") or la.get("platform") or "unknown").lower(),
                    "name": live_data.get("name") or la.get("name") or "Account",
                    "username": live_data.get("username") or "",
                    "picture": live_data.get("picture") or "",
                    "user_id": la.get("user_id"),
                    "owner_email": la.get("owner_email"),
                })

        # If no local mapping found and user_id is None (superadmin), use Repliz directly
        if not merged_accounts and user_id is None and repliz_map:
            for acc_id, acc in repliz_map.items():
                if acc.get("isConnected", True):
                    merged_accounts.append({
                        "account_id": acc_id,
                        "platform": acc.get("type", "unknown").lower(),
                        "name": acc.get("name") or acc.get("username", "Account"),
                        "username": acc.get("username") or "",
                        "picture": acc.get("picture") or "",
                        "user_id": None,
                    })

        return merged_accounts

    async def get_platforms_status(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Check connection status for each social media platform for the user."""
        all_platforms = ["tiktok", "instagram", "youtube", "facebook", "threads", "linkedin"]
        connected_accs = await self.get_connected_accounts(user_id=user_id)

        status_by_platform: Dict[str, Any] = {}
        for plat in all_platforms:
            matched = [a for a in connected_accs if a.get("platform", "").lower() == plat]
            status_by_platform[plat] = {
                "connected": len(matched) > 0,
                "count": len(matched),
                "accounts": matched,
            }

        return {
            "total_accounts": len(connected_accs),
            "platforms": status_by_platform,
            "has_any_connected": len(connected_accs) > 0,
        }

    def extract_clip_caption(
        self,
        clip: Dict[str, Any],
        platform: str = "",
        include_hashtags: bool = True,
    ) -> str:
        """Extract optimized caption and hashtags for a specific platform from clip metadata."""
        hook = clip.get("hook") or f"Clip #{clip.get('rank', 1)}"
        captions_dict = clip.get("captions") or {}

        # Platform specific caption priority
        platform_lower = platform.lower()
        if platform_lower in captions_dict and captions_dict[platform_lower]:
            caption_body = captions_dict[platform_lower]
        elif "tiktok" in captions_dict and captions_dict["tiktok"]:
            caption_body = captions_dict["tiktok"]
        elif "instagram" in captions_dict and captions_dict["instagram"]:
            caption_body = captions_dict["instagram"]
        elif clip.get("reason"):
            caption_body = f"{hook}\n\n{clip['reason']}"
        else:
            caption_body = hook

        # Hashtags
        tags = ""
        if include_hashtags:
            if platform_lower in ("tiktok", "instagram"):
                tags = "\n\n#fyp #viral #trending #reels #podcast #shorts #autocliper"
            elif platform_lower == "youtube":
                tags = "\n\n#Shorts #Viral #Podcast #Trending"
            elif platform_lower == "threads":
                tags = "\n\n#threads #viral #trending"
            else:
                tags = "\n\n#viral #video #trending"

        full_caption = f"{caption_body}{tags}".strip()
        # Cap caption length to 2000 chars to strictly comply with TikTok (2200) and Instagram (2200) limits
        if len(full_caption) > 2000:
            full_caption = full_caption[:1990].rstrip() + "..."
        return full_caption

    async def auto_schedule_job_clips(
        self,
        job_id: str,
        clips: List[Dict[str, Any]],
        output_dir: str,
        user_id: Optional[int] = None,
        target_platforms: Optional[List[str]] = None,
        target_account_ids: Optional[List[str]] = None,
        schedule_mode: str = "ai",
        custom_schedule_time: Optional[str] = None,
        notify_telegram: bool = True,
    ) -> Dict[str, Any]:
        """Execute automated scheduling of video clips to social accounts via Google Drive & Repliz API."""
        if not clips:
            return {"success": False, "error": "Tidak ada klip untuk dijadwalkan"}

        # 1. Fetch available connected social accounts for this user
        all_accounts = await self.get_connected_accounts(user_id=user_id)
        if not all_accounts:
            logger.info(f"auto_post: No connected social accounts found for user_id={user_id}.")
            return {"success": False, "error": "Belum ada akun sosial media yang terhubung di ClipHub"}

        # 2. Filter accounts by requested account IDs or platforms
        selected_accounts = []
        if target_account_ids and len(target_account_ids) > 0:
            target_ids_set = {str(aid).strip() for aid in target_account_ids if str(aid).strip()}
            for acc in all_accounts:
                if str(acc.get("account_id")) in target_ids_set or str(acc.get("username")) in target_ids_set:
                    selected_accounts.append(acc)

        if not selected_accounts and target_platforms:
            target_set = {p.strip().lower() for p in target_platforms if p.strip()}
            if "all" in target_set:
                selected_accounts = all_accounts
            else:
                for acc in all_accounts:
                    plat = acc.get("platform", "").lower()
                    acc_id = str(acc.get("account_id", ""))
                    if plat in target_set or acc_id in target_set:
                        selected_accounts.append(acc)
        elif not selected_accounts and not target_platforms:
            selected_accounts = all_accounts

        if not selected_accounts:
            return {
                "success": False,
                "error": "Tidak ada akun sosial media yang cocok atau terhubung untuk platform yang dipilih",
            }

        # 3. Calculate schedule times
        if schedule_mode == "instant":
            now = dt.datetime.now(dt.timezone.utc)
            schedule_times = [now + dt.timedelta(minutes=2 + (i * 3)) for i in range(len(clips))]
        elif schedule_mode == "custom" or custom_schedule_time:
            schedule_times = self.calculate_custom_schedule_times(
                clip_count=len(clips),
                custom_time_str=custom_schedule_time or "",
                interval_hours=2,
            )
        else:
            schedule_times = self.calculate_ai_schedule_times(clip_count=len(clips))

        # 4. Schedule each clip to selected accounts
        scheduled_records = []
        errors = []

        for i, clip in enumerate(clips):
            rank = clip.get("rank", i + 1)
            clip_file = find_final_clip(output_dir, rank)
            if not clip_file or not os.path.exists(clip_file):
                logger.warning(f"auto_post: Final video for clip #{rank} not found at {output_dir}")
                continue

            # Ensure 100% compliant MP4 format for TikTok and Instagram Reels (H.264 + AAC + yuv420p + faststart)
            try:
                compliant_clip_file = ensure_social_compliant_video(clip_file)
            except Exception as e:
                logger.warning(f"auto_post: Video compliance check fallback on clip #{rank}: {e}")
                compliant_clip_file = clip_file

            # Resolve public direct URL for Repliz (prefer direct tunnel/public URL)
            from src.infrastructure.social_compliance import resolve_public_media_base_url

            video_url = ""
            thumb_url = None
            public_backend = resolve_public_media_base_url()

            if public_backend:
                video_url = f"{public_backend}/api/jobs/{job_id}/clips/{rank}/final"
                thumb_url = f"{public_backend}/api/jobs/{job_id}/clips/{rank}/thumb"
            elif gdrive_uploader.is_configured:
                try:
                    filename = f"{job_id}_clip{rank}.mp4"
                    drive_res = gdrive_uploader.upload_video(compliant_clip_file, filename=filename)
                    video_url = drive_res.get("direct_link", "") or drive_res.get("web_view_link", "")
                except Exception as e:
                    logger.error(f"auto_post: GDrive upload failed for clip #{rank}: {e}")
                    errors.append(f"Clip #{rank} GDrive upload: {str(e)}")

                try:
                    thumb_dir = os.path.join(output_dir, "thumbnail")
                    candidate_thumb = os.path.join(thumb_dir, f"clip_{rank:02d}.jpg")
                    if not os.path.exists(candidate_thumb):
                        candidate_thumb = os.path.join(thumb_dir, f"clip_{rank:02d}_thumb.jpg")

                    compliant_thumb = ensure_social_compliant_thumbnail(
                        thumb_path=candidate_thumb if os.path.exists(candidate_thumb) else None,
                        video_path=compliant_clip_file,
                        output_path=os.path.join(thumb_dir, f"clip_{rank:02d}_social.jpg"),
                    )

                    if compliant_thumb and os.path.exists(compliant_thumb):
                        thumb_res = gdrive_uploader.upload_image(
                            compliant_thumb, filename=f"{job_id}_clip{rank}_thumb.jpg"
                        )
                        thumb_url = thumb_res.get("direct_link") or thumb_res.get("web_view_link")
                except Exception as e:
                    logger.warning(f"auto_post: Thumbnail upload skipped for clip #{rank}: {e}")

            if not video_url:
                logger.warning(f"auto_post: No public video URL for clip #{rank}. AUTOCLIPER_PUBLIC_URL or GDrive must be configured.")
                continue

            scheduled_time = schedule_times[i] if i < len(schedule_times) else dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)
            # Format ISO 8601 UTC string (e.g. 2026-08-28T12:00:00.000Z)
            schedule_iso = scheduled_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            # Extract tags for YouTube and hashtags
            raw_tags = []
            caption_hashtags = re.findall(r"#(\w+)", clip.get("hook", "") + " " + clip.get("reason", ""))
            if caption_hashtags:
                raw_tags = caption_hashtags[:10]
            if not raw_tags:
                raw_tags = ["Shorts", "Viral", "Trending", "Podcast"]

            # Schedule on each target account
            for acc in selected_accounts:
                platform = acc.get("platform", "video").lower()

                # Programmatic duration & constraint audit required by TikTok / Meta API
                if os.path.exists(compliant_clip_file):
                    valid, constraint_err = validate_social_media_constraints(
                        compliant_clip_file, platform=platform
                    )
                    if not valid:
                        logger.warning(
                            f"auto_post: Clip #{rank} skipped for {platform} ({acc.get('name')}): {constraint_err}"
                        )
                        errors.append(f"{platform} ({acc.get('name')}): {constraint_err}")
                        continue

                caption = self.extract_clip_caption(clip, platform=platform)
                title = clip.get("hook", f"Clip #{rank}")[:100]

                # Post type per platform: reel for Facebook, video for Instagram, TikTok, YouTube, Threads, LinkedIn
                post_type = "reel" if platform == "facebook" else "video"

                media_item: Dict[str, Any] = {
                    "alt": title,
                    "customThumbnail": bool(thumb_url),
                    "type": "video",
                    "thumbnail": thumb_url or "",
                    "url": video_url,
                }

                payload = {
                    "title": title,
                    "description": caption,
                    "topic": clip.get("topic") or (title[:50] if platform == "threads" else ""),
                    "type": post_type,
                    "medias": [media_item],
                    "meta": {"title": "", "description": "", "url": ""},
                    "additionalInfo": {
                        "isAiGenerated": False,
                        "isDraft": False,
                        "isAutoAddMusic": False,
                        "collaborators": [],
                        "mentions": [],
                        "music": {"id": "", "artist": "", "name": "", "thumbnail": ""},
                        "products": [],
                        "tags": raw_tags if platform == "youtube" else [],
                        "targetCountries": [],
                    },
                    "replies": [],
                    "accountId": acc["account_id"],
                    "scheduleAt": schedule_iso,
                }

                try:
                    res = await repliz_post("/public/schedule", json_body=payload)
                    schedule_id = (
                        res.get("scheduleId") or res.get("_id") or res.get("id")
                        if isinstance(res, dict)
                        else None
                    )

                    scheduled_records.append({
                        "clip_rank": rank,
                        "account_name": acc.get("name", platform),
                        "username": acc.get("username", ""),
                        "platform": platform,
                        "schedule_at": schedule_iso,
                        "title": title,
                        "schedule_id": schedule_id,
                        "res": res,
                    })
                    logger.info(f"auto_post: Scheduled clip #{rank} on {platform} ({acc.get('name')}) scheduleId={schedule_id} at {schedule_iso}")
                except Exception as e:
                    logger.error(f"auto_post: Failed to schedule clip #{rank} on {platform}: {e}")
                    errors.append(f"{platform} ({acc.get('name')}): {str(e)}")

        # 5. Send notification to Telegram if enabled
        if notify_telegram and scheduled_records:
            try:
                from src.infrastructure.telegram_service import telegram_service
                msg = (
                    f"<b>AI Auto-Post Scheduled ({len(scheduled_records)} Postingan)</b>\n\n"
                    f"<b>Job:</b> <code>{job_id[:12]}</code>\n"
                    f"<b>Mode:</b> {schedule_mode.upper()}\n\n"
                )
                for rec in scheduled_records[:6]:
                    user_tag = f" (@{rec['username']})" if rec.get('username') else ""
                    sched_tag = f" [ID: <code>{rec['schedule_id'][:8]}...</code>]" if rec.get('schedule_id') else ""
                    try:
                        t_utc = dt.datetime.fromisoformat(rec['schedule_at'].replace("Z", "+00:00"))
                        t_wib = t_utc.astimezone(self.WIB)
                        wib_str = t_wib.strftime("%H:%M WIB (%d %b)")
                    except Exception:
                        wib_str = rec['schedule_at'][:16].replace("T", " ")
                    msg += f"• <b>Clip #{rec['clip_rank']}</b> -> <b>{rec['platform'].upper()}</b> ({rec['account_name']}{user_tag}){sched_tag}\n"
                    msg += f"  Waktu: <code>{wib_str}</code>\n"
                    msg += f"  Title: <i>{rec['title'][:40]}...</i>\n\n"

                if len(scheduled_records) > 6:
                    msg += f"<i>...dan {len(scheduled_records) - 6} postingan lainnya.</i>\n"

                await telegram_service.send_message(msg)
            except Exception as e:
                logger.warning(f"auto_post: Failed to send Telegram notification: {e}")

        return {
            "success": len(scheduled_records) > 0,
            "scheduled_count": len(scheduled_records),
            "records": scheduled_records,
            "errors": errors,
        }


# Singleton instance
social_auto_post_service = SocialAutoPostService()
