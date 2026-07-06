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

    # Yaw estimation landmarks
    NOSE_TIP = 1
    LEFT_EYE_INNER = 33
    RIGHT_EYE_INNER = 263
    CHIN = 152
    FOREHEAD = 10

    # Configuration
    SLIDING_WINDOW_SEC = 0.5
    HYSTERESIS_SEC = 0.3
    MIN_LIP_VARIANCE = 0.002
    MIN_LIP_AMPLITUDE = 0.03       # Minimum lip movement range to count as speech
    DOMINANCE_THRESHOLD = 0.75
    MAX_YAW_DEG = 40.0             # Beyond this yaw, confidence = 0

    # Multimodal scoring weights — LIP is primary signal, head is secondary
    LIP_WEIGHT = 0.70              # CHANGED from 0.40 — lip variance is most reliable speech indicator
    HEAD_WEIGHT = 0.30             # CHANGED from 0.60 — head motion is weak proxy, easily confused
    HEAD_MOTION_NORMALIZE = 20.0

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
        vad_segments: Optional[List[Dict]] = None,
    ) -> Optional[ActiveSpeakerResult]:
        """Run multimodal active speaker detection on video.

        Uses: lip aperture (40%) + head motion (60%), gated by audio VAD.
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

        # State for head motion tracking per face position (left/right)
        prev_nose: Dict[int, Tuple[float, float]] = {}  # face_id → (x, y) in pixels

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

                        # Head motion: euclidean distance from previous nose position
                        head_motion = 0.0
                        if face_idx in prev_nose:
                            dx = cx - prev_nose[face_idx][0]
                            dy = cy - prev_nose[face_idx][1]
                            head_motion = min((dx**2 + dy**2) ** 0.5 / self.HEAD_MOTION_NORMALIZE, 1.0)
                        prev_nose[face_idx] = (cx, cy)

                        yaw = self._estimate_yaw_legacy(face_landmarks)
                        faces_in_frame.append(FaceSpeechFrame(
                            face_id=face_idx,
                            lip_aperture=lip_aperture,
                            head_motion=head_motion,
                            bbox_x=cx,
                            bbox_y=cy,
                            yaw_deg=yaw,
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

                        head_motion = 0.0
                        if face_idx in prev_nose:
                            dx = cx - prev_nose[face_idx][0]
                            dy = cy - prev_nose[face_idx][1]
                            head_motion = min((dx**2 + dy**2) ** 0.5 / self.HEAD_MOTION_NORMALIZE, 1.0)
                        prev_nose[face_idx] = (cx, cy)

                        faces_in_frame.append(FaceSpeechFrame(
                            face_id=face_idx,
                            lip_aperture=lip_aperture,
                            head_motion=head_motion,
                            bbox_x=cx,
                            bbox_y=cy,
                            yaw_deg=self._estimate_yaw_task(landmarks),
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
        """Compute active speaker per frame using yaw-aware multimodal scoring.

        Score = (lip_variance * 0.70 + head_motion_mean * 0.30) * pose_confidence
        
        Key improvements over naive scoring:
        - Lip variance is primary signal (70% weight) — most direct speech indicator
        - Head motion is secondary (30%) — catches nodding but doesn't dominate
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

                # Lip component: variance of aperture
                lip_values = [d[0] for d in window_data]
                lip_amplitude = max(lip_values) - min(lip_values)
                
                # Amplitude gate: if lips barely moved, it's not speech (noise)
                if lip_amplitude < self.MIN_LIP_AMPLITUDE:
                    lip_variance = 0.0
                else:
                    lip_variance = float(np.var(lip_values))

                # Head component: mean of head motion
                head_values = [d[1] for d in window_data]
                head_mean = float(np.mean(head_values))

                # Yaw component: average pose confidence in window
                yaw_values = [d[2] for d in window_data]
                avg_yaw = float(np.mean([abs(y) for y in yaw_values]))
                pose_conf = self._pose_confidence(avg_yaw)

                # Multimodal score WITH pose discount
                raw_score = lip_variance * self.LIP_WEIGHT + head_mean * self.HEAD_WEIGHT
                score = raw_score * pose_conf

                if score > best_score:
                    best_score = score
                    best_face_id = face_id

            # Only assign if score exceeds minimum threshold
            if best_score >= self.MIN_LIP_VARIANCE and best_face_id >= 0:
                per_frame_speaker[frame_idx] = best_face_id

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
