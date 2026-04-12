import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_notification(client: AsyncClient) -> None:
    response = await client.post(
        "/api/notifications",
        json={"title": "Test", "body": "Test body"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test"
    assert data["body"] == "Test body"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_list_notifications(client: AsyncClient) -> None:
    await client.post(
        "/api/notifications",
        json={"title": "Test", "body": "Test body"},
    )
    response = await client.get("/api/notifications")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test"


@pytest.mark.asyncio
async def test_list_notifications_filter_pending(client: AsyncClient) -> None:
    await client.post(
        "/api/notifications",
        json={"title": "Test", "body": "Test body"},
    )
    response = await client.get("/api/notifications?status=pending")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = await client.get("/api/notifications?status=completed")
    assert response.status_code == 200
    assert len(response.json()) == 0


@pytest.mark.asyncio
async def test_update_notification_status_completed(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/notifications",
        json={"title": "Test", "body": "Test body"},
    )
    notification_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/notifications/{notification_id}/status",
        json={"status": "completed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_delete_notification(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/notifications",
        json={"title": "Test", "body": "Test body"},
    )
    notification_id = create_resp.json()["id"]

    response = await client.delete(f"/api/notifications/{notification_id}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}

    response = await client.get("/api/notifications")
    assert response.status_code == 200
    assert len(response.json()) == 0
