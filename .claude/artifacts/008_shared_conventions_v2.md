# Shared Conventions — Lightcron

**Version**: v5
**Created**: 2026-03-21
**Updated**: 2026-03-21 — v2: corrected cancel from DELETE to POST; workers use DB-direct, not REST
**Updated**: 2026-03-21 — v3: two-stage worker liveness detection (60s → /health probe, 90s → offline)
**Updated**: 2026-03-21 — v4: pull-based job claiming; added `ready` status; scheduler no longer assigns workers
**Updated**: 2026-03-21 — v5: added web UI (J009, J010); web_ui_user persona; frontend conventions
**Agent**: design (Phase A)
**Purpose**: Single source of truth for naming, roles, thresholds, and patterns.
             Every BDD generation agent receives this document verbatim.

---

## System Architecture Pattern

Lightcron uses a **DB-as-bus** pattern. There is no message broker.

| Component              | How it communicates                                              |
|------------------------|------------------------------------------------------------------|
| Job Submitter (user)   | REST API → Lightcron Scheduler Service                           |
| Platform Operator      | REST API → Lightcron Scheduler Service                           |
| Lightcron Scheduler    | Reads/writes DB; serves REST API to users                        |
| Worker Agent (worker)  | Reads/writes DB directly (via pgBouncer) — NOT via scheduler REST API |
| Worker Agent health    | Exposes its own small REST API with only `GET /health`           |
| Scheduler health check | Calls `GET /health` on worker's REST API when DB heartbeat is stale |

**Key rule**: Worker nodes do not call the scheduler's REST API. They communicate exclusively
by reading and writing to the shared database.

---

## Naming Conventions

| Entity Type       | Convention              | Examples                          |
|-------------------|------------------------|-----------------------------------|
| Journey tags      | `@J{NNN}`              | @J001, @J002                      |
| Feature tags      | `@persona:{role}`      | @persona:job_submitter            |
| Priority tags     | `@P{N}`                | @P1, @P2, @P3                     |
| Runner tags       | `@smoke`, `@regression`, `@error-handling` | —               |
| Domain entities   | snake_case in steps    | job_id, worker_id, start_time     |
| API paths         | kebab-case segments    | /jobs, /jobs/{id}/cancel          |

---

## System Roles

| Role                | Description                                                         |
|---------------------|---------------------------------------------------------------------|
| `job_submitter`     | Application developer calling the scheduler REST API (or web UI) to schedule/query/cancel jobs |
| `platform_operator` | Engineer managing the Lightcron deployment and worker fleet; primary web UI user |
| `sre_operator`      | On-call engineer responding to incidents; uses web UI dashboard for at-a-glance status |
| `worker_agent`      | The process running on each worker node; reads/writes DB via pgBouncer; exposes `/health` |
| `scheduler`         | The Lightcron central service; owns the REST API and background dispatch/health-check loops |

---

## Domain Entity Names (EXACT — do not use synonyms)

| Canonical Name   | Do NOT use               |
|------------------|--------------------------|
| `Job`            | task, work item, event   |
| `Worker`         | node, executor, host     |
| `WorkerAgent`    | agent, daemon, client    |
| `job_id`         | task_id, id, uuid        |
| `worker_id`      | node_id, host_id         |
| `worker_status`  | worker_state, node_status|

---

## Key Database Tables (EXACT names)

| Table           | Owned by       | Purpose                                              |
|-----------------|----------------|------------------------------------------------------|
| `jobs`          | Scheduler writes; worker_agent writes status updates | Job definitions and lifecycle state |
| `worker_status` | worker_agent writes; scheduler reads                 | Worker registration and heartbeat   |

### `jobs` Key Fields

| Field         | Required | Notes                                                    |
|---------------|----------|----------------------------------------------------------|
| `job_id`      | Yes      | Unique identifier                                        |
| `command`     | Yes      | The command to execute                                   |
| `start_time`  | Yes      | When the job becomes eligible (pending → ready)          |
| `depends_on`  | No       | List of job_ids that must be `completed` first; default: empty |
| `max_runtime` | No       | Seconds; worker_agent kills process if exceeded; default: unlimited |
| `max_memory`  | No       | MB; enforced by worker_agent; default: unlimited         |
| `status`      | Yes      | See Job Status Values                                    |
| `worker_id`   | No       | Set by worker_agent on claim                             |
| `exit_code`   | No       | Set by worker_agent on process exit                      |
| `kill_reason` | No       | Set by worker_agent when process is killed; e.g. `max_runtime_exceeded` |
| `claimed_at`  | No       | Timestamp set by worker_agent on claim                   |
| `started_at`  | No       | Timestamp set by worker_agent on process start           |
| `finished_at` | No       | Timestamp set by worker_agent on process exit            |

