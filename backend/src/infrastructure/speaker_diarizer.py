"""SpeakerDiarizer — PyAnnote speaker-diarization-3.1 wrapper.

Identifies distinct speakers in audio/video files and produces
time-stamped segments attributed to each speaker.

Architecture:
1. Lazy-load PyAnnote Pipeline (GPU auto-detected)
2. Extract audio to temp WAV (16kHz mono) via FFmpeg
3. Run diarization with timeout protection
4. Parse itertracks → DiarizationSegment list
5. Graceful degradation: return None on any failure

Design decisions:
- Lazy loading: model only loads on first diarize() call
- _load_attempted flag prevents repeated load attempts after failure
- All exceptions caught and logged → return None
- Audio temp file ALWAYS cleaned up (finally block)
- asyncio.create_subprocess_exec for FFmpeg
- asyncio.to_thread for PyAnnote (CPU-bound)
"""
import asyncio
import gc
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class DiarizationSegment:
    """A single speaker segment with start/end timestamps."""

    start: float
    end: float
    speaker: str


@dataclass
class DiarizationResult:
    """Full diarization result for an audio/video file."""

    segments: List[DiarizationSegment] = field(default_factory=list)
    speaker_count: int = 0
    speakers: List[str] = field(default_factory=list)
    total_speech_duration: float = 0.0
    audio_duration: float = 0.0


# ─── Speaker Diarizer ─────────────────────────────────────────────────────────


