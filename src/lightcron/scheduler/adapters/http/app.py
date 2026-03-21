"""Scheduler FastAPI application."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lightcron.scheduler.adapters.http.jobs_router import router as jobs_router
from lightcron.scheduler.adapters.http.schemas import HealthResponse
from lightcron.scheduler.adapters.http.workers_router import router as workers_router


def _build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository
        from lightcron.scheduler.adapters.db.worker_repo import PostgresWorkerRepository
        from lightcron.scheduler.adapters.health.worker_health_client import (
            HttpxWorkerHealthClient,
        )
        from lightcron.scheduler.domain.jobs.services.dispatch_service import DispatchService
        from lightcron.scheduler.domain.jobs.services.job_service import JobService
        from lightcron.scheduler.domain.workers.services.worker_service import WorkerService
        from lightcron.shared.ports.determinism.adapters import (
            SystemTimeAdapter,
            SystemUUIDAdapter,
        )
        from sqlalchemy.ext.asyncio import create_async_engine

        pgbouncer_url = os.environ["PGBOUNCER_URL"]
        engine = create_async_engine(pgbouncer_url)

        job_repo = PostgresJobRepository(engine)
        worker_repo = PostgresWorkerRepository(engine)
        health_client = HttpxWorkerHealthClient()
        clock = SystemTimeAdapter()
        ids = SystemUUIDAdapter()

        application.state.job_service = JobService(job_repo, clock, ids)
        application.state.worker_service = WorkerService(worker_repo)

        dispatch_service = DispatchService(job_repo, worker_repo, health_client, clock)
        loop_tasks = [
            asyncio.create_task(dispatch_service.run_ready_transition_loop()),
            asyncio.create_task(dispatch_service.run_health_check_loop()),
        ]

        try:
            yield
        finally:
            for task in loop_tasks:
                task.cancel()
            await asyncio.gather(*loop_tasks, return_exceptions=True)
            await engine.dispose()

    app = FastAPI(title="Lightcron Scheduler", version="0.1.0", lifespan=lifespan)

    ui_origin = os.environ.get("LIGHTCRON_UI_ORIGIN", "http://localhost:5173")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ui_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    app.include_router(jobs_router)
    app.include_router(workers_router)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = _build_app()
