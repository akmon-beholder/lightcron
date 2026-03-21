"""Unit tests for ExecutionService.

Fakes replace the ProcessManager and JobDB ports. asyncio.sleep is patched
to a no-op so tests complete instantly. SIGTERM_GRACE_PERIOD_SECONDS is
patched to -1 in tests that need to exercise the SIGKILL path (deadline is
immediately in the past, so the while/else executes SIGKILL without waiting).
"""

from __future__ import annotations

import signal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from lightcron.worker.domain.execution.entities import JobExecution
from lightcron.worker.domain.execution.services.execution_service import ExecutionService

_MODULE = "lightcron.worker.domain.execution.services.execution_service"


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeProcessManager:
    """Controllable fake ProcessManager.

    default_exit_code: if set, start() immediately registers an exit code
        (simulates a process that finishes before the first poll).
    exit_on_term: if True, kill_group(SIGTERM) marks the process as exited
        (simulates a graceful shutdown response to SIGTERM).
    rss_mb: value returned by get_rss_mb().
    """

    def __init__(
        self,
        default_exit_code: int | None = None,
        exit_on_term: bool = True,
        rss_mb: float = 1.0,
    ) -> None:
        self._default_exit_code = default_exit_code
        self._exit_on_term = exit_on_term
        self._rss_mb = rss_mb
        self._next_pid = 1000
        self._exited: dict[int, int] = {}
        self.signals: list[tuple[int, signal.Signals]] = []

    def start(self, command: str) -> int:
        pid = self._next_pid
        self._next_pid += 1
        if self._default_exit_code is not None:
            self._exited[pid] = self._default_exit_code
        return pid

    def kill_group(self, pid: int, sig: signal.Signals) -> None:
        self.signals.append((pid, sig))
        if sig == signal.SIGTERM and self._exit_on_term:
            self._exited[pid] = -15
        elif sig == signal.SIGKILL:
            self._exited[pid] = -9

    def poll_exit(self, pid: int) -> int | None:
        return self._exited.get(pid)

    def get_rss_mb(self, pid: int) -> float:
        return self._rss_mb


class FakeJobDB:
    """Fake JobDB with terminal-state guard and a check_status override."""

    _TERMINAL = frozenset({"completed", "failed", "cancelled", "lost"})

    def __init__(self, check_status_override: str | None = None) -> None:
        self._statuses: dict[UUID, str] = {}
        self._check_status_override = check_status_override
        self.updates: list[dict[str, object]] = []

    async def claim_job(self, worker_id: UUID) -> JobExecution | None:
        return None

    async def update_status(
        self, job_id: UUID, status: str, **kwargs: object
    ) -> bool:
        if self._statuses.get(job_id) in self._TERMINAL:
            return False
        self._statuses[job_id] = status
        self.updates.append({"job_id": job_id, "status": status, **kwargs})
        return True

    async def check_status(self, job_id: UUID) -> str | None:
        if self._check_status_override is not None:
            return self._check_status_override
        return self._statuses.get(job_id)

    async def count_active_jobs(self, worker_id: UUID) -> int:
        return 0