class SpeakerDiarizer:
    """Wraps PyAnnote speaker-diarization-3.1 for multi-speaker detection.

    Lazy loads model on first call. Returns None on any failure
    for graceful pipeline degradation.
    """

    def __init__(
        self,
        hf_token: str = "",
        model_name: str = "pyannote/speaker-diarization-3.1",
        timeout_sec: int = 60,
        min_speakers: int = 2,
        max_speakers: int = 4,
    ):
        self._hf_token = hf_token
        self._model_name = model_name
        self._timeout_sec = timeout_sec
        self._min_speakers = min_speakers
        self._max_speakers = max_speakers

        self._pipeline = None
        self._load_attempted: bool = False
        self._load_failed: bool = False

    # ─── Properties ───────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Check if diarization is available (has token and no load failure)."""
        return bool(self._hf_token) and not self._load_failed

    # ─── Model Loading ────────────────────────────────────────────────────────

    def _load_model(self) -> bool:
        """Lazy load PyAnnote Pipeline. Auto-detect GPU/CPU.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if self._pipeline is not None:
            return True

        if self._load_attempted:
            return not self._load_failed

        self._load_attempted = True

        try:
            import torch
            from pyannote.audio import Pipeline

            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(
                f"speaker_diarizer: loading {self._model_name} on {device}"
            )

            pipeline = Pipeline.from_pretrained(
                self._model_name,
                token=self._hf_token,
            )
            pipeline.to(torch.device(device))

            self._pipeline = pipeline
            self._load_failed = False
            logger.info("speaker_diarizer: model loaded successfully")
            return True

        except Exception as e:
            self._load_failed = True
            logger.error(f"speaker_diarizer: model loading failed: {e}")
            return False

    # ─── Public API ───────────────────────────────────────────────────────────

    async def diarize(self, video_path: str) -> Optional[DiarizationResult]:
        """Run speaker diarization on a video/audio file.

        Extracts audio to temp WAV, runs PyAnnote with timeout,
        and parses results into DiarizationResult.

        Args:
            video_path: Path to video or audio file.

        Returns:
            DiarizationResult on success, None on any failure.
        """
        if not self.is_available:
            logger.warning("speaker_diarizer: not available (no token or load failed)")
            return None

        if not os.path.exists(video_path):
            logger.warning(f"speaker_diarizer: file not found: {video_path}")
            return None

        audio_path: Optional[str] = None

        try:
            # Step 1: Extract audio to temp WAV
            audio_path = await self._extract_audio(video_path)
            if audio_path is None:
                return None

            # Step 2: Ensure model is loaded
            if not self._load_model():
                return None

            # Step 3: Run diarization with timeout
            diarization = await asyncio.wait_for(
                asyncio.to_thread(self._run_diarization, audio_path),
                timeout=self._timeout_sec,
            )

            if diarization is None:
                return None

            # Step 4: Parse results
            segments: List[DiarizationSegment] = []
            speakers_set: set = set()
            total_speech: float = 0.0

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                seg = DiarizationSegment(
                    start=turn.start,
                    end=turn.end,
                    speaker=speaker,
                )
                segments.append(seg)
                speakers_set.add(speaker)
                total_speech += turn.end - turn.start

            speakers = sorted(speakers_set)

            # Get audio duration from file
            audio_duration = await self._get_audio_duration(audio_path)

            result = DiarizationResult(
                segments=segments,
                speaker_count=len(speakers),
                speakers=speakers,
                total_speech_duration=total_speech,
                audio_duration=audio_duration,
            )

            logger.info(
                f"speaker_diarizer: found {result.speaker_count} speakers, "
                f"{len(segments)} segments, "
                f"{total_speech:.1f}s speech / {audio_duration:.1f}s total"
            )
            return result

        except asyncio.TimeoutError:
            logger.error(
                f"speaker_diarizer: timeout after {self._timeout_sec}s "
                f"for {video_path}"
            )
            return None

        except MemoryError:
            logger.error("speaker_diarizer: OOM during diarization")
            return None

        except Exception as e:
            logger.error(f"speaker_diarizer: diarization failed: {e}")
            return None

        finally:
            # ALWAYS clean up temp audio
            if audio_path and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass

    # ─── Internal Methods ─────────────────────────────────────────────────────

    def _run_diarization(self, audio_path: str):
        """Synchronous PyAnnote diarization call (run in thread).

        Args:
            audio_path: Path to WAV audio file.

        Returns:
            PyAnnote Annotation object or None on failure.
        """
        try:
            diarization = self._pipeline(
                audio_path,
                min_speakers=self._min_speakers,
                max_speakers=self._max_speakers,
            )
            return diarization
        except Exception as e:
            logger.error(f"speaker_diarizer: pipeline execution failed: {e}")
            return None

    async def _extract_audio(self, video_path: str) -> Optional[str]:
        """Extract audio from video to temp WAV file (16kHz mono PCM).

        Uses FFmpeg via asyncio.create_subprocess_exec.

        Args:
            video_path: Path to input video/audio file.

        Returns:
            Path to temp WAV file on success, None on failure.
        """
        try:
            # Create temp file for audio output
            fd, audio_path = tempfile.mkstemp(suffix=".wav", prefix="diarize_")
            os.close(fd)

            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-vn",
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                audio_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(
                    f"speaker_diarizer: FFmpeg audio extraction failed "
                    f"(code {process.returncode}): {stderr.decode()[:200]}"
                )
                # Clean up failed output
                if os.path.exists(audio_path):
                    os.unlink(audio_path)
                return None

            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                logger.error("speaker_diarizer: extracted audio file is empty")
                if os.path.exists(audio_path):
                    os.unlink(audio_path)
                return None

            return audio_path

        except Exception as e:
            logger.error(f"speaker_diarizer: audio extraction failed: {e}")
            return None

    async def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio file duration via FFprobe.

        Args:
            audio_path: Path to audio file.

        Returns:
            Duration in seconds, 0.0 on failure.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            stdout, _ = await process.communicate()

            if process.returncode == 0 and stdout.strip():
                return float(stdout.strip())

        except Exception as e:
            logger.warning(f"speaker_diarizer: duration probe failed: {e}")

        return 0.0

    # ─── Cleanup ──────────────────────────────────────────────────────────────

    def unload(self) -> None:
        """Unload pipeline and free memory."""
        if self._pipeline is not None:
            del self._pipeline
            self._pipeline = None
            gc.collect()
            logger.info("speaker_diarizer: model unloaded")
