"""ProsodyAnalyzer — Audio prosody analysis for intelligent visual placement.

Analyzes audio waveform to detect:
- Silence gaps (opportunities for b-roll/transitions)
- Energy peaks (moments for zoom/emphasis)
- Speaking rate per segment (fast = high energy, slow = dramatic)
- Volume envelope (loud = emphasis, quiet = intimate)

Uses pydub for audio analysis (no heavy ML dependencies).
"""
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SilenceGap:
    """A silence gap in the audio — opportunity for visual event."""
    start: float
    end: float
    duration: float

    @property
    def midpoint(self) -> float:
        return (self.start + self.end) / 2.0


@dataclass
class EnergyPeak:
    """A moment of high audio energy — opportunity for emphasis."""
    time: float
    intensity: float  # 0.0 → 1.0 (normalized)


@dataclass
class ProsodyResult:
    """Full prosody analysis result for a clip."""
    silence_gaps: list[SilenceGap] = field(default_factory=list)
    energy_peaks: list[EnergyPeak] = field(default_factory=list)
    avg_speaking_rate: float = 0.0  # words per second
    volume_envelope: list[tuple[float, float]] = field(default_factory=list)  # [(time, rms)]
    duration: float = 0.0


class ProsodyAnalyzer:
    """Lightweight audio prosody analyzer using FFmpeg + basic signal processing."""

    def __init__(self, silence_threshold_db: float = -35.0, silence_min_duration: float = 0.6):
        self._silence_threshold = silence_threshold_db
        self._silence_min_duration = silence_min_duration

    def analyze(self, audio_path: str, words: Optional[list[dict]] = None) -> ProsodyResult:
        """Analyze audio file for prosody features.

        Args:
            audio_path: Path to audio/video file
            words: Optional word list from Whisper [{word, start, end}]

        Returns:
            ProsodyResult with silence gaps, energy peaks, speaking rate
        """
        if not os.path.exists(audio_path):
            logger.warning(f"prosody_analyzer: file not found {audio_path}")
            return ProsodyResult()

        result = ProsodyResult()

        # Get duration
        result.duration = self._get_duration(audio_path)

        # Detect silence gaps using FFmpeg silencedetect
        result.silence_gaps = self._detect_silence(audio_path)

        # Detect energy peaks using FFmpeg astats/volumedetect
        result.energy_peaks = self._detect_energy_peaks(audio_path)

        # Calculate speaking rate from words
        if words:
            result.avg_speaking_rate = self._calc_speaking_rate(words, result.duration)

        logger.info(
            f"prosody_analyzer: {len(result.silence_gaps)} gaps, "
            f"{len(result.energy_peaks)} peaks, "
            f"rate={result.avg_speaking_rate:.1f} wps"
        )
        return result

    def _get_duration(self, path: str) -> float:
        """Get audio duration using ffprobe."""
        try:
            cmd = ["ffprobe", "-v", "quiet", "-show_format", "-of", "json", path]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                import json
                data = json.loads(r.stdout)
                return float(data.get("format", {}).get("duration", 0))
        except Exception:
            pass
        return 0.0

    def _detect_silence(self, audio_path: str) -> list[SilenceGap]:
        """Detect silence gaps using FFmpeg silencedetect filter."""
        cmd = [
            "ffmpeg", "-i", audio_path,
            "-af", f"silencedetect=noise={self._silence_threshold}dB:d={self._silence_min_duration}",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            stderr = result.stderr

            # Parse silencedetect output
            import re
            starts = re.findall(r"silence_start: ([\d.]+)", stderr)
            ends = re.findall(r"silence_end: ([\d.]+)", stderr)

            gaps = []
            for i in range(min(len(starts), len(ends))):
                s = float(starts[i])
                e = float(ends[i])
                dur = e - s
                if dur >= self._silence_min_duration:
                    gaps.append(SilenceGap(start=s, end=e, duration=dur))

            return gaps
        except Exception as e:
            logger.debug(f"prosody: silence detection failed: {e}")
            return []

    def _detect_energy_peaks(self, audio_path: str, window_size: float = 0.5) -> list[EnergyPeak]:
        """Detect energy peaks by sampling RMS over time windows.

        Uses FFmpeg to extract volume information per time window.
        """
        # Get raw volume data using astats
        cmd = [
            "ffmpeg", "-i", audio_path,
            "-af", f"asetnsamples=n={int(48000 * window_size)},astats=metadata=1:reset=1",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            stderr = result.stderr

            # Parse RMS levels from astats output
            import re
            rms_values = re.findall(r"lavfi\.astats\.\d+\.RMS_level=([-\d.]+)", stderr)

            if not rms_values:
                return []

            # Convert to float, normalize to 0-1
            rms_floats = [float(v) for v in rms_values if v != "-inf"]
            if not rms_floats:
                return []

            max_rms = max(rms_floats)
            min_rms = min(rms_floats)
            rms_range = max_rms - min_rms if max_rms != min_rms else 1.0

            # Find peaks (top 20% of energy)
            threshold = min_rms + rms_range * 0.75
            peaks = []
            for i, rms in enumerate(rms_floats):
                if rms >= threshold:
                    time = i * window_size
                    intensity = (rms - min_rms) / rms_range
                    peaks.append(EnergyPeak(time=round(time, 2), intensity=round(intensity, 3)))

            # Deduplicate: keep peaks that are at least 2s apart
            filtered = []
            for peak in sorted(peaks, key=lambda p: -p.intensity):
                if not filtered or all(abs(peak.time - p.time) >= 2.0 for p in filtered):
                    filtered.append(peak)
                if len(filtered) >= 10:  # Max 10 peaks per clip
                    break

            return sorted(filtered, key=lambda p: p.time)

        except Exception as e:
            logger.debug(f"prosody: energy detection failed: {e}")
            return []

    def _calc_speaking_rate(self, words: list[dict], duration: float) -> float:
        """Calculate average speaking rate (words per second)."""
        if not words or duration <= 0:
            return 0.0
        # Filter out filler tokens like "-"
        real_words = [w for w in words if len(w.get("word", "")) > 1]
        return len(real_words) / duration
