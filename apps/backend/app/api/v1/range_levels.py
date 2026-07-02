"""GET /api/v1/range-levels — live buy/sell/stop levels per range symbol.

Monitoring feed for the Range Trader: shows the strategy's ACTUAL published levels
(the ``range_levels`` INFO signal the strategy emits once per ET day) enriched with
the current price and the held position, so a trigger that should have fired but
didn't is visible at a glance. Read-only, per-user.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.range_levels import RangeLevelRow, RangeLevelsResponse
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import ACTIVE_STRATEGY_STATUSES
from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.session import get_session

router = APIRouter(prefix="/range-levels", tags=["range-levels"])


def _status(
    buy: float | None, sell: float | None, stop: float | None,
    cur: float | None, qty: float,
) -> str:
    if qty and qty > 0:
        return "holding"
    if buy is None or sell is None:
        return "forming"  # opening range still building (or no levels yet)
    if cur is None:
        return "levels_set"
    if stop and cur <= stop:
        return "below_stop"
    if cur <= buy:
        return "at_buy"   # flat and at/under the buy level — watch for an entry
    if cur >= sell:
        return "at_sell"
    return "in_range"


@router.get("", response_model=RangeLevelsResponse)
async def get_range_levels(
    request: Request,
    strategy_id: int | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RangeLevelsResponse:
    now = datetime.now(UTC)

    # Resolve the strategy: explicit id (ownership-checked) or the user's active one.
    if strategy_id is not None:
        strat = await session.get(Strategy, strategy_id)
        if strat is None or strat.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Strategy not found")
    else:
        strat = (
            await session.execute(
                select(Strategy)
                .where(
                    Strategy.user_id == current_user.id,
                    Strategy.status.in_(list(ACTIVE_STRATEGY_STATUSES)),
                )
                .order_by(Strategy.id)
            )
        ).scalars().first()
    if strat is None:
        return RangeLevelsResponse(strategy_id=None, strategy_name=None, as_of=now, rows=[])

    symbols = [s.upper() for s in (strat.symbols_json or [])]
    sym_rows = (
        await session.execute(select(Symbol).where(Symbol.ticker.in_(symbols)))
    ).scalars().all() if symbols else []
    id_by_ticker = {s.ticker: s.id for s in sym_rows}
    ticker_by_id = {s.id: s.ticker for s in sym_rows}

    # Latest range_levels signal per symbol (last 2 days covers "today" across tz).
    since = now - timedelta(days=2)
    sigs = (
        await session.execute(
            select(Signal)
            .where(Signal.strategy_id == strat.id, Signal.received_at >= since)
            .order_by(Signal.received_at.desc())
        )
    ).scalars().all()
    latest: dict[str, tuple[dict, datetime]] = {}
    for sg in sigs:
        payload = sg.payload_json or {}
        if payload.get("kind") != "range_levels":
            continue
        tk = ticker_by_id.get(sg.symbol_id)
        if tk and tk not in latest:
            latest[tk] = (payload, sg.received_at)

    # Held quantity per symbol (local positions table).
    acct = (
        await session.execute(
            select(Account).where(
                Account.user_id == current_user.id, Account.mode == AccountMode.paper
            )
        )
    ).scalars().first()
    qty_by_ticker: dict[str, float] = {}
    if acct is not None:
        for p in (
            await session.execute(select(Position).where(Position.account_id == acct.id))
        ).scalars().all():
            tk = ticker_by_id.get(p.symbol_id)
            if tk:
                qty_by_ticker[tk] = float(p.qty)

    # Current price from the bar cache (best-effort; None on any miss).
    bar_cache = getattr(request.app.state, "bar_cache", None)

    async def _price(sym: str) -> float | None:
        if bar_cache is None:
            return None
        try:
            df = await bar_cache.get_bars(sym, "1Min", now - timedelta(days=1), now)
            return float(df.iloc[-1]["c"]) if len(df) else None
        except Exception:  # noqa: BLE001 — price is best-effort
            return None

    rows: list[RangeLevelRow] = []
    for tk in symbols:
        sig = latest.get(tk)
        lv: dict | None = sig[0] if sig else None
        at: datetime | None = sig[1] if sig else None
        buy = float(lv["buy"]) if lv else None
        sell = float(lv["sell"]) if lv else None
        stop = float(lv["stop"]) if lv else None
        qty = qty_by_ticker.get(tk, 0.0)
        cur = await _price(tk) if tk in id_by_ticker else None
        rows.append(
            RangeLevelRow(
                symbol=tk,
                buy=buy,
                sell=sell,
                stop=stop,
                current_price=cur,
                position_qty=qty,
                status=_status(buy, sell, stop, cur, qty),
                levels_at=at,
            )
        )
    return RangeLevelsResponse(
        strategy_id=strat.id, strategy_name=strat.name, as_of=now, rows=rows
    )
