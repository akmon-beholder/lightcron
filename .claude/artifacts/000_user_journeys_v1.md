# User Journeys — Lightcron

**Version**: 1.0
**Created**: 2026-03-21
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

---

## Journey: J001 — Schedule a Job

**Priority**: P1
**Lens**: Job Submitter

### User Story

As a job_submitter, I want to schedule a job with a start time and end time via the Web API so that Lightcron will run the job on a worker node during that window.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                        |
|------|--------------------------------------------------|--------------------------------------------------|-----------------------------------------|
| 1    | POST /jobs with command, start_time, and optional depends_on / max_runtime / max_memory | Validates payload; assigns job_id; stores as `pending` | HTTP 201, job_id returned |
| 2    | (no action — scheduler background loop)          | When start_time reached AND all depends_on jobs are `completed`, scheduler marks job `ready` | Job status is `ready` |
| 3    | GET /jobs/{job_id}                               | Returns current status                           | Status progresses through `ready` → `assigned` → `running` as worker_agents claim and start it |

### Acceptance Criteria

- **AC-J001-01**: Given a valid payload with command and start_time, When POST /jobs is called, Then HTTP 201 is returned with a unique job_id and status `pending`
- **AC-J001-02**: Given a job with start_time in the past, When POST /jobs is called, Then HTTP 422 is returned with a validation error
- **AC-J001-03**: Given a missing required field (command or start_time), When POST /jobs is called, Then HTTP 422 is returned identifying the missing field
- **AC-J001-04**: Given a valid payload with a depends_on list of existing job_ids, When POST /jobs is called, Then HTTP 201 is returned and the job stores the dependency list
- **AC-J001-05**: Given a depends_on list containing a job_id that does not exist, When POST /jobs is called, Then HTTP 422 is returned identifying the unknown dependency
- **AC-J001-06**: Given a valid payload with max_runtime set to a positive integer (seconds), When POST /jobs is called, Then HTTP 201 is returned and max_runtime is stored against the job
- **AC-J001-07**: Given a valid payload with no max_runtime or max_memory, When POST /jobs is called, Then the job is created with both limits set to unlimited

### BDD Feature File

**File**: `specs/features/job-management/schedule-job.feature`

### Error Scenarios

| Scenario               | Trigger                            | Expected Behaviour              |
|------------------------|------------------------------------|---------------------------------|
| Past start time        | start_time < now                   | HTTP 422, validation error      |
| Missing field          | command or start_time absent       | HTTP 422, field identified      |
| Unknown dependency     | depends_on contains unknown job_id | HTTP 422, unknown id identified |
| Invalid max_runtime    | max_runtime <= 0                   | HTTP 422, validation error      |
| Malformed JSON         | Unparseable request body           | HTTP 400                        |

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
| Stale last_seen + dead    | last_seen ≥60s; GET /health fails | Worker marked `offline`; jobs `timed_out` |
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
| Worker crashes after claim, before start | Heartbeat expires while `assigned`   | Scheduler marks job `timed_out` after 90s        |

---

## Journey: J004 — Job Runs to Completion

**Priority**: P1
**Lens**: Job Submitter / SRE

### User Story

As the worker_agent, I want to let a job process run until it exits naturally and record its exit code so that jobs complete on their own terms without needing a pre-defined end time.

### Flow Steps

| Step | User Action                                      | System Response                                  | Success Criteria                         |
|------|--------------------------------------------------|--------------------------------------------------|------------------------------------------|
| 1    | (worker_agent has started job process)           | Process runs; worker_agent monitors it           | Job status is `running`                  |
| 2    | Job process exits                                | worker_agent records exit_code; writes `completed` (exit 0) or `failed` (exit != 0) to jobs table | Job status is terminal |
| 3    | job_submitter calls GET /jobs/{job_id}           | Returns status, exit_code, started_at, finished_at, worker_id | Submitter can confirm outcome    |

### Acceptance Criteria

- **AC-J004-01**: Given a `running` job whose process exits with code 0, Then the worker_agent writes status `completed` and the exit_code to the jobs table
- **AC-J004-02**: Given a `running` job whose process exits with a non-zero code, Then the worker_agent writes status `failed` and the exit_code to the jobs table
- **AC-J004-03**: Given a job with max_runtime set and the process has been running for that duration, Then the worker_agent sends SIGTERM to the process
- **AC-J004-04**: Given a SIGTERM was sent and the process does not exit within the grace period, Then the worker_agent sends SIGKILL; the job is marked `failed` with a kill_reason of `max_runtime_exceeded`
- **AC-J004-05**: Given a job with no max_runtime set, Then the worker_agent lets the process run until it exits naturally with no timeout
- **AC-J004-06**: Given a completed or failed job, When GET /jobs/{job_id} is called, Then the response includes exit_code, started_at, finished_at, and worker_id

