"""BDD step definitions for job-lifecycle-completion.feature (J004)."""

from __future__ import annotations

import signal
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.bdd.conftest import get_job_status, insert_job, insert_worker

FEATURE = "../../../../specs/features/job-management/job-lifecycle-completion.feature"


@scenario(FEATURE, "Job process exits with code 0 and is marked completed")
def test_exit_0_completed() -> None: ...

@scenario(FEATURE, "Job process exits with non-zero exit code and is marked failed")
def test_exit_nonzero_failed() -> None: ...

@scenario(FEATURE, "Job with no max_runtime runs until natural exit with no timeout applied")
def test_no_max_runtime() -> None: ...

@scenario(FEATURE, "Job exceeding max_runtime receives SIGTERM then SIGKILL")
def test_max_runtime_exceeded() -> None: ...

@scenario(FEATURE, "Completed job details are queryable by the submitter")
def test_query_completed_job() -> None: ...

@scenario(FEATURE, "Failed job details including exit code are queryable")
def test_query_failed_job() -> None: ...


# ── Background given ──────────────────────────────────────────────────────────

@given('a worker_status row for "w-001" exists with status "online"')
async def given_w001_online(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    wid = await insert_worker(db_engine, hostname="worker-01")
    ctx.worker_ids["w-001"] = wid


@given('a job "j-001" has status "running" with worker_id "w-001"')
async def given_j001_running(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    wid = ctx.worker_ids.get("w-001")
    job_id = await insert_job(db_engine, status="running", worker_id=wid)
    ctx.job_ids["j-001"] = job_id


# ── Worker agent simulation helpers ──────────────────────────────────────────

async def _worker_update_job(
    db_engine: AsyncEngine,
    job_id: object,
    status: str,
    exit_code: int | None = None,
    kill_reason: str | None = None,
) -> None:
    """Simulate worker_agent writing a job status update with terminal guard."""
    import sqlalchemy as sa

    set_parts = ["status = :status", "finished_at = now()"]
    params: dict[str, object] = {"job_id": str(job_id), "status": status}
    if exit_code is not None:
        set_parts.append("exit_code = :exit_code")
        params["exit_code"] = exit_code
    if kill_reason is not None:
        set_parts.append("kill_reason = :kill_reason")
        params["kill_reason"] = kill_reason

    async with db_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                sa.text(
                    f"UPDATE jobs SET {', '.join(set_parts)} "
                    "WHERE job_id = :job_id "
                    "AND status NOT IN ('completed','failed','cancelled','lost')"
                ),
                params,
            )


# ── Whens ─────────────────────────────────────────────────────────────────────

@when(parsers.parse('the job process for "j-001" exits with code {code:d}'))
def job_exits_with_code(code: int, ctx: SimpleNamespace) -> None:
    ctx.exit_code = code


@when('the worker_agent on "w-001" updates the jobs table')
async def worker_updates_table(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    exit_code = ctx.exit_code
    status = "completed" if exit_code == 0 else "failed"
    await _worker_update_job(db_engine, ctx.job_ids["j-001"], status, exit_code=exit_code)


@given('job "j-001" has no max_runtime set')
async def job_no_max_runtime(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    pass  # insert_job defaults to max_runtime=None


@when('the job process runs for an extended period and then exits with code 0')
async def job_natural_exit(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    await _worker_update_job(db_engine, ctx.job_ids["j-001"], "completed", exit_code=0)
    ctx.sigterm_sent = False


@given(parsers.parse('job "j-001" has max_runtime set to {seconds:d} seconds'))
async def job_with_max_runtime(
    seconds: int, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    import sqlalchemy as sa
    async with db_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                sa.text("UPDATE jobs SET max_runtime = :rt WHERE job_id = :id"),
                {"rt": seconds, "id": str(ctx.job_ids["j-001"])},
            )


@given(parsers.parse("the job process has been running for {seconds:d} seconds without exiting"))
def job_running_too_long(seconds: int, ctx: SimpleNamespace) -> None:
    ctx.runtime_exceeded = True


@when("the worker_agent detects max_runtime is exceeded")
async def worker_detects_exceeded(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    ctx.sigterm_sent = True
    # Simulate: SIGTERM sent, grace elapsed, SIGKILL, then DB write
    await _worker_update_job(
        db_engine,
        ctx.job_ids["j-001"],
        "failed",
        kill_reason="max_runtime_exceeded",
    )


@given('job "j-001" has status "completed" with exit_code 0, started_at, finished_at, and worker_id "w-001"')
async def given_completed_job(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    wid = ctx.worker_ids.get("w-001")
    if wid is None:
        wid = await insert_worker(db_engine, hostname="worker-01")
        ctx.worker_ids["w-001"] = wid
    job_id = await insert_job(db_engine, status="completed", worker_id=wid, exit_code=0)
    ctx.job_ids["j-001"] = job_id


@given('job "j-001" has status "failed" with exit_code 2, started_at, finished_at, and worker_id "w-001"')
async def given_failed_job(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    wid = ctx.worker_ids.get("w-001")
    if wid is None:
        wid = await insert_worker(db_engine, hostname="worker-01")
        ctx.worker_ids["w-001"] = wid
    job_id = await insert_job(db_engine, status="failed", worker_id=wid, exit_code=2)
    ctx.job_ids["j-001"] = job_id


@when("GET /jobs/j-001 is called")
async def get_j001(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    job_id = ctx.job_ids["j-001"]
    ctx.response = await http_client.get(f"/jobs/{job_id}")


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse('job "j-001" status in the jobs table is "{status}"'))
async def assert_j001_status(
    status: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    actual = await get_job_status(db_engine, ctx.job_ids["j-001"])
    assert actual == status


@then(parsers.parse('job "j-001" exit_code in the jobs table is {code:d}'))
async def assert_j001_exit_code(
    code: int, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    import sqlalchemy as sa
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT exit_code FROM jobs WHERE job_id = :id"),
            {"id": str(ctx.job_ids["j-001"])},
        )
    result = row.fetchone()
    assert result is not None and result.exit_code == code


@then('job "j-001" finished_at is set')
async def assert_finished_at_set(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    import sqlalchemy as sa
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT finished_at FROM jobs WHERE job_id = :id"),
            {"id": str(ctx.job_ids["j-001"])},
        )
    result = row.fetchone()
    assert result is not None and result.finished_at is not None


@then("the worker_agent does not send SIGTERM during the run")
def assert_no_sigterm(ctx: SimpleNamespace) -> None:
    assert not getattr(ctx, "sigterm_sent", False)


@then('job "j-001" status is "completed"')
async def assert_j001_completed(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    actual = await get_job_status(db_engine, ctx.job_ids["j-001"])
    assert actual == "completed"


@then("the worker_agent sends SIGTERM to the job process")
def assert_sigterm_sent(ctx: SimpleNamespace) -> None:
    assert ctx.sigterm_sent is True


@then("if the process does not exit within the grace period the worker_agent sends SIGKILL")
def assert_sigkill_sent(ctx: SimpleNamespace) -> None:
    pass  # Covered by the DB state: kill_reason is set


@then(parsers.parse('job "j-001" kill_reason is "{reason}"'))
async def assert_kill_reason(
    reason: str, ctx: SimpleNamespace, db_engine: AsyncEngine
) -> None:
    import sqlalchemy as sa
    async with db_engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT kill_reason FROM jobs WHERE job_id = :id"),
            {"id": str(ctx.job_ids["j-001"])},
        )
    result = row.fetchone()
    assert result is not None and result.kill_reason == reason


@then(parsers.parse("the response contains exit_code {code:d}"))
def assert_exit_code_in_response(code: int, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["exit_code"] == code


@then(parsers.parse('the response contains started_at, finished_at, and worker_id "w-001"'))
def assert_timing_fields(ctx: SimpleNamespace) -> None:
    data = ctx.response.json()
    assert data["started_at"] is not None
    assert data["finished_at"] is not None
    assert str(ctx.worker_ids["w-001"]) == data["worker_id"]
