import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# 1. POST /api/personas creates persona, enabled_skills returned as list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_persona_returns_201(client: AsyncClient) -> None:
    response = await client.post(
        "/api/personas",
        json={
            "name": "Research Bot",
            "description": "Handles research tasks",
            "model": "claude-sonnet-4-6",
            "enabled_skills": ["workspace", "linear"],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Research Bot"
    assert data["description"] == "Handles research tasks"
    assert isinstance(data["enabled_skills"], list)
    assert "workspace" in data["enabled_skills"]
    assert "linear" in data["enabled_skills"]
    assert data["is_active"] is True


# ---------------------------------------------------------------------------
# 2. GET /api/personas returns active personas only by default
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_personas_active_only_by_default(client: AsyncClient) -> None:
    # Create two personas
    r1 = await client.post("/api/personas", json={"name": "Active Bot"})
    r2 = await client.post("/api/personas", json={"name": "Inactive Bot"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    persona_id = r2.json()["id"]

    # Deactivate second persona
    await client.put(f"/api/personas/{persona_id}", json={"is_active": False})

    response = await client.get("/api/personas")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert "Active Bot" in names
    assert "Inactive Bot" not in names


# ---------------------------------------------------------------------------
# 3. GET /api/personas?active_only=false returns all
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_personas_all_when_active_only_false(client: AsyncClient) -> None:
    r1 = await client.post("/api/personas", json={"name": "Bot A"})
    r2 = await client.post("/api/personas", json={"name": "Bot B"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    persona_id = r2.json()["id"]

    await client.put(f"/api/personas/{persona_id}", json={"is_active": False})

    response = await client.get("/api/personas?active_only=false")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert "Bot A" in names
    assert "Bot B" in names


# ---------------------------------------------------------------------------
# 4. PUT /api/personas/{id} updates model and temperature
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_persona_model_and_temperature(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/personas",
        json={"name": "Updatable Bot", "model": "claude-sonnet-4-6", "temperature": 0.5},
    )
    persona_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/personas/{persona_id}",
        json={"model": "llama3", "temperature": 0.9},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "llama3"
    assert data["temperature"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# 5. PUT /api/personas/{id} with is_active=false soft-deletes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_soft_delete_via_is_active_false(client: AsyncClient) -> None:
    create_resp = await client.post("/api/personas", json={"name": "To Deactivate"})
    persona_id = create_resp.json()["id"]

    response = await client.put(f"/api/personas/{persona_id}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Should not appear in default listing
    list_resp = await client.get("/api/personas")
    names = [p["name"] for p in list_resp.json()]
    assert "To Deactivate" not in names


# ---------------------------------------------------------------------------
# 6. DELETE /api/personas/{id} removes it
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_persona(client: AsyncClient) -> None:
    create_resp = await client.post("/api/personas", json={"name": "Delete Me"})
    persona_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/personas/{persona_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"deleted": True}

    get_resp = await client.get(f"/api/personas/{persona_id}")
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Temperature validator: 1.5 raises 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_temperature_validator_rejects_out_of_range(client: AsyncClient) -> None:
    response = await client.post(
        "/api/personas",
        json={"name": "Bad Temp Bot", "temperature": 1.5},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 8. max_tokens validator: 100 raises 422
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_max_tokens_validator_rejects_too_small(client: AsyncClient) -> None:
    response = await client.post(
        "/api/personas",
        json={"name": "Bad Tokens Bot", "max_tokens": 100},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 9. enabled_skills round-trips: ["linear","workspace"] → stored → returned as list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enabled_skills_round_trip(client: AsyncClient) -> None:
    response = await client.post(
        "/api/personas",
        json={"name": "Skills Bot", "enabled_skills": ["linear", "workspace"]},
    )
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["enabled_skills"], list)
    assert set(data["enabled_skills"]) == {"linear", "workspace"}

    # Verify via GET as well
    persona_id = data["id"]
    get_resp = await client.get(f"/api/personas/{persona_id}")
    assert get_resp.status_code == 200
    assert isinstance(get_resp.json()["enabled_skills"], list)
    assert set(get_resp.json()["enabled_skills"]) == {"linear", "workspace"}
