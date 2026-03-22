"""Worker agent registration and last-seen heartbeat loop."""

from __future__ import annotations

import asyncio
import logging
import socket
from uuid import UUID

from lightcron.constants import LAST_SEEN_UPDATE_INTERVAL_SECONDS
from lightcron.worker.ports.worker_status_db import WorkerStatusDB

logger = logging.getLogger(__name__)


class RegistrationService:
    def __init__(self, db: WorkerStatusDB) -> None:
        self._db = db
        self._worker_id: UUID | None = None

    @property
    def worker_id(self) -> UUID:
        if self._worker_id is None:
            raise RuntimeError("Worker not registered yet")
        return self._worker_id

    async def register(self, base_url: str | None = None) -> UUID:
        """Upsert this worker into worker_status and return the worker_id."""
        hostname = socket.gethostname()
        self._worker_id = await self._db.upsert_worker(hostname, base_url=base_url)
        logger.info(
            "Registered as worker_id=%s hostname=%s base_url=%s",
            self._worker_id,
            hostname,
            base_url,
        )
        return self._worker_id

    async def run_heartbeat_loop(self) -> None:
        """Update last_seen every LAST_SEEN_UPDATE_INTERVAL_SECONDS forever."""
        while True:
            try:
                await self._db.update_last_seen(self.worker_id)
                logger.debug("Heartbeat sent for worker_id=%s", self.worker_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Heartbeat failed for worker_id=%s", self.worker_id)
            await asyncio.sleep(LAST_SEEN_UPDATE_INTERVAL_SECONDS)