---

## Job Status Values (EXACT — exhaustive)

| Status      | Written by     | Meaning                                              |
|-------------|----------------|------------------------------------------------------|
| `pending`   | Scheduler      | Created; waiting for start_time and/or dependencies to be satisfied |
| `ready`     | Scheduler      | start_time reached AND all dependencies `completed`; available for worker_agents to claim |
| `assigned`  | Worker Agent   | worker_agent atomically claimed the job (wrote its worker_id); not yet started |
| `running`   | Worker Agent   | worker_agent started the process and updated the jobs table |
| `completed` | Worker Agent   | worker_agent stopped the job at end_time; process exited |
| `cancelled` | Scheduler      | Cancelled via REST API; worker_agent detects on next poll and stops if running |
| `failed`    | Worker Agent   | Execution error; worker_agent wrote failure with exit_code |
| `lost`      | Scheduler      | worker_status.last_seen expired; scheduler wrote `lost` — worker considered unreachable |

### Status Transition Flow

```
pending  ──(start_time reached + deps met)──▶  ready
ready    ──(worker_agent atomic claim)──────▶  assigned
assigned ──(worker_agent starts process)────▶  running
running  ──(end_time reached / exit 0)──────▶  completed
running  ──(exit code != 0)─────────────────▶  failed
pending/ready/assigned/running ─(API cancel)▶  cancelled
assigned/running ──(heartbeat timeout)──────▶  lost
```

---

## Worker Status Values (EXACT — exhaustive, stored in `worker_status` table)

| Status     | Written by   | Meaning                                               |
|------------|--------------|-------------------------------------------------------|
| `online`   | Worker Agent | Worker agent wrote registration or updated last_seen  |
| `offline`  | Scheduler    | Scheduler wrote offline after last_seen expired (90s) |

---

## Numeric Constants (EXACT — do not approximate)

| Constant                         | Value | Spec Reference                           |
|----------------------------------|-------|------------------------------------------|
| Worker last_seen update interval | 30s   | J002, J008                               |
| /health probe threshold          | 60s   | J008 — stage 1: call worker /health      |
| Worker offline threshold         | 90s   | J008 — stage 2: mark offline if /health also fails |
| SIGTERM grace period             | TBD   | J004 — to be confirmed                   |
| Max jobs per worker              | TBD   | To be defined in spec                    |

### Two-Stage Worker Liveness Detection (J008)

```
last_seen < 60s  →  worker considered healthy, no action
last_seen >= 60s →  Stage 1: scheduler calls GET /health on worker's REST API
                       /health returns 200  →  worker is alive; no status change
                       /health fails/timeout →  Stage 2: mark worker_status offline,
                                                mark all assigned/running jobs lost
last_seen >= 90s →  Skip /health probe (assume dead); go directly to Stage 2
```

This tolerates transient DB write failures on the worker while still recovering promptly from true worker crashes.

---

## Scheduler REST API Paths (user-facing — EXACT)

These paths are served by the Lightcron Scheduler Service and are called by human users only.

| Method | Path                        | Purpose                      |
|--------|-----------------------------|------------------------------|
| POST   | `/jobs`                     | Schedule a new job           |
| GET    | `/jobs/{job_id}`            | Query a specific job         |
| GET    | `/jobs`                     | List jobs (with filters)     |
| POST   | `/jobs/{job_id}/cancel`     | Request job cancellation     |
| GET    | `/workers`                  | List workers and their status |

**DO NOT** define `POST /workers/register`, `POST /workers/{id}/heartbeat`, or any REST endpoint
for worker-to-scheduler communication. Workers use the DB directly.

---

## Worker REST API Paths (EXACT — minimal, on each worker node)

| Method | Path      | Purpose                                               |
|--------|-----------|-------------------------------------------------------|
| GET    | `/health` | Returns 200 if worker_agent process is alive          |

The scheduler calls this endpoint only when `worker_status.last_seen` is stale, as a secondary
liveness check. It does not replace DB-based status.

---

## Worker DB Interaction Pattern (EXACT)

