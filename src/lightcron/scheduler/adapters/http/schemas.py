"""Pydantic request/response models for the scheduler REST API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ── Requests ──────────────────────────────────────────────────────────────────

class ScheduleJobRequest(BaseModel):
    command: str = Field(..., min_length=1)
    start_time: datetime
    depends_on: list[UUID] = Field(default_factory=list)
    max_runtime: int | None = Field(default=None, gt=0)
    max_memory: int | None = Field(default=None, gt=0)
    env_vars: dict[str, str] = Field(default_factory=dict)

    @field_validator("start_time")
    @classmethod
    def start_time_must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("start_time must be timezone-aware (include UTC offset or Z)")
        return v

    @model_validator(mode="after")
    def validate_env_vars(self) -> "ScheduleJobRequest":
        ev = self.env_vars
        if len(ev) > 100:
            raise ValueError("env_vars must not contain more than 100 keys")
        for k, v in ev.items():
            if not isinstance(k, str):
                raise ValueError(f"env_vars key {k!r} must be a string")
            if not isinstance(v, str):
                raise ValueError(f"env_vars value for key {k!r} must be a string")
            if len(k) > 256:
                raise ValueError(f"env_vars key {k!r} exceeds 256 characters")
            if len(v) > 4096:
                raise ValueError(f"env_vars value for key {k!r} exceeds 4096 characters")
        return self


# ── Responses ─────────────────────────────────────────────────────────────────

class JobSummaryResponse(BaseModel):
    """Used by POST /jobs (201) and GET /jobs (list items).

    Includes env_vars; does NOT include peak_memory_mb.
    """

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    command: str
    start_time: datetime
    depends_on: list[UUID]
    max_runtime: int | None
    max_memory: int | None
    env_vars: dict[str, str]
    status: str
    worker_id: UUID | None
    exit_code: int | None
    kill_reason: str | None
    claimed_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobDetailResponse(JobSummaryResponse):
    """Used by GET /jobs/{job_id} only.

    All JobSummaryResponse fields plus peak_memory_mb.
    """

    peak_memory_mb: float | None


# Backward-compat alias used by existing routers until they are updated.
JobResponse = JobSummaryResponse


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
    base_url: str | None


class HealthResponse(BaseModel):
    status: str = "ok"
