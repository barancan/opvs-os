import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_settings_empty(client: AsyncClient) -> None:
    response = await client.get("/api/settings/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_upsert_setting_non_secret(client: AsyncClient) -> None:
    response = await client.put(
        "/api/settings/test_key", json={"value": "hello", "is_secret": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "test_key"
    assert data["value"] == "hello"


@pytest.mark.asyncio
async def test_upsert_setting_secret_masked(client: AsyncClient) -> None:
    response = await client.put(
        "/api/settings/secret_key", json={"value": "supersecret", "is_secret": True}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "****cret"


@pytest.mark.asyncio
async def test_get_setting(client: AsyncClient) -> None:
    await client.put(
        "/api/settings/test_key", json={"value": "hello", "is_secret": False}
    )
    response = await client.get("/api/settings/test_key")
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "test_key"
    assert data["value"] == "hello"


@pytest.mark.asyncio
async def test_delete_setting(client: AsyncClient) -> None:
    await client.put(
        "/api/settings/test_key", json={"value": "hello", "is_secret": False}
    )
    response = await client.delete("/api/settings/test_key")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}

    response = await client.get("/api/settings/test_key")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_connection_test_unknown_service(client: AsyncClient) -> None:
    response = await client.post("/api/settings/test/unknown_service")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "Unknown service"


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
