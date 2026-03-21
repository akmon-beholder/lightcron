"""Test fakes for deterministic testing.

These fakes satisfy the same Protocol contracts as the system adapters
but return predictable, controllable values. Use them in unit tests to
eliminate non-determinism.

Usage::

    clock = FakeTimeAdapter()
    service = MyService(clock=clock)
    result = service.do_something()
    assert result.created_at == clock.now()

    clock.advance(seconds=60)
    result2 = service.do_something()
    assert result2.created_at == clock.now()
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

_ZERO_UUID = UUID("00000000-0000-0000-0000-000000000000")


class FakeTimeAdapter:
    """Deterministic time source for tests.

    Starts at a fixed time (default: 2026-01-01 00:00 UTC) and only
    advances when explicitly told to via ``advance()`` or ``set()``.
    """

    def __init__(self, fixed: datetime | None = None) -> None:
        self._time = fixed or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._time

    def advance(self, seconds: int) -> None:
        """Move the clock forward by *seconds*."""
        self._time += timedelta(seconds=seconds)

    def set(self, dt: datetime) -> None:
        """Jump the clock to an arbitrary point."""
        self._time = dt


class FakeUUIDAdapter:
    """Deterministic UUID source for tests.

    Returns UUIDs from a pre-configured sequence. Once the sequence is
    exhausted, falls back to the zero UUID.
    """

    def __init__(self, sequence: list[UUID] | None = None) -> None:
        self._sequence: list[UUID] = list(sequence or [])
        self._index: int = 0

    def generate(self) -> UUID:
        if self._index < len(self._sequence):
            result = self._sequence[self._index]
            self._index += 1
            return result
        return _ZERO_UUID


class FakeRandomAdapter:
    """Deterministic random source for tests.

    Returns values from a pre-configured list. Once exhausted, repeats
    the last value (or 0.5 if the list was empty).
    """

    def __init__(self, values: list[float | int] | None = None) -> None:
        self._values: list[float | int] = list(values or [0.5])
        self._index: int = 0

    def _next(self) -> float | int:
        if self._index < len(self._values):
            result = self._values[self._index]
            self._index += 1
            return result
        return self._values[-1] if self._values else 0.5

    def uniform(self, a: float, b: float) -> float:  # noqa: ARG002
        return float(self._next())

    def choice(self, seq: Sequence[Any]) -> Any:
        return seq[0] if seq else None

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002
        return int(self._next())
