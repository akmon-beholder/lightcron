"""Worker domain entity and status enum."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class WorkerStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass
class Worker:
    worker_id: UUID
    hostname: str
    status: WorkerStatus
    last_seen: datetime
    registered_at: datetime
    running_job_count: int = 0
    base_url: str | None = None
