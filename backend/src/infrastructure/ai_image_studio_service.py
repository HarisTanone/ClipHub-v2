"""AI Image Studio Service — Autonomous Image/Carousel & Visual Studio.

Provides:
1. Dynamic AI Image Generation via 9router / Gemini Image API gateway.
   Never hardcoded — reads NINE_ROUTER_BASE_URL, NINE_ROUTER_API_KEY, IMAGE_GEN_MODEL
   directly from system settings / model settings store.
2. Stock Photo & Video Footage sourcing (Pexels, Pixabay, Giphy, User Upload).
3. Rich Typography Rendering Engine (12 Pinterest & Editorial presets).
4. Video Footage compositing with timed typography and background music.
5. Autonomous Daily Hermes Scheduler with multiple slots per day (Pagi, Siang, Malam).
6. Auto-publishing / scheduling to social media accounts (TikTok, Instagram, etc. via Repliz).
7. MinIO persistence with local static fallback.
Zero emoji tolerance.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import io
import json
import logging
import os
import random
import re
import shutil
import subprocess
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image

from src.config import settings
from src.infrastructure.ai_image_typography import (
    AVAILABLE_FONTS,
    RESOLUTIONS,
    TypographyContent,
    typography_engine,
)
from src.infrastructure.image_typography_store import (
    get_all_typography_templates,
    get_typography_template,
)
from src.infrastructure.db_connection import get_dict_connection
from src.infrastructure.minio_service import MinioService
from src.infrastructure.model_settings_store import get_model_setting
from src.infrastructure.nine_router_client import NineRouterClient
from src.infrastructure.system_config_store import get_system_setting

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tmp", "image_studio"))
ASSETS_MUSIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "music"))


class AIImageStudioService:
    """Service to generate visual content, composite typography, and orchestrate Hermes auto-posting."""

    WIB = dt.timezone(dt.timedelta(hours=7))

    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(ASSETS_MUSIC_DIR, exist_ok=True)
        self._minio = MinioService()
        self._run_lock = asyncio.Lock()
        self._last_scheduled_runs: dict[tuple[int, str, str], bool] = {}
        self._ensure_tables()

    # ─── Dynamic Settings Resolution (Zero Hardcoding) ───────────────────────

    def get_image_api_endpoint(self) -> str:
        """Dynamically resolve image generation endpoint from settings/system.

        Reads from DB system_config_store / model_settings_store first,
        falling back to NINE_ROUTER_BASE_URL. Never uses hardcoded URLs.
        """
        override_url = get_system_setting("IMAGE_GEN_BASE_URL") or getattr(settings, "IMAGE_GEN_BASE_URL", "")
        base_url = (
            override_url
            or get_system_setting("NINE_ROUTER_BASE_URL")
            or get_model_setting("NINE_ROUTER_BASE_URL")
            or getattr(settings, "NINE_ROUTER_BASE_URL", "")
            or "http://127.0.0.1:20128/v1"
        ).strip().rstrip("/")

        if base_url.endswith("/images/generations"):
            return base_url
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return f"{base_url}/images/generations"

    def get_image_api_key(self) -> str:
        """Dynamically resolve image generation API key from settings/system or 9router."""
        return (
            get_system_setting("IMAGE_GEN_API_KEY")
            or get_model_setting("NINE_ROUTER_API_KEY")
            or get_system_setting("NINE_ROUTER_API_KEY")
            or getattr(settings, "IMAGE_GEN_API_KEY", "")
            or getattr(settings, "NINE_ROUTER_API_KEY", "")
            or ""
        ).strip()

    def get_image_model(self, model_hint: Optional[str] = None) -> str:
        """Dynamically resolve image generation model from user hint or settings/system."""
        if model_hint and model_hint != "auto" and model_hint.strip():
            return model_hint.strip()
        return (
            get_system_setting("IMAGE_GEN_MODEL")
            or get_model_setting("IMAGE_GEN_MODEL")
            or getattr(settings, "IMAGE_GEN_MODEL", "")
            or "ag/gemini-3.1-flash-image"
        ).strip()

    def _ensure_tables(self) -> None:
        """Create SQLite tables for AI image generator settings and runs if not exists."""
        conn = get_dict_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_image_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    topics TEXT NOT NULL DEFAULT '["Motivasi & Stoicism", "Mindset Sukses & Finansial", "Teknologi & Masa Depan AI", "Strategi Bisnis Modern"]',
                    daily_slots TEXT NOT NULL DEFAULT '[{"name": "Pagi", "time": "08:00", "count": 2, "enabled": true}, {"name": "Siang", "time": "13:00", "count": 2, "enabled": true}, {"name": "Malam", "time": "19:00", "count": 2, "enabled": true}]',
                    images_per_session INTEGER NOT NULL DEFAULT 2,
                    aspect_ratio TEXT NOT NULL DEFAULT '9:16',
                    template_preset TEXT NOT NULL DEFAULT 'auto',
                    font_family TEXT NOT NULL DEFAULT 'auto',
                    model_name TEXT NOT NULL DEFAULT 'auto',
                    background_source TEXT NOT NULL DEFAULT 'ai_gemini',
                    media_type TEXT NOT NULL DEFAULT 'image',
                    auto_post_enabled INTEGER NOT NULL DEFAULT 0,
                    target_account_ids TEXT NOT NULL DEFAULT '[]',
                    music_enabled INTEGER NOT NULL DEFAULT 0,
                    music_track TEXT NOT NULL DEFAULT 'auto',
                    footage_duration_sec INTEGER NOT NULL DEFAULT 8,
                    last_run_date TEXT DEFAULT NULL,
                    today_images_created INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_image_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    run_date TEXT NOT NULL,
                    session_name TEXT NOT NULL DEFAULT 'Manual Run',
                    topic TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    quote_hook TEXT NOT NULL DEFAULT '',
                    quote_headline TEXT NOT NULL DEFAULT '',
                    quote_body TEXT NOT NULL DEFAULT '',
                    quote_author TEXT NOT NULL DEFAULT '',
                    quote_handle TEXT NOT NULL DEFAULT '@cliperhub',
                    media_type TEXT NOT NULL DEFAULT 'image',
                    template_preset TEXT NOT NULL DEFAULT 'minimal_quote',
                    font_name TEXT NOT NULL DEFAULT 'Playfair Display',
                    model_name TEXT DEFAULT NULL,
                    aspect_ratio TEXT NOT NULL DEFAULT '9:16',
                    image_urls TEXT NOT NULL DEFAULT '[]',
                    video_url TEXT DEFAULT NULL,
                    local_paths TEXT NOT NULL DEFAULT '[]',
                    social_post_status TEXT NOT NULL DEFAULT 'idle',
                    social_details TEXT NOT NULL DEFAULT '{}',
                    trigger_source TEXT NOT NULL DEFAULT 'manual',
                    error_message TEXT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Schema migration: ensure model_name column exists
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(ai_image_settings)")
            cols_s = {row["name"] for row in cur.fetchall()}
            if "model_name" not in cols_s:
                conn.execute("ALTER TABLE ai_image_settings ADD COLUMN model_name TEXT NOT NULL DEFAULT 'auto'")

            cur.execute("PRAGMA table_info(ai_image_runs)")
            cols_r = {row["name"] for row in cur.fetchall()}
            if "model_name" not in cols_r:
                conn.execute("ALTER TABLE ai_image_runs ADD COLUMN model_name TEXT DEFAULT NULL")

            # Seed default record for user 1 if empty
            cur.execute("SELECT id FROM ai_image_settings WHERE user_id = 1")
            if not cur.fetchone():
                conn.execute("""
                    INSERT INTO ai_image_settings (user_id, enabled) VALUES (1, 0)
                """)
            conn.commit()
        except Exception as e:
            logger.error(f"[AIImageStudio] Table init failed: {e}")
        finally:
            conn.close()

    def get_settings(self, user_id: int = 1) -> dict[str, Any]:
        """Fetch current image studio settings for user."""
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_image_settings WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if not row:
                return self._default_settings(user_id)
            d = dict(row)
            d["enabled"] = bool(d.get("enabled", 0))
            d["auto_post_enabled"] = bool(d.get("auto_post_enabled", 0))
            d["music_enabled"] = bool(d.get("music_enabled", 0))
            try:
                d["topics"] = json.loads(d.get("topics") or "[]")
            except Exception:
                d["topics"] = []
            try:
                d["daily_slots"] = json.loads(d.get("daily_slots") or "[]")
            except Exception:
                d["daily_slots"] = []
            try:
                d["target_account_ids"] = json.loads(d.get("target_account_ids") or "[]")
            except Exception:
                d["target_account_ids"] = []

            # Include dynamic gateway info for UI visibility
            d["gateway_endpoint"] = self.get_image_api_endpoint()
            d["gateway_model"] = self.get_image_model(d.get("model_name"))
            d["gateway_has_key"] = bool(self.get_image_api_key())
            return d
        finally:
            conn.close()

    def update_settings(self, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Update image studio settings."""
        conn = get_dict_connection()
        try:
            fields = []
            values = []
            allowed_keys = [
                "enabled", "topics", "daily_slots", "images_per_session",
                "aspect_ratio", "template_preset", "font_family", "model_name",
                "background_source", "media_type", "auto_post_enabled",
                "target_account_ids", "music_enabled", "music_track",
                "footage_duration_sec",
            ]
            for k in allowed_keys:
                if k in data:
                    v = data[k]
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v)
                    elif isinstance(v, bool):
                        v = 1 if v else 0
                    fields.append(f"{k} = ?")
                    values.append(v)

            if fields:
                fields.append("updated_at = CURRENT_TIMESTAMP")
                values.append(user_id)
                query = f"UPDATE ai_image_settings SET {', '.join(fields)} WHERE user_id = ?"
                conn.execute(query, tuple(values))
                conn.commit()
            return self.get_settings(user_id)
        finally:
            conn.close()

    def _default_settings(self, user_id: int) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "enabled": False,
            "topics": [
                "Motivasi & Stoicism",
                "Mindset Sukses & Finansial",
                "Teknologi & Masa Depan AI",
                "Strategi Bisnis Modern",
            ],
            "daily_slots": [
                {"name": "Pagi", "time": "08:00", "count": 2, "enabled": True},
                {"name": "Siang", "time": "13:00", "count": 2, "enabled": True},
                {"name": "Malam", "time": "19:00", "count": 2, "enabled": True},
            ],
            "images_per_session": 2,
            "aspect_ratio": "9:16",
            "template_preset": "auto",
            "font_family": "auto",
            "model_name": "auto",
            "background_source": "ai_gemini",
            "media_type": "image",
            "auto_post_enabled": False,
            "target_account_ids": [],
            "music_enabled": False,
            "music_track": "auto",
            "footage_duration_sec": 8,
            "today_images_created": 0,
            "last_run_date": None,
            "gateway_endpoint": self.get_image_api_endpoint(),
            "gateway_model": self.get_image_model(),
            "gateway_has_key": bool(self.get_image_api_key()),
        }

    # ─── Media Generation Core (Dynamic Gateway) ──────────────────────────────

    async def generate_gemini_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        model_name: Optional[str] = None,
    ) -> Image.Image:
        """Call Image Generation API endpoint resolved dynamically from settings/system."""
        endpoint = self.get_image_api_endpoint()
        api_key = self.get_image_api_key()
        model = self.get_image_model(model_name)

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Enhance prompt for aesthetics and clean composition
        enhanced_prompt = (
            f"{prompt}, high quality photograph, aesthetic cinematic lighting, "
            f"minimalist atmospheric composition, sharp focus, 8k resolution, professional visual storytelling"
        )
        payload = {
            "model": model,
            "prompt": enhanced_prompt,
            "n": 1,
            "size": "auto",
            "quality": "auto",
            "background": "auto",
            "image_detail": "high",
            "output_format": "png",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Image generation API ({endpoint}) failed with HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            items = data.get("data", [])
            if not items or "b64_json" not in items[0]:
                raise RuntimeError("No image data returned from image generation API")

            b64_str = items[0]["b64_json"]
            raw_bytes = base64.b64decode(b64_str)
            return Image.open(io.BytesIO(raw_bytes))

    async def search_stock_photo(self, query: str, provider: str = "pexels") -> Optional[Image.Image]:
        """Fetch stock image from Pexels, Pixabay, or Giphy via dynamic settings keys."""
        if provider == "pexels":
            api_key = get_system_setting("PEXELS_API_KEY") or getattr(settings, "PEXELS_API_KEY", "")
            if api_key:
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        r = await client.get(
                            "https://api.pexels.com/v1/search",
                            headers={"Authorization": api_key},
                            params={"query": query, "per_page": 5, "orientation": "portrait"},
                        )
                        if r.status_code == 200:
                            photos = r.json().get("photos", [])
                            if photos:
                                img_url = photos[0]["src"].get("large2x") or photos[0]["src"].get("large")
                                img_resp = await client.get(img_url)
                                if img_resp.status_code == 200:
                                    return Image.open(io.BytesIO(img_resp.content))
                except Exception as e:
                    logger.warning(f"[AIImageStudio] Pexels search failed: {e}")

        elif provider == "pixabay":
            pixabay_key = get_system_setting("PIXABAY_API_KEY") or getattr(settings, "PIXABAY_API_KEY", "")
            if pixabay_key:
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        r = await client.get(
                            "https://pixabay.com/api/",
                            params={
                                "key": pixabay_key,
                                "q": query,
                                "image_type": "photo",
                                "orientation": "vertical",
                                "per_page": 5,
                            },
                        )
                        if r.status_code == 200:
                            hits = r.json().get("hits", [])
                            if hits:
                                img_url = hits[0].get("largeImageURL") or hits[0].get("webformatURL")
                                img_resp = await client.get(img_url)
                                if img_resp.status_code == 200:
                                    return Image.open(io.BytesIO(img_resp.content))
                except Exception as e:
                    logger.warning(f"[AIImageStudio] Pixabay search failed: {e}")

        elif provider == "giphy":
            giphy_key = get_system_setting("GIPHY_API_KEY") or getattr(settings, "GIPHY_API_KEY", "")
            if giphy_key:
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        r = await client.get(
                            "https://api.giphy.com/v1/gifs/search",
                            params={"api_key": giphy_key, "q": query, "limit": 5},
                        )
                        if r.status_code == 200:
                            gifs = r.json().get("data", [])
                            if gifs:
                                img_url = gifs[0].get("images", {}).get("original", {}).get("url")
                                if img_url:
                                    img_resp = await client.get(img_url)
                                    if img_resp.status_code == 200:
                                        return Image.open(io.BytesIO(img_resp.content))
                except Exception as e:
                    logger.warning(f"[AIImageStudio] Giphy search failed: {e}")

        return None

    async def search_stock_video_footage(self, query: str) -> Optional[str]:
        """Search and download portrait video footage from Pexels/Pixabay for motion text card."""
        api_key = get_system_setting("PEXELS_API_KEY") or getattr(settings, "PEXELS_API_KEY", "")
        if api_key:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.get(
                        "https://api.pexels.com/videos/search",
                        headers={"Authorization": api_key},
                        params={"query": query, "orientation": "portrait", "per_page": 5},
                    )
                    if r.status_code == 200:
                        videos = r.json().get("videos", [])
                        for vid in videos:
                            files = vid.get("video_files", [])
                            best_link = None
                            for f in files:
                                w, h = f.get("width", 0), f.get("height", 0)
                                if h >= 1280 and f.get("link"):
                                    best_link = f["link"]
                                    break
                            if not best_link and files:
                                best_link = files[0].get("link")

                            if best_link:
                                local_path = os.path.join(OUTPUT_DIR, f"footage_{uuid.uuid4().hex[:8]}.mp4")
                                async with client.stream("GET", best_link) as stream:
                                    with open(local_path, "wb") as f_out:
                                        async for chunk in stream.aiter_bytes():
                                            f_out.write(chunk)
                                return local_path
            except Exception as e:
                logger.warning(f"[AIImageStudio] Pexels video search failed: {e}")

        # Fallback to Pixabay Video
        pixabay_key = get_system_setting("PIXABAY_API_KEY") or getattr(settings, "PIXABAY_API_KEY", "")
        if pixabay_key:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.get(
                        "https://pixabay.com/api/videos/",
                        params={"key": pixabay_key, "q": query, "per_page": 5},
                    )
                    if r.status_code == 200:
                        hits = r.json().get("hits", [])
                        if hits:
                            videos_dict = hits[0].get("videos", {})
                            best_link = (
                                videos_dict.get("large", {}).get("url")
                                or videos_dict.get("medium", {}).get("url")
                                or videos_dict.get("small", {}).get("url")
                            )
                            if best_link:
                                local_path = os.path.join(OUTPUT_DIR, f"footage_{uuid.uuid4().hex[:8]}.mp4")
                                async with client.stream("GET", best_link) as stream:
                                    with open(local_path, "wb") as f_out:
                                        async for chunk in stream.aiter_bytes():
                                            f_out.write(chunk)
                                return local_path
            except Exception as e:
                logger.warning(f"[AIImageStudio] Pixabay video search failed: {e}")

        return None

    def suggest_quote_content(self, topic: str) -> dict[str, str]:
        """Use 9router AI to brainstorm and generate high-impact viral quote, hook, and prompt from any topic briefing."""
        safe_topic = (topic or "Inspirasi & Mindset").strip()
        fallback = {
            "hook": safe_topic.upper()[:24],
            "headline": f"Pelajaran paling esensial dari {safe_topic}.",
            "body": "Fokus pada prinsip dasar dan eksekusi konsisten untuk meraih lompatan eksponensial.",
            "author": "Hermes Director",
            "prompt": f"Minimalist cinematic photography capturing {safe_topic}, dramatic natural lighting, 8k resolution, editorial tone",
        }
        try:
            client = NineRouterClient(timeout=45)
            if not client.is_configured:
                return fallback

            sys_prompt = (
                "You are an elite creative director & viral copywriting psychologist. "
                "The user provides a topic, content briefing, or direction. "
                "You must autonomously explore, brainstorm, and create a fresh, deeply resonant viral angle specifically tailored to this briefing. "
                "Whatever topic is provided (whether philosophy, tech, business, culinary, fitness, relationships, comedy, or corporate), "
                "craft an impactful quote card content that hooks the audience instantly. "
                "Respond strictly with a single JSON object containing: "
                "\"hook\" (short category or punchy hook in uppercase, 2-3 words), "
                "\"headline\" (a punchy, memorable, deeply resonant statement/quote in Indonesian), "
                "\"body\" (1-2 sentences of practical wisdom, actionable perspective, or reflection), "
                "\"author\" (philosophical thinker, executive icon, or contextual persona matching the theme), "
                "\"prompt\" (highly detailed cinematic photography prompt for Gemini Image Generator). "
                "No markdown formatting, no emojis, pure JSON."
            )
            raw = client.chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"Briefing / Topic: {safe_topic}"},
                ],
                max_tokens=300,
            )
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("\n", 1)[0]
            parsed = json.loads(cleaned.strip())
            return {
                "hook": str(parsed.get("hook") or fallback["hook"]).upper(),
                "headline": str(parsed.get("headline") or fallback["headline"]),
                "body": str(parsed.get("body") or fallback["body"]),
                "author": str(parsed.get("author") or fallback["author"]),
                "prompt": str(parsed.get("prompt") or fallback["prompt"]),
            }
        except Exception as e:
            logger.debug(f"[AIImageStudio] AI quote generation fallback used: {e}")
            return fallback

    def _resolve_template_and_font(self, requested_template: str, requested_font: str, topic: str) -> tuple[str, str]:
        """Pick template and font dynamically from DB without hardcoded mood maps."""
        db_templates = get_all_typography_templates(include_inactive=False)
        template_ids = [t["id"] for t in db_templates] or ["minimal_quote"]

        if requested_template and requested_template != "auto" and requested_template in template_ids:
            template_id = requested_template
        else:
            # Dynamically select from active database templates
            template_id = random.choice(template_ids)

        if requested_font and requested_font != "auto" and requested_font in AVAILABLE_FONTS:
            font_name = requested_font
        else:
            tpl_meta = get_typography_template(template_id) or (db_templates[0] if db_templates else None)
            font_name = tpl_meta["primary_font"] if tpl_meta else "Playfair Display"

        return template_id, font_name

    async def render_image_item(
        self,
        topic: str,
        prompt: str,
        content: TypographyContent,
        background_source: str = "ai_gemini",
        custom_base_image: Optional[Image.Image] = None,
        model_name: Optional[str] = None,
    ) -> tuple[str, str]:
        """Generate, composite, save, and upload a single visual image item.

        Returns (local_file_path, public_url).
        """
        base_img: Optional[Image.Image] = None
        if custom_base_image:
            base_img = custom_base_image
        elif background_source == "ai_gemini":
            try:
                base_img = await self.generate_gemini_image(prompt, content.aspect_ratio, model_name=model_name)
            except Exception as e:
                logger.warning(f"[AIImageStudio] AI image failed, falling back to stock: {e}")
                base_img = await self.search_stock_photo(topic, provider="pexels")
        elif background_source in ("pexels", "pixabay", "giphy"):
            base_img = await self.search_stock_photo(topic or prompt, provider=background_source)
            if not base_img:
                base_img = await self.generate_gemini_image(prompt, content.aspect_ratio, model_name=model_name)

        final_img = typography_engine.render_overlay(base_img, content)

        filename = f"img_{uuid.uuid4().hex[:12]}.png"
        local_path = os.path.join(OUTPUT_DIR, filename)
        final_img.save(local_path, format="PNG", quality=95)

        public_url = f"/api/image-studio/media/{filename}"
        try:
            upload_res = self._minio.upload_clip(
                job_id="studio",
                clip_rank=1,
                file_path=local_path,
                content_type="image/png",
            )
            if upload_res and upload_res.get("presigned_url"):
                public_url = upload_res["presigned_url"]
            elif upload_res and upload_res.get("url"):
                public_url = upload_res["url"]
        except Exception as e:
            logger.debug(f"[AIImageStudio] MinIO upload skipped/offline: {e}")

        return local_path, public_url

    async def render_video_footage_item(
        self,
        topic: str,
        content: TypographyContent,
        footage_duration_sec: int = 8,
        music_track: str = "auto",
    ) -> tuple[str, str]:
        """Create video footage with overlay typography and optional audio bed."""
        footage_path = await self.search_stock_video_footage(topic)
        if not footage_path or not os.path.exists(footage_path):
            raise RuntimeError(f"No suitable video footage found for '{topic}'")

        transparent_overlay = typography_engine.render_overlay(None, content)
        overlay_png = os.path.join(OUTPUT_DIR, f"overlay_{uuid.uuid4().hex[:8]}.png")
        transparent_overlay.save(overlay_png, format="PNG")

        out_video_name = f"video_{uuid.uuid4().hex[:12]}.mp4"
        out_video_path = os.path.join(OUTPUT_DIR, out_video_name)

        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", footage_path,
            "-i", overlay_png,
            "-filter_complex",
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[v0];"
            f"[v0][1:v]overlay=0:0[vout]",
            "-map", "[vout]",
            "-t", str(footage_duration_sec),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            out_video_path,
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()

        try:
            os.remove(overlay_png)
            os.remove(footage_path)
        except Exception:
            pass

        if not os.path.exists(out_video_path):
            raise RuntimeError("FFmpeg video rendering failed")

        public_url = f"/api/image-studio/media/{out_video_name}"
        try:
            upload_res = self._minio.upload_clip(
                job_id="studio",
                clip_rank=1,
                file_path=out_video_path,
                content_type="video/mp4",
            )
            if upload_res and upload_res.get("presigned_url"):
                public_url = upload_res["presigned_url"]
            elif upload_res and upload_res.get("url"):
                public_url = upload_res["url"]
        except Exception as e:
            logger.debug(f"[AIImageStudio] MinIO video upload skipped/offline: {e}")

        return out_video_path, public_url

    # ─── High Level Execution Run ─────────────────────────────────────────────

    async def execute_generation_session(
        self,
        user_id: int = 1,
        topic: str = "",
        session_name: str = "Manual Run",
        image_count: int = 1,
        aspect_ratio: str = "9:16",
        template_preset: str = "auto",
        font_family: str = "auto",
        model_name: Optional[str] = None,
        background_source: str = "ai_gemini",
        media_type: str = "image",
        custom_prompt: str = "",
        quote_hook: str = "",
        quote_headline: str = "",
        quote_body: str = "",
        quote_author: str = "",
        quote_handle: str = "@cliperhub",
        accent_color: str = "#EAB308",
        auto_post: bool = False,
        target_account_ids: Optional[list[str]] = None,
        music_enabled: bool = False,
        music_id: Optional[str] = None,
        music_name: Optional[str] = None,
        music_artist: Optional[str] = None,
        music_thumbnail: Optional[str] = None,
        trigger_source: str = "manual",
    ) -> dict[str, Any]:
        """Execute a full generation batch, record run, and optionally auto-post."""
        async with self._run_lock:
            # 1. Fallback topic if empty
            if not topic:
                s = self.get_settings(user_id)
                topics = s.get("topics") or ["Inspirasi & Mindset"]
                topic = random.choice(topics)

            # 2. Resolve template, font, and model
            tpl_id, font_name = self._resolve_template_and_font(template_preset, font_family, topic)
            active_model = self.get_image_model(model_name)

            # 3. AI Copilot: if headline is not supplied, auto-suggest viral quote content
            if not quote_headline:
                suggested = self.suggest_quote_content(topic)
                hook = quote_hook or suggested["hook"]
                headline = suggested["headline"]
                body_text = quote_body or suggested["body"]
                author = quote_author or suggested["author"]
                prompt = custom_prompt or suggested["prompt"]
            else:
                hook = quote_hook or topic.upper()
                headline = quote_headline
                body_text = quote_body
                author = quote_author or "Hermes Perspective"
                prompt = custom_prompt or f"Aesthetic visual representation of {topic}, dramatic shadows, elegant modern editorial tone"

            local_paths: list[str] = []
            public_urls: list[str] = []
            video_url: Optional[str] = None

            today_str = dt.datetime.now(self.WIB).strftime("%Y-%m-%d")

            try:
                if media_type == "video_footage":
                    content = TypographyContent(
                        hook=hook,
                        headline=headline,
                        body=body_text,
                        author=author,
                        handle=quote_handle,
                        template=tpl_id,
                        font_family=font_name,
                        aspect_ratio=aspect_ratio,
                        accent_color=accent_color,
                    )
                    v_path, v_url = await self.render_video_footage_item(topic, content)
                    local_paths.append(v_path)
                    video_url = v_url
                    public_urls.append(v_url)
                else:
                    for i in range(max(1, image_count)):
                        slide_idx = f"0{i + 1} / 0{image_count}" if image_count > 1 else ""
                        item_headline = (
                            headline if i == 0
                            else f"Bagian {i + 1}: Kunci konsistensi tanpa membiarkan keraguan menghentikan langkahmu."
                        )
                        content = TypographyContent(
                            hook=hook,
                            headline=item_headline,
                            body=body_text if i == 0 else "Fokus pada apa yang bisa kamu kendalikan hari ini.",
                            author=author,
                            handle=quote_handle,
                            slide_index=slide_idx,
                            template=tpl_id,
                            font_family=font_name,
                            aspect_ratio=aspect_ratio,
                            accent_color=accent_color,
                        )
                        l_path, p_url = await self.render_image_item(
                            topic=topic,
                            prompt=f"{prompt}, variation {i + 1}",
                            content=content,
                            background_source=background_source,
                            model_name=active_model,
                        )
                        local_paths.append(l_path)
                        public_urls.append(p_url)

                # 4. Social Auto Post if requested (supports album bulking & background music)
                social_status = "idle"
                social_details: dict[str, Any] = {}
                if auto_post and target_account_ids:
                    social_status, social_details = await self._dispatch_social_post(
                        account_ids=target_account_ids,
                        media_urls=public_urls,
                        title=f"{topic} — {headline[:60]}",
                        caption=f"{headline}\n\n{body_text}\n\n— {author}\n\n#{topic.replace(' ', '')} #Inspirasi #Mindset #HermesAI",
                        media_type="video" if media_type == "video_footage" else "image",
                        music_enabled=music_enabled,
                        music_id=music_id,
                        music_name=music_name,
                        music_artist=music_artist,
                        music_thumbnail=music_thumbnail,
                    )

                # 5. Record run in SQLite
                conn = get_dict_connection()
                try:
                    cursor = conn.execute("""
                        INSERT INTO ai_image_runs (
                            user_id, run_date, session_name, topic, prompt,
                            quote_hook, quote_headline, quote_body, quote_author, quote_handle,
                            media_type, template_preset, font_name, model_name, aspect_ratio,
                            image_urls, video_url, local_paths,
                            social_post_status, social_details, trigger_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id, today_str, session_name, topic, prompt,
                        hook, headline, body_text, author, quote_handle,
                        media_type, tpl_id, font_name, active_model, aspect_ratio,
                        json.dumps(public_urls), video_url, json.dumps(local_paths),
                        social_status, json.dumps(social_details), trigger_source,
                    ))
                    run_id = cursor.lastrowid

                    conn.execute("""
                        UPDATE ai_image_settings
                        SET today_images_created = today_images_created + ?,
                            last_run_date = ?
                        WHERE user_id = ?
                    """, (len(public_urls), today_str, user_id))
                    conn.commit()
                finally:
                    conn.close()

                return {
                    "success": True,
                    "id": run_id,
                    "session_name": session_name,
                    "topic": topic,
                    "quote_headline": headline,
                    "quote_body": body_text,
                    "quote_hook": hook,
                    "template": tpl_id,
                    "font": font_name,
                    "model": active_model,
                    "aspect_ratio": aspect_ratio,
                    "media_type": media_type,
                    "image_urls": public_urls,
                    "video_url": video_url,
                    "count": len(public_urls),
                    "social_post_status": social_status,
                    "social_details": social_details,
                }

            except Exception as e:
                logger.error(f"[AIImageStudio] Session failed: {e}", exc_info=True)
                conn = get_dict_connection()
                try:
                    conn.execute("""
                        INSERT INTO ai_image_runs (
                            user_id, run_date, session_name, topic, prompt,
                            quote_hook, quote_headline, media_type, template_preset, font_name,
                            model_name, social_post_status, error_message, trigger_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'failed', ?, ?)
                    """, (
                        user_id, today_str, session_name, topic, prompt,
                        hook, headline, media_type, tpl_id, font_name,
                        active_model, str(e), trigger_source,
                    ))
                    conn.commit()
                finally:
                    conn.close()
                raise

    async def _dispatch_social_post(
        self,
        account_ids: list[str],
        media_urls: list[str],
        title: str,
        caption: str,
        media_type: str = "image",
        music_enabled: bool = False,
        music_id: Optional[str] = None,
        music_name: Optional[str] = None,
        music_artist: Optional[str] = None,
        music_thumbnail: Optional[str] = None,
    ) -> tuple[str, dict[str, Any]]:
        """Dispatch schedule request to Repliz API for target accounts with album/multi-image bulking & music support."""
        from src.presentation.routes.social.helpers import repliz_post

        is_video = (media_type in ("video", "video_footage"))

        # Determine Repliz post type strictly adhering to Repliz Swagger enum:
        # ["text", "image", "video", "reel", "album", "link", "story"]
        if is_video:
            post_type = "video"
        elif len(media_urls) > 1:
            post_type = "album"  # Repliz carousel of 2-5+ images
        else:
            post_type = "image"  # Single image

        # Construct medias list adhering to Repliz ScheduleMedia schema
        medias = []
        for idx, u in enumerate(media_urls):
            medias.append({
                "type": "video" if is_video else "image",
                "url": u,
                "alt": f"{title} - Bagian {idx + 1}" if len(media_urls) > 1 else title[:100],
                "thumbnail": u if not is_video else "",
                "customThumbnail": False,
            })

        schedule_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Additional info including music and AI labels
        additional_info: dict[str, Any] = {
            "isAiGenerated": False,
            "isDraft": False,
            "isShareToFeed": True,
            "collaborators": [],
        }

        # Music configuration for platforms that support music (TikTok image/album, Instagram, Facebook)
        if music_enabled or music_id:
            if music_id:
                additional_info["music"] = {
                    "id": str(music_id),
                    "artist": music_artist or "",
                    "name": music_name or "",
                    "thumbnail": music_thumbnail or "",
                    "volume": {
                        "video": 50,
                        "music": 100,
                    },
                }
                additional_info["isAutoAddMusic"] = False
            else:
                # Let TikTok/platforms auto-add recommended trending music to the photo post / album
                additional_info["isAutoAddMusic"] = True

        successes = []
        failures = []

        # TikTok titles are cut to 90 chars, Pinterest to 100 chars
        safe_title = title[:90]

        for acc_id in account_ids:
            payload = {
                "title": safe_title,
                "description": caption,
                "type": post_type,
                "medias": medias,
                "accountId": acc_id,
                "scheduleAt": schedule_at,
                "additionalInfo": additional_info,
            }
            try:
                res = await repliz_post("/public/schedule", json_body=payload)
                successes.append({"accountId": acc_id, "result": res})
            except Exception as ex:
                logger.error(f"[AIImageStudio] Repliz post failed for account {acc_id}: {ex}")
                failures.append({"accountId": acc_id, "error": str(ex)})

        status = "scheduled" if successes else ("failed" if failures else "idle")
        details = {
            "post_type": post_type,
            "media_count": len(medias),
            "music_enabled": music_enabled or bool(music_id),
            "successes": successes,
            "failures": failures,
        }
        return status, details

    # ─── Hermes Background Autonomous Scheduler ──────────────────────────────

    async def start_scheduler_loop(self) -> None:
        """Background loop: checks daily scheduled slots (pagi, siang, malam) and auto-triggers Hermes image posts."""
        logger.info("[AIImageStudio] Daemon started — monitoring daily visual generation slots")
        while True:
            try:
                await self._check_and_trigger_scheduled_slots()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AIImageStudio] Scheduler loop error: {e}")
            await asyncio.sleep(30)

    async def _check_and_trigger_scheduled_slots(self) -> None:
        """Evaluate whether any configured slot is due right now."""
        settings_data = self.get_settings(user_id=1)
        if not settings_data.get("enabled"):
            return

        now_wib = dt.datetime.now(self.WIB)
        current_time_str = now_wib.strftime("%H:%M")
        today_date_str = now_wib.strftime("%Y-%m-%d")

        daily_slots = settings_data.get("daily_slots") or []
        for slot in daily_slots:
            if not slot.get("enabled", True):
                continue

            slot_time = slot.get("time", "")
            slot_name = slot.get("name", "Slot")
            slot_count = int(slot.get("count", settings_data.get("images_per_session", 2)))

            if current_time_str == slot_time:
                run_key = (1, today_date_str, slot_name)
                if run_key in self._last_scheduled_runs:
                    continue

                logger.info(f"[AIImageStudio] Triggering Hermes slot: {slot_name} at {slot_time} WIB ({slot_count} items)")
                self._last_scheduled_runs[run_key] = True

                topics = settings_data.get("topics") or ["Inspirasi & Mindset"]
                topic = random.choice(topics)

                asyncio.create_task(
                    self.execute_generation_session(
                        user_id=1,
                        topic=topic,
                        session_name=f"Hermes Auto ({slot_name})",
                        image_count=slot_count,
                        aspect_ratio=settings_data.get("aspect_ratio", "9:16"),
                        template_preset=settings_data.get("template_preset", "auto"),
                        font_family=settings_data.get("font_family", "auto"),
                        model_name=settings_data.get("model_name", "auto"),
                        background_source=settings_data.get("background_source", "ai_gemini"),
                        media_type=settings_data.get("media_type", "image"),
                        auto_post=settings_data.get("auto_post_enabled", False),
                        target_account_ids=settings_data.get("target_account_ids", []),
                        music_enabled=settings_data.get("music_enabled", False),
                        music_id=str(settings_data.get("music_track")) if (settings_data.get("music_track") and str(settings_data.get("music_track")).isdigit()) else None,
                        trigger_source="hermes_scheduler",
                    )
                )

    def get_history(self, user_id: int = 1, limit: int = 40) -> list[dict[str, Any]]:
        """Fetch past generation runs."""
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM ai_image_runs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            rows = cur.fetchall()
            out = []
            for r in rows:
                item = dict(r)
                try:
                    item["image_urls"] = json.loads(item.get("image_urls") or "[]")
                except Exception:
                    item["image_urls"] = []
                try:
                    item["social_details"] = json.loads(item.get("social_details") or "{}")
                except Exception:
                    item["social_details"] = {}
                out.append(item)
            return out
        finally:
            conn.close()

    def delete_history_item(self, run_id: int, user_id: int = 1) -> bool:
        """Delete a past generation run and local files."""
        conn = get_dict_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT local_paths FROM ai_image_runs WHERE id = ? AND user_id = ?", (run_id, user_id))
            row = cur.fetchone()
            if row and row.get("local_paths"):
                try:
                    paths = json.loads(row["local_paths"])
                    for p in paths:
                        if os.path.exists(p):
                            os.remove(p)
                except Exception:
                    pass
            cur.execute("DELETE FROM ai_image_runs WHERE id = ? AND user_id = ?", (run_id, user_id))
            conn.commit()
            return True
        finally:
            conn.close()


ai_image_studio_service = AIImageStudioService()
