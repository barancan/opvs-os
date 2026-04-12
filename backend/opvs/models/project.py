from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opvs.database import Base


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Explicit join condition required because project_id has no FK declaration
    # (FK constraint added in Phase 3)
    linear_links: Mapped[list["ProjectLinearLink"]] = relationship(
        "ProjectLinearLink",
        primaryjoin="ProjectLinearLink.project_id == Project.id",
        foreign_keys="[ProjectLinearLink.project_id]",
        cascade="all, delete-orphan",
    )


class ProjectLinearLink(Base):
    __tablename__ = "project_linear_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # No FK constraint yet — added in Phase 3 once project IDs are stable
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    linear_project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    linear_project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(
        "Project",
        primaryjoin="ProjectLinearLink.project_id == Project.id",
        foreign_keys="[ProjectLinearLink.project_id]",
        overlaps="linear_links",
    )
