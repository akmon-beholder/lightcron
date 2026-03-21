"""FastAPI router for /jobs endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from lightcron.scheduler.adapters.http.deps import get_job_service
from lightcron.scheduler.adapters.http.schemas import (
    CancelJobResponse,
    JobResponse,
    ScheduleJobRequest,
)
from lightcron.scheduler.domain.jobs.entities import JobStatus
from lightcron.scheduler.domain.jobs.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_to_response(job: object) -> JobResponse:
    return JobResponse.model_validate(job)


@router.post("", status_code=201, response_model=JobResponse)
async def schedule_job(
    body: ScheduleJobRequest,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        job = await service.schedule_job(
            command=body.command,
            start_time=body.start_time,
            depends_on=body.depends_on,
            max_runtime=body.max_runtime,
            max_memory=body.max_memory,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _job_to_response(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: str | None = Query(default=None),
    service: JobService = Depends(get_job_service),
) -> list[JobResponse]:
    parsed_status: JobStatus | None = None
    if status is not None:
        try:
            parsed_status = JobStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=[{"field": "status", "msg": f"'{status}' is not a valid job status"}],
            )
    jobs = await service.list_jobs(parsed_status)
    return [_job_to_response(j) for j in jobs]


@router.post("/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_job(
    job_id: UUID,
    service: JobService = Depends(get_job_service),
) -> CancelJobResponse:
    try:
        job = await service.cancel_job(job_id)
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="Job is in a terminal state and cannot be cancelled",
        )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return CancelJobResponse(job_id=job.job_id, status=job.status)
