"""
Tests for the skills framework — Part 1 (backend/opvs/tests/test_skills.py)

Tests:
 1.  WorkspaceSkill._resolve_safe returns None for ../../../etc/passwd
 2.  WorkspaceSkill._resolve_safe returns valid path for _memory/stm/current.md
 3.  workspace_list_files returns file list for valid directory
 4.  workspace_capture creates a file in inbox with correct content
 5.  GET /api/projects/{id}/skills returns workspace as always_on=True, enabled=True
 6.  GET /api/projects/{id}/skills returns linear as enabled=False by default
 7.  PUT /api/projects/{id}/skills/linear?enabled=true enables it
 8.  GET /api/projects/{id}/skills after enable returns linear as enabled=True
 9.  PUT /api/projects/{id}/skills/workspace?enabled=false still returns enabled=True (always_on)
10.  LinearSkill.get_tool_definitions — all read tools have requires_approval=False
11.  LinearSkill.get_tool_definitions — all write tools have requires_approval=True
12.  workspace_write_ltm creates a new LTM page in the correct section
13.  workspace_write_ltm appends to an existing LTM page
14.  workspace_write_ltm updates INDEX.md with a wikilink entry
15.  workspace_write_ltm rejects invalid section names
16.  workspace_write_ltm has requires_approval=True
"""

import pathlib

import pytest
from httpx import AsyncClient

from opvs.skills.base import SkillContext
from opvs.skills.linear import LinearSkill
from opvs.skills.workspace import WorkspaceSkill

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

READ_TOOL_NAMES = {
    "linear_list_teams",
    "linear_list_projects",
    "linear_list_issues",
    "linear_get_issue",
    "linear_search_issues",
}

WRITE_TOOL_NAMES = {
    "linear_create_issue",
    "linear_update_issue",
    "linear_create_comment",
}


# ---------------------------------------------------------------------------
# 1. _resolve_safe rejects path traversal
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolve_safe_rejects_traversal(tmp_path: pathlib.Path) -> None:
    skill = WorkspaceSkill()
    result = skill._resolve_safe(tmp_path, "../../../etc/passwd")
    assert result is None


# ---------------------------------------------------------------------------
# 2. _resolve_safe accepts valid sub-path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolve_safe_accepts_valid_path(tmp_path: pathlib.Path) -> None:
    skill = WorkspaceSkill()
    # File doesn't need to exist for _resolve_safe; it just checks containment
    result = skill._resolve_safe(tmp_path, "_memory/stm/current.md")
    assert result is not None
    assert str(result).startswith(str(tmp_path.resolve()))


# ---------------------------------------------------------------------------
# 3. workspace_list_files returns file list for valid directory
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_list_files_valid(tmp_path: pathlib.Path) -> None:
    # Create a fake project root inside tmp_path
    project_root = tmp_path / "projects" / "my-project"
    project_root.mkdir(parents=True)
    (project_root / "README.md").write_text("hello")
    (project_root / "subdir").mkdir()

    skill = WorkspaceSkill()
    context = SkillContext(
        api_keys={},
        workspace_path=str(tmp_path),
        project_slug="my-project",
        project_id=1,
    )
    result = await skill.execute_tool("workspace_list_files", {}, context)

    assert result.success is True
    assert "README.md" in result.content
    assert "[dir]" in result.content


