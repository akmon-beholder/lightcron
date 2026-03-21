# lightcron — Solution Envelope

## Metadata
- **Project Slug**: lightcron
- **Version**: v2
- **Created**: 2026-03-21
- **Updated**: 2026-03-21 — v2: added web UI (J009, J010); lightcron-ui deployable unit; frontend stack
- **Status**: ready_for_ba
- **Lifecycle Mode**: lean

---

## Problem Statement

Lightcron is a lightweight job orchestration system. Users schedule jobs via a REST API or a web dashboard, specifying a command to run, a start time, optional resource limits, and optional dependencies on other jobs. Worker agents running on separate nodes poll a shared PostgreSQL database for jobs to claim and execute. The scheduler service maintains job lifecycle state and worker liveness. There is no message broker — the database is the sole communication bus between all system components. A React web UI provides a dashboard view of system state and a form to submit jobs.

---

## Constraints & Inputs

- **Language**: Python 3.12+
- **Architecture**: Hexagonal (ports and adapters) — backend; Feature-Sliced Design (FSD) — frontend
- **Database**: PostgreSQL 16+ — single source of truth; no external queue or broker
- **Connection pooling**: pgBouncer in session mode (required for `SELECT FOR UPDATE SKIP LOCKED`)
- **Single-tenant**: one organisation, one deployment
- **Hosting**: TBD — no production target defined yet (see DevOps condition C6)
- **Auth**: out of scope for v1 — noted as P2 in lens assessment
- **UI**: React/TypeScript SPA; communicates with the scheduler REST API only

---

## Personas & Roles

| Role | Description |
|---|---|
| `job_submitter` | Calls the scheduler REST API (or web UI) to schedule, query, and cancel jobs |
| `platform_operator` | Manages the Lightcron deployment and worker fleet; primary web UI user |
| `sre_operator` | Responds to incidents; uses web UI dashboard for at-a-glance system health |
| `worker_agent` | Process on each worker node; reads/writes DB directly via pgBouncer |
| `scheduler` | Central service; serves REST API and runs background loops |

---

## In Scope

- Job scheduling via REST API (command, start_time, depends_on, max_runtime, max_memory)
- Pull-based job claiming by worker agents via atomic DB operation
- Job lifecycle: pending → ready → assigned → running → completed / failed / cancelled / lost
- Worker registration and liveness via DB (worker_status table + two-stage /health probe)
- Dependency resolution: scheduler marks jobs `ready` only when all depends_on are `completed`
- Resource limit enforcement: max_runtime and max_memory (SIGTERM → grace → SIGKILL)
- Stuck job recovery: `lost` status when worker heartbeat expires
- Zombie process cleanup: worker_agent kills process if it reconnects and finds its job is `lost`
- Job cancellation via REST API; worker_agent detects on next poll
- Worker fleet status via REST API (GET /workers)
- Web UI dashboard: worker fleet panel + jobs panel with status filter + auto-refresh (J009)
- Web UI schedule job form: submit jobs via form with inline validation (J010)
- Local Docker Compose development environment

## Out of Scope (v1)

- REST API authentication / authorisation
- Job retry on failure (manual requeue only)
- Job priority or weighted scheduling
- Multi-tenancy
- Production hosting / deployment automation (pending target decision)
- Job output streaming or log capture
- Recurring / cron-style schedules (each run is a discrete job)
- Job cancellation mid-process on the worker (cancel is best-effort; detected on next poll cycle)

---

## Core User Flows

### F1: Schedule and Execute a Job (J001 → J003 → J004)
Job submitter POSTs to `/jobs` → scheduler stores as `pending` → scheduler background loop marks `ready` when conditions met → worker_agent claims atomically → starts process → process exits → worker_agent writes `completed`/`failed`.

### F2: Worker Node Lifecycle (J002)
worker_agent starts → upserts `worker_status` row with hostname → updates `last_seen` every 30s → scheduler health-check loop monitors `last_seen` → two-stage liveness (60s: call `/health`; 90s: mark `offline` and jobs `lost`).

### F3: Cancel a Job (J005)
Operator calls `POST /jobs/{job_id}/cancel` → scheduler writes `cancelled` to jobs table → if job was `running`, worker_agent detects on next poll and stops process.

### F4: Stuck Job Recovery (J008)
Worker heartbeat expires → scheduler writes `offline` to `worker_status`, `lost` to affected jobs → if worker reconnects with same worker_id, it detects `lost` on any process it is still running and kills it.

