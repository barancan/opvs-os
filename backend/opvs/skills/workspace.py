import pathlib
import re
from datetime import datetime
from typing import Any

from opvs.skills.base import SkillBase, SkillContext, ToolDefinition, ToolResult


class WorkspaceSkill(SkillBase):
    skill_id = "workspace"
    display_name = "Workspace"
    requires_setting = None  # always available

    def get_tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="workspace_read_file",
                description=(
                    "Read the contents of a file within the active project's "
                    "workspace directory. Path is relative to the project root."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Relative path within project workspace. "
                                "E.g. '_memory/decisions/2025-01-decision.md'"
                            ),
                        }
                    },
                    "required": ["path"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="workspace_list_files",
                description=(
                    "List files in a directory within the active project's workspace."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": (
                                "Relative directory path within project workspace. "
                                "Default: '' (project root)."
                            ),
                        }
                    },
                    "required": [],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="workspace_capture",
                description=(
                    "Write a markdown note to the project's memory inbox for later review. "
                    "Use this to capture insights, decisions, or important information."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Note title (used as filename)."},
                        "content": {"type": "string", "description": "Markdown content to save."},
                    },
                    "required": ["title", "content"],
                },
                requires_approval=False,  # inbox only — safe without approval
            ),
        ]

    async def execute_tool(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        context: SkillContext,
    ) -> ToolResult:
        project_root = (
            pathlib.Path(context.workspace_path) / "projects" / context.project_slug
        )

        handlers = {
            "workspace_read_file": self._read_file,
            "workspace_list_files": self._list_files,
            "workspace_capture": self._capture,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return ToolResult(success=False, content=f"Unknown tool: {tool_name}")

        try:
            return await handler(inputs, project_root)
        except Exception as e:
            return ToolResult(success=False, content=f"Workspace error: {str(e)[:200]}")

    def _resolve_safe(
        self, project_root: pathlib.Path, relative_path: str
    ) -> pathlib.Path | None:
        """Resolve path and verify it stays within project_root. Returns None if unsafe."""
        try:
            resolved = (project_root / relative_path).resolve()
            project_resolved = project_root.resolve()
            resolved.relative_to(project_resolved)  # raises ValueError if outside
            return resolved
        except (ValueError, Exception):
            return None

    async def _read_file(
        self, inputs: dict[str, Any], project_root: pathlib.Path
    ) -> ToolResult:
        path = self._resolve_safe(project_root, inputs.get("path", ""))
        if path is None:
            return ToolResult(
                success=False,
                content="Invalid path — must be within project workspace.",
            )
        if not path.exists():
            return ToolResult(success=False, content=f"File not found: {inputs['path']}")
        if not path.is_file():
            return ToolResult(success=False, content=f"Not a file: {inputs['path']}")

        content = path.read_text(encoding="utf-8")
        if len(content) > 8000:
            content = content[:8000] + "\n\n[... truncated at 8000 chars ...]"
        return ToolResult(success=True, content=content)

    async def _list_files(
        self, inputs: dict[str, Any], project_root: pathlib.Path
    ) -> ToolResult:
        directory = inputs.get("directory", "")
        if directory:
            path = self._resolve_safe(project_root, directory)
        else:
            path = project_root.resolve()
        if path is None:
            return ToolResult(success=False, content="Invalid directory path.")
        if not path.exists():
            return ToolResult(success=False, content=f"Directory not found: {directory}")
        if not path.is_dir():
            return ToolResult(success=False, content=f"Not a directory: {directory}")

        entries = sorted(path.iterdir())
        lines = []
        for entry in entries[:100]:  # cap at 100 entries
            rel = entry.relative_to(project_root.resolve())
            lines.append(f"{'[dir]' if entry.is_dir() else '[file]'} {rel}")

        return ToolResult(
            success=True,
            content=f"Contents of {directory or 'project root'} ({len(lines)} items):\n"
            + "\n".join(lines),
        )

    async def _capture(
        self, inputs: dict[str, Any], project_root: pathlib.Path
    ) -> ToolResult:
        inbox = project_root / "_memory" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)

        safe_title = re.sub(r"[^\w\s-]", "", inputs["title"])
        safe_title = re.sub(r"\s+", "_", safe_title).strip("_")[:60]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_title}.md"

        filepath = inbox / filename
        filepath.write_text(
            f"# {inputs['title']}\n\n"
            f"*Captured by orchestrator: {datetime.utcnow().isoformat()}*\n\n"
            f"{inputs['content']}\n",
            encoding="utf-8",
        )
        return ToolResult(
            success=True,
            content=f"Captured to inbox: {filename}",
            data={"filename": filename},
        )
