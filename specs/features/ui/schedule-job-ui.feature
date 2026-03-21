@J010 @P2 @persona:platform_operator @persona:job_submitter
Feature: Schedule a Job via Web UI Form
  As a platform_operator or job_submitter
  I want to schedule a new job by filling in a form in the web UI
  So that I can submit jobs without constructing raw HTTP requests

  Background:
    Given the Lightcron scheduler is running
    And the web UI is accessible
    And the user navigates to the "Schedule Job" page

  # ── Happy path ───────────────────────────────────────────────────────────────

  @smoke
  Scenario: User submits a valid job with required fields only
    Given the user enters command "/usr/bin/my-script.sh"
    And the user enters a start_time 5 minutes from now
    When the user submits the form
    Then the form submission succeeds
    And a job_id is displayed to the user
    And a link to the job detail view is shown

  @smoke
  Scenario: User submits a job with all optional fields populated
    Given the user enters command "/usr/bin/my-script.sh"
    And the user enters a start_time 5 minutes from now
    And the user enters max_runtime of 300
    And the user enters max_memory of 512
    When the user submits the form
    Then the form submission succeeds
    And a job_id is displayed to the user

  # ── Client-side validation ───────────────────────────────────────────────────

  @error-handling
  Scenario: Form shows validation error when command is missing
    Given the user leaves the command field empty
    And the user enters a start_time 5 minutes from now
    When the user submits the form
    Then the form shows a validation error on the command field
    And no request is sent to the API

  @error-handling
  Scenario: Form shows validation error when start_time is in the past
    Given the user enters command "/usr/bin/my-script.sh"
    And the user enters a start_time 10 minutes in the past
    When the user submits the form
    Then the form shows a validation error on the start_time field
    And no request is sent to the API

  @error-handling
  Scenario: Form shows validation error for non-positive max_runtime
    Given the user enters command "/usr/bin/my-script.sh"
    And the user enters a start_time 5 minutes from now
    And the user enters max_runtime of -1
    When the user submits the form
    Then the form shows a validation error on the max_runtime field
    And no request is sent to the API

  @error-handling
  Scenario: Form shows validation error for non-positive max_memory
    Given the user enters command "/usr/bin/my-script.sh"
    And the user enters a start_time 5 minutes from now
    And the user enters max_memory of 0
    When the user submits the form
    Then the form shows a validation error on the max_memory field
    And no request is sent to the API

  # ── Server-side validation passthrough ───────────────────────────────────────

  @error-handling
  Scenario: Form displays server error when depends_on contains an unknown job_id
    Given the user enters command "/usr/bin/my-script.sh"
    And the user enters a start_time 5 minutes from now
    And the user enters depends_on containing "00000000-0000-0000-0000-000000000000"
    When the user submits the form
    And the API returns HTTP 422 identifying the unknown dependency
    Then the form displays the server error message inline
    And the form remains on screen for the user to correct
