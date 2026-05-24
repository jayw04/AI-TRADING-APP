# P4 Item 1 — TradingView Pine Webhook Receiver

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-23 |
| Phase | **P4 — Polish & Extend**, Item §1 |
| Predecessor | *TradingWorkbench_P4_Checklist_v0.1.md* (tag `p3-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | A `POST /api/v1/alerts/tv` endpoint that accepts TradingView Pine alert webhooks, authenticates via a per-user secret in the JSON body, dedupes near-duplicate alerts, rate-limits by user, persists each as a `Signal` row with `type='pine_alert'`, and publishes on the event bus so the existing WS layer surfaces them. Includes the runbook for setting up a TV alert. Single PR. |
| Estimated wall time | 3–4 hours |
| Stopping point | `git tag p4-tv-webhooks-complete` |
| Out of scope | Pine *runtime* (executing Pine code in the engine). Hybrid Python/Pine strategies. Multi-step alerts. Per-user web UI for managing webhook secrets — secret rotation in P4 is a single REST endpoint; the dashboard UI lands when it's needed. |

---

## Session Goal

After this session:
- A trader can configure a TradingView Pine alert with a custom webhook URL pointing at this backend (typically via a Cloudflare tunnel for local development) and a JSON message template.
- TV fires the alert; the backend authenticates via the secret in the body, persists a `Signal` row with `type='pine_alert'`, and the signal appears in the UI's Signals view within 1 second.
- Duplicate alerts within 5 seconds are deduped (returns 200 but no second row).
- A wrong-secret POST returns 401 and is rate-limited.
- A `docs/runbook/tv-webhooks.md` documents the setup including a sample Pine alert message body.

What does NOT happen this session:
- No Pine code is executed by the backend. Pine alerts are a *signal-routing* feature, not a strategy *runtime* feature. Hybrid strategies (Pine-trigger + Python-execute) would be a separate item.
- No UI for managing webhook secrets. The secret is set via a one-shot REST call documented in the runbook.
- No retry-on-failure if the backend is down when TV fires. TV's webhooks are best-effort; if a missed alert matters, the strategy author needs to architect for it. Worth a note in the runbook.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p3-complete

./scripts/dev.sh &
sleep 30

# Backend healthy
curl -fs http://127.0.0.1:8000/healthz | jq -e '.status == "ok"'

# Existing signals API works (we'll surface pine_alerts through the same shape)
curl -fs http://127.0.0.1:8000/api/v1/signals?limit=5 | jq '.count'

# Cloudflare tunnel is up (if you plan to test against a real TV alert during smoke)
# Per Jay's prior setup: rag-app-tunnel (ID: 5dd987ce). Equivalent tunnel needed
# for the trading workbench backend — different hostname, same idea.
cloudflared tunnel list 2>/dev/null | head

docker compose down
```

- [ ] On `main`, clean tree, at `p3-complete` or later.
- [ ] Backend boots; `/api/v1/signals` reachable.
- [ ] (Optional) A tunnel to localhost:8000 if you intend to smoke against a real TV alert.

```bash
git checkout -b feat/p4-tv-pine-webhooks
```

---

## §1.1 — Database Migration: Per-User Webhook Secret

We need a per-user secret. Two options:
1. New column on `users`: simple, single migration.
2. Row in `system_config` keyed by `(user_id, key='pine_webhook_secret')`: matches the generic-KV pattern already used elsewhere.

**Decision: Option 1 (column on `users`).** This is a credential, not a configuration; storing it as a typed column makes the intent explicit and the migration trivial. P5 will introduce proper credential encryption when multi-user auth lands; until then the secret is plaintext at rest — same disposition as `ANTHROPIC_API_KEY` in `.env`.

Edit `apps/backend/app/db/models/user.py`. Add to the `User` model:

```python
from secrets import token_urlsafe

# ... inside User class:
pine_webhook_secret: Mapped[str | None] = mapped_column(
    String(64), nullable=True, unique=True, index=True
)
```

Generate migration:

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "P4: pine_webhook_secret on users"
```

Open the generated migration. Verify:

- [ ] `op.add_column("users", sa.Column("pine_webhook_secret", sa.String(64), nullable=True))`
- [ ] `op.create_index("ix_users_pine_webhook_secret", "users", ["pine_webhook_secret"], unique=True)`
- [ ] `op.create_unique_constraint(...)` if your dialect doesn't auto-uniq via the index.
- [ ] `downgrade()` drops the column.

Apply:

```bash
uv run alembic upgrade head
uv run sqlite3 data/workbench.sqlite ".schema users" | grep -i pine_webhook
# Expect: pine_webhook_secret VARCHAR(64), and a unique index on it.

# Round-trip
uv run alembic downgrade -1
uv run alembic upgrade head
cd ../..
```

- [ ] Migration applies and round-trips.

---

## §1.2 — Secret Generation and Rotation

The user needs a way to (a) generate their secret on first use, (b) rotate it later. One small REST endpoint covers both.

Edit `apps/backend/app/api/v1/users.py` (if it exists; otherwise create it):

```python
"""User-self endpoints. /me — the currently-authenticated user.

For P4 the auth stub returns user_id=1; in P5 this resolves to whichever
user the auth token identifies.
"""
from __future__ import annotations

from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import get_current_user
from app.db.models.user import User
from app.db.session import get_session
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])


