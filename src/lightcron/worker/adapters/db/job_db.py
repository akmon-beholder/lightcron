"""asyncpg implementation of JobDB for the worker agent."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from lightcron.constants import WORKER_DEFAULT_JOBS_DIR
from lightcron.worker.domain.execution.entities import JobExecution

_TERMINAL_STATUSES = "('completed', 'failed', 'cancelled', 'lost')"


def _get_jobs_dir() -> Path:
    return Path(os.environ.get("LIGHTCRON_JOBS_DIR", WORKER_DEFAULT_JOBS_DIR))


class AsyncpgJobDB:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim_job(self, worker_id: UUID) -> JobExecution | None:
        """Atomic claim using SELECT FOR UPDATE SKIP LOCKED.

        Requires pgBouncer pool_mode=session.
        """
        async with self._engine.connect() as conn, conn.begin():
            # Step 1: find a ready job
            row = await conn.execute(
                sa.text("""
                        SELECT job_id, command, max_runtime, max_memory, env_vars
                        FROM jobs
                        WHERE status = 'ready'
                        ORDER BY start_time ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    """)
            )
            candidate = row.fetchone()
            if candidate is None:
                return None

            # Step 2: atomically claim it
            result = await conn.execute(
                sa.text("""
                        UPDATE jobs
                        SET status = 'assigned',
                            worker_id = :worker_id,
                            claimed_at = now(),
                            updated_at = now()
                        WHERE job_id = :job_id AND status = 'ready'
                    """),
                {"worker_id": str(worker_id), "job_id": str(candidate.job_id)},
            )
            if result.rowcount == 0:
                # Another worker won the race
                return None

        env_vars: dict[str, str] = {}
        raw_env = candidate.env_vars
        if raw_env:
            if isinstance(raw_env, str):
                env_vars = json.loads(raw_env)
            else:
                env_vars = dict(raw_env)

        jobs_dir = _get_jobs_dir()
        job_id = candidate.job_id

        return JobExecution(
            job_id=job_id,
            command=candidate.command,
            worker_id=worker_id,
            max_runtime=candidate.max_runtime,
            max_memory=candidate.max_memory,
            env_vars=env_vars,
            stdout_path=jobs_dir / f"{job_id}.stdout",
            stderr_path=jobs_dir / f"{job_id}.stderr",
        )

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
        set_parts = ["status = :status"]
        params: dict[str, object] = {"job_id": str(job_id), "status": status}

        if exit_code is not None:
            set_parts.append("exit_code = :exit_code")
            params["exit_code"] = exit_code
        if kill_reason is not None:
            set_parts.append("kill_reason = :kill_reason")
            params["kill_reason"] = kill_reason
        if peak_memory_mb is not None:
            set_parts.append("peak_memory_mb = :peak_memory_mb")
            params["peak_memory_mb"] = peak_memory_mb
        if started_at is not None:
            set_parts.append("started_at = :started_at")
            params["started_at"] = started_at
        if finished_at is not None:
            set_parts.append("finished_at = :finished_at")
            params["finished_at"] = finished_at

        query = sa.text(
            f"UPDATE jobs SET {', '.join(set_parts)} "
            f"WHERE job_id = :job_id "
            f"AND status NOT IN {_TERMINAL_STATUSES}"
        )
        async with self._engine.connect() as conn, conn.begin():
            result = await conn.execute(query, params)
        return result.rowcount > 0

    async def check_status(self, job_id: UUID) -> str | None:
        async with self._engine.connect() as conn:
            row = await conn.execute(
                sa.text("SELECT status FROM jobs WHERE job_id = :id"),
                {"id": str(job_id)},
            )
            result = row.fetchone()
        return result.status if result else None

    async def count_active_jobs(self, worker_id: UUID) -> int:
        async with self._engine.connect() as conn:
            row = await conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM jobs "
                    "WHERE worker_id = :wid AND status IN ('assigned', 'running')"
                ),
                {"wid": str(worker_id)},
            )
            count = row.scalar_one()
        return int(count)
