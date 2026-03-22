# Lightcron — Implementation Tasklist v2 (Job Detail Feature)

## Metadata
- **Version**: v2
- **Created**: 2026-03-21
- **Agent**: ba (Phase B)
- **Inputs**: `004_spec_v2.md`, `002_spec_v1.md`, `003_tasklist_v1.md`, `001_solution_envelope_v2.md`
- **Status**: approved_for_build

---

## Conventions

- Task IDs: `T2-{NNN}` — never reuse, never renumber. v1 task IDs (T001–T046) are complete and must not be modified.
- Dependencies: a task may not begin until all listed predecessor tasks are complete.
- Agent assignments: `back` for `src/`, `front` for `frontend/`.
- All timing constants must be imported from `src/lightcron/constants.py` — no numeric literals.
- BDD step functions must be plain `def` (not `async def`); use `db_run()` for DB access.

---

## T2-001 · DB migration: env_vars, peak_memory_mb, base_url

**Agent**: back
**Depends on**: T004 (v1 initial migration must exist as `down_revision`)
**Scope**: `src/migrations/versions/002_job_detail_fields.py`

**Work**:
- Create Alembic migration with `revision = "002"` and `down_revision = "001"`
- Upgrade: `ALTER TABLE jobs ADD COLUMN env_vars JSONB NOT NULL DEFAULT '{}'::jsonb`
- Upgrade: `ALTER TABLE jobs ADD COLUMN peak_memory_mb DOUBLE PRECISION NULL`
- Upgrade: `ALTER TABLE worker_status ADD COLUMN base_url TEXT NULL`
- Downgrade: drops all three columns
- Verify `alembic check` passes after migration

**Acceptance criteria**:
- `alembic upgrade head` on a DB at revision 001 produces all three new columns with correct types and defaults
- `alembic downgrade 001` removes all three columns cleanly
- `alembic check` reports no outstanding migrations (ops condition C2)
- `jobs.env_vars` defaults to `{}` on existing rows (upgrade applies default retroactively)

---

## T2-002 · Constants: add WORKER_DEFAULT_JOBS_DIR

**Agent**: back
**Depends on**: T2-001
**Scope**: `src/lightcron/constants.py`

**Work**:
- Add `WORKER_DEFAULT_JOBS_DIR: str = "/var/logs/lightcron/jobs"` with docstring
- Verify `python -m lightcron.constants` imports without error
- Confirm no other file in `src/` hardcodes the string `/var/logs/lightcron/jobs` (search before writing)

**Acceptance criteria**:
- Constant is importable from `src/lightcron/constants.py`
- Value is exactly `"/var/logs/lightcron/jobs"`
- No string literal of that path exists elsewhere in `src/`

---

## T2-003 · Backend: update domain entities and Pydantic response models

**Agent**: back
**Depends on**: T2-001, T2-002
**Scope**:
- `src/lightcron/scheduler/domain/jobs/entities.py`
- `src/lightcron/scheduler/domain/workers/entities.py`
- `src/lightcron/worker/domain/execution/entities.py`
- `src/lightcron/scheduler/adapters/http/schemas.py`

**Work**:

Scheduler job entity (`scheduler/domain/jobs/entities.py`):
- Add `env_vars: dict[str, str]` field (default `{}`)
- Add `peak_memory_mb: float | None` field (default `None`)

Scheduler worker entity (`scheduler/domain/workers/entities.py`):
- Add `base_url: str | None` field (default `None`)

Worker execution entity (`worker/domain/execution/entities.py`):
- Add `env_vars: dict[str, str]` field
- Add `stdout_path: Path` field (computed from `LIGHTCRON_JOBS_DIR` + `job_id`)
- Add `stderr_path: Path` field (computed from `LIGHTCRON_JOBS_DIR` + `job_id`)

Pydantic schemas (`scheduler/adapters/http/schemas.py`):
- Define `JobSummaryResponse`: all v1 fields plus `env_vars`; no `peak_memory_mb`
- Define `JobDetailResponse`: all `JobSummaryResponse` fields plus `peak_memory_mb`
- Update `WorkerResponse` to add `base_url: str | None`
- Replace the existing single job response model with `JobSummaryResponse` and `JobDetailResponse`

