"""Small ffprobe helpers for keeping rendered video and audio on one clock."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaTimeline:
    """Start/end timestamps reported by ffprobe for one rendered file."""

    duration: float
    video_start: float
    video_duration: float
    audio_start: Optional[float]
    audio_duration: Optional[float]

    @property
    def start_drift(self) -> float:
        if self.audio_start is None:
            return 0.0
        return abs(self.video_start - self.audio_start)

    @property
    def end_drift(self) -> float:
        if self.audio_start is None or self.audio_duration is None:
            return 0.0
        video_end = self.video_start + self.video_duration
        audio_end = self.audio_start + self.audio_duration
        return abs(video_end - audio_end)


def probe_media_timeline(path: str, timeout: int = 12) -> Optional[MediaTimeline]:
    """Return stream timelines, or ``None`` when the file cannot be probed."""
    if not os.path.exists(path) or os.path.getsize(path) <= 0:
        return None

    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_entries", "format=start_time,duration:stream=codec_type,start_time,duration",
        path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "{}")
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None

    fmt = data.get("format") or {}
    streams = data.get("streams") or []

    def number(value: object, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    duration = max(0.0, number(fmt.get("duration")))
    format_start = number(fmt.get("start_time"))

    def stream_values(codec_type: str) -> tuple[Optional[float], Optional[float]]:
        for stream in streams:
            if stream.get("codec_type") != codec_type:
                continue
            start = number(stream.get("start_time"), format_start)
            stream_duration = number(stream.get("duration"), duration)
            return start, max(0.0, stream_duration)
        return None, None

    video_start, video_duration = stream_values("video")
    if video_start is None or video_duration is None:
        return None
    audio_start, audio_duration = stream_values("audio")
    return MediaTimeline(
        duration=duration or video_duration,
        video_start=video_start,
        video_duration=video_duration,
        audio_start=audio_start,
        audio_duration=audio_duration,
    )


def timeline_is_safe(
    path: str,
    expected_duration: Optional[float] = None,
    max_start_drift: float = 0.10,
    max_end_drift: float = 0.18,
    max_duration_error: float = 0.25,
) -> bool:
    """Reject outputs with a meaningful A/V offset or unexpected truncation.

    Files without an audio stream are accepted because some source clips are
    intentionally silent. A file that cannot be probed is rejected.
    """
    timeline = probe_media_timeline(path)
    if timeline is None or timeline.video_duration <= 0:
        logger.warning("media_timeline: ffprobe failed for %s", path)
        return False

    if expected_duration is not None and expected_duration > 0:
        if abs(timeline.video_duration - expected_duration) > max_duration_error:
            logger.warning(
                "media_timeline: duration mismatch for %s (expected=%.3fs, video=%.3fs)",
                path,
                expected_duration,
                timeline.video_duration,
            )
            return False

    if timeline.audio_start is not None:
        if timeline.start_drift > max_start_drift or timeline.end_drift > max_end_drift:
            logger.warning(
                "media_timeline: A/V drift for %s (start=%.3fs, end=%.3fs)",
                path,
                timeline.start_drift,
                timeline.end_drift,
            )
            return False

    return True
