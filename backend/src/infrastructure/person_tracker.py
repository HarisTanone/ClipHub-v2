"""Person Tracker — Simple IoU-based face/person tracking across frames.

Provides consistent person IDs across video frames without external dependencies.
Solves the "left/right swap" problem where sorting faces by X position per frame
causes identity switches when people move.

Algorithm:
  1. Each detection gets matched to existing tracks by IoU (Intersection over Union)
  2. IoU > threshold → same person (update track)
  3. No match → new track (assign new ID)
  4. Track not seen for N frames → mark lost → eventually remove
  5. Track ID persists across entire video

Optimized for podcast format:
  - Multiple stable people in the frame
  - Stable positions (IoU works well)
  - Frontal or semi-frontal faces (consistent bbox shape)
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BBox:
    """Bounding box in pixel coordinates."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return max(0, self.width) * max(0, self.height)

    @classmethod
    def from_relative(cls, xmin: float, ymin: float, w: float, h: float,
                      frame_w: int, frame_h: int) -> "BBox":
        """Create from MediaPipe-style relative coordinates."""
        x1 = xmin * frame_w
        y1 = ymin * frame_h
        x2 = (xmin + w) * frame_w
        y2 = (ymin + h) * frame_h
        return cls(x1, y1, x2, y2)


@dataclass
class Track:
    """A tracked person across frames."""
    track_id: int
    bbox: BBox                     # Last known position
    last_seen_frame: int           # Frame index where last detected
    first_seen_frame: int          # Frame index where first detected
    hits: int = 1                  # Number of frames this track was seen
    lost_count: int = 0            # Consecutive frames not matched
    avg_center_x: float = 0.0     # Running average X position
    positions_x: List[float] = field(default_factory=list)


@dataclass
class TrackedDetection:
    """A single detection matched to a track."""
    track_id: int
    bbox: BBox
    frame_idx: int
    is_new: bool = False           # True if this is a newly created track
    person_bbox: Optional[BBox] = None # Full person bounding box (for person-first reframe)
    face_bbox: Optional[BBox] = None  # Optional face bbox (for person-first mode)


