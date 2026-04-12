import pathlib
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from opvs.models.project import Project, ProjectLinearLink, ProjectStatus
from opvs.schemas.project import LinearLinkCreate, ProjectCreate, ProjectUpdate


def _generate_slug(name: str) -> str:
    """Convert a project name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Append a number suffix until the slug is unique."""
    slug = base_slug
    counter = 2
    while True:
        result = await db.execute(select(Project).where(Project.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def _create_project_workspace(workspace_path: str, slug: str) -> None:
    """Create ICM-style workspace directories for a new project. Idempotent."""
    base = pathlib.Path(workspace_path) / "projects" / slug
    memory = base / "_memory"

    # Create all memory subdirectories
    (memory / "stm").mkdir(parents=True, exist_ok=True)
    (memory / "inbox").mkdir(parents=True, exist_ok=True)
    (memory / "decisions").mkdir(parents=True, exist_ok=True)
    (memory / "research").mkdir(parents=True, exist_ok=True)
    (memory / "sessions").mkdir(parents=True, exist_ok=True)
    (base / "sessions").mkdir(parents=True, exist_ok=True)

    context_file = base / "CONTEXT.md"
    if not context_file.exists():
        context_file.write_text(
            "# READ-ONLY — do not modify this file\n\n"
            "# Project Context\n\n"
            "This file provides project-specific context to agents working on this project.\n"
            "Edit this file via the Projects management page in the opvs OS UI.\n\n"
            "## Project instructions\n\n"
            "*(No instructions defined yet. Add project-specific agent guidance here.)*\n",
            encoding="utf-8",
        )

    stm_file = memory / "stm" / "current.md"
    if not stm_file.exists():
        stm_file.write_text(
            "# Short-term memory\n\n*No context has been compacted yet.*\n",
            encoding="utf-8",
        )

    index_file = memory / "INDEX.md"
    if not index_file.exists():
        index_file.write_text(
            "# Project Memory Index\n\n"
            "Entry point for this project's long-term memory wiki.\n"
            "All links use Obsidian `[[wikilinks]]` format.\n\n"
            "## Short-term memory\n\n"
            "[[stm/current]]\n\n"
            "## Decisions\n\n"
            "*(Add links as decision records are created)*\n\n"
            "## Research\n\n"
            "*(Add links as research outputs are promoted from inbox)*\n\n"
            "## Session summaries\n\n"
            "*(Add links as agent sessions complete)*\n\n"
            "## Inbox\n\n"
            "Unreviewed orchestrator captures: `_memory/inbox/`\n",
            encoding="utf-8",
        )


def _ensure_global_memory_structure(workspace_path: str) -> None:
    """
    Ensure the global _memory/ directory has the correct structure.
    Safe to call multiple times — only creates missing directories, always rewrites INDEX.md.
    """
    memory = pathlib.Path(workspace_path) / "_memory"
    (memory / "people").mkdir(parents=True, exist_ok=True)
    (memory / "concepts").mkdir(parents=True, exist_ok=True)
    (memory / "stm").mkdir(parents=True, exist_ok=True)
    (memory / "inbox").mkdir(parents=True, exist_ok=True)

    index_file = memory / "INDEX.md"
    index_file.write_text(
        "# Global Memory Index\n\n"
        "Cross-project knowledge base. Use this for information that applies\n"
        "across multiple projects: people, domain concepts, org context.\n\n"
        "For project-specific memory, see:\n"
        "`workspace/projects/{slug}/_memory/INDEX.md`\n\n"
        "## People\n\n"
        "*(Stakeholders, team members, external contacts)*\n\n"
        "## Concepts\n\n"
        "*(Domain knowledge, frameworks, definitions)*\n\n"
        "## Inbox\n\n"
        "Global unreviewed captures: `_memory/inbox/`\n",
        encoding="utf-8",
    )


async def create_project(
    db: AsyncSession,
    data: ProjectCreate,
    workspace_path: str = "./workspace",
) -> Project:
    # Ensure global memory structure exists (idempotent)
    _ensure_global_memory_structure(workspace_path)

    base_slug = _generate_slug(data.name)
    slug = await _unique_slug(db, base_slug)
    project = Project(name=data.name, slug=slug, description=data.description)
    db.add(project)
    await db.flush()  # get the ID before commit

    _create_project_workspace(workspace_path, slug)

    await db.commit()
    await db.refresh(project)

    # Re-fetch with relationships loaded
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.linear_links))
        .where(Project.id == project.id)
    )
    loaded = result.scalar_one()
    return loaded


async def get_project(db: AsyncSession, project_id: int) -> Project | None:
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.linear_links))
        .where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


async def get_project_by_slug(db: AsyncSession, slug: str) -> Project | None:
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.linear_links))
        .where(Project.slug == slug)
    )
    return result.scalar_one_or_none()


async def list_projects(
    db: AsyncSession,
    status: ProjectStatus | None = None,
) -> list[Project]:
    query = (
        select(Project)
        .options(selectinload(Project.linear_links))
        .order_by(Project.created_at.asc())
    )
    if status is not None:
        query = query.where(Project.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_project(
    db: AsyncSession,
    project_id: int,
    data: ProjectUpdate,
) -> Project | None:
    project = await get_project(db, project_id)
    if project is None:
        return None
    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    if data.status is not None:
        project.status = data.status
    await db.commit()
    await db.refresh(project)
    return project


async def add_linear_link(
    db: AsyncSession,
    project_id: int,
    data: LinearLinkCreate,
) -> ProjectLinearLink | None:
    """Add a Linear project link. Returns None if project not found."""
    project = await get_project(db, project_id)
    if project is None:
        return None
    link = ProjectLinearLink(
        project_id=project_id,
        linear_project_id=data.linear_project_id,
        linear_project_name=data.linear_project_name,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def remove_linear_link(db: AsyncSession, link_id: int) -> bool:
    result = await db.execute(
        select(ProjectLinearLink).where(ProjectLinearLink.id == link_id)
    )
    link = result.scalar_one_or_none()
    if link is None:
        return False
    await db.delete(link)
    await db.commit()
    return True


async def ensure_default_project(
    db: AsyncSession,
    workspace_path: str = "./workspace",
) -> Project:
    """Called on startup. Creates a Default project if none exist."""
    projects = await list_projects(db)
    if projects:
        return projects[0]
    return await create_project(
        db,
        ProjectCreate(name="Default", description="Auto-created default project."),
        workspace_path=workspace_path,
    )
