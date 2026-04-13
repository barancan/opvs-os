from datetime import datetime

from pydantic import BaseModel, ConfigDict

from opvs.models.agent_session import SessionStatus


class AgentSessionCreate(BaseModel):
    project_id: int
    persona_id: int
    task: str


class AgentSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_uuid: str
    project_id: int
    persona_id: int
    persona_name: str
    task: str
    status: SessionStatus
    model_snapshot: str
    total_tokens: int
    result_summary: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
