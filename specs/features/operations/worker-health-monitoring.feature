@J007 @P2 @persona:platform_operator @persona:sre_operator
Feature: View Worker Fleet Status
  As a platform_operator
  I want to query all registered workers and their current status
  So that I can see which nodes are healthy, busy, or offline at a glance

  Background:
    Given the Lightcron scheduler is running

  @smoke
  Scenario: List workers shows all registered workers with their status
    Given workers are registered:
      | worker_id | hostname  | status  |
      | w-001     | worker-01 | online  |
      | w-002     | worker-02 | busy    |
      | w-003     | worker-03 | offline |
    When GET /workers is called
    Then the response status is 200
    And the response contains 3 workers
    And each worker entry includes worker_id, hostname, status, last_seen, and running job count

  @smoke
  Scenario: Worker with expired heartbeat appears as offline
    Given a worker "w-001" with hostname "worker-01" last sent a heartbeat 90 seconds ago
    When GET /workers is called
    Then the response status is 200
    And worker "w-001" has status "offline"

  @smoke
  Scenario: No workers registered returns empty list
    Given no workers are registered
    When GET /workers is called
    Then the response status is 200
    And the response contains an empty list

  @smoke
  Scenario: Worker with running jobs shows correct job count
    Given a worker "w-001" with hostname "worker-01" is online
    And worker "w-001" has 2 running jobs
    When GET /workers is called
    Then worker "w-001" running job count is 2
