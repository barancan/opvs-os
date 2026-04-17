from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from opvs.database import Base


class SenderType(StrEnum):
    USER = "user"
    AGENT = "agent"
    ORCHESTRATOR = "orchestrator"
    SYSTEM = "system"
    EVENT = "event"  # lightweight tool-status posts, rendered with reduced prominence


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # NULL = global chatroom message; non-null = scoped to a session
    session_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sender_type: Mapped[SenderType] = mapped_column(Enum(SenderType), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # True when agent is waiting for a response to this message
    requires_response: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True once a response has been provided
    response_provided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Optional: reply to another message
    reply_to_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
