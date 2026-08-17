"""SubtitleBuilder — Word-level alignment, hook suppression, and clip preparation."""
import logging
from typing import Any, Dict, List, Optional

from src.config import settings
from src.domain.entities import Clip, HighlightAnalysisResult, HighlightCandidate
from src.infrastructure.subtitle_words import sanitize_subtitle_words

logger = logging.getLogger(__name__)


def build_direct_edit_analysis(video_duration: float, custom_hook: object = None) -> HighlightAnalysisResult:
    """Build the direct-edit result without invoking the AI analyzer."""
    hook = str(custom_hook or "").strip()
    return HighlightAnalysisResult(
        clips=[HighlightCandidate(
            rank=1,
            start=0.0,
            end=video_duration,
            score=100,
            hook=hook,
            reason="Direct full-video edit",
        )],
        creative_direction={},
        broll_suggestions={},
        model_used="direct",
        chunks_processed=0,
    )


def pick_hook(h: Any) -> str:
    """A/B: primary hook vs hook_alt with resilient fallbacks."""
    primary = str(getattr(h, "hook", "") or "").strip()
    alt = str(getattr(h, "hook_alt", "") or "").strip()
    reason = str(getattr(h, "reason", "") or "").strip()
    rank = getattr(h, "rank", 1) or 1
    try:
        from src.infrastructure.hook_optimizer import HookOptimizer
        chosen = HookOptimizer.pick_hook_ab(primary, alt)
        if chosen and chosen.strip():
            return chosen.strip()
    except Exception:
        pass
    if primary:
        return primary
    if alt:
        return alt
    if reason:
        return reason[:60] if len(reason) > 60 else reason
    return f"Highlight #{rank}"


def build_clips_with_words(
    clips: List[Clip],
    words_per_clip: Dict[int, list],
    hook_duration: float = 0.0,
) -> Dict[int, List[dict]]:
    """Build subtitle word dicts per clip from word-level transcription output.

    Word-level transcription returns 0-based words (relative to each clip's
    start) — no timestamp shifting happens here. This method sanitizes them
    (clamp to clip duration, dedupe, mark highlights) and suppresses words
    that fall under the hook window when the clip has a hook text (the hook
    owns 0–hook_duration seconds).

    Returns {clip_rank: [{"word", "start", "end", "highlight"}]}.
    """
    clips_with_words: Dict[int, List[dict]] = {}
    for clip in clips:
        raw_words = words_per_clip.get(clip.rank, [])
        clip_duration = round(clip.end - clip.start, 3)
        # Only suppress subtitles under the hook when a hook text exists.
        sub_min = hook_duration if (clip.hook and hook_duration > 0) else 0.0
        valid_words = sanitize_subtitle_words(
            raw_words,
            clip_duration,
            subtitle_min_start=sub_min,
        )
        clips_with_words[clip.rank] = valid_words
        if valid_words:
            logger.info(
                f"v2_words clip {clip.rank}: {len(valid_words)} words, "
                f"first={valid_words[0]['start']:.2f}s (min={sub_min:.1f}), "
                f"last='{valid_words[-1]['word']}' @ {valid_words[-1]['start']:.1f}s, "
                f"clip_duration={clip_duration:.1f}s"
            )
    return clips_with_words


def prepare_clips_from_v2(
    highlights: list,
    broll_map: dict,
    video_duration: float,
    broll_parser_fn=None,
) -> List[Clip]:
    """Convert V2 HighlightCandidate list → Clip entities."""
    clips = []
    for h in highlights:
        start = max(0, h.start - 0.5)
        end = min(video_duration, h.end + 1.0)
        if end - start < settings.MIN_CLIP_DURATION:
            continue

        broll_suggestions = []
        if broll_parser_fn:
            broll_suggestions = broll_parser_fn(h.rank, broll_map, end - start)

        clips.append(Clip(
            rank=h.rank,
            score=h.score,
            start=start,
            end=end,
            hook=pick_hook(h),
            reason=h.reason,
            broll_suggestions=broll_suggestions,
        ))
    return clips
