"""JobRepository — SQLAlchemy implementation of IJobRepository."""
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update

from src.config import settings
from src.domain.entities import Job, JobStatus
from src.domain.interfaces import IJobRepository
from src.infrastructure.database import JobModel, async_session


class JobRepository(IJobRepository):
    async def create(self, job: Job) -> Job:
        async with async_session() as session:
            model = JobModel(
                job_id=job.job_id,
                youtube_url=job.youtube_url,
                status=job.status.value,
                video_duration=job.video_duration,
                style_preset=job.style_preset,
                target_aspect_ratio=job.target_aspect_ratio,
                hook_engine=job.hook_engine,
                hook_style=job.hook_style,
                broll_enabled=int(job.broll_enabled),
                autogrid_enabled=int(job.autogrid_enabled),
                # v3.0 Remotion fields
                use_remotion=int(job.use_remotion),
                ai_layer_enabled=int(job.ai_layer_enabled),
                threejs_enabled=int(job.threejs_enabled),
                remotion_quality=job.remotion_quality,
                user_id=job.user_id,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            job.created_at = model.created_at
            job.updated_at = model.updated_at
            return job

    async def get_by_job_id(self, job_id: str) -> Optional[Job]:
        async with async_session() as session:
            result = await session.execute(
                select(JobModel).where(JobModel.job_id == job_id)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._to_entity(model)

    async def update_status(
        self, job_id: str, status: JobStatus, error_message: Optional[str] = None
    ) -> None:
        async with async_session() as session:
            values: dict = {"status": status.value, "updated_at": datetime.utcnow()}
            if error_message is not None:
                values["error_message"] = error_message
            await session.execute(
                update(JobModel).where(JobModel.job_id == job_id).values(**values)
            )
            await session.commit()

    async def update_render_progress(self, job_id: str, progress: str) -> None:
        async with async_session() as session:
            await session.execute(
                update(JobModel)
                .where(JobModel.job_id == job_id)
                .values(render_progress=progress, updated_at=datetime.utcnow())
            )
            await session.commit()

    async def update_clips_count(
        self, job_id: str, total: int, success: int, failed: int
    ) -> None:
        async with async_session() as session:
            await session.execute(
                update(JobModel)
                .where(JobModel.job_id == job_id)
                .values(
                    clips_total=total,
                    clips_success=success,
                    clips_failed=failed,
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()

    async def update_video_title(self, job_id: str, title: str) -> None:
        async with async_session() as session:
            await session.execute(
                update(JobModel)
                .where(JobModel.job_id == job_id)
                .values(video_title=title, updated_at=datetime.utcnow())
            )
            await session.commit()

    async def update_clips_data(self, job_id: str, clips_data: dict) -> None:
        async with async_session() as session:
            await session.execute(
                update(JobModel)
                .where(JobModel.job_id == job_id)
                .values(clips_data=clips_data, updated_at=datetime.utcnow())
            )
            await session.commit()

    async def get_by_url_active(self, url: str) -> Optional[Job]:
        """Cari job aktif (bukan completed/failed/timeout) dengan URL yang sama."""
        terminal_statuses = [
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.TIMEOUT.value,
        ]
        async with async_session() as session:
            result = await session.execute(
                select(JobModel)
                .where(JobModel.youtube_url == url)
                .where(JobModel.status.notin_(terminal_statuses))
                .order_by(JobModel.created_at.desc())
                .limit(1)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return self._to_entity(model)

    def _to_entity(self, model: JobModel) -> Job:
        return Job(
            job_id=model.job_id,
            youtube_url=model.youtube_url,
            status=JobStatus(model.status),
            video_duration=model.video_duration,
            render_progress=model.render_progress,
            error_message=model.error_message,
            error_details=model.error_details,
            clips_data=model.clips_data,
            clips_total=model.clips_total,
            clips_success=model.clips_success,
            clips_failed=model.clips_failed,
            style_preset=model.style_preset or settings.DEFAULT_STYLE_PRESET,
            target_aspect_ratio=model.target_aspect_ratio or "9:16",
            hook_engine=model.hook_engine or "v3",
            hook_style=model.hook_style or "",
            broll_enabled=bool(model.broll_enabled),
            autogrid_enabled=bool(model.autogrid_enabled),
            use_remotion=bool(model.use_remotion),
            ai_layer_enabled=bool(model.ai_layer_enabled),
            threejs_enabled=bool(model.threejs_enabled),
            scene_graphs=model.scene_graphs,
            remotion_quality=model.remotion_quality or "medium",
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
