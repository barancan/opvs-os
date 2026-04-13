"""
Agent runner — executes agent sessions using the agentic loop.

Key behaviors:
- Concurrency limit: read from settings (key: agent_max_concurrent, default: 2)
- Each session runs in its own asyncio.Task with its own DB session
- Agents can post questions to the chatroom and await responses
- A session can be halted via halt_session() which sets a stop event
- Kill switch halts all sessions immediately
"""
import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import AsyncSessionLocal
from opvs.models.agent_message import AgentMessage, SenderType
from opvs.models.agent_session import AgentSession, SessionStatus
from opvs.schemas.agent_session import AgentSessionResponse

logger = logging.getLogger(__name__)

# Running tasks: session_uuid → asyncio.Task
_running_tasks: dict[str, asyncio.Task[None]] = {}

# Halt events: session_uuid → asyncio.Event (set = halt requested)
_halt_events: dict[str, asyncio.Event] = {}

# Chatroom response events: agent_message_id → asyncio.Event
_chatroom_response_events: dict[int, asyncio.Event] = {}


def get_running_count() -> int:
    return len([t for t in _running_tasks.values() if not t.done()])


async def _get_max_concurrent(db: AsyncSession) -> int:
    from opvs.services.settings_service import get_setting

    setting = await get_setting(db, "agent_max_concurrent")
    try:
        return int(setting.value) if setting and setting.value else 2
    except ValueError:
        return 2


