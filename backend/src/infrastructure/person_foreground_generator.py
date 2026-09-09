"""YOLO11-seg foreground PNG generator for cinematic text events."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from src.config import settings

from src.infrastructure.top_behind_subject_renderer import fast_guided_filter

logger = logging.getLogger(__name__)


class PersonForegroundGenerator:
    """Generate sparse, cropped RGBA frames only for selected event windows.

    Detection/reframing remains handled by the existing pipeline. This class is
    deliberately isolated so the optional effect can fail soft without changing
    the base video or its audio timeline.
    """

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or settings.YOLO_SEG_MODEL
        self._model = None

    async def generate_for_events(
        self,
        video_path: str,
        events: list[dict],
        output_dir: str,
        fps: int = 30,
        feather: int | None = None,
    ) -> list[dict]:
        return await asyncio.to_thread(
            self._generate_sync,
            video_path,
            events,
            output_dir,
            fps,
            feather or settings.TEXT_EMPHASIS_MASK_FEATHER,
        )

    def _load_model(self):
        if self._model is not None:
            return self._model

        model_p = self.model_path
        if not os.path.exists(model_p) and not os.path.isabs(model_p):
            candidates = [
                os.path.join(os.path.dirname(__file__), "..", "..", "yolo11n-seg.pt"),
                os.path.join(os.path.dirname(__file__), "..", "..", "backend", "yolo11n-seg.pt"),
                "backend/yolo11n-seg.pt",
                "yolo11n-seg.pt",
            ]
            for cand in candidates:
                if os.path.exists(cand):
                    model_p = os.path.abspath(cand)
                    break

        from ultralytics import YOLO
        self._model = YOLO(model_p)
        return self._model

    def _generate_sync(
        self,
        video_path: str,
        events: list[dict],
        output_dir: str,
        fps: int,
        feather: int,
    ) -> list[dict]:
        import cv2
        import numpy as np

        safe_events = [dict(event) for event in events[:2]]
        # Effects that need person segmentation (foreground PNG)
        # depth_cutout needs person segmentation PNG; other tracking effects need bbox/head/depth only
        behind_events = [event for event in safe_events if event.get("effect") in {"depth_cutout", "behind_person"}]
        tracking_effects = {"float_track", "smart_gap", "orbit_halo", "z_parallax",
                            "floating_text", "auto_avoid", "around_head", "depth_text"}
        tracking_events = [event for event in safe_events if event.get("effect") in tracking_effects]
        if not behind_events and not tracking_events:
            return safe_events

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("text_emphasis: unable to open video for segmentation: %s", video_path)
            return self._downgrade_behind_events(safe_events, "video_unreadable")
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            cap.release()
            return self._downgrade_behind_events(safe_events, "invalid_video_dimensions")

        try:
            model = self._load_model()
        except Exception as exc:
            cap.release()
            logger.warning("text_emphasis: YOLO segmentation unavailable, using hero_punch fallback: %s", exc)
            return self._downgrade_behind_events(safe_events, "segmentation_unavailable")

        os.makedirs(output_dir, exist_ok=True)
        kernel = max(1, min(31, int(feather)))
        if kernel % 2 == 0:
            kernel += 1

        try:
            all_track_events = behind_events + tracking_events
            for event in all_track_events:
                event_dir = os.path.join(output_dir, str(event.get("id") or "event"))
                os.makedirs(event_dir, exist_ok=True)
                start_frame = max(0, round(float(event["start"]) * fps))
                end_frame = max(start_frame + 1, round(float(event["end"]) * fps))
                generated: dict[int, dict] = {}
                needs_png = event.get("effect") in {"depth_cutout", "behind_person"}
                # Subsample tracking effects (every 3rd frame) for performance.
                # PNG effects need every frame for smooth mask animation.
                frame_step = 1 if needs_png else 3

                prev_png_alpha: np.ndarray | None = None
                classes_to_detect = [0, 24, 26, 27, 28, 39, 41, 63, 64, 65, 66, 67, 73, 76] if needs_png else [0]

                for composition_frame in range(start_frame, end_frame + 1, frame_step):
                    cap.set(cv2.CAP_PROP_POS_MSEC, composition_frame * 1000.0 / fps)
                    ok, frame = cap.read()
                    if not ok:
                        continue
                    try:
                        results = model.predict(
                            source=frame,
                            classes=classes_to_detect,
                            conf=float(settings.TEXT_EMPHASIS_SEG_CONFIDENCE),
                            verbose=False,
                        )
                        person_masks = []
                        person_bboxes = []
                        object_masks = []
                        result = results[0] if results else None
                        if result is not None and result.masks is not None:
                            masks = result.masks.data.detach().cpu().numpy()
                            boxes = (
                                result.boxes.xyxy.detach().cpu().numpy()
                                if result.boxes is not None
                                else []
                            )
                            classes_arr = (
                                result.boxes.cls.detach().cpu().numpy().astype(int)
                                if result.boxes is not None
                                else []
                            )
                            for i, m in enumerate(masks):
                                cls_id = int(classes_arr[i]) if i < len(classes_arr) else 0
                                if cls_id == 0:
                                    person_masks.append(m)
                                    if i < len(boxes):
                                        person_bboxes.append(boxes[i])
                                else:
                                    object_masks.append(m)
                    except Exception as exc:
                        logger.warning("text_emphasis: YOLO inference failed at frame %s: %s", composition_frame, exc)
                        continue

                    if not person_masks:
                        continue

                    masks = np.array(person_masks)
                    union = np.max(masks, axis=0)
                    if union.shape[:2] != (height, width):
                        union = cv2.resize(union, (width, height), interpolation=cv2.INTER_LINEAR)

                    # Merge overlapping held objects (laptop, cup, phone, etc.)
                    if object_masks and needs_png:
                        for obj_m in object_masks:
                            if obj_m.shape[:2] != (height, width):
                                obj_m = cv2.resize(obj_m, (width, height), interpolation=cv2.INTER_LINEAR)
                            overlap = float(np.sum((union > 0.3) & (obj_m > 0.3)))
                            obj_sum = float(np.sum(obj_m > 0.3))
                            if obj_sum > 0 and (overlap / obj_sum) >= 0.12:
                                union = np.maximum(union, obj_m)

                    # Compute person bbox from mask union (always, for tracking effects)
                    ys, xs = np.where(union > 0.5)
                    if xs.size == 0 or ys.size == 0:
                        continue
                    pad = max(8, round(min(width, height) * 0.012))
                    x1 = max(0, int(xs.min()) - pad)
                    y1 = max(0, int(ys.min()) - pad)
                    x2 = min(width, int(xs.max()) + pad + 1)
                    y2 = min(height, int(ys.max()) + pad + 1)

                    # Estimate head bbox (top ~22% of person bbox)
                    person_h = y2 - y1
                    person_w = x2 - x1
                    head_y1 = y1
                    head_y2 = min(y2, y1 + max(20, int(person_h * 0.22)))
                    head_x1 = max(0, x1 + int(person_w * 0.18))
                    head_x2 = min(width, x2 - int(person_w * 0.18))

                    # Estimate depth_z: normalized person area (larger = nearer)
                    person_area = person_w * person_h
                    frame_area = max(1, width * height)
                    depth_z = round(min(1.0, person_area / (frame_area * 0.35)), 3)

                    if needs_png:
                        # 1. Binarize & solidify body, microphones, ties, and hands
                        binary = (union >= 0.38).astype(np.uint8) * 255
                        pad_f = np.zeros((height + 4, width + 4), dtype=np.uint8)
                        pad_f[2 : height + 2, 2 : width + 2] = binary
                        pad_f[height + 2, :] = 255
                        flood = pad_f.copy()
                        ff_mask = np.zeros((height + 6, width + 6), dtype=np.uint8)
                        cv2.floodFill(flood, ff_mask, (0, 0), 128)
                        holes = (flood != 128) & (pad_f == 0)
                        pad_f[holes] = 255
                        sealed = pad_f[2 : height + 2, 2 : width + 2]

                        # Bounded scanline bridge for internal gaps (mics, hands on chest)
                        max_gap = max(35, int(round(person_w * 0.40)))
                        for y_row in range(y1, y2):
                            row_pts = np.where(sealed[y_row, :] > 0)[0]
                            if len(row_pts) >= 2:
                                diffs = np.diff(row_pts)
                                g_idxs = np.where(diffs > 1)[0]
                                for gi in g_idxs:
                                    xl = int(row_pts[gi])
                                    xr = int(row_pts[gi + 1])
                                    if (xr - xl) <= max_gap:
                                        sealed[y_row, xl : xr + 1] = 255

                        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 17))
                        sealed = cv2.morphologyEx(sealed, cv2.MORPH_CLOSE, k_close, iterations=1)
                        raw_alpha = (sealed >= 128).astype(np.float32)

                        # 2. Multi-frame temporal smoothing across sequence
                        if prev_png_alpha is not None and prev_png_alpha.shape == raw_alpha.shape:
                            diff = np.abs(raw_alpha - prev_png_alpha)
                            alpha_weight = np.where(diff < 0.12, 0.60, 0.15).astype(np.float32)
                            raw_alpha = alpha_weight * prev_png_alpha + (1.0 - alpha_weight) * raw_alpha
                        prev_png_alpha = raw_alpha.copy()

                        # 3. High-precision guided filter for razor-sharp edge snapping
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
                        refined_alpha = fast_guided_filter(gray, raw_alpha, r=6, eps=1e-3, subsample=2)
                        alpha = np.clip(refined_alpha * 255, 0, 255).astype(np.uint8)

                        crop = frame[y1:y2, x1:x2]
                        crop_alpha = alpha[y1:y2, x1:x2]
                        bgra = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA)
                        bgra[:, :, 3] = crop_alpha
                        frame_path = os.path.abspath(os.path.join(event_dir, f"frame_{composition_frame:06d}.png"))
                        if cv2.imwrite(frame_path, bgra):
                            generated[composition_frame] = {
                                "frame": composition_frame,
                                "path": frame_path,
                                "x": x1, "y": y1,
                                "width": x2 - x1, "height": y2 - y1,
                                "head_x": head_x1, "head_y": head_y1,
                                "head_width": head_x2 - head_x1, "head_height": head_y2 - head_y1,
                                "depth_z": depth_z,
                            }
                    else:
                        # Tracking effects: no PNG, just metadata
                        generated[composition_frame] = {
                            "frame": composition_frame,
                            "path": "",
                            "x": x1, "y": y1,
                            "width": x2 - x1, "height": y2 - y1,
                            "head_x": head_x1, "head_y": head_y1,
                            "head_width": head_x2 - head_x1, "head_height": head_y2 - head_y1,
                            "depth_z": depth_z,
                        }

                expected = end_frame - start_frame + 1
                coverage = len(generated) / max(1, expected)
                # Tracking effects use a lower threshold (no PNG needed, just bbox metadata).
                # With 3x subsampling, expected generated frames = expected/3, so adjust threshold.
                # A mostly valid behind-person sequence is usable, but never
                # hide long detector gaps with one old PNG: that makes the
                # foreground person visibly freeze while text keeps moving.
                min_coverage = 0.70 if needs_png else 0.20
                if coverage < min_coverage:
                    event["effect"] = "hero_punch"
                    event["fallback_reason"] = "insufficient_person_mask"
                    event["foreground_frames"] = []
                    logger.info(
                        "text_emphasis: %s downgraded to hero_punch (mask coverage %.0f%%)",
                        event.get("id"), coverage * 100,
                    )
                    continue

                # Fill only tiny misses. Long misses intentionally have no
                # foreground frame instead of holding a stale person image.
                available = sorted(generated)
                frames = []
                for frame_number in range(start_frame, end_frame + 1):
                    nearest = frame_number if frame_number in generated else min(
                        available, key=lambda candidate: abs(candidate - frame_number)
                    )
                    max_fill_gap = 2 if needs_png else frame_step
                    if abs(nearest - frame_number) <= max_fill_gap:
                        frames.append({**generated[nearest], "frame": frame_number})
                event["foreground_frames"] = frames
                event["source_width"] = width
                event["source_height"] = height
                event["mask_coverage"] = round(coverage, 3)
        finally:
            cap.release()

        by_id = {event.get("id"): event for event in all_track_events}
        return [by_id.get(event.get("id"), event) for event in safe_events]

    @staticmethod
    def _downgrade_behind_events(events: list[dict], reason: str) -> list[dict]:
        output = []
        tracking_effects = {
            "depth_cutout", "float_track", "smart_gap", "orbit_halo", "z_parallax",
            "behind_person", "floating_text", "auto_avoid", "around_head", "depth_text",
        }
        for event in events:
            updated = dict(event)
            if updated.get("effect") in tracking_effects:
                updated["effect"] = "hero_punch"
                updated["fallback_reason"] = reason
                updated["foreground_frames"] = []
            output.append(updated)
        return output