### F5: View System State (J009)
Operator opens web dashboard → UI fetches GET /workers and GET /jobs → renders worker fleet panel and jobs panel → optional status filter → auto-refreshes on interval.

### F6: Schedule a Job via UI (J010)
Operator opens Schedule Job page → fills form (command, start_time, optional fields) → UI validates client-side → UI POSTs to `/jobs` → displays job_id on success or inline errors on failure.

---

## Key Domain Objects

### Job
```
job_id          UUID, PK
command         TEXT NOT NULL
start_time      TIMESTAMPTZ NOT NULL
depends_on      UUID[] DEFAULT '{}'
max_runtime     INTEGER NULL  -- seconds; NULL = unlimited
max_memory      INTEGER NULL  -- MB; NULL = unlimited
status          job_status NOT NULL DEFAULT 'pending'
worker_id       UUID NULL REFERENCES worker_status(worker_id)
exit_code       INTEGER NULL
kill_reason     TEXT NULL     -- 'max_runtime_exceeded' | 'max_memory_exceeded'
claimed_at      TIMESTAMPTZ NULL
started_at      TIMESTAMPTZ NULL
finished_at     TIMESTAMPTZ NULL
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

### Worker
```
worker_id       UUID, PK
hostname        TEXT NOT NULL UNIQUE
status          worker_status NOT NULL DEFAULT 'online'
last_seen       TIMESTAMPTZ NOT NULL DEFAULT now()
registered_at   TIMESTAMPTZ NOT NULL DEFAULT now()
```

### Enums
```
job_status:     pending | ready | assigned | running | completed | failed | cancelled | lost
worker_status:  online | offline
```

---

## Policy & Rules Candidates

- A job may not be cancelled if its status is terminal (`completed`, `failed`, `lost`) → HTTP 409
- A job's `depends_on` list may only reference job_ids that exist at submission time → HTTP 422
- `max_runtime` and `max_memory` must be positive integers if provided → HTTP 422
- `start_time` must be in the future at submission time → HTTP 422
- Only one worker_agent may hold a job in `assigned` or `running` state at any time (enforced by atomic claim)
- The scheduler's write of `lost` is authoritative — a reconnecting worker_agent must not overwrite it
- A worker_agent must kill any process it is still running if the corresponding job is `lost` in the DB
- Worker identity is hostname-based: same hostname → same worker_id on reconnection
- Web UI communicates exclusively via the scheduler REST API — no direct DB access from the browser

---

## Architecture Proposal

### Deployable Units

| Unit | Description |
|---|---|
| `lightcron-scheduler` | FastAPI app + background loops (ready-transition, health-check) |
| `lightcron-worker` | Worker agent process + FastAPI /health endpoint |
| `lightcron-ui` | React/TypeScript SPA; served as static files (Nginx or scheduler static mount) |

All three units live in the same repository. The UI is a separate build artifact with its own entry point.

### Hexagonal Component Map — Backend

```
lightcron-scheduler
├── domain/
│   ├── jobs/
│   │   ├── entities.py          Job, JobStatus (enum)
│   │   └── services/
│   │       ├── job_service.py   schedule_job, cancel_job, get_job, list_jobs
│   │       └── dispatch_service.py  ready_transition_loop, health_check_loop
│   └── workers/
│       ├── entities.py          Worker, WorkerStatus (enum)
│       └── services/
│           └── worker_service.py  list_workers
├── ports/
│   ├── job_repository.py        Protocol: get, save, update_status, list_ready, list_by_worker
│   ├── worker_repository.py     Protocol: get_by_hostname, save, mark_offline, list_stale
│   ├── worker_health_client.py  Protocol: check_health(worker_id) -> bool
│   └── determinism/             TimePort, UUIDPort (already scaffolded)
└── adapters/
    ├── http/
    │   └── api.py               FastAPI routes + /health + CORS for UI
    ├── db/
    │   ├── job_repo.py          PostgreSQL JobRepository
    │   └── worker_repo.py       PostgreSQL WorkerRepository
    └── health/
        └── worker_health_client.py  httpx client calling worker /health

lightcron-worker
├── domain/
│   ├── execution/
│   │   ├── entities.py          JobExecution
│   │   └── services/
│   │       ├── claim_service.py      poll + atomic claim loop
│   │       ├── execution_service.py  start, monitor, kill process
│   │       └── registration_service.py  upsert + last_seen loop
├── ports/
│   ├── job_db.py                Protocol: claim_job, update_status, poll_assigned, check_status
│   ├── worker_status_db.py      Protocol: upsert_worker, update_last_seen
│   └── process_manager.py       Protocol: start, kill, poll_exit, get_memory_usage
│   └── determinism/             TimePort (shared)
└── adapters/
    ├── db/
    │   ├── job_db.py            asyncpg job reads/writes
    │   └── worker_status_db.py  asyncpg worker_status reads/writes
    ├── process/
    │   └── subprocess_adapter.py  subprocess + psutil
    └── http/
        └── health_api.py        FastAPI GET /health
