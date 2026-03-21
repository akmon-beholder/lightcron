"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from lightcron.scheduler.domain.jobs.services.job_service import JobService
from lightcron.scheduler.domain.workers.services.worker_service import WorkerService


def _get_job_service(request: Request) -> JobService:
    return request.app.state.job_service  # type: ignore[no-any-return]


def _get_worker_service(request: Request) -> WorkerService:
    return request.app.state.worker_service  # type: ignore[no-any-return]


get_job_service = Annotated[JobService, Depends(_get_job_service)]
get_worker_service = Annotated[WorkerService, Depends(_get_worker_service)]
