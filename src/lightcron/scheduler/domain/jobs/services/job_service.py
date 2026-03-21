"""Job management domain service."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from lightcron.scheduler.domain.jobs.entities import Job, JobStatus
from lightcron.scheduler.ports.job_repository import JobRepository
from lightcron.shared.ports.determinism.ports import TimePort, UUIDPort


class JobService:
    def __init__(
        self,
        jobs: JobRepository,
        clock: TimePort,
        ids: UUIDPort,
    ) -> None:
        self._jobs = jobs
        self._clock = clock
        self._ids = ids

    async def schedule_job(
        self,
        command: str,
        start_time: datetime,
        depends_on: list[UUID],
        max_runtime: int | None,
        max_memory: int | None,
    ) -> Job:
        """Validate and persist a new job.

        Raises ValueError with a descriptive message on any validation failure.
        """
        now = self._clock.now()

        if not command.strip():
            raise ValueError("command must not be empty")

        # Normalise to UTC for comparison
        if start_time.tzinfo is None:
            raise ValueError("start_time must be timezone-aware")
        if start_time <= now:
            raise ValueError("start_time must be in the future")

        if max_runtime is not None and max_runtime <= 0:
            raise ValueError("max_runtime must be a positive integer")

        if max_memory is not None and max_memory <= 0:
            raise ValueError("max_memory must be a positive integer")

        if depends_on and not await self._jobs.exists_all(depends_on):
            raise ValueError("depends_on contains unknown job_id(s)")

        job = Job(
            job_id=self._ids.generate(),
            command=command,
            start_time=start_time,
            depends_on=depends_on,
            max_runtime=max_runtime,
            max_memory=max_memory,
            status=JobStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        return await self._jobs.save(job)

    async def get_job(self, job_id: UUID) -> Job | None:
        return await self._jobs.get(job_id)

    async def list_jobs(self, status: JobStatus | None = None) -> list[Job]:
        if status is not None:
            return await self._jobs.list_by_status(status)
        # Return all jobs — list_by_status with None not supported; query all statuses
        results: list[Job] = []
        for s in JobStatus:
            results.extend(await self._jobs.list_by_status(s))
        return results

    async def cancel_job(self, job_id: UUID) -> Job | None:
        """Cancel a job. Returns the updated job, or None if not found.

        Raises ValueError with code 'terminal' if the job is in a terminal state.
        """
        job = await self._jobs.get(job_id)
        if job is None:
            return None
        if job.status.is_terminal():
            raise ValueError("terminal")

        updated = await self._jobs.update_status(job_id, JobStatus.CANCELLED)
        if not updated:
            # Race: another writer beat us to a terminal state
            raise ValueError("terminal")

        job.status = JobStatus.CANCELLED
        return job
