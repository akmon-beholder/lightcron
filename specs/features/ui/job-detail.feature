@J011 @P2 @persona:platform_operator @persona:sre_operator @persona:job_submitter
Feature: Inspect Job Detail via Web UI
  As a platform_operator or sre_operator
  I want to click on a job in the dashboard and see its full detail
  So that I can diagnose failures and verify job behaviour without database access

  Background:
    Given the Lightcron scheduler is running
    And the web UI is accessible

  # ── Core fields ───────────────────────────────────────────────────────────────

  @smoke
  Scenario: Job detail page shows core fields for a completed job
    Given a completed job "j-001" exists with command "/usr/bin/report.sh"
    And "j-001" has started_at "2026-03-21T10:00:00Z" and finished_at "2026-03-21T10:02:34Z"
    When the operator navigates to the job detail page for "j-001"
    Then the page displays the job_id "j-001"
    And the page displays the command "/usr/bin/report.sh"
    And the page displays the status "completed"
    And the page displays the actual runtime as "2m 34s"

  # ── Runtime and memory ───────────────────────────────────────────────────────

  @smoke
  Scenario: Job detail page shows peak memory for a completed job
    Given a completed job "j-002" exists with worker_id "w-001"
    And "j-002" has peak_memory_mb of 128.5
    When the operator navigates to the job detail page for "j-002"
    Then the page displays the peak memory as "128.5 MB"

  @smoke
  Scenario: Job detail page shows live elapsed time for a running job
    Given a running job "j-003" exists with started_at 90 seconds ago
    When the operator navigates to the job detail page for "j-003"
    Then the page displays a live elapsed time counting up from started_at

  Scenario: Peak memory shows placeholder for a job that has not started
    Given a pending job "j-004" exists
    When the operator navigates to the job detail page for "j-004"
    Then the peak memory field shows a "not yet available" placeholder

  # ── Output fetched from worker REST API ───────────────────────────────────────

  @smoke
  Scenario: Job detail page fetches and shows stdout from the worker REST API
    Given a completed job "j-005" exists with worker_id "w-001"
    And the worker "w-001" has base_url "http://worker-01:8001"
    And GET /jobs/j-005/stdout on worker "w-001" returns "Hello, world!"
    When the operator navigates to the job detail page for "j-005"
    Then the UI fetches stdout from "http://worker-01:8001/jobs/j-005/stdout"
    And the stdout block displays "Hello, world!" in a scrollable code block

  @smoke
  Scenario: Job detail page fetches and shows stderr from the worker REST API
    Given a completed job "j-006" exists with worker_id "w-001"
    And the worker "w-001" has base_url "http://worker-01:8001"
    And GET /jobs/j-006/stderr on worker "w-001" returns "Warning: config file not found"
    When the operator navigates to the job detail page for "j-006"
    Then the UI fetches stderr from "http://worker-01:8001/jobs/j-006/stderr"
    And the stderr block displays "Warning: config file not found" in a scrollable code block
    And the stderr block is visually distinguished from the stdout block

  Scenario: Job detail page shows empty state when worker returns 404 for stdout
    Given a completed job "j-007" exists with worker_id "w-001"
    And GET /jobs/j-007/stdout on worker "w-001" returns 404
    When the operator navigates to the job detail page for "j-007"
    Then the stdout block shows a "No output" empty state message

  Scenario: Job detail page shows empty state when worker returns 404 for stderr
    Given a completed job "j-008" exists with worker_id "w-001"
    And GET /jobs/j-008/stderr on worker "w-001" returns 404
    When the operator navigates to the job detail page for "j-008"
    Then the stderr block shows a "No output" empty state message

  Scenario: Output sections show "job in progress" placeholder while job is running
    Given a running job "j-009" exists with worker_id "w-001"
    When the operator navigates to the job detail page for "j-009"
    Then the stdout block shows a "job in progress" placeholder
    And the stderr block shows a "job in progress" placeholder
    And the peak memory field shows a "job in progress" placeholder
    And the UI does not make any request to the worker REST API for output

  # ── Worker offline ────────────────────────────────────────────────────────────

  @error-handling
  Scenario: Output sections show "worker offline" message when worker is unreachable
    Given a completed job "j-010" exists with worker_id "w-001"
    And the worker "w-001" REST API is unreachable
    When the operator navigates to the job detail page for "j-010"
    Then the stdout block shows a "Worker offline — logs unavailable" message
    And the stderr block shows a "Worker offline — logs unavailable" message

  # ── Kill reason ───────────────────────────────────────────────────────────────

  @smoke
  Scenario: Kill reason is shown prominently for a job killed for exceeding max_runtime
    Given a failed job "j-011" exists with kill_reason "max_runtime_exceeded" and worker_id "w-001"
    And GET /jobs/j-011/stderr on worker "w-001" returns "partial stderr before kill"
    When the operator navigates to the job detail page for "j-011"
    Then the page displays a warning banner containing "max_runtime_exceeded"
    And the stderr block displays "partial stderr before kill"

  Scenario: Kill reason is shown prominently for a job killed for exceeding max_memory
    Given a failed job "j-012" exists with kill_reason "max_memory_exceeded" and worker_id "w-001"
    When the operator navigates to the job detail page for "j-012"
    Then the page displays a warning banner containing "max_memory_exceeded"

  # ── Environment variables ────────────────────────────────────────────────────

  @smoke
  Scenario: Job detail page shows env_vars as a key/value table
    Given a completed job "j-013" exists with env_vars:
      | key       | value   |
      | APP_ENV   | staging |
      | LOG_LEVEL | debug   |
    When the operator navigates to the job detail page for "j-013"
    Then the env_vars section displays a table with key "APP_ENV" and value "staging"
    And the env_vars section displays a table with key "LOG_LEVEL" and value "debug"

  Scenario: Job detail page shows empty state when env_vars is empty
    Given a completed job "j-014" exists with no env_vars
    When the operator navigates to the job detail page for "j-014"
    Then the env_vars section shows a "No environment variables" empty state message

  # ── Error states ──────────────────────────────────────────────────────────────

  @error-handling
  Scenario: Job detail page shows error state when job is not found
    When the operator navigates to the job detail page for "j-does-not-exist"
    Then the page displays a "Job not found" error message
    And the page displays a link back to the dashboard

  # ── Auto-refresh ──────────────────────────────────────────────────────────────

  @smoke
  Scenario: Detail page auto-refreshes and fetches output once job completes
    Given a running job "j-015" exists with worker_id "w-001"
    And the operator is viewing the job detail page for "j-015"
    When the auto-refresh interval elapses
    And the job "j-015" has since completed
    And GET /jobs/j-015/stdout on worker "w-001" returns "final output"
    Then the detail page updates the status to "completed" without a full page reload
    And the stdout block is populated with "final output"
