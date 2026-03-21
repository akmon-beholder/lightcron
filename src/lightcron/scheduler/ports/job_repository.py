"""JobRepository port protocol."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from lightcron.scheduler.domain.jobs.entities import Job, JobStatus


class JobRepository(Protocol):
    async def get(self, job_id: UUID) -> Job | None: ...

    async def save(self, job: Job) -> Job: ...

    async def update_status(
        self,
        job_id: UUID,
        status: JobStatus,
        *,
        worker_id: UUID | None = None,
        exit_code: int | None = None,
        kill_reason: str | None = None,
        claimed_at: object = None,
        started_at: object = None,
        finished_at: object = None,
    ) -> bool:
        """Update job status with optional field updates.

        Applies the terminal-state guard:
        WHERE status NOT IN ('completed', 'failed', 'cancelled', 'lost').

        Returns True if the row was updated, False if the guard blocked it.
        """
        ...

    async def list_by_status(self, status: JobStatus) -> list[Job]: ...

    async def list_by_worker(self, worker_id: UUID) -> list[Job]: ...

    async def exists_all(self, job_ids: list[UUID]) -> bool:
        """Return True if every job_id in the list exists in the jobs table."""
        ...
