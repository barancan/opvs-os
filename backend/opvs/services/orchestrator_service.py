import logging
from datetime import datetime
from pathlib import Path

import anthropic
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

_STATIC_PREAMBLE = """\
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
Your short-term memory summary (if available) is included below in the system context.
Always read it before responding — it contains context from previous sessions.\
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


async def _build_system_prompt(db: AsyncSession) -> str:
    parts = [_STATIC_PREAMBLE]

    workspace_path = await _get_workspace_path(db)
    stm_file = workspace_path / "_memory" / "stm" / "current.md"
    if stm_file.exists():
        stm_content = stm_file.read_text(encoding="utf-8")
        parts.append(f"\n\n## Short-term memory\n\n{stm_content}")

    from opvs.services import killswitch_service

    ks_status = await killswitch_service.get_status(db)
    kill_switch_str = "ACTIVE — do not accept new task requests" if ks_status.active else "inactive"
    parts.append(f"\n\n## System state\n\n- Kill switch: {kill_switch_str}")

    from opvs.models.notification import NotificationStatus
    from opvs.services import notification_service

    pending = await notification_service.list_notifications(db, status=NotificationStatus.PENDING)
    parts.append(f"- Pending notifications: {len(pending)}")

    model = await _get_model(db)
    parts.append(f"- Orchestrator model: {model}")

    return "".join(parts)


async def _load_context_messages(db: AsyncSession) -> list[ChatMessage]:
    # Find most recent compact summary
    summary_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.is_compact_summary == True)  # noqa: E712
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    latest_summary = summary_result.scalar_one_or_none()

    if latest_summary is not None:
        subsequent_result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.id > latest_summary.id,
                ChatMessage.is_compact_summary == False,  # noqa: E712
            )
            .order_by(ChatMessage.id.asc())
            .limit(50)
        )
        subsequent = list(subsequent_result.scalars().all())
        return [latest_summary, *subsequent]
    else:
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.is_compact_summary == False)  # noqa: E712
            .order_by(ChatMessage.id.desc())
            .limit(50)
        )
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
            # Only USER and ASSISTANT roles reach the API; SYSTEM is only used for
            # compact summaries handled above. We assert the literal type here.
            assert msg.role in (MessageRole.USER, MessageRole.ASSISTANT)
            api_role: anthropic.types.MessageParam = {
                "role": "user" if msg.role == MessageRole.USER else "assistant",
                "content": msg.content,
            }
            api_messages.append(api_role)
    return api_messages


async def get_history(db: AsyncSession, limit: int = 50) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage).order_by(ChatMessage.created_at.asc()).limit(limit)
    )
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
    return total, COMPACT_THRESHOLD_TOKENS, compacted


async def send_message(
    db: AsyncSession,
    user_content: str,
    client_id: str,
) -> ChatMessage:
    # 1. Save user message
    user_msg = ChatMessage(
        role=MessageRole.USER,
        content=user_content,
        token_count=0,
        is_compact_summary=False,
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
        )
        db.add(assistant_msg)
        await db.flush()
        await db.refresh(assistant_msg)
        await manager.send_to(client_id, WS_CHAT_COMPLETE, {"message_id": assistant_msg.id})
        return assistant_msg

    try:
        # 3. Load history and build messages
        context_messages = await _load_context_messages(db)
        api_messages = _build_api_messages(context_messages)
        # Append current user message
        api_messages.append({"role": "user", "content": user_content})

        # 4. Build system prompt
        system_prompt = await _build_system_prompt(db)

        # 5. Get model
        model = await _get_model(db)

        # 6. Get API key
        api_key = await _get_setting_value(db, "anthropic_api_key")
        client = anthropic.AsyncAnthropic(api_key=api_key if api_key else None)

        # 7. Stream response
        full_content = ""
        output_tokens = 0

        async with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=api_messages,
        ) as stream:
            async for text in stream.text_stream:
                full_content += text
                await manager.send_to(client_id, WS_CHAT_TOKEN, {"token": text})
            final_message = await stream.get_final_message()
            output_tokens = final_message.usage.output_tokens

        # 8. Save assistant response
        assistant_msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=full_content,
            token_count=output_tokens,
            is_compact_summary=False,
        )
        db.add(assistant_msg)
        await db.flush()
        await db.refresh(assistant_msg)

        # 9. Broadcast complete
        await manager.send_to(
            client_id,
            WS_CHAT_COMPLETE,
            {"message_id": assistant_msg.id, "token_count": output_tokens},
        )

        # 10. Check compaction
        await _compact_if_needed(db, output_tokens)

        return assistant_msg

    except Exception as e:
        logger.error("orchestrator send_message error: %s", e, exc_info=True)
        await manager.send_to(client_id, WS_CHAT_ERROR, {"error": str(e)})
        error_msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=f"An error occurred: {e}",
            token_count=0,
            is_compact_summary=False,
        )
        db.add(error_msg)
        await db.flush()
        await db.refresh(error_msg)
        return error_msg


async def _compact_if_needed(db: AsyncSession, last_response_tokens: int) -> bool:
    summary_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.is_compact_summary == True)  # noqa: E712
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    latest_summary = summary_result.scalar_one_or_none()

    if latest_summary is not None:
        tokens_result = await db.execute(
            select(ChatMessage).where(
                ChatMessage.id > latest_summary.id,
                ChatMessage.is_compact_summary == False,  # noqa: E712
            )
        )
    else:
        tokens_result = await db.execute(
            select(ChatMessage).where(ChatMessage.is_compact_summary == False)  # noqa: E712
        )

    messages = list(tokens_result.scalars().all())
    total_tokens = sum(m.token_count for m in messages) + last_response_tokens

    if total_tokens >= COMPACT_THRESHOLD_TOKENS:
        await _run_compaction(db)
        return True
    return False


async def _run_compaction(db: AsyncSession) -> None:
    # 1. Load all current non-summary messages
    all_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.is_compact_summary == False)  # noqa: E712
        .order_by(ChatMessage.id.asc())
    )
    all_messages = list(all_result.scalars().all())

    if not all_messages:
        return

    conversation_text = "\n".join(
        f"{m.role.value.upper()}: {m.content}" for m in all_messages
    )
    compaction_prompt = _COMPACTION_PROMPT_TEMPLATE.format(messages=conversation_text)

    # 2. Call Claude for compaction summary
    model = await _get_model(db)
    api_key = await _get_setting_value(db, "anthropic_api_key")
    client = anthropic.AsyncAnthropic(api_key=api_key if api_key else None)

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": compaction_prompt}],
    )
    summary_text = ""
    for block in response.content:
        if isinstance(block, anthropic.types.TextBlock):
            summary_text = block.text
            break

    # 3. Write STM to workspace
    workspace_path = await _get_workspace_path(db)
    stm_dir = workspace_path / "_memory" / "stm"
    stm_dir.mkdir(parents=True, exist_ok=True)
    stm_file = stm_dir / "current.md"
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
        token_count=response.usage.output_tokens,
        is_compact_summary=True,
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
