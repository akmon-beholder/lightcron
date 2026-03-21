# Lightcron — Functional Specification

## Metadata
- **Version**: v1
- **Created**: 2026-03-21
- **Agent**: ba (Phase B)
- **Inputs**: `001_solution_envelope_v2.md`, `000_user_journeys_v1.md` (v1.1), `008_shared_conventions_v2.md` (v5)
- **Status**: approved_for_build

---

## Scope

This specification covers all 10 user journeys:

| Journey | Title | Priority |
|---------|-------|----------|
| J001 | Schedule a Job (REST API) | P1 |
| J002 | Worker Node Registers | P1 |
| J003 | Job Becomes Ready and Worker Claims It | P1 |
| J004 | Job Runs to Completion | P1 |
| J005 | Cancel a Job | P1 |
| J006 | Query Job Status | P1 |
| J007 | View Worker Fleet Status | P2 |
| J008 | Detect and Recover Stuck Jobs | P1 |
| J009 | View System State via Web UI Dashboard | P2 |
| J010 | Schedule a Job via Web UI Form | P2 |

---

## Constants

All timing constants are defined in `src/lightcron/constants.py`. Every scheduler and worker agent module must import from this file — no hardcoded numeric literals elsewhere.

```python
# src/lightcron/constants.py

READY_TRANSITION_INTERVAL_SECONDS: int = 10
HEALTH_CHECK_INTERVAL_SECONDS: int = 30
CLAIM_POLL_INTERVAL_SECONDS: int = 5
JOB_STATUS_POLL_INTERVAL_SECONDS: int = 5
LAST_SEEN_UPDATE_INTERVAL_SECONDS: int = 30
WORKER_HEALTH_PROBE_THRESHOLD_SECONDS: int = 60
WORKER_OFFLINE_THRESHOLD_SECONDS: int = 90
SIGTERM_GRACE_PERIOD_SECONDS: int = 30
```

Frontend timing constant (defined in `frontend/src/shared/constants.ts`):

```typescript
export const DASHBOARD_REFRESH_INTERVAL_MS: number = 10_000;
```

---

## Data Model

### PostgreSQL Enums

```sql
CREATE TYPE job_status AS ENUM (
  'pending', 'ready', 'assigned', 'running',
  'completed', 'failed', 'cancelled', 'lost'
);

CREATE TYPE worker_status AS ENUM ('online', 'offline');
```

### Table: `jobs`

```sql
CREATE TABLE jobs (
  job_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  command      TEXT NOT NULL,
  start_time   TIMESTAMPTZ NOT NULL,
  depends_on   UUID[] NOT NULL DEFAULT '{}',
  max_runtime  INTEGER NULL CHECK (max_runtime > 0),   -- seconds
  max_memory   INTEGER NULL CHECK (max_memory > 0),    -- MB
  status       job_status NOT NULL DEFAULT 'pending',
  worker_id    UUID NULL REFERENCES worker_status(worker_id),
  exit_code    INTEGER NULL,
  kill_reason  TEXT NULL,
  claimed_at   TIMESTAMPTZ NULL,
  started_at   TIMESTAMPTZ NULL,
  finished_at  TIMESTAMPTZ NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX jobs_status_idx ON jobs (status);
CREATE INDEX jobs_worker_id_idx ON jobs (worker_id);
CREATE INDEX jobs_start_time_idx ON jobs (start_time);
```

### Table: `worker_status`

```sql
CREATE TABLE worker_status (
  worker_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hostname      TEXT NOT NULL UNIQUE,
  status        worker_status NOT NULL DEFAULT 'online',
  last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
  registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX worker_status_last_seen_idx ON worker_status (last_seen);
```

### Status Transition Rules

A database trigger or application-layer guard must enforce that `updated_at` is refreshed on every row update to the `jobs` table.

Terminal statuses are: `completed`, `failed`, `cancelled`, `lost`.
Once a job reaches a terminal status, no further status updates are permitted (enforced by application-layer guard: `WHERE status NOT IN ('completed', 'failed', 'cancelled', 'lost')`).

---

## Scheduler REST API

Base path: all routes are served by the `lightcron-scheduler` FastAPI application.

### CORS

The scheduler must expose CORS headers permitting requests from the web UI origin. The allowed origin is configured via the environment variable `LIGHTCRON_UI_ORIGIN`. No wildcard (`*`) is permitted in production (ops condition C7).

In Docker Compose development, `LIGHTCRON_UI_ORIGIN=http://localhost:5173` is the default.