class SimpleIoUTracker:
    """IoU-based multi-object tracker. No external dependencies.

    Designed for:
    - Podcast scenes with multiple stable people
    - Works with face bounding boxes from MediaPipe
    - Gracefully handles temporary face occlusion
    """

    IOU_THRESHOLD = 0.20           # IoU > 0.2 → same person (low because faces are small)
    MAX_LOST_FRAMES = 8            # Remove track after 8 missed frames
    DISTANCE_FALLBACK = 0.25      # If IoU fails, use center distance (fraction of frame width)

    def __init__(self, frame_width: int = 1920, frame_height: int = 1080):
        self._next_id: int = 0
        self._tracks: Dict[int, Track] = {}
        self._frame_width = frame_width
        self._frame_height = frame_height

    @property
    def active_tracks(self) -> Dict[int, Track]:
        """Get currently active (non-lost) tracks."""
        return {tid: t for tid, t in self._tracks.items() if t.lost_count == 0}

    @property
    def all_tracks(self) -> Dict[int, Track]:
        """Get all tracks including recently lost."""
        return dict(self._tracks)

    @property
    def person_count(self) -> int:
        """Current number of tracked persons (active only)."""
        return len(self.active_tracks)

    def update(self, detections: List[BBox], frame_idx: int) -> List[TrackedDetection]:
        """Update tracker with new frame detections.

        Args:
            detections: List of bounding boxes detected in current frame
            frame_idx: Current frame index

        Returns:
            List of TrackedDetection with assigned track IDs
        """
        # Increment lost count for all tracks
        for track in self._tracks.values():
            track.lost_count += 1

        if not detections:
            # No detections — all tracks continue losing
            self._prune_lost_tracks()
            return []

        if not self._tracks:
            # No existing tracks — create new ones for all detections
            results = []
            for det_bbox in detections:
                track = self._create_track(det_bbox, frame_idx)
                results.append(TrackedDetection(
                    track_id=track.track_id,
                    bbox=det_bbox,
                    frame_idx=frame_idx,
                    is_new=True,
                ))
            return results

        # Match detections to existing tracks
        matched_det_indices, matched_track_ids, unmatched_dets = self._match(detections)

        results: List[TrackedDetection] = []

        # Update matched tracks
        for det_idx, track_id in zip(matched_det_indices, matched_track_ids):
            track = self._tracks[track_id]
            det_bbox = detections[det_idx]
            track.bbox = det_bbox
            track.last_seen_frame = frame_idx
            track.hits += 1
            track.lost_count = 0
            track.positions_x.append(det_bbox.center_x)
            track.avg_center_x = float(np.mean(track.positions_x[-20:]))  # Last 20 positions

            results.append(TrackedDetection(
                track_id=track_id,
                bbox=det_bbox,
                frame_idx=frame_idx,
                is_new=False,
            ))

        # Create new tracks for unmatched detections
        for det_idx in unmatched_dets:
            det_bbox = detections[det_idx]
            track = self._create_track(det_bbox, frame_idx)
            results.append(TrackedDetection(
                track_id=track.track_id,
                bbox=det_bbox,
                frame_idx=frame_idx,
                is_new=True,
            ))

        # Remove long-lost tracks
        self._prune_lost_tracks()

        return results

    def _match(self, detections: List[BBox]) -> Tuple[List[int], List[int], List[int]]:
        """Match detections to tracks using IoU + distance fallback.

        Returns:
            (matched_det_indices, matched_track_ids, unmatched_det_indices)
        """
        track_ids = list(self._tracks.keys())
        n_dets = len(detections)
        n_tracks = len(track_ids)

        if n_dets == 0 or n_tracks == 0:
            return [], [], list(range(n_dets))

        # Compute IoU matrix: [n_dets x n_tracks]
        iou_matrix = np.zeros((n_dets, n_tracks))
        for d_idx, det_bbox in enumerate(detections):
            for t_idx, track_id in enumerate(track_ids):
                track = self._tracks[track_id]
                iou = self._compute_iou(det_bbox, track.bbox)
                iou_matrix[d_idx, t_idx] = iou

        # Greedy matching: highest IoU first
        matched_det_indices: List[int] = []
        matched_track_ids: List[int] = []
        used_dets: set = set()
        used_tracks: set = set()

        # First pass: IoU matching
        while True:
            if iou_matrix.size == 0:
                break
            max_iou = iou_matrix.max()
            if max_iou < self.IOU_THRESHOLD:
                break

            d_idx, t_idx = np.unravel_index(iou_matrix.argmax(), iou_matrix.shape)
            d_idx, t_idx = int(d_idx), int(t_idx)

            matched_det_indices.append(d_idx)
            matched_track_ids.append(track_ids[t_idx])
            used_dets.add(d_idx)
            used_tracks.add(t_idx)

            # Zero out matched row and column
            iou_matrix[d_idx, :] = 0
            iou_matrix[:, t_idx] = 0

        # Second pass: distance-based fallback for unmatched
        unmatched_dets_round1 = [i for i in range(n_dets) if i not in used_dets]
        unmatched_tracks_round1 = [i for i in range(n_tracks) if i not in used_tracks]

        for d_idx in list(unmatched_dets_round1):
            det_bbox = detections[d_idx]
            best_dist = float('inf')
            best_t_idx = -1

            for t_idx in unmatched_tracks_round1:
                track = self._tracks[track_ids[t_idx]]
                dist = self._center_distance(det_bbox, track.bbox)
                # Normalize by frame width
                dist_ratio = dist / self._frame_width

                if dist_ratio < self.DISTANCE_FALLBACK and dist < best_dist:
                    best_dist = dist
                    best_t_idx = t_idx

            if best_t_idx >= 0:
                matched_det_indices.append(d_idx)
                matched_track_ids.append(track_ids[best_t_idx])
                used_dets.add(d_idx)
                unmatched_tracks_round1.remove(best_t_idx)

        unmatched_dets = [i for i in range(n_dets) if i not in used_dets]
        return matched_det_indices, matched_track_ids, unmatched_dets

    def _create_track(self, bbox: BBox, frame_idx: int) -> Track:
        """Create a new track."""
        track = Track(
            track_id=self._next_id,
            bbox=bbox,
            last_seen_frame=frame_idx,
            first_seen_frame=frame_idx,
            hits=1,
            lost_count=0,
            avg_center_x=bbox.center_x,
            positions_x=[bbox.center_x],
        )
        self._tracks[self._next_id] = track
        self._next_id += 1
        logger.debug(f"tracker: new track ID={track.track_id} at x={bbox.center_x:.0f}")
        return track

    def _prune_lost_tracks(self):
        """Remove tracks that have been lost for too long."""
        to_remove = [
            tid for tid, track in self._tracks.items()
            if track.lost_count > self.MAX_LOST_FRAMES
        ]
        for tid in to_remove:
            logger.debug(f"tracker: pruning track ID={tid} (lost too long)")
            del self._tracks[tid]

    @staticmethod
    def _compute_iou(bbox_a: BBox, bbox_b: BBox) -> float:
        """Compute Intersection over Union between two bounding boxes."""
        x1 = max(bbox_a.x1, bbox_b.x1)
        y1 = max(bbox_a.y1, bbox_b.y1)
        x2 = min(bbox_a.x2, bbox_b.x2)
        y2 = min(bbox_a.y2, bbox_b.y2)

        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        if intersection == 0:
            return 0.0

        union = bbox_a.area + bbox_b.area - intersection
        if union <= 0:
            return 0.0

        return intersection / union

    @staticmethod
    def _center_distance(bbox_a: BBox, bbox_b: BBox) -> float:
        """Euclidean distance between centers."""
        dx = bbox_a.center_x - bbox_b.center_x
        dy = bbox_a.center_y - bbox_b.center_y
        return (dx * dx + dy * dy) ** 0.5

    def get_stable_positions(self) -> Dict[int, float]:
        """Get stable X positions per track (median of all observations).

        Returns: Dict[track_id, median_x_position]
        """
        positions = {}
        for tid, track in self._tracks.items():
            if track.positions_x:
                positions[tid] = float(np.median(track.positions_x))
        return positions

    def reset(self):
        """Reset tracker state."""
        self._tracks.clear()
        self._next_id = 0
