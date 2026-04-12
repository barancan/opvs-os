from datetime import datetime

from pydantic import BaseModel, ConfigDict

from opvs.models.notification import NotificationSourceType, NotificationStatus


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    status: NotificationStatus
    source_type: NotificationSourceType
    agent_id: str | None
    session_id: str | None
    job_id: str | None
    priority: int
    orchestrator_prioritised: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class NotificationCreate(BaseModel):
    title: str
    body: str
    source_type: NotificationSourceType = NotificationSourceType.SYSTEM
    agent_id: str | None = None
    session_id: str | None = None
    job_id: str | None = None
    priority: int = 0


class NotificationStatusUpdate(BaseModel):
    status: NotificationStatus
