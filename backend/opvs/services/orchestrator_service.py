import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Literal

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
    manager,
)

logger = logging.getLogger(__name__)

ORCHESTRATOR_MODEL_SETTING_KEY = "orchestrator_model"
ORCHESTRATOR_MODEL_DEFAULT = "claude-sonnet-4-6"
CONTEXT_WINDOW_TOKENS = 200_000
COMPACT_THRESHOLD = 0.75
COMPACT_THRESHOLD_TOKENS = int(CONTEXT_WINDOW_TOKENS * COMPACT_THRESHOLD)  # 150_000
HISTORY_MESSAGES_AFTER_COMPACT = 8

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class OllamaUnreachableError(Exception):
    """Raised when Ollama host cannot be reached."""
    pass


class AnthropicQuotaExceededError(Exception):
    """Raised when Anthropic returns a rate limit or quota error.
    Operations must halt — do not fall back to another paid service."""
    pass


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
    """Return (name, slug) for a project, or None if not found. Avoids circular imports."""
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
# Message history
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


# ---------------------------------------------------------------------------
# Provider streaming
# ---------------------------------------------------------------------------


async def _stream_anthropic(
    model: str,
    messages: list[anthropic.types.MessageParam],
    system: str,
    api_key: str,
) -> AsyncGenerator[tuple[str, int, int], None]:
    """Stream tokens from Anthropic. Yields (token, input_tokens, output_tokens).
    input_tokens and output_tokens are 0 for intermediate chunks, populated on final.
    Raises AnthropicQuotaExceededError on rate limit / quota errors.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key if api_key else None)

    try:
        async with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield (text, 0, 0)
            final = await stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens
            yield ("", input_tokens, output_tokens)

    except anthropic.RateLimitError as e:
        raise AnthropicQuotaExceededError(
            f"Anthropic rate limit exceeded: {e}"
        ) from e
    except anthropic.APIStatusError as e:
        if e.status_code in (429, 529):
            raise AnthropicQuotaExceededError(
                f"Anthropic quota exceeded (HTTP {e.status_code}): {e}"
            ) from e
        raise


async def _stream_ollama(
    model: str,
    messages: list[anthropic.types.MessageParam],
    system: str,
    ollama_host: str,
) -> AsyncGenerator[tuple[str, int, int], None]:
    """Stream tokens from Ollama. Yields (token, input_tokens, output_tokens).
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


async def _stream_tokens(
    model: str,
    messages: list[anthropic.types.MessageParam],
    system: str,
    db: AsyncSession,
) -> AsyncGenerator[tuple[str, int, int], None]:
    """Route to the correct provider and handle fallback.

    Fallback rules:
    - Ollama unreachable → warn, fall back to claude-sonnet-4-6, yield a
      prefix token "[Ollama unavailable — responding via Claude]\\n\\n"
    - Anthropic quota exceeded → raise (caller must halt, not fall back)
    """
    provider = _detect_provider(model)

    if provider == "ollama":
        ollama_host = await _get_setting_value(db, "ollama_host") or "http://localhost:11434"
        try:
            async for item in _stream_ollama(model, messages, system, ollama_host):
                yield item
            return
        except OllamaUnreachableError as e:
            fallback_model = ORCHESTRATOR_MODEL_DEFAULT
            warning_msg = (
                f"[Ollama unavailable ({model}) — responding via {fallback_model}]\n\n"
            )
            yield (warning_msg, 0, 0)

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

            api_key = await _get_setting_value(db, "anthropic_api_key") or ""
            fallback_system = await _build_system_prompt(db, provider="anthropic")
            async for item in _stream_anthropic(fallback_model, messages, fallback_system, api_key):
                yield item

    else:
        api_key = await _get_setting_value(db, "anthropic_api_key") or ""
        async for item in _stream_anthropic(model, messages, system, api_key):
            yield item


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

    # 2. Check kill switch
    from opvs.services import killswitch_service

    ks_status = await killswitch_service.get_status(db)
    if ks_status.active:
        refusal = (
            "The kill switch is currently active. All agent operations are halted. "
            "Please recover the kill switch before sending new task requests."
        )
        assistant_msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=refusal,
            token_count=0,
            is_compact_summary=False,
            project_id=project_id,
        )
        db.add(assistant_msg)
        await db.flush()
        await db.refresh(assistant_msg)
        await manager.send_to(client_id, WS_CHAT_COMPLETE, {"message_id": assistant_msg.id})
        return assistant_msg

    try:
        # 3. Load history and build messages
        context_messages = await _load_context_messages(db, project_id=project_id)
        api_messages = _build_api_messages(context_messages)
        api_messages.append({"role": "user", "content": user_content})

        # 4. Get model and build system prompt
        model = await _get_model(db)
        provider = _detect_provider(model)
        system_prompt = await _build_system_prompt(db, project_id=project_id, provider=provider)

        # 5. Stream tokens
        full_content = ""
        input_tokens = 0
        output_tokens = 0

        try:
            async for token, in_tok, out_tok in _stream_tokens(model, api_messages, system_prompt, db):
                if token:
                    full_content += token
                    await manager.send_to(client_id, WS_CHAT_TOKEN, {"token": token})
                if in_tok or out_tok:
                    input_tokens = in_tok
                    output_tokens = out_tok

        except AnthropicQuotaExceededError as e:
            quota_error_text = (
                "⚠ Anthropic quota exceeded. Operations halted. "
                "Check your API usage at console.anthropic.com."
            )
            await manager.send_to(client_id, WS_CHAT_ERROR, {"error": quota_error_text})

            from opvs.models.notification import NotificationSourceType
            from opvs.schemas.notification import NotificationCreate
            from opvs.services.notification_service import create_notification

            await create_notification(
                db,
                NotificationCreate(
                    title="Anthropic quota exceeded — operations halted",
                    body=str(e)[:500],
                    source_type=NotificationSourceType.SYSTEM,
                    priority=10,
                ),
            )

            error_record = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=quota_error_text,
                token_count=0,
                is_compact_summary=False,
                project_id=project_id,
            )
            db.add(error_record)
            await db.flush()
            await db.refresh(error_record)
            return error_record

        # 6. Save assistant response
        total_tokens = input_tokens + output_tokens
        assistant_msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=full_content,
            token_count=total_tokens,
            is_compact_summary=False,
            project_id=project_id,
        )
        db.add(assistant_msg)
        await db.flush()
        await db.refresh(assistant_msg)

        # 7. Broadcast complete
        await manager.send_to(
            client_id,
            WS_CHAT_COMPLETE,
            {"message_id": assistant_msg.id, "token_count": total_tokens},
        )

        # 8. Check compaction
        await _compact_if_needed(db, total_tokens, project_id=project_id)

        return assistant_msg

    except Exception as e:
        logger.error("orchestrator send_message error: %s", e, exc_info=True)
        await manager.send_to(client_id, WS_CHAT_ERROR, {"error": str(e)})
        error_msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=f"An error occurred: {e}",
            token_count=0,
            is_compact_summary=False,
            project_id=project_id,
        )
        db.add(error_msg)
        await db.flush()
        await db.refresh(error_msg)
        return error_msg


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
