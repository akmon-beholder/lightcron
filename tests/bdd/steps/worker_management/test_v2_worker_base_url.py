"""BDD step definitions and scenario tests for v2 worker base_url and job detail ACs.

Covers:
  AC-V2-B04: GET /jobs/{job_id} returns peak_memory_mb
  AC-V2-B05: GET /jobs list does NOT return peak_memory_mb
  AC-V2-B06: GET /workers returns base_url when set
  AC-V2-B07: GET /workers returns base_url null when not configured
  AC-V2-B14: Worker registers base_url at startup
  AC-V2-B15: Worker re-registration preserves/updates base_url

All step functions are synchronous (pytest-bdd 8 requirement).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
import sqlalchemy as sa
from pytest_bdd import given, parsers, scenario, then, when
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.testclient import TestClient

from tests.bdd.conftest import db_run, insert_job, insert_worker


# ── Inline pytest tests for AC-V2-B04 through AC-V2-B07 ──────────────────────
# (These don't map to existing feature files; tested directly)


def test_get_job_detail_returns_peak_memory_mb(http_client: TestClient, ctx: SimpleNamespace) -> None:
    """AC-V2-B04: GET /jobs/{job_id} returns peak_memory_mb."""
    job_id = db_run(insert_job_with_peak_memory, peak_memory_mb=128.5)

    resp = http_client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "peak_memory_mb" in data, f"peak_memory_mb missing from response: {list(data.keys())}"
    assert data["peak_memory_mb"] == pytest.approx(128.5)


def test_list_jobs_omits_peak_memory_mb(http_client: TestClient, ctx: SimpleNamespace) -> None:
    """AC-V2-B05: GET /jobs list items do not contain peak_memory_mb key."""
    db_run(insert_job_with_peak_memory, peak_memory_mb=42.0)

    resp = http_client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) >= 1
    for job in jobs:
        assert "peak_memory_mb" not in job, (
            f"peak_memory_mb should not be in list response but was found: {job}"
        )


def test_get_workers_returns_base_url(http_client: TestClient, ctx: SimpleNamespace) -> None:
    """AC-V2-B06: GET /workers includes base_url when worker was registered with one."""
    db_run(insert_worker_with_base_url, hostname="worker-base-01", base_url="http://worker-01:8001")

    resp = http_client.get("/workers")
    assert resp.status_code == 200
    workers = resp.json()
    assert len(workers) >= 1
    found = next((w for w in workers if w["hostname"] == "worker-base-01"), None)
    assert found is not None, "worker-base-01 not found in /workers response"
    assert found["base_url"] == "http://worker-01:8001", (
        f"Expected base_url='http://worker-01:8001', got {found['base_url']!r}"
    )


def test_get_workers_returns_base_url_null_when_not_configured(
    http_client: TestClient, ctx: SimpleNamespace
) -> None:
    """AC-V2-B07: GET /workers base_url is null when not configured."""
    db_run(insert_worker_with_base_url, hostname="worker-no-url-01", base_url=None)

    resp = http_client.get("/workers")
    assert resp.status_code == 200
    workers = resp.json()
    found = next((w for w in workers if w["hostname"] == "worker-no-url-01"), None)
    assert found is not None, "worker-no-url-01 not found in /workers response"
    assert found["base_url"] is None, f"Expected base_url=null, got {found['base_url']!r}"


def test_worker_registers_base_url_at_startup(ctx: SimpleNamespace) -> None:
    """AC-V2-B14: Worker startup with LIGHTCRON_WORKER_BASE_URL registers that URL."""
    base_url = "http://worker-startup:8001"
    wid = db_run(_upsert_worker_with_base_url, hostname="startup-worker", base_url=base_url)

    result = db_run(_query_base_url_by_worker_id, wid)
    assert result == base_url, f"Expected base_url={base_url!r}, got {result!r}"


def test_worker_reregistration_updates_base_url(ctx: SimpleNamespace) -> None:
    """AC-V2-B15: Re-registration with new base_url updates the value; worker_id preserved."""
    hostname = "reregister-worker"
    first_wid = db_run(_upsert_worker_with_base_url, hostname=hostname, base_url="http://old-url:8001")

    # Re-register with new base_url
    second_wid = db_run(_upsert_worker_with_base_url, hostname=hostname, base_url="http://new-url:8001")

    # worker_id must be preserved
    assert first_wid == second_wid, (
        f"worker_id changed on re-registration: {first_wid} → {second_wid}"
    )

    # base_url must be updated
    result = db_run(_query_base_url_by_worker_id, second_wid)
    assert result == "http://new-url:8001", f"Expected updated base_url, got {result!r}"


# ── Async DB helpers ──────────────────────────────────────────────────────────

async def insert_job_with_peak_memory(engine: AsyncEngine, peak_memory_mb: float) -> UUID:
    """Insert a job with a given peak_memory_mb value and return its job_id."""
    async with engine.connect() as conn, conn.begin():
        row = await conn.execute(
            sa.text("""
                INSERT INTO jobs (
                    command, start_time, status, started_at, finished_at,
                    peak_memory_mb
                )
                VALUES (
                    'echo test',
                    now() - interval '1 minute',
                    CAST('completed' AS job_status),
                    now() - interval '5 seconds',
                    now(),
                    :peak_memory_mb
                )
                RETURNING job_id
            """),
            {"peak_memory_mb": peak_memory_mb},
        )
        return UUID(str(row.scalar_one()))


async def insert_worker_with_base_url(
    engine: AsyncEngine,
    hostname: str,
    base_url: str | None,
) -> UUID:
    """Insert a worker_status row with base_url and return worker_id."""
    async with engine.connect() as conn, conn.begin():
        row = await conn.execute(
            sa.text("""
                INSERT INTO worker_status (hostname, status, last_seen, registered_at, base_url)
                VALUES (:hostname, 'online', now(), now(), :base_url)
                RETURNING worker_id
            """),
            {"hostname": hostname, "base_url": base_url},
        )
        return UUID(str(row.scalar_one()))


async def _upsert_worker_with_base_url(
    engine: AsyncEngine,
    hostname: str,
    base_url: str | None,
) -> UUID:
    """Upsert worker using the actual adapter to test the registration path."""
    from lightcron.worker.adapters.db.worker_status_db import AsyncpgWorkerStatusDB
    db = AsyncpgWorkerStatusDB(engine)
    return await db.upsert_worker(hostname, base_url=base_url)


async def _query_base_url_by_worker_id(engine: AsyncEngine, worker_id: UUID) -> str | None:
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT base_url FROM worker_status WHERE worker_id = :id"),
            {"id": str(worker_id)},
        )
        result = row.fetchone()
    return result.base_url if result else None
