"""Assembly — Clips data assembly, metadata JSON generation, thumbnailing, and folder structure."""
import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from src.domain.entities import Clip, CreativeDirection, Job, VisualCategory

logger = logging.getLogger(__name__)


def best_clip_path(output_dir: str, rank: int, reframe_data: Optional[dict] = None) -> str:
    """Get best available clip path."""
    candidates = [
        f"{output_dir}/clip_{rank:02d}_brolled.mp4",
        f"{output_dir}/clip_{rank:02d}_reframed.mp4",
        f"{output_dir}/clip_{rank:02d}.mp4",
        f"{output_dir}/clip_{rank}.mp4",
    ]
    for path in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return f"{output_dir}/clip_{rank:02d}.mp4"


def assemble_clips_data(
    clips: List[Clip],
    words_per_clip: Dict[int, List[dict]],
    creative_direction: CreativeDirection,
    output_dir: str,
    transcript_source: str = "",
) -> dict:
    """Build final clips_data JSON for storage."""
    clips_output = []
    for clip in clips:
        final_path = f"{output_dir}/clip_{clip.rank:02d}_final.mp4"
        if not os.path.exists(final_path):
            for suffix in ["_subtitled", "_hooked", "_reframed", ""]:
                alt = f"{output_dir}/clip_{clip.rank:02d}{suffix}.mp4"
                if os.path.exists(alt):
                    final_path = alt
                    break

        words = words_per_clip.get(clip.rank, [])
        broll_path = f"{output_dir}/clip_{clip.rank:02d}_brolled.mp4"
        broll_n = len(clip.broll_suggestions or [])
        try:
            from src.infrastructure.clip_quality_helpers import (
                retention_trim_hints,
                suggest_cta,
                virality_breakdown,
            )
            viral = virality_breakdown(
                clip.score,
                hook=clip.hook or "",
                reason=clip.reason or "",
                duration=clip.end - clip.start,
                words=words,
                broll_count=broll_n,
            )
            cta = suggest_cta(clip.hook or "", clip.reason or "", clip.rank)
            retention = retention_trim_hints(words, clip.end - clip.start)
        except Exception:
            viral, cta, retention = {}, {}, {}
        try:
            from src.infrastructure.clip_quality_helpers import share_pack_for_clip
            captions, hashtags, hook_alts = share_pack_for_clip(
                hook=clip.hook or "",
                reason=clip.reason or "",
                score=clip.score,
                duration=clip.end - clip.start,
                words=words,
                visual_entities=list(getattr(clip, "visual_entities", None) or []),
                cta=cta,
                virality=viral,
                rank=clip.rank,
            )
        except Exception:
            captions, hashtags, hook_alts = {}, [], []
        clips_output.append({
            "rank": clip.rank,
            "score": clip.score,
            "start": clip.start,
            "end": clip.end,
            "duration": round(clip.end - clip.start, 2),
            "hook": clip.hook,
            "reason": clip.reason,
            "output_path": final_path,
            "words": words,
            "word_count": len(words),
            "has_subtitles": len(words) > 0,
            "broll_applied": os.path.exists(broll_path),
            "broll_suggestions": [
                {
                    "at_time": suggestion.at_time,
                    "keyword": suggestion.keyword,
                    "template": suggestion.template,
                    "duration": suggestion.duration,
                    "placement": getattr(suggestion, "placement", "") or "",
                    "visual_category": (
                        suggestion.visual_category.value
                        if isinstance(suggestion.visual_category, VisualCategory)
                        else str(suggestion.visual_category)
                    ),
                    "asset_source": (
                        suggestion.asset_result.source_api
                        if suggestion.asset_result else ""
                    ),
                }
                for suggestion in clip.broll_suggestions
            ],

            "text_emphasis_events": [
                {
                    key: value
                    for key, value in event.items()
                    if key != "foreground_frames"
                }
                for event in clip.text_emphasis_events[:2]
            ],
            "top_overlay_events": list(getattr(clip, "top_overlay_events", None) or []),
            "object_overlay_events": list(getattr(clip, "object_overlay_events", None) or []),
            "visual_entities": list(getattr(clip, "visual_entities", None) or []),
            "hyperframes_polish": getattr(clip, "hyperframes_polish", None),
            "virality": viral,
            "cta": cta,
            "retention_hints": retention,
            "captions": captions,
            "hashtags": hashtags,
            "hook_alts": hook_alts,
        })

    return {
        "pipeline_version": "v2",
        "transcript_source": transcript_source,
        "creative_direction": asdict(creative_direction),
        "clips": clips_output,
    }


