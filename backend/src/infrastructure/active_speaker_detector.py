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
    head_motion: float   # normalized head movement (0 = still, 1 = moving fast)
    bbox_x: float        # face center X in pixels
    bbox_y: float        # face center Y in pixels
    yaw_deg: float = 0.0 # estimated yaw angle (0 = frontal, ±90 = profile)
    nose_x: float = 0.0  # nose X in pixels, used after stable ID assignment
    nose_y: float = 0.0  # nose Y in pixels, used after stable ID assignment


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
    - Multiple visible people with relatively stable positions
    - Clear lip visibility
    - Works with the same MediaPipe dependency already in the project
    """

    # Lip landmarks (MediaPipe Face Mesh indices)
    UPPER_LIP_CENTER = 13
    LOWER_LIP_CENTER = 14
    MOUTH_RIGHT = 78
    MOUTH_LEFT = 308

    # Yaw estimation landmarks
    NOSE_TIP = 1
    LEFT_EYE_INNER = 33
    RIGHT_EYE_INNER = 263
    CHIN = 152
    FOREHEAD = 10

    # Configuration
    SLIDING_WINDOW_SEC = 0.5
    HYSTERESIS_SEC = 0.3
    MIN_LIP_VARIANCE = 0.00008
    MIN_LIP_AMPLITUDE = 0.012      # Minimum lip movement range to count as speech
    DOMINANCE_THRESHOLD = 0.75
    MAX_YAW_DEG = 40.0             # Beyond this yaw, confidence = 0

    # Multimodal scoring weights — LIP is primary signal, head is secondary
    LIP_VARIANCE_WEIGHT = 0.50
    LIP_AMPLITUDE_WEIGHT = 0.42
    HEAD_WEIGHT = 0.08             # Head motion is weak proxy, easily confused by listeners
    HEAD_MOTION_NORMALIZE = 20.0

    FACE_MESH_CONFIDENCE = 0.5
    POSITION_PROFILE_MISMATCH = 0.18

    def __init__(self, max_faces: Optional[int] = None):
        self._face_mesh = None
        self._use_legacy_api = False  # True if mp.solutions available
        if max_faces is None:
            try:
                from src.config import settings
                max_faces = settings.CENTERING_MAX_FACES
            except Exception:
                max_faces = 12
        self._max_faces = max(1, int(max_faces))

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
                    max_num_faces=self._max_faces,
                    refine_landmarks=True,
                    min_detection_confidence=self.FACE_MESH_CONFIDENCE,
                    min_tracking_confidence=0.5,
                )
                self._use_legacy_api = True
                logger.info(
                    "active_speaker: MediaPipe Face Mesh loaded "
                    f"(legacy API, max_faces={self._max_faces})"
                )
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
                        num_faces=self._max_faces,
                        min_face_detection_confidence=self.FACE_MESH_CONFIDENCE,
                        min_tracking_confidence=0.5,
                        output_face_blendshapes=False,
                    )
                    self._face_mesh = FaceLandmarker.create_from_options(options)
                    self._use_legacy_api = False
                    logger.info(
                        "active_speaker: MediaPipe FaceLandmarker loaded "
                        f"(task API, max_faces={self._max_faces})"
                    )
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
        vad_segments: Optional[List[Dict]] = None,
        position_targets: Optional[Dict[int, float]] = None,
        position_target_profiles: Optional[Dict[int, Dict[str, float]]] = None,
    ) -> Optional[ActiveSpeakerResult]:
        """Run multimodal active speaker detection on video.

        Uses: lip aperture (70%) + head motion (30%), gated by audio VAD.
        When audio is silent (no VAD activity), no one is scored as speaking.

        Args:
            video_path: Path to video file
            fps: Video FPS
            total_frames: Total frame count
            width: Frame width
            height: Frame height
            sample_interval_sec: How often to sample (0.2s = 5 samples/sec)
            max_samples: Maximum frames to process
            vad_segments: List of {'start': float, 'end': float} from Silero VAD.
                          If None, assumes continuous speech (fallback).
            position_targets: Stable person positions from face tracking, keyed by
                              positional speaker ID (0=leftmost, 1=next, ...).
            position_target_profiles: Stable X/Y/size face profiles keyed by
                                     positional speaker ID. Used when panelists
                                     share similar horizontal positions.
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
        frame_data: List[Tuple[int, List[FaceSpeechFrame]]] = []

        for frame_idx in sample_indices:
            t = frame_idx / fps

            # VAD gate: if audio is silent at this time, skip (no one is speaking)
            if vad_segments and not self._is_audio_active(t, vad_segments):
                frame_data.append((frame_idx, []))
                continue

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

                        yaw = self._estimate_yaw_legacy(face_landmarks)
                        faces_in_frame.append(FaceSpeechFrame(
                            face_id=face_idx,
                            lip_aperture=lip_aperture,
                            head_motion=0.0,
                            bbox_x=cx,
                            bbox_y=cy,
                            yaw_deg=yaw,
                            nose_x=cx,
                            nose_y=cy,
                        ))
            else:
                # Task API: mp.tasks.vision.FaceLandmarker
                import mediapipe as mp
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=proc_frame)
                result = self._face_mesh.detect(mp_image)
                if result.face_landmarks:
                    for face_idx, landmarks in enumerate(result.face_landmarks):
                        lip_aperture = self._compute_lip_aperture_task(landmarks, proc_frame.shape)
                        nose = landmarks[1]
                        cx = nose.x * width
                        cy = nose.y * height

                        faces_in_frame.append(FaceSpeechFrame(
                            face_id=face_idx,
                            lip_aperture=lip_aperture,
                            head_motion=0.0,
                            bbox_x=cx,
                            bbox_y=cy,
                            yaw_deg=self._estimate_yaw_task(landmarks),
                            nose_x=cx,
                            nose_y=cy,
                        ))

            frame_data.append((frame_idx, faces_in_frame))

        cap.release()

        if not frame_data:
            return None

        # Assign stable positional IDs before measuring head motion. MediaPipe's
        # per-frame face order is not stable, so head motion must be keyed by
        # the final left/right/N-position identity rather than raw face_idx.
        frame_data = self._assign_consistent_ids(
            frame_data,
            width,
            position_targets=position_targets,
            position_target_profiles=position_target_profiles,
            frame_height=height,
        )
        frame_data = self._compute_head_motion(frame_data)

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
        frame_counts: Dict[int, int] = {}
        for speaker_id in per_frame_speaker.values():
            frame_counts[speaker_id] = frame_counts.get(speaker_id, 0) + 1
        frame_counts_log = ", ".join(
            f"P{speaker_id}:{count}"
            for speaker_id, count in sorted(frame_counts.items())
        )
        segment_log = ", ".join(
            f"P{s.speaker_id}@{s.start_time:.1f}-{s.end_time:.1f}s"
            for s in segments[:8]
        )
        if len(segments) > 8:
            segment_log += ", ..."

        logger.info(
            f"active_speaker: detected {total_speakers} speakers, "
            f"dominant=ID{dominant_id} ({dominant_ratio:.0%}), "
            f"{len(segments)} segments"
        )
        logger.info(
            "active_speaker: timeline "
            f"frames={{{frame_counts_log}}}, segments=[{segment_log}]"
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

    def _estimate_yaw_legacy(self, face_landmarks) -> float:
        """Estimate face yaw angle from landmark asymmetry (legacy API).
        
        Uses nose-to-eye distances: if nose is closer to one eye than the other,
        face is rotated. Returns degrees (-90 to +90, 0 = frontal).
        """
        landmarks = face_landmarks.landmark
        nose = landmarks[self.NOSE_TIP]
        left_eye = landmarks[self.LEFT_EYE_INNER]
        right_eye = landmarks[self.RIGHT_EYE_INNER]

        d_left = abs(nose.x - left_eye.x)
        d_right = abs(nose.x - right_eye.x)
        denom = d_left + d_right

        if denom < 1e-6:
            return 0.0

        # Asymmetry ratio: 0 = frontal, ±1 = full profile
        ratio = (d_left - d_right) / denom
        return ratio * 90.0

    def _estimate_yaw_task(self, landmarks: list) -> float:
        """Estimate face yaw angle from landmark asymmetry (task API)."""
        nose = landmarks[self.NOSE_TIP]
        left_eye = landmarks[self.LEFT_EYE_INNER]
        right_eye = landmarks[self.RIGHT_EYE_INNER]

        d_left = abs(nose.x - left_eye.x)
        d_right = abs(nose.x - right_eye.x)
        denom = d_left + d_right

        if denom < 1e-6:
            return 0.0

        ratio = (d_left - d_right) / denom
        return ratio * 90.0

    def _pose_confidence(self, yaw_deg: float) -> float:
        """Discount factor for face yaw — less reliable landmarks when turned.
        
        Frontal (yaw=0°) → confidence 1.0
        Profile (yaw≥40°) → confidence 0.0
        Linear decay between.
        """
        return max(0.0, 1.0 - abs(yaw_deg) / self.MAX_YAW_DEG)

    def _assign_consistent_ids(
        self,
        frame_data: List[Tuple[int, List[FaceSpeechFrame]]],
        frame_width: int,
        position_targets: Optional[Dict[int, float]] = None,
        position_target_profiles: Optional[Dict[int, Dict[str, float]]] = None,
        frame_height: Optional[int] = None,
    ) -> List[Tuple[int, List[FaceSpeechFrame]]]:
        """Assign consistent positional face IDs.

        If stable targets are available from the IoU tracker, each Face Mesh
        detection is matched to the nearest target. This keeps lip/head scoring
        aligned with the same identities used later by auto-centering.

        Fallback: assign visible faces left-to-right for the current frame.
        """
        targets = self._normalise_position_targets(position_targets)
        profiles = self._normalise_position_target_profiles(position_target_profiles)

        for frame_idx, faces in frame_data:
            if not faces:
                continue

            if profiles:
                pairs: List[Tuple[float, int, int]] = []
                for face_idx, face in enumerate(faces):
                    for position_id, profile in profiles.items():
                        pairs.append((
                            self._face_profile_distance(
                                face,
                                profile,
                                frame_width,
                                frame_height,
                            ),
                            position_id,
                            face_idx,
                        ))

                used_faces: set[int] = set()
                used_positions: set[int] = set()
                for distance, position_id, face_idx in sorted(pairs):
                    if face_idx in used_faces or position_id in used_positions:
                        continue
                    if distance > self.POSITION_PROFILE_MISMATCH:
                        continue
                    faces[face_idx].face_id = position_id
                    used_faces.add(face_idx)
                    used_positions.add(position_id)

                next_id = max(profiles) + 1
                for face_idx, face in sorted(
                    enumerate(faces),
                    key=lambda item: (item[1].bbox_x, item[1].bbox_y),
                ):
                    if face_idx not in used_faces:
                        face.face_id = next_id
                        next_id += 1
                continue

            if targets:
                pairs: List[Tuple[float, int, int]] = []
                for face_idx, face in enumerate(faces):
                    for position_id, target_x in targets.items():
                        pairs.append((abs(face.bbox_x - target_x), position_id, face_idx))

                used_faces: set[int] = set()
                used_positions: set[int] = set()
                for _, position_id, face_idx in sorted(pairs):
                    if face_idx in used_faces or position_id in used_positions:
                        continue
                    faces[face_idx].face_id = position_id
                    used_faces.add(face_idx)
                    used_positions.add(position_id)

                next_id = max(targets) + 1
                for face_idx, face in sorted(
                    enumerate(faces),
                    key=lambda item: item[1].bbox_x,
                ):
                    if face_idx not in used_faces:
                        face.face_id = next_id
                        next_id += 1
                continue

            for position_id, face in enumerate(sorted(faces, key=lambda f: f.bbox_x)):
                face.face_id = position_id

        return frame_data

    @staticmethod
    def _normalise_position_targets(
        position_targets: Optional[Dict[int, float]]
    ) -> Dict[int, float]:
        """Return clean positional targets keyed by speaker position ID."""
        if not position_targets:
            return {}

        cleaned: Dict[int, float] = {}
        for key, value in position_targets.items():
            try:
                cleaned[int(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return dict(sorted(cleaned.items()))

    @staticmethod
    def _normalise_position_target_profiles(
        position_target_profiles: Optional[Dict[int, Dict[str, float]]],
        position_targets: Optional[Dict[int, float]] = None,
    ) -> Dict[int, Dict[str, float]]:
        """Return clean X/Y/size target profiles keyed by speaker position ID."""
        cleaned: Dict[int, Dict[str, float]] = {}
        if position_target_profiles:
            for key, profile in position_target_profiles.items():
                if not isinstance(profile, dict):
                    continue
                try:
                    position_id = int(key)
                    numeric = {
                        field: float(profile[field])
                        for field in ("x", "y", "width", "height", "area")
                        if field in profile
                    }
                except (TypeError, ValueError):
                    continue
                if "x" in numeric:
                    cleaned[position_id] = numeric

        if cleaned:
            return dict(sorted(cleaned.items()))

        if position_targets:
            for position_id, target_x in position_targets.items():
                cleaned[int(position_id)] = {"x": float(target_x)}

        return dict(sorted(cleaned.items()))

    @classmethod
    def _face_profile_distance(
        cls,
        face: FaceSpeechFrame,
        profile: Dict[str, float],
        frame_width: int,
        frame_height: Optional[int] = None,
    ) -> float:
        """Weighted normalized distance between a Face Mesh detection and a seat profile."""
        frame_w = max(float(frame_width), 1.0)
        frame_h = max(float(frame_height or frame_width), 1.0)
        dx = abs(face.bbox_x - profile.get("x", face.bbox_x)) / frame_w
        dy = 0.0
        if "y" in profile:
            dy = abs(face.bbox_y - profile["y"]) / frame_h
        return dx + dy * 0.85

    def _compute_head_motion(
        self,
        frame_data: List[Tuple[int, List[FaceSpeechFrame]]],
    ) -> List[Tuple[int, List[FaceSpeechFrame]]]:
        """Compute head motion after stable face IDs have been assigned."""
        prev_nose: Dict[int, Tuple[float, float]] = {}

        for _, faces in frame_data:
            for face in faces:
                prev = prev_nose.get(face.face_id)
                if prev:
                    dx = face.nose_x - prev[0]
                    dy = face.nose_y - prev[1]
                    face.head_motion = min(
                        (dx * dx + dy * dy) ** 0.5 / self.HEAD_MOTION_NORMALIZE,
                        1.0,
                    )
                else:
                    face.head_motion = 0.0
                prev_nose[face.face_id] = (face.nose_x, face.nose_y)

        return frame_data

    def _compute_active_speakers(
        self,
        frame_data: List[Tuple[int, List[FaceSpeechFrame]]],
        fps: float,
        sample_interval_sec: float,
    ) -> Dict[int, int]:
        """Compute active speaker per frame using yaw-aware multimodal scoring.

        Score = dominant lip movement + gated head motion, discounted by pose confidence.

        Key improvements over naive scoring:
        - Lip variance and lip amplitude are primary signals — most direct speech indicator
        - Head motion is only counted when mouth movement is also present
        - Pose confidence discounts faces that are turned (landmark noise)
        - Amplitude gate: lip movement must exceed MIN_LIP_AMPLITUDE to be counted
        
        This prevents the "listener who turns head" from being scored as speaker.

        Returns: Dict[frame_idx, active_speaker_face_id]
        """
        window_size = max(3, int(self.SLIDING_WINDOW_SEC / sample_interval_sec))

        # Build time series per face ID (now includes yaw)
        face_data_series: Dict[int, List[Tuple[int, float, float, float]]] = {}
        # face_id → [(frame_idx, lip_aperture, head_motion, yaw_deg)]

        for frame_idx, faces in frame_data:
            for face in faces:
                if face.face_id not in face_data_series:
                    face_data_series[face.face_id] = []
                face_data_series[face.face_id].append(
                    (frame_idx, face.lip_aperture, face.head_motion, face.yaw_deg)
                )

        if not face_data_series:
            return {}

        # For each sample point, compute yaw-aware multimodal score
        per_frame_speaker: Dict[int, int] = {}
        low_confidence_candidates: List[Tuple[int, int, float]] = []
        all_frame_indices = [fi for fi, _ in frame_data]

        for i, (frame_idx, faces) in enumerate(frame_data):
            win_start = max(0, i - window_size // 2)
            win_end = min(len(frame_data), i + window_size // 2 + 1)

            best_face_id = -1
            best_score = -1.0

            for face_id, series in face_data_series.items():
                window_frame_start = all_frame_indices[win_start]
                window_frame_end = all_frame_indices[min(win_end - 1, len(all_frame_indices) - 1)]

                window_data = [
                    (lip, head, yaw) for fi, lip, head, yaw in series
                    if window_frame_start <= fi <= window_frame_end
                ]

                if len(window_data) < 2:
                    continue

                # Lip component: variance + amplitude of aperture. Some podcast
                # speakers keep a steady open mouth while talking, so amplitude
                # catches speech that pure variance can miss.
                lip_values = [d[0] for d in window_data]
                lip_amplitude = max(lip_values) - min(lip_values)
                lip_variance = float(np.var(lip_values))
                lip_activity = min(1.0, lip_amplitude / max(self.MIN_LIP_AMPLITUDE, 1e-6))
                if lip_amplitude < self.MIN_LIP_AMPLITUDE * 0.5:
                    lip_variance = 0.0
                    lip_activity = 0.0

                # Head component: mean of head motion. Head movement is useful
                # only as support for real mouth motion; otherwise a listening
                # nod can beat the actual speaker.
                head_values = [d[1] for d in window_data]
                head_mean = float(np.mean(head_values))
                head_gate = lip_activity
                head_component = head_mean * head_gate

                # Yaw component: average pose confidence in window
                yaw_values = [d[2] for d in window_data]
                avg_yaw = float(np.mean([abs(y) for y in yaw_values]))
                pose_conf = self._pose_confidence(avg_yaw)

                # Multimodal score WITH pose discount. Lip signals dominate;
                # head motion only breaks ties when mouth activity is present.
                raw_score = (
                    lip_variance * self.LIP_VARIANCE_WEIGHT
                    + (lip_activity * self.MIN_LIP_VARIANCE) * self.LIP_AMPLITUDE_WEIGHT
                    + head_component * self.MIN_LIP_VARIANCE * self.HEAD_WEIGHT
                )
                score = raw_score * pose_conf

                if score > best_score:
                    best_score = score
                    best_face_id = face_id

            # Only assign if score exceeds minimum threshold
            if best_score > 0 and best_face_id >= 0:
                low_confidence_candidates.append((frame_idx, best_face_id, best_score))
            if best_score >= self.MIN_LIP_VARIANCE and best_face_id >= 0:
                per_frame_speaker[frame_idx] = best_face_id

        if not per_frame_speaker and low_confidence_candidates:
            fallback_floor = self.MIN_LIP_VARIANCE * 0.10
            fallback_candidates = [
                (frame_idx, face_id, score)
                for frame_idx, face_id, score in low_confidence_candidates
                if score >= fallback_floor
            ]
            if fallback_candidates:
                for frame_idx, face_id, _ in fallback_candidates:
                    per_frame_speaker[frame_idx] = face_id
                best_frame, best_face_id, best_score = max(
                    fallback_candidates,
                    key=lambda item: item[2],
                )
                logger.info(
                    "active_speaker: using low-confidence visual fallback "
                    f"(frames={len(fallback_candidates)}, best=P{best_face_id} "
                    f"@frame={best_frame}, score={best_score:.6f}, "
                    f"threshold={self.MIN_LIP_VARIANCE:.6f})"
                )

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

    def _is_audio_active(self, t: float, vad_segments: List[Dict]) -> bool:
        """Check if timestamp t falls within any VAD speech segment.

        Args:
            t: Time in seconds
            vad_segments: List of {'start': float, 'end': float}

        Returns:
            True if speech is happening at time t
        """
        if not vad_segments:
            return True  # No VAD data = assume continuous speech (fallback)
        for seg in vad_segments:
            if seg.get('start', 0) <= t <= seg.get('end', 0):
                return True
        return False
