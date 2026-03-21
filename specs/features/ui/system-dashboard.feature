@J009 @P2 @persona:platform_operator @persona:sre_operator
Feature: View System State via Web UI Dashboard
  As a platform_operator or sre_operator
  I want to view the current state of the Lightcron system via a web dashboard
  So that I can quickly assess worker health and job activity without using the REST API directly

  Background:
    Given the Lightcron scheduler is running
    And the web UI is accessible

  # ── Worker fleet panel ───────────────────────────────────────────────────────

  @smoke
  Scenario: Dashboard shows online workers with their running job counts
    Given a worker_status row for "w-001" with hostname "worker-01" has status "online"
    And 2 jobs in the jobs table have status "running" with worker_id "w-001"
    And a worker_status row for "w-002" with hostname "worker-02" has status "online"
    And 0 jobs in the jobs table have status "running" with worker_id "w-002"
    When the operator navigates to the dashboard page
    Then the worker fleet panel shows "worker-01" as "online" with 2 running jobs
    And the worker fleet panel shows "worker-02" as "online" with 0 running jobs

  @smoke
  Scenario: Dashboard shows an offline worker
    Given a worker_status row for "w-003" with hostname "worker-03" has status "offline"
    When the operator navigates to the dashboard page
    Then the worker fleet panel shows "worker-03" as "offline"

  @error-handling
  Scenario: Dashboard shows empty state when no workers are registered
    Given no rows exist in the worker_status table
    When the operator navigates to the dashboard page
    Then the worker fleet panel displays an empty state message

  # ── Jobs panel ───────────────────────────────────────────────────────────────

  @smoke
  Scenario: Dashboard shows recent jobs with their statuses
    Given a job "j-001" in the jobs table has status "running" with worker_id "w-001"
    And a job "j-002" in the jobs table has status "completed"
    And a job "j-003" in the jobs table has status "failed"
    When the operator navigates to the dashboard page
    Then the jobs panel shows "j-001" with status "running"
    And the jobs panel shows "j-002" with status "completed"
    And the jobs panel shows "j-003" with status "failed"

  @smoke
  Scenario: Jobs panel can be filtered by status
    Given a job "j-001" in the jobs table has status "running"
    And a job "j-002" in the jobs table has status "completed"
    When the operator navigates to the dashboard page
    And the operator selects the "running" status filter on the jobs panel
    Then the jobs panel shows "j-001" with status "running"
    And "j-002" does not appear in the jobs panel

  @error-handling
  Scenario: Dashboard shows empty state when no jobs exist
    Given no jobs exist in the jobs table
    When the operator navigates to the dashboard page
    Then the jobs panel displays an empty state message

  # ── Navigation to job detail ─────────────────────────────────────────────────

  @smoke
  Scenario: Clicking a job row navigates to the job detail page
    Given a job "j-nav" in the jobs table has status "completed"
    When the operator navigates to the dashboard page
    And the operator clicks on the job row for "j-nav"
    Then the browser navigates to the job detail page for "j-nav"

  # ── Auto-refresh ─────────────────────────────────────────────────────────────

  @smoke
  Scenario: Dashboard auto-refreshes and reflects updated state
    Given the operator is viewing the dashboard page
    And a job "j-004" in the jobs table has status "pending"
    When the auto-refresh interval elapses
    And the scheduler has since marked "j-004" as "ready"
    Then the jobs panel shows "j-004" with status "ready" without a full page reload
