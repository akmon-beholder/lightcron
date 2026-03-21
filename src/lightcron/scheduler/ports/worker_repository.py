"""WorkerRepository port protocol."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from lightcron.scheduler.domain.workers.entities import Worker


class WorkerRepository(Protocol):
    async def get_by_hostname(self, hostname: str) -> Worker | None: ...

    async def upsert(self, hostname: str) -> Worker:
        """Insert or update a worker_status row by hostname.

        On conflict (hostname already exists), updates status='online'
        and last_seen=now(). The existing worker_id is preserved.
        Returns the resulting Worker row.
        """
        ...

    async def mark_offline(self, worker_id: UUID) -> bool:
        """Set status='offline' for the given worker.

        Returns True if the row was updated, False if it was already offline
        or did not exist.
        """
        ...

    async def list_stale(
        self,
        probe_threshold_seconds: int,
        offline_threshold_seconds: int,
    ) -> tuple[list[Worker], list[Worker]]:
        """Return workers bucketed by last_seen age.

        Returns:
            (stage1_workers, stage2_workers) where:
            - stage1: last_seen age >= probe_threshold but < offline_threshold
              → scheduler should call GET /health
            - stage2: last_seen age >= offline_threshold
              → scheduler should mark offline directly
        """
        ...

    async def list_all(self) -> list[Worker]: ...
