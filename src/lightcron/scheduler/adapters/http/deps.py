"""FastAPI dependency injection helpers."""

from __future__ import annotations

from fastapi import Request

from lightcron.scheduler.domain.jobs.services.job_service import JobService
from lightcron.scheduler.domain.workers.services.worker_service import WorkerService


def get_job_service(request: Request) -> JobService:
    return request.app.state.job_service  # type: ignore[no-any-return]


def get_worker_service(request: Request) -> WorkerService:
    return request.app.state.worker_service  # type: ignore[no-any-return]
