@J001 @P1 @persona:job_submitter
Feature: Schedule a Job
  As a job_submitter
  I want to schedule a job with a start time via the Web API
  So that Lightcron will run the job on a worker node once it is ready

  Background:
    Given the Lightcron scheduler is running
    And no jobs exist

  @smoke
  Scenario: Successfully schedule a minimal job
    When a job_submitter submits a POST /jobs request with:
      | field      | value                        |
      | command    | /usr/bin/my-script.sh        |
      | start_time | 60 seconds from now          |
    Then the response status is 201
    And the response contains a unique job_id
    And the job status is "pending"
    And the job has no max_runtime or max_memory set

  @smoke
  Scenario: Successfully schedule a job with resource limits
    When a job_submitter submits a POST /jobs request with:
      | field       | value                        |
      | command     | /usr/bin/my-script.sh        |
      | start_time  | 60 seconds from now          |
      | max_runtime | 3600                         |
      | max_memory  | 512                          |
    Then the response status is 201
    And the response contains a unique job_id
    And the job max_runtime is 3600
    And the job max_memory is 512

  @smoke
  Scenario: Successfully schedule a job with dependencies
    Given a job "j-existing" already exists
    When a job_submitter submits a POST /jobs request with:
      | field      | value                        |
      | command    | /usr/bin/my-script.sh        |
      | start_time | 60 seconds from now          |
      | depends_on | ["j-existing"]               |
    Then the response status is 201
    And the response contains a unique job_id
    And the job depends_on includes "j-existing"

  @error-handling
  Scenario: Reject a job with a start_time in the past
    When a job_submitter submits a POST /jobs request with:
      | field      | value                        |
      | command    | /usr/bin/my-script.sh        |
      | start_time | 60 seconds ago               |
    Then the response status is 422
    And the response contains a validation error for "start_time"

  @error-handling
  Scenario Outline: Reject a job with a missing required field
    When a job_submitter submits a POST /jobs request missing the "<field>" field
    Then the response status is 422
    And the response identifies "<field>" as missing

    Examples:
      | field      |
      | command    |
      | start_time |

  @error-handling
  Scenario: Reject a job with a depends_on referencing an unknown job_id
    When a job_submitter submits a POST /jobs request with depends_on containing "j-does-not-exist"
    Then the response status is 422
    And the response identifies "j-does-not-exist" as an unknown dependency

  @error-handling
  Scenario: Reject a job with max_runtime set to zero or negative
    When a job_submitter submits a POST /jobs request with max_runtime -1
    Then the response status is 422
    And the response contains a validation error for "max_runtime"

  @error-handling
  Scenario: Reject a malformed JSON request body
    When a job_submitter sends a POST /jobs request with malformed JSON
    Then the response status is 400

  # ── env_vars ─────────────────────────────────────────────────────────────────

  @smoke
  Scenario: Successfully schedule a job with env_vars
    When a job_submitter submits a POST /jobs request with:
      | field      | value                        |
      | command    | /usr/bin/my-script.sh        |
      | start_time | 60 seconds from now          |
      | env_vars   | {"APP_ENV": "staging", "LOG_LEVEL": "debug"} |
    Then the response status is 201
    And the response contains a unique job_id
    And the job env_vars contains key "APP_ENV" with value "staging"
    And the job env_vars contains key "LOG_LEVEL" with value "debug"

  @smoke
  Scenario: Job submitted without env_vars has an empty env_vars map
    When a job_submitter submits a POST /jobs request with:
      | field      | value                        |
      | command    | /usr/bin/my-script.sh        |
      | start_time | 60 seconds from now          |
    Then the response status is 201
    And the job env_vars is empty

  @error-handling
  Scenario: Reject a job with env_vars containing non-string values
    When a job_submitter submits a POST /jobs request with env_vars containing a non-string value
    Then the response status is 422
    And the response contains a validation error for "env_vars"
