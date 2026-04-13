from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from opvs.database import Base


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Model: any Anthropic model ID or Ollama model name
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="claude-sonnet-4-6")
    # Custom system prompt / instructions for this persona
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Comma-separated skill IDs enabled for this persona e.g. "linear,workspace"
    enabled_skills: Mapped[str] = mapped_column(String(512), nullable=False, default="workspace")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
