# Lightcron — Functional Specification v2 (Job Detail Feature)

## Metadata
- **Version**: v2
- **Created**: 2026-03-21
- **Agent**: ba (Phase B)
- **Inputs**: `000_user_journeys_v1.md` (v1.3), `001_solution_envelope_v2.md`, `002_spec_v1.md`, `003_tasklist_v1.md`, feature files (schedule-job, job-lifecycle-completion, job-detail, system-dashboard, schedule-job-ui), `src/lightcron/constants.py`, `src/migrations/versions/001_initial_schema.py`
- **Status**: approved_for_build

---

## Scope

This document covers **only what is new or changed relative to `002_spec_v1.md`**. All v1 behaviour not mentioned here remains in force. This spec implements journey J011 (Inspect Job Detail via Web UI) and the supporting backend changes required by journeys J001 (env_vars) and J004 (output files, peak_memory_mb).

| Journey | Title | Priority | Status |
|---------|-------|----------|--------|
| J001 | Schedule a Job (env_vars addition) | P1 | Extended |
| J004 | Job Runs to Completion (output files, peak_memory_mb) | P1 | Extended |
| J009 | View System State via Web UI Dashboard (job row links) | P2 | Extended |
| J011 | Inspect Job Detail via Web UI | P2 | New |

---

## 1. New Constant

Add to `src/lightcron/constants.py`:

```python
WORKER_DEFAULT_JOBS_DIR: str = "/var/logs/lightcron/jobs"
"""Default directory on the worker node for job stdout/stderr output files."""
```

This constant must be imported by all worker agent modules that reference the jobs directory — no hardcoded path strings elsewhere.

---

## 2. DB Schema Changes

### Migration file

New file: `src/migrations/versions/002_job_detail_fields.py`

`revision`: `"002"`, `down_revision`: `"001"`

### 2.1 New columns on `jobs` table

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| `env_vars` | JSONB | NO | `'{}'::jsonb` |
| `peak_memory_mb` | DOUBLE PRECISION | YES | NULL |

SQL (upgrade):

```sql
ALTER TABLE jobs
  ADD COLUMN env_vars      JSONB             NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN peak_memory_mb DOUBLE PRECISION NULL;
```

SQL (downgrade):

```sql
ALTER TABLE jobs
  DROP COLUMN IF EXISTS env_vars,
  DROP COLUMN IF EXISTS peak_memory_mb;
```

### 2.2 New column on `worker_status` table

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| `base_url` | TEXT | YES | NULL |

SQL (upgrade):

```sql
ALTER TABLE worker_status
  ADD COLUMN base_url TEXT NULL;
```

SQL (downgrade):

```sql
ALTER TABLE worker_status
  DROP COLUMN IF EXISTS base_url;
```

### 2.3 Existing column invariants

All previously defined columns, indexes, constraints, and the `set_updated_at` trigger on `jobs` remain unchanged.

---

## 3. Scheduler API Changes

### 3.1 POST /jobs — updated request body

New optional field `env_vars`:

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `env_vars` | object (`{string: string}`) | No | `{}` | Flat map; all keys and values must be strings; max 100 keys; key length ≤ 256 chars; value length ≤ 4096 chars |

**Validation rules** (add to existing list; return HTTP 422 on violation):
- `env_vars` is present but is not a JSON object
- `env_vars` contains a key that is not a string
- `env_vars` contains a value that is not a string (e.g. integer, nested object, array, null)
- `env_vars` contains more than 100 keys
- Any key in `env_vars` exceeds 256 characters
- Any value in `env_vars` exceeds 4096 characters

### 3.2 Updated response shapes

v1 used a single `Job Response Shape` for all job endpoints. v2 replaces this with two distinct Pydantic response models.

#### `JobSummaryResponse`

Used by: `POST /jobs` (201 response) and `GET /jobs` (list items).

All v1 fields plus `env_vars`. Does **not** include `peak_memory_mb` (omitted from list responses for efficiency).

