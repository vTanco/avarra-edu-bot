from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BodyCode = Literal["0590", "0598"]


class ListEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: BodyCode
    specialty: str
    list_type: str | None = None

    @field_validator("specialty")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("specialty must not be empty")
        return v


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_localities: list[str] = Field(default_factory=list)
    specialty_preference_order: list[str] = Field(default_factory=list)


class PortalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    login_path: str


class SchedulerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_start: str
    daily_end: str
    poll_interval_seconds: int = Field(ge=5, le=60)


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    log_level: str = "INFO"
    storage_path: str
    log_path: str


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portal: PortalSettings
    user: UserSettings
    available_lists: list[ListEntry]
    thursday_open_specialties: list[ListEntry]
    scheduler: SchedulerSettings
    runtime: RuntimeSettings
