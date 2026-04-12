from datetime import datetime

from pydantic import BaseModel, ConfigDict

from opvs.models.chat_message import MessageRole


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    token_count: int
    is_compact_summary: bool
    created_at: datetime


class ChatRequest(BaseModel):
    content: str


class CompactStatus(BaseModel):
    total_tokens: int
    threshold: int
    compacted: bool
