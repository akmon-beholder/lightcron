"""Job execution service — runs, monitors, and finalises job processes."""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime

from lightcron.constants import (
    JOB_STATUS_POLL_INTERVAL_SECONDS,
    SIGTERM_GRACE_PERIOD_SECONDS,
)
from lightcron.worker.domain.execution.entities import JobExecution
from lightcron.worker.ports.job_db import JobDB
from lightcron.worker.ports.process_manager import ProcessManager

logger = logging.getLogger(__name__)


class ExecutionService:
    def __init__(self, db: JobDB, process_manager: ProcessManager) -> None:
        self._db = db
        self._pm = process_manager

    async def run_job(self, job: JobExecution) -> None:
        """Execute a claimed job end-to-end.

        This coroutine returns when the job reaches a terminal state.
        It is designed to be run as an asyncio task by the claim loop.
        """
        # Start the process
        pid = self._pm.start(job.command)
        job.pid = pid
        started_at = datetime.now(UTC)

        updated = await self._db.update_status(
            job.job_id,
            "running",
            started_at=started_at,
        )
        if not updated:
            # Scheduler has already marked job as cancelled/lost while we were claiming
            logger.warning("Job %s status guard blocked running update; killing process", job.job_id)
            self._pm.kill_group(pid, signal.SIGKILL)
            return

        logger.info("Started job %s pid=%d command=%r", job.job_id, pid, job.command)

        try:
            await self._monitor_job(job, pid, started_at)
        finally:
            job.pid = None

    async def _monitor_job(
        self,
        job: JobExecution,
        pid: int,
        started_at: datetime,
    ) -> None:
        """Poll loop: check exit, enforce limits, detect cancel/lost."""
        while True:
            await asyncio.sleep(JOB_STATUS_POLL_INTERVAL_SECONDS)

            # Check if process exited naturally
            exit_code = self._pm.poll_exit(pid)
            if exit_code is not None:
                await self._record_natural_exit(job, exit_code)
                return

            # Check current DB status for cancellation or lost
            status = await self._db.check_status(job.job_id)
            if status == "cancelled":
                logger.info("Job %s cancelled — stopping process", job.job_id)
                await self._stop_process(pid)
                return
            if status == "lost":
                logger.info("Job %s marked lost by scheduler — killing process immediately", job.job_id)
                self._pm.kill_group(pid, signal.SIGKILL)
                return

            # Enforce max_runtime
            if job.max_runtime is not None:
                elapsed = (datetime.now(UTC) - started_at).total_seconds()
                if elapsed >= job.max_runtime:
                    logger.info("Job %s exceeded max_runtime=%ds — terminating", job.job_id, job.max_runtime)
                    await self._kill_for_limit(job, pid, "max_runtime_exceeded")
                    return

            # Enforce max_memory
            if job.max_memory is not None:
                rss_mb = self._pm.get_rss_mb(pid)
                if rss_mb > job.max_memory:
                    logger.info(
                        "Job %s exceeded max_memory=%dMB (actual=%.1fMB) — terminating",
                        job.job_id,
                        job.max_memory,
                        rss_mb,
                    )
                    await self._kill_for_limit(job, pid, "max_memory_exceeded")
                    return

    async def _record_natural_exit(self, job: JobExecution, exit_code: int) -> None:
        finished_at = datetime.now(UTC)
        status = "completed" if exit_code == 0 else "failed"
        await self._db.update_status(
            job.job_id,
            status,
            exit_code=exit_code,
            finished_at=finished_at,
        )
        logger.info("Job %s exited with code %d → %s", job.job_id, exit_code, status)

    async def _kill_for_limit(
        self,
        job: JobExecution,
        pid: int,
        kill_reason: str,
    ) -> None:
        """SIGTERM → grace period → SIGKILL, then record as failed."""
        self._pm.kill_group(pid, signal.SIGTERM)

        # Wait for graceful exit during the grace period
        deadline = asyncio.get_event_loop().time() + SIGTERM_GRACE_PERIOD_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(1)
            if self._pm.poll_exit(pid) is not None:
                break
        else:
            # Grace period elapsed — force kill
            self._pm.kill_group(pid, signal.SIGKILL)
            await asyncio.sleep(1)

        finished_at = datetime.now(UTC)
        await self._db.update_status(
            job.job_id,
            "failed",
            kill_reason=kill_reason,
            finished_at=finished_at,
        )
        logger.info("Job %s killed — %s", job.job_id, kill_reason)

    async def _stop_process(self, pid: int) -> None:
        """SIGTERM → grace → SIGKILL for a cancelled job (no DB write)."""
        self._pm.kill_group(pid, signal.SIGTERM)
        deadline = asyncio.get_event_loop().time() + SIGTERM_GRACE_PERIOD_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(1)
            if self._pm.poll_exit(pid) is not None:
                return
        self._pm.kill_group(pid, signal.SIGKILL)
