import asyncio
import json
import logging
import uuid as uuid_lib
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import anthropic
import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.chat_message import ChatMessage, MessageRole
from opvs.websocket import (
    WS_CHAT_COMPLETE,
    WS_CHAT_ERROR,
    WS_CHAT_TOKEN,
    WS_COMPACT_TRIGGERED,
    WS_TOOL_APPROVAL_REQUIRED,
    WS_TOOL_REJECTED,
    WS_TOOL_RESULT,
    WS_TOOL_USED,
    manager,
)

logger = logging.getLogger(__name__)

ORCHESTRATOR_MODEL_SETTING_KEY = "orchestrator_model"
ORCHESTRATOR_MODEL_DEFAULT = "claude-sonnet-4-6"
CONTEXT_WINDOW_TOKENS = 200_000
COMPACT_THRESHOLD = 0.75
COMPACT_THRESHOLD_TOKENS = int(CONTEXT_WINDOW_TOKENS * COMPACT_THRESHOLD)  # 150_000
HISTORY_MESSAGES_AFTER_COMPACT = 8
MAX_LOOP_ITERATIONS = 10

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class OllamaUnreachableError(Exception):
    """Raised when Ollama host cannot be reached."""


class AnthropicQuotaExceededError(Exception):
    """Raised when Anthropic returns a rate limit or quota error.
    Operations must halt — do not fall back to another paid service."""


# ---------------------------------------------------------------------------
# Module-level approval state
# ---------------------------------------------------------------------------

# Pending approvals: request_id → asyncio.Event
_pending_approvals: dict[str, asyncio.Event] = {}
# Approval decisions: request_id → True (approved) or False (rejected)
_approval_decisions: dict[str, bool] = {}


def resolve_approval(request_id: str, approved: bool) -> bool:
    """
    Called by the approve/reject endpoints.
    Returns True if the request_id was found and resolved, False otherwise.
    """
    event = _pending_approvals.get(request_id)
    if event is None:
        return False
    _approval_decisions[request_id] = approved
    event.set()
    return True


# ---------------------------------------------------------------------------
# Preambles
# ---------------------------------------------------------------------------

ANTHROPIC_PREAMBLE_DEFAULT = """\
You are the opvs OS orchestrator. You are a PM assistant that helps manage \
agents, tasks, and information for a product manager's daily work.

## Hard constraints — never violate these
- You cannot execute shell commands under any circumstances
- You cannot write files outside workspace/_memory/ without explicit user approval
- You cannot spend money, call paid APIs, or make external requests directly
- You cannot start or stop agents in Phase 2 (agent management comes in Phase 3)
- If the kill switch is active, inform the user and do not accept new task requests

## What you can do in Phase 2
- Answer questions about system state (notifications, kill switch status)
- Trigger the kill switch when explicitly requested
- Help the user think through PM tasks, research questions, and decisions
- Create notifications to capture important information

## Memory
Your short-term memory summary and project context are included below.
Always read them before responding.\
"""

OLLAMA_PREAMBLE_DEFAULT = """\
You are the opvs OS orchestrator, a PM assistant.

Hard limits (never violate):
- No shell commands
- No file writes outside workspace/_memory/ without user approval
- No direct external API calls
- If kill switch is active: refuse new tasks, explain why

You can: answer questions about system state, trigger kill switch on request,
help with PM thinking, create notifications.

Your project context and memory summary are below. Read them before responding.\
"""

_COMPACTION_PROMPT_TEMPLATE = """\
You are summarizing a conversation between a PM and their AI orchestrator.
Create a dense, structured context summary that captures:
1. Active tasks and their current status
2. Key decisions made
3. Open questions awaiting resolution
4. Important context that will be needed in future sessions

Format as a markdown document with these exact sections.
Keep it under 800 tokens. Do not include pleasantries or meta-commentary.

Conversation to summarize:
{messages}\
"""


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


