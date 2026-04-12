import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.notification import NotificationSourceType
from opvs.models.settings import Setting
from opvs.schemas.killswitch import KillSwitchStatus
from opvs.schemas.notification import NotificationCreate
from opvs.websocket import WS_KILL_SWITCH_ACTIVATED, WS_KILL_SWITCH_RECOVERED, manager

logger = logging.getLogger(__name__)

_KEY_ACTIVE = "kill_switch_active"
_KEY_ACTIVATED_AT = "kill_switch_activated_at"


async def _get_setting_value(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        return ""
    return str(setting.value).strip()


async def _upsert_setting(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.value = value
    else:
        db.add(Setting(key=key, value=value, is_secret=False))
    await db.flush()


async def get_status(db: AsyncSession) -> KillSwitchStatus:
    active_val = await _get_setting_value(db, _KEY_ACTIVE)
    activated_at_val = await _get_setting_value(db, _KEY_ACTIVATED_AT)
    active = active_val == "true"
    activated_at = activated_at_val if activated_at_val else None
    return KillSwitchStatus(active=active, activated_at=activated_at)


async def activate(db: AsyncSession) -> KillSwitchStatus:
    from opvs.services import notification_service

    now = datetime.utcnow().isoformat()
    await _upsert_setting(db, _KEY_ACTIVE, "true")
    await _upsert_setting(db, _KEY_ACTIVATED_AT, now)
    await manager.broadcast(WS_KILL_SWITCH_ACTIVATED, {"activated_at": now})
    await notification_service.create_notification(
        db,
        NotificationCreate(
            title="Kill switch activated",
            body="All agent operations have been halted.",
            source_type=NotificationSourceType.SYSTEM,
        ),
    )
    return KillSwitchStatus(active=True, activated_at=now)


async def recover(db: AsyncSession, reason: str) -> KillSwitchStatus:
    from opvs.services import notification_service

    await _upsert_setting(db, _KEY_ACTIVE, "false")
    workspace_path_val = await _get_setting_value(db, "workspace_path")
    workspace_path = Path(workspace_path_val) if workspace_path_val else Path("./workspace")
    memory_dir = workspace_path / "_memory" / "inbox"
    memory_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow()
    filename = f"killswitch_recovery_{timestamp.strftime('%Y%m%d_%H%M%S')}.md"
    recovery_file = memory_dir / filename
    content = f"""# Kill Switch Recovery

**Timestamp:** {timestamp.isoformat()}

**Reason provided by user:**

{reason}

---

*Please review agent state and any interrupted operations before resuming normal work.*
"""
    recovery_file.write_text(content, encoding="utf-8")
    logger.info("Kill switch recovery written to %s", recovery_file)
    await manager.broadcast(WS_KILL_SWITCH_RECOVERED, {"reason": reason[:100]})
    await notification_service.create_notification(
        db,
        NotificationCreate(
            title="Kill switch recovered",
            body=f"System resumed. Reason: {reason[:100]}",
            source_type=NotificationSourceType.SYSTEM,
        ),
    )
    return KillSwitchStatus(active=False, activated_at=None)