```json
{
  "job_id": "uuid",
  "command": "string",
  "start_time": "ISO 8601",
  "depends_on": ["uuid"],
  "max_runtime": "integer | null",
  "max_memory": "integer | null",
  "env_vars": {"string": "string"},
  "status": "job_status enum",
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

#### `JobDetailResponse`

Used by: `GET /jobs/{job_id}` only.

All fields from `JobSummaryResponse` plus `peak_memory_mb`.

```json
{
  "job_id": "uuid",
  "command": "string",
  "start_time": "ISO 8601",
  "depends_on": ["uuid"],
  "max_runtime": "integer | null",
  "max_memory": "integer | null",
  "env_vars": {"string": "string"},
  "status": "job_status enum",
  "worker_id": "uuid | null",
  "exit_code": "integer | null",
  "kill_reason": "string | null",
  "peak_memory_mb": "float | null",
  "claimed_at": "ISO 8601 | null",
  "started_at": "ISO 8601 | null",
  "finished_at": "ISO 8601 | null",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

**Note**: `stdout` and `stderr` content are never in either response shape. They are retrieved by the UI directly from the worker REST API.

### 3.3 GET /workers — updated Worker Response Shape

Add `base_url` field to the worker response:

```json
{
  "worker_id": "uuid",
  "hostname": "string",
  "status": "online | offline",
  "last_seen": "ISO 8601",
  "registered_at": "ISO 8601",
  "running_job_count": "integer",
  "base_url": "string | null"
}
```

`base_url` is the value stored in `worker_status.base_url`. It is `null` if the worker has not configured `LIGHTCRON_WORKER_BASE_URL`.

---

## 4. Worker REST API Changes

The worker's FastAPI application gains two new endpoints and a CORS update.

### 4.1 GET /jobs/{job_id}/stdout

```
GET /jobs/{job_id}/stdout
```

**Behaviour**:
- Reads `{LIGHTCRON_JOBS_DIR}/{job_id}.stdout` from disk.
- Returns `200` with `Content-Type: text/plain` and the file contents as the response body.
- Returns `404 {"detail": "Not found"}` if the file does not exist.

**No authentication required** (consistent with v1 worker endpoints).

### 4.2 GET /jobs/{job_id}/stderr

```
GET /jobs/{job_id}/stderr
```

Identical behaviour to `GET /jobs/{job_id}/stdout` but reads `{LIGHTCRON_JOBS_DIR}/{job_id}.stderr`.

### 4.3 CORS on worker

The worker FastAPI app must expose CORS headers permitting requests from the UI origin. Configuration mechanism is identical to the scheduler's:

- Allowed origin configured via `LIGHTCRON_UI_ORIGIN` env var.
- No wildcard (`*`) in production (extends ops condition C7 to the worker).
- In Docker Compose development, `LIGHTCRON_UI_ORIGIN=http://localhost:5173` is the default.

### 4.4 Worker registration — base_url

At startup, the worker upserts its `base_url` into `worker_status` alongside the existing registration fields:

```sql
INSERT INTO worker_status (hostname, status, last_seen, registered_at, base_url)
VALUES ($hostname, 'online', now(), now(), $base_url)
ON CONFLICT (hostname) DO UPDATE
  SET status = 'online', last_seen = now(), base_url = $base_url;
```

`$base_url` is read from the `LIGHTCRON_WORKER_BASE_URL` environment variable (e.g. `http://worker-01:8001`). If `LIGHTCRON_WORKER_BASE_URL` is not set, `$base_url` is `NULL`.

---

## 5. Worker Agent Execution Changes

### 5.1 Jobs directory setup

- On startup, before registration, the worker agent ensures `LIGHTCRON_JOBS_DIR` exists.
- `LIGHTCRON_JOBS_DIR` is read from the environment variable of the same name; if not set, defaults to `WORKER_DEFAULT_JOBS_DIR` (`/var/logs/lightcron/jobs`).
- If the directory does not exist, create it (equivalent to `os.makedirs(path, exist_ok=True)`).
- This is a startup prerequisite: if directory creation fails, the worker agent must log the error and exit.

### 5.2 env_vars passthrough

- When a job is claimed, the worker agent reads `env_vars` from the job record.
- Before spawning the subprocess, compute the child environment as: `{**os.environ, **job.env_vars}`.
- Job `env_vars` take precedence on key collision.
- Pass the merged environment via the `env=` argument of the subprocess call.
- If `env_vars` is empty (`{}`), the subprocess inherits `os.environ` unchanged.

### 5.3 Output streaming to files

- Before spawning the subprocess, open two file handles:
  - `{LIGHTCRON_JOBS_DIR}/{job_id}.stdout` — opened for writing (create or overwrite)
  - `{LIGHTCRON_JOBS_DIR}/{job_id}.stderr` — opened for writing (create or overwrite)
- Pass these file handles as `stdout=` and `stderr=` in the subprocess call (not `subprocess.PIPE`).
- Output is written continuously to disk as the process runs; no buffering in memory.
- File handles are closed when the process exits (regardless of exit reason: natural exit, SIGKILL, cancel, lost).
- Files remain on disk after process exit. The worker agent does not delete them.
- If file creation fails (e.g. directory missing), the worker agent must log the error and mark the job `failed` before attempting to start the process.

### 5.4 Peak memory tracking

- On every `JOB_STATUS_POLL_INTERVAL_SECONDS` poll cycle (while the job process is running), read the process RSS via `psutil.Process(pid).memory_info().rss`.
- Convert to MB: `rss_bytes / 1024 / 1024`.
- Track a running maximum in memory across all poll cycles for the job's lifetime.
- On every terminal-state DB write (completed, failed from natural exit, failed from max_runtime, failed from max_memory, and after SIGKILL in cancel/lost handling), include `peak_memory_mb` in the UPDATE:

```sql
UPDATE jobs
SET status = $status,
    finished_at = now(),
    exit_code = $exit_code,
    kill_reason = $kill_reason,
    peak_memory_mb = $peak_memory_mb,
    updated_at = now()
WHERE job_id = $job_id
  AND status NOT IN ('completed', 'failed', 'cancelled', 'lost');
```

- If `psutil` raises `NoSuchProcess` during polling (process exited between poll start and RSS read), the current peak remains unchanged; it is written on the terminal write.
- Memory monitoring latency is accepted for v1: there is an inherent delay of up to `JOB_STATUS_POLL_INTERVAL_SECONDS` between a peak and detection.

### 5.5 JobExecution entity extension

The `JobExecution` dataclass must be extended with:

| Field | Type | Notes |
|-------|------|-------|
| `env_vars` | `dict[str, str]` | Read from DB at claim time |
| `stdout_path` | `Path` | Computed from `LIGHTCRON_JOBS_DIR` and `job_id` |
| `stderr_path` | `Path` | Computed from `LIGHTCRON_JOBS_DIR` and `job_id` |

---

## 6. Policy Rule Changes

### R12 — amended

v1 text: "Web UI must not call worker REST APIs directly."

**v2 amendment**: "The Web UI must not call worker REST APIs directly, **except for log retrieval** (`GET /jobs/{job_id}/stdout` and `GET /jobs/{job_id}/stderr`). All other UI communication goes through the scheduler REST API."

### R14 — new

"Worker CORS allowed origin must be configured via `LIGHTCRON_UI_ORIGIN` env var; no wildcard in production." (Extends ops condition C7 to the worker. The scheduler's R13 remains unchanged.)

---

## 7. Web UI Changes

### 7.1 Updated Job entity

File: `frontend/src/entities/job/model.ts`

Add two fields to the `Job` interface:

```typescript
env_vars: Record<string, string>;      // always present (empty {} if none)
peak_memory_mb: number | null;         // null before job has started
```

The `JobSummaryResponse` shape (from `GET /jobs` list) does not include `peak_memory_mb`; this field is only populated when the detail endpoint is used. The `Job` type in the entity model should reflect the union and declare `peak_memory_mb` as optional (`peak_memory_mb?: number | null`) so it can be used for both list and detail contexts without duplication.

### 7.2 Updated Worker entity

File: `frontend/src/entities/worker/model.ts`

Add one field to the `Worker` interface:

```typescript
base_url: string | null;
```

### 7.3 New API hooks

#### `useJob` — `frontend/src/shared/api/useJob.ts`

TanStack Query hook for `GET /jobs/{job_id}` (returns `JobDetailResponse`).

- Accepts `jobId: string`.
- Auto-refreshes every `DASHBOARD_REFRESH_INTERVAL_MS` while the job is **not** in a terminal state (`completed | failed | cancelled | lost`).
- Once terminal, `refetchInterval` is disabled (the data will not change).
- Exposes `{ data, isLoading, isError }`.

#### `useJobOutput` — `frontend/src/shared/api/useJobOutput.ts`

Fetches stdout or stderr from the worker REST API.

- Accepts `{ baseUrl: string | null, jobId: string, stream: 'stdout' | 'stderr' }`.
- Only called (enabled) when `baseUrl` is non-null AND the job is in a terminal state.
- Fetches: `GET {baseUrl}/jobs/{jobId}/{stream}`
- Returns `{ data: string | null, isOffline: boolean }`:
  - `data`: file content string on 200; `null` on 404 or network error
  - `isOffline`: `true` if the request fails with a network error (worker unreachable); `false` otherwise (including 404)
- Does not auto-refresh once fetched (terminal jobs have stable output).

### 7.4 Updated frontend constants

File: `frontend/src/shared/constants.ts`

Add:

```typescript
export const JOB_DETAIL_REFRESH_INTERVAL_MS: number = 5_000;
```

This constant is used by `useJob` for polling non-terminal jobs on the detail page.

### 7.5 Job detail page

New page: `frontend/src/pages/job-detail/JobDetailPage.tsx`

Route: `/jobs/:job_id`

The page renders seven sections in order. All sections derive from the `JobDetailResponse` data or the output hooks.

#### Section 1 — Header

- `job_id` displayed in monospace font
- Status badge (reuse `JobStatusBadge`)

#### Section 2 — Summary

Displayed as a definition list or two-column table:

| Label | Source |
|-------|--------|
| Command | `job.command` |
| Worker | `job.worker_id` (or "—" if null) |
| Created | `job.created_at` |
| Claimed | `job.claimed_at` (or "—" if null) |
| Started | `job.started_at` (or "—" if null) |
| Finished | `job.finished_at` (or "—" if null) |

#### Section 3 — Runtime and Resources

| Label | Source | Notes |
|-------|--------|-------|
| Actual runtime | Derived from `started_at` / `finished_at` | See rules below |
| Peak memory | `job.peak_memory_mb` | See rules below |
| Max runtime | `job.max_runtime` (or "Unlimited") | |
| Max memory | `job.max_memory` (or "Unlimited") | |
| Kill reason | `job.kill_reason` | Displayed as a **warning banner** (visually prominent, e.g. amber/red) when non-null; placed at the top of the section |

**Actual runtime display rules**:
- If `started_at` is null: display "—" (job has not started)
- If `started_at` is set and `finished_at` is null and job status is `running`: display a **live elapsed time counter** that increments every second using the browser clock from `started_at`
- If both `started_at` and `finished_at` are set: display `finished_at - started_at` in human-readable format, e.g. "2m 34s"

**Peak memory display rules**:
- If job status is `running` or `assigned`: display "job in progress" placeholder
- If `peak_memory_mb` is null and job is in a non-running, non-terminal state (`pending`): display "not yet available" placeholder
- If `peak_memory_mb` is a number: display as `"{value} MB"` (e.g. "128.5 MB")

#### Section 4 — Environment Variables

- If `job.env_vars` is non-empty: render a two-column table with columns "Key" and "Value"; one row per entry.
- If `job.env_vars` is empty (`{}`): render "No environment variables" empty state text.

#### Section 5 — Output

Two sub-sections: stdout and stderr. Each is a labelled, scrollable `<pre>` block.

**State logic per stream** (applies independently to stdout and stderr):

| Job state | `base_url` | Hook result | Display |
|-----------|-----------|-------------|---------|
| Not terminal (pending/ready/assigned/running) | any | hook disabled | "job in progress" placeholder |
| Terminal | null | hook disabled | "Worker offline — logs unavailable" |
| Terminal | non-null | network error | "Worker offline — logs unavailable" |
| Terminal | non-null | 404 | "No output" empty state |
| Terminal | non-null | 200 | File content in scrollable `<pre>` block |

Stderr block must be **visually distinguished** from stdout (e.g. different border colour, label, or background tint).

#### Section 6 — Dependencies

- If `job.depends_on` is non-empty: render each UUID as a link to `/jobs/{uuid}`.
- If `job.depends_on` is empty: render "No dependencies" empty state.

#### Section 7 — Not Found / Error States

- If `GET /jobs/{job_id}` returns 404: render a full-page "Job not found" message with a link back to `/` (dashboard).
- If `GET /jobs/{job_id}` returns a network error: render a "Could not load job" error with a retry action.

### 7.6 Dashboard job rows — clickable

File: `frontend/src/widgets/jobs-panel/index.tsx`

Each job row in `JobsPanel` must be rendered as (or wrap) a link to `/jobs/{job.job_id}`.

**Feature file AC**: `system-dashboard.feature` scenario "Clicking a job row navigates to the job detail page" (AC-J009-08 in this spec — see §8).

### 7.7 Schedule Job page — link to detail after submit

This is already specified in v1 (T041 AC: "show link with path `/jobs/{job_id}`"). Now that the detail page exists, the link must resolve to a real page. No change to the form behaviour is required; the link destination is now functional.

### 7.8 Router update

File: `frontend/src/app/router.tsx`

Add route: `/jobs/:job_id` → `JobDetailPage`

---

## 8. Acceptance Criteria

### Backend (pytest-bdd)

All backend ACs are tested via BDD scenarios against a real PostgreSQL database using `db_run()` and the `TestClient`. All step functions must be synchronous `def` (not `async def`).

| AC | Scenario | Verification |
|----|----------|-------------|
| **AC-V2-B01** | `env_vars` is stored when a job is scheduled with a valid env_vars map | POST /jobs with `{"env_vars": {"APP_ENV": "staging"}}` → 201; GET /jobs/{job_id} returns `env_vars.APP_ENV == "staging"` |
| **AC-V2-B02** | `env_vars` defaults to `{}` when not provided | POST /jobs without `env_vars` field → 201; response `env_vars` is `{}` |
| **AC-V2-B03** | POST /jobs rejects env_vars with non-string value | POST /jobs with `{"env_vars": {"KEY": 123}}` → 422 with error on `env_vars` field |
| **AC-V2-B04** | GET /jobs/{job_id} returns `peak_memory_mb` | Job with `peak_memory_mb = 128.5` in DB → GET /jobs/{job_id} response includes `peak_memory_mb: 128.5` |
| **AC-V2-B05** | GET /jobs list response omits `peak_memory_mb` | GET /jobs response items do not contain `peak_memory_mb` key |
| **AC-V2-B06** | GET /workers response includes `base_url` | Worker registered with `base_url = "http://worker-01:8001"` → GET /workers response item has `base_url: "http://worker-01:8001"` |
| **AC-V2-B07** | GET /workers `base_url` is null when not configured | Worker registered without `LIGHTCRON_WORKER_BASE_URL` → GET /workers response item has `base_url: null` |
| **AC-V2-B08** | Worker writes stdout and stderr to files in LIGHTCRON_JOBS_DIR | Job process writes to stdout/stderr → files exist at configured path after exit |
| **AC-V2-B09** | Worker defaults to `/var/logs/lightcron/jobs` when LIGHTCRON_JOBS_DIR not set | Worker started without env var → uses `WORKER_DEFAULT_JOBS_DIR` constant value |
| **AC-V2-B10** | Partial output file retained after kill | Job killed mid-run → output file contains whatever was written before kill; file is not deleted |
| **AC-V2-B11** | Worker REST API GET /jobs/{job_id}/stdout serves file content | File exists at path → 200 text/plain with correct body |
| **AC-V2-B12** | Worker REST API GET /jobs/{job_id}/stderr serves file content | File exists at path → 200 text/plain with correct body |
| **AC-V2-B13** | Worker REST API returns 404 for missing file | No file at path → 404 `{"detail": "Not found"}` |
| **AC-V2-B14** | Worker registers base_url at startup | Startup with `LIGHTCRON_WORKER_BASE_URL=http://w:8001` → `worker_status.base_url` is `http://w:8001` |
| **AC-V2-B15** | Worker re-registration preserves base_url update | Worker re-registers with new base_url → new value stored; worker_id unchanged |

### Frontend (Playwright)

All frontend ACs map to scenarios in `specs/features/ui/job-detail.feature` and the updated `specs/features/ui/system-dashboard.feature`. Tests run against a Docker Compose stack (scheduler + DB + worker).

| AC | Maps to | Verification |
|----|---------|-------------|
| **AC-V2-F01** | AC-J011-01 | Detail page shows job_id, command, status, start_time, depends_on, max_runtime, max_memory |
| **AC-V2-F02** | AC-J011-02 | Completed job: actual runtime displayed as "2m 34s" |
| **AC-V2-F03** | AC-J011-03 | Running job: live elapsed time counter visible and incrementing |
| **AC-V2-F04** | AC-J011-04 | Completed job: peak_memory_mb displayed as "128.5 MB" |
| **AC-V2-F05** | AC-J011-05 | Pending job: peak memory shows "not yet available" placeholder |
| **AC-V2-F06** | AC-J011-06 | Completed job: stdout block populated from worker REST API |
| **AC-V2-F07** | AC-J011-07 | Worker returns 404 for stdout: stdout block shows "No output" |
| **AC-V2-F08** | AC-J011-08 | Completed job: stderr block populated, visually distinguished |
| **AC-V2-F09** | AC-J011-09 | Worker returns 404 for stderr: stderr block shows "No output" |
| **AC-V2-F10** | AC-J011-10 | Failed job with kill_reason: warning banner visible; stderr shown |
| **AC-V2-F11** | AC-J011-11 | Non-empty env_vars: displayed as two-column key/value table |
| **AC-V2-F12** | AC-J011-12 | Empty env_vars: "No environment variables" empty state |
| **AC-V2-F13** | AC-J011-13 | Unknown job_id: "Job not found" error state with dashboard link |
| **AC-V2-F14** | AC-J011-14 | Running job: output sections show "job in progress"; no fetch to worker |
| **AC-V2-F15** | AC-J011-15 | Auto-refresh: status updates without page reload; output fetched on terminal |
| **AC-V2-F16** | AC-J011-16 | env_vars passed to subprocess (verified via output file containing env var value) |
| **AC-V2-F17** | AC-J011-17 | Worker offline: both output sections show "Worker offline — logs unavailable" |
| **AC-V2-F18** | AC-J011-18 | UI constructs worker log URL from `base_url` in GET /workers response |
| **AC-V2-F19** | AC-J009 (new) | Dashboard job row click navigates to `/jobs/{job_id}` |

---

## 9. Frontend Constants (updated)

File: `frontend/src/shared/constants.ts`

```typescript
export const DASHBOARD_REFRESH_INTERVAL_MS: number = 10_000;  // unchanged from v1
export const JOB_DETAIL_REFRESH_INTERVAL_MS: number = 5_000;  // new
```

---

## 10. Known Limitations (additions to v1)

6. **Output file retention policy**: Output files (`{job_id}.stdout`, `{job_id}.stderr`) accumulate on the worker node indefinitely. No TTL or cleanup mechanism is implemented in v1. Operators must manage disk usage manually.

7. **Worker offline output unavailability**: If the worker node that ran a job is permanently decommissioned, stdout/stderr are permanently unavailable via the UI (the files are not replicated to the scheduler or any central store). This is a known and accepted trade-off of the file-based approach.

8. **Single-worker output**: If a job is reassigned to a different worker (currently impossible in v1 but noted for future), the output files would be on the original worker only.

---

## 11. Policy Rules (updated table)

Replace R12 and add R14. All other rules from v1 §Policy Rules are unchanged.

| # | Rule | Enforced by | Error |
|---|------|-------------|-------|
| R12 (amended) | Web UI must not call worker REST APIs directly, except for log retrieval (`GET /jobs/{job_id}/stdout` and `/stderr`) | Frontend design | — |
| R14 (new) | Worker CORS allowed origin must be configured via `LIGHTCRON_UI_ORIGIN` env var; no wildcard in production | Worker adapter | Ops condition C7 extended |
