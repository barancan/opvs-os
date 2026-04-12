from typing import Any

import httpx

from opvs.skills.base import SkillBase, SkillContext, ToolDefinition, ToolResult

LINEAR_API = "https://api.linear.app/graphql"


class LinearSkill(SkillBase):
    skill_id = "linear"
    display_name = "Linear"
    requires_setting = "linear_api_key"

    def get_tool_definitions(self) -> list[ToolDefinition]:
        return [
            # ── READ TOOLS (no approval) ──────────────────────────────────
            ToolDefinition(
                name="linear_list_teams",
                description="List all teams in the Linear workspace.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="linear_list_projects",
                description=(
                    "List projects in Linear, optionally filtered by team."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "team_id": {
                            "type": "string",
                            "description": "Filter by team ID (optional).",
                        }
                    },
                    "required": [],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="linear_list_issues",
                description=(
                    "List issues from Linear. Supports filtering by team, "
                    "project, status, assignee, and priority."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "team_id": {"type": "string", "description": "Filter by team ID."},
                        "project_id": {"type": "string", "description": "Filter by Linear project ID."},
                        "status": {"type": "string", "description": "Filter by state name (e.g. 'In Progress')."},
                        "assignee_email": {"type": "string", "description": "Filter by assignee email."},
                        "priority": {
                            "type": "integer",
                            "description": "Filter by priority: 0=no priority, 1=urgent, 2=high, 3=medium, 4=low.",
                        },
                        "first": {
                            "type": "integer",
                            "description": "Max issues to return (default 25, max 50).",
                        },
                    },
                    "required": [],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="linear_get_issue",
                description="Get full details of a single Linear issue including comments.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_id": {
                            "type": "string",
                            "description": "The Linear issue ID (e.g. 'ENG-123' or UUID).",
                        }
                    },
                    "required": ["issue_id"],
                },
                requires_approval=False,
            ),
            ToolDefinition(
                name="linear_search_issues",
                description="Full-text search across Linear issues.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query string."},
                        "first": {"type": "integer", "description": "Max results (default 10)."},
                    },
                    "required": ["query"],
                },
                requires_approval=False,
            ),
            # ── WRITE TOOLS (approval required) ──────────────────────────
            ToolDefinition(
                name="linear_create_issue",
                description="Create a new issue in Linear.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Issue title."},
                        "description": {"type": "string", "description": "Issue description (markdown)."},
                        "team_id": {"type": "string", "description": "Team ID to create the issue in."},
                        "project_id": {"type": "string", "description": "Linear project ID (optional)."},
                        "priority": {
                            "type": "integer",
                            "description": "Priority: 0=none, 1=urgent, 2=high, 3=medium, 4=low.",
                        },
                        "assignee_id": {"type": "string", "description": "User ID to assign (optional)."},
                    },
                    "required": ["title", "team_id"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="linear_update_issue",
                description="Update an existing Linear issue.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "string", "description": "Issue ID to update."},
                        "title": {"type": "string", "description": "New title (optional)."},
                        "description": {"type": "string", "description": "New description (optional)."},
                        "state_id": {"type": "string", "description": "New state ID (optional)."},
                        "priority": {"type": "integer", "description": "New priority (optional)."},
                        "assignee_id": {"type": "string", "description": "New assignee ID (optional)."},
                    },
                    "required": ["issue_id"],
                },
                requires_approval=True,
            ),
            ToolDefinition(
                name="linear_create_comment",
                description="Post a comment on a Linear issue.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_id": {"type": "string", "description": "Issue ID to comment on."},
                        "body": {"type": "string", "description": "Comment text (markdown)."},
                    },
                    "required": ["issue_id", "body"],
                },
                requires_approval=True,
            ),
        ]

    async def execute_tool(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        context: SkillContext,
    ) -> ToolResult:
        api_key = context.api_keys.get("linear_api_key", "")
        if not api_key:
            return ToolResult(success=False, content="Linear API key not configured.")

        handlers = {
            "linear_list_teams": self._list_teams,
            "linear_list_projects": self._list_projects,
            "linear_list_issues": self._list_issues,
            "linear_get_issue": self._get_issue,
            "linear_search_issues": self._search_issues,
            "linear_create_issue": self._create_issue,
            "linear_update_issue": self._update_issue,
            "linear_create_comment": self._create_comment,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return ToolResult(success=False, content=f"Unknown tool: {tool_name}")

        try:
            return await handler(inputs, api_key)
        except httpx.ConnectError:
            return ToolResult(success=False, content="Cannot reach Linear API.")
        except Exception as e:
            return ToolResult(success=False, content=f"Linear error: {str(e)[:300]}")

    async def _graphql(
        self, query: str, variables: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                LINEAR_API,
                json={"query": query, "variables": variables},
                headers={"Authorization": api_key, "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            if "errors" in data:
                raise ValueError(str(data["errors"]))
            return dict(data.get("data", {}))

    async def _list_teams(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        data = await self._graphql(
            "query { teams { nodes { id name key } } }", {}, api_key
        )
        teams = data.get("teams", {}).get("nodes", [])
        if not teams:
            return ToolResult(success=True, content="No teams found.", data={"teams": []})
        lines = [f"- {t['name']} (id: {t['id']}, key: {t['key']})" for t in teams]
        return ToolResult(
            success=True,
            content="Teams:\n" + "\n".join(lines),
            data={"teams": teams},
        )

    async def _list_projects(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        team_id = inputs.get("team_id")
        if team_id:
            query = """
            query($teamId: String!) {
              team(id: $teamId) {
                projects { nodes { id name description state } }
              }
            }"""
            data = await self._graphql(query, {"teamId": team_id}, api_key)
            projects = data.get("team", {}).get("projects", {}).get("nodes", [])
        else:
            query = "query { projects { nodes { id name description state } } }"
            data = await self._graphql(query, {}, api_key)
            projects = data.get("projects", {}).get("nodes", [])

        if not projects:
            return ToolResult(success=True, content="No projects found.", data={"projects": []})
        lines = [
            f"- {p['name']} (id: {p['id']}, state: {p.get('state', 'unknown')})"
            for p in projects
        ]
        return ToolResult(
            success=True,
            content="Projects:\n" + "\n".join(lines),
            data={"projects": projects},
        )

    async def _list_issues(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        filters: list[str] = []
        variables: dict[str, Any] = {}

        if inputs.get("team_id"):
            filters.append("team: { id: { eq: $teamId } }")
            variables["teamId"] = inputs["team_id"]
        if inputs.get("project_id"):
            filters.append("project: { id: { eq: $projectId } }")
            variables["projectId"] = inputs["project_id"]
        if inputs.get("status"):
            filters.append("state: { name: { eq: $status } }")
            variables["status"] = inputs["status"]
        if inputs.get("priority") is not None:
            filters.append("priority: { eq: $priority }")
            variables["priority"] = inputs["priority"]

        first = min(int(inputs.get("first", 25)), 50)
        filter_str = ("filter: { " + ", ".join(filters) + " }") if filters else ""

        var_decls = []
        if "teamId" in variables:
            var_decls.append("$teamId: ID!")
        if "projectId" in variables:
            var_decls.append("$projectId: ID!")
        if "status" in variables:
            var_decls.append("$status: String!")
        if "priority" in variables:
            var_decls.append("$priority: Int!")

        var_str = ("(" + ", ".join(var_decls) + ")") if var_decls else ""

        query = f"""
        query{var_str} {{
          issues({filter_str} first: {first} orderBy: updatedAt) {{
            nodes {{
              id identifier title
              state {{ name }}
              priority
              assignee {{ name }}
              project {{ name }}
              team {{ name }}
              updatedAt
              url
            }}
          }}
        }}"""

        data = await self._graphql(query, variables, api_key)
        issues = data.get("issues", {}).get("nodes", [])

        if not issues:
            return ToolResult(success=True, content="No issues found matching filters.", data={"issues": []})

        lines = []
        for issue in issues:
            state = issue.get("state", {}).get("name", "?")
            assignee = (
                issue.get("assignee", {}).get("name", "unassigned")
                if issue.get("assignee")
                else "unassigned"
            )
            lines.append(
                f"- [{issue['identifier']}] {issue['title']} "
                f"| {state} | {assignee} | {issue.get('url', '')}"
            )
        return ToolResult(
            success=True,
            content=f"Issues ({len(issues)}):\n" + "\n".join(lines),
            data={"issues": issues},
        )

    async def _get_issue(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        issue_id = inputs["issue_id"]
        query = """
        query($id: String!) {
          issue(id: $id) {
            id identifier title description
            state { name }
            priority
            assignee { name email }
            project { name }
            team { name }
            comments { nodes { body user { name } createdAt } }
            url createdAt updatedAt
          }
        }"""
        data = await self._graphql(query, {"id": issue_id}, api_key)
        issue = data.get("issue")
        if not issue:
            return ToolResult(success=False, content=f"Issue {issue_id} not found.")

        comments = issue.get("comments", {}).get("nodes", [])
        comment_text = ""
        if comments:
            comment_text = "\n\nComments:\n" + "\n".join(
                f"  [{c['user']['name']}]: {c['body']}" for c in comments
            )

        content = (
            f"[{issue['identifier']}] {issue['title']}\n"
            f"State: {issue.get('state', {}).get('name', '?')}\n"
            f"Assignee: {issue.get('assignee', {}).get('name', 'unassigned') if issue.get('assignee') else 'unassigned'}\n"
            f"Description:\n{issue.get('description', '(none)')}"
            f"{comment_text}"
        )
        return ToolResult(success=True, content=content, data={"issue": issue})

    async def _search_issues(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        first = min(int(inputs.get("first", 10)), 25)
        query = """
        query($query: String!, $first: Int!) {
          issueSearch(query: $query, first: $first) {
            nodes {
              id identifier title
              state { name }
              assignee { name }
              url
            }
          }
        }"""
        data = await self._graphql(
            query, {"query": inputs["query"], "first": first}, api_key
        )
        issues = data.get("issueSearch", {}).get("nodes", [])
        if not issues:
            return ToolResult(success=True, content="No issues found.", data={"issues": []})
        lines = [
            f"- [{i['identifier']}] {i['title']} | {i.get('state', {}).get('name', '?')} | {i.get('url', '')}"
            for i in issues
        ]
        return ToolResult(
            success=True,
            content=f"Search results ({len(issues)}):\n" + "\n".join(lines),
            data={"issues": issues},
        )

    async def _create_issue(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        mutation = """
        mutation($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id identifier title url }
          }
        }"""
        issue_input: dict[str, Any] = {
            "title": inputs["title"],
            "teamId": inputs["team_id"],
        }
        if inputs.get("description"):
            issue_input["description"] = inputs["description"]
        if inputs.get("project_id"):
            issue_input["projectId"] = inputs["project_id"]
        if inputs.get("priority") is not None:
            issue_input["priority"] = inputs["priority"]
        if inputs.get("assignee_id"):
            issue_input["assigneeId"] = inputs["assignee_id"]

        data = await self._graphql(mutation, {"input": issue_input}, api_key)
        result = data.get("issueCreate", {})
        if not result.get("success"):
            return ToolResult(success=False, content="Failed to create issue.")
        issue = result["issue"]
        return ToolResult(
            success=True,
            content=f"Created [{issue['identifier']}] {issue['title']}\n{issue['url']}",
            data={"issue": issue},
        )

    async def _update_issue(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        mutation = """
        mutation($id: String!, $input: IssueUpdateInput!) {
          issueUpdate(id: $id, input: $input) {
            success
            issue { id identifier title }
          }
        }"""
        update_input: dict[str, Any] = {}
        for src, dst in [
            ("title", "title"),
            ("description", "description"),
            ("state_id", "stateId"),
            ("priority", "priority"),
            ("assignee_id", "assigneeId"),
        ]:
            if inputs.get(src) is not None:
                update_input[dst] = inputs[src]

        data = await self._graphql(
            mutation, {"id": inputs["issue_id"], "input": update_input}, api_key
        )
        result = data.get("issueUpdate", {})
        if not result.get("success"):
            return ToolResult(success=False, content="Failed to update issue.")
        issue = result["issue"]
        return ToolResult(
            success=True,
            content=f"Updated [{issue['identifier']}] {issue['title']}",
            data={"issue": issue},
        )

    async def _create_comment(
        self, inputs: dict[str, Any], api_key: str
    ) -> ToolResult:
        mutation = """
        mutation($input: CommentCreateInput!) {
          commentCreate(input: $input) {
            success
            comment { id body }
          }
        }"""
        data = await self._graphql(
            mutation,
            {"input": {"issueId": inputs["issue_id"], "body": inputs["body"]}},
            api_key,
        )
        result = data.get("commentCreate", {})
        if not result.get("success"):
            return ToolResult(success=False, content="Failed to create comment.")
        return ToolResult(
            success=True,
            content=f"Comment posted: {inputs['body'][:100]}...",
            data={"comment": result.get("comment", {})},
        )