async def create_folder_structure(
    job_id: str,
    job: Job,
    clips: List[Clip],
    clips_with_words: Dict[int, List[dict]],
    creative_direction: CreativeDirection,
    output_dir: str,
    trim_results: Dict[int, bool],
) -> None:
    """Create raw/, final/, thumbnail/, json_analisa/ + slim meta index."""
    thumb_dir = f"{output_dir}/thumbnail"
    raw_dir = f"{output_dir}/raw"
    final_dir = f"{output_dir}/final"
    os.makedirs(thumb_dir, exist_ok=True)
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    for clip in clips:
        if not trim_results.get(clip.rank):
            continue
        rank = clip.rank

        final_path = f"{output_dir}/clip_{rank:02d}_final.mp4"
        thumb_path = f"{thumb_dir}/clip_{rank:02d}.jpg"
        if os.path.exists(final_path):
            seek = 1.2
            try:
                from src.infrastructure.clip_quality_helpers import (
                    generate_smart_thumbnail,
                    smart_thumbnail_seek,
                )
                words = clips_with_words.get(rank, []) if isinstance(clips_with_words, dict) else []
                dur = max(0.5, float(clip.end) - float(clip.start))
                seek = smart_thumbnail_seek(words, dur, hook=clip.hook or "")
                ok = generate_smart_thumbnail(final_path, thumb_path, seek=seek, width=1080)
                if not ok:
                    raise RuntimeError("smart thumb failed")
            except Exception:
                thumb_cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{max(0.2, float(seek)):.2f}",
                    "-i", final_path,
                    "-frames:v", "1",
                    "-vf", "scale='min(1080,iw)':-2",
                    "-q:v", "2",
                    thumb_path,
                ]
                try:
                    await asyncio.to_thread(
                        subprocess.run, thumb_cmd, capture_output=True, text=True, timeout=15
                    )
                except Exception:
                    pass

            if os.path.exists(thumb_path):
                for alias in [
                    f"{thumb_dir}/clip_{rank:02d}_thumb.jpg",
                    f"{thumb_dir}/clip_{rank}_thumb.jpg",
                    f"{thumb_dir}/clip_{rank:02d}_social.jpg",
                ]:
                    try:
                        shutil.copy2(thumb_path, alias)
                    except Exception:
                        pass

        raw_src = f"{output_dir}/clip_{rank:02d}.mp4"
        if os.path.exists(raw_src):
            shutil.copy2(raw_src, f"{raw_dir}/clip_{rank:02d}.mp4")

        if os.path.exists(final_path):
            shutil.copy2(final_path, f"{final_dir}/clip_{rank:02d}.mp4")

    from src.infrastructure.clip_quality_helpers import (
        build_clip_analisa,
        write_split_job_meta,
    )

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
                "asset_source": (
                    s.asset_result.source_api if s.asset_result else ""
                ),
            })
        te = [
            {k: v for k, v in ev.items() if k != "foreground_frames"}
            for ev in (c.text_emphasis_events or [])[:2]
        ]
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
            text_emphasis_events=te,
            top_overlay_events=list(getattr(c, "top_overlay_events", None) or []),
            object_overlay_events=list(getattr(c, "object_overlay_events", None) or []),
            visual_entities=list(getattr(c, "visual_entities", None) or []),
            extra={
                "hyperframes_polish": getattr(c, "hyperframes_polish", None),
            },
        ))

    write_split_job_meta(
        output_dir,
        job_id=job_id,
        youtube_url=job.youtube_url,
        aspect_ratio=job.target_aspect_ratio,
        created_at=str(job.created_at) if job.created_at else None,
        clip_payloads=payloads,
        clips_total=len(clips),
        clips_success=sum(1 for c in clips if trim_results.get(c.rank)),
    )
    logger.info(f"[{job_id}] Folder structure created (json_analisa split)")
