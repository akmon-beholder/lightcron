"""PostgreSQL implementation of WorkerRepository."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from lightcron.scheduler.domain.workers.entities import Worker, WorkerStatus

_SELECT_COLS = """
    w.worker_id, w.hostname, w.status, w.last_seen, w.registered_at,
    COUNT(j.job_id) FILTER (WHERE j.status = 'running') AS running_job_count
"""

_FROM_JOIN = """
    FROM worker_status w
    LEFT JOIN jobs j ON j.worker_id = w.worker_id
"""


def _row_to_worker(row: sa.engine.Row) -> Worker:  # type: ignore[type-arg]
    return Worker(
        worker_id=row.worker_id,
        hostname=row.hostname,
        status=WorkerStatus(row.status),
        last_seen=row.last_seen,
        registered_at=row.registered_at,
        running_job_count=row.running_job_count or 0,
    )


class PostgresWorkerRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_by_hostname(self, hostname: str) -> Worker | None:
        async with self._engine.connect() as conn:
            row = await conn.execute(
                sa.text(
                    f"SELECT {_SELECT_COLS} {_FROM_JOIN} "
                    "WHERE w.hostname = :hostname "
                    "GROUP BY w.worker_id"
                ),
                {"hostname": hostname},
            )
            result = row.fetchone()
        return _row_to_worker(result) if result else None

    async def upsert(self, hostname: str) -> Worker:
        async with self._engine.connect() as conn, conn.begin():
            row = await conn.execute(
                sa.text("""
                        INSERT INTO worker_status (hostname, status, last_seen, registered_at)
                        VALUES (:hostname, 'online', now(), now())
                        ON CONFLICT (hostname) DO UPDATE
                            SET status = 'online', last_seen = now()
                        RETURNING worker_id, hostname, status, last_seen, registered_at
                    """),
                {"hostname": hostname},
            )
            result = row.fetchone()
        assert result is not None
        return Worker(
            worker_id=result.worker_id,
            hostname=result.hostname,
            status=WorkerStatus(result.status),
            last_seen=result.last_seen,
            registered_at=result.registered_at,
            running_job_count=0,
        )

    async def mark_offline(self, worker_id: UUID) -> bool:
        async with self._engine.connect() as conn, conn.begin():
            result = await conn.execute(
                sa.text(
                    "UPDATE worker_status SET status = 'offline' "
                    "WHERE worker_id = :id AND status = 'online'"
                ),
                {"id": str(worker_id)},
            )
        return result.rowcount > 0

    async def list_stale(
        self,
        probe_threshold_seconds: int,
        offline_threshold_seconds: int,
    ) -> tuple[list[Worker], list[Worker]]:
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sa.text(f"""
                    SELECT {_SELECT_COLS},
                           EXTRACT(EPOCH FROM (now() - w.last_seen)) AS age_seconds
                    {_FROM_JOIN}
                    WHERE w.status = 'online'
                      AND EXTRACT(EPOCH FROM (now() - w.last_seen)) >= :probe_threshold
                    GROUP BY w.worker_id
                """),
                {"probe_threshold": probe_threshold_seconds},
            )
            results = rows.fetchall()

        stage1: list[Worker] = []
        stage2: list[Worker] = []
        for row in results:
            worker = _row_to_worker(row)
            if row.age_seconds >= offline_threshold_seconds:
                stage2.append(worker)
            else:
                stage1.append(worker)
        return stage1, stage2

    async def list_all(self) -> list[Worker]:
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                sa.text(
                    f"SELECT {_SELECT_COLS} {_FROM_JOIN} "
                    "GROUP BY w.worker_id "
                    "ORDER BY w.registered_at"
                )
            )
        return [_row_to_worker(r) for r in rows.fetchall()]
