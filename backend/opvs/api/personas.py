from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import get_db
from opvs.schemas.persona import PersonaCreate, PersonaResponse, PersonaUpdate
from opvs.services import persona_service

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("", response_model=list[PersonaResponse])
async def list_personas(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
) -> list[PersonaResponse]:
    personas = await persona_service.list_personas(db, active_only=active_only)
    return [PersonaResponse.from_orm_with_skills(p) for p in personas]


@router.post("", response_model=PersonaResponse, status_code=201)
async def create_persona(
    data: PersonaCreate,
    db: AsyncSession = Depends(get_db),
) -> PersonaResponse:
    persona = await persona_service.create_persona(db, data)
    return PersonaResponse.from_orm_with_skills(persona)


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
) -> PersonaResponse:
    persona = await persona_service.get_persona(db, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return PersonaResponse.from_orm_with_skills(persona)


@router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: int,
    data: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
) -> PersonaResponse:
    persona = await persona_service.update_persona(db, persona_id, data)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return PersonaResponse.from_orm_with_skills(persona)


@router.delete("/{persona_id}")
async def delete_persona(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    deleted = await persona_service.delete_persona(db, persona_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {"deleted": True}
