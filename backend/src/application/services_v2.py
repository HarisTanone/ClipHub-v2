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
from src.infrastructure.silero_vad import SileroVADProcessor

if TYPE_CHECKING:
    from src.infrastructure.sse_progress_emitter import SSEProgressEmitter
    from src.infrastructure.overlap_detector import OverlapDetector
    from src.infrastructure.ffprobe_validator import FFprobeValidator
    from src.infrastructure.resource_monitor import ResourceMonitor
    from src.domain.interfaces_remotion import IRemotionRenderer

logger = logging.getLogger(__name__)


class V2PipelineService:
    """V2 Pipeline orchestrator for non-premium users.

    Fully local pipeline: Faster-Whisper + Ollama LLM + Silero VAD.
    No external API dependencies.
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

        # V2 components
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

        # Remotion
        self._remotion_adapter = remotion_adapter

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

        Smart cache: skips download/transcript/analysis if cached.
        force_reprocess in job.clips_data invalidates cache.
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

        # Re-read clips_data from DB to ensure style configs are available
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
            # Save video title if available
            if error_or_title and valid:
                try:
                    await self._repo.update_video_title(job_id, error_or_title)
                except Exception:
                    pass  # Non-critical
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

            # ═══ Step 3: Faster-Whisper Full Transcription (LOCAL) ═══
            cached_transcript = cache.load_transcript(video_id) if video_id else None
            if cached_transcript and cached_transcript.get("raw_segments"):
                from src.domain.entities import TranscriptResult, TranscriptSegment
                transcript_result = TranscriptResult(
                    segments=[TranscriptSegment(**s) for s in cached_transcript["segments"]],
                    source=cached_transcript.get("source", "cache"),
                    language=cached_transcript.get("language", "id"),
                    total_duration=duration,
                )
                raw_whisper_segments = cached_transcript["raw_segments"]
                logger.info(f"[{job_id}] Transcript SKIPPED (cached: {len(transcript_result.segments)} segments)")
                self._emit(job_id, 3, "v2_transcript", "complete")
            else:
                self._emit(job_id, 3, "v2_transcript", "start")
                await self._repo.update_status(job_id, JobStatus.V2_TRANSCRIBING)
                try:
                    from src.infrastructure.local_transcriber import LocalTranscriber
                    local_transcriber = LocalTranscriber(self._whisper)
                    transcript_result, raw_whisper_segments = await local_transcriber.transcribe(
                        video_path, duration
                    )
                except Exception as e:
                    await self._repo.update_status(job_id, JobStatus.FAILED, f"Transcription gagal: {e}")
                    return
                # Save to cache (include raw_segments for word-level reuse)
                if video_id:
                    cache.save_transcript(video_id, {
                        "segments": [{"text": s.text, "start": s.start, "end": s.end} for s in transcript_result.segments],
                        "raw_segments": raw_whisper_segments,
                        "source": transcript_result.source,
                        "language": transcript_result.language,
                    })
                logger.info(
                    f"[{job_id}] V2 transcript (local): {len(transcript_result.segments)} segments, "
                    f"{sum(len(s.get('words', [])) for s in raw_whisper_segments)} words"
                )
                self._emit(job_id, 3, "v2_transcript", "complete")

            # ═══ Step 4: LLM Highlight Analysis (Ollama LOCAL) ═══
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
                    from src.infrastructure.highlight_analyzer import HighlightAnalyzer, HighlightAnalyzerError
                    analyzer = HighlightAnalyzer()
                    analysis_result = await analyzer.analyze_highlights(
                        transcript_result, duration, max_clips
                    )
                except Exception as e:
                    await self._repo.update_status(job_id, JobStatus.FAILED, f"LLM analysis gagal: {e}")
                    return

                if not analysis_result.clips:
                    await self._repo.update_status(job_id, JobStatus.FAILED, "Tidak ada momen viral terdeteksi")
                    return

                # Save to cache
                if video_id:
                    cache.save_analysis(video_id, {
                        "clips": [{"rank": c.rank, "start": c.start, "end": c.end, "score": c.score,
                                    "hook": c.hook, "reason": c.reason, "content_type": c.content_type,
                                    "speaker_energy": c.speaker_energy, "hook_alt": c.hook_alt}
                                   for c in analysis_result.clips],
                        "creative_direction": analysis_result.creative_direction,
                        "broll_suggestions": analysis_result.broll_suggestions,
                        "model_used": analysis_result.model_used,
                        "chunks_processed": analysis_result.chunks_processed,
                    }, version="v2")
                logger.info(
                    f"[{job_id}] V2 analysis (Ollama): {len(analysis_result.clips)} clips, "
                    f"model={analysis_result.model_used}"
                )
                self._emit(job_id, 4, "v2_highlight_analysis", "complete")

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

            # ═══ Step 7.5: Skip (no longer needed — full Whisper done in Step 3) ═══
            audio_slices = []  # Keep variable for VAD compatibility

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

            # Center-crop fallback for 9:16 (when YOLO model unavailable or fails all clips)
            if flags.yolo_enabled and not reframe_data and job.target_aspect_ratio == "9:16":
                import subprocess as _sp
                logger.info(f"[{job_id}] Applying center-crop fallback for 9:16 (YOLO produced no results)")
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
                        logger.warning(f"[{job_id}] Center-crop fallback error clip {clip.rank}: {e}")

            # ═══ Step 9: Whisper on TRIMMED CLIPS (per-clip for accurate timestamps) ═══
            self._emit(job_id, 9, "v2_selective_whisper", "start")
            await self._repo.update_status(job_id, JobStatus.V2_WORD_TRANSCRIBING)

            # Run Whisper on each trimmed clip directly — gives word timestamps
            # perfectly relative to clip start (0.0 = beginning of clip audio)
            words_per_clip: dict[int, list[Word]] = {}
            from src.infrastructure.groq_whisper import GroqWhisperTranscriber
            clip_whisper = GroqWhisperTranscriber()

            for clip in clips:
                if not trim_results.get(clip.rank):
                    continue
                # Use the reframed clip if available (has correct audio), else raw trimmed
                clip_path = f"{output_dir}/clip_{clip.rank:02d}_reframed.mp4"
                if not os.path.exists(clip_path):
                    clip_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"

                if not os.path.exists(clip_path):
                    continue

                try:
                    # Transcribe the trimmed clip — timestamps will be 0-based (relative to clip start)
                    segments = await clip_whisper.transcribe(clip_path)
                    clip_words = []
                    for seg in segments:
                        for w in seg.get("words", []):
                            word_text = w.get("word", "").strip()
                            w_start = w.get("start", 0)
                            w_end = w.get("end", 0)
                            if word_text and w_end > w_start:
                                clip_words.append(Word(
                                    word=word_text,
                                    start=round(w_start, 3),
                                    end=round(w_end, 3),
                                    highlight=False,
                                ))
                    words_per_clip[clip.rank] = clip_words
                    logger.info(f"[{job_id}] Whisper clip {clip.rank}: {len(clip_words)} words, first='{clip_words[0].word if clip_words else 'N/A'}' @ {clip_words[0].start if clip_words else 0:.3f}s")
                except Exception as e:
                    logger.warning(f"[{job_id}] Whisper clip {clip.rank} failed: {e}")
                    # Fallback: extract from full-video timestamps (less accurate)
                    clip_words = self._extract_words_for_clip(raw_whisper_segments, clip.start, clip.end)
                    words_per_clip[clip.rank] = clip_words

            logger.info(
                f"[{job_id}] V2 per-clip Whisper: "
                f"{sum(1 for w in words_per_clip.values() if w)}/{clips_count} clips with words "
                f"({sum(len(w) for w in words_per_clip.values())} total words)"
            )
            self._emit(job_id, 9, "v2_selective_whisper", "complete")

            # ═══ Step 9.5: V2 Silero VAD ═══
            self._emit(job_id, "9.5", "v2_vad_refine", "start")
            await self._repo.update_status(job_id, JobStatus.V2_VAD_REFINING)

            # Save original clip starts BEFORE VAD adjusts them (needed for subtitle timing)
            original_starts = {clip.rank: clip.start for clip in clips}

            vad_applied = 0
            for clip in clips:
                if not trim_results.get(clip.rank):
                    continue
                # VAD needs WAV audio — extract from trimmed clip
                clip_video_path = f"{output_dir}/clip_{clip.rank:02d}.mp4"
                clip_audio_path = f"{output_dir}/clip_{clip.rank:02d}_vad.wav"
                try:
                    # Extract audio for VAD (16kHz mono WAV)
                    import subprocess
                    extract_cmd = [
                        "ffmpeg", "-y", "-i", clip_video_path,
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                        "-loglevel", "error", clip_audio_path,
                    ]
                    await asyncio.to_thread(
                        subprocess.run, extract_cmd, capture_output=True, timeout=30
                    )
                    
                    if not os.path.exists(clip_audio_path):
                        continue
                    
                    clip_duration = clip.end - clip.start
                    vad_result = await self._vad.refine_clip_boundaries(
                        audio_path=clip_audio_path,
                        original_start=0.0,
                        original_end=clip_duration,
                        padded_start=0.0,
                    )
                    
                    # Apply VAD shift (preserve original for subtitle timing)
                    if not vad_result.used_fallback:
                        orig_start = clip.start
                        clip.start = orig_start + vad_result.final_start
                        clip.end = orig_start + vad_result.final_end
                        vad_applied += 1
                except Exception as e:
                    logger.debug(f"[{job_id}] VAD clip {clip.rank}: {e}")
                finally:
                    # Cleanup VAD audio
                    if os.path.exists(clip_audio_path):
                        os.remove(clip_audio_path)
            logger.info(f"[{job_id}] V2 VAD refinement: {vad_applied}/{clips_count} clips adjusted")
            self._emit(job_id, "9.5", "v2_vad_refine", "complete")

            # ═══ Step 10: Highlight Words (from V2 analysis, skip Gemini) ═══
            # V2 already has highlight info from Groq LLM — no separate Gemini call needed
            self._emit(job_id, 10, "highlights", "start")
            await self._repo.update_status(job_id, JobStatus.HIGHLIGHTING)
            # Convert words_per_clip to the format expected by downstream
            clips_with_words = self._build_clips_with_words(clips, words_per_clip, original_starts)
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

            # Build final clips_data
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

    def _extract_words_for_clip(
        self, raw_segments: list[dict], clip_start: float, clip_end: float
    ) -> list[Word]:
        """Extract words from raw Whisper segments that fall within clip boundaries.
        
        Words are returned with ABSOLUTE timestamps (will be converted to
        relative in _build_clips_with_words later).
        """
        words = []
        for seg in raw_segments:
            for w in seg.get("words", []):
                w_start = w.get("start", 0)
                w_end = w.get("end", 0)
                w_text = w.get("word", "").strip()
                if not w_text:
                    continue
                # Keep words within clip range (with small tolerance)
                if w_end >= clip_start and w_start <= clip_end:
                    words.append(Word(
                        word=w_text,
                        start=round(w_start, 3),
                        end=round(w_end, 3),
                        highlight=False,
                    ))
        return words

    def _build_clips_with_words(
        self, clips: list[Clip], words_per_clip: dict[int, list[Word]],
        original_starts: dict[int, float] = None,
    ) -> dict[int, list[dict]]:
        """Convert Word objects to dict format expected by subtitle renderer.
        
        If words were transcribed per-clip (start near 0), they're already relative.
        If words were extracted from full-video (start near clip.start), convert to relative.
        """
        result = {}
        for clip in clips:
            words = words_per_clip.get(clip.rank, [])
            if not words:
                result[clip.rank] = []
                continue

            # Detect if words are already relative (first word start < 10s = per-clip Whisper)
            # vs absolute (first word start near clip.start = extracted from full video)
            first_word_start = words[0].start if words else 0
            trim_point = (original_starts or {}).get(clip.rank, clip.start)

            # If first word is close to 0 (within 10s), words are already per-clip relative
            already_relative = first_word_start < 10.0

            relative_words = []
            for w in words:
                if already_relative:
                    rel_start = round(w.start, 3)
                    rel_end = round(w.end, 3)
                else:
                    # Convert absolute → relative
                    rel_start = round(w.start - trim_point, 3)
                    rel_end = round(w.end - trim_point, 3)

                if rel_start >= 0 and rel_end > rel_start:
                    relative_words.append({
                        "word": w.word,
                        "start": rel_start,
                        "end": rel_end,
                        "highlight": w.highlight,
                    })

            if relative_words:
                logger.info(
                    f"v2_words clip {clip.rank}: mode={'per-clip' if already_relative else 'extracted'}, "
                    f"{len(relative_words)} words, "
                    f"first='{relative_words[0]['word']}' @ {relative_words[0]['start']:.3f}s"
                )

            result[clip.rank] = relative_words
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
        Applies user's custom style from job.clips_data if available.
        """
        # ─── Load custom style configs from job ────────────────────────
        hook_style_config = {}
        subtitle_style_config = {}
        if job.clips_data:
            hook_style_config = job.clips_data.get("hook_style_config", {})
            subtitle_style_config = job.clips_data.get("subtitle_style_config", {})
        
        logger.info(
            f"[{job_id}] Render style: hook_anim={hook_style_config.get('animation', 'N/A')}, "
            f"sub_font={subtitle_style_config.get('fontFamily', 'N/A')}, "
            f"sub_color={subtitle_style_config.get('color', 'N/A')}, "
            f"sub_highlight={subtitle_style_config.get('highlightColor', 'N/A')}"
        )

        # ═══ Remotion is ALWAYS used for hook+subtitle rendering ═══
        # FFmpeg subtitle rendering is deprecated — Remotion produces correct karaoke + style
        use_remotion = False
        if self._remotion_adapter:
            try:
                if await self._remotion_adapter.health_check():
                    use_remotion = True
                    logger.info(f"[{job_id}] Remotion server healthy — using Remotion for render")
                else:
                    # Server not running — start it and wait
                    logger.info(f"[{job_id}] Remotion server not running — starting...")
                    started = await self._remotion_adapter.start_server()
                    if started and await self._remotion_adapter.health_check():
                        use_remotion = True
                        logger.info(f"[{job_id}] Remotion server started successfully")
                    else:
                        logger.error(f"[{job_id}] Failed to start Remotion server — will attempt FFmpeg fallback")
            except Exception as e:
                logger.error(f"[{job_id}] Remotion startup error: {e} — will attempt FFmpeg fallback")
        else:
            logger.warning(f"[{job_id}] No Remotion adapter configured — using FFmpeg fallback")

        if use_remotion:
            # ═══ Remotion Path — Single unified render (hook + subtitle) ═══
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

                in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
                out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"

                clip_words_raw = clips_with_words.get(clip.rank, [])
                clip_hook = clip.hook or ""
                
                # Filter words during hook period — hook overlay (z-index 2) covers subtitles
                # so words spoken during hook are invisible anyway. Start subtitles AFTER hook.
                hook_dur = hook_style_config.get("duration", 3.0) if clip_hook else 0
                clip_words = [w for w in clip_words_raw if w.get("start", 0) >= hook_dur]
                hook_style = hook_style_config.get("animation", "") or creative_direction.hook_animation or "fade_scale"

                # Build creative direction dict with style configs
                cd_dict = asdict(creative_direction) if creative_direction else {}
                if hook_style_config:
                    cd_dict["hook_style_config"] = hook_style_config
                if subtitle_style_config:
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
                        logger.info(f"[{job_id}] Remotion rendered clip {clip.rank} ({result.render_time_seconds:.1f}s)")
                    else:
                        logger.error(f"[{job_id}] Remotion failed clip {clip.rank}: {result.error_message}")
                        # Fallback: copy base clip
                        import shutil
                        if os.path.exists(in_path) and not os.path.exists(out_path):
                            shutil.copy2(in_path, out_path)
                except Exception as e:
                    logger.exception(f"[{job_id}] Remotion error clip {clip.rank}: {e}")
                    import shutil
                    if os.path.exists(in_path) and not os.path.exists(out_path):
                        shutil.copy2(in_path, out_path)

            self._emit(job_id, 14, "remotion_render", "complete")
            return  # Skip FFmpeg rendering below

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

        # Determine hook style from user config or creative direction
        hook_style = hook_style_config.get("animation", "") or creative_direction.hook_animation or "fade_scale"

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            in_path = self._best_clip_path(output_dir, clip.rank, reframe_data)
            out_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
            try:
                from src.presentation.dependencies import get_job_service
                v1_service = get_job_service()
                await v1_service._render_hook_ffmpeg(
                    in_path, clip.hook, out_path,
                    hook_style=hook_style,
                )
            except Exception as e:
                logger.warning(f"[{job_id}] Hook render clip {clip.rank}: {e}")
                import shutil
                if not os.path.exists(out_path) and os.path.exists(in_path):
                    shutil.copy2(in_path, out_path)
        self._emit(job_id, 13, "hook_render", "complete")

        # ─── Subtitle Rendering ────────────────────────────────────────
        self._emit(job_id, 14, "subtitle_render", "start")
        await self._repo.update_status(job_id, JobStatus.SUBTITLE_RENDERING)

        # Build SubtitleStyleConfig from user's custom config or creative direction
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
            # V2: words already have correct relative timestamps from full-video Whisper
            # No offset needed — we filter out hook-period words instead
            start_offset=0.0,
            # Groq Whisper turbo timestamps are ~1s early — compensate
            timing_offset=1.0,
        )

        # Apply glow if enabled in custom config
        if subtitle_style_config.get("glowEnabled") or subtitle_style_config.get("glow_enabled"):
            sub_style.shadow_color = f"{sub_style.highlight_color}@0.6"
        
        logger.info(
            f"[{job_id}] SubtitleStyle: font={sub_style.font_family}, color={sub_style.color}, "
            f"highlight={sub_style.highlight_color}, position={sub_style.position}, offset={sub_style.start_offset}s"
        )

        for clip in clips:
            if not trim_results.get(clip.rank):
                continue
            words = clips_with_words.get(clip.rank, [])
            # Subtitle rendered ON TOP of hooked video (same order as V1)
            hooked_path = f"{output_dir}/clip_{clip.rank:02d}_hooked.mp4"
            brolled_path = f"{output_dir}/clip_{clip.rank:02d}_broll.mp4"
            in_path = brolled_path if os.path.exists(brolled_path) else (
                hooked_path if os.path.exists(hooked_path) else
                self._best_clip_path(output_dir, clip.rank, reframe_data)
            )
            out_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
            try:
                if self._subtitle_renderer and words:
                    # V2: filter words during hook period (0-3s) — don't overlay with hook text
                    # Words already have correct relative timestamps, no offset shift needed
                    hook_duration = 3.0
                    filtered_words = [w for w in words if w.get("start", 0) >= hook_duration]
                    
                    # Diagnostic: log first 3 words timing for sync verification
                    if filtered_words:
                        sample = filtered_words[:3]
                        logger.info(
                            f"[{job_id}] Subtitle clip {clip.rank}: "
                            f"first_word='{sample[0]['word']}' @ {sample[0]['start']:.2f}s, "
                            f"total={len(filtered_words)} words, "
                            f"clip_trim_start={clip.start:.2f}s"
                        )
                    
                    self._subtitle_renderer.render_subtitles(
                        video_path=in_path,
                        words=filtered_words,
                        style=sub_style,
                        output_path=out_path,
                        start_offset=0.0,  # No shift — timestamps are already correct
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

        # ─── Post-render: Verify subtitle sync ────────────────────────────
        try:
            from src.infrastructure.subtitle_sync_verifier import SubtitleSyncVerifier
            verifier = SubtitleSyncVerifier()
            sync_results = verifier.verify_all_clips(output_dir, clips_with_words, hook_duration=3.0)
            failed_clips = [r for r, v in sync_results.items() if not v["passed"]]
            if failed_clips:
                logger.warning(f"[{job_id}] Subtitle sync issues in clips: {failed_clips}")
                for rank, v in sync_results.items():
                    if v.get("issues"):
                        logger.warning(f"[{job_id}] Clip {rank} sync: {'; '.join(v['issues'])}")
            else:
                logger.info(f"[{job_id}] Subtitle sync VERIFIED: all {len(sync_results)} clips OK")
        except Exception as e:
            logger.debug(f"[{job_id}] Subtitle sync verification skipped: {e}")

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

    async def _create_folder_structure(
        self,
        job_id: str,
        job: Job,
        clips: list[Clip],
        clips_with_words: dict[int, list[dict]],
        creative_direction: CreativeDirection,
        output_dir: str,
        trim_results: dict[int, bool],
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

            # Generate thumbnail from final video (seek to 1s)
            final_path = f"{output_dir}/clip_{rank:02d}_final.mp4"
            thumb_path = f"{thumb_dir}/clip_{rank:02d}.jpg"
            if os.path.exists(final_path):
                thumb_cmd = [
                    "ffmpeg", "-y", "-i", final_path,
                    "-ss", "1", "-frames:v", "1",
                    "-vf", "scale=360:-1",
                    "-q:v", "3",
                    thumb_path,
                ]
                try:
                    await asyncio.to_thread(subprocess.run, thumb_cmd, capture_output=True, text=True, timeout=15)
                except Exception:
                    pass

            # Copy raw clip to raw/ folder
            raw_src = f"{output_dir}/clip_{rank:02d}.mp4"
            if os.path.exists(raw_src):
                shutil.copy2(raw_src, f"{raw_dir}/clip_{rank:02d}.mp4")

            # Copy final clip to final/ folder
            if os.path.exists(final_path):
                shutil.copy2(final_path, f"{final_dir}/clip_{rank:02d}.mp4")

        # Generate meta JSON — format matches V1 pipeline exactly
        clips_count = len(clips)
        success_count = sum(1 for c in clips if trim_results.get(c.rank))

        meta = {
            "job_id": job_id,
            "youtube_url": job.youtube_url,
            "aspect_ratio": job.target_aspect_ratio,
            "clips_total": clips_count,
            "clips_success": success_count,
            "created_at": str(job.created_at) if job.created_at else None,
            "clips": [
                {
                    "rank": c.rank,
                    "start": c.start,
                    "end": c.end,
                    "duration": c.end - c.start,
                    "hook": c.hook,
                    "score": c.score,
                    "words": clips_with_words.get(c.rank, []),
                }
                for c in clips
            ],
        }

        meta_path = f"{output_dir}/meta_{job_id}.json"
        with open(meta_path, "w") as f:
            json_mod.dump(meta, f, indent=2, default=str)

        logger.info(f"[{job_id}] Folder structure created: raw/{success_count}, final/{success_count}, thumbnail/, meta JSON")
