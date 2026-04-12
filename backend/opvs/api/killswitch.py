from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import get_db
from opvs.schemas.killswitch import KillSwitchRecover, KillSwitchStatus
from opvs.services import killswitch_service

router = APIRouter(prefix="/api/killswitch", tags=["killswitch"])


@router.get("/status", response_model=KillSwitchStatus)
async def get_kill_switch_status(
    db: AsyncSession = Depends(get_db),
) -> KillSwitchStatus:
    return await killswitch_service.get_status(db)


@router.post("/activate", response_model=KillSwitchStatus)
async def activate_kill_switch(
    db: AsyncSession = Depends(get_db),
) -> KillSwitchStatus:
    return await killswitch_service.activate(db)


@router.post("/recover", response_model=KillSwitchStatus)
async def recover_kill_switch(
    data: KillSwitchRecover,
    db: AsyncSession = Depends(get_db),
) -> KillSwitchStatus:
    return await killswitch_service.recover(db, data.reason)
