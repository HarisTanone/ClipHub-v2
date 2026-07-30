"""Canvas background template library API."""
from fastapi import APIRouter, Query

from src.infrastructure.canvas_templates import (
    build_canvas_config,
    get_template,
    list_templates,
)

router = APIRouter(prefix="/canvas-templates", tags=["canvas-templates"])


@router.get("")
async def get_canvas_templates(aspect_ratio: str | None = Query(default=None)):
    """List design-preset background templates.

    content aspect 16:9 / 1:1 → templates that fill TikTok 9:16 letterbox.
    Final canvas is always 9:16.
    """
    templates = list_templates(aspect_ratio)
    return {"success": True, "data": templates, "output_canvas": "9:16"}


@router.get("/{template_id}")
async def get_canvas_template(template_id: str, aspect_ratio: str = Query(default="16:9")):
    """Resolve template + canvas config for content aspect on 9:16 TikTok canvas."""
    tpl = get_template(template_id)
    if not tpl:
        return {"success": False, "error": "Template not found"}
    cfg = build_canvas_config(
        aspect_ratio,
        background_mode="template",
        background_template_id=template_id,
    )
    return {"success": True, "data": tpl, "canvas": cfg}