**Acceptance criteria**:
- `mypy --strict` passes on all modified files
- `JobDetailResponse` includes `peak_memory_mb`; `JobSummaryResponse` does not
- `WorkerResponse` includes `base_url`
- `JobExecution` includes `env_vars`, `stdout_path`, `stderr_path`

---

## T2-004 · Backend: update POST /jobs to accept and validate env_vars

**Agent**: back
**Depends on**: T2-003
**Scope**:
- `src/lightcron/scheduler/adapters/http/jobs_router.py`
- `src/lightcron/scheduler/domain/jobs/services/job_service.py`
- `src/lightcron/scheduler/adapters/db/job_repo.py`

**Work**:

Request model:
- Add optional `env_vars: dict[str, str]` field with default `{}`
- Add Pydantic validator: all keys strings, all values strings, max 100 keys, key ≤ 256 chars, value ≤ 4096 chars
- Return HTTP 422 on any violation with error pointing to `env_vars` field

Domain service (`schedule_job`):
- Accept `env_vars` parameter; pass through to repository

DB adapter:
- Include `env_vars` in the INSERT statement (serialize to JSONB)

Response:
- POST /jobs now returns `JobSummaryResponse` (includes `env_vars`, excludes `peak_memory_mb`)

**Acceptance criteria** (BDD):
- AC-V2-B01: valid env_vars stored and returned
- AC-V2-B02: missing env_vars defaults to `{}`
- AC-V2-B03: non-string value in env_vars returns 422 with error on `env_vars`
- Existing schedule-job.feature scenarios continue to pass

---

## T2-005 · Backend: update GET /jobs/{job_id}, GET /jobs, GET /workers responses

**Agent**: back
**Depends on**: T2-003
**Scope**:
- `src/lightcron/scheduler/adapters/http/jobs_router.py`
- `src/lightcron/scheduler/adapters/http/workers_router.py`
- `src/lightcron/scheduler/adapters/db/job_repo.py`
- `src/lightcron/scheduler/adapters/db/worker_repo.py`

**Work**:

GET /jobs/{job_id}:
- Return `JobDetailResponse` (includes `peak_memory_mb`)
- DB adapter reads `peak_memory_mb` and `env_vars` from the `jobs` row

GET /jobs (list):
- Return list of `JobSummaryResponse` (includes `env_vars`, excludes `peak_memory_mb`)
- DB adapter must not read `peak_memory_mb` in the list query (efficiency)

GET /workers:
- Return list of workers including `base_url` field
- DB adapter reads `base_url` from `worker_status` rows

**Acceptance criteria** (BDD):
- AC-V2-B04: GET /jobs/{job_id} returns `peak_memory_mb`
- AC-V2-B05: GET /jobs list items do not contain `peak_memory_mb`
- AC-V2-B06: GET /workers item with base_url set returns correct value
- AC-V2-B07: GET /workers item without base_url returns `null`
- Existing query-job-status and worker-health-monitoring scenarios continue to pass

---

## T2-006 · Worker agent: jobs directory, file output, env_vars passthrough, peak_memory_mb, base_url registration

**Agent**: back
**Depends on**: T2-003
**Scope**:
- `src/lightcron/worker/domain/execution/services/registration_service.py`
- `src/lightcron/worker/domain/execution/services/execution_service.py`
- `src/lightcron/worker/adapters/db/worker_status_db.py`
- `src/lightcron/worker/adapters/db/job_db.py`
- `src/lightcron/worker/adapters/process/subprocess_adapter.py`
- `src/lightcron/worker/main.py`

**Work**:

Jobs directory setup (`main.py` or `registration_service.py`):
- On startup, read `LIGHTCRON_JOBS_DIR` from env; fall back to `WORKER_DEFAULT_JOBS_DIR`
- Call `os.makedirs(jobs_dir, exist_ok=True)`; if it fails, log and exit

Worker registration (`registration_service.py`, `worker_status_db.py`):
- Read `LIGHTCRON_WORKER_BASE_URL` env var; default `None`
- Include `base_url` in the upsert INSERT/UPDATE SQL (spec §4.4)

Claim DB adapter (`job_db.py`):
- `claim_job` reads `env_vars` from the claimed row and populates `JobExecution.env_vars`
- Compute `stdout_path` and `stderr_path` from `LIGHTCRON_JOBS_DIR` and `job_id`

