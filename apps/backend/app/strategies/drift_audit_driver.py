"""§8 drift audit — deterministic driver for the LIVE ``MomentumDaily`` class.

Drives the ACTUAL live strategy (not a re-implementation) through a historical session
sequence with deterministic adapters that replace ONLY the external execution deps
(context state, broker/order, prices/bars, clock) — the decision logic (`_evaluate`,
`_regime`, `_eligible`, `_fired_triggers`, `_select_targets`) is the real code. Per session
it captures the decision seams into a :class:`SeamRecord` for `drift_audit.build_report`.

Fidelity notes:
  * scores come from the caller's ``scores_provider(day)`` — for the real run this is the
    production ``FactorAccessor.momentum_scores`` pinned to the historical day; for tests,
    a synthetic frame. The live class calls ``momentum_scores`` with NO ``as_of`` (uses the
    store's latest date), so the adapter pins the store to ``day``.
  * the execution book fills a submitted order at the NEXT session's reference price (the
    replica's next-open model), so holdings evolve identically GIVEN identical decisions;
    divergent decisions cause holdings to diverge (the report records first-mismatch +
    cumulative effect).
  * SPY is absent from the SEP store (findings doc), so the regime gauge is a market proxy;
    the caller feeds the SAME proxy series as the market symbol's bars so both sides use the
    identical regime input ("equivalent execution representation", §8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from app.strategies.drift_audit import SeamRecord

ScoresProvider = Callable[[date], "pd.DataFrame"]
BarsProvider = Callable[[str, date, int], "pd.DataFrame"]  # (symbol, as_of, n) -> daily bars


@dataclass
class _Pos:
    qty: Decimal
    side: str = "long"


@dataclass
class _OrderIntent:
    symbol: str
    side: str            # "buy" | "sell"
    qty: Decimal
    client_order_id: str | None
    reason: str


@dataclass
class DriftCtxAdapter:
    """A deterministic StrategyContext stand-in exposing exactly the surface the live
    ``MomentumDaily`` uses. State is in-memory; orders fill at the next session's price."""

    symbols: list[str]
    strategy_id: int
    scores_provider: ScoresProvider
    bars_provider: BarsProvider
    equity: Decimal = Decimal(100_000)
    sim_day: date = field(default_factory=lambda: date(2005, 1, 3))

    _state: dict[str, Any] = field(default_factory=dict)
    _positions: dict[str, Decimal] = field(default_factory=dict)
    _pending: list[_OrderIntent] = field(default_factory=list)
    _fills: list[dict] = field(default_factory=list)
    submitted_today: list[_OrderIntent] = field(default_factory=list)
    signals_today: list[dict] = field(default_factory=list)
    _fill_seq: int = 0

    # ---- factors (pinned to sim_day) ----
    @property
    def factors(self) -> _FactorsProxy:
        return _FactorsProxy(self)

    # ---- positions / equity ----
    async def get_position_for(self, symbol: str) -> _Pos | None:
        q = self._positions.get(symbol.upper())
        return _Pos(qty=q) if q is not None and q > 0 else None

    async def get_account_equity(self) -> Decimal | None:
        return self.equity

    async def pending_buy_qty(self) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for o in self._pending:
            if o.side == "buy":
                out[o.symbol.upper()] = out.get(o.symbol.upper(), Decimal(0)) + o.qty
        return out

    async def get_recent_bars(self, symbol: str, timeframe: str, n: int = 100) -> pd.DataFrame:
        return self.bars_provider(symbol.upper(), self.sim_day, n)

    # ---- orders ----
    async def submit_order(self, order_request: Any) -> Any:
        side = getattr(getattr(order_request, "side", None), "value", None) or str(
            getattr(order_request, "side", "buy")).lower()
        sym = str(getattr(order_request, "symbol_ticker", None)
                  or getattr(order_request, "symbol", "")).upper()
        qty = Decimal(str(getattr(order_request, "qty", 0) or 0))
        coid = getattr(order_request, "client_order_id", None)
        intent = _OrderIntent(symbol=sym, side=("sell" if "sell" in side.lower() else "buy"),
                              qty=qty, client_order_id=coid, reason="")
        self._pending.append(intent)
        self.submitted_today.append(intent)

        class _Ack:
            rejection_reason = None
            id = 0
        return _Ack()

    async def open_orders(self, *, client_order_id_prefix: str | None = None) -> list[Any]:
        out = []
        for o in self._pending:
            if client_order_id_prefix and not (o.client_order_id or "").startswith(
                    client_order_id_prefix):
                continue
            out.append(_OpenOrderObs(symbol=o.symbol, side=o.side, qty=o.qty,
                                     client_order_id=o.client_order_id))
        return out

    async def recent_fills(self, *, since: Any = None, after_fill_id: int | None = None,
                           client_order_id_prefix: str | None = None) -> list[Any]:
        out = []
        for f in self._fills:
            if after_fill_id is not None and f["fill_id"] <= after_fill_id:
                continue
            if client_order_id_prefix and not (f["client_order_id"] or "").startswith(
                    client_order_id_prefix):
                continue
            out.append(_FillObs(**f))
        return out

    # ---- signals ----
    async def log_signal(self, symbol: str, signal_type: Any, payload: dict | None = None) -> int:
        self.signals_today.append({"symbol": symbol, "type": str(signal_type),
                                   "payload": payload or {}})
        return len(self.signals_today)

    # ---- durable state (dict-backed CAS mirroring the real _rev contract) ----
    async def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    async def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    async def clear_state(self, key: str) -> None:
        self._state.pop(key, None)

    async def compare_and_set_state(self, key: str, *, expected_rev: int | None,
                                    new_value: dict) -> bool:
        cur = self._state.get(key)
        cur_rev = cur.get("_rev") if isinstance(cur, dict) else None
        if expected_rev is None:
            if cur is not None:
                return False
        elif cur_rev != expected_rev:
            return False
        self._state[key] = new_value
        return True

    # ---- execution: advance to the next session, filling pending orders ----
    def settle(self, fill_prices: dict[str, float]) -> None:
        """Fill all pending orders at ``fill_prices`` (next-session reference price) and
        update holdings + equity. A BUY adds qty; a SELL removes it. Records fills so the
        strategy's seed reconciliation (``recent_fills``) sees them."""
        for o in self._pending:
            px = fill_prices.get(o.symbol.upper())
            if px is None:
                continue
            self._fill_seq += 1
            signed = o.qty if o.side == "buy" else -o.qty
            self._positions[o.symbol.upper()] = self._positions.get(o.symbol.upper(),
                                                                    Decimal(0)) + signed
            if self._positions[o.symbol.upper()] <= 0:
                self._positions.pop(o.symbol.upper(), None)
            self._fills.append({
                "fill_id": self._fill_seq, "order_id": None, "symbol": o.symbol.upper(),
                "side": o.side, "qty": o.qty, "price": Decimal(str(px)),
                "client_order_id": o.client_order_id,
                "filled_at": datetime.now(UTC),
            })
        self._pending.clear()


