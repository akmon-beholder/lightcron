"""System (production) implementations of determinism ports.

These adapters call real stdlib functions and are the ONLY place where
non-deterministic calls should appear. Domain code receives these via
dependency injection and depends only on the Protocol definitions in
``ports.py``.
"""

from __future__ import annotations

import random as _random
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


class SystemTimeAdapter:
    """Production adapter that returns the real current UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class SystemUUIDAdapter:
    """Production adapter that generates real UUID4 values."""

    def generate(self) -> UUID:
        return uuid4()


class SystemRandomAdapter:
    """Production adapter that delegates to stdlib ``random``."""

    def uniform(self, a: float, b: float) -> float:
        return _random.uniform(a, b)

    def choice(self, seq: Sequence[Any]) -> Any:
        return _random.choice(seq)

    def randint(self, a: int, b: int) -> int:
        return _random.randint(a, b)
