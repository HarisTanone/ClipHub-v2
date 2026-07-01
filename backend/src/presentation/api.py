"""FastAPI application with lifespan and CORS."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.infrastructure.alerting_service import AlertingService
from src.infrastructure.auto_scale_advisor import AutoScaleAdvisor
from src.infrastructure.arq_job_queue import ARQJobQueue
from src.presentation.routes.jobs import router as jobs_router
from src.presentation.routes.monitoring import router as monitoring_router
from src.presentation.routes.progress import router as progress_router
from src.presentation.routes.auth import router as auth_router
from src.presentation.routes.brolls import router as brolls_router
from src.presentation.routes.settings import router as settings_router
from src.presentation.routes.preview import router as preview_router
from src.presentation.routes.styles import router as styles_router
from src.presentation.routes.remotion import router as remotion_router
from src.presentation.routes.presets import router as presets_router
from src.presentation.routes.storage import router as storage_router
from src.presentation.routes.features import router as features_router
from src.presentation.routes.transcript import router as transcript_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Shared instances for background tasks ────────────────────────────────────
_job_queue = ARQJobQueue()
_alerting_service = AlertingService(job_queue=_job_queue)
_auto_scale_advisor = AutoScaleAdvisor()


async def _auto_scale_loop() -> None:
    """Background loop: evaluate scaling recommendation every 60s."""
    while True:
        try:
            queue_depth = _job_queue.pending_count
            _auto_scale_advisor.evaluate(queue_depth, current_workers=1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("auto_scale_loop_error", extra={"error": str(e)})
        await asyncio.sleep(AutoScaleAdvisor.EVAL_INTERVAL)


async def _recover_stale_jobs() -> None:
    """Mark in-progress jobs from a previous server instance as failed.

    When the server restarts, any jobs that were actively processing are now
    orphaned — their pipeline coroutines no longer exist. This marks them as
    failed so URL dedup won't block new submissions for the same URL.
    """
    from sqlalchemy import text, update
    from src.infrastructure.database import async_session, JobModel

    terminal = ("completed", "failed", "timeout")
    try:
        async with async_session() as session:
            result = await session.execute(
                text(
                    "SELECT job_id, status FROM jobs "
                    "WHERE status NOT IN ('completed', 'failed', 'timeout')"
                )
            )
            stale_jobs = result.fetchall()

            if stale_jobs:
                job_ids = [row[0] for row in stale_jobs]
                await session.execute(
                    update(JobModel)
                    .where(JobModel.job_id.in_(job_ids))
                    .values(
                        status="failed",
                        error_message="Pipeline interrupted: server restarted",
                    )
                )
                await session.commit()
                for job_id, old_status in stale_jobs:
                    logger.info(
                        f"stale_job_recovered: {job_id} ({old_status} → failed)"
                    )
                logger.info(f"Recovered {len(stale_jobs)} stale job(s) from previous instance")
            else:
                logger.info("No stale jobs to recover")
    except Exception as e:
        logger.warning(f"stale_job_recovery_failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create dirs, init DB, recover stale jobs, start background tasks. Shutdown: cancel tasks."""
    os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

    # ─── Migrate DB schema (add missing columns BEFORE ORM init) ──────────
    try:
        from src.infrastructure.db_connection import get_dict_connection
        conn = get_dict_connection()
        cur = conn.cursor()
        # Check and add missing columns
        cur.execute("PRAGMA table_info(jobs)")
        job_cols = [row["name"] for row in cur.fetchall()]
        if "pipeline_version" not in job_cols:
            cur.execute("ALTER TABLE jobs ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'v1'")
            logger.info("migration: added pipeline_version to jobs table")
        if "video_title" not in job_cols:
            cur.execute("ALTER TABLE jobs ADD COLUMN video_title TEXT DEFAULT NULL")
            logger.info("migration: added video_title to jobs table")

        cur.execute("PRAGMA table_info(users)")
        user_cols = [row["name"] for row in cur.fetchall()]
        if "is_premium" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER NOT NULL DEFAULT 0")
            logger.info("migration: added is_premium to users table")
        if "pipeline_override" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN pipeline_override TEXT DEFAULT NULL")
            logger.info("migration: added pipeline_override to users table")

        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"migration: schema migration failed (non-critical): {e}")

    # ─── Initialize SQLite database (create tables if needed) ─────────────
    from src.infrastructure.database import init_db
    await init_db()

    # ─── Seed roles, permissions, superadmin user ─────────────────────────
    from src.infrastructure.db_seeder import seed_database
    seed_database()

    # ─── Migrate orphan jobs (no user_id) to superadmin ───────────────────
    try:
        from src.infrastructure.db_connection import get_dict_connection
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("UPDATE jobs SET user_id = 1 WHERE user_id IS NULL")
        migrated = cur.rowcount
        conn.commit()
        conn.close()
        if migrated > 0:
            logger.info(f"Migrated {migrated} orphan jobs to superadmin (user_id=1)")
    except Exception as e:
        logger.warning(f"orphan_job_migration_failed: {e}")

    # ─── Recover stale jobs from previous server instance ─────────────────
    await _recover_stale_jobs()

    # ─── Start background tasks ───────────────────────────────────────────
    alerting_task = asyncio.create_task(
        _alerting_service.monitor_loop(get_queue_depth=lambda: _job_queue.pending_count)
    )
    auto_scale_task = asyncio.create_task(_auto_scale_loop())

    logger.info("Server started — local pipeline mode")
    logger.info("Background tasks started: AlertingService, AutoScaleAdvisor")

    yield

    # ─── Cancel background tasks on shutdown ──────────────────────────────
    alerting_task.cancel()
    auto_scale_task.cancel()
    for task in (alerting_task, auto_scale_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("Server stopped — background tasks cancelled")


app = FastAPI(
    title="AutoCliper Backend",
    description="Pipeline otomatis konversi YouTube → klip pendek viral. "
    "Semua processing lokal: YouTube Transcript → Gemini → FFmpeg trim → Whisper word-level.",
    version="0.4.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://100.64.5.96:3001",
        "http://100.64.5.96:3000",
        "http://192.168.168.58:3001",
        "http://192.168.168.58:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(progress_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(preview_router, prefix="/api")
app.include_router(brolls_router)
app.include_router(monitoring_router)
# v3.0 Remotion integration
app.include_router(styles_router, prefix="/api")
app.include_router(remotion_router, prefix="/api")
app.include_router(transcript_router, prefix="/api")
app.include_router(presets_router, prefix="/api")
app.include_router(storage_router, prefix="/api")
app.include_router(features_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.4.0", "mode": "local"}
