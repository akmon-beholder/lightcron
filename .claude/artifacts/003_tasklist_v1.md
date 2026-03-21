# Lightcron — Implementation Tasklist

## Metadata
- **Version**: v1
- **Created**: 2026-03-21
- **Agent**: ba (Phase B)
- **Inputs**: `002_spec_v1.md`, `001_solution_envelope_v2.md`
- **Status**: approved_for_build

---

## Conventions

- Task IDs: `T{NNN}` — never reuse or renumber.
- Dependencies: a task may not begin until all listed predecessor tasks are complete.
- Agent assignments: `back` for `src/`, `front` for `frontend/`, `ops` for infra/CI.
- BDD feature files in `specs/features/` are the acceptance criteria for each task. Step definitions are a separate task group.
- All timing constants must be imported from `src/lightcron/constants.py` — no literals.

---

## Group 1 — Project Scaffold

### T001 · Repository structure and Python package setup
**Agent**: back
**Scope**: `pyproject.toml`, `src/lightcron/__init__.py`, `src/lightcron/constants.py`
**Work**:
- Configure `pyproject.toml` with two optional dependency groups: `scheduler` and `worker`
- Create `src/lightcron/constants.py` with all constants from spec §Constants
- Confirm `ruff`, `mypy`, `bandit`, `pip-audit` are listed as dev dependencies
- Confirm `pytest`, `pytest-bdd`, `pytest-asyncio`, `pytest-cov` are listed
**AC**: `python -m lightcron.constants` imports without error; all constant names and values match spec

---

### T002 · Docker Compose development environment
**Agent**: ops
**Scope**: `docker-compose.yml`, `docker-compose.override.yml`, `.env.example`
**Work**:
- `db` service: PostgreSQL 16
- `pgbouncer` service: configured with `pool_mode=session`; forwards to `db`
- `scheduler` service: builds from `src/`, mounts code for hot-reload, connects via pgBouncer
- `worker` service: builds from `src/`, mounts code, connects via pgBouncer, `N=2` concurrency
- `ui` service: runs `vite dev` from `frontend/`
- `.env.example` documents all required environment variables: `DATABASE_URL`, `PGBOUNCER_URL`, `LIGHTCRON_UI_ORIGIN`, `VITE_API_BASE_URL`, `WORKER_CONCURRENCY`
**AC**: `docker compose up` starts all services; scheduler returns 200 on `GET /health`

---

### T003 · CI pipeline skeleton
**Agent**: ops
**Scope**: `.github/workflows/ci.yml`
**Work**:
- Jobs: `lint` (ruff, eslint), `type-check` (mypy, tsc), `test-backend`, `test-e2e`, `security`
- `security` job: gitleaks (ops condition C1), bandit, pip-audit
- All jobs run on pull requests and pushes to `main`
- Artifacts: coverage report uploaded from `test-backend`
**AC**: CI pipeline defined; all jobs present (they may fail at this stage — scaffold only)

---

## Group 2 — Database Schema and Migrations

### T004 · Alembic setup and initial migration
**Agent**: back
**Scope**: `alembic.ini`, `src/migrations/`, `src/migrations/versions/001_initial_schema.py`
**Work**:
- Initialise Alembic with async SQLAlchemy engine
- Migration creates: `job_status` enum, `worker_status` enum, `worker_status` table, `jobs` table with all fields and constraints from spec §Data Model
- All indexes from spec included
- `updated_at` trigger on `jobs` table
**AC**: `alembic upgrade head` on a fresh DB creates both tables and all indexes; `alembic check` passes (ops condition C2)

---

### T005 · pgBouncer session-mode integration test
**Agent**: back
**Scope**: `tests/integration/test_pgbouncer.py`
**Work**:
- Test connects via pgBouncer URL (not direct DB) and executes `SELECT FOR UPDATE SKIP LOCKED`
- Test asserts the lock works correctly (rowcount, lock released on commit)
- A separate negative test asserts that configuring pgBouncer in transaction mode breaks the lock (documents the failure mode)
**AC**: Integration test passes; failure mode documented (ops condition C5)

---

