"""CacheManager — Persist video, transcript, and analysis for reuse.

Saves expensive pipeline outputs so re-submissions of the same URL
can skip download, transcription, and AI analysis steps.

Cached per video_id:
  - {video_id}.mp4           → Original downloaded video
  - {video_id}_transcript.json → Transcript segments (YouTube/Groq)
  - {video_id}_analysis_v1.json → Gemini analysis result
  - {video_id}_analysis_v2.json → Groq analysis result

Cache is IGNORED when force_reprocess=True.
"""
import json
import logging
import os
import re
import shutil
from dataclasses import asdict
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(settings.DOWNLOAD_DIR, "..", "cache")


class CacheManager:
    """Manages cached pipeline artifacts per video_id."""

    def __init__(self):
        self._cache_dir = os.path.abspath(CACHE_DIR)
        os.makedirs(self._cache_dir, exist_ok=True)

    # ─── Video ID Extraction ──────────────────────────────────────────────────

    @staticmethod
    def extract_video_id(url: str) -> str:
        """Extract YouTube video ID from URL."""
        patterns = [
            r"(?:v=)([a-zA-Z0-9_-]{11})",
            r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
            r"(?:embed/)([a-zA-Z0-9_-]{11})",
            r"(?:shorts/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    # ─── Paths ────────────────────────────────────────────────────────────────

    def _video_path(self, video_id: str) -> str:
        return os.path.join(self._cache_dir, f"{video_id}.mp4")

    def _transcript_path(self, video_id: str) -> str:
        return os.path.join(self._cache_dir, f"{video_id}_transcript.json")

    def _analysis_path(self, video_id: str, version: str) -> str:
        return os.path.join(self._cache_dir, f"{video_id}_analysis_{version}.json")

    # ─── Check Existence ──────────────────────────────────────────────────────

    def has_video(self, video_id: str) -> bool:
        path = self._video_path(video_id)
        return os.path.exists(path) and os.path.getsize(path) > 10000

    def has_transcript(self, video_id: str) -> bool:
        path = self._transcript_path(video_id)
        return os.path.exists(path) and os.path.getsize(path) > 100

    def has_analysis(self, video_id: str, version: str = "v2") -> bool:
        path = self._analysis_path(video_id, version)
        return os.path.exists(path) and os.path.getsize(path) > 100

    def get_cache_status(self, video_id: str, version: str = "v2") -> dict:
        """Get cache status for a video_id. Returns dict of what's available."""
        return {
            "video_id": video_id,
            "has_video": self.has_video(video_id),
            "has_transcript": self.has_transcript(video_id),
            "has_analysis": self.has_analysis(video_id, version),
            "video_path": self._video_path(video_id) if self.has_video(video_id) else None,
        }

    # ─── Save ─────────────────────────────────────────────────────────────────

    def save_video(self, video_id: str, source_path: str) -> str:
        """Copy/link video to cache. Returns cached path."""
        dest = self._video_path(video_id)
        if os.path.exists(dest):
            return dest
        try:
            # Hard link (same filesystem, no extra disk usage)
            os.link(source_path, dest)
        except OSError:
            # Cross-filesystem: copy
            shutil.copy2(source_path, dest)
        logger.info(f"cache: saved video {video_id} ({os.path.getsize(dest) / 1024 / 1024:.1f}MB)")
        return dest

    def save_transcript(self, video_id: str, transcript_data: dict) -> str:
        """Save transcript result as JSON. Returns path."""
        dest = self._transcript_path(video_id)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, ensure_ascii=False, indent=2)
        logger.info(f"cache: saved transcript {video_id} ({len(transcript_data.get('segments', []))} segments)")
        return dest

    def save_analysis(self, video_id: str, analysis_data: dict, version: str = "v2") -> str:
        """Save analysis result as JSON. Returns path."""
        dest = self._analysis_path(video_id, version)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)
        logger.info(f"cache: saved analysis_{version} {video_id} ({len(analysis_data.get('clips', []))} clips)")
        return dest

    # ─── Load ─────────────────────────────────────────────────────────────────

    def get_video_path(self, video_id: str) -> Optional[str]:
        """Get cached video path if exists."""
        path = self._video_path(video_id)
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            return path
        return None

    def load_transcript(self, video_id: str) -> Optional[dict]:
        """Load cached transcript. Returns dict or None."""
        path = self._transcript_path(video_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def load_analysis(self, video_id: str, version: str = "v2") -> Optional[dict]:
        """Load cached analysis. Returns dict or None."""
        path = self._analysis_path(video_id, version)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    # ─── Invalidate ───────────────────────────────────────────────────────────

    def invalidate(self, video_id: str) -> None:
        """Remove all cached data for a video_id (used by force_reprocess)."""
        for path in [
            self._video_path(video_id),
            self._transcript_path(video_id),
            self._analysis_path(video_id, "v1"),
            self._analysis_path(video_id, "v2"),
        ]:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"cache: invalidated {os.path.basename(path)}")
