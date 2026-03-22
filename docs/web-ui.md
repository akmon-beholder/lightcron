# Lightcron Web UI Guide

The Lightcron web UI is a React single-page application that provides a real-time view of your worker fleet and job queue, a form for scheduling new jobs, and a detail page for inspecting individual jobs.

By default it runs at **http://localhost:5173** and talks to the scheduler API at **http://localhost:8000**.

---

## Navigation

The blue header bar is present on every page and provides two links:

- **Dashboard** — system overview (worker fleet + job list)
- **Schedule Job** — form to submit a new job

---

## Dashboard

The dashboard auto-refreshes every 10 seconds. It has two panels.

### Empty state

When no workers or jobs exist the dashboard shows placeholder messages in each panel.

![Dashboard empty state](screenshots/dashboard-empty.png)

### Worker Fleet panel

The Worker Fleet table lists every registered worker agent. Each row shows:

| Column | Description |
|--------|-------------|
| **Hostname** | The hostname the worker reported at registration |
| **Status** | `online` (green badge) or `offline` (grey badge) |
| **Last Seen** | Relative time since the worker last sent a heartbeat |
| **Running Jobs** | Count of jobs currently assigned to and running on this worker |

A worker transitions to `offline` automatically when its heartbeat has not been received within the configured threshold.

![Dashboard with worker fleet](screenshots/dashboard-workers.png)

### Jobs panel

The Jobs table lists jobs from the scheduler, newest first. Each row shows:

| Column | Description |
|--------|-------------|
| **Job ID** | Truncated UUID — click to open the job detail page |
| **Command** | The shell command to be executed (truncated to 80 characters) |
| **Status** | Colour-coded badge (see status reference below) |
| **Worker** | Truncated UUID of the worker assigned to the job, or `–` if unassigned |

Clicking a job ID navigates to the **Job Detail** page for that job.

![Dashboard with jobs](screenshots/dashboard-jobs.png)

#### Job status reference

| Status | Colour | Meaning |
|--------|--------|---------|
| `pending` | Blue | Waiting for its scheduled start time or dependencies |
| `ready` | Blue | Start time reached; waiting to be claimed by a worker |
| `assigned` | Yellow | Claimed by a worker; execution starting |
| `running` | Yellow | Actively executing on a worker |
| `completed` | Green | Finished with exit code 0 |
| `failed` | Red | Finished with a non-zero exit code, or exceeded resource limits |
| `cancelled` | Grey | Cancelled by a user request |
| `lost` | Grey | Worker stopped reporting while job was running |

#### Filtering by status

Use the **Status** dropdown on the right of the Jobs panel header to show only jobs in a specific state. Selecting a status immediately re-fetches the filtered list.

![Dashboard filtered to running jobs](screenshots/dashboard-filter-running.png)

---

## Schedule Job

Click **Schedule Job** in the navigation bar to open the job submission form.

![Schedule Job form](screenshots/schedule-job-form.png)

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| **Command** | Yes | The shell command the worker will execute, e.g. `python train.py --epochs 100` |
| **Start Time** | Yes | Earliest time the job may be dispatched. Must be in the future. |
| **Max Runtime (seconds)** | No | Hard upper limit on execution time. The worker sends SIGTERM then SIGKILL if the job exceeds this. |
| **Max Memory (MB)** | No | RSS memory limit. The worker kills the job if it exceeds this. |
| **Environment Variables** | No | Comma-separated `KEY=VALUE` pairs injected into the job's process environment, e.g. `APP_ENV=production, REGION=eu-west-1`. |
| **Depends On (comma-separated UUIDs)** | No | Job IDs that must reach `completed` before this job becomes eligible to run. |

### Filled form example

![Schedule Job form filled in](screenshots/schedule-job-filled.png)

### Validation

The form validates fields client-side before submitting:

- **Command** is required
- **Start Time** must be set and in the future
- **Max Runtime** and **Max Memory**, if provided, must be positive integers

Server-side errors (e.g. an unrecognised dependency UUID) are displayed inline below the relevant field.

![Schedule Job validation errors](screenshots/schedule-job-validation.png)

### Success

On successful submission a confirmation banner appears showing the new Job ID. A **View job detail →** link takes you directly to the job's detail page.

![Schedule Job success](screenshots/schedule-job-success.png)

---

## Job Detail

Click any job ID in the dashboard to open the job detail page at `/jobs/<job_id>`.

### Core fields

The header area shows the job's essential metadata:

| Field | Description |
|-------|-------------|
| **Job ID** | Full UUID |
| **Command** | The command as submitted |
| **Status** | Current status badge |
| **Worker** | Hostname of the assigned worker |
| **Scheduled** | The `start_time` that was requested |
| **Started** | When the worker began execution |
| **Finished** | When the process exited (terminal jobs only) |
| **Duration** | Actual wall-clock runtime; shown as a live counter while running |
| **Peak Memory** | Maximum RSS recorded during execution (terminal jobs) |
| **Exit Code** | Process exit code (terminal jobs) |

### Kill reason banner

When a job was killed by the worker (e.g. for exceeding `max_runtime` or `max_memory`), a prominent warning banner is shown below the header.

### Environment variables

The **Environment Variables** section renders the `env_vars` that were passed to the job as a key/value table. When the job was submitted with no environment variables, the section shows a "No environment variables" placeholder.

### stdout and stderr

The **stdout** and **stderr** sections fetch output directly from the worker node's REST API once the job reaches a terminal state. Output is displayed in scrollable code blocks.

Possible states for each output section:

| State | Display |
|-------|---------|
| Job still running | "Job in progress — output will appear here when complete" |
| Job complete, output available | Scrollable `<pre>` block with the file contents |
| Job complete, no output file | "No output" |
| Worker unreachable | "Worker offline — logs unavailable" |

The detail page auto-refreshes while the job is running. When the status transitions to a terminal state the output sections are populated automatically.

![Completed job detail](screenshots/job-detail-completed.png)

![Failed job detail (kill reason banner visible)](screenshots/job-detail-failed.png)

![Running job detail (live elapsed time, output placeholder)](screenshots/job-detail-running.png)

---

## Starting the UI locally

```bash
# Start the backend stack (DB, pgBouncer, scheduler, worker)
docker compose up -d db pgbouncer scheduler worker

# Start the Vite dev server
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173** in your browser.

For the full stack including the UI in Docker:

```bash
docker compose --profile ui up -d
```