async def _get_setting_value(db: AsyncSession, key: str) -> str:
    from sqlalchemy import select as sa_select

    from opvs.models.settings import Setting

    result = await db.execute(sa_select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        return ""
    return str(setting.value).strip()


async def _get_model(db: AsyncSession) -> str:
    result = await _get_setting_value(db, ORCHESTRATOR_MODEL_SETTING_KEY)
    return result if result else ORCHESTRATOR_MODEL_DEFAULT


async def _get_workspace_path(db: AsyncSession) -> Path:
    val = await _get_setting_value(db, "workspace_path")
    return Path(val) if val else Path("./workspace")


async def _get_stm_path(db: AsyncSession, project_id: int | None) -> "Path":
    workspace_path = await _get_workspace_path(db)
    if project_id is not None:
        from opvs.services import project_service

        project = await project_service.get_project(db, project_id)
        if project is not None:
            return workspace_path / "projects" / project.slug / "_memory" / "stm" / "current.md"
    return workspace_path / "_memory" / "stm" / "current.md"


async def _load_api_keys(db: AsyncSession) -> dict[str, str]:
    """Load all relevant API keys from the settings table."""
    keys = ["linear_api_key", "anthropic_api_key"]
    result: dict[str, str] = {}
    for key in keys:
        result[key] = await _get_setting_value(db, key) or ""
    return result


async def _get_project(
    db: AsyncSession, project_id: int
) -> "object | None":
    """Return the Project ORM object or None."""
    from sqlalchemy import select as sa_select

    from opvs.models.project import Project

    res = await db.execute(sa_select(Project).where(Project.id == project_id))
    return res.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


def _detect_provider(model: str) -> Literal["anthropic", "ollama"]:
    """Determine which provider to use based on model name.
    All Anthropic models start with 'claude-'. Everything else routes to Ollama.
    """
    if model.startswith("claude-"):
        return "anthropic"
    return "ollama"


# ---------------------------------------------------------------------------
# Preamble loading
# ---------------------------------------------------------------------------


async def _load_preamble(db: AsyncSession, provider: str) -> str:
    """Load user-edited preamble from DB, fall back to hardcoded default."""
    key = (
        "orchestrator_preamble_anthropic"
        if provider == "anthropic"
        else "orchestrator_preamble_ollama"
    )
    value = await _get_setting_value(db, key)
    if value and value.strip():
        return value.strip()
    return (
        ANTHROPIC_PREAMBLE_DEFAULT
        if provider == "anthropic"
        else OLLAMA_PREAMBLE_DEFAULT
    )


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------


async def _get_project_for_prompt(
    db: AsyncSession, project_id: int
) -> "tuple[str, str] | None":
    """Return (name, slug) for a project, or None if not found."""
    from sqlalchemy import select as sa_select

    from opvs.models.project import Project

    result = await db.execute(sa_select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        return None
    return (project.name, project.slug)


async def _build_system_prompt(
    db: AsyncSession,
    project_id: int | None = None,
    provider: str = "anthropic",
) -> str:
    workspace_path = await _get_workspace_path(db)
    preamble = await _load_preamble(db, provider)
    sections: list[str] = [preamble]

    # 1. Global memory index
    global_index = workspace_path / "_memory" / "INDEX.md"
    if global_index.exists():
        content = global_index.read_text(encoding="utf-8").strip()
        sections.append(f"## Global memory index\n\n{content}")

    # 2. Project-scoped context and memory
    if project_id is not None:
        project_info = await _get_project_for_prompt(db, project_id)
        if project_info is not None:
            project_name, project_slug = project_info
            sections.append(
                f"## Active project\n\nName: {project_name}\nSlug: {project_slug}"
            )

            context_file = workspace_path / "projects" / project_slug / "CONTEXT.md"
            if context_file.exists():
                raw = context_file.read_text(encoding="utf-8").strip()
                body = "\n".join(
                    line for line in raw.splitlines()
                    if not line.startswith("# READ-ONLY")
                ).strip()
                if body:
                    sections.append(f"## Project context\n\n{body}")

            project_index = (
                workspace_path / "projects" / project_slug / "_memory" / "INDEX.md"
            )
            if project_index.exists():
                content = project_index.read_text(encoding="utf-8").strip()
                sections.append(f"## Project memory index\n\n{content}")

            stm_file = await _get_stm_path(db, project_id)
            if stm_file.exists():
                content = stm_file.read_text(encoding="utf-8").strip()
                if "No context has been compacted yet" not in content:
                    sections.append(f"## Short-term memory\n\n{content}")

    # 3. Dynamic system state
    from opvs.services import killswitch_service

    ks_status = await killswitch_service.get_status(db)
    kill_switch_str = "ACTIVE — do not accept new task requests" if ks_status.active else "inactive"

    from opvs.models.notification import NotificationStatus
    from opvs.services import notification_service

    pending = await notification_service.list_notifications(
        db, status=NotificationStatus.PENDING, project_id=project_id
    )
    model = await _get_model(db)

    sections.append(
        f"## System state\n\n"
        f"- Kill switch: {kill_switch_str}\n"
        f"- Pending notifications: {len(pending)}\n"
        f"- Orchestrator model: {model}\n"
        f"- Active project ID: {project_id}\n"
    )

    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Message history helpers
# ---------------------------------------------------------------------------


async def _load_context_messages(
    db: AsyncSession, project_id: int | None = None
) -> list[ChatMessage]:
    project_filter = (
        ChatMessage.project_id == project_id
        if project_id is not None
        else None
    )

    summary_query = (
        select(ChatMessage)
        .where(ChatMessage.is_compact_summary == True)  # noqa: E712
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    if project_filter is not None:
        summary_query = summary_query.where(project_filter)
    summary_result = await db.execute(summary_query)
    latest_summary = summary_result.scalar_one_or_none()

    if latest_summary is not None:
        subsequent_query = (
            select(ChatMessage)
            .where(
                ChatMessage.id > latest_summary.id,
                ChatMessage.is_compact_summary == False,  # noqa: E712
            )
            .order_by(ChatMessage.id.asc())
            .limit(50)
        )
        if project_filter is not None:
            subsequent_query = subsequent_query.where(project_filter)
        subsequent_result = await db.execute(subsequent_query)
        subsequent = list(subsequent_result.scalars().all())
        return [latest_summary, *subsequent]
    else:
        base_query = (
            select(ChatMessage)
            .where(ChatMessage.is_compact_summary == False)  # noqa: E712
            .order_by(ChatMessage.id.desc())
            .limit(50)
        )
        if project_filter is not None:
            base_query = base_query.where(project_filter)
        result = await db.execute(base_query)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages


def _build_api_messages(
    context_messages: list[ChatMessage],
) -> list[anthropic.types.MessageParam]:
    api_messages: list[anthropic.types.MessageParam] = []
    for msg in context_messages:
        if msg.is_compact_summary:
            api_messages.append({"role": "user", "content": msg.content})
            api_messages.append(
                {"role": "assistant", "content": "Understood. I have the context summary."}
            )
        else:
            assert msg.role in (MessageRole.USER, MessageRole.ASSISTANT)
            api_role: anthropic.types.MessageParam = {
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content,
            }
            api_messages.append(api_role)
    return api_messages


async def _build_messages(
    db: AsyncSession,
    project_id: int | None,
    new_user_content: str,
) -> list[dict[str, Any]]:
    """
    Load chat history from DB and append the new user message.
    Returns a list of {"role": ..., "content": ...} dicts.

    Uses the most recent compact summary as the starting point.
    Tool exchange messages are NOT stored in DB — only text messages.
    """
    from sqlalchemy import select as sa_select

    # Find the latest compact summary
    summary_query = (
        sa_select(ChatMessage)
        .where(
            ChatMessage.is_compact_summary == True,  # noqa: E712
            ChatMessage.project_id == project_id,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    result = await db.execute(summary_query)
    latest_summary = result.scalar_one_or_none()

    # Load messages after the summary (or all if no summary)
    msg_query = sa_select(ChatMessage).where(
        ChatMessage.project_id == project_id,
        ChatMessage.is_compact_summary == False,  # noqa: E712
    )
    if latest_summary:
        msg_query = msg_query.where(
            ChatMessage.created_at > latest_summary.created_at
        )
    msg_query = msg_query.order_by(ChatMessage.created_at.asc()).limit(50)
    result = await db.execute(msg_query)
    history = list(result.scalars().all())

    messages: list[dict[str, Any]] = []

    # Inject compact summary as a user/assistant pair
    if latest_summary:
        messages.append({"role": "user", "content": latest_summary.content})
        messages.append(
            {"role": "assistant", "content": "Understood. I have the context summary."}
        )

    # Add history
    for msg in history:
        if msg.role in (MessageRole.USER, MessageRole.ASSISTANT):
            role_str = "user" if msg.role == MessageRole.USER else "assistant"
            messages.append({"role": role_str, "content": msg.content})

    # Add current user message
    messages.append({"role": "user", "content": new_user_content})

    return messages


# ---------------------------------------------------------------------------
# LLM callers — Anthropic (with tool support)
# ---------------------------------------------------------------------------


async def _call_anthropic(
    model: str,
    messages: list[dict[str, Any]],
    system: str,
    tool_definitions: list[dict[str, Any]],
    db: AsyncSession,
    client_id: str,
) -> tuple[str, list[dict[str, Any]], int, int]:
    """
    Call Anthropic with streaming + tool support.

    Streams text tokens via WS and returns the full content blocks list.
    Returns: (stop_reason, content_blocks, input_tokens, output_tokens)
    """
    api_key = await _get_setting_value(db, "anthropic_api_key") or ""
    client = anthropic.AsyncAnthropic(api_key=api_key if api_key else None)

    content_blocks: list[dict[str, Any]] = []
    current_text = ""
    current_tool_raw = ""
    stop_reason = "end_turn"
    in_tok = 0
    out_tok = 0

    try:
        async with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system,
            messages=cast(list[anthropic.types.MessageParam], messages),
            tools=cast(Any, tool_definitions if tool_definitions else anthropic.NOT_GIVEN),
        ) as stream:
            async for event in stream:
                if isinstance(event, anthropic.types.RawContentBlockStartEvent):
                    block = event.content_block
                    if isinstance(block, anthropic.types.TextBlock):
                        current_text = ""
                    elif isinstance(block, anthropic.types.ToolUseBlock):
                        # Flush any accumulated text first
                        if current_text:
                            content_blocks.append({"type": "text", "text": current_text})
                            current_text = ""
                        current_tool_raw = ""
                        content_blocks.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": {},
                        })

                elif isinstance(event, anthropic.types.RawContentBlockDeltaEvent):
                    delta = event.delta
                    if isinstance(delta, anthropic.types.TextDelta):
                        current_text += delta.text
                        await manager.send_to(
                            client_id, WS_CHAT_TOKEN, {"content": delta.text}
                        )
                    elif isinstance(delta, anthropic.types.InputJSONDelta):
                        current_tool_raw += delta.partial_json

                elif isinstance(event, anthropic.types.RawContentBlockStopEvent):
                    if current_text:
                        content_blocks.append({"type": "text", "text": current_text})
                        current_text = ""
                    # Parse accumulated JSON input for the last tool_use block
                    if content_blocks and content_blocks[-1]["type"] == "tool_use":
                        try:
                            content_blocks[-1]["input"] = (
                                json.loads(current_tool_raw) if current_tool_raw else {}
                            )
                        except json.JSONDecodeError:
                            content_blocks[-1]["input"] = {}
                        current_tool_raw = ""

            final = await stream.get_final_message()
        stop_reason = str(final.stop_reason or "end_turn")
        in_tok = final.usage.input_tokens
        out_tok = final.usage.output_tokens

    except anthropic.RateLimitError as e:
        raise AnthropicQuotaExceededError(str(e)) from e
    except anthropic.APIStatusError as e:
        if e.status_code in (429, 529):
            raise AnthropicQuotaExceededError(str(e)) from e
        raise

    return stop_reason, content_blocks, in_tok, out_tok


# ---------------------------------------------------------------------------
# LLM callers — Ollama (OpenAI-compat with tool support)
# ---------------------------------------------------------------------------


async def _call_ollama_agentic(
    model: str,
    messages: list[dict[str, Any]],
    system: str,
    tool_definitions: list[dict[str, Any]],
    db: AsyncSession,
    client_id: str,
) -> tuple[str, list[dict[str, Any]], int, int]:
    """
    Call Ollama via OpenAI-compatible /v1/chat/completions endpoint with tool support.

    Returns: (stop_reason, content_blocks, input_tokens, output_tokens)
    """
    ollama_host = await _get_setting_value(db, "ollama_host") or "http://localhost:11434"
    url = f"{ollama_host.rstrip('/')}/v1/chat/completions"

    # Build messages with system prepended
    full_messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]

    # Normalize: content must be str for Ollama
    normalized: list[dict[str, Any]] = []
    for msg in full_messages:
        content = msg.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "tool_result":
                        text_parts.append(f"[Tool result]: {part.get('content', '')}")
                    else:
                        text_parts.append(str(part))
                else:
                    text_parts.append(str(part))
            normalized.append({"role": msg["role"], "content": "\n".join(text_parts)})
        else:
            normalized.append(msg)

    # Convert Anthropic tool format to OpenAI function format
    oai_tools: list[dict[str, Any]] = []
    for t in tool_definitions:
        oai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })

    payload: dict[str, Any] = {
        "model": model,
        "messages": normalized,
        "stream": True,
    }
    if oai_tools:
        payload["tools"] = oai_tools

    content_blocks: list[dict[str, Any]] = []
    current_text = ""
    stop_reason = "end_turn"
    in_tok = 0
    out_tok = 0

    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            async with http_client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                tool_calls_acc: dict[int, dict[str, Any]] = {}

                async for raw_line in response.aiter_lines():
                    if not raw_line.strip() or raw_line == "data: [DONE]":
                        continue
                    line = raw_line.removeprefix("data: ").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    choice = (data.get("choices") or [{}])[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason")

                    text_chunk = delta.get("content", "")
                    if text_chunk:
                        current_text += text_chunk
                        await manager.send_to(
                            client_id, WS_CHAT_TOKEN, {"content": text_chunk}
                        )

                    # Accumulate tool calls
                    for tc in delta.get("tool_calls", []):
                        idx = int(tc.get("index", 0))
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc.get("id", f"call_{idx}"),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": "",
                            }
                        tool_calls_acc[idx]["arguments"] += (
                            tc.get("function", {}).get("arguments", "")
                        )

                    if finish_reason == "tool_calls":
                        stop_reason = "tool_use"
                    elif finish_reason in ("stop", "length"):
                        stop_reason = "end_turn"

                    usage = data.get("usage", {})
                    if usage:
                        in_tok = int(usage.get("prompt_tokens", 0))
                        out_tok = int(usage.get("completion_tokens", 0))

                # Build content blocks from accumulated data
                if current_text:
                    content_blocks.append({"type": "text", "text": current_text})

                for tc in sorted(tool_calls_acc.values(), key=lambda x: x.get("id", "")):
                    try:
                        input_data: dict[str, Any] = (
                            json.loads(tc["arguments"]) if tc["arguments"] else {}
                        )
                    except json.JSONDecodeError:
                        input_data = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": input_data,
                    })

    except httpx.ConnectError as e:
        raise OllamaUnreachableError(str(e)) from e
    except httpx.TimeoutException as e:
        raise OllamaUnreachableError(str(e)) from e
    except httpx.HTTPStatusError as e:
        raise OllamaUnreachableError(
            f"Ollama returned HTTP {e.response.status_code}: {e}"
        ) from e

    return stop_reason, content_blocks, in_tok, out_tok


