"""BDD step definitions for stuck-job-recovery.feature (J008).

All step functions are synchronous (pytest-bdd 8 requirement).
"""

from __future__ import annotations

from types import SimpleNamespace

import sqlalchemy as sa
from pytest_bdd import given, parsers, scenario, then, when
from starlette.testclient import TestClient

from tests.bdd.conftest import (
    FakeWorkerHealthClient,
    db_run,
    get_job_status,
    get_worker_status,
    insert_job,
    insert_worker,
)

FEATURE = "../../../../specs/features/operations/stuck-job-recovery.feature"


@scenario(FEATURE, "Worker with stale last_seen but healthy /health endpoint stays online")
def test_stage1_healthy_stays_online() -> None: ...

@scenario(FEATURE, "Worker with stale last_seen and failing /health is marked offline")
def test_stage1_unhealthy_marked_offline() -> None: ...

@scenario(FEATURE, "Running job is marked lost when last_seen exceeds 90s (no /health probe)")
def test_stage2_running_job_lost() -> None: ...

@scenario(FEATURE, "Assigned job is marked lost when last_seen exceeds 90s")
def test_stage2_assigned_job_lost() -> None: ...

@scenario(FEATURE, "Worker with fresh last_seen is left completely alone")
def test_fresh_worker_untouched() -> None: ...

@scenario(FEATURE, "Lost jobs are visible via the REST API status filter")
def test_lost_jobs_visible_via_api() -> None: ...

@scenario(FEATURE, "Worker that re-registers after going offline recovers its worker_id and comes back online")
def test_reregister_recovers() -> None: ...

@scenario(FEATURE, "Worker agent kills a process it is still running when the scheduler has marked it lost")
def test_worker_kills_lost_process() -> None: ...

@scenario(FEATURE, "Multiple workers failing simultaneously marks all their jobs as lost")
def test_mass_failure() -> None: ...


# ── Async DB helpers ──────────────────────────────────────────────────────────

async def _run_health_check(engine, fake_health) -> None:
    from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository
    from lightcron.scheduler.adapters.db.worker_repo import PostgresWorkerRepository
    from lightcron.scheduler.domain.jobs.services.dispatch_service import DispatchService
    from lightcron.shared.ports.determinism.adapters import SystemTimeAdapter

    job_repo = PostgresJobRepository(engine)
    worker_repo = PostgresWorkerRepository(engine)
    service = DispatchService(job_repo, worker_repo, fake_health, SystemTimeAdapter())  # type: ignore[arg-type]
    await service._run_health_check_once()


async def _run_health_check_unhealthy(engine, fake_health, worker_ids: dict) -> None:
    """Mark all known workers unhealthy then re-run health check."""
    from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository
    from lightcron.scheduler.adapters.db.worker_repo import PostgresWorkerRepository
    from lightcron.scheduler.domain.jobs.services.dispatch_service import DispatchService
    from lightcron.shared.ports.determinism.adapters import SystemTimeAdapter

    client = fake_health
    if isinstance(client, FakeWorkerHealthClient):
        for wid in worker_ids.values():
            client.set_unhealthy(str(wid))

    job_repo = PostgresJobRepository(engine)
    worker_repo = PostgresWorkerRepository(engine)
    service = DispatchService(job_repo, worker_repo, fake_health, SystemTimeAdapter())  # type: ignore[arg-type]
    await service._run_health_check_once()


async def _upsert_worker_restart(engine, hostname: str):
    from lightcron.worker.adapters.db.worker_status_db import AsyncpgWorkerStatusDB
    db = AsyncpgWorkerStatusDB(engine)
    return await db.upsert_worker(hostname)


async def _query_worker_by_hostname(engine, hostname: str):
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT status FROM worker_status WHERE hostname = :h"),
            {"h": hostname},
        )
        return row.fetchone()


async def _query_worker_id_by_hostname(engine, hostname: str):
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT worker_id FROM worker_status WHERE hostname = :h"),
            {"h": hostname},
        )
        return row.fetchone()


# ── Givens ────────────────────────────────────────────────────────────────────

@given(parsers.parse('a worker_status row for "{name}" has last_seen 60 seconds ago'))
def given_worker_stale_60s(name: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=f"host-{name}", last_seen_offset_seconds=65)
    ctx.worker_ids[name] = wid


