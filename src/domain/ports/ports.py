"""Protocol definitions for deterministic port injection.

These protocols define the contracts that system adapters and test fakes
must satisfy. Domain code depends on these protocols, never on concrete
implementations.

Usage in domain services::

    class MyService:
        def __init__(self, clock: TimePort, ids: UUIDPort) -> None:
            self._clock = clock
            self._ids = ids

        def create_item(self) -> Item:
            return Item(id=self._ids.generate(), created_at=self._clock.now())
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


class TimePort(Protocol):
    """Contract for obtaining the current time."""

    def now(self) -> datetime: ...


class UUIDPort(Protocol):
    """Contract for generating unique identifiers."""

    def generate(self) -> UUID: ...


class RandomPort(Protocol):
    """Contract for random number generation."""

    def uniform(self, a: float, b: float) -> float: ...

    def choice(self, seq: Sequence[Any]) -> Any: ...

    def randint(self, a: int, b: int) -> int: ...
