"""FaceOnCropDetector — Face detection restricted to person crop region.

Instead of running face detection on the full frame (expensive, noisy),
this detector runs ONLY on the upper portion of each tracked person's
bounding box — the head region.

Benefits:
  - Smaller search area → faster inference, fewer false positives
  - Enables heavier/more accurate face detectors (RetinaFace, SCRFD)
    without full-frame computational cost
  - Face coordinates are mapped back to full-frame space for downstream use

Supported backends:
  - RetinaFace (retinaface-pytorch): high accuracy, handles occlusion well
  - SCRFD (insightface): lighter, ONNX-optimized
  - MediaPipe (fallback): already in project, zero extra dependencies

Design:
  - Lazy-load detector on first call
  - Operates on cropped numpy arrays
  - Returns face bbox in ORIGINAL frame coordinates (not crop-local)
  - Integrates with ActiveSpeakerDetector (provides face landmarks region)
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.infrastructure.person_tracker import BBox

logger = logging.getLogger(__name__)


@dataclass
class FaceDetectionResult:
    """Face detection result in full-frame coordinates."""
    bbox: BBox                     # Face bounding box in original frame pixels
    confidence: float
    person_track_id: int           # Which person track this face belongs to
    landmarks: Optional[List[Tuple[float, float]]] = None  # 5-point landmarks if available

    @property
    def center_x(self) -> float:
        return self.bbox.center_x

    @property
    def center_y(self) -> float:
        return self.bbox.center_y

    @property
    def width(self) -> float:
        return self.bbox.width

    @property
    def height(self) -> float:
        return self.bbox.height


class FaceOnCropDetector:
    """Detect faces only within person crop regions.

    Crops the upper portion (head region) of each person bbox and runs
    face detection on that smaller region. Results are mapped back to
    full-frame coordinates.

    Args:
        backend: 'retinaface', 'scrfd', or 'mediapipe'.
        head_ratio: Fraction of person bbox height to use as head region (0.35 = top 35%).
        confidence_threshold: Minimum face detection confidence.
        min_face_size: Minimum face width in pixels to accept.
    """

    def __init__(
        self,
        backend: str = "retinaface",
        head_ratio: float = 0.35,
        confidence_threshold: float = 0.55,
        min_face_size: int = 20,
    ):
        self._backend = backend
        self._head_ratio = head_ratio
        self._confidence_threshold = confidence_threshold
        self._min_face_size = min_face_size

        self._detector = None
        self._load_attempted = False
        self._load_failed = False
        self._active_backend: str = ""

    @property
    def is_available(self) -> bool:
        return not self._load_failed

    @property
    def active_backend(self) -> str:
        """Which backend is actually loaded."""
        return self._active_backend

    def _load_detector(self) -> bool:
        """Lazy-load face detector with fallback chain."""
        if self._detector is not None:
            return True
        if self._load_attempted:
            return not self._load_failed
        self._load_attempted = True

        # Try backends in preference order
        if self._backend == "retinaface":
            if self._try_load_retinaface():
                return True
            if self._try_load_scrfd():
                return True
        elif self._backend == "scrfd":
            if self._try_load_scrfd():
                return True
            if self._try_load_retinaface():
                return True

        # Final fallback: MediaPipe (always available in this project)
        return self._try_load_mediapipe()

    def _try_load_retinaface(self) -> bool:
        """Load RetinaFace detector."""
        try:
            from retinaface.pre_trained_models import get_model

            self._detector = get_model("resnet50_2020-07-20", max_size=640)
            self._detector.eval()
            self._active_backend = "retinaface"
            logger.info("face_on_crop: RetinaFace loaded (resnet50)")
            return True
        except ImportError:
            logger.debug("face_on_crop: retinaface-pytorch not available")
            return False
        except Exception as e:
            logger.warning(f"face_on_crop: RetinaFace load failed: {e}")
            return False

    def _try_load_scrfd(self) -> bool:
        """Load SCRFD detector via insightface."""
        try:
            from insightface.app import FaceAnalysis

            self._detector = FaceAnalysis(
                name="buffalo_sc",
                allowed_modules=["detection"],
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            self._detector.prepare(ctx_id=0, det_size=(640, 640))
            self._active_backend = "scrfd"
            logger.info("face_on_crop: SCRFD loaded (insightface buffalo_sc)")
            return True
        except ImportError:
            logger.debug("face_on_crop: insightface not available")
            return False
        except Exception as e:
            logger.warning(f"face_on_crop: SCRFD load failed: {e}")
            return False

    def _try_load_mediapipe(self) -> bool:
        """Fallback: MediaPipe Face Detection (already in project)."""
        try:
            import mediapipe as mp

            if hasattr(mp, 'solutions') and hasattr(mp.solutions, 'face_detection'):
                self._detector = mp.solutions.face_detection.FaceDetection(
                    min_detection_confidence=self._confidence_threshold,
                    model_selection=1,
                )
                self._active_backend = "mediapipe"
                logger.info("face_on_crop: MediaPipe Face Detection fallback loaded")
                return True
            else:
                # Task API
                from mediapipe.tasks.vision import FaceDetector, FaceDetectorOptions
                from mediapipe.tasks.vision.core.vision_task_running_mode import VisionTaskRunningMode
                from mediapipe.tasks import BaseOptions
                import os

                model_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'models')
                os.makedirs(model_dir, exist_ok=True)
                model_path = os.path.join(model_dir, 'blaze_face_short_range.tflite')

                if not os.path.exists(model_path):
                    import urllib.request
                    url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
                    urllib.request.urlretrieve(url, model_path)

                base_options = BaseOptions(model_asset_path=model_path)
                options = FaceDetectorOptions(
                    base_options=base_options,
                    running_mode=VisionTaskRunningMode.IMAGE,
                    min_detection_confidence=self._confidence_threshold,
                )
                self._detector = FaceDetector.create_from_options(options)
                self._active_backend = "mediapipe_task"
                logger.info("face_on_crop: MediaPipe Task API fallback loaded")
                return True

        except Exception as e:
            self._load_failed = True
            logger.error(f"face_on_crop: all backends failed: {e}")
            return False

    def detect_faces_for_persons(
        self,
        frame: np.ndarray,
        person_bboxes: Dict[int, BBox],
    ) -> List[FaceDetectionResult]:
        """Detect face for each tracked person.

        For each person bbox, crops the head region, runs face detection,
        and maps results back to full-frame coordinates.

        Args:
            frame: Full video frame (BGR numpy array, H x W x 3).
            person_bboxes: Dict mapping person_track_id → person BBox.

        Returns:
            List of FaceDetectionResult (one per person with detected face).
            Persons with no detected face are omitted.
        """
        if not self._load_detector():
            return []

        results: List[FaceDetectionResult] = []
        frame_h, frame_w = frame.shape[:2]

        for track_id, person_bbox in person_bboxes.items():
            # Compute head region (top portion of person bbox)
            head_crop, offset_x, offset_y = self._extract_head_region(
                frame, person_bbox, frame_w, frame_h
            )

            if head_crop is None or head_crop.size == 0:
                continue

            # Run face detection on crop
            face_result = self._detect_in_crop(head_crop, track_id, offset_x, offset_y)
            if face_result is not None:
                results.append(face_result)

        return results

    def _extract_head_region(
        self,
        frame: np.ndarray,
        person_bbox: BBox,
        frame_w: int,
        frame_h: int,
    ) -> Tuple[Optional[np.ndarray], int, int]:
        """Extract head region crop from person bbox.

        Returns:
            (crop_array, offset_x, offset_y) — offsets for coordinate mapping.
            Returns (None, 0, 0) if crop is invalid.
        """
        person_h = person_bbox.height
        head_h = person_h * self._head_ratio

        # Head region: top portion of person bbox with small horizontal padding
        pad_x = person_bbox.width * 0.05  # 5% horizontal padding
        x1 = max(0, int(person_bbox.x1 - pad_x))
        y1 = max(0, int(person_bbox.y1))
        x2 = min(frame_w, int(person_bbox.x2 + pad_x))
        y2 = min(frame_h, int(person_bbox.y1 + head_h))

        if x2 <= x1 or y2 <= y1:
            return None, 0, 0

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
            return None, 0, 0

        return crop, x1, y1

    def _detect_in_crop(
        self,
        crop: np.ndarray,
        track_id: int,
        offset_x: int,
        offset_y: int,
    ) -> Optional[FaceDetectionResult]:
        """Run face detection on a cropped region.

        Dispatches to the appropriate backend and maps coordinates back.
        """
        if self._active_backend == "retinaface":
            return self._detect_retinaface(crop, track_id, offset_x, offset_y)
        elif self._active_backend == "scrfd":
            return self._detect_scrfd(crop, track_id, offset_x, offset_y)
        elif self._active_backend in ("mediapipe", "mediapipe_task"):
            return self._detect_mediapipe(crop, track_id, offset_x, offset_y)
        return None

    def _detect_retinaface(
        self,
        crop: np.ndarray,
        track_id: int,
        offset_x: int,
        offset_y: int,
    ) -> Optional[FaceDetectionResult]:
        """RetinaFace detection on crop."""
        try:
            import cv2
            import torch

            # RetinaFace expects RGB
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

            with torch.no_grad():
                predictions = self._detector.predict_jsons(crop_rgb)

            if not predictions:
                return None

            # Take highest confidence face
            best = max(predictions, key=lambda p: p.get("score", 0))
            score = best.get("score", 0)
            if score < self._confidence_threshold:
                return None

            bbox_coords = best.get("bbox", [])
            if len(bbox_coords) < 4:
                return None

            # Map crop-local coords back to full frame
            fx1 = float(bbox_coords[0]) + offset_x
            fy1 = float(bbox_coords[1]) + offset_y
            fx2 = float(bbox_coords[2]) + offset_x
            fy2 = float(bbox_coords[3]) + offset_y

            face_w = fx2 - fx1
            if face_w < self._min_face_size:
                return None

            # Extract landmarks if available
            landmarks = None
            lm_data = best.get("landmarks", [])
            if lm_data and len(lm_data) >= 5:
                landmarks = [
                    (float(pt[0]) + offset_x, float(pt[1]) + offset_y)
                    for pt in lm_data[:5]
                ]

            return FaceDetectionResult(
                bbox=BBox(fx1, fy1, fx2, fy2),
                confidence=float(score),
                person_track_id=track_id,
                landmarks=landmarks,
            )

        except Exception as e:
            logger.debug(f"face_on_crop: RetinaFace inference error for track {track_id}: {e}")
            return None

    def _detect_scrfd(
        self,
        crop: np.ndarray,
        track_id: int,
        offset_x: int,
        offset_y: int,
    ) -> Optional[FaceDetectionResult]:
        """SCRFD (insightface) detection on crop."""
        try:
            faces = self._detector.get(crop)

            if not faces:
                return None

            # Take largest face (most likely the actual person's face)
            best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

            score = float(best.det_score) if hasattr(best, 'det_score') else 0.9
            if score < self._confidence_threshold:
                return None

            x1, y1, x2, y2 = best.bbox
            face_w = float(x2) - float(x1)
            if face_w < self._min_face_size:
                return None

            # Map back to full frame
            fx1 = float(x1) + offset_x
            fy1 = float(y1) + offset_y
            fx2 = float(x2) + offset_x
            fy2 = float(y2) + offset_y

            # Extract landmarks
            landmarks = None
            if hasattr(best, 'kps') and best.kps is not None:
                landmarks = [
                    (float(pt[0]) + offset_x, float(pt[1]) + offset_y)
                    for pt in best.kps[:5]
                ]

            return FaceDetectionResult(
                bbox=BBox(fx1, fy1, fx2, fy2),
                confidence=score,
                person_track_id=track_id,
                landmarks=landmarks,
            )

        except Exception as e:
            logger.debug(f"face_on_crop: SCRFD inference error for track {track_id}: {e}")
            return None

    def _detect_mediapipe(
        self,
        crop: np.ndarray,
        track_id: int,
        offset_x: int,
        offset_y: int,
    ) -> Optional[FaceDetectionResult]:
        """MediaPipe face detection on crop (fallback)."""
        try:
            import cv2

            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            crop_h, crop_w = crop_rgb.shape[:2]

            if self._active_backend == "mediapipe":
                # Legacy API
                results = self._detector.process(crop_rgb)
                if not results.detections:
                    return None

                # Take highest confidence
                best = max(
                    results.detections,
                    key=lambda d: d.score[0] if d.score else 0,
                )
                score = float(best.score[0]) if best.score else 0.0
                if score < self._confidence_threshold:
                    return None

                bbox = best.location_data.relative_bounding_box
                x1 = bbox.xmin * crop_w + offset_x
                y1 = bbox.ymin * crop_h + offset_y
                x2 = (bbox.xmin + bbox.width) * crop_w + offset_x
                y2 = (bbox.ymin + bbox.height) * crop_h + offset_y

            else:
                # Task API
                import mediapipe as mp
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_rgb)
                result = self._detector.detect(mp_image)

                if not result.detections:
                    return None

                best = result.detections[0]
                score = float(best.categories[0].score) if best.categories else 0.0
                if score < self._confidence_threshold:
                    return None

                bbox = best.bounding_box
                x1 = float(bbox.origin_x) + offset_x
                y1 = float(bbox.origin_y) + offset_y
                x2 = float(bbox.origin_x + bbox.width) + offset_x
                y2 = float(bbox.origin_y + bbox.height) + offset_y

            face_w = x2 - x1
            if face_w < self._min_face_size:
                return None

            return FaceDetectionResult(
                bbox=BBox(x1, y1, x2, y2),
                confidence=score,
                person_track_id=track_id,
                landmarks=None,
            )

        except Exception as e:
            logger.debug(f"face_on_crop: MediaPipe error for track {track_id}: {e}")
            return None
