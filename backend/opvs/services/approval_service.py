"""
Durable approval state and restart recovery.

Approval persistence:
  Every tool approval request is written to the DB before the agentic loop
  awaits user input. This means after a restart the row is visible and can be
  expired deterministically instead of silently forgotten.

Expiry window:
  APPROVAL_EXPIRY_MINUTES defines how long a PENDING approval stays valid.
  Anything older than this is auto-resolved to EXPIRED on startup.

Session recovery:
  Sessions left in QUEUED / RUNNING / WAITING after a restart had their
  asyncio.Task killed. recover_interrupted_sessions() marks them FAILED,
  posts a chatroom system message, and creates a notification.
"""
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.agent_message import AgentMessage, SenderType
from opvs.models.agent_session import AgentSession, SessionStatus
from opvs.models.tool_approval import ToolApproval, ToolApprovalSource, ToolApprovalStatus

logger = logging.getLogger(__name__)

# Approvals older than this without resolution are auto-expired on restart.
APPROVAL_EXPIRY_MINUTES = 30


async def create_approval(
    db: AsyncSession,
    *,
    request_id: str,
    tool_name: str,
    platform: str,
    action: str,
    description: str,
    parameters: dict[str, Any],
    source: ToolApprovalSource,
    session_uuid: str | None = None,
    project_id: int | None = None,
) -> ToolApproval:
    """Persist an approval request before the loop awaits user input."""
    expires_at = datetime.now(UTC) + timedelta(minutes=APPROVAL_EXPIRY_MINUTES)
    row = ToolApproval(
        request_id=request_id,
        tool_name=tool_name,
        platform=platform,
        action=action,
        description=description,
        parameters=json.dumps(parameters),
        status=ToolApprovalStatus.PENDING,
        source=source,
        session_uuid=session_uuid,
        project_id=project_id,
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()
    return row


async def resolve_approval_db(
    db: AsyncSession,
    request_id: str,
    *,
    approved: bool,
) -> ToolApproval | None:
    """
    Update a PENDING approval row to APPROVED or REJECTED.
    Returns None if the row does not exist or is already resolved/expired.
    """
    result = await db.execute(
        select(ToolApproval).where(ToolApproval.request_id == request_id)
    )
    row = result.scalar_one_or_none()
    if row is None or row.status != ToolApprovalStatus.PENDING:
        return None
    row.status = ToolApprovalStatus.APPROVED if approved else ToolApprovalStatus.REJECTED
    row.resolved_at = datetime.now(UTC)
    await db.flush()
    return row


async def get_approval(db: AsyncSession, request_id: str) -> ToolApproval | None:
    result = await db.execute(
        select(ToolApproval).where(ToolApproval.request_id == request_id)
    )
    return result.scalar_one_or_none()


async def expire_stale_approvals(db: AsyncSession) -> int:
    """
    Mark all PENDING rows whose expires_at has passed as EXPIRED.
    Called once on daemon startup before accepting new requests.
    Returns the number of rows expired.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(ToolApproval).where(
            ToolApproval.status == ToolApprovalStatus.PENDING,
            ToolApproval.expires_at < now,
        )
    )
    stale = list(result.scalars().all())
    for row in stale:
        row.status = ToolApprovalStatus.EXPIRED
        row.resolved_at = now
    if stale:
        await db.flush()
    logger.info("Expired %d stale tool approval(s) on startup", len(stale))
    return len(stale)


async def recover_interrupted_sessions(db: AsyncSession) -> int:
    """
    Mark sessions that were QUEUED / RUNNING / WAITING as FAILED.
    Their asyncio.Tasks were killed by the restart and cannot be resumed.

    For each session:
    - Sets status=FAILED, error_message, completed_at
    - Posts a SYSTEM message to the project chatroom
    - Creates a system notification

    Returns the count of sessions recovered.
    """
    from opvs.models.notification import NotificationSourceType
    from opvs.schemas.notification import NotificationCreate
    from opvs.services.notification_service import create_notification

    result = await db.execute(
        select(AgentSession).where(
            AgentSession.status.in_([
                SessionStatus.QUEUED,
                SessionStatus.RUNNING,
                SessionStatus.WAITING,
            ])
        )
    )
    interrupted = list(result.scalars().all())
    now = datetime.now(UTC)

    for session in interrupted:
        session.status = SessionStatus.FAILED
        session.completed_at = now
        session.error_message = "Process restarted: session was interrupted and cannot be resumed"

        chatroom_msg = AgentMessage(
            project_id=session.project_id,
            session_uuid=session.session_uuid,
            sender_type=SenderType.SYSTEM,
            sender_name="System",
            content=(
                f"Session interrupted: {session.persona_name} was active when "
                "the process restarted. The session has been marked as failed."
            ),
        )
        db.add(chatroom_msg)

    if interrupted:
        await db.flush()
        for session in interrupted:
            await create_notification(
                db,
                NotificationCreate(
                    title=f"Session interrupted: {session.persona_name}",
                    body=(
                        f"The agent session for task \"{session.task[:120]}\" "
                        "was interrupted by a process restart. "
                        "Spawn a new session to retry."
                    ),
                    source_type=NotificationSourceType.SYSTEM,
                    project_id=session.project_id,
                    priority=3,
                ),
            )

    logger.info("Recovered %d interrupted session(s) on startup", len(interrupted))
    return len(interrupted)
