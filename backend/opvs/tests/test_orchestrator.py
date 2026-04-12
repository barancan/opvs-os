from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


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
    mock_text_stream = AsyncMock()
    mock_text_stream.__aiter__ = AsyncMock(return_value=iter(["Hello", " world"]))

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


async def _async_gen(items: list[str]) -> AsyncGenerator[str, None]:
    for item in items:
        yield item
