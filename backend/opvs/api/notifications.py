from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import get_db
from opvs.models.notification import NotificationStatus
from opvs.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationStatusUpdate,
)
from opvs.services import notification_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    status: NotificationStatus | None = Query(default=None),
    project_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationResponse]:
    items = await notification_service.list_notifications(
        db, status=status, project_id=project_id
    )
    return [NotificationResponse.model_validate(item) for item in items]


@router.post("", response_model=NotificationResponse)
async def create_notification(
    data: NotificationCreate,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    item = await notification_service.create_notification(db, data)
    return NotificationResponse.model_validate(item)


@router.put("/{notification_id}/status", response_model=NotificationResponse)
async def update_notification_status(
    notification_id: int,
    data: NotificationStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    item = await notification_service.update_notification_status(
        db, notification_id, data.status
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationResponse.model_validate(item)


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    deleted = await notification_service.delete_notification(db, notification_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"deleted": True}
