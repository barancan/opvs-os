import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.scheduled_job import JobStatus, ScheduledJob
from opvs.scheduler import _execute_job, _register_job, _remove_job
from opvs.schemas.scheduled_job import ScheduledJobCreate, ScheduledJobUpdate


async def create_job(db: AsyncSession, data: ScheduledJobCreate) -> ScheduledJob:
    job = ScheduledJob(
        project_id=data.project_id,
        name=data.name,
        description=data.description,
        cron=data.cron,
        timezone=data.timezone,
        prompt=data.prompt,
        status=JobStatus.ACTIVE,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    # Register with scheduler
    _register_job(job.id, job.cron, job.timezone, job.project_id, job.prompt)
    return job


async def list_jobs(
    db: AsyncSession,
    project_id: int | None = None,
    status: JobStatus | None = None,
) -> list[ScheduledJob]:
    query = select(ScheduledJob).order_by(ScheduledJob.created_at.desc())
    if project_id is not None:
        query = query.where(ScheduledJob.project_id == project_id)
    if status is not None:
        query = query.where(ScheduledJob.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_job(db: AsyncSession, job_id: int) -> ScheduledJob | None:
    result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
    return result.scalar_one_or_none()


async def update_job(
    db: AsyncSession, job_id: int, data: ScheduledJobUpdate
) -> ScheduledJob | None:
    job = await get_job(db, job_id)
    if job is None:
        return None

    if data.name is not None:
        job.name = data.name
    if data.description is not None:
        job.description = data.description
    if data.cron is not None:
        job.cron = data.cron
    if data.timezone is not None:
        job.timezone = data.timezone
    if data.prompt is not None:
        job.prompt = data.prompt
    if data.status is not None:
        job.status = data.status

    await db.commit()
    await db.refresh(job)

    # Sync with scheduler
    if job.status == JobStatus.ACTIVE:
        _register_job(job.id, job.cron, job.timezone, job.project_id, job.prompt)
    else:
        _remove_job(job.id)

    return job


async def delete_job(db: AsyncSession, job_id: int) -> bool:
    job = await get_job(db, job_id)
    if job is None:
        return False
    _remove_job(job_id)
    await db.delete(job)
    await db.commit()
    return True


async def run_job_now(db: AsyncSession, job_id: int) -> bool:
    """Trigger a job immediately outside its schedule."""
    job = await get_job(db, job_id)
    if job is None:
        return False
    # Fire and forget — runs in background
    asyncio.create_task(_execute_job(job.id, job.project_id, job.prompt))
    return True
