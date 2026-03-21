# Lightcron

A lightweight job orchestration system. Users schedule jobs via a REST API or a web dashboard; worker agents running on separate nodes pull jobs from a shared PostgreSQL database and execute them. There is no message broker — the database is the sole communication bus between all components.

## Features

- **Job scheduling** — submit a command with a start time, optional resource limits (`max_runtime`, `max_memory`), and optional dependencies on other jobs
- **Pull-based execution** — worker agents atomically claim ready jobs; no central dispatcher
- **Job lifecycle** — `pending → ready → assigned → running → completed / failed / cancelled / lost`
- **Worker liveness** — two-stage health check: DB `last_seen` heartbeat + HTTP `/health` probe; dead workers' jobs are automatically marked `lost`
- **Resource enforcement** — SIGTERM → grace period → SIGKILL for runtime and memory limit breaches
- **Job cancellation** — cancel any non-terminal job via the API; workers detect cancellation on their next poll
- **Web dashboard** — React UI showing live worker fleet status and job activity with auto-refresh
- **Schedule via UI** — submit jobs through a form without constructing raw HTTP requests

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  job_submitter / operator                           │
│  REST API  ←→  Scheduler (FastAPI, port 8000)       │
│  Web UI    ←→  React SPA (Vite, port 5173)          │
└──────────────────────┬──────────────────────────────┘
                       │ PostgreSQL (via pgBouncer, session mode)
          ┌────────────┴────────────┐
          │  Worker Agent (n nodes) │
          │  polls + claims jobs    │
          │  health endpoint :8001  │
          └─────────────────────────┘
```

The scheduler runs two background loops:
- **Ready-transition loop** (every 10 s) — marks `pending` jobs `ready` when `start_time` is reached and all dependencies are `completed`
- **Health-check loop** (every 30 s) — detects stale workers and marks their jobs `lost`

## Prerequisites

| Tool | Version |
|------|---------|
| Docker + Docker Compose | v2+ |
| Python | 3.12+ |
| [uv](https://docs.astral.sh/uv/) | latest |
| Node.js | 20+ (frontend only) |

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start the full stack (DB + pgBouncer + scheduler + worker)
docker compose up -d

# 3. Apply database migrations
uv run alembic upgrade head

# 4. Check the scheduler is up
curl http://localhost:8000/health
```

The scheduler API is at `http://localhost:8000`.

To also start the web UI:

```bash
docker compose --profile ui up -d
# then open http://localhost:5173
```

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/jobs` | Schedule a new job |
| `GET` | `/jobs` | List jobs (optional `?status=` filter) |
| `GET` | `/jobs/{job_id}` | Get a single job |
| `POST` | `/jobs/{job_id}/cancel` | Cancel a job |
| `GET` | `/workers` | List registered workers |
| `GET` | `/health` | Scheduler liveness probe |

### Schedule a job

```bash
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "command": "/usr/bin/my-script.sh",
    "start_time": "2026-03-22T10:00:00Z",
    "max_runtime": 300,
    "max_memory": 512
  }'
```

## Running Tests

### Prerequisites

The backend test suite is an integration suite that requires a live PostgreSQL instance.

```bash
# Start just the database
docker compose up db -d

# Apply migrations
uv run alembic upgrade head
```

### Backend BDD tests

```bash
# Install all dev dependencies
uv sync --all-extras

# Run all BDD tests
uv run python -m pytest tests/bdd/ -v

# Run with coverage report
uv run python -m pytest tests/bdd/ --cov=src/lightcron --cov-report=term-missing

# Run a specific feature
uv run python -m pytest tests/bdd/steps/job_management/ -v

# Run only smoke tests
uv run python -m pytest tests/bdd/ -m smoke -v
```

### Integration tests (pgBouncer `SELECT FOR UPDATE SKIP LOCKED`)

```bash
# Requires both db and pgbouncer services
docker compose up db pgbouncer -d

