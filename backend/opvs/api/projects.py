from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.config import settings as app_settings
from opvs.database import get_db
from opvs.models.project import ProjectStatus
from opvs.schemas.project import (
    LinearLinkCreate,
    LinearLinkResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from opvs.services import project_service
from opvs.services.settings_service import get_setting

router = APIRouter(prefix="/api/projects", tags=["projects"])


async def _workspace_path(db: AsyncSession) -> str:
    setting = await get_setting(db, "workspace_path")
    return str(setting.value) if setting else app_settings.workspace_path


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    status: ProjectStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    projects = await project_service.list_projects(db, status=status)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    wp = await _workspace_path(db)
    project = await project_service.create_project(db, data, workspace_path=wp)
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await project_service.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await project_service.update_project(db, project_id, data)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(project)


@router.post("/{project_id}/linear-links", response_model=LinearLinkResponse, status_code=201)
async def add_linear_link(
    project_id: int,
    data: LinearLinkCreate,
    db: AsyncSession = Depends(get_db),
) -> LinearLinkResponse:
    link = await project_service.add_linear_link(db, project_id, data)
    if link is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return LinearLinkResponse.model_validate(link)


@router.delete("/{project_id}/linear-links/{link_id}")
async def remove_linear_link(
    project_id: int,
    link_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    deleted = await project_service.remove_linear_link(db, link_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"deleted": True}