# ---------------------------------------------------------------------------
# Unified LLM caller with fallback
# ---------------------------------------------------------------------------


async def _call_llm(
    model: str,
    provider: str,
    messages: list[dict[str, Any]],
    system: str,
    tool_definitions: list[dict[str, Any]],
    db: AsyncSession,
    client_id: str,
) -> tuple[str, list[dict[str, Any]], int, int]:
    """
    Dispatch to the correct LLM provider and handle Ollama fallback.

    Returns: (stop_reason, content_blocks, input_tokens, output_tokens)
    """
    if provider == "anthropic":
        return await _call_anthropic(model, messages, system, tool_definitions, db, client_id)

    # Ollama path
    try:
        return await _call_ollama_agentic(
            model, messages, system, tool_definitions, db, client_id
        )
    except OllamaUnreachableError as e:
        fallback_model = ORCHESTRATOR_MODEL_DEFAULT
        warning_msg = (
            f"[Ollama unavailable ({model}) — responding via {fallback_model}]\n\n"
        )
        await manager.send_to(client_id, WS_CHAT_TOKEN, {"content": warning_msg})

        from opvs.models.notification import NotificationSourceType
        from opvs.schemas.notification import NotificationCreate
        from opvs.services.notification_service import create_notification

        await create_notification(
            db,
            NotificationCreate(
                title="Ollama unavailable",
                body=(
                    f"Could not reach Ollama ({model}). "
                    f"Fell back to {fallback_model}. Error: {str(e)[:200]}"
                ),
                source_type=NotificationSourceType.SYSTEM,
            ),
        )

        fallback_system = await _build_system_prompt(db, provider="anthropic")
        stop_reason, content_blocks, in_tok, out_tok = await _call_anthropic(
            fallback_model, messages, fallback_system, tool_definitions, db, client_id
        )

        # Prepend warning to text output
        if content_blocks and content_blocks[0].get("type") == "text":
            content_blocks[0]["text"] = warning_msg + content_blocks[0]["text"]
        else:
            content_blocks.insert(0, {"type": "text", "text": warning_msg})

        return stop_reason, content_blocks, in_tok, out_tok