Subprocess adapter (`subprocess_adapter.py`):
- `start(command, env_vars, stdout_path, stderr_path)`: merge env, open file handles, spawn
- Subprocess `env = {**os.environ, **env_vars}`
- `stdout=open(stdout_path, "w")`, `stderr=open(stderr_path, "w")`
- Close file handles on process exit in finally block

Execution service (`execution_service.py`):
- Track `peak_memory_mb: float = 0.0` per job
- On each poll cycle: `rss = psutil.Process(pid).memory_info().rss / 1024 / 1024`; update running max
- Include `peak_memory_mb` in all terminal-state DB writes (UPDATE ... SET peak_memory_mb = $peak_memory_mb ...)
- Handle `psutil.NoSuchProcess` gracefully (use last-known peak)

`update_status` DB adapter (`job_db.py`):
- Accept optional `peak_memory_mb: float | None = None`
- Include in UPDATE when provided; apply terminal-state guard (WHERE status NOT IN (...))

**Acceptance criteria** (BDD):
- AC-V2-B08: stdout and stderr files written during job execution
- AC-V2-B09: defaults to WORKER_DEFAULT_JOBS_DIR when env var unset
- AC-V2-B10: partial output retained after kill; files not deleted
- AC-V2-B14: base_url registered at startup
- AC-V2-B15: re-registration updates base_url; worker_id preserved
- Existing job-lifecycle-completion.feature scenarios continue to pass
- peak_memory_mb is non-null in the DB after job completion (verifiable via GET /jobs/{job_id})

---

## T2-007 · Worker REST API: GET /jobs/{job_id}/stdout and /stderr, CORS

**Agent**: back
**Depends on**: T2-002
**Scope**: `src/lightcron/worker/adapters/http/health_api.py` (or new router file if preferred)

**Work**:

New endpoints on the worker FastAPI app:

```
GET /jobs/{job_id}/stdout
GET /jobs/{job_id}/stderr
```

For each:
- Compute `path = LIGHTCRON_JOBS_DIR / f"{job_id}.{stream}"`
- If file exists: return `PlainTextResponse(path.read_text())` with status 200
- If file does not exist: raise `HTTPException(status_code=404, detail="Not found")`
- `LIGHTCRON_JOBS_DIR` read from env var; default `WORKER_DEFAULT_JOBS_DIR`

CORS:
- Add `CORSMiddleware` to the worker FastAPI app
- `allow_origins = [os.environ.get("LIGHTCRON_UI_ORIGIN", "")]` — no wildcard
- `allow_methods = ["GET"]`
- `allow_headers = ["*"]`

**Acceptance criteria** (BDD):
- AC-V2-B11: GET /jobs/{job_id}/stdout → 200 text/plain with file contents
- AC-V2-B12: GET /jobs/{job_id}/stderr → 200 text/plain with file contents
- AC-V2-B13: missing file → 404 `{"detail": "Not found"}`
- CORS headers present for `LIGHTCRON_UI_ORIGIN` origin on both endpoints

---

## T2-008 · BDD tests: all new backend behaviour

**Agent**: back
**Depends on**: T2-004, T2-005, T2-006, T2-007
**Scope**: `tests/bdd/steps/` (extend existing step files or add new ones as appropriate)

**Work**:

Write or extend step definitions covering all 15 backend ACs (AC-V2-B01 through AC-V2-B15).

Step file placement:
- `env_vars` scheduling steps: extend `tests/bdd/steps/job_management/` (alongside T031 steps)
- `peak_memory_mb`, output files, env_vars passthrough: extend `tests/bdd/steps/job_management/`
- Worker REST API steps (stdout/stderr serve, 404): add to `tests/bdd/steps/job_management/` or a new `tests/bdd/steps/worker_api/` file
- `base_url` registration steps: extend `tests/bdd/steps/worker_management/`

All step functions: plain `def`; DB access via `db_run()`; HTTP via `TestClient`.

For output file tests: use a temporary directory (pytest `tmp_path` fixture) as `LIGHTCRON_JOBS_DIR`; create/read files directly in steps.

For worker REST API tests: start the worker FastAPI app via `TestClient` in the step's `given` background; configure `LIGHTCRON_JOBS_DIR` to a temp path.

