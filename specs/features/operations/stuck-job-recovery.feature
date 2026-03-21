@J008 @P1 @persona:sre_operator @persona:platform_operator
Feature: Detect and Recover Stuck Jobs via Two-Stage Liveness Check
  As the scheduler
  I want to use a two-stage liveness check (DB last_seen + worker /health probe)
  So that transient DB write failures do not falsely mark healthy workers as offline,
  but true worker crashes are still detected and stuck jobs are recovered promptly

  # Two-stage logic:
  #   last_seen >= 60s  → Stage 1: call GET /health on worker
  #     /health 200     → worker alive; no status change
  #     /health fails   → Stage 2: mark worker offline, mark jobs timed_out
  #   last_seen >= 90s  → skip /health; go directly to Stage 2

  Background:
    Given the Lightcron scheduler is running

  # ── Stage 1: /health probe ──────────────────────────────────────────────────

  @smoke
  Scenario: Worker with stale last_seen but healthy /health endpoint stays online
    Given a worker_status row for "w-001" has last_seen 60 seconds ago
    And a job "j-001" in the jobs table has status "running" with worker_id "w-001"
    When the scheduler runs its health check
    And the scheduler calls GET /health on the worker_agent at "w-001"
    And the worker_agent returns HTTP 200
    Then worker_status for "w-001" status remains "online"
    And job "j-001" status remains "running"

  @error-handling
  Scenario: Worker with stale last_seen and failing /health is marked offline
    Given a worker_status row for "w-001" has last_seen 60 seconds ago
    And a job "j-002" in the jobs table has status "running" with worker_id "w-001"
    When the scheduler runs its health check
    And the scheduler calls GET /health on the worker_agent at "w-001"
    And the worker_agent does not respond (connection refused or timeout)
    Then worker_status for "w-001" has status "offline"
    And job "j-002" status in the jobs table is "timed_out"

  # ── Stage 2: threshold exceeded, skip /health ────────────────────────────────

  @smoke
  Scenario: Running job is marked timed_out when last_seen exceeds 90s (no /health probe)
    Given a worker_status row for "w-002" has last_seen 90 seconds ago
    And a job "j-003" in the jobs table has status "running" with worker_id "w-002"
    When the scheduler runs its health check
    Then the scheduler does NOT call GET /health on "w-002"
    And worker_status for "w-002" has status "offline"
    And job "j-003" status in the jobs table is "timed_out"

  @smoke
  Scenario: Assigned job is marked timed_out when last_seen exceeds 90s
    Given a worker_status row for "w-002" has last_seen 90 seconds ago
    And a job "j-004" in the jobs table has status "assigned" with worker_id "w-002"
    When the scheduler runs its health check
    Then job "j-004" status in the jobs table is "timed_out"

  # ── Healthy worker: no action ────────────────────────────────────────────────

  @smoke
  Scenario: Worker with fresh last_seen is left completely alone
    Given a worker_status row for "w-003" has last_seen 20 seconds ago
    And a job "j-005" in the jobs table has status "running" with worker_id "w-003"
    When the scheduler runs its health check
    Then the scheduler does NOT call GET /health on "w-003"
    And worker_status for "w-003" status remains "online"
    And job "j-005" status remains "running"

  # ── Observability ────────────────────────────────────────────────────────────

  @smoke
  Scenario: Timed-out jobs are visible via the REST API status filter
    Given a job "j-006" has status "timed_out" with worker_id "w-001" in the jobs table
    When GET /jobs?status=timed_out is called
    Then the response status is 200
    And job "j-006" appears in the response with worker_id "w-001"

  # ── Re-registration ──────────────────────────────────────────────────────────

  @smoke
  Scenario: Worker that re-registers after going offline gets a fresh online status
    Given a worker_status row for hostname "worker-01" has status "offline"
    When the worker_agent on "worker-01" restarts and upserts to worker_status
    Then the worker_status row for "worker-01" has status "online"
    And last_seen is updated to approximately now

  # ── Mass failure ─────────────────────────────────────────────────────────────

  @error-handling
  Scenario: Multiple workers failing simultaneously marks all their jobs as timed_out
    Given worker_status rows for "w-004" and "w-005" both have last_seen 90 seconds ago
    And job "j-007" has status "running" with worker_id "w-004"
    And job "j-008" has status "running" with worker_id "w-005"
    When the scheduler runs its health check
    Then job "j-007" status is "timed_out"
    And job "j-008" status is "timed_out"
    And worker_status for "w-004" has status "offline"
    And worker_status for "w-005" has status "offline"