# ---------------------------------------------------------------------------
# Approval helpers
# ---------------------------------------------------------------------------


def _tool_action_label(tool_name: str) -> str:
    """Return a human-readable action label for a tool name."""
    labels = {
        "linear_create_issue": "Create issue",
        "linear_update_issue": "Update issue",
        "linear_create_comment": "Post comment",
    }
    return labels.get(tool_name, tool_name.replace("_", " ").title())


def _describe_tool_action(tool_name: str, inputs: dict[str, Any]) -> str:
    """Return a human-readable description of what the tool will do."""
    if tool_name == "linear_create_issue":
        return (
            f"Create issue \"{inputs.get('title', '(untitled)')}\" "
            f"in team {inputs.get('team_id', '?')}"
        )
    if tool_name == "linear_update_issue":
        changes = [k for k in inputs if k != "issue_id"]
        return (
            f"Update issue {inputs.get('issue_id', '?')}: change {', '.join(changes)}"
        )
    if tool_name == "linear_create_comment":
        body_preview = str(inputs.get("body", ""))[:80]
        return f"Post comment on {inputs.get('issue_id', '?')}: \"{body_preview}...\""
    return f"Execute {tool_name} with {len(inputs)} parameter(s)"


async def _create_quota_notification(db: AsyncSession) -> None:
    from opvs.models.notification import NotificationSourceType
    from opvs.schemas.notification import NotificationCreate
    from opvs.services.notification_service import create_notification

    await create_notification(
        db,
        NotificationCreate(
            title="Anthropic quota exceeded — operations halted",
            body=(
                "The Anthropic API returned a rate limit or quota error. "
                "Check usage at console.anthropic.com."
            ),
            source_type=NotificationSourceType.SYSTEM,
            priority=10,
        ),
    )


