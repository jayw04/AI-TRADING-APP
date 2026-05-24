"""In-process dedup and rate limiting for inbound webhooks.

State is in-memory only. A backend restart clears everything, which is
acceptable because:

- dedup matters only on a ~5 second horizon,
- per-user rate limit matters only on a ~60 second horizon,
- the "real" rate limiter would live behind a proper auth gateway
  (P5 alongside multi-user).

Concurrency: APScheduler + FastAPI both run on the asyncio event loop,
so the dict operations are serialized by the loop without explicit
locking.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from typing import Any

# ---------- Dedup ----------

DEDUP_WINDOW_SECONDS = 5.0

# content_hash -> last-seen epoch seconds
_dedup_cache: dict[str, float] = {}


def _compute_content_hash(
    *,
    user_id: int,
    symbol: str,
    side: str | None,
    strategy_id: int | None,
    payload: dict[str, Any],
) -> str:
    body = json.dumps(
        {
            "user_id": user_id,
            "symbol": symbol,
            "side": side,
            "strategy_id": strategy_id,
            "payload": payload,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def is_duplicate_alert(
    *,
    user_id: int,
    symbol: str,
    side: str | None,
    strategy_id: int | None,
    payload: dict[str, Any],
) -> bool:
    """Return True if an identical alert was seen within ``DEDUP_WINDOW_SECONDS``.

    Always updates the cache, even on a duplicate — a hammering source
    stays suppressed for the full window rather than slipping through
    every ``DEDUP_WINDOW_SECONDS``.
    """
    now = time.time()
    cutoff = now - DEDUP_WINDOW_SECONDS
    stale = [k for k, t in _dedup_cache.items() if t < cutoff]
    for k in stale:
        _dedup_cache.pop(k, None)

    h = _compute_content_hash(
        user_id=user_id,
        symbol=symbol,
        side=side,
        strategy_id=strategy_id,
        payload=payload,
    )
    last_seen = _dedup_cache.get(h)
    _dedup_cache[h] = now
    return last_seen is not None and (now - last_seen) < DEDUP_WINDOW_SECONDS


# ---------- Per-secret rate limit ----------

RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MAX_PER_WINDOW = 20

_rate_buckets: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(*, secret: str) -> bool:
    """Sliding-window per-secret rate limit. Records the current call's
    timestamp before checking so a flood stays limited."""
    now = time.time()
    key = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]
    bucket = _rate_buckets[key]
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    fresh = [t for t in bucket if t > cutoff]
    fresh.append(now)
    _rate_buckets[key] = fresh
    return len(fresh) > RATE_LIMIT_MAX_PER_WINDOW


# ---------- Failed-auth IP throttle ----------
#
# Two-step API by design: ``is_auth_attempt_rate_limited`` is a read-only
# check (call before doing work), ``record_auth_failure`` appends a
# failed-attempt timestamp (call after a 401). Counting only failed attempts
# matches the threat model — bad-actor probing — without throttling
# legitimate high-volume callers whose secrets are valid.

FAILED_AUTH_WINDOW_SECONDS = 60.0
FAILED_AUTH_MAX_PER_WINDOW = 10

_failed_auth_buckets: dict[str, list[float]] = defaultdict(list)


def _prune_failed_auth(client_ip: str) -> list[float]:
    cutoff = time.time() - FAILED_AUTH_WINDOW_SECONDS
    fresh = [t for t in _failed_auth_buckets[client_ip] if t > cutoff]
    _failed_auth_buckets[client_ip] = fresh
    return fresh


def is_auth_attempt_rate_limited(*, client_ip: str) -> bool:
    """Return True if this IP has already accumulated too many bad-secret
    POSTs in the current window. Does NOT record the current call."""
    return len(_prune_failed_auth(client_ip)) >= FAILED_AUTH_MAX_PER_WINDOW


def record_auth_failure(*, client_ip: str) -> None:
    """Append a failed-auth timestamp for ``client_ip``. Call after a 401."""
    _prune_failed_auth(client_ip).append(time.time())


# ---------- Test helpers ----------


def _reset_for_tests() -> None:
    _dedup_cache.clear()
    _rate_buckets.clear()
    _failed_auth_buckets.clear()
