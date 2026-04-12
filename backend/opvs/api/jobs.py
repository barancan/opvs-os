from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import get_db
from opvs.models.scheduled_job import JobStatus
from opvs.schemas.scheduled_job import (
    ScheduledJobCreate,
    ScheduledJobResponse,
    ScheduledJobUpdate,
)
from opvs.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[ScheduledJobResponse])
async def list_jobs(
    project_id: int | None = Query(default=None),
    status: JobStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduledJobResponse]:
    jobs = await job_service.list_jobs(db, project_id=project_id, status=status)
    return [ScheduledJobResponse.model_validate(j) for j in jobs]


@router.post("", response_model=ScheduledJobResponse, status_code=201)
async def create_job(
    data: ScheduledJobCreate,
    db: AsyncSession = Depends(get_db),
) -> ScheduledJobResponse:
    job = await job_service.create_job(db, data)
    return ScheduledJobResponse.model_validate(job)


@router.get("/{job_id}", response_model=ScheduledJobResponse)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> ScheduledJobResponse:
    job = await job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return ScheduledJobResponse.model_validate(job)


@router.put("/{job_id}", response_model=ScheduledJobResponse)
async def update_job(
    job_id: int,
    data: ScheduledJobUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScheduledJobResponse:
    job = await job_service.update_job(db, job_id, data)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return ScheduledJobResponse.model_validate(job)


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    deleted = await job_service.delete_job(db, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True}


@router.post("/{job_id}/run")
async def run_job_now(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Trigger a job immediately regardless of schedule."""
    success = await job_service.run_job_now(db, job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "triggered"}
