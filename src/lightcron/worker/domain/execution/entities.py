"""Worker agent domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID


@dataclass
class JobExecution:
    """Represents a job that this worker agent has claimed."""

    job_id: UUID
    command: str
    worker_id: UUID
    max_runtime: int | None  # seconds; None = unlimited
    max_memory: int | None   # MB; None = unlimited
    env_vars: dict[str, str] = field(default_factory=dict)
    stdout_path: Path = field(default_factory=lambda: Path("/dev/null"))
    stderr_path: Path = field(default_factory=lambda: Path("/dev/null"))
    pid: int | None = None   # Set after process is started
