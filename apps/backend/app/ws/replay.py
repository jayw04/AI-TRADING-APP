"""Replay buffer placeholder.

P0 ships only the shape — no actual replay logic. Used from P1+ to let a
freshly-connected WS client catch up on the last N events per topic before
live events start flowing.

TODO: window sizes here are placeholders; reconcile with Implementation
Plan v0.2 §8 once that doc lands in docs/implementation/.
"""

from __future__ import annotations

from typing import Any

# Per-topic ring-buffer depths. Tune in later phases once we have real traffic.
REPLAY_WINDOWS: dict[str, int] = {
    "system": 16,
    "account": 16,
    "orders": 128,
    "fills": 128,
    "positions": 32,
    "signals": 256,
    "risk": 64,
    "journal": 64,
}


class ReplayBuffer:
    """Per-topic ring buffer. P0: shape only, no implementation."""

    def __init__(self, windows: dict[str, int] | None = None) -> None:
        self._windows = dict(windows or REPLAY_WINDOWS)

    def append(self, topic: str, event: dict[str, Any]) -> None:
        raise NotImplementedError("Replay buffer is P1+.")

    def snapshot(self, topic: str) -> list[dict[str, Any]]:
        raise NotImplementedError("Replay buffer is P1+.")
