import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.notification import Notification, NotificationStatus
from opvs.schemas.notification import NotificationCreate
from opvs.websocket import WS_NOTIFICATION_CREATED, WS_NOTIFICATION_UPDATED, manager

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    data: NotificationCreate,
) -> Notification:
    notification = Notification(
        title=data.title,
        body=data.body,
        source_type=data.source_type,
        agent_id=data.agent_id,
        session_id=data.session_id,
        job_id=data.job_id,
        priority=data.priority,
        status=NotificationStatus.PENDING,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    await manager.broadcast(
        WS_NOTIFICATION_CREATED,
        {
            "id": notification.id,
            "title": notification.title,
            "status": notification.status.value,
            "source_type": notification.source_type.value,
        },
    )
    return notification


async def list_notifications(
    db: AsyncSession,
    status: NotificationStatus | None = None,
    limit: int = 50,
) -> list[Notification]:
    query = select(Notification)
    if status is not None:
        query = query.where(Notification.status == status)
    query = query.order_by(
        Notification.orchestrator_prioritised.desc(),
        Notification.priority.desc(),
        Notification.created_at.desc(),
    ).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_notification(db: AsyncSession, notification_id: int) -> Notification | None:
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    return result.scalar_one_or_none()


async def update_notification_status(
    db: AsyncSession,
    notification_id: int,
    status: NotificationStatus,
) -> Notification | None:
    from datetime import datetime

    notification = await get_notification(db, notification_id)
    if notification is None:
        return None
    notification.status = status
    if status == NotificationStatus.COMPLETED:
        notification.completed_at = datetime.utcnow()
    await db.flush()
    await db.refresh(notification)
    await manager.broadcast(
        WS_NOTIFICATION_UPDATED,
        {
            "id": notification.id,
            "status": notification.status.value,
        },
    )
    return notification


async def delete_notification(db: AsyncSession, notification_id: int) -> bool:
    notification = await get_notification(db, notification_id)
    if notification is None:
        return False
    await db.delete(notification)
    await db.flush()
    return True
