from datetime import datetime

from pydantic import BaseModel, ConfigDict

from opvs.models.agent_message import SenderType


class AgentMessageCreate(BaseModel):
    project_id: int
    session_uuid: str | None = None
    sender_type: SenderType
    sender_name: str
    content: str
    requires_response: bool = False
    reply_to_id: int | None = None


class AgentMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    session_uuid: str | None
    sender_type: SenderType
    sender_name: str
    content: str
    requires_response: bool
    response_provided: bool
    reply_to_id: int | None
    created_at: datetime
