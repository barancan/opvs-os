from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from opvs.database import Base


class SessionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"      # waiting for user/agent response in chatroom
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"        # stopped by user (not kill switch)


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # UUID string used as the session directory name and WS client_id
    session_uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    persona_id: Mapped[int] = mapped_column(Integer, nullable=False)
    persona_name: Mapped[str] = mapped_column(String(255), nullable=False)  # snapshot at run time
    task: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus), default=SessionStatus.QUEUED, nullable=False
    )
    # Snapshot of persona config at run time (so edits don't affect running sessions)
    model_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    instructions_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    enabled_skills_snapshot: Mapped[str] = mapped_column(String(512), nullable=False)
    temperature_snapshot: Mapped[float] = mapped_column(Float, nullable=False)
    max_tokens_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    # Token usage
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Result summary written on completion
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
