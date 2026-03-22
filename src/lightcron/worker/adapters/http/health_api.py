"""Worker agent health endpoint and job output endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from lightcron.constants import WORKER_DEFAULT_JOBS_DIR


class HealthResponse(BaseModel):
    status: str = "ok"


def _get_jobs_dir() -> Path:
    return Path(os.environ.get("LIGHTCRON_JOBS_DIR", WORKER_DEFAULT_JOBS_DIR))


def build_health_app() -> FastAPI:
    app = FastAPI(title="Lightcron Worker Agent", version="0.1.0")

    ui_origin = os.environ.get("LIGHTCRON_UI_ORIGIN", "")
    if ui_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[ui_origin],
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/jobs/{job_id}/stdout")
    async def get_stdout(job_id: UUID) -> PlainTextResponse:
        path = _get_jobs_dir() / f"{job_id}.stdout"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return PlainTextResponse(path.read_text())

    @app.get("/jobs/{job_id}/stderr")
    async def get_stderr(job_id: UUID) -> PlainTextResponse:
        path = _get_jobs_dir() / f"{job_id}.stderr"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return PlainTextResponse(path.read_text())

    return app
