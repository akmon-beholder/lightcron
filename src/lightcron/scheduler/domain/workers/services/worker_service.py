"""Worker query domain service."""

from __future__ import annotations

from lightcron.scheduler.domain.workers.entities import Worker
from lightcron.scheduler.ports.worker_repository import WorkerRepository


class WorkerService:
    def __init__(self, workers: WorkerRepository) -> None:
        self._workers = workers

    async def list_workers(self) -> list[Worker]:
        return await self._workers.list_all()