DATABASE_URL=postgresql+asyncpg://lightcron:lightcron@localhost:5432/lightcron \
PGBOUNCER_URL=postgresql+asyncpg://lightcron:lightcron@localhost:6432/lightcron \
uv run python -m pytest tests/integration/ -v
```

### Frontend Playwright e2e tests

The Playwright tests require:
- The scheduler API running at `http://localhost:8000`
- A clean database (no registered workers — the worker container must not be running)
- Node.js 20+ with npm (use [nvm](https://github.com/nvm-sh/nvm) if needed)

```bash
# Start only the scheduler stack (no worker, no docker UI)
docker compose up db pgbouncer scheduler -d --wait

# Install Node dependencies and Playwright browsers (first time only)
cd frontend
npm install
npx playwright install chromium   # --with-deps requires sudo; omit if browsers already cached

# Run Playwright tests (Playwright starts/stops the Vite dev server automatically)
VITE_API_BASE_URL=http://localhost:8000 \
DATABASE_URL=postgresql://lightcron:lightcron@localhost:5432/lightcron \
npx playwright test

# Run in headed mode (useful for debugging)
VITE_API_BASE_URL=http://localhost:8000 \
DATABASE_URL=postgresql://lightcron:lightcron@localhost:5432/lightcron \
npx playwright test --headed
```

> **Note**: The docker `ui` profile service is for running the full stack in production-like mode. For testing, Playwright manages the Vite dev server itself via `webServer` in `playwright.config.ts`.

### Linting and type checking

```bash
# Python linting
uv run ruff check src/ tests/

# Python type checking
uv run mypy

# Frontend linting
cd frontend && npm run lint

# Frontend type checking
cd frontend && npm run type-check
```

## Project Structure

```
lightcron/
├── src/lightcron/
│   ├── constants.py              # All timing constants (single source of truth)
│   ├── scheduler/
│   │   ├── domain/jobs/          # Job entity, JobService, DispatchService
│   │   ├── domain/workers/       # Worker entity, WorkerService
│   │   ├── ports/                # JobRepository, WorkerRepository, WorkerHealthClient
│   │   └── adapters/
│   │       ├── db/               # PostgresJobRepository, PostgresWorkerRepository
│   │       ├── health/           # HttpWorkerHealthClient
│   │       └── http/             # FastAPI app, jobs router, workers router, schemas
│   └── worker/
│       ├── domain/execution/     # ExecutionService, ClaimService, RegistrationService
│       ├── ports/                # JobDB, WorkerStatusDB, ProcessManager
│       └── adapters/
│           ├── db/               # AsyncpgJobDB, AsyncpgWorkerStatusDB
│           ├── http/             # Worker health endpoint (:8001)
│           └── process/          # SubprocessAdapter (process group management)
├── src/migrations/               # Alembic migrations
│   └── versions/001_initial_schema.py
├── frontend/src/                 # React 18 / TypeScript / Vite (Feature-Sliced Design)
│   ├── app/                      # Router, QueryClientProvider, entry point
│   ├── pages/                    # DashboardPage, ScheduleJobPage
│   ├── widgets/                  # WorkerFleetPanel, JobsPanel
│   ├── features/                 # StatusFilter, ScheduleJobForm, useScheduleJob
│   ├── entities/                 # Job model + badge, Worker model + badge
│   └── shared/                   # API client, useJobs, useWorkers, constants
├── specs/features/               # Gherkin feature files (source of truth for behaviour)
│   ├── job-management/
│   ├── worker-management/
│   ├── operations/
│   └── ui/
├── tests/
│   ├── bdd/                      # pytest-bdd integration tests (require live DB)
│   └── integration/              # pgBouncer-specific tests
├── scripts/check_fk_integrity.sql
├── docker-compose.yml
└── pyproject.toml
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | asyncpg URL for direct Postgres connection (migrations, tests) |
| `PGBOUNCER_URL` | — | asyncpg URL through pgBouncer (scheduler and worker at runtime) |
| `LIGHTCRON_UI_ORIGIN` | — | Allowed CORS origin for the web UI (e.g. `http://localhost:5173`) |
| `WORKER_CONCURRENCY` | `2` | Max concurrent jobs per worker node |
| `VITE_API_BASE_URL` | — | Scheduler API base URL for the frontend (build-time) |

## Acknowledgements

This project was built using the Claude Agent Framework created by Neal Naidoo.

## License

MIT — see [LICENSE](LICENSE).
