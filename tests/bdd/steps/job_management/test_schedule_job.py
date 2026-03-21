"""BDD step definitions for schedule-job.feature (J001)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import AsyncClient
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.bdd.conftest import insert_job

FEATURE = "../../../../specs/features/job-management/schedule-job.feature"


@scenario(FEATURE, "Successfully schedule a minimal job")
def test_schedule_minimal_job() -> None: ...

@scenario(FEATURE, "Successfully schedule a job with resource limits")
def test_schedule_with_limits() -> None: ...

@scenario(FEATURE, "Successfully schedule a job with dependencies")
def test_schedule_with_deps() -> None: ...

@scenario(FEATURE, "Reject a job with a start_time in the past")
def test_reject_past_start_time() -> None: ...

@scenario(FEATURE, "Reject a job with a missing required field", example_converters={"field": str})
def test_reject_missing_field() -> None: ...

@scenario(FEATURE, "Reject a job with a depends_on referencing an unknown job_id")
def test_reject_unknown_dep() -> None: ...

@scenario(FEATURE, "Reject a job with max_runtime set to zero or negative")
def test_reject_invalid_max_runtime() -> None: ...

@scenario(FEATURE, "Reject a malformed JSON request body")
def test_reject_malformed_json() -> None: ...


# ── Givens ────────────────────────────────────────────────────────────────────

@given(parsers.parse('a job "{name}" already exists'))
async def given_job_exists(name: str, ctx: SimpleNamespace, db_engine: AsyncEngine) -> None:
    job_id = await insert_job(db_engine, command="echo placeholder", status="pending")
    ctx.job_ids[name] = job_id


# ── Whens ─────────────────────────────────────────────────────────────────────

@when("a job_submitter submits a POST /jobs request with:", target_fixture="response")
async def submit_job_with_table(
    ctx: SimpleNamespace,
    http_client: AsyncClient,
    step: object,
) -> object:
    rows: dict[str, str] = {r["field"]: r["value"] for r in step.datatable.rows[1:]}  # type: ignore[attr-defined]

    start_time_str = rows.get("start_time", "")
    if "from now" in start_time_str:
        seconds = int(start_time_str.split()[0])
        start_time = (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
    elif "ago" in start_time_str:
        seconds = int(start_time_str.split()[0])
        start_time = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()
    else:
        start_time = start_time_str

    payload: dict[str, object] = {
        "command": rows.get("command", "echo test"),
        "start_time": start_time,
    }
    if "max_runtime" in rows:
        payload["max_runtime"] = int(rows["max_runtime"])
    if "max_memory" in rows:
        payload["max_memory"] = int(rows["max_memory"])
    if "depends_on" in rows:
        dep_names = json.loads(rows["depends_on"])
        payload["depends_on"] = [str(ctx.job_ids[n]) for n in dep_names]

    resp = await http_client.post("/jobs", json=payload)
    ctx.response = resp
    return resp


@when(parsers.parse('a job_submitter submits a POST /jobs request missing the "{field}" field'))
async def submit_job_missing_field(
    field: str, ctx: SimpleNamespace, http_client: AsyncClient
) -> None:
    future = (datetime.now(UTC) + timedelta(seconds=60)).isoformat()
    payload: dict[str, object] = {"command": "echo test", "start_time": future}
    payload.pop(field, None)
    if field == "command":
        payload.pop("command", None)
    elif field == "start_time":
        payload.pop("start_time", None)
    ctx.response = await http_client.post("/jobs", json=payload)


@when("a job_submitter submits a POST /jobs request with depends_on containing \"j-does-not-exist\"")
async def submit_job_unknown_dep(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    future = (datetime.now(UTC) + timedelta(seconds=60)).isoformat()
    ctx.response = await http_client.post("/jobs", json={
        "command": "echo test",
        "start_time": future,
        "depends_on": ["00000000-0000-0000-0000-000000000000"],
    })


@when("a job_submitter submits a POST /jobs request with max_runtime -1")
async def submit_job_invalid_runtime(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    future = (datetime.now(UTC) + timedelta(seconds=60)).isoformat()
    ctx.response = await http_client.post("/jobs", json={
        "command": "echo test",
        "start_time": future,
        "max_runtime": -1,
    })


@when("a job_submitter sends a POST /jobs request with malformed JSON")
async def submit_malformed_json(ctx: SimpleNamespace, http_client: AsyncClient) -> None:
    ctx.response = await http_client.post(
        "/jobs",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )


# ── Thens ─────────────────────────────────────────────────────────────────────

@then(parsers.parse("the response status is {code:d}"))
def assert_status(code: int, ctx: SimpleNamespace) -> None:
    assert ctx.response.status_code == code, (
        f"Expected {code}, got {ctx.response.status_code}: {ctx.response.text}"
    )


@then("the response contains a unique job_id")
def assert_has_job_id(ctx: SimpleNamespace) -> None:
    data = ctx.response.json()
    assert "job_id" in data
    UUID(data["job_id"])  # raises if not valid UUID


@then(parsers.parse('the job status is "{status}"'))
def assert_job_status(status: str, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["status"] == status


@then("the job has no max_runtime or max_memory set")
def assert_no_limits(ctx: SimpleNamespace) -> None:
    data = ctx.response.json()
    assert data["max_runtime"] is None
    assert data["max_memory"] is None


@then(parsers.parse("the job max_runtime is {value:d}"))
def assert_max_runtime(value: int, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["max_runtime"] == value


@then(parsers.parse("the job max_memory is {value:d}"))
def assert_max_memory(value: int, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["max_memory"] == value


@then(parsers.parse('the job depends_on includes "{name}"'))
def assert_depends_on(name: str, ctx: SimpleNamespace) -> None:
    dep_ids = ctx.response.json()["depends_on"]
    expected = str(ctx.job_ids[name])
    assert expected in dep_ids


@then(parsers.parse('the response contains a validation error for "{field}"'))
def assert_validation_error_field(field: str, ctx: SimpleNamespace) -> None:
    body = ctx.response.text
    assert field in body, f"Expected '{field}' in error response: {body}"


@then(parsers.parse('the response identifies "{field}" as missing'))
def assert_missing_field(field: str, ctx: SimpleNamespace) -> None:
    body = ctx.response.text
    assert field in body, f"Expected '{field}' mentioned in: {body}"


@then('the response identifies "j-does-not-exist" as an unknown dependency')
def assert_unknown_dep_error(ctx: SimpleNamespace) -> None:
    body = ctx.response.text
    assert "depends_on" in body or "unknown" in body.lower(), f"Unexpected: {body}"
