from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import get_db
from opvs.schemas.settings import ConnectionTestResult, SettingResponse, SettingUpdate
from opvs.services import settings_service

router = APIRouter(prefix="/api/settings")


@router.get("/", response_model=list[SettingResponse])
async def list_settings(db: AsyncSession = Depends(get_db)) -> list[SettingResponse]:
    items = await settings_service.get_all_settings(db)
    return [SettingResponse.model_validate(item) for item in items]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)) -> SettingResponse:
    item = await settings_service.get_setting(db, key)
    if item is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return SettingResponse.model_validate(item)


@router.put("/{key}", response_model=SettingResponse)
async def upsert_setting(
    key: str, data: SettingUpdate, db: AsyncSession = Depends(get_db)
) -> SettingResponse:
    item = await settings_service.upsert_setting(db, key, data)
    return SettingResponse.model_validate(item)


@router.delete("/{key}")
async def delete_setting(
    key: str, db: AsyncSession = Depends(get_db)
) -> dict[str, bool]:
    deleted = await settings_service.delete_setting(db, key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"deleted": True}


@router.post("/test/{service}", response_model=ConnectionTestResult)
async def test_service_connection(
    service: str,
    db: AsyncSession = Depends(get_db),
) -> ConnectionTestResult:
    return await settings_service.test_connection(service, db)