---

### POST /jobs

Schedule a new job.

**Request body** (`application/json`):

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `command` | string | Yes | Non-empty |
| `start_time` | ISO 8601 datetime | Yes | Must be in the future (> `now()` at time of request) |
| `depends_on` | array of UUID strings | No | Default `[]`; each UUID must reference an existing `job_id` |
| `max_runtime` | integer | No | Must be > 0 (seconds); omit for unlimited |
| `max_memory` | integer | No | Must be > 0 (MB); omit for unlimited |

**Responses**:

| Status | Condition | Body |
|--------|-----------|------|
| 201 | Job created | Full job object (see Job Response Shape) |
| 400 | Malformed JSON | `{"detail": "..."}` |
| 422 | Validation failure | `{"detail": [{"field": "...", "msg": "..."}]}` |

**Validation rules** (return 422 on violation):
- `command` missing or empty
- `start_time` missing, not a valid ISO 8601 datetime, or ≤ `now()`
- Any UUID in `depends_on` does not exist in the `jobs` table
- `max_runtime` present but ≤ 0
- `max_memory` present but ≤ 0

**Job Response Shape** (used by POST /jobs, GET /jobs/{job_id}, GET /jobs):

```json
{
  "job_id": "uuid",
  "command": "string",
  "start_time": "ISO 8601",
  "depends_on": ["uuid", ...],
  "max_runtime": "integer | null",
  "max_memory": "integer | null",
  "status": "pending",
  "worker_id": "uuid | null",
  "exit_code": "integer | null",
  "kill_reason": "string | null",
  "claimed_at": "ISO 8601 | null",
  "started_at": "ISO 8601 | null",
  "finished_at": "ISO 8601 | null",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

---

### GET /jobs/{job_id}

Retrieve a single job by ID.

**Path parameter**: `job_id` — UUID string.

**Responses**:

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Job found | Full job object |
| 404 | `job_id` not found | `{"detail": "Job not found"}` |

---

### GET /jobs

List jobs, optionally filtered by status.

**Query parameters**:

| Parameter | Type | Required | Constraints |
|-----------|------|----------|-------------|
| `status` | string | No | Must be a valid `job_status` enum value if provided |

**Responses**:

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Success | Array of full job objects (empty array if none match) |
| 422 | `status` is not a valid enum value | `{"detail": [{"field": "status", "msg": "..."}]}` |

---

### POST /jobs/{job_id}/cancel

Request cancellation of a job.

**Path parameter**: `job_id` — UUID string.

**No request body.**

**Behaviour**:
- If job status is `pending`, `ready`, or `assigned`: scheduler writes `cancelled` directly.
- If job status is `running`: scheduler writes `cancelled`; the worker_agent detects the status change on its next poll cycle and stops the process.
- The UPDATE must use the terminal-state guard: `WHERE status NOT IN ('completed', 'failed', 'cancelled', 'lost')`.

**Responses**:

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Cancellation accepted | `{"job_id": "uuid", "status": "cancelled"}` |
| 404 | `job_id` not found | `{"detail": "Job not found"}` |
| 409 | Job is in a terminal state | `{"detail": "Job is in a terminal state and cannot be cancelled"}` |

---

### GET /workers

List all registered workers and their current status.

**No query parameters.**

**Responses**:

| Status | Condition | Body |
|--------|-----------|------|
| 200 | Success | Array of worker objects (empty array if none registered) |

**Worker Response Shape**:

```json
{
  "worker_id": "uuid",
  "hostname": "string",
  "status": "online | offline",
  "last_seen": "ISO 8601",
  "registered_at": "ISO 8601",
  "running_job_count": "integer"
}
```

`running_job_count` is the count of jobs in the `jobs` table with `status = 'running'` and `worker_id` matching this worker.

---

### GET /health (Scheduler)

Liveness probe for the scheduler service itself (ops condition C4).

**Responses**:

| Status | Body |
|--------|------|
| 200 | `{"status": "ok"}` |

---

## Scheduler Background Loops

### Ready-Transition Loop

**Interval**: `READY_TRANSITION_INTERVAL_SECONDS` (10s)

**SQL** (executed inside a transaction with `SELECT FOR UPDATE` or advisory lock to be safe at >1 scheduler instance):

```sql
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
  );
