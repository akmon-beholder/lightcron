"""JobDB port protocol for the worker agent."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from lightcron.worker.domain.execution.entities import JobExecution


class JobDB(Protocol):
    async def claim_job(self, worker_id: UUID) -> JobExecution | None:
        """Attempt to atomically claim a ready job for this worker.

        Uses SELECT FOR UPDATE SKIP LOCKED + UPDATE WHERE status='ready'.
        Returns None if no ready job is available or the claim was lost to
        another worker.

        Requires pgBouncer pool_mode=session.
        """
        ...

    async def update_status(
        self,
        job_id: UUID,
        status: str,
        *,
        exit_code: int | None = None,
        kill_reason: str | None = None,
        peak_memory_mb: float | None = None,
        started_at: object = None,
        finished_at: object = None,
    ) -> bool:
        """Update job status with terminal-state guard.

        Returns True if the update succeeded, False if blocked by guard.
        """
        ...

    async def check_status(self, job_id: UUID) -> str | None:
        """Return the current status string of the job, or None if not found."""
        ...

    async def count_active_jobs(self, worker_id: UUID) -> int:
        """Return the count of assigned+running jobs for this worker."""
        ...
