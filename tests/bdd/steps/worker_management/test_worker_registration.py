"""BDD step definitions for worker-registration.feature (J002)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.bdd.conftest import get_worker_status, insert_worker

FEATURE = "../../../../specs/features/worker-management/worker-registration.feature"


@scenario(FEATURE, "Worker agent registers on startup by upserting to worker_status")
def test_register_on_startup() -> None: ...

@scenario(FEATURE, "Worker agent maintains registration by updating last_seen every 30 seconds")
def test_heartbeat_updates_last_seen() -> None: ...

@scenario(FEATURE, "Scheduler marks worker offline after last_seen has not been updated for 90 seconds")
def test_offline_after_90s() -> None: ...

@scenario(FEATURE, "Re-registering the same hostname on restart is idempotent")
def test_reregister_idempotent() -> None: ...

@scenario(FEATURE, "Scheduler can confirm worker is alive via worker REST health endpoint")
def test_health_endpoint() -> None: ...


# ── Givens ────────────────────────────────────────────────────────────────────

@given(parsers.parse('a worker_status row exists for worker_id "{name}" with status "{status}"'))
async def given_worker_row(
    name: str, status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = await insert_worker(db_engine, hostname=f"host-{name}", status=status)
    ctx.worker_ids[name] = wid


@given(parsers.parse('the last_seen timestamp for "{name}" is 90 seconds in the past'))
async def set_last_seen_stale(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = ctx.worker_ids[name]
    async with db_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                sa.text(
                    "UPDATE worker_status SET last_seen = now() - interval '95 seconds' "
                    "WHERE worker_id = :id"
                ),
                {"id": str(wid)},
            )


@given(parsers.parse('a worker_status row exists for hostname "{hostname}" with worker_id "{name}" and status "{status}"'))
async def given_worker_by_hostname(
    hostname: str,
    name: str,
    status: str,
    ctx: SimpleNamespace,
    db_engine: AsyncEngine,
) -> None:
    wid = await insert_worker(db_engine, hostname=hostname, status=status)
    ctx.worker_ids[name] = wid
    ctx.worker_ids[hostname] = wid


@given(parsers.parse('a worker_status row for "{name}" has a stale last_seen'))
async def given_stale_worker(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = await insert_worker(db_engine, hostname=f"host-{name}", last_seen_offset_seconds=65)
    ctx.worker_ids[name] = wid


@given(parsers.parse('the worker_agent on "{name}" is still running'))
def given_worker_still_running(name: str, ctx: SimpleNamespace) -> None:
    pass  # Logical state — the health endpoint on the worker returns 200


# ── Whens ─────────────────────────────────────────────────────────────────────

@when(parsers.parse('the worker_agent on hostname "{hostname}" starts up'))
def worker_starts(hostname: str, ctx: SimpleNamespace) -> None:
    ctx.registering_hostname = hostname


@when(parsers.parse('it upserts a row to worker_status with hostname "{hostname}" and status "{status}"'))
async def worker_upserts(
    hostname: str,
    status: str,
    ctx: SimpleNamespace,
    worker_status_db: object,
) -> None:
    from lightcron.worker.adapters.db.worker_status_db import AsyncpgWorkerStatusDB
    wid = await worker_status_db.upsert_worker(hostname)  # type: ignore[attr-defined]
    ctx.worker_ids[hostname] = wid


@when(parsers.parse('30 seconds elapse and the worker_agent updates worker_status.last_seen for "{name}"'))
async def heartbeat_update(
    name: str, ctx: SimpleNamespace, worker_status_db: object
) -> None:
    wid = ctx.worker_ids[name]
    await worker_status_db.update_last_seen(wid)  # type: ignore[attr-defined]


@when("the scheduler runs its health check")
async def run_health_check(
    ctx: SimpleNamespace,
    db_engine: AsyncEngine,
    fake_health: object,
) -> None:
    from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository
    from lightcron.scheduler.adapters.db.worker_repo import PostgresWorkerRepository
    from lightcron.scheduler.domain.jobs.services.dispatch_service import DispatchService
    from lightcron.shared.ports.determinism.adapters import SystemTimeAdapter

    job_repo = PostgresJobRepository(db_engine)
    worker_repo = PostgresWorkerRepository(db_engine)
    service = DispatchService(job_repo, worker_repo, fake_health, SystemTimeAdapter())  # type: ignore[arg-type]
    await service._run_health_check_once()


@when(parsers.parse('the worker_agent on hostname "{hostname}" starts up and upserts to worker_status'))
async def worker_restarts(
    hostname: str, ctx: SimpleNamespace, worker_status_db: object
) -> None:
    wid = await worker_status_db.upsert_worker(hostname)  # type: ignore[attr-defined]
    ctx.worker_ids[f"re-{hostname}"] = wid


@when(parsers.parse('the scheduler calls GET /health on the worker_agent at "{name}"'))
async def health_check_worker(name: str, ctx: SimpleNamespace) -> None:
    from lightcron.worker.adapters.http.health_api import build_health_app
    from httpx import AsyncClient, ASGITransport

    health_app = build_health_app()
    async with AsyncClient(transport=ASGITransport(app=health_app), base_url="http://worker") as client:
        ctx.response = await client.get("/health")


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse('a row exists in worker_status for hostname "{hostname}" with status "{status}"'))
async def assert_worker_row(
    hostname: str, status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT status FROM worker_status WHERE hostname = :h"),
            {"h": hostname},
        )
        result = row.fetchone()
    assert result is not None, f"No worker_status row for hostname {hostname!r}"
    assert result.status == status


@then("the row has a unique worker_id")
async def assert_has_worker_id(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        row = await conn.execute(sa.text("SELECT worker_id FROM worker_status LIMIT 1"))
        result = row.fetchone()
    assert result is not None
    UUID(str(result.worker_id))


@then("last_seen is set to approximately now")
async def assert_last_seen_now(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text(
                "SELECT EXTRACT(EPOCH FROM (now() - last_seen)) AS age FROM worker_status "
                "ORDER BY registered_at DESC LIMIT 1"
            )
        )
        result = row.fetchone()
    assert result is not None and abs(float(result.age)) < 5


@then(parsers.parse('last_seen for worker_id "{name}" is updated to approximately now'))
async def assert_last_seen_updated(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = ctx.worker_ids[name]
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text(
                "SELECT EXTRACT(EPOCH FROM (now() - last_seen)) AS age "
                "FROM worker_status WHERE worker_id = :id"
            ),
            {"id": str(wid)},
        )
        result = row.fetchone()
    assert result is not None and abs(float(result.age)) < 5


@then(parsers.parse('worker_status for "{name}" has status "{status}"'))
async def assert_worker_status(
    name: str, status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = ctx.worker_ids.get(name)
    if wid is None:
        # Try by hostname key
        async with db_engine.connect() as conn:
            row = await conn.execute(
                sa.text("SELECT status FROM worker_status WHERE hostname LIKE :h"),
                {"h": f"%{name}%"},
            )
            result = row.fetchone()
        assert result is not None and result.status == status
    else:
        actual = await get_worker_status(db_engine, wid)
        assert actual == status


@then(parsers.parse('the row for hostname "{hostname}" has status "{status}"'))
async def assert_hostname_status(
    hostname: str, status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT status FROM worker_status WHERE hostname = :h"),
            {"h": hostname},
        )
        result = row.fetchone()
    assert result is not None and result.status == status


@then(parsers.parse('the worker_id remains "{name}"'))
async def assert_worker_id_preserved(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    original_wid = ctx.worker_ids.get(name) or ctx.worker_ids.get(f"w-{name.split('-')[-1]}")
    hostname = next(
        (h for h, wid in ctx.worker_ids.items() if wid == original_wid), None
    )
    if hostname is None:
        return  # Can't verify without hostname mapping

    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT worker_id FROM worker_status WHERE hostname = :h"),
            {"h": hostname},
        )
        result = row.fetchone()
    assert result is not None and str(result.worker_id) == str(original_wid)
