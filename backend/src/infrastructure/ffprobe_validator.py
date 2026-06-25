"""FFprobeValidator — validates trimmed video output using ffprobe."""
import json
import logging
import os
import subprocess
from typing import Optional

from src.domain.entities import FFprobeResult

logger = logging.getLogger(__name__)


class FFprobeValidator:
    """Validates trimmed video output using ffprobe.

    Checks duration, video stream presence, and audio stream presence.
    """

    TIMEOUT = 10  # seconds
    MIN_DURATION = 0.5  # seconds

    def validate(self, file_path: str) -> FFprobeResult:
        """Run ffprobe and verify duration, video stream, audio stream.

        Args:
            file_path: Path to the video file to validate.

        Returns:
            FFprobeResult with validation status and metadata.
        """
        # Check zero-byte file
        if not os.path.exists(file_path):
            return FFprobeResult(
                valid=False, duration=0.0, has_video=False, has_audio=False,
                error=f"File not found: {file_path}"
            )

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return FFprobeResult(
                valid=False, duration=0.0, has_video=False, has_audio=False,
                error="File is zero bytes"
            )

        # Run ffprobe
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return FFprobeResult(
                valid=False, duration=0.0, has_video=False, has_audio=False,
                error=f"ffprobe timed out after {self.TIMEOUT}s"
            )
        except FileNotFoundError:
            return FFprobeResult(
                valid=False, duration=0.0, has_video=False, has_audio=False,
                error="ffprobe not found in PATH"
            )

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else f"ffprobe exit code {result.returncode}"
            return FFprobeResult(
                valid=False, duration=0.0, has_video=False, has_audio=False,
                error=error_msg
            )

        # Parse JSON output
        try:
            probe_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return FFprobeResult(
                valid=False, duration=0.0, has_video=False, has_audio=False,
                error=f"Failed to parse ffprobe output: {e}"
            )

        # Extract duration
        duration = self._extract_duration(probe_data)

        # Check streams
        streams = probe_data.get("streams", [])
        has_video = any(s.get("codec_type") == "video" for s in streams)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)

        # Validate
        valid = (
            duration > self.MIN_DURATION
            and has_video
            and has_audio
        )

        error: Optional[str] = None
        if not valid:
            issues = []
            if duration <= self.MIN_DURATION:
                issues.append(f"duration {duration:.2f}s <= {self.MIN_DURATION}s")
            if not has_video:
                issues.append("no video stream")
            if not has_audio:
                issues.append("no audio stream")
            error = "; ".join(issues)

        return FFprobeResult(
            valid=valid,
            duration=duration,
            has_video=has_video,
            has_audio=has_audio,
            error=error,
        )

    def _extract_duration(self, probe_data: dict) -> float:
        """Extract duration from ffprobe data (format or stream level)."""
        # Try format-level duration first
        fmt = probe_data.get("format", {})
        if "duration" in fmt:
            try:
                return float(fmt["duration"])
            except (ValueError, TypeError):
                pass

        # Fallback to first stream with duration
        for stream in probe_data.get("streams", []):
            if "duration" in stream:
                try:
                    return float(stream["duration"])
                except (ValueError, TypeError):
                    continue

        return 0.0
