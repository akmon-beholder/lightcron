"""Scheduler background dispatch service.

Implements two loops:
  1. ready-transition: marks pending jobs as ready when conditions are met.
  2. health-check: detects stale workers and marks them offline + jobs lost.
"""

from __future__ import annotations

import asyncio
import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from lightcron.constants import (
    HEALTH_CHECK_INTERVAL_SECONDS,
    READY_TRANSITION_INTERVAL_SECONDS,
    WORKER_HEALTH_PROBE_THRESHOLD_SECONDS,
    WORKER_OFFLINE_THRESHOLD_SECONDS,
)
from lightcron.scheduler.domain.jobs.entities import JobStatus
from lightcron.scheduler.ports.job_repository import JobRepository
from lightcron.scheduler.ports.worker_health_client import WorkerHealthClient
from lightcron.scheduler.ports.worker_repository import WorkerRepository
from lightcron.shared.ports.determinism.ports import TimePort

logger = logging.getLogger(__name__)

# PostgreSQL advisory lock key for the ready-transition loop.
# Prevents two scheduler instances from running the same loop simultaneously.
_READY_TRANSITION_LOCK_KEY = 1_000_001


class DispatchService:
    def __init__(
        self,
        jobs: JobRepository,
        workers: WorkerRepository,
        health_client: WorkerHealthClient,
        clock: TimePort,
    ) -> None:
        self._jobs = jobs
        self._workers = workers
        self._health_client = health_client
        self._clock = clock

    # ── Ready-transition loop ─────────────────────────────────────────────────

    async def run_ready_transition_loop(self) -> None:
        """Run forever, transitioning pending → ready every interval."""
        while True:
            try:
                await self._run_ready_transition_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in ready-transition loop")
            await asyncio.sleep(READY_TRANSITION_INTERVAL_SECONDS)

    async def _run_ready_transition_once(self) -> None:
        """Mark eligible pending jobs as ready (single pass).

        Uses a PostgreSQL advisory lock so multiple scheduler instances
        do not race to transition the same rows.
        """
        # The job_repo engine is accessed via the repo's internal engine.
        # We need a raw connection for the advisory lock pattern.
        # This method is intentionally coupled to the PostgresJobRepository
        # to leverage the underlying engine — acceptable in the adapter layer.
        from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository

        repo = self._jobs
        if not isinstance(repo, PostgresJobRepository):
            # Fallback for tests using fakes — run without advisory lock
            await self._transition_pending_to_ready_sql(None)
            return

        engine: AsyncEngine = repo._engine
        async with engine.connect() as conn, conn.begin():
            # Try to acquire advisory lock (non-blocking)
            lock_acquired = await conn.scalar(
                sa.text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": _READY_TRANSITION_LOCK_KEY},
            )
            if not lock_acquired:
                logger.debug("Ready-transition: another scheduler holds the lock, skipping")
                return

            await conn.execute(sa.text("""
                    UPDATE jobs
                    SET status = 'ready', updated_at = now()
                    WHERE status = 'pending'
                      AND start_time <= now()
                      AND (
                        depends_on = '{}'
                        OR NOT EXISTS (
                            SELECT 1 FROM jobs dep
                            WHERE dep.job_id = ANY(jobs.depends_on)
                              AND dep.status != 'completed'
                        )
                      )
                """))
                # Lock is released automatically at transaction end

    async def _transition_pending_to_ready_sql(self, conn: object) -> None:
        """Used by fake/test implementations without advisory lock."""
        pass

    # ── Health-check loop ─────────────────────────────────────────────────────

    async def run_health_check_loop(self) -> None:
        """Run forever, checking worker liveness every interval."""
        while True:
            try:
                await self._run_health_check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in health-check loop")
            await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)

    async def _run_health_check_once(self) -> None:
        """Two-stage liveness check for all stale workers (single pass)."""
        stage1_workers, stage2_workers = await self._workers.list_stale(
            probe_threshold_seconds=WORKER_HEALTH_PROBE_THRESHOLD_SECONDS,
            offline_threshold_seconds=WORKER_OFFLINE_THRESHOLD_SECONDS,
        )

        # Stage 1: workers with 60s ≤ age < 90s — call /health first
        for worker in stage1_workers:
            address = f"http://{worker.hostname}"
            alive = await self._health_client.check_health(worker.worker_id, address)
            if alive:
                logger.debug("Health probe OK for worker %s", worker.worker_id)
            else:
                logger.info(
                    "Worker %s (%s) failed /health probe — marking offline",
                    worker.worker_id,
                    worker.hostname,
                )
                await self._mark_worker_offline_and_jobs_lost(worker.worker_id)

        # Stage 2: workers with age ≥ 90s — skip /health probe
        for worker in stage2_workers:
            logger.info(
                "Worker %s (%s) last_seen ≥ %ds — marking offline",
                worker.worker_id,
                worker.hostname,
                WORKER_OFFLINE_THRESHOLD_SECONDS,
            )
            await self._mark_worker_offline_and_jobs_lost(worker.worker_id)

    async def _mark_worker_offline_and_jobs_lost(self, worker_id: object) -> None:
        """Stage 2: atomically mark worker offline and all its assigned/running jobs lost."""
        from lightcron.scheduler.adapters.db.job_repo import PostgresJobRepository
        from lightcron.scheduler.adapters.db.worker_repo import PostgresWorkerRepository

        job_repo = self._jobs
        worker_repo = self._workers

        if isinstance(job_repo, PostgresJobRepository) and isinstance(
            worker_repo, PostgresWorkerRepository
        ):
            # Execute both writes in a single transaction for atomicity
            engine: AsyncEngine = job_repo._engine
            async with engine.connect() as conn, conn.begin():
                await conn.execute(
                    sa.text(
                        "UPDATE worker_status SET status = 'offline' "
                        "WHERE worker_id = :id AND status = 'online'"
                    ),
                    {"id": str(worker_id)},
                )
                await conn.execute(
                    sa.text(
                        "UPDATE jobs SET status = 'lost', updated_at = now() "
                        "WHERE worker_id = :id "
                        "AND status IN ('assigned', 'running')"
                    ),
                    {"id": str(worker_id)},
                )
        else:
            # Fallback for test fakes
            from uuid import UUID
            wid = worker_id if isinstance(worker_id, UUID) else UUID(str(worker_id))
            await worker_repo.mark_offline(wid)
            for job in await job_repo.list_by_worker(wid):
                if job.status in (JobStatus.ASSIGNED, JobStatus.RUNNING):
                    await job_repo.update_status(job.job_id, JobStatus.LOST)
