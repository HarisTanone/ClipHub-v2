"""Top Behind Subject Overlay — portrait top-region B-roll behind person cutout.

Keeps existing full-frame B-roll splice intact. This is additive: only the top
~50% of the frame gets stock footage/image *behind* the YOLO person mask, with
a soft vertical gradient. Bottom stays original. Never coexists with AI text
emphasis on the same time ranges (caller must block).
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from src.config import settings
from src.infrastructure.gpu_encoder import get_video_encoder_args

logger = logging.getLogger(__name__)


@dataclass
class TopOverlaySegment:
    """One timed top-overlay window on a clip timeline (0-based)."""
    at_time: float
    duration: float
    asset_path: str
    keyword: str = ""
    source: str = ""


def fast_guided_filter(
    guide_gray: np.ndarray,
    mask: np.ndarray,
    r: int = 8,
    eps: float = 1e-3,
    subsample: int = 2,
) -> np.ndarray:
    """Fast Guided Filter: snaps low-res YOLO segmentation mask to high-res image edges.

    Refines mask contours around hair, shoulders, clothing, and ears down to subpixel
    accuracy using the image luminance gradient.
    """
    h, w = guide_gray.shape[:2]
    if subsample > 1:
        sw, sh = max(1, w // subsample), max(1, h // subsample)
        small_guide = cv2.resize(guide_gray, (sw, sh), interpolation=cv2.INTER_AREA)
        small_mask = cv2.resize(mask, (sw, sh), interpolation=cv2.INTER_AREA)
        small_r = max(1, r // subsample)
    else:
        small_guide = guide_gray
        small_mask = mask
        small_r = r

    mean_I = cv2.boxFilter(small_guide, cv2.CV_32F, (small_r, small_r))
    mean_p = cv2.boxFilter(small_mask, cv2.CV_32F, (small_r, small_r))
    mean_Ip = cv2.boxFilter(small_guide * small_mask, cv2.CV_32F, (small_r, small_r))
    cov_Ip = mean_Ip - mean_I * mean_p

    mean_II = cv2.boxFilter(small_guide * small_guide, cv2.CV_32F, (small_r, small_r))
    var_I = mean_II - mean_I * mean_I

    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I

    mean_a = cv2.boxFilter(a, cv2.CV_32F, (small_r, small_r))
    mean_b = cv2.boxFilter(b, cv2.CV_32F, (small_r, small_r))

    if subsample > 1:
        mean_a = cv2.resize(mean_a, (w, h), interpolation=cv2.INTER_LINEAR)
        mean_b = cv2.resize(mean_b, (w, h), interpolation=cv2.INTER_LINEAR)

    q = mean_a * guide_gray + mean_b
    return np.clip(q, 0.0, 1.0)


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
        outline_thickness: int | None = None,
        outline_color: tuple[int, int, int] | str | None = None,
        outline_style: str | None = None,
        crop_bias_y: float | None = None,
        speaker_mask_mode: str | None = None,
        smart_crop: bool | None = None,
        smart_crop_conf: float | None = None,
        person_scale: float | None = None,
        person_shift_y: float | None = None,
        person_anchor: str | None = None,
        person_edge_margin: float | None = None,
        bg_black: float | None = None,
        outline_bust_ratio: float | None = None,
        outline_edge_margin: float | None = None,
        model_path: str | None = None,
        det_model_path: str | None = None,
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
        self.mask_stride = 1 if mask_stride is None else max(1, int(mask_stride))

        self.outline_thickness = max(
            1,
            int(
                outline_thickness
                if outline_thickness is not None
                else settings.TOP_OVERLAY_OUTLINE_THICKNESS
            ),
        )
        self.outline_color = self._parse_bgr_color(
            outline_color if outline_color is not None else settings.TOP_OVERLAY_OUTLINE_COLOR
        )
        style = (
            outline_style
            if outline_style is not None
            else getattr(settings, "TOP_OVERLAY_OUTLINE_STYLE", "white")
        )
        self.outline_style = str(style or "white").strip().lower()
        self.crop_bias_y = float(
            np.clip(
                crop_bias_y if crop_bias_y is not None else settings.TOP_OVERLAY_CROP_BIAS_Y,
                0.0,
                1.0,
            )
        )
        mode = (
            speaker_mask_mode
            if speaker_mask_mode is not None
            else getattr(settings, "TOP_OVERLAY_SPEAKER_MASK_MODE", "dual_auto")
        )
        self.speaker_mask_mode = str(mode or "dual_auto").strip().lower()
        self.smart_crop = bool(
            smart_crop
            if smart_crop is not None
            else getattr(settings, "TOP_OVERLAY_SMART_CROP", True)
        )
        self.smart_crop_conf = float(
            smart_crop_conf
            if smart_crop_conf is not None
            else getattr(settings, "TOP_OVERLAY_SMART_CROP_CONF", 0.25)
        )
        self.person_scale = float(
            np.clip(
                person_scale
                if person_scale is not None
                else getattr(settings, "TOP_OVERLAY_PERSON_SCALE", 1.0),
                0.35,
                1.0,
            )
        )
        self.person_shift_y = float(
            np.clip(
                person_shift_y
                if person_shift_y is not None
                else getattr(settings, "TOP_OVERLAY_PERSON_SHIFT_Y", 0.0),
                0.0,
                0.75,
            )
        )
        anchor = (
            person_anchor
            if person_anchor is not None
            else getattr(settings, "TOP_OVERLAY_PERSON_ANCHOR", "natural")
        )
        self.person_anchor = str(anchor or "natural").strip().lower()
        self.person_edge_margin = float(
            np.clip(
                person_edge_margin
                if person_edge_margin is not None
                else getattr(settings, "TOP_OVERLAY_PERSON_EDGE_MARGIN", 0.03),
                0.0,
                0.20,
            )
        )
        self.bg_black = float(
            np.clip(
                bg_black
                if bg_black is not None
                else getattr(settings, "TOP_OVERLAY_BG_BLACK", 0.0),
                0.0,
                1.0,
            )
        )
        self.outline_bust_ratio = float(
            np.clip(
                outline_bust_ratio
                if outline_bust_ratio is not None
                else getattr(settings, "TOP_OVERLAY_OUTLINE_BUST_RATIO", 0.48),
                0.25,
                1.0,
            )
        )
        self.outline_edge_margin = float(
            np.clip(
                outline_edge_margin
                if outline_edge_margin is not None
                else getattr(settings, "TOP_OVERLAY_OUTLINE_EDGE_MARGIN", 0.05),
                0.0,
                0.15,
            )
        )

        self.model_path = model_path or settings.YOLO_SEG_MODEL
        self.det_model_path = det_model_path or settings.YOLO_MODEL_PATH
        self._model = None
        self._det_model = None
        self._gradient_cache: dict[tuple[int, int], np.ndarray] = {}
        self._subject_cache: dict[int, tuple[float, float]] = {}
        self._max_mask_components = 2

        # Temporal smoothing state
        self._prev_clean_mask: np.ndarray | None = None
        self._prev_mask_centroid: tuple[float, float] | None = None

    # ─── Public Frame Compositor ────────────────────────────────────────────

    def render(
        self,
        frame: np.ndarray,
        person_mask: np.ndarray,
        overlay_frame: np.ndarray,
        effective_opacity: float | None = None,
    ) -> np.ndarray:
        """Composite one BGR frame with pristine edge-snapped foreground alpha matting."""
        h, w = frame.shape[:2]
        if overlay_frame.shape[:2] != (h, w):
            overlay_frame = self.cover_resize(overlay_frame, w, h)

        # 1. Normalize and clean mask with subpixel edge-guided matting
        p = self._normalize_person_mask(person_mask, h, w)
        p = self._clean_person_mask(p, guide_frame=frame)

        # 2. Adaptive Motion-Aware Temporal EMA Smoothing
        if (
            self._prev_clean_mask is not None
            and self._prev_clean_mask.shape == p.shape
        ):
            diff = np.abs(p - self._prev_clean_mask)
            alpha_weight = np.where(diff < 0.12, 0.65, 0.15).astype(np.float32)
            p = alpha_weight * self._prev_clean_mask + (1.0 - alpha_weight) * p
            p = np.clip(p, 0.0, 1.0)
        self._prev_clean_mask = p.copy()

        # 3. Layout person (natural 1:1 original crispness)
        frame_f, p, layout = self._layout_person_supporting(frame, p)

        # 4. Top region alpha with smoothstep bottom fade
        opacity = self.overlay_opacity if effective_opacity is None else effective_opacity
        top_alpha = self._top_gradient(h, w) * float(np.clip(opacity, 0.0, 1.0))
        top_alpha3 = top_alpha[:, :, None]

        # 5. Background plate: B-roll in upper region, blending into original frame below
        ov = overlay_frame.astype(np.float32)
        ov_soft = cv2.GaussianBlur(ov, (0, 0), 0.8)
        ov = ov * 0.82 + ov_soft * 0.18

        frame_float = frame_f.astype(np.float32)
        bg_plate = ov * top_alpha3 + frame_float * (1.0 - top_alpha3)

        # Optional soft backdrop grade
        black_a = float(self.bg_black)
        if black_a > 0.01:
            yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
            dim_map = 1.0 - (black_a * 0.15 * np.clip((yy - 0.10) / 0.60, 0.0, 1.0))
            bg_plate = bg_plate * dim_map[:, :, None]

        # 6. Optional contact drop shadow behind person
        if self.person_shadow and p.max() > 0.01:
            shadow = cv2.GaussianBlur(p, (25, 25), 0)
            shadow_intensity = 0.20 * top_alpha
            bg_plate = bg_plate * (1.0 - (shadow * shadow_intensity)[:, :, None])

        # 7. Foreground person composited over background plate
        p3 = p[:, :, None]
        out = frame_float * p3 + bg_plate * (1.0 - p3)

        # 8. Optional stylized bust glow / outline
        if self.person_outline and p.max() > 0.01:
            out = self._draw_person_outline(out, p, top_alpha, layout=layout)

        return np.clip(out, 0, 255).astype(np.uint8)

    def _layout_person_supporting(
        self,
        frame: np.ndarray,
        p: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, dict]:
        """Keep natural 1:1 person always: 100% original sharpness, zero shrink, zero shift."""
        h, w = frame.shape[:2]
        layout = {
            "scale": 1.0,
            "shift_y": 0.0,
            "anchor": "natural",
            "y0": 0,
            "y1": h - 1,
            "x0": 0,
            "x1": w - 1,
            "ph": h,
        }
        ys, xs = np.where(p >= 0.45)
        if len(ys):
            layout.update(
                y0=int(ys.min()),
                y1=int(ys.max()),
                x0=int(xs.min()),
                x1=int(xs.max()),
                ph=int(ys.max() - ys.min() + 1),
            )
        return frame, p, layout

    def cover_resize(
        self,
        image: np.ndarray,
        target_w: int,
        target_h: int,
        subject_xy: tuple[float, float] | None = None,
    ) -> np.ndarray:
        """object-fit: cover; pin subject into TOP visible band (behind-person)."""
        ih, iw = image.shape[:2]
        if ih <= 0 or iw <= 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)

        if target_h > target_w and iw >= ih:
            top_target_h = int(target_h * float(np.clip(self.split_ratio, 0.35, 0.65)))
            scale = max(target_w / iw, top_target_h / ih)
            nw, nh = max(target_w, int(round(iw * scale))), max(1, int(round(ih * scale)))
            resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)

            max_x = max(0, nw - target_w)
            if subject_xy is not None and 0.0 <= float(subject_xy[0]) <= 1.0:
                sx = float(subject_xy[0])
                cx = sx * nw
                x0 = int(np.clip(cx - target_w * 0.5, 0, max_x))
            else:
                x0 = max_x // 2

            out_frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            copy_h = min(nh, target_h)
            out_frame[:copy_h, :target_w] = resized[:copy_h, x0 : x0 + target_w]
            return out_frame

        scale = max(target_w / iw, target_h / ih) * 1.12
        nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
        max_x = max(0, nw - target_w)
        max_y = max(0, nh - target_h)

        x0 = max_x // 2
        y0 = int(round(max_y * float(np.clip(self.crop_bias_y, 0.0, 0.28))))

        if max_x > 0 or max_y > 0:
            cx = cy = None
            if subject_xy is not None:
                try:
                    sx, sy = float(subject_xy[0]), float(subject_xy[1])
                    if 0.0 <= sx <= 1.0 and 0.0 <= sy <= 1.0:
                        cx = sx * nw
                        cy = sy * nh
                except (TypeError, ValueError):
                    cx = cy = None

            if cx is None:
                try:
                    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
                    sh, sw = max(1, nh // 6), max(1, nw // 6)
                    small = cv2.resize(gray, (sw, sh))
                    small = cv2.GaussianBlur(small, (0, 0), 1.0)
                    gx = cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3)
                    gy = cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3)
                    edge = cv2.magnitude(gx, gy)
                    thr = float(np.percentile(edge, 50))
                    weight = np.clip(edge - thr, 0, None) + 0.35
                    thr_b = float(np.percentile(small, 50))
                    weight = weight + 0.45 * np.clip(small.astype(np.float32) - thr_b, 0, None)
                    row_boost = np.linspace(2.4, 0.20, sh, dtype=np.float32)[:, None]
                    weight = weight * row_boost
                    yy, xx = np.mgrid[0:sh, 0:sw]
                    wsum = float(weight.sum()) or 1.0
                    scale_x = nw / float(sw)
                    scale_y = nh / float(sh)
                    cx = float((xx * weight).sum() / wsum) * scale_x
                    cy = float((yy * weight).sum() / wsum) * scale_y
                except Exception:
                    cx = cy = None

            if cx is not None and cy is not None:
                x0 = int(np.clip(cx - target_w * 0.5, 0, max_x))
                band_mid = float(np.clip(self.split_ratio * 0.42, 0.16, 0.28))
                smart_y = int(np.clip(cy - target_h * band_mid, 0, max_y))
                bias_y = int(round(max_y * float(np.clip(self.crop_bias_y, 0.0, 0.22))))
                mix = 0.97 if subject_xy is not None else 0.92
                y0 = int(round(mix * smart_y + (1.0 - mix) * bias_y))
                if subject_xy is None:
                    y0 = min(y0, int(max_y * 0.35))
                y0 = int(np.clip(y0, 0, max_y))

        return resized[y0 : y0 + target_h, x0 : x0 + target_w]

    # ─── Clip-Level Pipeline ────────────────────────────────────────────────

    async def apply_to_clip(
        self,
        video_path: str,
        segments: list[TopOverlaySegment],
        output_path: str,
        fps: float | None = None,
    ) -> Optional[str]:
        """Bake top-behind overlays into video with lossless audio stream copy and HD pipeline."""
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
        asset_handles: list[tuple[TopOverlaySegment, object, bool, int]] = []
        for i, seg in enumerate(segs):
            is_video = self._is_video(seg.asset_path)
            if is_video:
                oc = cv2.VideoCapture(seg.asset_path)
                if not oc.isOpened():
                    continue
                asset_handles.append((seg, oc, True, i))
            else:
                img = cv2.imread(seg.asset_path, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                subject = self._detect_subject_xy(img) if self.smart_crop else None
                if subject is not None:
                    self._subject_cache[i] = subject
                img = self.cover_resize(img, width, height, subject_xy=subject)
                asset_handles.append((seg, img, False, i))
        if not asset_handles:
            cap.release()
            return None

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        encoder_args = get_video_encoder_args("medium")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "bgr24",
            "-r", f"{use_fps:.4f}",
            "-i", "-",
            "-i", video_path,
            "-map", "0:v:0",
            "-map", "1:a:0?",
            *encoder_args,
            "-c:a", "copy",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]

        pipe = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

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
                    pipe.stdin.write(frame.tobytes())
                    frame_idx += 1
                    self._prev_clean_mask = None
                    continue

                seg, handle, is_vid, asset_id = active
                overlay = self._read_overlay(handle, is_vid, width, height, asset_id=asset_id)
                if overlay is None:
                    pipe.stdin.write(frame.tobytes())
                    frame_idx += 1
                    continue

                fade_dur = min(0.35, seg.duration / 3.0)
                t_in = min(1.0, max(0.0, (t - seg.at_time) / max(0.01, fade_dur)))
                t_out = min(1.0, max(0.0, (seg.at_time + seg.duration - t) / max(0.01, fade_dur)))
                raw_time_alpha = min(t_in, t_out)
                smooth_time_alpha = raw_time_alpha * raw_time_alpha * (3.0 - 2.0 * raw_time_alpha)

                if frame_idx % self.mask_stride == 0 or last_mask.max() < 0.01:
                    last_mask = self._predict_person_mask(model, frame, height, width)

                composite = self.render(
                    frame=frame,
                    person_mask=last_mask,
                    overlay_frame=overlay,
                    effective_opacity=self.overlay_opacity * smooth_time_alpha,
                )

                pipe.stdin.write(composite.tobytes())
                frame_idx += 1

        finally:
            cap.release()
            for _, handle, is_vid, _ in asset_handles:
                if is_vid:
                    handle.release()
            try:
                _, stderr = pipe.communicate()
            except ValueError:
                # If stdin was already closed, wait for process completion
                pipe.wait()
                stderr = pipe.stderr.read() if pipe.stderr else b""

        if pipe.returncode != 0:
            err_msg = stderr.decode(errors="ignore")[-400:] if stderr else "unknown"
            logger.error(f"top_overlay: FFmpeg pipe failed: {err_msg}")
            return None

        if frame_idx == 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return None

        logger.info(
            "top_overlay: wrote %s (%d frames, %d segments, 100%% HD pipe)",
            output_path,
            frame_idx,
            len(asset_handles),
        )
        return output_path

    # ─── Mask Processing & Guided Matting ────────────────────────────────────

    @staticmethod
    def _parse_bgr_color(value: tuple[int, int, int] | str | None) -> tuple[int, int, int]:
        """Parse 'R,G,B' or 'B,G,R' string / tuple into BGR for OpenCV draw."""
        if isinstance(value, (tuple, list)) and len(value) == 3:
            r, g, b = (int(value[0]), int(value[1]), int(value[2]))
            return (b, g, r)
        text = str(value or "255,255,255").strip()
        parts = [p.strip() for p in text.replace(" ", ",").split(",") if p.strip()]
        if len(parts) != 3:
            return (255, 255, 255)
        try:
            r, g, b = (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
        except ValueError:
            return (255, 255, 255)
        return (
            int(np.clip(b, 0, 255)),
            int(np.clip(g, 0, 255)),
            int(np.clip(r, 0, 255)),
        )

    def _normalize_person_mask(self, person_mask: np.ndarray, h: int, w: int) -> np.ndarray:
        if person_mask.dtype != np.float32 and person_mask.dtype != np.float64:
            p = person_mask.astype(np.float32)
            if p.max() > 1.5:
                p = p / 255.0
        else:
            p = person_mask.astype(np.float32)
        if p.shape[:2] != (h, w):
            p = cv2.resize(p, (w, h), interpolation=cv2.INTER_LINEAR)
        return np.clip(p, 0.0, 1.0)

    def _clean_person_mask(self, p: np.ndarray, guide_frame: np.ndarray | None = None) -> np.ndarray:
        """High-precision anti-aliased matte with Fast Guided Matting edge snap."""
        if p.max() < 0.01:
            return p

        h, w = p.shape[:2]
        binary = (p >= 0.40).astype(np.uint8) * 255

        # 1. Connected components
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        if n > 1:
            areas = stats[1:, cv2.CC_STAT_AREA]
            order = np.argsort(areas)[::-1]
            keep_n = max(1, min(int(self._max_mask_components), len(order)))
            if keep_n >= 2 and len(order) >= 2:
                a0 = float(areas[order[0]])
                a1 = float(areas[order[1]])
                if a0 <= 0 or a1 / a0 < 0.25:
                    keep_n = 1
            keep_labels = {1 + int(order[i]) for i in range(keep_n)}
            binary = np.where(np.isin(labels, list(keep_labels)), 255, 0).astype(np.uint8)

        # 2. Fill internal holes
        flood = binary.copy()
        ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        cv2.floodFill(flood, ff_mask, (0, 0), 128)
        holes = (flood != 128) & (binary == 0)
        binary[holes] = 255

        # 3. Morphological close
        k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k3, iterations=1)

        float_mask = (binary >= 128).astype(np.float32)

        # 4. Fast Guided Filter
        if guide_frame is not None and guide_frame.shape[:2] == (h, w):
            gray = cv2.cvtColor(guide_frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            float_mask = fast_guided_filter(gray, float_mask, r=6, eps=1e-3, subsample=2)
        else:
            float_mask = cv2.GaussianBlur(float_mask, (5, 5), 0)

        return np.clip(float_mask, 0.0, 1.0)

    def _draw_person_outline(
        self,
        out: np.ndarray,
        p: np.ndarray,
        top_alpha: np.ndarray,
        layout: dict | None = None,
    ) -> np.ndarray:
        """Organic bust glow — head → neck → shoulder only."""
        binary = (p >= 0.50).astype(np.uint8) * 255
        if binary.max() == 0:
            return out

        h, w = out.shape[:2]
        style = self.outline_style if self.outline_style in {
            "white", "neon", "black", "gradient", "comic",
        } else "white"

        ys, xs = np.where(binary > 0)
        if len(ys) == 0:
            return out
        py0, py1 = int(ys.min()), int(ys.max())
        if layout:
            py0 = int(layout.get("y0", py0))
            py1 = int(layout.get("y1", py1))
        ph = max(1, py1 - py0 + 1)
        bust_h = max(8, int(round(ph * float(self.outline_bust_ratio))))
        bust_y1 = min(h - 1, py0 + bust_h)

        row = np.arange(h, dtype=np.float32)
        mid = py0 + bust_h * 0.55
        end_y = float(bust_y1)
        bust_w = np.ones(h, dtype=np.float32)
        bust_w[row > end_y] = 0.0
        zone = (row >= mid) & (row <= end_y)
        if zone.any() and end_y > mid:
            t = (row[zone] - mid) / max(1.0, end_y - mid)
            bust_w[zone] = 1.0 - (t * t * (3.0 - 2.0 * t))
        bust_w = bust_w[:, None]

        m = float(self.outline_edge_margin)
        mx = max(2, int(round(w * m)))
        my_bot = max(2, int(round(h * max(m, 0.06))))
        edge_kill = np.ones((h, w), dtype=np.float32)
        edge_kill[:, :mx] = 0.0
        edge_kill[:, w - mx :] = 0.0
        edge_kill[h - my_bot :, :] = 0.0
        if mx > 2:
            for i in range(mx):
                a = i / float(mx)
                edge_kill[:, i] = np.minimum(edge_kill[:, i], a)
                edge_kill[:, w - 1 - i] = np.minimum(edge_kill[:, w - 1 - i], a)

        bust_bin = binary.copy()
        bust_bin[int(end_y) + 1 :, :] = 0
        fade_rows = max(4, bust_h // 5)
        for i in range(fade_rows):
            y = int(end_y) - fade_rows + i + 1
            if 0 <= y < h:
                bust_bin[y, :] = (
                    bust_bin[y, :].astype(np.float32) * (1.0 - (i + 1) / fade_rows)
                ).astype(np.uint8)
        if bust_bin.max() == 0:
            return out

        k_org = max(3, int(round(min(h, w) * 0.010)))
        if k_org % 2 == 0:
            k_org += 1
        k_ell = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_org, k_org))
        bust_bin = cv2.morphologyEx(bust_bin, cv2.MORPH_CLOSE, k_ell, iterations=1)
        bust_bin = cv2.GaussianBlur(bust_bin, (k_org, k_org), 0)
        bust_bin = (bust_bin >= 80).astype(np.uint8) * 255
        if bust_bin.max() == 0:
            return out

        scale = max(1.0, min(h, w) / 720.0)
        th = max(5, int(round(int(self.outline_thickness) * scale * 0.85)))
        if style == "comic":
            th = max(4, int(round(th * 0.75)))
        pad = max(3, th // 2 + 1)
        k_pad = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pad | 1, pad | 1))
        edge_src = cv2.dilate(bust_bin, k_pad, iterations=1)
        contours, _ = cv2.findContours(edge_src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return out

        good = []
        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < 40:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            if bw > w * 0.90 and bh > h * 0.50:
                continue
            if len(cnt) >= 10:
                pts = cnt.reshape(-1, 2).astype(np.float32)
                k = min(7, max(3, len(pts) // 16))
                if k % 2 == 0:
                    k += 1
                pad_n = k // 2
                ext = np.concatenate([pts[-pad_n:], pts, pts[:pad_n]], axis=0)
                ker = np.ones(k, dtype=np.float32) / float(k)
                sx = np.convolve(ext[:, 0], ker, mode="valid")
                sy = np.convolve(ext[:, 1], ker, mode="valid")
                n = min(len(sx), len(sy), len(pts))
                smooth = np.stack([sx[:n], sy[:n]], axis=1).astype(np.int32).reshape(-1, 1, 2)
                good.append(smooth)
            else:
                good.append(cnt)
        if not good:
            return out
        contours = good

        region = np.clip(np.maximum(top_alpha, 0.55), 0.0, 1.0) * bust_w * edge_kill
        hard = np.zeros(out.shape[:2], dtype=np.uint8)
        line_type = cv2.LINE_AA

        if style == "comic":
            for cnt in contours:
                pts = cnt.reshape(-1, 2)
                if len(pts) < 4:
                    cv2.drawContours(hard, [cnt], -1, 255, thickness=th, lineType=line_type)
                    continue
                step = max(4, len(pts) // 16)
                dash = max(2, step // 2)
                for i in range(0, len(pts), step):
                    a = pts[i : i + dash]
                    if len(a) >= 2:
                        cv2.polylines(hard, [a], False, 255, thickness=th, lineType=line_type)
        else:
            cv2.drawContours(hard, contours, -1, 255, thickness=th, lineType=line_type)
            outer = cv2.dilate(hard, k_pad, iterations=1)
            hard = cv2.max(hard, outer)

        hard[:, :mx] = 0
        hard[:, w - mx :] = 0
        hard[h - my_bot :, :] = 0
        hard[int(end_y) + 1 :, :] = 0

        near = max(mx + 2, int(round(w * 0.08)))
        bust_rows = slice(max(0, py0 - 2), min(h, int(end_y) + 1))
        band_h = max(1, int(end_y) - py0 + 1)
        thr_col = 255.0 * band_h * 0.70
        col_sum = hard[bust_rows, :].sum(axis=0).astype(np.float32)
        for c in np.where(col_sum > thr_col)[0]:
            if int(c) < near or int(c) >= w - near:
                hard[bust_rows, int(c)] = 0

        thr_row = 255.0 * w * 0.70
        row_sum = hard.sum(axis=1).astype(np.float32)
        for r in range(max(0, int(end_y) - 4), min(h, int(end_y) + 2)):
            if row_sum[r] > thr_row:
                hard[r, :] = 0

        glow_sigma = max(1.5, th * 0.45)
        if style == "neon":
            glow_sigma = max(2.2, th * 0.90)
        glow = cv2.GaussianBlur(hard, (0, 0), sigmaX=glow_sigma)

        interior = cv2.erode(binary, k_pad, iterations=max(2, pad // 2)).astype(np.float32) / 255.0
        glow_w = 0.65
        if style == "neon":
            glow_w = 1.20
        elif style == "black":
            glow_w = 0.25
        elif style == "comic":
            glow_w = 0.15
        stroke = np.clip(
            hard.astype(np.float32) / 255.0
            + glow.astype(np.float32) / 255.0 * glow_w,
            0.0,
            1.0,
        )
        stroke = stroke * region * (1.0 - interior)
        stroke = np.where(stroke >= 0.28, 1.0, stroke * 0.35)
        stroke = np.clip(stroke, 0.0, 1.0)

        if style == "black":
            color = np.array((0.0, 0.0, 0.0), dtype=np.float32)
        elif style == "neon":
            color = np.array((255.0, 180.0, 40.0), dtype=np.float32)
        elif style == "gradient":
            yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
            c_top = np.array((40.0, 200.0, 255.0), dtype=np.float32)
            c_bot = np.array((255.0, 120.0, 40.0), dtype=np.float32)
            color_map = (
                c_top[None, None, :] * (1.0 - yy[:, :, None])
                + c_bot[None, None, :] * yy[:, :, None]
            )
            stroke3 = stroke[:, :, None]
            return out * (1.0 - stroke3) + color_map * stroke3
        else:
            color = np.array(self.outline_color, dtype=np.float32)

        stroke3 = stroke[:, :, None]
        painted = out * (1.0 - stroke3) + color[None, None, :] * stroke3
        if style in {"white", "gradient"}:
            inner = cv2.erode(hard, k_pad, iterations=1)
            inner_edge = cv2.subtract(hard, inner).astype(np.float32) / 255.0
            inner_edge = inner_edge * region * (1.0 - interior) * 0.55
            black = np.array((8.0, 8.0, 8.0), dtype=np.float32)
            painted = (
                painted * (1.0 - inner_edge[:, :, None])
                + black[None, None, :] * inner_edge[:, :, None]
            )
        if style == "neon":
            bloom = cv2.GaussianBlur(hard, (0, 0), sigmaX=max(3.0, th * 1.4)).astype(np.float32) / 255.0
            bloom = bloom * region * (1.0 - interior) * 0.50
            painted = painted * (1.0 - bloom[:, :, None]) + color[None, None, :] * bloom[:, :, None]
        elif style == "white":
            blue = np.array((255.0, 140.0, 30.0), dtype=np.float32)
            bloom = cv2.GaussianBlur(hard, (0, 0), sigmaX=max(3.5, th * 1.5)).astype(np.float32) / 255.0
            bloom = bloom * region * (1.0 - interior) * 0.42
            painted = painted * (1.0 - bloom[:, :, None]) + blue[None, None, :] * bloom[:, :, None]
        return painted

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
            n = split - solid_end
            x = np.linspace(0.0, 1.0, n, dtype=np.float32)
            s = x * x * (3.0 - 2.0 * x)
            col[solid_end:split] = 1.0 - s
        g = np.broadcast_to(col[:, None], (h, w)).copy()
        self._gradient_cache[key] = g
        return g

    def _load_model(self):
        if self._model is not None:
            return self._model
        from ultralytics import YOLO

        self._model = YOLO(self.model_path)
        return self._model

    def _load_det_model(self):
        if self._det_model is not None:
            return self._det_model
        from ultralytics import YOLO

        self._det_model = YOLO(self.det_model_path)
        return self._det_model

    def _detect_subject_xy(self, image: np.ndarray) -> tuple[float, float] | None:
        """YOLO det on B-roll frame → subject center (normalized 0..1)."""
        if image is None or image.size == 0:
            return None
        try:
            model = self._load_det_model()
            results = model.predict(
                source=image,
                conf=self.smart_crop_conf,
                verbose=False,
            )
            result = results[0] if results else None
            if result is None or result.boxes is None or len(result.boxes) == 0:
                return None
            boxes = result.boxes
            xyxy = boxes.xyxy.detach().cpu().numpy()
            confs = boxes.conf.detach().cpu().numpy()
            clss = boxes.cls.detach().cpu().numpy().astype(int)
            ih, iw = image.shape[:2]
            best = None
            for box, conf, cls_id in zip(xyxy, confs, clss):
                if int(cls_id) == 0:
                    continue
                x1, y1, x2, y2 = map(float, box)
                bw = max(1.0, x2 - x1)
                bh = max(1.0, y2 - y1)
                area = bw * bh
                cy = (y1 + y2) * 0.5
                upper_bonus = 1.25 if cy < ih * 0.70 else 0.85
                score = float(conf) * area * upper_bonus
                cx = (x1 + x2) * 0.5 / max(1.0, float(iw))
                cyn = cy / max(1.0, float(ih))
                if best is None or score > best[0]:
                    best = (score, float(np.clip(cx, 0.0, 1.0)), float(np.clip(cyn, 0.0, 1.0)))
            if best is None:
                return None
            return (best[1], best[2])
        except Exception as exc:
            logger.debug("top_overlay: subject detect fail: %s", exc)
            return None

    def _predict_person_mask(self, model, frame: np.ndarray, h: int, w: int) -> np.ndarray:
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

            resized = []
            for m in masks:
                mm = m.astype(np.float32)
                if mm.shape[:2] != (h, w):
                    mm = cv2.resize(mm, (w, h), interpolation=cv2.INTER_LINEAR)
                resized.append(np.clip(mm, 0.0, 1.0))

            if not resized:
                return np.zeros((h, w), dtype=np.float32)

            combined = np.zeros((h, w), dtype=np.float32)
            areas = [float(m.sum()) for m in resized]
            max_area = max(areas) if areas else 0.0

            for i, m in enumerate(resized):
                if areas[i] >= max_area * 0.15:
                    combined = np.maximum(combined, m)

            return np.clip(combined, 0.0, 1.0)

        except Exception as exc:
            logger.debug("top_overlay: mask fail: %s", exc)
            return np.zeros((h, w), dtype=np.float32)

    @staticmethod
    def _is_video(path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}

    @staticmethod
    def _active_segment(
        handles: list, t: float
    ) -> Optional[tuple]:
        for item in handles:
            seg = item[0]
            if seg.at_time <= t < seg.at_time + seg.duration:
                return item
        return None

    def _read_overlay(
        self, handle, is_vid: bool, w: int, h: int, asset_id: int = 0
    ) -> Optional[np.ndarray]:
        if not is_vid:
            return handle
        ok, frame = handle.read()
        if not ok:
            handle.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = handle.read()
            if not ok:
                return None
        subject = None
        if self.smart_crop:
            subject = self._subject_cache.get(asset_id)
            if subject is None:
                subject = self._detect_subject_xy(frame)
                if subject is not None:
                    self._subject_cache[asset_id] = subject
        return self.cover_resize(frame, w, h, subject_xy=subject)


def _placement_of(suggestion) -> str:
    val = getattr(suggestion, "placement", None)
    if hasattr(val, "value"):
        val = val.value
    return str(val or "").strip().lower()


def _is_still_asset(suggestion) -> bool:
    asset = getattr(suggestion, "asset_result", None)
    if asset and not getattr(asset, "is_fallback", True):
        fmt = (getattr(asset, "asset_format", "") or "").lower()
        if fmt in {"image", "photo", "png", "jpg", "jpeg", "svg", "gif"}:
            return True
    return False


def snap_overlay_to_phrase(
    at_time: float,
    duration: float,
    words: list[dict] | None,
    clip_duration: float = 0.0,
    min_dur: float = 2.5,
    max_dur: float = 3.2,
) -> tuple[float, float]:
    """Snap behind-person window to nearby word/phrase bounds when available."""
    at = max(0.0, float(at_time or 0.0))
    dur = float(np.clip(float(duration or 2.8), min_dur, max_dur))
    if not words:
        if clip_duration > 0:
            dur = min(dur, max(0.4, clip_duration - at))
        return round(at, 3), round(max(0.4, dur), 3)

    starts = []
    for w in words:
        try:
            ws = float(w.get("start", 0))
            we = float(w.get("end", ws + 0.2))
        except (TypeError, ValueError):
            continue
        starts.append((ws, we, str(w.get("word") or "")))
    if not starts:
        return round(at, 3), round(dur, 3)

    best = min(starts, key=lambda t: abs(t[0] - at))
    if abs(best[0] - at) > 0.8:
        if clip_duration > 0:
            dur = min(dur, max(0.4, clip_duration - at))
        return round(at, 3), round(max(min_dur, min(max_dur, dur)), 3)

    phrase_start = best[0]
    phrase_end = best[1]
    for ws, we, _ in starts:
        if ws < phrase_start - 0.05:
            continue
        if ws <= phrase_end + 0.35 and (ws - phrase_start) <= max_dur:
            phrase_end = max(phrase_end, we)
        if phrase_end - phrase_start >= max_dur:
            break
    phrase_start = max(0.0, phrase_start - 0.05)
    phrase_end = phrase_end + 0.12
    new_dur = float(np.clip(phrase_end - phrase_start, min_dur, max_dur))
    if clip_duration > 0:
        new_dur = min(new_dur, max(0.4, clip_duration - phrase_start))
    return round(phrase_start, 3), round(max(0.4, new_dur), 3)


def pick_top_overlay_suggestions(
    suggestions: list,
    max_per_clip: int | None = None,
    blocked_ranges: list[tuple[float, float]] | None = None,
    words: list[dict] | None = None,
    clip_duration: float = 0.0,
) -> list[TopOverlaySegment]:
    """Pick BRollSuggestion rows for top-behind-person."""
    limit = max(1, max_per_clip) if max_per_clip is not None else 3
    blocked = list(blocked_ranges or [])
    words = words or []
    scored = []

    for s in suggestions:
        placement = _placement_of(s)
        if placement == "full_frame":
            continue

        res = _resolve_top_overlay_asset(s)
        if res is None:
            continue
        path, fmt, source = res

        is_still = _is_still_asset(s)
        score = 0
        if placement != "behind_person":
            score += 3
        if is_still:
            score += 1
        cat = getattr(s, "visual_category", None)
        cat_val = cat.value if hasattr(cat, "value") else str(cat or "")
        if cat_val in {"icon", "motion_graphic"}:
            score += 2
        at = float(getattr(s, "at_time", 0))
        dur = float(getattr(s, "duration", 2.0))
        at, dur = snap_overlay_to_phrase(at, dur, words, clip_duration=clip_duration)
        if any(not (at + dur <= a or at >= b) for a, b in blocked):
            continue
        scored.append((score, at, dur, s, path, source))

    scored.sort(key=lambda x: (x[0], x[1]))
    picked = []
    used: list[tuple[float, float]] = []
    for _, at, dur, s, path, source in scored:
        if any(not (at + dur <= a or at >= b) for a, b in used):
            continue
        if any(not (at + dur <= a or at >= b) for a, b in blocked):
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


def pick_full_frame_suggestions(suggestions: list) -> list:
    """Suggestions that should timeline-splice (person replaced by stock video)."""
    out = []
    for s in suggestions:
        placement = _placement_of(s)
        if placement == "behind_person":
            continue
        has_splice = bool(
            getattr(s, "splice_segment", None)
            and getattr(getattr(s, "splice_segment", None), "footage_path", None)
        )
        asset = getattr(s, "asset_result", None)
        is_video_asset = bool(
            asset
            and not getattr(asset, "is_fallback", True)
            and (getattr(asset, "asset_format", "") or "").lower() == "video"
            and getattr(asset, "local_path", None)
        )
        if placement == "full_frame" or has_splice or is_video_asset:
            out.append(s)
        elif placement == "" and has_splice:
            out.append(s)
    return out


def _resolve_top_overlay_asset(suggestion) -> tuple[str, str, str] | None:
    """Return (path, format, source) from asset_result and/or splice_segment."""
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
            getattr(seg, "platform", None) or getattr(seg, "source", "") or source or "splice",
        )
    return None
