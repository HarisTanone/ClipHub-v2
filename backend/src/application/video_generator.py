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
    voice: str = ""
    speed: float = 1.0
    instructions: str = ""
    num_scenes: int = 0
    subtitles_enabled: bool = True
    subtitle_style: dict[str, Any] = field(default_factory=dict)
    include_bgm: bool = True
    bgm_volume: float = field(default_factory=lambda: settings.VIDEO_GEN_BGM_VOLUME)
    title: Optional[str] = None
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
    """

    def __init__(self, output_dir: Optional[str] = None):
        self._jobs: dict[str, VideoGenJob] = {}
        self._output_dir = output_dir or settings.VIDEO_GEN_OUTPUT_DIR
        os.makedirs(self._output_dir, exist_ok=True)

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

            cur.execute("""
                INSERT INTO video_generator_jobs (
                    job_id, user_id, topic, status, progress, target_duration,
                    voice, speed, instructions, num_scenes, subtitles_enabled,
                    subtitle_style_json, include_bgm, bgm_volume, title,
                    story_json, scenes_json, timeline_json, output_path, error,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    include_bgm=excluded.include_bgm,
                    bgm_volume=excluded.bgm_volume,
                    title=excluded.title,
                    story_json=excluded.story_json,
                    scenes_json=excluded.scenes_json,
                    timeline_json=excluded.timeline_json,
                    output_path=excluded.output_path,
                    error=excluded.error,
                    completed_at=excluded.completed_at
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

        return VideoGenJob(
            job_id=row["job_id"],
            topic=row["topic"],
            status=status_val,
            progress=int(row["progress"] or 0),
            target_duration=int(row["target_duration"] or 65),
            voice=row["voice"] or "",
            speed=float(row["speed"] or 1.0),
            instructions=row["instructions"] or "",
            num_scenes=int(row["num_scenes"]) if "num_scenes" in row.keys() and row["num_scenes"] is not None else 0,
            subtitles_enabled=bool(row["subtitles_enabled"]) if "subtitles_enabled" in row.keys() and row["subtitles_enabled"] is not None else True,
            subtitle_style=subtitle_style,
            include_bgm=bool(row["include_bgm"]) if "include_bgm" in row.keys() and row["include_bgm"] is not None else True,
            bgm_volume=float(row["bgm_volume"]) if "bgm_volume" in row.keys() and row["bgm_volume"] is not None else settings.VIDEO_GEN_BGM_VOLUME,
            title=row["title"],
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
        voice: str = "",
        speed: float = 1.0,
        instructions: str = "",
        num_scenes: int = 0,
        subtitles_enabled: bool = True,
        subtitle_style: Optional[dict[str, Any]] = None,
        include_bgm: bool = True,
        bgm_volume: Optional[float] = None,
        user_id: Optional[int] = None,
    ) -> VideoGenJob:
        """Create a new video generation job."""
        job_id = uuid4().hex[:12]
        job = VideoGenJob(
            job_id=job_id,
            topic=topic,
            target_duration=target_duration or settings.VIDEO_GEN_TARGET_DURATION,
            voice=voice or settings.DEEPGRAM_TTS_VOICE,
            speed=speed or settings.DEEPGRAM_TTS_SPEED,
            instructions=instructions,
            num_scenes=num_scenes,
            subtitles_enabled=subtitles_enabled,
            subtitle_style=normalize_subtitle_style(subtitle_style),
            include_bgm=include_bgm,
            bgm_volume=(
                settings.VIDEO_GEN_BGM_VOLUME
                if bgm_volume is None
                else max(0.0, min(0.5, bgm_volume))
            ),
            user_id=user_id,
        )
        self._jobs[job_id] = job
        self._persist_job(job)
        return job

    def get_job(self, job_id: str) -> Optional[VideoGenJob]:
        if job_id in self._jobs:
            return self._jobs[job_id]
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
        return None

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
                # Keep in memory cache or merge with ongoing in-memory status
                if j.job_id in self._jobs:
                    mem_job = self._jobs[j.job_id]
                    if mem_job.status not in (VideoGenStatus.COMPLETED, VideoGenStatus.FAILED):
                        db_jobs.append(mem_job)
                        continue
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
            scenes = await self._step_search_footage(story, work_dir)
            job.scenes_with_footage = scenes
            job.progress = 35
            self._persist_job(job)

            # Step 3: Download footage
            job.status = VideoGenStatus.DOWNLOADING
            job.progress = 40
            self._persist_job(job)
            scenes = await self._step_download_footage(scenes, work_dir)
            job.scenes_with_footage = scenes
            job.progress = 55
            self._persist_job(job)

            # Step 4: Generate TTS
            job.status = VideoGenStatus.GENERATING_TTS
            job.progress = 60
            self._persist_job(job)
            scenes = await self._step_generate_tts(scenes, job, work_dir)
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
            scenes = await self._step_search_footage(story, work_dir)

            # Pre-select top candidate for each scene
            for scene in scenes:
                candidates = scene.get("footage_candidates", [])
                if candidates and not scene.get("selected_footage"):
                    best = self._pick_best_candidate(candidates, scene) or candidates[0]
                    scene["selected_footage"] = best

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

        from src.infrastructure.youtube_search import YouTubeSearch

        yt = YouTubeSearch()
        candidates = await yt.search_for_single_scene(target_scene, custom_query=query, results_per_query=6)
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
            # Step 3: Download chosen footage
            job.status = VideoGenStatus.DOWNLOADING
            job.progress = 20
            self._persist_job(job)
            scenes = await self._step_download_footage(job.scenes_with_footage or [], work_dir)
            job.scenes_with_footage = scenes
            job.progress = 50
            self._persist_job(job)

            # Step 4: Generate TTS
            job.status = VideoGenStatus.GENERATING_TTS
            job.progress = 60
            self._persist_job(job)
            scenes = await self._step_generate_tts(scenes, job, work_dir)
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
        """Step 1: AI generates structured story from topic."""
        from src.infrastructure.story_agent import StoryAgent, StoryGenerationError

        agent = StoryAgent()

        story = await agent.generate_story(
            topic=job.topic,
            target_duration=job.target_duration,
            num_scenes=job.num_scenes,
            instructions=job.instructions,
        )

        logger.info(
            f"video_gen [{job.job_id}]: story generated — "
            f"'{story.get('title', '')}', {len(story.get('scenes', []))} scenes"
        )
        return story

    async def _step_search_footage(self, story: dict, work_dir: str) -> list[dict]:
        """Step 2: Search YouTube and Pexels for footage per scene."""
        from src.infrastructure.youtube_search import YouTubeSearch

        yt = YouTubeSearch()
        scenes = story.get("scenes", [])

        scenes = await yt.search_for_scenes(
            scenes=scenes,
            results_per_scene=5,
            shorts_only=False,
        )

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
        """Step 3: Download chosen/best footage candidate for each scene."""
        footage_dir = os.path.join(work_dir, "footage")
        os.makedirs(footage_dir, exist_ok=True)

        for i, scene in enumerate(scenes):
            best = scene.get("selected_footage") or scene.get("footage_source")
            if not best:
                candidates = scene.get("footage_candidates", [])
                if candidates:
                    best = self._pick_best_candidate(candidates, scene)

            if not best:
                scene["footage_path"] = None
                continue

            duration_needed = scene.get("duration_estimate", 10) + 3  # buffer
            url = best.get("url") or ""
            platform = best.get("platform", "youtube")

            path = None
            if platform == "pexels" or (url.startswith("http") and ".mp4" in url):
                from src.infrastructure.footage_downloader import FootageDownloader
                from src.domain.entities import VideoCandidate
                candidate_obj = VideoCandidate(
                    id=best.get("video_id", f"scene_{i}"),
                    platform="pexels",
                    embed_url=url,
                    thumbnail_url=best.get("thumbnail_url", ""),
                    preview_url=best.get("thumbnail_url", ""),
                    source_url=url,
                    title=best.get("title", ""),
                )
                dl = FootageDownloader(output_dir=footage_dir)
                path = await dl.download(candidate_obj, duration_needed)
            else:
                path = await self._download_youtube_segment(
                    url=url,
                    duration_needed=duration_needed,
                    output_dir=footage_dir,
                    scene_id=scene.get("id", i),
                )

            scene["footage_path"] = path
            scene["footage_source"] = best

            if path:
                logger.info(
                    f"video_gen: scene {scene.get('id', i)} footage downloaded "
                    f"from '{best.get('title', '')[:40]}'"
                )

            await asyncio.sleep(0.3)

        downloaded = sum(1 for s in scenes if s.get("footage_path"))
        logger.info(f"video_gen: downloaded footage for {downloaded}/{len(scenes)} scenes")

        return scenes

    async def _step_generate_tts(
        self, scenes: list[dict], job: VideoGenJob, work_dir: str
    ) -> list[dict]:
        """Step 4: Generate TTS narration for each scene."""
        from src.infrastructure.deepgram_tts import DeepgramTTS

        tts_dir = os.path.join(work_dir, "tts")
        os.makedirs(tts_dir, exist_ok=True)

        tts = DeepgramTTS(output_dir=tts_dir)

        scenes = await tts.synthesize_scenes(
            scenes=scenes,
            voice=job.voice,
            speed=job.speed,
        )

        # Log TTS results
        total_tts_duration = sum(s.get("tts_duration", 0) for s in scenes)
        tts_count = sum(1 for s in scenes if s.get("tts_path"))
        logger.info(
            f"video_gen [{job.job_id}]: TTS generated for {tts_count}/{len(scenes)} "
            f"scenes, total narration: {total_tts_duration:.1f}s"
        )

        if any(scene.get("narration", "").strip() for scene in scenes) and not tts_count:
            raise RuntimeError(
                "Narration generation failed for every scene. Check the Deepgram API configuration."
            )

        return scenes

    def _step_assemble_timeline(self, scenes: list[dict]) -> list[dict]:
        """Step 5: Build render timeline — sync footage to TTS duration.

        Each timeline entry has:
        - scene_id
        - footage_path (video file)
        - tts_path (audio narration)
        - start_time (in final video)
        - duration (from TTS, or estimated)
        - narration (for subtitle generation)
        """
        timeline = []
        current_time = 0.0

        for scene in scenes:
            # Duration comes from TTS (authoritative) or estimate
            duration = scene.get("tts_duration", 0)
            if duration <= 0:
                duration = scene.get("duration_estimate", 7)

            entry = {
                "scene_id": scene.get("id", 0),
                "footage_path": scene.get("footage_path"),
                "tts_path": scene.get("tts_path"),
                "start_time": current_time,
                "duration": duration,
                "narration": scene.get("narration", ""),
                "transition": scene.get("transition", "cut"),
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
        """Step 6: FFmpeg render — combine footage + TTS + subtitles.

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
        await self._concat_clips(scene_clips, concat_path)

        # Step 6c: Merge TTS audio with timed silence for missing scene narration.
        merged_audio_path = os.path.join(work_dir, "narration_full.mp3")
        await self._concat_audio(timeline, merged_audio_path)

        # Step 6d: Generate styled ASS captions from the narration timeline.
        subtitle_path = None
        if job.subtitles_enabled:
            candidate_path = os.path.join(work_dir, "captions.ass")
            if write_ass_subtitles(timeline, candidate_path, job.subtitle_style):
                subtitle_path = candidate_path

        # Step 6e: Final composite — video + narration + subtitle + optional BGM
        await self._final_composite(
            video_path=concat_path,
            audio_path=merged_audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            job=job,
            work_dir=work_dir,
        )

        if not os.path.exists(output_path):
            raise RuntimeError("Final video render failed — output file not created")

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"video_gen [{job.job_id}]: final video {size_mb:.1f}MB → {output_path}")

        return output_path

    # ─── Helper Methods ────────────────────────────────────────────────────────

    def _pick_best_candidate(self, candidates: list[dict], scene: dict) -> Optional[dict]:
        """Score and pick the best footage candidate for a scene.

        Scoring factors:
        - Title/query relevance to visual description (highest weight)
        - View count (popularity signal)
        - Duration (prefer videos with enough content)
        """
        if not candidates:
            return None

        target_duration = scene.get("duration_estimate", 7)

        # Build search terms from visual description + queries for matching
        search_terms = set()
        visual = scene.get("visual", "")
        for word in visual.lower().split():
            if len(word) > 3:  # Skip short words
                search_terms.add(word)
        for q in scene.get("search_queries", []):
            for word in q.lower().split():
                if len(word) > 3:
                    search_terms.add(word)

        scored = []
        for c in candidates:
            score = 0.0

            # Title keyword overlap (highest weight)
            title_words = set(w.lower() for w in c.get("title", "").split() if len(w) > 3)
            overlap = len(search_terms & title_words)
            score += overlap * 2.0  # 2 points per matching word

            # View count bonus (log scale)
            views = c.get("view_count", 0)
            if views > 1000000:
                score += 2.0
            elif views > 100000:
                score += 1.5
            elif views > 10000:
                score += 1.0
            elif views > 1000:
                score += 0.5

            # Duration: prefer videos longer than needed (more to work with)
            dur = c.get("duration_seconds", 0)
            if dur >= target_duration:
                score += 1.5
            elif dur >= target_duration * 0.7:
                score += 0.8

            # Bonus for footage/cinematic/drone in title (stock-like content)
            title_lower = c.get("title", "").lower()
            stock_keywords = ["footage", "cinematic", "drone", "4k", "stock", "timelapse", "b-roll", "broll"]
            for kw in stock_keywords:
                if kw in title_lower:
                    score += 1.0
                    break

            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    async def _download_youtube_segment(
        self, url: str, duration_needed: float, output_dir: str, scene_id: int
    ) -> Optional[str]:
        """Download a YouTube video segment via yt-dlp."""
        filename = f"footage_scene_{scene_id}_{uuid4().hex[:6]}.mp4"
        output_path = os.path.join(output_dir, filename)

        # Download first N seconds (enough for our scene)
        section = f"*0-{int(duration_needed) + 5}"

        cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=1080]/best[height<=1080]/best",
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
            # Trim and scale footage to 1080x1920 (9:16)
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1",
                "-i", footage_path,
                "-t", str(duration),
                "-vf", (
                    "scale=1080:1920:force_original_aspect_ratio=increase,"
                    "crop=1080:1920,"
                    "setsar=1"
                ),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
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
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s=1080x1920:d={duration}:r=30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
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

    async def _concat_clips(self, clips: list[str], output_path: str) -> None:
        """Concatenate video clips using FFmpeg concat demuxer."""
        # Filter only existing clips
        valid_clips = [c for c in clips if c and os.path.exists(c)]

        if not valid_clips:
            # No clips at all — generate a short black video as placeholder
            logger.warning("video_gen: no valid clips to concat, generating placeholder")
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=black:s=1080x1920:d=10:r=30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
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
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
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
            audio_path = entry.get("tts_path")
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
    ) -> None:
        """Render a delivery-ready MP4 with caption, narration, and optional BGM."""
        if not os.path.exists(video_path):
            logger.warning("video_gen: concat video missing, generating placeholder")
            audio_duration = "10"
            if os.path.exists(audio_path):
                audio_duration = f"{await self._media_duration(audio_path, fallback=10):.3f}"

            placeholder_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s=1080x1920:d={audio_duration}:r=30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                video_path,
            ]
            succeeded, error = await self._run_ffmpeg(placeholder_cmd, timeout=60)
            if not succeeded or not os.path.exists(video_path):
                logger.error("video_gen: placeholder render failed: %s", error)
                raise RuntimeError("Concat video missing and placeholder generation failed")

        rendered, error = await self._render_final_pass(
            video_path=video_path,
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            include_bgm=job.include_bgm,
            bgm_volume=job.bgm_volume,
        )
        if not rendered and subtitle_path:
            logger.warning("video_gen: caption render failed, retrying without captions: %s", error)
            rendered, error = await self._render_final_pass(
                video_path=video_path,
                audio_path=audio_path,
                subtitle_path=None,
                output_path=output_path,
                include_bgm=job.include_bgm,
                bgm_volume=job.bgm_volume,
            )
        if not rendered:
            logger.warning("video_gen: enhanced composite failed, using fallback: %s", error)
            rendered = await self._fallback_render(video_path, audio_path, output_path)
        if not rendered or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Final video render failed: {error}")

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
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-profile:v", "high", "-level:v", "4.1",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-r", "30", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        return await self._run_ffmpeg(cmd, timeout=300)

    async def _media_duration(self, path: str, fallback: float) -> float:
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
