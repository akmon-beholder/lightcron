"""Integration tests for pgBouncer session-mode requirement.

These tests verify that SELECT FOR UPDATE SKIP LOCKED works correctly when
connecting via pgBouncer in session mode, and document the failure mode when
using transaction mode.

Run against a live pgBouncer instance:
    DATABASE_URL=... PGBOUNCER_URL=... pytest tests/integration/test_pgbouncer.py

ops condition C5: pgBouncer pool_mode=session must be enforced by config.
"""

from __future__ import annotations

import asyncio
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


PGBOUNCER_URL = os.environ.get("PGBOUNCER_URL", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not PGBOUNCER_URL or not DATABASE_URL,
    reason="PGBOUNCER_URL and DATABASE_URL must be set for integration tests",
)


async def _claim_one(url: str, job_id: str) -> bool:
    """Attempt to claim a job row using SELECT FOR UPDATE SKIP LOCKED.

    Returns True if this caller won the lock, False if the row was skipped.
    """
    engine = create_async_engine(url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                row = await conn.execute(
                    sa.text(
                        "SELECT job_id FROM jobs "
                        "WHERE job_id = :id AND status = 'ready' "
                        "FOR UPDATE SKIP LOCKED"
                    ),
                    {"id": job_id},
                )
                result = row.fetchone()
                if result is None:
                    return False
                await conn.execute(
                    sa.text(
                        "UPDATE jobs SET status = 'assigned' WHERE job_id = :id"
                    ),
                    {"id": job_id},
                )
                return True
    finally:
        await engine.dispose()


@pytest.fixture()
async def ready_job(db_engine: sa.ext.asyncio.AsyncEngine) -> str:
    """Insert a single ready job and return its job_id."""
    async with db_engine.connect() as conn:
        async with conn.begin():
            row = await conn.execute(
                sa.text(
                    "INSERT INTO jobs (command, start_time, status) "
                    "VALUES ('echo test', now(), 'ready') "
                    "RETURNING job_id"
                )
            )
            job_id = str(row.scalar_one())
    yield job_id
    # Cleanup
    async with db_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                sa.text("DELETE FROM jobs WHERE job_id = :id"),
                {"id": job_id},
            )


@pytest.fixture()
async def db_engine() -> sa.ext.asyncio.AsyncEngine:
    engine = create_async_engine(DATABASE_URL, poolclass=sa.pool.NullPool)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_select_for_update_skip_locked_via_pgbouncer(ready_job: str) -> None:
    """SELECT FOR UPDATE SKIP LOCKED via pgBouncer session mode.

    Two concurrent callers attempt to claim the same ready job.
    Exactly one must succeed; the other must see 0 rows (SKIP LOCKED).
    This requires pgBouncer pool_mode=session — transaction mode breaks this.
    """
    results = await asyncio.gather(
        _claim_one(PGBOUNCER_URL, ready_job),
        _claim_one(PGBOUNCER_URL, ready_job),
    )
    winners = sum(results)
    assert winners == 1, (
        f"Expected exactly 1 winner but got {winners}. "
        "This usually means pgBouncer is in transaction mode, not session mode."
    )


@pytest.mark.asyncio
async def test_direct_connection_also_works(ready_job: str) -> None:
    """Confirm that direct DB connections also support the locking pattern.

    This is a sanity check — the atomic claim must work even without pgBouncer
    in local development or test environments.
    """
    results = await asyncio.gather(
        _claim_one(DATABASE_URL, ready_job),
        _claim_one(DATABASE_URL, ready_job),
    )
    winners = sum(results)
    assert winners == 1, f"Expected exactly 1 winner but got {winners}."
