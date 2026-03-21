"""Worker agent health endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


def build_health_app() -> FastAPI:
    app = FastAPI(title="Lightcron Worker Agent", version="0.1.0")

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    return app