@dataclass
class _FactorsProxy:
    _adapter: DriftCtxAdapter

    def momentum_scores(self, as_of: date | None = None, *, n: int = 500,
                        lookback_days: int = 252, skip_days: int = 21) -> pd.DataFrame:
        # Live calls with no as_of → pinned to the adapter's sim_day.
        return self._adapter.scores_provider(as_of or self._adapter.sim_day)


@dataclass
class _OpenOrderObs:
    symbol: str
    side: str
    qty: Decimal
    client_order_id: str | None


@dataclass
class _FillObs:
    fill_id: int
    order_id: str | None
    symbol: str
    side: str
    qty: Decimal
    price: Decimal
    client_order_id: str | None
    filled_at: datetime


def capture_seam(strategy: Any, adapter: DriftCtxAdapter, day: date) -> SeamRecord:
    """Compute the day's SeamRecord from the strategy's (already-run) decision state +
    pure re-invocation of the deterministic selection seams. Call AFTER ``_evaluate``."""
    scores = adapter.scores_provider(day)
    eligible = strategy._eligible(scores)
    ranking = tuple(str(t) for t in eligible.index)
    held = {k: v for k, v in adapter._positions.items() if v > 0}
    targets = tuple(strategy._select_targets(scores, held))
    gross = float(getattr(strategy, "_regime_gross", 0.0) or 0.0)
    weights: dict[str, float] = {}
    if targets:
        w = min(1.0 / len(targets), float(strategy.params.get("max_position_pct", 0.20))) * gross
        weights = {t: w for t in targets}
    reasons = [s["payload"].get("reason", "") for s in adapter.signals_today]
    is_seed = any("seed" in r for r in reasons)
    trade = bool(adapter.submitted_today) or is_seed
    trigger = "+".join(r for r in reasons if r) or "reviewed_no_trigger"
    return SeamRecord(
        date=day.isoformat(),
        scores={str(t): float(v) for t, v in scores["score"].items()} if "score" in scores else {},
        eligible=ranking, ranking=ranking, target_names=targets, weights=weights,
        regime_gross=gross, trade_initiated=trade, trigger=trigger, is_seed=is_seed)


async def drive_live(strategy: Any, adapter: DriftCtxAdapter, trading_days: list[date], *,
                     fill_price_fn: Callable[[str, date], float | None],
                     eval_symbol: str = "__eval__") -> list[SeamRecord]:
    """Drive the live class across ``trading_days``, capturing a SeamRecord per session.

    Matches the replica's SAME-DAY-close rebalance: a session's orders settle at that
    session's ``fill_price_fn`` price right after ``on_bar``, so the next session's seed
    reconciliation (via ``recent_fills``) sees the fills and the holdings evolve identically
    to the replica given identical decisions. The seam is captured BEFORE settling (the
    decision was made against the holdings known at decision time).
    """
    from app.strategies.context import Bar

    records: list[SeamRecord] = []
    for day in trading_days:
        adapter.sim_day = day
        adapter.submitted_today = []
        adapter.signals_today = []
        ts = datetime(day.year, day.month, day.day, 21, 10, tzinfo=UTC)
        await strategy.on_bar(Bar(symbol=eval_symbol, timeframe="1Day", t=ts,
                                  o=1, h=1, l=1, c=1, v=1))
        records.append(capture_seam(strategy, adapter, day))
        fills = {o.symbol: fill_price_fn(o.symbol, day) for o in adapter._pending}
        adapter.settle({k: v for k, v in fills.items() if v is not None})
    return records


