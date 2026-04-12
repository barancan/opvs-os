import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_killswitch_initial_status(client: AsyncClient) -> None:
    response = await client.get("/api/killswitch/status")
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is False
    assert data["activated_at"] is None


@pytest.mark.asyncio
async def test_killswitch_activate(client: AsyncClient) -> None:
    response = await client.post("/api/killswitch/activate")
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is True
    assert data["activated_at"] is not None


@pytest.mark.asyncio
async def test_killswitch_status_after_activate(client: AsyncClient) -> None:
    await client.post("/api/killswitch/activate")
    response = await client.get("/api/killswitch/status")
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is True


@pytest.mark.asyncio
async def test_killswitch_recover(client: AsyncClient, tmp_path: object) -> None:
    await client.post("/api/killswitch/activate")
    response = await client.post(
        "/api/killswitch/recover",
        json={"reason": "test recovery"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is False


@pytest.mark.asyncio
async def test_killswitch_status_after_recover(client: AsyncClient) -> None:
    await client.post("/api/killswitch/activate")
    await client.post("/api/killswitch/recover", json={"reason": "test"})
    response = await client.get("/api/killswitch/status")
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is False