async def spawn_session(
    db: AsyncSession,
    project_id: int,
    persona_id: int,
    task: str,
) -> AgentSessionResponse:
    """
    Create a session record and start the agent task.
    Raises ValueError if at concurrency limit or persona not found.
    """
    from opvs.services.persona_service import get_persona

    max_concurrent = await _get_max_concurrent(db)
    if get_running_count() >= max_concurrent:
        raise ValueError(
            f"Concurrency limit reached ({max_concurrent} agents running). "
            f"Wait for one to complete or increase agent_max_concurrent in Settings."
        )

    persona = await get_persona(db, persona_id)
    if persona is None:
        raise ValueError(f"Persona {persona_id} not found")

    session_uuid = str(uuid.uuid4())

    session = AgentSession(
        session_uuid=session_uuid,
        project_id=project_id,
        persona_id=persona_id,
        persona_name=persona.name,
        task=task,
        status=SessionStatus.QUEUED,
        model_snapshot=persona.model,
        instructions_snapshot=persona.instructions,
        enabled_skills_snapshot=persona.enabled_skills,
        temperature_snapshot=persona.temperature,
        max_tokens_snapshot=persona.max_tokens,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    session_id = session.id

    halt_event = asyncio.Event()
    _halt_events[session_uuid] = halt_event

    task_obj: asyncio.Task[None] = asyncio.create_task(
        _run_session(session_id, session_uuid, project_id, halt_event)
    )
    _running_tasks[session_uuid] = task_obj

    return AgentSessionResponse.model_validate(session)


async def halt_session(session_uuid: str) -> bool:
    """Request halt for a specific session. Returns False if not running."""
    event = _halt_events.get(session_uuid)
    if event is None:
        return False
    event.set()
    return True


def resolve_chatroom_response(message_id: int) -> bool:
    """Called when user replies to an agent question. Unblocks the agent."""
    event = _chatroom_response_events.get(message_id)
    if event is None:
        return False
    event.set()
    return True


async def _run_session(
    session_id: int,
    session_uuid: str,
    project_id: int,
    halt_event: asyncio.Event,
) -> None:
    from opvs.models.notification import NotificationSourceType
    from opvs.models.project import Project
    from opvs.schemas.notification import NotificationCreate
    from opvs.services.notification_service import create_notification
    from opvs.services.orchestrator_service import (
        OllamaUnreachableError,
        _call_anthropic,
        _call_ollama_agentic,
        _detect_provider,
    )
    from opvs.skills.base import SkillContext
    from opvs.skills.registry import SKILL_MAP, find_tool, get_all_tool_definitions
    from opvs.websocket import (
        WS_AGENT_MESSAGE,
        WS_AGENT_TOKEN,
        WS_SESSION_COMPLETED,
        WS_SESSION_FAILED,
        WS_SESSION_HALTED,
        WS_SESSION_STARTED,
        manager,
    )

    async with AsyncSessionLocal() as db:
        # Load session record; bail out cleanly if not found (e.g. in tests)
        result = await db.execute(select(AgentSession).where(AgentSession.id == session_id))
        session = result.scalar_one_or_none()
        if session is None:
            logger.error("Session %d not found in DB — aborting runner task", session_id)
            return

        session.status = SessionStatus.RUNNING
        session.started_at = datetime.now(UTC)
        await db.commit()

        await manager.broadcast(
            WS_SESSION_STARTED,
            {
                "session_uuid": session_uuid,
                "project_id": project_id,
                "persona_name": session.persona_name,
            },
        )

        # Post "joined the chat" message
        join_msg = AgentMessage(
            project_id=project_id,
            session_uuid=session_uuid,
            sender_type=SenderType.AGENT,
            sender_name=session.persona_name,
            content=f"I'm online and starting my task: {session.task[:100]}",
        )
        db.add(join_msg)
        await db.commit()
        await db.refresh(join_msg)
        await manager.broadcast(
            WS_AGENT_MESSAGE,
            {
                "id": join_msg.id,
                "session_uuid": session_uuid,
                "sender_type": "agent",
                "sender_name": session.persona_name,
                "content": join_msg.content,
                "requires_response": False,
                "created_at": join_msg.created_at.isoformat(),
            },
        )

        try:
            # Build context
            system_prompt = await _build_agent_system_prompt(db, session, project_id)
            api_keys = await _load_api_keys(db)

            skill_ids = [
                s.strip()
                for s in session.enabled_skills_snapshot.split(",")
                if s.strip()
            ]
            enabled_skills = [SKILL_MAP[sid] for sid in skill_ids if sid in SKILL_MAP]

            proj_result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = proj_result.scalar_one_or_none()
            project_slug = project.slug if project else "default"
            workspace_path = await _get_workspace_path(db)

            skill_context = SkillContext(
                api_keys=api_keys,
                workspace_path=workspace_path,
                project_slug=project_slug,
                project_id=project_id,
            )
            tool_definitions = get_all_tool_definitions(enabled_skills)

            # Agentic loop
            messages: list[dict[str, Any]] = [{"role": "user", "content": session.task}]
            full_response = ""
            total_tokens = 0
            MAX_ITER = 10
            client_id = f"agent_{session_uuid}"

            for _iteration in range(MAX_ITER):
                if halt_event.is_set():
                    raise asyncio.CancelledError("Halted by user")

                model = session.model_snapshot
                provider = _detect_provider(model)

                if provider == "anthropic":
                    stop_reason, content_blocks, in_tok, out_tok = (
                        await _call_anthropic(
                            model, messages, system_prompt, tool_definitions, db, client_id
                        )
                    )
                else:
                    try:
                        stop_reason, content_blocks, in_tok, out_tok = (
                            await _call_ollama_agentic(
                                model, messages, system_prompt, tool_definitions, db, client_id
                            )
                        )
                    except OllamaUnreachableError as e:
                        raise RuntimeError(f"Ollama unreachable: {e}") from e

                total_tokens += in_tok + out_tok
                tool_results: list[dict[str, Any]] = []

                for block in content_blocks:
                    if block["type"] == "text":
                        text = str(block.get("text", ""))
                        full_response += text

                        # If the agent is asking a question, post it and wait
                        if text.strip().endswith("?") and len(text.strip()) > 20:
                            await _post_question(
                                db,
                                project_id,
                                session_uuid,
                                session.persona_name,
                                text,
                                halt_event,
                            )

                        await manager.send_to(
                            client_id,
                            WS_AGENT_TOKEN,
                            {"content": text, "session_uuid": session_uuid},
                        )

                    elif block["type"] == "tool_use":
                        tool_id = str(block["id"])
                        tool_name = str(block["name"])
                        tool_input: dict[str, Any] = dict(block.get("input", {}))

                        found = find_tool(tool_name, enabled_skills)
                        if found is None:
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": f"Tool not available: {tool_name}",
                                }
                            )
                            continue

                        skill, tool_def = found
                        if tool_def.requires_approval:
                            approved = await _request_approval_via_chat(
                                db,
                                project_id,
                                session_uuid,
                                session.persona_name,
                                tool_name,
                                tool_input,
                                halt_event,
                            )
                            if not approved:
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": tool_id,
                                        "content": "Action rejected by user.",
                                    }
                                )
                                continue

                        tool_result = await skill.execute_tool(
                            tool_name, tool_input, skill_context
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": (
                                    tool_result.content
                                    if tool_result.success
                                    else f"Tool failed: {tool_result.content}"
                                ),
                            }
                        )

                messages.append({"role": "assistant", "content": content_blocks})
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})

                if stop_reason == "end_turn" or not tool_results:
                    break

            # Session completed successfully
            session.status = SessionStatus.COMPLETED
            session.completed_at = datetime.now(UTC)
            session.total_tokens = total_tokens
            session.result_summary = full_response[:1000]
            await db.commit()

            await create_notification(
                db,
                NotificationCreate(
                    title=f"Agent complete: {session.persona_name}",
                    body=full_response[:500],
                    source_type=NotificationSourceType.AGENT,
                    agent_id=str(session.persona_id),
                    session_id=session_uuid,
                    project_id=project_id,
                ),
            )

            done_msg = AgentMessage(
                project_id=project_id,
                session_uuid=session_uuid,
                sender_type=SenderType.AGENT,
                sender_name=session.persona_name,
                content="Task complete. My output has been sent to your notifications.",
            )
            db.add(done_msg)
            await db.commit()
            await db.refresh(done_msg)
            await manager.broadcast(
                WS_AGENT_MESSAGE,
                {
                    "id": done_msg.id,
                    "session_uuid": session_uuid,
                    "sender_type": "agent",
                    "sender_name": session.persona_name,
                    "content": done_msg.content,
                    "requires_response": False,
                    "created_at": done_msg.created_at.isoformat(),
                },
            )
            await manager.broadcast(
                WS_SESSION_COMPLETED,
                {"session_uuid": session_uuid, "project_id": project_id},
            )

        except asyncio.CancelledError:
            session.status = SessionStatus.HALTED
            session.completed_at = datetime.now(UTC)
            await db.commit()
            await manager.broadcast(WS_SESSION_HALTED, {"session_uuid": session_uuid})

        except Exception as e:
            logger.error("Session %s failed: %s", session_uuid, e)
            session.status = SessionStatus.FAILED
            session.completed_at = datetime.now(UTC)
            session.error_message = str(e)[:500]
            await db.commit()
            await create_notification(
                db,
                NotificationCreate(
                    title=f"Agent failed: {session.persona_name}",
                    body=str(e)[:300],
                    source_type=NotificationSourceType.AGENT,
                    agent_id=str(session.persona_id),
                    session_id=session_uuid,
                    project_id=project_id,
                    priority=5,
                ),
            )
            await manager.broadcast(
                WS_SESSION_FAILED,
                {"session_uuid": session_uuid, "error": str(e)[:200]},
            )

        finally:
            _running_tasks.pop(session_uuid, None)
            _halt_events.pop(session_uuid, None)


