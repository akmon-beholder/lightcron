@J004 @P1 @persona:job_submitter
Feature: Job Runs to Completion
  As the worker_agent
  I want to let a job process run until it exits naturally and record its exit code
  So that jobs complete on their own terms without needing a pre-defined end time

  Background:
    Given the Lightcron scheduler is running
    And a worker_status row for "w-001" exists with status "online"
    And a job "j-001" has status "running" with worker_id "w-001"

  @smoke
  Scenario: Job process exits with code 0 and is marked completed
    When the job process for "j-001" exits with code 0
    And the worker_agent on "w-001" updates the jobs table
    Then job "j-001" status in the jobs table is "completed"
    And job "j-001" exit_code in the jobs table is 0
    And job "j-001" finished_at is set

  @error-handling
  Scenario: Job process exits with non-zero exit code and is marked failed
    When the job process for "j-001" exits with code 1
    And the worker_agent on "w-001" updates the jobs table
    Then job "j-001" status in the jobs table is "failed"
    And job "j-001" exit_code in the jobs table is 1
    And job "j-001" finished_at is set

  @smoke
  Scenario: Job with no max_runtime runs until natural exit with no timeout applied
    Given job "j-001" has no max_runtime set
    When the job process runs for an extended period and then exits with code 0
    Then the worker_agent does not send SIGTERM during the run
    And job "j-001" status is "completed"

  @smoke
  Scenario: Job exceeding max_runtime receives SIGTERM then SIGKILL
    Given job "j-001" has max_runtime set to 60 seconds
    And the job process has been running for 60 seconds without exiting
    When the worker_agent detects max_runtime is exceeded
    Then the worker_agent sends SIGTERM to the job process
    And if the process does not exit within the grace period the worker_agent sends SIGKILL
    And job "j-001" status in the jobs table is "failed"
    And job "j-001" kill_reason is "max_runtime_exceeded"

  @smoke
  Scenario: Completed job details are queryable by the submitter
    Given job "j-001" has status "completed" with exit_code 0, started_at, finished_at, and worker_id "w-001"
    When GET /jobs/j-001 is called
    Then the response status is 200
    And the response contains status "completed"
    And the response contains exit_code 0
    And the response contains started_at, finished_at, and worker_id "w-001"

  @smoke
  Scenario: Failed job details including exit code are queryable
    Given job "j-001" has status "failed" with exit_code 2, started_at, finished_at, and worker_id "w-001"
    When GET /jobs/j-001 is called
    Then the response status is 200
    And the response contains status "failed"
    And the response contains exit_code 2

  # ── Output file storage ───────────────────────────────────────────────────────

  @smoke
  Scenario: Worker writes stdout and stderr to files in the jobs directory
    Given the worker is configured with LIGHTCRON_JOBS_DIR "/tmp/lightcron-test-jobs"
    And a job "j-002" is running with worker_id "w-001"
    When the job process for "j-002" writes "hello stdout" to stdout
    And the job process for "j-002" writes "hello stderr" to stderr
    And the job process for "j-002" exits with code 0
    Then the file "/tmp/lightcron-test-jobs/j-002.stdout" contains "hello stdout"
    And the file "/tmp/lightcron-test-jobs/j-002.stderr" contains "hello stderr"
    And job "j-002" status in the jobs table is "completed"

  Scenario: Worker defaults to /var/logs/lightcron/jobs when LIGHTCRON_JOBS_DIR is not set
    Given the worker is started without LIGHTCRON_JOBS_DIR configured
    Then the worker uses "/var/logs/lightcron/jobs" as the jobs output directory

  Scenario: Output files contain partial content when a job is killed
    Given the worker is configured with LIGHTCRON_JOBS_DIR "/tmp/lightcron-test-jobs"
    And a job "j-003" has max_runtime set to 1 second
    And the job process for "j-003" writes "partial output" to stdout before being killed
    When the worker_agent detects max_runtime is exceeded and kills the process
    Then the file "/tmp/lightcron-test-jobs/j-003.stdout" contains "partial output"
    And job "j-003" kill_reason is "max_runtime_exceeded"

  @smoke
  Scenario: Worker REST API serves stdout file content
    Given the worker is configured with LIGHTCRON_JOBS_DIR "/tmp/lightcron-test-jobs"
    And the file "/tmp/lightcron-test-jobs/j-004.stdout" contains "output line 1"
    When GET /jobs/j-004/stdout is called on the worker REST API
    Then the response status is 200
    And the response content-type is "text/plain"
    And the response body is "output line 1"

  @smoke
  Scenario: Worker REST API serves stderr file content
    Given the worker is configured with LIGHTCRON_JOBS_DIR "/tmp/lightcron-test-jobs"
    And the file "/tmp/lightcron-test-jobs/j-004.stderr" contains "error line 1"
    When GET /jobs/j-004/stderr is called on the worker REST API
    Then the response status is 200
    And the response body is "error line 1"

  @error-handling
  Scenario: Worker REST API returns 404 when output file does not exist
    Given no output file exists for job "j-005"
    When GET /jobs/j-005/stdout is called on the worker REST API
    Then the response status is 404