### T006 · FK integrity post-migration validation
**Agent**: ops
**Scope**: `scripts/check_fk_integrity.sql`, updated `.github/workflows/ci.yml`
**Work**:
- Script queries `pg_catalog` to verify all FK constraints are present and valid after migration
- CI `test-backend` job runs this script after `alembic upgrade head` (ops condition C3)
**AC**: Script returns exit code 0 on a correctly migrated DB; CI job runs it

---

## Group 3 — Scheduler: Domain and Ports

### T007 · Job domain entity and status enum
**Agent**: back
**Scope**: `src/lightcron/scheduler/domain/jobs/entities.py`
**Work**:
- `JobStatus` enum with all 8 values from spec
- `Job` dataclass with all fields from spec §Data Model; all timestamps as `datetime`; `depends_on` as `list[UUID]`
- `is_terminal()` method returning True for `completed | failed | cancelled | lost`
**AC**: Unit tests cover enum values and `is_terminal()`

---

### T008 · Worker domain entity and status enum
**Agent**: back
**Scope**: `src/lightcron/scheduler/domain/workers/entities.py`
**Work**:
- `WorkerStatus` enum: `online | offline`
- `Worker` dataclass with all fields from spec; `running_job_count: int` field (populated by repository)
**AC**: Unit tests cover entity construction

---

### T009 · Scheduler port protocols
**Agent**: back
**Scope**: `src/lightcron/scheduler/ports/`
**Work**:
- `JobRepository` Protocol: `get(job_id) -> Job | None`, `save(job) -> Job`, `update_status(job_id, status, **kwargs) -> bool`, `list_by_status(status) -> list[Job]`, `list_by_worker(worker_id) -> list[Job]`
- `WorkerRepository` Protocol: `get_by_hostname(hostname) -> Worker | None`, `upsert(hostname) -> Worker`, `mark_offline(worker_id) -> bool`, `list_stale(probe_threshold, offline_threshold) -> tuple[list[Worker], list[Worker]]` (returns workers in stage-1 and stage-2 buckets)
- `WorkerHealthClient` Protocol: `check_health(worker_id, address) -> bool`
- `TimePort`, `UUIDPort` already scaffolded — confirm they exist and are importable
**AC**: Protocols are importable; mypy passes with `--strict` on these files

---

## Group 4 — Scheduler: REST API

### T010 · FastAPI application shell and health endpoint
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/http/app.py`
**Work**:
- FastAPI app instance with CORS middleware; allowed origin from `LIGHTCRON_UI_ORIGIN` env var (ops condition C7)
- `GET /health` → `{"status": "ok"}` (ops condition C4)
- Lifespan handler that starts/stops background loops (wired in later tasks)
**AC**: `GET /health` returns 200; CORS headers present for `LIGHTCRON_UI_ORIGIN`

---

### T011 · POST /jobs endpoint
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/http/jobs_router.py`, `src/lightcron/scheduler/domain/jobs/services/job_service.py`
**Work**:
- Pydantic request model with all fields and validation rules from spec §POST /jobs
- `schedule_job(command, start_time, depends_on, max_runtime, max_memory)` domain service method
- Validation: start_time in future; all depends_on UUIDs exist; max_runtime/max_memory positive
- Returns 201 with full job object; 422 on validation failure; 400 on malformed JSON
**AC**: BDD steps for `specs/features/job-management/schedule-job.feature` pass

---

### T012 · GET /jobs/{job_id} and GET /jobs endpoints
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/http/jobs_router.py`
**Work**:
- `GET /jobs/{job_id}`: returns full job object or 404
- `GET /jobs`: returns list; accepts `status` query param; validates it against `JobStatus` enum; returns 422 for invalid values
**AC**: BDD steps for `specs/features/job-management/query-job-status.feature` pass

---

### T013 · POST /jobs/{job_id}/cancel endpoint
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/http/jobs_router.py`, `src/lightcron/scheduler/domain/jobs/services/job_service.py`
**Work**:
- `cancel_job(job_id)` service method
- Returns 200 if not terminal; 409 if terminal; 404 if not found
- UPDATE uses terminal-state guard (`WHERE status NOT IN (...)`)
**AC**: BDD steps for `specs/features/job-management/cancel-job.feature` pass

