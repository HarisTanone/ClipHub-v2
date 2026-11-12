"""REST API routes for AI Image & Visual Post Studio (Hermes Automation & Instant Generator)."""
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.infrastructure.ai_image_studio_service import (
    ASSETS_MUSIC_DIR,
    OUTPUT_DIR,
    ai_image_studio_service,
)
from src.infrastructure.ai_image_typography import typography_engine
from src.presentation.auth_deps import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/image-studio", tags=["AI Image Studio"])


class UpdateImageStudioSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    topics: Optional[List[str]] = None
    daily_slots: Optional[List[Dict[str, Any]]] = None
    images_per_session: Optional[int] = Field(None, ge=1, le=10)
    aspect_ratio: Optional[str] = Field(None, description="9:16, 1:1, 4:5, 16:9")
    template_preset: Optional[str] = None
    font_family: Optional[str] = None
    model_name: Optional[str] = None
    background_source: Optional[str] = Field(None, description="ai_gemini, pexels, pixabay, giphy, user_upload")
    media_type: Optional[str] = Field(None, description="image, video_footage")
    auto_post_enabled: Optional[bool] = None
    target_account_ids: Optional[List[str]] = None
    music_enabled: Optional[bool] = None
    music_track: Optional[str] = None
    footage_duration_sec: Optional[int] = Field(None, ge=3, le=30)


class InstantGenerateRequest(BaseModel):
    topic: Optional[str] = ""
    prompt: Optional[str] = ""
    quote_hook: Optional[str] = ""
    quote_headline: Optional[str] = ""
    quote_body: Optional[str] = ""
    quote_author: Optional[str] = ""
    quote_handle: Optional[str] = "@cliperhub"
    accent_color: Optional[str] = "#EAB308"
    template_preset: Optional[str] = "minimal_quote"
    font_family: Optional[str] = "auto"
    model_name: Optional[str] = "auto"
    aspect_ratio: Optional[str] = "9:16"
    background_source: Optional[str] = "ai_gemini"
    media_type: Optional[str] = "image"
    image_count: Optional[int] = Field(1, ge=1, le=10)
    auto_post: Optional[bool] = False
    target_account_ids: Optional[List[str]] = None
    music_enabled: Optional[bool] = False
    music_id: Optional[str] = None
    music_name: Optional[str] = None
    music_artist: Optional[str] = None
    music_thumbnail: Optional[str] = None
    progress_token: Optional[str] = Field(None, max_length=100)


class SuggestContentRequest(BaseModel):
    topic: str = Field(..., description="Topik atau tema visual")


class CreateTemplateRequest(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=2, max_length=100)
    vibe: Optional[str] = ""
    primary_font: Optional[str] = "Playfair Display"
    secondary_font: Optional[str] = "Inter"
    recommended_accent: Optional[str] = "#EAB308"
    layout_type: Optional[str] = "minimal_quote"
    sort_order: Optional[int] = 50


class UpdateTemplateRequest(BaseModel):
    name: Optional[str] = None
    vibe: Optional[str] = None
    primary_font: Optional[str] = None
    secondary_font: Optional[str] = None
    recommended_accent: Optional[str] = None
    layout_type: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CreateFontRequest(BaseModel):
    id: Optional[str] = None
    font_name: str = Field(..., min_length=2)
    file_name: str = Field(..., min_length=3)
    sort_order: Optional[int] = 50


class UpdateFontRequest(BaseModel):
    font_name: Optional[str] = None
    file_name: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CreateAspectRatioRequest(BaseModel):
    id: str = Field(..., description="Format rasio, misal: '3:4' atau '2:3'")
    name: str = Field(...)
    width: int = Field(..., gt=100)
    height: int = Field(..., gt=100)
    description: Optional[str] = ""
    sort_order: Optional[int] = 50


class UpdateAspectRatioRequest(BaseModel):
    name: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class TriggerHermesRunRequest(BaseModel):
    slot_name: Optional[str] = "Manual Run"
    topic_override: Optional[str] = None
    count_override: Optional[int] = Field(None, ge=1, le=10)
    progress_token: Optional[str] = Field(None, max_length=100)


class SocialPublishRequest(BaseModel):
    run_id: int
    account_ids: List[str]
    title: Optional[str] = ""
    caption: Optional[str] = ""
    music_enabled: Optional[bool] = False
    music_id: Optional[str] = None
    music_name: Optional[str] = None
    music_artist: Optional[str] = None
    music_thumbnail: Optional[str] = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(user: CurrentUser = Depends(get_current_user)):
    """Fetch current AI Image Studio automation settings."""
    settings_data = ai_image_studio_service.get_settings(user_id=user.id)
    return {
        "success": True,
        "data": settings_data,
    }


