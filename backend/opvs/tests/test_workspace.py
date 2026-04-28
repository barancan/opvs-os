"""
Tests for the workspace browser + LTM ingestion API.

Tests:
 1.  GET /workspace/tree returns CONTEXT.md and _memory/ node for a new project
 2.  GET /workspace/tree returns 404 for unknown project
 3.  GET /workspace/file reads a known file
 4.  GET /workspace/file with path traversal returns 400
 5.  GET /workspace/file for missing file returns 404
 6.  PUT /workspace/file updates an existing .md file
 7.  PUT /workspace/file with path traversal returns 400
 8.  PUT /workspace/file with non-.md extension returns 400
 9.  PUT /workspace/file for non-existent file returns 404
10.  POST /workspace/ingest happy path: file written, INDEX.md updated, notification created
11.  POST /workspace/ingest skips non-.md files
12.  POST /workspace/ingest skips files that exceed the 512 KB limit
13.  POST /workspace/ingest rejects an invalid section (422)
14.  POST /workspace/ingest for unknown project returns 404
"""

import io
import pathlib
from typing import Any

import pytest
from httpx import AsyncClient

from opvs import config as opvs_config
from opvs.api import workspace as workspace_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project(client: AsyncClient, name: str = "BrainTest") -> Any:
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201
    return dict(r.json())


def _make_upload(
    filename: str = "test-note.md",
    content: str = "# Test\n\nHello.",
) -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("files", (filename, io.BytesIO(content.encode()), "text/markdown"))


# ---------------------------------------------------------------------------
# 1. Tree returns CONTEXT.md + _memory node
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_tree_new_project(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client)
    project_id = int(project["id"])

    r = await client.get(f"/api/projects/{project_id}/workspace/tree")
    assert r.status_code == 200
    nodes = r.json()["nodes"]
    names = [n["name"] for n in nodes]
    assert "CONTEXT.md" in names
    assert "_memory" in names

    memory_node = next(n for n in nodes if n["name"] == "_memory")
    assert memory_node["type"] == "dir"
    assert isinstance(memory_node["children"], list)


