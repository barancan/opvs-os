from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.models.persona import Persona
from opvs.schemas.persona import PersonaCreate, PersonaUpdate


def _skills_to_str(skills: list[str]) -> str:
    return ",".join(s.strip() for s in skills if s.strip())


async def create_persona(db: AsyncSession, data: PersonaCreate) -> Persona:
    persona = Persona(
        name=data.name,
        description=data.description,
        model=data.model,
        instructions=data.instructions,
        enabled_skills=_skills_to_str(data.enabled_skills),
        temperature=data.temperature,
        max_tokens=data.max_tokens,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


async def list_personas(db: AsyncSession, active_only: bool = True) -> list[Persona]:
    query = select(Persona).order_by(Persona.created_at.desc())
    if active_only:
        query = query.where(Persona.is_active == True)  # noqa: E712
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_persona(db: AsyncSession, persona_id: int) -> Persona | None:
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    return result.scalar_one_or_none()


async def update_persona(
    db: AsyncSession, persona_id: int, data: PersonaUpdate
) -> Persona | None:
    persona = await get_persona(db, persona_id)
    if persona is None:
        return None
    if data.name is not None:
        persona.name = data.name
    if data.description is not None:
        persona.description = data.description
    if data.model is not None:
        persona.model = data.model
    if data.instructions is not None:
        persona.instructions = data.instructions
    if data.enabled_skills is not None:
        persona.enabled_skills = _skills_to_str(data.enabled_skills)
    if data.temperature is not None:
        persona.temperature = data.temperature
    if data.max_tokens is not None:
        persona.max_tokens = data.max_tokens
    if data.is_active is not None:
        persona.is_active = data.is_active
    await db.commit()
    await db.refresh(persona)
    return persona


async def delete_persona(db: AsyncSession, persona_id: int) -> bool:
    persona = await get_persona(db, persona_id)
    if persona is None:
        return False
    await db.delete(persona)
    await db.commit()
    return True
