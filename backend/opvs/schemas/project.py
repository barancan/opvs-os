from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from opvs.models.project import ProjectStatus


class LinearLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    linear_project_id: str
    linear_project_name: str
    created_at: datetime


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime
    linear_links: list[LinearLinkResponse] = []


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Project name cannot be empty")
        return v.strip()


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None


class LinearLinkCreate(BaseModel):
    linear_project_id: str
    linear_project_name: str


# keep re importable for service use
__all__ = [
    "LinearLinkResponse",
    "ProjectResponse",
    "ProjectCreate",
    "ProjectUpdate",
    "LinearLinkCreate",
]