---

### T014 · GET /workers endpoint
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/http/workers_router.py`, `src/lightcron/scheduler/domain/workers/services/worker_service.py`
**Work**:
- Returns list of all workers with `running_job_count` populated
- Empty list if no workers registered
**AC**: BDD steps for `specs/features/operations/worker-health-monitoring.feature` pass

---

## Group 5 — Scheduler: Database Adapters

### T015 · PostgreSQL JobRepository adapter
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/db/job_repo.py`
**Work**:
- Implements `JobRepository` protocol using `asyncpg` + SQLAlchemy core
- All methods: `get`, `save`, `update_status`, `list_by_status`, `list_by_worker`
- `update_status` applies terminal-state guard
**AC**: All adapter methods covered by integration tests against a real PostgreSQL instance

---

### T016 · PostgreSQL WorkerRepository adapter
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/db/worker_repo.py`
**Work**:
- Implements `WorkerRepository` protocol
- `upsert(hostname)`: INSERT ... ON CONFLICT (hostname) DO UPDATE
- `list_stale(probe_threshold, offline_threshold)`: returns workers bucketed into stage-1 and stage-2 by `last_seen` age
- `running_job_count` computed in the same query (LEFT JOIN or subquery)
**AC**: Integration tests cover upsert idempotency and stale bucketing

---

### T017 · httpx WorkerHealthClient adapter
**Agent**: back
**Scope**: `src/lightcron/scheduler/adapters/health/worker_health_client.py`
**Work**:
- Calls `GET http://{address}/health` with a 5s timeout
- Returns `True` on HTTP 200; `False` on any error, non-200 response, or timeout
**AC**: Unit tests with mocked httpx verify both True and False paths

---

## Group 6 — Scheduler: Background Loops

### T018 · Ready-transition loop
**Agent**: back
**Scope**: `src/lightcron/scheduler/domain/jobs/services/dispatch_service.py`
**Work**:
- Implements the ready-transition SQL from spec §Ready-Transition Loop
- Runs every `READY_TRANSITION_INTERVAL_SECONDS`
- Uses PostgreSQL advisory lock to be safe at >1 scheduler instance
**AC**: BDD steps for `specs/features/worker-management/job-dispatch.feature` (scheduler scenarios) pass; concurrent scheduler instances do not double-transition the same job (integration test)

---

### T019 · Health-check loop
**Agent**: back
**Scope**: `src/lightcron/scheduler/domain/jobs/services/dispatch_service.py`
**Work**:
- Implements two-stage liveness logic from spec §Health-Check Loop
- Uses `WorkerHealthClient` port for stage-1 /health probe
- Stage 2 writes `offline` to worker_status and `lost` to affected jobs atomically
- Terminal-state guard on the jobs UPDATE
**AC**: BDD steps for `specs/features/operations/stuck-job-recovery.feature` pass

---

## Group 7 — Worker Agent: Domain and Ports

### T020 · Worker agent domain entities and ports
**Agent**: back
**Scope**: `src/lightcron/worker/domain/execution/entities.py`, `src/lightcron/worker/ports/`
**Work**:
- `JobExecution` dataclass: `job_id`, `command`, `max_runtime`, `max_memory`, `worker_id`, `pid` (nullable)
- `JobDB` Protocol: `claim_job(worker_id) -> JobExecution | None`, `update_status(job_id, status, **kwargs) -> bool`, `check_status(job_id) -> JobStatus`
- `WorkerStatusDB` Protocol: `upsert_worker(hostname) -> str` (returns worker_id), `update_last_seen(worker_id) -> None`
- `ProcessManager` Protocol: `start(command) -> int` (returns pid), `kill_group(pid, signal) -> None`, `poll_exit(pid) -> int | None` (returns exit_code or None if still running), `get_rss_mb(pid) -> float`
**AC**: Protocols importable; mypy strict passes

---

## Group 8 — Worker Agent: Database Adapters

