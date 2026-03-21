"""BDD step definitions for worker-health-monitoring.feature (J007).

All step functions are synchronous (pytest-bdd 8 requirement).
"""

from __future__ import annotations

from types import SimpleNamespace

from pytest_bdd import given, parsers, scenario, then, when
from starlette.testclient import TestClient

from tests.bdd.conftest import db_run, insert_job, insert_worker

FEATURE = "../../../../specs/features/operations/worker-health-monitoring.feature"


@scenario(FEATURE, "List workers shows all registered workers with their status")
def test_list_workers() -> None: ...

@scenario(FEATURE, "Worker with expired heartbeat appears as offline")
def test_expired_heartbeat_offline() -> None: ...

@scenario(FEATURE, "No workers registered returns empty list")
def test_no_workers_empty() -> None: ...

@scenario(FEATURE, "Worker with running jobs shows correct job count")
def test_worker_running_job_count() -> None: ...


# ── Givens ────────────────────────────────────────────────────────────────────

@given("workers are registered:")
def given_workers_registered(ctx: SimpleNamespace, datatable: list) -> None:
    """Insert workers from a datatable with columns: name, hostname, status."""
    for row in datatable[1:]:
        name, hostname, status = row[0], row[1], row[2]
        wid = db_run(insert_worker, hostname=hostname, status=status)
        ctx.worker_ids[name] = wid
        ctx.worker_ids[hostname] = wid


@given(parsers.parse('a worker "{name}" with hostname "{hostname}" last sent a heartbeat 90 seconds ago'))
def given_worker_stale_90s(name: str, hostname: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=hostname, status="offline", last_seen_offset_seconds=95)
    ctx.worker_ids[name] = wid
    ctx.worker_ids[hostname] = wid


@given(parsers.parse('a worker "{name}" with hostname "{hostname}" is online'))
def given_worker_online(name: str, hostname: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=hostname, status="online")
    ctx.worker_ids[name] = wid
    ctx.worker_ids[hostname] = wid


@given(parsers.parse('worker "{name}" has {count:d} running jobs'))
def given_worker_has_running_jobs(name: str, count: int, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids[name]
    for _ in range(count):
        db_run(insert_job, status="running", worker_id=wid)


# ── Whens ─────────────────────────────────────────────────────────────────────

@when("GET /workers is called")
def get_workers(ctx: SimpleNamespace, http_client: TestClient) -> None:
    ctx.response = http_client.get("/workers")


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse("the response contains {count:d} workers"))
def assert_worker_count(count: int, ctx: SimpleNamespace) -> None:
    data = ctx.response.json()
    assert len(data) == count, f"Expected {count} workers, got {len(data)}"


@then("each worker entry includes worker_id, hostname, status, last_seen, and running job count")
def assert_worker_fields(ctx: SimpleNamespace) -> None:
    for entry in ctx.response.json():
        assert "worker_id" in entry
        assert "hostname" in entry
        assert "status" in entry
        assert "last_seen" in entry
        assert "running_job_count" in entry


@then(parsers.parse('worker "{name}" has status "offline"'))
def assert_worker_status_offline(name: str, ctx: SimpleNamespace) -> None:
    wid = str(ctx.worker_ids[name])
    workers = ctx.response.json()
    match = next((w for w in workers if w["worker_id"] == wid), None)
    assert match is not None, f"Worker {name} not found in response"
    assert match["status"] == "offline", f"Expected offline, got {match['status']!r}"


@then("the response contains an empty list")
def assert_empty_workers(ctx: SimpleNamespace) -> None:
    assert ctx.response.json() == []


@then(parsers.parse('worker "{name}" running job count is {count:d}'))
def assert_running_job_count(name: str, count: int, ctx: SimpleNamespace) -> None:
    wid = str(ctx.worker_ids[name])
    workers = ctx.response.json()
    match = next((w for w in workers if w["worker_id"] == wid), None)
    assert match is not None, f"Worker {name} not found in response"
    assert match["running_job_count"] == count, (
        f"Expected running_job_count={count}, got {match['running_job_count']}"
    )
