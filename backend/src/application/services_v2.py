"""V2PipelineService — Pipeline orchestrator for non-premium users.

Uses GroqTranscriber (YouTube API → Groq Whisper) + GroqAnalyzer (Dynamic Chunking)
+ MicroSlicer + SelectiveWhisper (local Faster-Whisper) + Silero VAD.
NO Gemini dependency.

Pipeline Steps (V2):
  1. Validate              — yt-dlp validate URL, extract duration
  2. Download              — Download full video
  3. V2 Transcript         — YouTube API (primary) → Groq Whisper (fallback)
  4. V2 Highlight Analysis — Dynamic Chunking → Groq LLM → Ollama fallback
  4.5 Micro-Slice          — Extract audio per highlight (±3s padding)
  4.7 Selective Whisper    — Local Faster-Whisper word-level on micro-slices
  4.9 VAD Refinement       — Silero VAD natural cut boundaries
  5. Prepare Clips         — Time padding, overlap detection
  6. Aspect Ratio Router   — Set pipeline flags
  7. Trim Clips            — FFmpeg precise re-encode
  8. YOLO Seg + Reframe    — Conditional
  10+ Hook, Subtitle, Encode (REUSE from V1)
"""
import asyncio
import logging
import os
import time
from dataclasses import asdict
from typing import Optional, TYPE_CHECKING

from src.config import settings
from src.domain.entities import (
    AudioSlice, BRollSuggestion, Clip, CreativeDirection, Job, JobStatus,
    PipelineFlags, VisualCategory, Word,
)
from src.domain.interfaces import (
    IAspectRatioRouter,
    IAssetFetcher,
    IBRollInjector,
    IBrowserRenderEngine,
    IDownloader,
    IGroqAnalyzer,
    IGroqTranscriber,
    IJobRepository,
    IMicroSlicer,
    IRenderer,
    ISubtitleRenderer,
    IWhisperLocal,
    IYoloReframeEngine,
)
from src.infrastructure.silero_vad import SileroVADProcessor

if TYPE_CHECKING:
    from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
    from src.infrastructure.overlap_detector import OverlapDetector
    from src.infrastructure.resource_monitor import ResourceMonitor
    from src.domain.interfaces_remotion import IRemotionRenderer

logger = logging.getLogger(__name__)


