from pydantic import BaseModel


class KillSwitchStatus(BaseModel):
    active: bool
    activated_at: str | None


class KillSwitchActivate(BaseModel):
    pass


class KillSwitchRecover(BaseModel):
    reason: str
