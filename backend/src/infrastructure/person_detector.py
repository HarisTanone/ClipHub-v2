"""PersonDetector — RF-DETR based full-body person detection.

Replaces MediaPipe Face Detection as the primary detection anchor.
Detects full person bounding boxes which persist even when face is occluded,
turned, or looking down.

Models supported:
  - rfdetr-medium: faster, lower VRAM
  - rfdetr-large: default, best balance
  - rfdetr-2xlarge: highest recall, heavier

Design:
  - Lazy-load model on first call
  - GPU auto-detected via torch.cuda
  - Returns BBox in absolute pixel coordinates (same as person_tracker.BBox)
  - Confidence threshold configurable via settings.PERSON_CONF_THRESHOLD
"""
import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


PersonBox = Tuple[float, float, float, float, float]


def filter_duplicate_person_boxes(
    detections: Sequence[PersonBox],
) -> List[PersonBox]:
    """Suppress nested/tight-loose body boxes before tracker ID assignment.

    Rules:
      1. High IoU → same person; keep higher-confidence.
      2. High containment (nested shell) → same person; keep the *tighter*
         (smaller) box. Outer mega-boxes that swallow a real person are dropped.
      3. Multi-person container: a box whose area is ≥1.8× another and that
         contains the other's center is dropped (RF-DETR group blob).
    """
    if len(detections) < 2:
        return list(detections)

    # Conf desc, then *smaller* area first so individual people win over shells.
    ordered = sorted(
        detections,
        key=lambda det: (
            float(det[4]),
            -((float(det[2]) - float(det[0])) * (float(det[3]) - float(det[1]))),
        ),
        reverse=True,
    )
    selected: List[PersonBox] = []
    for detection in ordered:
        x1, y1, x2, y2, conf = map(float, detection)
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        area = width * height
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        is_duplicate = False
        replace_idx: Optional[int] = None
        for idx, existing in enumerate(selected):
            ex1, ey1, ex2, ey2, e_conf = map(float, existing)
            e_width = max(0.0, ex2 - ex1)
            e_height = max(0.0, ey2 - ey1)
            e_area = e_width * e_height
            inter_w = max(0.0, min(x2, ex2) - max(x1, ex1))
            inter_h = max(0.0, min(y2, ey2) - max(y1, ey1))
            intersection = inter_w * inter_h
            union = max(1.0, area + e_area - intersection)
            iou = intersection / union
            smaller = max(1.0, min(area, e_area))
            containment = intersection / smaller
            larger_diagonal = max(
                1.0,
                math.hypot(max(width, e_width), max(height, e_height)),
            )
            center_distance = math.hypot(
                center_x - (ex1 + ex2) / 2.0,
                center_y - (ey1 + ey2) / 2.0,
            )
            c_ratio = center_distance / larger_diagonal

            # Classic NMS: heavy overlap → keep higher conf (already ordered).
            if iou >= 0.55:
                logger.info(
                    f"person_detector: DUP suppress iou={iou:.3f} "
                    f"drop conf={conf:.2f} keep conf={e_conf:.2f}"
                )
                is_duplicate = True
                break

            # Nested same-person: keep tighter (smaller) box.
            if containment >= 0.80 and c_ratio <= 0.35:
                if area >= e_area:
                    logger.info(
                        f"person_detector: DUP nest-drop-large "
                        f"contain={containment:.3f} c_ratio={c_ratio:.3f} "
                        f"drop conf={conf:.2f} area={area:.0f} "
                        f"keep conf={e_conf:.2f} area={e_area:.0f}"
                    )
                    is_duplicate = True
                    break
                # Current is tighter → replace the outer shell already selected.
                logger.info(
                    f"person_detector: DUP nest-replace-large "
                    f"contain={containment:.3f} c_ratio={c_ratio:.3f} "
                    f"keep conf={conf:.2f} area={area:.0f} "
                    f"drop conf={e_conf:.2f} area={e_area:.0f}"
                )
                replace_idx = idx
                break

            # Container blob: much larger box encloses another person's center.
            if area >= e_area * 1.8:
                e_cx, e_cy = (ex1 + ex2) / 2.0, (ey1 + ey2) / 2.0
                if x1 <= e_cx <= x2 and y1 <= e_cy <= y2 and containment >= 0.50:
                    logger.info(
                        f"person_detector: DUP container-drop "
                        f"contain={containment:.3f} area_ratio={area / max(1.0, e_area):.2f} "
                        f"drop conf={conf:.2f}"
                    )
                    is_duplicate = True
                    break
            elif e_area >= area * 1.8:
                if ex1 <= center_x <= ex2 and ey1 <= center_y <= ey2 and containment >= 0.50:
                    logger.info(
                        f"person_detector: DUP container-replace "
                        f"contain={containment:.3f} "
                        f"keep conf={conf:.2f} drop conf={e_conf:.2f}"
                    )
                    replace_idx = idx
                    break

        if is_duplicate:
            continue
        box = (x1, y1, x2, y2, conf)
        if replace_idx is not None:
            selected[replace_idx] = box
        else:
            selected.append(box)

    return sorted(
        selected,
        key=lambda det: (
            (float(det[0]) + float(det[2])) / 2.0,
            (float(det[1]) + float(det[3])) / 2.0,
        ),
    )



