"""Initial schema: jobs and worker_status tables.

Revision ID: 001
Revises:
Create Date: 2026-03-21

"""

from __future__ import annotations

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TYPE job_status AS ENUM (
            'pending',
            'ready',
            'assigned',
            'running',
            'completed',
            'failed',
            'cancelled',
            'lost'
        )
    """)

    op.execute("""
        CREATE TYPE worker_status_enum AS ENUM (
            'online',
            'offline'
        )
    """)

    # ── worker_status ──────────────────────────────────────────────────────────
    # Must be created before jobs because jobs.worker_id references it.
    op.execute("""
        CREATE TABLE worker_status (
            worker_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            hostname      TEXT NOT NULL UNIQUE,
            status        worker_status_enum NOT NULL DEFAULT 'online',
            last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX worker_status_last_seen_idx
            ON worker_status (last_seen)
    """)

    # ── jobs ──────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE jobs (
            job_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            command     TEXT NOT NULL,
            start_time  TIMESTAMPTZ NOT NULL,
            depends_on  UUID[] NOT NULL DEFAULT '{}',
            max_runtime INTEGER NULL CHECK (max_runtime > 0),
            max_memory  INTEGER NULL CHECK (max_memory > 0),
            status      job_status NOT NULL DEFAULT 'pending',
            worker_id   UUID NULL REFERENCES worker_status(worker_id),
            exit_code   INTEGER NULL,
            kill_reason TEXT NULL,
            claimed_at  TIMESTAMPTZ NULL,
            started_at  TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX jobs_status_idx    ON jobs (status)")
    op.execute("CREATE INDEX jobs_worker_id_idx ON jobs (worker_id)")
    op.execute("CREATE INDEX jobs_start_time_idx ON jobs (start_time)")

    # ── updated_at trigger ────────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER jobs_set_updated_at
        BEFORE UPDATE ON jobs
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS jobs_set_updated_at ON jobs")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS worker_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS worker_status_enum")
