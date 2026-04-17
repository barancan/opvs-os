from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.agent_message import AgentMessage, SenderType
from opvs.models.agent_session import AgentSession
from opvs.services import agent_runner
from opvs.services.agent_runner import (
    CHATROOM_HISTORY_LIMIT,
    CHATROOM_HISTORY_WINDOW_HOURS,
    _build_agent_system_prompt,
    _format_chatroom_history,
    _relative_time,
    _tool_event_summary,
)


# ---------------------------------------------------------------------------
# Helper — create a persona so we have a valid persona_id
# ---------------------------------------------------------------------------
async def _create_persona(client: AsyncClient, name: str = "Test Bot") -> int:
    r = await client.post(
        "/api/personas",
        json={"name": name, "model": "claude-sonnet-4-6"},
    )
    assert r.status_code == 201
    return int(r.json()["id"])


# ---------------------------------------------------------------------------
# 1. POST /api/sessions creates a session and returns QUEUED status
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_spawn_session_returns_queued(client: AsyncClient) -> None:
    persona_id = await _create_persona(client)
    response = await client.post(
        "/api/sessions",
        json={"project_id": 1, "persona_id": persona_id, "task": "Write a summary"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "queued"
    assert data["persona_id"] == persona_id
    assert data["task"] == "Write a summary"
    assert data["project_id"] == 1
    assert "session_uuid" in data


# ---------------------------------------------------------------------------
# 2. GET /api/sessions?project_id=1 returns sessions for that project
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_sessions_project_scoped(client: AsyncClient) -> None:
    persona_id = await _create_persona(client, "Lister Bot")

    await client.post(
        "/api/sessions",
        json={"project_id": 1, "persona_id": persona_id, "task": "Task for p1"},
    )
    await client.post(
        "/api/sessions",
        json={"project_id": 2, "persona_id": persona_id, "task": "Task for p2"},
    )

    r = await client.get("/api/sessions?project_id=1")
    assert r.status_code == 200
    tasks = [s["task"] for s in r.json()]
    assert "Task for p1" in tasks
    assert "Task for p2" not in tasks


# ---------------------------------------------------------------------------
# 3. POST /api/sessions/{uuid}/halt with unknown uuid returns 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_halt_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.post("/api/sessions/nonexistent-uuid-1234/halt")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4. GET /api/sessions/chatroom/messages?project_id=1 returns empty list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chatroom_messages_empty(client: AsyncClient) -> None:
    response = await client.get("/api/sessions/chatroom/messages?project_id=99")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# 5. POST /api/sessions/chatroom/reply posts user message and returns it
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_post_user_reply_to_chatroom(client: AsyncClient) -> None:
    response = await client.post(
        "/api/sessions/chatroom/reply",
        json={
            "project_id": 1,
            "sender_type": "user",
            "sender_name": "You",
            "content": "Hello from the user!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Hello from the user!"
    assert data["sender_type"] == "user"
    assert data["project_id"] == 1
    assert data["response_provided"] is False

    # Verify it appears in the chatroom
    msgs_r = await client.get("/api/sessions/chatroom/messages?project_id=1")
    assert msgs_r.status_code == 200
    contents = [m["content"] for m in msgs_r.json()]
    assert "Hello from the user!" in contents


# ---------------------------------------------------------------------------
# 6. get_running_count() returns 0 on fresh start
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_running_count_zero_on_fresh_start() -> None:
    # Clear any stale tasks from other tests
    agent_runner._running_tasks.clear()
    assert agent_runner.get_running_count() == 0


# ---------------------------------------------------------------------------
# 7. Concurrency limit: mock running count, spawn_session raises 409
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrency_limit_returns_409(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    persona_id = await _create_persona(client, "Overflow Bot")
    # Patch get_running_count to simulate 2 running agents (default max)
    monkeypatch.setattr(agent_runner, "get_running_count", lambda: 2)

    response = await client.post(
        "/api/sessions",
        json={"project_id": 1, "persona_id": persona_id, "task": "One too many"},
    )
    assert response.status_code == 409
    assert "Concurrency limit" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Helpers for chatroom history tests
# ---------------------------------------------------------------------------

def _make_message(
    sender_name: str,
    content: str,
    sender_type: SenderType = SenderType.USER,
    minutes_ago: int = 10,
    project_id: int = 1,
) -> AgentMessage:
    msg = AgentMessage(
        project_id=project_id,
        sender_type=sender_type,
        sender_name=sender_name,
        content=content,
    )
    msg.created_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return msg


def _make_session(name: str = "TestBot") -> AgentSession:
    session = MagicMock(spec=AgentSession)
    session.persona_name = name
    session.instructions_snapshot = "Be helpful."
    return session  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 8. _relative_time formats correctly
# ---------------------------------------------------------------------------

def test_relative_time_just_now() -> None:
    dt = datetime.now(UTC) - timedelta(seconds=30)
    assert _relative_time(dt) == "just now"


def test_relative_time_minutes() -> None:
    dt = datetime.now(UTC) - timedelta(minutes=45)
    assert _relative_time(dt) == "45m ago"


def test_relative_time_hours() -> None:
    dt = datetime.now(UTC) - timedelta(hours=3)
    assert _relative_time(dt) == "3h ago"


# ---------------------------------------------------------------------------
# 9. _format_chatroom_history renders sender name, timestamp, and content
# ---------------------------------------------------------------------------

def test_format_chatroom_history_includes_sender_and_content() -> None:
    messages = [
        _make_message("Alice", "Can you check the auth issue?", minutes_ago=20),
        _make_message("ResearchBot", "Found 3 related tickets.", SenderType.AGENT, minutes_ago=10),
    ]
    output = _format_chatroom_history(messages)
    assert "Alice" in output
    assert "Can you check the auth issue?" in output
    assert "ResearchBot" in output
    assert "Found 3 related tickets." in output


def test_format_chatroom_history_preserves_order() -> None:
    messages = [
        _make_message("Alice", "First message", minutes_ago=30),
        _make_message("Bob", "Second message", minutes_ago=10),
    ]
    output = _format_chatroom_history(messages)
    assert output.index("First message") < output.index("Second message")


# ---------------------------------------------------------------------------
# 10. _build_agent_system_prompt injects history / shows empty placeholder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_prompt_injects_chatroom_history(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recent_msg = _make_message("Alice", "Please look into the payment bug", minutes_ago=30)
    db_session.add(recent_msg)
    await db_session.commit()

    session = _make_session("BugBot")

    monkeypatch.setattr(
        agent_runner, "_get_workspace_path", AsyncMock(return_value="/tmp/ws")
    )

    prompt = await _build_agent_system_prompt(db_session, session, project_id=1)

    assert "Alice" in prompt
    assert "Please look into the payment bug" in prompt
    assert "Recent chatroom activity" in prompt
    assert "(No recent activity)" not in prompt


@pytest.mark.asyncio
async def test_system_prompt_shows_empty_placeholder_when_no_history(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _make_session("EmptyBot")

    monkeypatch.setattr(
        agent_runner, "_get_workspace_path", AsyncMock(return_value="/tmp/ws")
    )

    prompt = await _build_agent_system_prompt(db_session, session, project_id=999)

    assert "Recent chatroom activity" in prompt
    assert "(No recent activity)" in prompt


@pytest.mark.asyncio
async def test_system_prompt_excludes_system_sender_type(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_msg = _make_message(
        "System", "Task complete. Output sent to notifications.", SenderType.SYSTEM, minutes_ago=5
    )
    user_msg = _make_message("Alice", "Great work!", SenderType.USER, minutes_ago=3)
    db_session.add(system_msg)
    db_session.add(user_msg)
    await db_session.commit()

    session = _make_session("FilterBot")

    monkeypatch.setattr(
        agent_runner, "_get_workspace_path", AsyncMock(return_value="/tmp/ws")
    )

    prompt = await _build_agent_system_prompt(db_session, session, project_id=1)

    assert "Task complete. Output sent to notifications." not in prompt
    assert "Great work!" in prompt


@pytest.mark.asyncio
async def test_system_prompt_excludes_messages_outside_window(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_msg = _make_message(
        "Alice",
        "This is ancient history",
        minutes_ago=(CHATROOM_HISTORY_WINDOW_HOURS * 60) + 30,
    )
    recent_msg = _make_message("Bob", "This is recent", minutes_ago=10)
    db_session.add(old_msg)
    db_session.add(recent_msg)
    await db_session.commit()

    session = _make_session("WindowBot")

    monkeypatch.setattr(
        agent_runner, "_get_workspace_path", AsyncMock(return_value="/tmp/ws")
    )

    prompt = await _build_agent_system_prompt(db_session, session, project_id=1)

    assert "This is ancient history" not in prompt
    assert "This is recent" in prompt


# ---------------------------------------------------------------------------
# _tool_event_summary — deterministic summary from tool name + inputs
# ---------------------------------------------------------------------------

def test_tool_event_summary_workspace_read_file() -> None:
    assert _tool_event_summary("workspace_read_file", {"path": "_memory/stm/current.md"}) == \
        "Read _memory/stm/current.md"


def test_tool_event_summary_workspace_list_files_with_directory() -> None:
    result = _tool_event_summary("workspace_list_files", {"directory": "_memory"})
    assert result == "Listed files in _memory"


def test_tool_event_summary_workspace_list_files_empty_directory() -> None:
    result = _tool_event_summary("workspace_list_files", {})
    assert result == "Listed files in project root"


def test_tool_event_summary_workspace_capture() -> None:
    result = _tool_event_summary("workspace_capture", {"title": "Auth decisions", "content": "..."})
    assert result == "Captured: Auth decisions"


def test_tool_event_summary_workspace_write_ltm() -> None:
    result = _tool_event_summary(
        "workspace_write_ltm",
        {"section": "decisions", "filename": "auth-migration", "title": "T", "content": "C"},
    )
    assert result == "LTM write: decisions/auth-migration"


def test_tool_event_summary_linear_get_issue() -> None:
    result = _tool_event_summary("linear_get_issue", {"issue_id": "OPS-142"})
    assert result == "Fetched issue OPS-142"


def test_tool_event_summary_linear_search_issues() -> None:
    result = _tool_event_summary("linear_search_issues", {"query": "payment bug"})
    assert "payment bug" in result


def test_tool_event_summary_linear_create_issue() -> None:
    result = _tool_event_summary("linear_create_issue", {"title": "Fix login timeout", "team_id": "T1"})
    assert "Fix login timeout" in result


def test_tool_event_summary_unknown_tool() -> None:
    result = _tool_event_summary("some_future_tool", {"x": 1})
    assert "some_future_tool" in result


# ---------------------------------------------------------------------------
# system_prompt excludes EVENT messages from chatroom history injection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_prompt_excludes_event_messages(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_msg = _make_message(
        "ResearchBot", "Read _memory/stm/current.md", SenderType.EVENT, minutes_ago=5
    )
    user_msg = _make_message("Alice", "Good, keep going", SenderType.USER, minutes_ago=3)
    db_session.add(event_msg)
    db_session.add(user_msg)
    await db_session.commit()

    session = _make_session("AnotherBot")
    monkeypatch.setattr(agent_runner, "_get_workspace_path", AsyncMock(return_value="/tmp/ws"))

    prompt = await _build_agent_system_prompt(db_session, session, project_id=1)

    assert "Read _memory/stm/current.md" not in prompt
    assert "Good, keep going" in prompt
