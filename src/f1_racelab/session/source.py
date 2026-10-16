"""Mode-independent session source contract consumed by API and UI adapters."""

from __future__ import annotations

from typing import Protocol

from .contracts import RaceState, SessionId


class RaceSource(Protocol):
    """Replay, live and simulation expose the same canonical state at time t."""

    session: SessionId
    duration_seconds: float

    def state_at(self, seconds: float) -> RaceState:
        """Return one validated session state at a nonnegative clock time."""
