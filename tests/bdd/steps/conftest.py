"""Shared step definitions reused across multiple feature files."""

from __future__ import annotations

import pytest
from pytest_bdd import given


@given("the Lightcron scheduler is running")
def scheduler_running(http_client: object) -> None:
    """The http_client fixture ensures the scheduler app is up."""


@given("no jobs exist")
def no_jobs(ctx: object) -> None:
    """clean_tables autouse fixture already cleared jobs between scenarios."""


@given("the worker_status table is empty")
def worker_status_empty(ctx: object) -> None:
    """clean_tables autouse fixture already cleared worker_status."""


@given("no workers are registered")
def no_workers(ctx: object) -> None:
    """clean_tables autouse fixture already cleared worker_status."""