```

**Acceptance criteria**:
- A `pending` job with `start_time <= now()` and no `depends_on` is marked `ready` within `READY_TRANSITION_INTERVAL_SECONDS + ε` of its start_time.
- A `pending` job with `depends_on` remains `pending` until all referenced jobs are `completed`.
- A job with a circular dependency (A depends on B, B depends on A) remains `pending` indefinitely — this is a known limitation (see §Known Limitations).
- Two concurrent scheduler instances must not double-transition the same job. The loop must use either a PostgreSQL advisory lock (`pg_try_advisory_lock`) or a row-level lock with `SELECT FOR UPDATE`.

---

### Health-Check Loop

**Interval**: `HEALTH_CHECK_INTERVAL_SECONDS` (30s)

**Two-stage liveness logic:**

```
For each worker in worker_status where status = 'online':
  age = now() - last_seen

  if age < WORKER_HEALTH_PROBE_THRESHOLD_SECONDS (60s):
    → no action

  elif age < WORKER_OFFLINE_THRESHOLD_SECONDS (90s):
    → Stage 1: call GET /health on worker_agent
      if HTTP 200: no action (worker is alive despite stale DB write)
      if error/timeout: → Stage 2

  else (age >= WORKER_OFFLINE_THRESHOLD_SECONDS):
    → Stage 2 directly (skip /health probe)

Stage 2:
  UPDATE worker_status SET status = 'offline' WHERE worker_id = ? AND status = 'online'
  UPDATE jobs SET status = 'lost', updated_at = now()
    WHERE worker_id = ?
      AND status IN ('assigned', 'running')
```

**Acceptance criteria**:
- A worker whose `last_seen` is < 60s old is not probed and is not marked `offline`.
- A worker whose `last_seen` is ≥ 60s but < 90s old is probed; if `/health` returns 200, it remains `online`.
- A worker whose `last_seen` is ≥ 60s but < 90s old is probed; if `/health` fails, it is marked `offline` and its `assigned`/`running` jobs are marked `lost`.
- A worker whose `last_seen` is ≥ 90s old is marked `offline` without a `/health` probe.
- All `assigned` and `running` jobs belonging to the affected worker are marked `lost` atomically in Stage 2.
- The terminal-state guard applies: Stage 2 UPDATE must use `WHERE status IN ('assigned', 'running')` — it must not overwrite `completed`, `failed`, `cancelled`, or `lost` jobs.
- The `/health` probe timeout must be short (suggested: 5s) to avoid blocking the health-check loop.

---

## Worker Agent Behaviour

### Startup / Registration

On start, the worker_agent upserts its row in `worker_status` by hostname:

```sql
INSERT INTO worker_status (hostname, status, last_seen, registered_at)
VALUES ($hostname, 'online', now(), now())
ON CONFLICT (hostname) DO UPDATE
  SET status = 'online', last_seen = now();