# ---------------------------------------------------------------------------
# 2. Tree 404 for unknown project
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_tree_unknown_project(client: AsyncClient) -> None:
    r = await client.get("/api/projects/99999/workspace/tree")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 3. File read — success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_file_read_success(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "ReadTest")
    project_id = int(project["id"])
    slug = str(project["slug"])

    # Write a known file into the project workspace
    stm = tmp_path / "projects" / slug / "_memory" / "stm" / "current.md"
    stm.write_text("# STM\n\nHello from STM.", encoding="utf-8")

    r = await client.get(
        f"/api/projects/{project_id}/workspace/file",
        params={"path": "_memory/stm/current.md"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["path"] == "_memory/stm/current.md"
    assert "Hello from STM." in data["content"]


# ---------------------------------------------------------------------------
# 4. File read — path traversal rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_file_read_path_traversal_rejected(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "TraversalRead")
    project_id = int(project["id"])

    r = await client.get(
        f"/api/projects/{project_id}/workspace/file",
        params={"path": "../../../etc/passwd"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 5. File read — missing file returns 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_file_read_missing(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "MissingRead")
    project_id = int(project["id"])

    r = await client.get(
        f"/api/projects/{project_id}/workspace/file",
        params={"path": "_memory/decisions/nonexistent.md"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 6. File write — success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_file_write_success(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "WriteTest")
    project_id = int(project["id"])
    slug = str(project["slug"])

    stm_path = tmp_path / "projects" / slug / "_memory" / "stm" / "current.md"
    stm_path.write_text("# Old", encoding="utf-8")

    r = await client.put(
        f"/api/projects/{project_id}/workspace/file",
        json={"path": "_memory/stm/current.md", "content": "# Updated\n\nNew content."},
    )
    assert r.status_code == 200
    assert r.json()["saved"] is True
    assert stm_path.read_text(encoding="utf-8") == "# Updated\n\nNew content."


# ---------------------------------------------------------------------------
# 7. File write — path traversal rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_file_write_path_traversal_rejected(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "TraversalWrite")
    project_id = int(project["id"])

    r = await client.put(
        f"/api/projects/{project_id}/workspace/file",
        json={"path": "../../evil.md", "content": "bad"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 8. File write — non-.md extension rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_file_write_non_md_rejected(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "NonMdWrite")
    project_id = int(project["id"])

    r = await client.put(
        f"/api/projects/{project_id}/workspace/file",
        json={"path": "_memory/evil.sh", "content": "rm -rf /"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 9. File write — non-existent file returns 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_file_write_nonexistent_returns_404(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "NoExistWrite")
    project_id = int(project["id"])

    r = await client.put(
        f"/api/projects/{project_id}/workspace/file",
        json={"path": "_memory/decisions/ghost.md", "content": "hi"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 10. Ingest happy path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_happy_path(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "IngestHappy")
    project_id = int(project["id"])
    slug = str(project["slug"])

    r = await client.post(
        f"/api/projects/{project_id}/workspace/ingest",
        data={"section": "decisions"},
        files=[_make_upload("auth-strategy.md", "# Auth Strategy\n\nUse JWT.")],
    )
    assert r.status_code == 200
    body = r.json()
    assert "auth-strategy.md" in body["imported"]
    assert body["skipped"] == []
    assert body["errors"] == []

    # File written to disk
    dest = tmp_path / "projects" / slug / "_memory" / "decisions" / "auth-strategy.md"
    assert dest.exists()
    assert "JWT" in dest.read_text(encoding="utf-8")

    # INDEX.md updated
    index = tmp_path / "projects" / slug / "_memory" / "INDEX.md"
    assert index.exists()
    assert "auth-strategy" in index.read_text(encoding="utf-8")

    # Notification created
    notif_r = await client.get(f"/api/notifications?project_id={project_id}")
    assert notif_r.status_code == 200
    titles = [n["title"] for n in notif_r.json()]
    assert any("decisions" in t for t in titles)


# ---------------------------------------------------------------------------
# 11. Ingest skips non-.md files
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_skips_non_markdown(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "IngestSkip")
    project_id = int(project["id"])

    r = await client.post(
        f"/api/projects/{project_id}/workspace/ingest",
        data={"section": "research"},
        files=[
            ("files", ("report.txt", io.BytesIO(b"text content"), "text/plain")),
            ("files", ("notes.md", io.BytesIO(b"# Notes"), "text/markdown")),
        ],
    )
    assert r.status_code == 200
    body = r.json()
    assert "notes.md" in body["imported"]
    assert any("report.txt" in s for s in body["skipped"])


# ---------------------------------------------------------------------------
# 12. Ingest skips files that exceed the 512 KB limit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_skips_oversized_files(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "IngestBig")
    project_id = int(project["id"])

    big_content = b"# Big\n\n" + b"x" * (workspace_module._MAX_INGEST_BYTES + 1)

    r = await client.post(
        f"/api/projects/{project_id}/workspace/ingest",
        data={"section": "research"},
        files=[("files", ("huge.md", io.BytesIO(big_content), "text/markdown"))],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == []
    assert any("huge.md" in s for s in body["skipped"])


# ---------------------------------------------------------------------------
# 13. Ingest rejects invalid section
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_invalid_section(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))
    project = await _create_project(client, "IngestBadSection")
    project_id = int(project["id"])

    r = await client.post(
        f"/api/projects/{project_id}/workspace/ingest",
        data={"section": "../../etc"},
        files=[_make_upload()],
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 14. Ingest for unknown project returns 404
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_unknown_project(
    client: AsyncClient,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opvs_config.settings, "workspace_path", str(tmp_path))

    r = await client.post(
        "/api/projects/99999/workspace/ingest",
        data={"section": "decisions"},
        files=[_make_upload()],
    )
    assert r.status_code == 404
