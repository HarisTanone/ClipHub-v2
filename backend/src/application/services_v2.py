"""V2PipelineService — Pipeline orchestrator for transcript-based clipping.

Uses YouTube Transcript API/9router Groq Whisper/local fallback + 9router-backed
dynamic chunking and router-first word-level transcription. NO Gemini dependency.
NO MicroSlicer, NO Silero VAD.

Pipeline Steps (V2):
  1. Validate              — yt-dlp validate URL, extract duration
  2. Download              — Download full video
  3. V2 Transcript         — YouTube API → 9router Groq → local Whisper
  4. V2 Highlight Analysis — Dynamic Chunking → 9router LLM
  5. Prepare Clips         — Time padding, overlap detection
  6. Aspect Ratio Router   — Set pipeline flags
  7. Trim Clips            — FFmpeg precise re-encode
  8. YOLO Seg + Reframe    — Conditional
  9. Word-Level Transcription — 9router Groq → Faster-Whisper fallback
  10. Build Subtitle Data  — Validate & format words for rendering
  11. Auto B-roll        — Optional visual overlay; audio timeline unchanged
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

if TYPE_CHECKING:
    from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
    from src.infrastructure.overlap_detector import OverlapDetector
    from src.infrastructure.resource_monitor import ResourceMonitor
    from src.domain.interfaces_remotion import IRemotionRenderer

logger = logging.getLogger(__name__)


class V2PipelineService:
    """V2 Pipeline orchestrator for non-premium users.

    Architecture: YouTube API/9router Groq/local fallback → 9router LLM → Trim →
    router-first WordLevelTranscriber → render pipeline.
    NO Gemini. NO MicroSlicer. NO Silero VAD.
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
            else:
                cached_analysis = cache.load_analysis(video_id, "v2") if video_id else None
            if not direct_mode and cached_analysis:
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
            if direct_mode:
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
            merged_clips_data = dict(job.clips_data or {})
            merged_clips_data.update(pending_clips_data)
            job.clips_data = merged_clips_data
            await self._repo.update_clips_data(job_id, merged_clips_data)
            self._emit(job_id, 5, "prepare_clips", "complete")

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
            if flags.yolo_enabled and self._yolo_reframe:
                reframe_style = (job.clips_data or {}).get("hook_style_config", {})
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    try:
                        result = await self._yolo_reframe.process(
                            in_path,
                            out_path,
                            job.target_aspect_ratio,
                            flags.autogrid_enabled,
                            content_profile=(job.clips_data or {}).get("content_profile", {}),
                            transition_style=reframe_style.get("transitionStyle", "cut"),
                            transition_duration=reframe_style.get("transitionDuration", 0.35),
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
            logger.info(
                f"[{job_id}] Word-level: "
                f"{sum(1 for w in words_per_clip.values() if w)}/{len(trimmed_ranks)} clips with words, "
                f"{sum(len(w) for w in words_per_clip.values())} total words"
            )
            self._emit(job_id, 9, "word_level", "complete")

            # ═══ Step 10: Build Subtitle Data (words already 0-based) ═══
            self._emit(job_id, 10, "highlights", "start")
            await self._repo.update_status(job_id, JobStatus.HIGHLIGHTING)
            clips_with_words: dict[int, list[dict]] = {}
            for clip in clips:
                raw_words = words_per_clip.get(clip.rank, [])
                clip_duration = round(clip.end - clip.start, 3)
                valid_words = sanitize_subtitle_words(raw_words, clip_duration)
                clips_with_words[clip.rank] = valid_words
                if valid_words:
                    logger.info(
                        f"v2_words clip {clip.rank}: {len(valid_words)} words, "
                        f"last='{valid_words[-1]['word']}' @ {valid_words[-1]['start']:.1f}s, "
                        f"clip_duration={clip_duration:.1f}s"
                    )
            self._emit(job_id, 10, "highlights", "complete")

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
            )

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

        except Exception as e:
            logger.exception(f"[{job_id}] V2 pipeline FAILED: {e}")
            await self._repo.update_status(
                job_id, JobStatus.FAILED,
                f"V2 pipeline error: {str(e)[:500]}"
            )

    # ─── V2-Specific Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_direct_edit_analysis(video_duration: float, custom_hook: object = None):
        """Build the direct-edit result without invoking the AI analyzer."""
        from src.domain.entities import HighlightAnalysisResult, HighlightCandidate

        hook = str(custom_hook or "").strip()
        return HighlightAnalysisResult(
            clips=[HighlightCandidate(
                rank=1,
                start=0.0,
                end=video_duration,
                score=100,
                hook=hook,
                reason="Direct full-video edit",
            )],
            creative_direction={},
            broll_suggestions={},
            model_used="direct",
            chunks_processed=0,
        )

    def _prepare_clips_from_v2(
        self, highlights: list, broll_map: dict, video_duration: float
    ) -> list[Clip]:
        """Convert V2 HighlightCandidate list → Clip entities."""
        clips = []
        for h in highlights:
            start = max(0, h.start - 0.5)
            end = min(video_duration, h.end + 1.0)
            if end - start < settings.MIN_CLIP_DURATION:
                continue

            broll_suggestions = self._parse_broll_suggestions(
                h.rank,
                broll_map,
                end - start,
            )

            clips.append(Clip(
                rank=h.rank,
                score=h.score,
                start=start,
                end=end,
                hook=h.hook,
                reason=h.reason,
                broll_suggestions=broll_suggestions,
            ))
        return clips

    @staticmethod
    def _parse_broll_suggestions(
        clip_rank: int,
        broll_map: dict,
        clip_duration: float,
    ) -> list[BRollSuggestion]:
        """Convert and constrain AI B-roll output to a clip-safe timeline."""
        if not isinstance(broll_map, dict) or clip_duration <= 1.0:
            return []

        raw_suggestions = broll_map.get(str(clip_rank), [])
        if not isinstance(raw_suggestions, list):
            return []

        allowed_templates = {
            "word_pop_typography",
            "line_reveal_typography",
            "particle_text_burst",
        }
        parsed: list[BRollSuggestion] = []
        for raw in raw_suggestions[:3]:
            if not isinstance(raw, dict):
                continue
            keyword = " ".join(str(raw.get("keyword") or "").split())[:80]
            if not keyword:
                continue
            try:
                at_time = float(raw.get("at_time", 0))
                duration = float(raw.get("duration", 2.0))
            except (TypeError, ValueError):
                continue

            safe_start = 3.0 if clip_duration > 4.0 else 0.0
            at_time = max(safe_start, at_time)
            if at_time >= clip_duration - 1.0:
                continue
            duration = min(3.0, max(1.5, duration), clip_duration - at_time)
            if duration < 1.0:
                continue

            try:
                visual_cat = VisualCategory(raw.get("visual_category", "footage"))
            except (ValueError, TypeError):
                visual_cat = VisualCategory.FOOTAGE
            template = str(raw.get("template") or "word_pop_typography")
            if template not in allowed_templates:
                template = "word_pop_typography"

            parsed.append(BRollSuggestion(
                at_time=round(at_time, 3),
                keyword=keyword,
                template=template,
                duration=round(duration, 3),
                visual_category=visual_cat,
            ))
        return parsed

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

        suggestions = [
            suggestion
            for clip in clips
            for suggestion in clip.broll_suggestions
        ]
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
                await self._asset_fetcher.fetch_assets(suggestions, creative_direction)
            except Exception as exc:
                # The injector can still render its typography fallback.
                logger.warning(f"[{job_id}] B-roll asset search failed; using fallback: {exc}")

        # ─── Step 10.6: Splice B-Roll Footage (video track replacement) ───────
        if settings.BROLL_SPLICE_ENABLED:
            splice_count = 0
            for clip in clips:
                if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                    continue

                # Collect splice segments from suggestions
                splice_segments = [
                    s.splice_segment for s in clip.broll_suggestions
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
                # Cleanup intermediate footage files
                footage_dir = os.path.join(output_dir, "broll_footage")
                if os.path.exists(footage_dir):
                    import shutil
                    shutil.rmtree(footage_dir, ignore_errors=True)

        # ─── Step 10.6b: Splice legacy video assets (Pexels/Pixabay direct) ──
        # If ClipScout didn't provide splice_segments but legacy fetcher got video
        # assets, also splice them full-frame (not overlay).
        if settings.BROLL_SPLICE_ENABLED:
            from src.infrastructure.footage_processor import FootageProcessor
            legacy_processor = FootageProcessor()

            for clip in clips:
                if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                    continue
                brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
                if os.path.exists(brolled_path):
                    continue  # Already spliced by ClipScout path

                # Collect video assets that have asset_result but no splice_segment
                video_suggestions = [
                    s for s in clip.broll_suggestions
                    if (s.asset_result
                        and not s.asset_result.is_fallback
                        and s.asset_result.asset_format == "video"
                        and not s.splice_segment
                        and os.path.exists(s.asset_result.local_path))
                ]
                if not video_suggestions:
                    continue

                # Process each legacy video asset to 1080x1920 and create SpliceSegment
                legacy_segments = []
                for idx, s in enumerate(video_suggestions):
                    processed = await legacy_processor.process(
                        raw_path=s.asset_result.local_path,
                        target_duration=s.duration,
                        clip_rank=clip.rank,
                        index=idx,
                        output_dir=os.path.join(output_dir, "broll_footage"),
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
                        )
                        if result_path == splice_output and os.path.exists(splice_output):
                            os.rename(splice_output, brolled_path)
                            logger.info(f"[{job_id}] Legacy video spliced clip {clip.rank}")
                    except Exception as exc:
                        logger.warning(f"[{job_id}] Legacy video splice failed clip {clip.rank}: {exc}")

        # ─── Overlay fallback: only for non-video assets (images, gif, drawtext) ─
        applied_count = 0
        for clip in clips:
            if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                continue

            brolled_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
            reframed_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
            base_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            # Skip overlay injection if splice already produced the brolled file
            if os.path.exists(brolled_path):
                applied_count += 1
                continue
            input_path = reframed_path if os.path.exists(reframed_path) else base_path
            output_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"

            # Filter out video suggestions (already handled by splice above)
            # Only pass non-video suggestions to overlay injector
            non_video_suggestions = [
                s for s in clip.broll_suggestions
                if not (s.asset_result
                        and not s.asset_result.is_fallback
                        and s.asset_result.asset_format == "video")
            ]
            if not non_video_suggestions:
                continue

            try:
                result_path = await self._broll_injector.inject(
                    input_path,
                    non_video_suggestions,
                    output_path,
                )
                if result_path == output_path and os.path.exists(output_path):
                    applied_count += 1
            except Exception as exc:
                logger.warning(f"[{job_id}] B-roll overlay failed clip {clip.rank}: {exc}")

        logger.info(
            f"[{job_id}] Auto B-roll complete: {applied_count}/{len(clips)} clips applied"
        )
        self._emit(job_id, 11, "broll", "complete")

    async def _ensure_broll_suggestions(
        self,
        job: Job,
        job_id: str,
        clips: list[Clip],
        clips_with_words: dict[int, list[dict]],
    ) -> None:
        """Fill only missing B-roll plans without replacing valid AI output."""
        if not job.broll_enabled:
            return

        missing = [clip for clip in clips if not clip.broll_suggestions]
        if not missing:
            return

        missing_words = {
            clip.rank: clips_with_words.get(clip.rank, [])
            for clip in missing
        }
        durations = {
            clip.rank: max(0.0, clip.end - clip.start)
            for clip in missing
        }
        try:
            analyzer = self._get_analyzer()
            analyze = getattr(analyzer, "analyze_broll_for_clips", None)
            if not analyze:
                logger.warning(f"[{job_id}] B-roll recovery analyzer unavailable")
                return
            recovered = await analyze(
                missing_words,
                durations,
                max_suggestions=2,
            )
        except Exception as exc:
            logger.warning(f"[{job_id}] B-roll recovery skipped: {exc}")
            return

        recovered_count = 0
        for clip in missing:
            suggestions = self._parse_broll_suggestions(
                clip.rank,
                recovered,
                durations[clip.rank],
            )
            if suggestions:
                clip.broll_suggestions = suggestions
                recovered_count += len(suggestions)

        logger.info(
            f"[{job_id}] Auto B-roll recovery: {recovered_count} suggestions "
            f"for {sum(1 for clip in missing if clip.broll_suggestions)}/{len(missing)} clips"
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
        hook_duration = float((job_data.get("hook_style_config") or {}).get("duration", 3.0) or 3.0)
        for clip in clips:
            min_starts[clip.rank] = hook_duration + 0.35 if clip.hook else 1.0
            blocked_ranges[clip.rank] = [
                (suggestion.at_time, suggestion.at_time + suggestion.duration)
                for suggestion in clip.broll_suggestions
                if job.broll_enabled
            ]

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

            if any(event.get("effect") == "behind_person" for event in events):
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
    ) -> None:
        """Run hook + subtitle render via Remotion only."""
        # Load custom style configs
        hook_style_config = {}
        subtitle_style_config = {}
        if job.clips_data:
            hook_style_config = job.clips_data.get("hook_style_config", {})
            subtitle_style_config = job.clips_data.get("subtitle_style_config", {})
        text_emphasis_style_config = normalise_text_emphasis_style(
            (job.clips_data or {}).get("text_emphasis_style_config")
        )

        logger.info(
            f"[{job_id}] Render style: hook_anim={hook_style_config.get('animation', 'N/A')}, "
            f"hook_color={hook_style_config.get('color', 'N/A')}, "
            f"hook_glow={hook_style_config.get('glowEnabled', 'N/A')}, "
            f"hook_config_keys={list(hook_style_config.keys()) if hook_style_config else '[]'}, "
            f"sub_font={subtitle_style_config.get('fontFamily', 'N/A')}"
        )

        # ═══ Remotion is required for hook + subtitle fidelity ═══
        use_remotion = False
        if self._remotion_adapter:
            try:
                if await self._remotion_adapter.health_check():
                    use_remotion = True
                else:
                    started = await self._remotion_adapter.start_server()
                    if started and await self._remotion_adapter.health_check():
                        use_remotion = True
            except Exception as e:
                logger.warning(f"[{job_id}] Remotion unavailable: {e}")

        if not use_remotion:
            raise RuntimeError(
                "Remotion is required for hook/subtitle rendering. "
                "FFmpeg fallback is disabled so final output matches preview."
            )

        await self._render_via_remotion(
            job, job_id, clips, clips_with_words, creative_direction,
            output_dir, trim_results, reframe_data,
            hook_style_config, subtitle_style_config,
            text_emphasis_style_config,
        )

    async def _render_via_remotion(
        self, job, job_id, clips, clips_with_words, creative_direction,
        output_dir, trim_results, reframe_data,
        hook_style_config, subtitle_style_config, text_emphasis_style_config=None,
    ) -> None:
        """Render all clips via Remotion server (parallel, max 2 concurrent)."""
        self._emit(job_id, 13, "remotion_render", "start")
        await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)
        initialize_clip_readiness(output_dir)

        from src.domain.interfaces_remotion import RemotionRenderConfig
        render_config = RemotionRenderConfig(
            concurrency=settings.REMOTION_CONCURRENCY,
            quality=settings.REMOTION_QUALITY,
            enable_threejs=settings.REMOTION_ENABLE_THREEJS,
            enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
        )

        # Parallel rendering: 2 clips max (prevents Remotion delayRender timeout on long clips)
        render_semaphore = asyncio.Semaphore(2)
        render_errors: list[str] = []

        async def render_one_clip(clip):
            async with render_semaphore:
                if not trim_results.get(clip.rank):
                    return

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
                clip_duration = max(0.0, clip.end - clip.start)
                clip_words = sanitize_subtitle_words(clip_words_raw, clip_duration)

                clip_reframe = reframe_data.get(clip.rank)

                hook_style = (hook_style_config.get("animation", "")
                              or creative_direction.hook_animation or "podcast_lower_third")

                cd_dict = asdict(creative_direction) if creative_direction else {}
                cd_dict["hook_style_config"] = hook_style_config
                cd_dict["subtitle_style_config"] = subtitle_style_config
                cd_dict["text_emphasis_style_config"] = (
                    text_emphasis_style_config or normalise_text_emphasis_style(None)
                )
                cd_dict["content_profile"] = (job.clips_data or {}).get("content_profile", {})
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

                try:
                    result = await self._remotion_adapter.render_clip(
                        scene_graph={"clip_rank": clip.rank, "duration": clip.end - clip.start, "layers": []},
                        creative_direction=cd_dict,
                        video_path=in_path,
                        output_path=out_path,
                        clip_rank=clip.rank,
                        config=render_config,
                        words=clip_words,
                        hook_text=clip_hook,
                        hook_style=hook_style,
                        text_emphasis_events=clip.text_emphasis_events,
                    )
                    if result.success:
                        mark_clip_ready(output_dir, clip.rank)
                        logger.info(f"[{job_id}] Remotion clip {clip.rank} ({result.render_time_seconds:.1f}s)")
                    else:
                        message = f"clip {clip.rank}: {result.error_message or 'unknown Remotion error'}"
                        logger.error(f"[{job_id}] Remotion failed {message}")
                        render_errors.append(message)
                except Exception as e:
                    message = f"clip {clip.rank}: {e}"
                    logger.exception(f"[{job_id}] Remotion error {message}")
                    render_errors.append(message)

        # Launch all clips in parallel (semaphore limits to 2 concurrent)
        await asyncio.gather(*[render_one_clip(clip) for clip in clips])

        if render_errors:
            raise RuntimeError(
                "Remotion hook/subtitle render failed; FFmpeg fallback is disabled: "
                + "; ".join(render_errors[:5])
            )

        self._emit(job_id, 14, "remotion_render", "complete")

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

    def _best_clip_path(self, output_dir: str, rank: int, reframe_data: dict) -> str:
        """Get best available clip path."""
        candidates = [
            f"{output_dir}/clip_{rank:02d}_reframed.mp4",
            f"{output_dir}/clip_{rank:02d}.mp4",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return f"{output_dir}/clip_{rank:02d}.mp4"

    def _assemble_clips_data(
        self,
        clips: list[Clip],
        words_per_clip: dict[int, list[dict]],
        creative_direction: CreativeDirection,
        output_dir: str,
        transcript_source: str = "",
    ) -> dict:
        """Build final clips_data JSON for storage."""
        clips_output = []
        for clip in clips:
            final_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            if not os.path.exists(final_path):
                for suffix in ["_subtitled", "_hooked", "_reframed", ""]:
                    alt = f"{output_dir}/clip_{clip.rank:02d}{suffix}.mp4"
                    if os.path.exists(alt):
                        final_path = alt
                        break

            words = words_per_clip.get(clip.rank, [])
            broll_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
            clips_output.append({
                "rank": clip.rank,
                "score": clip.score,
                "start": clip.start,
                "end": clip.end,
                "duration": round(clip.end - clip.start, 2),
                "hook": clip.hook,
                "reason": clip.reason,
                "output_path": final_path,
                "words": words,
                "word_count": len(words),
                "has_subtitles": len(words) > 0,
                "broll_applied": os.path.exists(broll_path),
                "broll_suggestions": [
                    {
                        "at_time": suggestion.at_time,
                        "keyword": suggestion.keyword,
                        "template": suggestion.template,
                        "duration": suggestion.duration,
                        "visual_category": (
                            suggestion.visual_category.value
                            if isinstance(suggestion.visual_category, VisualCategory)
                            else str(suggestion.visual_category)
                        ),
                        "asset_source": (
                            suggestion.asset_result.source_api
                            if suggestion.asset_result else ""
                        ),
                    }
                    for suggestion in clip.broll_suggestions
                ],
                "text_emphasis_events": [
                    {
                        key: value
                        for key, value in event.items()
                        if key != "foreground_frames"
                    }
                    for event in clip.text_emphasis_events[:2]
                ],
            })

        return {
            "pipeline_version": "v2",
            "transcript_source": transcript_source,
            "creative_direction": asdict(creative_direction),
            "clips": clips_output,
        }

    async def _create_folder_structure(
        self, job_id, job, clips, clips_with_words, creative_direction, output_dir, trim_results,
    ) -> None:
        """Create organized folder structure: raw/, final/, thumbnail/, meta JSON."""
        import subprocess
        import shutil
        import json as json_mod

        thumb_dir = f"{output_dir}/thumbnail"
        raw_dir = f"{output_dir}/raw"
        final_dir = f"{output_dir}/final"
        os.makedirs(thumb_dir, exist_ok=True)
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(final_dir, exist_ok=True)

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            rank = clip.rank

            final_path = f"{output_dir}/clip_{rank:02d}_final.mp4"
            thumb_path = f"{thumb_dir}/clip_{rank:02d}.jpg"
            if os.path.exists(final_path):
                thumb_cmd = [
                    "ffmpeg", "-y", "-i", final_path,
                    "-ss", "1", "-frames:v", "1",
                    "-vf", "scale=360:-1", "-q:v", "3",
                    thumb_path,
                ]
                try:
                    await asyncio.to_thread(subprocess.run, thumb_cmd, capture_output=True, text=True, timeout=15)
                except Exception:
                    pass

            raw_src = f"{output_dir}/clip_{rank:02d}.mp4"
            if os.path.exists(raw_src):
                shutil.copy2(raw_src, f"{raw_dir}/clip_{rank:02d}.mp4")

            if os.path.exists(final_path):
                shutil.copy2(final_path, f"{final_dir}/clip_{rank:02d}.mp4")

        meta = {
            "job_id": job_id,
            "youtube_url": job.youtube_url,
            "aspect_ratio": job.target_aspect_ratio,
            "clips_total": len(clips),
            "clips_success": sum(1 for c in clips if trim_results.get(c.rank)),
            "created_at": str(job.created_at) if job.created_at else None,
            "clips": [
                {
                    "rank": c.rank, "start": c.start, "end": c.end,
                    "duration": c.end - c.start, "hook": c.hook, "score": c.score,
                    "words": clips_with_words.get(c.rank, []),
                }
                for c in clips
            ],
        }
        meta_path = f"{output_dir}/meta_{job_id}.json"
        with open(meta_path, "w") as f:
            json_mod.dump(meta, f, indent=2, default=str)

        logger.info(f"[{job_id}] Folder structure created")
