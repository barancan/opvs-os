"""
Tests for durable approval state and restart recovery.

Tests:
 1.  expire_stale_approvals marks PENDING rows past their expires_at as EXPIRED
 2.  expire_stale_approvals leaves PENDING rows that have not yet expired
 3.  expire_stale_approvals leaves already-resolved (APPROVED/REJECTED) rows untouched
 4.  recover_interrupted_sessions marks RUNNING sessions as FAILED
 5.  recover_interrupted_sessions marks QUEUED sessions as FAILED
 6.  recover_interrupted_sessions marks WAITING sessions as FAILED
 7.  recover_interrupted_sessions leaves COMPLETED sessions untouched
 8.  recover_interrupted_sessions leaves HALTED and FAILED sessions untouched
 9.  recover_interrupted_sessions creates a system notification per interrupted session
10.  Multiple concurrent approval requests are all stored independently in the DB
11.  resolve_approval_db updates the status and sets resolved_at
12.  POST /chat/approve returns 409 with "expired" detail for an expired approval
13.  POST /chat/approve returns 409 with "already approved" for a resolved approval
14.  POST /chat/approve returns 404 for a completely unknown request_id
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.agent_session import AgentSession, SessionStatus
from opvs.models.tool_approval import ToolApproval, ToolApprovalSource, ToolApprovalStatus
from opvs.services.approval_service import (
    APPROVAL_EXPIRY_MINUTES,
    create_approval,
    expire_stale_approvals,
    get_approval,
    recover_interrupted_sessions,
    resolve_approval_db,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req_id() -> str:
    return str(uuid.uuid4())


async def _make_approval(
    db: AsyncSession,
    *,
    request_id: str | None = None,
    status: ToolApprovalStatus = ToolApprovalStatus.PENDING,
    minutes_ago: int = 0,
    expiry_minutes: int = APPROVAL_EXPIRY_MINUTES,
) -> ToolApproval:
    rid = request_id or _req_id()
    now = datetime.now(UTC)
    created = now - timedelta(minutes=minutes_ago)
    expires = created + timedelta(minutes=expiry_minutes)

    row = ToolApproval(
        request_id=rid,
        tool_name="linear_create_issue",
        platform="Linear",
        action="Create issue",
        description="Test approval",
        parameters="{}",
        status=status,
        source=ToolApprovalSource.ORCHESTRATOR,
        expires_at=expires,
        created_at=created,
    )
    db.add(row)
    await db.flush()
    return row


async def _make_session(
    db: AsyncSession,
    status: SessionStatus,
    persona_name: str = "TestBot",
    project_id: int = 1,
) -> AgentSession:
    session = AgentSession(
        session_uuid=str(uuid.uuid4()),
        project_id=project_id,
        persona_id=1,
        persona_name=persona_name,
        task="Test task",
        status=status,
        model_snapshot="claude-sonnet-4-6",
        instructions_snapshot="Be helpful.",
        enabled_skills_snapshot="workspace",
        temperature_snapshot=1.0,
        max_tokens_snapshot=4096,
    )
    db.add(session)
    await db.flush()
    return session


# ---------------------------------------------------------------------------
# 1. expire_stale_approvals — past expiry → EXPIRED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expire_stale_approvals_marks_pending_expired(
    db_session: AsyncSession,
) -> None:
    # Created 60 minutes ago, expiry window is 30 minutes → already past expiry
    stale = await _make_approval(
        db_session,
        minutes_ago=60,
        expiry_minutes=30,
    )
    await db_session.commit()

    count = await expire_stale_approvals(db_session)
    await db_session.commit()

    assert count == 1
    refreshed = await get_approval(db_session, stale.request_id)
    assert refreshed is not None
    assert refreshed.status == ToolApprovalStatus.EXPIRED
    assert refreshed.resolved_at is not None


# ---------------------------------------------------------------------------
# 2. expire_stale_approvals — within expiry window → untouched
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expire_stale_approvals_leaves_fresh_pending(
    db_session: AsyncSession,
) -> None:
    fresh = await _make_approval(
        db_session,
        minutes_ago=5,
        expiry_minutes=30,
    )
    await db_session.commit()

    count = await expire_stale_approvals(db_session)

    assert count == 0
    refreshed = await get_approval(db_session, fresh.request_id)
    assert refreshed is not None
    assert refreshed.status == ToolApprovalStatus.PENDING


# ---------------------------------------------------------------------------
# 3. expire_stale_approvals — already resolved → untouched
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expire_stale_approvals_leaves_resolved(
    db_session: AsyncSession,
) -> None:
    approved = await _make_approval(
        db_session,
        minutes_ago=60,
        expiry_minutes=30,
        status=ToolApprovalStatus.APPROVED,
    )
    rejected = await _make_approval(
        db_session,
        minutes_ago=60,
        expiry_minutes=30,
        status=ToolApprovalStatus.REJECTED,
    )
    await db_session.commit()

    count = await expire_stale_approvals(db_session)

    assert count == 0
    assert (await get_approval(db_session, approved.request_id)).status == ToolApprovalStatus.APPROVED  # type: ignore[union-attr]
    assert (await get_approval(db_session, rejected.request_id)).status == ToolApprovalStatus.REJECTED  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 4. recover_interrupted_sessions — RUNNING → FAILED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recover_running_session_marked_failed(
    db_session: AsyncSession,
) -> None:
    session = await _make_session(db_session, SessionStatus.RUNNING)
    await db_session.commit()

    count = await recover_interrupted_sessions(db_session)
    await db_session.commit()

    assert count == 1
    await db_session.refresh(session)
    assert session.status == SessionStatus.FAILED
    assert session.error_message is not None
    assert "restarted" in session.error_message
    assert session.completed_at is not None


# ---------------------------------------------------------------------------
# 5. recover_interrupted_sessions — QUEUED → FAILED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recover_queued_session_marked_failed(
    db_session: AsyncSession,
) -> None:
    session = await _make_session(db_session, SessionStatus.QUEUED)
    await db_session.commit()

    count = await recover_interrupted_sessions(db_session)

    assert count == 1
    await db_session.refresh(session)
    assert session.status == SessionStatus.FAILED


# ---------------------------------------------------------------------------
# 6. recover_interrupted_sessions — WAITING → FAILED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recover_waiting_session_marked_failed(
    db_session: AsyncSession,
) -> None:
    session = await _make_session(db_session, SessionStatus.WAITING)
    await db_session.commit()

    count = await recover_interrupted_sessions(db_session)

    assert count == 1
    await db_session.refresh(session)
    assert session.status == SessionStatus.FAILED


# ---------------------------------------------------------------------------
# 7. recover_interrupted_sessions — COMPLETED → untouched
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recover_leaves_completed_session(
    db_session: AsyncSession,
) -> None:
    session = await _make_session(db_session, SessionStatus.COMPLETED)
    await db_session.commit()

    count = await recover_interrupted_sessions(db_session)

    assert count == 0
    await db_session.refresh(session)
    assert session.status == SessionStatus.COMPLETED


# ---------------------------------------------------------------------------
# 8. recover_interrupted_sessions — HALTED and FAILED → untouched
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recover_leaves_terminal_sessions(
    db_session: AsyncSession,
) -> None:
    halted = await _make_session(db_session, SessionStatus.HALTED, "Bot1")
    failed = await _make_session(db_session, SessionStatus.FAILED, "Bot2")
    await db_session.commit()

    count = await recover_interrupted_sessions(db_session)

    assert count == 0
    await db_session.refresh(halted)
    await db_session.refresh(failed)
    assert halted.status == SessionStatus.HALTED
    assert failed.status == SessionStatus.FAILED


# ---------------------------------------------------------------------------
# 9. recover_interrupted_sessions creates a notification per session
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recover_creates_notification(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _make_session(db_session, SessionStatus.RUNNING, "AlertBot", project_id=1)
    await _make_session(db_session, SessionStatus.QUEUED, "SecondBot", project_id=1)
    await db_session.commit()

    count = await recover_interrupted_sessions(db_session)
    await db_session.commit()

    assert count == 2
    r = await client.get("/api/notifications?project_id=1")
    assert r.status_code == 200
    titles = [n["title"] for n in r.json()]
    interrupted = [t for t in titles if "interrupted" in t.lower()]
    assert len(interrupted) == 2


# ---------------------------------------------------------------------------
# 10. Multiple concurrent approvals all stored independently
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_approvals_all_stored(
    db_session: AsyncSession,
) -> None:
    ids = [_req_id() for _ in range(5)]
    for rid in ids:
        await create_approval(
            db_session,
            request_id=rid,
            tool_name="linear_create_issue",
            platform="Linear",
            action="Create issue",
            description="Test",
            parameters={"title": rid},
            source=ToolApprovalSource.ORCHESTRATOR,
        )
    await db_session.commit()

    for rid in ids:
        row = await get_approval(db_session, rid)
        assert row is not None
        assert row.status == ToolApprovalStatus.PENDING
        assert row.request_id == rid


# ---------------------------------------------------------------------------
# 11. resolve_approval_db updates status and resolved_at
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolve_approval_db_approved(
    db_session: AsyncSession,
) -> None:
    row = await _make_approval(db_session, minutes_ago=1)
    await db_session.commit()

    result = await resolve_approval_db(db_session, row.request_id, approved=True)
    await db_session.commit()

    assert result is not None
    assert result.status == ToolApprovalStatus.APPROVED
    assert result.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_approval_db_rejected(
    db_session: AsyncSession,
) -> None:
    row = await _make_approval(db_session, minutes_ago=1)
    await db_session.commit()

    result = await resolve_approval_db(db_session, row.request_id, approved=False)

    assert result is not None
    assert result.status == ToolApprovalStatus.REJECTED


@pytest.mark.asyncio
async def test_resolve_approval_db_idempotent_on_already_resolved(
    db_session: AsyncSession,
) -> None:
    row = await _make_approval(db_session, status=ToolApprovalStatus.APPROVED)
    await db_session.commit()

    result = await resolve_approval_db(db_session, row.request_id, approved=False)

    # Already resolved — should not change
    assert result is None
    refreshed = await get_approval(db_session, row.request_id)
    assert refreshed is not None
    assert refreshed.status == ToolApprovalStatus.APPROVED


# ---------------------------------------------------------------------------
# 12. POST /chat/approve returns 409 for an expired approval
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approve_endpoint_expired_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    row = await _make_approval(
        db_session,
        minutes_ago=60,
        expiry_minutes=30,
        status=ToolApprovalStatus.EXPIRED,
    )
    await db_session.commit()

    r = await client.post(f"/api/chat/approve/{row.request_id}")
    assert r.status_code == 409
    assert "expired" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 13. POST /chat/approve returns 409 for an already-approved request
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approve_endpoint_already_approved_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    row = await _make_approval(
        db_session,
        status=ToolApprovalStatus.APPROVED,
    )
    await db_session.commit()

    r = await client.post(f"/api/chat/approve/{row.request_id}")
    assert r.status_code == 409
    assert "approved" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 14. POST /chat/approve returns 404 for completely unknown request_id
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_approve_endpoint_unknown_request_id_returns_404(
    client: AsyncClient,
) -> None:
    r = await client.post(f"/api/chat/approve/{_req_id()}")
    assert r.status_code == 404
