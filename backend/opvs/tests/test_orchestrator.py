from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401 — used in type hints

from opvs.services.orchestrator_service import (
    ANTHROPIC_PREAMBLE_DEFAULT,
    AnthropicQuotaExceededError,
    OllamaUnreachableError,
    _detect_provider,
    _load_preamble,
)

# ---------------------------------------------------------------------------
# Existing tests
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


@pytest.mark.asyncio
async def test_send_chat_message_mocked(client: AsyncClient) -> None:
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5

    mock_final_message = MagicMock()
    mock_final_message.usage = mock_usage

    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=None)
    mock_stream.text_stream = _async_gen(["Hello", " world"])
    mock_stream.get_final_message = AsyncMock(return_value=mock_final_message)

    mock_client_instance = AsyncMock()
    mock_client_instance.messages.stream = MagicMock(return_value=mock_stream)

    with patch(
        "opvs.services.orchestrator_service.anthropic.AsyncAnthropic",
        return_value=mock_client_instance,
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
# New tests — provider detection
# ---------------------------------------------------------------------------


def test_detect_provider_anthropic() -> None:
    assert _detect_provider("claude-sonnet-4-6") == "anthropic"


def test_detect_provider_ollama_gemma() -> None:
    assert _detect_provider("gemma3:4b") == "ollama"


def test_detect_provider_ollama_llama() -> None:
    assert _detect_provider("llama3.1:8b") == "ollama"


# ---------------------------------------------------------------------------
# New tests — preamble loading
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
# New tests — fallback and quota error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_ollama_unreachable_falls_back_to_claude(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """When Ollama is unreachable, send_message falls back to Claude and creates a notification."""
    from opvs.models.settings import Setting

    # Set model to an Ollama model
    db_session.add(Setting(key="orchestrator_model", value="gemma3:4b"))
    await db_session.flush()

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5

    mock_final_message = MagicMock()
    mock_final_message.usage = mock_usage

    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=None)
    mock_stream.text_stream = _async_gen(["Fallback", " response"])
    mock_stream.get_final_message = AsyncMock(return_value=mock_final_message)

    mock_client_instance = AsyncMock()
    mock_client_instance.messages.stream = MagicMock(return_value=mock_stream)

    async def raise_ollama_unreachable(
        model: str,
        messages: object,
        system: str,
        ollama_host: str,
    ) -> AsyncGenerator[tuple[str, int, int], None]:
        raise OllamaUnreachableError("Connection refused")
        # Make mypy happy — this is unreachable but satisfies AsyncGenerator type
        yield ("", 0, 0)

    with (
        patch(
            "opvs.services.orchestrator_service._stream_ollama",
            side_effect=raise_ollama_unreachable,
        ),
        patch(
            "opvs.services.orchestrator_service.anthropic.AsyncAnthropic",
            return_value=mock_client_instance,
        ),
    ):
        response = await client.post(
            "/api/chat",
            json={"content": "Test fallback"},
            params={"client_id": "test-client"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "assistant"
    # Response should contain the fallback prefix
    assert "Ollama unavailable" in data["content"]
    assert "Fallback response" in data["content"]

    # Notification should have been created
    notif_resp = await client.get("/api/notifications")
    assert notif_resp.status_code == 200
    notifications = notif_resp.json()
    ollama_notifs = [n for n in notifications if "Ollama unavailable" in n["title"]]
    assert len(ollama_notifs) >= 1


@pytest.mark.asyncio
async def test_send_message_anthropic_quota_error_halts_no_fallback(
    client: AsyncClient,
) -> None:
    """When Anthropic raises a quota error, send_message returns error message and creates
    notification. It must NOT fall back to another model."""
    call_count = 0

    async def quota_error_stream(
        model: str,
        messages: object,
        system: str,
        api_key: str,
    ) -> AsyncGenerator[tuple[str, int, int], None]:
        nonlocal call_count
        call_count += 1
        raise AnthropicQuotaExceededError("Rate limit exceeded")
        yield ("", 0, 0)

    with patch(
        "opvs.services.orchestrator_service._stream_anthropic",
        side_effect=quota_error_stream,
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

    # _stream_anthropic must have been called exactly once — no retry/fallback
    assert call_count == 1

    # Notification should have been created
    notif_resp = await client.get("/api/notifications")
    assert notif_resp.status_code == 200
    notifications = notif_resp.json()
    quota_notifs = [n for n in notifications if "quota exceeded" in n["title"].lower()]
    assert len(quota_notifs) >= 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_gen(items: list[str]) -> AsyncGenerator[str, None]:
    for item in items:
        yield item
