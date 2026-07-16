"""PersonTrackerV2 — ByteTrack/BoT-SORT person tracking via Ultralytics.

Replaces SimpleIoUTracker for the person-first pipeline. Uses Ultralytics'
built-in tracking which integrates BoT-SORT (with ReID + camera motion
compensation) or ByteTrack (lighter, no ReID).

Key differences from SimpleIoUTracker:
  - Tracks FULL BODY (person bbox), not just face bbox
  - BoT-SORT uses appearance features (ReID) for re-identification
  - Handles occlusion, overlapping people, and temporary disappearances
  - Track IDs persist even when person is partially occluded
  - No manual ghost elimination needed (tracker handles identity)

Output is compatible with the existing pipeline — produces TrackedPerson
objects with the same interface downstream code expects (track_id, bbox,
center_x, center_y, area).

Design:
  - Wraps Ultralytics model.track() with persist=True
  - Stateful: maintains track state across update() calls
  - Fallback to supervision ByteTrack if Ultralytics tracking unavailable
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.infrastructure.person_tracker import BBox

logger = logging.getLogger(__name__)


@dataclass
class TrackedPerson:
    """A person detection matched to a persistent track.

    Compatible interface with legacy TrackedDetection but keyed on
    person body bbox rather than face bbox.
    """
    track_id: int
    bbox: BBox                     # Full body bounding box
    frame_idx: int
    confidence: float = 0.0
    is_new: bool = False           # True if this track was just created

    @property
    def center_x(self) -> float:
        return self.bbox.center_x

    @property
    def center_y(self) -> float:
        return self.bbox.center_y


@dataclass
class TrackHistory:
    """Accumulated history for a single person track."""
    track_id: int
    positions_x: List[float] = field(default_factory=list)
    positions_y: List[float] = field(default_factory=list)
    widths: List[float] = field(default_factory=list)
    heights: List[float] = field(default_factory=list)
    areas: List[float] = field(default_factory=list)
    frame_count: int = 0
    first_seen_frame: int = 0
    last_seen_frame: int = 0


class PersonTrackerV2:
    """ByteTrack/BoT-SORT person tracker via Ultralytics.

    Designed for the person-first reframe pipeline. Tracks full body
    bounding boxes across frames with persistent IDs.

    Args:
        tracker_type: 'botsort' or 'bytetrack'.
        model_path: Path to YOLO model for tracking (default: yolo11n.pt).
        max_lost_frames: How long to keep a lost track before removal.
        frame_width: Video frame width (for normalization).
        frame_height: Video frame height (for normalization).
    """

    PERSON_CLASS_ID = 0

    def __init__(
        self,
        tracker_type: str = "botsort",
        model_path: str = "yolo11n.pt",
        max_lost_frames: int = 8,
        frame_width: int = 1920,
        frame_height: int = 1080,
    ):
        self._tracker_type = tracker_type
        self._model_path = model_path
        self._max_lost_frames = max_lost_frames
        self._frame_width = frame_width
        self._frame_height = frame_height

        self._model = None
        self._load_attempted = False
        self._load_failed = False

        # Track history accumulation
        self._track_histories: Dict[int, TrackHistory] = {}
        self._frame_counter: int = 0

        # Fallback: supervision-based tracker
        self._sv_tracker = None
        self._use_supervision_fallback = False

    @property
    def is_available(self) -> bool:
        return not self._load_failed

    @property
    def active_track_count(self) -> int:
        """Number of currently active tracks."""
        if not self._track_histories:
            return 0
        cutoff = self._frame_counter - self._max_lost_frames
        return sum(
            1 for h in self._track_histories.values()
            if h.last_seen_frame >= cutoff
        )

    def _load_model(self) -> bool:
        """Lazy-load tracker backend.

        Architecture per PRD §4.2:
          - PRIMARY: supervision ByteTrack (fed externally by RF-DETR detections)
          - FALLBACK: Ultralytics model.track() (self-contained detection+tracking
            when RF-DETR is unavailable or detections not provided)

        The supervision path is preferred because it separates detection from
        tracking, allowing RF-DETR to be the detection source as the PRD requires.
        """
        if self._sv_tracker is not None or self._model is not None:
            return True
        if self._load_attempted:
            return not self._load_failed
        self._load_attempted = True

        # Primary: supervision ByteTrack (works with external detections from RF-DETR)
        if self._try_load_supervision():
            return True

        # Fallback: Ultralytics model.track() (bundled detection+tracking)
        return self._try_load_ultralytics()

    def _try_load_supervision(self) -> bool:
        """Primary: load supervision ByteTrack for RF-DETR-fed tracking."""
        try:
            import supervision as sv
            self._sv_tracker = sv.ByteTrack(
                track_activation_threshold=0.25,
                lost_track_buffer=self._max_lost_frames,
                minimum_matching_threshold=0.8,
                frame_rate=30,
            )
            self._use_supervision_fallback = False  # It's not a fallback — it's primary
            logger.info(
                f"person_tracker_v2: supervision ByteTrack loaded (PRIMARY) "
                f"— tracking RF-DETR detections externally"
            )
            return True
        except ImportError:
            logger.debug("person_tracker_v2: supervision not available")
            return False
        except Exception as e:
            logger.warning(f"person_tracker_v2: supervision ByteTrack failed: {e}")
            return False

    def _try_load_ultralytics(self) -> bool:
        """Fallback: load Ultralytics YOLO for bundled detection+tracking."""
        try:
            from ultralytics import YOLO

            self._model = YOLO(self._model_path)
            logger.info(
                f"person_tracker_v2: Ultralytics loaded (FALLBACK) "
                f"(model={self._model_path}, tracker={self._tracker_type})"
            )
            return True
        except ImportError:
            self._load_failed = True
            logger.error("person_tracker_v2: neither supervision nor ultralytics available")
            return False
        except Exception as e:
            self._load_failed = True
            logger.error(f"person_tracker_v2: model load failed: {e}")
            return False

    def update(
        self,
        frame: np.ndarray,
        frame_idx: int,
        detections: Optional[List] = None,
    ) -> List[TrackedPerson]:
        """Update tracker with a new frame.

        Routing logic (per PRD §4.2):
          - If detections provided AND supervision loaded → feed RF-DETR detections
            to ByteTrack (preferred path, no redundant detection)
          - If no detections AND Ultralytics loaded → model.track() handles both
            detection and tracking internally (fallback path)
          - If detections provided but only Ultralytics available → still use
            model.track() (detections ignored, Ultralytics re-detects internally)

        Args:
            frame: BGR numpy array (H, W, 3).
            frame_idx: Current frame index in video.
            detections: Pre-computed PersonDetection list from PersonDetector.
                       When provided with supervision tracker, RF-DETR detections
                       are tracked directly without redundant detection.

        Returns:
            List of TrackedPerson with persistent track IDs.
        """
        if not self._load_model():
            return []

        self._frame_counter = frame_idx

        # Primary path: supervision ByteTrack fed by external detections (RF-DETR)
        if self._sv_tracker is not None and detections is not None:
            return self._update_supervision(frame, frame_idx, detections)

        # Fallback path: Ultralytics bundled detection+tracking
        if self._model is not None:
            return self._update_ultralytics(frame, frame_idx, detections)

        return []

    def _update_ultralytics(
        self,
        frame: np.ndarray,
        frame_idx: int,
        detections: Optional[List] = None,
    ) -> List[TrackedPerson]:
        """Run Ultralytics model.track() with persist=True."""
        try:
            tracker_config = f"{self._tracker_type}.yaml"

            results = self._model.track(
                source=frame,
                tracker=tracker_config,
                persist=True,
                classes=[self.PERSON_CLASS_ID],
                verbose=False,
            )

            if not results or results[0].boxes is None:
                return []

            boxes = results[0].boxes
            tracked_persons: List[TrackedPerson] = []

            # boxes.id is None if no tracks are assigned yet
            if boxes.id is None:
                return []

            for i in range(len(boxes)):
                track_id = int(boxes.id[i].cpu().numpy())
                xyxy = boxes.xyxy[i].cpu().numpy()
                conf = float(boxes.conf[i].cpu().numpy())

                bbox = BBox(
                    x1=float(xyxy[0]),
                    y1=float(xyxy[1]),
                    x2=float(xyxy[2]),
                    y2=float(xyxy[3]),
                )

                is_new = track_id not in self._track_histories
                tracked_persons.append(TrackedPerson(
                    track_id=track_id,
                    bbox=bbox,
                    frame_idx=frame_idx,
                    confidence=conf,
                    is_new=is_new,
                ))

                # Update history
                self._update_history(track_id, bbox, frame_idx)

            return tracked_persons

        except Exception as e:
            logger.warning(f"person_tracker_v2: tracking error: {e}")
            return []

    def _update_supervision(
        self,
        frame: np.ndarray,
        frame_idx: int,
        detections: Optional[List] = None,
    ) -> List[TrackedPerson]:
        """Fallback tracking using supervision ByteTrack.

        Requires pre-computed detections (from PersonDetector).
        """
        import supervision as sv

        if detections is None or len(detections) == 0:
            return []

        # Convert PersonDetection list to supervision Detections
        xyxy = np.array([
            [d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2]
            for d in detections
        ])
        confidence = np.array([d.confidence for d in detections])

        sv_detections = sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
        )

        # Run tracker
        tracked = self._sv_tracker.update_with_detections(sv_detections)

        tracked_persons: List[TrackedPerson] = []
        if tracked.tracker_id is None:
            return []

        for i in range(len(tracked)):
            track_id = int(tracked.tracker_id[i])
            x1, y1, x2, y2 = tracked.xyxy[i]

            bbox = BBox(
                x1=float(x1),
                y1=float(y1),
                x2=float(x2),
                y2=float(y2),
            )

            is_new = track_id not in self._track_histories
            tracked_persons.append(TrackedPerson(
                track_id=track_id,
                bbox=bbox,
                frame_idx=frame_idx,
                confidence=float(tracked.confidence[i]) if tracked.confidence is not None else 1.0,
                is_new=is_new,
            ))

            self._update_history(track_id, bbox, frame_idx)

        return tracked_persons

    def _update_history(self, track_id: int, bbox: BBox, frame_idx: int) -> None:
        """Accumulate track history for stable position computation."""
        if track_id not in self._track_histories:
            self._track_histories[track_id] = TrackHistory(
                track_id=track_id,
                first_seen_frame=frame_idx,
            )

        history = self._track_histories[track_id]
        history.positions_x.append(bbox.center_x)
        history.positions_y.append(bbox.center_y)
        history.widths.append(bbox.width)
        history.heights.append(bbox.height)
        history.areas.append(bbox.area)
        history.frame_count += 1
        history.last_seen_frame = frame_idx

    def get_stable_positions(self) -> Dict[int, float]:
        """Get stable X positions per track (median of all observations).

        Compatible with SimpleIoUTracker.get_stable_positions() interface.

        Returns: Dict[track_id, median_x_position]
        """
        positions: Dict[int, float] = {}
        for track_id, history in self._track_histories.items():
            if history.positions_x:
                positions[track_id] = float(np.median(history.positions_x))
        return positions

    def get_stable_profiles(self) -> Dict[int, Dict[str, float]]:
        """Get full stable profiles (X, Y, width, height, area) per track.

        Returns: Dict[track_id, {x, y, width, height, area}]
        """
        profiles: Dict[int, Dict[str, float]] = {}
        for track_id, history in self._track_histories.items():
            if not history.positions_x:
                continue
            profiles[track_id] = {
                "x": float(np.median(history.positions_x)),
                "y": float(np.median(history.positions_y)),
                "width": float(np.median(history.widths)),
                "height": float(np.median(history.heights)),
                "area": float(np.median(history.areas)),
            }
        return profiles

    def get_person_count(self, min_frame_ratio: float = 0.15) -> int:
        """Get number of distinct persons seen reliably.

        Filters out transient detections (ghosts/noise) using minimum
        frame appearance ratio.

        Args:
            min_frame_ratio: Minimum fraction of total frames a track must
                            appear in to be counted as a real person.

        Returns:
            Number of reliable person tracks.
        """
        if not self._track_histories or self._frame_counter <= 0:
            return 0

        total_sampled = self._frame_counter
        count = 0
        for history in self._track_histories.values():
            if history.frame_count / max(1, total_sampled) >= min_frame_ratio:
                count += 1
        return count

    def build_position_model(self) -> dict:
        """Build position model compatible with PodcastReframeEngine output.

        Returns dict with same structure as legacy _build_position_model():
          - person_count
          - stable_positions: Dict[track_id, median_x]
          - stable_position_profiles: Dict[track_id, {x, y, width, height, area}]
          - position_targets: Dict[position_id, median_x]
          - position_target_profiles: Dict[position_id, {x, y, ...}]
          - track_to_position: Dict[track_id, position_id]
        """
        profiles = self.get_stable_profiles()
        stable_positions = self.get_stable_positions()

        if not profiles:
            return {
                "person_count": 0,
                "stable_positions": {},
                "stable_position_profiles": {},
                "position_targets": {},
                "position_target_profiles": {},
                "track_to_position": {},
            }

        # Filter out transient tracks
        min_frames = max(2, int(self._frame_counter * 0.10))
        reliable_tracks = {
            tid: prof for tid, prof in profiles.items()
            if self._track_histories[tid].frame_count >= min_frames
        }

        if not reliable_tracks:
            reliable_tracks = profiles

        # Cluster nearby tracks into "seats" (same logic as legacy)
        clusters = self._cluster_tracks(reliable_tracks)

        # Build position mapping
        position_targets: Dict[int, float] = {}
        position_target_profiles: Dict[int, Dict[str, float]] = {}
        track_to_position: Dict[int, int] = {}

        for position_id, cluster in enumerate(clusters):
            merged_profile = self._merge_profiles(
                [reliable_tracks[tid] for tid in cluster["track_ids"]]
            )
            position_targets[position_id] = merged_profile["x"]
            position_target_profiles[position_id] = merged_profile
            for tid in cluster["track_ids"]:
                track_to_position[tid] = position_id

        # stable_positions/profiles only for reliable tracks
        stable_positions = {
            tid: prof["x"] for tid, prof in reliable_tracks.items()
        }
        stable_position_profiles = dict(reliable_tracks)

        return {
            "person_count": len(position_targets),
            "stable_positions": stable_positions,
            "stable_position_profiles": stable_position_profiles,
            "position_targets": position_targets,
            "position_target_profiles": position_target_profiles,
            "track_to_position": track_to_position,
        }

    def _cluster_tracks(
        self,
        profiles: Dict[int, Dict[str, float]],
        threshold: float = 0.12,
    ) -> List[dict]:
        """Cluster tracks by spatial proximity into 'seats'.

        Simple greedy clustering: if a track's normalized center distance
        to an existing cluster is below threshold, merge them.
        """
        clusters: List[dict] = []
        frame_w = max(float(self._frame_width), 1.0)
        frame_h = max(float(self._frame_height), 1.0)

        for track_id in sorted(profiles, key=lambda tid: profiles[tid]["x"]):
            profile = profiles[track_id]
            best_cluster_idx: Optional[int] = None
            best_distance = float("inf")

            for idx, cluster in enumerate(clusters):
                dx = abs(profile["x"] - cluster["profile"]["x"]) / frame_w
                dy = abs(profile.get("y", 0) - cluster["profile"].get("y", 0)) / frame_h
                distance = dx + dy * 0.85
                if distance < best_distance:
                    best_distance = distance
                    best_cluster_idx = idx

            if best_cluster_idx is not None and best_distance <= threshold:
                cluster = clusters[best_cluster_idx]
                cluster["track_ids"].append(track_id)
                cluster["profiles"].append(profile)
                cluster["profile"] = self._merge_profiles(cluster["profiles"])
            else:
                clusters.append({
                    "track_ids": [track_id],
                    "profiles": [profile],
                    "profile": dict(profile),
                })

        # Sort clusters left-to-right
        clusters.sort(key=lambda c: c["profile"]["x"])
        return clusters

    @staticmethod
    def _merge_profiles(profiles: List[Dict[str, float]]) -> Dict[str, float]:
        """Merge multiple track profiles representing the same seat."""
        return {
            "x": float(np.median([p.get("x", 0.0) for p in profiles])),
            "y": float(np.median([p.get("y", 0.0) for p in profiles])),
            "width": float(np.median([p.get("width", 0.0) for p in profiles])),
            "height": float(np.median([p.get("height", 0.0) for p in profiles])),
            "area": float(np.median([p.get("area", 0.0) for p in profiles])),
        }

    def reset(self) -> None:
        """Reset tracker state for a new video."""
        self._track_histories.clear()
        self._frame_counter = 0
        if self._sv_tracker is not None:
            try:
                self._sv_tracker.reset()
            except Exception:
                pass
        # Ultralytics tracker resets via new model.track() call without persist
        # We keep the model loaded but clear internal history
