"""httpx implementation of WorkerHealthClient."""

from __future__ import annotations

from uuid import UUID

import httpx


class HttpxWorkerHealthClient:
    """Calls GET /health on a worker agent and returns True on HTTP 200."""

    _TIMEOUT_SECONDS = 5.0

    async def check_health(self, _worker_id: UUID, address: str) -> bool:
        url = f"{address.rstrip('/')}/health"
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT_SECONDS) as client:
                response = await client.get(url)
            return response.status_code == 200
        except Exception:
            return False
