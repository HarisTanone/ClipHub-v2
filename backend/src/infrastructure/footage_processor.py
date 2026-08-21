"""Footage Processor — re-encode and trim footage for B-roll splice.

Processes raw downloaded footage into the exact format needed for video splice:
- Resolution: job aspect (9:16=1080x1920, 16:9=1920x1080, 1:1=1080x1080)
- Codec: H.264, preset fast
- FPS: 30
- Center-crop for non-matching aspect ratios
- Trim to exact required duration
- No audio (video-only output for splice)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


class FootageProcessor:
    """Process raw footage into splice-ready format for any output aspect."""

    async def process(
        self,
        raw_path: str,
        target_duration: float,
        clip_rank: int,
        index: int,
        output_dir: str,
        width: int = 1080,
        height: int = 1920,
        crop_x: Optional[int] = None,
        crop_y: Optional[int] = None,
        layout_mode: Optional[str] = None,
    ) -> Optional[str]:
        """Re-encode and trim footage to target format using AI-aware crop or PiP layout.

        Args:
            raw_path: Path to raw downloaded footage.
            target_duration: Required duration in seconds.
            clip_rank: Clip rank for output filename.
            index: B-roll index within the clip (0-based).
            output_dir: Directory to save processed footage.
            width: Output width (from resolution_for_aspect).
            height: Output height (from resolution_for_aspect).
            crop_x: Optional AI-determined horizontal crop coordinate.
            crop_y: Optional AI-determined vertical crop coordinate.
            layout_mode: Optional placement mode ('behind_person', 'side_broll', 'full_broll').

        Returns:
            Path to processed footage file, or None on failure.
        """
        if not raw_path or not os.path.exists(raw_path):
            logger.warning(f"footage_proc: raw file not found, skipping: {raw_path}")
            return None

        w = max(2, int(width) // 2 * 2)
        h = max(2, int(height) // 2 * 2)

        output_name = f"clip_{clip_rank:02d}_broll_footage_{index:02d}.mp4"
        output_path = os.path.join(output_dir, output_name)
        os.makedirs(output_dir, exist_ok=True)

        if layout_mode == "side_broll":
            # Side B-roll: Preserve 16:9 aspect inside 9:16 frame as floating PiP card
            card_w = int(w * 0.90) // 2 * 2
            card_h = int(card_w * 9 / 16) // 2 * 2
            pad_top = int(h * 0.12)
            vf_filter = (
                f"scale={card_w}:{card_h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:{pad_top}:color=black@0,"
                "setsar=1"
            )
        elif crop_x is not None:
            # AI-Aware smart crop centered on focal subject
            cx = max(0, int(crop_x))
            cy = max(0, int(crop_y or 0))
            vf_filter = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h}:{cx}:{cy},"
                "setsar=1"
            )
        else:
            # Standard center crop fallback
            vf_filter = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},"
                "setsar=1"
            )

        from src.infrastructure.gpu_encoder import get_video_encoder_args
        cmd = [
            "ffmpeg", "-y",
            "-i", raw_path,
            "-t", f"{target_duration:.3f}",
            "-vf", vf_filter,
            *get_video_encoder_args("medium"),
            "-r", "30",
            "-an",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)

            if proc.returncode == 0 and os.path.exists(output_path):
                size_kb = os.path.getsize(output_path) // 1024
                logger.info(
                    f"footage_proc: processed clip_{clip_rank} broll_{index} "
                    f"({target_duration:.1f}s, {w}x{h}, {size_kb}KB) → {output_name}"
                )
                return output_path
            else:
                error_msg = stderr.decode(errors="replace")[-300:] if stderr else "unknown"
                logger.error(f"footage_proc: FFmpeg failed (rc={proc.returncode}): {error_msg}")

        except asyncio.TimeoutError:
            logger.error(f"footage_proc: FFmpeg timed out processing {raw_path}")
        except FileNotFoundError:
            logger.error("footage_proc: FFmpeg not found in PATH")
        except Exception as exc:
            logger.error(f"footage_proc: unexpected error: {exc}")

        if os.path.exists(output_path):
            os.remove(output_path)
        return None
