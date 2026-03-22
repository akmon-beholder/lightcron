"""Job domain entity and status enum."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class JobStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"

    def is_terminal(self) -> bool:
        return self in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.LOST,
        )


@dataclass
class Job:
    job_id: UUID
    command: str
    start_time: datetime
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    depends_on: list[UUID] = field(default_factory=list)
    max_runtime: int | None = None   # seconds
    max_memory: int | None = None    # MB
    env_vars: dict[str, str] = field(default_factory=dict)
    peak_memory_mb: float | None = None
    worker_id: UUID | None = None
    exit_code: int | None = None
    kill_reason: str | None = None
    claimed_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