### T021 · asyncpg JobDB adapter
**Agent**: back
**Scope**: `src/lightcron/worker/adapters/db/job_db.py`
**Work**:
- `claim_job`: executes claim sequence from spec §Claim Loop (SELECT FOR UPDATE SKIP LOCKED + UPDATE with rowcount check)
- `update_status`: with terminal-state guard
- `check_status`: simple SELECT
**AC**: Integration test (via pgBouncer) verifies concurrent claim by two workers assigns job to exactly one

---

### T022 · asyncpg WorkerStatusDB adapter
**Agent**: back
**Scope**: `src/lightcron/worker/adapters/db/worker_status_db.py`
**Work**:
- `upsert_worker`: INSERT ... ON CONFLICT (hostname) DO UPDATE; returns existing or new worker_id
- `update_last_seen`: UPDATE worker_status SET last_seen = now()
**AC**: Integration tests cover first registration, re-registration (worker_id preserved), and heartbeat update

---

## Group 9 — Worker Agent: Process Manager

### T023 · subprocess + psutil ProcessManager adapter
**Agent**: back
**Scope**: `src/lightcron/worker/adapters/process/subprocess_adapter.py`
**Work**:
- `start(command)`: spawns subprocess, returns pid; captures no output (stdout/stderr to `/dev/null` or a log file — out of scope for v1 but must not block)
- `kill_group(pid, signal)`: calls `os.killpg(os.getpgid(pid), signal)`
- `poll_exit(pid)`: non-blocking; returns exit code if exited, None if running
- `get_rss_mb(pid)`: uses `psutil.Process(pid).memory_info().rss / 1024 / 1024`
- Handles `psutil.NoSuchProcess` gracefully (process already exited)
**AC**: Unit tests with mock subprocess verify all four methods; note: process group kill must be tested on Linux

---

## Group 10 — Worker Agent: Registration and Claim Loops

### T024 · Registration and last-seen loop
**Agent**: back
**Scope**: `src/lightcron/worker/domain/execution/services/registration_service.py`
**Work**:
- On start: calls `WorkerStatusDB.upsert_worker(hostname)`; stores returned `worker_id` for all subsequent operations
- Loop: calls `WorkerStatusDB.update_last_seen(worker_id)` every `LAST_SEEN_UPDATE_INTERVAL_SECONDS`
**AC**: BDD steps for `specs/features/worker-management/worker-registration.feature` pass

---

### T025 · Claim loop
**Agent**: back
**Scope**: `src/lightcron/worker/domain/execution/services/claim_service.py`
**Work**:
- Polls every `CLAIM_POLL_INTERVAL_SECONDS`
- Checks running job count against `N` before claiming
- Executes claim sequence; hands off claimed job to execution_service
- On empty result: waits for next poll interval
**AC**: BDD steps for `specs/features/worker-management/job-dispatch.feature` (worker agent scenarios) pass; race condition scenario passes

---

## Group 11 — Worker Agent: Execution Lifecycle

### T026 · Job execution service — start and natural exit
**Agent**: back
**Scope**: `src/lightcron/worker/domain/execution/services/execution_service.py`
**Work**:
- Start: calls `ProcessManager.start(command)`, writes `running` + `started_at` to DB
- Monitor loop every `JOB_STATUS_POLL_INTERVAL_SECONDS`:
  - `poll_exit`: if exited, write `completed` (exit 0) or `failed` (exit != 0) + `exit_code` + `finished_at`
  - `check_status`: if `cancelled`, stop process; if `lost`, kill group immediately
- All DB writes use terminal-state guard
**AC**: BDD steps for `specs/features/job-management/job-lifecycle-completion.feature` (natural exit scenarios) pass

---

### T027 · Job execution service — max_runtime enforcement
**Agent**: back
**Scope**: `src/lightcron/worker/domain/execution/services/execution_service.py`
**Work**:
- In monitor loop: if `max_runtime` is set and `elapsed >= max_runtime`, send SIGTERM
- Wait `SIGTERM_GRACE_PERIOD_SECONDS`; send SIGKILL if still running
- Write `failed`, `kill_reason = 'max_runtime_exceeded'`, `finished_at` with terminal-state guard
**AC**: BDD steps for job-lifecycle-completion.feature (max_runtime scenarios) pass

