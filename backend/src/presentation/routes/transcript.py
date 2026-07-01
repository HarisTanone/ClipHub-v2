"""Transcript pre-check endpoint — verify subtitle availability before job submission.

Returns in ~1-2 seconds. User knows immediately if video can be processed.
"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/transcript", tags=["transcript"])
logger = logging.getLogger(__name__)


class TranscriptCheckRequest(BaseModel):
    url: str


class TranscriptCheckResponse(BaseModel):
    available: bool
    language: Optional[str] = None
    source: Optional[str] = None  # 'youtube_api' | 'groq_whisper'
    segments_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    error_code: Optional[str] = None
    message: Optional[str] = None


@router.post("/check", response_model=TranscriptCheckResponse)
async def check_transcript(req: TranscriptCheckRequest):
    """Quick check if video has usable transcript (~1-2 seconds).

    Call this BEFORE submitting a job to avoid wasting time on download
    only to discover there's no subtitle available.
    """
    try:
        from src.infrastructure.groq_transcriber import GroqTranscriber

        transcriber = GroqTranscriber()
        video_id = transcriber._extract_video_id(req.url)

        # Only check YouTube API (fast, no audio download needed)
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, transcriber._fetch_youtube_transcript_sync, video_id, 0.0
        )

        if result and result.segments:
            return TranscriptCheckResponse(
                available=True,
                language=result.language,
                source=result.source,
                segments_count=len(result.segments),
                duration_seconds=result.total_duration or (result.segments[-1].end if result.segments else 0),
                message=f"Subtitle tersedia ({result.source}, {result.language})",
            )
        else:
            return TranscriptCheckResponse(
                available=False,
                error_code="EMPTY_TRANSCRIPT",
                message="Subtitle ditemukan tapi kosong setelah filtering.",
            )

    except Exception as e:
        error_msg = str(e)
        error_code = "TRANSCRIPT_CHECK_FAILED"

        if "no transcript" in error_msg.lower() or "not available" in error_msg.lower():
            error_code = "NO_TRANSCRIPT"
            error_msg = "Video ini tidak memiliki subtitle/caption."
        elif "disabled" in error_msg.lower():
            error_code = "TRANSCRIPTS_DISABLED"
            error_msg = "Subtitle dinonaktifkan oleh pemilik video."
        elif "unavailable" in error_msg.lower() or "private" in error_msg.lower():
            error_code = "VIDEO_UNAVAILABLE"
            error_msg = "Video tidak tersedia (private/deleted)."

        logger.debug(f"Transcript check failed for {req.url}: {e}")
        return TranscriptCheckResponse(
            available=False,
            error_code=error_code,
            message=error_msg,
        )
