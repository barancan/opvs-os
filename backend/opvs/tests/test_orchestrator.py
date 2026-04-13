import asyncio
import pathlib
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.services.orchestrator_service import (
    ANTHROPIC_PREAMBLE_DEFAULT,
    AnthropicQuotaExceededError,
    _describe_tool_action,
    _detect_provider,
    _load_preamble,
    _pending_approvals,
    _tool_action_label,
    resolve_approval,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_only_call_llm(text: str) -> AsyncMock:
    """Return an AsyncMock for _call_llm that yields a single text block."""
    return AsyncMock(
        return_value=("end_turn", [{"type": "text", "text": text}], 10, 5)
    )


# ---------------------------------------------------------------------------
# Existing tests — chat history / compact status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_history_empty(client: AsyncClient) -> None:
    response = await client.get("/api/chat/history")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_clear_chat_history(client: AsyncClient) -> None:
    response = await client.delete("/api/chat/history")
    assert response.status_code == 200
    assert response.json() == {"cleared": True}


@pytest.mark.asyncio
async def test_compact_status_fresh(client: AsyncClient) -> None:
    response = await client.get("/api/chat/compact")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tokens"] == 0
    assert data["threshold"] == 150000
    assert data["compacted"] is False


# ---------------------------------------------------------------------------
# Existing tests — send_message (updated to mock _call_llm)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_chat_message_mocked(client: AsyncClient) -> None:
    with patch(
        "opvs.services.orchestrator_service._call_llm",
        _text_only_call_llm("Hello world"),
    ):
        response = await client.post(
            "/api/chat",
            json={"content": "Hello orchestrator"},
            params={"client_id": "test-client"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "assistant"
    assert data["content"] == "Hello world"

    history_resp = await client.get("/api/chat/history")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello orchestrator"
    assert history[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Existing tests — provider detection
# ---------------------------------------------------------------------------


def test_detect_provider_anthropic() -> None:
    assert _detect_provider("claude-sonnet-4-6") == "anthropic"


def test_detect_provider_ollama_gemma() -> None:
    assert _detect_provider("gemma3:4b") == "ollama"


def test_detect_provider_ollama_llama() -> None:
    assert _detect_provider("llama3.1:8b") == "ollama"


# ---------------------------------------------------------------------------
# Existing tests — preamble loading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_preamble_returns_default_when_empty(db_session: AsyncSession) -> None:
    """When DB key is empty, fall back to hardcoded default."""
    preamble = await _load_preamble(db_session, "anthropic")
    assert preamble == ANTHROPIC_PREAMBLE_DEFAULT


@pytest.mark.asyncio
async def test_load_preamble_returns_db_value(db_session: AsyncSession) -> None:
    """When orchestrator_preamble_anthropic is set in DB, return that value."""
    from opvs.models.settings import Setting

    custom = "Custom preamble for testing"
    setting = Setting(key="orchestrator_preamble_anthropic", value=custom)
    db_session.add(setting)
    await db_session.flush()

    preamble = await _load_preamble(db_session, "anthropic")
    assert preamble == custom


# ---------------------------------------------------------------------------
# Existing tests — fallback and quota (updated to mock _call_llm / _call_anthropic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_ollama_unreachable_falls_back_to_claude(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """When Ollama is unreachable, _call_llm falls back to Claude and creates a notification."""
    from opvs.models.settings import Setting

    db_session.add(Setting(key="orchestrator_model", value="gemma3:4b"))
    await db_session.flush()

    fallback_text = "[Ollama unavailable (gemma3:4b) — responding via claude-sonnet-4-6]\n\nFallback response"

    async def mock_call_llm(**_kwargs: object) -> tuple[str, list[dict[str, object]], int, int]:
        return ("end_turn", [{"type": "text", "text": fallback_text}], 10, 5)

    with patch(
        "opvs.services.orchestrator_service._call_llm",
        side_effect=mock_call_llm,
    ):
        response = await client.post(
            "/api/chat",
            json={"content": "Test fallback"},
            params={"client_id": "test-client"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "assistant"
    assert "Ollama unavailable" in data["content"]


@pytest.mark.asyncio
async def test_send_message_anthropic_quota_error_halts_no_fallback(
    client: AsyncClient,
) -> None:
    """When Anthropic raises a quota error, send_message returns error message
    and creates a notification. It must NOT fall back to another model."""
    call_count = 0

    async def quota_error_call_llm(
        **_kwargs: object,
    ) -> tuple[str, list[dict[str, object]], int, int]:
        nonlocal call_count
        call_count += 1
        raise AnthropicQuotaExceededError("Rate limit exceeded")

    with patch(
        "opvs.services.orchestrator_service._call_llm",
        side_effect=quota_error_call_llm,
    ):
        response = await client.post(
            "/api/chat",
            json={"content": "Test quota halt"},
            params={"client_id": "test-client"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "assistant"
    assert "quota exceeded" in data["content"].lower()

    # _call_llm must have been called exactly once — no retry/fallback
    assert call_count == 1

    # Notification should have been created
    notif_resp = await client.get("/api/notifications")
    assert notif_resp.status_code == 200
    notifications = notif_resp.json()
    quota_notifs = [n for n in notifications if "quota exceeded" in n["title"].lower()]
    assert len(quota_notifs) >= 1


# ---------------------------------------------------------------------------
# New tests — resolve_approval
# ---------------------------------------------------------------------------


def test_resolve_approval_unknown_request_id_returns_false() -> None:
    """resolve_approval with an unknown request_id must return False."""
    result = resolve_approval("nonexistent-id-xyz", approved=True)
    assert result is False


def test_resolve_approval_valid_request_id_returns_true_and_sets_event() -> None:
    """resolve_approval with a registered request_id returns True and sets the Event."""
    request_id = "test-resolve-123"
    event = asyncio.Event()
    _pending_approvals[request_id] = event

    try:
        result = resolve_approval(request_id, approved=True)
        assert result is True
        assert event.is_set()
    finally:
        _pending_approvals.pop(request_id, None)


# ---------------------------------------------------------------------------
# New tests — tool label / description helpers
# ---------------------------------------------------------------------------


def test_tool_action_label_create_issue() -> None:
    assert _tool_action_label("linear_create_issue") == "Create issue"


def test_describe_tool_action_create_issue_contains_title() -> None:
    desc = _describe_tool_action(
        "linear_create_issue", {"title": "Test", "team_id": "T1"}
    )
    assert "Test" in desc


# ---------------------------------------------------------------------------
# New tests — agentic loop via mocked _call_llm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_text_only_loop(client: AsyncClient) -> None:
    """Text-only response: saves user + assistant messages, broadcasts CHAT_COMPLETE."""
    with patch(
        "opvs.services.orchestrator_service._call_llm",
        _text_only_call_llm("Agentic response"),
    ):
        response = await client.post(
            "/api/chat",
            json={"content": "hello"},
            params={"client_id": "test-client"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Agentic response"

    history = (await client.get("/api/chat/history")).json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Agentic response"


@pytest.mark.asyncio
async def test_send_message_tool_use_no_approval(client: AsyncClient) -> None:
    """Tool_use block for a read tool (no approval) executes and loop finishes."""
    from opvs.skills.base import ToolResult

    call_count = 0

    async def mock_call_llm(**_kwargs: object) -> tuple[str, list[dict[str, object]], int, int]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First iteration: return a tool_use block
            return (
                "tool_use",
                [
                    {
                        "type": "tool_use",
                        "id": "tu_001",
                        "name": "workspace_list_files",
                        "input": {"directory": ""},
                    }
                ],
                10,
                5,
            )
        # Second iteration: return final text
        return ("end_turn", [{"type": "text", "text": "Files listed."}], 10, 5)

    mock_tool_result = ToolResult(success=True, content="[file] README.md")

    with patch(
        "opvs.services.orchestrator_service._call_llm",
        side_effect=mock_call_llm,
    ):
        with patch(
            "opvs.skills.workspace.WorkspaceSkill.execute_tool",
            AsyncMock(return_value=mock_tool_result),
        ):
            response = await client.post(
                "/api/chat",
                json={"content": "list workspace files"},
                params={"client_id": "test-client"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Files listed."
    assert call_count == 2

    # Tool exchange messages must NOT appear in history
    history = (await client.get("/api/chat/history")).json()
    roles = [m["role"] for m in history]
    assert "user" in roles
    assert "assistant" in roles
    # No tool_result or tool_use messages in DB
    for msg in history:
        assert msg["role"] in ("user", "assistant", "system")


# ---------------------------------------------------------------------------
# New tests — approve/reject endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_unknown_request_id_returns_404(client: AsyncClient) -> None:
    response = await client.post("/api/chat/approve/nonexistent-id-abc")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reject_unknown_request_id_returns_404(client: AsyncClient) -> None:
    response = await client.post("/api/chat/reject/nonexistent-id-abc")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# New tests — delta_update_stm bootstraps STM when none exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delta_update_stm_bootstraps_when_no_stm(
    tmp_path: pathlib.Path,
    db_session: AsyncSession,
) -> None:
    """delta_update_stm should write an STM file using a mocked LLM call."""
    from unittest.mock import MagicMock

    from opvs.models.settings import Setting
    from opvs.services.orchestrator_service import delta_update_stm

    # Point workspace_path to tmp_path so STM writes go there
    db_session.add(Setting(key="workspace_path", value=str(tmp_path)))
    await db_session.flush()

    mock_text_block = MagicMock()
    mock_text_block.text = (
        "## Active tasks\n- [test]: running\n\n"
        "## Recent decisions\n*(none yet)*\n\n"
        "## Open questions\n*(none yet)*\n\n"
        "## Key context\n*(none yet)*\n\n"
        "## Recent agent outputs\n*(none yet)*\n"
    )
    mock_response = MagicMock()
    mock_response.content = [mock_text_block]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("opvs.services.orchestrator_service.anthropic", mock_anthropic):
        await delta_update_stm(db_session, "test task started", project_id=None)

    stm_path = pathlib.Path(str(tmp_path)) / "projects" / "default" / "_memory" / "stm" / "current.md"
    assert stm_path.exists()
    content = stm_path.read_text()
    assert "Active tasks" in content


# ---------------------------------------------------------------------------
# New tests — COMPACTION_PROMPT_TEMPLATE has all five sections
# ---------------------------------------------------------------------------


def test_compaction_prompt_template_has_five_sections() -> None:
    from opvs.services.orchestrator_service import COMPACTION_PROMPT_TEMPLATE

    required_sections = [
        "## Active tasks",
        "## Recent decisions",
        "## Open questions",
        "## Key context",
        "## Recent agent outputs",
    ]
    for section in required_sections:
        assert section in COMPACTION_PROMPT_TEMPLATE, f"Missing section: {section}"


# ---------------------------------------------------------------------------
# New tests — MESSAGE_DELTA_THRESHOLD is 10
# ---------------------------------------------------------------------------


def test_message_delta_threshold_value() -> None:
    from opvs.services.orchestrator_service import MESSAGE_DELTA_THRESHOLD

    assert MESSAGE_DELTA_THRESHOLD == 10
