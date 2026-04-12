from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class SettingCreate(BaseModel):
    key: str
    value: str
    is_secret: bool = False


class SettingUpdate(BaseModel):
    value: str
    is_secret: bool = False


class SettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str
    is_secret: bool
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def mask_secret_value(self) -> "SettingResponse":
        if self.is_secret:
            if len(self.value) >= 4:
                self.value = "****" + self.value[-4:]
            else:
                self.value = "****"
        return self


class ConnectionTestResult(BaseModel):
    ok: bool
    error: str | None = None
