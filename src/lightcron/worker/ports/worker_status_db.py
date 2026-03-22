"""WorkerStatusDB port protocol for the worker agent."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class WorkerStatusDB(Protocol):
    async def upsert_worker(self, hostname: str, base_url: str | None = None) -> UUID:
        """Insert or update a worker_status row. Returns the worker_id."""
        ...

    async def update_last_seen(self, worker_id: UUID) -> None:
        """Set last_seen = now() for this worker."""
        ...
