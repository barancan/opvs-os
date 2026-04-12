"""
APScheduler setup and job execution for opvs OS scheduled jobs.

Jobs stored in SQLite are loaded on startup and registered with APScheduler.
When a job fires, it runs the orchestrator's send_message with the job's prompt,
using a synthetic client_id so tokens stream to any connected client.
"""
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Module-level scheduler instance
scheduler = AsyncIOScheduler()


def get_scheduler() -> AsyncIOScheduler:
    return scheduler


async def start_scheduler(app_instance: object) -> None:
    """Start scheduler and load all active jobs from DB."""
    from sqlalchemy import select

    from opvs.database import AsyncSessionLocal
    from opvs.models.scheduled_job import JobStatus, ScheduledJob

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledJob).where(ScheduledJob.status == JobStatus.ACTIVE)
        )
        jobs = list(result.scalars().all())

    for job in jobs:
        _register_job(job.id, job.cron, job.timezone, job.project_id, job.prompt)

    scheduler.start()
    logger.info("Scheduler started with %d active jobs", len(jobs))


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _register_job(
    job_id: int,
    cron: str,
    timezone: str,
    project_id: int,
    prompt: str,
) -> None:
    """Register a single job with APScheduler."""
    parts = cron.split()
    trigger = CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        timezone=timezone,
    )
    scheduler.add_job(
        _execute_job,
        trigger=trigger,
        id=f"job_{job_id}",
        args=[job_id, project_id, prompt],
        replace_existing=True,
        misfire_grace_time=300,  # 5 min grace if server was down
    )


def _remove_job(job_id: int) -> None:
    job_key = f"job_{job_id}"
    if scheduler.get_job(job_key):
        scheduler.remove_job(job_key)


async def _execute_job(job_id: int, project_id: int, prompt: str) -> None:
    """
    Called by APScheduler when a job fires.
    Runs the orchestrator agentic loop with the job's prompt.
    Creates a notification with the result.
    """
    from sqlalchemy import select

    from opvs.database import AsyncSessionLocal
    from opvs.models.notification import NotificationSourceType
    from opvs.models.scheduled_job import ScheduledJob
    from opvs.schemas.notification import NotificationCreate
    from opvs.services import orchestrator_service
    from opvs.services.notification_service import create_notification
    from opvs.websocket import (
        WS_JOB_COMPLETED,
        WS_JOB_FAILED,
        WS_JOB_STARTED,
        manager,
    )

    client_id = f"job_{job_id}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    async with AsyncSessionLocal() as db:
        # Broadcast job started
        await manager.broadcast(WS_JOB_STARTED, {"job_id": job_id, "project_id": project_id})

        # Fetch job and update last_run_at
        result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return

        job_name = job.name
        job.last_run_at = datetime.now(UTC)
        job.last_run_status = "running"
        await db.commit()

        try:
            # Run the orchestrator agentic loop
            message = await orchestrator_service.send_message(
                db=db,
                user_content=f"[Scheduled job: {job_name}]\n\n{prompt}",
                client_id=client_id,
                project_id=project_id,
            )

            # Mark success
            job.last_run_status = "success"
            await db.commit()

            # Create notification with result
            await create_notification(
                db,
                NotificationCreate(
                    title=f"Job complete: {job_name}",
                    body=message.content[:500],
                    source_type=NotificationSourceType.JOB,
                    job_id=str(job_id),
                    project_id=project_id,
                ),
            )
            await db.commit()

            await manager.broadcast(
                WS_JOB_COMPLETED,
                {"job_id": job_id, "project_id": project_id},
            )

        except Exception as e:
            logger.error("Job %d failed: %s", job_id, e)

            job.last_run_status = "failed"
            await db.commit()

            await create_notification(
                db,
                NotificationCreate(
                    title=f"Job failed: {job_name}",
                    body=str(e)[:300],
                    source_type=NotificationSourceType.JOB,
                    job_id=str(job_id),
                    project_id=project_id,
                    priority=5,
                ),
            )
            await db.commit()

            await manager.broadcast(
                WS_JOB_FAILED,
                {"job_id": job_id, "project_id": project_id, "error": str(e)[:200]},
            )
