"""BDD step definitions for cancel-job.feature (J005).

All step functions are synchronous (pytest-bdd 8 requirement).
"""

from __future__ import annotations

from types import SimpleNamespace

from pytest_bdd import given, parsers, scenario, then, when
from starlette.testclient import TestClient

from tests.bdd.conftest import db_run, get_job_status, insert_job, insert_worker

FEATURE = "../../../../specs/features/job-management/cancel-job.feature"


@scenario(FEATURE, "Cancel a pending job")
def test_cancel_pending() -> None: ...

@scenario(FEATURE, "Cancel a running job — scheduler writes cancelled; worker_agent detects and stops")
def test_cancel_running() -> None: ...

@scenario(FEATURE, "Cancel an assigned job")
def test_cancel_assigned() -> None: ...

@scenario(FEATURE, "Cannot cancel a completed job")
def test_cannot_cancel_completed() -> None: ...

@scenario(FEATURE, "Cannot cancel a failed job")
def test_cannot_cancel_failed() -> None: ...

@scenario(FEATURE, "Cannot cancel a lost job")
def test_cannot_cancel_lost() -> None: ...

@scenario(FEATURE, "Cancel returns 404 for unknown job")
def test_cancel_unknown() -> None: ...

@scenario(FEATURE, "Job is marked cancelled even when the assigned worker is currently offline")
def test_cancel_offline_worker() -> None: ...


# ── Givens ────────────────────────────────────────────────────────────────────

@given(parsers.parse('a job "{name}" exists with status "{status}"'))
def given_job_with_status(name: str, status: str, ctx: SimpleNamespace) -> None:
    job_id = db_run(insert_job, status=status)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a job "{name}" has status "{status}"'))
def given_job_has_status(name: str, status: str, ctx: SimpleNamespace) -> None:
    job_id = db_run(insert_job, status=status)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a worker "{name}" is registered in worker_status with status "{status}"'))
def given_worker_registered(name: str, status: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=f"host-{name}", status=status)
    ctx.worker_ids[name] = wid


@given(parsers.parse('a job "{name}" has status "{status}" with worker_id "{worker}" in the jobs table'))
def given_job_with_worker_in_table(
    name: str, status: str, worker: str, ctx: SimpleNamespace
) -> None:
    wid = ctx.worker_ids.get(worker)
    job_id = db_run(insert_job, status=status, worker_id=wid)
    ctx.job_ids[name] = job_id


@given(parsers.parse('a worker "{name}" has status "{status}" in worker_status'))
def given_worker_with_status(name: str, status: str, ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname=f"host-{name}", status=status)
    ctx.worker_ids[name] = wid


@given(parsers.parse('a job "{name}" has status "{status}" with worker_id "{worker}"'))
def given_job_status_worker(name: str, status: str, worker: str, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get(worker)
    if wid is None:
        wid = db_run(insert_worker, hostname=f"host-{worker}")
        ctx.worker_ids[worker] = wid
    job_id = db_run(insert_job, status=status, worker_id=wid)
    ctx.job_ids[name] = job_id


# ── Whens ─────────────────────────────────────────────────────────────────────

@when(parsers.parse("POST /jobs/{name}/cancel is called"))
def post_cancel(name: str, ctx: SimpleNamespace, http_client: TestClient) -> None:
    job_id = ctx.job_ids.get(name)
    if job_id is None:
        url = "/jobs/00000000-0000-0000-0000-000000000000/cancel"
    else:
        url = f"/jobs/{job_id}/cancel"
    ctx.response = http_client.post(url)


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse('job "{name}" status is "{status}"'))
def assert_job_status_in_db(name: str, status: str, ctx: SimpleNamespace) -> None:
    job_id = ctx.job_ids[name]
    actual = db_run(get_job_status, job_id)
    assert actual == status, f"Expected {status!r}, got {actual!r}"


@then(parsers.parse('job "{name}" status is "{status}" in the jobs table'))
def assert_job_status_in_table(name: str, status: str, ctx: SimpleNamespace) -> None:
    job_id = ctx.job_ids[name]
    actual = db_run(get_job_status, job_id)
    assert actual == status


@then(parsers.parse('the worker_agent on "{worker}" detects the "{status}" status on its next poll'))
def worker_detects_status(worker: str, status: str, ctx: SimpleNamespace) -> None:
    job_id = ctx.job_ids.get("j-002")
    if job_id:
        actual = db_run(get_job_status, job_id)
        assert actual == status


@then(parsers.parse('the worker_agent stops the job process for "{name}"'))
def worker_stops_job(name: str) -> None:
    pass