# ---------------------------------------------------------------------------
# Ollama streaming (kept for compaction)
# ---------------------------------------------------------------------------


async def _stream_ollama(
    model: str,
    messages: list[anthropic.types.MessageParam],
    system: str,
    ollama_host: str,
) -> AsyncGenerator[tuple[str, int, int], None]:
    """Stream tokens from Ollama via /api/chat. Used only for compaction.
    Yields (token, input_tokens, output_tokens).
    Raises OllamaUnreachableError if the host cannot be reached.
    """
    full_messages: list[dict[str, str]] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    for msg in messages:
        full_messages.append({
            "role": str(msg["role"]),
            "content": str(msg["content"]),
        })

    url = f"{ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": full_messages,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                input_tokens = 0
                output_tokens = 0

                async for raw_line in response.aiter_lines():
                    if not raw_line.strip():
                        continue
                    try:
                        data = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    if not data.get("done", False):
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield (token, 0, 0)
                    else:
                        input_tokens = data.get("prompt_eval_count", 0)
                        output_tokens = data.get("eval_count", 0)
                        yield ("", input_tokens, output_tokens)

    except httpx.ConnectError as e:
        raise OllamaUnreachableError(
            f"Cannot reach Ollama at {ollama_host}: {e}"
        ) from e
    except httpx.TimeoutException as e:
        raise OllamaUnreachableError(
            f"Ollama request timed out at {ollama_host}: {e}"
        ) from e
    except httpx.HTTPStatusError as e:
        raise OllamaUnreachableError(
            f"Ollama returned HTTP {e.response.status_code}: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_history(
    db: AsyncSession, limit: int = 50, project_id: int | None = None
) -> list[ChatMessage]:
    query = select(ChatMessage).order_by(ChatMessage.created_at.asc()).limit(limit)
    if project_id is not None:
        query = query.where(ChatMessage.project_id == project_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def clear_history(db: AsyncSession) -> None:
    await db.execute(delete(ChatMessage))
    await db.flush()


async def get_compact_status(db: AsyncSession) -> tuple[int, int, bool]:
    summary_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.is_compact_summary == True)  # noqa: E712
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    latest_summary = summary_result.scalar_one_or_none()

    if latest_summary is not None:
        tokens_result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.id > latest_summary.id,
                ChatMessage.is_compact_summary == False,  # noqa: E712
            )
        )
        messages = list(tokens_result.scalars().all())
    else:
        tokens_result = await db.execute(
            select(ChatMessage).where(ChatMessage.is_compact_summary == False)  # noqa: E712
        )
        messages = list(tokens_result.scalars().all())

    total = sum(m.token_count for m in messages)
    compacted = latest_summary is not None

    # Dynamic threshold based on current model/provider
    model = await _get_model(db)
    provider = _detect_provider(model)
    if provider == "ollama":
        window_str = await _get_setting_value(db, "ollama_context_window") or "8192"
        try:
            context_window = int(window_str)
        except ValueError:
            context_window = 8192
        threshold = int(context_window * COMPACT_THRESHOLD)
    else:
        threshold = COMPACT_THRESHOLD_TOKENS

    return total, threshold, compacted


