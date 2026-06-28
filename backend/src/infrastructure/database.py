"""SQLAlchemy async engine, session, and ORM model — SQLite backend."""
import os
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import settings

# Ensure data directory exists
_db_dir = os.path.dirname(settings.db_path)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    # SQLite doesn't use pool_size/max_overflow the same way
    connect_args={"check_same_thread": False},
)


# Enable WAL mode and foreign keys for SQLite on each connection
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    youtube_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    video_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    video_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="validating")
    render_progress: Mapped[str | None] = mapped_column(String(10), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    clips_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    clips_total: Mapped[int] = mapped_column(Integer, default=0)
    clips_success: Mapped[int] = mapped_column(Integer, default=0)
    clips_failed: Mapped[int] = mapped_column(Integer, default=0)
    style_preset: Mapped[str] = mapped_column(String(50), default="bold_black", nullable=False, server_default="bold_black")
    target_aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16", nullable=False, server_default="9:16")
    hook_engine: Mapped[str] = mapped_column(String(10), default="v3", nullable=False, server_default="v3")
    hook_style: Mapped[str] = mapped_column(String(50), default="", nullable=False, server_default="")
    broll_enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default="1")
    autogrid_enabled: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    # v3.0 Remotion fields
    use_remotion: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    ai_layer_enabled: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    threejs_enabled: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    scene_graphs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    remotion_quality: Mapped[str] = mapped_column(String(20), default="medium", nullable=False, server_default="medium")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(5), default="v1", nullable=False, server_default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class StylePresetModel(Base):
    """Style presets for Remotion rendering."""
    __tablename__ = "style_presets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_color: Mapped[str] = mapped_column(String(10), default="#ffffff", nullable=False)
    secondary_color: Mapped[str] = mapped_column(String(10), default="#ffcc00", nullable=False)
    background_accent: Mapped[str] = mapped_column(String(10), default="#000000", nullable=False)
    typography_mood: Mapped[str] = mapped_column(String(30), default="bold_impact", nullable=False)
    hook_animation: Mapped[str] = mapped_column(String(30), default="fade_scale", nullable=False)
    energy_level: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    transition_style: Mapped[str] = mapped_column(String(20), default="smooth", nullable=False)
    subtitle_position: Mapped[str] = mapped_column(String(20), default="bottom", nullable=False)
    subtitle_uppercase: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enable_threejs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enable_ai_layer: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_system: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class RemotionRenderModel(Base):
    """Track Remotion render jobs."""
    __tablename__ = "remotion_renders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(20), nullable=False)
    clip_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    render_job_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_frame: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_frames: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    render_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HookAnimationModel(Base):
    """Available hook animation styles."""
    __tablename__ = "hook_animations"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


async def init_db():
    """Create all tables if they don't exist (for SQLite auto-setup)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