**Acceptance criteria**:
- All 15 AC-V2-B01–AC-V2-B15 scenarios pass with `pytest -m smoke` and full suite
- No `async def` step functions
- No hardcoded paths — all use `WORKER_DEFAULT_JOBS_DIR` constant or `tmp_path` fixture

---

## T2-009 · Frontend: update Job and Worker entity types; add useJob and useJobOutput hooks

**Agent**: front
**Depends on**: T2-003 (backend models must be finalised first so TypeScript types can match)
**Scope**:
- `frontend/src/entities/job/model.ts`
- `frontend/src/entities/worker/model.ts`
- `frontend/src/shared/api/useJob.ts` (new)
- `frontend/src/shared/api/useJobOutput.ts` (new)
- `frontend/src/shared/constants.ts`

**Work**:

`entities/job/model.ts`:
- Add `env_vars: Record<string, string>` to `Job` interface
- Add `peak_memory_mb?: number | null` to `Job` interface (optional to accommodate list vs detail)

`entities/worker/model.ts`:
- Add `base_url: string | null` to `Worker` interface

`shared/constants.ts`:
- Add `export const JOB_DETAIL_REFRESH_INTERVAL_MS: number = 5_000`

`shared/api/useJob.ts`:
- TanStack Query hook for `GET /jobs/{jobId}`
- Returns `JobDetailResponse` typed as `Job` (with `peak_memory_mb` present)
- `refetchInterval`: `JOB_DETAIL_REFRESH_INTERVAL_MS` while job is non-terminal; disabled once terminal
- Terminal statuses: `completed | failed | cancelled | lost`
- Exposes `{ data, isLoading, isError, error }`

`shared/api/useJobOutput.ts`:
- Accepts `{ baseUrl: string | null, jobId: string, stream: 'stdout' | 'stderr' }`
- Disabled (`enabled: false`) when `baseUrl` is null or job is non-terminal
- On 200: `data = responseText`, `isOffline = false`
- On 404: `data = null`, `isOffline = false`
- On network error / other: `data = null`, `isOffline = true`
- Does not auto-refresh (terminal output is stable)

**Acceptance criteria**:
- `tsc --noEmit` passes
- `useJob` re-fetches every `JOB_DETAIL_REFRESH_INTERVAL_MS` for non-terminal jobs and stops on terminal
- `useJobOutput` is not called while job is non-terminal
- `useJobOutput` returns `isOffline: true` on network error, `isOffline: false` on 404

---

## T2-010 · Frontend: job detail page; dashboard job rows clickable

**Agent**: front
**Depends on**: T2-009
**Scope**:
- `frontend/src/pages/job-detail/JobDetailPage.tsx` (new)
- `frontend/src/app/router.tsx`
- `frontend/src/widgets/jobs-panel/index.tsx`

**Work**:

`JobDetailPage.tsx`:
- Route param: `job_id` via `useParams()`
- Uses `useJob(job_id)` and `useWorkers()` hooks
- Derives worker `base_url` by finding the worker matching `job.worker_id` in the workers list
- Uses `useJobOutput({ baseUrl, jobId, stream: 'stdout' })` and `useJobOutput({ baseUrl, jobId, stream: 'stderr' })`
- Renders seven sections as per spec §7.5:
  1. Header (job_id monospace, `JobStatusBadge`)
  2. Summary (command, worker, created_at, claimed_at, started_at, finished_at)
  3. Runtime and Resources (actual runtime with live counter for running jobs; peak_memory; max limits; kill_reason warning banner)
  4. Environment Variables (key/value table or "No environment variables")
  5. Output (stdout and stderr blocks with all state variants per spec §7.5 Section 5)
  6. Dependencies (links or "No dependencies")
- Error states: 404 → "Job not found" + dashboard link; network error → "Could not load job" + retry

Live elapsed time:
- Use `setInterval` (or equivalent React hook) to increment display every 1000ms
- Reads from `job.started_at`; stops updating when `finished_at` is set

`router.tsx`:
- Add `/jobs/:job_id` → `<JobDetailPage />`

`widgets/jobs-panel/index.tsx`:
- Wrap each job row (or make it) a React Router `<Link to={`/jobs/${job.job_id}`}>` element