# ---------------------------------------------------------------------------
# 4. workspace_capture creates file in inbox with correct content
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_capture_creates_file(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "projects" / "my-project"
    project_root.mkdir(parents=True)

    skill = WorkspaceSkill()
    context = SkillContext(
        api_keys={},
        workspace_path=str(tmp_path),
        project_slug="my-project",
        project_id=1,
    )
    result = await skill.execute_tool(
        "workspace_capture",
        {"title": "Test Note", "content": "Some insight here."},
        context,
    )

    assert result.success is True
    inbox = project_root / "_memory" / "inbox"
    files = list(inbox.iterdir())
    assert len(files) == 1
    text = files[0].read_text()
    assert "Test Note" in text
    assert "Some insight here." in text


# ---------------------------------------------------------------------------
# 5. GET /api/projects/{id}/skills — workspace always_on=True, enabled=True
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_skills_workspace_always_on(client: AsyncClient) -> None:
    # Create a project first
    resp = await client.post("/api/projects", json={"name": "Skills Test"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    resp = await client.get(f"/api/projects/{project_id}/skills")
    assert resp.status_code == 200
    skills = resp.json()
    workspace = next(s for s in skills if s["skill_id"] == "workspace")
    assert workspace["always_on"] is True
    assert workspace["enabled"] is True


# ---------------------------------------------------------------------------
# 6. GET /api/projects/{id}/skills — linear disabled by default
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_skills_linear_disabled_by_default(client: AsyncClient) -> None:
    resp = await client.post("/api/projects", json={"name": "Skills Test 2"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    resp = await client.get(f"/api/projects/{project_id}/skills")
    assert resp.status_code == 200
    skills = resp.json()
    linear = next(s for s in skills if s["skill_id"] == "linear")
    assert linear["enabled"] is False
    assert linear["always_on"] is False


# ---------------------------------------------------------------------------
# 7. PUT /api/projects/{id}/skills/linear?enabled=true enables linear
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enable_linear_skill(client: AsyncClient) -> None:
    resp = await client.post("/api/projects", json={"name": "Skills Test 3"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    resp = await client.put(f"/api/projects/{project_id}/skills/linear?enabled=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_id"] == "linear"
    assert data["enabled"] is True


# ---------------------------------------------------------------------------
# 8. GET after enable returns linear as enabled=True
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_skills_after_enable(client: AsyncClient) -> None:
    resp = await client.post("/api/projects", json={"name": "Skills Test 4"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    await client.put(f"/api/projects/{project_id}/skills/linear?enabled=true")

    resp = await client.get(f"/api/projects/{project_id}/skills")
    assert resp.status_code == 200
    skills = resp.json()
    linear = next(s for s in skills if s["skill_id"] == "linear")
    assert linear["enabled"] is True


# ---------------------------------------------------------------------------
# 9. PUT workspace?enabled=false still returns enabled=True (always_on)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_always_on_cannot_be_disabled(client: AsyncClient) -> None:
    resp = await client.post("/api/projects", json={"name": "Skills Test 5"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    resp = await client.put(f"/api/projects/{project_id}/skills/workspace?enabled=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["always_on"] is True


# ---------------------------------------------------------------------------
# 12. workspace_write_ltm creates a new LTM page in the correct section
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_ltm_creates_new_page(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "projects" / "my-project"
    project_root.mkdir(parents=True)

    skill = WorkspaceSkill()
    context = SkillContext(
        api_keys={},
        workspace_path=str(tmp_path),
        project_slug="my-project",
        project_id=1,
    )
    result = await skill.execute_tool(
        "workspace_write_ltm",
        {
            "section": "research",
            "filename": "stablecoin-latam",
            "title": "Stablecoin LATAM Research",
            "content": "Key finding: adoption is growing in Brazil.",
        },
        context,
    )

    assert result.success is True
    assert "created" in result.content
    ltm_file = project_root / "_memory" / "research" / "stablecoin-latam.md"
    assert ltm_file.exists()
    text = ltm_file.read_text()
    assert "Stablecoin LATAM Research" in text
    assert "adoption is growing in Brazil" in text


# ---------------------------------------------------------------------------
# 13. workspace_write_ltm appends to an existing LTM page
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_ltm_appends_to_existing_page(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "projects" / "my-project"
    (project_root / "_memory" / "decisions").mkdir(parents=True)
    existing_file = project_root / "_memory" / "decisions" / "payment-flow.md"
    existing_file.write_text("# Payment Flow\n\nOriginal content.\n")

    skill = WorkspaceSkill()
    context = SkillContext(
        api_keys={},
        workspace_path=str(tmp_path),
        project_slug="my-project",
        project_id=1,
    )
    result = await skill.execute_tool(
        "workspace_write_ltm",
        {
            "section": "decisions",
            "filename": "payment-flow",
            "title": "Payment Flow",
            "content": "New addendum: switched to Stripe.",
        },
        context,
    )

    assert result.success is True
    assert "appended to" in result.content
    text = existing_file.read_text()
    assert "Original content." in text
    assert "New addendum: switched to Stripe." in text


# ---------------------------------------------------------------------------
# 14. workspace_write_ltm updates INDEX.md with a wikilink entry
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_ltm_updates_index(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "projects" / "my-project"
    (project_root / "_memory").mkdir(parents=True)
    index_file = project_root / "_memory" / "INDEX.md"
    index_file.write_text("# Memory Index\n\n## Research\n\n## Decisions\n")

    skill = WorkspaceSkill()
    context = SkillContext(
        api_keys={},
        workspace_path=str(tmp_path),
        project_slug="my-project",
        project_id=1,
    )
    await skill.execute_tool(
        "workspace_write_ltm",
        {
            "section": "research",
            "filename": "market-analysis",
            "title": "Market Analysis",
            "content": "Details here.",
        },
        context,
    )

    index_text = index_file.read_text()
    assert "[[research/market-analysis]]" in index_text
    assert "Market Analysis" in index_text


# ---------------------------------------------------------------------------
# 15. workspace_write_ltm rejects invalid section names
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_ltm_rejects_invalid_section(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "projects" / "my-project"
    project_root.mkdir(parents=True)

    skill = WorkspaceSkill()
    context = SkillContext(
        api_keys={},
        workspace_path=str(tmp_path),
        project_slug="my-project",
        project_id=1,
    )
    result = await skill.execute_tool(
        "workspace_write_ltm",
        {
            "section": "secrets",
            "filename": "passwords",
            "title": "Passwords",
            "content": "hunter2",
        },
        context,
    )

    assert result.success is False
    assert "Invalid section" in result.content


# ---------------------------------------------------------------------------
# 16. workspace_write_ltm has requires_approval=True
# ---------------------------------------------------------------------------
def test_write_ltm_requires_approval() -> None:
    skill = WorkspaceSkill()
    tool_defs = skill.get_tool_definitions()
    ltm_tool = next(t for t in tool_defs if t.name == "workspace_write_ltm")
    assert ltm_tool.requires_approval is True


# ---------------------------------------------------------------------------
# 10. LinearSkill read tools have requires_approval=False
# ---------------------------------------------------------------------------
def test_linear_read_tools_no_approval() -> None:
    skill = LinearSkill()
    tool_defs = skill.get_tool_definitions()
    for tool_def in tool_defs:
        if tool_def.name in READ_TOOL_NAMES:
            assert tool_def.requires_approval is False, (
                f"{tool_def.name} should have requires_approval=False"
            )


# ---------------------------------------------------------------------------
# 11. LinearSkill write tools have requires_approval=True
# ---------------------------------------------------------------------------
def test_linear_write_tools_require_approval() -> None:
    skill = LinearSkill()
    tool_defs = skill.get_tool_definitions()
    for tool_def in tool_defs:
        if tool_def.name in WRITE_TOOL_NAMES:
            assert tool_def.requires_approval is True, (
                f"{tool_def.name} should have requires_approval=True"
            )
