import pathlib
import re
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.config import settings as app_settings
from opvs.database import get_db
from opvs.schemas.notification import NotificationCreate
from opvs.services import notification_service, project_service
from opvs.services.settings_service import get_setting

router = APIRouter(prefix="/api/projects", tags=["workspace"])

_VALID_SECTIONS = {"decisions", "research", "people", "concepts", "patterns"}
_MAX_INGEST_BYTES = 512 * 1024  # 512 KB


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WorkspaceNode(BaseModel):
    path: str
    name: str
    type: Literal["file", "dir"]
    children: list["WorkspaceNode"] | None = None


class WorkspaceTreeResponse(BaseModel):
    nodes: list[WorkspaceNode]


class WorkspaceFileResponse(BaseModel):
    path: str
    content: str


class WorkspaceFileWrite(BaseModel):
    path: str
    content: str


class WorkspaceFileSaveResponse(BaseModel):
    path: str
    saved: bool


class WorkspaceIngestResponse(BaseModel):
    imported: list[str]
    skipped: list[str]
    errors: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_project_root(project_id: int, db: AsyncSession) -> pathlib.Path:
    project = await project_service.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    setting = await get_setting(db, "workspace_path")
    wp = str(setting.value) if setting else app_settings.workspace_path
    return pathlib.Path(wp) / "projects" / project.slug


def _resolve_safe(
    project_root: pathlib.Path, relative_path: str
) -> pathlib.Path | None:
    """Resolve path and verify it stays within project_root. Returns None if unsafe."""
    try:
        resolved = (project_root / relative_path).resolve()
        project_resolved = project_root.resolve()
        resolved.relative_to(project_resolved)
        return resolved
    except (ValueError, Exception):
        return None


def _build_node(
    abs_path: pathlib.Path, project_root: pathlib.Path, depth: int = 0
) -> WorkspaceNode:
    rel = str(abs_path.relative_to(project_root))
    if abs_path.is_dir() and depth < 5:
        children = [
            _build_node(child, project_root, depth + 1)
            for child in sorted(abs_path.iterdir())
        ][:100]  # cap at 100 entries per directory
        return WorkspaceNode(path=rel, name=abs_path.name, type="dir", children=children)
    return WorkspaceNode(path=rel, name=abs_path.name, type="file")


def _regenerate_index(project_root: pathlib.Path) -> None:
    """Rebuild _memory/INDEX.md from current LTM section contents."""
    memory = project_root / "_memory"
    sections = ["decisions", "research", "people", "concepts", "patterns"]

    parts: list[str] = [
        "# Project Memory Index\n\n",
        "Entry point for this project's long-term memory wiki.\n",
        "All links use Obsidian `[[wikilinks]]` format.\n\n",
        "## Short-term memory\n\n",
        "[[stm/current]]\n\n",
    ]

    for section in sections:
        parts.append(f"## {section.capitalize()}\n\n")
        section_dir = memory / section
        if section_dir.exists():
            md_files = sorted(section_dir.glob("*.md"))
            if md_files:
                for f in md_files:
                    first_line = f.read_text(encoding="utf-8").split("\n")[0].lstrip("# ").strip()
                    title = first_line if first_line else f.stem
                    parts.append(f"- [[{section}/{f.stem}]] — {title}\n")
            else:
                parts.append("*(No entries yet)*\n")
        else:
            parts.append("*(No entries yet)*\n")
        parts.append("\n")

    parts.extend([
        "## Session summaries\n\n*(Add links as agent sessions complete)*\n\n",
        "## Inbox\n\nUnreviewed orchestrator captures: `_memory/inbox/`\n",
    ])

    (memory / "INDEX.md").write_text("".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{project_id}/workspace/tree", response_model=WorkspaceTreeResponse)
async def get_workspace_tree(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> WorkspaceTreeResponse:
    project_root = await _get_project_root(project_id, db)
    if not project_root.exists():
        return WorkspaceTreeResponse(nodes=[])

    nodes: list[WorkspaceNode] = []

    ctx = project_root / "CONTEXT.md"
    if ctx.exists():
        nodes.append(WorkspaceNode(path="CONTEXT.md", name="CONTEXT.md", type="file"))

    memory = project_root / "_memory"
    if memory.exists():
        nodes.append(_build_node(memory, project_root))

    return WorkspaceTreeResponse(nodes=nodes)


@router.get("/{project_id}/workspace/file", response_model=WorkspaceFileResponse)
async def get_workspace_file(
    project_id: int,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceFileResponse:
    project_root = await _get_project_root(project_id, db)
    resolved = _resolve_safe(project_root, path)
    if resolved is None:
        raise HTTPException(status_code=400, detail="Invalid or unsafe path")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Path is a directory, not a file")

    return WorkspaceFileResponse(path=path, content=resolved.read_text(encoding="utf-8"))


@router.put("/{project_id}/workspace/file", response_model=WorkspaceFileSaveResponse)
async def put_workspace_file(
    project_id: int,
    body: WorkspaceFileWrite,
    db: AsyncSession = Depends(get_db),
) -> WorkspaceFileSaveResponse:
    if not body.path.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files may be edited")

    project_root = await _get_project_root(project_id, db)
    resolved = _resolve_safe(project_root, body.path)
    if resolved is None:
        raise HTTPException(status_code=400, detail="Invalid or unsafe path")
    if not resolved.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found — use ingest to create new files",
        )

    resolved.write_text(body.content, encoding="utf-8")
    return WorkspaceFileSaveResponse(path=body.path, saved=True)


@router.post("/{project_id}/workspace/ingest", response_model=WorkspaceIngestResponse)
async def ingest_workspace_files(
    project_id: int,
    section: str = Form(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceIngestResponse:
    project_root = await _get_project_root(project_id, db)

    if section not in _VALID_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid section '{section}'. "
                f"Must be one of: {', '.join(sorted(_VALID_SECTIONS))}"
            ),
        )

    section_dir = project_root / "_memory" / section
    section_dir.mkdir(parents=True, exist_ok=True)

    imported: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for upload in files:
        original_name = upload.filename or "unnamed"

        if not original_name.lower().endswith(".md"):
            skipped.append(f"{original_name} (not a .md file)")
            continue

        data = await upload.read()

        if len(data) > _MAX_INGEST_BYTES:
            skipped.append(f"{original_name} (exceeds 512 KB limit)")
            continue

        stem = pathlib.Path(original_name).stem
        safe_stem = re.sub(r"[^\w\-]", "-", stem).strip("-")[:80]
        if not safe_stem:
            errors.append(f"{original_name} (could not derive safe filename)")
            continue

        resolved_dest = _resolve_safe(project_root, f"_memory/{section}/{safe_stem}.md")
        if resolved_dest is None:
            errors.append(f"{original_name} (unsafe resolved path)")
            continue

        try:
            resolved_dest.write_bytes(data)
            imported.append(f"{safe_stem}.md")
        except OSError as exc:
            errors.append(f"{original_name} ({type(exc).__name__}: {exc})")

    if imported:
        _regenerate_index(project_root)

        body_lines = [f"Imported {len(imported)} file(s) into {section}:"]
        for name in imported:
            body_lines.append(f"  \u2022 {name}")
        if skipped:
            body_lines.append(f"\nSkipped: {', '.join(skipped)}")

        await notification_service.create_notification(
            db,
            NotificationCreate(
                title=f"Memory imported: {section} ({len(imported)} files)",
                body="\n".join(body_lines),
                project_id=project_id,
            ),
        )
        await db.commit()

    return WorkspaceIngestResponse(
        imported=imported,
        skipped=skipped,
        errors=errors,
    )
