from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from opvs.models.scheduled_job import JobStatus


class ScheduledJobCreate(BaseModel):
    project_id: int
    name: str
    description: str | None = None
    cron: str
    timezone: str = "UTC"
    prompt: str

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError("Cron must have 5 fields: minute hour day month weekday")
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class ScheduledJobUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    cron: str | None = None
    timezone: str | None = None
    prompt: str | None = None
    status: JobStatus | None = None


class ScheduledJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str | None
    cron: str
    timezone: str
    prompt: str
    status: JobStatus
    last_run_at: datetime | None
    last_run_status: str | None
    created_at: datetime
    updated_at: datetime
