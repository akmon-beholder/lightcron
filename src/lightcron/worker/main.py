"""Worker agent entry point.

Starts three concurrent loops:
  1. Registration + last-seen heartbeat
  2. Claim loop (poll DB for ready jobs)
  3. Health API server (GET /health)
"""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from sqlalchemy.ext.asyncio import create_async_engine

from lightcron.worker.adapters.db.job_db import AsyncpgJobDB
from lightcron.worker.adapters.db.worker_status_db import AsyncpgWorkerStatusDB
from lightcron.worker.adapters.http.health_api import build_health_app
from lightcron.worker.adapters.process.subprocess_adapter import SubprocessAdapter
from lightcron.worker.domain.execution.services.claim_service import ClaimService
from lightcron.worker.domain.execution.services.execution_service import ExecutionService
from lightcron.worker.domain.execution.services.registration_service import RegistrationService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    pgbouncer_url = os.environ["PGBOUNCER_URL"]
    concurrency = int(os.environ.get("WORKER_CONCURRENCY", "2"))
    health_port = int(os.environ.get("WORKER_HEALTH_PORT", "8001"))

    engine = create_async_engine(pgbouncer_url)
    job_db = AsyncpgJobDB(engine)
    worker_status_db = AsyncpgWorkerStatusDB(engine)
    process_manager = SubprocessAdapter()

    # Register this worker and get its worker_id
    registration = RegistrationService(worker_status_db)
    worker_id = await registration.register()

    execution = ExecutionService(job_db, process_manager)
    claim = ClaimService(job_db, execution, worker_id, concurrency)

    # Build health API server config
    health_app = build_health_app()
    health_config = uvicorn.Config(health_app, host="0.0.0.0", port=health_port, log_level="warning")
    health_server = uvicorn.Server(health_config)

    logger.info("Worker agent started — worker_id=%s concurrency=%d", worker_id, concurrency)

    tasks = [
        asyncio.create_task(registration.run_heartbeat_loop()),
        asyncio.create_task(claim.run_claim_loop()),
        asyncio.create_task(health_server.serve()),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
