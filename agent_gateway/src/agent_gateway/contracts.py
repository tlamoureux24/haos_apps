"""Strict version-one HTTP contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ENTITY_ID = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class IdentityCreateRequest(StrictContract):
    display_name: str = Field(min_length=1, max_length=120)
    identity_type: Literal["client", "event_source", "scheduler"]
    actions: list[str] = Field(default_factory=list, max_length=32)


class IdentityRevokeRequest(StrictContract):
    identity_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class JobCancelRequest(StrictContract):
    job_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class EventSubject(StrictContract):
    entity_id: str = Field(min_length=3, max_length=255)

    @field_validator("entity_id")
    @classmethod
    def valid_entity_id(cls, value: str) -> str:
        if not ENTITY_ID.fullmatch(value):
            raise ValueError("Invalid Home Assistant entity ID")
        return value


class EventCreateRequest(StrictContract):
    schema_version: Literal[1]
    event_type: Literal["gatus.endpoint_unavailable"]
    occurred_at: datetime
    source: Literal["home_assistant"]
    subject: EventSubject
    attributes: dict[str, Any] = Field(default_factory=dict)
    requested_task: Literal["gatus_readonly_diagnostic"]

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("attributes")
    @classmethod
    def bounded_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 32:
            raise ValueError("Too many event attributes")
        if any(len(str(key)) > 80 for key in value):
            raise ValueError("Event attribute key is too long")
        return value
