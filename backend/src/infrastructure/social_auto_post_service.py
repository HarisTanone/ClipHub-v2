"""SocialAutoPostService — AI Smart Scheduling & Auto-Publishing to Social Media."""
import asyncio
import datetime as dt
import logging
import os
import random
from typing import Any, Dict, List, Optional

from src.config import settings
from src.infrastructure.clip_outputs import find_final_clip
from src.infrastructure.db_connection import get_dict_connection
from src.infrastructure.gdrive_uploader import gdrive_uploader
from src.presentation.routes.social.helpers import repliz_get, repliz_post

logger = logging.getLogger(__name__)


class SocialAutoPostService:
    """Service to automatically schedule and post video clips to social media via AI."""

    DEFAULT_PEAK_HOURS = ["11:30", "15:00", "18:30", "20:30"]

    def calculate_ai_schedule_times(
        self,
        clip_count: int,
        peak_hours_str: str = "",
        interval_hours: int = 4,
        start_time: Optional[dt.datetime] = None,
    ) -> List[dt.datetime]:
        """Calculate smart AI scheduled posting timestamps for a series of clips.

        Distributes clips across peak engagement hours with organic natural jitter (±3-7 mins).
        """
        now = start_time or dt.datetime.now(dt.timezone.utc)
        
        # Parse peak hours
        raw_hours = [h.strip() for h in (peak_hours_str or "").split(",") if h.strip()]
        if not raw_hours:
            raw_hours = self.DEFAULT_PEAK_HOURS

        peak_slots = []
        for h in raw_hours:
            try:
                parts = h.split(":")
                peak_slots.append((int(parts[0]), int(parts[1]) if len(parts) > 1 else 0))
            except Exception:
                pass

        if not peak_slots:
            peak_slots = [(11, 30), (15, 0), (18, 30), (20, 30)]

        peak_slots.sort()

        schedule_times: List[dt.datetime] = []
        current_day = now.date()

        # Minimum delay from now (at least 15 minutes in future)
        min_start = now + dt.timedelta(minutes=15)

        # Build candidate slots starting from current day up to next 7 days
        candidate_slots: List[dt.datetime] = []
        for day_offset in range(10):
            target_date = current_day + dt.timedelta(days=day_offset)
            for hour, minute in peak_slots:
                slot = dt.datetime(
                    year=target_date.year,
                    month=target_date.month,
                    day=target_date.day,
                    hour=hour,
                    minute=minute,
                    tzinfo=dt.timezone.utc,
                )
                if slot > min_start:
                    candidate_slots.append(slot)

        # Assign slots to each clip with natural jitter
        for i in range(clip_count):
            if i < len(candidate_slots):
                base_slot = candidate_slots[i]
            else:
                last_slot = schedule_times[-1] if schedule_times else min_start
                base_slot = last_slot + dt.timedelta(hours=interval_hours)

            # Add jitter between -5 and +5 minutes
            jitter_sec = random.randint(-300, 300)
            slot_with_jitter = base_slot + dt.timedelta(seconds=jitter_sec)
            if slot_with_jitter <= now:
                slot_with_jitter = now + dt.timedelta(minutes=15 + (i * 30))

            schedule_times.append(slot_with_jitter)

        return schedule_times

    async def get_connected_accounts(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch active connected social accounts from DB or Repliz."""
        accounts = []
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            query = "SELECT * FROM social_accounts"
            params = []
            if user_id is not None:
                query += " WHERE user_id = ?"
                params.append(user_id)
            cur.execute(query, tuple(params))
            for row in cur.fetchall():
                accounts.append(dict(row))
        except Exception as e:
            logger.warning(f"Failed to fetch accounts from DB: {e}")
        finally:
            conn.close()

        # If empty or needed, fetch live accounts from Repliz
        if not accounts:
            try:
                live_res = await repliz_get("/public/account?page=1&limit=50")
                if isinstance(live_res, dict) and "docs" in live_res:
                    for acc in live_res["docs"]:
                        if acc.get("isConnected"):
                            accounts.append({
                                "account_id": acc.get("_id") or acc.get("id"),
                                "platform": acc.get("type", "unknown").lower(),
                                "name": acc.get("name") or acc.get("username", "Account"),
                            })
            except Exception as e:
                logger.warning(f"Failed to fetch live Repliz accounts: {e}")

        return accounts

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
            else:
                tags = "\n\n#viral #video #trending"

        full_caption = f"{caption_body}{tags}".strip()
        return full_caption

    async def auto_schedule_job_clips(
        self,
        job_id: str,
        clips: List[Dict[str, Any]],
        output_dir: str,
        target_platforms: Optional[List[str]] = None,
        schedule_mode: str = "ai",
        notify_telegram: bool = True,
    ) -> Dict[str, Any]:
        """Execute automated scheduling of video clips to social accounts."""
        if not clips:
            return {"success": False, "error": "No clips to schedule"}

        # 1. Fetch available connected social accounts
        all_accounts = await self.get_connected_accounts()
        if not all_accounts:
            logger.info("auto_post: No connected social accounts found.")
            return {"success": False, "error": "Belum ada akun sosial media yang terhubung di ClipHub"}

        # 2. Filter accounts by requested platforms / account IDs
        selected_accounts = []
        if target_platforms:
            target_set = {p.strip().lower() for p in target_platforms if p.strip()}
            if "all" in target_set:
                selected_accounts = all_accounts
            else:
                for acc in all_accounts:
                    plat = acc.get("platform", "").lower()
                    acc_id = str(acc.get("account_id", ""))
                    if plat in target_set or acc_id in target_set:
                        selected_accounts.append(acc)
        else:
            selected_accounts = all_accounts

        if not selected_accounts:
            return {"success": False, "error": "Tidak ada akun yang cocok dengan platform yang dipilih"}

        # 3. Calculate schedule times
        if schedule_mode == "instant":
            now = dt.datetime.now(dt.timezone.utc)
            schedule_times = [now + dt.timedelta(minutes=2 + (i * 3)) for i in range(len(clips))]
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

            # Upload video to Google Drive or get public URL
            video_url = ""
            if gdrive_uploader.is_configured:
                try:
                    filename = f"{job_id}_clip{rank}.mp4"
                    drive_res = gdrive_uploader.upload_video(clip_file, filename=filename)
                    video_url = drive_res.get("direct_link", "")
                except Exception as e:
                    logger.error(f"auto_post: GDrive upload failed for clip #{rank}: {e}")
                    errors.append(f"Clip #{rank} GDrive upload: {str(e)}")

            if not video_url:
                logger.warning(f"auto_post: No public video URL for clip #{rank}. GDrive must be configured.")
                continue

            scheduled_time = schedule_times[i] if i < len(schedule_times) else dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)
            schedule_iso = scheduled_time.isoformat()

            # Schedule on each target account
            for acc in selected_accounts:
                platform = acc.get("platform", "video")
                caption = self.extract_clip_caption(clip, platform=platform)
                title = clip.get("hook", f"Clip #{rank}")[:100]

                payload = {
                    "title": title,
                    "description": caption,
                    "type": "video",
                    "medias": [
                        {
                            "alt": title,
                            "customThumbnail": False,
                            "type": "video",
                            "thumbnail": "",
                            "url": video_url,
                        }
                    ],
                    "meta": {"title": "", "description": "", "url": ""},
                    "additionalInfo": {
                        "isAiGenerated": True,
                        "isDraft": False,
                        "isAutoAddMusic": False,
                        "collaborators": [],
                        "mentions": [],
                        "music": {"id": "", "artist": "", "name": "", "thumbnail": ""},
                        "products": [],
                        "tags": [],
                        "targetCountries": [],
                    },
                    "replies": [],
                    "accountId": acc["account_id"],
                    "scheduleAt": schedule_iso,
                }

                try:
                    res = await repliz_post("/public/schedule", json_body=payload)
                    scheduled_records.append({
                        "clip_rank": rank,
                        "account_name": acc.get("name", platform),
                        "platform": platform,
                        "schedule_at": schedule_iso,
                        "title": title,
                        "res": res,
                    })
                    logger.info(f"auto_post: Scheduled clip #{rank} on {platform} ({acc.get('name')}) at {schedule_iso}")
                except Exception as e:
                    logger.error(f"auto_post: Failed to schedule clip #{rank} on {platform}: {e}")
                    errors.append(f"{platform} ({acc.get('name')}): {str(e)}")

        # 5. Send notification to Telegram if enabled
        if notify_telegram and scheduled_records:
            try:
                from src.infrastructure.telegram_service import telegram_service
                msg = (
                    f"🚀 <b>AI Auto-Post Scheduled ({len(scheduled_records)} Postingan)</b>\n\n"
                    f"📌 <b>Job:</b> <code>{job_id[:12]}</code>\n"
                    f"🤖 <b>Mode:</b> AI Smart Peak-Hours\n\n"
                )
                for rec in scheduled_records[:6]:
                    time_display = rec['schedule_at'][:16].replace("T", " ")
                    msg += f"• <b>Clip #{rec['clip_rank']}</b> ➔ <b>{rec['platform'].upper()}</b> ({rec['account_name']})\n"
                    msg += f"  ⏰ <code>{time_display} UTC</code>\n"
                    msg += f"  💬 <i>{rec['title'][:40]}...</i>\n\n"

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
