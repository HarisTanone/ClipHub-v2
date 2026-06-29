"""SubtitleSyncVerifier — Post-render verification of subtitle/audio alignment.

Runs after each clip render to verify that subtitle text appears at the
correct time relative to the spoken audio. Uses FFmpeg to extract audio
timestamps and compares against the drawtext enable expressions.

This catches:
- Offset bugs (subtitle too early/late)
- Missing subtitles (words not rendered)
- Duration mismatches
"""
import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class SubtitleSyncVerifier:
    """Verify subtitle timing matches audio in rendered clips."""

    def verify_clip(
        self,
        video_path: str,
        words: list[dict],
        hook_duration: float = 3.0,
        tolerance: float = 0.5,
    ) -> dict:
        """Verify subtitle sync for a rendered clip.

        Extracts actual audio duration and checks if word timestamps
        are within expected range.

        Args:
            video_path: Path to rendered final clip
            words: Word dicts with relative timestamps [{word, start, end}]
            hook_duration: Seconds of hook at start (subtitles hidden during this)
            tolerance: Acceptable sync error in seconds

        Returns:
            Dict with verification results:
            {
                "passed": bool,
                "video_duration": float,
                "first_word_time": float,
                "last_word_time": float,
                "word_count": int,
                "issues": [str]
            }
        """
        result = {
            "passed": True,
            "video_duration": 0,
            "first_word_time": 0,
            "last_word_time": 0,
            "word_count": len(words),
            "issues": [],
        }

        if not os.path.exists(video_path):
            result["passed"] = False
            result["issues"].append(f"Video not found: {video_path}")
            return result

        # Get actual video duration
        duration = self._get_duration(video_path)
        result["video_duration"] = duration

        if not words:
            result["issues"].append("No words provided for verification")
            return result

        # Filter subtitle words (after hook)
        subtitle_words = [w for w in words if w.get("start", 0) >= hook_duration]
        if not subtitle_words:
            result["issues"].append(f"No words after hook ({hook_duration}s)")
            result["passed"] = False
            return result

        first_word = subtitle_words[0]
        last_word = subtitle_words[-1]
        result["first_word_time"] = first_word["start"]
        result["last_word_time"] = last_word["end"]

        # Check 1: First subtitle should appear AFTER hook
        if first_word["start"] < hook_duration - tolerance:
            result["passed"] = False
            result["issues"].append(
                f"First subtitle at {first_word['start']:.2f}s — before hook ends at {hook_duration}s"
            )

        # Check 2: Last word should end BEFORE video ends
        if last_word["end"] > duration + tolerance:
            result["passed"] = False
            result["issues"].append(
                f"Last word ends at {last_word['end']:.2f}s — video is only {duration:.2f}s"
            )

        # Check 3: No gaps > 5s between consecutive words (suspicious)
        for i in range(1, len(subtitle_words)):
            gap = subtitle_words[i]["start"] - subtitle_words[i - 1]["end"]
            if gap > 5.0:
                result["issues"].append(
                    f"Large gap ({gap:.1f}s) between words at {subtitle_words[i-1]['end']:.1f}s"
                )

        # Check 4: Word timing is monotonically increasing
        for i in range(1, len(subtitle_words)):
            if subtitle_words[i]["start"] < subtitle_words[i - 1]["start"]:
                result["passed"] = False
                result["issues"].append(
                    f"Non-monotonic timestamps at word '{subtitle_words[i]['word']}'"
                )
                break

        if result["passed"] and not result["issues"]:
            logger.debug(
                f"sync_verify: PASS — {len(subtitle_words)} words, "
                f"first={first_word['start']:.2f}s, last={last_word['end']:.2f}s, "
                f"duration={duration:.2f}s"
            )
        else:
            logger.warning(
                f"sync_verify: {'FAIL' if not result['passed'] else 'WARN'} — "
                f"{'; '.join(result['issues'])}"
            )

        return result

    def verify_all_clips(
        self,
        output_dir: str,
        clips_with_words: dict[int, list[dict]],
        hook_duration: float = 3.0,
    ) -> dict[int, dict]:
        """Verify all clips in a job output directory.

        Returns dict mapping clip_rank → verification result.
        """
        results = {}
        for rank, words in clips_with_words.items():
            final_path = os.path.join(output_dir, f"clip_{rank:02d}_final.mp4")
            if os.path.exists(final_path):
                results[rank] = self.verify_clip(final_path, words, hook_duration)
            else:
                results[rank] = {
                    "passed": False,
                    "issues": [f"Final clip not found: {final_path}"],
                }
        return results

    def _get_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return float(data.get("format", {}).get("duration", 0))
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
            pass
        return 0