```

### FSD Component Map — Frontend

```
lightcron-ui (React 18 / TypeScript / Vite)
├── app/
│   ├── main.tsx                 Entry point; React Query provider
│   ├── router.tsx               React Router routes
│   └── styles/                  Global CSS / design tokens
├── pages/
│   ├── dashboard/               Route: /
│   │   └── DashboardPage.tsx    Composes WorkerFleetWidget + JobsPanelWidget
│   └── schedule-job/            Route: /jobs/new
│       └── ScheduleJobPage.tsx  Renders ScheduleJobForm feature
├── widgets/
│   ├── worker-fleet-panel/
│   │   └── WorkerFleetPanel.tsx Displays list of WorkerCard entities
│   └── jobs-panel/
│       └── JobsPanel.tsx        Displays list of JobRow entities + status filter
├── features/
│   ├── schedule-job/
│   │   ├── ScheduleJobForm.tsx  Controlled form; calls useScheduleJob hook
│   │   └── useScheduleJob.ts    TanStack Query mutation → POST /jobs
│   └── filter-jobs/
│       └── StatusFilter.tsx     Controlled filter; updates jobs panel query
├── entities/
│   ├── job/
│   │   ├── model.ts             Job type, JobStatus enum
│   │   └── JobStatusBadge.tsx   Coloured status pill component
│   └── worker/
│       ├── model.ts             Worker type, WorkerStatus enum
│       └── WorkerStatusBadge.tsx
└── shared/
    ├── api/
    │   ├── client.ts            Axios/fetch base client; base URL from env
    │   ├── useJobs.ts           TanStack Query: GET /jobs (with status filter)
    │   └── useWorkers.ts        TanStack Query: GET /workers
    └── ui/
        └── EmptyState.tsx       Reusable empty state component
```

### Ports (key protocols)

| Port | Direction | Notes |
|---|---|---|
| `JobRepository` | Outbound (scheduler) | Read/write jobs table |
| `WorkerRepository` | Outbound (scheduler) | Read/write worker_status table |
| `WorkerHealthClient` | Outbound (scheduler) | HTTP GET /health on worker |
| `JobDB` | Outbound (worker) | Claim + status updates on jobs table |
| `WorkerStatusDB` | Outbound (worker) | Register + last_seen on worker_status |
| `ProcessManager` | Outbound (worker) | Start/kill OS processes, read memory |
| `TimePort` | Outbound (both) | Deterministic clock (already in src/domain/ports/) |
| `UUIDPort` | Outbound (scheduler) | Deterministic UUID generation |

### Claim Atomicity

Worker agents claim jobs using:
```sql
SELECT job_id FROM jobs
WHERE status = 'ready'
ORDER BY start_time ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;

UPDATE jobs
SET status = 'assigned', worker_id = $1, claimed_at = now()
WHERE job_id = $2 AND status = 'ready';
```
The UPDATE rowcount is checked: 0 rows = lost race, try next candidate.
This requires pgBouncer `pool_mode = session`.

### Shared Constants Module

All timing constants are defined once in `src/lightcron/constants.py` and imported by both the scheduler and worker agent packages. They are hardcoded for v1; future deployments may override them via a DB configuration table.

```python
# src/lightcron/constants.py

# Scheduler loops
READY_TRANSITION_INTERVAL_SECONDS: int = 10   # How often scheduler checks pending → ready
HEALTH_CHECK_INTERVAL_SECONDS: int = 30        # How often scheduler checks worker liveness

# Worker agent loops
CLAIM_POLL_INTERVAL_SECONDS: int = 5           # How often worker polls for ready jobs
JOB_STATUS_POLL_INTERVAL_SECONDS: int = 5      # How often worker checks for cancel/lost
LAST_SEEN_UPDATE_INTERVAL_SECONDS: int = 30    # How often worker updates worker_status.last_seen

# Worker liveness thresholds (must be consistent with LAST_SEEN_UPDATE_INTERVAL)
WORKER_HEALTH_PROBE_THRESHOLD_SECONDS: int = 60   # Stage 1: call /health
WORKER_OFFLINE_THRESHOLD_SECONDS: int = 90         # Stage 2: mark offline + jobs lost