### BDD Feature File

**File**: `specs/features/job-management/job-lifecycle-completion.feature`

### Error Scenarios

| Scenario                   | Trigger                              | Expected Behaviour                              |
|----------------------------|--------------------------------------|-------------------------------------------------|
| Non-zero exit code         | Process exits with code != 0         | Status → `failed`, exit_code recorded           |
| max_runtime exceeded       | Process runs longer than max_runtime | SIGTERM → grace → SIGKILL; status → `failed`, kill_reason `max_runtime_exceeded` |
| Worker agent crashes mid-job | Heartbeat expires while `running`  | Scheduler marks job `timed_out`                 |

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
- **AC-J005-03**: Given a `completed`, `failed`, or `timed_out` job, When POST /jobs/{job_id}/cancel is called, Then HTTP 409 is returned (terminal state, cannot cancel)
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

As the scheduler, I want to detect when a worker has stopped sending heartbeats and automatically mark its jobs as `timed_out` so that stuck jobs do not remain in `running` or `assigned` state indefinitely.

### Flow Steps

| Step | User Action                                      | System Response                                                       | Success Criteria                          |
|------|--------------------------------------------------|-----------------------------------------------------------------------|-------------------------------------------|
| 1    | Worker stops sending heartbeats                  | Scheduler records no heartbeat received                               | last_seen timestamp stops updating        |
| 2    | (90s elapse since last heartbeat)                | Scheduler marks worker as `offline`; marks all its `running` and `assigned` jobs as `timed_out` | Worker is `offline`; jobs are `timed_out` |
| 3    | Operator calls GET /jobs?status=timed_out        | Returns list of affected jobs                                         | All stuck jobs visible for remediation    |

### Acceptance Criteria

- **AC-J008-01**: Given a worker with a `running` job that has not sent a heartbeat for 90s, Then the scheduler marks the worker as `offline` and the job as `timed_out`
- **AC-J008-02**: Given a worker with an `assigned` job (not yet confirmed running) that has not sent a heartbeat for 90s, Then the job is marked `timed_out`
- **AC-J008-03**: Given a worker that re-registers after going `offline`, Then it is treated as a new registration with a new worker_id
- **AC-J008-04**: Given a `timed_out` job, When queried via GET /jobs/{job_id}, Then status is `timed_out` with the worker_id that was assigned

### BDD Feature File

**File**: `specs/features/operations/stuck-job-recovery.feature`

### Error Scenarios

| Scenario                   | Trigger                              | Expected Behaviour                         |
|----------------------------|--------------------------------------|--------------------------------------------|
| Transient network blip     | Worker misses 1-2 heartbeats but recovers | Job remains `running` (threshold is 90s) |
| Multiple workers go offline | Mass worker failure                  | All affected jobs marked `timed_out`       |

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

J007 (Worker Fleet Status) — requires J002
```

---

## Test Coverage Matrix

| Journey | Feature File                                          | pytest-bdd | playwright-bdd |
|---------|-------------------------------------------------------|------------|----------------|
| J001    | specs/features/job-management/schedule-job.feature    | Yes        | No (API-only)  |
| J002    | specs/features/worker-management/worker-registration.feature | Yes | No (API-only) |
| J003    | specs/features/worker-management/job-dispatch.feature | Yes        | No (API-only)  |
| J004    | specs/features/job-management/job-lifecycle-completion.feature | Yes | No (API-only) |
| J005    | specs/features/job-management/cancel-job.feature      | Yes        | No (API-only)  |
| J006    | specs/features/job-management/query-job-status.feature | Yes       | No (API-only)  |
| J007    | specs/features/operations/worker-health-monitoring.feature | Yes   | No (API-only)  |
| J008    | specs/features/operations/stuck-job-recovery.feature  | Yes        | No (API-only)  |

---

## Handoff to Phase B

**Summary for Solution Design**:
- Total Journeys: 8
- P1 (Critical): J001, J002, J003, J004, J005, J006, J008
- P2 (Important): J007
- Key Technical Implications:
  - Scheduler has two background loops: ready-transition (pending→ready) and health-check (worker liveness)
  - Worker agents pull and claim jobs from the DB — no push/assignment from the scheduler
  - Atomic claim requires `SELECT FOR UPDATE SKIP LOCKED` or equivalent CAS to prevent double-claiming
  - `depends_on` is a list of job_ids; scheduler evaluates all before marking `ready`
  - Accepted trade-off: pull-based adds latency (poll interval) vs. push-based; acceptable for v1
  - Job process lifecycle (SIGTERM → grace → SIGKILL) owned by the worker_agent
  - All state lives in the database — ACID guarantees are critical for status transitions
- Suggested Implementation Order: J002 → J001 → J003 → J004 → J008 → J005 → J006 → J007
