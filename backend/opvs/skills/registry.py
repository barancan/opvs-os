from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.project_skill import ProjectSkill
from opvs.skills.base import SkillBase, ToolDefinition
from opvs.skills.linear import LinearSkill
from opvs.skills.workspace import WorkspaceSkill

# All available skills — add new skills here
ALL_SKILLS: list[SkillBase] = [
    WorkspaceSkill(),
    LinearSkill(),
]

SKILL_MAP: dict[str, SkillBase] = {s.skill_id: s for s in ALL_SKILLS}


async def get_enabled_skills(
    db: AsyncSession,
    project_id: int,
    api_keys: dict[str, str],
) -> list[SkillBase]:
    """
    Return skills that are:
    1. Workspace skill — always enabled, no DB check needed
    2. Other skills — enabled in project_skills table AND have required API key set
    """
    result = await db.execute(
        select(ProjectSkill).where(ProjectSkill.project_id == project_id)
    )
    project_skill_rows = {row.skill_id: row for row in result.scalars().all()}

    enabled: list[SkillBase] = []
    for skill in ALL_SKILLS:
        if skill.skill_id == "workspace":
            enabled.append(skill)
            continue

        # Check project opt-in
        row = project_skill_rows.get(skill.skill_id)
        if row is None or not row.enabled:
            continue

        # Check API key configured
        if skill.requires_setting:
            if not api_keys.get(skill.requires_setting, "").strip():
                continue

        enabled.append(skill)

    return enabled


def get_all_tool_definitions(skills: list[SkillBase]) -> list[dict[str, object]]:
    """Convert SkillBase tool definitions to Anthropic API format."""
    tools: list[dict[str, object]] = []
    for skill in skills:
        for tool_def in skill.get_tool_definitions():
            tools.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "input_schema": tool_def.input_schema,
            })
    return tools


def find_tool(
    tool_name: str, skills: list[SkillBase]
) -> tuple[SkillBase, ToolDefinition] | None:
    """Find which skill owns a tool name and return (skill, definition)."""
    for skill in skills:
        for tool_def in skill.get_tool_definitions():
            if tool_def.name == tool_name:
                return (skill, tool_def)
    return None