@dataclass
class PersonDetection:
    """A single detected person with bounding box and confidence."""
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    confidence: float

    @property
    def center_x(self) -> float:
        return (self.bbox_x1 + self.bbox_x2) / 2

    @property
    def center_y(self) -> float:
        return (self.bbox_y1 + self.bbox_y2) / 2

    @property
    def width(self) -> float:
        return self.bbox_x2 - self.bbox_x1

    @property
    def height(self) -> float:
        return self.bbox_y2 - self.bbox_y1

    @property
    def area(self) -> float:
        return max(0, self.width) * max(0, self.height)

    def to_xyxy(self) -> tuple:
        """Return (x1, y1, x2, y2) tuple."""
        return (self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2)

    def to_box_tuple(self) -> PersonBox:
        return (
            self.bbox_x1,
            self.bbox_y1,
            self.bbox_x2,
            self.bbox_y2,
            self.confidence,
        )

    @classmethod
    def from_box_tuple(cls, box: PersonBox) -> "PersonDetection":
        return cls(
            bbox_x1=float(box[0]),
            bbox_y1=float(box[1]),
            bbox_x2=float(box[2]),
            bbox_y2=float(box[3]),
            confidence=float(box[4]),
        )


class PersonDetector:
    """RF-DETR based person detection.

    Lazy-loads the model on first detect() call. Supports multiple RF-DETR
    variants selectable via config.

    Args:
        model_variant: One of 'rfdetr-medium', 'rfdetr-large', 'rfdetr-2xlarge'.
        confidence_threshold: Minimum confidence to accept a detection.
    """

    # RF-DETR model class mapping
    _MODEL_MAP = {
        "rfdetr-medium": "RFDETRBase",
        "rfdetr-large": "RFDETRLarge",
        "rfdetr-2xlarge": "RFDETRLarge",  # fallback to Large if 2XLarge unavailable
    }

    # COCO 'person' is class 0 in Ultralytics (0-index) and often class 1 in
    # RF-DETR/supervision exports (1-index). Accept both; never drop real people
    # because of off-by-one class maps.
    PERSON_CLASS_ID = 0
    PERSON_CLASS_IDS = frozenset({0, 1})


    def __init__(
        self,
        model_variant: str = "rfdetr-large",
        confidence_threshold: float = 0.50,
    ):
        self._model_variant = model_variant
        self._confidence_threshold = confidence_threshold
        self._model = None
        self._load_attempted = False
        self._load_failed = False
        self._use_supervision = False

    @property
    def is_available(self) -> bool:
        """Check if detector can be loaded."""
        return not self._load_failed

    def _load_model(self) -> bool:
        """Lazy-load RF-DETR model.

        Tries rfdetr package first. Falls back to Ultralytics YOLO with
        RF-DETR-style usage if the dedicated package isn't available.
        """
        if self._model is not None:
            return True
        if self._load_attempted:
            return not self._load_failed
        self._load_attempted = True

        try:
            import rfdetr

            model_class_name = self._MODEL_MAP.get(
                self._model_variant, "RFDETRLarge"
            )

            if hasattr(rfdetr, model_class_name):
                model_class = getattr(rfdetr, model_class_name)
            elif hasattr(rfdetr, "RFDETRLarge"):
                model_class = rfdetr.RFDETRLarge
                logger.info(
                    f"person_detector: {model_class_name} not found, "
                    "falling back to RFDETRLarge"
                )
            else:
                model_class = rfdetr.RFDETRBase
                logger.info(
                    "person_detector: falling back to RFDETRBase"
                )

            self._model = model_class()
            self._use_supervision = True
            logger.info(
                f"person_detector: RF-DETR loaded "
                f"(variant={self._model_variant}, class={model_class.__name__})"
            )
            return True

        except ImportError:
            logger.warning(
                "person_detector: rfdetr package not available, "
                "falling back to Ultralytics YOLO person detection"
            )
            return self._load_ultralytics_fallback()

        except Exception as e:
            logger.error(f"person_detector: failed to load RF-DETR: {e}")
            return self._load_ultralytics_fallback()

    def _load_ultralytics_fallback(self) -> bool:
        """Fallback: use Ultralytics YOLO for person detection."""
        try:
            from ultralytics import YOLO

            self._model = YOLO("yolo11n.pt")
            self._use_supervision = False
            logger.info("person_detector: using Ultralytics YOLO fallback")
            return True

        except Exception as e:
            self._load_failed = True
            logger.error(f"person_detector: all detection backends failed: {e}")
            return False

    def detect(
        self,
        frame: np.ndarray,
        confidence_override: Optional[float] = None,
    ) -> List[PersonDetection]:
        """Detect persons in a single frame.

        Args:
            frame: BGR or RGB numpy array (H, W, 3).
            confidence_override: Override default confidence threshold.

        Returns:
            List of PersonDetection sorted by area (largest first).
        """
        if not self._load_model():
            return []

        threshold = confidence_override or self._confidence_threshold
        if self._use_supervision:
            detections = self._detect_rfdetr(frame, threshold)
        else:
            detections = self._detect_ultralytics(frame, threshold)

        detections = [
            PersonDetection.from_box_tuple(box)
            for box in filter_duplicate_person_boxes(
                [d.to_box_tuple() for d in detections]
            )
        ]
        detections.sort(key=lambda d: d.area, reverse=True)
        return detections

    def _detect_rfdetr(
        self,
        frame: np.ndarray,
        threshold: float,
    ) -> List[PersonDetection]:
        """Run RF-DETR inference using supervision Detections output."""
        import supervision as sv

        results = self._model.predict(frame, threshold=threshold)

        if not isinstance(results, sv.Detections):
            logger.debug("person_detector: unexpected result type, attempting parse")
            return []

        detections: List[PersonDetection] = []
        dropped_classes: dict = {}
        for i in range(len(results)):
            class_id = int(results.class_id[i]) if results.class_id is not None else -1
            # Accept 0 (Ultralytics COCO) and 1 (RF-DETR 1-index COCO person).
            if class_id not in self.PERSON_CLASS_IDS:
                dropped_classes[class_id] = dropped_classes.get(class_id, 0) + 1
                continue

            confidence = float(results.confidence[i]) if results.confidence is not None else 1.0
            if confidence < threshold:
                continue

            x1, y1, x2, y2 = results.xyxy[i]
            detections.append(PersonDetection(
                bbox_x1=float(x1),
                bbox_y1=float(y1),
                bbox_x2=float(x2),
                bbox_y2=float(y2),
                confidence=confidence,
            ))

        if not detections and dropped_classes and not getattr(self, "_logged_class_map", False):
            self._logged_class_map = True
            logger.warning(
                f"person_detector: RF-DETR boxes present but none matched "
                f"PERSON_CLASS_IDS={sorted(self.PERSON_CLASS_IDS)}; "
                f"dropped_class_counts={dropped_classes} total_raw={len(results)}"
            )

        return detections



    def _detect_ultralytics(
        self,
        frame: np.ndarray,
        threshold: float,
    ) -> List[PersonDetection]:
        """Run Ultralytics YOLO inference as fallback."""
        results = self._model.predict(
            source=frame,
            classes=[self.PERSON_CLASS_ID],
            conf=threshold,
            verbose=False,
        )

        detections: List[PersonDetection] = []
        if not results or results[0].boxes is None:
            return detections

        boxes = results[0].boxes
        for i in range(len(boxes)):
            xyxy = boxes.xyxy[i].cpu().numpy()
            conf = float(boxes.conf[i].cpu().numpy())
            detections.append(PersonDetection(
                bbox_x1=float(xyxy[0]),
                bbox_y1=float(xyxy[1]),
                bbox_x2=float(xyxy[2]),
                bbox_y2=float(xyxy[3]),
                confidence=conf,
            ))

        return detections

    def detect_batch(
        self,
        frames: List[np.ndarray],
        confidence_override: Optional[float] = None,
    ) -> List[List[PersonDetection]]:
        """Detect persons in multiple frames (sequential, no batching yet).

        Future: implement true batch inference for GPU efficiency.
        """
        return [self.detect(frame, confidence_override) for frame in frames]
