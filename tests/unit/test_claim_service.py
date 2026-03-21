"""Unit tests for ClaimService._try_claim logic."""

from __future__ import annotations

import asyncio
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from lightcron.worker.domain.execution.entities import JobExecution
from lightcron.worker.domain.execution.services.claim_service import ClaimService


class FakeJobDB:
    def __init__(self, active_count: int = 0, job: JobExecution | None = None) -> None:
        self._active_count = active_count
        self._job = job

    async def claim_job(self, worker_id: UUID) -> JobExecution | None:
        return self._job

    async def count_active_jobs(self, worker_id: UUID) -> int:
        return self._active_count

    async def update_status(self, *args: object, **kwargs: object) -> bool:
        return True

    async def check_status(self, job_id: UUID) -> str | None:
        return "running"


class FakeExecutionService:
    def __init__(self) -> None:
        self.jobs_run: list[JobExecution] = []

    async def run_job(self, job: JobExecution) -> None:
        self.jobs_run.append(job)


def _make_job() -> JobExecution:
    return JobExecution(
        job_id=uuid4(),
        command="echo test",
        worker_id=uuid4(),
        max_runtime=None,
        max_memory=None,
    )


async def test_skips_when_task_set_at_capacity() -> None:
    db = FakeJobDB(active_count=0, job=_make_job())
    exe = FakeExecutionService()
    svc = ClaimService(db, exe, uuid4(), concurrency=1)

    # Manually fill the active task set with a non-done task
    async def _long() -> None:
        await asyncio.sleep(1000)

    task = asyncio.create_task(_long())
    svc._active_tasks.add(task)

    await svc._try_claim()
    assert len(exe.jobs_run) == 0

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_skips_when_db_count_at_capacity() -> None:
    db = FakeJobDB(active_count=2, job=_make_job())
    exe = FakeExecutionService()
    svc = ClaimService(db, exe, uuid4(), concurrency=2)

    await svc._try_claim()
    assert len(exe.jobs_run) == 0


async def test_skips_when_no_job_available() -> None:
    db = FakeJobDB(active_count=0, job=None)
    exe = FakeExecutionService()
    svc = ClaimService(db, exe, uuid4(), concurrency=2)

    await svc._try_claim()
    assert len(exe.jobs_run) == 0


async def test_creates_task_when_job_claimed() -> None:
    job = _make_job()
    db = FakeJobDB(active_count=0, job=job)
    exe = FakeExecutionService()
    svc = ClaimService(db, exe, uuid4(), concurrency=2)

    await svc._try_claim()
    await asyncio.sleep(0)  # yield so the spawned task runs

    assert len(exe.jobs_run) == 1
    assert exe.jobs_run[0] is job
    assert len(svc._active_tasks) == 1


_CLAIM_MODULE = "lightcron.worker.domain.execution.services.claim_service"


async def test_run_claim_loop_is_cancellable() -> None:
    """run_claim_loop runs until cancelled and propagates CancelledError."""
    db = FakeJobDB(active_count=0, job=None)
    exe = FakeExecutionService()
    svc = ClaimService(db, exe, uuid4(), concurrency=2)

    # Patch the interval to 0 so asyncio.sleep(0) is used — it yields control
    # without blocking, allowing the loop to run and be cancelled quickly.
    with patch(f"{_CLAIM_MODULE}.CLAIM_POLL_INTERVAL_SECONDS", 0):
        task = asyncio.create_task(svc.run_claim_loop())
        await asyncio.sleep(0)  # let the loop start its first iteration
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_run_claim_loop_continues_after_exception() -> None:
    """Exceptions in _try_claim are logged but the loop keeps running."""
    call_count = 0

    class BrokenJobDB(FakeJobDB):
        async def count_active_jobs(self, worker_id: UUID) -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient DB error")
            return 0

    db = BrokenJobDB(job=None)
    exe = FakeExecutionService()
    svc = ClaimService(db, exe, uuid4(), concurrency=2)

    with patch(f"{_CLAIM_MODULE}.CLAIM_POLL_INTERVAL_SECONDS", 0):
        task = asyncio.create_task(svc.run_claim_loop())
        # Yield twice: first iteration raises, second succeeds
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert call_count >= 2  # loop continued past the exception


async def test_prunes_completed_tasks() -> None:
    db = FakeJobDB(active_count=0, job=None)
    exe = FakeExecutionService()
    svc = ClaimService(db, exe, uuid4(), concurrency=2)

    async def _done() -> None:
        return

    task = asyncio.create_task(_done())
    await asyncio.sleep(0)  # let it complete
    assert task.done()

    svc._active_tasks.add(task)
    await svc._try_claim()

    assert task not in svc._active_tasks
