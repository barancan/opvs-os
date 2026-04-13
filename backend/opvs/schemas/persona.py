from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class PersonaCreate(BaseModel):
    name: str
    description: str | None = None
    model: str = "claude-sonnet-4-6"
    instructions: str = ""
    enabled_skills: list[str] = ["workspace"]
    temperature: float = 0.7
    max_tokens: int = 4096

    @field_validator("temperature")
    @classmethod
    def validate_temp(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Temperature must be between 0.0 and 1.0")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_tokens(cls, v: int) -> int:
        if not 256 <= v <= 32768:
            raise ValueError("max_tokens must be between 256 and 32768")
        return v


class PersonaUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    model: str | None = None
    instructions: str | None = None
    enabled_skills: list[str] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None


class PersonaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    model: str
    instructions: str
    enabled_skills: list[str]   # parsed from comma-separated string
    temperature: float
    max_tokens: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_skills(cls, persona: object) -> "PersonaResponse":
        p = persona
        data = {
            "id": p.id,  # type: ignore[attr-defined]
            "name": p.name,  # type: ignore[attr-defined]
            "description": p.description,  # type: ignore[attr-defined]
            "model": p.model,  # type: ignore[attr-defined]
            "instructions": p.instructions,  # type: ignore[attr-defined]
            "enabled_skills": [
                s.strip() for s in p.enabled_skills.split(",")  # type: ignore[attr-defined]
                if s.strip()
            ],
            "temperature": p.temperature,  # type: ignore[attr-defined]
            "max_tokens": p.max_tokens,  # type: ignore[attr-defined]
            "is_active": p.is_active,  # type: ignore[attr-defined]
            "created_at": p.created_at,  # type: ignore[attr-defined]
            "updated_at": p.updated_at,  # type: ignore[attr-defined]
        }
        return cls(**data)
