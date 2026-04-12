from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.config import settings as app_settings
from opvs.database import get_db
from opvs.models.project import ProjectStatus
from opvs.models.project_skill import ProjectSkill
from opvs.schemas.project import (
    LinearLinkCreate,
    LinearLinkResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from opvs.services import project_service
from opvs.services.settings_service import get_setting
from opvs.skills.registry import ALL_SKILLS, SKILL_MAP

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


@router.get("/{project_id}/skills")
async def list_project_skills(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    """
    Return all available skills with their enabled status for this project.
    Each item: { skill_id, display_name, enabled, always_on, requires_setting,
                 setting_configured: bool }
    """
    result = await db.execute(
        select(ProjectSkill).where(ProjectSkill.project_id == project_id)
    )
    rows = {row.skill_id: row for row in result.scalars().all()}

    response: list[dict[str, object]] = []
    for skill in ALL_SKILLS:
        if skill.skill_id == "workspace":
            response.append({
                "skill_id": skill.skill_id,
                "display_name": skill.display_name,
                "enabled": True,
                "always_on": True,
                "requires_setting": None,
                "setting_configured": True,
            })
            continue

        row = rows.get(skill.skill_id)
        setting_configured = True
        if skill.requires_setting:
            setting = await get_setting(db, skill.requires_setting)
            setting_configured = bool(setting and setting.value.strip())

        response.append({
            "skill_id": skill.skill_id,
            "display_name": skill.display_name,
            "enabled": row.enabled if row else False,
            "always_on": False,
            "requires_setting": skill.requires_setting,
            "setting_configured": setting_configured,
        })

    return response


@router.put("/{project_id}/skills/{skill_id}")
async def set_project_skill(
    project_id: int,
    skill_id: str,
    enabled: bool,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Enable or disable a skill for a project."""
    if skill_id == "workspace":
        return {"skill_id": "workspace", "enabled": True, "always_on": True}

    if skill_id not in SKILL_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown skill: {skill_id}")

    result = await db.execute(
        select(ProjectSkill).where(
            ProjectSkill.project_id == project_id,
            ProjectSkill.skill_id == skill_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = ProjectSkill(project_id=project_id, skill_id=skill_id, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled

    await db.commit()
    return {"skill_id": skill_id, "enabled": enabled, "always_on": False}
