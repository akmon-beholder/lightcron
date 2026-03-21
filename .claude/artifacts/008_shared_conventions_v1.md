# Shared Conventions — Lightcron

**Version**: v1
**Created**: 2026-03-21
**Agent**: design (Phase A)
**Purpose**: Single source of truth for naming, roles, thresholds, and patterns.
             Every BDD generation agent receives this document verbatim.

---

## Naming Conventions

| Entity Type       | Convention              | Examples                          |
|-------------------|------------------------|-----------------------------------|
| Journey tags      | `@J{NNN}`              | @J001, @J002                      |
| Feature tags      | `@persona:{role}`      | @persona:job_submitter            |
| Priority tags     | `@P{N}`                | @P1, @P2, @P3                     |
| Runner tags       | `@smoke`, `@regression`, `@error-handling` | —               |
| Domain entities   | snake_case in steps    | job_id, worker_id, start_time     |
| API paths         | kebab-case segments    | /jobs, /workers, /workers/{id}/heartbeat |

---

## System Roles

| Role            | Description                                                    |
|-----------------|----------------------------------------------------------------|
| `job_submitter` | Application developer calling the Web API to schedule/query/cancel jobs |
| `platform_operator` | Engineer managing the Lightcron deployment and worker fleet |
| `sre_operator`  | On-call engineer responding to incidents and managing running jobs |
| `runner_agent`  | The process running on each worker node; communicates with the scheduler |
| `scheduler`     | The Lightcron central service; owns job state, dispatches jobs |

---

## Domain Entity Names (EXACT — do not use synonyms)

| Canonical Name  | Do NOT use               |
|-----------------|--------------------------|
| `Job`           | task, work item, event   |
| `Worker`        | node, executor, host     |
| `Schedule`      | cron, trigger, timer     |
| `RunnerAgent`   | agent, daemon, client    |
| `job_id`        | task_id, id, uuid        |
| `worker_id`     | node_id, host_id         |

---

## Job Status Values (EXACT — exhaustive)

| Status      | Meaning                                              |
|-------------|------------------------------------------------------|
| `pending`   | Scheduled, not yet dispatched to a worker            |
| `assigned`  | Dispatched to a worker, runner_agent not yet confirmed start |
| `running`   | Runner agent has confirmed the job is executing      |
| `completed` | Runner agent stopped the job at scheduled end time   |
| `cancelled` | Explicitly cancelled via API before or during execution |
| `failed`    | Execution error reported by runner agent             |
| `timed_out` | Worker heartbeat expired while job was assigned/running |

---

## Worker Status Values (EXACT — exhaustive)

| Status     | Meaning                                              |
|------------|------------------------------------------------------|
| `online`   | Registered, heartbeat current, accepting assignments |
| `busy`     | Running one or more jobs (still accepting if capacity allows) |
| `offline`  | Heartbeat expired; not available for assignment      |

---

## Numeric Constants (EXACT — do not approximate)

| Constant                  | Value | Spec Reference          |
|---------------------------|-------|-------------------------|
| Worker heartbeat interval | 30s   | J002, J008              |
| Worker heartbeat timeout  | 90s   | J008 (3 missed beats)   |
| Stuck job detection lag   | 90s   | J008                    |
| Max jobs per worker       | TBD   | To be defined in spec   |

---

## API Paths (EXACT — do not invent paths the spec doesn't define)

| Method | Path                          | Purpose                      |
|--------|-------------------------------|------------------------------|
| POST   | `/jobs`                       | Schedule a new job           |
| GET    | `/jobs/{job_id}`              | Query job status             |
| GET    | `/jobs`                       | List jobs (with filters)     |
| DELETE | `/jobs/{job_id}`              | Cancel a job                 |
| POST   | `/workers/register`           | Worker registers with scheduler |
| POST   | `/workers/{worker_id}/heartbeat` | Runner agent sends heartbeat |
| GET    | `/workers`                    | List workers and their status |

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

## Anti-Patterns

- Do NOT invent API paths not listed above
- Do NOT use synonyms for entity names — use exact names from this document
- Do NOT round numeric constants (heartbeat timeout is 90s, not "about a minute")
- Do NOT assume authentication details — mark auth steps as `# TODO: auth scheme TBD`
- If the spec is ambiguous, mark with `# SPEC-AMBIGUOUS: {what's unclear}`
