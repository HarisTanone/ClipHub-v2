"""Style presets API routes — v3.0 Remotion integration."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import StylePresetModel, HookAnimationModel, async_session

router = APIRouter(prefix="/style-presets", tags=["Style Presets"])


# ─── Response Models ──────────────────────────────────────────────────────────

class StylePresetResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    primary_color: str
    secondary_color: str
    background_accent: str
    typography_mood: str
    hook_animation: str
    energy_level: str
    transition_style: str
    subtitle_position: str
    subtitle_uppercase: bool
    enable_threejs: bool
    enable_ai_layer: bool
    is_system: bool

    class Config:
        from_attributes = True


class HookAnimationResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    preview_url: Optional[str] = None

    class Config:
        from_attributes = True


class StylePresetListResponse(BaseModel):
    success: bool = True
    data: list[StylePresetResponse]
    total: int


class HookAnimationListResponse(BaseModel):
    success: bool = True
    data: list[HookAnimationResponse]
    total: int


# ─── Style Presets Endpoints ──────────────────────────────────────────────────

@router.get("", response_model=StylePresetListResponse)
async def list_style_presets(active_only: bool = True):
    """List all available style presets."""
    async with async_session() as session:
        query = select(StylePresetModel)
        if active_only:
            query = query.where(StylePresetModel.is_active == 1)
        query = query.order_by(StylePresetModel.name)
        
        result = await session.execute(query)
        presets = result.scalars().all()
        
        return StylePresetListResponse(
            data=[
                StylePresetResponse(
                    id=p.id,
                    name=p.name,
                    description=p.description,
                    primary_color=p.primary_color,
                    secondary_color=p.secondary_color,
                    background_accent=p.background_accent,
                    typography_mood=p.typography_mood,
                    hook_animation=p.hook_animation,
                    energy_level=p.energy_level,
                    transition_style=p.transition_style,
                    subtitle_position=p.subtitle_position,
                    subtitle_uppercase=bool(p.subtitle_uppercase),
                    enable_threejs=bool(p.enable_threejs),
                    enable_ai_layer=bool(p.enable_ai_layer),
                    is_system=bool(p.is_system),
                )
                for p in presets
            ],
            total=len(presets),
        )


@router.get("/{preset_id}", response_model=StylePresetResponse)
async def get_style_preset(preset_id: str):
    """Get a specific style preset by ID."""
    async with async_session() as session:
        result = await session.execute(
            select(StylePresetModel).where(StylePresetModel.id == preset_id)
        )
        preset = result.scalar_one_or_none()
        
        if not preset:
            raise HTTPException(status_code=404, detail="Style preset not found")
        
        return StylePresetResponse(
            id=preset.id,
            name=preset.name,
            description=preset.description,
            primary_color=preset.primary_color,
            secondary_color=preset.secondary_color,
            background_accent=preset.background_accent,
            typography_mood=preset.typography_mood,
            hook_animation=preset.hook_animation,
            energy_level=preset.energy_level,
            transition_style=preset.transition_style,
            subtitle_position=preset.subtitle_position,
            subtitle_uppercase=bool(preset.subtitle_uppercase),
            enable_threejs=bool(preset.enable_threejs),
            enable_ai_layer=bool(preset.enable_ai_layer),
            is_system=bool(preset.is_system),
        )


# ─── Hook Animations Endpoints ────────────────────────────────────────────────

@router.get("/hooks/animations", response_model=HookAnimationListResponse)
async def list_hook_animations():
    """List all available hook animations."""
    async with async_session() as session:
        result = await session.execute(
            select(HookAnimationModel)
            .where(HookAnimationModel.is_active == 1)
            .order_by(HookAnimationModel.name)
        )
        animations = result.scalars().all()
        
        return HookAnimationListResponse(
            data=[
                HookAnimationResponse(
                    id=a.id,
                    name=a.name,
                    description=a.description,
                    preview_url=a.preview_url,
                )
                for a in animations
            ],
            total=len(animations),
        )