---

### T028 · Job execution service — max_memory enforcement
**Agent**: back
**Scope**: `src/lightcron/worker/domain/execution/services/execution_service.py`
**Work**:
- In monitor loop: if `max_memory` is set and `get_rss_mb(pid) > max_memory`, send SIGTERM
- Same grace period / SIGKILL / DB write pattern as T027
- Write `kill_reason = 'max_memory_exceeded'`
**AC**: BDD steps for job-lifecycle-completion.feature (max_memory scenarios) pass

---

### T029 · Worker agent: cancel detection and zombie cleanup
**Agent**: back
**Scope**: `src/lightcron/worker/domain/execution/services/execution_service.py`
**Work**:
- Cancel: on `cancelled` detected in poll, SIGTERM → grace → SIGKILL; no DB write
- Zombie cleanup: on `lost` detected, immediate SIGKILL; no DB write
**AC**: BDD steps for cancel-job.feature (worker-side scenarios) and stuck-job-recovery.feature (zombie cleanup scenario) pass

---

## Group 12 — Worker Agent: Health API

### T030 · Worker agent health endpoint
**Agent**: back
**Scope**: `src/lightcron/worker/adapters/http/health_api.py`
**Work**:
- Minimal FastAPI app: `GET /health` → `{"status": "ok"}`
- Runs in a background thread/task alongside the main worker loops
- No DB dependency — returns 200 as long as the process is alive
**AC**: `GET /health` returns 200 on a running worker; BDD step "worker_agent returns HTTP 200" is satisfiable

---

## Group 13 — Backend BDD Step Definitions

### T031 · Step definitions: job management features
**Agent**: back
**Scope**: `tests/bdd/steps/job_management/`
**Work**:
- Step definitions for: `schedule-job.feature`, `query-job-status.feature`, `cancel-job.feature`, `job-lifecycle-completion.feature`
- Uses real DB (pytest fixture with transaction rollback per scenario)
**AC**: All `@smoke` and `@error-handling` scenarios in the four feature files pass

---

### T032 · Step definitions: worker management features
**Agent**: back
**Scope**: `tests/bdd/steps/worker_management/`
**Work**:
- Step definitions for: `worker-registration.feature`, `job-dispatch.feature`
- Race condition scenario uses two concurrent asyncio tasks
**AC**: All scenarios pass; race condition scenario is deterministic (not flaky)

---

### T033 · Step definitions: operations features
**Agent**: back
**Scope**: `tests/bdd/steps/operations/`
**Work**:
- Step definitions for: `stuck-job-recovery.feature`, `worker-health-monitoring.feature`
- Uses fake `WorkerHealthClient` (returns True or raises, per scenario)
**AC**: All scenarios pass

---

## Group 14 — CI Pipeline — Backend

### T034 · CI: backend test job with coverage gate
**Agent**: ops
**Scope**: `.github/workflows/ci.yml`
**Work**:
- `test-backend` job: spin up PostgreSQL + pgBouncer via Docker Compose; run `alembic upgrade head`; run FK integrity check (ops condition C3); run pytest with `--cov=src/lightcron --cov-fail-under=80`
- Coverage report uploaded as artifact
**AC**: CI passes with ≥ 80% coverage; `alembic check` runs before upgrade (ops condition C2)

---

### T035 · CI: security scanning
**Agent**: ops
**Scope**: `.github/workflows/ci.yml`
**Work**:
- gitleaks in `security` job (ops condition C1)
- bandit with fail-on-high
- pip-audit with fail-on-vulnerability
**AC**: All three tools run; pipeline fails if any secret, high-severity SAST issue, or known vulnerability is found

---

## Group 15 — Frontend

### T036 · Frontend project scaffold
**Agent**: front
**Scope**: `frontend/`
**Work**:
- Vite + React 18 + TypeScript project initialised in `frontend/`
- Dependencies: `react-router-dom`, `@tanstack/react-query`, `axios` (or native fetch)
- Dev dependencies: `typescript`, `eslint`, `prettier`, `playwright`, `@playwright/test`
- `VITE_API_BASE_URL` used as the API base URL (read via `import.meta.env`)
- `frontend/src/shared/constants.ts` with `DASHBOARD_REFRESH_INTERVAL_MS = 10_000`
- `tsconfig.json` with strict mode
**AC**: `npm run dev` starts Vite; `tsc --noEmit` passes; `npm run lint` passes