class WebhookSecretResponse(BaseModel):
    pine_webhook_secret: str
    # Surface a help string so the runbook flow is self-describing in the
    # response payload. The trader copies the secret into their TV alert
    # JSON body; the URL is the same for everyone.
    instructions: str


@router.post("/me/regenerate-webhook-secret", response_model=WebhookSecretResponse)
async def regenerate_webhook_secret(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Generate (or rotate) the current user's Pine webhook secret.

    Returns the new secret in the response. The secret is the ONLY piece of
    credential that goes into the user's TradingView alert body. Treat it
    like a password.
    """
    row = await session.get(User, current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    # 256-bit URL-safe secret; ~43 chars.
    new_secret = token_urlsafe(32)
    row.pine_webhook_secret = new_secret
    await session.commit()

    return WebhookSecretResponse(
        pine_webhook_secret=new_secret,
        instructions=(
            "Place this secret in the JSON body of your TradingView alert as "
            "the 'secret' field. See docs/runbook/tv-webhooks.md for the full "
            "message template."
        ),
    )


@router.get("/me/webhook-secret", response_model=WebhookSecretResponse)
async def get_webhook_secret(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Show the current Pine webhook secret. If unset, returns 404 with
    instructions to regenerate."""
    row = await session.get(User, current_user.id)
    if row is None or not row.pine_webhook_secret:
        raise HTTPException(
            status_code=404,
            detail="No Pine webhook secret set. POST /users/me/regenerate-webhook-secret to create one.",
        )
    return WebhookSecretResponse(
        pine_webhook_secret=row.pine_webhook_secret,
        instructions="See docs/runbook/tv-webhooks.md.",
    )
```

Mount in `apps/backend/app/main.py`:

```python
from app.api.v1 import users as users_router
app.include_router(users_router.router, prefix="/api/v1")
```

- [ ] `users.py` endpoints created.
- [ ] Mounted.

> The `GET` endpoint returns the secret in plaintext. This is acceptable in P4 (local-only, single-user) but a real concern for P5 multi-user — at that point the GET should be removed and rotation becomes write-only with the secret shown exactly once. Note this in the runbook.

---

## §1.3 — Pydantic Schemas

Create `apps/backend/app/api/v1/schemas/alerts.py`:

```python
"""Pydantic schemas for TradingView Pine alert webhooks.

The body shape is deliberately permissive on `payload` (Dict[str, Any]) so
TV alert authors can include arbitrary metadata (price, indicator values,
strategy_name, etc.) without us shipping a schema update each time.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TVWebhookRequest(BaseModel):
    """Body of a TradingView Pine webhook POST.

    Example body the trader puts in their alert:

      {
        "secret": "{{your_secret_here}}",
        "symbol": "{{ticker}}",
        "side": "buy",
        "payload": {
          "price": "{{close}}",
          "rsi": "{{plot_0}}",
          "comment": "RSI cross under 30"
        }
      }

    TV substitutes the {{...}} tokens at alert time.
    """
    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=8, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    # Side is optional — some alerts are pure information events (RSI cross,
    # volume spike) without a directional bias.
    side: Optional[Literal["buy", "sell", "long", "short", "flat"]] = None
    # The strategy_id field lets the alert bind to a Strategy row. If set,
    # the user-id-on-the-secret must own that strategy or we 403.
    strategy_id: Optional[int] = Field(default=None, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class TVWebhookAcceptedResponse(BaseModel):
    """Response when an alert is accepted (or deduped — both are 200)."""
    signal_id: Optional[int]              # None if deduped
    deduped: bool
    received_at: str                       # ISO timestamp
```

- [ ] Schemas created.

---

## §1.4 — Dedup + Rate Limit Helpers

Create `apps/backend/app/alerts/__init__.py` (empty) and `apps/backend/app/alerts/throttle.py`:

```python
"""In-process dedup and rate limiting for inbound webhooks.

State is in-memory only. A backend restart clears everything — acceptable
because:
  - dedup matters only on a ~5 second horizon
  - rate limit matters only on a ~60 second horizon
  - the deferred "real" rate limiter would live behind a proper auth gateway,
    which is P5 alongside multi-user.

Concurrency: APScheduler + FastAPI both run on the asyncio event loop, so
the dict operations are serialized by the loop without explicit locking.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------- Dedup ----------

# Maps content_hash → ts (epoch seconds). We drop duplicates within
# DEDUP_WINDOW_SECONDS. Cleanup happens on each request rather than on a
# timer (cheap; we already iterate the dict).
DEDUP_WINDOW_SECONDS = 5.0
_dedup_cache: dict[str, float] = {}


def _compute_content_hash(*, user_id: int, symbol: str, side: str | None,
                          strategy_id: int | None, payload: dict[str, Any]) -> str:
    # Stable serialization: sorted keys to avoid dict-order false negatives.
    body = json.dumps({
        "user_id": user_id,
        "symbol": symbol,
        "side": side,
        "strategy_id": strategy_id,
        "payload": payload,
    }, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def is_duplicate_alert(*, user_id: int, symbol: str, side: str | None,
                       strategy_id: int | None, payload: dict[str, Any]) -> bool:
    """Returns True if an identical alert was seen within DEDUP_WINDOW_SECONDS.

    Always updates the cache so a subsequent identical alert later resets the
    window (TV may legitimately send the same condition twice with a longer
    gap; we only want to suppress *near-instant* duplicates).
    """
    now = time.time()
    # Cleanup: drop entries older than the window
    cutoff = now - DEDUP_WINDOW_SECONDS
    stale = [k for k, t in _dedup_cache.items() if t < cutoff]
    for k in stale:
        _dedup_cache.pop(k, None)

    h = _compute_content_hash(
        user_id=user_id, symbol=symbol, side=side,
        strategy_id=strategy_id, payload=payload,
    )
    last_seen = _dedup_cache.get(h)
    _dedup_cache[h] = now
    if last_seen is not None and (now - last_seen) < DEDUP_WINDOW_SECONDS:
        return True
    return False


# ---------- Rate limit ----------

# Per-secret sliding window counter. We don't expose the secret in logs —
# only its hash prefix.
RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MAX_PER_WINDOW = 20
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(*, secret: str) -> bool:
    """Returns True if this secret has already hit the rate limit in the
    current window. Always records the current call's timestamp (the cost of
    rate-limited calls is included so a hammering caller stays limited)."""
    now = time.time()
    key = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]
    bucket = _rate_buckets[key]
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    # Drop entries outside the window
    fresh = [t for t in bucket if t > cutoff]
    fresh.append(now)
    _rate_buckets[key] = fresh
    return len(fresh) > RATE_LIMIT_MAX_PER_WINDOW


# ---------- Failed-auth throttle (separate from rate limit) ----------

# A bad-secret POST is a credential probing attempt. We rate-limit BY IP
# rather than by secret (because there is no valid secret to key on).
# A real production deployment would do this at the gateway layer; in P4
# we do a minimal version here.
_failed_auth_buckets: dict[str, list[float]] = defaultdict(list)
FAILED_AUTH_WINDOW_SECONDS = 60.0
FAILED_AUTH_MAX_PER_WINDOW = 10


def is_auth_attempt_rate_limited(*, client_ip: str) -> bool:
    now = time.time()
    bucket = _failed_auth_buckets[client_ip]
    cutoff = now - FAILED_AUTH_WINDOW_SECONDS
    fresh = [t for t in bucket if t > cutoff]
    fresh.append(now)
    _failed_auth_buckets[client_ip] = fresh
    return len(fresh) > FAILED_AUTH_MAX_PER_WINDOW


# ---------- Test helpers ----------

def _reset_for_tests() -> None:
    _dedup_cache.clear()
    _rate_buckets.clear()
    _failed_auth_buckets.clear()
```

- [ ] `throttle.py` created.

---

## §1.5 — The Endpoint

Create `apps/backend/app/api/v1/alerts.py`:

```python
"""POST /api/v1/alerts/tv — TradingView Pine alert receiver.

Flow:
  1. Validate body shape (Pydantic).
  2. Lookup the user by `secret`. Wrong secret → 401, IP rate-limited.
  3. Resolve the symbol ticker to a `symbols` row. Unknown → 400.
  4. If `strategy_id` is set, verify ownership (404 if mismatch).
  5. Dedup check.
  6. Rate-limit check.
  7. Insert Signal row with type=PINE_ALERT.
  8. Publish signal.new on the bus.
  9. Return TVWebhookAcceptedResponse.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.throttle import (
    is_auth_attempt_rate_limited,
    is_duplicate_alert,
    is_rate_limited,
)
from app.api.v1.schemas.alerts import TVWebhookAcceptedResponse, TVWebhookRequest
from app.db.enums import SignalType
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.db.session import get_session

logger = structlog.get_logger(__name__)


router = APIRouter(prefix="/alerts", tags=["alerts"])


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Tunnels (Cloudflare, etc.) put the real client
    IP in X-Forwarded-For; trust the first value when present."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/tv", response_model=TVWebhookAcceptedResponse)
async def receive_tv_alert(
    body: TVWebhookRequest,
    request: Request,
):
    """Accept a TradingView Pine alert webhook.

    This endpoint deliberately doesn't use the auth stub — the secret in the
    body IS the auth. The current_user is resolved by secret lookup.
    """
    client_ip = _client_ip(request)

    # Pre-flight: bad-actor IP throttle. If this IP has been failing auth
    # rapidly, refuse to even DB-lookup.
    if is_auth_attempt_rate_limited(client_ip=client_ip):
        logger.warning("tv_alert_ip_rate_limited", ip=client_ip)
        raise HTTPException(status_code=429, detail="Too many requests")

    # Use a short-lived session for auth lookup (avoids holding a session
    # if the request will be rejected).
    from app.db.session import session_scope        # convenience wrapper

    async with session_scope() as session:
        user = (await session.execute(
            select(User).where(User.pine_webhook_secret == body.secret)
        )).scalars().first()

        if user is None:
            logger.warning("tv_alert_bad_secret", ip=client_ip)
            # Note: we do NOT include a "did you mean" or detail leak.
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        # The secret matched; user authenticated. Now do per-user rate limit.
        if is_rate_limited(secret=body.secret):
            logger.warning("tv_alert_user_rate_limited", user_id=user.id, ip=client_ip)
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Resolve symbol
        symbol_row = (await session.execute(
            select(Symbol).where(Symbol.ticker == body.symbol)
        )).scalars().first()
        if symbol_row is None:
            logger.info("tv_alert_unknown_symbol", user_id=user.id, ticker=body.symbol)
            raise HTTPException(status_code=400, detail=f"Unknown symbol: {body.symbol}")

        # If strategy_id given, verify ownership
        if body.strategy_id is not None:
            strat = await session.get(StrategyRow, body.strategy_id)
            if strat is None or strat.user_id != user.id:
                logger.warning("tv_alert_strategy_ownership_mismatch",
                               user_id=user.id, strategy_id=body.strategy_id)
                raise HTTPException(status_code=404, detail="Strategy not found")

        # Dedup
        if is_duplicate_alert(
            user_id=user.id, symbol=body.symbol, side=body.side,
            strategy_id=body.strategy_id, payload=body.payload,
        ):
            logger.info("tv_alert_deduped",
                        user_id=user.id, symbol=body.symbol, side=body.side)
            return TVWebhookAcceptedResponse(
                signal_id=None,
                deduped=True,
                received_at=datetime.now(timezone.utc).isoformat(),
            )

        # Insert signal
        # Pack the side into the payload alongside any TV-supplied data.
        merged_payload = dict(body.payload)
        if body.side is not None:
            merged_payload["side"] = body.side
        merged_payload["source"] = "tradingview"
        merged_payload["received_from_ip"] = client_ip

        signal = Signal(
            user_id=user.id,
            strategy_id=body.strategy_id,    # nullable
            symbol_id=symbol_row.id,
            type=SignalType.PINE_ALERT,
            payload_json=merged_payload,
            received_at=datetime.now(timezone.utc),
        )
        session.add(signal)
        await session.commit()
        await session.refresh(signal)
        signal_id = signal.id

    # Outside the session — publish on the bus
    bus = getattr(request.app.state, "event_bus", None)
    if bus is not None:
        try:
            await bus.publish("signal.new", {
                "signal_id": signal_id,
                "strategy_id": body.strategy_id,
                "symbol": body.symbol,
                "type": SignalType.PINE_ALERT.value,
                "payload": merged_payload,
                "received_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            logger.exception("tv_alert_bus_publish_failed", signal_id=signal_id)

    logger.info("tv_alert_accepted",
                user_id=user.id, signal_id=signal_id,
                symbol=body.symbol, side=body.side,
                strategy_id=body.strategy_id)

    return TVWebhookAcceptedResponse(
        signal_id=signal_id,
        deduped=False,
        received_at=datetime.now(timezone.utc).isoformat(),
    )
```

Mount in `apps/backend/app/main.py`:

```python
from app.api.v1 import alerts as alerts_router
app.include_router(alerts_router.router, prefix="/api/v1")
```

- [ ] Router created and mounted.

> About the `session_scope()` import — if your codebase exposes session-factory access through a different helper, swap it. The intent is: don't lean on FastAPI's `Depends(get_session)` here because we want a session even when the request is rejected on the throttle path, and we want to commit-and-close before publishing on the bus.

---

## §1.6 — Tests

Create `apps/backend/tests/api/test_tv_alerts.py`:

```python
"""TradingView Pine webhook endpoint tests."""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.alerts.throttle import _reset_for_tests
from app.db.enums import SignalType, StrategyStatus, StrategyType
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def reset_throttle():
    _reset_for_tests()
    yield
    _reset_for_tests()


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(
            id=1, email="jay@test", display_name="Jay",
            pine_webhook_secret="test-secret-abc123",
        ))
        session.add(User(
            id=2, email="other@test", display_name="Other",
            pine_webhook_secret="other-secret-xyz789",
        ))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(StrategyRow(
            id=1, user_id=1, name="user1-strat", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=2, user_id=2, name="user2-strat", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.fixture
async def client(seeded):
    from unittest.mock import MagicMock, AsyncMock
    from app.main import create_app
    app = create_app()
    app.state.event_bus = MagicMock()
    app.state.event_bus.publish = AsyncMock()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_valid_alert_creates_signal(client, session_factory):
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "side": "buy",
        "payload": {"price": "190.5", "rsi": "28.1"},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["signal_id"] is not None
    assert body["deduped"] is False

    async with session_factory() as session:
        sig = await session.get(Signal, body["signal_id"])
        assert sig is not None
        assert sig.user_id == 1
        assert sig.type == SignalType.PINE_ALERT
        assert sig.strategy_id is None
        assert sig.payload_json["price"] == "190.5"
        assert sig.payload_json["side"] == "buy"
        assert sig.payload_json["source"] == "tradingview"


@pytest.mark.asyncio
async def test_bad_secret_returns_401(client):
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "nope-not-a-real-secret",
        "symbol": "AAPL",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unknown_symbol_returns_400(client):
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "ZZZZZZ",
    })
    assert resp.status_code == 400
    assert "Unknown symbol" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_strategy_ownership_mismatch_returns_404(client):
    """user1's secret + user2's strategy_id → 404."""
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "strategy_id": 2,                    # belongs to user 2
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_strategy_id_binds_correctly(client, session_factory):
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "strategy_id": 1,
        "side": "sell",
        "payload": {"rsi": "75.0"},
    })
    assert resp.status_code == 200
    sid = resp.json()["signal_id"]
    async with session_factory() as session:
        sig = await session.get(Signal, sid)
        assert sig.strategy_id == 1


@pytest.mark.asyncio
async def test_dedup_within_window(client):
    body = {
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "side": "buy",
        "payload": {"price": "190.5"},
    }
    r1 = await client.post("/api/v1/alerts/tv", json=body)
    assert r1.status_code == 200
    assert r1.json()["deduped"] is False

    r2 = await client.post("/api/v1/alerts/tv", json=body)
    assert r2.status_code == 200
    assert r2.json()["deduped"] is True
    assert r2.json()["signal_id"] is None


@pytest.mark.asyncio
async def test_dedup_does_not_apply_to_different_payloads(client):
    r1 = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123", "symbol": "AAPL",
        "side": "buy", "payload": {"price": "190.5"},
    })
    r2 = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123", "symbol": "AAPL",
        "side": "buy", "payload": {"price": "190.6"},
    })
    assert r1.json()["deduped"] is False
    assert r2.json()["deduped"] is False


@pytest.mark.asyncio
async def test_rate_limit_kicks_in_after_threshold(client):
    """RATE_LIMIT_MAX_PER_WINDOW=20. 21st request should be rate-limited."""
    for i in range(20):
        resp = await client.post("/api/v1/alerts/tv", json={
            "secret": "test-secret-abc123",
            "symbol": "AAPL",
            "side": "buy",
            "payload": {"i": i},      # vary to avoid dedup
        })
        assert resp.status_code == 200, f"failed at i={i}: {resp.text}"

    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "side": "buy",
        "payload": {"i": 999},
    })
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_extra_fields_rejected(client):
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "fnord": "extra",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_publishes_signal_new_on_bus(client):
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "AAPL",
        "side": "buy",
    })
    assert resp.status_code == 200

    # The MagicMock event_bus.publish should have been called with ('signal.new', payload)
    bus = client._transport.app.state.event_bus
    bus.publish.assert_called()
    args = bus.publish.call_args.args
    assert args[0] == "signal.new"
    assert args[1]["type"] == "pine_alert"
    assert args[1]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_symbol_is_uppercased(client, session_factory):
    resp = await client.post("/api/v1/alerts/tv", json={
        "secret": "test-secret-abc123",
        "symbol": "aapl",                    # lowercase
    })
    assert resp.status_code == 200
    sid = resp.json()["signal_id"]
    async with session_factory() as session:
        sig = await session.get(Signal, sid)
        sym = await session.get(Symbol, sig.symbol_id)
        assert sym.ticker == "AAPL"


@pytest.mark.asyncio
async def test_failed_auth_ip_throttle(client):
    """11 bad-secret POSTs from same IP → second 11th is throttled (429),
    before the secret is even looked up."""
    for _ in range(10):
        r = await client.post("/api/v1/alerts/tv", json={
            "secret": "wrong-secret-attempt", "symbol": "AAPL",
        })
        assert r.status_code == 401

    r = await client.post("/api/v1/alerts/tv", json={
        "secret": "wrong-secret-attempt", "symbol": "AAPL",
    })
    assert r.status_code == 429
```

Also create a small throttle unit test in `apps/backend/tests/alerts/test_throttle.py`:

```python
"""Unit tests for the throttle helpers."""
import time

import pytest

from app.alerts import throttle as th


@pytest.fixture(autouse=True)
def reset():
    th._reset_for_tests()
    yield
    th._reset_for_tests()


def test_dedup_first_call_is_not_duplicate():
    assert th.is_duplicate_alert(
        user_id=1, symbol="AAPL", side="buy",
        strategy_id=None, payload={"x": 1},
    ) is False


def test_dedup_second_identical_call_is_duplicate():
    args = dict(user_id=1, symbol="AAPL", side="buy",
                strategy_id=None, payload={"x": 1})
    th.is_duplicate_alert(**args)
    assert th.is_duplicate_alert(**args) is True


def test_dedup_different_payload_is_not_duplicate():
    th.is_duplicate_alert(user_id=1, symbol="AAPL", side="buy",
                          strategy_id=None, payload={"x": 1})
    assert th.is_duplicate_alert(
        user_id=1, symbol="AAPL", side="buy",
        strategy_id=None, payload={"x": 2},
    ) is False


def test_dedup_window_expires():
    args = dict(user_id=1, symbol="AAPL", side="buy",
                strategy_id=None, payload={})
    th.is_duplicate_alert(**args)
    # Forcibly age the entry past the window
    h = th._compute_content_hash(**args)
    th._dedup_cache[h] = time.time() - (th.DEDUP_WINDOW_SECONDS + 1.0)
    assert th.is_duplicate_alert(**args) is False


def test_rate_limit_allows_under_threshold():
    for _ in range(th.RATE_LIMIT_MAX_PER_WINDOW):
        assert th.is_rate_limited(secret="abc") is False


def test_rate_limit_fires_over_threshold():
    for _ in range(th.RATE_LIMIT_MAX_PER_WINDOW):
        th.is_rate_limited(secret="abc")
    assert th.is_rate_limited(secret="abc") is True


def test_rate_limit_separate_secrets_independent():
    for _ in range(th.RATE_LIMIT_MAX_PER_WINDOW):
        th.is_rate_limited(secret="abc")
    # Different secret has its own bucket
    assert th.is_rate_limited(secret="def") is False


def test_failed_auth_throttle():
    for _ in range(th.FAILED_AUTH_MAX_PER_WINDOW):
        assert th.is_auth_attempt_rate_limited(client_ip="1.2.3.4") is False
    assert th.is_auth_attempt_rate_limited(client_ip="1.2.3.4") is True
```

Run:

```bash
cd apps/backend
uv run pytest tests/api/test_tv_alerts.py tests/alerts/test_throttle.py -v
uv run pytest -q          # full suite still green
cd ../..
```

- [ ] All endpoint tests pass (~11 cases).
- [ ] Throttle unit tests pass (~8 cases).
- [ ] Full backend suite still green.

---

## §1.7 — Runbook Doc

Create `docs/runbook/tv-webhooks.md`:

````markdown
# TradingView Pine Webhook Setup

The workbench accepts Pine alert webhooks from TradingView. Each accepted
alert becomes a `Signal` row with `type='pine_alert'` and surfaces in the
Signals view (cross-strategy) and the relevant Strategy detail (if bound).

## One-time setup

### 1. Generate your webhook secret

```bash
curl -X POST http://127.0.0.1:8000/api/v1/users/me/regenerate-webhook-secret
```

Response includes a 256-bit URL-safe secret. **Save it now** — the GET
endpoint will show it again, but rotate any time and you'll need to update
every TV alert that references the old one.

### 2. Expose your backend to the internet

TradingView's webhook senders are on TV's infrastructure, not your local
machine. You need a public URL that routes to `http://127.0.0.1:8000`.

Recommended: Cloudflare Tunnel.

```bash
cloudflared tunnel create workbench-alerts
cloudflared tunnel route dns workbench-alerts workbench-alerts.<your-domain>
# Then in the cloudflared config: ingress: workbench-alerts.<your-domain>
#   → http://localhost:8000
cloudflared tunnel run workbench-alerts
```

Confirm reachability:

```bash
curl -X POST https://workbench-alerts.<your-domain>/api/v1/alerts/tv \
  -H "Content-Type: application/json" \
  -d '{"secret":"<your-secret>","symbol":"AAPL"}'
# Expect 200 with signal_id.
```

> **Local development tip.** If you don't want a public URL, you can test
> against `http://127.0.0.1:8000` using curl in step 4 below — just skip
> the TV side.

### 3. Configure the TV alert

On any TradingView chart:

1. Right-click → Add alert.
2. Set the condition (any Pine alert condition or built-in indicator alert).
3. **Notifications tab → Webhook URL:**
   `https://workbench-alerts.<your-domain>/api/v1/alerts/tv`
4. **Message:** paste the JSON template below. TradingView substitutes
   `{{ticker}}`, `{{close}}`, etc. at alert time.

```json
{
  "secret": "<paste-your-secret-here>",
  "symbol": "{{ticker}}",
  "side": "buy",
  "payload": {
    "price": "{{close}}",
    "alert_name": "{{plot_title}}",
    "interval": "{{interval}}",
    "comment": "{{strategy.order.comment}}"
  }
}
```

For an exit alert, set `"side": "sell"`. For a non-directional info alert
(e.g. "RSI crossed 50"), omit `side`.

### 4. (Optional) Bind to a strategy

If you have a Python strategy you want to feed signals into, add
`"strategy_id": <id>` to the JSON body. The backend verifies the
strategy belongs to you (the secret identifies the user).

```json
{
  "secret": "<your-secret>",
  "symbol": "{{ticker}}",
  "strategy_id": 5,
  "side": "buy"
}
```

The Python strategy's `on_signal` handler is invoked when a bound
pine_alert lands.

### 5. Verify end-to-end

After saving the alert, wait for it to fire (or force-fire from TV's
test button).

Check the backend logs:

```bash
docker compose logs backend | grep tv_alert_accepted
```

Or query the API:

```bash
curl http://127.0.0.1:8000/api/v1/signals?type=pine_alert | jq '.items[0]'
```

The signal also broadcasts on the `signals` WS topic — Strategies tab
and Signals page update instantly.

## Limits

- **Dedup window:** 5 seconds. Identical alerts within 5s of each other
  produce one signal row.
- **Rate limit:** 20 alerts per minute per secret. The 21st returns
  429 and is dropped.
- **Symbol must be known** to the workbench (in `symbols` table). For
  US equities pulled by Alpaca this is automatic; for international or
  exotic instruments, populate `symbols` manually first.

## Failure modes

- **TV's webhook delivery is best-effort.** If the backend is down when
  TV fires, the alert is lost. There is no retry. Design strategies that
  can tolerate missed alerts.
- **The secret is in your alert body in plaintext.** Don't share alert
  exports without redacting it. If a secret leaks, rotate immediately.

## Rotation

```bash
curl -X POST http://127.0.0.1:8000/api/v1/users/me/regenerate-webhook-secret
```

Update every TV alert that uses the old secret. The old secret is
invalidated immediately.

## What if I don't see my alert?

1. Check `tv_alert_*` log lines in the backend:
   ```bash
   docker compose logs backend | grep tv_alert
   ```
   - `tv_alert_bad_secret` → wrong secret in body
   - `tv_alert_unknown_symbol` → ticker not in the symbols table
   - `tv_alert_user_rate_limited` → over 20/min
   - `tv_alert_deduped` → identical alert in last 5s
   - `tv_alert_accepted` → all good

2. If you don't see anything: the request didn't reach the backend.
   Check your tunnel, the URL, and TV's own log (Manage Alerts → Logs).

3. The alert reached the backend but isn't in the UI:
   - Refresh the page (the WS may have disconnected).
   - Confirm via `GET /api/v1/signals?type=pine_alert`.
````

- [ ] Runbook committed.

---

## §1.8 — Manual Smoke

Two flavors. The first works without a TV account; the second requires one.

### 1.8.1 — Local curl smoke (no TV needed)

```bash
./scripts/dev.sh &
sleep 30

# Generate a secret
SECRET=$(curl -s -X POST http://127.0.0.1:8000/api/v1/users/me/regenerate-webhook-secret \
  | jq -r '.pine_webhook_secret')
echo "Secret: $SECRET"

# Send a happy-path alert
curl -s -X POST http://127.0.0.1:8000/api/v1/alerts/tv \
  -H "Content-Type: application/json" \
  -d "{
    \"secret\": \"$SECRET\",
    \"symbol\": \"AAPL\",
    \"side\": \"buy\",
    \"payload\": {\"price\": \"190.50\", \"alert_name\": \"RSI Oversold\"}
  }" | jq

# Verify it was persisted
curl -s "http://127.0.0.1:8000/api/v1/signals?type=pine_alert&limit=1" | jq '.items[0]'

# Send the SAME alert immediately — expect dedup
curl -s -X POST http://127.0.0.1:8000/api/v1/alerts/tv \
  -H "Content-Type: application/json" \
  -d "{
    \"secret\": \"$SECRET\",
    \"symbol\": \"AAPL\",
    \"side\": \"buy\",
    \"payload\": {\"price\": \"190.50\", \"alert_name\": \"RSI Oversold\"}
  }" | jq '.deduped'
# Expect: true

# Bad secret
curl -s -X POST http://127.0.0.1:8000/api/v1/alerts/tv \
  -H "Content-Type: application/json" \
  -d '{"secret":"wrong","symbol":"AAPL"}'
# Expect: 401

# Unknown symbol
curl -s -X POST http://127.0.0.1:8000/api/v1/alerts/tv \
  -H "Content-Type: application/json" \
  -d "{\"secret\":\"$SECRET\",\"symbol\":\"BOGUS\"}"
# Expect: 400

# Check signals page in UI: open http://localhost:5173 and look for the alert

docker compose down
```

- [ ] All five curl steps behave as documented.

### 1.8.2 — Real TV alert smoke (if you have a tunnel and TV account)

Configure a TV alert per the runbook §3. Fire it (use the "Test" button in
TV's Alert manager). Confirm:

- [ ] Backend log shows `tv_alert_accepted`.
- [ ] Signal appears in the Signals view in the UI within ~1 second.
- [ ] If you set `strategy_id`, the signal appears in that strategy's Signals tab.

---

## §1.9 — Commit and PR

```bash
git add apps/backend/app/db/models/user.py
git add apps/backend/alembic/versions/                 # the new migration
git add apps/backend/app/api/v1/users.py
git add apps/backend/app/api/v1/schemas/alerts.py
git add apps/backend/app/api/v1/alerts.py
git add apps/backend/app/alerts/
git add apps/backend/app/main.py
git add apps/backend/tests/api/test_tv_alerts.py
git add apps/backend/tests/alerts/test_throttle.py
git add docs/runbook/tv-webhooks.md

git commit -m "feat(alerts): TradingView Pine webhook receiver (P4 item 1)

- New endpoint POST /api/v1/alerts/tv accepts TV Pine alert webhooks
- Per-user secret stored in users.pine_webhook_secret (rotate via
  POST /api/v1/users/me/regenerate-webhook-secret)
- Body schema with extra='forbid', symbol uppercased, optional strategy_id
  ownership-checked, optional side ∈ {buy,sell,long,short,flat}
- In-process dedup: identical alerts within 5s return 200 with deduped=true
- In-process rate limit: 20 alerts/min per secret → 429
- Failed-auth IP throttle: 10 bad-secret POSTs/min from same IP → 429
- Inserts Signal row with type=PINE_ALERT, publishes signal.new on the bus
  so the existing WS layer surfaces it instantly
- Tests: 11 endpoint cases + 8 throttle unit cases
- docs/runbook/tv-webhooks.md covers Cloudflare tunnel setup, TV alert
  message template, and troubleshooting"

git push -u origin feat/p4-tv-pine-webhooks

gh pr create \
  --title "feat(alerts): TradingView Pine webhook receiver (P4 item 1)" \
  --body "P4 Item 1 — TV Pine alerts now route to signals. Closes the deferral noted in P2 §1 (signals.type reserved pine_alert with no handler). Single PR."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag -a p4-tv-webhooks-complete -m "P4: TV Pine webhook receiver"
git push origin p4-tv-webhooks-complete
```

- [ ] PR merged.
- [ ] Tag pushed.
- [ ] `todo.md` updated to mark P4 §1 ✅.

---

## Verification Checklist (full session)

- [ ] §1.1 Migration adds `users.pine_webhook_secret` with unique index; round-trips.
- [ ] §1.2 `POST /users/me/regenerate-webhook-secret` and `GET /users/me/webhook-secret` work.
- [ ] §1.3 Pydantic schemas reject extra fields, uppercase symbol, validate side enum.
- [ ] §1.4 Dedup window 5s, rate limit 20/min, failed-auth IP throttle 10/min.
- [ ] §1.5 Endpoint enforces auth → throttle → ownership → dedup → rate → persist → publish in that order.
- [ ] §1.6 19 tests pass (11 endpoint + 8 throttle).
- [ ] §1.7 Runbook covers tunnel setup, alert template, troubleshooting.
- [ ] §1.8 Curl smoke + (optional) real TV alert smoke green.
- [ ] §1.9 PR merged, tag pushed.

---

## Notes & Gotchas

1. **The secret is in the JSON body, not the URL path or a header.** TV's alert message body is fully user-customizable; URL paths are not always logged-clean by intermediaries; custom headers aren't supported on all TV plans. Body is the most portable.

2. **Dedup is in-memory and process-local.** A backend restart resets the dedup cache. Two simultaneous workers (none today, but if you add them in P5) would have independent caches — the same alert routed to two workers within 5s would create two signal rows. Fix when multi-worker becomes real.

3. **Rate limit is in-memory too.** Same caveat: per-worker. The "real" rate limiter would live behind a proper auth gateway (nginx, envoy, cloudflare). For MVP the in-process limiter is a useful guard against runaway TV alert loops, not a defense against deliberate attack.

4. **`is_duplicate_alert` ALWAYS updates the cache, even when returning True.** That means each identical alert resets the sliding window. If TV is repeatedly mis-firing once a second, we suppress every one of them. The opposite design (only-update-on-non-duplicate) would let them through every 5s. Per requirements, we want the former.

5. **Failed-auth IP throttle counts ALL bad-secret POSTs, not just sequential ones.** A bad actor probing 11 different secrets from one IP gets 429 on the 11th. This is generous; real production gateways are stricter.

6. **Symbol resolution rejects unknown tickers with 400.** A TV alert for `ZZZZZZ` doesn't silently disappear into the void — the trader sees the 400 in TV's alert log. If you legitimately need to receive alerts for symbols not in `symbols`, populate that table manually before configuring the alert.

7. **`strategy_id` binding doesn't auto-trigger the strategy's `on_signal` handler.** That's a P2 framework feature: a strategy's engine dispatches `on_signal` when a `signal.new` event fires for its strategy_id. If you bind a TV alert to a strategy and the engine is dispatching that strategy, `on_signal` fires. If the strategy is IDLE, the row is persisted but not handled.

8. **The `side` field accepts both buy/sell AND long/short.** TV alert authors use both vocabularies. We don't normalize — the value is passed through into `payload_json.side` as written. Strategies that consume this need to handle either form.

9. **Multi-line JSON bodies in TV alerts are fine.** TV preserves whitespace; the parser handles either pretty-printed or single-line. The runbook example is pretty-printed for readability.

10. **The `received_from_ip` field in payload_json is a forensic aid.** If a strange signal appears, you can see which IP delivered it. Cloudflare's `cf-connecting-ip` header is honored via `X-Forwarded-For` chain parsing.

11. **No retry-on-failure if the backend is down.** TV's webhooks are fire-and-forget. The runbook explicitly tells users to design for missed alerts. The right way to make alerts reliable is the queue-on-TV's-side, not retry-on-our-side.

12. **Pine *runtime* is not in scope.** This item routes signals; it does not execute Pine. A future item could compile Pine to Python (P7), but the simpler bridge — TV does the Pine work, sends us the signal — is what this item delivers.

13. **Don't bundle other P4 items into this PR.** §2 (async backtest), §3 (Opportunities page), etc. are separable. Tag and ship.

---

*End of P4 Item 1 v0.1.*