async def send_message(
    db: AsyncSession,
    user_content: str,
    client_id: str,
    project_id: int | None = None,
) -> ChatMessage:
    """
    Send a user message and run the agentic loop.

    Flow:
    1. Save user message to DB
    2. Check kill switch
    3. Load enabled skills for the active project
    4. Build messages array from history
    5. Run agentic loop (max MAX_LOOP_ITERATIONS):
       a. Call LLM with tools via _call_llm
       b. Text blocks were already streamed in _call_llm; accumulate for DB
       c. For tool_use blocks:
          - No approval: execute silently, emit WS_TOOL_USED + WS_TOOL_RESULT
          - Approval: emit WS_TOOL_APPROVAL_REQUIRED, await event
       d. Inject tool_results and continue loop
       e. Break on end_turn or no tool_results
    6. Save final assistant text to DB
    7. Broadcast WS_CHAT_COMPLETE
    8. Check compaction
    """
    from opvs.skills.base import SkillContext
    from opvs.skills.registry import find_tool, get_all_tool_definitions, get_enabled_skills

    # 1. Save user message
    user_msg = ChatMessage(
        role=MessageRole.USER,
        content=user_content,
        token_count=0,
        is_compact_summary=False,
        project_id=project_id,
    )
    db.add(user_msg)
    await db.flush()
    await db.refresh(user_msg)

    # 2. Kill switch check
    from opvs.services import killswitch_service

    ks = await killswitch_service.get_status(db)
    if ks.active:
        refusal = (
            "The kill switch is currently active. All agent operations are halted. "
            "Please recover the kill switch before sending new task requests."
        )
        refusal_msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=refusal,
            token_count=0,
            is_compact_summary=False,
            project_id=project_id,
        )
        db.add(refusal_msg)
        await db.flush()
        await db.refresh(refusal_msg)
        await manager.send_to(client_id, WS_CHAT_COMPLETE, {"message_id": refusal_msg.id})
        return refusal_msg

    # 3. Load skills
    api_keys = await _load_api_keys(db)
    enabled_skills = await get_enabled_skills(db, project_id or 0, api_keys)
    tool_definitions = get_all_tool_definitions(enabled_skills)

    # Get project slug for workspace skill context
    project_slug = "default"
    if project_id:
        project_obj = await _get_project(db, project_id)
        if project_obj is not None:
            project_slug = str(getattr(project_obj, "slug", "default"))

    workspace_path = await _get_setting_value(db, "workspace_path") or "./workspace"

    skill_context = SkillContext(
        api_keys=api_keys,
        workspace_path=workspace_path,
        project_slug=project_slug,
        project_id=project_id or 0,
    )

    # 4. Build initial messages from history
    messages: list[dict[str, Any]] = await _build_messages(db, project_id, user_content)

    # 5. Detect provider and build system prompt
    model = await _get_model(db)
    provider = _detect_provider(model)
    system = await _build_system_prompt(db, project_id=project_id, provider=provider)

    # 6. Agentic loop
    full_text_response = ""
    total_input_tokens = 0
    total_output_tokens = 0
    tools_used: list[str] = []

    try:
        for _iteration in range(MAX_LOOP_ITERATIONS):
            stop_reason, response_content, in_tok, out_tok = await _call_llm(
                model=model,
                provider=provider,
                messages=messages,
                system=system,
                tool_definitions=tool_definitions,
                db=db,
                client_id=client_id,
            )
            total_input_tokens += in_tok
            total_output_tokens += out_tok

            tool_results: list[dict[str, Any]] = []

            for block in response_content:
                if block["type"] == "text":
                    full_text_response += block.get("text", "")

                elif block["type"] == "tool_use":
                    tool_id = str(block["id"])
                    tool_name = str(block["name"])
                    tool_input: dict[str, Any] = dict(block.get("input", {}))

                    found = find_tool(tool_name, enabled_skills)
                    if found is None:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": f"Unknown tool: {tool_name}",
                        })
                        continue

                    skill, tool_def = found
                    tools_used.append(tool_name)

                    if tool_def.requires_approval:
                        request_id = str(uuid_lib.uuid4())
                        event = asyncio.Event()
                        _pending_approvals[request_id] = event

                        description = _describe_tool_action(tool_name, tool_input)
                        await manager.send_to(
                            client_id,
                            WS_TOOL_APPROVAL_REQUIRED,
                            {
                                "request_id": request_id,
                                "tool_name": tool_name,
                                "platform": skill.display_name,
                                "action": _tool_action_label(tool_name),
                                "description": description,
                                "parameters": tool_input,
                            },
                        )

                        # Wait for user decision (indefinitely)
                        await event.wait()

                        approved = _approval_decisions.pop(request_id, False)
                        _pending_approvals.pop(request_id, None)

                        if not approved:
                            await manager.send_to(
                                client_id, WS_TOOL_REJECTED, {"tool_name": tool_name}
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": "Action was rejected by the user.",
                            })
                            continue

                    # Execute tool (approved or no approval needed)
                    tool_result = await skill.execute_tool(
                        tool_name, tool_input, skill_context
                    )

                    await manager.send_to(
                        client_id,
                        WS_TOOL_RESULT,
                        {
                            "tool_name": tool_name,
                            "success": tool_result.success,
                            "content": tool_result.content[:200],
                        },
                    )

                    if not tool_def.requires_approval:
                        await manager.send_to(
                            client_id, WS_TOOL_USED, {"tool_name": tool_name}
                        )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": (
                            tool_result.content
                            if tool_result.success
                            else f"Tool failed: {tool_result.content}"
                        ),
                    })

            # Update messages for next iteration
            messages.append({"role": "assistant", "content": response_content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # Break conditions
            if stop_reason == "end_turn" or not tool_results:
                break

    except AnthropicQuotaExceededError:
        error_msg = (
            "⚠ Anthropic quota exceeded. Operations halted. "
            "Check your API usage at console.anthropic.com."
        )
        await manager.send_to(client_id, WS_CHAT_ERROR, {"error": error_msg})
        await _create_quota_notification(db)
        error_record = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=error_msg,
            token_count=0,
            is_compact_summary=False,
            project_id=project_id,
        )
        db.add(error_record)
        await db.flush()
        await db.refresh(error_record)
        return error_record

    except Exception as e:
        logger.error("orchestrator send_message error: %s", e, exc_info=True)
        await manager.send_to(client_id, WS_CHAT_ERROR, {"error": str(e)})
        error_msg_text = f"An error occurred: {e}"
        error_record = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=error_msg_text,
            token_count=0,
            is_compact_summary=False,
            project_id=project_id,
        )
        db.add(error_record)
        await db.flush()
        await db.refresh(error_record)
        return error_record

    # 7. Save final text response to DB
    total_tokens = total_input_tokens + total_output_tokens
    assistant_msg = ChatMessage(
        role=MessageRole.ASSISTANT,
        content=full_text_response,
        token_count=total_tokens,
        is_compact_summary=False,
        project_id=project_id,
    )
    db.add(assistant_msg)
    await db.flush()
    await db.refresh(assistant_msg)

    await manager.broadcast(WS_CHAT_COMPLETE, {"message_id": assistant_msg.id})

    # 8. Check compaction
    await _compact_if_needed(db, total_tokens, project_id=project_id)

    return assistant_msg


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