```

This preserves the existing `worker_id` on reconnect (the PK is not overwritten).

**Acceptance criteria**:
- On first registration, a new `worker_id` UUID is generated.
- On re-registration with the same hostname, the existing `worker_id` is preserved.
- After reconnection, `status` is `online` and `last_seen` is approximately `now()`.

---

### Last-Seen Heartbeat Loop

**Interval**: `LAST_SEEN_UPDATE_INTERVAL_SECONDS` (30s)

```sql
UPDATE worker_status SET last_seen = now() WHERE worker_id = $worker_id;
```

This loop runs continuously while the worker_agent process is alive.

---

### Claim Loop

**Interval**: `CLAIM_POLL_INTERVAL_SECONDS` (5s)

**Pre-claim concurrency guard**: Before claiming, the worker_agent checks how many jobs it currently has in `assigned` or `running` status. If the count equals `N` (the configured concurrency limit), it skips the claim attempt for this cycle.

```sql
SELECT COUNT(*) FROM jobs
WHERE worker_id = $worker_id AND status IN ('assigned', 'running');
```

**Claim sequence** (runs within a single connection in session mode):

```sql
-- Step 1: find a ready job
SELECT job_id FROM jobs
WHERE status = 'ready'
ORDER BY start_time ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Step 2: atomically claim it
UPDATE jobs
SET status = 'assigned', worker_id = $worker_id, claimed_at = now(), updated_at = now()
WHERE job_id = $job_id AND status = 'ready';
-- Check rowcount: 0 = another worker won the race, skip this job
```

**Acceptance criteria**:
- If `rowcount = 0`, the worker_agent does not hold the job and tries the next `ready` job.
- Exactly one worker_agent claims a job in a concurrent race.
- A worker at capacity (running N jobs) does not attempt to claim additional jobs.
- pgBouncer must be in `pool_mode = session` for `SELECT FOR UPDATE SKIP LOCKED` to work correctly (ops condition C5).

---

### Job Execution Lifecycle

After a successful claim:

1. **Start**: Spawn process for `command`. Update jobs table:
   ```sql
   UPDATE jobs SET status = 'running', started_at = now(), updated_at = now()
   WHERE job_id = $job_id;
   ```

2. **Monitor**: While process runs, poll memory usage every `JOB_STATUS_POLL_INTERVAL_SECONDS` (5s) using psutil. Kill the **process group** (`os.killpg`) — not just the process — to handle forking subprocesses.

3. **max_runtime enforcement** (if set):
   - If `now() - started_at >= max_runtime`: send `SIGTERM` to process group.
   - Wait up to `SIGTERM_GRACE_PERIOD_SECONDS` (30s) for exit.
   - If still running: send `SIGKILL`.
   - Write to DB:
     ```sql
     UPDATE jobs SET status = 'failed', finished_at = now(),
       kill_reason = 'max_runtime_exceeded', updated_at = now()
     WHERE job_id = $job_id;
     ```

4. **max_memory enforcement** (if set):
   - If `psutil` reports RSS > `max_memory` MB: send `SIGTERM` to process group.
   - Same grace period and SIGKILL logic as above.
   - Write `kill_reason = 'max_memory_exceeded'` to DB.

5. **Natural exit**:
   - Exit code 0: `status = 'completed'`
   - Exit code != 0: `status = 'failed'`
   - Always write `finished_at`, `exit_code`, `updated_at`.

**Acceptance criteria**:
- All DB writes use the terminal-state guard (`WHERE job_id = $job_id AND status NOT IN ('completed', 'failed', 'cancelled', 'lost')`) to handle the cancel/lost race.
- SIGTERM grace period: if process exits during the grace window, record the exit code and reason correctly without sending SIGKILL.
- Memory monitoring latency: there is an inherent delay between a memory limit breach and detection at the next poll cycle. This is accepted for v1.

---

### Cancel Detection

The worker_agent polls for cancellation on every `JOB_STATUS_POLL_INTERVAL_SECONDS` (5s) cycle for each running job:

```sql
SELECT status FROM jobs WHERE job_id = $job_id;
```

If `status = 'cancelled'`:
- Send `SIGTERM` to process group.
- Wait up to `SIGTERM_GRACE_PERIOD_SECONDS` for exit.
- If still running: send `SIGKILL`.
- Do NOT write any status update (the scheduler has already written `cancelled`; it is authoritative).

---

### Lost Detection / Zombie Cleanup

On every `JOB_STATUS_POLL_INTERVAL_SECONDS` (5s) cycle, the same status poll that checks for `cancelled` also checks for `lost`:

If `status = 'lost'` and the worker_agent still has an active process for that job:
- Send `SIGKILL` immediately (no SIGTERM — the scheduler has already decided the job is lost).
- Do NOT write any status update to the jobs table.

If the worker_agent restarts and finds processes for jobs that are now `lost`, the same rule applies.

---

### Worker Agent Health Endpoint

A minimal FastAPI application running alongside the worker_agent loop:

```
GET /health
→ 200 {"status": "ok"}
```

This endpoint returns 200 as long as the worker_agent process is alive. It has no dependency on DB connectivity.

---

## Web UI

### Technology

React 18 / TypeScript / Vite, following Feature-Sliced Design (FSD). Tests use Playwright.

The API base URL is configured via the Vite environment variable `VITE_API_BASE_URL`. This must not be hardcoded (ops condition C7 spirit — no hardcoded origins).

### Dashboard Page (`/`) — J009

**Data sources**: `GET /workers`, `GET /jobs`

**Worker Fleet Panel**:
- Lists all workers: worker_id, hostname, status (with coloured badge), last_seen (human-relative format, e.g. "30s ago"), running_job_count.
- Workers with `status = 'offline'` are visually distinguished.
- Empty state: "No workers registered" if list is empty.

**Jobs Panel**:
- Lists all jobs (or filtered subset): job_id, command (truncated at 80 chars), status (with coloured badge), worker_id (if assigned).
- Status filter: a dropdown or tab strip allowing the user to filter by any valid `job_status` value or "all".
- Empty state: "No jobs" if list is empty.

**Auto-refresh**:
- Both panels refresh every `DASHBOARD_REFRESH_INTERVAL_MS` (10,000 ms) using TanStack Query's `refetchInterval`.
- Refresh happens in the background — no loading spinner unless initial load.

**Acceptance criteria**:
- AC-J009-01 through AC-J009-07 (see user journeys).

---

### Schedule Job Page (`/jobs/new`) — J010

**Form fields**:

| Field | Type | Required | Client-side validation |
|-------|------|----------|------------------------|
| `command` | text input | Yes | Non-empty |
| `start_time` | datetime-local input | Yes | Must be in the future |
| `max_runtime` | number input | No | If provided, must be > 0 |
| `max_memory` | number input | No | If provided, must be > 0 |
| `depends_on` | text input (comma-separated UUIDs) | No | No client-side UUID existence check |

**Submit behaviour**:
- Client-side validation runs on submit. If any client-side rule fails, the relevant field shows an inline error and the API is not called.
- On API success (201): display the returned `job_id` prominently; show a link to the job detail view (future: GET /jobs/{job_id}). The form does not auto-clear, allowing the user to submit another similar job.
- On API error 422: display the server's `detail` message(s) inline next to the relevant field(s).
- On API error 4xx/5xx (other): display a generic top-level error message.

**Acceptance criteria**:
- AC-J010-01 through AC-J010-07 (see user journeys).

---

## Policy Rules (Exhaustive)

These rules are enforced at the application layer. Database constraints (CHECK, FK) provide a secondary safety net but are not the primary enforcement mechanism.

| # | Rule | Enforced by | Error |
|---|------|-------------|-------|
| R01 | `command` must be non-empty | Scheduler API | HTTP 422 |
| R02 | `start_time` must be > `now()` at submission | Scheduler API | HTTP 422 |
| R03 | Every UUID in `depends_on` must exist in `jobs` | Scheduler API | HTTP 422 |
| R04 | `max_runtime` must be a positive integer if provided | Scheduler API + DB CHECK | HTTP 422 |
| R05 | `max_memory` must be a positive integer if provided | Scheduler API + DB CHECK | HTTP 422 |
| R06 | Cancellation is rejected for terminal-status jobs | Scheduler API | HTTP 409 |
| R07 | Only one worker_agent may hold a job in `assigned`/`running` at a time | Atomic DB claim | — |
| R08 | The scheduler's write of `lost` or `cancelled` is authoritative | Worker agent guard | Worker does not overwrite |
| R09 | Worker identity is hostname-based: same hostname → same worker_id | UPSERT ON CONFLICT (hostname) | — |
| R10 | All DB status writes use terminal-state guard | Application layer | Silent no-op if race |
| R11 | Worker_agent kills process group, not just the process | Process adapter | — |
| R12 | Web UI must not call worker REST APIs directly | Frontend design | — |
| R13 | CORS allowed origin must be configured via env var; no wildcard in prod | Scheduler adapter | Ops condition C7 |

---

## Known Limitations (v1)

1. **Dependency cycle detection**: If job A depends on job B and job B depends on job A, both jobs will remain `pending` indefinitely. The ready-transition loop will never satisfy the condition. This is not treated as an error — the jobs silently stay `pending`. Tooling to detect this is deferred to v2.

2. **Cancel is best-effort**: If a worker_agent is offline when a job is cancelled, the process will continue running until the worker_agent comes back online and polls. At that point, the process will be stopped. The job status in the DB is `cancelled` regardless.

3. **Memory monitoring latency**: There is an inherent delay of up to `JOB_STATUS_POLL_INTERVAL_SECONDS` between a memory limit breach and detection. A process that briefly spikes and drops may not be caught.

4. **No job retry**: Failed or lost jobs must be manually requeued by submitting a new job. Automatic retry is out of scope for v1.

5. **Authentication**: The scheduler REST API is unauthenticated in v1. It is assumed to be accessible only within a trusted network.

---

## Quality Gates

All ops conditions from the solution envelope must be implemented as tasks and verified before the first deployment:

| Condition | Description | Gate type |
|-----------|-------------|-----------|
| C1 | gitleaks secret detection in CI | hard |
| C2 | `alembic check` before `alembic upgrade head` in CI | hard |
| C3 | FK integrity validation after migrations | hard |
| C4 | Scheduler exposes `GET /health` | hard |
| C5 | pgBouncer `pool_mode=session` enforced by config; integration test validates | hard |
| C6 | No production deployment automation until hosting is decided | documentation |
| C7 | CORS origin from env var; no wildcard in production | hard |
| C8 | Playwright e2e smoke tests in CI against Docker Compose stack | hard |
