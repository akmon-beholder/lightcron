"""Canonical determinism pattern library.

Provides port protocols, system adapters, and test fakes for the three
common sources of non-determinism: time, UUIDs, and randomness.

Quick start::

    # Production wiring
    from patterns.determinism import SystemTimeAdapter, SystemUUIDAdapter
    service = MyService(clock=SystemTimeAdapter(), ids=SystemUUIDAdapter())

    # Test wiring
    from patterns.determinism import FakeTimeAdapter, FakeUUIDAdapter
    service = MyService(clock=FakeTimeAdapter(), ids=FakeUUIDAdapter())
"""

from patterns.determinism.adapters import (
    SystemRandomAdapter,
    SystemTimeAdapter,
    SystemUUIDAdapter,
)
from patterns.determinism.fakes import (
    FakeRandomAdapter,
    FakeTimeAdapter,
    FakeUUIDAdapter,
)
from patterns.determinism.ports import RandomPort, TimePort, UUIDPort

__all__ = [
    # Ports (protocols)
    "TimePort",
    "UUIDPort",
    "RandomPort",
    # System adapters
    "SystemTimeAdapter",
    "SystemUUIDAdapter",
    "SystemRandomAdapter",
    # Test fakes
    "FakeTimeAdapter",
    "FakeUUIDAdapter",
    "FakeRandomAdapter",
]
