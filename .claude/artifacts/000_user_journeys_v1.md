# User Journeys — Lightcron

**Version**: 1.3
**Created**: 2026-03-21
**Updated**: 2026-03-21 — v1.3: stdout/stderr stored as files on the worker node (not in DB); worker exposes new REST endpoints for log retrieval; UI fetches logs directly from worker REST API; GET /workers extended with base_url; R12 amended; J004 and J011 updated accordingly
**Agent**: design (Phase A)

---

## Composite Persona

**Name**: Alex Chen
**Role**: Backend Engineer at a product company; also wears a light ops hat
**Goals**: Schedule recurring and one-off workloads (report generation, data sync, cleanup tasks) reliably, without adding broker infrastructure to the stack
**Pain Points**: Celery required a broker; cron had no visibility; previous systems had silent failures
**Tech Comfort**: High — comfortable with HTTP APIs and Python; not interested in cluster-management ceremonies

---

## Lens Assessment

| Lens                | Key Concerns                                             | Priority |
|---------------------|----------------------------------------------------------|----------|
| Job Submitter       | Reliable submission, queryable status, silent failure prevention | P1 |
| Platform Operator   | Worker fleet management, job dispatch, no-downtime scaling | P1 |
| SRE / On-Call       | Fast incident diagnosis, cancel/force-stop without DB access | P1 |
| System Admin        | API auth, worker identity, audit trail, retention        | P2 |
| Web UI User         | At-a-glance system health; submit jobs without constructing raw HTTP requests | P2 |

---

## Journey: J001 — Schedule a Job

**Priority**: P1
**Lens**: Job Submitter

### User Story

As a job_submitter, I want to schedule a job with a start time and end time via the Web API so that Lightcron will run the job on a worker node during that window.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                        |
|------|--------------------------------------------------|--------------------------------------------------|-----------------------------------------|
| 1    | POST /jobs with command, start_time, and optional depends_on / max_runtime / max_memory / env_vars | Validates payload; assigns job_id; stores as `pending` | HTTP 201, job_id returned |
| 2    | (no action — scheduler background loop)          | When start_time reached AND all depends_on jobs are `completed`, scheduler marks job `ready` | Job status is `ready` |
| 3    | GET /jobs/{job_id}                               | Returns current status                           | Status progresses through `ready` → `assigned` → `running` as worker_agents claim and start it |

### Acceptance Criteria

