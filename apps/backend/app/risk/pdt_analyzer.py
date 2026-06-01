"""Pattern Day Trader detection (P5 §5).

FINRA defines a Pattern Day Trader as one who executes 4+ day trades in a
rolling 5-business-day period in a margin account with equity < $25,000. A
"day trade" is opening and closing the same position (same symbol) within the
same trading session.

The workbench surfaces a WARNING (it does not block) when:
  - 3+ day trades in the rolling 5-business-day window (we warn one early), AND
  - account equity < $25,000 (or unknown).

Drift notes vs the v0.2 doc (reconciled against live schema):
  - Order has symbol_id (FK), not a `symbol` string; we join Symbol for the
    ticker used in grouping + the detected-day-trade payload.
  - Equity is read from the broker adapter's sync get_account() dict.
  - SQLEnum binds the enum NAME; OrderSide comparisons use enum members.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OrderSide
from app.db.models.account import Account
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.utils.time import ensure_aware

logger = structlog.get_logger(__name__)


PDT_EQUITY_THRESHOLD = Decimal("25000.00")
PDT_DAY_TRADE_THRESHOLD = 3  # we warn at 3 — FINRA's trigger is 4
PDT_WINDOW_BUSINESS_DAYS = 5


@dataclass
class PdtStatus:
    account_id: int
    is_at_risk: bool
    day_trade_count: int
    threshold: int
    window_days: int
    account_equity: Decimal | None
    equity_threshold: Decimal
    detected_day_trades: list[dict[str, Any]]


class PdtAnalyzer:
    def __init__(self, *, session: AsyncSession, broker_registry: Any = None) -> None:
        self._session = session
        self._broker_registry = broker_registry

    async def compute(self, account_id: int) -> PdtStatus:
        account = await self._session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")

        cutoff = self._business_days_ago(PDT_WINDOW_BUSINESS_DAYS)
        rows = (
            await self._session.execute(
                select(Fill, Order.side, Symbol.ticker)
                .join(Order, Fill.order_id == Order.id)
                .join(Symbol, Order.symbol_id == Symbol.id)
                .where(Order.account_id == account_id)
                .where(Fill.filled_at >= cutoff)
                .order_by(Fill.filled_at)
            )
        ).all()

        day_trades = self._identify_day_trades(rows)
        equity = await self._fetch_equity(account)

        is_at_risk = len(day_trades) >= PDT_DAY_TRADE_THRESHOLD and (
            equity is None or equity < PDT_EQUITY_THRESHOLD
        )

        return PdtStatus(
            account_id=account_id,
            is_at_risk=is_at_risk,
            day_trade_count=len(day_trades),
            threshold=PDT_DAY_TRADE_THRESHOLD,
            window_days=PDT_WINDOW_BUSINESS_DAYS,
            account_equity=equity,
            equity_threshold=PDT_EQUITY_THRESHOLD,
            detected_day_trades=day_trades,
        )

    def _identify_day_trades(self, fill_rows: Sequence[Any]) -> list[dict[str, Any]]:
        """Walk fills in time order; track per-symbol per-day position state.
        Emit a day trade when position goes 0 → non-zero → 0 within one day.
        Position-walk (not pair-counting) handles partial fills correctly."""
        per_day_per_symbol: dict[
            tuple[date, str], list[tuple[datetime, OrderSide, Decimal]]
        ] = defaultdict(list)
        for fill, side, ticker in fill_rows:
            eastern_date = self._utc_to_eastern_date(fill.filled_at)
            per_day_per_symbol[(eastern_date, ticker)].append(
                (fill.filled_at, side, fill.qty)
            )

        day_trades: list[dict[str, Any]] = []
        for (eastern_date, ticker), events in per_day_per_symbol.items():
            position = Decimal("0")
            opened_at: datetime | None = None
            for ts, side, qty in events:
                signed = qty if side == OrderSide.BUY else -qty
                prev = position
                position += signed
                if prev == 0 and position != 0:
                    opened_at = ts
                elif prev != 0 and position == 0 and opened_at is not None:
                    oa = ensure_aware(opened_at)
                    cl = ensure_aware(ts)
                    day_trades.append(
                        {
                            "date": eastern_date.isoformat(),
                            "symbol": ticker,
                            "opened_at": oa.isoformat() if oa else None,
                            "closed_at": cl.isoformat() if cl else None,
                        }
                    )
                    opened_at = None
        return day_trades

    async def _fetch_equity(self, account: Account) -> Decimal | None:
        if self._broker_registry is None:
            return None
        adapter = self._broker_registry.get(account.id)
        if adapter is None:
            return None
        try:
            # Sync adapter call (Session 2 v1.0: BrokerAdapter is sync, dict return).
            snapshot = adapter.get_account()
            eq = snapshot.get("equity") if isinstance(snapshot, dict) else None
            return Decimal(str(eq)) if eq is not None else None
        except Exception:
            logger.exception("pdt_equity_fetch_failed", account_id=account.id)
            return None

    def _business_days_ago(self, n: int) -> datetime:
        d = datetime.now(UTC)
        days_back = 0
        while days_back < n:
            d = d - timedelta(days=1)
            if d.weekday() < 5:
                days_back += 1
        return d

    def _utc_to_eastern_date(self, ts: datetime) -> date:
        aware = ensure_aware(ts)
        assert aware is not None  # fills always carry a timestamp
        eastern = aware - timedelta(hours=5)
        return eastern.date()
