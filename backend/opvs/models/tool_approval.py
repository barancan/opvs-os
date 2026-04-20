from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from opvs.database import Base


class ToolApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ToolApprovalSource(StrEnum):
    ORCHESTRATOR = "orchestrator"
    AGENT = "agent"


class ToolApproval(Base):
    __tablename__ = "tool_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # UUID assigned by the requesting loop; used as the correlation key
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON-encoded dict of tool input parameters
    parameters: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[ToolApprovalStatus] = mapped_column(
        Enum(ToolApprovalStatus),
        default=ToolApprovalStatus.PENDING,
        nullable=False,
    )
    source: Mapped[ToolApprovalSource] = mapped_column(
        Enum(ToolApprovalSource), nullable=False
    )
    # Nullable: only set for agent-originated approvals
    session_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Hard deadline; anything PENDING past this is expired on restart
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
