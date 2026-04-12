import anthropic
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.config import settings
from opvs.models.settings import Setting
from opvs.schemas.settings import ConnectionTestResult, SettingUpdate


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


async def test_connection(service: str) -> ConnectionTestResult:
    try:
        if service == "anthropic":
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return ConnectionTestResult(ok=True)
        elif service == "linear":
            async with httpx.AsyncClient() as http:
                response = await http.post(
                    "https://api.linear.app/graphql",
                    json={"query": "{ viewer { id } }"},
                    headers={"Authorization": f"Bearer {settings.linear_api_key}"},
                )
                if response.status_code == 200:
                    body = response.json()
                    if body.get("data", {}).get("viewer", {}).get("id"):
                        return ConnectionTestResult(ok=True)
                    return ConnectionTestResult(
                        ok=False, error="Unexpected response from Linear"
                    )
                return ConnectionTestResult(
                    ok=False, error=f"HTTP {response.status_code}"
                )
        elif service == "ollama":
            async with httpx.AsyncClient(timeout=5.0) as http:
                response = await http.get(f"{settings.ollama_host}/api/tags")
                if response.status_code == 200:
                    return ConnectionTestResult(ok=True)
                return ConnectionTestResult(
                    ok=False, error=f"HTTP {response.status_code}"
                )
        else:
            return ConnectionTestResult(ok=False, error="Unknown service")
    except anthropic.APIError as e:
        return ConnectionTestResult(ok=False, error=str(e))
    except Exception as e:
        return ConnectionTestResult(ok=False, error=str(e))
