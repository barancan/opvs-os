import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.services import project_service


# ---------------------------------------------------------------------------
# 1. POST /api/projects creates a project with auto-generated slug
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_project_returns_201(client: AsyncClient) -> None:
    response = await client.post(
        "/api/projects",
        json={"name": "My Product", "description": "A test project"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Product"
    assert data["slug"] == "my-product"
    assert data["status"] == "active"
    assert data["linear_links"] == []


# ---------------------------------------------------------------------------
# 2. Slug generation: "My Product" → "my-product"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_slug_generation(client: AsyncClient) -> None:
    response = await client.post("/api/projects", json={"name": "  My Product!  "})
    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == "my-product"


# ---------------------------------------------------------------------------
# 3. Slug uniqueness: two projects named "Test" get "test" and "test-2"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_slug_uniqueness(client: AsyncClient) -> None:
    r1 = await client.post("/api/projects", json={"name": "Test"})
    r2 = await client.post("/api/projects", json={"name": "Test"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["slug"] == "test"
    assert r2.json()["slug"] == "test-2"


# ---------------------------------------------------------------------------
# 4. GET /api/projects returns all projects
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient) -> None:
    await client.post("/api/projects", json={"name": "Alpha"})
    await client.post("/api/projects", json={"name": "Beta"})
    response = await client.get("/api/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert "Alpha" in names
    assert "Beta" in names


# ---------------------------------------------------------------------------
# 5. GET /api/projects?status=active filters correctly
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_projects_filter_by_status(client: AsyncClient) -> None:
    create_resp = await client.post("/api/projects", json={"name": "ToArchive"})
    project_id = create_resp.json()["id"]
    await client.put(f"/api/projects/{project_id}", json={"status": "archived"})

    active_resp = await client.get("/api/projects?status=active")
    assert active_resp.status_code == 200
    active_names = [p["name"] for p in active_resp.json()]
    assert "ToArchive" not in active_names

    archived_resp = await client.get("/api/projects?status=archived")
    assert archived_resp.status_code == 200
    archived_names = [p["name"] for p in archived_resp.json()]
    assert "ToArchive" in archived_names


# ---------------------------------------------------------------------------
# 6. GET /api/projects/{id} returns project with linear_links list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_project_includes_linear_links(client: AsyncClient) -> None:
    create_resp = await client.post("/api/projects", json={"name": "Linkable"})
    project_id = create_resp.json()["id"]
    response = await client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert "linear_links" in data
    assert isinstance(data["linear_links"], list)


# ---------------------------------------------------------------------------
# 7. PUT /api/projects/{id} updates name and description
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_project_name_and_description(client: AsyncClient) -> None:
    create_resp = await client.post("/api/projects", json={"name": "Old Name"})
    project_id = create_resp.json()["id"]
    response = await client.put(
        f"/api/projects/{project_id}",
        json={"name": "New Name", "description": "Updated desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["description"] == "Updated desc"


# ---------------------------------------------------------------------------
# 8. PUT /api/projects/{id} with status=archived archives the project
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_archive_project(client: AsyncClient) -> None:
    create_resp = await client.post("/api/projects", json={"name": "Active Project"})
    project_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "active"

    response = await client.put(f"/api/projects/{project_id}", json={"status": "archived"})
    assert response.status_code == 200
    assert response.json()["status"] == "archived"


# ---------------------------------------------------------------------------
# 9. POST /api/projects/{id}/linear-links adds a Linear link
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_linear_link(client: AsyncClient) -> None:
    create_resp = await client.post("/api/projects", json={"name": "Linked Project"})
    project_id = create_resp.json()["id"]

    link_resp = await client.post(
        f"/api/projects/{project_id}/linear-links",
        json={"linear_project_id": "lin_proj_abc", "linear_project_name": "My Linear Project"},
    )
    assert link_resp.status_code == 201
    link_data = link_resp.json()
    assert link_data["linear_project_id"] == "lin_proj_abc"
    assert link_data["linear_project_name"] == "My Linear Project"
    assert link_data["project_id"] == project_id

    # Verify it appears in GET
    get_resp = await client.get(f"/api/projects/{project_id}")
    assert len(get_resp.json()["linear_links"]) == 1


# ---------------------------------------------------------------------------
# 10. DELETE /api/projects/{id}/linear-links/{link_id} removes it
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_remove_linear_link(client: AsyncClient) -> None:
    create_resp = await client.post("/api/projects", json={"name": "Project With Link"})
    project_id = create_resp.json()["id"]

    link_resp = await client.post(
        f"/api/projects/{project_id}/linear-links",
        json={"linear_project_id": "lin_proj_xyz", "linear_project_name": "XYZ Linear"},
    )
    link_id = link_resp.json()["id"]

    del_resp = await client.delete(f"/api/projects/{project_id}/linear-links/{link_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"deleted": True}

    get_resp = await client.get(f"/api/projects/{project_id}")
    assert get_resp.json()["linear_links"] == []


# ---------------------------------------------------------------------------
# 11. GET /api/notifications?project_id=1 returns project-scoped AND null-project items
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notifications_include_global_and_scoped(client: AsyncClient) -> None:
    create_resp = await client.post("/api/projects", json={"name": "Notify Project"})
    project_id = create_resp.json()["id"]

    # Global notification (no project_id)
    await client.post(
        "/api/notifications",
        json={"title": "Global", "body": "No project"},
    )
    # Scoped notification
    await client.post(
        "/api/notifications",
        json={"title": "Scoped", "body": "Has project", "project_id": project_id},
    )

    response = await client.get(f"/api/notifications?project_id={project_id}")
    assert response.status_code == 200
    titles = [n["title"] for n in response.json()]
    assert "Global" in titles
    assert "Scoped" in titles


# ---------------------------------------------------------------------------
# 12. GET /api/notifications?project_id=1 does NOT return project_id=2 notifications
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notifications_exclude_other_project(client: AsyncClient) -> None:
    r1 = await client.post("/api/projects", json={"name": "Project One"})
    r2 = await client.post("/api/projects", json={"name": "Project Two"})
    project_id_1 = r1.json()["id"]
    project_id_2 = r2.json()["id"]

    await client.post(
        "/api/notifications",
        json={"title": "For P2", "body": "Only P2", "project_id": project_id_2},
    )

    response = await client.get(f"/api/notifications?project_id={project_id_1}")
    assert response.status_code == 200
    titles = [n["title"] for n in response.json()]
    assert "For P2" not in titles


# ---------------------------------------------------------------------------
# 13. ensure_default_project called twice does not create a second default project
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ensure_default_project_idempotent(db_session: AsyncSession) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = await project_service.ensure_default_project(db_session, workspace_path=tmpdir)
        p2 = await project_service.ensure_default_project(db_session, workspace_path=tmpdir)

    assert p1.id == p2.id

    all_projects = await project_service.list_projects(db_session)
    assert len(all_projects) == 1
