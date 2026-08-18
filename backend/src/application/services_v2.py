"""V2PipelineService — Pipeline orchestrator for transcript-based clipping.

Uses YouTube Transcript API/9router Groq Whisper/local fallback + 9router-backed
dynamic chunking and router-first word-level transcription. NO Gemini dependency.

Pipeline Steps (V2):
  1. Validate              — yt-dlp validate URL, extract duration
  2. Download              — Download full video
  3. V2 Transcript         — YouTube API → 9router Groq → local Whisper
  4. V2 Highlight Analysis — Dynamic Chunking → 9router LLM (double-pass)
  5. Prepare Clips         — Time padding, overlap detection
  5.5 Silero VAD           — Snap start/end to silence (no mid-speech cuts)
  6. Aspect Ratio Router   — Set pipeline flags
  7. Trim Clips            — FFmpeg re-encode, A/V zero-based sync
  8. YOLO Seg + Reframe    — Conditional
  9. Word-Level Transcription — 9router Groq → Faster-Whisper fallback
  10. Build Subtitle Data  — Words from hook_end only (hook owns 0–3s)
  11. Auto B-roll        — Optional; audio timeline unchanged
  12+ Hook + Subtitle Render — Remotion only, matching preview config
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import asdict
from typing import Optional, TYPE_CHECKING

from src.config import settings
from src.domain.entities import (
    BRollSuggestion, Clip, CreativeDirection, Job, JobStatus,
    PipelineFlags, SpliceSegment, VisualCategory, Word,
    BrollMotionStyle, LEGACY_TEMPLATE_TO_MOTION,
)
from src.domain.interfaces import (
    IAspectRatioRouter,
    IAssetFetcher,
    IBRollInjector,
    IBrowserRenderEngine,
    IDownloader,
    IGroqAnalyzer,
    IJobRepository,
    IRenderer,
    ISubtitleRenderer,
    IWhisperLocal,
    IYoloReframeEngine,
)
from src.infrastructure.content_intelligence import ContentIntelligence
from src.infrastructure.clip_outputs import initialize_clip_readiness, mark_clip_ready
from src.infrastructure.subtitle_words import sanitize_subtitle_words
from src.infrastructure.text_emphasis import normalise_text_emphasis_style
from src.infrastructure.video_splicer import VideoSplicer
from src.infrastructure.person_first_reframe_engine import PersonFirstReframeEngine
from src.pipeline import (
    assemble_clips_data,
    best_clip_path,
    build_broll_events,
    build_clips_with_words,
    build_direct_edit_analysis,
    create_folder_structure,
    parse_broll_suggestions,
    pick_hook,
    prepare_clips_from_v2,
    write_early_json_analisa,
)

if TYPE_CHECKING:
    from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
    from src.infrastructure.overlap_detector import OverlapDetector
    from src.infrastructure.resource_monitor import ResourceMonitor
    from src.domain.interfaces_remotion import IRemotionRenderer

logger = logging.getLogger(__name__)


class V2PipelineService:
    """V2 Pipeline orchestrator for non-premium users.

    Architecture: YouTube API/9router Groq/local fallback → 9router LLM →
    Silero VAD boundary snap → Trim (A/V normalized) → WordLevelTranscriber →
    Remotion (hook 0–3s, subtitles after).
    """

    def __init__(
        self,
        job_repo: IJobRepository,
        downloader: IDownloader,
        renderer: IRenderer,
        whisper_local: IWhisperLocal,
        # ─── Shared pipeline components ──────────────────────────────
        aspect_ratio_router: Optional[IAspectRatioRouter] = None,
        yolo_reframe_engine: Optional[IYoloReframeEngine] = None,
        browser_render_engine: Optional[IBrowserRenderEngine] = None,
        broll_injector: Optional[IBRollInjector] = None,
        subtitle_renderer: Optional[ISubtitleRenderer] = None,
        asset_fetcher: Optional[IAssetFetcher] = None,
        # ─── Infrastructure ──────────────────────────────────────────
        sse_emitter: Optional["SSEProgressEmitter"] = None,
        overlap_detector: Optional["OverlapDetector"] = None,
        resource_monitor: Optional["ResourceMonitor"] = None,
        # ─── Remotion Integration ────────────────────────────────────
        remotion_adapter: Optional["IRemotionRenderer"] = None,
    ):
        self._repo = job_repo
        self._downloader = downloader
        self._renderer = renderer
        self._whisper = whisper_local

        # V2 components (lazy-init in run_pipeline)
        self._transcriber = None   # Transcript provider — lazy
        self._analyzer = None      # 9router-backed analyzer — lazy
        self._word_level_transcriber = None  # Local word-level transcriber — lazy

        # Shared components
        self._aspect_router = aspect_ratio_router
        self._yolo_reframe = yolo_reframe_engine
        self._browser_render = browser_render_engine
        self._broll_injector = broll_injector
        self._subtitle_renderer = subtitle_renderer
        self._asset_fetcher = asset_fetcher
        self._video_splicer = VideoSplicer()

        # Infrastructure
        self._sse = sse_emitter
        self._overlap_detector = overlap_detector
        self._resource_monitor = resource_monitor

        # Remotion
        self._remotion_adapter = remotion_adapter

    # ─── Lazy Component Initialization ────────────────────────────────────────

    def _get_transcriber(self):
        """Lazy-init transcript provider (TAHAP 1)."""
        if self._transcriber is None:
            from src.infrastructure.groq_transcriber import GroqTranscriber
            self._transcriber = GroqTranscriber()
        return self._transcriber

    def _get_analyzer(self):
        """Lazy-init 9router-backed analyzer (TAHAP 2)."""
        if self._analyzer is None:
            from src.infrastructure.groq_analyzer import GroqAnalyzer
            self._analyzer = GroqAnalyzer()
        return self._analyzer

    def _get_word_level_transcriber(self):
        """Lazy-init router-first word transcription with local fallback."""
        if self._word_level_transcriber is None:
            from src.infrastructure.word_level_transcriber import WordLevelTranscriber
            self._word_level_transcriber = WordLevelTranscriber()
        return self._word_level_transcriber

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _emit(self, job_id: str, step, name: str, event: str = "start", duration: float = 0):
        if not self._sse:
            return
        try:
            if event == "start":
                self._sse.emit_step_start(job_id, step, name)
            elif event == "complete":
                self._sse.emit_step_complete(job_id, step, name, duration)
            elif event == "done":
                self._sse.emit_job_done(job_id, name, duration, step)
        except Exception:
            pass

    def _emit_clip_progress(
        self,
        job_id: str,
        clip_rank: int,
        total_clips: int,
        stage: str,
        eta_seconds: Optional[int] = None,
    ) -> None:
        if not self._sse:
            return
        try:
            self._sse.emit_clip_progress(
                job_id=job_id,
                clip_rank=clip_rank,
                total_clips=total_clips,
                stage=stage,
                eta_seconds=eta_seconds,
            )
        except Exception:
            pass

    def _calc_max_clips(self, duration: float) -> int:
        if duration < 180:
            n = 2
        elif duration < 600:
            n = 5
        elif duration < 1800:
            n = 8
        elif duration < 3600:
            n = 12
        else:
            n = 15
        limit = settings.VIDEO_FINAL_RESULT
        if limit and limit > 0:
            n = min(n, limit)
        return n

    def _source_info(self, job: Job) -> dict:
        if isinstance(job.clips_data, dict) and isinstance(job.clips_data.get("source"), dict):
            return job.clips_data["source"]
        return {"type": "youtube", "url": job.youtube_url}

    def _is_upload_source(self, job: Job) -> bool:
        return self._source_info(job).get("type") == "upload"

    def _probe_local_duration(self, video_path: str) -> float:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-300:] or "ffprobe failed")
        data = json.loads(result.stdout or "{}")
        duration = float((data.get("format") or {}).get("duration") or 0)
        if duration <= 0:
            raise RuntimeError("durasi video tidak terbaca")
        return duration

    async def _prepare_uploaded_video(self, job: Job, video_path: str) -> tuple[str, float]:
        source = self._source_info(job)
        source_path = str(source.get("path") or "")
        if not source_path or not os.path.exists(source_path):
            raise FileNotFoundError("File upload tidak ditemukan")

        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        if os.path.abspath(source_path) != os.path.abspath(video_path):
            try:
                os.link(source_path, video_path)
            except OSError:
                shutil.copy2(source_path, video_path)

        duration = float(source.get("duration") or 0) or self._probe_local_duration(video_path)
        if duration > settings.MAX_VIDEO_DURATION:
            minutes = int(duration // 60)
            raise RuntimeError(
                f"Video terlalu panjang ({minutes} menit). Maksimal {settings.MAX_VIDEO_DURATION // 60} menit."
            )
        title = str(source.get("filename") or os.path.basename(source_path) or "Uploaded video")
        return title, duration

    # ─── Main Pipeline ────────────────────────────────────────────────────────

    async def run_pipeline(self, job: Job) -> None:
        """Execute the V2 pipeline for a job.

        Flow:
        1. Validate → 2. Download → 3. YouTube/local Transcript →
        4. 9router Chunked Analysis → 5. Prepare Clips → 6. Route →
        7. Trim → 8. YOLO → 9. Word-Level Transcription → 10. Build Subtitle →
        11+. Hook/Subtitle/Encode
        """
        job_id = job.job_id
        url = job.youtube_url
        video_path = f"{settings.DOWNLOAD_DIR}/{job_id}.mp4"
        output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
        os.makedirs(output_dir, exist_ok=True)
        video_title = ""
        pipeline_start = time.time()

        # ─── Cache setup ──────────────────────────────────────────────
        from src.infrastructure.cache_manager import CacheManager
        cache = CacheManager()

        # Re-read clips_data from DB for style configs
        fresh_job = await self._repo.get_by_job_id(job_id)
        if fresh_job and fresh_job.clips_data:
            job.clips_data = fresh_job.clips_data

        is_upload_source = self._is_upload_source(job)
        video_id = None if is_upload_source else cache.extract_video_id(url)
        force_reprocess = bool(job.clips_data and job.clips_data.get("force_reprocess"))

        if force_reprocess and video_id:
            cache.invalidate(video_id)
            logger.info(f"[{job_id}] Cache invalidated (force_reprocess)")

        try:
            # Pre-job: resource check
            if self._resource_monitor:
                try:
                    self._resource_monitor.check_and_raise()
                except Exception as e:
                    await self._repo.update_status(job_id, JobStatus.FAILED, str(e)[:512])
                    return

            # ═══ Step 1: Validate ═══
            self._emit(job_id, 1, "validate", "start")
            await self._repo.update_status(job_id, JobStatus.VALIDATING)
            try:
                from src.infrastructure.telegram_service import telegram_service
                asyncio.create_task(telegram_service.notify_job_started(
                    job_id=job_id,
                    title=job.title or url or "Video",
                    source_url=url or "Direct Upload"
                ))
            except Exception:
                pass
            if is_upload_source:
                try:
                    video_title, duration = await self._prepare_uploaded_video(job, video_path)
                except Exception as e:
                    await self._repo.update_status(job_id, JobStatus.FAILED, str(e)[:512])
                    return
                job.video_duration = duration
                try:
                    await self._repo.update_video_title(job_id, video_title)
                except Exception:
                    pass
            else:
                valid, error_or_title, duration = await self._downloader.validate_url(url)
                if not valid:
                    await self._repo.update_status(job_id, JobStatus.FAILED, error_or_title)
                    return
                video_title = error_or_title or ""
                job.video_duration = duration
                if error_or_title and valid:
                    try:
                        await self._repo.update_video_title(job_id, error_or_title)
                    except Exception:
                        pass
            self._emit(job_id, 1, "validate", "complete")

            # ═══ Step 2: Download (SKIP if cached) ═══
            cached_video = cache.get_video_path(video_id) if video_id else None
            if is_upload_source:
                self._emit(job_id, 2, "download", "complete")
                logger.info(f"[{job_id}] Upload source ready: {video_path}")
            elif cached_video:
                import shutil
                if not os.path.exists(video_path):
                    try:
                        os.link(cached_video, video_path)
                    except OSError:
                        shutil.copy2(cached_video, video_path)
                logger.info(f"[{job_id}] Download SKIPPED (cached: {video_id})")
                self._emit(job_id, 2, "download", "complete")
            else:
                self._emit(job_id, 2, "download", "start")
                await self._repo.update_status(job_id, JobStatus.DOWNLOADING)
                await self._downloader.download_video(url, video_path)
                if video_id and os.path.exists(video_path):
                    cache.save_video(video_id, video_path)
                self._emit(job_id, 2, "download", "complete")

            # ═══ Step 3: TAHAP 1 — YouTube API / Groq Whisper Transcript ═══
            cached_transcript = cache.load_transcript(video_id) if video_id else None
            if cached_transcript and cached_transcript.get("segments"):
                from src.domain.entities import TranscriptResult, TranscriptSegment
                transcript_result = TranscriptResult(
                    segments=[TranscriptSegment(**s) for s in cached_transcript["segments"]],
                    source=cached_transcript.get("source", "cache"),
                    language=cached_transcript.get("language", "id"),
                    total_duration=duration,
                )
                logger.info(f"[{job_id}] Transcript SKIPPED (cached: {len(transcript_result.segments)} segments)")
                self._emit(job_id, 3, "v2_transcript", "complete")
            else:
                self._emit(job_id, 3, "v2_transcript", "start")
                await self._repo.update_status(job_id, JobStatus.V2_TRANSCRIBING)
                try:
                    if is_upload_source:
                        from src.infrastructure.local_transcriber import LocalTranscriber
                        transcript_result, _raw_segments = await LocalTranscriber(self._whisper).transcribe(
                            video_path, duration
                        )
                        if not transcript_result.segments:
                            raise RuntimeError("Tidak ada suara/transkrip terdeteksi di video upload")
                    else:
                        transcriber = self._get_transcriber()
                        transcript_result = await transcriber.transcribe(url, duration)
                except Exception as e:
                    error_msg = str(e)
                    if "no transcript" in error_msg.lower() or "tidak tersedia" in error_msg.lower():
                        error_msg = "Video ini tidak memiliki subtitle/caption. Silakan pilih video yang memiliki subtitle."
                    await self._repo.update_status(job_id, JobStatus.FAILED, error_msg)
                    return
                # Cache transcript
                if video_id and transcript_result.segments:
                    cache.save_transcript(video_id, {
                        "segments": [{"text": s.text, "start": s.start, "end": s.end}
                                     for s in transcript_result.segments],
                        "source": transcript_result.source,
                        "language": transcript_result.language,
                    })
                logger.info(
                    f"[{job_id}] V2 transcript: {len(transcript_result.segments)} segments, "
                    f"source={transcript_result.source}, lang={transcript_result.language}"
                )
                self._emit(job_id, 3, "v2_transcript", "complete")

            # ═══ Step 4: TAHAP 2 — Groq LLM Chunked Highlight Analysis ═══
            direct_mode = is_upload_source and (job.clips_data or {}).get("processing_mode") == "direct"
            if direct_mode:
                analysis_result = self._build_direct_edit_analysis(
                    duration,
                    (job.clips_data or {}).get("custom_hook"),
                )
                if job.broll_enabled:
                    try:
                        analyzer = self._get_analyzer()
                        analysis_result.broll_suggestions = await analyzer.analyze_broll(
                            transcript_result,
                            duration,
                        )
                    except Exception as exc:
                        # Auto B-roll is optional. A provider/asset failure must
                        # never prevent Direct Edit from producing subtitles.
                        logger.warning(f"[{job_id}] Direct Edit B-roll analysis skipped: {exc}")
                self._emit(job_id, 4, "direct_edit", "complete")
                logger.info(
                    f"[{job_id}] Direct Edit: viral analysis skipped, full source selected, "
                    f"custom_hook={bool(analysis_result.clips[0].hook)}, "
                    f"broll_enabled={job.broll_enabled}, "
                    f"broll_count={len(analysis_result.broll_suggestions.get('1', []))}"
                )
            user_custom_clips = (job.clips_data or {}).get("custom_clips")
            if user_custom_clips:
                from src.domain.entities import HighlightCandidate, HighlightAnalysisResult
                analysis_result = HighlightAnalysisResult(
                    clips=[
                        HighlightCandidate(
                            rank=int(c.get("rank", i + 1)),
                            start=float(c.get("start", 0)),
                            end=float(c.get("end", 0)),
                            score=int(c.get("score") or 90),
                            hook=str(c.get("hook", f"Klip #{i+1}")),
                            reason=str(c.get("reason", "Custom clip from review")),
                            content_type=str(c.get("content_type", "general")),
                            speaker_energy=str(c.get("speaker_energy", "medium")),
                            hook_alt=str(c.get("hook_alt", "")),
                        )
                        for i, c in enumerate(user_custom_clips)
                    ],
                    creative_direction=(job.clips_data or {}).get("creative_direction", {}),
                    broll_suggestions={},
                    model_used="custom_clips_from_review",
                    chunks_processed=0,
                )
                logger.info(f"[{job_id}] Viral analysis SKIPPED (using {len(analysis_result.clips)} custom clips from preview review)")
                self._emit(job_id, 4, "v2_highlight_analysis", "complete")
            elif not direct_mode and (cached_analysis := ((cache.load_analysis(video_id, "v1") or cache.load_analysis(video_id, "v2")) if video_id else None)):
                from src.domain.entities import HighlightCandidate, HighlightAnalysisResult
                analysis_result = HighlightAnalysisResult(
                    clips=[HighlightCandidate(**c) for c in cached_analysis["clips"]],
                    creative_direction=cached_analysis.get("creative_direction", {}),
                    broll_suggestions=cached_analysis.get("broll_suggestions", {}),
                    model_used=cached_analysis.get("model_used", "cache"),
                    chunks_processed=cached_analysis.get("chunks_processed", 0),
                )
                logger.info(f"[{job_id}] Analysis SKIPPED (cached: {len(analysis_result.clips)} clips)")
                self._emit(job_id, 4, "v2_highlight_analysis", "complete")
            elif not direct_mode:
                self._emit(job_id, 4, "v2_highlight_analysis", "start")
                await self._repo.update_status(job_id, JobStatus.V2_ANALYZING)
                max_clips = self._calc_max_clips(duration)
                try:
                    analyzer = self._get_analyzer()
                    analysis_result = await analyzer.analyze_highlights(
                        transcript_result, duration, max_clips
                    )
                except Exception as e:
                    await self._repo.update_status(
                        job_id, JobStatus.FAILED, f"Highlight analysis gagal: {e}"
                    )
                    return

                if not analysis_result.clips:
                    await self._repo.update_status(
                        job_id, JobStatus.FAILED, "Tidak ada momen viral terdeteksi"
                    )
                    return

                # Cache analysis
                if video_id:
                    cache.save_analysis(video_id, {
                        "clips": [{"rank": c.rank, "start": c.start, "end": c.end, "score": c.score,
                                    "hook": c.hook, "reason": c.reason, "content_type": c.content_type,
                                    "speaker_energy": c.speaker_energy, "hook_alt": getattr(c, 'hook_alt', '')}
                                   for c in analysis_result.clips],
                        "creative_direction": analysis_result.creative_direction,
                        "broll_suggestions": analysis_result.broll_suggestions,
                        "model_used": analysis_result.model_used,
                        "chunks_processed": analysis_result.chunks_processed,
                    }, version="v2")
                logger.info(
                    f"[{job_id}] V2 analysis: {len(analysis_result.clips)} clips, "
                    f"model={analysis_result.model_used}, chunks={analysis_result.chunks_processed}"
                )
                self._emit(job_id, 4, "v2_highlight_analysis", "complete")

            if not analysis_result.clips:
                await self._repo.update_status(
                    job_id, JobStatus.FAILED, "Tidak ada momen viral terdeteksi"
                )
                return

            # Parse creative direction
            creative_direction = CreativeDirection.from_dict(
                analysis_result.creative_direction
            ) if analysis_result.creative_direction else CreativeDirection()

            content_profile = ContentIntelligence().detect(
                metadata={"title": video_title, "url": url},
                transcript_text=transcript_result.full_text,
                clip_hints=[asdict(c) for c in analysis_result.clips],
                autogrid_enabled=job.autogrid_enabled,
            )
            merged_clips_data = dict(job.clips_data or {})
            merged_clips_data["content_profile"] = content_profile.to_dict()
            job.clips_data = merged_clips_data
            await self._repo.update_clips_data(job_id, merged_clips_data)
            logger.info(
                f"[{job_id}] Content profile: type={content_profile.content_type}, "
                f"confidence={content_profile.confidence}, grid={content_profile.grid_strategy}"
            )

            # ═══ Step 5: Prepare Clips ═══
            self._emit(job_id, 5, "prepare_clips", "start")
            await self._repo.update_status(job_id, JobStatus.PREPARING)
            if user_custom_clips:
                clips = [
                    Clip(
                        rank=int(c.get("rank", i + 1)),
                        score=int(c.get("score") or 90),
                        start=float(c.get("start", 0)),
                        end=float(c.get("end", 0)),
                        hook=str(c.get("hook", f"Klip #{i+1}")),
                        reason=str(c.get("reason", "Custom clip from review")),
                        broll_suggestions=[],
                    )
                    for i, c in enumerate(user_custom_clips)
                ]
            elif direct_mode:
                direct_highlight = analysis_result.clips[0]
                clips = [Clip(
                    rank=1,
                    score=100,
                    start=0.0,
                    end=duration,
                    hook=direct_highlight.hook,
                    reason=direct_highlight.reason,
                    broll_suggestions=self._parse_broll_suggestions(
                        1,
                        analysis_result.broll_suggestions,
                        duration,
                    ),
                )]
            else:
                clips = self._prepare_clips_from_v2(
                    analysis_result.clips,
                    analysis_result.broll_suggestions,
                    duration,
                )
                if self._overlap_detector and clips:
                    try:
                        clips = self._overlap_detector.resolve_overlaps(clips)
                    except Exception:
                        pass
                limit = settings.VIDEO_FINAL_RESULT
                if limit and limit > 0 and clips:
                    clips = clips[:limit]
            if not clips:
                await self._repo.update_status(
                    job_id, JobStatus.FAILED, "Tidak ada clip valid setelah filtering"
                )
                return

            # Re-number clips sequentially (1, 2, 3, ...) after filtering
            for i, clip in enumerate(clips):
                clip.rank = i + 1

            clips_count = len(clips)
            await self._repo.update_clips_count(job_id, clips_count, 0, 0)

            # Publish the AI-selected clip slots immediately. The detail page
            # can now show every candidate as locked/processing while renders
            # complete independently in the background.
            pending_clips_data = self._assemble_clips_data(
                clips,
                {},
                creative_direction,
                output_dir,
                transcript_source=transcript_result.source,
            )
            pending_clips_data["broll_enabled"] = job.broll_enabled
            pending_clips_data["broll_image_overlay"] = bool(getattr(job, "broll_image_overlay", True))
            pending_clips_data["broll_behind_person"] = bool(getattr(job, "broll_behind_person", True))
            pending_clips_data["broll_video_footage"] = bool(getattr(job, "broll_video_footage", True))
            merged_clips_data = dict(job.clips_data or {})
            merged_clips_data.update(pending_clips_data)
            job.clips_data = merged_clips_data
            await self._repo.update_clips_data(job_id, merged_clips_data)
            self._emit(job_id, 5, "prepare_clips", "complete")

            # ═══ Step 5.5: Silero VAD — snap cuts to silence (no mid-speech) ═══
            # Runs on absolute source timestamps BEFORE trim so FFmpeg seeks to
            # silence boundaries. Audio is never re-timed relative to video —
            # trim still re-encodes both streams onto a shared zero clock.
            if not direct_mode and settings.VAD_ENABLED:
                self._emit(job_id, 5, "v2_vad_refining", "start")
                await self._repo.update_status(job_id, JobStatus.V2_VAD_REFINING)
                try:
                    from src.infrastructure.vad_boundary_adjuster import VADBoundaryAdjuster
                    vad = VADBoundaryAdjuster()
                    for clip in clips:
                        adj_start, adj_end = await vad.adjust_clip_boundaries(
                            video_path, clip.start, clip.end
                        )
                        # Keep bounds inside the source; refuse inverted ranges.
                        adj_start = max(0.0, min(adj_start, duration - 1.0))
                        adj_end = max(adj_start + settings.MIN_CLIP_DURATION, min(adj_end, duration))
                        if adj_start != clip.start or adj_end != clip.end:
                            logger.info(
                                f"[{job_id}] VAD clip {clip.rank}: "
                                f"{clip.start:.2f}-{clip.end:.2f} → {adj_start:.2f}-{adj_end:.2f}"
                            )
                            clip.start = round(adj_start, 3)
                            clip.end = round(adj_end, 3)
                    # Refresh published clip slots with VAD-adjusted times
                    pending_clips_data = self._assemble_clips_data(
                        clips,
                        {},
                        creative_direction,
                        output_dir,
                        transcript_source=transcript_result.source,
                    )
                    pending_clips_data["broll_enabled"] = job.broll_enabled
                    pending_clips_data["broll_image_overlay"] = bool(getattr(job, "broll_image_overlay", True))
                    pending_clips_data["broll_behind_person"] = bool(getattr(job, "broll_behind_person", True))
                    pending_clips_data["broll_video_footage"] = bool(getattr(job, "broll_video_footage", True))
                    merged_clips_data = dict(job.clips_data or {})
                    merged_clips_data.update(pending_clips_data)
                    job.clips_data = merged_clips_data
                    await self._repo.update_clips_data(job_id, merged_clips_data)
                    logger.info(f"[{job_id}] Silero VAD applied to {len(clips)} clips")
                except Exception as e:
                    logger.warning(f"[{job_id}] VAD skipped (non-fatal): {e}")
                self._emit(job_id, 5, "v2_vad_refining", "complete")

            # ═══ Step 6: Aspect Ratio Router ═══
            self._emit(job_id, 6, "aspect_router", "start")

            await self._repo.update_status(job_id, JobStatus.ROUTING)
            if self._aspect_router:
                flags = self._aspect_router.route(job.target_aspect_ratio, job.autogrid_enabled)
            else:
                flags = PipelineFlags.for_portrait() if job.target_aspect_ratio == "9:16" else PipelineFlags.for_landscape()
            self._emit(job_id, 6, "aspect_router", "complete")

            # ═══ Step 7: Trim Clips ═══
            self._emit(job_id, 7, "trim", "start")
            await self._repo.update_status(job_id, JobStatus.TRIMMING)
            trim_results = await self._trim_all_clips(
                job_id,
                video_path,
                clips,
                output_dir,
                # Every downstream reframe/B-roll filter operates on a
                # zero-based clock. Normalize YouTube and uploaded containers
                # alike so audio never retains a source seek offset.
                normalize_timestamps=True,
            )
            self._emit(job_id, 7, "trim", "complete")

            # ═══ Step 8: YOLO Seg + Reframe ═══
            self._emit(job_id, 8, "yolo_reframe", "start")
            await self._repo.update_status(job_id, JobStatus.SEGMENTING)
            reframe_data = {}

            # Execute Global Audio Diarization ONCE for entire source video
            global_diarization = None
            if flags.yolo_enabled and getattr(settings, "HF_TOKEN", ""):
                try:
                    from src.infrastructure.speaker_diarizer import (
                        SpeakerDiarizer,
                        get_cached_global_diarization,
                        set_cached_global_diarization,
                    )
                    cache_key = f"diarization_{video_path}"
                    global_diarization = get_cached_global_diarization(cache_key)
                    if global_diarization:
                        logger.info(f"[{job_id}] Global diarization CACHE HIT for {video_path}")
                    else:
                        diarizer = SpeakerDiarizer(
                            hf_token=settings.HF_TOKEN,
                            model_name=getattr(settings, "DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1"),
                            timeout_sec=getattr(settings, "DIARIZATION_TIMEOUT_SEC", 120),
                        )
                        if diarizer.is_available:
                            logger.info(f"[{job_id}] Running GLOBAL audio diarization on source video ({duration:.1f}s)...")
                            t_dia = time.time()
                            global_diarization = await diarizer.diarize(video_path)
                            if global_diarization:
                                set_cached_global_diarization(cache_key, global_diarization)
                                logger.info(
                                    f"[{job_id}] Global diarization complete in {time.time() - t_dia:.1f}s: "
                                    f"{global_diarization.speaker_count} speakers, {len(global_diarization.segments)} segments"
                                )
                except Exception as e:
                    logger.warning(f"[{job_id}] Global diarization skipped (fallback to per-clip): {e}")

            if flags.yolo_enabled and self._yolo_reframe:
                reframe_style = (job.clips_data or {}).get("hook_style_config", {})
                valid_clips = [c for c in clips if trim_results.get(c.rank)]
                total_valid = len(valid_clips)

                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    clip_dur = max(1.0, float(clip.end - clip.start))
                    est_reframe_sec = max(5, round(clip_dur * 1.1))

                    self._emit_clip_progress(
                        job_id=job_id,
                        clip_rank=clip.rank,
                        total_clips=total_valid,
                        stage="Reframing 9:16",
                        eta_seconds=est_reframe_sec,
                    )
                    try:
                        result = await self._yolo_reframe.process(
                            in_path,
                            out_path,
                            job.target_aspect_ratio,
                            flags.autogrid_enabled,
                            content_profile=(job.clips_data or {}).get("content_profile", {}),
                            transition_style=reframe_style.get("transitionStyle", "cut"),
                            transition_duration=reframe_style.get("transitionDuration", 0.35),
                            global_diarization=global_diarization,
                            clip_start=clip.start,
                            clip_end=clip.end,
                        )
                        reframe_data[clip.rank] = result
                    except Exception as e:
                        logger.warning(f"[{job_id}] YOLO reframe failed clip {clip.rank}: {e}")
            self._emit(job_id, 8, "yolo_reframe", "complete")

            # ═══ Step 8.1: Person-First Shadow Mode (parallel comparison) ═══
            if (
                settings.REFRAME_PIPELINE_MODE == "shadow"
                and flags.yolo_enabled
                and reframe_data
            ):
                try:
                    shadow_engine = PersonFirstReframeEngine(
                        hf_token=getattr(settings, "HF_TOKEN", ""),
                    )
                    shadow_results = {}
                    for clip in clips:
                        if not trim_results.get(clip.rank):
                            continue
                        in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                        shadow_out = f"{output_dir}/clip_{clip.rank:02d}_shadow.mp4"
                        try:
                            shadow_result = await shadow_engine.process(
                                in_path,
                                shadow_out,
                                job.target_aspect_ratio,
                                flags.autogrid_enabled,
                                content_profile=(job.clips_data or {}).get("content_profile", {}),
                                transition_style=reframe_style.get("transitionStyle", "cut"),
                                transition_duration=reframe_style.get("transitionDuration", 0.35),
                                global_diarization=global_diarization,
                                clip_start=clip.start,
                                clip_end=clip.end,
                            )
                            shadow_results[clip.rank] = shadow_result
                        except Exception as e:
                            logger.debug(f"[{job_id}] shadow reframe clip {clip.rank}: {e}")

                    # Log comparison metrics
                    for rank in reframe_data:
                        legacy = reframe_data[rank]
                        shadow = shadow_results.get(rank, {})
                        logger.info(
                            f"[{job_id}] SHADOW COMPARE clip {rank}: "
                            f"legacy_method={legacy.get('method', 'unknown')}, "
                            f"legacy_persons={legacy.get('person_count', 0)}, "
                            f"shadow_method={shadow.get('method', 'unknown')}, "
                            f"shadow_persons={shadow.get('person_count', 0)}"
                        )

                    # Cleanup shadow outputs (not used for final render)
                    for clip in clips:
                        shadow_out = f"{output_dir}/clip_{clip.rank:02d}_shadow.mp4"
                        if os.path.exists(shadow_out):
                            os.remove(shadow_out)

                except Exception as e:
                    logger.warning(f"[{job_id}] shadow mode error (non-fatal): {e}")

            # ═══ Step 8.2: Person-First Active Mode ═══
            elif settings.REFRAME_PIPELINE_MODE == "person_first" and flags.yolo_enabled and not reframe_data:
                # Only run if Step 8 (PodcastReframeEngine) did NOT produce results.
                # PodcastReframeEngine already handles person-first mode internally
                # when REFRAME_PIPELINE_MODE == "person_first".
                person_first_engine = PersonFirstReframeEngine(
                    hf_token=getattr(settings, "HF_TOKEN", ""),
                )
                reframe_data = {}
                reframe_style = (job.clips_data or {}).get("hook_style_config", {})
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    try:
                        result = await person_first_engine.process(
                            in_path,
                            out_path,
                            job.target_aspect_ratio,
                            flags.autogrid_enabled,
                            content_profile=(job.clips_data or {}).get("content_profile", {}),
                            transition_style=reframe_style.get("transitionStyle", "cut"),
                            transition_duration=reframe_style.get("transitionDuration", 0.35),
                            global_diarization=global_diarization,
                            clip_start=clip.start,
                            clip_end=clip.end,
                        )
                        reframe_data[clip.rank] = result
                    except Exception as e:
                        logger.warning(f"[{job_id}] person_first reframe failed clip {clip.rank}: {e}")

            # Center-crop fallback for 9:16 — ONLY if YOLO model wasn't loaded
            # If YOLO ran but returned None (e.g. union_crop decided to skip because
            # speakers too wide), respect that decision — don't force center-crop
            if flags.yolo_enabled and not reframe_data and not self._yolo_reframe and job.target_aspect_ratio == "9:16":
                import subprocess as _sp
                from src.infrastructure.gpu_encoder import get_video_encoder_args
                logger.info(f"[{job_id}] Applying center-crop fallback for 9:16 (YOLO not available)")
                encoder_args = get_video_encoder_args("medium")
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    crop_cmd = [
                        "ffmpeg", "-y", "-i", in_path,
                        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
                        *encoder_args,
                        "-c:a", "copy", "-movflags", "+faststart",
                        out_path,
                    ]
                    try:
                        result = await asyncio.to_thread(
                            _sp.run, crop_cmd, capture_output=True, text=True, timeout=60
                        )
                        if result.returncode == 0 and os.path.exists(out_path):
                            reframe_data[clip.rank] = {"method": "center_crop_fallback"}
                    except Exception as e:
                        logger.warning(f"[{job_id}] Center-crop error clip {clip.rank}: {e}")

            # ═══ Step 8.5: GPU Memory Cleanup (prevent CUDA OOM for Whisper) ═══
            # PyAnnote + MediaPipe + YOLO consume significant VRAM during reframe.
            # Release all GPU memory before Faster-Whisper model loads.
            try:
                import torch
                import gc
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                gc.collect()
                logger.info(f"[{job_id}] GPU memory released after reframe step")
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"[{job_id}] GPU cleanup warning (non-critical): {e}")

            # ═══ Step 9: Word-Level Transcription on Trimmed Clips ═══
            self._emit(job_id, 9, "word_level", "start")
            await self._repo.update_status(job_id, JobStatus.V2_WORD_TRANSCRIBING)
            trimmed_ranks = [clip.rank for clip in clips if trim_results.get(clip.rank)]
            word_level = self._get_word_level_transcriber()
            words_per_clip: dict[int, list[dict]] = await word_level.transcribe_all_clips(
                clips_dir=output_dir,
                clip_ranks=trimmed_ranks,
                language=transcript_result.language or "id",
            )
            # Resilient fallback: If any trimmed clip has 0 words (e.g. rate limit / network / audio lock),
            # slice timestamps from global transcript segments so subtitles NEVER fail to render!
            for clip in clips:
                if not trim_results.get(clip.rank):
                    continue
                if not words_per_clip.get(clip.rank) and transcript_result and getattr(transcript_result, "segments", None):
                    fallback_words = self._slice_words_from_transcript(clip, transcript_result.segments)
                    if fallback_words:
                        words_per_clip[clip.rank] = fallback_words
                        logger.info(
                            f"[{job_id}] Word-level fallback from global transcript: "
                            f"{len(fallback_words)} words recovered for clip {clip.rank}"
                        )
            logger.info(
                f"[{job_id}] Word-level: "
                f"{sum(1 for w in words_per_clip.values() if w)}/{len(trimmed_ranks)} clips with words, "
                f"{sum(len(w) for w in words_per_clip.values())} total words"
            )
            self._emit(job_id, 9, "word_level", "complete")

            # ═══ Step 10: Build Subtitle Data (words already 0-based) ═══
            # Hook owns 0–N seconds (default 3s). Subtitles must not appear there.
            hook_duration = float(
                ((job.clips_data or {}).get("hook_style_config") or {}).get("duration", 3.0) or 3.0
            )
            self._emit(job_id, 10, "highlights", "start")
            await self._repo.update_status(job_id, JobStatus.HIGHLIGHTING)
            clips_with_words: dict[int, list[dict]] = self._build_clips_with_words(
                clips, words_per_clip, hook_duration=hook_duration
            )
            self._emit(job_id, 10, "highlights", "complete")

            # Stash words for phrase-aware behind-person duration (step 11 overlay)
            self._last_clips_with_words = clips_with_words

            # ═══ Step 10.5: Prosody (energy peaks → zoom punch) ═══
            prosody_results: dict = {}
            try:
                from src.infrastructure.prosody_analyzer import ProsodyAnalyzer
                analyzer = ProsodyAnalyzer()
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    clip_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    if not os.path.exists(clip_path):
                        continue
                    try:
                        prosody_results[clip.rank] = analyzer.analyze(clip_path)
                    except Exception as pe:
                        logger.debug(f"[{job_id}] prosody clip {clip.rank}: {pe}")
            except Exception as e:
                logger.warning(f"[{job_id}] Prosody analyzer unavailable: {e}")

            # ═══ Step 11: Optional Auto B-roll ═══
            # Recover missing creative-direction suggestions from the exact
            # word-level transcript. This keeps Analyze First working even when
            # the separate creative JSON response is malformed or times out.
            await self._ensure_broll_suggestions(
                job=job,
                job_id=job_id,
                clips=clips,
                clips_with_words=clips_with_words,
            )
            # Draft json_analisa early so asset search uses ID+EN seeds from it.
            try:
                self._write_early_json_analisa(
                    job=job,
                    job_id=job_id,
                    clips=clips,
                    clips_with_words=clips_with_words,
                    output_dir=output_dir,
                )
            except Exception as e:
                logger.warning(f"[{job_id}] Early json_analisa write failed: {e}")
            # The B-roll renderer keeps the same zero-based duration and audio
            # clock, so word timestamps and lip-sync remain unchanged.
            await self._apply_brolls(
                job=job,
                job_id=job_id,
                clips=clips,
                creative_direction=creative_direction,
                output_dir=output_dir,
                trim_results=trim_results,
            )

            # ═══ Step 11.5: Optional sparse AI cinematic text ═══
            # Selection is anchored to the word-level transcript. YOLO11-seg
            # only creates foreground assets; it never rewrites the source.
            await self._prepare_text_emphasis(
                job=job,
                job_id=job_id,
                clips=clips,
                clips_with_words=clips_with_words,
                output_dir=output_dir,
                trim_results=trim_results,
            )

            # Checkpoint before expensive Remotion renders
            try:
                from src.infrastructure.checkpoint_manager import CheckpointManager
                CheckpointManager().save(
                    job_id, 12, "pre_remotion",
                    {"clip_ranks": [c.rank for c in clips if trim_results.get(c.rank)]},
                )
            except Exception:
                pass

            # ═══ Step 12+: Hook, Subtitle, Encode (REUSE) ═══
            await self._render_clips(
                job=job,
                job_id=job_id,
                clips=clips,
                clips_with_words=clips_with_words,
                creative_direction=creative_direction,
                output_dir=output_dir,
                trim_results=trim_results,
                reframe_data=reframe_data,
                prosody_results=prosody_results,
            )

            # ═══ Step 12.4: HyperFrames polish (AI lower-third from entities) ═══
            try:
                await self._apply_hyperframes_polish(
                    job=job,
                    job_id=job_id,
                    clips=clips,
                    output_dir=output_dir,
                    trim_results=trim_results,
                )
            except Exception as e:
                logger.warning(f"[{job_id}] HyperFrames polish skipped: {e}")

            # ═══ Step 12.5: Audio post (music bed duck under speech) ═══
            try:
                await self._mix_audio_clips(
                    job_id=job_id,
                    clips=clips,
                    creative_direction=creative_direction,
                    output_dir=output_dir,
                    trim_results=trim_results,
                )
            except Exception as e:
                logger.warning(f"[{job_id}] Audio mix step skipped: {e}")

            # ═══ Step 12: Folder Structure + Thumbnails + Meta JSON ═══
            await self._create_folder_structure(
                job_id=job_id,
                job=job,
                clips=clips,
                clips_with_words=clips_with_words,
                creative_direction=creative_direction,
                output_dir=output_dir,
                trim_results=trim_results,
            )

            # ═══ Final: Assemble results ═══
            success_count = sum(
                1 for clip in clips
                if os.path.exists(f"{output_dir}/clip_{clip.rank:02d}_final.mp4")
                or os.path.exists(f"{output_dir}/clip_{clip.rank:02d}_subtitled.mp4")
                or os.path.exists(f"{output_dir}/clip_{clip.rank:02d}.mp4")
            )
            failed_count = clips_count - success_count
            await self._repo.update_clips_count(job_id, clips_count, success_count, failed_count)

            clips_data = self._assemble_clips_data(
                clips, clips_with_words, creative_direction, output_dir,
                transcript_source=transcript_result.source,
            )
            clips_data["broll_enabled"] = job.broll_enabled
            clips_data["broll_image_overlay"] = bool(getattr(job, "broll_image_overlay", True))
            clips_data["broll_behind_person"] = bool(getattr(job, "broll_behind_person", True))
            clips_data["broll_video_footage"] = bool(getattr(job, "broll_video_footage", True))
            for clip_output in clips_data.get("clips", []):
                layout = reframe_data.get(clip_output.get("rank"), {})
                if isinstance(layout, dict):
                    clip_output["reframe_layout"] = layout.get("layout", "single")
                    clip_output["reframe_method"] = layout.get("method", "")
                    if layout.get("subtitle_position_y") is not None:
                        clip_output["subtitle_position_y"] = layout["subtitle_position_y"]
                    for key in (
                        "layout_mode",
                        "layout_events",
                        "framing_events",
                        "transition_style",
                        "transition_duration",
                    ):
                        if layout.get(key) is not None:
                            clip_output[key] = layout[key]
            if job.clips_data:
                for key in (
                    "hook_style_config",
                    "content_profile",
                    "source",
                    "source_type",
                    "processing_mode",
                    "custom_hook",
                    "text_emphasis_enabled",
                    "text_emphasis_style_config",
                ):
                    if job.clips_data.get(key):
                        clips_data[key] = job.clips_data[key]
                if job.clips_data.get("subtitle_style_config"):
                    clips_data["subtitle_style_config"] = job.clips_data["subtitle_style_config"]
            await self._repo.update_clips_data(job_id, clips_data)

            total_time = time.time() - pipeline_start
            await self._repo.update_status(job_id, JobStatus.COMPLETED)
            self._emit(job_id, 16, "done", "done", total_time)
            logger.info(
                f"[{job_id}] V2 pipeline COMPLETED in {total_time:.1f}s — "
                f"{success_count}/{clips_count} clips"
            )

            # Telegram notification on job completion
            try:
                from src.infrastructure.telegram_service import telegram_service
                clips_list = [asdict(c) if hasattr(c, "__dataclass_fields__") else (c if isinstance(c, dict) else c.__dict__) for c in (valid_clips or clips)]
                asyncio.create_task(telegram_service.notify_job_completed(
                    job_id=job_id,
                    title=video_title or job.title or job.youtube_url or "Video",
                    clips_count=len(clips_list),
                    clips=clips_list,
                    output_dir=output_dir,
                ))
            except Exception:
                pass

        except asyncio.CancelledError:
            logger.info(f"[{job_id}] V2 pipeline cancelled by user.")
            try:
                await self._repo.update_status(job_id, JobStatus.FAILED, "Cancelled by user")
            except Exception:
                pass
            return
        except Exception as e:
            logger.exception(f"[{job_id}] V2 pipeline FAILED: {e}")
            await self._repo.update_status(
                job_id, JobStatus.FAILED,
                f"V2 pipeline error: {str(e)[:500]}"
            )
            # Telegram notification on job failure
            try:
                from src.infrastructure.telegram_service import telegram_service
                asyncio.create_task(telegram_service.notify_job_failed(
                    job_id=job_id,
                    error=str(e),
                    title=video_title or job.title or ""
                ))
            except Exception:
                pass

    # ─── V2-Specific Helpers ──────────────────────────────────────────────────

    _build_direct_edit_analysis = staticmethod(build_direct_edit_analysis)
    _pick_hook = staticmethod(pick_hook)
    _parse_broll_suggestions = staticmethod(parse_broll_suggestions)

    def _build_clips_with_words(
        self,
        clips: list[Clip],
        words_per_clip: dict[int, list],
        hook_duration: float = 0.0,
    ) -> dict[int, list[dict]]:
        return build_clips_with_words(clips, words_per_clip, hook_duration)

    def _slice_words_from_transcript(self, clip: Clip, segments: list) -> list[dict]:
        """Recover word timestamps by slicing global transcript segments for a clip's time range."""
        clip_words = []
        clip_dur = max(0.0, float(clip.end) - float(clip.start))
        for seg in segments or []:
            s_start = float(getattr(seg, "start", 0.0))
            s_end = float(getattr(seg, "end", 0.0))
            # Check overlap with clip range
            if s_end <= clip.start or s_start >= clip.end:
                continue
            seg_rel_start = max(0.0, s_start - float(clip.start))
            seg_rel_end = min(clip_dur, s_end - float(clip.start))
            if seg_rel_end <= seg_rel_start:
                continue
            text = str(getattr(seg, "text", "") or "").strip()
            if not text:
                continue
            tokens = text.split()
            if not tokens:
                continue
            token_dur = (seg_rel_end - seg_rel_start) / len(tokens)
            for idx, token in enumerate(tokens):
                w_s = seg_rel_start + idx * token_dur
                w_e = min(clip_dur, w_s + token_dur)
                clip_words.append({
                    "word": token,
                    "start": round(w_s, 3),
                    "end": round(w_e, 3),
                })
        return clip_words

    def _prepare_clips_from_v2(
        self, highlights: list, broll_map: dict, video_duration: float
    ) -> list[Clip]:
        return prepare_clips_from_v2(highlights, broll_map, video_duration, self._parse_broll_suggestions)


    async def _trim_all_clips(
        self,
        job_id: str,
        video_path: str,
        clips: list[Clip],
        output_dir: str,
        normalize_timestamps: bool = False,
    ) -> dict[int, bool]:
        """Trim all clips using FFmpeg."""
        results = {}
        for clip in clips:
            out_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            try:
                success = await self._renderer.trim_clip(
                    video_path,
                    clip,
                    out_path,
                    normalize_timestamps=normalize_timestamps,
                )
                results[clip.rank] = success
                if not success:
                    logger.warning(f"[{job_id}] Trim failed for clip {clip.rank}")
            except Exception as e:
                logger.warning(f"[{job_id}] Trim error clip {clip.rank}: {e}")
                results[clip.rank] = False
        return results

    async def _apply_brolls(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        creative_direction: CreativeDirection,
        output_dir: str,
        trim_results: dict[int, bool],
    ) -> None:
        """Apply optional B-roll before Remotion renders hooks and subtitles."""
        self._emit(job_id, 11, "broll", "start")
        if not job.broll_enabled:
            logger.info(f"[{job_id}] Auto B-roll disabled by user")
            self._emit(job_id, 11, "broll", "complete")
            return

        # Stamp clip topic (hook/reason) onto suggestions for entity lock + pass-2 context.
        suggestions: list[BRollSuggestion] = []
        for clip in clips:
            topic = " ".join(
                x for x in (clip.hook or "", clip.reason or "") if x
            ).strip()
            for suggestion in clip.broll_suggestions:
                if topic and not (suggestion.reason or "").strip():
                    suggestion.reason = topic[:200]
                suggestions.append(suggestion)
        if not suggestions:
            logger.info(f"[{job_id}] Auto B-roll enabled, but no relevant suggestions were found")
            self._emit(job_id, 11, "broll", "complete")
            return

        if not self._broll_injector:
            logger.warning(f"[{job_id}] Auto B-roll renderer unavailable; continuing without B-roll")
            self._emit(job_id, 11, "broll", "complete")
            return

        await self._repo.update_status(job_id, JobStatus.BROLL)
        if self._asset_fetcher:
            try:
                # Footage search seeds from early json_analisa (ID + EN + objects)
                from src.infrastructure.object_image_overlay import (
                    footage_keywords_from_analisa,
                    load_clip_analisa,
                )
                analisa_q: list[str] = []
                seen_q: set[str] = set()
                for clip in clips:
                    analisa = load_clip_analisa(output_dir, clip.rank)
                    for kw in footage_keywords_from_analisa(analisa):
                        low = kw.lower()
                        if low not in seen_q:
                            seen_q.add(low)
                            analisa_q.append(kw)
                from src.infrastructure.canvas_templates import resolution_for_aspect

                out_w, out_h = resolution_for_aspect(job.target_aspect_ratio or "9:16")
                await self._asset_fetcher.fetch_assets(
                    suggestions,
                    creative_direction,
                    analisa_extra_queries=analisa_q[:24] if analisa_q else None,
                    target_width=out_w,
                    target_height=out_h,
                )
            except TypeError:
                # Older IAssetFetcher signature without analisa_extra_queries / resolution
                try:
                    await self._asset_fetcher.fetch_assets(suggestions, creative_direction)
                except Exception as exc:
                    logger.warning(f"[{job_id}] B-roll asset search failed; using fallback: {exc}")
            except Exception as exc:
                # The injector can still render its typography fallback.
                logger.warning(f"[{job_id}] B-roll asset search failed; using fallback: {exc}")

        # ─── Step 10.6: Splice B-Roll Footage (video track replacement) ───────
        # Only placement=full_frame (or video without behind_person). Never splice
        # behind_person suggestions — those keep the person on screen.
        from src.infrastructure.top_behind_subject_renderer import pick_full_frame_suggestions
        from src.infrastructure.canvas_templates import resolution_for_aspect as _res_for_aspect
        _out_w, _out_h = _res_for_aspect(job.target_aspect_ratio or "9:16")

        allow_video = bool(getattr(job, "broll_video_footage", True))
        allow_behind = bool(getattr(job, "broll_behind_person", True))
        allow_image = bool(getattr(job, "broll_image_overlay", True))
        # clips_data is source of truth when job reloaded mid-pipeline
        cd = job.clips_data or {}
        if "broll_video_footage" in cd:
            allow_video = bool(cd["broll_video_footage"])
        if "broll_behind_person" in cd:
            allow_behind = bool(cd["broll_behind_person"])
        if "broll_image_overlay" in cd:
            allow_image = bool(cd["broll_image_overlay"])
        logger.info(
            f"[{job_id}] B-roll subtypes: image={allow_image} behind={allow_behind} video={allow_video}"
        )

        if settings.BROLL_SPLICE_ENABLED and allow_video:
            splice_count = 0
            for clip in clips:
                if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                    continue

                full_frame = pick_full_frame_suggestions(clip.broll_suggestions)
                # Collect splice segments from full-frame suggestions only
                splice_segments = [
                    s.splice_segment for s in full_frame
                    if hasattr(s, 'splice_segment') and s.splice_segment
                ]
                if not splice_segments:
                    continue


                # Determine input path
                reframed_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                base_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                input_path = reframed_path if os.path.exists(reframed_path) else base_path
                splice_output = f"{output_dir}/clip_{clip.rank:02d}_spliced.mp4"

                self._emit(job_id, 11, "broll_splice", "start")
                try:
                    result_path = await self._video_splicer.splice(
                        clip_path=input_path,
                        segments=splice_segments,
                        output_path=splice_output,
                        width=_out_w,
                        height=_out_h,
                    )
                    if result_path == splice_output and os.path.exists(splice_output):
                        splice_count += 1
                        # Rename spliced as the "brolled" output so downstream steps use it
                        brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                        os.rename(splice_output, brolled_path)
                except Exception as exc:
                    logger.warning(f"[{job_id}] B-roll splice failed clip {clip.rank}: {exc}")
                finally:
                    self._emit(job_id, 11, "broll_splice", "complete")

            if splice_count > 0:
                logger.info(f"[{job_id}] B-roll splice: {splice_count}/{len(clips)} clips spliced")
            # Keep broll_footage until after top-behind overlay — picker/renderer
            # may still need splice_segment.footage_path / asset local paths.

        # ─── Step 10.6b: Splice legacy video assets (Pexels/Pixabay direct) ──

        # If ClipScout didn't provide splice_segments but legacy fetcher got video
        # assets, also splice them full-frame (not overlay).
        if settings.BROLL_SPLICE_ENABLED and allow_video:
            from src.infrastructure.footage_processor import FootageProcessor
            legacy_processor = FootageProcessor()

            for clip in clips:
                if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                    continue
                brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                if os.path.exists(brolled_path):
                    continue  # Already spliced by ClipScout path

                # Full-frame video assets only (skip behind_person placement)
                video_suggestions = [
                    s for s in pick_full_frame_suggestions(clip.broll_suggestions)
                    if (s.asset_result
                        and not s.asset_result.is_fallback
                        and s.asset_result.asset_format == "video"
                        and not s.splice_segment
                        and os.path.exists(s.asset_result.local_path))
                ]
                if not video_suggestions:
                    continue


                # Process each legacy video asset to job resolution and create SpliceSegment
                legacy_segments = []
                for idx, s in enumerate(video_suggestions):
                    processed = await legacy_processor.process(
                        raw_path=s.asset_result.local_path,
                        target_duration=s.duration,
                        clip_rank=clip.rank,
                        index=idx,
                        output_dir=os.path.join(output_dir, "broll_footage"),
                        width=_out_w,
                        height=_out_h,
                    )
                    if processed:
                        legacy_segments.append(SpliceSegment(
                            footage_path=processed,
                            at_time=s.at_time,
                            duration=s.duration,
                            keyword=s.keyword,
                            source_id=s.asset_result.source_api or "legacy",
                            platform=s.asset_result.source_api or "legacy",
                        ))

                if legacy_segments:
                    reframed_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    base_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    input_path = reframed_path if os.path.exists(reframed_path) else base_path
                    splice_output = f"{output_dir}/clip_{clip.rank:02d}_spliced.mp4"

                    try:
                        result_path = await self._video_splicer.splice(
                            clip_path=input_path,
                            segments=legacy_segments,
                            output_path=splice_output,
                            width=_out_w,
                            height=_out_h,
                        )
                        if result_path == splice_output and os.path.exists(splice_output):
                            os.rename(splice_output, brolled_path)
                            logger.info(f"[{job_id}] Legacy video spliced clip {clip.rank}")
                    except Exception as exc:
                        logger.warning(f"[{job_id}] Legacy video splice failed clip {clip.rank}: {exc}")

        # No full-frame overlay fallback for splice. Non-video assets feed the
        # additive Top Behind Subject path instead (portrait only).
        applied_count = sum(
            1 for clip in clips
            if os.path.exists(f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4")
        )
        logger.info(
            f"[{job_id}] Auto B-roll splice: {applied_count}/{len(clips)} clips "
            "timeline-spliced"
        )

        # ─── Step 10.7: Top Behind Subject Overlay (additive, portrait) ──────
        # Full-frame splice stays as-is. Additionally place image/video assets
        # behind the person in the top ~50% only. Runs on base/reframed (or
        # already-spliced) clip so both effects can coexist on different times.
        if (
            settings.TOP_OVERLAY_ENABLED
            and job.target_aspect_ratio == "9:16"
            and allow_behind
        ):
            await self._apply_top_behind_overlay(
                job=job,
                job_id=job_id,
                clips=clips,
                output_dir=output_dir,
                trim_results=trim_results,
                clips_with_words=getattr(self, "_last_clips_with_words", None),
            )

        # ─── Step 10.8: Object image+text overlay (noun → stock photo card) ──
        if allow_image:
            await self._apply_object_image_overlay(
                job=job,
                job_id=job_id,
                clips=clips,
                output_dir=output_dir,
                trim_results=trim_results,
                clips_with_words=getattr(self, "_last_clips_with_words", None),
            )
        else:
            logger.info(f"[{job_id}] Object image overlay disabled by user")

        # Drop intermediate footage only after top-behind bake.
        footage_dir = os.path.join(output_dir, "broll_footage")
        if os.path.exists(footage_dir):
            shutil.rmtree(footage_dir, ignore_errors=True)

        self._emit(job_id, 11, "broll", "complete")




    async def _apply_top_behind_overlay(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        output_dir: str,
        trim_results: dict[int, bool],
        clips_with_words: dict[int, list[dict]] | None = None,
    ) -> None:
        """Bake top-region behind-person overlays. Additive to full-frame splice.

        Blocks full-frame splice time ranges — person is gone there, so
        behind-person would be invisible. Tracks must use different times.
        Phrase-aware when word timestamps available.
        """
        from src.infrastructure.top_behind_subject_renderer import (
            TopBehindSubjectRenderer,
            pick_top_overlay_suggestions,
            pick_full_frame_suggestions,
        )

        words_map = clips_with_words or {}
        renderer = TopBehindSubjectRenderer()
        applied = 0
        for clip in clips:
            if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                clip.top_overlay_events = []
                continue

            # Block times already used by full-frame splice (person replaced)
            blocked = []
            for s in pick_full_frame_suggestions(clip.broll_suggestions):
                has_asset = bool(
                    (s.splice_segment and getattr(s.splice_segment, "footage_path", None))
                    or (
                        s.asset_result
                        and not s.asset_result.is_fallback
                        and s.asset_result.asset_format == "video"
                        and s.asset_result.local_path
                    )
                )
                if has_asset or (getattr(s, "placement", "") or "") == "full_frame":
                    blocked.append((float(s.at_time), float(s.at_time) + float(s.duration)))

            clip_dur = max(0.0, float(clip.end) - float(clip.start))
            segments = pick_top_overlay_suggestions(
                clip.broll_suggestions,
                max_per_clip=settings.TOP_OVERLAY_MAX_PER_CLIP,
                blocked_ranges=blocked,
                words=words_map.get(clip.rank) or [],
                clip_duration=clip_dur,
            )
            if not segments:
                clip.top_overlay_events = []
                continue


            # Prefer already-spliced full-frame B-roll so top-behind is additive
            # (does not discard timeline splice when both effects run).
            reframed_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
            base_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
            if os.path.exists(brolled_path):
                input_path = brolled_path
            elif os.path.exists(reframed_path):
                input_path = reframed_path
            else:
                input_path = base_path
            if not os.path.exists(input_path):
                clip.top_overlay_events = []
                continue


            out_path = f"{output_dir}/clip_{clip.rank:02d}_top_overlay.mp4"
            try:
                result = await renderer.apply_to_clip(
                    video_path=input_path,
                    segments=segments,
                    output_path=out_path,
                )
            except Exception as exc:
                logger.warning(f"[{job_id}] Top overlay failed clip {clip.rank}: {exc}")
                clip.top_overlay_events = []
                continue

            if result and os.path.exists(out_path):
                target = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                try:
                    if os.path.exists(target):
                        os.remove(target)
                    os.rename(out_path, target)
                except OSError:
                    shutil.move(out_path, target)
                clip.top_overlay_events = [
                    {
                        "at_time": s.at_time,
                        "duration": s.duration,
                        "keyword": s.keyword,
                        "source": s.source,
                        "asset_path": s.asset_path,
                    }
                    for s in segments
                ]
                applied += 1
            else:
                clip.top_overlay_events = []

        logger.info(
            f"[{job_id}] Top behind-subject overlay: {applied}/{len(clips)} clips"
        )

    async def _apply_object_image_overlay(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        output_dir: str,
        trim_results: dict[int, bool],
        clips_with_words: dict[int, list[dict]] | None = None,
    ) -> None:
        """AI visual entities → stock photo card + styled label on video.

        Style from DB object_overlay_configs (or env defaults). Stack: image then text.
        Animation/position/size/radius all configurable. No domain lexicon.
        """
        from src.infrastructure.object_image_overlay import (
            ObjectImageOverlayRenderer,
            load_clip_analisa,
            load_object_overlay_style,
            objects_from_analisa,
            pick_object_mentions,
            words_from_analisa,
        )
        from src.infrastructure.clip_quality_helpers import extract_objects

        try:
            style = load_object_overlay_style(getattr(job, "user_id", None))
        except Exception:
            style = load_object_overlay_style(None)
        if not style.get("enabled", True) or not getattr(settings, "OBJECT_OVERLAY_ENABLED", True):
            for c in clips:
                c.object_overlay_events = []
            return

        words_map = clips_with_words or {}
        renderer = ObjectImageOverlayRenderer()
        applied = 0
        for clip in clips:
            if not trim_results.get(clip.rank):
                clip.object_overlay_events = []
                continue

            clip_dur = max(0.0, float(clip.end) - float(clip.start))
            words = list(words_map.get(clip.rank) or [])
            # AI VE / analisa first; extract_objects top-ups thin VE with proper-case words
            ve = list(getattr(clip, "visual_entities", None) or [])
            analisa = load_clip_analisa(output_dir, clip.rank)
            if not words and analisa:
                words = words_from_analisa(analisa)
            objects = objects_from_analisa(analisa) if analisa else []
            seed = objects or ve
            objects = extract_objects(words, visual_entities=seed)

            # Block full-frame splice + top-overlay + text-emphasis windows lightly
            blocked: list[tuple[float, float]] = []
            for s in clip.broll_suggestions or []:
                place = (getattr(s, "placement", "") or "").lower()
                if place in ("full_frame", "splice", ""):
                    # only hard-block full_frame with real asset
                    if place == "full_frame" or getattr(s, "splice_segment", None):
                        blocked.append((float(s.at_time), float(s.at_time) + float(s.duration)))
            for ev in getattr(clip, "top_overlay_events", None) or []:
                try:
                    blocked.append((float(ev["at_time"]), float(ev["at_time"]) + float(ev["duration"])))
                except (KeyError, TypeError, ValueError):
                    pass
            for ev in getattr(clip, "text_emphasis_events", None) or []:
                try:
                    st = float(ev.get("start", ev.get("at_time", 0)) or 0)
                    en = float(ev.get("end", st + 1.5) or st + 1.5)
                    blocked.append((st, en))
                except (TypeError, ValueError):
                    pass

            mentions = pick_object_mentions(
                words,
                objects,
                max_items=int(style.get("max_per_clip", 3)),
                clip_duration=clip_dur,
                blocked_ranges=blocked,
                style=style,
            )
            if not mentions:
                clip.object_overlay_events = []
                continue

            events = await renderer.resolve_events(
                mentions,
                output_dir=output_dir,
                clip_hook=clip.hook or "",
                clip_reason=clip.reason or "",
                style=style,
            )
            if not events:
                clip.object_overlay_events = []
                continue

            reframed = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
            base = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            brolled = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
            if os.path.exists(brolled):
                input_path = brolled
            elif os.path.exists(reframed):
                input_path = reframed
            else:
                input_path = base
            if not os.path.exists(input_path):
                clip.object_overlay_events = []
                continue

            out_path = f"{output_dir}/clip_{clip.rank:02d}_obj_overlay.mp4"
            try:
                result = await renderer.apply_to_clip(
                    video_path=input_path,
                    events=events,
                    output_path=out_path,
                    style=style,
                )
            except Exception as exc:
                logger.warning(f"[{job_id}] Object overlay failed clip {clip.rank}: {exc}")
                clip.object_overlay_events = []
                continue

            if result and os.path.exists(out_path):
                target = brolled
                try:
                    if os.path.exists(target):
                        os.remove(target)
                    os.rename(out_path, target)
                except OSError:
                    shutil.move(out_path, target)
                clip.object_overlay_events = [e.to_dict() for e in events]
                applied += 1
            else:
                clip.object_overlay_events = []

        logger.info(
            f"[{job_id}] Object image overlay: {applied}/{len(clips)} clips"
        )

    def _write_early_json_analisa(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        clips_with_words: dict[int, list[dict]],
        output_dir: str,
    ) -> None:
        write_early_json_analisa(job, job_id, clips, clips_with_words, output_dir)

    async def _ensure_broll_suggestions(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        clips_with_words: dict[int, list[dict]],
    ) -> None:
        """AI visual entities always; per-clip B-roll replan when broll_enabled.

        Entities feed object-image overlay + json_analisa even if B-roll off.
        """
        targets = [
            clip for clip in clips
            if clips_with_words.get(clip.rank)
        ]
        if not targets:
            return

        words_map = {
            clip.rank: clips_with_words.get(clip.rank, [])
            for clip in targets
        }
        durations = {
            clip.rank: max(0.0, clip.end - clip.start)
            for clip in targets
        }
        clip_meta = {
            clip.rank: {"hook": clip.hook or "", "reason": clip.reason or ""}
            for clip in targets
        }

        visual_entities: dict = {}
        try:
            analyzer = self._get_analyzer()
            extract_ve = getattr(analyzer, "analyze_visual_entities_for_clips", None)
            if extract_ve:
                try:
                    visual_entities = await extract_ve(
                        words_map,
                        durations,
                        clip_meta=clip_meta,
                        max_objects=10,
                    ) or {}
                except Exception as exc:
                    logger.warning(f"[{job_id}] Visual entity extract skipped: {exc}")
                    visual_entities = {}
            for clip in targets:
                ents = visual_entities.get(clip.rank) or visual_entities.get(str(clip.rank)) or []
                if ents:
                    clip.visual_entities = list(ents)
        except Exception as exc:
            logger.warning(f"[{job_id}] Visual entity extract failed: {exc}")

        # B-roll replan is optional; object overlay still has visual_entities above.
        if not job.broll_enabled:
            logger.info(
                f"[{job_id}] B-roll off — visual_entities="
                f"{sum(1 for c in targets if getattr(c, 'visual_entities', None))}"
            )
            return

        try:
            analyzer = self._get_analyzer()
            analyze = getattr(analyzer, "analyze_broll_for_clips", None)
            if not analyze:
                logger.warning(f"[{job_id}] B-roll recovery analyzer unavailable")
                return
            recovered = await analyze(
                words_map,
                durations,
                max_suggestions=2,
                clip_meta=clip_meta,
                visual_entities=visual_entities,
            )
        except TypeError:
            try:
                analyzer = self._get_analyzer()
                analyze = getattr(analyzer, "analyze_broll_for_clips", None)
                if not analyze:
                    return
                recovered = await analyze(
                    words_map,
                    durations,
                    max_suggestions=2,
                    clip_meta=clip_meta,
                )
            except Exception as exc:
                logger.warning(f"[{job_id}] B-roll recovery skipped: {exc}")
                return
        except Exception as exc:
            logger.warning(f"[{job_id}] B-roll recovery skipped: {exc}")
            return

        recovered_count = 0
        for clip in targets:
            suggestions = self._parse_broll_suggestions(
                clip.rank,
                recovered,
                durations[clip.rank],
            )
            if suggestions:
                clip.broll_suggestions = suggestions
                recovered_count += len(suggestions)

        logger.info(
            f"[{job_id}] Auto B-roll per-clip: {recovered_count} suggestions "
            f"for {sum(1 for clip in targets if clip.broll_suggestions)}/{len(targets)} clips "
            f"(visual_entities={sum(1 for c in targets if getattr(c, 'visual_entities', None))})"
        )

    async def _prepare_text_emphasis(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        clips_with_words: dict[int, list[dict]],
        output_dir: str,
        trim_results: dict[int, bool],
    ) -> None:
        """Analyze at most two emphasis events and prepare person masks."""
        job_data = job.clips_data or {}
        if not bool(job_data.get("text_emphasis_enabled", False)):
            logger.info(f"[{job_id}] AI cinematic text disabled by user")
            return

        style = normalise_text_emphasis_style(job_data.get("text_emphasis_style_config"))
        durations = {clip.rank: max(0.0, clip.end - clip.start) for clip in clips}
        min_starts = {}
        blocked_ranges = {}
        # Adaptive min_start for short clips (hook may consume most of a short clip).
        hook_duration = float((job_data.get("hook_style_config") or {}).get("duration", 3.0) or 3.0)
        for clip in clips:
            clip_dur = max(0.0, clip.end - clip.start)
            if clip.hook:
                # Leave room for at least one short emphasis event after hook.
                min_starts[clip.rank] = min(hook_duration + 0.2, max(0.3, clip_dur * 0.35))
            else:
                min_starts[clip.rank] = min(1.0, max(0.2, clip_dur * 0.08))
            blocked = [
                (suggestion.at_time, suggestion.at_time + suggestion.duration)
                for suggestion in clip.broll_suggestions
                if job.broll_enabled
            ]
            for ev in getattr(clip, 'top_overlay_events', None) or []:
                try:
                    at = float(ev.get('at_time', 0))
                    dur = float(ev.get('duration', 0))
                except (TypeError, ValueError):
                    continue
                if dur > 0:
                    blocked.append((at, at + dur))
            blocked_ranges[clip.rank] = blocked

        try:
            analyzer = self._get_analyzer()
            analyze = getattr(analyzer, "analyze_text_emphasis", None)
            if not analyze:
                logger.warning(f"[{job_id}] Text emphasis analyzer unavailable")
                return
            event_map = await analyze(
                clips_with_words,
                durations,
                style=style,
                min_start_by_clip=min_starts,
                blocked_ranges_by_clip=blocked_ranges,
                max_events=min(2, int(settings.TEXT_EMPHASIS_MAX_EVENTS)),
            )
        except Exception as exc:
            # This feature is opt-in decoration. A router failure must not make
            # an otherwise valid subtitle render fail.
            logger.warning(f"[{job_id}] AI cinematic text analysis skipped: {exc}")
            return

        from src.infrastructure.person_foreground_generator import PersonForegroundGenerator
        generator = PersonForegroundGenerator()
        total_events = 0
        for clip in clips:
            events = list(event_map.get(clip.rank, []))[:2]
            if not events or not trim_results.get(clip.rank):
                clip.text_emphasis_events = []
                continue

            # Effects that need person detection (segmentation PNG or bbox metadata)
            from src.infrastructure.text_emphasis import TRACKING_EFFECTS, map_legacy_effect
            tracking_effects = TRACKING_EFFECTS
            # Map any residual legacy effect names before FG gen / Remotion
            events = [
                {**event, "effect": map_legacy_effect(event.get("effect"))}
                for event in events
            ]
            if any(event.get("effect") in tracking_effects for event in events):
                brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                reframed_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                base_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                video_path = (
                    brolled_path if os.path.exists(brolled_path)
                    else reframed_path if os.path.exists(reframed_path)
                    else base_path
                )
                try:
                    events = await generator.generate_for_events(
                        video_path,
                        events,
                        os.path.join(output_dir, "text_emphasis", f"clip_{clip.rank:02d}"),
                        fps=30,
                        feather=int(style.get("maskFeather", settings.TEXT_EMPHASIS_MASK_FEATHER)),
                    )
                except Exception as exc:
                    logger.warning(f"[{job_id}] Person mask failed clip {clip.rank}: {exc}")
                    events = generator._downgrade_behind_events(events, "segmentation_error")
            clip.text_emphasis_events = events[:2]
            total_events += len(clip.text_emphasis_events)

        logger.info(
            f"[{job_id}] AI cinematic text prepared: {total_events} events "
            f"across {len(clips)} clips (max 2/clip)"
        )

    _build_broll_events = staticmethod(build_broll_events)

    async def _render_clips(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        clips_with_words: dict[int, list[dict]],
        creative_direction: CreativeDirection,
        output_dir: str,
        trim_results: dict[int, bool],
        reframe_data: dict,
        prosody_results: dict | None = None,
    ) -> None:
        """Run hook + subtitle via Remotion and/or HyperFrames per-engine choice."""
        from src.infrastructure.hf_style_catalog import resolve_engine

        # Load custom style configs
        hook_style_config = {}
        subtitle_style_config = {}
        if job.clips_data:
            hook_style_config = job.clips_data.get("hook_style_config", {}) or {}
            subtitle_style_config = job.clips_data.get("subtitle_style_config", {}) or {}
        text_emphasis_style_config = normalise_text_emphasis_style(
            (job.clips_data or {}).get("text_emphasis_style_config")
        )

        hook_engine = resolve_engine(hook_style_config)
        sub_engine = resolve_engine(subtitle_style_config)

        logger.info(
            f"[{job_id}] Render style: hook_engine={hook_engine} "
            f"hook_anim={hook_style_config.get('animation', 'N/A')}, "
            f"sub_engine={sub_engine} "
            f"sub_font={subtitle_style_config.get('fontFamily', 'N/A')}"
        )

        # Remotion still needed for canvas / AI text / mixed engines.
        # Pure HF (both engines hyperframes + no canvas/ai-text) can skip.
        need_canvas = bool((job.clips_data or {}).get("canvas_config")) or (
            (job.target_aspect_ratio or "") in ("16:9", "1:1")
        )
        need_ai_text = bool(getattr(job, "text_emphasis_enabled", False) or (job.clips_data or {}).get("text_emphasis_enabled"))
        pure_hf = (
            hook_engine == "hyperframes"
            and sub_engine == "hyperframes"
            and not need_canvas
            and not need_ai_text
        )

        # Pure direct path: both hook + sub use ffmpeg or skia → no Remotion/HF browser needed
        has_text_emphasis_events = any(bool(getattr(c, "text_emphasis_events", None)) for c in clips)
        pure_direct = (
            hook_engine in ("ffmpeg", "skia")
            and sub_engine in ("ffmpeg", "skia")
            and not need_canvas
            and not (need_ai_text and has_text_emphasis_events)
        )

        use_remotion = False
        if getattr(job, "use_remotion", True) is not False and not pure_hf and not pure_direct and self._remotion_adapter:
            try:
                if await self._remotion_adapter.health_check():
                    use_remotion = True
                else:
                    started = await self._remotion_adapter.start_server()
                    if started and await self._remotion_adapter.health_check():
                        use_remotion = True
            except Exception as e:
                logger.warning(f"[{job_id}] Remotion unavailable: {e}")

        if pure_hf:
            await self._render_via_hyperframes_engines(
                job, job_id, clips, clips_with_words,
                output_dir, trim_results,
                hook_style_config, subtitle_style_config,
            )
            return

        if pure_direct:
            await self._render_via_direct_engines(
                job, job_id, clips, clips_with_words,
                output_dir, trim_results,
                hook_style_config, subtitle_style_config,
                hook_engine=hook_engine, sub_engine=sub_engine,
            )
            return

        if not use_remotion:
            # Fallback: if Remotion down but HF selected for both, try HF path
            if hook_engine == "hyperframes" and sub_engine == "hyperframes":
                await self._render_via_hyperframes_engines(
                    job, job_id, clips, clips_with_words,
                    output_dir, trim_results,
                    hook_style_config, subtitle_style_config,
                )
                return
            logger.warning(
                f"[{job_id}] Remotion is unavailable (hook_engine={hook_engine}, sub_engine={sub_engine}). "
                "Gracefully falling back to direct FFmpeg/Skia rendering so hook & subtitles always render."
            )
            await self._render_via_direct_engines(
                job, job_id, clips, clips_with_words,
                output_dir, trim_results,
                hook_style_config, subtitle_style_config,
                hook_engine="ffmpeg" if hook_engine == "remotion" else hook_engine,
                sub_engine="ffmpeg" if sub_engine == "remotion" else sub_engine,
            )
            return

        await self._render_via_remotion(
            job, job_id, clips, clips_with_words, creative_direction,
            output_dir, trim_results, reframe_data,
            hook_style_config, subtitle_style_config,
            text_emphasis_style_config,
            prosody_results=prosody_results or {},
        )
        # Post-Remotion HF overlays when user picked HF for hook and/or subtitle
        if hook_engine == "hyperframes" or sub_engine == "hyperframes":
            errors = await self._apply_hf_hook_subtitle_pass(
                job, job_id, clips, clips_with_words,
                output_dir, trim_results,
                hook_style_config, subtitle_style_config,
                hook_engine=hook_engine, sub_engine=sub_engine,
            )
            if errors:
                raise RuntimeError(
                    "HyperFrames hook/subtitle render failed: "
                    + "; ".join(errors[:5])
                )
        # Post-Remotion FFmpeg / Skia overlays when user picked FFmpeg or Skia for hook and/or subtitle
        if hook_engine in ("ffmpeg", "skia") or sub_engine in ("ffmpeg", "skia"):
            direct_errors = await self._apply_direct_hook_subtitle_pass(
                job, job_id, clips, clips_with_words,
                output_dir, trim_results,
                hook_style_config, subtitle_style_config,
                hook_engine=hook_engine, sub_engine=sub_engine,
            )
            if direct_errors:
                logger.warning(f"[{job_id}] Post-Remotion direct pass warnings: {direct_errors}")

    async def _render_via_remotion(
        self, job, job_id, clips, clips_with_words, creative_direction,
        output_dir, trim_results, reframe_data,
        hook_style_config, subtitle_style_config, text_emphasis_style_config=None,
        prosody_results: dict | None = None,
    ) -> None:
        """Render all clips via Remotion server (parallel, max 2 concurrent)."""
        self._emit(job_id, 13, "remotion_render", "start")
        await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)
        initialize_clip_readiness(output_dir)

        from src.domain.interfaces_remotion import RemotionRenderConfig
        from src.infrastructure.canvas_templates import (
            build_canvas_config,
            output_resolution_for_job,
            resolution_for_aspect,
        )
        # Final TikTok canvas always 9:16; content aspect only affects video slot + template
        res = output_resolution_for_job(job.target_aspect_ratio)
        render_config = RemotionRenderConfig(
            concurrency=settings.REMOTION_CONCURRENCY,
            quality=settings.REMOTION_QUALITY,
            enable_threejs=settings.REMOTION_ENABLE_THREEJS,
            enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
            resolution=res,
        )

        # Parallel rendering: 2 clips max (prevents Remotion delayRender timeout on long clips)
        render_semaphore = asyncio.Semaphore(2)
        render_errors: list[str] = []
        prosody_map = prosody_results or {}

        async def render_one_clip(clip):
            async with render_semaphore:
                if not trim_results.get(clip.rank):
                    return

                clip_duration = max(0.0, clip.end - clip.start)
                est_render_sec = max(5, round(clip_duration * 0.8))
                self._emit_clip_progress(
                    job_id=job_id,
                    clip_rank=clip.rank,
                    total_clips=len(clips),
                    stage="Rendering Karaoke & Hook",
                    eta_seconds=est_render_sec,
                )

                brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                reframed_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                base_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                in_path = (
                    brolled_path if os.path.exists(brolled_path)
                    else reframed_path if os.path.exists(reframed_path)
                    else base_path
                )
                out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"

                clip_words_raw = clips_with_words.get(clip.rank, [])
                clip_hook = clip.hook or ""
                # words already filtered at Step 10; re-sanitize with hook window
                # so any re-entry path still keeps subtitles off during hook.
                hook_dur = float(hook_style_config.get("duration", 3.0) or 3.0)
                sub_min = hook_dur if clip_hook else 0.0
                clip_words = sanitize_subtitle_words(
                    clip_words_raw,
                    clip_duration,
                    subtitle_min_start=sub_min,
                )


                clip_reframe = reframe_data.get(clip.rank)

                from src.infrastructure.hf_style_catalog import resolve_engine as _resolve_eng
                hook_eng = _resolve_eng(hook_style_config)
                sub_eng = _resolve_eng(subtitle_style_config)
                sub_enabled = (subtitle_style_config or {}).get("enabled", True) is not False
                # Remotion only renders hook/sub when Remotion engine is specifically selected and enabled.
                remotion_hook_text = clip_hook if hook_eng == "remotion" else ""
                remotion_words = (clip_words if sub_eng == "remotion" else []) if sub_enabled else []

                hook_style = (hook_style_config.get("animation", "")
                              or creative_direction.hook_animation or "podcast_lower_third")

                cd_dict = asdict(creative_direction) if creative_direction else {}
                cd_dict["hook_style_config"] = hook_style_config
                cd_dict["subtitle_style_config"] = subtitle_style_config
                cd_dict["text_emphasis_style_config"] = (
                    text_emphasis_style_config or normalise_text_emphasis_style(None)
                )
                cd_dict["content_profile"] = (job.clips_data or {}).get("content_profile", {})
                # Canvas template/upload for 16:9 and 1:1
                canvas = (job.clips_data or {}).get("canvas_config")
                if not canvas and (job.target_aspect_ratio or "") in ("16:9", "1:1"):
                    canvas = build_canvas_config(
                        job.target_aspect_ratio,
                        background_mode=(job.clips_data or {}).get("background_mode"),
                        background_template_id=(job.clips_data or {}).get("background_template_id"),
                        background_image_url=(job.clips_data or {}).get("background_image_data_url"),
                    )
                if canvas:
                    cd_dict["canvas_config"] = canvas
                if clip_reframe and isinstance(clip_reframe, dict):
                    cd_dict["reframe_method"] = clip_reframe.get("method", "")
                    cd_dict["reframe_layout"] = clip_reframe.get("layout", "single")
                    cd_dict["subtitle_position_y"] = clip_reframe.get("subtitle_position_y")
                    for key in (
                        "layout_mode",
                        "layout_events",
                        "framing_events",
                        "transition_style",
                        "transition_duration",
                    ):
                        if clip_reframe.get(key) is not None:
                            cd_dict[key] = clip_reframe[key]
                if "transition_style" not in cd_dict and hook_style_config.get("transitionStyle"):
                    cd_dict["transition_style"] = hook_style_config.get("transitionStyle")
                if "transition_duration" not in cd_dict and hook_style_config.get("transitionDuration") is not None:
                    cd_dict["transition_duration"] = hook_style_config.get("transitionDuration")

                # Prosody punch: energy peaks → zoom_events for Remotion
                prosody = prosody_map.get(clip.rank)
                peaks = getattr(prosody, "energy_peaks", None) if prosody else None
                if peaks:
                    cd_dict["zoom_events"] = [
                        {"time": peak.time, "intensity": peak.intensity, "duration": 0.5}
                        for peak in peaks[:8]
                        if peak.time > hook_dur
                    ]

                try:
                    from src.infrastructure.clip_quality_helpers import suggest_cta
                    clip_cta = suggest_cta(clip_hook or "", getattr(clip, "reason", "") or "", clip.rank)
                except Exception:
                    clip_cta = None

                try:
                    result = await self._remotion_adapter.render_clip(
                        scene_graph={"clip_rank": clip.rank, "duration": clip.end - clip.start, "layers": []},
                        creative_direction=cd_dict,
                        video_path=in_path,
                        output_path=out_path,
                        clip_rank=clip.rank,
                        config=render_config,
                        words=remotion_words,
                        hook_text=remotion_hook_text,
                        hook_style=hook_style,
                        text_emphasis_events=clip.text_emphasis_events,
                        broll_events=self._build_broll_events(clip, job.broll_motion_style),
                        cta=clip_cta,
                    )
                    if result.success:
                        # HF-owned layers and direct passes are pending. Do not expose an
                        # incomplete Remotion base as a ready final clip.
                        has_pending_pass = (
                            hook_eng in ("hyperframes", "ffmpeg", "skia")
                            or sub_eng in ("hyperframes", "ffmpeg", "skia")
                        )
                        if not has_pending_pass:
                            # Watermark (FFmpeg overlay/drawtext) — final pass
                            await self._apply_watermark(job, clip.rank, output_dir, out_path, job_id)
                            mark_clip_ready(output_dir, clip.rank)
                            self._emit_clip_progress(
                                job_id=job_id,
                                clip_rank=clip.rank,
                                total_clips=len(clips),
                                stage="Ready",
                                eta_seconds=0,
                            )
                        logger.info(f"[{job_id}] Remotion clip {clip.rank} ({result.render_time_seconds:.1f}s)")
                    else:
                        message = f"clip {clip.rank}: {result.error_message or 'unknown Remotion error'}"
                        logger.warning(f"[{job_id}] Remotion failed {message}; falling back to direct FFmpeg rendering for clip {clip.rank}")
                        await self._render_via_direct_engines(
                            job, job_id, [clip], clips_with_words,
                            output_dir, trim_results,
                            hook_style_config, subtitle_style_config,
                            hook_engine="ffmpeg" if hook_eng == "remotion" else hook_eng,
                            sub_engine="ffmpeg" if sub_eng == "remotion" else sub_eng,
                        )
                except Exception as e:
                    message = f"clip {clip.rank}: {e}"
                    logger.warning(f"[{job_id}] Remotion error {message}; falling back to direct FFmpeg rendering for clip {clip.rank}")
                    try:
                        await self._render_via_direct_engines(
                            job, job_id, [clip], clips_with_words,
                            output_dir, trim_results,
                            hook_style_config, subtitle_style_config,
                            hook_engine="ffmpeg" if hook_eng == "remotion" else hook_eng,
                            sub_engine="ffmpeg" if sub_eng == "remotion" else sub_eng,
                        )
                    except Exception as direct_err:
                        logger.error(f"[{job_id}] Direct fallback also failed clip {clip.rank}: {direct_err}")
                        render_errors.append(f"clip {clip.rank}: {e}")

        # Launch all clips in parallel (semaphore limits to 2 concurrent)
        await asyncio.gather(*[render_one_clip(clip) for clip in clips])

        if render_errors:
            logger.warning(f"[{job_id}] Remotion had errors on {len(render_errors)} clips: {render_errors}")

        self._emit(job_id, 14, "remotion_render", "complete")

    async def _render_via_hyperframes_engines(
        self,
        job,
        job_id: str,
        clips: list,
        clips_with_words: dict,
        output_dir: str,
        trim_results: dict[int, bool],
        hook_style_config: dict,
        subtitle_style_config: dict,
    ) -> None:
        """Pure HyperFrames path: both hook+subtitle use fixed HF templates."""
        self._emit(job_id, 13, "hyperframes_render", "start")
        await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)
        initialize_clip_readiness(output_dir)
        errors = await self._apply_hf_hook_subtitle_pass(
            job, job_id, clips, clips_with_words,
            output_dir, trim_results,
            hook_style_config, subtitle_style_config,
            hook_engine="hyperframes", sub_engine="hyperframes",
            base_is_input=True,
        )
        if errors:
            raise RuntimeError(
                "HyperFrames hook/subtitle render failed: " + "; ".join(errors[:5])
            )
        self._emit(job_id, 14, "hyperframes_render", "complete")

    async def _apply_watermark(self, job, clip_rank: int, output_dir: str, final_path: str, job_id: str) -> None:
        """Apply the user-configured watermark (FFmpeg) to a finished clip, in place."""
        from src.infrastructure.watermark_renderer import apply_watermark_for_job
        await apply_watermark_for_job(
            job, clip_rank, output_dir, final_path,
            fonts_dir=getattr(self, "_fonts_dir", "assets/fonts"),
            job_id=job_id,
        )

    async def _render_via_direct_engines(
        self,
        job,
        job_id: str,
        clips: list,
        clips_with_words: dict,
        output_dir: str,
        trim_results: dict[int, bool],
        hook_style_config: dict,
        subtitle_style_config: dict,
        hook_engine: str = "ffmpeg",
        sub_engine: str = "ffmpeg",
    ) -> None:
        """Pure direct rendering (FFmpeg drawtext / Skia GPU canvas) without Remotion browser."""
        engine_label = f"{hook_engine}+{sub_engine}"
        self._emit(job_id, 13, f"{hook_engine}_render", "start")
        await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)
        initialize_clip_readiness(output_dir)

        from src.infrastructure.subtitle_renderer import SubtitleRenderer
        from src.domain.entities import SubtitleStyleConfig
        from src.infrastructure.subtitle_words import sanitize_subtitle_words

        errors: list[str] = []
        hook_style = hook_style_config.get("animation", "zoom_punch") if hook_style_config else "zoom_punch"
        hook_dur = float(hook_style_config.get("duration", 3.0) or 3.0) if hook_style_config else 3.0
        fonts_dir = getattr(self, "_fonts_dir", "assets/fonts")

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue

            # Resolve input path (brolled > reframed > trimmed)
            base_path = self._best_clip_path(output_dir, clip.rank, {})
            if not base_path or not os.path.exists(base_path):
                continue

            clip_dur = max(0.0, float(clip.end) - float(clip.start))
            final_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"

            # ── 1-Pass FFmpeg Compositor Optimization ──
            # When both hook and subtitle (or hook-only / sub-only) use FFmpeg drawtext,
            # combine Hook + Subtitle + Watermark into 1 single encode pass!
            sub_enabled = (subtitle_style_config or {}).get("enabled", True) is not False
            if hook_engine == "ffmpeg" and sub_engine == "ffmpeg":
                from src.infrastructure.unified_ffmpeg_compositor import UnifiedFFmpegCompositor
                compositor = UnifiedFFmpegCompositor(font_dir=fonts_dir)
                words_raw = clips_with_words.get(clip.rank) or []
                sub_min = hook_dur if clip.hook else 0.0
                words = sanitize_subtitle_words(words_raw, clip_dur, subtitle_min_start=sub_min) if sub_enabled else []
                watermark_cfg = (job.clips_data or {}).get("watermark_config") or {}

                success = await compositor.render_single_pass(
                    input_video=base_path,
                    output_video=final_path,
                    hook_text=clip.hook or "",
                    hook_style_config=hook_style_config,
                    words=words,
                    subtitle_style_config=subtitle_style_config,
                    watermark_config=watermark_cfg,
                )
                if success and os.path.exists(final_path):
                    logger.info(f"[{job_id}] 1-pass FFmpeg composite rendered clip {clip.rank}")
                    mark_clip_ready(output_dir, clip.rank)
                    self._emit_clip_progress(
                        job_id=job_id,
                        clip_rank=clip.rank,
                        total_clips=len(clips),
                        stage="Ready",
                        eta_seconds=0,
                    )
                    continue
                else:
                    logger.warning(f"[{job_id}] 1-pass FFmpeg composite failed clip {clip.rank}; falling back to multi-step")

            # ── Fallback / Skia Multi-Step Pipeline ──
            # ── Hook render (FFmpeg drawtext / Skia kinetic) ──
            hooked_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
            if clip.hook:
                try:
                    if hook_engine == "skia" or str(hook_style).startswith("skia_"):
                        from src.infrastructure.skia_hook_renderer import SkiaHookRenderer
                        skia_hook = SkiaHookRenderer(font_dir=fonts_dir)
                        await skia_hook.render_hook(
                            base_path, clip.hook, hooked_path,
                            hook_style=hook_style,
                            style_config=hook_style_config,
                        )
                        logger.info(f"[{job_id}] Skia hook rendered clip {clip.rank} style={hook_style}")
                    else:
                        from src.application.services import AutoClipService
                        svc = AutoClipService.__new__(AutoClipService)
                        svc._fonts_dir = fonts_dir
                        await svc._render_hook_ffmpeg(
                            base_path, clip.hook, hooked_path,
                            hook_style=hook_style,
                            style_config=hook_style_config,
                        )
                        logger.info(f"[{job_id}] {hook_engine} hook rendered clip {clip.rank}")
                except Exception as e:
                    logger.warning(f"[{job_id}] {hook_engine} hook failed clip {clip.rank}: {e}")
                    errors.append(f"hook clip {clip.rank}: {e}")
                    hooked_path = base_path
            else:
                hooked_path = base_path

            # ── Subtitle render (FFmpeg drawtext or Skia GPU canvas) ──
            words_raw = clips_with_words.get(clip.rank) or []
            sub_min = hook_dur if clip.hook else 0.0
            words = sanitize_subtitle_words(words_raw, clip_dur, subtitle_min_start=sub_min) if sub_enabled else []

            if words and sub_enabled:
                try:
                    if sub_engine == "skia":
                        from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
                        renderer = SkiaSubtitleRenderer(font_dir=fonts_dir)
                        renderer.render_subtitles(hooked_path, words, subtitle_style_config or {}, final_path)
                        logger.info(f"[{job_id}] Skia subtitle rendered clip {clip.rank}")
                    else:
                        renderer = SubtitleRenderer(font_dir=fonts_dir)
                        style_cfg = SubtitleStyleConfig.from_dict(subtitle_style_config or {})
                        renderer.render_subtitles(hooked_path, words, style_cfg, final_path)
                        logger.info(f"[{job_id}] FFmpeg subtitle rendered clip {clip.rank}")

                    # Verify final_path exists; if not created by renderer, copy hooked_path
                    if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
                        import shutil
                        shutil.copy2(hooked_path, final_path)
                except Exception as e:
                    logger.warning(f"[{job_id}] {sub_engine} subtitle failed clip {clip.rank}: {e}")
                    errors.append(f"subtitle clip {clip.rank}: {e}")
                    import shutil
                    shutil.copy2(hooked_path, final_path)
            else:
                import shutil
                shutil.copy2(hooked_path, final_path)

            # Watermark (FFmpeg overlay/drawtext) — final pass on top of everything
            await self._apply_watermark(job, clip.rank, output_dir, final_path, job_id)
            final_dir_clip = f"{output_dir}/final/clip_{clip.rank:02d}.mp4"
            if os.path.isdir(f"{output_dir}/final"):
                try:
                    import shutil
                    shutil.copy2(final_path, final_dir_clip)
                except Exception:
                    pass
            mark_clip_ready(output_dir, clip.rank)
            self._emit_clip_progress(
                job_id=job_id,
                clip_rank=clip.rank,
                total_clips=len(clips),
                stage="Ready",
                eta_seconds=0,
            )

        if errors:
            logger.warning(f"[{job_id}] {engine_label} render had {len(errors)} errors (non-fatal)")

        self._emit(job_id, 14, f"{hook_engine}_render", "complete")

    async def _render_via_ffmpeg_engines(
        self,
        job,
        job_id: str,
        clips: list,
        clips_with_words: dict,
        output_dir: str,
        trim_results: dict[int, bool],
        hook_style_config: dict,
        subtitle_style_config: dict,
    ) -> None:
        """Alias for backward compatibility."""
        await self._render_via_direct_engines(
            job, job_id, clips, clips_with_words,
            output_dir, trim_results,
            hook_style_config, subtitle_style_config,
            hook_engine="ffmpeg", sub_engine="ffmpeg",
        )

    async def _apply_direct_hook_subtitle_pass(
        self,
        job,
        job_id: str,
        clips: list,
        clips_with_words: dict,
        output_dir: str,
        trim_results: dict[int, bool],
        hook_style_config: dict,
        subtitle_style_config: dict,
        *,
        hook_engine: str,
        sub_engine: str,
    ) -> list[str]:
        """Apply FFmpeg/Skia hook and/or subtitle on top of existing Remotion final output."""
        import shutil
        from src.infrastructure.subtitle_words import sanitize_subtitle_words

        errors: list[str] = []
        fonts_dir = getattr(self, "_fonts_dir", "assets/fonts")
        hook_style = hook_style_config.get("animation", "zoom_punch") if hook_style_config else "zoom_punch"
        hook_dur = float(hook_style_config.get("duration", 3.0) or 3.0) if hook_style_config else 3.0

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            final = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            if not os.path.exists(final):
                continue

            clip_dur = max(0.0, float(clip.end) - float(clip.start))
            current = final
            tmp_hook = f"{output_dir}/clip_{clip.rank:02d}_direct_hook.mp4"
            tmp_sub = f"{output_dir}/clip_{clip.rank:02d}_direct_sub.mp4"

            try:
                # ── 1-Pass Optimization when both hook and subtitle are FFmpeg direct ──
                if hook_engine == "ffmpeg" and sub_engine == "ffmpeg":
                    from src.infrastructure.unified_ffmpeg_compositor import UnifiedFFmpegCompositor
                    compositor = UnifiedFFmpegCompositor(font_dir=fonts_dir)
                    words_raw = clips_with_words.get(clip.rank) or []
                    sub_min = hook_dur if clip.hook else 0.0
                    words = sanitize_subtitle_words(words_raw, clip_dur, subtitle_min_start=sub_min)
                    tmp_composite = f"{output_dir}/clip_{clip.rank:02d}_direct_composite.mp4"

                    success = await compositor.render_single_pass(
                        input_video=final,
                        output_video=tmp_composite,
                        hook_text=clip.hook or "",
                        hook_style_config=hook_style_config,
                        words=words,
                        subtitle_style_config=subtitle_style_config,
                    )
                    if success and os.path.exists(tmp_composite):
                        os.replace(tmp_composite, final)
                        continue
                    elif os.path.exists(tmp_composite):
                        try:
                            os.remove(tmp_composite)
                        except OSError:
                            pass

                # ── Multi-Step Direct Pass (Fallback or Skia Subtitle) ──
                # Direct hook pass (if hook_engine is ffmpeg or skia)
                if hook_engine in ("ffmpeg", "skia") and clip.hook:
                    if hook_engine == "skia" or str(hook_style).startswith("skia_"):
                        from src.infrastructure.skia_hook_renderer import SkiaHookRenderer
                        skia_hook = SkiaHookRenderer(font_dir=fonts_dir)
                        await skia_hook.render_hook(
                            current, clip.hook, tmp_hook,
                            hook_style=hook_style,
                            style_config=hook_style_config,
                        )
                    else:
                        from src.application.services import AutoClipService
                        svc = AutoClipService.__new__(AutoClipService)
                        svc._fonts_dir = getattr(self, "_fonts_dir", "/usr/share/fonts/truetype")
                        await svc._render_hook_ffmpeg(
                            current, clip.hook, tmp_hook,
                            hook_style=hook_style,
                            style_config=hook_style_config,
                        )
                    if os.path.exists(tmp_hook):
                        current = tmp_hook

                # Direct subtitle pass (if sub_engine is ffmpeg or skia)
                sub_enabled = (subtitle_style_config or {}).get("enabled", True) is not False
                if sub_engine in ("ffmpeg", "skia") and sub_enabled:
                    words_raw = clips_with_words.get(clip.rank) or []
                    sub_min = hook_dur if (clip.hook and hook_engine in ("ffmpeg", "skia", "hyperframes", "remotion")) else 0.0
                    words = sanitize_subtitle_words(words_raw, clip_dur, subtitle_min_start=sub_min)
                    if words:
                        if sub_engine == "skia":
                            from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
                            renderer = SkiaSubtitleRenderer(font_dir=fonts_dir)
                            renderer.render_subtitles(current, words, subtitle_style_config or {}, tmp_sub)
                        else:
                            from src.infrastructure.subtitle_renderer import SubtitleRenderer
                            from src.domain.entities import SubtitleStyleConfig
                            renderer = SubtitleRenderer(font_dir=fonts_dir)
                            style_cfg = SubtitleStyleConfig.from_dict(subtitle_style_config or {})
                            renderer.render_subtitles(current, words, style_cfg, tmp_sub)

                        if os.path.exists(tmp_sub):
                            current = tmp_sub

                if current != final:
                    try:
                        os.replace(current, final)
                    except OSError:
                        shutil.move(current, final)

                for p in (tmp_hook, tmp_sub):
                    if p != final and os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass

                # Watermark (FFmpeg overlay/drawtext) — final pass
                await self._apply_watermark(job, clip.rank, output_dir, final, job_id)
                final_dir_clip = f"{output_dir}/final/clip_{clip.rank:02d}.mp4"
                if os.path.isdir(f"{output_dir}/final"):
                    try:
                        shutil.copy2(final, final_dir_clip)
                    except Exception:
                        pass
                mark_clip_ready(output_dir, clip.rank)
                self._emit_clip_progress(
                    job_id=job_id,
                    clip_rank=clip.rank,
                    total_clips=len(clips),
                    stage="Ready",
                    eta_seconds=0,
                )
            except Exception as exc:
                errors.append(f"clip {clip.rank}: {exc}")
                logger.warning(f"[{job_id}] Direct hook/sub pass clip {clip.rank}: {exc}")

        return errors

    async def _apply_hf_hook_subtitle_pass(
        self,
        job,
        job_id: str,
        clips: list,
        clips_with_words: dict,
        output_dir: str,
        trim_results: dict[int, bool],
        hook_style_config: dict,
        subtitle_style_config: dict,
        *,
        hook_engine: str,
        sub_engine: str,
        base_is_input: bool = False,
    ) -> list[str]:
        """Overlay HF hook and/or subtitle templates onto clip finals.

        base_is_input=True → start from brolled/reframed/base (pure HF path).
        base_is_input=False → start from existing *_final.mp4 (post-Remotion).
        """
        from src.infrastructure.hf_style_catalog import (
            hook_events_from_text,
            resolve_hf_template,
            subtitle_events_from_words,
        )
        from src.infrastructure.hyperframes_adapter import get_hyperframes_adapter

        hf = get_hyperframes_adapter()
        # Force enable for explicit user engine choice even if polish flag off
        health = await hf.health()
        healthy = str(health.get("status") or "").lower() in {"healthy", "ok"} or health.get("http_status") == 200
        if not healthy:
            return [f"HyperFrames down: {health}"]

        hook_tpl = resolve_hf_template(hook_style_config, kind="hook")
        sub_tpl = resolve_hf_template(subtitle_style_config, kind="subtitle")
        hook_dur = float((hook_style_config or {}).get("duration", 3.0) or 3.0)
        errors: list[str] = []
        applied = 0

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            brolled = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
            reframed = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
            base = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            final = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            if base_is_input:
                in_path = (
                    brolled if os.path.exists(brolled)
                    else reframed if os.path.exists(reframed)
                    else base
                )
            else:
                in_path = final if os.path.exists(final) else (
                    brolled if os.path.exists(brolled)
                    else reframed if os.path.exists(reframed)
                    else base
                )
            if not os.path.exists(in_path):
                errors.append(f"clip {clip.rank}: input missing")
                continue

            clip_dur = max(0.0, float(clip.end) - float(clip.start))
            current = in_path
            tmp_hook = f"{output_dir}/clip_{clip.rank:02d}_hf_hook.mp4"
            tmp_sub = f"{output_dir}/clip_{clip.rank:02d}_hf_sub.mp4"

            try:
                if hook_engine == "hyperframes":
                    events = hook_events_from_text(clip.hook or "", hook_dur)
                    if events:
                        r = await hf.render_polish(
                            base_video=current,
                            events=events,
                            output_path=tmp_hook,
                            template=hook_tpl,
                            duration=clip_dur,
                            job_id=job_id,
                            clip_id=f"{clip.rank}-hook",
                            user_id=getattr(job, "user_id", None),
                            force=True,
                        )
                        if (
                            r.get("ok")
                            and r.get("mode") == "hyperframes"
                            and os.path.exists(tmp_hook)
                            and os.path.getsize(tmp_hook) > 1000
                        ):
                            current = tmp_hook
                        else:
                            logger.warning(
                                f"[{job_id}] HyperFrames hook failed on clip {clip.rank} ({r}), falling back to Skia/FFmpeg hook"
                            )
                            # Fallback to Skia / FFmpeg hook
                            fb_ok = False
                            try:
                                from src.infrastructure.skia_hook_renderer import SkiaHookRenderer
                                skia_hook = SkiaHookRenderer(font_dir=getattr(self, "_fonts_dir", "assets/fonts"))
                                hook_style = hook_style_config.get("animation", "skia_impact_badge") if hook_style_config else "skia_impact_badge"
                                await skia_hook.render_hook(
                                    current, clip.hook or "", tmp_hook,
                                    hook_style=hook_style,
                                    style_config=hook_style_config,
                                )
                                if os.path.exists(tmp_hook) and os.path.getsize(tmp_hook) > 1000:
                                    current = tmp_hook
                                    fb_ok = True
                                    logger.info(f"[{job_id}] Skia hook fallback successful for clip {clip.rank}")
                            except Exception as fb_exc:
                                logger.warning(f"[{job_id}] Skia hook fallback failed: {fb_exc}")

                            if not fb_ok:
                                errors.append(f"clip {clip.rank} hook: {r}")
                                continue

                sub_enabled = (subtitle_style_config or {}).get("enabled", True) is not False
                if sub_engine == "hyperframes" and sub_enabled:
                    words = clips_with_words.get(clip.rank, []) or []
                    # Skip words during hook window when remotion/HF hook already on
                    sub_words = []
                    for w in words:
                        if not isinstance(w, dict):
                            continue
                        try:
                            st = float(w.get("start", 0) or 0)
                        except (TypeError, ValueError):
                            st = 0.0
                        if (clip.hook or "").strip() and st < hook_dur:
                            continue
                        sub_words.append(w)
                    events = subtitle_events_from_words(sub_words)
                    if events:
                        r = await hf.render_polish(
                            base_video=current,
                            events=events,
                            output_path=tmp_sub,
                            template=sub_tpl,
                            duration=clip_dur,
                            job_id=job_id,
                            clip_id=f"{clip.rank}-sub",
                            user_id=getattr(job, "user_id", None),
                            force=True,
                        )
                        if (
                            r.get("ok")
                            and r.get("mode") == "hyperframes"
                            and os.path.exists(tmp_sub)
                            and os.path.getsize(tmp_sub) > 1000
                        ):
                            current = tmp_sub
                        else:
                            logger.warning(
                                f"[{job_id}] HyperFrames subtitle failed on clip {clip.rank} ({r}), falling back to Skia subtitle"
                            )
                            # Fallback to Skia subtitle
                            fb_ok = False
                            try:
                                from src.infrastructure.skia_subtitle_renderer import SkiaSubtitleRenderer
                                from src.infrastructure.subtitle_words import sanitize_subtitle_words
                                renderer = SkiaSubtitleRenderer(font_dir=getattr(self, "_fonts_dir", "assets/fonts"))
                                sub_min = hook_dur if clip.hook else 0.0
                                words_clean = sanitize_subtitle_words(words, clip_dur, subtitle_min_start=sub_min)
                                renderer.render_subtitles(current, words_clean, subtitle_style_config or {}, tmp_sub)
                                if os.path.exists(tmp_sub) and os.path.getsize(tmp_sub) > 1000:
                                    current = tmp_sub
                                    fb_ok = True
                                    logger.info(f"[{job_id}] Skia subtitle fallback successful for clip {clip.rank}")
                            except Exception as fb_exc:
                                logger.warning(f"[{job_id}] Skia subtitle fallback failed: {fb_exc}")

                            if not fb_ok:
                                errors.append(f"clip {clip.rank} sub: {r}")
                                continue

                if base_is_input and current == in_path:
                    # No hook/subtitle events: preserve the reusable base and
                    # still create the final output/readiness marker.
                    shutil.copy2(in_path, final)
                elif current != final:
                    try:
                        os.replace(current, final)
                    except OSError:
                        shutil.move(current, final)

                for p in (tmp_hook, tmp_sub):
                    if p != final and os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass

                # Watermark (FFmpeg overlay/drawtext) — final pass on top of everything
                await self._apply_watermark(job, clip.rank, output_dir, final, job_id)
                mark_clip_ready(output_dir, clip.rank)
                self._emit_clip_progress(
                    job_id=job_id,
                    clip_rank=clip.rank,
                    total_clips=len(clips),
                    stage="Ready",
                    eta_seconds=0,
                )
                applied += 1
                try:
                    clip.hyperframes_polish = {
                        **(getattr(clip, "hyperframes_polish", None) or {}),
                        "hook_engine": hook_engine,
                        "subtitle_engine": sub_engine,
                        "hook_template": hook_tpl if hook_engine == "hyperframes" else None,
                        "subtitle_template": sub_tpl if sub_engine == "hyperframes" else None,
                        "mode": "hyperframes",
                    }
                except Exception:
                    pass
            except Exception as exc:
                errors.append(f"clip {clip.rank}: {exc}")
                logger.warning(f"[{job_id}] HF engine pass clip {clip.rank}: {exc}")

        logger.info(f"[{job_id}] HF hook/sub pass: {applied}/{len(clips)} clips errors={len(errors)}")
        return errors

    async def _apply_hyperframes_polish(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        output_dir: str,
        trim_results: dict[int, bool],
    ) -> None:
        """Post-Remotion polish: AI visual entities → lower_third via HyperFrames.

        Non-fatal. Uses object_overlay_events (stock thumbs) or visual_entities.
        This optional pass only adds compact lower-thirds after hook/subtitle.
        """
        from src.infrastructure.hyperframes_adapter import (
            events_from_clip_ai,
            get_hyperframes_adapter,
        )

        hf = get_hyperframes_adapter()
        cfg = hf.effective_config(getattr(job, "user_id", None))
        if not cfg.get("enabled"):
            return

        health = await hf.health()
        if str(health.get("status") or "").lower() not in {"healthy", "ok"} and health.get("http_status") != 200:
            logger.warning(f"[{job_id}] HyperFrames down — polish skip: {health}")
            return

        applied = 0
        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            final = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            if not os.path.exists(final):
                continue
            clip_dur = max(0.0, float(clip.end) - float(clip.start))
            events = events_from_clip_ai(
                object_overlay_events=list(getattr(clip, "object_overlay_events", None) or []),
                visual_entities=list(getattr(clip, "visual_entities", None) or []),
                clip_hook=clip.hook or "",
                clip_duration=clip_dur,
                max_events=4,
            )
            if not events:
                continue
            out_tmp = f"{output_dir}/clip_{clip.rank:02d}_hf_polish.mp4"
            from src.infrastructure.hf_style_catalog import resolve_hf_template
            chosen_template = resolve_hf_template(cfg, kind="polish", clip_index=clip.rank)
            try:
                result = await hf.render_polish(
                    base_video=final,
                    events=events,
                    output_path=out_tmp,
                    template=chosen_template,
                    duration=clip_dur,
                    job_id=job_id,
                    clip_id=clip.rank,
                    user_id=getattr(job, "user_id", None),
                )
            except Exception as exc:
                logger.warning(f"[{job_id}] HF polish clip {clip.rank}: {exc}")
                continue
            if not result.get("ok") or not os.path.exists(out_tmp):
                logger.warning(
                    f"[{job_id}] HF polish clip {clip.rank} failed: {result}"
                )
                if os.path.exists(out_tmp):
                    try:
                        os.remove(out_tmp)
                    except OSError:
                        pass
                continue
            try:
                os.replace(out_tmp, final)
            except OSError:
                shutil.move(out_tmp, final)
            # stamp meta for UI + json_analisa
            try:
                clip.hyperframes_polish = {
                    **(getattr(clip, "hyperframes_polish", None) or {}),
                    "template": result.get("template") or cfg.get("default_template"),
                    "mode": result.get("mode"),
                    "events": len(events),
                    "labels": [e.get("label") for e in events if e.get("label")],
                }
            except Exception:
                pass
            applied += 1
            logger.info(
                f"[{job_id}] HF polish clip {clip.rank}: {len(events)} events mode={result.get('mode')}"
            )

        logger.info(f"[{job_id}] HyperFrames polish: {applied}/{len(clips)} clips")

    async def _mix_audio_clips(
        self,
        job_id: str,
        clips: list[Clip],
        creative_direction: CreativeDirection,
        output_dir: str,
        trim_results: dict[int, bool],
    ) -> None:
        """Music bed auto-duck under speech (post-Remotion). Non-fatal on miss."""
        self._emit(job_id, 13, "audio_mix", "start")
        from src.infrastructure.audio_mixer import AudioMixer, AudioMixConfig

        mood = getattr(creative_direction, "music_mood", None) or "energetic"
        if str(mood).lower() in {"none", "off", "silent"}:
            self._emit(job_id, 13, "audio_mix", "complete")
            return

        mixer = AudioMixer()
        cfg = AudioMixConfig(music_mood=str(mood), music_enabled=True)
        mixed_n = 0
        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            final_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            if not os.path.exists(final_path):
                continue
            mixed_path = f"{output_dir}/clip_{clip.rank:02d}_mixed.mp4"
            try:
                result = await asyncio.to_thread(mixer.mix_audio, final_path, mixed_path, cfg)
                if result == mixed_path and os.path.exists(mixed_path):
                    os.replace(mixed_path, final_path)
                    mark_clip_ready(output_dir, clip.rank)
                    mixed_n += 1
            except Exception as e:
                logger.debug(f"[{job_id}] audio mix clip {clip.rank}: {e}")
        logger.info(f"[{job_id}] Audio mix: {mixed_n}/{len(clips)} clips")
        self._emit(job_id, 13, "audio_mix", "complete")

    async def _render_via_ffmpeg(
        self, job, job_id, clips, clips_with_words, creative_direction,
        output_dir, trim_results, reframe_data,
        hook_style_config, subtitle_style_config,
    ) -> None:
        """Deprecated: V2 hook/subtitle must render through Remotion."""
        raise RuntimeError(
            "FFmpeg hook/subtitle fallback is disabled for V2. "
            "Use Remotion so rendered output matches the preview."
        )

    def _best_clip_path(self, output_dir: str, rank: int, reframe_data: dict = None) -> str:
        """Get best available clip path."""
        from src.pipeline.assembly import best_clip_path
        return best_clip_path(output_dir, rank, reframe_data)

    def _assemble_clips_data(
        self,
        clips: list[Clip],
        words_per_clip: dict[int, list[dict]],
        creative_direction: CreativeDirection,
        output_dir: str,
        transcript_source: str = "",
    ) -> dict:
        """Build final clips_data JSON for storage."""
        from src.pipeline.assembly import assemble_clips_data
        return assemble_clips_data(clips, words_per_clip, creative_direction, output_dir, transcript_source)

    async def _create_folder_structure(
        self, job_id, job, clips, clips_with_words, creative_direction, output_dir, trim_results,
    ) -> None:
        """Create raw/, final/, thumbnail/, json_analisa/ + slim meta index."""
        await create_folder_structure(job_id, job, clips, clips_with_words, creative_direction, output_dir, trim_results)

