"""``POST /api/v1/alerts/tv`` — TradingView Pine alert receiver.

Order of operations:

1. Pre-flight IP throttle — bad-actor probes never reach the DB.
2. Resolve user by ``secret``. Wrong secret → 401.
3. Per-secret rate limit. Over → 429.
4. Resolve ``symbol`` ticker → ``symbols`` row. Unknown → 400.
5. If ``strategy_id`` given, verify the secret's user owns it. Mismatch → 404.
6. Dedup check (5s window on user × symbol × side × strategy_id × payload).
   Duplicate → 200 with ``deduped=true``, no row written.
7. Insert ``Signal`` with ``type=PINE_ALERT``; commit.
8. Publish ``signal.new`` on the bus so the WS layer surfaces it.
9. Return 200 with the new ``signal_id``.

The secret in the body IS the auth — no ``Depends(get_current_user)`` here;
the stub auth would short-circuit to user 1 regardless of which secret was
sent.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.throttle import (
    is_auth_attempt_rate_limited,
    is_duplicate_alert,
    is_rate_limited,
    record_auth_failure,
)
from app.api.v1.schemas.alerts import TVWebhookAcceptedResponse, TVWebhookRequest
from app.db.enums import SignalType
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.events import get_event_bus
from app.security import CredentialKind, CredentialStore

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Tunnels (Cloudflare, etc.) put the real client
    in X-Forwarded-For; trust the first value when present."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _authenticate_webhook(presented_secret: str, session: AsyncSession) -> User | None:
    """Resolve which user a Pine webhook belongs to (P5 §4).

    The Pine webhook secret moved into the encrypted credential store, so we
    decrypt each active user's stored secret and compare in constant time.
    O(users) decrypts per webhook — fine for the single-tenant MVP; a
    SHA-256 lookup column is the optimization if multi-user scale grows
    (out of scope for §4; see session doc Notes & Gotchas #7).
    """
    store = CredentialStore(session)
    users = (await session.execute(select(User))).scalars().all()
    for user in users:
        stored = await store.get(user.id, CredentialKind.PINE_WEBHOOK_SECRET)
        if stored is None:
            continue
        if hmac.compare_digest(stored, presented_secret):
            return user
    return None


@router.post("/tv", response_model=TVWebhookAcceptedResponse)
async def receive_tv_alert(
    body: TVWebhookRequest,
    request: Request,
) -> TVWebhookAcceptedResponse:
    client_ip = _client_ip(request)

    if is_auth_attempt_rate_limited(client_ip=client_ip):
        logger.warning("tv_alert_ip_rate_limited", ip=client_ip)
        raise HTTPException(status_code=429, detail="Too many requests")

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        user = await _authenticate_webhook(body.secret, session)

        if user is None:
            record_auth_failure(client_ip=client_ip)
            logger.warning("tv_alert_bad_secret", ip=client_ip)
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        if is_rate_limited(secret=body.secret):
            logger.warning(
                "tv_alert_user_rate_limited", user_id=user.id, ip=client_ip
            )
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        symbol_row = (
            await session.execute(
                select(Symbol).where(Symbol.ticker == body.symbol)
            )
        ).scalars().first()
        if symbol_row is None:
            logger.info(
                "tv_alert_unknown_symbol", user_id=user.id, ticker=body.symbol
            )
            raise HTTPException(
                status_code=400, detail=f"Unknown symbol: {body.symbol}"
            )

        if body.strategy_id is not None:
            strat = await session.get(StrategyRow, body.strategy_id)
            if strat is None or strat.user_id != user.id:
                logger.warning(
                    "tv_alert_strategy_ownership_mismatch",
                    user_id=user.id,
                    strategy_id=body.strategy_id,
                )
                raise HTTPException(status_code=404, detail="Strategy not found")

        if is_duplicate_alert(
            user_id=user.id,
            symbol=body.symbol,
            side=body.side,
            strategy_id=body.strategy_id,
            payload=body.payload,
        ):
            logger.info(
                "tv_alert_deduped",
                user_id=user.id,
                symbol=body.symbol,
                side=body.side,
            )
            return TVWebhookAcceptedResponse(
                signal_id=None,
                deduped=True,
                received_at=datetime.now(UTC).isoformat(),
            )

        merged_payload = dict(body.payload)
        if body.side is not None:
            merged_payload["side"] = body.side
        merged_payload["source"] = "tradingview"
        merged_payload["received_from_ip"] = client_ip

        signal = Signal(
            user_id=user.id,
            strategy_id=body.strategy_id,
            symbol_id=symbol_row.id,
            type=SignalType.PINE_ALERT,
            payload_json=merged_payload,
            received_at=datetime.now(UTC),
        )
        session.add(signal)
        await session.commit()
        await session.refresh(signal)
        signal_id = signal.id

    bus = get_event_bus()
    try:
        await bus.publish(
            "signal.new",
            {
                "signal_id": signal_id,
                "strategy_id": body.strategy_id,
                "symbol": body.symbol,
                "type": SignalType.PINE_ALERT.value,
                "payload": merged_payload,
                "received_at": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:
        logger.exception("tv_alert_bus_publish_failed", signal_id=signal_id)

    logger.info(
        "tv_alert_accepted",
        user_id=user.id,
        signal_id=signal_id,
        symbol=body.symbol,
        side=body.side,
        strategy_id=body.strategy_id,
    )

    return TVWebhookAcceptedResponse(
        signal_id=signal_id,
        deduped=False,
        received_at=datetime.now(UTC).isoformat(),
    )