async def _compact_if_needed(
    db: AsyncSession, last_response_tokens: int, project_id: int | None = None
) -> bool:
    project_filter = (
        ChatMessage.project_id == project_id if project_id is not None else None
    )

    # Determine threshold based on current model/provider
    model = await _get_model(db)
    provider = _detect_provider(model)
    if provider == "ollama":
        window_str = await _get_setting_value(db, "ollama_context_window") or "8192"
        try:
            context_window = int(window_str)
        except ValueError:
            context_window = 8192
        threshold = int(context_window * COMPACT_THRESHOLD)
    else:
        threshold = COMPACT_THRESHOLD_TOKENS

    summary_query = (
        select(ChatMessage)
        .where(ChatMessage.is_compact_summary == True)  # noqa: E712
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    if project_filter is not None:
        summary_query = summary_query.where(project_filter)
    summary_result = await db.execute(summary_query)
    latest_summary = summary_result.scalar_one_or_none()

    if latest_summary is not None:
        tokens_query = select(ChatMessage).where(
            ChatMessage.id > latest_summary.id,
            ChatMessage.is_compact_summary == False,  # noqa: E712
        )
    else:
        tokens_query = select(ChatMessage).where(
            ChatMessage.is_compact_summary == False  # noqa: E712
        )
    if project_filter is not None:
        tokens_query = tokens_query.where(project_filter)
    tokens_result = await db.execute(tokens_query)

    messages = list(tokens_result.scalars().all())
    total_tokens = sum(m.token_count for m in messages) + last_response_tokens

    if total_tokens >= threshold:
        await _run_compaction(db, project_id=project_id)
        return True
    return False


async def _run_compaction(db: AsyncSession, project_id: int | None = None) -> None:
    project_filter = (
        ChatMessage.project_id == project_id if project_id is not None else None
    )

    # 1. Load all current non-summary messages
    all_query = (
        select(ChatMessage)
        .where(ChatMessage.is_compact_summary == False)  # noqa: E712
        .order_by(ChatMessage.id.asc())
    )
    if project_filter is not None:
        all_query = all_query.where(project_filter)
    all_result = await db.execute(all_query)
    all_messages = list(all_result.scalars().all())

    if not all_messages:
        return

    conversation_text = "\n".join(
        f"{m.role.value.upper()}: {m.content}" for m in all_messages
    )
    compaction_prompt = _COMPACTION_PROMPT_TEMPLATE.format(messages=conversation_text)
    compaction_messages: list[anthropic.types.MessageParam] = [
        {"role": "user", "content": compaction_prompt}
    ]

    # 2. Use same model as orchestrator
    model = await _get_model(db)
    provider = _detect_provider(model)

    summary_text = ""
    summary_tokens = 0

    if provider == "ollama":
        ollama_host = await _get_setting_value(db, "ollama_host") or "http://localhost:11434"
        try:
            async for token, _, out_tok in _stream_ollama(
                model, compaction_messages, "", ollama_host
            ):
                summary_text += token
                if out_tok:
                    summary_tokens = out_tok
        except OllamaUnreachableError:
            # Skip compaction silently if Ollama is down — will retry next time
            return
    else:
        api_key = await _get_setting_value(db, "anthropic_api_key") or ""
        client = anthropic.AsyncAnthropic(api_key=api_key if api_key else None)
        response = await client.messages.create(
            model=model,
            max_tokens=1024,
            messages=compaction_messages,
        )
        for block in response.content:
            if isinstance(block, anthropic.types.TextBlock):
                summary_text = block.text
                break
        summary_tokens = response.usage.output_tokens

    # 3. Write STM to project-scoped or global workspace path
    stm_file = await _get_stm_path(db, project_id)
    stm_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow()
    stm_content = f"""# Short-term memory
*Compacted: {now.isoformat()}*
*Covers: {len(all_messages)} messages*

{summary_text}
"""
    stm_file.write_text(stm_content, encoding="utf-8")

    # 4. Save summary as chat_message
    summary_msg = ChatMessage(
        role=MessageRole.SYSTEM,
        content=stm_content,
        token_count=summary_tokens,
        is_compact_summary=True,
        project_id=project_id,
    )
    db.add(summary_msg)
    await db.flush()

    # 5. Delete older non-summary messages, keep last HISTORY_MESSAGES_AFTER_COMPACT
    keep_ids = [m.id for m in all_messages[-HISTORY_MESSAGES_AFTER_COMPACT:]]
    delete_ids = [m.id for m in all_messages if m.id not in keep_ids]
    if delete_ids:
        await db.execute(
            delete(ChatMessage).where(ChatMessage.id.in_(delete_ids))
        )
    await db.flush()

    # 6. Broadcast
    await manager.broadcast(WS_COMPACT_TRIGGERED, {"messages_compacted": len(all_messages)})
    logger.info("Compaction complete: %d messages compacted", len(all_messages))
