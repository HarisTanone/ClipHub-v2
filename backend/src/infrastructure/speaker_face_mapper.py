"""SpeakerFaceMapper — Correlates PyAnnote speaker IDs to IoU tracker face track IDs.

Uses temporal co-occurrence counting to determine which diarization speaker
corresponds to which visual face track. Designed for podcast scenarios where
speakers have stable face positions.

Algorithm overview:
  1. For each sampled frame, determine which speaker is active (from diarization)
     and which face tracks are visible (from IoU tracker output).
  2. Build a co-occurrence matrix: cooccurrence[speaker_label][track_id] += 1
     each time a speaker is active while a track is visible in the same frame.
  3. Greedy assignment: for each speaker, pick the track with the highest count.
  4. Confidence = best_count / total_count_for_speaker (how dominant the mapping is).
  5. Conflict resolution: if two speakers map to the same track, use a spatial
     heuristic — sort speakers alphabetically, sort conflicting tracks by stable
     X position (left-to-right), and assign in order.
  6. Reliability: the overall mapping is considered reliable if all individual
     confidences meet or exceed the threshold.

Optimized for:
  - Podcast format (2-4 speakers, stable positions, frontal faces)
  - Works with sampled frames (not every frame needed)
  - Graceful handling of unmapped speakers/tracks
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.infrastructure.person_tracker import TrackedDetection
from src.infrastructure.speaker_diarizer import DiarizationSegment

logger = logging.getLogger(__name__)


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class SpeakerFaceMapping:
    """Mapping from a single diarization speaker to a face track.

    Attributes:
        speaker_label: The PyAnnote speaker label (e.g., "SPEAKER_00").
        track_id: The IoU tracker face track ID this speaker maps to.
        confidence: How confident the mapping is (0.0-1.0).
                    Computed as best_count / total_count for this speaker.
        frame_count: Total number of frames where this speaker was active
                     and at least one track was visible.
    """

    speaker_label: str
    track_id: int
    confidence: float
    frame_count: int


@dataclass
class MappingResult:
    """Full result from speaker-to-face mapping.

    Attributes:
        mappings: Dict of speaker_label → SpeakerFaceMapping for successful mappings.
        overall_confidence: Minimum confidence across all mappings (worst-case indicator).
        is_reliable: True if all confidences >= the configured threshold.
        unmapped_speakers: Speakers that couldn't be mapped to any track.
        unmapped_tracks: Track IDs that weren't assigned to any speaker.
    """

    mappings: Dict[str, SpeakerFaceMapping] = field(default_factory=dict)
    overall_confidence: float = 0.0
    is_reliable: bool = False
    unmapped_speakers: List[str] = field(default_factory=list)
    unmapped_tracks: List[int] = field(default_factory=list)


# ─── Speaker Face Mapper ──────────────────────────────────────────────────────


class SpeakerFaceMapper:
    """Correlates PyAnnote speaker IDs to IoU tracker face track IDs.

    Uses temporal co-occurrence: if speaker X is talking while face track Y
    is visible in the frame, that's evidence they're the same person.

    The more frames they co-occur in, the stronger the mapping.

    Args:
        confidence_threshold: Minimum confidence required for a mapping to be
                              considered reliable. Default 0.5 (majority rule).
    """

    def __init__(self, confidence_threshold: float = 0.5):
        self._confidence_threshold = confidence_threshold

    def build_mapping(
        self,
        diarization_segments: List[DiarizationSegment],
        per_frame_tracked: List[List[TrackedDetection]],
        sample_timestamps: List[float],
        stable_positions: Dict[int, float],
    ) -> MappingResult:
        """Build speaker-to-face-track mapping using temporal co-occurrence.

        Algorithm:
          1. For each sampled frame (indexed into per_frame_tracked):
             - Look up the timestamp from sample_timestamps[frame_idx]
             - Find which speaker is active at that time via linear scan
               through diarization_segments
             - For each TrackedDetection visible in that frame, increment
               cooccurrence[speaker][track_id]
          2. Greedy assignment: for each speaker, pick track with highest count
          3. Confidence = best_count / total_count_for_speaker
          4. Conflict resolution: if 2 speakers map to the same track, use
             spatial heuristic (sort speakers by label, sort tracks by X
             position from stable_positions, assign left-to-right)
          5. is_reliable = all confidences >= threshold

        Args:
            diarization_segments: List of DiarizationSegment from PyAnnote.
            per_frame_tracked: List of TrackedDetection lists, one per sampled frame.
            sample_timestamps: Timestamp (seconds) for each sampled frame index.
            stable_positions: Dict[track_id → median X position] from the tracker.

        Returns:
            MappingResult with all mappings and reliability info.
        """
        if not diarization_segments or not per_frame_tracked:
            logger.warning("speaker_face_mapper: empty input, returning empty result")
            return MappingResult()

        # Step 1: Build co-occurrence matrix
        cooccurrence = self._build_cooccurrence(
            diarization_segments, per_frame_tracked, sample_timestamps
        )

        if not cooccurrence:
            logger.warning("speaker_face_mapper: no co-occurrences found")
            all_speakers = list({seg.speaker for seg in diarization_segments})
            all_tracks = list(stable_positions.keys())
            return MappingResult(
                unmapped_speakers=all_speakers,
                unmapped_tracks=all_tracks,
            )

        # Step 2: Greedy assignment
        raw_mappings = self._greedy_assign(cooccurrence)

        # Step 3: Detect and resolve conflicts
        resolved_mappings = self._resolve_conflicts(
            raw_mappings, cooccurrence, stable_positions
        )

        # Step 4: Build final result
        return self._build_result(
            resolved_mappings, cooccurrence, diarization_segments, stable_positions
        )

    def _build_cooccurrence(
        self,
        diarization_segments: List[DiarizationSegment],
        per_frame_tracked: List[List[TrackedDetection]],
        sample_timestamps: List[float],
    ) -> Dict[str, Dict[int, int]]:
        """Build co-occurrence matrix: cooccurrence[speaker][track_id] = count.

        For each sampled frame, finds the active speaker and increments
        the count for every visible track in that frame.

        Uses linear scan through diarization segments to find active speaker.
        This is acceptable because segment counts are typically small (<100).
        """
        cooccurrence: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))

        num_frames = min(len(per_frame_tracked), len(sample_timestamps))

        for frame_idx in range(num_frames):
            timestamp = sample_timestamps[frame_idx]
            tracked_in_frame = per_frame_tracked[frame_idx]

            if not tracked_in_frame:
                continue

            # Find active speaker at this timestamp (linear scan)
            active_speaker = self._find_active_speaker(
                diarization_segments, timestamp
            )

            if active_speaker is None:
                continue

            # Increment co-occurrence for every visible track
            for detection in tracked_in_frame:
                cooccurrence[active_speaker][detection.track_id] += 1

        return dict(cooccurrence)

    def _find_active_speaker(
        self,
        segments: List[DiarizationSegment],
        timestamp: float,
    ) -> Optional[str]:
        """Find which speaker is active at the given timestamp.

        Linear scan through segments. Returns the speaker label of the
        first segment that contains the timestamp, or None if no speaker
        is active.
        """
        for seg in segments:
            if seg.start <= timestamp <= seg.end:
                return seg.speaker
        return None

    def _greedy_assign(
        self,
        cooccurrence: Dict[str, Dict[int, int]],
    ) -> Dict[str, Tuple[int, float, int]]:
        """Greedy assignment: for each speaker, pick the track with highest count.

        Uses margin-based confidence: measures how dominant top1 is compared to top2.
        This works much better for 3+ people where co-occurrence is naturally spread
        (multiple faces visible in the same frame).

        Returns:
            Dict[speaker_label → (track_id, confidence, total_count)]
        """
        mappings: Dict[str, Tuple[int, float, int]] = {}

        for speaker, track_counts in cooccurrence.items():
            if not track_counts:
                continue

            total_count = sum(track_counts.values())
            sorted_counts = sorted(track_counts.values(), reverse=True)
            best_track = max(track_counts, key=track_counts.get)
            best_count = sorted_counts[0]
            second_count = sorted_counts[1] if len(sorted_counts) > 1 else 0

            # Margin-based confidence: how dominant is top1 vs top2
            # For 2 people: top1=45, top2=3 → margin = (45-3)/45 = 0.93 (great)
            # For 3 people: top1=30, top2=12, top3=5 → margin = (30-12)/30 = 0.60 (still good)
            # Edge case: top1=20, top2=18 → margin = (20-18)/20 = 0.10 (unreliable!)
            margin_confidence = (best_count - second_count) / max(best_count, 1)

            # Also keep absolute confidence for edge cases (1 track only)
            absolute_confidence = best_count / total_count if total_count > 0 else 0.0

            # Use the better of the two (margin is primary, absolute is fallback)
            confidence = max(margin_confidence, absolute_confidence)

            mappings[speaker] = (best_track, confidence, total_count)

        return mappings

    def _resolve_conflicts(
        self,
        raw_mappings: Dict[str, Tuple[int, float, int]],
        cooccurrence: Dict[str, Dict[int, int]],
        stable_positions: Dict[int, float],
    ) -> Dict[str, Tuple[int, float, int]]:
        """Resolve conflicts where multiple speakers map to the same track.

        Spatial heuristic:
          - Sort conflicting speakers alphabetically by label
          - Sort available tracks by X position (left-to-right) from stable_positions
          - Assign in order: leftmost track to first speaker, etc.

        Non-conflicting mappings are preserved as-is.
        """
        # Find which tracks are claimed by multiple speakers
        track_to_speakers: Dict[int, List[str]] = defaultdict(list)
        for speaker, (track_id, _, _) in raw_mappings.items():
            track_to_speakers[track_id].append(speaker)

        # Separate conflicts from clean mappings
        resolved: Dict[str, Tuple[int, float, int]] = {}
        conflicting_speakers: List[str] = []

        for speaker, mapping_data in raw_mappings.items():
            track_id = mapping_data[0]
            if len(track_to_speakers[track_id]) == 1:
                # No conflict — keep as-is
                resolved[speaker] = mapping_data
            else:
                conflicting_speakers.append(speaker)

        if not conflicting_speakers:
            return resolved

        # Spatial heuristic for conflicting speakers
        logger.info(
            f"speaker_face_mapper: resolving conflict for speakers "
            f"{conflicting_speakers}"
        )

        # Gather all tracks that conflicting speakers could map to
        candidate_tracks: set = set()
        for speaker in conflicting_speakers:
            candidate_tracks.update(cooccurrence.get(speaker, {}).keys())

        # Remove tracks already assigned to non-conflicting speakers
        assigned_tracks = {t for t, _, _ in resolved.values()}
        available_tracks = sorted(
            candidate_tracks - assigned_tracks,
            key=lambda tid: stable_positions.get(tid, float("inf")),
        )

        # Sort speakers alphabetically
        conflicting_speakers.sort()

        # Assign left-to-right
        for i, speaker in enumerate(conflicting_speakers):
            if i < len(available_tracks):
                track_id = available_tracks[i]
                track_counts = cooccurrence.get(speaker, {})
                total_count = sum(track_counts.values())
                best_count = track_counts.get(track_id, 0)
                confidence = best_count / total_count if total_count > 0 else 0.0
                resolved[speaker] = (track_id, confidence, total_count)
            else:
                logger.warning(
                    f"speaker_face_mapper: no available track for speaker {speaker}"
                )

        return resolved

    def _build_result(
        self,
        resolved_mappings: Dict[str, Tuple[int, float, int]],
        cooccurrence: Dict[str, Dict[int, int]],
        diarization_segments: List[DiarizationSegment],
        stable_positions: Dict[int, float],
    ) -> MappingResult:
        """Build the final MappingResult from resolved mappings."""
        mappings: Dict[str, SpeakerFaceMapping] = {}

        for speaker, (track_id, confidence, total_count) in resolved_mappings.items():
            mappings[speaker] = SpeakerFaceMapping(
                speaker_label=speaker,
                track_id=track_id,
                confidence=confidence,
                frame_count=total_count,
            )

        # Determine unmapped speakers (in diarization but not mapped)
        all_speakers = list({seg.speaker for seg in diarization_segments})
        mapped_speakers = set(mappings.keys())
        unmapped_speakers = [s for s in all_speakers if s not in mapped_speakers]

        # Determine unmapped tracks (known tracks not assigned)
        assigned_tracks = {m.track_id for m in mappings.values()}
        all_known_tracks = set(stable_positions.keys())
        unmapped_tracks = sorted(all_known_tracks - assigned_tracks)

        # Overall confidence = minimum across all mappings
        if mappings:
            overall_confidence = min(m.confidence for m in mappings.values())
        else:
            overall_confidence = 0.0

        # Reliable if all mappings have sufficient margin between top1 and top2
        # Uses MAPPING_MARGIN_THRESHOLD (default 0.3) instead of the old absolute threshold
        is_reliable = bool(mappings) and all(
            m.confidence >= self._confidence_threshold for m in mappings.values()
        )

        result = MappingResult(
            mappings=mappings,
            overall_confidence=overall_confidence,
            is_reliable=is_reliable,
            unmapped_speakers=unmapped_speakers,
            unmapped_tracks=unmapped_tracks,
        )

        logger.info(
            f"speaker_face_mapper: mapped {len(mappings)} speakers, "
            f"confidence={overall_confidence:.2f}, reliable={is_reliable}, "
            f"unmapped_speakers={unmapped_speakers}, unmapped_tracks={unmapped_tracks}"
        )

        return result
