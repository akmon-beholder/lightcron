@J003 @P1 @persona:platform_operator
Feature: Job Ready Transition and Pull-Based Worker Claiming
  As the scheduler and worker_agent
  I want the scheduler to mark jobs ready when their conditions are met
  And worker_agents to atomically claim ready jobs from the database
  So that no central dispatcher is needed and workers self-organise

  Background:
    Given the Lightcron scheduler is running

  # ── Scheduler: pending → ready transition ────────────────────────────────────

  @smoke
  Scenario: Scheduler marks a job ready when start_time is reached and there are no dependencies
    Given a job "j-001" exists in the jobs table with status "pending", start_time of now, and no depends_on
    When the scheduler runs its ready-transition loop
    Then job "j-001" status in the jobs table is "ready"

  @smoke
  Scenario: Scheduler marks a job ready when start_time is reached and all dependencies are completed
    Given a job "j-dep" exists with status "completed"
    And a job "j-001" exists with status "pending", start_time of now, and depends_on ["j-dep"]
    When the scheduler runs its ready-transition loop
    Then job "j-001" status in the jobs table is "ready"

  @error-handling
  Scenario: Job stays pending when start_time is reached but a dependency is not yet completed
    Given a job "j-dep" exists with status "running"
    And a job "j-001" exists with status "pending", start_time of now, and depends_on ["j-dep"]
    When the scheduler runs its ready-transition loop
    Then job "j-001" status remains "pending"

  @error-handling
  Scenario: Job stays pending when start_time has not yet been reached
    Given a job "j-001" exists with status "pending", start_time 60 seconds from now, and no depends_on
    When the scheduler runs its ready-transition loop
    Then job "j-001" status remains "pending"

  # ── Worker Agent: atomic claim ────────────────────────────────────────────────

  @smoke
  Scenario: Worker agent polls the jobs table and claims a ready job
    Given a job "j-001" exists in the jobs table with status "ready" and command "/usr/bin/my-script.sh"
    And a worker_agent "w-001" is online
    When the worker_agent on "w-001" polls for ready jobs and attempts to claim "j-001"
    Then job "j-001" status in the jobs table is "assigned"
    And job "j-001" worker_id in the jobs table is "w-001"
    And the worker_agent has the job command and any resource limits (max_runtime, max_memory)

  @smoke
  Scenario: Worker agent updates status to running after starting the job process
    Given a job "j-001" has status "assigned" with worker_id "w-001"
    When the worker_agent on "w-001" starts the job process
    And updates the jobs table
    Then job "j-001" status in the jobs table is "running"

  @error-handling
  Scenario: Exactly one worker wins when two agents claim the same job simultaneously
    Given a job "j-001" exists with status "ready"
    And worker_agents "w-001" and "w-002" both attempt to claim "j-001" at the same time
    When both atomic claim updates are executed
    Then job "j-001" status is "assigned"
    And exactly one of "w-001" or "w-002" is recorded as worker_id
    And the other worker_agent observes 0 rows affected and does not hold the job

  @error-handling
  Scenario: Worker agent finds nothing to claim when no ready jobs exist
    Given no jobs in the jobs table have status "ready"
    When the worker_agent on "w-001" polls for ready jobs
    Then the worker_agent finds no jobs to claim and waits for the next poll interval

  # ── Interaction: ready job waits for a worker ─────────────────────────────────

  @error-handling
  Scenario: Ready job remains ready when no workers are online
    Given no rows in worker_status have status "online"
    And a job "j-002" exists with status "ready"
    When time passes and no worker_agent polls
    Then job "j-002" status remains "ready"

  # ── Stuck job after claim ──────────────────────────────────────────────────────

  @error-handling
  Scenario: Assigned job transitions to timed_out if worker heartbeat expires before confirming start
    Given a job "j-003" has status "assigned" with worker_id "w-003"
    And worker_status for "w-003" has last_seen 90 seconds ago
    When the scheduler runs its health check
    Then job "j-003" status in the jobs table is "timed_out"
    And worker_status for "w-003" has status "offline"
