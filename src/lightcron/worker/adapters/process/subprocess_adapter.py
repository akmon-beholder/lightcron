"""subprocess + psutil implementation of ProcessManager."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess

import psutil


class SubprocessAdapter:
    """Manages OS subprocesses for job execution.

    Key design decisions:
    - Uses start_new_session=True so the child gets its own process group,
      allowing os.killpg to reach all forked descendants.
    - stdout/stderr are redirected to /dev/null for v1 (no log capture).
    - poll_exit is non-blocking.
    """

    def start(self, command: str) -> int:
        proc = subprocess.Popen(
            shlex.split(command),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # creates a new process group
        )
        return proc.pid

    def kill_group(self, pid: int, sig: signal.Signals) -> None:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass  # Process already exited — safe to ignore

    def poll_exit(self, pid: int) -> int | None:
        try:
            proc = psutil.Process(pid)
            if proc.status() == psutil.STATUS_ZOMBIE:
                # Reap the zombie to get its exit code
                _, status = os.waitpid(pid, os.WNOHANG)
                if _:
                    return os.waitstatus_to_exitcode(status)
                return None
            if not proc.is_running():
                return 0  # Unknown exit — treat as success
            return None
        except psutil.NoSuchProcess:
            return 0  # Process no longer exists

    def get_rss_mb(self, pid: int) -> float:
        try:
            proc = psutil.Process(pid)
            return proc.memory_info().rss / (1024 * 1024)
        except psutil.NoSuchProcess:
            return 0.0
