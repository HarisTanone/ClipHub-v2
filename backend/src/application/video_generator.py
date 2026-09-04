"""Video Generator — Orchestrator pipeline: Topic → Final Video.

Pipeline steps:
1. AI Story Agent → structured scenes JSON
2. YouTube Search → footage candidates per scene
3. yt-dlp → download best footage
4. Deepgram TTS → narration audio per scene
5. Timeline assembly → match footage to TTS duration
6. FFmpeg → render final 9:16 video (footage + voice + subtitle + BGM)

Superuser only. Runs as async background job.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from src.application.video_gen_captions import (
    ffmpeg_subtitle_filter,
    normalize_subtitle_style,
    write_ass_subtitles,
)
from src.config import settings

logger = logging.getLogger(__name__)


class VideoGenStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    GENERATING_STORY = "generating_story"
    SEARCHING_FOOTAGE = "searching_footage"
    AWAITING_SELECTION = "awaiting_selection"
    DOWNLOADING = "downloading"
    GENERATING_TTS = "generating_tts"
    ASSEMBLING = "assembling"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class VideoGenJob:
    """State object for a video generation job."""
    job_id: str
    topic: str
    status: VideoGenStatus = VideoGenStatus.QUEUED
    progress: int = 0  # 0-100
    target_duration: int = 65
    tts_provider: str = "gemini"
    tts_model: str = "gemini-3.1-flash-tts-preview"
    voice: str = "Kore"
    speed: float = 1.0
    instructions: str = ""
    num_scenes: int = 0
    subtitles_enabled: bool = True
    subtitle_style: dict[str, Any] = field(default_factory=dict)
    hook_enabled: bool = True
    custom_hook: Optional[str] = None
    hook_style: dict[str, Any] = field(default_factory=dict)
    include_bgm: bool = True
    bgm_volume: float = field(default_factory=lambda: settings.VIDEO_GEN_BGM_VOLUME)
    title: Optional[str] = None
    source_video_url: Optional[str] = None
    agentic_understanding: bool = True
    language: Optional[str] = "id"
    video_processing_mode: Optional[str] = "agentic"
    media_resolution: Optional[str] = "low"
    fps: Optional[float] = None
    start_offset: Optional[float] = None
    end_offset: Optional[float] = None
    watermark_config: Optional[dict] = None
    transition: Optional[str] = "dissolve"
    cta_config: Optional[dict] = None
    ai_text_config: Optional[dict] = None
    thumbnail_url: Optional[str] = None
    aspect_ratio: str = "9:16"
    # Results

    story: Optional[dict] = None
    scenes_with_footage: Optional[list] = None
    timeline: Optional[list] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    # Timing
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    # User
    user_id: Optional[int] = None


class VideoGenerator:
    """Orchestrator: Topic → Final 9:16 Video.

    Coordinates all sub-systems:
    - StoryAgent (LLM)
    - YouTubeSearch (API)
    - FootageDownloader (yt-dlp)
    - DeepgramTTS (narration)
    - FFmpeg (final render)
    - SkiaHookRenderer (opening hook title overlay)
    """

    def __init__(self, output_dir: Optional[str] = None):
        self._jobs: dict[str, VideoGenJob] = {}
        self._output_dir = output_dir or settings.VIDEO_GEN_OUTPUT_DIR
        os.makedirs(self._output_dir, exist_ok=True)
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create video_generator_jobs table if needed and migrate missing columns."""
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS video_generator_jobs (
                    job_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER DEFAULT 0,
                    target_duration INTEGER DEFAULT 65,
                    voice TEXT DEFAULT '',
                    speed REAL DEFAULT 1.0,
                    instructions TEXT DEFAULT '',
                    num_scenes INTEGER DEFAULT 0,
                    subtitles_enabled INTEGER DEFAULT 1,
                    subtitle_style_json TEXT,
                    hook_enabled INTEGER DEFAULT 1,
                    custom_hook TEXT,
                    hook_style_json TEXT,
                    include_bgm INTEGER DEFAULT 1,
                    bgm_volume REAL DEFAULT 0.15,
                    title TEXT,
                    story_json TEXT,
                    scenes_json TEXT,
                    timeline_json TEXT,
                    output_path TEXT,
                    error TEXT,
                    created_at REAL,
                    completed_at REAL
                )
            """)
            cur.execute("PRAGMA table_info(video_generator_jobs)")
            cols = {row["name"] for row in cur.fetchall()}
            if "hook_enabled" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN hook_enabled INTEGER DEFAULT 1")
            if "custom_hook" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN custom_hook TEXT")
            if "hook_style_json" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN hook_style_json TEXT")
            if "tts_provider" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN tts_provider TEXT DEFAULT 'elevenlabs'")
            if "tts_model" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN tts_model TEXT DEFAULT 'eleven_multilingual_v2'")
            if "source_video_url" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN source_video_url TEXT")
            if "agentic_understanding" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN agentic_understanding INTEGER DEFAULT 1")
            if "language" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN language TEXT DEFAULT 'id'")
            if "video_processing_mode" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN video_processing_mode TEXT DEFAULT 'agentic'")
            if "media_resolution" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN media_resolution TEXT DEFAULT 'low'")
            if "fps" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN fps REAL")
            if "start_offset" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN start_offset REAL")
            if "end_offset" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN end_offset REAL")
            if "watermark_config" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN watermark_config TEXT")
            if "transition" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN transition TEXT DEFAULT 'dissolve'")
            if "cta_config" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN cta_config TEXT")
            if "ai_text_config" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN ai_text_config TEXT")
            if "thumbnail_url" not in cols:
                cur.execute("ALTER TABLE video_generator_jobs ADD COLUMN thumbnail_url TEXT")
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning(f"video_gen: failed to ensure video_generator_jobs table: {exc}")

    def _persist_job(self, job: VideoGenJob) -> None:
        """Persist job state to SQLite database."""
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            status_val = job.status.value if hasattr(job.status, "value") else str(job.status)
            title = job.title or (job.story.get("title") if job.story else None)
            story_json = json.dumps(job.story) if job.story else None
            scenes_json = json.dumps(job.scenes_with_footage) if job.scenes_with_footage else None
            timeline_json = json.dumps(job.timeline) if job.timeline else None
            subtitle_style_json = json.dumps(job.subtitle_style) if job.subtitle_style else None
            hook_style_json = json.dumps(job.hook_style) if job.hook_style else None
            watermark_config_json = json.dumps(job.watermark_config) if job.watermark_config else None
            cta_config_json = json.dumps(job.cta_config) if job.cta_config else None
            ai_text_config_json = json.dumps(job.ai_text_config) if job.ai_text_config else None

            cur.execute("""
                INSERT INTO video_generator_jobs (
                    job_id, user_id, topic, status, progress, target_duration,
                    voice, speed, instructions, num_scenes, subtitles_enabled,
                    subtitle_style_json, hook_enabled, custom_hook, hook_style_json,
                    include_bgm, bgm_volume, title, story_json, scenes_json,
                    timeline_json, output_path, error, created_at, completed_at,
                    tts_provider, tts_model, source_video_url, agentic_understanding, language,
                    video_processing_mode, media_resolution, fps, start_offset, end_offset,
                    watermark_config, transition, cta_config, ai_text_config, thumbnail_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    topic=excluded.topic,
                    status=excluded.status,
                    progress=excluded.progress,
                    target_duration=excluded.target_duration,
                    voice=excluded.voice,
                    speed=excluded.speed,
                    instructions=excluded.instructions,
                    num_scenes=excluded.num_scenes,
                    subtitles_enabled=excluded.subtitles_enabled,
                    subtitle_style_json=excluded.subtitle_style_json,
                    hook_enabled=excluded.hook_enabled,
                    custom_hook=excluded.custom_hook,
                    hook_style_json=excluded.hook_style_json,
                    include_bgm=excluded.include_bgm,
                    bgm_volume=excluded.bgm_volume,
                    title=excluded.title,
                    story_json=excluded.story_json,
                    scenes_json=excluded.scenes_json,
                    timeline_json=excluded.timeline_json,
                    output_path=excluded.output_path,
                    error=excluded.error,
                    completed_at=excluded.completed_at,
                    tts_provider=excluded.tts_provider,
                    tts_model=excluded.tts_model,
                    source_video_url=excluded.source_video_url,
                    agentic_understanding=excluded.agentic_understanding,
                    language=excluded.language,
                    video_processing_mode=excluded.video_processing_mode,
                    media_resolution=excluded.media_resolution,
                    fps=excluded.fps,
                    start_offset=excluded.start_offset,
                    end_offset=excluded.end_offset,
                    watermark_config=excluded.watermark_config,
                    transition=excluded.transition,
                    cta_config=excluded.cta_config,
                    ai_text_config=excluded.ai_text_config,
                    thumbnail_url=excluded.thumbnail_url
            """, (
                job.job_id,
                job.user_id,
                job.topic,
                status_val,
                job.progress,
                job.target_duration,
                job.voice,
                job.speed,
                job.instructions,
                job.num_scenes,
                1 if job.subtitles_enabled else 0,
                subtitle_style_json,
                1 if job.hook_enabled else 0,
                job.custom_hook,
                hook_style_json,
                1 if job.include_bgm else 0,
                job.bgm_volume,
                title,
                story_json,
                scenes_json,
                timeline_json,
                job.output_path,
                job.error,
                job.created_at,
                job.completed_at,
                job.tts_provider,
                job.tts_model,
                job.source_video_url,
                1 if job.agentic_understanding else 0,
                job.language or "id",
                job.video_processing_mode or "agentic",
                job.media_resolution or "low",
                job.fps,
                job.start_offset,
                job.end_offset,
                watermark_config_json,
                job.transition or "dissolve",
                cta_config_json,
                ai_text_config_json,
                job.thumbnail_url or "",
            ))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning(f"video_gen: failed to persist job {job.job_id} to DB: {exc}")

    def _row_to_job(self, row) -> VideoGenJob:
        """Convert a DB row into a VideoGenJob dataclass."""
        try:
            status_val = VideoGenStatus(row["status"])
        except Exception:
            status_val = VideoGenStatus.FAILED if row["status"] == "failed" else VideoGenStatus.QUEUED

        story = json.loads(row["story_json"]) if row["story_json"] else None
        scenes = json.loads(row["scenes_json"]) if ("scenes_json" in row.keys() and row["scenes_json"]) else None
        timeline = json.loads(row["timeline_json"]) if row["timeline_json"] else None
        subtitle_style = (
            json.loads(row["subtitle_style_json"])
            if ("subtitle_style_json" in row.keys() and row["subtitle_style_json"])
            else {}
        )
        hook_style = (
            json.loads(row["hook_style_json"])
            if ("hook_style_json" in row.keys() and row["hook_style_json"])
            else {}
        )
        tts_provider = row["tts_provider"] if ("tts_provider" in row.keys() and row["tts_provider"]) else "gemini"
        tts_model = row["tts_model"] if ("tts_model" in row.keys() and row["tts_model"]) else "gemini-3.1-flash-tts-preview"
        source_video_url = row["source_video_url"] if ("source_video_url" in row.keys()) else None
        agentic_understanding = bool(row["agentic_understanding"]) if ("agentic_understanding" in row.keys() and row["agentic_understanding"] is not None) else True
        language = row["language"] if ("language" in row.keys() and row["language"]) else "id"
        video_processing_mode = row["video_processing_mode"] if ("video_processing_mode" in row.keys() and row["video_processing_mode"]) else "agentic"
        media_resolution = row["media_resolution"] if ("media_resolution" in row.keys() and row["media_resolution"]) else "low"
        fps = float(row["fps"]) if ("fps" in row.keys() and row["fps"] is not None) else None
        start_offset = float(row["start_offset"]) if ("start_offset" in row.keys() and row["start_offset"] is not None) else None
        end_offset = float(row["end_offset"]) if ("end_offset" in row.keys() and row["end_offset"] is not None) else None
        watermark_config = json.loads(row["watermark_config"]) if ("watermark_config" in row.keys() and row["watermark_config"]) else None
        transition = row["transition"] if ("transition" in row.keys() and row["transition"]) else "dissolve"
        cta_config = json.loads(row["cta_config"]) if ("cta_config" in row.keys() and row["cta_config"]) else None
        ai_text_config = json.loads(row["ai_text_config"]) if ("ai_text_config" in row.keys() and row["ai_text_config"]) else None
        thumbnail_url = row["thumbnail_url"] if ("thumbnail_url" in row.keys()) else None

        return VideoGenJob(
            job_id=row["job_id"],
            topic=row["topic"],
            status=status_val,
            progress=int(row["progress"] or 0),
            target_duration=int(row["target_duration"] or 65),
            tts_provider=tts_provider,
            tts_model=tts_model,
            voice=row["voice"] or "Kore",
            speed=float(row["speed"] or 1.0),
            instructions=row["instructions"] or "",
            num_scenes=int(row["num_scenes"]) if "num_scenes" in row.keys() and row["num_scenes"] is not None else 0,
            subtitles_enabled=bool(row["subtitles_enabled"]) if "subtitles_enabled" in row.keys() and row["subtitles_enabled"] is not None else True,
            subtitle_style=subtitle_style,
            hook_enabled=bool(row["hook_enabled"]) if "hook_enabled" in row.keys() and row["hook_enabled"] is not None else True,
            custom_hook=row["custom_hook"] if "custom_hook" in row.keys() else None,
            hook_style=hook_style,
            include_bgm=bool(row["include_bgm"]) if "include_bgm" in row.keys() and row["include_bgm"] is not None else True,
            bgm_volume=float(row["bgm_volume"]) if "bgm_volume" in row.keys() and row["bgm_volume"] is not None else settings.VIDEO_GEN_BGM_VOLUME,
            title=row["title"],
            source_video_url=source_video_url,
            agentic_understanding=agentic_understanding,
            language=language,
            video_processing_mode=video_processing_mode,
            media_resolution=media_resolution,
            fps=fps,
            start_offset=start_offset,
            end_offset=end_offset,
            watermark_config=watermark_config,
            transition=transition,
            cta_config=cta_config,
            ai_text_config=ai_text_config,
            thumbnail_url=thumbnail_url,
            story=story,
            scenes_with_footage=scenes,
            timeline=timeline,
            output_path=row["output_path"],
            error=row["error"],
            created_at=float(row["created_at"] or 0.0),
            completed_at=float(row["completed_at"]) if row["completed_at"] is not None else None,
            user_id=row["user_id"],
        )

    def create_job(
        self,
        topic: str,
        target_duration: int = 0,
        tts_provider: Optional[str] = None,
        tts_model: Optional[str] = None,
        voice: str = "",
        speed: float = 1.0,
        instructions: str = "",
        num_scenes: int = 0,
        subtitles_enabled: bool = True,
        subtitle_style: Optional[dict[str, Any]] = None,
        hook_enabled: bool = True,
        custom_hook: Optional[str] = None,
        hook_style: Optional[dict[str, Any]] = None,
        include_bgm: bool = True,
        bgm_volume: Optional[float] = None,
        source_video_url: Optional[str] = None,
        agentic_understanding: bool = True,
        language: Optional[str] = None,
        video_processing_mode: Optional[str] = "agentic",
        media_resolution: Optional[str] = "low",
        fps: Optional[float] = None,
        start_offset: Optional[float] = None,
        end_offset: Optional[float] = None,
        watermark_config: Optional[dict[str, Any]] = None,
        transition: Optional[str] = "dissolve",
        cta_config: Optional[dict[str, Any]] = None,
        ai_text_config: Optional[dict[str, Any]] = None,
        aspect_ratio: str = "9:16",
        user_id: Optional[int] = None,
    ) -> VideoGenJob:

        """Create a new video generation job."""
        job_id = uuid4().hex[:12]

        # Automatic language detection
        from src.infrastructure.language_detector import detect_language
        if not language or language.strip().lower() in ("auto", "default"):
            resolved_language = detect_language(topic, instructions)
        elif language.strip().lower() in ("indonesian", "id", "indonesia"):
            resolved_language = "id"
        elif language.strip().lower() == "english":
            resolved_language = "en"
        else:
            resolved_language = language.strip().lower()

        resolved_provider = (tts_provider or getattr(settings, "VIDEO_GEN_TTS_PROVIDER", "gemini") or "gemini").lower()
        if "deepgram" in resolved_provider:
            resolved_provider = "deepgram"
            default_voice = settings.DEEPGRAM_TTS_VOICE
            default_model = "aura-2-thalia-en"
        else:
            resolved_provider = "gemini"
            default_voice = getattr(settings, "GEMINI_TTS_VOICE", "Kore")
            default_model = getattr(settings, "GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")

        resolved_model = tts_model or default_model

        job = VideoGenJob(
            job_id=job_id,
            topic=topic,
            target_duration=target_duration or settings.VIDEO_GEN_TARGET_DURATION,
            tts_provider=resolved_provider,
            tts_model=resolved_model,
            voice=voice or default_voice,
            speed=speed or 1.0,
            instructions=instructions,
            num_scenes=num_scenes,
            subtitles_enabled=subtitles_enabled,
            subtitle_style=normalize_subtitle_style(subtitle_style),
            hook_enabled=hook_enabled,
            custom_hook=custom_hook.strip() if custom_hook and custom_hook.strip() else None,
            hook_style=hook_style or {},
            include_bgm=include_bgm,
            bgm_volume=(
                settings.VIDEO_GEN_BGM_VOLUME
                if bgm_volume is None
                else max(0.0, min(0.5, bgm_volume))
            ),
            source_video_url=source_video_url.strip() if source_video_url and source_video_url.strip() else None,
            agentic_understanding=agentic_understanding,
            language=resolved_language,
            video_processing_mode=video_processing_mode or "agentic",
            media_resolution=media_resolution or "low",
            fps=fps,
            start_offset=start_offset,
            end_offset=end_offset,
            watermark_config=watermark_config,
            transition=transition or "dissolve",
            cta_config=cta_config,
            ai_text_config=ai_text_config,
            user_id=user_id,
        )
        self._jobs[job_id] = job
        self._persist_job(job)
        return job

    def get_job(self, job_id: str) -> Optional[VideoGenJob]:
        # Always check database first to maintain consistency across multi-worker processes
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM video_generator_jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            conn.close()
            if row:
                job = self._row_to_job(row)
                self._jobs[job_id] = job
                return job
        except Exception as exc:
            logger.warning(f"video_gen: failed to read job {job_id} from DB: {exc}")

        return self._jobs.get(job_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete a video generation job and clean up its temporary and output files."""
        job = self.get_job(job_id)
        # Pop from in-memory cache
        self._jobs.pop(job_id, None)

        # Delete from DB
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM video_generator_jobs WHERE job_id = ?", (job_id,))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning(f"video_gen: failed to delete job {job_id} from DB: {exc}")

        # Delete local files/work dir
        work_dir = os.path.join(self._output_dir, job_id)
        if os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception as exc:
                logger.warning(f"video_gen: failed to delete work_dir for job {job_id}: {exc}")

        if job and job.output_path and os.path.exists(job.output_path):
            try:
                os.remove(job.output_path)
            except Exception:
                pass

        return True

    def retry_job(self, job_id: str) -> VideoGenJob:
        """Reset and restart a failed job in place."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = VideoGenStatus.QUEUED
        job.progress = 0
        job.error = None
        job.completed_at = None
        self._jobs[job_id] = job
        self._persist_job(job)
        return job

    def list_jobs(
        self,
        user_id: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[VideoGenJob]:
        db_jobs: list[VideoGenJob] = []
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            query = "SELECT * FROM video_generator_jobs"
            params: list[Any] = []
            if user_id is not None:
                query += " WHERE user_id = ?"
                params.append(user_id)
            query += " ORDER BY created_at DESC"
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            conn.close()
            for r in rows:
                j = self._row_to_job(r)
                self._jobs[j.job_id] = j
                db_jobs.append(j)
            return db_jobs
        except Exception as exc:
            logger.warning(f"video_gen: failed to list jobs from DB, falling back to memory: {exc}")
            jobs = list(self._jobs.values())
            if user_id is not None:
                jobs = [j for j in jobs if j.user_id == user_id]
            sorted_jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)
            if limit is not None:
                return sorted_jobs[offset : offset + limit]
            return sorted_jobs

    def count_jobs(self, user_id: Optional[int] = None) -> int:
        try:
            from src.infrastructure.db_connection import get_dict_connection
            conn = get_dict_connection()
            cur = conn.cursor()
            query = "SELECT COUNT(*) as count FROM video_generator_jobs"
            params: list[Any] = []
            if user_id is not None:
                query += " WHERE user_id = ?"
                params.append(user_id)
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            conn.close()
            if row:
                return int(row["count"])
        except Exception as exc:
            logger.warning(f"video_gen: failed to count jobs from DB: {exc}")
        if user_id is not None:
            return len([j for j in self._jobs.values() if j.user_id == user_id])
        return len(self._jobs)

    async def run_pipeline(self, job_id: str) -> VideoGenJob:
        """Execute the full video generation pipeline (one-click auto mode)."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        work_dir = os.path.join(self._output_dir, job_id)
        os.makedirs(work_dir, exist_ok=True)

        try:
            # Step 1: Generate story
            job.status = VideoGenStatus.GENERATING_STORY
            job.progress = 5
            self._persist_job(job)
            story = await self._step_generate_story(job)
            job.story = story
            job.title = story.get("title")
            job.progress = 15
            self._persist_job(job)

            # Step 2: Search footage
            job.status = VideoGenStatus.SEARCHING_FOOTAGE
            job.progress = 20
            self._persist_job(job)
            scenes = await self._step_search_footage(story, work_dir, job=job)

            # Step 2b: AI Video Director Curation Pass (LLM evaluates real candidates)
            from src.infrastructure.story_agent import StoryAgent
            story_agent = StoryAgent()
            scenes = await story_agent.curate_scene_footages(scenes)
            job.scenes_with_footage = scenes
            job.progress = 35
            self._persist_job(job)

            # Step 3 & 4: Parallel Execution of TTS Generation and Footage Download
            job.status = VideoGenStatus.DOWNLOADING
            job.progress = 40
            self._persist_job(job)

            tts_task = self._step_generate_tts(scenes, job, work_dir)
            dl_task = self._step_download_footage(scenes, work_dir)
            scenes_tts, scenes_dl = await asyncio.gather(tts_task, dl_task)

            # Merge TTS audio metadata and downloaded footage paths into unified scenes
            for i, scene in enumerate(scenes):
                if i < len(scenes_tts):
                    scene["tts_path"] = scenes_tts[i].get("tts_path")
                    scene["tts_duration"] = scenes_tts[i].get("tts_duration")
                    scene["audio_path"] = scenes_tts[i].get("audio_path")
                    scene["audio_duration"] = scenes_tts[i].get("audio_duration")
                if i < len(scenes_dl):
                    scene["footage_path"] = scenes_dl[i].get("footage_path")
                    scene["selected_footage"] = scenes_dl[i].get("selected_footage")
                    scene["footage_source"] = scenes_dl[i].get("footage_source")

            job.scenes_with_footage = scenes
            job.progress = 60
            self._persist_job(job)

            # Step 4b: Gemini Agentic Video Understanding Alignment Pass
            if getattr(job, "agentic_understanding", True):
                logger.info(f"video_gen [{job.job_id}]: running Gemini Agentic Video Understanding alignment pass...")
                try:
                    from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
                    agentic_svc = GeminiAgenticVideoService()
                    for scene in scenes:
                        f_path = scene.get("footage_path")
                        if f_path and os.path.exists(f_path):
                            await agentic_svc.align_scene_footage(
                                scene=scene,
                                local_footage_path=f_path,
                                topic=job.topic,
                                processing_mode=getattr(job, "video_processing_mode", "agentic") or "agentic",
                                media_resolution=getattr(job, "media_resolution", "low") or "low",
                                fps=getattr(job, "fps", None),
                                start_offset=getattr(job, "start_offset", None),
                                end_offset=getattr(job, "end_offset", None),
                            )
                except Exception as ag_err:
                    logger.warning(f"video_gen [{job.job_id}]: agentic alignment pass fallback ({ag_err})")

            job.scenes_with_footage = scenes
            job.progress = 70
            self._persist_job(job)

            # Step 5: Assemble timeline
            job.status = VideoGenStatus.ASSEMBLING
            job.progress = 75
            self._persist_job(job)
            timeline = self._step_assemble_timeline(scenes)
            job.timeline = timeline
            job.progress = 80
            self._persist_job(job)

            # Step 6: Render final video
            job.status = VideoGenStatus.RENDERING
            job.progress = 85
            self._persist_job(job)
            output_path = await self._step_render_video(timeline, job, work_dir)
            job.output_path = output_path
            job.progress = 100

            # Done
            job.status = VideoGenStatus.COMPLETED
            job.completed_at = time.time()
            self._persist_job(job)

            total_time = job.completed_at - job.created_at
            logger.info(
                f"video_gen: job {job_id} completed in {total_time:.1f}s → {output_path}"
            )

        except Exception as exc:
            job.status = VideoGenStatus.FAILED
            job.error = str(exc)
            job.completed_at = time.time()
            self._persist_job(job)
            logger.error(f"video_gen: job {job_id} failed: {exc}", exc_info=True)

        return job

    async def plan_scenes_and_footage(self, job_id: str) -> VideoGenJob:
        """Plan story and search footage candidates without rendering (interactive mode)."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        work_dir = os.path.join(self._output_dir, job_id)
        os.makedirs(work_dir, exist_ok=True)

        try:
            # Step 1: Generate story
            job.status = VideoGenStatus.GENERATING_STORY
            job.progress = 15
            self._persist_job(job)
            story = await self._step_generate_story(job)
            job.story = story
            job.title = story.get("title")
            job.progress = 40
            self._persist_job(job)

            # Step 2: Search footage candidates
            job.status = VideoGenStatus.SEARCHING_FOOTAGE
            job.progress = 50
            self._persist_job(job)
            scenes = await self._step_search_footage(story, work_dir, job=job)

            # AI Video Director Curation Pass for initial selection
            from src.infrastructure.story_agent import StoryAgent
            story_agent = StoryAgent()
            scenes = await story_agent.curate_scene_footages(scenes)

            # Pre-select top candidate for any unassigned scenes
            for scene in scenes:
                candidates = scene.get("footage_candidates", [])
                if candidates and not scene.get("selected_footage"):
                    best = self._pick_best_candidate(candidates, scene) or candidates[0]
                    scene["selected_footage"] = best
                    scene["footage_source"] = best

            job.scenes_with_footage = scenes
            job.status = VideoGenStatus.AWAITING_SELECTION
            job.progress = 100
            self._persist_job(job)

        except Exception as exc:
            job.status = VideoGenStatus.FAILED
            job.error = str(exc)
            job.completed_at = time.time()
            self._persist_job(job)
            logger.error(f"video_gen [{job_id}] planning failed: {exc}", exc_info=True)

        return job

    async def search_scene_footage(self, job_id: str, scene_id: int, query: str) -> list[dict]:
        """Re-search footage candidates for a specific scene with custom keywords."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        scenes = job.scenes_with_footage or (job.story.get("scenes", []) if job.story else [])
        target_scene = None
        for s in scenes:
            if s.get("id") == scene_id:
                target_scene = s
                break

        if not target_scene:
            raise ValueError(f"Scene {scene_id} not found in job {job_id}")

        from src.infrastructure.social_footage_searcher import SocialFootageSearcher

        searcher = SocialFootageSearcher()
        is_id = (getattr(job, "language", "id") or "id").lower() == "id"
        candidates = await searcher.search_for_single_scene(
            target_scene,
            is_indonesian=is_id,
            results_per_platform=3,
            custom_query=query,
        )
        target_scene["footage_candidates"] = candidates
        job.scenes_with_footage = scenes
        self._persist_job(job)
        return candidates

    async def render_with_selected_scenes(self, job_id: str, selected_scenes: list[dict]) -> VideoGenJob:
        """Render final video using user-curated footage selections."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if selected_scenes:
            job.scenes_with_footage = selected_scenes
            if job.story:
                job.story["scenes"] = selected_scenes

        work_dir = os.path.join(self._output_dir, job_id)
        os.makedirs(work_dir, exist_ok=True)

        try:
            # Step 3 & 4: Parallel Execution of TTS Generation and Footage Download
            job.status = VideoGenStatus.DOWNLOADING
            job.progress = 25
            self._persist_job(job)

            scenes_input = list(job.scenes_with_footage or [])
            tts_task = self._step_generate_tts(scenes_input, job, work_dir)
            dl_task = self._step_download_footage(scenes_input, work_dir)
            scenes_tts, scenes_dl = await asyncio.gather(tts_task, dl_task)

            for i, scene in enumerate(scenes_input):
                if i < len(scenes_tts):
                    scene["tts_path"] = scenes_tts[i].get("tts_path")
                    scene["tts_duration"] = scenes_tts[i].get("tts_duration")
                    scene["audio_path"] = scenes_tts[i].get("audio_path")
                    scene["audio_duration"] = scenes_tts[i].get("audio_duration")
                if i < len(scenes_dl):
                    scene["footage_path"] = scenes_dl[i].get("footage_path")
                    scene["selected_footage"] = scenes_dl[i].get("selected_footage")
                    scene["footage_source"] = scenes_dl[i].get("footage_source")

            scenes = scenes_input
            job.scenes_with_footage = scenes
            job.progress = 65
            self._persist_job(job)

            # Step 4b: Gemini Agentic Video Understanding Alignment Pass
            if getattr(job, "agentic_understanding", True):
                logger.info(f"video_gen [{job_id}]: running Gemini Agentic Video Understanding alignment pass on selected scenes...")
                try:
                    from src.infrastructure.gemini_agentic_video_service import GeminiAgenticVideoService
                    agentic_svc = GeminiAgenticVideoService()
                    for scene in scenes:
                        f_path = scene.get("footage_path")
                        if f_path and os.path.exists(f_path):
                            await agentic_svc.align_scene_footage(
                                scene=scene,
                                local_footage_path=f_path,
                                topic=job.topic,
                                processing_mode=getattr(job, "video_processing_mode", "agentic") or "agentic",
                                media_resolution=getattr(job, "media_resolution", "low") or "low",
                                fps=getattr(job, "fps", None),
                                start_offset=getattr(job, "start_offset", None),
                                end_offset=getattr(job, "end_offset", None),
                            )
                except Exception as ag_err:
                    logger.warning(f"video_gen [{job_id}]: agentic alignment pass fallback ({ag_err})")

            job.scenes_with_footage = scenes
            job.progress = 75
            self._persist_job(job)

            # Step 5: Assemble timeline
            job.status = VideoGenStatus.ASSEMBLING
            job.progress = 80
            self._persist_job(job)
            timeline = self._step_assemble_timeline(scenes)
            job.timeline = timeline
            job.progress = 85
            self._persist_job(job)

            # Step 6: Render final video
            job.status = VideoGenStatus.RENDERING
            job.progress = 90
            self._persist_job(job)
            output_path = await self._step_render_video(timeline, job, work_dir)
            job.output_path = output_path
            job.progress = 100
            job.status = VideoGenStatus.COMPLETED
            job.completed_at = time.time()
            self._persist_job(job)

            total_time = job.completed_at - job.created_at
            logger.info(
                f"video_gen [{job_id}] rendered with custom footage in {total_time:.1f}s → {output_path}"
            )

        except Exception as exc:
            job.status = VideoGenStatus.FAILED
            job.error = str(exc)
            job.completed_at = time.time()
            self._persist_job(job)
            logger.error(f"video_gen [{job_id}] render failed: {exc}", exc_info=True)

        return job

    # ─── Pipeline Steps ────────────────────────────────────────────────────────

    async def _step_generate_story(self, job: VideoGenJob) -> dict:
        """Step 1: AI generates structured story from topic or understands source video."""
        from src.infrastructure.story_agent import StoryAgent, StoryGenerationError

        agent = StoryAgent()

        if getattr(job, "source_video_url", None) and job.source_video_url.strip():
            story = await agent.generate_story_from_video(
                source_video_url=job.source_video_url.strip(),
                topic=job.topic,
                target_duration=job.target_duration,
                num_scenes=job.num_scenes,
                instructions=job.instructions,
                use_agentic=getattr(job, "agentic_understanding", True),
            )
        else:
            story = await agent.generate_story(
                topic=job.topic,
                target_duration=job.target_duration,
                num_scenes=job.num_scenes,
                instructions=job.instructions,
                language=getattr(job, "language", "id") or "id",
            )

        if job.custom_hook and job.custom_hook.strip():
            story["hook"] = job.custom_hook.strip()

        logger.info(
            f"video_gen [{job.job_id}]: story generated — "
            f"'{story.get('title', '')}', {len(story.get('scenes', []))} scenes (language={getattr(job, 'language', 'id')})"
        )
        return story

    async def _step_search_footage(self, story: dict, work_dir: str, job: Optional[VideoGenJob] = None) -> list[dict]:
        """Step 2: Search multi-platform footage (YouTube Shorts, TikTok, Instagram, Threads, X, stock) per scene."""
        from src.infrastructure.social_footage_searcher import SocialFootageSearcher

        searcher = SocialFootageSearcher()
        scenes = story.get("scenes", [])
        is_id = (getattr(job, "language", "id") or "id").lower() == "id" if job else True

        scenes = await searcher.search_for_scenes(
            scenes=scenes,
            is_indonesian=is_id,
            results_per_platform=3,
        )

        # If job has a source_video_url, inject it as primary candidate with exact timestamps
        if job and getattr(job, "source_video_url", None) and job.source_video_url.strip():
            for s in scenes:
                ts_start = float(s.get("source_start_timestamp") or 0.0)
                src_cand = {
                    "video_id": "source_video",
                    "title": f"Source Video ({ts_start:.1f}s)",
                    "url": job.source_video_url.strip(),
                    "thumbnail_url": "",
                    "duration_seconds": 60,
                    "view_count": 100000,
                    "channel": "Source Video",
                    "query": s.get("visual", ""),
                    "platform": "youtube" if ("youtube.com" in job.source_video_url or "youtu.be" in job.source_video_url) else "direct",
                    "start_timestamp": ts_start,
                }
                cands = [src_cand] + [c for c in s.get("footage_candidates", []) if c.get("video_id") != "source_video"]
                s["footage_candidates"] = cands
                s["selected_footage"] = src_cand
                s["footage_source"] = src_cand

        total_candidates = sum(
            len(s.get("footage_candidates", [])) for s in scenes
        )
        logger.info(
            f"video_gen: found {total_candidates} footage candidates "
            f"across {len(scenes)} scenes"
        )
        return scenes

    async def _step_download_footage(
        self, scenes: list[dict], work_dir: str
    ) -> list[dict]:
        """Step 3: Download top candidate for each scene via yt-dlp / direct stock downloader with multi-candidate fallback."""
        from src.infrastructure.footage_downloader import FootageDownloader

        downloader = FootageDownloader(output_dir=os.path.join(work_dir, "footage"))

        for i, scene in enumerate(scenes):
            selected = scene.get("selected_footage") or scene.get("footage_source")
            raw_cands = scene.get("footage_candidates", []) or []

            # Prioritize candidates list: selected candidate first, then rest sorted by score
            ordered_candidates: list[dict] = []
            if selected:
                ordered_candidates.append(selected)

            scored = []
            for c in raw_cands:
                if not isinstance(c, dict):
                    continue
                if selected and (
                    (c.get("video_id") and c.get("video_id") == selected.get("video_id"))
                    or (c.get("url") and c.get("url") == selected.get("url"))
                ):
                    continue
                score = self._score_candidate(c, scene)
                scored.append((score, c))

            scored.sort(key=lambda x: x[0], reverse=True)
            ordered_candidates.extend([c for _, c in scored])

            downloaded_path = None
            used_source = None

            # Try candidate options in order until a valid footage file is successfully downloaded
            for cand_idx, cand in enumerate(ordered_candidates):
                # If already downloaded local file exists, reuse
                if cand.get("local_path") and os.path.exists(cand["local_path"]) and os.path.getsize(cand["local_path"]) > 0:
                    downloaded_path = cand["local_path"]
                    used_source = cand
                    break

                video_url = cand.get("url", "")
                if not video_url and cand.get("video_id"):
                    video_url = f"https://www.youtube.com/watch?v={cand['video_id']}"

                if not video_url:
                    continue

                try:
                    logger.info(
                        f"video_gen: downloading footage for scene {i + 1} "
                        f"(candidate {cand_idx + 1}/{len(ordered_candidates)}): {cand.get('title', '')[:50]}"
                    )
                    local_path = await downloader.download_segment(
                        url=video_url,
                        start_time=float(cand.get("start_timestamp") or 0.0),
                        duration=max(10.0, float(scene.get("duration_estimate", 7)) + 4.0),
                        scene_id=scene.get("id", i + 1),
                        platform=cand.get("platform"),
                        video_id=cand.get("video_id"),
                    )
                    if local_path and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                        downloaded_path = local_path
                        used_source = cand
                        break
                except Exception as dl_err:
                    logger.warning(f"video_gen: candidate {cand_idx + 1} download failed for scene {i + 1}: {dl_err}")

            # Dynamic query fallback if all initial candidates failed
            if not downloaded_path:
                logger.warning(f"video_gen: all {len(ordered_candidates)} candidates failed for scene {i + 1}, trying dynamic query fallback...")
                try:
                    from src.infrastructure.youtube_search import YouTubeSearch
                    yt = YouTubeSearch()
                    fallback_queries = list(scene.get("search_queries", []))
                    if scene.get("visual"):
                        fallback_queries.append(scene["visual"][:80])

                    for fq in fallback_queries:
                        if not fq:
                            continue
                        fb_cands = await yt.search_for_single_scene(scene, custom_query=fq, results_per_query=3)
                        for fb_c in fb_cands:
                            fb_url = fb_c.get("url") or (f"https://www.youtube.com/watch?v={fb_c['video_id']}" if fb_c.get("video_id") else None)
                            if not fb_url:
                                continue
                            fb_path = await downloader.download_segment(
                                url=fb_url,
                                start_time=float(fb_c.get("start_timestamp") or 0.0),
                                duration=max(10.0, float(scene.get("duration_estimate", 7)) + 4.0),
                                scene_id=scene.get("id", i + 1),
                                platform=fb_c.get("platform"),
                                video_id=fb_c.get("video_id"),
                            )
                            if fb_path and os.path.exists(fb_path) and os.path.getsize(fb_path) > 0:
                                downloaded_path = fb_path
                                used_source = fb_c
                                break
                        if downloaded_path:
                            break
                except Exception as fb_err:
                    logger.warning(f"video_gen: dynamic fallback search failed for scene {i + 1}: {fb_err}")

            # Adjacent scene borrowing fallback: NEVER leave scene with black screen if other scenes have footage
            if not downloaded_path:
                for other_scene in scenes:
                    if other_scene.get("footage_path") and os.path.exists(other_scene["footage_path"]):
                        downloaded_path = other_scene["footage_path"]
                        used_source = other_scene.get("footage_source") or other_scene.get("selected_footage")
                        logger.info(f"video_gen: scene {i + 1} borrowing footage from scene {other_scene.get('id', '?')} to prevent black frame")
                        break

            scene["footage_path"] = downloaded_path
            scene["selected_footage"] = used_source
            scene["footage_source"] = used_source

        return scenes

    async def _step_generate_tts(
        self, scenes: list[dict], job: VideoGenJob, work_dir: str
    ) -> list[dict]:
        """Step 4: Generate TTS audio per scene via Gemini TTS (default), Deepgram, or failproof EdgeTTS."""
        tts_dir = os.path.join(work_dir, "tts")
        os.makedirs(tts_dir, exist_ok=True)

        provider = (job.tts_provider or getattr(settings, "VIDEO_GEN_TTS_PROVIDER", "gemini") or "gemini").lower()
        if "deepgram" in provider or (job.voice and "aura" in job.voice.lower()):
            primary_provider = "deepgram"
        else:
            primary_provider = "gemini"

        # ── 1. Try Primary Provider ──
        if primary_provider == "gemini":
            from src.infrastructure.gemini_tts import GeminiTTS
            tts = GeminiTTS(output_dir=tts_dir)
            voice_id = job.voice or getattr(settings, "GEMINI_TTS_VOICE", "Kore")
            model_id = job.tts_model or getattr(settings, "GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")

            try:
                scenes = await tts.synthesize_scenes(
                    scenes=scenes,
                    voice_id=voice_id,
                    model_id=model_id,
                    speed=job.speed,
                )
            except Exception as exc:
                logger.warning(f"video_gen: GeminiTTS synthesize_scenes failed ({exc}), falling back to individual calls")
                for i, scene in enumerate(scenes):
                    narration = (scene.get("narration") or "").strip()
                    if not narration or scene.get("tts_path"):
                        continue
                    try:
                        audio_path = await tts.synthesize(
                            text=narration,
                            voice_id=voice_id,
                            model_id=model_id,
                            speed=job.speed,
                            output_path=os.path.join(tts_dir, f"tts_{i + 1}.mp3"),
                        )
                        if audio_path and os.path.exists(audio_path):
                            dur = await self._media_duration(audio_path, fallback=5.0)
                            scene["tts_path"] = audio_path
                            scene["tts_duration"] = dur
                    except Exception as e:
                        logger.warning(f"video_gen: Gemini TTS failed for scene {i + 1}: {e}")

        else:
            from src.infrastructure.deepgram_tts import DeepgramTTS
            tts = DeepgramTTS(output_dir=tts_dir)
            voice = job.voice or settings.DEEPGRAM_TTS_VOICE

            try:
                scenes = await tts.synthesize_scenes(
                    scenes=scenes,
                    voice=voice,
                    speed=job.speed,
                )
            except Exception as exc:
                logger.warning(f"video_gen: Deepgram synthesize_scenes failed ({exc}), falling back to individual calls")
                for i, scene in enumerate(scenes):
                    narration = (scene.get("narration") or "").strip()
                    if not narration or scene.get("tts_path"):
                        continue
                    try:
                        audio_path = await tts.synthesize(
                            text=narration,
                            voice=voice,
                            speed=job.speed,
                            output_path=os.path.join(tts_dir, f"tts_{i + 1}.mp3"),
                        )
                        if audio_path and os.path.exists(audio_path):
                            duration = await self._media_duration(audio_path, fallback=5.0)
                            scene["tts_path"] = audio_path
                            scene["tts_duration"] = duration
                    except Exception as e:
                        logger.warning(f"video_gen: Deepgram TTS failed for scene {i + 1}: {e}")

        # ── 2. Fallback to Secondary Provider for any failed scenes ──
        missing_scenes = [s for s in scenes if not s.get("tts_path") and (s.get("narration") or "").strip()]
        if missing_scenes:
            sec_provider = "deepgram" if primary_provider == "gemini" else "gemini"
            logger.info(f"video_gen: {len(missing_scenes)} scenes missing audio, attempting secondary provider '{sec_provider}'")
            if sec_provider == "deepgram":
                try:
                    from src.infrastructure.deepgram_tts import DeepgramTTS
                    sec_tts = DeepgramTTS(output_dir=tts_dir)
                    for i, scene in enumerate(scenes):
                        if not scene.get("tts_path") and (scene.get("narration") or "").strip():
                            a_path = await sec_tts.synthesize(text=scene["narration"].strip(), speed=job.speed)
                            if a_path and os.path.exists(a_path):
                                dur = await self._media_duration(a_path, fallback=5.0)
                                scene["tts_path"] = a_path
                                scene["tts_duration"] = dur
                except Exception as sec_err:
                    logger.warning(f"video_gen: secondary Deepgram fallback failed: {sec_err}")
            else:
                try:
                    from src.infrastructure.gemini_tts import GeminiTTS
                    sec_tts = GeminiTTS(output_dir=tts_dir)
                    for i, scene in enumerate(scenes):
                        if not scene.get("tts_path") and (scene.get("narration") or "").strip():
                            a_path = await sec_tts.synthesize(text=scene["narration"].strip(), speed=job.speed)
                            if a_path and os.path.exists(a_path):
                                dur = await self._media_duration(a_path, fallback=5.0)
                                scene["tts_path"] = a_path
                                scene["tts_duration"] = dur
                except Exception as sec_err:
                    logger.warning(f"video_gen: secondary Gemini TTS fallback failed: {sec_err}")

        # ── 3. Failproof Tertiary Fallback: EdgeTTS (Free Neural TTS) ──
        still_missing = [s for s in scenes if not s.get("tts_path") and (s.get("narration") or "").strip()]
        if still_missing:
            logger.info(f"video_gen: {len(still_missing)} scenes still missing audio, applying zero-quota EdgeTTS Neural fallback")
            try:
                from src.infrastructure.edge_tts_helper import EdgeTTSHelper
                edge_helper = EdgeTTSHelper(output_dir=tts_dir)
                for i, scene in enumerate(scenes):
                    if not scene.get("tts_path") and (scene.get("narration") or "").strip():
                        a_path = await edge_helper.synthesize(
                            text=scene["narration"].strip(),
                            speed=job.speed,
                            output_path=os.path.join(tts_dir, f"edge_scene_{i + 1}.mp3"),
                        )
                        if a_path and os.path.exists(a_path):
                            dur = await self._media_duration(a_path, fallback=5.0)
                            scene["tts_path"] = a_path
                            scene["tts_duration"] = dur
                            logger.info(f"video_gen: scene {i + 1} rescued with EdgeTTS ({dur:.2f}s)")
            except Exception as edge_err:
                logger.error(f"video_gen: EdgeTTS fallback error: {edge_err}")

        # Ensure audio_path and audio_duration aliases
        for scene in scenes:
            if scene.get("tts_path"):
                scene["audio_path"] = scene["tts_path"]
            if scene.get("tts_duration"):
                scene["audio_duration"] = scene["tts_duration"]

        return scenes

    def _step_assemble_timeline(self, scenes: list[dict]) -> list[dict]:
        """Step 5: Assemble timeline with exact timing."""
        timeline = []
        current_time = 0.0

        for scene in scenes:
            duration = scene.get("tts_duration") or scene.get("audio_duration") or scene.get("duration_estimate", 7)
            audio_path = scene.get("tts_path") or scene.get("audio_path")
            entry = {
                "scene_id": scene.get("id", len(timeline) + 1),
                "narration": scene.get("narration", ""),
                "footage_path": scene.get("footage_path"),
                "audio_path": audio_path,
                "tts_path": audio_path,
                "start_time": current_time,
                "duration": duration,
                "start_timestamp": float(scene.get("start_timestamp") or 0.0),
                "transition": scene.get("transition", "cut"),
                "visual": scene.get("visual", ""),
            }
            timeline.append(entry)
            current_time += duration

        total_duration = current_time
        logger.info(
            f"video_gen: timeline assembled — {len(timeline)} entries, "
            f"total duration: {total_duration:.1f}s"
        )

        return timeline

    async def _step_render_video(
        self, timeline: list[dict], job: VideoGenJob, work_dir: str
    ) -> str:
        """Step 6: FFmpeg render — combine footage + TTS + subtitles + opening hook.

        Produces a final 9:16 (1080x1920) MP4.
        """
        output_path = os.path.join(work_dir, f"final_{job.job_id}.mp4")

        # Step 6a: Prepare individual scene clips (footage trimmed to TTS duration)
        clips_dir = os.path.join(work_dir, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        scene_clips = []
        for entry in timeline:
            clip_path = await self._prepare_scene_clip(entry, clips_dir)
            scene_clips.append(clip_path)

        # Step 6b: Concatenate all scene clips
        concat_path = os.path.join(work_dir, "concat_video.mp4")
        try:
            await self._concat_clips(scene_clips, concat_path, transition=job.transition)
        except TypeError:
            await self._concat_clips(scene_clips, concat_path)

        # Step 6c: Merge TTS audio with timed silence for missing scene narration.
        merged_audio_path = os.path.join(work_dir, "narration_full.mp3")
        await self._concat_audio(timeline, merged_audio_path)

        # Step 6d: Subtitles (Skia or FFmpeg ASS)
        from src.infrastructure.hf_style_catalog import resolve_engine

        sub_engine = "skia"
        if job.subtitles_enabled:
            if isinstance(job.subtitle_style, dict):
                sub_engine = (
                    job.subtitle_style.get("engine")
                    or resolve_engine(job.subtitle_style)
                )
            elif isinstance(job.subtitle_style, str):
                sub_engine = resolve_engine({"animation": job.subtitle_style})

            # In VideoGenerator pipeline, remotion/hyperframes subtitle engines map to Skia or FFmpeg
            if sub_engine not in ("skia", "ffmpeg"):
                preset = ""
                if isinstance(job.subtitle_style, dict):
                    preset = str(job.subtitle_style.get("stylePreset") or job.subtitle_style.get("preset") or "").lower()
                elif isinstance(job.subtitle_style, str):
                    preset = job.subtitle_style.lower()

                if preset in ("classic", "classic_karaoke"):
                    sub_engine = "ffmpeg"
                else:
                    sub_engine = "skia"

        subtitle_path = None
        if job.subtitles_enabled and sub_engine == "ffmpeg":
            candidate_path = os.path.join(work_dir, "captions.ass")
            if write_ass_subtitles(timeline, candidate_path, job.subtitle_style):
                subtitle_path = candidate_path

        # Step 6e: Final composite — video + narration + optional FFmpeg subtitle + optional BGM
        subtitle_burned = await self._final_composite(
            video_path=concat_path,
            audio_path=merged_audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            job=job,
            work_dir=work_dir,
        )

        if not os.path.exists(output_path):
            raise RuntimeError("Final video render failed — output file not created")

        font_candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")),
            "backend/assets/fonts",
            "assets/fonts",
        ]
        fonts_dir = next((d for d in font_candidates if os.path.exists(d)), "assets/fonts")

        # Step 6e.2: If subtitles enabled and NOT yet burned (e.g. Skia engine or FFmpeg ASS pass skipped/failed), apply Skia subtitle overlay
        if job.subtitles_enabled and not subtitle_burned:
            try:
                from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
                skia_sub = SkiaSubtitleRenderer(font_dir=fonts_dir)

                # Build timed words from timeline narration & scene word timestamps
                timeline_words = []
                t_cursor = 0.0
                for entry in timeline:
                    dur = max(0.1, float(entry.get("duration", 0.0) or entry.get("tts_duration", 0.0) or entry.get("audio_duration", 0.0) or 0.0))
                    narr = str(entry.get("narration", "") or "").strip()
                    entry_words = entry.get("words")
                    if entry_words and isinstance(entry_words, list) and len(entry_words) > 0:
                        for w in entry_words:
                            if isinstance(w, dict) and "word" in w:
                                timeline_words.append({
                                    "word": str(w["word"]),
                                    "start": round(t_cursor + float(w.get("start", 0)), 2),
                                    "end": round(t_cursor + float(w.get("end", 0.1)), 2),
                                })
                    elif narr:
                        tokens = narr.split()
                        if tokens:
                            step_dur = dur / len(tokens)
                            for wi, tok in enumerate(tokens):
                                timeline_words.append({
                                    "word": tok,
                                    "start": round(t_cursor + wi * step_dur, 2),
                                    "end": round(t_cursor + (wi + 1) * step_dur, 2),
                                })
                    t_cursor += dur

                if timeline_words:
                    sub_rendered_path = os.path.join(work_dir, f"sub_skia_{job.job_id}.mp4")
                    style_cfg = job.subtitle_style if isinstance(job.subtitle_style, dict) else {"stylePreset": job.subtitle_style}

                    await asyncio.to_thread(
                        skia_sub.render_subtitles,
                        video_path=output_path,
                        words=timeline_words,
                        style=style_cfg,
                        output_path=sub_rendered_path,
                    )
                    if os.path.exists(sub_rendered_path) and os.path.getsize(sub_rendered_path) > 0:
                        import shutil
                        shutil.move(sub_rendered_path, output_path)
                        subtitle_burned = True
                        logger.info(f"video_gen [{job.job_id}]: successfully applied Skia subtitle overlay ({len(timeline_words)} words)")
            except Exception as sub_err:
                logger.warning(f"video_gen [{job.job_id}]: Skia subtitle overlay error: {sub_err}, attempting fallback ASS...")

            # Emergency Fallback: If still not burned, burn via FFmpeg ASS subtitles filter
            if not subtitle_burned:
                try:
                    ass_fallback = os.path.join(work_dir, "captions_fallback.ass")
                    if write_ass_subtitles(timeline, ass_fallback, job.subtitle_style):
                        fb_sub_path = os.path.join(work_dir, f"sub_fb_{job.job_id}.mp4")
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", output_path,
                            "-vf", ffmpeg_subtitle_filter(ass_fallback, fonts_dir),
                            "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                            "-c:a", "copy",
                            "-movflags", "+faststart",
                            fb_sub_path,
                        ]
                        succeeded, _ = await self._run_ffmpeg(cmd, timeout=120)
                        if succeeded and os.path.exists(fb_sub_path) and os.path.getsize(fb_sub_path) > 0:
                            import shutil
                            shutil.move(fb_sub_path, output_path)
                            subtitle_burned = True
                            logger.info(f"video_gen [{job.job_id}]: successfully applied emergency fallback ASS subtitles")
                except Exception as fb_err:
                    logger.warning(f"video_gen [{job.job_id}]: fallback ASS subtitle burning failed: {fb_err}")

        # Step 6f: Burn opening Hook overlay if hook is enabled
        if job.hook_enabled and os.path.exists(output_path):
            hook_text = (
                job.custom_hook
                or (job.story.get("hook") if job.story else "")
                or (job.title if job.title else "")
                or (timeline[0].get("narration") if timeline else "")
            )
            if hook_text and hook_text.strip():
                hook_style_dict = job.hook_style if isinstance(job.hook_style, dict) else {"animation": job.hook_style}
                hook_engine = (
                    hook_style_dict.get("engine")
                    or resolve_engine(hook_style_dict)
                )
                hook_style_name = (
                    hook_style_dict.get("animation")
                    or hook_style_dict.get("hook_style")
                    or "skia_impact_badge"
                )
                hook_duration = float(hook_style_dict.get("duration", 3.0) or 3.0)

                hook_applied = False

                # 1. HyperFrames Hook Engine
                if hook_engine == "hyperframes":
                    try:
                        from src.infrastructure.hyperframes_adapter import get_hyperframes_adapter
                        hf = get_hyperframes_adapter()
                        from src.infrastructure.hf_style_catalog import resolve_hf_template
                        hf_tpl = resolve_hf_template(hook_style_dict, kind="hook")
                        events = [{
                            "label": hook_text.strip()[:80],
                            "sub": "HOOK",
                            "start": 0.0,
                            "end": max(0.8, hook_duration),
                            "word": hook_text.strip()[:80],
                        }]
                        hf_hook_path = os.path.join(work_dir, f"hook_hf_{job.job_id}.mp4")
                        hf_res = await hf.render_polish(
                            base_video=output_path,
                            events=events,
                            output_path=hf_hook_path,
                            template=hf_tpl,
                            duration=hook_duration,
                            job_id=job.job_id,
                            force=True,
                        )
                        if hf_res.get("ok") and os.path.exists(hf_hook_path) and os.path.getsize(hf_hook_path) > 0:
                            import shutil
                            shutil.move(hf_hook_path, output_path)
                            hook_applied = True
                            logger.info(f"video_gen [{job.job_id}]: successfully applied HyperFrames hook overlay ({hf_tpl})")
                    except Exception as hf_err:
                        logger.warning(f"video_gen [{job.job_id}]: HyperFrames hook failed, falling back to Skia: {hf_err}")

                # 2. Remotion Hook Engine
                if not hook_applied and hook_engine == "remotion":
                    try:
                        from src.infrastructure.remotion_adapter import RemotionAdapter
                        remotion = RemotionAdapter()
                        # If Remotion server is active, try remotion render; otherwise fallback
                        pass
                    except Exception as rem_err:
                        logger.warning(f"video_gen [{job.job_id}]: Remotion hook unavailable, falling back to Skia: {rem_err}")

                # 3. Skia / FFmpeg Hook Engine (or Fallback)
                if not hook_applied:
                    try:
                        from src.infrastructure.skia_hook_renderer import SkiaHookRenderer
                        renderer = SkiaHookRenderer(font_dir=fonts_dir)
                        hooked_path = os.path.join(work_dir, f"hooked_{job.job_id}.mp4")
                        await renderer.render_hook(
                            video_path=output_path,
                            hook_text=hook_text.strip(),
                            output_path=hooked_path,
                            hook_style=hook_style_name,
                            style_config=hook_style_dict,
                        )
                        if os.path.exists(hooked_path) and os.path.getsize(hooked_path) > 0:
                            import shutil
                            shutil.move(hooked_path, output_path)
                            hook_applied = True
                            logger.info(f"video_gen [{job.job_id}]: successfully applied Skia hook overlay ({hook_style_name})")
                    except Exception as hook_err:
                        logger.warning(f"video_gen [{job.job_id}]: failed to burn hook overlay: {hook_err}")

        # Step 6g: Watermark overlay
        if job.watermark_config and os.path.exists(output_path):
            try:
                from src.infrastructure.watermark_renderer import apply_watermark_if_configured
                await apply_watermark_if_configured(
                    config=job.watermark_config,
                    output_dir=work_dir,
                    clip_rank=1,
                    final_path=output_path,
                    fonts_dir="assets/fonts",
                    job_id=job.job_id,
                )
                logger.info(f"video_gen [{job.job_id}]: successfully applied watermark")
            except Exception as wm_err:
                logger.warning(f"video_gen [{job.job_id}]: watermark application failed: {wm_err}")

        # Step 6h: Call to Action (CTA) overlay / end-card
        if job.cta_config and os.path.exists(output_path):
            try:
                from src.infrastructure.cta_renderer import apply_cta_if_configured
                await apply_cta_if_configured(
                    config=job.cta_config,
                    output_dir=work_dir,
                    clip_rank=1,
                    final_path=output_path,
                    fonts_dir="assets/fonts",
                    job_id=job.job_id,
                )
                logger.info(f"video_gen [{job.job_id}]: successfully applied CTA end-card")
            except Exception as cta_err:
                logger.warning(f"video_gen [{job.job_id}]: CTA application failed: {cta_err}")

        # Step 6i: Extract crisp keyframe thumbnail at 00:00:01 and render viral TikTok cover
        try:
            thumb_filename = f"thumbnail_{job.job_id}.jpg"
            thumb_path = os.path.join(work_dir, thumb_filename)
            thumb_cmd = [
                "ffmpeg", "-y",
                "-ss", "00:00:01",
                "-i", output_path,
                "-vframes", "1",
                "-q:v", "2",
                thumb_path,
            ]
            await self._run_ffmpeg(thumb_cmd, timeout=30)
            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                # Enhance thumbnail into high-CTR TikTok cover with Hook, Caption, and Hashtags
                try:
                    from src.infrastructure.social_cover_generator import generate_social_cover
                    hook_for_cover = (
                        job.custom_hook
                        or (job.story or {}).get("hook")
                        or (job.story or {}).get("title")
                        or job.topic
                    )
                    caption_for_cover = (
                        (job.story or {}).get("title")
                        if (job.story or {}).get("title") != hook_for_cover
                        else job.topic
                    )
                    wm_text = None
                    if job.watermark_config and job.watermark_config.get("enabled"):
                        wm_text = job.watermark_config.get("text")

                    generate_social_cover(
                        base_image_path=thumb_path,
                        output_path=thumb_path,
                        hook_text=hook_for_cover,
                        caption_text=caption_for_cover,
                        hashtags=None,  # Generates dynamic tags from topic keywords
                        aspect_ratio=getattr(job, "aspect_ratio", "9:16") or "9:16",
                        watermark_text=wm_text,
                        include_play_indicator=True,
                    )
                except Exception as cover_err:
                    logger.warning(f"video_gen [{job.job_id}]: social cover enhancement fallback ({cover_err})")

                job.thumbnail_url = f"/api/video-generator/jobs/{job.job_id}/thumbnail"
                self._persist_job(job)
                logger.info(f"video_gen [{job.job_id}]: generated viral social thumbnail cover -> {thumb_path}")
        except Exception as th_err:
            logger.debug(f"video_gen [{job.job_id}]: thumbnail extraction error: {th_err}")

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(
            f"video_gen [{job.job_id}]: final video {size_mb:.1f}MB (Subtitles={job.subtitles_enabled}, Hook={job.hook_enabled}, Watermark={bool(job.watermark_config)}, CTA={bool(job.cta_config)}) → {output_path}"
        )

        return output_path

    # ─── Helper Methods ────────────────────────────────────────────────────────

    def _score_candidate(self, candidate: dict, scene: dict) -> float:
        """Calculate deep semantic relevance score for a footage candidate."""
        if not candidate or not isinstance(candidate, dict):
            return 0.0

        target_duration = scene.get("duration_estimate", 7)
        search_terms = set()
        entity_terms = set()

        visual = scene.get("visual", "")
        for word in visual.lower().split():
            clean_w = "".join(c for c in word if c.isalnum())
            if len(clean_w) > 3:
                search_terms.add(clean_w)

        for q in scene.get("search_queries", []):
            q_words = [("".join(c for c in w if c.isalnum())) for w in q.lower().split()]
            for word in q_words:
                if len(word) > 2:
                    search_terms.add(word)
            # First query is typically the specific entity query (e.g. "Salatiga aerial drone")
            if q == scene.get("search_queries", [""])[0]:
                for word in q_words:
                    if len(word) > 3:
                        entity_terms.add(word)

        for word in scene.get("narration", "").lower().split():
            clean_w = "".join(c for c in word if c.isalnum())
            if len(clean_w) > 4:
                search_terms.add(clean_w)

        score = 0.0
        title_lower = candidate.get("title", "").lower()
        title_words = set("".join(c for c in w if c.isalnum()) for w in title_lower.split() if len(w) > 2)
        cand_query_words = set("".join(c for c in w if c.isalnum()) for w in candidate.get("query", "").lower().split() if len(w) > 2)

        # 0. Dynamic Negative Keyword Filtering (using scene-defined avoid keywords)
        avoid_keywords = set(scene.get("avoid_keywords", [])) | set(scene.get("negative_keywords", []))
        if avoid_keywords:
            cand_blob = f"{title_lower} {candidate.get('query', '')}".lower()
            if any(k.lower() in cand_blob for k in avoid_keywords if k.strip()):
                return -50.0

        # 1. Named Entity Exact Match Bonus (e.g. "Salatiga" or "Jawa Tengah" in YouTube title)
        entity_overlap = len(entity_terms & title_words)
        if entity_overlap > 0:
            score += entity_overlap * 5.0

        # 2. General Keyword Overlap
        overlap = len(search_terms & (title_words | cand_query_words))
        score += overlap * 2.5

        # 3. Platform preference
        platform = candidate.get("platform", "").lower()
        if platform in ["pexels", "pixabay"]:
            score += 3.0
        elif platform == "youtube" and entity_overlap > 0:
            # High-value real local documentary/drone footage on YouTube
            score += 4.0

        # 4. View count bonus (log scale)
        views = candidate.get("view_count", 0)
        if views > 1000000:
            score += 2.0
        elif views > 100000:
            score += 1.5
        elif views > 10000:
            score += 1.0
        elif views > 1000:
            score += 0.5

        # 5. Duration preference: prefer videos with enough footage for full scene length
        dur = candidate.get("duration_seconds", 0)
        if dur >= target_duration:
            score += 1.5
        elif dur >= target_duration * 0.7:
            score += 0.8

        # 6. Stock & Documentary keywords bonus
        stock_keywords = [
            "footage", "cinematic", "drone", "4k", "stock", "timelapse",
            "b-roll", "broll", "macro", "slow motion", "4k 60fps", "close up",
            "aerial", "sejarah", "history", "vintage", "archive", "colonial"
        ]
        for kw in stock_keywords:
            if kw in title_lower:
                score += 1.2

        return score

    def _pick_best_candidate(self, candidates: list[dict], scene: dict) -> Optional[dict]:
        """Score and pick the best footage candidate for a scene."""
        if not candidates:
            return None

        scored = [(self._score_candidate(c, scene), c) for c in candidates if isinstance(c, dict)]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    async def _download_youtube_segment(
        self, url: str, duration_needed: float, output_dir: str, scene_id: int
    ) -> Optional[str]:
        """Download a YouTube video segment via yt-dlp."""
        filename = f"footage_scene_{scene_id}_{uuid4().hex[:6]}.mp4"
        output_path = os.path.join(output_dir, filename)

        # Skip first 2 seconds intro buffer for long videos to capture active content
        start_sec = 2
        section = f"*{start_sec}-{int(duration_needed) + start_sec + 5}"

        cmd = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=web,web_creator,android,ios",
            "--format-sort", "res:2160,fps:60,vcodec:av01,vcodec:vp9,vcodec:h264,br,size",
            "-f", "bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/best[height<=2160]/best",
            "--download-sections", section,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-warnings",
            "--quiet",
            "-o", output_path,
            url,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)

            if proc.returncode == 0 and os.path.exists(output_path):
                return output_path
            else:
                err = stderr.decode(errors="replace")[:200] if stderr else "unknown"
                logger.warning(f"video_gen: yt-dlp failed scene {scene_id}: {err}")

        except asyncio.TimeoutError:
            logger.warning(f"video_gen: yt-dlp timeout scene {scene_id}")
        except FileNotFoundError:
            logger.error("video_gen: yt-dlp not found in PATH")
        except Exception as exc:
            logger.warning(f"video_gen: download error scene {scene_id}: {exc}")

        return None

    async def _prepare_scene_clip(self, entry: dict, clips_dir: str) -> str:
        """Prepare a single scene clip: trim footage to match TTS duration, scale to 9:16."""
        scene_id = entry["scene_id"]
        duration = entry["duration"]
        footage_path = entry.get("footage_path")

        clip_path = os.path.join(clips_dir, f"clip_{scene_id:03d}.mp4")

        if footage_path and os.path.exists(footage_path):
            # Trim and scale footage to 1080x1920 (9:16), seeking to agentic moment
            start_ts = float(entry.get("start_timestamp") or 0.0)
            from src.infrastructure.gpu_encoder import get_video_encoder_args
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(max(0.0, start_ts)),
                "-stream_loop", "-1",
                "-i", footage_path,
                "-t", str(duration),
                "-vf", (
                    (
                        "scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp,"
                        "crop=1920:1080,"
                    ) if getattr(job, "aspect_ratio", "9:16") == "16:9" else (
                        "scale=1080:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp,"
                        "crop=1080:1080,"
                    ) if getattr(job, "aspect_ratio", "9:16") == "1:1" else (
                        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp,"
                        "crop=1080:1920,"
                    )
                ) + (
                    "unsharp=lx=3:ly=3:la=0.4:cx=3:cy=3:ca=0.2,"
                    "setsar=1"
                ),

                *get_video_encoder_args("medium"),
                "-an",  # No audio from footage
                "-r", "30",
                "-pix_fmt", "yuv420p",
                clip_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if os.path.exists(clip_path) and os.path.getsize(clip_path) > 0:
                logger.debug(f"video_gen: scene {scene_id} clip from footage OK")
                return clip_path
            else:
                err = stderr.decode(errors="replace")[:200] if stderr else ""
                logger.warning(f"video_gen: scene {scene_id} footage encode failed: {err}")
        else:
            logger.info(f"video_gen: scene {scene_id} no footage, using black frame")

        # Fallback: generate black frame with matching duration
        from src.infrastructure.gpu_encoder import get_video_encoder_args
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s=1080x1920:d={duration}:r=30",
            *get_video_encoder_args("medium"),
            "-pix_fmt", "yuv420p",
            clip_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)

        if not os.path.exists(clip_path):
            logger.error(f"video_gen: scene {scene_id} even black frame failed!")

        return clip_path

    async def _concat_clips(self, clips: list[str], output_path: str, transition: Optional[str] = "dissolve") -> None:
        """Concatenate video clips using FFmpeg concat filter."""
        # Filter only existing clips
        valid_clips = [c for c in clips if c and os.path.exists(c)]

        if not valid_clips:
            # No clips at all — generate a short black video as placeholder
            logger.warning("video_gen: no valid clips to concat, generating placeholder")
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=black:s=1080x1920:d=10:r=30",
                "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                "-pix_fmt", "yuv420p",
                output_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            return

        if len(valid_clips) == 1:
            # Single clip — just copy it
            shutil.copy2(valid_clips[0], output_path)
            return

        # Use filter_complex concat (tolerant of minor codec/param differences)
        # Unlike concat demuxer, this re-encodes and normalizes all inputs
        inputs = []
        for clip in valid_clips:
            inputs.extend(["-i", clip])

        # Build filter: [0:v][1:v][2:v]...concat=n=N:v=1:a=0[outv]
        filter_parts = "".join(f"[{i}:v]" for i in range(len(valid_clips)))
        filter_str = f"{filter_parts}concat=n={len(valid_clips)}:v=1:a=0[outv]"

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[outv]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if not os.path.exists(output_path):
            err_msg = stderr.decode(errors="replace")[:500] if stderr else "unknown"
            logger.error(f"video_gen: filter_complex concat failed: {err_msg}")
            # Fallback: use first valid clip
            shutil.copy2(valid_clips[0], output_path)

    async def _concat_audio(self, timeline: list[dict], output_path: str) -> None:
        """Concatenate narration while preserving the duration of every scene."""
        entries = [
            entry for entry in timeline
            if float(entry.get("duration") or 0) > 0
        ]
        if not entries:
            raise RuntimeError("Cannot assemble narration without timeline entries")

        inputs: list[str] = []
        filters: list[str] = []
        labels: list[str] = []

        for index, entry in enumerate(entries):
            duration = max(0.1, float(entry["duration"]))
            audio_path = entry.get("tts_path") or entry.get("audio_path")
            if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                inputs.extend(["-i", audio_path])
            else:
                inputs.extend([
                    "-f", "lavfi",
                    "-t", f"{duration:.3f}",
                    "-i", "anullsrc=r=48000:cl=stereo",
                ])
            label = f"a{index}"
            filters.append(
                f"[{index}:a]aresample=48000,apad,atrim=duration={duration:.3f}[{label}]"
            )
            labels.append(f"[{label}]")

        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[aout]")
        cmd = [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[aout]",
            "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000",
            output_path,
        ]
        succeeded, error = await self._run_ffmpeg(cmd, timeout=180)
        if not succeeded or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Narration assembly failed: {error}")

    def _generate_srt(self, timeline: list[dict], srt_path: str) -> None:
        """Generate SRT subtitle file from timeline narration."""
        lines = []
        for i, entry in enumerate(timeline, 1):
            narration = entry.get("narration", "").strip()
            if not narration:
                continue

            start = entry["start_time"]
            end = start + entry["duration"]

            lines.append(str(i))
            lines.append(f"{self._format_srt_time(start)} --> {self._format_srt_time(end)}")
            lines.append(narration)
            lines.append("")

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    async def _final_composite(
        self,
        video_path: str,
        audio_path: str,
        subtitle_path: Optional[str],
        output_path: str,
        job: VideoGenJob,
        work_dir: str,
    ) -> bool:
        """Render a delivery-ready MP4 with caption, narration, and optional BGM.

        Returns True if captions were successfully burned into output_path during this pass.
        """
        if not os.path.exists(video_path):
            logger.warning("video_gen: concat video missing, generating placeholder")
            audio_duration = "10"
            if os.path.exists(audio_path):
                audio_duration = f"{await self._media_duration(audio_path, fallback=10):.3f}"

            placeholder_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s=1080x1920:d={audio_duration}:r=30",
                "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                "-pix_fmt", "yuv420p",
                video_path,
            ]
            succeeded, error = await self._run_ffmpeg(placeholder_cmd, timeout=60)
            if not succeeded or not os.path.exists(video_path):
                logger.error("video_gen: placeholder render failed: %s", error)
                raise RuntimeError("Concat video missing and placeholder generation failed")

        subtitle_burned = False
        rendered, error = await self._render_final_pass(
            video_path=video_path,
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            include_bgm=job.include_bgm,
            bgm_volume=job.bgm_volume,
        )
        if rendered and subtitle_path:
            subtitle_burned = True
        elif not rendered and subtitle_path:
            logger.warning("video_gen: caption render pass failed (%s), retrying base composite...", error)
            rendered, error = await self._render_final_pass(
                video_path=video_path,
                audio_path=audio_path,
                subtitle_path=None,
                output_path=output_path,
                include_bgm=job.include_bgm,
                bgm_volume=job.bgm_volume,
            )
            subtitle_burned = False

        if not rendered:
            logger.warning("video_gen: enhanced composite failed, using fallback: %s", error)
            rendered = await self._fallback_render(video_path, audio_path, output_path)
            subtitle_burned = False

        if not rendered or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Final video render failed: {error}")

        return subtitle_burned

    async def _fallback_render(
        self, video_path: str, audio_path: str, output_path: str
    ) -> bool:
        """Last-resort video and narration render without captions or BGM."""
        rendered, _ = await self._render_final_pass(
            video_path=video_path,
            audio_path=audio_path,
            subtitle_path=None,
            output_path=output_path,
            include_bgm=False,
            bgm_volume=0,
        )
        return rendered

    async def _render_final_pass(
        self,
        video_path: str,
        audio_path: str,
        subtitle_path: Optional[str],
        output_path: str,
        include_bgm: bool,
        bgm_volume: float,
    ) -> tuple[bool, str]:
        video_duration = await self._media_duration(video_path, fallback=10)
        inputs = ["-i", video_path]
        filters: list[str] = []
        narration_input: Optional[int] = None
        bgm_input: Optional[int] = None

        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            narration_input = 1
            inputs.extend(["-i", audio_path])

        if include_bgm:
            bgm_path = self._find_bgm()
            if bgm_path:
                bgm_input = len(inputs) // 2
                inputs.extend(["-stream_loop", "-1", "-i", bgm_path])

        if narration_input is None and bgm_input is None:
            silence_input = len(inputs) // 2
            inputs.extend([
                "-f", "lavfi",
                "-t", f"{video_duration:.3f}",
                "-i", "anullsrc=r=48000:cl=stereo",
            ])
            filters.append(
                f"[{silence_input}:a]aresample=48000,atrim=duration={video_duration:.3f}[aout]"
            )
        elif narration_input is not None and bgm_input is not None:
            filters.extend([
                f"[{narration_input}:a]aresample=48000,apad,atrim=duration={video_duration:.3f}[narr]",
                f"[{bgm_input}:a]aresample=48000,volume={bgm_volume:.3f},atrim=duration={video_duration:.3f}[bgm]",
                "[narr][bgm]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.97[aout]",
            ])
        elif narration_input is not None:
            filters.append(
                f"[{narration_input}:a]aresample=48000,apad,atrim=duration={video_duration:.3f}[aout]"
            )
        else:
            filters.append(
                f"[{bgm_input}:a]aresample=48000,volume={bgm_volume:.3f},atrim=duration={video_duration:.3f}[aout]"
            )

        if subtitle_path and os.path.exists(subtitle_path) and os.path.getsize(subtitle_path) > 0:
            filters.insert(0, f"[0:v]{ffmpeg_subtitle_filter(subtitle_path)}[vout]")
        else:
            filters.insert(0, "[0:v]null[vout]")

        cmd = [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-profile:v", "high", "-level:v", "4.1",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-r", "30", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        return await self._run_ffmpeg(cmd, timeout=300)

    async def _media_duration(self, path: str, fallback: float = 10.0) -> float:
        if not path or not os.path.exists(path):
            return fallback
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0:
                duration = float(stdout.decode().strip())
                if duration > 0:
                    return duration
        except (OSError, ValueError, asyncio.TimeoutError):
            pass
        return fallback

    async def _run_ffmpeg(self, cmd: list[str], timeout: int) -> tuple[bool, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return False, "FFmpeg is not installed or unavailable on PATH"

        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return False, f"FFmpeg timed out after {timeout}s"

        if proc.returncode == 0:
            return True, ""
        return False, stderr.decode(errors="replace")[-800:] if stderr else "Unknown FFmpeg error"

    def _find_bgm(self) -> Optional[str]:
        """Find a background music file from the BGM directory."""
        bgm_dir = settings.VIDEO_GEN_BGM_DIR
        if not os.path.isdir(bgm_dir):
            return None

        # Pick first available MP3/WAV
        import random
        bgm_files = [
            os.path.join(bgm_dir, f)
            for f in os.listdir(bgm_dir)
            if f.endswith((".mp3", ".wav", ".m4a"))
        ]

        if not bgm_files:
            return None

        return random.choice(bgm_files)

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Format seconds to SRT timestamp (HH:MM:SS,mmm)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# Singleton instance
_video_generator: Optional[VideoGenerator] = None


def get_video_generator() -> VideoGenerator:
    """Get or create the VideoGenerator singleton."""
    global _video_generator
    if _video_generator is None:
        _video_generator = VideoGenerator()
    return _video_generator
