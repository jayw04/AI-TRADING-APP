"""Per-topic replay buffer for the WebSocket gateway.

When a client subscribes to a topic, the gateway replays recent events from
that topic's ring buffer before live events start flowing. Bounds memory by
keeping at most ``REPLAY_WINDOWS[topic]`` events per topic.

Single instance per backend process — the buffer is process-global state,
not per-connection.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from threading import Lock
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

_DEFAULT_WINDOW = 32


class ReplayBuffer:
    """Per-topic ring buffer. Thread-safe (a normal lock is fine — we only
    append/read short critical sections, never block on I/O)."""

    def __init__(self, windows: dict[str, int] | None = None) -> None:
        self._windows = dict(windows or REPLAY_WINDOWS)
        self._buffers: dict[str, deque[dict[str, Any]]] = {}
        self._lock = Lock()

    def _bucket(self, topic: str) -> deque[dict[str, Any]]:
        b = self._buffers.get(topic)
        if b is None:
            maxlen = self._windows.get(topic, _DEFAULT_WINDOW)
            b = deque(maxlen=maxlen)
            self._buffers[topic] = b
        return b

    def append(self, topic: str, event: dict[str, Any]) -> None:
        with self._lock:
            self._bucket(topic).append(event)

    def get_recent(self, topic: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._buffers.get(topic, ()))

    # Back-compat alias for older tests / docs.
    def snapshot(self, topic: str) -> list[dict[str, Any]]:
        return self.get_recent(topic)


def get_replay_buffer() -> ReplayBuffer:
    """Process-global buffer, lazily created."""
    global _BUFFER
    if _BUFFER is None:
        _BUFFER = ReplayBuffer()
    return _BUFFER


_BUFFER: ReplayBuffer | None = None


def reset_replay_buffer() -> None:
    """Test helper."""
    global _BUFFER
    _BUFFER = None


def known_topics() -> Iterable[str]:
    """Configured WS topics (not bus topics)."""
    return REPLAY_WINDOWS.keys()
