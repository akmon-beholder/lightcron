"""WorkerHealthClient port protocol."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class WorkerHealthClient(Protocol):
    async def check_health(self, worker_id: UUID, address: str) -> bool:
        """Call GET /health on the worker agent at the given address.

        Args:
            worker_id: Used for logging/tracing only.
            address:   Base URL of the worker agent, e.g. "http://worker-01:8001"

        Returns:
            True  — worker responded HTTP 200.
            False — any error: connection refused, timeout, non-200 response.
        """
        ...
