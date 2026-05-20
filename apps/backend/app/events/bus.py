"""In-process async pub/sub event bus.

P0: no persistence, no cross-process delivery. One bus per FastAPI process.
Each subscriber owns an asyncio.Queue that the bus fans out to on publish.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any


class EventBus:
    def __init__(self, queue_maxsize: int = 1024) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._queue_maxsize = queue_maxsize
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        subscribers = list(self._subscribers.get(topic, ()))
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest on backpressure so a slow subscriber can't stall the producer.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(event)

    async def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_maxsize)
        async with self._lock:
            self._subscribers.setdefault(topic, []).append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                if topic in self._subscribers and queue in self._subscribers[topic]:
                    self._subscribers[topic].remove(queue)
                    if not self._subscribers[topic]:
                        del self._subscribers[topic]

    def subscriber_count(self, topic: str) -> int:
        return len(self._subscribers.get(topic, ()))


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    return EventBus()


def reset_event_bus() -> None:
    """Test helper: drop the cached bus so the next get_event_bus() returns a fresh one."""
    get_event_bus.cache_clear()