def _make_job(
    max_runtime: int | None = None,
    max_memory: int | None = None,
) -> JobExecution:
    return JobExecution(
        job_id=uuid4(),
        command="echo test",
        worker_id=uuid4(),
        max_runtime=max_runtime,
        max_memory=max_memory,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_natural_exit_success_records_completed() -> None:
    # Process exits with code 0 before the first poll → completed
    with patch("asyncio.sleep"):
        pm = FakeProcessManager(default_exit_code=0)
        db = FakeJobDB()
        svc = ExecutionService(db, pm)
        await svc.run_job(_make_job())

    assert db.updates[-1]["status"] == "completed"
    assert db.updates[-1]["exit_code"] == 0


async def test_natural_exit_failure_records_failed() -> None:
    with patch("asyncio.sleep"):
        pm = FakeProcessManager(default_exit_code=1)
        db = FakeJobDB()
        svc = ExecutionService(db, pm)
        await svc.run_job(_make_job())

    assert db.updates[-1]["status"] == "failed"
    assert db.updates[-1]["exit_code"] == 1


async def test_cancelled_job_sends_sigterm_and_no_db_write() -> None:
    # check_status always returns "cancelled" — process is still running
    with patch("asyncio.sleep"):
        pm = FakeProcessManager(exit_on_term=True)
        db = FakeJobDB(check_status_override="cancelled")
        svc = ExecutionService(db, pm)
        await svc.run_job(_make_job())

    # SIGTERM must be sent to stop the process
    assert any(sig == signal.SIGTERM for _, sig in pm.signals)
    # Cancel must NOT write a new status to the DB (only the initial "running" update)
    statuses = [u["status"] for u in db.updates]
    assert statuses == ["running"]


async def test_lost_job_sends_sigkill_and_no_db_write() -> None:
    with patch("asyncio.sleep"):
        pm = FakeProcessManager()
        db = FakeJobDB(check_status_override="lost")
        svc = ExecutionService(db, pm)
        await svc.run_job(_make_job())

    assert any(sig == signal.SIGKILL for _, sig in pm.signals)
    statuses = [u["status"] for u in db.updates]
    assert statuses == ["running"]


async def test_max_runtime_exceeded_records_failed() -> None:
    # max_runtime=0 → elapsed >= 0 triggers on first poll
    # SIGTERM_GRACE_PERIOD_SECONDS=-1 → deadline already past → straight to SIGKILL
    with patch("asyncio.sleep"), patch(f"{_MODULE}.SIGTERM_GRACE_PERIOD_SECONDS", -1):
        pm = FakeProcessManager()
        db = FakeJobDB()
        svc = ExecutionService(db, pm)
        await svc.run_job(_make_job(max_runtime=0))

    assert any(sig == signal.SIGKILL for _, sig in pm.signals)
    last = db.updates[-1]
    assert last["status"] == "failed"
    assert last["kill_reason"] == "max_runtime_exceeded"


async def test_max_memory_exceeded_records_failed() -> None:
    # RSS 200 MB > max_memory 10 MB → triggers on first poll
    with patch("asyncio.sleep"), patch(f"{_MODULE}.SIGTERM_GRACE_PERIOD_SECONDS", -1):
        pm = FakeProcessManager(rss_mb=200.0)
        db = FakeJobDB()
        svc = ExecutionService(db, pm)
        await svc.run_job(_make_job(max_memory=10))

    assert any(sig == signal.SIGKILL for _, sig in pm.signals)
    last = db.updates[-1]
    assert last["status"] == "failed"
    assert last["kill_reason"] == "max_memory_exceeded"


async def test_max_runtime_graceful_exit_no_sigkill() -> None:
    # Process exits cleanly after SIGTERM — SIGKILL should NOT be sent
    with patch("asyncio.sleep"):
        # exit_on_term=True: process exits after SIGTERM within grace period
        pm = FakeProcessManager(exit_on_term=True)
        db = FakeJobDB()
        svc = ExecutionService(db, pm)
        await svc.run_job(_make_job(max_runtime=0))

    sent_sigs = [sig for _, sig in pm.signals]
    assert signal.SIGTERM in sent_sigs
    assert signal.SIGKILL not in sent_sigs
    assert db.updates[-1]["status"] == "failed"
    assert db.updates[-1]["kill_reason"] == "max_runtime_exceeded"


async def test_status_guard_kills_process_when_running_update_blocked() -> None:
    # If the scheduler marks a job terminal before the worker writes "running",
    # the terminal-state guard blocks the update and the worker must kill the process.
    with patch("asyncio.sleep"):
        pm = FakeProcessManager()
        db = FakeJobDB()
        job = _make_job()
        db._statuses[job.job_id] = "cancelled"  # pre-set terminal state
        svc = ExecutionService(db, pm)
        await svc.run_job(job)

    # Process must be killed immediately
    assert any(sig == signal.SIGKILL for _, sig in pm.signals)
    # No status updates should have been written (guard blocked "running")
    assert len(db.updates) == 0
