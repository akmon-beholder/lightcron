"""Shared BDD test infrastructure.

Provides:
  - db_engine:     Real PostgreSQL engine for integration tests
  - clean_tables:  Truncates jobs + worker_status between each scenario
  - ctx:           Per-scenario mutable state dict (shared between steps)
  - fake_health:   FakeWorkerHealthClient with configurable responses
  - scheduler_app: Bare FastAPI app wired with test services (no background loops)
  - http_client:   httpx.AsyncClient pointing at the scheduler app
  - worker_db/job_db: Raw DB adapters for worker agent tests
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from uuid import UUID

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://lightcron:lightcron@localhost:5432/lightcron",
)


# ── Database ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(TEST_DB_URL)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables(db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    yield
    async with db_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(sa.text("DELETE FROM jobs"))
            await conn.execute(sa.text("DELETE FROM worker_status"))


# ── Per-scenario state ────────────────────────────────────────────────────────

@pytest.fixture
def ctx() -> SimpleNamespace:
    """Mutable namespace for sharing state between steps in a scenario."""
    return SimpleNamespace(
        response=None,
        job_ids={},      # logical name → UUID
        worker_ids={},   # logical name → UUID
    )


# ── Fake adapters ─────────────────────────────────────────────────────────────

class FakeWorkerHealthClient:
    """Fake WorkerHealthClient with configurable per-worker responses."""

    def __init__(self) -> None:
        self.responses: dict[str, bool] = {}  # worker_id str → True/False
        self.probed: list[str] = []            # worker_id strings that were probed

    def set_healthy(self, worker_id: str) -> None:
        self.responses[worker_id] = True

    def set_unhealthy(self, worker_id: str) -> None:
        self.responses[worker_id] = False

    async def check_health(self, worker_id: UUID, address: str) -> bool:
        wid = str(worker_id)
        self.probed.append(wid)
        return self.responses.get(wid, True)


@pytest.fixture
def fake_health() -> FakeWorkerHealthClient:
    return FakeWorkerHealthClient()


# ── Scheduler HTTP test app ────────────────────────────────────────────────────

@pytest.fixture
async def scheduler_app(db_engine: AsyncEngine, fake_health: FakeWorkerHealthClient):  # type: ignore[return]
    """A bare FastAPI scheduler app with test services injected (no background loops)."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository
    from lightcron.scheduler.adapters.db.worker_repo import PostgresWorkerRepository
    from lightcron.scheduler.adapters.http.jobs_router import router as jobs_router
    from lightcron.scheduler.adapters.http.schemas import HealthResponse
    from lightcron.scheduler.adapters.http.workers_router import router as workers_router
    from lightcron.scheduler.domain.jobs.services.job_service import JobService
    from lightcron.scheduler.domain.workers.services.worker_service import WorkerService
    from lightcron.shared.ports.determinism.adapters import SystemTimeAdapter, SystemUUIDAdapter

    app = FastAPI(title="Lightcron Scheduler (test)")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    job_repo = PostgresJobRepository(db_engine)
    worker_repo = PostgresWorkerRepository(db_engine)

    app.state.job_service = JobService(job_repo, SystemTimeAdapter(), SystemUUIDAdapter())
    app.state.worker_service = WorkerService(worker_repo)
    app.state.job_repo = job_repo
    app.state.worker_repo = worker_repo
    app.state.fake_health = fake_health

    app.include_router(jobs_router)
    app.include_router(workers_router)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


@pytest.fixture
async def http_client(scheduler_app) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[return]
    async with AsyncClient(
        transport=ASGITransport(app=scheduler_app), base_url="http://test"
    ) as client:
        yield client


# ── Raw DB helpers (worker agent tests) ───────────────────────────────────────

@pytest.fixture
def job_db(db_engine: AsyncEngine):  # type: ignore[return]
    from lightcron.worker.adapters.db.job_db import AsyncpgJobDB
    return AsyncpgJobDB(db_engine)


@pytest.fixture
def worker_status_db(db_engine: AsyncEngine):  # type: ignore[return]
    from lightcron.worker.adapters.db.worker_status_db import AsyncpgWorkerStatusDB
    return AsyncpgWorkerStatusDB(db_engine)


# ── DB helper functions ────────────────────────────────────────────────────────

async def insert_worker(
    engine: AsyncEngine,
    hostname: str = "worker-01",
    status: str = "online",
    last_seen_offset_seconds: int = 0,
) -> UUID:
    """Insert a worker_status row and return the worker_id."""
    async with engine.connect() as conn:
        async with conn.begin():
            row = await conn.execute(
                sa.text("""
                    INSERT INTO worker_status (hostname, status, last_seen, registered_at)
                    VALUES (:hostname, :status,
                            now() - :offset * interval '1 second',
                            now() - :offset * interval '1 second')
                    RETURNING worker_id
                """),
                {"hostname": hostname, "status": status, "offset": last_seen_offset_seconds},
            )
            return UUID(str(row.scalar_one()))


async def insert_job(
    engine: AsyncEngine,
    *,
    command: str = "echo test",
    start_time_offset_seconds: int = -10,  # default: 10s in the past (already ready-eligible)
    status: str = "pending",
    worker_id: UUID | None = None,
    exit_code: int | None = None,
    depends_on: list[UUID] | None = None,
    max_runtime: int | None = None,
    max_memory: int | None = None,
    kill_reason: str | None = None,
) -> UUID:
    """Insert a job row and return the job_id."""
    async with engine.connect() as conn:
        async with conn.begin():
            row = await conn.execute(
                sa.text("""
                    INSERT INTO jobs (
                        command, start_time, status, worker_id,
                        exit_code, depends_on, max_runtime, max_memory, kill_reason,
                        started_at, finished_at
                    )
                    VALUES (
                        :command,
                        now() + :offset * interval '1 second',
                        :status, :worker_id,
                        :exit_code, :depends_on, :max_runtime, :max_memory, :kill_reason,
                        CASE WHEN :status IN ('running','completed','failed','lost','cancelled') THEN now() - interval '5 seconds' ELSE NULL END,
                        CASE WHEN :status IN ('completed','failed') THEN now() ELSE NULL END
                    )
                    RETURNING job_id
                """),
                {
                    "command": command,
                    "offset": start_time_offset_seconds,
                    "status": status,
                    "worker_id": str(worker_id) if worker_id else None,
                    "exit_code": exit_code,
                    "depends_on": [str(d) for d in (depends_on or [])],
                    "max_runtime": max_runtime,
                    "max_memory": max_memory,
                    "kill_reason": kill_reason,
                },
            )
            return UUID(str(row.scalar_one()))


async def get_job_status(engine: AsyncEngine, job_id: UUID) -> str | None:
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT status FROM jobs WHERE job_id = :id"),
            {"id": str(job_id)},
        )
        result = row.fetchone()
    return result.status if result else None


async def get_worker_status(engine: AsyncEngine, worker_id: UUID) -> str | None:
    async with engine.connect() as conn:
        row = await conn.execute(
            sa.text("SELECT status FROM worker_status WHERE worker_id = :id"),
            {"id": str(worker_id)},
        )
        result = row.fetchone()
    return result.status if result else None
