"""Unit tests for RegistrationService."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from lightcron.worker.domain.execution.services.registration_service import RegistrationService


class FakeWorkerStatusDB:
    def __init__(self, worker_id: UUID | None = None) -> None:
        self._worker_id = worker_id or uuid4()
        self.last_seen_updates: list[UUID] = []

    async def upsert_worker(self, hostname: str, base_url: str | None = None) -> UUID:
        return self._worker_id

    async def update_last_seen(self, worker_id: UUID) -> None:
        self.last_seen_updates.append(worker_id)


def test_worker_id_raises_before_register() -> None:
    svc = RegistrationService(FakeWorkerStatusDB())
    with pytest.raises(RuntimeError, match="not registered"):
        _ = svc.worker_id


async def test_register_returns_worker_id() -> None:
    expected = uuid4()
    db = FakeWorkerStatusDB(expected)
    svc = RegistrationService(db)
    result = await svc.register()
    assert result == expected
    assert svc.worker_id == expected


_REG_MODULE = "lightcron.worker.domain.execution.services.registration_service"


async def test_heartbeat_survives_transient_db_error() -> None:
    """A DB exception in update_last_seen is logged and the loop continues."""
    call_count = 0

    class FlakyDB(FakeWorkerStatusDB):
        async def update_last_seen(self, worker_id: UUID) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            await super().update_last_seen(worker_id)

    db = FlakyDB()
    svc = RegistrationService(db)
    await svc.register()

    # Patch interval to 0 so asyncio.sleep(0) is used — yields control without blocking.
    with patch(f"{_REG_MODULE}.LAST_SEEN_UPDATE_INTERVAL_SECONDS", 0):
        task = asyncio.create_task(svc.run_heartbeat_loop())
        # Yield twice: first iteration raises, second succeeds
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert call_count >= 2  # loop ran past the exception


async def test_heartbeat_calls_update_last_seen() -> None:
    db = FakeWorkerStatusDB()
    svc = RegistrationService(db)
    await svc.register()

    task = asyncio.create_task(svc.run_heartbeat_loop())
    await asyncio.sleep(0)  # yield so the loop runs its first iteration
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert len(db.last_seen_updates) >= 1
    assert db.last_seen_updates[0] == svc.worker_id
