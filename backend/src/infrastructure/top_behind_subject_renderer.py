"""Top Behind Subject Overlay — portrait top-region B-roll behind person cutout.

Keeps existing full-frame B-roll splice intact. This is additive: only the top
~50% of the frame gets stock footage/image *behind* the YOLO person mask, with
a soft vertical gradient. Bottom stays original. Never coexists with AI text
emphasis on the same time ranges (caller must block).
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TopOverlaySegment:
    """One timed top-overlay window on a clip timeline (0-based)."""
    at_time: float
    duration: float
    asset_path: str
    keyword: str = ""
    source: str = ""


class TopBehindSubjectRenderer:
    """Composite top-region overlay behind YOLO person mask.

    Frame API (unit-testable):
        render(frame, person_mask, overlay_frame) -> composite BGR uint8

    Clip API (pipeline):
        apply_to_clip(video_path, segments, output_path) -> output_path or None
    """

    def __init__(
        self,
        split_ratio: float | None = None,
        fade_height: float | None = None,
        overlay_opacity: float | None = None,
        person_outline: bool | None = None,
        person_shadow: bool | None = None,
        seg_confidence: float | None = None,
        mask_feather: int | None = None,
        mask_stride: int | None = None,
        model_path: str | None = None,
    ):
        self.split_ratio = float(
            split_ratio if split_ratio is not None else settings.TOP_OVERLAY_SPLIT_RATIO
        )
        self.fade_height = float(
            fade_height if fade_height is not None else settings.TOP_OVERLAY_FADE_HEIGHT
        )
        self.overlay_opacity = float(
            overlay_opacity if overlay_opacity is not None else settings.TOP_OVERLAY_OPACITY
        )
        self.person_outline = bool(
            person_outline if person_outline is not None else settings.TOP_OVERLAY_PERSON_OUTLINE
        )
        self.person_shadow = bool(
            person_shadow if person_shadow is not None else settings.TOP_OVERLAY_PERSON_SHADOW
        )
        self.seg_confidence = float(
            seg_confidence if seg_confidence is not None else settings.TOP_OVERLAY_SEG_CONFIDENCE
        )
        self.mask_feather = int(
            mask_feather if mask_feather is not None else settings.TOP_OVERLAY_MASK_FEATHER
        )
        self.mask_stride = max(
            1,
            int(mask_stride if mask_stride is not None else settings.TOP_OVERLAY_MASK_STRIDE),
        )
        self.model_path = model_path or settings.YOLO_SEG_MODEL
        self._model = None
        self._gradient_cache: dict[tuple[int, int], np.ndarray] = {}

    # ─── Public frame compositor ────────────────────────────────────────────

    def render(
        self,
        frame: np.ndarray,
        person_mask: np.ndarray,
        overlay_frame: np.ndarray,
    ) -> np.ndarray:
        """Composite one BGR frame.

        Args:
            frame: original BGR HxWx3 uint8
            person_mask: HxW float/uint8, person=foreground ( >0.5 or >127 )
            overlay_frame: BGR HxWx3 already cover-cropped to frame size
        """
        import cv2

        h, w = frame.shape[:2]
        if overlay_frame.shape[:2] != (h, w):
            overlay_frame = self.cover_resize(overlay_frame, w, h)

        # Person alpha 0..1 (full body — never cropped by split)
        if person_mask.dtype != np.float32 and person_mask.dtype != np.float64:
            p = person_mask.astype(np.float32)
            if p.max() > 1.5:
                p = p / 255.0
        else:
            p = person_mask.astype(np.float32)
        if p.shape[:2] != (h, w):
            p = cv2.resize(p, (w, h), interpolation=cv2.INTER_LINEAR)
        p = np.clip(p, 0.0, 1.0)

        feather = max(1, self.mask_feather)
        if feather % 2 == 0:
            feather += 1
        if feather > 1:
            p = cv2.GaussianBlur(p, (feather, feather), 0)
            p = np.clip(p, 0.0, 1.0)

        # Top region alpha with soft bottom fade (0 = no overlay, 1 = full)
        top_alpha = self._top_gradient(h, w) * float(np.clip(self.overlay_opacity, 0.0, 1.0))
        # Overlay only where NOT person, in top region
        bg_blend = top_alpha * (1.0 - p)
        bg_blend3 = bg_blend[:, :, None]

        out = frame.astype(np.float32)
        ov = overlay_frame.astype(np.float32)
        out = out * (1.0 - bg_blend3) + ov * bg_blend3

        # Person stays original (already excluded from bg_blend). Optional FX:
        if self.person_shadow and p.max() > 0.01:
            # soft drop under person in top region only
            shadow = cv2.GaussianBlur(p, (21, 21), 0)
            shadow = shadow * top_alpha * 0.25
            out = out * (1.0 - shadow[:, :, None])

        if self.person_outline and p.max() > 0.01:
            edges = cv2.Canny((p * 255).astype(np.uint8), 50, 150)
            edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
            out[edges > 0] = out[edges > 0] * 0.3 + np.array([255, 255, 255], dtype=np.float32) * 0.7

        return np.clip(out, 0, 255).astype(np.uint8)

    def cover_resize(self, image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        """object-fit: cover → center crop."""
        import cv2

        ih, iw = image.shape[:2]
        if ih <= 0 or iw <= 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        scale = max(target_w / iw, target_h / ih)
        nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
        x0 = max(0, (nw - target_w) // 2)
        y0 = max(0, (nh - target_h) // 2)
        return resized[y0 : y0 + target_h, x0 : x0 + target_w]

    # ─── Clip-level apply ───────────────────────────────────────────────────

    async def apply_to_clip(
        self,
        video_path: str,
        segments: list[TopOverlaySegment],
        output_path: str,
        fps: float | None = None,
    ) -> Optional[str]:
        """Bake top-behind overlays into a new mp4; audio stream-copied."""
        if not segments or not os.path.exists(video_path):
            return None
        return await asyncio.to_thread(
            self._apply_sync, video_path, segments, output_path, fps
        )

    def _apply_sync(
        self,
        video_path: str,
        segments: list[TopOverlaySegment],
        output_path: str,
        fps: float | None,
    ) -> Optional[str]:
        import cv2

        segs = sorted(
            [s for s in segments if s.duration > 0.2 and os.path.exists(s.asset_path)],
            key=lambda s: s.at_time,
        )
        if not segs:
            return None

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("top_overlay: cannot open %s", video_path)
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        use_fps = float(fps or src_fps or 30.0)
        if width <= 0 or height <= 0:
            cap.release()
            return None

        try:
            model = self._load_model()
        except Exception as exc:
            cap.release()
            logger.warning("top_overlay: YOLO seg unavailable: %s", exc)
            return None

        # Preload overlay assets (image once / video caps)
        asset_handles: list[tuple[TopOverlaySegment, object, bool]] = []
        for seg in segs:
            is_video = self._is_video(seg.asset_path)
            if is_video:
                oc = cv2.VideoCapture(seg.asset_path)
                if not oc.isOpened():
                    continue
                asset_handles.append((seg, oc, True))
            else:
                img = cv2.imread(seg.asset_path, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                img = self.cover_resize(img, width, height)
                asset_handles.append((seg, img, False))
        if not asset_handles:
            cap.release()
            return None

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        tmp_video = output_path + ".novid.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp_video, fourcc, use_fps, (width, height))
        if not writer.isOpened():
            for _, handle, is_vid in asset_handles:
                if is_vid:
                    handle.release()
            cap.release()
            return None

        last_mask = np.zeros((height, width), dtype=np.float32)
        frame_idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                t = frame_idx / use_fps
                active = self._active_segment(asset_handles, t)
                if active is None:
                    writer.write(frame)
                    frame_idx += 1
                    continue

                seg, handle, is_vid = active
                overlay = self._read_overlay(handle, is_vid, width, height)
                if overlay is None:
                    writer.write(frame)
                    frame_idx += 1
                    continue

                if frame_idx % self.mask_stride == 0 or last_mask.max() < 0.01:
                    last_mask = self._predict_person_mask(model, frame, height, width)

                composite = self.render(frame, last_mask, overlay)
                writer.write(composite)
                frame_idx += 1
        finally:
            writer.release()
            cap.release()
            for _, handle, is_vid in asset_handles:
                if is_vid:
                    handle.release()

        if frame_idx == 0 or not os.path.exists(tmp_video):
            return None

        if not self._mux_audio(video_path, tmp_video, output_path):
            # no audio / mux fail → use video-only
            try:
                os.replace(tmp_video, output_path)
            except OSError:
                return None
        else:
            try:
                os.remove(tmp_video)
            except OSError:
                pass

        logger.info(
            "top_overlay: wrote %s (%d frames, %d segments)",
            output_path,
            frame_idx,
            len(asset_handles),
        )
        return output_path

    # ─── Internals ──────────────────────────────────────────────────────────

    def _top_gradient(self, h: int, w: int) -> np.ndarray:
        key = (h, w)
        cached = self._gradient_cache.get(key)
        if cached is not None:
            return cached

        split = int(round(h * float(np.clip(self.split_ratio, 0.2, 0.8))))
        fade = int(round(h * float(np.clip(self.fade_height, 0.02, 0.4))))
        fade = max(1, fade)
        col = np.zeros(h, dtype=np.float32)
        solid_end = max(0, split - fade)
        col[:solid_end] = 1.0
        if fade > 0 and solid_end < split:
            # smoothstep fade solid → 0 across [solid_end, split]
            n = split - solid_end
            x = np.linspace(0.0, 1.0, n, dtype=np.float32)
            # smoothstep: 1 at start → 0 at end
            s = x * x * (3.0 - 2.0 * x)
            col[solid_end:split] = 1.0 - s
        # below split stays 0
        g = np.broadcast_to(col[:, None], (h, w)).copy()
        self._gradient_cache[key] = g
        return g

    def _load_model(self):
        if self._model is not None:
            return self._model
        from ultralytics import YOLO

        self._model = YOLO(self.model_path)
        return self._model

    def _predict_person_mask(self, model, frame: np.ndarray, h: int, w: int) -> np.ndarray:
        import cv2

        try:
            results = model.predict(
                source=frame,
                classes=[0],
                conf=self.seg_confidence,
                verbose=False,
            )
            result = results[0] if results else None
            if result is None or result.masks is None:
                return np.zeros((h, w), dtype=np.float32)
            masks = result.masks.data.detach().cpu().numpy()
            if masks.size == 0:
                return np.zeros((h, w), dtype=np.float32)
            union = np.max(masks, axis=0).astype(np.float32)
            if union.shape[:2] != (h, w):
                union = cv2.resize(union, (w, h), interpolation=cv2.INTER_LINEAR)
            return np.clip(union, 0.0, 1.0)
        except Exception as exc:
            logger.debug("top_overlay: mask fail: %s", exc)
            return np.zeros((h, w), dtype=np.float32)

    @staticmethod
    def _is_video(path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}

    @staticmethod
    def _active_segment(
        handles: list[tuple[TopOverlaySegment, object, bool]], t: float
    ) -> Optional[tuple[TopOverlaySegment, object, bool]]:
        for item in handles:
            seg = item[0]
            if seg.at_time <= t < seg.at_time + seg.duration:
                return item
        return None

    def _read_overlay(self, handle, is_vid: bool, w: int, h: int) -> Optional[np.ndarray]:
        import cv2

        if not is_vid:
            return handle  # already cover-resized image
        ok, frame = handle.read()
        if not ok:
            # loop overlay video
            handle.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = handle.read()
            if not ok:
                return None
        return self.cover_resize(frame, w, h)

    @staticmethod
    def _mux_audio(src_video: str, video_only: str, output_path: str) -> bool:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_only,
            "-i", src_video,
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return r.returncode == 0 and os.path.exists(output_path)
        except Exception as exc:
            logger.warning("top_overlay: mux failed: %s", exc)
            return False


def _resolve_top_overlay_asset(suggestion) -> tuple[str, str, str] | None:
    """Return (path, format, source) from asset_result and/or splice_segment.

    ClipScout often sets splice_segment only (no asset_result). Legacy path sets
    asset_result. Both must feed top-behind-person overlay.
    """
    path = ""
    fmt = ""
    source = ""
    asset = getattr(suggestion, "asset_result", None)
    if asset and not getattr(asset, "is_fallback", True):
        path = getattr(asset, "local_path", "") or ""
        fmt = (getattr(asset, "asset_format", "") or "").lower()
        source = getattr(asset, "source_api", "") or ""
        if path and os.path.exists(path):
            return path, fmt, source

    seg = getattr(suggestion, "splice_segment", None)
    if seg and getattr(seg, "footage_path", None) and os.path.exists(seg.footage_path):
        return (
            seg.footage_path,
            fmt or "video",
            source or getattr(seg, "platform", "") or "",
        )
    return None


def pick_top_overlay_suggestions(
    suggestions: list,
    max_per_clip: int | None = None,
    blocked_ranges: list[tuple[float, float]] | None = None,
) -> list:
    """Pick BRollSuggestion rows for top-overlay (prefer image; skip AI-text zones).

    Does not mutate suggestions used for full-frame splice. Returns a new list.
    Accepts ClipScout splice-only rows and legacy asset_result rows.
    """
    limit = max_per_clip if max_per_clip is not None else settings.TOP_OVERLAY_MAX_PER_CLIP
    blocked = blocked_ranges or []
    scored = []
    for s in suggestions:
        resolved = _resolve_top_overlay_asset(s)
        if not resolved:
            continue
        path, fmt, source = resolved
        # Prefer stills for behind-person look; video still allowed
        score = 0 if fmt in {"png", "jpg", "jpeg", "webp", "gif", "svg"} else 1
        at = float(getattr(s, "at_time", 0))
        dur = float(getattr(s, "duration", 2.0))
        if any(not (at + dur <= a or at >= b) for a, b in blocked):
            continue
        scored.append((score, at, s, path, source))

    scored.sort(key=lambda x: (x[0], x[1]))
    picked = []
    used: list[tuple[float, float]] = []
    for _, at, s, path, source in scored:
        dur = float(s.duration)
        if any(not (at + dur <= a or at >= b) for a, b in used):
            continue
        used.append((at, at + dur))
        picked.append(
            TopOverlaySegment(
                at_time=at,
                duration=dur,
                asset_path=path,
                keyword=getattr(s, "keyword", "") or "",
                source=source,
            )
        )
        if len(picked) >= limit:
            break
    return picked

