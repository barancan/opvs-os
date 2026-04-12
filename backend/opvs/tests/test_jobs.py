from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient  # noqa: E402

VALID_JOB_PAYLOAD = {
    "project_id": 1,
    "name": "Daily standup",
    "cron": "0 7 * * *",
    "timezone": "UTC",
    "prompt": "Summarise yesterday's activity and post a standup update.",
}


@pytest.mark.asyncio
async def test_create_job(client: AsyncClient) -> None:
    with patch("opvs.services.job_service._register_job") as mock_register:
        response = await client.post("/api/jobs", json=VALID_JOB_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Daily standup"
    assert data["cron"] == "0 7 * * *"
    assert data["status"] == "active"
    assert data["project_id"] == 1
    assert data["id"] is not None
    mock_register.assert_called_once()


@pytest.mark.asyncio
async def test_list_jobs_project_scoped(client: AsyncClient) -> None:
    with patch("opvs.services.job_service._register_job"):
        await client.post("/api/jobs", json=VALID_JOB_PAYLOAD)
        await client.post(
            "/api/jobs",
            json={**VALID_JOB_PAYLOAD, "project_id": 2, "name": "Other project job"},
        )

    response = await client.get("/api/jobs?project_id=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["project_id"] == 1

    response = await client.get("/api/jobs?project_id=2")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_get_job(client: AsyncClient) -> None:
    with patch("opvs.services.job_service._register_job"):
        create_resp = await client.post("/api/jobs", json=VALID_JOB_PAYLOAD)
    job_id = create_resp.json()["id"]

    response = await client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["name"] == "Daily standup"


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/jobs9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_job_pause_removes_from_scheduler(client: AsyncClient) -> None:
    with patch("opvs.services.job_service._register_job"):
        create_resp = await client.post("/api/jobs", json=VALID_JOB_PAYLOAD)
    job_id = create_resp.json()["id"]

    with patch("opvs.services.job_service._remove_job") as mock_remove:
        response = await client.put(
            f"/api/jobs/{job_id}", json={"status": "paused"}
        )
    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    mock_remove.assert_called_once_with(job_id)


@pytest.mark.asyncio
async def test_delete_job(client: AsyncClient) -> None:
    with patch("opvs.services.job_service._register_job"):
        create_resp = await client.post("/api/jobs", json=VALID_JOB_PAYLOAD)
    job_id = create_resp.json()["id"]

    with patch("opvs.services.job_service._remove_job"):
        response = await client.delete(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}

    # Confirm it's gone
    response = await client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cron_validator_valid(client: AsyncClient) -> None:
    with patch("opvs.services.job_service._register_job"):
        response = await client.post("/api/jobs", json=VALID_JOB_PAYLOAD)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_cron_validator_invalid(client: AsyncClient) -> None:
    payload = {**VALID_JOB_PAYLOAD, "cron": "invalid"}
    response = await client.post("/api/jobs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_run_job_now(client: AsyncClient) -> None:
    with patch("opvs.services.job_service._register_job"):
        create_resp = await client.post("/api/jobs", json=VALID_JOB_PAYLOAD)
    job_id = create_resp.json()["id"]

    with patch("opvs.services.job_service._execute_job", new_callable=AsyncMock):
        with patch("asyncio.create_task") as mock_task:
            response = await client.post(f"/api/jobs/{job_id}/run")
    assert response.status_code == 200
    assert response.json() == {"status": "triggered"}
    mock_task.assert_called_once()


@pytest.mark.asyncio
async def test_run_job_now_not_found(client: AsyncClient) -> None:
    response = await client.post("/api/jobs9999/run")
    assert response.status_code == 404
