import pytest
from httpx import AsyncClient

from opvs.services import agent_runner


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
