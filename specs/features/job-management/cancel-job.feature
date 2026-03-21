@J005 @P1 @persona:sre_operator @persona:job_submitter
Feature: Cancel a Job
  As an sre_operator or job_submitter
  I want to cancel a job via the API regardless of whether it is pending, assigned, or running
  So that I can stop unwanted or stuck work without direct database or node access

  Background:
    Given the Lightcron scheduler is running

  @smoke
  Scenario: Cancel a pending job
    Given a job "j-001" exists with status "pending"
    When POST /jobs/j-001/cancel is called
    Then the response status is 200
    And job "j-001" status is "cancelled"

  @smoke
  Scenario: Cancel a running job — scheduler writes cancelled; worker_agent detects and stops
    Given a worker "w-001" is registered in worker_status with status "online"
    And a job "j-002" has status "running" with worker_id "w-001" in the jobs table
    When POST /jobs/j-002/cancel is called
    Then the response status is 200
    And job "j-002" status is "cancelled" in the jobs table
    And the worker_agent on "w-001" detects the "cancelled" status on its next poll
    And the worker_agent stops the job process for "j-002"

  @smoke
  Scenario: Cancel an assigned job
    Given a worker "w-001" is registered in worker_status with status "online"
    And a job "j-003" has status "assigned" with worker_id "w-001"
    When POST /jobs/j-003/cancel is called
    Then the response status is 200
    And job "j-003" status is "cancelled"

  @error-handling
  Scenario: Cannot cancel a completed job
    Given a job "j-004" has status "completed"
    When POST /jobs/j-004/cancel is called
    Then the response status is 409

  @error-handling
  Scenario: Cannot cancel a failed job
    Given a job "j-005" has status "failed"
    When POST /jobs/j-005/cancel is called
    Then the response status is 409

  @error-handling
  Scenario: Cannot cancel a timed_out job
    Given a job "j-007" has status "timed_out"
    When POST /jobs/j-007/cancel is called
    Then the response status is 409

  @error-handling
  Scenario: Cancel returns 404 for unknown job
    When POST /jobs/does-not-exist/cancel is called
    Then the response status is 404

  @error-handling
  Scenario: Job is marked cancelled even when the assigned worker is currently offline
    Given a worker "w-002" has status "offline" in worker_status
    And a job "j-006" has status "running" with worker_id "w-002" in the jobs table
    When POST /jobs/j-006/cancel is called
    Then the response status is 200
    And job "j-006" status is "cancelled" in the jobs table
