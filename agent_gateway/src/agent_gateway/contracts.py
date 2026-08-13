"""Strict version-one HTTP contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class EventCreateRequest(StrictContract):
    schema_version: Literal[1]
    event_type: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    occurred_at: datetime
    subject: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    requested_task: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")

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

    @field_validator("subject")
    @classmethod
    def bounded_subject(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 32:
            raise ValueError("Too many subject fields")
        if any(len(str(key)) > 80 for key in value):
            raise ValueError("Event subject key is too long")
        return value
