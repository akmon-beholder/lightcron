"""asyncpg implementation of WorkerStatusDB for the worker agent."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine


class AsyncpgWorkerStatusDB:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def upsert_worker(self, hostname: str, base_url: str | None = None) -> UUID:
        """Upsert by hostname; preserve existing worker_id on conflict."""
        async with self._engine.connect() as conn, conn.begin():
            row = await conn.execute(
                sa.text("""
                        INSERT INTO worker_status (hostname, status, last_seen, registered_at, base_url)
                        VALUES (:hostname, 'online', now(), now(), :base_url)
                        ON CONFLICT (hostname) DO UPDATE
                            SET status = 'online', last_seen = now(), base_url = :base_url
                        RETURNING worker_id
                    """),
                {"hostname": hostname, "base_url": base_url},
            )
            return UUID(str(row.scalar_one()))

    async def update_last_seen(self, worker_id: UUID) -> None:
        async with self._engine.connect() as conn, conn.begin():
            await conn.execute(
                sa.text(
                    "UPDATE worker_status SET last_seen = now() "
                    "WHERE worker_id = :id"
                ),
                {"id": str(worker_id)},
            )