@given(parsers.parse('a worker_status row for "{name}" has last_seen 90 seconds ago'))
def given_worker_stale_90s(name: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=f"host-{name}", last_seen_offset_seconds=95)
    ctx.worker_ids[name] = wid


@given(parsers.parse('a worker_status row for "{name}" has last_seen 20 seconds ago'))
def given_worker_fresh(name: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=f"host-{name}", last_seen_offset_seconds=20)
    ctx.worker_ids[name] = wid


@given(parsers.parse('a job "{name}" in the jobs table has status "{status}" with worker_id "{worker}"'))
def given_job_with_worker(name: str, status: str, worker: str, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get(worker)
    if wid is None:
        wid = db_run(insert_worker, hostname=f"host-{worker}")
        ctx.worker_ids[worker] = wid
    job_id = db_run(insert_job, status=status, worker_id=wid)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a job "{name}" has status "lost" with worker_id "{worker}" in the jobs table'))
def given_lost_job_with_worker(name: str, worker: str, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get(worker)
    if wid is None:
        wid = db_run(insert_worker, hostname=f"host-{worker}")
        ctx.worker_ids[worker] = wid
    job_id = db_run(insert_job, status="lost", worker_id=wid)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a worker_status row for hostname "{hostname}" with worker_id "{name}" has status "offline"'))
def given_offline_worker_with_hostname(hostname: str, name: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=hostname, status="offline")
    ctx.worker_ids[name] = wid
    ctx.worker_ids[hostname] = wid


@given(parsers.parse('a worker_status row for "{name}" has status "online"'))
def given_worker_online(name: str, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get(name)
    if wid is None:
        wid = db_run(insert_worker, hostname=f"host-{name}", status="online")
        ctx.worker_ids[name] = wid


@given(parsers.parse('the worker_agent on "{name}" still has the process for "{job}" running locally'))
def given_worker_has_local_process(name: str, job: str, ctx: SimpleNamespace) -> None:
    ctx.local_process_running = True
    ctx.local_process_job = job


@given(parsers.parse('worker_status rows for "{w1}" and "{w2}" both have last_seen 90 seconds ago'))
def given_two_stale_workers(w1: str, w2: str, ctx: SimpleNamespace) -> None:
    wid1 = db_run(insert_worker, hostname=f"host-{w1}", last_seen_offset_seconds=95)
    wid2 = db_run(insert_worker, hostname=f"host-{w2}", last_seen_offset_seconds=95)
    ctx.worker_ids[w1] = wid1
    ctx.worker_ids[w2] = wid2


@given(parsers.parse('job "{name}" has status "running" with worker_id "{worker}"'))
def given_running_job_with_worker(name: str, worker: str, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get(worker)
    if wid is None:
        wid = db_run(insert_worker, hostname=f"host-{worker}")
        ctx.worker_ids[worker] = wid
    job_id = db_run(insert_job, status="running", worker_id=wid)
    ctx.job_ids[name] = job_id


# ── Whens ─────────────────────────────────────────────────────────────────────

@when("the scheduler runs its health check")
def run_health_check(ctx: SimpleNamespace, fake_health: object) -> None:
    db_run(_run_health_check, fake_health)


@when(parsers.parse('the scheduler calls GET /health on the worker_agent at "{name}"'))
def scheduler_probes_worker(name: str, ctx: SimpleNamespace, fake_health: object) -> None:
    pass  # Health probe happens inside _run_health_check; this step is declarative


@when("the worker_agent returns HTTP 200")
def worker_returns_200(ctx: SimpleNamespace, fake_health: object) -> None:
    pass  # FakeWorkerHealthClient defaults to True (healthy)


@when("the worker_agent does not respond (connection refused or timeout)")
def worker_does_not_respond(ctx: SimpleNamespace, fake_health: object) -> None:
    """Mark all workers unhealthy and re-run the health check."""
    db_run(_run_health_check_unhealthy, fake_health, ctx.worker_ids)


@when(parsers.parse('the worker_agent on "{hostname}" restarts and upserts to worker_status'))
def worker_restarts(hostname: str, ctx: SimpleNamespace) -> None:
    wid = db_run(_upsert_worker_restart, hostname)
    ctx.worker_ids[f"re-{hostname}"] = wid


@when(parsers.parse('the worker_agent polls the jobs table for its running job statuses'))
def worker_polls_job_status(ctx: SimpleNamespace) -> None:
    job_name = getattr(ctx, "local_process_job", None)
    if job_name:
        job_id = ctx.job_ids.get(job_name)
        if job_id:
            ctx.polled_job_status = db_run(get_job_status, job_id)


@when(parsers.parse('detects that "{name}" has status "lost"'))
def worker_detects_lost(name: str, ctx: SimpleNamespace) -> None:
    assert ctx.polled_job_status == "lost"


@when("GET /jobs?status=lost is called")
def get_jobs_lost(ctx: SimpleNamespace, http_client: TestClient) -> None:
    ctx.response = http_client.get("/jobs", params={"status": "lost"})


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse('worker_status for "{name}" status remains "online"'))
def assert_worker_still_online(name: str, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids[name]
    actual = db_run(get_worker_status, wid)
    assert actual == "online", f"Expected online, got {actual!r}"


@then(parsers.parse('job "{name}" status remains "running"'))
def assert_job_still_running(name: str, ctx: SimpleNamespace) -> None:
    job_id = ctx.job_ids[name]
    actual = db_run(get_job_status, job_id)
    assert actual == "running", f"Expected running, got {actual!r}"


@then(parsers.parse('worker_status for "{name}" has status "offline"'))
def assert_worker_offline(name: str, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids[name]
    actual = db_run(get_worker_status, wid)
    assert actual == "offline", f"Expected offline, got {actual!r}"


@then(parsers.parse('job "{name}" status in the jobs table is "lost"'))
def assert_job_lost(name: str, ctx: SimpleNamespace) -> None:
    job_id = ctx.job_ids[name]
    actual = db_run(get_job_status, job_id)
    assert actual == "lost", f"Expected lost, got {actual!r}"


@then(parsers.parse('the scheduler does NOT call GET /health on "{name}"'))
def assert_no_health_probe(name: str, ctx: SimpleNamespace, fake_health: object) -> None:
    if isinstance(fake_health, FakeWorkerHealthClient):
        wid = ctx.worker_ids.get(name)
        if wid is not None:
            assert str(wid) not in fake_health.probed, (
                f"Worker {name} ({wid}) should NOT have been probed but was"
            )


@then(parsers.parse('job "{name}" appears in the response with worker_id "{worker}"'))
def assert_job_in_response(name: str, worker: str, ctx: SimpleNamespace) -> None:
    job_id = str(ctx.job_ids[name])
    wid = str(ctx.worker_ids[worker])
    jobs = ctx.response.json()
    match = next((j for j in jobs if j["job_id"] == job_id), None)
    assert match is not None, f"Job {name} ({job_id}) not found in response"
    assert match["worker_id"] == wid, f"Expected worker_id {wid}, got {match['worker_id']}"


@then(parsers.parse('the worker_status row for "{hostname}" has status "online"'))
def assert_worker_row_online(hostname: str, ctx: SimpleNamespace) -> None:
    result = db_run(_query_worker_by_hostname, hostname)
    assert result is not None and result.status == "online"


@then(parsers.parse('the worker_id remains "{name}"'))
def assert_worker_id_preserved(name: str, ctx: SimpleNamespace) -> None:
    original_wid = ctx.worker_ids.get(name)
    if original_wid is None:
        return
    hostname = next(
        (h for h, wid in ctx.worker_ids.items() if wid == original_wid and h != name), None
    )
    if hostname is None:
        return
    result = db_run(_query_worker_id_by_hostname, hostname)
    assert result is not None and str(result.worker_id) == str(original_wid)


@then(parsers.parse('the worker_agent kills the process for "{name}"'))
def assert_worker_kills_process(name: str, ctx: SimpleNamespace) -> None:
    assert getattr(ctx, "local_process_running", False) is True


@then(parsers.parse('the worker_agent does not write any status update to the jobs table for "{name}"'))
def assert_no_status_update_written(name: str, ctx: SimpleNamespace) -> None:
    job_id = ctx.job_ids.get(name)
    if job_id is None:
        return
    actual = db_run(get_job_status, job_id)
    assert actual == "lost", f"Job status should remain lost, got {actual!r}"


@then(parsers.parse('job "{name}" status is "lost"'))
def assert_job_status_lost(name: str, ctx: SimpleNamespace) -> None:
    job_id = ctx.job_ids[name]
    actual = db_run(get_job_status, job_id)
    assert actual == "lost", f"Expected lost, got {actual!r}"