# Process lifecycle
SIGTERM_GRACE_PERIOD_SECONDS: int = 30         # Wait after SIGTERM before SIGKILL
```

### Background Loop Cadence

| Loop | Owner | Interval (constant) |
|---|---|---|
| Ready-transition | Scheduler | 10s (`READY_TRANSITION_INTERVAL_SECONDS`) |
| Health-check | Scheduler | 30s (`HEALTH_CHECK_INTERVAL_SECONDS`) |
| Claim poll | Worker agent | 5s (`CLAIM_POLL_INTERVAL_SECONDS`) |
| Last-seen update | Worker agent | 30s (`LAST_SEEN_UPDATE_INTERVAL_SECONDS`) |
| Job status poll | Worker agent | 5s (`JOB_STATUS_POLL_INTERVAL_SECONDS`) |

---

## Adjacent Impact Zones

| Component | Primary Scope | Adjacent Zones | Recommendation |
|---|---|---|---|
| Claim loop | `jobs` table | `worker_status` (read to enforce concurrency limit N) | Include in scope — same transaction boundary |
| Health-check loop | `worker_status` | `jobs` (write `lost`) | Include in scope — same service |
| Process manager | OS subprocess | psutil memory polling | Include in scope — same adapter |
| Alembic migrations | DB schema | pgBouncer config (session mode dependency) | Document only — ops concern |
| Worker concurrency | Claim loop | `jobs` (count running jobs for this worker_id before claiming) | Include in scope — pre-claim guard |
| Scheduler CORS config | FastAPI adapter | Web UI origin | Include in scope — required for UI to call API in dev |

---

## Security & Privacy

### Threats & Controls

| Threat | Control |
|---|---|
| Unauthenticated job submission | Out of scope v1; API is trusted-network only |
| Secrets in job commands | No log capture of command content; noted as risk |
| Worker impersonation | Hostname-based identity; only mitigated by network trust in v1 |
| DB credential exposure | Credentials via environment variables only; never in code |
| Secret leakage in CI | gitleaks secret detection in CI pipeline (ops condition C1) |
| Runaway process consuming all resources | max_runtime / max_memory limits; SIGTERM → SIGKILL |
| Cross-origin requests from UI | CORS configured on scheduler to allow UI dev origin; restrict in production |

### Notes
- All timestamps stored and compared in UTC
- No PII expected in job definitions (commands are system paths + args)
- DB connection strings must not appear in logs
- UI base URL configured via environment variable (no hardcoded origins)

---

## Operational Reality

- **Multiple scheduler instances**: The ready-transition loop must use `SELECT FOR UPDATE` or a PostgreSQL advisory lock to prevent two scheduler instances from racing to mark the same job `ready`. Design for HA from the start even if v1 runs one instance.
- **pgBouncer session mode**: Required for `SELECT FOR UPDATE SKIP LOCKED`. Must be enforced by config, not convention (ops condition C5). Integration tests must validate that transaction-mode connections fail the lock test.
- **Memory monitoring**: psutil polls memory usage; there is a latency window between limit breach and detection. This is acceptable for v1.
- **Process group management**: The process adapter must kill the process group (not just the process) to prevent orphaned child processes.
- **Clock skew**: All time comparisons use DB server time (`now()`) for consistency. Worker agents should not use local system time for job timing decisions.
- **Poll interval latency**: Pull-based claiming introduces latency between a job becoming `ready` and a worker claiming it. This is an accepted trade-off for v1.
- **UI served as static files**: The React build output is served by Nginx (or mounted as static files on the scheduler in dev). No SSR.

---

## DevOps Approval

```yaml
devops_approval:
  verdict: APPROVED_WITH_CONDITIONS
  approved_by: ops
  date: "2026-03-21"
  canonical_stack:
    language: python
    version: "3.12"
    api_framework: fastapi
    db: postgresql
    db_version: "16"
    db_driver: asyncpg
    query_layer: sqlalchemy-core-async
    migrations: alembic
    connection_pool: pgbouncer
    pool_mode: session
    testing: pytest + pytest-bdd
    lint: ruff
    type_check: mypy
    sast: bandit
    secret_detection: gitleaks
    dependency_scan: pip-audit
    containerisation: docker-compose
    ci: github-actions
    coverage_threshold: 80
    frontend_framework: react
    frontend_version: "18"
    frontend_language: typescript
    frontend_tooling: vite
    frontend_data_fetching: tanstack-query
    frontend_routing: react-router
    frontend_testing: playwright
    frontend_lint: eslint + prettier
    frontend_type_check: tsc --noEmit
  conditions:
    - id: C1
      description: "Add gitleaks to CI pipeline for secret detection"
      gate: hard
    - id: C2
      description: "Run alembic check before alembic upgrade head in CI and deploy"
      gate: hard
    - id: C3
      description: "Post-migration FK integrity validation required"
      gate: hard
    - id: C4
      description: "Scheduler service must expose GET /health (not just worker agent)"
      gate: hard
    - id: C5
      description: "pgBouncer pool_mode=session must be enforced by config; integration test must validate"
      gate: hard
    - id: C6
      description: "Production environment TBD; no prod deployment automation until hosting decided"
      gate: documentation
    - id: C7
      description: "CORS origin for UI must be explicitly configured via env var; no wildcard '*' in production"
      gate: hard
    - id: C8
      description: "Playwright e2e tests must run in CI against a Docker Compose stack (scheduler + DB); coverage not required for UI but smoke tests are"
      gate: hard
  non_negotiables_verified: true
