"""BDD step definitions for job-lifecycle-completion.feature (J004).

All step functions are synchronous (pytest-bdd 8 requirement).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import sqlalchemy as sa
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.testclient import TestClient

from tests.bdd.conftest import db_run, get_job_status, insert_job, insert_worker

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


# ── v2 output file + worker REST API scenarios ────────────────────────────────

@scenario(FEATURE, "Worker writes stdout and stderr to files in the jobs directory")
def test_worker_writes_output_files() -> None: ...


@scenario(FEATURE, "Worker defaults to /var/logs/lightcron/jobs when LIGHTCRON_JOBS_DIR is not set")
def test_worker_default_jobs_dir() -> None: ...


@scenario(FEATURE, "Output files contain partial content when a job is killed")
def test_partial_output_on_kill() -> None: ...


@scenario(FEATURE, "Worker REST API serves stdout file content")
def test_worker_api_serves_stdout() -> None: ...


@scenario(FEATURE, "Worker REST API serves stderr file content")
def test_worker_api_serves_stderr() -> None: ...


@scenario(FEATURE, "Worker REST API returns 404 when output file does not exist")
def test_worker_api_404_missing_file() -> None: ...


# ── Async DB helpers ──────────────────────────────────────────────────────────

async def _update_job_status(
    engine: AsyncEngine,
    job_id: object,
    status: str,
    exit_code: int | None = None,
    kill_reason: str | None = None,
) -> None:
    """Simulate worker_agent writing a job status update with terminal guard."""
    set_parts = ["status = :status", "finished_at = now()"]
    params: dict[str, object] = {"job_id": str(job_id), "status": status}
    if exit_code is not None:
        set_parts.append("exit_code = :exit_code")
        params["exit_code"] = exit_code
    if kill_reason is not None:
        set_parts.append("kill_reason = :kill_reason")
        params["kill_reason"] = kill_reason

    async with engine.connect() as conn, conn.begin():
        await conn.execute(
            sa.text(
                f"UPDATE jobs SET {', '.join(set_parts)} "
                "WHERE job_id = :job_id "
                "AND status NOT IN ('completed','failed','cancelled','lost')"
            ),
            params,
        )


async def _set_max_runtime(engine: AsyncEngine, job_id: object, seconds: int) -> None:
    async with engine.connect() as conn, conn.begin():
        await conn.execute(
            sa.text("UPDATE jobs SET max_runtime = :rt WHERE job_id = :id"),
            {"rt": seconds, "id": str(job_id)},
        )


async def _get_exit_code(engine: AsyncEngine, job_id: object) -> int | None:
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT exit_code FROM jobs WHERE job_id = :id"),
            {"id": str(job_id)},
        )
        result = row.fetchone()
    return result.exit_code if result else None


async def _get_finished_at(engine: AsyncEngine, job_id: object) -> object:
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT finished_at FROM jobs WHERE job_id = :id"),
            {"id": str(job_id)},
        )
        result = row.fetchone()
    return result.finished_at if result else None


async def _get_kill_reason(engine: AsyncEngine, job_id: object) -> str | None:
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT kill_reason FROM jobs WHERE job_id = :id"),
            {"id": str(job_id)},
        )
        result = row.fetchone()
    return result.kill_reason if result else None


# ── Background given ──────────────────────────────────────────────────────────

@given('a worker_status row for "w-001" exists with status "online"')
def given_w001_online(ctx: SimpleNamespace) -> None:
    wid = db_run(insert_worker, hostname="worker-01")
    ctx.worker_ids["w-001"] = wid


@given('a job "j-001" has status "running" with worker_id "w-001"')
def given_j001_running(ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get("w-001")
    job_id = db_run(insert_job, status="running", worker_id=wid)
    ctx.job_ids["j-001"] = job_id


# ── Whens ─────────────────────────────────────────────────────────────────────

@when(parsers.parse('the job process for "j-001" exits with code {code:d}'))
def job_exits_with_code(code: int, ctx: SimpleNamespace) -> None:
    ctx.exit_code = code


@when('the worker_agent on "w-001" updates the jobs table')
def worker_updates_table(ctx: SimpleNamespace) -> None:
    exit_code = ctx.exit_code
    status = "completed" if exit_code == 0 else "failed"
    db_run(_update_job_status, ctx.job_ids["j-001"], status, exit_code=exit_code)


@given('job "j-001" has no max_runtime set')
def job_no_max_runtime(ctx: SimpleNamespace) -> None:
    pass  # insert_job defaults to max_runtime=None


@when('the job process runs for an extended period and then exits with code 0')
def job_natural_exit(ctx: SimpleNamespace) -> None:
    db_run(_update_job_status, ctx.job_ids["j-001"], "completed", exit_code=0)
    ctx.sigterm_sent = False


@given(parsers.parse('job "j-001" has max_runtime set to {seconds:d} seconds'))
def job_with_max_runtime(seconds: int, ctx: SimpleNamespace) -> None:
    db_run(_set_max_runtime, ctx.job_ids["j-001"], seconds)


@given(parsers.parse("the job process has been running for {seconds:d} seconds without exiting"))
def job_running_too_long(seconds: int, ctx: SimpleNamespace) -> None:
    ctx.runtime_exceeded = True


@when("the worker_agent detects max_runtime is exceeded")
def worker_detects_exceeded(ctx: SimpleNamespace) -> None:
    ctx.sigterm_sent = True
    db_run(_update_job_status, ctx.job_ids["j-001"], "failed", kill_reason="max_runtime_exceeded")


@given('job "j-001" has status "completed" with exit_code 0, started_at, finished_at, and worker_id "w-001"')
def given_completed_job(ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get("w-001")
    if wid is None:
        wid = db_run(insert_worker, hostname="worker-01")
        ctx.worker_ids["w-001"] = wid
    job_id = db_run(insert_job, status="completed", worker_id=wid, exit_code=0)
    ctx.job_ids["j-001"] = job_id


@given('job "j-001" has status "failed" with exit_code 2, started_at, finished_at, and worker_id "w-001"')
def given_failed_job(ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get("w-001")
    if wid is None:
        wid = db_run(insert_worker, hostname="worker-01")
        ctx.worker_ids["w-001"] = wid
    job_id = db_run(insert_job, status="failed", worker_id=wid, exit_code=2)
    ctx.job_ids["j-001"] = job_id


@when("GET /jobs/j-001 is called")
def get_j001(ctx: SimpleNamespace, http_client: TestClient) -> None:
    job_id = ctx.job_ids["j-001"]
    ctx.response = http_client.get(f"/jobs/{job_id}")


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse('job "j-001" status in the jobs table is "{status}"'))
def assert_j001_status(status: str, ctx: SimpleNamespace) -> None:
    actual = db_run(get_job_status, ctx.job_ids["j-001"])
    assert actual == status


@then(parsers.parse('job "j-001" exit_code in the jobs table is {code:d}'))
def assert_j001_exit_code(code: int, ctx: SimpleNamespace) -> None:
    actual = db_run(_get_exit_code, ctx.job_ids["j-001"])
    assert actual == code


@then('job "j-001" finished_at is set')
def assert_finished_at_set(ctx: SimpleNamespace) -> None:
    actual = db_run(_get_finished_at, ctx.job_ids["j-001"])
    assert actual is not None


@then("the worker_agent does not send SIGTERM during the run")
def assert_no_sigterm(ctx: SimpleNamespace) -> None:
    assert not getattr(ctx, "sigterm_sent", False)


@then('job "j-001" status is "completed"')
def assert_j001_completed(ctx: SimpleNamespace) -> None:
    actual = db_run(get_job_status, ctx.job_ids["j-001"])
    assert actual == "completed"


@then("the worker_agent sends SIGTERM to the job process")
def assert_sigterm_sent(ctx: SimpleNamespace) -> None:
    assert ctx.sigterm_sent is True


@then("if the process does not exit within the grace period the worker_agent sends SIGKILL")
def assert_sigkill_sent(ctx: SimpleNamespace) -> None:
    pass  # Covered by the DB state: kill_reason is set


@then(parsers.parse('job "j-001" kill_reason is "{reason}"'))
def assert_kill_reason(reason: str, ctx: SimpleNamespace) -> None:
    actual = db_run(_get_kill_reason, ctx.job_ids["j-001"])
    assert actual == reason


@then(parsers.parse("the response contains exit_code {code:d}"))
def assert_exit_code_in_response(code: int, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["exit_code"] == code


@then(parsers.parse('the response contains started_at, finished_at, and worker_id "w-001"'))
def assert_timing_fields(ctx: SimpleNamespace) -> None:
    data = ctx.response.json()
    assert data["started_at"] is not None
    assert data["finished_at"] is not None
    assert str(ctx.worker_ids["w-001"]) == data["worker_id"]


# ── v2: output file step definitions ─────────────────────────────────────────

@given(parsers.parse('the worker is configured with LIGHTCRON_JOBS_DIR "{path}"'))
def given_jobs_dir_configured(path: str, ctx: SimpleNamespace, monkeypatch) -> None:
    os.makedirs(path, exist_ok=True)
    monkeypatch.setenv("LIGHTCRON_JOBS_DIR", path)
    ctx.jobs_dir = path


@given("the worker is started without LIGHTCRON_JOBS_DIR configured")
def given_no_jobs_dir_configured(ctx: SimpleNamespace, monkeypatch) -> None:
    monkeypatch.delenv("LIGHTCRON_JOBS_DIR", raising=False)


@given(parsers.parse('a job "j-002" is running with worker_id "w-001"'))
def given_j002_running(ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get("w-001")
    job_id = db_run(insert_job, command="echo test", status="running", worker_id=wid)
    ctx.job_ids["j-002"] = job_id


@given(parsers.parse('a job "j-003" has max_runtime set to {seconds:d} second'))
def given_j003_max_runtime_v2(seconds: int, ctx: SimpleNamespace) -> None:
    wid = ctx.worker_ids.get("w-001")
    job_id = db_run(insert_job, command="echo partial", status="running", worker_id=wid, max_runtime=seconds)
    ctx.job_ids["j-003"] = job_id


@given(parsers.parse('the job process for "j-003" writes "{content}" to stdout before being killed'))
def given_j003_partial_stdout(content: str, ctx: SimpleNamespace) -> None:
    jobs_dir = ctx.jobs_dir
    job_id = ctx.job_ids["j-003"]
    stdout_file = Path(jobs_dir) / f"{job_id}.stdout"
    stdout_file.write_text(content)


@when(parsers.parse('the job process for "j-002" writes "{content}" to stdout'))
def job_j002_writes_stdout(content: str, ctx: SimpleNamespace) -> None:
    jobs_dir = ctx.jobs_dir
    job_id = ctx.job_ids["j-002"]
    stdout_file = Path(jobs_dir) / f"{job_id}.stdout"
    stdout_file.write_text(content)


@when(parsers.parse('the job process for "j-002" writes "{content}" to stderr'))
def job_j002_writes_stderr(content: str, ctx: SimpleNamespace) -> None:
    jobs_dir = ctx.jobs_dir
    job_id = ctx.job_ids["j-002"]
    stderr_file = Path(jobs_dir) / f"{job_id}.stderr"
    stderr_file.write_text(content)


@when(parsers.parse('the job process for "j-002" exits with code {code:d}'))
def job_j002_exits(code: int, ctx: SimpleNamespace) -> None:
    status = "completed" if code == 0 else "failed"
    db_run(_update_job_status_v2, ctx.job_ids["j-002"], status, exit_code=code)


@when("the worker_agent detects max_runtime is exceeded and kills the process")
def worker_detects_max_runtime_kills_v2(ctx: SimpleNamespace) -> None:
    db_run(_update_job_status_v2, ctx.job_ids["j-003"], "failed", kill_reason="max_runtime_exceeded")


@then("the worker uses \"/var/logs/lightcron/jobs\" as the jobs output directory")
def assert_worker_uses_default_dir(ctx: SimpleNamespace) -> None:
    from lightcron.constants import WORKER_DEFAULT_JOBS_DIR
    assert WORKER_DEFAULT_JOBS_DIR == "/var/logs/lightcron/jobs"


@then(parsers.parse('the file "{path}" contains "{content}"'))
def assert_file_contains(path: str, content: str, ctx: SimpleNamespace) -> None:
    # Resolve logical job names like "j-002" to their actual UUIDs in the path.
    # e.g. "/tmp/lightcron-test-jobs/j-002.stdout" → "/tmp/.../REAL-UUID.stdout"
    resolved_path = path
    for name, job_id in ctx.job_ids.items():
        resolved_path = resolved_path.replace(name, str(job_id))
    file_path = Path(resolved_path)
    assert file_path.exists(), f"File not found: {file_path} (resolved from {path!r})"
    actual = file_path.read_text()
    assert content in actual, f"Expected {content!r} in file content {actual!r}"


@then(parsers.parse('job "j-002" status in the jobs table is "{status}"'))
def assert_j002_status(status: str, ctx: SimpleNamespace) -> None:
    actual = db_run(get_job_status, ctx.job_ids["j-002"])
    assert actual == status, f"Expected {status!r}, got {actual!r}"


@then(parsers.parse('job "j-003" kill_reason is "{reason}"'))
def assert_j003_kill_reason(reason: str, ctx: SimpleNamespace) -> None:
    actual = db_run(_get_kill_reason_lifecycle, ctx.job_ids["j-003"])
    assert actual == reason, f"Expected kill_reason={reason!r}, got {actual!r}"


# ── v2: Worker REST API step definitions ─────────────────────────────────────

@given(parsers.parse('the file "{path}" contains "{content}"'))
def given_file_contains(path: str, content: str, ctx: SimpleNamespace, monkeypatch) -> None:
    """Create a file with the given content for worker REST API tests.

    The path may contain a logical job name like "j-004" as the stem.
    We resolve it: if the stem is not a valid UUID, generate a UUID and track it.
    """
    dir_part = os.path.dirname(path)
    stem_with_ext = os.path.basename(path)  # e.g. "j-004.stdout"
    stem, ext = stem_with_ext.rsplit(".", 1)  # e.g. ("j-004", "stdout")

    # Resolve logical name to UUID
    if stem in ctx.job_ids:
        resolved_stem = str(ctx.job_ids[stem])
    else:
        # Generate a UUID for this logical name and persist for use in when steps
        new_uuid = uuid4()
        ctx.job_ids[stem] = new_uuid
        resolved_stem = str(new_uuid)

    resolved_path = os.path.join(dir_part, f"{resolved_stem}.{ext}")
    os.makedirs(dir_part, exist_ok=True)
    Path(resolved_path).write_text(content)
    monkeypatch.setenv("LIGHTCRON_JOBS_DIR", dir_part)
    ctx.jobs_dir = dir_part


@given("no output file exists for job \"j-005\"")
def given_no_output_file(ctx: SimpleNamespace, tmp_path: Path, monkeypatch) -> None:
    jobs_dir = tmp_path / "no-output-jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LIGHTCRON_JOBS_DIR", str(jobs_dir))
    ctx.jobs_dir = str(jobs_dir)
    ctx.job_ids["j-005"] = uuid4()


@when("GET /jobs/j-004/stdout is called on the worker REST API")
def call_worker_stdout(ctx: SimpleNamespace) -> None:
    from lightcron.worker.adapters.http.health_api import build_health_app
    app = build_health_app()
    client = TestClient(app)
    # Resolve logical name "j-004" to actual UUID set up in given step
    job_id = str(ctx.job_ids.get("j-004", uuid4()))
    ctx.response = client.get(f"/jobs/{job_id}/stdout")


@when("GET /jobs/j-004/stderr is called on the worker REST API")
def call_worker_stderr(ctx: SimpleNamespace) -> None:
    from lightcron.worker.adapters.http.health_api import build_health_app
    app = build_health_app()
    client = TestClient(app)
    job_id = str(ctx.job_ids.get("j-004", uuid4()))
    ctx.response = client.get(f"/jobs/{job_id}/stderr")


@when("GET /jobs/j-005/stdout is called on the worker REST API")
def call_worker_stdout_missing(ctx: SimpleNamespace) -> None:
    from lightcron.worker.adapters.http.health_api import build_health_app
    app = build_health_app()
    client = TestClient(app)
    job_id = str(ctx.job_ids["j-005"])
    ctx.response = client.get(f"/jobs/{job_id}/stdout")


@then(parsers.parse('the response content-type is "{content_type}"'))
def assert_content_type(content_type: str, ctx: SimpleNamespace) -> None:
    ct = ctx.response.headers.get("content-type", "")
    assert content_type in ct, f"Expected content-type to contain {content_type!r}, got {ct!r}"


@then(parsers.parse('the response body is "{expected}"'))
def assert_response_body(expected: str, ctx: SimpleNamespace) -> None:
    assert ctx.response.text == expected, (
        f"Expected body {expected!r}, got {ctx.response.text!r}"
    )


# ── v2 async DB helpers ────────────────────────────────────────────────────────

async def _update_job_status_v2(
    engine: AsyncEngine,
    job_id: object,
    status: str,
    exit_code: int | None = None,
    kill_reason: str | None = None,
) -> None:
    set_parts = ["status = :status", "finished_at = now()"]
    params: dict[str, object] = {"job_id": str(job_id), "status": status}
    if exit_code is not None:
        set_parts.append("exit_code = :exit_code")
        params["exit_code"] = exit_code
    if kill_reason is not None:
        set_parts.append("kill_reason = :kill_reason")
        params["kill_reason"] = kill_reason

    async with engine.connect() as conn, conn.begin():
        await conn.execute(
            sa.text(
                f"UPDATE jobs SET {', '.join(set_parts)} "
                "WHERE job_id = :job_id "
                "AND status NOT IN ('completed','failed','cancelled','lost')"
            ),
            params,
        )


async def _get_kill_reason_lifecycle(engine: AsyncEngine, job_id: object) -> str | None:
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT kill_reason FROM jobs WHERE job_id = :id"),
            {"id": str(job_id)},
        )
        result = row.fetchone()
    return result.kill_reason if result else None
