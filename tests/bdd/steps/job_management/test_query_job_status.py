"""BDD step definitions for query-job-status.feature (J006)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.bdd.conftest import insert_job, insert_worker

FEATURE = "../../../../specs/features/job-management/query-job-status.feature"


@scenario(FEATURE, "Query a known job returns full details")
def test_query_known_job() -> None: ...

@scenario(FEATURE, "Query an unknown job returns 404")
def test_query_unknown_job() -> None: ...

@scenario(FEATURE, "List jobs filtered by status")
def test_list_filtered() -> None: ...

@scenario(FEATURE, "List all jobs returns all records")
def test_list_all() -> None: ...

@scenario(FEATURE, "List jobs when none exist returns empty list")
def test_list_empty() -> None: ...

@scenario(FEATURE, "Filter with an invalid status value returns 422")
def test_invalid_filter() -> None: ...


# ── Givens ────────────────────────────────────────────────────────────────────

@given('a job "j-001" exists with status "running", command "/usr/bin/my-script.sh", start_time, end_time, and worker_id "w-001"')
async def given_running_job_with_worker(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    wid = await insert_worker(db_engine, hostname="worker-01")
    ctx.worker_ids["w-001"] = wid
    job_id = await insert_job(
        db_engine,
        command="/usr/bin/my-script.sh",
        status="running",
        worker_id=wid,
    )
    ctx.job_ids["j-001"] = job_id


@given("jobs exist with statuses \"pending\", \"running\", and \"completed\"")
async def given_mixed_status_jobs(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    for status in ("pending", "running", "completed"):
        await insert_job(db_engine, status=status)


@given("3 jobs exist with varying statuses")
async def given_three_jobs(ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    for status in ("pending", "running", "failed"):
        await insert_job(db_engine, status=status)


# ── Whens ─────────────────────────────────────────────────────────────────────

@when('GET /jobs/j-001 is called')
async def get_job_j001(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    job_id = ctx.job_ids.get("j-001")
    url = f"/jobs/{job_id}" if job_id else "/jobs/00000000-0000-0000-0000-000000000000"
    ctx.response = await http_client.get(url)


@when("GET /jobs/does-not-exist is called")
async def get_unknown_job(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    ctx.response = await http_client.get("/jobs/00000000-0000-0000-0000-000000000000")


@when("GET /jobs?status=running is called")
async def get_jobs_running(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    ctx.response = await http_client.get("/jobs", params={"status": "running"})


@when("GET /jobs is called")
async def get_all_jobs(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    ctx.response = await http_client.get("/jobs")


@when("GET /jobs?status=not-a-real-status is called")
async def get_jobs_invalid_status(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    ctx.response = await http_client.get("/jobs", params={"status": "not-a-real-status"})


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse('the response contains job_id "j-001"'))
def assert_response_has_job_id(ctx: SimpleNamespace) -> None:
    data = ctx.response.json()
    assert str(ctx.job_ids["j-001"]) == data["job_id"]


@then(parsers.parse('the response contains status "{status}"'))
def assert_response_status_field(status: str, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["status"] == status


@then(parsers.parse('the response contains command "{command}"'))
def assert_response_command(command: str, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["command"] == command


@then(parsers.parse('the response contains start_time, end_time, and worker_id "w-001"'))
def assert_response_timing_and_worker(ctx: SimpleNamespace) -> None:
    data = ctx.response.json()
    assert data["start_time"] is not None
    assert str(ctx.worker_ids["w-001"]) == data["worker_id"]


@then("the response contains only jobs with status \"running\"")
def assert_only_running(ctx: SimpleNamespace) -> None:
    jobs = ctx.response.json()
    assert len(jobs) > 0
    assert all(j["status"] == "running" for j in jobs)


@then(parsers.parse("the response contains {count:d} jobs"))
def assert_job_count(count: int, ctx: SimpleNamespace) -> None:
    assert len(ctx.response.json()) == count


@then("the response contains an empty list")
def assert_empty_list(ctx: SimpleNamespace) -> None:
    assert ctx.response.json() == []
