from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """Anthropic tool definition format."""

    name: str
    description: str
    input_schema: dict[str, Any]
    requires_approval: bool = False  # True for all write operations


@dataclass
class ToolResult:
    """Result returned from tool execution."""

    success: bool
    content: str  # human-readable result for Claude
    data: dict[str, Any] = field(default_factory=dict)  # structured data


class SkillBase:
    """
    Base class for all skills.

    Subclasses define:
    - skill_id: str — unique identifier (e.g. "linear")
    - display_name: str — shown in UI (e.g. "Linear")
    - requires_setting: str | None — settings key that must be non-empty to use
      (e.g. "linear_api_key"). None = always available.
    - get_tool_definitions() -> list[ToolDefinition]
    - execute_tool(tool_name, inputs, context) -> ToolResult
    """

    skill_id: str = ""
    display_name: str = ""
    requires_setting: str | None = None

    def get_tool_definitions(self) -> list[ToolDefinition]:
        raise NotImplementedError

    async def execute_tool(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        context: SkillContext,
    ) -> ToolResult:
        raise NotImplementedError


@dataclass
class SkillContext:
    """Runtime context passed to skill execute_tool calls."""

    api_keys: dict[str, str]  # all saved API keys
    workspace_path: str  # absolute workspace path
    project_slug: str  # active project slug
    project_id: int  # active project ID
