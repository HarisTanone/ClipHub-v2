"""TelegramService — Comprehensive Telegram bot, group, channel & video automation."""
import asyncio
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional
import httpx

from src.config import settings
from src.infrastructure.db_connection import get_dict_connection, get_connection

logger = logging.getLogger(__name__)


def _ensure_telegram_table():
    """Ensure the telegram_settings database table exists with full schema."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS telegram_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_enabled INTEGER NOT NULL DEFAULT 0,
                bot_token TEXT NOT NULL DEFAULT '',
                bot_username TEXT NOT NULL DEFAULT '',
                chat_id TEXT NOT NULL DEFAULT '',
                group_id TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL DEFAULT '',
                topic_id TEXT NOT NULL DEFAULT '',
                allowed_users TEXT NOT NULL DEFAULT '',
                notify_on_job_start INTEGER NOT NULL DEFAULT 1,
                notify_on_job_complete INTEGER NOT NULL DEFAULT 1,
                notify_on_job_failed INTEGER NOT NULL DEFAULT 1,
                send_video_files INTEGER NOT NULL DEFAULT 1,
                include_caption INTEGER NOT NULL DEFAULT 1,
                include_hashtags INTEGER NOT NULL DEFAULT 1,
                include_virality_score INTEGER NOT NULL DEFAULT 1,
                notify_target TEXT NOT NULL DEFAULT 'all',
                auto_post_social INTEGER NOT NULL DEFAULT 0,
                auto_post_platforms TEXT NOT NULL DEFAULT '',
                auto_post_schedule_mode TEXT NOT NULL DEFAULT 'ai',
                auto_post_interval_hours INTEGER NOT NULL DEFAULT 4,
                auto_post_peak_hours TEXT NOT NULL DEFAULT '11:30,15:00,18:30,20:30',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Auto-migration for existing tables without new columns
        existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(telegram_settings)").fetchall()}
        migrations = [
            ("auto_post_social", "INTEGER NOT NULL DEFAULT 0"),
            ("auto_post_platforms", "TEXT NOT NULL DEFAULT ''"),
            ("auto_post_schedule_mode", "TEXT NOT NULL DEFAULT 'ai'"),
            ("auto_post_interval_hours", "INTEGER NOT NULL DEFAULT 4"),
            ("auto_post_peak_hours", "TEXT NOT NULL DEFAULT '11:30,15:00,18:30,20:30'"),
        ]
        for col_name, col_def in migrations:
            if col_name not in existing_cols:
                try:
                    cur.execute(f"ALTER TABLE telegram_settings ADD COLUMN {col_name} {col_def}")
                except Exception as e:
                    logger.debug(f"telegram: migration note for {col_name}: {e}")

        # Check if default row exists
        cur.execute("SELECT id FROM telegram_settings WHERE id = 1")
        if not cur.fetchone():
            default_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or os.getenv("ALERT_TELEGRAM_TOKEN", "")
            default_chat = getattr(settings, "TELEGRAM_CHAT_ID", "") or os.getenv("ALERT_TELEGRAM_CHAT_ID", "")
            is_enabled = 1 if (default_token and default_chat) else 0
            cur.execute("""
                INSERT INTO telegram_settings (
                    id, is_enabled, bot_token, chat_id, group_id, channel_id, notify_target,
                    auto_post_social, auto_post_platforms, auto_post_schedule_mode
                ) VALUES (1, ?, ?, ?, '', '', 'all', 0, '', 'ai')
            """, (is_enabled, default_token, default_chat))
        conn.commit()
    except Exception as e:
        logger.warning(f"telegram: table init warning: {e}")
    finally:
        conn.close()


_ensure_telegram_table()


class TelegramService:
    """Service to manage Telegram Bot credentials, settings, alerts, and video clip sending."""

    def __init__(self):
        _ensure_telegram_table()

    def get_settings(self, mask_token: bool = False) -> Dict[str, Any]:
        """Fetch current Telegram settings from SQLite."""
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM telegram_settings WHERE id = 1")
            row = cur.fetchone()
            if not row:
                return {
                    "is_enabled": False,
                    "bot_token": "",
                    "bot_username": "",
                    "chat_id": "",
                    "group_id": "",
                    "channel_id": "",
                    "topic_id": "",
                    "allowed_users": "",
                    "notify_on_job_start": True,
                    "notify_on_job_complete": True,
                    "notify_on_job_failed": True,
                    "send_video_files": True,
                    "include_caption": True,
                    "include_hashtags": True,
                    "include_virality_score": True,
                    "notify_target": "all",
                }
            data = dict(row)
            data["is_enabled"] = bool(data.get("is_enabled", 0))
            data["notify_on_job_start"] = bool(data.get("notify_on_job_start", 1))
            data["notify_on_job_complete"] = bool(data.get("notify_on_job_complete", 1))
            data["notify_on_job_failed"] = bool(data.get("notify_on_job_failed", 1))
            data["send_video_files"] = bool(data.get("send_video_files", 1))
            data["include_caption"] = bool(data.get("include_caption", 1))
            data["include_hashtags"] = bool(data.get("include_hashtags", 1))
            data["include_virality_score"] = bool(data.get("include_virality_score", 1))
            data["auto_post_social"] = bool(data.get("auto_post_social", 0))
            data["auto_post_platforms"] = str(data.get("auto_post_platforms", "")).strip()
            data["auto_post_schedule_mode"] = str(data.get("auto_post_schedule_mode", "ai")).strip()
            data["auto_post_interval_hours"] = int(data.get("auto_post_interval_hours", 4))
            data["auto_post_peak_hours"] = str(data.get("auto_post_peak_hours", "11:30,15:00,18:30,20:30")).strip()

            if mask_token and data.get("bot_token"):
                token = data["bot_token"]
                if len(token) > 10:
                    data["bot_token_masked"] = token[:4] + "••••••••" + token[-4:]
                else:
                    data["bot_token_masked"] = "••••••••"

            return data
        finally:
            conn.close()

    def update_settings(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Update Telegram configuration."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE telegram_settings SET
                    is_enabled = ?,
                    bot_token = ?,
                    bot_username = ?,
                    chat_id = ?,
                    group_id = ?,
                    channel_id = ?,
                    topic_id = ?,
                    allowed_users = ?,
                    notify_on_job_start = ?,
                    notify_on_job_complete = ?,
                    notify_on_job_failed = ?,
                    send_video_files = ?,
                    include_caption = ?,
                    include_hashtags = ?,
                    include_virality_score = ?,
                    notify_target = ?,
                    auto_post_social = ?,
                    auto_post_platforms = ?,
                    auto_post_schedule_mode = ?,
                    auto_post_interval_hours = ?,
                    auto_post_peak_hours = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (
                1 if new_settings.get("is_enabled") else 0,
                str(new_settings.get("bot_token", "")).strip(),
                str(new_settings.get("bot_username", "")).strip(),
                str(new_settings.get("chat_id", "")).strip(),
                str(new_settings.get("group_id", "")).strip(),
                str(new_settings.get("channel_id", "")).strip(),
                str(new_settings.get("topic_id", "")).strip(),
                str(new_settings.get("allowed_users", "")).strip(),
                1 if new_settings.get("notify_on_job_start", True) else 0,
                1 if new_settings.get("notify_on_job_complete", True) else 0,
                1 if new_settings.get("notify_on_job_failed", True) else 0,
                1 if new_settings.get("send_video_files", True) else 0,
                1 if new_settings.get("include_caption", True) else 0,
                1 if new_settings.get("include_hashtags", True) else 0,
                1 if new_settings.get("include_virality_score", True) else 0,
                str(new_settings.get("notify_target", "all")).strip(),
                1 if new_settings.get("auto_post_social") else 0,
                str(new_settings.get("auto_post_platforms", "")).strip(),
                str(new_settings.get("auto_post_schedule_mode", "ai")).strip(),
                int(new_settings.get("auto_post_interval_hours", 4)),
                str(new_settings.get("auto_post_peak_hours", "11:30,15:00,18:30,20:30")).strip(),
            ))
            conn.commit()
            logger.info("telegram: settings updated successfully")
            return self.get_settings()
        finally:
            conn.close()

    async def test_connection(
        self,
        bot_token: Optional[str] = None,
        target_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Test bot token via getMe and optionally send a test ping to target chat/group."""
        cfg = self.get_settings()
        token = bot_token if bot_token is not None else cfg.get("bot_token", "")
        if not token:
            return {"success": False, "error": "Bot token tidak boleh kosong"}

        t_start = time.time()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # 1. Test getMe
                res = await client.get(f"https://api.telegram.org/bot{token}/getMe")
                latency_ms = round((time.time() - t_start) * 1000)

                if res.status_code != 200:
                    err_msg = res.json().get("description", f"HTTP {res.status_code}")
                    return {
                        "success": False,
                        "error": f"Bot token tidak valid: {err_msg}",
                        "latency_ms": latency_ms,
                    }

                bot_info = res.json().get("result", {})
                bot_username = bot_info.get("username", "")
                bot_name = bot_info.get("first_name", "")

                # Update bot_username in DB if changed
                if bot_username:
                    try:
                        c = get_connection()
                        c.execute("UPDATE telegram_settings SET bot_username = ? WHERE id = 1", (bot_username,))
                        c.commit()
                        c.close()
                    except Exception:
                        pass

                # 2. Test send message if target provided or in settings
                destination = target_id or cfg.get("chat_id") or cfg.get("group_id") or cfg.get("channel_id")
                msg_sent = False
                send_error = None

                if destination:
                    test_msg = (
                        f"🤖 <b>ClipHub Telegram Bot Connected!</b>\n\n"
                        f"• <b>Bot:</b> {bot_name} (@{bot_username})\n"
                        f"• <b>Target:</b> <code>{destination}</code>\n"
                        f"• <b>Latency:</b> <code>{latency_ms}ms</code>\n"
                        f"• <b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                        f"✨ <i>Koneksi bot dan grup/channel Telegram siap digunakan!</i>"
                    )
                    payload: Dict[str, Any] = {
                        "chat_id": destination,
                        "text": test_msg,
                        "parse_mode": "HTML",
                    }
                    if cfg.get("topic_id"):
                        try:
                            payload["message_thread_id"] = int(cfg["topic_id"])
                        except ValueError:
                            pass

                    send_res = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json=payload
                    )
                    if send_res.status_code == 200:
                        msg_sent = True
                    else:
                        send_error = send_res.json().get("description", f"HTTP {send_res.status_code}")

                return {
                    "success": True,
                    "bot_name": bot_name,
                    "bot_username": bot_username,
                    "latency_ms": latency_ms,
                    "message_sent": msg_sent,
                    "destination": destination,
                    "send_error": send_error,
                }

        except Exception as e:
            return {"success": False, "error": f"Koneksi gagal: {str(e)}"}

    def _get_target_destinations(self, cfg: Dict[str, Any], explicit_target: Optional[str] = None) -> List[str]:
        """Resolve list of destination chat IDs to broadcast to."""
        if explicit_target:
            return [explicit_target]

        mode = cfg.get("notify_target", "all")
        destinations = []

        if mode in ("chat", "all") and cfg.get("chat_id"):
            destinations.append(cfg["chat_id"])
        if mode in ("group", "all") and cfg.get("group_id"):
            destinations.append(cfg["group_id"])
        if mode in ("channel", "all") and cfg.get("channel_id"):
            destinations.append(cfg["channel_id"])

        # Deduplicate preserving order
        seen = set()
        out = []
        for d in destinations:
            if d and d not in seen:
                seen.add(d)
                out.append(d)
        return out

    async def send_message(
        self,
        html_text: str,
        target_id: Optional[str] = None,
        disable_preview: bool = True
    ) -> bool:
        """Send formatted HTML message to configured targets."""
        cfg = self.get_settings()
        if not cfg.get("is_enabled") and not target_id:
            return False

        token = cfg.get("bot_token")
        if not token:
            return False

        destinations = self._get_target_destinations(cfg, target_id)
        if not destinations:
            return False

        success = False
        async with httpx.AsyncClient(timeout=15) as client:
            for chat_id in destinations:
                try:
                    payload: Dict[str, Any] = {
                        "chat_id": chat_id,
                        "text": html_text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": disable_preview,
                    }
                    if cfg.get("topic_id"):
                        try:
                            payload["message_thread_id"] = int(cfg["topic_id"])
                        except ValueError:
                            pass

                    res = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json=payload
                    )
                    if res.status_code == 200:
                        success = True
                    else:
                        logger.warning(f"telegram: sendMessage to {chat_id} failed: {res.text[:150]}")
                except Exception as e:
                    logger.warning(f"telegram: sendMessage error for {chat_id}: {e}")

        return success

    async def send_video(
        self,
        video_path: str,
        caption: str = "",
        target_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send actual MP4 video file to Telegram chat/group/channel."""
        cfg = self.get_settings()
        token = cfg.get("bot_token")
        if not token:
            return {"success": False, "error": "Bot token belum diatur"}

        if not os.path.exists(video_path):
            return {"success": False, "error": f"File video tidak ditemukan: {video_path}"}

        file_size = os.path.getsize(video_path)
        # Telegram Bot API max file upload is 50MB (52428800 bytes)
        if file_size > 50 * 1024 * 1024:
            logger.warning(f"telegram: file {video_path} is {file_size / (1024*1024):.1f}MB (>50MB limit)")
            # Send message instead with warning
            await self.send_message(
                f"⚠️ <b>Video Terlalu Besar untuk Dikirim Langsung</b>\n\n"
                f"File: <code>{os.path.basename(video_path)}</code> ({file_size / (1024*1024):.1f}MB)\n"
                f"Batas upload Telegram Bot API adalah 50MB.",
                target_id=target_id
            )
            return {"success": False, "error": "Ukuran video melebihi batas Telegram Bot API (50MB)"}

        destinations = self._get_target_destinations(cfg, target_id)
        if not destinations:
            return {"success": False, "error": "Tidak ada target Chat ID / Group ID / Channel ID yang dikonfigurasi"}

        sent_count = 0
        last_error = None

        # Truncate caption if > 1024 characters (Telegram caption limit)
        clean_caption = caption[:1020] if len(caption) > 1024 else caption

        async with httpx.AsyncClient(timeout=60) as client:
            for chat_id in destinations:
                try:
                    data: Dict[str, Any] = {
                        "chat_id": chat_id,
                        "caption": clean_caption,
                        "parse_mode": "HTML",
                        "supports_streaming": "true",
                    }
                    if cfg.get("topic_id"):
                        try:
                            data["message_thread_id"] = str(cfg["topic_id"])
                        except ValueError:
                            pass

                    with open(video_path, "rb") as vf:
                        files = {
                            "video": (os.path.basename(video_path), vf, "video/mp4")
                        }
                        res = await client.post(
                            f"https://api.telegram.org/bot{token}/sendVideo",
                            data=data,
                            files=files
                        )

                    if res.status_code == 200:
                        sent_count += 1
                        logger.info(f"telegram: sent video {os.path.basename(video_path)} to {chat_id}")
                    else:
                        last_error = res.json().get("description", f"HTTP {res.status_code}")
                        logger.warning(f"telegram: sendVideo failed to {chat_id}: {last_error}")
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"telegram: sendVideo exception for {chat_id}: {e}")

        return {
            "success": sent_count > 0,
            "sent_count": sent_count,
            "error": last_error if sent_count == 0 else None
        }

    async def notify_job_started(self, job_id: str, title: str, source_url: str) -> bool:
        """Send notification when a video processing job starts."""
        cfg = self.get_settings()
        if not cfg.get("is_enabled") or not cfg.get("notify_on_job_start"):
            return False

        short_id = job_id.replace("job_", "")[:8]
        msg = (
            f"🎬 <b>Job Rendering Dimulai</b>\n\n"
            f"📌 <b>Judul:</b> {title or 'Video'}\n"
            f"🔗 <b>Source:</b> {source_url}\n"
            f"🆔 <code>{short_id}</code>\n"
            f"⏳ <i>Sedang menganalisis momen terbaik & merender klip 9:16...</i>"
        )
        return await self.send_message(msg)

    async def notify_job_completed(
        self,
        job_id: str,
        title: str,
        clips_count: int,
        clips: List[Dict[str, Any]],
        output_dir: Optional[str] = None
    ) -> bool:
        """Send notification when job completes, and send video clips if enabled."""
        cfg = self.get_settings()
        if not cfg.get("is_enabled") or not cfg.get("notify_on_job_complete"):
            return False

        short_id = job_id.replace("job_", "")[:8]
        msg = (
            f"🎉 <b>Job Selesai — {clips_count} Klip Siap!</b>\n\n"
            f"📌 <b>Judul:</b> {title or 'Video'}\n"
            f"🆔 <code>{short_id}</code>\n"
            f"✂️ <b>Total Klip:</b> {clips_count}\n\n"
        )

        for i, clip in enumerate(clips[:5], 1):
            hook = clip.get("hook") or f"Clip #{clip.get('rank', i)}"
            score = clip.get("virality_score") or clip.get("score")
            score_str = f" [Score: {score}]" if score is not None and cfg.get("include_virality_score") else ""
            msg += f"• #{clip.get('rank', i)}: {hook}{score_str}\n"

        if clips_count > 5:
            msg += f"\n<i>...dan {clips_count - 5} klip lainnya.</i>\n"

        msg += f"\n👉 <i>Buka dashboard ClipHub untuk review & download.</i>"

        await self.send_message(msg)

        # If send_video_files is enabled and output_dir exists, send the video clips!
        if cfg.get("send_video_files") and output_dir and os.path.exists(output_dir):
            for clip in clips:
                rank = clip.get("rank", 1)
                # Find final video file
                candidates = [
                    os.path.join(output_dir, f"clip_{rank:02d}_final.mp4"),
                    os.path.join(output_dir, f"clip_{rank:02d}.mp4"),
                    os.path.join(output_dir, f"final_{rank}.mp4"),
                ]
                video_file = next((c for c in candidates if os.path.exists(c)), None)
                if video_file:
                    hook_title = clip.get("hook", f"Clip #{rank}")
                    tags = " #fyp #viral #shorts #reels #podcast" if cfg.get("include_hashtags") else ""
                    caption = f"🎬 <b>Clip #{rank}:</b> {hook_title}\n\n{tags}"
                    await self.send_video(video_file, caption=caption)
                    # small delay between sending multiple videos
                    await asyncio.sleep(1.0)

        # Trigger AI Auto-Post to Social Media if enabled
        if cfg.get("auto_post_social") and output_dir and os.path.exists(output_dir):
            try:
                from src.infrastructure.social_auto_post_service import social_auto_post_service
                platforms = [p.strip() for p in cfg.get("auto_post_platforms", "").split(",") if p.strip()]
                asyncio.create_task(social_auto_post_service.auto_schedule_job_clips(
                    job_id=job_id,
                    clips=clips,
                    output_dir=output_dir,
                    target_platforms=platforms or None,
                    schedule_mode=cfg.get("auto_post_schedule_mode", "ai"),
                    notify_telegram=True,
                ))
            except Exception as e:
                logger.warning(f"telegram: failed to trigger auto-post: {e}")

        return True

    async def notify_job_failed(self, job_id: str, error: str, title: str = "") -> bool:
        """Send notification when a video processing job fails."""
        cfg = self.get_settings()
        if not cfg.get("is_enabled") or not cfg.get("notify_on_job_failed"):
            return False

        short_id = job_id.replace("job_", "")[:8]
        msg = (
            f"❌ <b>Job Gagal Diproses</b>\n\n"
            f"📌 <b>Judul:</b> {title or 'Video'}\n"
            f"🆔 <code>{short_id}</code>\n"
            f"⚠️ <b>Error:</b> <code>{error[:300]}</code>"
        )
        return await self.send_message(msg)

    async def send_clip_by_rank(
        self,
        job_id: str,
        clip_rank: int,
        custom_caption: Optional[str] = None,
        target_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find and send a specific clip from a job."""
        job_output_dir = os.path.join(settings.OUTPUT_DIR, job_id)
        candidates = [
            os.path.join(job_output_dir, f"clip_{clip_rank:02d}_final.mp4"),
            os.path.join(job_output_dir, f"clip_{clip_rank:02d}.mp4"),
            os.path.join(job_output_dir, f"final_{clip_rank}.mp4"),
        ]
        video_file = next((c for c in candidates if os.path.exists(c)), None)
        if not video_file:
            return {"success": False, "error": f"File video klip #{clip_rank} belum tersedia"}

        caption = custom_caption or f"🎬 Clip #{clip_rank} - {job_id}"
        return await self.send_video(video_file, caption=caption, target_id=target_id)


# Global singleton instance
telegram_service = TelegramService()
