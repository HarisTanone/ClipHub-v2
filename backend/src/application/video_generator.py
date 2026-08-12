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
from typing import Optional
from uuid import uuid4

from src.config import settings

logger = logging.getLogger(__name__)


class VideoGenStatus(str, Enum):
    QUEUED = "queued"
    GENERATING_STORY = "generating_story"
    SEARCHING_FOOTAGE = "searching_footage"
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

    def __init__(self):
        self._jobs: dict[str, VideoGenJob] = {}
        self._output_dir = settings.VIDEO_GEN_OUTPUT_DIR
        os.makedirs(self._output_dir, exist_ok=True)

    def create_job(
        self,
        topic: str,
        target_duration: int = 0,
        voice: str = "",
        speed: float = 1.0,
        instructions: str = "",
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
            user_id=user_id,
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[VideoGenJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, user_id: Optional[int] = None) -> list[VideoGenJob]:
        jobs = list(self._jobs.values())
        if user_id is not None:
            jobs = [j for j in jobs if j.user_id == user_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def run_pipeline(self, job_id: str) -> VideoGenJob:
        """Execute the full video generation pipeline.

        This is the main entry point — runs all steps sequentially.
        Should be called as a background task.
        """
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        work_dir = os.path.join(self._output_dir, job_id)
        os.makedirs(work_dir, exist_ok=True)

        try:
            # Step 1: Generate story
            job.status = VideoGenStatus.GENERATING_STORY
            job.progress = 5
            story = await self._step_generate_story(job)
            job.story = story
            job.progress = 15

            # Step 2: Search footage
            job.status = VideoGenStatus.SEARCHING_FOOTAGE
            job.progress = 20
            scenes = await self._step_search_footage(story, work_dir)
            job.scenes_with_footage = scenes
            job.progress = 35

            # Step 3: Download footage
            job.status = VideoGenStatus.DOWNLOADING
            job.progress = 40
            scenes = await self._step_download_footage(scenes, work_dir)
            job.scenes_with_footage = scenes
            job.progress = 55

            # Step 4: Generate TTS
            job.status = VideoGenStatus.GENERATING_TTS
            job.progress = 60
            scenes = await self._step_generate_tts(scenes, job, work_dir)
            job.scenes_with_footage = scenes
            job.progress = 70

            # Step 5: Assemble timeline
            job.status = VideoGenStatus.ASSEMBLING
            job.progress = 75
            timeline = self._step_assemble_timeline(scenes)
            job.timeline = timeline
            job.progress = 80

            # Step 6: Render final video
            job.status = VideoGenStatus.RENDERING
            job.progress = 85
            output_path = await self._step_render_video(timeline, job, work_dir)
            job.output_path = output_path
            job.progress = 100

            # Done
            job.status = VideoGenStatus.COMPLETED
            job.completed_at = time.time()

            total_time = job.completed_at - job.created_at
            logger.info(
                f"video_gen: job {job_id} completed in {total_time:.1f}s → {output_path}"
            )

        except Exception as exc:
            job.status = VideoGenStatus.FAILED
            job.error = str(exc)
            job.completed_at = time.time()
            logger.error(f"video_gen: job {job_id} failed: {exc}", exc_info=True)

        return job

    # ─── Pipeline Steps ────────────────────────────────────────────────────────

    async def _step_generate_story(self, job: VideoGenJob) -> dict:
        """Step 1: AI generates structured story from topic."""
        from src.infrastructure.story_agent import StoryAgent, StoryGenerationError

        agent = StoryAgent()

        story = await agent.generate_story(
            topic=job.topic,
            target_duration=job.target_duration,
            instructions=job.instructions,
        )

        logger.info(
            f"video_gen [{job.job_id}]: story generated — "
            f"'{story.get('title', '')}', {len(story.get('scenes', []))} scenes"
        )
        return story

    async def _step_search_footage(self, story: dict, work_dir: str) -> list[dict]:
        """Step 2: Search YouTube for footage per scene."""
        from src.infrastructure.youtube_search import YouTubeSearch

        yt = YouTubeSearch()
        scenes = story.get("scenes", [])

        scenes = await yt.search_for_scenes(
            scenes=scenes,
            results_per_scene=5,
            shorts_only=False,  # Allow both shorts and regular videos
        )

        # Log results
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
        """Step 3: Download best footage candidate for each scene."""
        footage_dir = os.path.join(work_dir, "footage")
        os.makedirs(footage_dir, exist_ok=True)

        for i, scene in enumerate(scenes):
            candidates = scene.get("footage_candidates", [])
            if not candidates:
                scene["footage_path"] = None
                continue

            # Pick best candidate: prefer higher views, reasonable duration
            best = self._pick_best_candidate(candidates, scene)
            if not best:
                scene["footage_path"] = None
                continue

            # Download via yt-dlp
            duration_needed = scene.get("duration_estimate", 10) + 3  # buffer
            path = await self._download_youtube_segment(
                url=best["url"],
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

            # Rate limit
            await asyncio.sleep(0.5)

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

        # Step 6c: Merge all TTS audio into one track
        tts_paths = [e["tts_path"] for e in timeline if e.get("tts_path")]
        merged_audio_path = os.path.join(work_dir, "narration_full.mp3")
        await self._concat_audio(tts_paths, merged_audio_path)

        # Step 6d: Generate subtitle file from timeline
        srt_path = os.path.join(work_dir, "subtitles.srt")
        self._generate_srt(timeline, srt_path)

        # Step 6e: Final composite — video + narration + subtitle + optional BGM
        await self._final_composite(
            video_path=concat_path,
            audio_path=merged_audio_path,
            srt_path=srt_path,
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

    async def _concat_audio(self, audio_paths: list[str], output_path: str) -> None:
        """Concatenate audio files using FFmpeg."""
        if not audio_paths:
            # Generate silence
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", "5",
                "-c:a", "libmp3lame",
                output_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            return

        valid_paths = [p for p in audio_paths if p and os.path.exists(p)]
        if not valid_paths:
            return

        if len(valid_paths) == 1:
            shutil.copy2(valid_paths[0], output_path)
            return

        # Concat with filter_complex
        inputs = []
        for p in valid_paths:
            inputs.extend(["-i", p])

        filter_str = "".join(f"[{i}:a]" for i in range(len(valid_paths)))
        filter_str += f"concat=n={len(valid_paths)}:v=0:a=1[out]"

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            output_path,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=120)

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
        srt_path: str,
        output_path: str,
        job: VideoGenJob,
        work_dir: str,
    ) -> None:
        """Final render: video + narration + subtitles + optional BGM."""
        if not os.path.exists(video_path):
            logger.warning("video_gen: concat video missing, generating placeholder")
            # Generate placeholder video matching audio duration
            audio_duration = "10"
            if os.path.exists(audio_path):
                # Get audio duration via ffprobe
                probe_cmd = [
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *probe_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                try:
                    audio_duration = str(float(stdout.decode().strip()))
                except (ValueError, AttributeError):
                    pass

            placeholder_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s=1080x1920:d={audio_duration}:r=30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                video_path,
            ]
            proc = await asyncio.create_subprocess_exec(
                *placeholder_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)

            if not os.path.exists(video_path):
                raise RuntimeError("Concat video missing and placeholder generation failed")

        # Build FFmpeg command
        inputs = ["-i", video_path]
        filter_parts = []

        # Add narration audio
        has_audio = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
        if has_audio:
            inputs.extend(["-i", audio_path])

        # Check for BGM
        bgm_path = self._find_bgm()
        has_bgm = bgm_path is not None
        if has_bgm:
            inputs.extend(["-i", bgm_path])

        # Build audio mix
        if has_audio and has_bgm:
            # Mix narration (full volume) + BGM (low volume)
            bgm_vol = settings.VIDEO_GEN_BGM_VOLUME
            audio_filter = (
                f"[1:a]volume=1.0[narr];"
                f"[2:a]volume={bgm_vol}[bgm];"
                f"[narr][bgm]amix=inputs=2:duration=first[aout]"
            )
            filter_parts.append(audio_filter)
            audio_map = ["-map", "0:v", "-map", "[aout]"]
        elif has_audio:
            audio_map = ["-map", "0:v", "-map", "1:a"]
        else:
            audio_map = ["-map", "0:v"]

        # Subtitle filter (burn-in) — configurable via settings
        sub_filter = ""
        if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            # Escape path for FFmpeg
            escaped_srt = srt_path.replace("'", "'\\''").replace(":", "\\:")
            # Build ASS force_style from config
            style_parts = [
                f"FontSize={settings.VIDEO_GEN_SUB_FONT_SIZE}",
                f"FontName={settings.VIDEO_GEN_SUB_FONT_NAME}",
                f"PrimaryColour={settings.VIDEO_GEN_SUB_PRIMARY_COLOR}",
                f"OutlineColour={settings.VIDEO_GEN_SUB_OUTLINE_COLOR}",
                f"BackColour={settings.VIDEO_GEN_SUB_BACK_COLOR}",
                f"Outline={settings.VIDEO_GEN_SUB_OUTLINE}",
                f"Shadow={settings.VIDEO_GEN_SUB_SHADOW}",
                f"MarginV={settings.VIDEO_GEN_SUB_MARGIN_V}",
                f"MarginL={settings.VIDEO_GEN_SUB_MARGIN_L}",
                f"MarginR={settings.VIDEO_GEN_SUB_MARGIN_R}",
                f"Alignment={settings.VIDEO_GEN_SUB_ALIGNMENT}",
                f"Bold={settings.VIDEO_GEN_SUB_BOLD}",
                f"BorderStyle={settings.VIDEO_GEN_SUB_BORDER_STYLE}",
            ]
            force_style = ",".join(style_parts)
            sub_filter = f"subtitles='{escaped_srt}':force_style='{force_style}'"

        # Build full command
        cmd = ["ffmpeg", "-y", *inputs]

        if filter_parts and sub_filter:
            # Complex filter with audio mix + subtitles on video
            vf = sub_filter
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-vf", vf])
            cmd.extend(audio_map)
        elif filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(audio_map)
        elif sub_filter:
            cmd.extend(["-vf", sub_filter])
            cmd.extend(audio_map)
        else:
            cmd.extend(audio_map)

        # Output settings
        cmd.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            "-shortest",
            output_path,
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[-500:] if stderr else "unknown"
            logger.error(f"video_gen: final render failed: {err}")
            # Retry without subtitles and BGM (simpler)
            await self._fallback_render(video_path, audio_path, output_path)

    async def _fallback_render(
        self, video_path: str, audio_path: str, output_path: str
    ) -> None:
        """Simplified fallback render: video + audio only, no subs/BGM."""
        cmd = ["ffmpeg", "-y", "-i", video_path]

        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            cmd.extend(["-i", audio_path, "-map", "0:v", "-map", "1:a"])
        else:
            cmd.extend(["-map", "0:v"])

        cmd.extend([
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            output_path,
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=180)

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
