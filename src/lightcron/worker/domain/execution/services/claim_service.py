"""Worker agent claim loop — polls for ready jobs and claims them."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from lightcron.constants import CLAIM_POLL_INTERVAL_SECONDS
from lightcron.worker.domain.execution.services.execution_service import ExecutionService
from lightcron.worker.ports.job_db import JobDB

logger = logging.getLogger(__name__)


class ClaimService:
    def __init__(
        self,
        db: JobDB,
        execution_service: ExecutionService,
        worker_id: UUID,
        concurrency: int,
    ) -> None:
        self._db = db
        self._execution = execution_service
        self._worker_id = worker_id
        self._concurrency = concurrency
        self._active_tasks: set[asyncio.Task[None]] = set()

    async def run_claim_loop(self) -> None:
        """Poll for ready jobs and spawn execution tasks up to concurrency limit."""
        while True:
            try:
                await self._try_claim()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in claim loop")
            await asyncio.sleep(CLAIM_POLL_INTERVAL_SECONDS)

    async def _try_claim(self) -> None:
        # Prune completed tasks
        self._active_tasks = {t for t in self._active_tasks if not t.done()}

        if len(self._active_tasks) >= self._concurrency:
            logger.debug("At capacity (%d/%d) — skipping claim", len(self._active_tasks), self._concurrency)
            return

        active_count = await self._db.count_active_jobs(self._worker_id)
        if active_count >= self._concurrency:
            logger.debug("DB count at capacity (%d/%d) — skipping claim", active_count, self._concurrency)
            return

        job = await self._db.claim_job(self._worker_id)
        if job is None:
            return

        logger.info("Claimed job %s", job.job_id)
        task = asyncio.create_task(self._execution.run_job(job))
        self._active_tasks.add(task)
