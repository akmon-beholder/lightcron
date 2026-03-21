# Lightcron — Project Instructions for Claude

## What This Project Is

Lightcron is a lightweight job orchestration system. Workers pull jobs from PostgreSQL; there is no message broker. The architecture is hexagonal (backend) and Feature-Sliced Design (frontend).

Key design constraints that must be preserved:
- **DB-as-bus**: PostgreSQL is the only communication channel between scheduler, workers, and UI
- **pgBouncer session mode**: required for `SELECT FOR UPDATE SKIP LOCKED`; transaction mode silently breaks atomic claiming
- **Terminal-state guard**: every DB status write uses `WHERE status NOT IN ('completed','failed','cancelled','lost')`
- **Process group kill**: `os.killpg` not `os.kill` — worker commands may fork children
- **Advisory lock**: `pg_try_advisory_xact_lock(1_000_001)` prevents double ready-transition in multi-scheduler deployments

## CAF Agent Routing

| Work type | Agent |
|-----------|-------|
| New feature (spec + tasklist) | ba → back/front → verify |
| Bug fix, config change | Fast-track: back or front → verify |
| DB migrations, CI changes | ops |
| Architecture / user journey change | design → ba |

**Exclusive paths**: `back` writes `src/` only; `front` writes `frontend/` only.

## Running Tests

Tests require a live PostgreSQL instance. Always start the database first:

```bash
docker compose up db -d
uv run alembic upgrade head
```

Run the full BDD suite:

```bash
uv run python -m pytest tests/bdd/ -v
```

Run with coverage (must reach 80%):

```bash
uv run python -m pytest tests/bdd/ --cov=src/lightcron --cov-report=term-missing --cov-fail-under=80
```

Run a single scenario file:

```bash
uv run python -m pytest tests/bdd/steps/job_management/test_schedule_job.py -v
```

Run just smoke tests:

```bash
uv run python -m pytest tests/bdd/ -m smoke -v
```

The pgBouncer integration test also requires `pgbouncer` service running (`docker compose up pgbouncer -d`).

## Test Architecture

Tests are **BDD integration tests** — they use a real DB, not mocks. There is no unit test layer for DB adapters.

Key fixtures (all in `tests/bdd/conftest.py`):
- `db_engine` — session-scoped async SQLAlchemy engine
- `clean_tables` — autouse; runs `DELETE FROM jobs; DELETE FROM worker_status` after each scenario
- `ctx` — per-scenario `SimpleNamespace` with `response`, `job_ids`, `worker_ids` dicts
- `fake_health` — `FakeWorkerHealthClient`; configure per-worker responses with `set_healthy(wid)` / `set_unhealthy(wid)`; tracks `probed` list
- `scheduler_app` — bare FastAPI app with real DB adapters, no background loops
- `http_client` — `httpx.AsyncClient` pointed at `scheduler_app`
- `job_db` / `worker_status_db` — raw worker-agent DB adapters for worker management tests

Background loops (ready-transition, health-check) are tested by calling their `_run_*_once()` methods directly — they are never started as background tasks in tests.

## Coding Conventions

All timing constants must be imported from `src/lightcron/constants.py` — no numeric literals in application code.

Step definitions in `tests/bdd/steps/`:
- Steps reused across multiple feature files live in `tests/bdd/steps/conftest.py`
- All `@scenario` test functions must be `async def` (pytest-bdd 8 + asyncio_mode=auto)
- Use `parsers.parse(...)` for any step with a variable; bare strings for fixed steps

Frontend conventions (FSD layer import rule):
```
shared ← entities ← features ← widgets ← pages ← app
```
No layer may import from a layer above it. The web UI must not call worker REST APIs directly (only the scheduler API at `VITE_API_BASE_URL`).

## Key Files

| File | Purpose |
|------|---------|
| `src/lightcron/constants.py` | All timing constants — edit here first |
| `src/migrations/versions/001_initial_schema.py` | Full DB schema including triggers |
| `tests/bdd/conftest.py` | All shared test fixtures and DB helper functions |
| `tests/bdd/steps/conftest.py` | Shared step definitions (response status, background given, etc.) |
| `.claude/artifacts/002_spec_v1.md` | Authoritative functional spec — check before changing behaviour |
| `.claude/artifacts/003_tasklist_v1.md` | Full task breakdown with acceptance criteria |
| `.claude/manifest.yaml` | CAF manifest — update `outstanding.remediation` when bugs are found |

## Known Limitations (v1)

1. Dependency cycle detection not implemented — circular deps leave jobs pending forever
2. Cancel is best-effort — process keeps running until worker polls again
3. Memory monitoring latency — up to 5 s gap between breach and detection
4. No job retry — failed/lost jobs must be manually requeued
5. No authentication — assume trusted network

## Deployment

Not yet decided. See ops condition C6 in the solution envelope. Do not push to production without resolving this.
