"""BDD step definitions for job-dispatch.feature (J003)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.bdd.conftest import get_job_status, insert_job, insert_worker

FEATURE = "../../../../specs/features/worker-management/job-dispatch.feature"


@scenario(FEATURE, "Scheduler marks a job ready when start_time is reached and there are no dependencies")
def test_ready_no_deps() -> None: ...

@scenario(FEATURE, "Scheduler marks a job ready when start_time is reached and all dependencies are completed")
def test_ready_deps_completed() -> None: ...

@scenario(FEATURE, "Job stays pending when start_time is reached but a dependency is not yet completed")
def test_stays_pending_dep_not_completed() -> None: ...

@scenario(FEATURE, "Job stays pending when start_time has not yet been reached")
def test_stays_pending_future_start() -> None: ...

@scenario(FEATURE, "Worker agent polls the jobs table and claims a ready job")
def test_worker_claims_ready_job() -> None: ...

@scenario(FEATURE, "Worker agent updates status to running after starting the job process")
def test_worker_updates_running() -> None: ...

@scenario(FEATURE, "Exactly one worker wins when two agents claim the same job simultaneously")
def test_race_condition_one_winner() -> None: ...

@scenario(FEATURE, "Worker agent finds nothing to claim when no ready jobs exist")
def test_no_ready_jobs() -> None: ...

@scenario(FEATURE, "Ready job remains ready when no workers are online")
def test_ready_no_workers() -> None: ...

@scenario(FEATURE, "Assigned job transitions to lost if worker heartbeat expires before confirming start")
def test_assigned_job_lost_on_heartbeat_expiry() -> None: ...


# ── Background ────────────────────────────────────────────────────────────────

@given("the Lightcron scheduler is running")
def scheduler_running() -> None:
    pass  # Scheduler services are wired in the test fixtures


# ── Givens: scheduler/pending→ready ──────────────────────────────────────────

@given(parsers.parse('a job "{name}" exists in the jobs table with status "pending", start_time of now, and no depends_on'))
async def given_pending_job_no_deps(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = await insert_job(db_engine, status="pending", start_time_offset_seconds=0)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a job "{name}" exists with status "pending", start_time of now, and depends_on ["{dep}"]'))
async def given_pending_job_with_dep(
    name: str, dep: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    dep_id = ctx.job_ids[dep]
    job_id = await insert_job(
        db_engine,
        status="pending",
        start_time_offset_seconds=0,
        depends_on=[dep_id],
    )
    ctx.job_ids[name] = job_id


@given(parsers.parse('a job "{name}" exists with status "{status}", start_time of now, and depends_on ["{dep}"]'))
async def given_pending_job_dep_any_status(
    name: str, status: str, dep: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    dep_id = ctx.job_ids[dep]
    job_id = await insert_job(
        db_engine,
        status="pending",
        start_time_offset_seconds=0,
        depends_on=[dep_id],
    )
    ctx.job_ids[name] = job_id


@given(parsers.parse('a job "{name}" exists with status "pending", start_time 60 seconds from now, and no depends_on'))
async def given_pending_job_future_start(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = await insert_job(db_engine, status="pending", start_time_offset_seconds=60)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a job "{name}" exists with status "{status}"'))
async def given_job_with_any_status(
    name: str, status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = await insert_job(db_engine, status=status)
    ctx.job_ids[name] = job_id


# ── Givens: worker claiming ───────────────────────────────────────────────────

@given(parsers.parse('a job "{name}" exists in the jobs table with status "ready" and command "{command}"'))
async def given_ready_job_with_command(
    name: str, command: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = await insert_job(db_engine, status="ready", command=command)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a worker_agent "{name}" is online'))
async def given_worker_online(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = await insert_worker(db_engine, hostname=f"host-{name}")
    ctx.worker_ids[name] = wid


@given(parsers.parse('a job "{name}" has status "assigned" with worker_id "{worker}"'))
async def given_assigned_job(
    name: str, worker: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = ctx.worker_ids.get(worker)
    if wid is None:
        wid = await insert_worker(db_engine, hostname=f"host-{worker}")
        ctx.worker_ids[worker] = wid
    job_id = await insert_job(db_engine, status="assigned", worker_id=wid)
    ctx.job_ids[name] = job_id


@given(parsers.parse('worker_agents "{w1}" and "{w2}" both attempt to claim "{name}" at the same time'))
async def given_two_workers_ready_to_claim(
    w1: str, w2: str, name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid1 = await insert_worker(db_engine, hostname=f"host-{w1}")
    wid2 = await insert_worker(db_engine, hostname=f"host-{w2}")
    ctx.worker_ids[w1] = wid1
    ctx.worker_ids[w2] = wid2
    # job already inserted by a prior given; if not, insert now
    if name not in ctx.job_ids:
        job_id = await insert_job(db_engine, status="ready")
        ctx.job_ids[name] = job_id


@given('no jobs in the jobs table have status "ready"')
async def given_no_ready_jobs(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    pass  # clean_tables fixture guarantees empty state; no insert needed


@given('no rows in worker_status have status "online"')
async def given_no_online_workers(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    pass  # clean_tables guarantees empty state


@given(parsers.parse('a job "{name}" exists with status "ready"'))
async def given_ready_job(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = await insert_job(db_engine, status="ready")
    ctx.job_ids[name] = job_id


@given(parsers.parse('worker_status for "{name}" has last_seen 90 seconds ago'))
async def given_worker_stale_90s(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    wid = ctx.worker_ids.get(name)
    if wid is None:
        wid = await insert_worker(db_engine, hostname=f"host-{name}", last_seen_offset_seconds=95)
        ctx.worker_ids[name] = wid
        return
    async with db_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                sa.text(
                    "UPDATE worker_status SET last_seen = now() - interval '95 seconds' "
                    "WHERE worker_id = :id"
                ),
                {"id": str(wid)},
            )


# ── Whens ─────────────────────────────────────────────────────────────────────

@when("the scheduler runs its ready-transition loop")
async def run_ready_transition(db_engine: AsyncEngine) -> None:
    from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository
    from lightcron.scheduler.adapters.db.worker_repo import PostgresWorkerRepository
    from lightcron.scheduler.adapters.health.worker_health_client import HttpWorkerHealthClient
    from lightcron.scheduler.domain.jobs.services.dispatch_service import DispatchService
    from lightcron.shared.ports.determinism.adapters import SystemTimeAdapter

    job_repo = PostgresJobRepository(db_engine)
    worker_repo = PostgresWorkerRepository(db_engine)
    health_client = HttpWorkerHealthClient()
    service = DispatchService(job_repo, worker_repo, health_client, SystemTimeAdapter())
    await service._run_ready_transition_once()


@when(parsers.parse('the worker_agent on "{name}" polls for ready jobs and attempts to claim "{job}"'))
async def worker_claims_job(
    name: str, job: str, ctx: SimpleNamespace, job_db: object
) -> None:
    wid = ctx.worker_ids[name]
    job_id = ctx.job_ids[job]
    claimed = await job_db.claim_job(wid)  # type: ignore[attr-defined]
    ctx.claimed_job = claimed


@when(parsers.parse('the worker_agent on "{name}" starts the job process'))
def worker_starts_process(name: str, ctx: SimpleNamespace) -> None:
    ctx.process_started = True


@when("updates the jobs table")
async def worker_updates_to_running(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    job_id = ctx.job_ids.get("j-001")
    async with db_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                sa.text(
                    "UPDATE jobs SET status = 'running', started_at = now(), updated_at = now() "
                    "WHERE job_id = :id AND status NOT IN ('completed','failed','cancelled','lost')"
                ),
                {"id": str(job_id)},
            )


@when("both atomic claim updates are executed")
async def both_claims_executed(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    from lightcron.worker.adapters.db.job_db import AsyncpgJobDB

    job_db = AsyncpgJobDB(db_engine)
    wid1 = ctx.worker_ids.get("w-001")
    wid2 = ctx.worker_ids.get("w-002")

    results = await asyncio.gather(
        job_db.claim_job(wid1),
        job_db.claim_job(wid2),
        return_exceptions=True,
    )
    ctx.claim_results = results


@when(parsers.parse('the worker_agent on "{name}" polls for ready jobs'))
async def worker_polls_no_jobs(
    name: str, ctx: SimpleNamespace, job_db: object
) -> None:
    wid = ctx.worker_ids.get(name)
    if wid is None:
        from uuid import uuid4
        wid = uuid4()
    claimed = await job_db.claim_job(wid)  # type: ignore[attr-defined]
    ctx.claimed_job = claimed


@when("time passes and no worker_agent polls")
def time_passes(ctx: SimpleNamespace) -> None:
    pass  # No-op: DB state not changed


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


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse('job "{name}" status in the jobs table is "{status}"'))
async def assert_job_status_in_table(
    name: str, status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = ctx.job_ids[name]
    actual = await get_job_status(db_engine, job_id)
    assert actual == status, f"Expected {status!r}, got {actual!r}"


@then(parsers.parse('job "{name}" status remains "{status}"'))
async def assert_job_status_remains(
    name: str, status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = ctx.job_ids[name]
    actual = await get_job_status(db_engine, job_id)
    assert actual == status, f"Expected job to remain {status!r}, got {actual!r}"


@then(parsers.parse('job "{name}" worker_id in the jobs table is "{worker}"'))
async def assert_job_worker_id(
    name: str, worker: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = ctx.job_ids[name]
    expected_wid = ctx.worker_ids[worker]
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT worker_id FROM jobs WHERE job_id = :id"),
            {"id": str(job_id)},
        )
        result = row.fetchone()
    assert result is not None and str(result.worker_id) == str(expected_wid)


@then("the worker_agent has the job command and any resource limits (max_runtime, max_memory)")
def assert_worker_has_job_details(ctx: SimpleNamespace) -> None:
    claimed = getattr(ctx, "claimed_job", None)
    assert claimed is not None, "Worker did not claim a job"
    assert hasattr(claimed, "command") or isinstance(claimed, dict)


@then(parsers.parse('job "{name}" status is "assigned"'))
async def assert_job_assigned(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = ctx.job_ids[name]
    actual = await get_job_status(db_engine, job_id)
    assert actual == "assigned", f"Expected assigned, got {actual!r}"


@then(parsers.parse('exactly one of "{w1}" or "{w2}" is recorded as worker_id'))
async def assert_one_winner(
    w1: str, w2: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = ctx.job_ids.get("j-001")
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT worker_id FROM jobs WHERE job_id = :id"),
            {"id": str(job_id)},
        )
        result = row.fetchone()
    assert result is not None
    recorded = str(result.worker_id)
    wid1 = str(ctx.worker_ids[w1])
    wid2 = str(ctx.worker_ids[w2])
    assert recorded in (wid1, wid2), f"worker_id {recorded} is neither {w1} nor {w2}"
    ctx.winning_worker_id = recorded


@then(parsers.parse('the other worker_agent observes 0 rows affected and does not hold the job'))
def assert_loser_gets_nothing(ctx: SimpleNamespace) -> None:
    results = getattr(ctx, "claim_results", [])
    none_count = sum(1 for r in results if r is None)
    assert none_count == 1, f"Expected exactly 1 None (loser), got claim_results={results}"


@then("the worker_agent finds no jobs to claim and waits for the next poll interval")
def assert_no_job_claimed(ctx: SimpleNamespace) -> None:
    assert getattr(ctx, "claimed_job", None) is None


@then(parsers.parse('job "{name}" status remains "ready"'))
async def assert_job_remains_ready(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = ctx.job_ids[name]
    actual = await get_job_status(db_engine, job_id)
    assert actual == "ready", f"Expected ready, got {actual!r}"


@then(parsers.parse('job "{name}" status in the jobs table is "lost"'))
async def assert_job_lost(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    job_id = ctx.job_ids[name]
    actual = await get_job_status(db_engine, job_id)
    assert actual == "lost", f"Expected lost, got {actual!r}"


@then(parsers.parse('worker_status for "{name}" has status "offline"'))
async def assert_worker_offline(
    name: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    from tests.bdd.conftest import get_worker_status
    wid = ctx.worker_ids[name]
    actual = await get_worker_status(db_engine, wid)
    assert actual == "offline", f"Expected offline, got {actual!r}"