async def _build_agent_system_prompt(
    db: AsyncSession, session: AgentSession, project_id: int
) -> str:
    import pathlib

    from sqlalchemy import select as sa_select

    from opvs.models.project import Project

    workspace_path = await _get_workspace_path(db)

    proj_result = await db.execute(
        sa_select(Project).where(Project.id == project_id)
    )
    project = proj_result.scalar_one_or_none()
    project_name = project.name if project else "Unknown"
    project_slug = project.slug if project else "default"

    stm_path = (
        pathlib.Path(workspace_path)
        / "projects"
        / project_slug
        / "_memory"
        / "stm"
        / "current.md"
    )
    stm = stm_path.read_text() if stm_path.exists() else ""

    return f"""You are {session.persona_name}, an AI agent.

## Your instructions
{session.instructions_snapshot}

## Hard constraints
- No shell commands
- Only write files within your session directory or _memory/inbox/
- No direct external API calls — use only your available tools
- If you need to ask a question, state it clearly ending with a ?

## Project context
Project: {project_name}

## Short-term memory
{stm if stm and "No context" not in stm else "(No memory yet)"}

## Chatroom
You are connected to the agent chatroom. Other agents and the user can see
your messages. If you need help, ask — end your question with a ?
"""


async def _post_question(
    db: AsyncSession,
    project_id: int,
    session_uuid: str,
    sender_name: str,
    question: str,
    halt_event: asyncio.Event,
) -> None:
    """Post a question to the chatroom and wait for a response."""
    from opvs.websocket import WS_AGENT_MESSAGE, WS_SESSION_WAITING, manager

    msg = AgentMessage(
        project_id=project_id,
        session_uuid=session_uuid,
        sender_type=SenderType.AGENT,
        sender_name=sender_name,
        content=question,
        requires_response=True,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    event: asyncio.Event = asyncio.Event()
    _chatroom_response_events[msg.id] = event

    await manager.broadcast(
        WS_SESSION_WAITING, {"session_uuid": session_uuid, "message_id": msg.id}
    )
    await manager.broadcast(
        WS_AGENT_MESSAGE,
        {
            "id": msg.id,
            "session_uuid": session_uuid,
            "sender_type": "agent",
            "sender_name": sender_name,
            "content": question,
            "requires_response": True,
            "created_at": msg.created_at.isoformat(),
        },
    )

    wait_task = asyncio.create_task(event.wait())
    halt_task = asyncio.create_task(halt_event.wait())
    done, pending = await asyncio.wait(
        [wait_task, halt_task], return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()
    _chatroom_response_events.pop(msg.id, None)


async def _request_approval_via_chat(
    db: AsyncSession,
    project_id: int,
    session_uuid: str,
    sender_name: str,
    tool_name: str,
    tool_input: dict[str, Any],
    halt_event: asyncio.Event,
) -> bool:
    """Post a tool approval request to the chatroom. Returns True if approved."""
    from opvs.websocket import WS_AGENT_MESSAGE, manager

    content = (
        f"I need your approval to run **{tool_name}** with these parameters:\n"
        f"```json\n{json.dumps(tool_input, indent=2)[:500]}\n```\n"
        f"Reply **approve** to proceed or **reject** to skip."
    )
    msg = AgentMessage(
        project_id=project_id,
        session_uuid=session_uuid,
        sender_type=SenderType.AGENT,
        sender_name=sender_name,
        content=content,
        requires_response=True,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    event: asyncio.Event = asyncio.Event()
    _chatroom_response_events[msg.id] = event

    await manager.broadcast(
        WS_AGENT_MESSAGE,
        {
            "id": msg.id,
            "session_uuid": session_uuid,
            "sender_type": "agent",
            "sender_name": sender_name,
            "content": content,
            "requires_response": True,
            "message_id_for_approval": msg.id,
            "created_at": msg.created_at.isoformat(),
        },
    )

    wait_task = asyncio.create_task(event.wait())
    halt_task = asyncio.create_task(halt_event.wait())
    done, pending = await asyncio.wait(
        [wait_task, halt_task], return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()
    _chatroom_response_events.pop(msg.id, None)

    if halt_event.is_set():
        return False

    # Check the reply content
    reply_result = await db.execute(
        select(AgentMessage).where(AgentMessage.reply_to_id == msg.id).limit(1)
    )
    reply = reply_result.scalar_one_or_none()
    return bool(reply and "approve" in reply.content.lower())


async def _get_workspace_path(db: AsyncSession) -> str:
    from opvs.config import settings as app_settings
    from opvs.services.settings_service import get_setting

    setting = await get_setting(db, "workspace_path")
    return setting.value if setting and setting.value else app_settings.workspace_path


async def _load_api_keys(db: AsyncSession) -> dict[str, str]:
    from opvs.services.settings_service import get_setting

    keys = ["linear_api_key", "anthropic_api_key"]
    result: dict[str, str] = {}
    for key in keys:
        setting = await get_setting(db, key)
        result[key] = setting.value if setting and setting.value else ""
    return result
