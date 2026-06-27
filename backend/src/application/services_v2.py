"""V2PipelineService — Pipeline orchestrator for non-premium users.

Uses Groq (transcript + LLM) + Faster-Whisper (selective) + Silero VAD
instead of Gemini video understanding.

Pipeline Steps (V2):
  1. Validate              — yt-dlp validate URL, extract duration (REUSE)
  2. Download              — Download full video (REUSE)
  3. V2 Transcript         — YouTube API / Groq Whisper fallback
  4. V2 Highlight Analysis — Groq LLM with dynamic chunking
  5. Prepare Clips         — Time padding, overlap detection (REUSE)
  6. Aspect Ratio Router   — Set pipeline flags (REUSE)
  7. Trim Clips            — FFmpeg stream copy (REUSE)
  7.5 Micro-Slice          — Extract audio per highlight
  8. YOLO Seg + Reframe    — Conditional (REUSE)
  9. V2 Selective Whisper  — Word-level on short clips only
  9.5 V2 Silero VAD        — Natural cut refinement
  10+ B-Roll, Hook, Subtitle, Encode, Upload (REUSE from V1)
"""
import asyncio
import logging
import os
import time
from dataclasses import asdict
from typing import Optional, TYPE_CHECKING

from src.config import settings
from src.domain.entities import (
    BRollSuggestion, Clip, CreativeDirection, Job, JobStatus,
    PipelineFlags, VisualCategory, Word,
)
from src.domain.interfaces import (
    IAspectRatioRouter,
    IAssetFetcher,
    IBRollInjector,
    IBrowserRenderEngine,
    IDownloader,
    IJobRepository,
    IRenderer,
    ISubtitleRenderer,
    IWhisperLocal,
    IYoloReframeEngine,
)
from src.infrastructure.groq_transcriber import GroqTranscriber, TranscriptionError
from src.infrastructure.groq_analyzer import GroqAnalyzer, GroqAnalyzerError
from src.infrastructure.micro_slicer import MicroSlicer, MicroSlicerError
from src.infrastructure.selective_whisper import SelectiveWhisperTranscriber
from src.infrastructure.silero_vad import SileroVADProcessor

if TYPE_CHECKING:
    from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
    from src.infrastructure.overlap_detector import OverlapDetector
    from src.infrastructure.ffprobe_validator import FFprobeValidator
    from src.infrastructure.resource_monitor import ResourceMonitor

logger = logging.getLogger(__name__)