- **AC-J001-01**: Given a valid payload with command and start_time, When POST /jobs is called, Then HTTP 201 is returned with a unique job_id and status `pending`
- **AC-J001-02**: Given a job with start_time in the past, When POST /jobs is called, Then HTTP 422 is returned with a validation error
- **AC-J001-03**: Given a missing required field (command or start_time), When POST /jobs is called, Then HTTP 422 is returned identifying the missing field
- **AC-J001-04**: Given a valid payload with a depends_on list of existing job_ids, When POST /jobs is called, Then HTTP 201 is returned and the job stores the dependency list
- **AC-J001-05**: Given a depends_on list containing a job_id that does not exist, When POST /jobs is called, Then HTTP 422 is returned identifying the unknown dependency
- **AC-J001-06**: Given a valid payload with max_runtime set to a positive integer (seconds), When POST /jobs is called, Then HTTP 201 is returned and max_runtime is stored against the job
- **AC-J001-07**: Given a valid payload with max_memory set to a positive integer (MB), When POST /jobs is called, Then HTTP 201 is returned and max_memory is stored against the job
- **AC-J001-08**: Given a valid payload with no max_runtime or max_memory, When POST /jobs is called, Then the job is created with both limits set to unlimited
- **AC-J001-09**: Given a valid payload with an env_vars map (string keys and string values), When POST /jobs is called, Then HTTP 201 is returned and the env_vars map is stored against the job and will be passed to the subprocess at execution time
- **AC-J001-10**: Given a valid payload with no env_vars field, When POST /jobs is called, Then the job is created with an empty env_vars map (the subprocess inherits the worker's environment without additions)
- **AC-J001-11**: Given a payload with env_vars that is not a flat key-value map of strings (e.g. nested objects, non-string values), When POST /jobs is called, Then HTTP 422 is returned identifying the invalid env_vars format

### BDD Feature File

**File**: `specs/features/job-management/schedule-job.feature`

### Error Scenarios

| Scenario               | Trigger                            | Expected Behaviour              |
|------------------------|------------------------------------|---------------------------------|
| Past start time        | start_time < now                   | HTTP 422, validation error      |
| Missing field          | command or start_time absent       | HTTP 422, field identified      |
| Unknown dependency     | depends_on contains unknown job_id | HTTP 422, unknown id identified |
| Invalid max_runtime    | max_runtime <= 0                   | HTTP 422, validation error      |
| Invalid max_memory     | max_memory <= 0                    | HTTP 422, validation error      |
| Malformed JSON         | Unparseable request body           | HTTP 400                        |
| Invalid env_vars type  | env_vars is not a flat string map  | HTTP 422, validation error      |

---

## Journey: J002 — Worker Node Registers

**Priority**: P1
**Lens**: Platform Operator

### User Story

As a worker_agent on a worker node, I want to register with the scheduler so that the scheduler knows this node is available to accept job assignments.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                        |
|------|--------------------------------------------------|--------------------------------------------------|-----------------------------------------|
| 1    | worker_agent starts up and upserts row to worker_status with hostname | Scheduler reads worker as `online` | Row in worker_status with status `online` |
| 2    | worker_agent updates worker_status.last_seen every 30s | Scheduler reads current last_seen | last_seen timestamp is current          |
| 3    | worker_agent stops updating last_seen            | After 90s scheduler marks worker_status as `offline` | Worker status is `offline`         |

### Acceptance Criteria

- **AC-J002-01**: Given a worker_agent starts up, When it upserts to worker_status with its hostname, Then a row exists with status `online` and a unique worker_id
- **AC-J002-02**: Given a registered worker_agent, When it updates worker_status.last_seen every 30s, Then last_seen reflects the current time
- **AC-J002-03**: Given a worker_agent that has not updated last_seen for 90s, Then the scheduler marks its worker_status row as `offline`
- **AC-J002-04**: Given a worker_status row with a stale last_seen (≥60s but <90s), When the scheduler calls GET /health on the worker_agent and receives 200, Then the worker remains `online`

### BDD Feature File

**File**: `specs/features/worker-management/worker-registration.feature`

### Error Scenarios

| Scenario              | Trigger                              | Expected Behaviour                         |
|-----------------------|--------------------------------------|--------------------------------------------|
| last_seen timeout     | No DB update for 90s                 | Scheduler marks worker_status `offline`    |
| Stale last_seen + healthy | last_seen ≥60s; GET /health → 200 | Worker remains `online`               |
| Stale last_seen + dead    | last_seen ≥60s; GET /health fails | Worker marked `offline`; jobs `lost` |
| Duplicate registration | Same hostname re-registers          | Existing worker_id preserved; status reset to `online` |

---

## Journey: J003 — Job Becomes Ready and Worker Claims It

**Priority**: P1
**Lens**: Platform Operator

### User Story

As the scheduler and worker_agent, I want the scheduler to mark a job `ready` when its conditions are met, and worker_agents to compete to atomically claim `ready` jobs, so that no central dispatcher is needed and the system scales by adding workers.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                         |
|------|--------------------------------------------------|--------------------------------------------------|------------------------------------------|
| 1    | (scheduler background loop runs)                 | Scheduler checks `pending` jobs: if start_time ≤ now AND all depends_on are `completed`, writes status=`ready` | Job status is `ready` |
| 2    | worker_agent polls the jobs table for `ready` jobs | Finds one or more `ready` jobs                  | worker_agent has candidate job_ids       |
| 3    | worker_agent attempts atomic claim               | `UPDATE jobs SET status='assigned', worker_id=<self> WHERE job_id=? AND status='ready'`; checks rows affected | Winner: status is `assigned` with worker_id; loser: 0 rows affected, tries next |
| 4    | worker_agent starts the job process              | worker_agent updates jobs table to `running`     | Job status is `running`                  |

### Acceptance Criteria

- **AC-J003-01**: Given a `pending` job whose start_time has been reached and has no unmet dependencies, When the scheduler loop runs, Then the job status transitions to `ready`
- **AC-J003-02**: Given a `pending` job with a dependency that is not yet `completed`, When the scheduler loop runs, Then the job remains `pending` even if start_time has passed
- **AC-J003-03**: Given a `ready` job, When a worker_agent performs an atomic claim, Then the job status transitions to `assigned` with the claiming worker's worker_id
- **AC-J003-04**: Given two worker_agents attempting to claim the same `ready` job simultaneously, Then exactly one succeeds (job status `assigned`); the other observes 0 rows affected and moves on
- **AC-J003-05**: Given a job is `assigned`, When the worker_agent starts the process and updates the jobs table, Then the job status transitions to `running`
- **AC-J003-06**: Given no `ready` jobs exist, When a worker_agent polls, Then it finds nothing to claim and waits for the next poll interval

### BDD Feature File

**File**: `specs/features/worker-management/job-dispatch.feature`

### Error Scenarios

| Scenario                           | Trigger                                   | Expected Behaviour                              |
|------------------------------------|-------------------------------------------|-------------------------------------------------|
| Dependency not yet completed       | depends_on job still `running`            | Job stays `pending`; re-evaluated each scheduler loop |
| All workers offline                | No `online` workers polling               | Job stays `ready` until a worker comes online and polls |
| Claim race condition               | Two workers claim simultaneously          | Exactly one wins; other retries with next `ready` job |
| Worker crashes after claim, before start | Heartbeat expires while `assigned`   | Scheduler marks job `lost` after 90s        |

---

## Journey: J004 — Job Runs to Completion

**Priority**: P1
**Lens**: Job Submitter / SRE

### User Story

As the worker_agent, I want to let a job process run until it exits naturally and record its exit code so that jobs complete on their own terms without needing a pre-defined end time.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                         |
|------|--------------------------------------------------|--------------------------------------------------|------------------------------------------|
| 1    | (worker_agent has started job process)           | Process runs; worker_agent monitors it; stdout and stderr are streamed to files on the worker node | Job status is `running`; output files exist at `{LIGHTCRON_JOBS_DIR}/{job_id}.stdout` and `{LIGHTCRON_JOBS_DIR}/{job_id}.stderr` |
| 2    | Job process exits                                | worker_agent records exit_code and peak_memory_mb; writes `completed` (exit 0) or `failed` (exit != 0) to jobs table; output files remain on disk | Job status is terminal; output files readable via worker REST API |
| 3    | job_submitter calls GET /jobs/{job_id}           | Returns status, exit_code, started_at, finished_at, worker_id, peak_memory_mb | Submitter can confirm outcome    |

### Acceptance Criteria

- **AC-J004-01**: Given a `running` job whose process exits with code 0, Then the worker_agent writes status `completed` and the exit_code to the jobs table
- **AC-J004-02**: Given a `running` job whose process exits with a non-zero code, Then the worker_agent writes status `failed` and the exit_code to the jobs table
- **AC-J004-03**: Given a job with max_runtime set and the process has been running for that duration, Then the worker_agent sends SIGTERM to the process
- **AC-J004-04**: Given a SIGTERM was sent and the process does not exit within the grace period, Then the worker_agent sends SIGKILL; the job is marked `failed` with a kill_reason of `max_runtime_exceeded`
- **AC-J004-05**: Given a job with no max_runtime set, Then the worker_agent lets the process run until it exits naturally with no runtime timeout
- **AC-J004-07**: Given a job with max_memory set and the process exceeds that limit, Then the worker_agent sends SIGTERM to the process
- **AC-J004-08**: Given a SIGTERM was sent for a memory violation and the process does not exit within the grace period, Then the worker_agent sends SIGKILL; the job is marked `failed` with a kill_reason of `max_memory_exceeded`
- **AC-J004-09**: Given a job with no max_memory set, Then the worker_agent places no memory limit on the process
- **AC-J004-06**: Given a completed or failed job, When GET /jobs/{job_id} is called, Then the response includes exit_code, started_at, finished_at, worker_id, and peak_memory_mb
- **AC-J004-10**: Given a job process is running, Then the worker_agent streams its stdout to `{LIGHTCRON_JOBS_DIR}/{job_id}.stdout` and its stderr to `{LIGHTCRON_JOBS_DIR}/{job_id}.stderr`; the files are created at process start and remain on disk after the process exits
- **AC-J004-11**: Given `LIGHTCRON_JOBS_DIR` is not set, Then the worker_agent defaults to `/var/logs/lightcron/jobs` as the output directory
- **AC-J004-12**: Given a job that is killed (max_runtime or max_memory exceeded), Then the output files contain whatever was written up to the point of termination; the files are not deleted or truncated by the kill sequence

### BDD Feature File

**File**: `specs/features/job-management/job-lifecycle-completion.feature`

### Error Scenarios

| Scenario                   | Trigger                              | Expected Behaviour                              |
|----------------------------|--------------------------------------|-------------------------------------------------|
| Non-zero exit code         | Process exits with code != 0         | Status → `failed`, exit_code recorded           |
| max_runtime exceeded       | Process runs longer than max_runtime | SIGTERM → grace → SIGKILL; status → `failed`, kill_reason `max_runtime_exceeded`; partial output files retained |
| max_memory exceeded        | Process exceeds max_memory           | SIGTERM → grace → SIGKILL; status → `failed`, kill_reason `max_memory_exceeded`; partial output files retained  |
| Worker agent crashes mid-job | Heartbeat expires while `running`  | Scheduler marks job `lost`; output files remain on disk at whatever state they were |
| Output directory missing   | LIGHTCRON_JOBS_DIR path does not exist | worker_agent creates the directory on startup  |

---

## Journey: J005 — Cancel a Job

**Priority**: P1
**Lens**: SRE / Job Submitter

### User Story

As an sre_operator or job_submitter, I want to cancel a job via the API regardless of whether it is pending, assigned, or running so that I can stop unwanted or stuck work without direct database or node access.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                         |
|------|--------------------------------------------------|--------------------------------------------------|------------------------------------------|
| 1    | POST /jobs/{job_id}/cancel                       | Scheduler writes `cancelled` to jobs table; if `running`, worker_agent detects on next poll | HTTP 200, status `cancelled` |
| 2    | (if job was running) Worker agent receives cancellation | Worker agent sends SIGTERM to job process | Job process stopped                      |
| 3    | GET /jobs/{job_id}                               | Returns status `cancelled`                       | Final status is `cancelled`              |

### Acceptance Criteria

- **AC-J005-01**: Given a `pending` job, When POST /jobs/{job_id}/cancel is called, Then HTTP 200 is returned and status is `cancelled`
- **AC-J005-02**: Given a `running` job, When POST /jobs/{job_id}/cancel is called, Then HTTP 200 is returned, the scheduler writes `cancelled` to the jobs table, and the worker_agent stops the process on its next poll
- **AC-J005-03**: Given a `completed`, `failed`, or `lost` job, When POST /jobs/{job_id}/cancel is called, Then HTTP 409 is returned (terminal state, cannot cancel)
- **AC-J005-04**: Given a job_id that does not exist, When POST /jobs/{job_id}/cancel is called, Then HTTP 404 is returned

### BDD Feature File

**File**: `specs/features/job-management/cancel-job.feature`

### Error Scenarios

| Scenario              | Trigger                           | Expected Behaviour         |
|-----------------------|-----------------------------------|----------------------------|
| Already terminal      | Job is `completed` or `failed`    | HTTP 409 Conflict          |
| Unknown job           | job_id not found                  | HTTP 404                   |
| Runner unreachable    | Worker offline when cancellation sent | Job marked `cancelled`; runner cleans up on reconnect |

---

## Journey: J006 — Query Job Status

**Priority**: P1
**Lens**: Job Submitter

### User Story

As a job_submitter, I want to query the current status and execution details of a job via the API so that my application can react to job completion, failure, or progress.

### Flow Steps

| Step | User Action                 | System Response                                                  | Success Criteria                          |
|------|----------------------------|------------------------------------------------------------------|-------------------------------------------|
| 1    | GET /jobs/{job_id}          | Returns job_id, status, command, start_time, end_time, worker_id (if assigned), timestamps | HTTP 200 with full job record  |
| 2    | GET /jobs?status=running    | Returns list of jobs matching the filter                         | HTTP 200 with filtered list               |

### Acceptance Criteria

- **AC-J006-01**: Given a valid job_id, When GET /jobs/{job_id} is called, Then HTTP 200 is returned with status, command, start_time, end_time, and (if assigned) worker_id
- **AC-J006-02**: Given a job_id that does not exist, When GET /jobs/{job_id} is called, Then HTTP 404 is returned
- **AC-J006-03**: Given a status filter, When GET /jobs?status={status} is called, Then only jobs with that status are returned
- **AC-J006-04**: Given no jobs exist, When GET /jobs is called, Then HTTP 200 is returned with an empty list

### BDD Feature File

**File**: `specs/features/job-management/query-job-status.feature`

### Error Scenarios

| Scenario        | Trigger             | Expected Behaviour |
|-----------------|---------------------|--------------------|
| Unknown job_id  | job_id not found    | HTTP 404           |
| Invalid filter  | Unknown status value | HTTP 422           |

---

## Journey: J007 — View Worker Fleet Status

**Priority**: P2
**Lens**: Platform Operator / SRE

### User Story

As a platform_operator, I want to query all registered workers and their current status so that I can see which nodes are healthy, busy, or offline at a glance.

### Flow Steps

| Step | User Action     | System Response                                                                 | Success Criteria                      |
|------|-----------------|---------------------------------------------------------------------------------|---------------------------------------|
| 1    | GET /workers    | Returns list of workers with worker_id, hostname, status, last_seen, running job count | HTTP 200 with full worker list  |

### Acceptance Criteria

- **AC-J007-01**: Given registered workers exist, When GET /workers is called, Then HTTP 200 is returned with each worker's worker_id, hostname, status, last_seen timestamp, and count of currently running jobs
- **AC-J007-02**: Given no workers are registered, When GET /workers is called, Then HTTP 200 is returned with an empty list
- **AC-J007-03**: Given a worker whose last heartbeat was more than 90s ago, Then its status is `offline` in the response

### BDD Feature File

**File**: `specs/features/operations/worker-health-monitoring.feature`

### Error Scenarios

| Scenario        | Trigger                   | Expected Behaviour                    |
|-----------------|---------------------------|---------------------------------------|
| Stale worker    | Heartbeat expired > 90s   | Worker appears in list as `offline`   |

---

## Journey: J008 — Detect and Recover Stuck Job

**Priority**: P1
**Lens**: SRE / Platform Operator

### User Story

As the scheduler, I want to detect when a worker has stopped sending heartbeats and automatically mark its jobs as `lost` so that stuck jobs do not remain in `running` or `assigned` state indefinitely.

### Flow Steps

| Step | User Action                                      | System Response                                                       | Success Criteria                          |
|------|--------------------------------------------------|-----------------------------------------------------------------------|-------------------------------------------|
| 1    | Worker stops sending heartbeats                  | Scheduler records no heartbeat received                               | last_seen timestamp stops updating        |
| 2    | (90s elapse since last heartbeat)                | Scheduler marks worker as `offline`; marks all its `running` and `assigned` jobs as `lost` | Worker is `offline`; jobs are `lost` |
| 3    | Operator calls GET /jobs?status=lost        | Returns list of affected jobs                                         | All stuck jobs visible for remediation    |

### Acceptance Criteria

- **AC-J008-01**: Given a worker with a `running` job that has not sent a heartbeat for 90s, Then the scheduler marks the worker as `offline` and the job as `lost`
- **AC-J008-02**: Given a worker with an `assigned` job (not yet confirmed running) that has not sent a heartbeat for 90s, Then the job is marked `lost`
- **AC-J008-03**: Given a worker that re-registers after going `offline`, Then it receives the same worker_id as before (matched by hostname) and its status is reset to `online`
- **AC-J008-04**: Given a `lost` job, When queried via GET /jobs/{job_id}, Then status is `lost` with the worker_id that was assigned
- **AC-J008-05**: Given a worker_agent reconnects and finds a job it was running has status `lost` in the jobs table, Then the worker_agent kills the process and does not update the job status (the scheduler's `lost` write is authoritative)

### BDD Feature File

**File**: `specs/features/operations/stuck-job-recovery.feature`

### Error Scenarios

| Scenario                   | Trigger                              | Expected Behaviour                         |
|----------------------------|--------------------------------------|--------------------------------------------|
| Transient network blip     | Worker misses 1-2 heartbeats but recovers | Job remains `running` (threshold is 90s) |
| Multiple workers go offline | Mass worker failure                  | All affected jobs marked `lost`       |

---

## Journey: J009 — View System State via Web UI Dashboard

**Priority**: P2
**Lens**: Platform Operator / SRE

### User Story

As a platform_operator or sre_operator, I want a web dashboard that shows the current state of the worker fleet and recent jobs so that I can assess system health without constructing REST API requests.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                        |
|------|--------------------------------------------------|--------------------------------------------------|-----------------------------------------|
| 1    | Navigate to the dashboard URL                    | UI fetches GET /workers and GET /jobs from the scheduler REST API | Dashboard renders worker fleet panel and jobs panel |
| 2    | Apply a status filter to the jobs panel          | UI fetches GET /jobs?status={filter}             | Jobs panel updates to show only matching jobs |
| 3    | (auto-refresh interval elapses)                  | UI re-fetches both endpoints                     | Panels reflect latest state without a page reload |

### Acceptance Criteria

- **AC-J009-01**: Given registered workers, When the dashboard is loaded, Then the worker fleet panel shows each worker's worker_id, hostname, status, last_seen, and count of running jobs
- **AC-J009-02**: Given an offline worker, When the dashboard is loaded, Then that worker appears in the fleet panel with status `offline`
- **AC-J009-03**: Given jobs in the jobs table, When the dashboard is loaded, Then the jobs panel shows each job's job_id, command (truncated if long), status, and worker_id (if assigned)
- **AC-J009-04**: Given the jobs panel is displaying jobs, When the user selects a status filter, Then only jobs with that status are shown
- **AC-J009-05**: Given the dashboard is open, When the auto-refresh interval elapses, Then the UI re-fetches worker and job data and updates both panels without a full page reload
- **AC-J009-06**: Given no workers are registered, When the dashboard is loaded, Then the worker fleet panel shows a "no workers registered" empty state
- **AC-J009-07**: Given no jobs exist, When the dashboard is loaded, Then the jobs panel shows a "no jobs" empty state

### BDD Feature File

**File**: `specs/features/ui/system-dashboard.feature`

### Error Scenarios

| Scenario              | Trigger                         | Expected Behaviour                               |
|-----------------------|---------------------------------|--------------------------------------------------|
| No workers            | Empty worker_status table       | Empty state message in worker fleet panel        |
| No jobs               | Empty jobs table                | Empty state message in jobs panel                |
| Offline worker        | Worker last_seen > 90s          | Worker shown as `offline` in fleet panel         |

---

## Journey: J010 — Schedule a Job via Web UI Form

**Priority**: P2
**Lens**: Platform Operator / Job Submitter

### User Story

As a platform_operator or job_submitter, I want to schedule a new job by filling in a form in the web UI so that I can submit jobs without constructing raw HTTP requests.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                        |
|------|--------------------------------------------------|--------------------------------------------------|-----------------------------------------|
| 1    | Navigate to the "Schedule Job" page              | Form renders with fields: command, start_time, max_runtime (optional), max_memory (optional), depends_on (optional), env_vars (optional) | Form is usable |
| 2    | Fill in the form and submit                      | UI POSTs to /jobs with the form data             | HTTP 201; job_id displayed; link to job detail shown |
| 3    | Submit with invalid data                         | UI shows inline validation errors (client-side or from API 422 response) | User can correct and resubmit |

### Acceptance Criteria

- **AC-J010-01**: Given valid command and start_time, When the user submits the form, Then a job is created (HTTP 201) and the job_id is displayed to the user
- **AC-J010-02**: Given the user leaves command empty, When the user submits, Then an inline validation error is shown on the command field and the form is not submitted to the API
- **AC-J010-03**: Given the user enters a start_time in the past, When the user submits, Then an inline validation error is shown on the start_time field
- **AC-J010-04**: Given the user enters a non-positive max_runtime, When the user submits, Then an inline validation error is shown on the max_runtime field
- **AC-J010-05**: Given the user enters a non-positive max_memory, When the user submits, Then an inline validation error is shown on the max_memory field
- **AC-J010-06**: Given valid form data including all optional fields (max_runtime, max_memory, depends_on), When the user submits, Then the job is created with all fields stored
- **AC-J010-07**: Given the server returns a 422 error for an unknown depends_on job_id, When the response is received, Then the UI displays the server error message inline

### BDD Feature File

**File**: `specs/features/ui/schedule-job-ui.feature`

### Error Scenarios

| Scenario                  | Trigger                            | Expected Behaviour                              |
|---------------------------|------------------------------------|-------------------------------------------------|
| Missing command           | command field empty                | Inline validation error; no API call made       |
| Past start_time           | start_time < now                   | Inline validation error; no API call made       |
| Invalid max_runtime       | max_runtime ≤ 0                    | Inline validation error; no API call made       |
| Invalid max_memory        | max_memory ≤ 0                     | Inline validation error; no API call made       |
| Unknown depends_on        | Server returns 422                 | Server error displayed inline                   |

---

## Journey: J011 — Inspect Job Detail via Web UI

**Priority**: P2
**Lens**: Platform Operator / SRE / Job Submitter

### User Story

As a platform_operator or sre_operator, I want to click on a job in the dashboard and see its full detail — including stdout/stderr output, environment variables it ran with, its actual runtime, and peak memory usage — so that I can diagnose failures and verify job behaviour without database access.

### Background

This journey introduces new data accessible from the job detail page. Some fields are stored in the `jobs` table; stdout and stderr are stored as files on the worker node and retrieved via the worker's REST API.

**Fields stored in the `jobs` table** (returned by `GET /jobs/{job_id}`):
- **`env_vars`**: a flat key-value map of strings submitted at schedule time (POST /jobs) and passed by the worker to the subprocess environment at execution time. Stored at creation; not mutated after submission.
- **`peak_memory_mb`**: the highest RSS memory reading (in MB) observed by psutil during execution. Written by the worker_agent to the DB on job completion or termination. NULL before the job has started.

**Fields stored as files on the worker node**:
- **stdout**: written to `{LIGHTCRON_JOBS_DIR}/{job_id}.stdout` during job execution.
- **stderr**: written to `{LIGHTCRON_JOBS_DIR}/{job_id}.stderr` during job execution.
- Retrieved via new worker REST API endpoints (see below). The web UI calls the worker REST API directly for log retrieval — this is an explicit exception to the general rule that the UI communicates only with the scheduler.

**New worker REST API endpoints** (added in this journey):
- `GET /jobs/{job_id}/stdout` → `200 text/plain` (file content) | `404` if file not found
- `GET /jobs/{job_id}/stderr` → `200 text/plain` (file content) | `404` if file not found
- Worker CORS must be configured to allow the UI origin (same mechanism as the scheduler's `LIGHTCRON_UI_ORIGIN`).

**Worker URL discovery**: `GET /workers` (scheduler) is extended with a `base_url` field (e.g. `http://worker-hostname:8001`) so the UI can construct worker endpoint URLs without hardcoding. The worker registers its base URL with the scheduler at startup.

Actual runtime is derived by the UI from `started_at` and `finished_at` — not stored separately.

### Flow Steps

| Step | User Action                                           | System Response                                                                    | Success Criteria                                     |
|------|-------------------------------------------------------|------------------------------------------------------------------------------------|------------------------------------------------------|
| 1    | User is on the dashboard jobs panel; clicks on a job row | UI navigates to the job detail page at `/jobs/{job_id}` | Job detail page loads for that job_id              |
| 2    | UI fetches `GET /jobs/{job_id}` from scheduler        | Scheduler returns the job object including env_vars and peak_memory_mb (no output content) | HTTP 200; core fields rendered; worker_id known |
| 3    | UI fetches `GET /workers` (or uses cached data) to resolve the worker's base_url | Scheduler returns worker list including base_url for each worker | UI has the target worker's API URL |
| 4    | UI fetches `GET /jobs/{job_id}/stdout` and `GET /jobs/{job_id}/stderr` from the worker's REST API | Worker returns file content as text/plain | stdout and stderr blocks populated |
| 5    | User inspects stdout/stderr output                    | UI renders each stream in a separate read-only scrollable code block; stderr visually distinguished from stdout | Output is readable; long output does not overflow the layout |
| 6    | User inspects env_vars                                | UI renders env_vars as a two-column table (key / value); empty state shown if no env_vars were set | Env vars are easy to scan |
| 7    | User navigates back to dashboard                      | Browser back button or a "Back to dashboard" link returns to `/`                  | Navigation works as expected                         |

### Acceptance Criteria

- **AC-J011-01**: Given a job_id that exists, When the user navigates to `/jobs/{job_id}` in the UI, Then the job detail page loads and displays the job's core fields: job_id, command, status, start_time, depends_on list, max_runtime, and max_memory
- **AC-J011-02**: Given a completed job with started_at and finished_at both set, When the detail page is loaded, Then the UI displays the actual runtime computed from `finished_at - started_at` in a human-readable format (e.g. "2m 34s")
- **AC-J011-03**: Given a running job with started_at set and finished_at NULL, When the detail page is loaded, Then the UI displays a live elapsed time counting up from started_at using the current local clock
- **AC-J011-04**: Given a completed or failed job with peak_memory_mb set, When the detail page is loaded, Then the UI displays peak_memory_mb in megabytes (e.g. "128 MB")
- **AC-J011-05**: Given a pending or assigned job (not yet started) where peak_memory_mb is NULL, When the detail page is loaded, Then the peak memory field shows a "not yet available" placeholder rather than a blank or error
- **AC-J011-06**: Given a completed job, When the detail page loads, Then the UI fetches `GET /jobs/{job_id}/stdout` from the worker's REST API and renders the response in a read-only scrollable code block
- **AC-J011-07**: Given the worker returns a 404 for `GET /jobs/{job_id}/stdout` (file not found or job produced no stdout), When the detail page loads, Then the stdout block shows a "No output" empty state message
- **AC-J011-08**: Given a completed job, When the detail page loads, Then the UI fetches `GET /jobs/{job_id}/stderr` from the worker's REST API and renders the response in a read-only scrollable code block, visually distinguished from stdout
- **AC-J011-09**: Given the worker returns a 404 for `GET /jobs/{job_id}/stderr`, When the detail page loads, Then the stderr block shows a "No output" empty state message
- **AC-J011-10**: Given a failed job with kill_reason set (e.g. `max_runtime_exceeded` or `max_memory_exceeded`), When the detail page is loaded, Then kill_reason is displayed prominently (e.g. as a warning banner above the output sections), and stderr is shown even if partial
- **AC-J011-11**: Given a job whose env_vars map is non-empty, When the detail page is loaded, Then the UI renders the env_vars as a two-column key/value table
- **AC-J011-12**: Given a job whose env_vars map is empty (no env_vars were submitted), When the detail page is loaded, Then the env_vars section shows a "No environment variables" empty state rather than a blank table
- **AC-J011-13**: Given a job_id that does not exist in the scheduler, When the UI fetches GET /jobs/{job_id}, Then the detail page renders a clear "Job not found" error state with a link back to the dashboard
- **AC-J011-14**: Given a running job, When the detail page is displayed, Then the output sections show a "job in progress" placeholder; the UI does not attempt to fetch output from the worker until the job is in a terminal state
- **AC-J011-15**: Given the detail page is open and the auto-refresh interval elapses, Then the UI re-fetches `GET /jobs/{job_id}` from the scheduler and updates all displayed fields; once the job reaches a terminal state the UI also fetches the output files from the worker
- **AC-J011-16**: Given a job with env_vars submitted at schedule time, When the worker_agent claims and starts the job, Then the subprocess is launched with the env_vars merged into the worker's environment (worker base env vars plus the job's env_vars; job env_vars take precedence on key collision)
- **AC-J011-17**: Given the worker node is offline or unreachable, When the UI attempts to fetch output files, Then the output sections display a "Worker offline — logs unavailable" message rather than an error
- **AC-J011-18**: Given the `GET /workers` response includes a `base_url` for each worker, When the UI needs to fetch output for a job, Then it uses the `base_url` of the job's assigned worker to construct the log endpoint URL

### BDD Feature File

**File**: `specs/features/ui/job-detail.feature`

### Error Scenarios

| Scenario                         | Trigger                                         | Expected Behaviour                                                               |
|----------------------------------|-------------------------------------------------|----------------------------------------------------------------------------------|
| Job not found                    | job_id in URL does not exist in DB              | Detail page shows "Job not found" error state with link back to dashboard        |
| Job still running — no output    | Job status is not terminal                      | Output sections show "job in progress" placeholder; no fetch to worker API       |
| Job killed — partial stderr      | kill_reason set; stderr file may be partial     | kill_reason shown as warning banner; stderr block shows partial content from worker API |
| No env_vars                      | env_vars is empty map                           | Env vars section shows "No environment variables" empty state                   |
| Scheduler API unreachable        | GET /jobs/{job_id} returns network error        | Detail page shows generic "Could not load job" error with retry option           |
| Worker offline                   | Worker REST API unreachable                     | Output sections show "Worker offline — logs unavailable"                         |
| Output file not found on worker  | Worker returns 404 for stdout or stderr         | Relevant block shows "No output" empty state                                     |

---

## Journey Dependency Map

```
J002 (Worker Registration)
  └── J003 (Job Dispatch) — requires at least one online worker
        └── J004 (Job Completion) — requires a running job
        └── J008 (Stuck Job Recovery) — requires a running job and worker

J001 (Schedule Job)
  └── J003 (Job Dispatch) — job must exist to be dispatched
  └── J005 (Cancel Job) — job must exist to be cancelled
  └── J006 (Query Status) — job must exist to query
  └── J010 (Schedule Job via UI) — UI wraps J001 REST call
  └── J011 (Job Detail via UI) — job must exist and have run to show detail

J007 (Worker Fleet Status) — requires J002
  └── J009 (System Dashboard) — UI wraps J006 + J007 REST calls
        └── J011 (Job Detail via UI) — user navigates from dashboard job row to detail page

J004 (Job Completion) — worker writes output and peak_memory_mb on completion
  └── J011 (Job Detail via UI) — detail page shows output and memory stats from completed job

J001 (Schedule Job with env_vars) — env_vars stored at creation
  └── J011 (Job Detail via UI) — detail page shows env_vars from job record
```

---

## Test Coverage Matrix

| Journey | Feature File                                                        | pytest-bdd | playwright-bdd |
|---------|---------------------------------------------------------------------|------------|----------------|
| J001    | specs/features/job-management/schedule-job.feature                  | Yes        | No (API-only)  |
| J002    | specs/features/worker-management/worker-registration.feature        | Yes        | No (API-only)  |
| J003    | specs/features/worker-management/job-dispatch.feature               | Yes        | No (API-only)  |
| J004    | specs/features/job-management/job-lifecycle-completion.feature      | Yes        | No (API-only)  |
| J005    | specs/features/job-management/cancel-job.feature                    | Yes        | No (API-only)  |
| J006    | specs/features/job-management/query-job-status.feature              | Yes        | No (API-only)  |
| J007    | specs/features/operations/worker-health-monitoring.feature          | Yes        | No (API-only)  |
| J008    | specs/features/operations/stuck-job-recovery.feature                | Yes        | No (API-only)  |
| J009    | specs/features/ui/system-dashboard.feature                          | No         | Yes            |
| J010    | specs/features/ui/schedule-job-ui.feature                           | No         | Yes            |
| J011    | specs/features/ui/job-detail.feature                                | No         | Yes            |

---

## Handoff to Phase B

**Summary for Solution Design**:
- Total Journeys: 11
- P1 (Critical): J001, J002, J003, J004, J005, J006, J008
- P2 (Important): J007, J009, J010, J011
- Key Technical Implications:
  - Scheduler has two background loops: ready-transition (pending→ready) and health-check (worker liveness)
  - Worker agents pull and claim jobs from the DB — no push/assignment from the scheduler
  - Atomic claim requires `SELECT FOR UPDATE SKIP LOCKED` or equivalent CAS to prevent double-claiming
  - `depends_on` is a list of job_ids; scheduler evaluates all before marking `ready`
  - Accepted trade-off: pull-based adds latency (poll interval) vs. push-based; acceptable for v1
  - Job process lifecycle (SIGTERM → grace → SIGKILL) owned by the worker_agent
  - All state lives in the database — ACID guarantees are critical for status transitions
  - Web UI (J009, J010, J011) is a React/TypeScript SPA; communicates with the scheduler REST API for all data except job output logs; tested with Playwright
  - **New (v1.3)**: `env_vars` is a flat key-value string map stored on the job at creation and passed by the worker_agent to the subprocess environment at execution time; displayed on the job detail page
  - **New (v1.3)**: stdout and stderr are written as files on the worker node during job execution (`{LIGHTCRON_JOBS_DIR}/{job_id}.stdout` / `.stderr`); `LIGHTCRON_JOBS_DIR` defaults to `/var/logs/lightcron/jobs`; worker creates the directory on startup if absent
  - **New (v1.3)**: Worker exposes two new REST endpoints: `GET /jobs/{job_id}/stdout` and `GET /jobs/{job_id}/stderr` returning `text/plain`; the Web UI calls these directly (explicit exception to the general scheduler-only rule)
  - **New (v1.3)**: Worker CORS must allow the UI origin; `GET /workers` response extended with `base_url` field so the UI can discover worker endpoints at runtime
  - **New (v1.3)**: `peak_memory_mb` is the highest RSS reading observed during execution, written to the DB on job completion or termination; displayed on the job detail page
  - **New (v1.3)**: Actual runtime is derived in the UI from `started_at` / `finished_at`; not stored separately
  - **New (v1.3)**: `jobs` table requires two new columns: `env_vars` (JSONB NOT NULL DEFAULT '{}') and `peak_memory_mb` (DOUBLE PRECISION NULL); no stdout/stderr columns in DB
- Suggested Implementation Order: J002 → J001 → J003 → J004 → J008 → J005 → J006 → J007 → J009 → J010 → J011
