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


class ConnectorCreateRequest(StrictContract):
    display_name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    bearer_token: str = Field(default="", max_length=4096)


class ConnectorIdRequest(StrictContract):
    connector_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class ConnectorEnabledRequest(ConnectorIdRequest):
    enabled: bool


class TaskToolSelection(StrictContract):
    connector_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    tool_name: str = Field(min_length=1, max_length=160)


class TaskCreateRequest(StrictContract):
    display_name: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    objective: str = Field(min_length=1, max_length=4000)
    max_attempts: int = Field(ge=1, le=10)
    tools: list[TaskToolSelection] = Field(min_length=1, max_length=100)


class TaskIdRequest(StrictContract):
    task_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class TaskEnabledRequest(TaskIdRequest):
    enabled: bool


class TaskRunRequest(TaskIdRequest):
    input: dict[str, Any] = Field(default_factory=dict, max_length=64)


class ScheduleCreateRequest(StrictContract):
    display_name: str = Field(min_length=1, max_length=120)
    task_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    interval_minutes: int = Field(ge=1, le=10080)


class ScheduleIdRequest(StrictContract):
    schedule_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class ScheduleEnabledRequest(ScheduleIdRequest):
    enabled: bool


class EventCreateRequest(StrictContract):
    schema_version: Literal[1]
    event_type: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    occurred_at: datetime
    subject: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)

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


class EventMappingCreateRequest(StrictContract):
    display_name: str = Field(min_length=1, max_length=120)
    source_identity_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    event_type: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    task_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9-]+$")
    cooldown_minutes: int = Field(default=0, ge=0, le=10080)
    grace_minutes: int = Field(default=0, ge=0, le=1440)
    recovery_event_type: str | None = Field(default=None, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    input_mode: Literal["full_event", "subject", "attributes"] = "full_event"


class EventMappingIdRequest(StrictContract):
    mapping_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


class EventMappingEnabledRequest(EventMappingIdRequest):
    enabled: bool