class V2PipelineService:
    """V2 Pipeline orchestrator for non-premium users.

    Architecture: YouTube API → Groq Whisper → Groq LLM → MicroSlicer →
    Faster-Whisper (local) → Silero VAD → existing render pipeline.
    NO Gemini. NO per-clip cloud Whisper.
    """

    def __init__(
        self,
        job_repo: IJobRepository,
        downloader: IDownloader,
        renderer: IRenderer,
        whisper_local: IWhisperLocal,
        # ─── V2 specific components ──────────────────────────────────
        silero_vad: Optional[SileroVADProcessor] = None,
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
        self._vad = silero_vad or SileroVADProcessor()
        self._transcriber = None   # GroqTranscriber — lazy
        self._analyzer = None      # GroqAnalyzer — lazy
        self._micro_slicer = None  # MicroSlicer — lazy
        self._selective_whisper = None  # SelectiveWhisperTranscriber — lazy

        # Shared components
        self._aspect_router = aspect_ratio_router
        self._yolo_reframe = yolo_reframe_engine
        self._browser_render = browser_render_engine
        self._broll_injector = broll_injector
        self._subtitle_renderer = subtitle_renderer
        self._asset_fetcher = asset_fetcher

        # Infrastructure
        self._sse = sse_emitter
        self._overlap_detector = overlap_detector
        self._resource_monitor = resource_monitor

        # Remotion
        self._remotion_adapter = remotion_adapter

    # ─── Lazy Component Initialization ────────────────────────────────────────

    def _get_transcriber(self):
        """Lazy-init GroqTranscriber (TAHAP 1)."""
        if self._transcriber is None:
            from src.infrastructure.groq_transcriber import GroqTranscriber
            self._transcriber = GroqTranscriber()
        return self._transcriber

    def _get_analyzer(self):
        """Lazy-init GroqAnalyzer (TAHAP 2)."""
        if self._analyzer is None:
            from src.infrastructure.groq_analyzer import GroqAnalyzer
            self._analyzer = GroqAnalyzer()
        return self._analyzer

    def _get_micro_slicer(self):
        """Lazy-init MicroSlicer (TAHAP 3)."""
        if self._micro_slicer is None:
            from src.infrastructure.micro_slicer import MicroSlicer
            self._micro_slicer = MicroSlicer()
        return self._micro_slicer

    def _get_selective_whisper(self):
        """Lazy-init SelectiveWhisperTranscriber (TAHAP 4)."""
        if self._selective_whisper is None:
            from src.infrastructure.selective_whisper import SelectiveWhisperTranscriber
            self._selective_whisper = SelectiveWhisperTranscriber(self._whisper)
        return self._selective_whisper

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

    # ─── Main Pipeline ────────────────────────────────────────────────────────

    async def run_pipeline(self, job: Job) -> None:
        """Execute the V2 pipeline for a job.

        Flow:
        1. Validate → 2. Download → 3. YouTube/Groq Transcript →
        4. Groq LLM Chunked Analysis → 4.5. MicroSlice → 4.7. Selective Whisper →
        4.9. VAD → 5. Prepare Clips → 6. Route → 7. Trim → 8. YOLO →
        10+. Hook/Subtitle/Encode
        """
        job_id = job.job_id
        url = job.youtube_url
        video_path = f"{settings.DOWNLOAD_DIR}/{job_id}.mp4"
        output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
        os.makedirs(output_dir, exist_ok=True)
        pipeline_start = time.time()

        # ─── Cache setup ──────────────────────────────────────────────
        from src.infrastructure.cache_manager import CacheManager
        cache = CacheManager()
        video_id = cache.extract_video_id(url)
        force_reprocess = bool(job.clips_data and job.clips_data.get("force_reprocess"))

        # Re-read clips_data from DB for style configs
        fresh_job = await self._repo.get_by_job_id(job_id)
        if fresh_job and fresh_job.clips_data:
            job.clips_data = fresh_job.clips_data

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
            valid, error_or_title, duration = await self._downloader.validate_url(url)
            if not valid:
                await self._repo.update_status(job_id, JobStatus.FAILED, error_or_title)
                return
            job.video_duration = duration
            if error_or_title and valid:
                try:
                    await self._repo.update_video_title(job_id, error_or_title)
                except Exception:
                    pass
            self._emit(job_id, 1, "validate", "complete")

            # ═══ Step 2: Download (SKIP if cached) ═══
            cached_video = cache.get_video_path(video_id) if video_id else None
            if cached_video:
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
                    transcriber = self._get_transcriber()
                    transcript_result = await transcriber.transcribe(url, duration)
                except Exception as e:
                    await self._repo.update_status(
                        job_id, JobStatus.FAILED, f"Transcription gagal: {e}"
                    )
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
            cached_analysis = cache.load_analysis(video_id, "v2") if video_id else None
            if cached_analysis:
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
            else:
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

            # ═══ Step 4.5: TAHAP 3 — Micro-Slicing ═══
            self._emit(job_id, "4.5", "v2_micro_slicing", "start")
            await self._repo.update_status(job_id, JobStatus.V2_MICRO_SLICING)
            micro_slicer = self._get_micro_slicer()
            audio_slices: list[AudioSlice] = []
            try:
                highlights_for_slicer = [
                    {"rank": c.rank, "start": c.start, "end": c.end}
                    for c in analysis_result.clips
                ]
                audio_slices = await micro_slicer.slice_audio(
                    video_path, highlights_for_slicer, output_dir, duration
                )
                logger.info(
                    f"[{job_id}] Micro-sliced: {len(audio_slices)}/{len(analysis_result.clips)} clips"
                )
            except Exception as e:
                logger.warning(f"[{job_id}] Micro-slicing failed: {e} — will skip selective whisper")
            self._emit(job_id, "4.5", "v2_micro_slicing", "complete")

            # ═══ Step 4.7: TAHAP 4 — Selective Faster-Whisper (word-level) ═══
            self._emit(job_id, "4.7", "v2_selective_whisper", "start")
            await self._repo.update_status(job_id, JobStatus.V2_WORD_TRANSCRIBING)
            words_per_clip: dict[int, list[Word]] = {}
            if audio_slices:
                try:
                    selective_whisper = self._get_selective_whisper()
                    words_per_clip = await selective_whisper.transcribe_all_clips(
                        audio_slices, max_parallel=settings.MAX_WHISPER_PARALLEL
                    )
                except Exception as e:
                    logger.warning(f"[{job_id}] Selective Whisper failed: {e}")
            logger.info(
                f"[{job_id}] Selective Whisper: "
                f"{sum(1 for w in words_per_clip.values() if w)}/{len(analysis_result.clips)} clips with words, "
                f"{sum(len(w) for w in words_per_clip.values())} total words"
            )
            self._emit(job_id, "4.7", "v2_selective_whisper", "complete")

            # ═══ Step 4.9: TAHAP 5 — Silero VAD Refinement ═══
            self._emit(job_id, "4.9", "v2_vad_refine", "start")
            await self._repo.update_status(job_id, JobStatus.V2_VAD_REFINING)
            vad_applied = 0
            for audio_slice in audio_slices:
                try:
                    from src.domain.entities import VADResult
                    vad_result = await self._vad.refine_clip_boundaries(
                        audio_path=audio_slice.audio_path,
                        original_start=audio_slice.original_start,
                        original_end=audio_slice.original_end,
                        padded_start=audio_slice.padded_start,
                    )
                    if not vad_result.used_fallback:
                        # Update the highlight timestamps with VAD-refined boundaries
                        for clip_candidate in analysis_result.clips:
                            if clip_candidate.rank == audio_slice.clip_rank:
                                clip_candidate.start = vad_result.final_start
                                clip_candidate.end = vad_result.final_end
                                vad_applied += 1
                                break
                except Exception as e:
                    logger.debug(f"[{job_id}] VAD clip {audio_slice.clip_rank}: {e}")
            logger.info(f"[{job_id}] VAD refinement: {vad_applied}/{len(audio_slices)} clips adjusted")
            self._emit(job_id, "4.9", "v2_vad_refine", "complete")

            # Cleanup micro-slice audio files
            try:
                micro_slicer.cleanup_slices(audio_slices)
            except Exception:
                pass

            # ═══ Step 5: Prepare Clips ═══
            self._emit(job_id, 5, "prepare_clips", "start")
            await self._repo.update_status(job_id, JobStatus.PREPARING)
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
            # so downstream steps (trim, reframe, render) use contiguous ranks
            rank_mapping: dict[int, int] = {}  # original_rank → new_sequential_rank
            for i, clip in enumerate(clips):
                rank_mapping[clip.rank] = i + 1
                clip.rank = i + 1

            clips_count = len(clips)
            await self._repo.update_clips_count(job_id, clips_count, 0, 0)
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
            trim_results = await self._trim_all_clips(job_id, video_path, clips, output_dir)
            self._emit(job_id, 7, "trim", "complete")

            # ═══ Step 8: YOLO Seg + Reframe ═══
            self._emit(job_id, 8, "yolo_reframe", "start")
            await self._repo.update_status(job_id, JobStatus.SEGMENTING)
            reframe_data = {}
            if flags.yolo_enabled and self._yolo_reframe:
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    try:
                        result = await self._yolo_reframe.process(
                            in_path, out_path, job.target_aspect_ratio, flags.autogrid_enabled
                        )
                        reframe_data[clip.rank] = result
                    except Exception as e:
                        logger.warning(f"[{job_id}] YOLO reframe failed clip {clip.rank}: {e}")
            self._emit(job_id, 8, "yolo_reframe", "complete")

            # Center-crop fallback for 9:16
            if flags.yolo_enabled and not reframe_data and job.target_aspect_ratio == "9:16":
                import subprocess as _sp
                logger.info(f"[{job_id}] Applying center-crop fallback for 9:16")
                for clip in clips:
                    if not trim_results.get(clip.rank):
                        continue
                    in_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                    out_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                    crop_cmd = [
                        "ffmpeg", "-y", "-i", in_path,
                        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
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

            # ═══ Step 10: Build Word Data for Subtitle Rendering ═══
            self._emit(job_id, 10, "highlights", "start")
            await self._repo.update_status(job_id, JobStatus.HIGHLIGHTING)

            # Remap words_per_clip keys to match new sequential ranks
            if rank_mapping:
                remapped_words: dict[int, list[Word]] = {}
                for old_rank, new_rank in rank_mapping.items():
                    if old_rank in words_per_clip:
                        remapped_words[new_rank] = words_per_clip[old_rank]
                words_per_clip = remapped_words

            clips_with_words = self._build_clips_with_words(clips, words_per_clip)
            self._emit(job_id, 10, "highlights", "complete")

            # ═══ Step 11+: Hook, Subtitle, Encode (REUSE) ═══
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
                clips, words_per_clip, creative_direction, output_dir,
                transcript_source=transcript_result.source,
            )
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

            # Parse B-Roll suggestions for this clip
            broll_suggestions = []
            rank_key = str(h.rank)
            if rank_key in broll_map:
                for bs in broll_map[rank_key]:
                    try:
                        visual_cat = VisualCategory(bs.get("visual_category", "footage"))
                    except (ValueError, KeyError):
                        visual_cat = VisualCategory.FOOTAGE
                    broll_suggestions.append(BRollSuggestion(
                        at_time=float(bs.get("at_time", 0)),
                        keyword=bs.get("keyword", ""),
                        template=bs.get("template", "word_pop_typography"),
                        duration=float(bs.get("duration", 2.0)),
                        visual_category=visual_cat,
                    ))

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

    def _build_clips_with_words(
        self, clips: list[Clip], words_per_clip: dict[int, list[Word]],
    ) -> dict[int, list[dict]]:
        """Convert Word objects to dict format for subtitle renderer.

        Words from SelectiveWhisper have ABSOLUTE timestamps.
        Convert to RELATIVE (from clip start) for subtitle rendering.
        """
        result = {}
        for clip in clips:
            words = words_per_clip.get(clip.rank, [])
            if not words:
                result[clip.rank] = []
                continue

            # Convert absolute → relative to clip start
            relative_words = []
            for w in words:
                rel_start = round(w.start - clip.start, 3)
                rel_end = round(w.end - clip.start, 3)

                # Keep word if it has ANY overlap with clip (handles VAD boundary shift)
                if rel_end > 0:
                    rel_start = max(0, rel_start)  # Clamp negative start to 0
                    relative_words.append({
                        "word": w.word,
                        "start": rel_start,
                        "end": rel_end,
                        "highlight": w.highlight,
                    })

            if relative_words:
                logger.debug(
                    f"v2_words clip {clip.rank}: "
                    f"{len(relative_words)} words, "
                    f"first='{relative_words[0]['word']}' @ {relative_words[0]['start']:.3f}s"
                )

            result[clip.rank] = relative_words
        return result

    async def _trim_all_clips(
        self, job_id: str, video_path: str, clips: list[Clip], output_dir: str
    ) -> dict[int, bool]:
        """Trim all clips using FFmpeg."""
        results = {}
        for clip in clips:
            out_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            try:
                success = await self._renderer.trim_clip(video_path, clip, out_path)
                results[clip.rank] = success
                if not success:
                    logger.warning(f"[{job_id}] Trim failed for clip {clip.rank}")
            except Exception as e:
                logger.warning(f"[{job_id}] Trim error clip {clip.rank}: {e}")
                results[clip.rank] = False
        return results

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
        """Run render steps: Hook + Subtitle via Remotion or FFmpeg fallback."""
        # Load custom style configs
        hook_style_config = {}
        subtitle_style_config = {}
        if job.clips_data:
            hook_style_config = job.clips_data.get("hook_style_config", {})
            subtitle_style_config = job.clips_data.get("subtitle_style_config", {})

        logger.info(
            f"[{job_id}] Render style: hook_anim={hook_style_config.get('animation', 'N/A')}, "
            f"hook_color={hook_style_config.get('color', 'N/A')}, "
            f"hook_glow={hook_style_config.get('glowEnabled', 'N/A')}, "
            f"hook_config_keys={list(hook_style_config.keys()) if hook_style_config else '[]'}, "
            f"sub_font={subtitle_style_config.get('fontFamily', 'N/A')}"
        )

        # ═══ Try Remotion first ═══
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

        if use_remotion:
            await self._render_via_remotion(
                job, job_id, clips, clips_with_words, creative_direction,
                output_dir, trim_results, reframe_data,
                hook_style_config, subtitle_style_config,
            )
            return

        # ═══ FFmpeg Fallback ═══
        await self._render_via_ffmpeg(
            job, job_id, clips, clips_with_words, creative_direction,
            output_dir, trim_results, reframe_data,
            hook_style_config, subtitle_style_config,
        )

    async def _render_via_remotion(
        self, job, job_id, clips, clips_with_words, creative_direction,
        output_dir, trim_results, reframe_data,
        hook_style_config, subtitle_style_config,
    ) -> None:
        """Render all clips via Remotion server."""
        self._emit(job_id, 13, "remotion_render", "start")
        await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)

        from src.domain.interfaces_remotion import RemotionRenderConfig
        render_config = RemotionRenderConfig(
            concurrency=settings.REMOTION_CONCURRENCY,
            quality=settings.REMOTION_QUALITY,
            enable_threejs=settings.REMOTION_ENABLE_THREEJS,
            enable_ai_layer=settings.REMOTION_ENABLE_AI_LAYER,
        )

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue

            reframed_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
            base_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
            in_path = reframed_path if os.path.exists(reframed_path) else base_path
            out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"

            clip_words_raw = clips_with_words.get(clip.rank, [])
            clip_hook = clip.hook or ""

            # Send all words to Remotion — ClipComposition.tsx handles hook-period filtering
            clip_words = clip_words_raw

            hook_style = (hook_style_config.get("animation", "")
                          or creative_direction.hook_animation or "fade_scale")

            cd_dict = asdict(creative_direction) if creative_direction else {}
            # ALWAYS pass style configs to Remotion (even if empty — Remotion handles defaults)
            cd_dict["hook_style_config"] = hook_style_config
            cd_dict["subtitle_style_config"] = subtitle_style_config

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
                )
                if result.success:
                    logger.info(f"[{job_id}] Remotion clip {clip.rank} ({result.render_time_seconds:.1f}s)")
                else:
                    logger.error(f"[{job_id}] Remotion failed clip {clip.rank}: {result.error_message}")
                    import shutil
                    if os.path.exists(in_path) and not os.path.exists(out_path):
                        shutil.copy2(in_path, out_path)
            except Exception as e:
                logger.exception(f"[{job_id}] Remotion error clip {clip.rank}: {e}")
                import shutil
                if os.path.exists(in_path) and not os.path.exists(out_path):
                    shutil.copy2(in_path, out_path)

        self._emit(job_id, 14, "remotion_render", "complete")

    async def _render_via_ffmpeg(
        self, job, job_id, clips, clips_with_words, creative_direction,
        output_dir, trim_results, reframe_data,
        hook_style_config, subtitle_style_config,
    ) -> None:
        """FFmpeg-based hook + subtitle rendering (fallback when Remotion unavailable)."""
        # ─── Hook Rendering ────────────────────────────────────────────
        self._emit(job_id, 13, "hook_render", "start")
        await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)

        hook_style = (hook_style_config.get("animation", "")
                      or creative_direction.hook_animation or "fade_scale")

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
            out_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
            try:
                from src.presentation.dependencies import get_job_service
                v1_service = get_job_service()
                await v1_service._render_hook_ffmpeg(in_path, clip.hook, out_path, hook_style=hook_style)
            except Exception as e:
                logger.warning(f"[{job_id}] Hook render clip {clip.rank}: {e}")
                import shutil
                if not os.path.exists(out_path) and os.path.exists(in_path):
                    shutil.copy2(in_path, out_path)
        self._emit(job_id, 13, "hook_render", "complete")

        # ─── Subtitle Rendering ────────────────────────────────────────
        self._emit(job_id, 14, "subtitle_render", "start")
        await self._repo.update_status(job_id, JobStatus.SUBTITLE_RENDERING)

        from src.domain.entities import SubtitleStyleConfig
        sub_style = SubtitleStyleConfig(
            font_family=subtitle_style_config.get("fontFamily", subtitle_style_config.get("font_family", "Poppins")),
            font_size=int(subtitle_style_config.get("fontSize", subtitle_style_config.get("font_size", 34))),
            uppercase=subtitle_style_config.get("uppercase", creative_direction.subtitle_uppercase),
            capitalize=subtitle_style_config.get("capitalize", False),
            color=subtitle_style_config.get("color", creative_direction.primary_color),
            highlight_color=subtitle_style_config.get("highlightColor", subtitle_style_config.get("highlight_color", creative_direction.secondary_color)),
            position=subtitle_style_config.get("position", creative_direction.subtitle_position or "bottom"),
            stroke_width=int(subtitle_style_config.get("strokeWidth", subtitle_style_config.get("stroke_width", 3))),
            max_words_per_line=int(subtitle_style_config.get("maxWordsPerLine", subtitle_style_config.get("max_words_per_line", 3))),
            line_transition=subtitle_style_config.get("lineTransition", subtitle_style_config.get("line_transition", "word_pop")),
            start_offset=0.0,
            timing_offset=0.0,  # V2: words from local Whisper are accurate, no offset needed
        )

        if subtitle_style_config.get("glowEnabled") or subtitle_style_config.get("glow_enabled"):
            sub_style.shadow_color = f"{sub_style.highlight_color}@0.6"

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            words = clips_with_words.get(clip.rank, [])
            hooked_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
            in_path = hooked_path if os.path.exists(hooked_path) else self._best_clip_path(output_dir, clip.rank, reframe_data)
            out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            try:
                if self._subtitle_renderer and words:
                    hook_duration = 3.0
                    filtered_words = [w for w in words if w.get("start", 0) >= hook_duration]
                    if not filtered_words and words:
                        filtered_words = words
                    self._subtitle_renderer.render_subtitles(
                        video_path=in_path, words=filtered_words,
                        style=sub_style, output_path=out_path, start_offset=0.0,
                    )
                else:
                    import shutil
                    if not os.path.exists(out_path) and os.path.exists(in_path):
                        shutil.copy2(in_path, out_path)
            except Exception as e:
                logger.warning(f"[{job_id}] Subtitle render clip {clip.rank}: {e}")
                import shutil
                if not os.path.exists(out_path) and os.path.exists(in_path):
                    shutil.copy2(in_path, out_path)
        self._emit(job_id, 14, "subtitle_render", "complete")

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
        words_per_clip: dict[int, list[Word]],
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
            clips_output.append({
                "rank": clip.rank,
                "score": clip.score,
                "start": clip.start,
                "end": clip.end,
                "duration": round(clip.end - clip.start, 2),
                "hook": clip.hook,
                "reason": clip.reason,
                "output_path": final_path,
                "word_count": len(words),
                "has_subtitles": len(words) > 0,
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
