"""Pydantic request/response models for the scheduler REST API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Requests ──────────────────────────────────────────────────────────────────

class ScheduleJobRequest(BaseModel):
    command: str = Field(..., min_length=1)
    start_time: datetime
    depends_on: list[UUID] = Field(default_factory=list)
    max_runtime: int | None = Field(default=None, gt=0)
    max_memory: int | None = Field(default=None, gt=0)

    @field_validator("start_time")
    @classmethod
    def start_time_must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start_time must be timezone-aware (include UTC offset or Z)")
        return v


# ── Responses ─────────────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    command: str
    start_time: datetime
    depends_on: list[UUID]
    max_runtime: int | None
    max_memory: int | None
    status: str
    worker_id: UUID | None
    exit_code: int | None
    kill_reason: str | None
    claimed_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CancelJobResponse(BaseModel):
    job_id: UUID
    status: str


class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_id: UUID
    hostname: str
    status: str
    last_seen: datetime
    registered_at: datetime
    running_job_count: int


class HealthResponse(BaseModel):
    status: str = "ok"
