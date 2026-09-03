"""GET /api/v1/range-levels — live buy/sell/stop levels per range symbol.

Monitoring feed for the Range Trader. Everyday rule (2026-07-27): after the
opening-range window closes, the UI must show **today's** ET levels.

Prefer the strategy's published ``range_levels`` INFO signal for today ET.
If that signal is missing (cold start / restore / missed OR window), compute
the same formula from 1Min bars so the panel is never blank mid-session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

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
from app.services.range_opening_levels import (
    compute_opening_levels_from_cache,
    params_or_defaults,
)

ET = ZoneInfo("America/New_York")

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


def _is_today_et(ts: datetime) -> bool:
    return ts.astimezone(ET).date() == datetime.now(ET).date()


@router.get("", response_model=RangeLevelsResponse)
async def get_range_levels(
    request: Request,
    strategy_id: int | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RangeLevelsResponse:
    now = datetime.now(UTC)
    today_et = datetime.now(ET).date()

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

    # Prefer today's ET range_levels signal; keep a 2-day lookback for receipt order.
    since = now - timedelta(days=2)
    sigs = (
        await session.execute(
            select(Signal)
            .where(Signal.strategy_id == strat.id, Signal.received_at >= since)
            .order_by(Signal.received_at.desc())
        )
    ).scalars().all()
    latest_today: dict[str, tuple[dict, datetime]] = {}
    for sg in sigs:
        payload = sg.payload_json or {}
        if payload.get("kind") != "range_levels":
            continue
        if not _is_today_et(sg.received_at):
            continue
        tk = ticker_by_id.get(sg.symbol_id)
        if tk and tk not in latest_today:
            latest_today[tk] = (payload, sg.received_at)

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
    or_minutes, stop_buf = params_or_defaults(strat.params_json)

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
        sig = latest_today.get(tk)
        buy: float | None = None
        sell: float | None = None
        stop: float | None = None
        at: datetime | None = None
        if sig is not None:
            lv, at = sig
            buy = float(lv["buy"]) if lv.get("buy") is not None else None
            sell = float(lv["sell"]) if lv.get("sell") is not None else None
            stop = float(lv["stop"]) if lv.get("stop") is not None else None
        elif bar_cache is not None and (strat.params_json or {}).get(
            "level_mode", "opening_range"
        ) == "opening_range":
            # Everyday rule: after OR closes, fill the UI from bars when no signal.
            computed = await compute_opening_levels_from_cache(
                bar_cache,
                tk,
                day=today_et,
                opening_range_minutes=or_minutes,
                stop_buffer_pct=stop_buf,
            )
            if computed is not None:
                buy, sell, stop = computed
                at = now
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
