"""BRollEngine — B-roll suggestions parsing, timeline constraints, and early analisa."""
import logging
from typing import Any, Dict, List, Optional

from src.domain.entities import (
    BRollSuggestion,
    BrollMotionStyle,
    Clip,
    Job,
    LEGACY_TEMPLATE_TO_MOTION,
    VisualCategory,
)

logger = logging.getLogger(__name__)


def parse_broll_suggestions(
    clip_rank: int,
    broll_map: dict,
    clip_duration: float,
) -> List[BRollSuggestion]:
    """Convert and constrain AI B-roll output to a clip-safe timeline."""
    if not isinstance(broll_map, dict) or clip_duration <= 1.0:
        return []

    raw_suggestions = broll_map.get(str(clip_rank), [])
    if not isinstance(raw_suggestions, list):
        return []

    allowed_templates = {
        "word_pop_typography",
        "line_reveal_typography",
        "particle_text_burst",
    }
    # Up to 4: e.g. 2 full_frame + 2 behind_person on different times
    parsed: List[BRollSuggestion] = []
    for raw in raw_suggestions[:4]:
        if not isinstance(raw, dict):
            continue
        keyword = " ".join(str(raw.get("keyword") or "").split())[:80]
        if not keyword:
            continue
        try:
            at_time = float(raw.get("at_time", 0))
            duration = float(raw.get("duration", 2.0))
        except (TypeError, ValueError):
            continue

        safe_start = 3.0 if clip_duration > 4.0 else 0.0
        at_time = max(safe_start, at_time)
        if at_time >= clip_duration - 1.0:
            continue
        duration = min(3.0, max(1.5, duration), clip_duration - at_time)
        if duration < 1.0:
            continue

        try:
            visual_cat = VisualCategory(raw.get("visual_category", "footage"))
        except (ValueError, TypeError):
            visual_cat = VisualCategory.FOOTAGE
        template = str(raw.get("template") or "word_pop_typography")
        if template not in allowed_templates:
            template = "word_pop_typography"

        # v3.1: resolve Remotion motion style. Accept either an explicit
        # "motion_style" field (new) or fall back to the legacy template id
        # mapping. This keeps older analysis outputs rendering correctly.
        motion_style: Optional[BrollMotionStyle] = None
        raw_motion = raw.get("motion_style")
        if raw_motion:
            try:
                motion_style = BrollMotionStyle(raw_motion)
            except (ValueError, TypeError):
                motion_style = None
        if motion_style is None:
            motion_style = LEGACY_TEMPLATE_TO_MOTION.get(template)

        placement = str(raw.get("placement") or "").strip().lower()
        if placement in {"fullframe", "splice", "replace"}:
            placement = "full_frame"
        elif placement in {"behind", "top_overlay", "overlay", "top"}:
            placement = "behind_person"
        elif placement not in {"full_frame", "behind_person"}:
            # Infer: footage video → full_frame; icon/image → behind_person
            if visual_cat in (VisualCategory.ICON, VisualCategory.MOTION_GRAPHIC):
                placement = "behind_person"
            else:
                placement = "full_frame"

        reason = " ".join(str(raw.get("reason") or "").split())[:200]
        parsed.append(BRollSuggestion(
            at_time=round(at_time, 3),
            keyword=keyword,
            template=template,
            duration=round(duration, 3),
            reason=reason,
            visual_category=visual_cat,
            motion_style=motion_style,
            placement=placement,
        ))

    # Ensure dual tracks when AI only emits one placement type.
    # Need different times so full_frame splice + behind_person can coexist.
    full = [s for s in parsed if s.placement == "full_frame"]
    behind = [s for s in parsed if s.placement == "behind_person"]
    if full and not behind and len(full) >= 2:
        for s in full[1:]:
            s.placement = "behind_person"
    elif behind and not full and len(behind) >= 2:
        behind[0].placement = "full_frame"
    return parsed


def build_broll_events(
    clip: Clip,
    job_motion_style: Optional[str] = None,
) -> List[dict]:
    """Convert a clip's BRollSuggestion list into Remotion BrollEvent dicts."""
    # B-roll is a replacement-track concern. Returning no Remotion events
    # prevents preview/final from silently reintroducing an overlay layer.
    return []


def write_early_json_analisa(
    job: Job,
    job_id: str,
    clips: List[Clip],
    clips_with_words: Dict[int, List[dict]],
    output_dir: str,
) -> None:
    """Draft per-clip analisa BEFORE asset fetch — seeds ID+EN footage search."""
    from src.infrastructure.clip_quality_helpers import build_clip_analisa, write_split_job_meta
    from src.domain.entities import VisualCategory

    payloads = []
    for c in clips:
        words = clips_with_words.get(c.rank, []) if isinstance(clips_with_words, dict) else []
        broll_dicts = []
        for s in (c.broll_suggestions or []):
            vc = s.visual_category
            broll_dicts.append({
                "at_time": s.at_time,
                "keyword": s.keyword,
                "template": s.template,
                "duration": s.duration,
                "reason": getattr(s, "reason", "") or "",
                "placement": getattr(s, "placement", "") or "",
                "visual_category": (
                    vc.value if isinstance(vc, VisualCategory) else str(vc or "")
                ),
            })
        payloads.append(build_clip_analisa(
            no=c.rank,
            rank=c.rank,
            start=c.start,
            end=c.end,
            hook=c.hook or "",
            reason=c.reason or "",
            score=c.score,
            words=words,
            broll_suggestions=broll_dicts,
            text_emphasis_events=list(getattr(c, "text_emphasis_events", None) or [])[:2],
            top_overlay_events=list(getattr(c, "top_overlay_events", None) or []),
            object_overlay_events=list(getattr(c, "object_overlay_events", None) or []),
            visual_entities=list(getattr(c, "visual_entities", None) or []),
            extra={"hyperframes_polish": getattr(c, "hyperframes_polish", None)},
        ))
    write_split_job_meta(
        output_dir,
        job_id=job_id,
        youtube_url=job.youtube_url,
        aspect_ratio=job.target_aspect_ratio,
        created_at=str(job.created_at) if job.created_at else None,
        clip_payloads=payloads,
        clips_total=len(clips),
        clips_success=len(clips),
    )