# ---- replica (Stage 4 variant C) seam extractor ----

class _ReplicaDayScores:
    """Duck-typed DayScores: ``ranked`` (best-first), ``score`` (dict), ``rank`` (dict)."""
    ranked: list[str]
    score: dict[str, float]
    rank: dict[str, int]


SelectFn = Callable[[Any, set[str], "dict[str, int] | None"], "list[str]"]
WeighFn = Callable[["list[str]", date], "dict[str, float]"]
PriceFn = Callable[[str, date], "float | None"]


def capture_replica_seams(
    trading_days: list[date], day_scores: dict[date, Any], gross: dict[date, float], *,
    select_fn: SelectFn, weigh_fn: WeighFn, price_fn: PriceFn,
    backstop_days: int, weight_drift_pct: float, turnover_cost_bps: float,
    initial_equity: float,
) -> list[SeamRecord]:
    """A faithful transcription of Stage 4 ``simulate`` (backtest_momentum_stage4.py lines
    176-238) that additionally emits a SeamRecord per session. The mark-to-market, trade
    gate (``changed or regime_flip or drift or since>=BACKSTOP_DAYS``), turnover cost, and
    same-day-close rebalance are reproduced exactly; ``select_fn``/``weigh_fn``/``price_fn``
    are the validated ``select_n``/``weigh``/store-price functions (injected so the loop is
    testable without the full store). Weights are captured as the gross-scaled targets."""
    equity = initial_equity
    sleeves: dict[str, float] = {}
    cash = 0.0
    target_w: dict[str, float] = {}
    last_px: dict[str, float] = {}
    held: set[str] = set()
    since = 0
    prev_rank: dict[str, int] | None = None
    applied_gross = 1.0
    records: list[SeamRecord] = []

    for d in trading_days:
        if held:                                        # mark-to-market (simulate 177-188)
            for tk in list(held):
                p = price_fn(tk, d)
                if p is not None:
                    lp = last_px.get(tk, 0.0)
                    if lp > 0:
                        sleeves[tk] *= 1.0 + (p / lp - 1.0)
                    last_px[tk] = p
            equity = sum(sleeves.values()) + cash
        g = gross.get(d, 1.0)
        ds = day_scores.get(d)
        if ds is None:                                  # thin day: no decision
            since += 1
            records.append(SeamRecord(date=d.isoformat(), scores={}, eligible=(), ranking=(),
                                      target_names=(), weights={}, regime_gross=g,
                                      trade_initiated=False, trigger="no_scores"))
            continue

        target = select_fn(ds, held, prev_rank)
        prev_rank = ds.rank
        changed = set(target) != held
        regime_flip = abs(g - applied_gross) > 1e-9
        drift = bool(held and equity > 0 and target_w and max(
            abs(sleeves.get(tk, 0.0) / equity - target_w.get(tk, 0.0)) for tk in held)
            > weight_drift_pct)
        backstop = since >= backstop_days
        trade = bool(changed or regime_flip or drift or backstop)

        base = weigh_fn(target, d) if (g > 0.0 and target) else {}
        neww = {tk: w * g for tk, w in base.items()}
        trig = "+".join(t for t, on in (("changed", changed), ("regime_flip", regime_flip),
                        ("drift", drift), ("backstop", backstop)) if on) or "reviewed_no_trigger"
        records.append(SeamRecord(
            date=d.isoformat(), scores=dict(ds.score),
            eligible=tuple(ds.ranked), ranking=tuple(ds.ranked),
            target_names=tuple(target), weights=neww, regime_gross=g,
            trade_initiated=trade, trigger=trig))

        if not trade:
            since += 1
            continue
        cash_w = 1.0 - sum(neww.values())
        curw = {tk: (sleeves.get(tk, 0.0) / equity if equity > 0 else 0.0)
                for tk in set(sleeves) | set(neww)}
        cur_cash_w = cash / equity if equity > 0 else 0.0
        turnover = 0.5 * (sum(abs(neww.get(k, 0.0) - curw.get(k, 0.0))
                          for k in set(neww) | set(curw)) + abs(cash_w - cur_cash_w))
        equity *= 1.0 - (turnover_cost_bps / 1e4) * turnover
        sleeves = {tk: w * equity for tk, w in neww.items()}
        cash = cash_w * equity
        last_px = {tk: (price_fn(tk, d) or 0.0) for tk in neww}
        target_w = dict(neww)
        held = set(neww)
        applied_gross = g
        since = 0
    return records


__all__ = [
    "BarsProvider",
    "DriftCtxAdapter",
    "PriceFn",
    "ScoresProvider",
    "SelectFn",
    "WeighFn",
    "capture_replica_seams",
    "capture_seam",
    "drive_live",
]
