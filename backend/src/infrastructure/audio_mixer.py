"""AudioMixer — Post-production audio processing with music bed ducking.

Applies:
- Dialogue compression (even volume)
- Music bed with auto-ducking (volume drops when speaker talks)
- Optional ambient layer
- Loudness normalization (LUFS target)
"""
import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Music bed assets directory
MUSIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "music")


@dataclass
class AudioMixConfig:
    """Configuration for audio post-processing."""
    # Music bed
    music_enabled: bool = True
    music_mood: str = "energetic"  # energetic / chill / dramatic / suspense
    music_volume_db: float = -24.0  # Base music volume (before ducking)
    # Ducking (music dips when dialogue plays)
    ducking_threshold: float = 0.02  # Sensitivity (lower = more ducking)
    ducking_ratio: float = 8.0       # How much to compress
    ducking_attack_ms: float = 150.0
    ducking_release_ms: float = 800.0
    # Dialogue processing
    dialogue_compression: bool = True
    dialogue_highpass_hz: int = 80   # Remove low rumble
    # Master
    loudness_target_lufs: float = -14.0  # Spotify/YouTube standard


class AudioMixer:
    """Post-production audio mixer with music bed ducking."""

    def __init__(self, music_dir: str = ""):
        self._music_dir = music_dir or MUSIC_DIR

    def mix_audio(
        self,
        video_path: str,
        output_path: str,
        config: Optional[AudioMixConfig] = None,
    ) -> str:
        """Apply audio post-processing to video.

        Pipeline:
        1. Extract dialogue → compress + EQ
        2. Select music bed → set volume
        3. Sidechain: dialogue triggers ducking on music
        4. Mix together + loudness normalize
        5. Mux back into video

        Returns output_path on success, video_path on failure.
        """
        if not os.path.exists(video_path):
            return video_path

        cfg = config or AudioMixConfig()
        music_path = self._select_music(cfg.music_mood)

        if not cfg.music_enabled or not music_path:
            # Just apply dialogue processing (compression + normalization)
            return self._process_dialogue_only(video_path, output_path, cfg)

        return self._mix_with_music(video_path, music_path, output_path, cfg)

    def _select_music(self, mood: str) -> Optional[str]:
        """Select a music bed file based on mood."""
        if not os.path.isdir(self._music_dir):
            return None

        # Look for mood-named file
        candidates = [
            f"{mood}.mp3",
            f"{mood}.wav",
            f"{mood}_bed.mp3",
            f"bg_{mood}.mp3",
        ]
        for name in candidates:
            path = os.path.join(self._music_dir, name)
            if os.path.exists(path):
                return path

        # Fallback: any available music file
        for f in os.listdir(self._music_dir):
            if f.endswith((".mp3", ".wav", ".m4a")):
                return os.path.join(self._music_dir, f)
        return None

    def _process_dialogue_only(self, video_path: str, output_path: str, cfg: AudioMixConfig) -> str:
        """Apply compression + normalization to dialogue without music."""
        # Build audio filter chain
        filters = []

        if cfg.dialogue_compression:
            filters.append(f"highpass=f={cfg.dialogue_highpass_hz}")
            filters.append("acompressor=threshold=-20dB:ratio=4:attack=5:release=50")

        # Loudness normalization
        filters.append(f"loudnorm=I={cfg.loudness_target_lufs}:TP=-1.5:LRA=11")

        filter_chain = ",".join(filters) if filters else "anull"

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-af", filter_chain,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"audio_mixer: dialogue processed → {os.path.basename(output_path)}")
                return output_path
            logger.warning(f"audio_mixer: dialogue processing failed: {result.stderr[-200:]}")
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"audio_mixer: exception: {e}")

        return video_path

    def _mix_with_music(self, video_path: str, music_path: str, output_path: str, cfg: AudioMixConfig) -> str:
        """Mix dialogue with music bed using sidechain compression (ducking).

        FFmpeg filter graph:
        - Input 0: video (with dialogue audio)
        - Input 1: music bed
        - Apply: highpass + compressor on dialogue
        - Apply: volume reduction + sidechain compress on music (triggered by dialogue)
        - Mix together
        - Loudness normalize
        """
        # Build filter_complex for sidechain ducking
        filter_complex = (
            # Process dialogue: highpass + compression
            f"[0:a]highpass=f={cfg.dialogue_highpass_hz},"
            f"acompressor=threshold=-20dB:ratio=4:attack=5:release=50[dialogue];"
            # Process music: set volume + loop to match video duration
            f"[1:a]volume={cfg.music_volume_db}dB,"
            f"aloop=loop=-1:size=2e+09[music_raw];"
            # Sidechain compress music (duck when dialogue is loud)
            f"[music_raw][dialogue]sidechaincompress="
            f"threshold={cfg.ducking_threshold}:"
            f"ratio={cfg.ducking_ratio}:"
            f"attack={cfg.ducking_attack_ms}:"
            f"release={cfg.ducking_release_ms}[music_ducked];"
            # Mix dialogue + ducked music
            f"[dialogue][music_ducked]amix=inputs=2:duration=first:dropout_transition=3[mixed];"
            # Loudness normalize
            f"[mixed]loudnorm=I={cfg.loudness_target_lufs}:TP=-1.5:LRA=11[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[out]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info(f"audio_mixer: mixed with music ({cfg.music_mood}) → {os.path.basename(output_path)}")
                return output_path

            # Fallback: try without music if sidechain fails
            logger.warning(f"audio_mixer: music mix failed, falling back to dialogue-only: {result.stderr[-200:]}")
            return self._process_dialogue_only(video_path, output_path, cfg)

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"audio_mixer: exception: {e}")
            return video_path
