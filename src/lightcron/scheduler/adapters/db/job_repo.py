"""PostgreSQL implementation of JobRepository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from lightcron.scheduler.domain.jobs.entities import Job, JobStatus
from lightcron.scheduler.ports.job_repository import JobRepository

_TERMINAL_STATUSES = ("completed", "failed", "cancelled", "lost")

_SELECT_COLS = """
    job_id, command, start_time, depends_on, max_runtime, max_memory,
    status, worker_id, exit_code, kill_reason,
    claimed_at, started_at, finished_at, created_at, updated_at
"""


def _row_to_job(row: sa.engine.Row) -> Job:  # type: ignore[type-arg]
    return Job(
        job_id=row.job_id,
        command=row.command,
        start_time=row.start_time,
        depends_on=list(row.depends_on) if row.depends_on else [],
        max_runtime=row.max_runtime,
        max_memory=row.max_memory,
        status=JobStatus(row.status),
        worker_id=row.worker_id,
        exit_code=row.exit_code,
        kill_reason=row.kill_reason,
        claimed_at=row.claimed_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresJobRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, job_id: UUID) -> Job | None:
        async with self._engine.connect() as conn:
            row = await conn.execute(
                sa.text(f"SELECT {_SELECT_COLS} FROM jobs WHERE job_id = :id"),
                {"id": str(job_id)},
            )
            result = row.fetchone()
        return _row_to_job(result) if result else None

    async def save(self, job: Job) -> Job:
        async with self._engine.connect() as conn:
            async with conn.begin():
                row = await conn.execute(
                    sa.text("""
                        INSERT INTO jobs (
                            job_id, command, start_time, depends_on,
                            max_runtime, max_memory, status,
                            created_at, updated_at
                        ) VALUES (
                            :job_id, :command, :start_time, :depends_on,
                            :max_runtime, :max_memory, :status,
                            :created_at, :updated_at
                        )
                        RETURNING """ + _SELECT_COLS),
                    {
                        "job_id": str(job.job_id),
                        "command": job.command,
                        "start_time": job.start_time,
                        "depends_on": [str(d) for d in job.depends_on],
                        "max_runtime": job.max_runtime,
                        "max_memory": job.max_memory,
                        "status": job.status.value,
                        "created_at": job.created_at,
                        "updated_at": job.updated_at,
                    },
                )
                result = row.fetchone()
        assert result is not None
        return _row_to_job(result)

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
        # Build dynamic SET clause for optional fields
        set_parts = ["status = :status"]
        params: dict[str, object] = {
            "job_id": str(job_id),
            "status": status.value,
        }
        if worker_id is not None:
            set_parts.append("worker_id = :worker_id")
            params["worker_id"] = str(worker_id)
        if exit_code is not None:
            set_parts.append("exit_code = :exit_code")
            params["exit_code"] = exit_code
        if kill_reason is not None:
            set_parts.append("kill_reason = :kill_reason")
            params["kill_reason"] = kill_reason
        if claimed_at is not None:
            set_parts.append("claimed_at = :claimed_at")
            params["claimed_at"] = claimed_at
        if started_at is not None:
            set_parts.append("started_at = :started_at")
            params["started_at"] = started_at
        if finished_at is not None:
            set_parts.append("finished_at = :finished_at")
            params["finished_at"] = finished_at

        terminal_list = ", ".join(f"'{s}'" for s in _TERMINAL_STATUSES)
        query = sa.text(
            f"UPDATE jobs SET {', '.join(set_parts)} "
            f"WHERE job_id = :job_id "
            f"AND status NOT IN ({terminal_list})"
        )
        async with self._engine.connect() as conn:
            async with conn.begin():
                result = await conn.execute(query, params)
        return result.rowcount > 0

    async def list_by_status(self, status: JobStatus) -> list[Job]:
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sa.text(f"SELECT {_SELECT_COLS} FROM jobs WHERE status = :status"),
                {"status": status.value},
            )
        return [_row_to_job(r) for r in rows.fetchall()]

    async def list_by_worker(self, worker_id: UUID) -> list[Job]:
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sa.text(
                    f"SELECT {_SELECT_COLS} FROM jobs WHERE worker_id = :worker_id"
                ),
                {"worker_id": str(worker_id)},
            )
        return [_row_to_job(r) for r in rows.fetchall()]

    async def exists_all(self, job_ids: list[UUID]) -> bool:
        if not job_ids:
            return True
        id_strs = [str(j) for j in job_ids]
        async with self._engine.connect() as conn:
            row = await conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM jobs WHERE job_id = ANY(:ids)"
                ),
                {"ids": id_strs},
            )
            count = row.scalar_one()
        return int(count) == len(job_ids)