class V2PipelineService:
    """V2 Pipeline orchestrator for non-premium users.

    Replaces Gemini with Groq-based text analysis while reusing
    existing infrastructure (trim, YOLO, B-Roll, subtitle, render).
    """

    def __init__(
        self,
        job_repo: IJobRepository,
        downloader: IDownloader,
        renderer: IRenderer,
        whisper_local: IWhisperLocal,
        # ─── V2 specific components ──────────────────────────────────
        groq_transcriber: Optional[GroqTranscriber] = None,
        groq_analyzer: Optional[GroqAnalyzer] = None,
        micro_slicer: Optional[MicroSlicer] = None,
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
    ):
        self._repo = job_repo
        self._downloader = downloader
        self._renderer = renderer
        self._whisper = whisper_local

        # V2 components (create defaults if not provided)
        self._transcriber = groq_transcriber or GroqTranscriber()
        self._analyzer = groq_analyzer or GroqAnalyzer()
        self._micro_slicer = micro_slicer or MicroSlicer()
        self._selective_whisper = SelectiveWhisperTranscriber(self._whisper)
        self._vad = silero_vad or SileroVADProcessor()

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
        else:
            n = 10
        limit = settings.VIDEO_FINAL_RESULT
        if limit and limit > 0:
            n = min(n, limit)
        return n

    # ─── Main Pipeline ────────────────────────────────────────────────────────

    async def run_pipeline(self, job: Job) -> None:
        """Execute the V2 pipeline for a job.

        This method handles the full lifecycle: validate → download → V2 analysis
        → trim → YOLO → V2 whisper → V2 VAD → render steps.
        """
        job_id = job.job_id
        url = job.youtube_url
        video_path = f"{settings.DOWNLOAD_DIR}/{job_id}.mp4"
        output_dir = f"{settings.OUTPUT_DIR}/{job_id}"
        os.makedirs(output_dir, exist_ok=True)
        pipeline_start = time.time()

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
            valid, error, duration = await self._downloader.validate_url(url)
            if not valid:
                await self._repo.update_status(job_id, JobStatus.FAILED, error)
                return
            job.video_duration = duration
            self._emit(job_id, 1, "validate", "complete")

            # ═══ Step 2: Download ═══
            self._emit(job_id, 2, "download", "start")
            await self._repo.update_status(job_id, JobStatus.DOWNLOADING)
            await self._downloader.download_video(url, video_path)
            self._emit(job_id, 2, "download", "complete")

            # ═══ Step 3: V2 Transcript (TAHAP 1) ═══
            self._emit(job_id, 3, "v2_transcript", "start")
            await self._repo.update_status(job_id, JobStatus.V2_TRANSCRIBING)
            try:
                transcript_result = await self._transcriber.transcribe(url, duration)
            except TranscriptionError as e:
                await self._repo.update_status(job_id, JobStatus.FAILED, f"Transcription gagal: {e}")
                return
            logger.info(
                f"[{job_id}] V2 transcript: {len(transcript_result.segments)} segments, "
                f"source={transcript_result.source}, lang={transcript_result.language}"
            )
            self._emit(job_id, 3, "v2_transcript", "complete")

            # ═══ Step 4: V2 Highlight Analysis (TAHAP 2) ═══
            self._emit(job_id, 4, "v2_highlight_analysis", "start")
            await self._repo.update_status(job_id, JobStatus.V2_ANALYZING)
            max_clips = self._calc_max_clips(duration)
            try:
                analysis_result = await self._analyzer.analyze_highlights(
                    transcript_result, duration, max_clips
                )
            except GroqAnalyzerError as e:
                await self._repo.update_status(job_id, JobStatus.FAILED, f"Highlight analysis gagal: {e}")
                return

            if not analysis_result.clips:
                await self._repo.update_status(job_id, JobStatus.FAILED, "Tidak ada momen viral terdeteksi")
                return

            # Parse creative direction
            creative_direction = CreativeDirection.from_dict(
                analysis_result.creative_direction
            ) if analysis_result.creative_direction else CreativeDirection()
            logger.info(
                f"[{job_id}] V2 highlights: {len(analysis_result.clips)} clips, "
                f"model={analysis_result.model_used}, chunks={analysis_result.chunks_processed}"
            )
            self._emit(job_id, 4, "v2_highlight_analysis", "complete")

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
                await self._repo.update_status(job_id, JobStatus.FAILED, "Tidak ada clip valid setelah filtering")
                return
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

            # ═══ Step 7.5: V2 Micro-Slice (TAHAP 3) ═══
            self._emit(job_id, "7.5", "v2_micro_slice", "start")
            await self._repo.update_status(job_id, JobStatus.V2_MICRO_SLICING)
            highlights_for_slice = [
                {"rank": c.rank, "start": c.start, "end": c.end}
                for c in clips if trim_results.get(c.rank)
            ]
            audio_slices_dir = f"{output_dir}/audio_slices"
            try:
                audio_slices = await self._micro_slicer.slice_audio(
                    video_path, highlights_for_slice, audio_slices_dir, duration
                )
            except MicroSlicerError as e:
                logger.warning(f"[{job_id}] Micro-slicing failed: {e}")
                audio_slices = []
            self._emit(job_id, "7.5", "v2_micro_slice", "complete")

            # ═══ Step 8: YOLO Seg + Reframe (REUSE) ═══
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

            # ═══ Step 9: V2 Selective Whisper (TAHAP 4) ═══
            self._emit(job_id, 9, "v2_selective_whisper", "start")
            await self._repo.update_status(job_id, JobStatus.V2_WORD_TRANSCRIBING)
            words_per_clip: dict[int, list[Word]] = {}
            if audio_slices:
                words_per_clip = await self._selective_whisper.transcribe_all_clips(
                    audio_slices, max_parallel=settings.MAX_WHISPER_PARALLEL
                )
            logger.info(
                f"[{job_id}] V2 selective whisper: "
                f"{sum(1 for w in words_per_clip.values() if w)}/{clips_count} clips with words"
            )
            self._emit(job_id, 9, "v2_selective_whisper", "complete")

            # ═══ Step 9.5: V2 Silero VAD (TAHAP 5) ═══
            self._emit(job_id, "9.5", "v2_vad_refine", "start")
            await self._repo.update_status(job_id, JobStatus.V2_VAD_REFINING)
            vad_applied = 0
            if audio_slices:
                for audio_slice in audio_slices:
                    try:
                        vad_result = await self._vad.refine_clip_boundaries(
                            audio_path=audio_slice.audio_path,
                            original_start=audio_slice.original_start,
                            original_end=audio_slice.original_end,
                            padded_start=audio_slice.padded_start,
                        )
                        if not vad_result.used_fallback:
                            # Update clip timestamps
                            for clip in clips:
                                if clip.rank == audio_slice.clip_rank:
                                    clip.start = vad_result.final_start
                                    clip.end = vad_result.final_end
                                    vad_applied += 1
                                    break
                    except Exception as e:
                        logger.debug(f"[{job_id}] VAD clip {audio_slice.clip_rank}: {e}")
            logger.info(f"[{job_id}] V2 VAD refinement: {vad_applied}/{clips_count} clips adjusted")
            self._emit(job_id, "9.5", "v2_vad_refine", "complete")

            # ═══ Step 10: Highlight Words (from V2 analysis, skip Gemini) ═══
            # V2 already has highlight info from Groq LLM — no separate Gemini call needed
            self._emit(job_id, 10, "highlights", "start")
            await self._repo.update_status(job_id, JobStatus.HIGHLIGHTING)
            # Convert words_per_clip to the format expected by downstream
            clips_with_words = self._build_clips_with_words(clips, words_per_clip)
            self._emit(job_id, 10, "highlights", "complete")

            # ═══ Step 11+: B-Roll, Hook, Subtitle (REUSE existing pipeline) ═══
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

            # ═══ Final: Assemble results ═══
            success_count = sum(
                1 for clip in clips
                if os.path.exists(f"{output_dir}/clip_{clip.rank:02d}_final.mp4")
                or os.path.exists(f"{output_dir}/clip_{clip.rank:02d}_subtitled.mp4")
                or os.path.exists(f"{output_dir}/clip_{clip.rank:02d}.mp4")
            )
            failed_count = clips_count - success_count
            await self._repo.update_clips_count(job_id, clips_count, success_count, failed_count)

            # Build final clips_data
            clips_data = self._assemble_clips_data(
                clips, words_per_clip, creative_direction, output_dir,
                transcript_source=transcript_result.source,
            )
            await self._repo.update_clips_data(job_id, clips_data)

            # Cleanup temp audio slices
            if audio_slices:
                self._micro_slicer.cleanup_slices(audio_slices)

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
        self, clips: list[Clip], words_per_clip: dict[int, list[Word]]
    ) -> dict[int, list[dict]]:
        """Convert Word objects to dict format expected by downstream renderers."""
        result = {}
        for clip in clips:
            words = words_per_clip.get(clip.rank, [])
            # Convert to relative timestamps (from clip start)
            relative_words = SelectiveWhisperTranscriber.words_to_relative(words, clip.start)
            result[clip.rank] = [
                {"word": w.word, "start": w.start, "end": w.end, "highlight": w.highlight}
                for w in relative_words
            ]
        return result

    async def _trim_all_clips(
        self, job_id: str, video_path: str, clips: list[Clip], output_dir: str
    ) -> dict[int, bool]:
        """Trim all clips using FFmpeg stream copy."""
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
        """Run render steps: B-Roll, Hook, Subtitle.

        Uses existing rendering infrastructure (same as V1 pipeline).
        """
        # ─── B-Roll Asset Fetching ─────────────────────────────────────
        if job.broll_enabled and self._asset_fetcher:
            self._emit(job_id, 11, "asset_fetch", "start")
            all_suggestions = []
            for clip in clips:
                all_suggestions.extend(clip.broll_suggestions)
            if all_suggestions:
                try:
                    await self._asset_fetcher.fetch_assets(all_suggestions, creative_direction)
                except Exception as e:
                    logger.warning(f"[{job_id}] Asset fetch failed: {e}")
            self._emit(job_id, 11, "asset_fetch", "complete")

        # ─── B-Roll Injection ──────────────────────────────────────────
        if job.broll_enabled and self._broll_injector:
            self._emit(job_id, 12, "broll_inject", "start")
            await self._repo.update_status(job_id, JobStatus.BROLL)
            for clip in clips:
                if not trim_results.get(clip.rank) or not clip.broll_suggestions:
                    continue
                in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
                out_path = f"{output_dir}/clip_{clip.rank:02d}_broll.mp4"
                try:
                    await self._broll_injector.inject(in_path, clip.broll_suggestions, out_path)
                except Exception as e:
                    logger.warning(f"[{job_id}] B-Roll inject clip {clip.rank}: {e}")
            self._emit(job_id, 12, "broll_inject", "complete")

        # ─── Hook Rendering ────────────────────────────────────────────
        self._emit(job_id, 13, "hook_render", "start")
        await self._repo.update_status(job_id, JobStatus.HOOK_RENDERING)
        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
            out_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
            try:
                if self._browser_render:
                    style_config = {
                        "animation": creative_direction.hook_animation or "fade_scale",
                        "primary_color": creative_direction.primary_color,
                        "secondary_color": creative_direction.secondary_color,
                    }
                    await self._browser_render.render_hook(
                        clip.hook, style_config, out_path,
                        duration_ms=3000, width=1080, height=1920,
                    )
                else:
                    # Fallback: copy without hook (hook rendering requires browser engine)
                    import shutil
                    if not os.path.exists(out_path):
                        shutil.copy2(in_path, out_path)
            except Exception as e:
                logger.warning(f"[{job_id}] Hook render clip {clip.rank}: {e}")
                import shutil
                if not os.path.exists(out_path) and os.path.exists(in_path):
                    shutil.copy2(in_path, out_path)
        self._emit(job_id, 13, "hook_render", "complete")

        # ─── Subtitle Rendering ────────────────────────────────────────
        self._emit(job_id, 14, "subtitle_render", "start")
        await self._repo.update_status(job_id, JobStatus.SUBTITLE_RENDERING)
        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            words = clips_with_words.get(clip.rank, [])
            in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
            out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            try:
                if self._subtitle_renderer and words:
                    self._subtitle_renderer.render_subtitles(
                        in_path, words, creative_direction, out_path
                    )
                else:
                    # No words or no renderer → copy as final
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
        """Get the best available clip path (reframed > broll > hooked > base)."""
        candidates = [
            f"{output_dir}/clip_{rank:02d}_hooked.mp4",
            f"{output_dir}/clip_{rank:02d}_broll.mp4",
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
                # Try other paths
                for suffix in ["_subtitled", "_hooked", "_broll", "_reframed", ""]:
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