**Acceptance criteria**:
- `tsc --noEmit` passes
- `npm run lint` passes
- AC-V2-F01 through AC-V2-F19 verifiable via Playwright (tested in T2-011)
- Live counter increments on running jobs; does not render for pending/assigned jobs
- kill_reason warning banner visible only when `kill_reason` is non-null
- stdout and stderr blocks visually distinguished

---

## T2-011 · Frontend: Playwright e2e tests for job-detail.feature

**Agent**: front
**Depends on**: T2-010
**Scope**: `frontend/tests/e2e/job-detail.spec.ts` (new)

**Work**:

Write Playwright tests covering all 18 scenarios in `specs/features/ui/job-detail.feature` and the dashboard navigation scenario (AC-V2-F19).

Test infrastructure:
- Seed jobs (completed, running, failed, pending) via the scheduler REST API in test setup
- For output file tests: pre-create files in the worker's `LIGHTCRON_JOBS_DIR` or use a mock worker REST API (MSW or a test double FastAPI app)
- For worker offline test: simulate network error on worker URL (Playwright `route` intercept or disabled worker service)
- For `base_url` discovery test: verify the URL the UI requests against (Playwright `page.on('request', ...)` or route intercept)

Scenarios to cover (one Playwright test per scenario or scenario outline):
1. Core fields for completed job (AC-V2-F01, AC-V2-F02)
2. Peak memory for completed job (AC-V2-F04)
3. Live elapsed time for running job (AC-V2-F03)
4. Peak memory placeholder for pending job (AC-V2-F05)
5. Stdout fetched and shown from worker API (AC-V2-F06)
6. Stderr fetched and shown, visually distinguished (AC-V2-F08)
7. 404 stdout → "No output" (AC-V2-F07)
8. 404 stderr → "No output" (AC-V2-F09)
9. Running job → "job in progress"; no worker fetch (AC-V2-F14)
10. Worker offline → "Worker offline — logs unavailable" on both streams (AC-V2-F17)
11. Kill reason warning banner (AC-V2-F10)
12. env_vars key/value table (AC-V2-F11)
13. Empty env_vars → "No environment variables" (AC-V2-F12)
14. Unknown job_id → "Job not found" (AC-V2-F13)
15. Auto-refresh updates status and fetches output (AC-V2-F15)
16. base_url used to construct worker log URL (AC-V2-F18)
17. Dashboard job row click navigates to detail page (AC-V2-F19)
18. env_vars passed to subprocess (AC-V2-F16) — verify via stdout file content

**Acceptance criteria**:
- All 18 Playwright tests pass against the Docker Compose stack
- `@smoke` scenarios pass with `--grep @smoke` flag subset
- No test sleeps without purpose — use `waitFor` / polling assertions
- Tests are deterministic (no flaky timing)

---

## Implementation Order

```
T2-001 (DB migration)
  └── T2-002 (constant)
        └── T2-003 (entities + schemas)
              ├── T2-004 (POST /jobs env_vars)
              ├── T2-005 (GET responses)
              ├── T2-006 (worker agent execution)
              └── T2-007 (worker REST API)  ← also depends on T2-002 directly

After T2-004 + T2-005 + T2-006 + T2-007:
  └── T2-008 (BDD tests — all backend ACs)

After T2-003:
  └── T2-009 (frontend entities + hooks)
        └── T2-010 (job detail page + dashboard rows)
              └── T2-011 (Playwright e2e tests)
```

**Parallel tracks** (after T2-003 is complete):

- **Backend track**: T2-004 → T2-005 → T2-006 → T2-007 → T2-008 (sequential; each task builds on the previous)
- **Frontend track**: T2-009 → T2-010 → T2-011 (sequential; can start once T2-003 backend models are finalised)

T2-007 (worker REST API) can proceed in parallel with T2-004/T2-005/T2-006 since it only depends on T2-002.

---

## Known Limitations (additions to v1 tasklist)

These are documented decisions, not tasks:

6. Output file accumulation on worker nodes — no cleanup mechanism. Operators manage disk manually. Deferred to v3.
7. Permanent log loss if worker node is decommissioned — accepted trade-off of file-based approach. Central log store deferred to v3.
8. No env_vars size limit on total payload — only per-key and per-value limits plus max 100 keys. Accepted for v1.
