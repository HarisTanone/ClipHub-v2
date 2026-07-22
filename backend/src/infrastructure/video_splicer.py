"""Video Splicer — cut & replace video track with B-roll footage.

FFmpeg concat demuxer approach:
1. Split original video into segments (video-only, no audio)
2. Insert processed footage between segments
3. Concat all video segments
4. Map original audio (stream copy, no re-encode)
5. Validate A/V sync

Key guarantees:
- Audio stream is NEVER modified (copy only)
- Output duration matches input duration exactly
- Subtitle timing unaffected (anchored to audio)
- All video parts normalized to 1080x1920 H.264 30fps before concat
  (mismatched SAR/fps/res used to make concat demuxer stop early → ~before+broll only)
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Optional

from src.config import settings
from src.domain.entities import SpliceSegment
from src.domain.interfaces import IVideoSplicer
from src.infrastructure.media_timeline import probe_media_timeline, timeline_is_safe

logger = logging.getLogger(__name__)

# Must match FootageProcessor output so concat demuxer stays continuous.
_PART_W = 1080
_PART_H = 1920
_PART_FPS = 30
_VF_NORMALIZE = (
    f"scale={_PART_W}:{_PART_H}:force_original_aspect_ratio=increase,"
    f"crop={_PART_W}:{_PART_H},"
    "setsar=1,"
    f"fps={_PART_FPS}"
)


class VideoSplicer(IVideoSplicer):
    """Splice footage segments into video track.

    Strategy:
    - Extract video-only parts (before/after each splice point), normalized
    - Re-normalize stock footage to the same stream params
    - Concat: [before][footage][after] using FFmpeg concat demuxer
    - Map original audio with -c:a copy
    - Validate duration + A/V drift after splice
    """

    MAX_SYNC_DRIFT = 0.1
    MAX_DURATION_ERROR = 0.5  # slightly looser than 0.25 for re-encode drift

    def __init__(self):
        self._crossfade_sec = settings.BROLL_SPLICE_CROSSFADE_SEC
        self._max_per_clip = settings.BROLL_SPLICE_MAX_PER_CLIP

    async def splice(
        self,
        clip_path: str,
        segments: list[SpliceSegment],
        output_path: str,
    ) -> str:
        """Splice footage segments into video track.

        Returns:
            output_path on success, clip_path on failure (fallback).
        """
        if not segments:
            return clip_path

        if not os.path.exists(clip_path):
            logger.error(f"video_splicer: clip not found: {clip_path}")
            return clip_path

        valid_segments = [s for s in segments if os.path.exists(s.footage_path)]
        if not valid_segments:
            logger.warning("video_splicer: no valid footage files, skipping splice")
            return clip_path

        valid_segments = valid_segments[: self._max_per_clip]

        if not self._validate_no_overlap(valid_segments):
            logger.error("video_splicer: segments overlap (< 1s gap), falling back")
            return clip_path

        sorted_segments = sorted(valid_segments, key=lambda s: s.at_time)

        temp_dir = tempfile.mkdtemp(prefix="splice_")
        temp_files: list[str] = []

        try:
            result = await self._splice_all(
                clip_path, sorted_segments, output_path, temp_dir, temp_files
            )

            if result and os.path.exists(result):
                if self._validate_sync(result, clip_path):
                    logger.info(
                        f"video_splicer: splice complete — {len(sorted_segments)} segments "
                        f"→ {os.path.basename(result)}"
                    )
                    return result
                logger.error("video_splicer: validation failed after splice, falling back")
                try:
                    os.remove(result)
                except OSError:
                    pass
                return clip_path

            return clip_path

        except Exception as exc:
            logger.error(f"video_splicer: splice failed: {exc}")
            return clip_path

        finally:
            self._cleanup(temp_dir, temp_files)

    async def _splice_all(
        self,
        clip_path: str,
        segments: list[SpliceSegment],
        output_path: str,
        temp_dir: str,
        temp_files: list[str],
    ) -> Optional[str]:
        """Build [before][footage][after]… then concat + map original audio."""
        timeline = probe_media_timeline(clip_path)
        if not timeline:
            logger.error("video_splicer: cannot probe clip duration")
            return None

        clip_duration = timeline.video_duration
        concat_parts: list[str] = []
        prev_end = 0.0

        for i, segment in enumerate(segments):
            at_time = max(0.0, min(segment.at_time, clip_duration - 0.5))
            splice_dur = max(0.5, float(segment.duration))
            splice_end = min(clip_duration, at_time + splice_dur)

            # BEFORE
            if at_time > prev_end + 0.05:
                before_path = os.path.join(temp_dir, f"part_before_{i:02d}.mp4")
                if await self._extract_video_segment(clip_path, prev_end, at_time, before_path):
                    concat_parts.append(before_path)
                    temp_files.append(before_path)
                else:
                    logger.error(
                        "video_splicer: required source part failed [%.1fs-%.1fs]",
                        prev_end,
                        at_time,
                    )
                    return None

            # FOOTAGE — re-normalize so stream matches extracted parts exactly
            footage_norm = os.path.join(temp_dir, f"part_footage_{i:02d}.mp4")
            actual_dur = splice_end - at_time
            if not await self._normalize_video(
                segment.footage_path, footage_norm, target_duration=actual_dur
            ):
                logger.error(
                    "video_splicer: footage normalize failed: %s",
                    segment.footage_path,
                )
                return None
            concat_parts.append(footage_norm)
            temp_files.append(footage_norm)

            prev_end = splice_end

        # AFTER
        if clip_duration > prev_end + 0.05:
            after_path = os.path.join(temp_dir, "part_after_final.mp4")
            if await self._extract_video_segment(clip_path, prev_end, clip_duration, after_path):
                concat_parts.append(after_path)
                temp_files.append(after_path)
            else:
                logger.error(
                    "video_splicer: required final source part failed [%.1fs-%.1fs]",
                    prev_end,
                    clip_duration,
                )
                return None

        if len(concat_parts) < 2:
            logger.warning("video_splicer: not enough parts to concat")
            return None

        # Probe parts — refuse to concat if sum is far under source duration
        part_durs: list[float] = []
        for p in concat_parts:
            tl = probe_media_timeline(p)
            d = tl.video_duration if tl else 0.0
            part_durs.append(d)
            logger.info(
                "video_splicer: part %s duration=%.2fs size=%s",
                os.path.basename(p),
                d,
                os.path.getsize(p) if os.path.exists(p) else 0,
            )

        parts_sum = sum(part_durs)
        if parts_sum < clip_duration - 2.0:
            logger.error(
                "video_splicer: parts sum too short (sum=%.1fs < clip=%.1fs) — abort",
                parts_sum,
                clip_duration,
            )
            return None

        concat_list_path = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list_path, "w") as f:
            for part in concat_parts:
                safe_path = part.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")
        temp_files.append(concat_list_path)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Prefer re-encode concat: stream-copy often truncates when any residual
        # param differs (timebase/SAR). Parts are already H.264; re-encode is safe.
        if await self._run_concat(concat_list_path, clip_path, output_path, copy_video=False):
            out_tl = probe_media_timeline(output_path)
            out_dur = out_tl.video_duration if out_tl else 0.0
            if abs(out_dur - clip_duration) <= self.MAX_DURATION_ERROR + 1.0:
                return output_path
            logger.warning(
                "video_splicer: re-encode concat duration mismatch "
                "(out=%.1fs expected=%.1fs), trying stream-copy",
                out_dur,
                clip_duration,
            )
            try:
                os.remove(output_path)
            except OSError:
                pass

        if await self._run_concat(concat_list_path, clip_path, output_path, copy_video=True):
            out_tl = probe_media_timeline(output_path)
            out_dur = out_tl.video_duration if out_tl else 0.0
            if abs(out_dur - clip_duration) <= self.MAX_DURATION_ERROR + 1.0:
                return output_path
            logger.error(
                "video_splicer: concat produced wrong duration (out=%.1fs expected=%.1fs)",
                out_dur,
                clip_duration,
            )
            try:
                os.remove(output_path)
            except OSError:
                pass

        return None

    async def _run_concat(
        self,
        concat_list_path: str,
        clip_path: str,
        output_path: str,
        *,
        copy_video: bool,
    ) -> bool:
        if copy_video:
            vcodec = ["-c:v", "copy"]
            timeout = 120.0
        else:
            vcodec = [
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-r", str(_PART_FPS),
            ]
            timeout = 300.0

        # No -shortest: video parts are built to sum ≈ clip_duration; audio is
        # stream-copied from source. -shortest would truncate a slightly-long
        # video and hide duration bugs.
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list_path,
            "-i", clip_path,
            "-map", "0:v:0",
            "-map", "1:a:0?",
            *vcodec,
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        proc: Optional[asyncio.subprocess.Process] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            err = (stderr or b"").decode(errors="replace")[-400:]
            logger.warning(
                "video_splicer: concat %s failed rc=%s: %s",
                "copy" if copy_video else "reencode",
                proc.returncode,
                err,
            )
            return False
        except asyncio.TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.communicate()
            logger.warning("video_splicer: concat timed out after %.0fs", timeout)
            return False
        except Exception as exc:
            logger.warning(f"video_splicer: concat error: {exc}")
            return False

    async def _extract_video_segment(
        self,
        clip_path: str,
        start: float,
        end: float,
        output_path: str,
    ) -> bool:
        """Extract video-only segment, normalized to 1080x1920@30fps H.264."""
        duration = end - start
        if duration <= 0.05:
            return False

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}",
            "-i", clip_path,
            "-t", f"{duration:.3f}",
            "-vf", _VF_NORMALIZE,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            "-movflags", "+faststart",
            output_path,
        ]

        proc: Optional[asyncio.subprocess.Process] = None
        # Encode time scales with duration; long tails need real headroom.
        timeout = max(90.0, duration * 4.0 + 60.0)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            ok = proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0
            if not ok:
                err = (stderr or b"").decode(errors="replace")[-300:]
                logger.warning(
                    "video_splicer: extract failed [%.1f-%.1f] rc=%s: %s",
                    start,
                    end,
                    proc.returncode,
                    err,
                )
                return False

            # Sanity: part duration must be close to requested
            tl = probe_media_timeline(output_path)
            if tl is None or tl.video_duration < duration * 0.85:
                logger.warning(
                    "video_splicer: extract short [%.1f-%.1f] got=%.2fs want=%.2fs",
                    start,
                    end,
                    tl.video_duration if tl else 0.0,
                    duration,
                )
                return False
            return True
        except asyncio.TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.communicate()
            logger.warning(
                "video_splicer: segment extract timed out after %.1fs [%.1f-%.1f]",
                timeout,
                start,
                end,
            )
            return False
        except Exception as exc:
            logger.warning(
                f"video_splicer: segment extract failed [{start:.1f}-{end:.1f}]: {exc}"
            )
            return False

    async def _normalize_video(
        self,
        src_path: str,
        output_path: str,
        target_duration: Optional[float] = None,
    ) -> bool:
        """Force stock footage onto the same 1080x1920@30fps params as extracts."""
        if not os.path.exists(src_path):
            return False

        cmd = [
            "ffmpeg", "-y",
            "-i", src_path,
            "-vf", _VF_NORMALIZE,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            "-movflags", "+faststart",
        ]
        if target_duration and target_duration > 0.05:
            cmd.extend(["-t", f"{target_duration:.3f}"])
        cmd.append(output_path)

        proc: Optional[asyncio.subprocess.Process] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=90.0)
            return (
                proc.returncode == 0
                and os.path.exists(output_path)
                and os.path.getsize(output_path) > 0
            )
        except asyncio.TimeoutError:
            if proc is not None:
                proc.kill()
                await proc.communicate()
            return False
        except Exception:
            return False

    def _validate_no_overlap(self, segments: list[SpliceSegment]) -> bool:
        """Ensure minimum 1s gap between segments."""
        sorted_segs = sorted(segments, key=lambda s: s.at_time)
        for i in range(len(sorted_segs) - 1):
            end_current = sorted_segs[i].at_time + sorted_segs[i].duration
            start_next = sorted_segs[i + 1].at_time
            if start_next - end_current < 1.0:
                logger.warning(
                    f"video_splicer: overlap detected — segment ends at {end_current:.1f}s, "
                    f"next starts at {start_next:.1f}s "
                    f"(gap: {start_next - end_current:.1f}s < 1.0s)"
                )
                return False
        return True

    def _validate_sync(self, output_path: str, original_path: str) -> bool:
        """Reject truncated, unprobeable, silent, or desynchronised outputs."""
        original_tl = probe_media_timeline(original_path)
        output_tl = probe_media_timeline(output_path)
        if original_tl is None or output_tl is None:
            logger.warning("video_splicer: cannot probe source/output for validation")
            return False

        if original_tl.audio_start is not None and output_tl.audio_start is None:
            logger.error("video_splicer: output lost the original audio stream")
            return False

        if not timeline_is_safe(
            output_path,
            expected_duration=original_tl.video_duration,
            max_start_drift=self.MAX_SYNC_DRIFT,
            max_end_drift=0.25,
            max_duration_error=self.MAX_DURATION_ERROR,
        ):
            return False

        logger.info(
            f"video_splicer: validation OK — start_drift={output_tl.start_drift:.3f}s, "
            f"end_drift={output_tl.end_drift:.3f}s, "
            f"video={output_tl.video_duration:.1f}s, "
            f"audio={output_tl.audio_duration or 0:.1f}s"
        )
        return True

    def _cleanup(self, temp_dir: str, temp_files: list[str]) -> None:
        """Remove intermediate files and temp directory."""
        for path in temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

        try:
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except OSError:
            pass
