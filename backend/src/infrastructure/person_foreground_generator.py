"""YOLO11-seg foreground PNG generator for text-behind-person events."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from src.config import settings

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
        
        import rfdetr
        self._model = rfdetr.RFDETRSegLarge()
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
        behind_events = [event for event in safe_events if event.get("effect") == "behind_person"]
        # Effects that need person bbox/head/depth metadata (no PNG needed)
        tracking_effects = {"floating_text", "auto_avoid", "around_head", "depth_text"}
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
            logger.warning("text_emphasis: RF-DETR-Seg unavailable, using spotlight fallback: %s", exc)
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
                needs_png = event.get("effect") == "behind_person"
                # Subsample tracking effects (every 3rd frame) for performance.
                # PNG effects need every frame for smooth mask animation.
                frame_step = 1 if needs_png else 3

                for composition_frame in range(start_frame, end_frame + 1, frame_step):
                    cap.set(cv2.CAP_PROP_POS_MSEC, composition_frame * 1000.0 / fps)
                    ok, frame = cap.read()
                    if not ok:
                        continue
                    try:
                        preds = model.predict(frame, threshold=float(settings.TEXT_EMPHASIS_SEG_CONFIDENCE))
                        person_masks = []
                        person_bboxes = []
                        for idx in range(len(preds)):
                            cname = preds.data.get('class_name')[idx] if 'class_name' in preds.data else ""
                            cid = preds.class_id[idx]
                            if cname == "person" or cid == 1:
                                person_masks.append(preds.mask[idx])
                                if hasattr(preds, 'xyxy') and idx < len(preds.xyxy):
                                    person_bboxes.append(preds.xyxy[idx])
                    except Exception as exc:
                        logger.warning("text_emphasis: RF-DETR inference failed at frame %s: %s", composition_frame, exc)
                        continue

                    if not person_masks:
                        continue

                    masks = np.array(person_masks)
                    union = np.max(masks, axis=0)
                    if union.shape[:2] != (height, width):
                        union = cv2.resize(union, (width, height), interpolation=cv2.INTER_LINEAR)

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
                        alpha = np.clip(union * 255, 0, 255).astype(np.uint8)
                        alpha = cv2.GaussianBlur(alpha, (kernel, kernel), 0)
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
                min_coverage = 0.90 if needs_png else 0.20
                if coverage < min_coverage:
                    event["effect"] = "spotlight"
                    event["fallback_reason"] = "insufficient_person_mask"
                    event["foreground_frames"] = []
                    logger.info(
                        "text_emphasis: %s downgraded to spotlight (mask coverage %.0f%%)",
                        event.get("id"), coverage * 100,
                    )
                    continue

                # Fill rare single-frame misses with the nearest successful mask.
                available = sorted(generated)
                frames = []
                for frame_number in range(start_frame, end_frame + 1):
                    nearest = frame_number if frame_number in generated else min(
                        available, key=lambda candidate: abs(candidate - frame_number)
                    )
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
        tracking_effects = {"behind_person", "floating_text", "auto_avoid", "around_head", "depth_text"}
        for event in events:
            updated = dict(event)
            if updated.get("effect") in tracking_effects:
                updated["effect"] = "spotlight"
                updated["fallback_reason"] = reason
                updated["foreground_frames"] = []
            output.append(updated)
        return output
