@J006 @P1 @persona:job_submitter
Feature: Query Job Status
  As a job_submitter
  I want to query the current status and execution details of a job via the API
  So that my application can react to job completion, failure, or progress

  Background:
    Given the Lightcron scheduler is running

  @smoke
  Scenario: Query a known job returns full details
    Given a job "j-001" exists with status "running", command "/usr/bin/my-script.sh", start_time, end_time, and worker_id "w-001"
    When GET /jobs/j-001 is called
    Then the response status is 200
    And the response contains job_id "j-001"
    And the response contains status "running"
    And the response contains command "/usr/bin/my-script.sh"
    And the response contains start_time, end_time, and worker_id "w-001"

  @error-handling
  Scenario: Query an unknown job returns 404
    When GET /jobs/does-not-exist is called
    Then the response status is 404

  @smoke
  Scenario: List jobs filtered by status
    Given jobs exist with statuses "pending", "running", and "completed"
    When GET /jobs?status=running is called
    Then the response status is 200
    And the response contains only jobs with status "running"

  @smoke
  Scenario: List all jobs returns all records
    Given 3 jobs exist with varying statuses
    When GET /jobs is called
    Then the response status is 200
    And the response contains 3 jobs

  @smoke
  Scenario: List jobs when none exist returns empty list
    Given no jobs exist
    When GET /jobs is called
    Then the response status is 200
    And the response contains an empty list

  @error-handling
  Scenario: Filter with an invalid status value returns 422
    When GET /jobs?status=not-a-real-status is called
    Then the response status is 422
