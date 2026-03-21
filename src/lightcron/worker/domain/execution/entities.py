"""Worker agent domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class JobExecution:
    """Represents a job that this worker agent has claimed."""

    job_id: UUID
    command: str
    worker_id: UUID
    max_runtime: int | None  # seconds; None = unlimited
    max_memory: int | None   # MB; None = unlimited
    pid: int | None = None   # Set after process is started