```

---

## Gotchas & Ambiguities

1. **Multiple scheduler instances**: The ready-transition loop needs coordination (advisory lock or row-level lock) to be safe at >1 instance. Even if v1 runs one, the code must not assume singleness.

2. **pgBouncer + SELECT FOR UPDATE**: Transaction pooling silently breaks the atomic claim. The integration test for claiming must use a pgBouncer connection (not a direct DB connection) to catch misconfiguration.

3. **psutil and process groups**: `psutil` on Linux requires the process adapter to kill the process group (`os.killpg`) to catch forking processes. Tests on the target OS are essential.

4. **Cancel vs lost race**: A job could be simultaneously cancelled by a user and marked `lost` by the health-check loop. Both writes target the same row. The DB update must use a terminal-state guard: `WHERE status NOT IN ('completed', 'failed', 'cancelled', 'lost')` to make both writes idempotent.

5. **Dependency cycle detection (accepted limitation)**: Nothing in v1 prevents a job from declaring a circular dependency. The ready-transition loop will never mark such jobs `ready`; they will remain `pending` indefinitely. This is accepted for v1 — BA should document it as a known limitation in the spec, not a task.

6. **UI auto-refresh and stale data**: TanStack Query's `refetchInterval` is the recommended mechanism. The interval value should be documented in a UI constants file (separate from the backend `constants.py`). Default suggested: 10s for dashboard data.

---

## Open Questions (Blocking)

None — all OQs resolved. See Gotchas for accepted limitations.

---

## BA Handoff Instructions

**Lifecycle mode: lean** — BA produces spec and tasklist; no separate quality gates artifact required unless BA judges complexity warrants it.

**Artifacts to produce:**
- `002_spec_v1.md` — Full functional spec covering all 10 journeys
- `003_tasklist_v1.md` — Implementation tasks ordered per suggested sequence

**Must include in spec:**
- All constant values from `src/lightcron/constants.py` (all OQs resolved)
- All 8 ops conditions (C1–C8) as explicit tasks in the tasklist
- Gotcha #1 (multiple scheduler instances) as an acceptance criterion on the health-check loop
- Gotcha #4 (cancel/lost race) as an acceptance criterion
- Gotcha #5 (dependency cycles) as a documented known limitation (not a task)
- Gotcha #6 (UI auto-refresh) as a UI constants decision in the spec
- CORS configuration as a task (ops condition C7)

**Suggested task groupings for tasklist:**
1. Project scaffold (pyproject.toml, Docker Compose, CI skeleton)
2. DB schema + Alembic migrations + pgBouncer config
3. Scheduler: domain + ports + DB adapters
4. Scheduler: REST API (with CORS config)
5. Scheduler: background loops (ready-transition, health-check)
6. Worker agent: domain + ports + DB adapters
7. Worker agent: process manager adapter
8. Worker agent: claim loop + execution lifecycle
9. Worker agent: health API
10. BDD step definitions — backend (pytest-bdd)
11. CI pipeline — backend (gitleaks, alembic check, FK integrity, coverage)
12. Frontend scaffold (Vite + React + TypeScript + TanStack Query + React Router)
13. Frontend entities + shared API client (useJobs, useWorkers)
14. Frontend: dashboard page (worker fleet panel + jobs panel + filter + auto-refresh)
15. Frontend: schedule job page (form + validation + submit)
16. Playwright e2e tests + CI integration (ops condition C8)
