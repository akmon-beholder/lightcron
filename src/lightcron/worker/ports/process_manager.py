"""ProcessManager port protocol for the worker agent."""

from __future__ import annotations

import signal
from pathlib import Path
from typing import Protocol


class ProcessManager(Protocol):
    def start(
        self,
        command: str,
        env_vars: dict[str, str] | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
    ) -> int:
        """Spawn a subprocess for command. Returns the PID."""
        ...

    def kill_group(self, pid: int, sig: signal.Signals) -> None:
        """Send signal to the entire process group rooted at pid.

        Uses os.killpg to ensure forked child processes are also signalled.
        Handles the case where the process has already exited gracefully.
        """
        ...

    def poll_exit(self, pid: int) -> int | None:
        """Non-blocking check of process status.

        Returns the exit code if the process has exited, None if still running.
        """
        ...

    def get_rss_mb(self, pid: int) -> float:
        """Return resident set size of the process in MB.

        Returns 0.0 if the process no longer exists.
        """
        ...
