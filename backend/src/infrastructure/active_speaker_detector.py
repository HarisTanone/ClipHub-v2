"""Active Speaker Detector — Lip movement analysis via MediaPipe Face Mesh.

Determines which person is speaking by tracking lip aperture variance.
Higher variance = mouth moving = speaking.

Algorithm:
  1. Face Mesh → 468 landmarks per face
  2. Lip aperture = distance between upper lip (landmark 13) and lower lip (landmark 14)
  3. Track aperture over sliding window (0.5s)
  4. Face with HIGHEST variance in window = active speaker
  5. Hysteresis: hold speaker assignment for 0.3s after switch (anti-flicker)

Landmarks used (MediaPipe Face Mesh):
  - 13: upper lip center (inner)
  - 14: lower lip center (inner)
  - 78: right mouth corner
  - 308: left mouth corner
  - Lip aperture ratio = vertical_open / mouth_width (normalized, face-size-independent)
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FaceSpeechFrame:
    """Speech data for a single face in a single frame."""
    face_id: int
    lip_aperture: float  # normalized lip opening (0 = closed, 1 = wide open)
    bbox_x: float        # face center X in pixels
    bbox_y: float        # face center Y in pixels


@dataclass
class SpeakerSegment:
    """Continuous segment where one speaker is active."""
    speaker_id: int       # face/track ID of the active speaker
    start_time: float     # seconds
    end_time: float       # seconds
    confidence: float     # how certain we are (0-1)


@dataclass
class ActiveSpeakerResult:
    """Full result from active speaker detection."""
    segments: List[SpeakerSegment]
    dominant_speaker_id: Optional[int]       # who spoke the most
    dominant_ratio: float                     # % of time dominant speaker was active
    per_frame_speaker: Dict[int, int]        # frame_idx → active speaker face_id
    total_speakers: int


class ActiveSpeakerDetector:
    """Detect active speaker via lip movement using MediaPipe Face Mesh.

    Designed for podcast format:
    - 2 people, frontal faces, relatively stable positions
    - Clear lip visibility
    - Works with the same MediaPipe dependency already in the project
    """

    # Lip landmarks (MediaPipe Face Mesh indices)
    UPPER_LIP_CENTER = 13
    LOWER_LIP_CENTER = 14
    MOUTH_RIGHT = 78
    MOUTH_LEFT = 308

    # Configuration
    SLIDING_WINDOW_SEC = 0.5       # Window for variance calculation
    HYSTERESIS_SEC = 0.3           # Hold speaker for this long before switching
    MIN_LIP_VARIANCE = 0.002      # Below this → not speaking (both silent)
    DOMINANCE_THRESHOLD = 0.75    # If one speaker talks ≥75% → single crop candidate

    FACE_MESH_CONFIDENCE = 0.5
    MAX_FACES = 2                  # Optimize for podcast (2 people max)

    def __init__(self):
        self._face_mesh = None
        self._use_legacy_api = False  # True if mp.solutions available

    def _load_model(self) -> bool:
        """Lazy-load MediaPipe Face Mesh (compatible with both legacy and task API)."""
        if self._face_mesh is not None:
            return True
        try:
            import mediapipe as mp
            # Try legacy API first (mediapipe ≤0.10.21, has mp.solutions)
            if hasattr(mp, 'solutions') and hasattr(mp.solutions, 'face_mesh'):
                self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=self.MAX_FACES,
                    refine_landmarks=True,
                    min_detection_confidence=self.FACE_MESH_CONFIDENCE,
                    min_tracking_confidence=0.5,
                )
                self._use_legacy_api = True
                logger.info("active_speaker: MediaPipe Face Mesh loaded (legacy API)")
                return True
            else:
                # New Task API (mediapipe ≥0.10.30)
                try:
                    from mediapipe.tasks.vision import FaceLandmarker, FaceLandmarkerOptions
                    from mediapipe.tasks.vision.core.vision_task_running_mode import VisionTaskRunningMode
                    from mediapipe.tasks import BaseOptions

                    base_options = BaseOptions(model_asset_path=self._find_face_mesh_model())
                    options = FaceLandmarkerOptions(
                        base_options=base_options,
                        running_mode=VisionTaskRunningMode.IMAGE,
                        num_faces=self.MAX_FACES,
                        min_face_detection_confidence=self.FACE_MESH_CONFIDENCE,
                        min_tracking_confidence=0.5,
                        output_face_blendshapes=False,
                    )
                    self._face_mesh = FaceLandmarker.create_from_options(options)
                    self._use_legacy_api = False
                    logger.info("active_speaker: MediaPipe FaceLandmarker loaded (task API)")
                    return True
                except (ImportError, ModuleNotFoundError) as e:
                    logger.warning(f"active_speaker: Task API not available: {e}")
                    return False
        except Exception as e:
            logger.warning(f"active_speaker: failed to load Face Mesh: {e}")
            return False

    def _find_face_mesh_model(self) -> str:
        """Find or download the face_landmarker model for task API."""
        import os
        model_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, 'face_landmarker.task')

        if not os.path.exists(model_path):
            import urllib.request
            url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
            logger.info("active_speaker: downloading face_landmarker model...")
            urllib.request.urlretrieve(url, model_path)
            logger.info(f"active_speaker: model saved to {model_path}")

        return model_path

    def detect(
        self,
        video_path: str,
        fps: float,
        total_frames: int,
        width: int,
        height: int,
        sample_interval_sec: float = 0.2,
        max_samples: int = 150,
    ) -> Optional[ActiveSpeakerResult]:
        """Run active speaker detection on video.

        Args:
            video_path: Path to video file
            fps: Video FPS
            total_frames: Total frame count
            width: Frame width
            height: Frame height
            sample_interval_sec: How often to sample (0.2s = 5 samples/sec for good lip tracking)
            max_samples: Maximum frames to process

        Returns:
            ActiveSpeakerResult or None if detection fails
        """
        if not self._load_model():
            return None

        import cv2
        cv2.setNumThreads(0)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        sample_interval = max(1, int(fps * sample_interval_sec))
        sample_indices = list(range(0, total_frames, sample_interval))[:max_samples]

        # Collect per-frame lip data
        # Key: frame_idx → List[FaceSpeechFrame]
        frame_data: List[Tuple[int, List[FaceSpeechFrame]]] = []

        for frame_idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Downscale for speed (Face Mesh is heavier than Face Detection)
            proc_frame = frame_rgb
            scale = 1.0
            if frame_rgb.shape[1] > 960:
                scale = 960 / frame_rgb.shape[1]
                proc_frame = cv2.resize(
                    frame_rgb,
                    (int(frame_rgb.shape[1] * scale), int(frame_rgb.shape[0] * scale)),
                )

            faces_in_frame: List[FaceSpeechFrame] = []

            if self._use_legacy_api:
                # Legacy: mp.solutions.face_mesh
                results = self._face_mesh.process(proc_frame)
                if results.multi_face_landmarks:
                    for face_idx, face_landmarks in enumerate(results.multi_face_landmarks):
                        lip_aperture = self._compute_lip_aperture_legacy(face_landmarks, proc_frame.shape)
                        nose = face_landmarks.landmark[1]
                        cx = nose.x * width
                        cy = nose.y * height
                        faces_in_frame.append(FaceSpeechFrame(
                            face_id=face_idx,
                            lip_aperture=lip_aperture,
                            bbox_x=cx,
                            bbox_y=cy,
                        ))
            else:
                # Task API: mp.tasks.vision.FaceLandmarker
                import mediapipe as mp
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=proc_frame)
                result = self._face_mesh.detect(mp_image)
                if result.face_landmarks:
                    for face_idx, landmarks in enumerate(result.face_landmarks):
                        lip_aperture = self._compute_lip_aperture_task(landmarks, proc_frame.shape)
                        nose = landmarks[1]  # NormalizedLandmark
                        cx = nose.x * width
                        cy = nose.y * height
                        faces_in_frame.append(FaceSpeechFrame(
                            face_id=face_idx,
                            lip_aperture=lip_aperture,
                            bbox_x=cx,
                            bbox_y=cy,
                        ))

            frame_data.append((frame_idx, faces_in_frame))

        cap.release()

        if not frame_data:
            return None

        # Assign consistent face IDs based on X position (left=0, right=1)
        frame_data = self._assign_consistent_ids(frame_data, width)

        # Compute active speaker per frame using sliding window variance
        per_frame_speaker = self._compute_active_speakers(
            frame_data, fps, sample_interval_sec
        )

        if not per_frame_speaker:
            return None

        # Build speaker segments with hysteresis
        segments = self._build_segments(per_frame_speaker, fps, sample_interval)

        # Compute dominance
        speaker_times: Dict[int, float] = {}
        for seg in segments:
            dur = seg.end_time - seg.start_time
            speaker_times[seg.speaker_id] = speaker_times.get(seg.speaker_id, 0) + dur

        total_time = sum(speaker_times.values()) if speaker_times else 1.0
        dominant_id = max(speaker_times, key=speaker_times.get) if speaker_times else None
        dominant_ratio = speaker_times.get(dominant_id, 0) / total_time if dominant_id is not None else 0

        total_speakers = len(set(s.speaker_id for s in segments))

        logger.info(
            f"active_speaker: detected {total_speakers} speakers, "
            f"dominant=ID{dominant_id} ({dominant_ratio:.0%}), "
            f"{len(segments)} segments"
        )

        return ActiveSpeakerResult(
            segments=segments,
            dominant_speaker_id=dominant_id,
            dominant_ratio=dominant_ratio,
            per_frame_speaker=per_frame_speaker,
            total_speakers=total_speakers,
        )

    def _compute_lip_aperture_legacy(self, face_landmarks, frame_shape: tuple) -> float:
        """Compute normalized lip aperture (legacy mp.solutions API).

        Returns: ratio of vertical lip opening to mouth width (0 = closed, ~0.5 = wide open).
        """
        landmarks = face_landmarks.landmark
        h, w = frame_shape[:2]

        # Vertical opening: upper lip center to lower lip center
        upper = landmarks[self.UPPER_LIP_CENTER]
        lower = landmarks[self.LOWER_LIP_CENTER]
        vertical_dist = abs(lower.y - upper.y) * h

        # Horizontal width: mouth corner to corner (for normalization)
        left_corner = landmarks[self.MOUTH_LEFT]
        right_corner = landmarks[self.MOUTH_RIGHT]
        mouth_width = abs(right_corner.x - left_corner.x) * w

        if mouth_width < 1.0:
            return 0.0

        # Normalized aperture (face-size-independent)
        return vertical_dist / mouth_width

    def _compute_lip_aperture_task(self, landmarks: list, frame_shape: tuple) -> float:
        """Compute normalized lip aperture (task API — landmarks is list of NormalizedLandmark).

        Returns: ratio of vertical lip opening to mouth width.
        """
        h, w = frame_shape[:2]

        upper = landmarks[self.UPPER_LIP_CENTER]
        lower = landmarks[self.LOWER_LIP_CENTER]
        vertical_dist = abs(lower.y - upper.y) * h

        left_corner = landmarks[self.MOUTH_LEFT]
        right_corner = landmarks[self.MOUTH_RIGHT]
        mouth_width = abs(right_corner.x - left_corner.x) * w

        if mouth_width < 1.0:
            return 0.0

        return vertical_dist / mouth_width

    def _assign_consistent_ids(
        self,
        frame_data: List[Tuple[int, List[FaceSpeechFrame]]],
        frame_width: int,
    ) -> List[Tuple[int, List[FaceSpeechFrame]]]:
        """Assign consistent face IDs: leftmost face = ID 0, rightmost = ID 1.

        Simple heuristic for podcast (2 people, relatively stable positions).
        Works because podcast participants don't swap seats.
        """
        midpoint = frame_width / 2.0

        for frame_idx, faces in frame_data:
            if len(faces) == 2:
                # Sort by X position: left = 0, right = 1
                sorted_faces = sorted(faces, key=lambda f: f.bbox_x)
                sorted_faces[0].face_id = 0
                sorted_faces[1].face_id = 1
            elif len(faces) == 1:
                # Single face — assign based on which side of midpoint
                faces[0].face_id = 0 if faces[0].bbox_x < midpoint else 1

        return frame_data

    def _compute_active_speakers(
        self,
        frame_data: List[Tuple[int, List[FaceSpeechFrame]]],
        fps: float,
        sample_interval_sec: float,
    ) -> Dict[int, int]:
        """Compute active speaker per frame using sliding window variance.

        Returns: Dict[frame_idx, active_speaker_face_id]
        """
        window_size = max(3, int(self.SLIDING_WINDOW_SEC / sample_interval_sec))

        # Build time series of lip apertures per face ID
        face_apertures: Dict[int, List[Tuple[int, float]]] = {}  # face_id → [(frame_idx, aperture)]

        for frame_idx, faces in frame_data:
            for face in faces:
                if face.face_id not in face_apertures:
                    face_apertures[face.face_id] = []
                face_apertures[face.face_id].append((frame_idx, face.lip_aperture))

        if not face_apertures:
            return {}

        # For each sample point, compute variance in sliding window per face
        per_frame_speaker: Dict[int, int] = {}
        all_frame_indices = [fi for fi, _ in frame_data]

        for i, (frame_idx, faces) in enumerate(frame_data):
            # Window: [i - window_size//2, i + window_size//2]
            win_start = max(0, i - window_size // 2)
            win_end = min(len(frame_data), i + window_size // 2 + 1)

            best_face_id = -1
            best_variance = -1.0

            for face_id, aperture_series in face_apertures.items():
                # Get apertures within window time range
                window_frame_start = all_frame_indices[win_start]
                window_frame_end = all_frame_indices[min(win_end - 1, len(all_frame_indices) - 1)]

                window_apertures = [
                    ap for fi, ap in aperture_series
                    if window_frame_start <= fi <= window_frame_end
                ]

                if len(window_apertures) < 2:
                    continue

                variance = float(np.var(window_apertures))

                if variance > best_variance:
                    best_variance = variance
                    best_face_id = face_id

            # Only assign if variance exceeds minimum (someone is actually talking)
            if best_variance >= self.MIN_LIP_VARIANCE and best_face_id >= 0:
                per_frame_speaker[frame_idx] = best_face_id
            # else: no one is speaking in this window (both silent)

        return per_frame_speaker

    def _build_segments(
        self,
        per_frame_speaker: Dict[int, int],
        fps: float,
        sample_interval: int,
    ) -> List[SpeakerSegment]:
        """Build continuous speaker segments with hysteresis.

        Hysteresis: don't switch speaker until new speaker holds for HYSTERESIS_SEC.
        """
        if not per_frame_speaker:
            return []

        sorted_frames = sorted(per_frame_speaker.keys())
        hysteresis_frames = int(self.HYSTERESIS_SEC * fps / sample_interval)

        segments: List[SpeakerSegment] = []
        current_speaker = per_frame_speaker[sorted_frames[0]]
        segment_start_frame = sorted_frames[0]
        pending_switch: Optional[Tuple[int, int]] = None  # (new_speaker, frames_held)

        for frame_idx in sorted_frames[1:]:
            speaker = per_frame_speaker[frame_idx]

            if speaker == current_speaker:
                # Same speaker — reset any pending switch
                pending_switch = None
            else:
                # Different speaker detected
                if pending_switch is None or pending_switch[0] != speaker:
                    # Start new pending switch
                    pending_switch = (speaker, 1)
                else:
                    # Continue pending switch
                    pending_switch = (pending_switch[0], pending_switch[1] + 1)

                # Check if hysteresis threshold met
                if pending_switch[1] >= hysteresis_frames:
                    # Commit the switch
                    segments.append(SpeakerSegment(
                        speaker_id=current_speaker,
                        start_time=segment_start_frame / fps,
                        end_time=frame_idx / fps,
                        confidence=0.8,
                    ))
                    current_speaker = pending_switch[0]
                    segment_start_frame = frame_idx
                    pending_switch = None

        # Close last segment
        last_frame = sorted_frames[-1]
        segments.append(SpeakerSegment(
            speaker_id=current_speaker,
            start_time=segment_start_frame / fps,
            end_time=(last_frame + sample_interval) / fps,
            confidence=0.8,
        ))

        return segments
