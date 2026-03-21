@J002 @P1 @persona:platform_operator
Feature: Worker Node Registration via Database
  As a worker_agent on a worker node
  I want to register my presence by writing to the worker_status table
  So that the scheduler knows this node is available to accept job assignments

  Background:
    Given the Lightcron scheduler is running
    And the worker_status table is empty

  @smoke
  Scenario: Worker agent registers on startup by upserting to worker_status
    When the worker_agent on hostname "worker-01" starts up
    And it upserts a row to worker_status with hostname "worker-01" and status "online"
    Then a row exists in worker_status for hostname "worker-01" with status "online"
    And the row has a unique worker_id
    And last_seen is set to approximately now

  @smoke
  Scenario: Worker agent maintains registration by updating last_seen every 30 seconds
    Given a worker_status row exists for worker_id "w-abc" with status "online"
    When 30 seconds elapse and the worker_agent updates worker_status.last_seen for "w-abc"
    Then last_seen for worker_id "w-abc" is updated to approximately now

  @error-handling
  Scenario: Scheduler marks worker offline after last_seen has not been updated for 90 seconds
    Given a worker_status row exists for worker_id "w-def" with status "online"
    And the last_seen timestamp for "w-def" is 90 seconds in the past
    When the scheduler runs its health check
    Then worker_status for "w-def" has status "offline"

  @smoke
  Scenario: Re-registering the same hostname on restart is idempotent
    Given a worker_status row exists for hostname "worker-01" with worker_id "w-abc" and status "offline"
    When the worker_agent on hostname "worker-01" starts up and upserts to worker_status
    Then the row for hostname "worker-01" has status "online"
    And the worker_id remains "w-abc"
    And last_seen is updated to approximately now

  @smoke
  Scenario: Scheduler can confirm worker is alive via worker REST health endpoint
    Given a worker_status row for "w-abc" has a stale last_seen
    And the worker_agent on "w-abc" is still running
    When the scheduler calls GET /health on the worker_agent at "w-abc"
    Then the response status is 200