---

### T037 · Frontend entities: Job and Worker models
**Agent**: front
**Scope**: `frontend/src/entities/job/`, `frontend/src/entities/worker/`
**Work**:
- `job/model.ts`: `Job` interface (all fields from spec Job Response Shape), `JobStatus` enum
- `job/JobStatusBadge.tsx`: coloured pill component; one colour per status
- `worker/model.ts`: `Worker` interface (all fields from spec Worker Response Shape), `WorkerStatus` enum
- `worker/WorkerStatusBadge.tsx`: coloured pill; `online` = green, `offline` = grey
**AC**: TypeScript types match the API response shapes exactly; components render without error

---

### T038 · Frontend shared API client and query hooks
**Agent**: front
**Scope**: `frontend/src/shared/api/`
**Work**:
- `client.ts`: base axios/fetch instance with `baseURL = import.meta.env.VITE_API_BASE_URL`
- `useJobs.ts`: TanStack Query hook; accepts optional `status` filter; `refetchInterval` disabled (set per consumer)
- `useWorkers.ts`: TanStack Query hook; `refetchInterval` disabled
- Both hooks expose `data`, `isLoading`, `isError`
**AC**: Hooks are typed; unit tests with mocked fetch verify data and error states

---

### T039 · Dashboard page — worker fleet panel
**Agent**: front
**Scope**: `frontend/src/widgets/worker-fleet-panel/`, `frontend/src/pages/dashboard/`
**Work**:
- `WorkerFleetPanel` widget: renders a list of worker rows using `Worker` entity; each row shows hostname, status badge, last_seen (relative), running_job_count
- Empty state renders "No workers registered" when list is empty
- `DashboardPage` mounts `WorkerFleetPanel`; wires `useWorkers` with `refetchInterval = DASHBOARD_REFRESH_INTERVAL_MS`
**AC**: AC-J009-01, AC-J009-02, AC-J009-06 satisfied; Playwright tests pass

---

### T040 · Dashboard page — jobs panel with status filter
**Agent**: front
**Scope**: `frontend/src/widgets/jobs-panel/`, `frontend/src/features/filter-jobs/`
**Work**:
- `StatusFilter` feature: dropdown/tabs with all `JobStatus` values + "All"; updates query param
- `JobsPanel` widget: renders list of job rows (job_id, command truncated to 80 chars, status badge, worker_id); wires `useJobs` with active filter and `refetchInterval = DASHBOARD_REFRESH_INTERVAL_MS`
- Empty state renders "No jobs" when list is empty
- `DashboardPage` composes `JobsPanel` below `WorkerFleetPanel`
**AC**: AC-J009-03, AC-J009-04, AC-J009-05, AC-J009-07 satisfied; Playwright tests pass

---

### T041 · Schedule Job page — form and submit
**Agent**: front
**Scope**: `frontend/src/features/schedule-job/`, `frontend/src/pages/schedule-job/`
**Work**:
- `ScheduleJobForm` feature: controlled form with all fields from spec §Schedule Job Page
- Client-side validation on submit: command non-empty; start_time in future; max_runtime/max_memory > 0 if provided
- `useScheduleJob` TanStack Query mutation: POST /jobs; maps API 422 detail to field-level errors
- On success: display job_id; show link with path `/jobs/{job_id}` (page may not exist yet — link is rendered but leads to a placeholder)
- On 422: display server errors inline
- On other errors: display generic top-level message
- `ScheduleJobPage` at route `/jobs/new`
**AC**: AC-J010-01 through AC-J010-07 satisfied; Playwright tests pass

---

### T042 · React Router setup and navigation
**Agent**: front
**Scope**: `frontend/src/app/router.tsx`, `frontend/src/app/main.tsx`
**Work**:
- Routes: `/` → `DashboardPage`, `/jobs/new` → `ScheduleJobPage`
- `QueryClientProvider` wraps the router
- Simple navigation header with links to Dashboard and "Schedule Job"
**AC**: Navigating between pages works; browser back/forward works

