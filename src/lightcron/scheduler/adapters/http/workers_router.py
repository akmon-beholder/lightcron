"""FastAPI router for /workers endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from lightcron.scheduler.adapters.http.deps import get_worker_service
from lightcron.scheduler.adapters.http.schemas import WorkerResponse
from lightcron.scheduler.domain.workers.services.worker_service import WorkerService

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=list[WorkerResponse])
async def list_workers(
    service: WorkerService = Depends(get_worker_service),
) -> list[WorkerResponse]:
    workers = await service.list_workers()
    return [WorkerResponse.model_validate(w) for w in workers]
