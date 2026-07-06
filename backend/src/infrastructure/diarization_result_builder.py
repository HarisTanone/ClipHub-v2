"""DiarizationResultBuilder — Converts diarization + speaker-face mapping into ActiveSpeakerResult.

Bridges the PyAnnote diarization pipeline with the existing dynamic panning system
by producing an ActiveSpeakerResult that downstream code already understands.

This means ZERO changes needed in the panning/framing layer — it receives the
same data structure whether the source is lip-movement detection or diarization.
"""
import logging
from typing import Dict, List, Optional

from src.infrastructure.active_speaker_detector import ActiveSpeakerResult, SpeakerSegment
from src.infrastructure.speaker_diarizer import DiarizationResult, DiarizationSegment
from src.infrastructure.speaker_face_mapper import MappingResult

logger = logging.getLogger(__name__)


class DiarizationResultBuilder:
    """Converts PyAnnote diarization output + speaker-face mapping into ActiveSpeakerResult.

    The downstream dynamic panning code expects an ActiveSpeakerResult with:
      - per_frame_speaker: frame_idx → track_id (sampled at regular intervals)
      - segments: list of SpeakerSegment with track_id-based speaker_id
      - dominant_speaker_id / dominant_ratio for framing bias
      - total_speakers count

    This builder constructs that from DiarizationResult + MappingResult so that
    the panning pipeline requires zero modifications.
    """

    @staticmethod
    def build(
        diarization: DiarizationResult,
        mapping: MappingResult,
        fps: float,
        total_frames: int,
        stable_positions: Dict[int, float],
        sample_interval_sec: float = 1.0,
        track_to_position: Optional[Dict[int, int]] = None,
    ) -> ActiveSpeakerResult:
        """Build ActiveSpeakerResult from diarization and speaker-face mapping.

        Args:
            diarization: Full diarization result with timed speaker segments.
            mapping: Speaker-to-face-track mapping with confidence scores.
            fps: Video frame rate (frames per second).
            total_frames: Total number of frames in the video.
            stable_positions: Dict mapping track_id to median X position.
                              Used to convert track_ids to positional indices
                              (0=leftmost, 1=next, etc.) matching the downstream
                              panning convention.
            sample_interval_sec: Interval between per-frame samples (seconds).
                                 Default 1.0 means one sample per second.
            track_to_position: Optional precomputed mapping from raw tracker IDs
                               to consolidated positional IDs.

        Returns:
            ActiveSpeakerResult compatible with the dynamic panning pipeline.
        """
        logger.info(
            f"diarization_result_builder: building result from "
            f"{len(diarization.segments)} segments, "
            f"{len(mapping.mappings)} mappings, "
            f"fps={fps}, total_frames={total_frames}"
        )

        # Build track_id → positional_index (0=leftmost, 1=next, etc.)
        if track_to_position is None:
            sorted_track_ids = sorted(stable_positions.keys(), key=lambda tid: stable_positions[tid])
            track_to_position = {tid: idx for idx, tid in enumerate(sorted_track_ids)}
        else:
            track_to_position = {
                int(track_id): int(position_id)
                for track_id, position_id in track_to_position.items()
            }

        logger.debug(
            f"diarization_result_builder: track_to_position mapping: {track_to_position}"
        )

        # Step 1: Build per_frame_speaker dict
        per_frame_speaker = DiarizationResultBuilder._build_per_frame_speaker(
            diarization, mapping, fps, total_frames, sample_interval_sec,
            track_to_position,
        )

        # Step 2: Build segments list
        segments = DiarizationResultBuilder._build_segments(
            diarization, mapping, track_to_position
        )

        # Step 3: Calculate dominant speaker
        dominant_speaker_id, dominant_ratio = (
            DiarizationResultBuilder._calculate_dominant_speaker(segments)
        )

        result = ActiveSpeakerResult(
            segments=segments,
            dominant_speaker_id=dominant_speaker_id,
            dominant_ratio=dominant_ratio,
            per_frame_speaker=per_frame_speaker,
            total_speakers=diarization.speaker_count,
        )

        logger.info(
            f"diarization_result_builder: built result with "
            f"{len(segments)} segments, "
            f"{len(per_frame_speaker)} frame samples, "
            f"dominant_speaker={dominant_speaker_id} ({dominant_ratio:.2f})"
        )

        return result

    @staticmethod
    def _build_per_frame_speaker(
        diarization: DiarizationResult,
        mapping: MappingResult,
        fps: float,
        total_frames: int,
        sample_interval_sec: float,
        track_to_position: Dict[int, int],
    ) -> Dict[int, int]:
        """Build per-frame speaker dictionary by sampling at regular intervals.

        Iterates from frame 0 to total_frames stepping by (fps * sample_interval_sec).
        For each sample frame, finds the active speaker at that timestamp and maps
        it to the corresponding positional index (0=leftmost, 1=rightmost, etc.).

        Args:
            diarization: Diarization result with segments.
            mapping: Speaker-to-track mapping.
            fps: Video frame rate.
            total_frames: Total frames in video.
            sample_interval_sec: Seconds between samples.
            track_to_position: Mapping from track_id to positional index.

        Returns:
            Dict mapping frame_idx to active speaker positional index.
        """
        per_frame_speaker: Dict[int, int] = {}
        step = int(fps * sample_interval_sec)

        if step < 1:
            step = 1

        frame_idx = 0
        while frame_idx < total_frames:
            timestamp = frame_idx / fps

            # Find active speaker at this timestamp (linear scan)
            active_speaker = DiarizationResultBuilder._find_active_speaker(
                diarization.segments, timestamp
            )

            if active_speaker is not None and active_speaker in mapping.mappings:
                track_id = mapping.mappings[active_speaker].track_id
                # Convert track_id to positional index (0=left, 1=right, etc.)
                if track_id in track_to_position:
                    per_frame_speaker[frame_idx] = track_to_position[track_id]

            frame_idx += step

        return per_frame_speaker

    @staticmethod
    def _find_active_speaker(
        segments: List[DiarizationSegment],
        timestamp: float,
    ) -> Optional[str]:
        """Find which speaker is active at the given timestamp.

        Linear scan through segments. Returns the speaker label of the
        first segment that contains the timestamp, or None if silent.

        Args:
            segments: List of diarization segments.
            timestamp: Time in seconds to query.

        Returns:
            Speaker label string or None if no one is speaking.
        """
        for seg in segments:
            if seg.start <= timestamp <= seg.end:
                return seg.speaker
        return None

    @staticmethod
    def _build_segments(
        diarization: DiarizationResult,
        mapping: MappingResult,
        track_to_position: Dict[int, int],
    ) -> List[SpeakerSegment]:
        """Convert DiarizationSegments to SpeakerSegments using the face mapping.

        Skips segments whose speaker has no mapping (unmapped speakers) or
        whose track_id is not in the positional mapping.

        Args:
            diarization: Diarization result with raw segments.
            mapping: Speaker-to-track mapping with confidence.
            track_to_position: Mapping from track_id to positional index.

        Returns:
            List of SpeakerSegment with positional-index-based speaker_id.
        """
        segments: List[SpeakerSegment] = []

        for seg in diarization.segments:
            if seg.speaker not in mapping.mappings:
                logger.debug(
                    f"diarization_result_builder: skipping segment for "
                    f"unmapped speaker {seg.speaker}"
                )
                continue

            speaker_mapping = mapping.mappings[seg.speaker]
            track_id = speaker_mapping.track_id

            if track_id not in track_to_position:
                logger.debug(
                    f"diarization_result_builder: skipping segment for "
                    f"track_id {track_id} not in stable_positions"
                )
                continue

            segments.append(
                SpeakerSegment(
                    speaker_id=track_to_position[track_id],
                    start_time=seg.start,
                    end_time=seg.end,
                    confidence=speaker_mapping.confidence,
                )
            )

        return segments

    @staticmethod
    def _calculate_dominant_speaker(
        segments: List[SpeakerSegment],
    ) -> tuple:
        """Calculate which speaker has the highest total speaking duration.

        Args:
            segments: List of SpeakerSegment with durations.

        Returns:
            Tuple of (dominant_speaker_id, dominant_ratio).
            Returns (None, 0.0) if no segments exist.
        """
        if not segments:
            return None, 0.0

        # Sum durations per track_id
        duration_by_speaker: Dict[int, float] = {}
        for seg in segments:
            duration = seg.end_time - seg.start_time
            duration_by_speaker[seg.speaker_id] = (
                duration_by_speaker.get(seg.speaker_id, 0.0) + duration
            )

        total_duration = sum(duration_by_speaker.values())

        if total_duration <= 0:
            return None, 0.0

        dominant_speaker_id = max(duration_by_speaker, key=duration_by_speaker.get)
        dominant_ratio = duration_by_speaker[dominant_speaker_id] / total_duration

        return dominant_speaker_id, dominant_ratio
