"""Unit tests for SubprocessAdapter.

Uses real OS processes (true, false, sleep, echo) to verify lifecycle management.
All tests are synchronous — no asyncio needed for this adapter.
"""

from __future__ import annotations

import signal
import time

import pytest

from lightcron.worker.adapters.process.subprocess_adapter import SubprocessAdapter


@pytest.fixture
def adapter() -> SubprocessAdapter:
    return SubprocessAdapter()


def test_start_returns_positive_pid(adapter: SubprocessAdapter) -> None:
    pid = adapter.start("echo hello")
    assert pid > 0
    time.sleep(0.05)  # let it exit cleanly


def test_poll_exit_none_while_running(adapter: SubprocessAdapter) -> None:
    pid = adapter.start("sleep 10")
    try:
        assert adapter.poll_exit(pid) is None
    finally:
        adapter.kill_group(pid, signal.SIGKILL)
        time.sleep(0.05)


def test_poll_exit_returns_zero_on_success(adapter: SubprocessAdapter) -> None:
    pid = adapter.start("true")
    time.sleep(0.1)
    result = adapter.poll_exit(pid)
    assert result == 0


def test_poll_exit_returns_nonzero_on_failure(adapter: SubprocessAdapter) -> None:
    pid = adapter.start("false")
    time.sleep(0.1)
    result = adapter.poll_exit(pid)
    assert result is not None
    assert result != 0


def test_kill_group_terminates_running_process(adapter: SubprocessAdapter) -> None:
    pid = adapter.start("sleep 10")
    adapter.kill_group(pid, signal.SIGKILL)
    time.sleep(0.1)
    assert adapter.poll_exit(pid) is not None


def test_kill_group_safe_on_already_exited_process(adapter: SubprocessAdapter) -> None:
    pid = adapter.start("true")
    time.sleep(0.1)
    # Should not raise even though process has already exited
    adapter.kill_group(pid, signal.SIGKILL)


def test_get_rss_mb_returns_positive_for_running_process(adapter: SubprocessAdapter) -> None:
    pid = adapter.start("sleep 10")
    try:
        rss = adapter.get_rss_mb(pid)
        assert rss > 0.0
    finally:
        adapter.kill_group(pid, signal.SIGKILL)
        time.sleep(0.05)


def test_get_rss_mb_returns_zero_for_nonexistent_pid(adapter: SubprocessAdapter) -> None:
    assert adapter.get_rss_mb(999_999_999) == 0.0
