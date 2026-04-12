import logging

import anthropic
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.config import settings
from opvs.models.settings import Setting
from opvs.schemas.settings import ConnectionTestResult, SettingUpdate

logger = logging.getLogger(__name__)


async def get_all_settings(db: AsyncSession) -> list[Setting]:
    result = await db.execute(select(Setting))
    return list(result.scalars().all())


async def get_setting(db: AsyncSession, key: str) -> Setting | None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    return result.scalar_one_or_none()


async def upsert_setting(db: AsyncSession, key: str, data: SettingUpdate) -> Setting:
    existing = await get_setting(db, key)
    if existing is not None:
        existing.value = data.value
        existing.is_secret = data.is_secret
        await db.flush()
        await db.refresh(existing)
        return existing
    new_setting = Setting(key=key, value=data.value, is_secret=data.is_secret)
    db.add(new_setting)
    await db.flush()
    await db.refresh(new_setting)
    return new_setting


async def delete_setting(db: AsyncSession, key: str) -> bool:
    existing = await get_setting(db, key)
    if existing is None:
        return False
    await db.delete(existing)
    await db.flush()
    return True


async def _get_setting_value(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        return ""
    # strip() guards against whitespace introduced by copy-paste
    return str(setting.value).strip()


async def test_connection(service: str, db: AsyncSession) -> ConnectionTestResult:
    logger.info("test_connection: service=%s", service)
    try:
        if service == "anthropic":
            api_key = await _get_setting_value(db, "anthropic_api_key")
            if not api_key:
                return ConnectionTestResult(
                    ok=False,
                    error="No API key saved. Enter and save your key first.",
                )
            logger.info("anthropic: key length=%d, calling API", len(api_key))
            client = anthropic.AsyncAnthropic(api_key=api_key)
            await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            logger.info("anthropic: connection OK")
            return ConnectionTestResult(ok=True)
        elif service == "linear":
            api_key = await _get_setting_value(db, "linear_api_key")
            if not api_key:
                return ConnectionTestResult(
                    ok=False,
                    error="No API key saved. Enter and save your key first.",
                )
            logger.info("linear: key length=%d, calling API", len(api_key))
            async with httpx.AsyncClient() as http:
                response = await http.post(
                    "https://api.linear.app/graphql",
                    json={"query": "{ viewer { id } }"},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                logger.info("linear: response status=%d", response.status_code)
                if response.status_code == 200:
                    body = response.json()
                    if body.get("data", {}).get("viewer", {}).get("id"):
                        logger.info("linear: connection OK")
                        return ConnectionTestResult(ok=True)
                    errors = body.get("errors")
                    error_msg = errors[0].get("message") if errors else "Unexpected response from Linear"
                    logger.warning("linear: API error: %s", error_msg)
                    return ConnectionTestResult(ok=False, error=str(error_msg))
                if response.status_code == 401:
                    return ConnectionTestResult(
                        ok=False, error="Authentication failed — check your API key"
                    )
                logger.warning("linear: unexpected status=%d body=%s", response.status_code, response.text[:200])
                return ConnectionTestResult(
                    ok=False, error=f"HTTP {response.status_code}"
                )
        elif service == "ollama":
            host = await _get_setting_value(db, "ollama_host") or settings.ollama_host
            logger.info("ollama: host=%s, calling API", host)
            async with httpx.AsyncClient(timeout=5.0) as http:
                response = await http.get(f"{host}/api/tags")
                if response.status_code == 200:
                    logger.info("ollama: connection OK")
                    return ConnectionTestResult(ok=True)
                logger.warning("ollama: unexpected status=%d", response.status_code)
                return ConnectionTestResult(
                    ok=False, error=f"HTTP {response.status_code}"
                )
        else:
            return ConnectionTestResult(ok=False, error="Unknown service")
    except anthropic.APIError as e:
        logger.error("anthropic: API error: %s", e)
        return ConnectionTestResult(ok=False, error=str(e))
    except Exception as e:
        logger.error("test_connection(%s) unexpected error: %s", service, e, exc_info=True)
        return ConnectionTestResult(ok=False, error=str(e))