---

## Group 16 — Playwright E2E Tests and CI

### T043 · Playwright configuration and test infrastructure
**Agent**: front
**Scope**: `frontend/playwright.config.ts`, `frontend/tests/e2e/`
**Work**:
- Playwright configured to run against `http://localhost:5173` (Vite dev) or a Docker Compose stack
- `globalSetup`: seeds the DB with known state via the scheduler REST API before each test run
- `globalTeardown`: cleans up seeded data
**AC**: `npx playwright test` runs without configuration errors; globalSetup/teardown execute

---

### T044 · Playwright tests: dashboard feature (J009)
**Agent**: front
**Scope**: `frontend/tests/e2e/dashboard.spec.ts`
**Work**:
- E2E tests covering `specs/features/ui/system-dashboard.feature` scenarios
- Smoke scenarios: worker fleet panel, offline worker, jobs panel, status filter
- Error-handling scenarios: empty states
- Auto-refresh test: seeds a job in pending state, waits for dashboard refresh interval, asserts status updated (requires scheduler to be running)
**AC**: All 7 scenarios in `system-dashboard.feature` pass

---

### T045 · Playwright tests: schedule job feature (J010)
**Agent**: front
**Scope**: `frontend/tests/e2e/schedule-job.spec.ts`
**Work**:
- E2E tests covering `specs/features/ui/schedule-job-ui.feature` scenarios
- Smoke: valid submission with required fields; all optional fields
- Error-handling: missing command, past start_time, invalid max_runtime, invalid max_memory, unknown depends_on (server 422)
**AC**: All 7 scenarios in `schedule-job-ui.feature` pass

---

### T046 · CI: Playwright e2e job
**Agent**: ops
**Scope**: `.github/workflows/ci.yml`
**Work**:
- `test-e2e` job: starts full Docker Compose stack (scheduler + DB + pgBouncer + UI); waits for health checks; runs `npx playwright test`
- Playwright test report uploaded as CI artifact
- Job is a hard gate (ops condition C8)
**AC**: CI `test-e2e` job passes; smoke tests run against Docker Compose stack

---

## Implementation Order

```
Group 1  (scaffold)           T001 → T002 → T003
Group 2  (DB + migrations)    T001 → T004 → T005 → T006
Group 3  (scheduler domain)   T004 → T007 → T008 → T009
Group 4  (scheduler API)      T009 → T010 → T011 → T012 → T013 → T014
Group 5  (scheduler DB)       T009 → T015 → T016 → T017
Group 6  (scheduler loops)    T015, T016, T017 → T018 → T019
Group 7  (worker domain)      T004 → T020
Group 8  (worker DB)          T020, T005 → T021 → T022
Group 9  (process manager)    T020 → T023
Group 10 (worker loops)       T021, T022 → T024 → T025
Group 11 (execution)          T023, T025 → T026 → T027 → T028 → T029
Group 12 (worker health)      T020 → T030
Group 13 (BDD steps)          T011–T014, T018, T019, T024–T029 → T031 → T032 → T033
Group 14 (backend CI)         T031–T033 → T034 → T035
Group 15 (frontend)           T002 → T036 → T037 → T038 → T039 → T040 → T041 → T042
Group 16 (e2e + CI)           T042, T010–T014 → T043 → T044 → T045 → T046
```

**Suggested parallel tracks** (after T001–T006 complete):
- **Backend track**: Groups 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14
- **Frontend track**: Groups 15 → 16 (can start once T002 and T010 are done)

---

## Known Limitations (from spec)

These are documented here so BA decisions are visible at the tasklist level. None of these are tasks.

1. Dependency cycle detection — jobs with circular `depends_on` stay `pending` indefinitely. Deferred to v2.
2. Cancel is best-effort — worker must come back online to clean up. Accepted for v1.
3. Memory monitoring latency — up to one poll cycle between breach and detection. Accepted for v1.
4. No job retry — manual requeue only. Out of scope for v1.
5. No authentication — trusted-network only. Out of scope for v1.
