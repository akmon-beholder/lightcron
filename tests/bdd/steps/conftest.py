"""Shared step definitions reused across multiple feature files.

In pytest-bdd 8, steps defined in a test_*.py file are scoped to that file.
Steps that are referenced by more than one feature must live here.

All step functions are synchronous — pytest-bdd 8 calls them via a sync
call_fixture_func mechanism. Use db_run() from conftest for any async DB work.
"""

from __future__ import annotations

from types import SimpleNamespace

import sqlalchemy as sa
from pytest_bdd import given, parsers, then

from tests.bdd.conftest import db_run

# ── Background steps (used by every feature) ──────────────────────────────

@given("the Lightcron scheduler is running")
def scheduler_running(http_client: object) -> None:
    """The http_client fixture ensures the scheduler app is wired up."""


@given("no jobs exist")
def no_jobs(ctx: object) -> None:
    """clean_tables autouse fixture already cleared jobs between scenarios."""


@given("the worker_status table is empty")
def worker_status_empty(ctx: object) -> None:
    """clean_tables autouse fixture already cleared worker_status."""


@given("no workers are registered")
def no_workers(ctx: object) -> None:
    """clean_tables autouse fixture already cleared worker_status."""


# ── HTTP response status (used by job-management, cancel, worker-registration) ─

@then(parsers.parse("the response status is {code:d}"))
def assert_response_status(code: int, ctx: SimpleNamespace) -> None:
    assert ctx.response.status_code == code, (
        f"Expected HTTP {code}, got {ctx.response.status_code}: {ctx.response.text}"
    )


# ── Response body assertions shared across features ───────────────────────

@then(parsers.parse('the response contains status "{status}"'))
def assert_response_contains_status(status: str, ctx: SimpleNamespace) -> None:
    assert ctx.response.json()["status"] == status


# ── Timestamp assertions shared across features ────────────────────────────

@then("last_seen is set to approximately now")
def assert_last_seen_set_now(ctx: SimpleNamespace) -> None:
    """Verify the most recently touched worker_status row has a fresh last_seen."""
    async def _query(engine):
        async with engine.connect() as conn:
            row = await conn.execute(
                sa.text(
                    "SELECT EXTRACT(EPOCH FROM (now() - last_seen)) AS age "
                    "FROM worker_status ORDER BY last_seen DESC LIMIT 1"
                )
            )
            return row.fetchone()

    result = db_run(_query)
    assert result is not None and abs(float(result.age)) < 5, (
        f"last_seen is {result.age:.1f}s old, expected < 5s"
    )


@then("last_seen is updated to approximately now")
def assert_last_seen_updated_now(ctx: SimpleNamespace) -> None:
    """Verify the most recently touched worker_status row has a fresh last_seen."""
    async def _query(engine):
        async with engine.connect() as conn:
            row = await conn.execute(
                sa.text(
                    "SELECT EXTRACT(EPOCH FROM (now() - last_seen)) AS age "
                    "FROM worker_status ORDER BY last_seen DESC LIMIT 1"
                )
            )
            return row.fetchone()

    result = db_run(_query)
    assert result is not None and abs(float(result.age)) < 5, (
        f"last_seen is {result.age:.1f}s old, expected < 5s"
    )
