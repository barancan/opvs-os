import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.schemas.notification import NotificationCreate
from opvs.services.notification_service import create_notification


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


@pytest.mark.asyncio
async def test_notification_body_not_truncated(client: AsyncClient) -> None:
    long_body = "x" * 2000
    response = await client.post(
        "/api/notifications",
        json={"title": "Long body test", "body": long_body},
    )
    assert response.status_code == 200
    assert response.json()["body"] == long_body


@pytest.mark.asyncio
async def test_notification_body_full_content_roundtrip(db_session: AsyncSession) -> None:
    long_body = "A" * 1500 + " — end marker"
    notification = await create_notification(
        db_session,
        NotificationCreate(title="Roundtrip test", body=long_body),
    )
    assert notification.body == long_body
    assert notification.body.endswith("— end marker")


@pytest.mark.asyncio
async def test_error_notification_includes_exception_type(db_session: AsyncSession) -> None:
    try:
        raise ValueError("something went wrong with detail")
    except Exception as e:
        body = f"{type(e).__name__}: {e}"

    notification = await create_notification(
        db_session,
        NotificationCreate(title="Agent failed: TestAgent", body=body),
    )
    assert "ValueError" in notification.body
    assert "something went wrong with detail" in notification.body


@pytest.mark.asyncio
async def test_error_notification_body_not_truncated(db_session: AsyncSession) -> None:
    long_error = "x" * 600
    try:
        raise RuntimeError(long_error)
    except Exception as e:
        body = f"{type(e).__name__}: {e}"

    notification = await create_notification(
        db_session,
        NotificationCreate(title="Job failed: test", body=body),
    )
    assert len(notification.body) > 600
    assert long_error in notification.body