```
Worker Agent startup:
  UPSERT worker_status SET status='online', hostname=..., last_seen=now() WHERE hostname=...

Worker Agent last_seen loop (every 30s):
  UPDATE worker_status SET last_seen=now() WHERE worker_id=...

Worker Agent claim loop (poll interval TBD):
  -- Step 1: find a ready job
  SELECT job_id FROM jobs WHERE status='ready' LIMIT 1 FOR UPDATE SKIP LOCKED
  -- Step 2: atomically claim it (only one worker wins)
  UPDATE jobs SET status='assigned', worker_id=<self>, claimed_at=now()
    WHERE job_id=<id> AND status='ready'
  -- If UPDATE affected 0 rows: another worker claimed it; try next

Worker Agent job start (after successful claim):
  UPDATE jobs SET status='running', started_at=now() WHERE job_id=...

Worker Agent job complete/fail:
  UPDATE jobs SET status='completed'|'failed', finished_at=now(), exit_code=... WHERE job_id=...

Worker Agent cancel detection (during running, checked each poll cycle):
  SELECT status FROM jobs WHERE job_id=... -- if 'cancelled', stop process
```

### Scheduler Background Loop Pattern (EXACT)

```
Scheduler ready-transition loop (poll interval TBD):
  -- Mark jobs as ready when start_time passed and all dependencies completed
  UPDATE jobs SET status='ready'
    WHERE status='pending'
      AND start_time <= now()
      AND (
        depends_on IS NULL OR depends_on = '[]'
        OR NOT EXISTS (
          SELECT 1 FROM jobs dep
          WHERE dep.job_id = ANY(jobs.depends_on)
            AND dep.status != 'completed'
        )
      )

Scheduler health-check loop (every 30s):
  -- Two-stage liveness: see Numeric Constants for thresholds
  -- Stage 1 (last_seen >= 60s): call GET /health on worker_agent
  -- Stage 2 (last_seen >= 90s OR /health failed): mark worker offline, jobs lost
```

---

## Required Scenario Types Per Feature

Every `.feature` file MUST include:
- `@smoke`: Happy-path end-to-end scenario
- `@error-handling`: At least one failure/edge case scenario

---

## Background Step Pattern

```gherkin
Background:
  Given the Lightcron scheduler is running
  And no jobs or workers exist
```

(Adjust "And" clauses per feature as needed — use only what applies.)

---

---

## Web UI Pages (EXACT — React Router routes)

The web UI is a React/TypeScript SPA that communicates exclusively with the scheduler REST API.

| Route        | Page Component     | Purpose                                      |
|--------------|--------------------|----------------------------------------------|
| `/`          | `DashboardPage`    | Worker fleet panel + jobs panel (J009)       |
| `/jobs/new`  | `ScheduleJobPage`  | Job submission form (J010)                   |

**Key rule**: The web UI ONLY calls the scheduler REST API paths listed in the Scheduler REST API Paths table above. It does not call worker REST APIs directly.

---

## Frontend Architecture (EXACT — Feature-Sliced Design layers)

| Layer      | Purpose                                         | Examples                            |
|------------|-------------------------------------------------|-------------------------------------|
| `app/`     | Entry point, router, global providers           | React Query provider, Router        |
| `pages/`   | Route-level components; compose widgets         | DashboardPage, ScheduleJobPage      |
| `widgets/` | Standalone UI blocks composed from features/entities | WorkerFleetPanel, JobsPanel    |
| `features/`| User-facing interactive behaviours              | ScheduleJobForm, StatusFilter       |
| `entities/`| Business objects + their UI representations     | Job model + JobStatusBadge          |
| `shared/`  | Reusable infrastructure; no business logic      | API client, useJobs, useWorkers     |

**Import rule** (FSD): lower layers may NOT import from higher layers.
`shared` ← `entities` ← `features` ← `widgets` ← `pages` ← `app`

---

## Anti-Patterns

- Do NOT use DELETE for job cancellation — use POST /jobs/{job_id}/cancel
- Do NOT define REST endpoints for worker-to-scheduler communication
- Do NOT model worker heartbeats as REST calls — they are DB writes
- Do NOT invent API paths not listed above
- Do NOT use synonyms for entity names — use exact names from this document
- Do NOT round numeric constants (last_seen timeout is 90s, not "about a minute")
- Do NOT assume authentication details — mark auth steps as `# TODO: auth scheme TBD`
- If the spec is ambiguous, mark with `# SPEC-AMBIGUOUS: {what's unclear}`
- Do NOT have the web UI call worker REST APIs directly — it must go via the scheduler API
- Do NOT hardcode the scheduler API base URL in frontend code — use an environment variable
