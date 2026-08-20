"""B-roll Subject & Composition Analyzer for AI-Aware Crop & Layout Selection.

Analyzes 16:9 / landscape B-roll footage:
1. Extracts representative keyframes (start, mid, end).
2. Performs YOLO object detection + Saliency energy mapping to find the focal subject.
3. Computes optical motion trajectories across keyframes.
4. Calculates the optimal horizontal crop window (smart_crop_x) for 9:16 vertical extraction.
5. Resolves the optimal layout mode:
   - BEHIND_PERSON: when the B-roll subject can sit cleanly in the upper negative space (above shoulders).
   - SIDE_BROLL: when B-roll has wide 16:9 context, charts, diagrams, or wide multi-subject scene.
   - FULL_BROLL: when a full cutaway scene change is best suited.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import cv2
import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)


class BrollPlacementMode(str, Enum):
    BEHIND_PERSON = "behind_person"
    SIDE_BROLL = "side_broll"
    FULL_BROLL = "full_broll"


@dataclass
class BrollSubject:
    """Detected focal subject in B-roll footage."""
    box: Tuple[float, float, float, float]  # Normalized [x1, y1, x2, y2]
    center_x: float
    center_y: float
    width: float
    height: float
    label: str = "subject"
    confidence: float = 1.0
    motion_dx: float = 0.0
    motion_dy: float = 0.0
    saliency_score: float = 1.0


@dataclass
class BrollAnalysisResult:
    """Comprehensive composition analysis of B-roll footage."""
    recommended_mode: BrollPlacementMode
    smart_crop_x: int
    smart_crop_y: int
    scaled_w: int
    scaled_h: int
    target_w: int
    target_h: int
    primary_subject: Optional[BrollSubject] = None
    all_subjects: List[BrollSubject] = field(default_factory=list)
    is_wide_scene: bool = False
    motion_intensity: float = 0.0
    negative_space_top: float = 0.0  # Vertical headroom available above speaker


class BrollSubjectAnalyzer:
    """AI-powered B-roll Subject Detection and Composition Analyzer."""

    def __init__(self, yolo_model_path: Optional[str] = None):
        self._model_path = yolo_model_path or getattr(settings, "YOLO_MODEL_PATH", "models/yolo26n.pt")
        self._model = None
        self._load_attempted = False

    def _get_model(self):
        """Lazy load YOLO model."""
        if not self._load_attempted:
            self._load_attempted = True
            try:
                from ultralytics import YOLO
                if os.path.exists(self._model_path):
                    self._model = YOLO(self._model_path)
                else:
                    # Fallback to standard lightweight model
                    self._model = YOLO("yolov8n.pt")
                logger.info("broll_subject_analyzer: YOLO model loaded successfully")
            except Exception as e:
                logger.warning(f"broll_subject_analyzer: YOLO unavailable ({e}), using OpenCV saliency fallback")
                self._model = None
        return self._model

    def analyze_video(
        self,
        video_path: str,
        speaker_box: Optional[Tuple[float, float, float, float]] = None,
        target_w: int = 1080,
        target_h: int = 1920,
        force_mode: Optional[str] = None,
    ) -> BrollAnalysisResult:
        """Extract keyframes and analyze 16:9 B-roll video."""
        if not video_path or not os.path.exists(video_path):
            return self._fallback_result(target_w, target_h, force_mode)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return self._fallback_result(target_w, target_h, force_mode)

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return self._fallback_result(target_w, target_h, force_mode)

        # Sample 3 keyframes: 15%, 50%, 85%
        sample_indices = [
            max(0, int(total_frames * 0.15)),
            max(0, int(total_frames * 0.50)),
            min(total_frames - 1, int(total_frames * 0.85)),
        ]

        frames: List[np.ndarray] = []
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                frames.append(frame)
        cap.release()

        if not frames:
            return self._fallback_result(target_w, target_h, force_mode)

        return self.analyze_frames(
            frames=frames,
            speaker_box=speaker_box,
            target_w=target_w,
            target_h=target_h,
            force_mode=force_mode,
        )

    def analyze_frames(
        self,
        frames: List[np.ndarray],
        speaker_box: Optional[Tuple[float, float, float, float]] = None,
        target_w: int = 1080,
        target_h: int = 1920,
        force_mode: Optional[str] = None,
    ) -> BrollAnalysisResult:
        """Analyze a sequence of frames for subjects, motion, and composition."""
        if not frames:
            return self._fallback_result(target_w, target_h, force_mode)

        mid_frame = frames[len(frames) // 2]
        ih, iw = mid_frame.shape[:2]

        # 1. Detect subjects in the middle frame
        subjects = self._detect_subjects(mid_frame)

        # 2. Track motion across sampled frames if multiple frames provided
        motion_intensity = 0.0
        if len(frames) >= 2 and subjects:
            primary = subjects[0]
            start_subjects = self._detect_subjects(frames[0])
            end_subjects = self._detect_subjects(frames[-1])
            if start_subjects and end_subjects:
                dx = end_subjects[0].center_x - start_subjects[0].center_x
                dy = end_subjects[0].center_y - start_subjects[0].center_y
                primary.motion_dx = dx
                primary.motion_dy = dy
                motion_intensity = float(np.sqrt(dx * dx + dy * dy))

        primary_subject = subjects[0] if subjects else None

        # 3. Calculate Smart Crop Coordinates for 9:16
        # When 16:9 is scaled to match target height target_h (1920), width becomes scaled_w (e.g. 3413)
        scale = max(target_w / iw, target_h / ih)
        scaled_w = max(target_w, int(round(iw * scale)))
        scaled_h = max(target_h, int(round(ih * scale)))

        max_crop_x = max(0, scaled_w - target_w)
        max_crop_y = max(0, scaled_h - target_h)

        if primary_subject:
            # Center the crop window around subject's center_x
            target_cx = primary_subject.center_x * scaled_w
            smart_crop_x = int(np.clip(target_cx - target_w * 0.5, 0, max_crop_x))
            target_cy = primary_subject.center_y * scaled_h
            smart_crop_y = int(np.clip(target_cy - target_h * 0.4, 0, max_crop_y))
        else:
            smart_crop_x = max_crop_x // 2
            smart_crop_y = int(round(max_crop_y * 0.15))

        # Ensure even coordinates for FFmpeg compatibility
        smart_crop_x = (smart_crop_x // 2) * 2
        smart_crop_y = (smart_crop_y // 2) * 2

        # 4. Determine Scene Geometry & Layout Mode
        is_wide = (iw / ih) >= 1.6
        is_wide_scene = bool(
            is_wide
            and (
                primary_subject is None
                or primary_subject.width > 0.65
                or len(subjects) >= 3
            )
        )

        if force_mode:
            try:
                recommended_mode = BrollPlacementMode(force_mode.lower())
            except ValueError:
                recommended_mode = BrollPlacementMode.BEHIND_PERSON
        else:
            recommended_mode = self._determine_layout_mode(
                primary_subject=primary_subject,
                speaker_box=speaker_box,
                is_wide_scene=is_wide_scene,
                motion_intensity=motion_intensity,
            )

        # Negative space headroom above speaker
        headroom = speaker_box[1] if speaker_box else 0.35

        return BrollAnalysisResult(
            recommended_mode=recommended_mode,
            smart_crop_x=smart_crop_x,
            smart_crop_y=smart_crop_y,
            scaled_w=scaled_w,
            scaled_h=scaled_h,
            target_w=target_w,
            target_h=target_h,
            primary_subject=primary_subject,
            all_subjects=subjects,
            is_wide_scene=is_wide_scene,
            motion_intensity=motion_intensity,
            negative_space_top=float(headroom),
        )

    def _detect_subjects(self, frame: np.ndarray) -> List[BrollSubject]:
        """Detect salient subjects using YOLO or Saliency."""
        h, w = frame.shape[:2]
        model = self._get_model()

        if model is not None:
            try:
                results = model.predict(frame, conf=0.25, verbose=False)
                subjects: List[BrollSubject] = []
                for r in results:
                    boxes = getattr(r, "boxes", None)
                    if boxes is None or len(boxes) == 0:
                        continue
                    for box in boxes:
                        xyxy = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0].cpu().numpy())
                        cls_id = int(box.cls[0].cpu().numpy())
                        label = model.names.get(cls_id, "object") if hasattr(model, "names") else "object"

                        x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                        norm_box = (
                            float(np.clip(x1 / w, 0.0, 1.0)),
                            float(np.clip(y1 / h, 0.0, 1.0)),
                            float(np.clip(x2 / w, 0.0, 1.0)),
                            float(np.clip(y2 / h, 0.0, 1.0)),
                        )
                        bw = norm_box[2] - norm_box[0]
                        bh = norm_box[3] - norm_box[1]
                        cx = norm_box[0] + bw / 2.0
                        cy = norm_box[1] + bh / 2.0

                        subjects.append(BrollSubject(
                            box=norm_box,
                            center_x=cx,
                            center_y=cy,
                            width=bw,
                            height=bh,
                            label=label,
                            confidence=conf,
                        ))

                if subjects:
                    # Sort by confidence * area (most prominent subject first)
                    subjects.sort(key=lambda s: s.confidence * (s.width * s.height), reverse=True)
                    return subjects
            except Exception as e:
                logger.debug(f"broll_subject_analyzer: YOLO detection error: {e}")

        # Fallback: OpenCV Gradient & Saliency Energy
        return self._detect_saliency(frame)

    def _detect_saliency(self, frame: np.ndarray) -> List[BrollSubject]:
        """Compute salient visual center using multi-scale Sobel edge & luminance energy."""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sh, sw = max(1, h // 8), max(1, w // 8)
        small = cv2.resize(gray, (sw, sh))
        small = cv2.GaussianBlur(small, (0, 0), 1.2)

        gx = cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3)
        edge = cv2.magnitude(gx, gy)

        thr = float(np.percentile(edge, 60))
        weight = np.clip(edge - thr, 0, None) + 0.20

        # Boost upper-middle region for aesthetic composition
        row_boost = np.linspace(1.8, 0.6, sh, dtype=np.float32)[:, None]
        weight = weight * row_boost

        yy, xx = np.mgrid[0:sh, 0:sw]
        wsum = float(weight.sum()) or 1.0

        cx = float((xx * weight).sum() / wsum) / sw
        cy = float((yy * weight).sum() / wsum) / sh

        cx = float(np.clip(cx, 0.1, 0.9))
        cy = float(np.clip(cy, 0.1, 0.9))

        return [
            BrollSubject(
                box=(max(0.0, cx - 0.2), max(0.0, cy - 0.2), min(1.0, cx + 0.2), min(1.0, cy + 0.2)),
                center_x=cx,
                center_y=cy,
                width=0.4,
                height=0.4,
                label="saliency_focus",
                confidence=0.85,
            )
        ]

    def _determine_layout_mode(
        self,
        primary_subject: Optional[BrollSubject],
        speaker_box: Optional[Tuple[float, float, float, float]],
        is_wide_scene: bool,
        motion_intensity: float,
    ) -> BrollPlacementMode:
        """Intelligently choose between BEHIND_PERSON, SIDE_BROLL, and FULL_BROLL."""
        # 1. If the scene is wide landscape or diagram/chart with wide multi-focus → SIDE_BROLL (PiP / Split)
        if is_wide_scene:
            return BrollPlacementMode.SIDE_BROLL

        # 2. If no speaker is present in foreground → FULL_BROLL
        if speaker_box is None:
            return BrollPlacementMode.BEHIND_PERSON

        speaker_top_y = speaker_box[1]  # Head top level

        if primary_subject is not None:
            # If subject fits nicely above speaker's shoulders (or in upper 45% of frame)
            if primary_subject.center_y <= 0.45 or primary_subject.height <= 0.40:
                return BrollPlacementMode.BEHIND_PERSON

            # If subject is wide and sits right at the center where speaker stands
            if primary_subject.width > 0.55 and 0.35 <= primary_subject.center_y <= 0.75:
                return BrollPlacementMode.SIDE_BROLL

        # Default for high production value is BEHIND_PERSON
        return BrollPlacementMode.BEHIND_PERSON

    def _fallback_result(
        self,
        target_w: int,
        target_h: int,
        force_mode: Optional[str] = None,
    ) -> BrollAnalysisResult:
        """Fallback result when video cannot be analyzed."""
        mode = BrollPlacementMode.BEHIND_PERSON
        if force_mode:
            try:
                mode = BrollPlacementMode(force_mode.lower())
            except ValueError:
                mode = BrollPlacementMode.BEHIND_PERSON

        return BrollAnalysisResult(
            recommended_mode=mode,
            smart_crop_x=0,
            smart_crop_y=0,
            scaled_w=target_w,
            scaled_h=target_h,
            target_w=target_w,
            target_h=target_h,
            is_wide_scene=False,
            motion_intensity=0.0,
            negative_space_top=0.35,
        )