@router.put("/settings")
@router.post("/settings")
async def update_settings(
    req: UpdateImageStudioSettingsRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update AI Image Studio automation settings."""
    update_data = req.model_dump(exclude_unset=True)
    updated = ai_image_studio_service.update_settings(user_id=user.id, data=update_data)
    return {
        "success": True,
        "message": "Pengaturan AI Image Studio berhasil diperbarui",
        "data": updated,
    }


@router.get("/templates")
async def list_templates(include_inactive: bool = False):
    """List all available typography templates dynamically loaded from database."""
    from src.infrastructure.image_typography_store import get_all_typography_templates
    return {
        "success": True,
        "data": get_all_typography_templates(include_inactive=include_inactive),
    }


@router.post("/templates")
async def create_template(
    req: CreateTemplateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new custom typography template in database."""
    from src.infrastructure.image_typography_store import create_typography_template
    tpl = create_typography_template(req.model_dump(exclude_unset=True))
    return {
        "success": True,
        "message": f"Template '{tpl.get('name')}' berhasil disimpan ke database",
        "data": tpl,
    }


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    req: UpdateTemplateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update fields of an existing typography template in database."""
    from src.infrastructure.image_typography_store import update_typography_template
    updated = update_typography_template(template_id, req.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    return {
        "success": True,
        "message": "Template berhasil diperbarui di database",
        "data": updated,
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a typography template from database."""
    from src.infrastructure.image_typography_store import delete_typography_template
    ok = delete_typography_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan")
    return {
        "success": True,
        "message": "Template berhasil dihapus dari database",
    }


@router.post("/templates/reset")
async def reset_templates(
    user: CurrentUser = Depends(get_current_user),
):
    """Reset all templates in database to factory defaults."""
    from src.infrastructure.image_typography_store import reset_typography_templates
    templates = reset_typography_templates()
    return {
        "success": True,
        "message": "Template berhasil di-reset ke preset bawaan database",
        "data": templates,
    }


@router.get("/fonts")
async def list_fonts(include_inactive: bool = False):
    """List available font typography families from database."""
    from src.infrastructure.image_typography_store import get_all_typography_fonts
    fonts = get_all_typography_fonts(include_inactive=include_inactive)
    return {
        "success": True,
        "data": [f["font_name"] for f in fonts],
        "fonts": fonts,
    }


@router.post("/fonts")
async def create_font(
    req: CreateFontRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Add a new typography font definition into database."""
    from src.infrastructure.image_typography_store import create_typography_font
    f = create_typography_font(req.model_dump(exclude_unset=True))
    return {
        "success": True,
        "message": f"Font '{f.get('font_name')}' berhasil ditambahkan ke database",
        "data": f,
    }


@router.put("/fonts/{font_id}")
async def update_font(
    font_id: str,
    req: UpdateFontRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update typography font in database."""
    from src.infrastructure.image_typography_store import update_typography_font
    f = update_typography_font(font_id, req.model_dump(exclude_unset=True))
    if not f:
        raise HTTPException(status_code=404, detail="Font tidak ditemukan")
    return {
        "success": True,
        "message": "Font berhasil diperbarui di database",
        "data": f,
    }


@router.delete("/fonts/{font_id}")
async def delete_font(
    font_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete typography font from database."""
    from src.infrastructure.image_typography_store import delete_typography_font
    ok = delete_typography_font(font_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Font tidak ditemukan")
    return {
        "success": True,
        "message": "Font berhasil dihapus dari database",
    }


@router.get("/aspect-ratios")
async def list_aspect_ratios(include_inactive: bool = False):
    """List all canvas aspect ratios and dimensions from database."""
    from src.infrastructure.image_typography_store import get_all_aspect_ratios
    return {
        "success": True,
        "data": get_all_aspect_ratios(include_inactive=include_inactive),
    }


@router.post("/aspect-ratios")
async def create_aspect_ratio_endpoint(
    req: CreateAspectRatioRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Add a custom aspect ratio and canvas dimension into database."""
    from src.infrastructure.image_typography_store import create_aspect_ratio
    ar = create_aspect_ratio(req.model_dump(exclude_unset=True))
    return {
        "success": True,
        "message": f"Aspek rasio '{ar.get('id')}' berhasil ditambahkan ke database",
        "data": ar,
    }


@router.put("/aspect-ratios/{aspect_id}")
async def update_aspect_ratio_endpoint(
    aspect_id: str,
    req: UpdateAspectRatioRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update aspect ratio in database."""
    from src.infrastructure.image_typography_store import update_aspect_ratio
    ar = update_aspect_ratio(aspect_id, req.model_dump(exclude_unset=True))
    if not ar:
        raise HTTPException(status_code=404, detail="Aspek rasio tidak ditemukan")
    return {
        "success": True,
        "message": "Aspek rasio berhasil diperbarui di database",
        "data": ar,
    }


@router.delete("/aspect-ratios/{aspect_id}")
async def delete_aspect_ratio_endpoint(
    aspect_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete aspect ratio from database."""
    from src.infrastructure.image_typography_store import delete_aspect_ratio
    ok = delete_aspect_ratio(aspect_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Aspek rasio tidak ditemukan")
    return {
        "success": True,
        "message": "Aspek rasio berhasil dihapus dari database",
    }


@router.get("/accents")
async def list_accents():
    """List all accent color presets from database."""
    from src.infrastructure.image_typography_store import get_all_accent_presets
    return {
        "success": True,
        "data": get_all_accent_presets(),
    }


@router.post("/suggest-content")
async def suggest_quote_content(
    req: SuggestContentRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate intelligent viral quote, hook, body, and prompt via 9router AI."""
    result = ai_image_studio_service.suggest_quote_content(req.topic)
    return {
        "success": True,
        "data": result,
    }


@router.post("/generate")
async def generate_instant(
    req: InstantGenerateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Instant visual generation endpoint with prompt, typography, and optional social posting."""
    try:
        result = await ai_image_studio_service.execute_generation_session(
            user_id=user.id,
            topic=req.topic or "Inspirasi & Mindset",
            session_name="Instant Studio",
            image_count=req.image_count or 1,
            aspect_ratio=req.aspect_ratio or "9:16",
            template_preset=req.template_preset or "minimal_quote",
            font_family=req.font_family or "auto",
            model_name=req.model_name or "auto",
            background_source=req.background_source or "ai_gemini",
            media_type=req.media_type or "image",
            custom_prompt=req.prompt or "",
            quote_hook=req.quote_hook or "",
            quote_headline=req.quote_headline or "",
            quote_body=req.quote_body or "",
            quote_author=req.quote_author or "",
            quote_handle=req.quote_handle or "@cliperhub",
            accent_color=req.accent_color or "#EAB308",
            auto_post=bool(req.auto_post),
            target_account_ids=req.target_account_ids or [],
            music_enabled=bool(req.music_enabled),
            music_id=req.music_id,
            music_name=req.music_name,
            music_artist=req.music_artist,
            music_thumbnail=req.music_thumbnail,
            trigger_source="instant_studio",
            progress_token=req.progress_token,
        )
        return {
            "success": True,
            "message": "Visual post berhasil dibuat",
            "data": result,
        }
    except Exception as e:
        logger.error(f"[AIImageStudio] Instant generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def trigger_hermes_session(
    req: TriggerHermesRunRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Trigger an immediate Hermes session run with current configured settings."""
    settings_data = ai_image_studio_service.get_settings(user_id=user.id)
    topics = settings_data.get("topics") or ["Inspirasi & Mindset"]
    topic = req.topic_override or topics[0]
    count = req.count_override or settings_data.get("images_per_session", 2)

    music_track = settings_data.get("music_track")
    try:
        result = await ai_image_studio_service.execute_generation_session(
            user_id=user.id,
            topic=topic,
            session_name=req.slot_name or "Manual Hermes Trigger",
            image_count=count,
            aspect_ratio=settings_data.get("aspect_ratio", "9:16"),
            template_preset=settings_data.get("template_preset", "auto"),
            font_family=settings_data.get("font_family", "auto"),
            model_name=settings_data.get("model_name", "auto"),
            background_source=settings_data.get("background_source", "ai_gemini"),
            media_type=settings_data.get("media_type", "image"),
            footage_duration_sec=settings_data.get("footage_duration_sec", 8),
            auto_post=settings_data.get("auto_post_enabled", False),
            target_account_ids=settings_data.get("target_account_ids", []),
            music_enabled=settings_data.get("music_enabled", False),
            music_id=str(music_track) if (music_track and str(music_track).isdigit()) else None,
            trigger_source="manual_trigger",
            progress_token=req.progress_token,
        )
        return {
            "success": True,
            "message": f"Hermes session berhasil dieksekusi ({count} item)",
            "data": result,
        }
    except Exception as e:
        logger.error(f"[AIImageStudio] Hermes session failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress/{token}")
async def get_generation_progress(token: str, user: CurrentUser = Depends(get_current_user)):
    """Poll live progress for a single generate/run request identified by a
    client-generated token. Returns data=None if the token is unknown (not yet
    started, already expired, or never used a progress_token)."""
    state = ai_image_studio_service.get_progress(token)
    return {
        "success": True,
        "data": state,
    }


@router.get("/history")
async def get_history(user: CurrentUser = Depends(get_current_user)):
    """Fetch history of generated images and runs."""
    items = ai_image_studio_service.get_history(user_id=user.id)
    return {
        "success": True,
        "data": items,
    }


@router.delete("/history/{run_id}")
async def delete_history_item(run_id: int, user: CurrentUser = Depends(get_current_user)):
    """Delete a generated run."""
    success = ai_image_studio_service.delete_history_item(run_id, user_id=user.id)
    return {
        "success": success,
        "message": "Riwayat dan file gambar berhasil dihapus",
    }


@router.post("/post-social")
async def publish_run_to_social(
    req: SocialPublishRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Publish an existing generated run to selected social accounts."""
    history = ai_image_studio_service.get_history(user_id=user.id)
    matched = next((h for h in history if h.get("id") == req.run_id), None)
    if not matched:
        raise HTTPException(status_code=404, detail="Run history not found")

    media_urls = matched.get("image_urls") or []
    if matched.get("video_url"):
        media_urls = [matched["video_url"]]

    if not media_urls:
        raise HTTPException(status_code=400, detail="No media files found in this run")

    status, details = await ai_image_studio_service._dispatch_social_post(
        account_ids=req.account_ids,
        media_urls=media_urls,
        title=req.title or matched.get("topic", "Visual Post"),
        caption=req.caption or f"{matched.get('quote_headline', '')}\n\n{matched.get('quote_body', '')}",
        media_type="video" if matched.get("media_type") == "video_footage" else ("carousel" if len(media_urls) > 1 else "photo"),
        music_enabled=bool(req.music_enabled),
        music_id=req.music_id,
        music_name=req.music_name,
        music_artist=req.music_artist,
        music_thumbnail=req.music_thumbnail,
    )

    try:
        from src.infrastructure.database import get_dict_connection
        import json
        conn = get_dict_connection()
        try:
            conn.execute(
                """
                UPDATE ai_image_runs
                SET social_post_status = ?, social_details = ?
                WHERE id = ? AND user_id = ?
                """,
                (status, json.dumps(details), req.run_id, user.id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as db_err:
        logger.warning(f"[AIImageStudio] Failed to update ai_image_runs post status: {db_err}")

    return {
        "success": status in ("scheduled", "partial"),
        "status": status,
        "details": details,
    }


@router.post("/upload-media")
async def upload_custom_media(
    file: UploadFile = File(...),
    media_type: str = "image",  # image, video, music
    user: CurrentUser = Depends(get_current_user),
):
    """Upload custom background image, video footage, or music track."""
    target_dir = ASSETS_MUSIC_DIR if media_type == "music" else OUTPUT_DIR
    ext = os.path.splitext(file.filename or "")[1] or (".mp3" if media_type == "music" else ".png")
    filename = f"upload_{uuid.uuid4().hex[:10]}{ext}"
    dest_path = os.path.join(target_dir, filename)

    content = await file.read()
    with open(dest_path, "wb") as f_out:
        f_out.write(content)

    return {
        "success": True,
        "filename": filename,
        "url": f"/api/image-studio/media/{filename}",
        "local_path": dest_path,
    }


@router.get("/media/{filename}")
async def serve_media(filename: str):
    """Serve local generated images, videos, or music files."""
    # Sanitize filename
    safe_name = os.path.basename(filename)
    path_output = os.path.join(OUTPUT_DIR, safe_name)
    path_music = os.path.join(ASSETS_MUSIC_DIR, safe_name)

    target_path = None
    if os.path.exists(path_output):
        target_path = path_output
    elif os.path.exists(path_music):
        target_path = path_music

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Media file not found")

    ext = os.path.splitext(safe_name)[1].lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(
        target_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*"},
    )

