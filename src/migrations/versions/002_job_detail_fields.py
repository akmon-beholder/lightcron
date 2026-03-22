"""Add env_vars and peak_memory_mb to jobs; add base_url to worker_status.

Revision ID: 002
Revises: 001
Create Date: 2026-03-22

"""

from __future__ import annotations

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE jobs
          ADD COLUMN env_vars      JSONB             NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN peak_memory_mb DOUBLE PRECISION NULL
    """)

    op.execute("""
        ALTER TABLE worker_status
          ADD COLUMN base_url TEXT NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE jobs
          DROP COLUMN IF EXISTS env_vars,
          DROP COLUMN IF EXISTS peak_memory_mb
    """)

    op.execute("""
        ALTER TABLE worker_status
          DROP COLUMN IF EXISTS base_url
    """)
