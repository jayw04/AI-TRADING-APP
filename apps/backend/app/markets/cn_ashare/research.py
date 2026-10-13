"""A-share strategy candidates and a descriptive daily-bar research run. RESEARCH-ONLY.

The run is a plumbing check of the whole chain (stored raw data -> reproducible adjustment ->
signal -> simulated A-share execution constraints -> report). Every result is labelled
``NON_INFERENTIAL_DESCRIPTIVE`` together with its sample label: a 20-stock, one-year sample says
nothing about whether a strategy works.

Accounting conventions (repeated in the report):

* Signals use back-adjusted (HFQ) closes up to and including the decision day; orders fill at the
  next trading day's raw open through ``execution.execute`` or are refused with a reason.
* Holdings are marked at the raw close. On a day the stock does not trade, the last traded close
  is carried; no price is invented for the missing day.
* A corporate action (factor change) is credited as cash equal to the drop from the previous close
  to the ex-rights reference price. Exact for a cash dividend before tax; an approximation for
  bonus shares and rights issues. Dividend tax is not modelled.
* A position still held when its stock stops trading for good (delisted) cannot be sold; it is
  valued at zero in the net result and its last-close value is reported separately.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from app.markets.cn_ashare import SCOPE, context, rules
from app.markets.cn_ashare.adjust import FactorGap, hfq
from app.markets.cn_ashare.execution import DailyBar, Fill, Order, Position, apply_fill, execute
from app.markets.cn_ashare.symbols import SymbolError, parse
from app.markets.context import PriceBasis

DESCRIPTIVE = "NON_INFERENTIAL_DESCRIPTIVE"
TRADING_DAYS_PER_YEAR = 242  # approximate SSE/SZSE trading days per year, for annualizing only


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    name: str
    hypothesis: str
    signal: str
    lookback_days: int
    direction: str  # "high" picks the largest lookback return, "low" the smallest
    top_k: int
    rebalance: str
    status: str = "CANDIDATE"


CANDIDATES: dict[str, Candidate] = {
    c.candidate_id: c
    for c in (
        Candidate(
            candidate_id="CN-MOM-20D",
            name="20-day momentum, monthly",
            hypothesis="Main-board stocks with the strongest 20-day adjusted return keep outperforming over the next month.",
            signal="HFQ close-to-close return over 20 trading days",
            lookback_days=20,
            direction="high",
            top_k=5,
            rebalance="last trading day of each month; fill at the next open",
        ),
        Candidate(
            candidate_id="CN-REV-5D",
            name="5-day reversal, monthly",
            hypothesis="Main-board stocks with the weakest 5-day adjusted return rebound over the next month.",
            signal="HFQ close-to-close return over 5 trading days",
            lookback_days=5,
            direction="low",
            top_k=5,
            rebalance="last trading day of each month; fill at the next open",
        ),
    )
}


def _month_ends(days: list[date]) -> list[date]:
    return [d for i, d in enumerate(days) if i + 1 == len(days) or days[i + 1].month != d.month]


def _bar(r: dict[str, Any]) -> DailyBar:
    return DailyBar(
        symbol=r["symbol"],
        trade_date=r["trade_date"],
        open=r["open"],
        high=r["high"],
        low=r["low"],
        close=r["close"],
        pre_close=r["pre_close"],
        volume_shares=r["volume_shares"] or 0.0,
        amount_cny=r["amount_cny"] or 0.0,
        trade_status=r["trade_status"],
        is_st=r["is_st"],
    )


def run_descriptive(
    candidate_id: str,
    *,
    provider: str,
    open_days: list[date],
    daily: list[dict[str, Any]],
    factors: list[dict[str, Any]],
    securities: list[dict[str, Any]],
    sample_label: str,
    capital_cny: float = 1_000_000.0,
    commission: rules.CommissionAssumption | None = None,
) -> dict[str, Any]:
    cand = CANDIDATES[candidate_id]
    commission = commission or rules.CommissionAssumption()
    days = sorted(open_days)
    bars: dict[str, dict[date, dict[str, Any]]] = {}
    for r in daily:
        bars.setdefault(r["symbol"], {})[r["trade_date"]] = r
    fac: dict[str, list[dict[str, Any]]] = {}
    for r in factors:
        fac.setdefault(r["symbol"], []).append(r)
    listed = {s["symbol"]: s["list_date"] for s in securities}
    delisted = {s["symbol"]: s["delist_date"] for s in securities if s["delist_date"]}

    excluded: dict[str, str] = {}
    signal_close: dict[str, dict[date, float]] = {}
    for sym in sorted(bars):
        try:
            rules.require_in_scope(parse(sym))
        except (rules.RuleNotConfigured, SymbolError) as exc:
            excluded[sym] = f"out of scope: {exc}"
            continue
        try:
            s = hfq(sym, bars[sym].values(), fac.get(sym, []))
        except FactorGap as exc:
            excluded[sym] = f"no adjustment factor: {exc}"
            continue
        signal_close[sym] = dict(zip(s.dates, s.close, strict=True))

    def lookback_return(sym: str, day: date) -> float | None:
        traded = sorted(d for d in signal_close[sym] if d <= day)
        if not traded or traded[-1] != day or len(traded) <= cand.lookback_days:
            return None
        return signal_close[sym][day] / signal_close[sym][traded[-1 - cand.lookback_days]] - 1.0

    def next_open_day(day: date) -> date | None:
        i = bisect_right(days, day)
        return days[i] if i < len(days) else None

    def listing_age(sym: str, day: date) -> int | None:
        ld = listed.get(sym)
        if ld is None or not days or ld < days[0]:
            return None
        return sum(1 for d in days if ld <= d < day)

    cash = capital_cny
    positions: dict[str, Position] = {}
    last_close: dict[str, float] = {}
    fills: list[Fill] = []
    refusals: Counter[str] = Counter()
    refusal_examples: list[dict[str, Any]] = []
    fees_total = 0.0
    dividends = 0.0
    resized = 0
    equity_curve: list[tuple[date, float]] = []
    pending: list[Order] = []
    rebalance_days = set(_month_ends(days))

    for day in days:
        # 1. fills decided on the previous trading day, sells before buys
        for order in sorted(pending, key=lambda o: (o.side != "sell", o.symbol)):
            nb = bars.get(order.symbol, {}).get(day)
            res = execute(
                order,
                _bar(nb) if nb else None,
                day,
                position=positions.get(order.symbol),
                trading_days_since_listing=listing_age(order.symbol, day),
                commission=commission,
            )
            if (
                isinstance(res, Fill)
                and res.order.side == "buy"
                and res.notional_cny + res.fees.total > cash
            ):
                # The open moved against the decision-day close: buy the lots the cash still covers.
                fit = int(cash / (res.price * (1 + 0.001)) / rules.LOT_SIZE) * rules.LOT_SIZE
                if fit <= 0:
                    refusals["INSUFFICIENT_CASH"] += 1
                    continue
                resized += 1
                order = Order(order.symbol, "buy", fit, order.decision_day)
                res = execute(
                    order,
                    _bar(nb) if nb else None,
                    day,
                    position=positions.get(order.symbol),
                    trading_days_since_listing=listing_age(order.symbol, day),
                    commission=commission,
                )
                if isinstance(res, Fill) and res.notional_cny + res.fees.total > cash:
                    refusals["INSUFFICIENT_CASH"] += 1
                    continue
            if isinstance(res, Fill):
                fills.append(res)
                fees_total += res.fees.total
                cash += (-1 if res.order.side == "buy" else 1) * res.notional_cny - res.fees.total
                apply_fill(positions, res)
            else:
                refusals[res.reason] += 1
                if len(refusal_examples) < 10:
                    refusal_examples.append(
                        {
                            "symbol": order.symbol,
                            "side": order.side,
                            "day": day.isoformat(),
                            "reason": res.reason,
                        }
                    )
        pending = []
        # 2. corporate actions on held names, then mark to market at the raw close
        for sym, pos in positions.items():
            hr = bars.get(sym, {}).get(day)
            if hr is None or hr["trade_status"] != 1:
                continue
            prev = last_close.get(sym)
            if prev is not None and hr["pre_close"] is not None and hr["pre_close"] < prev - 1e-9:
                per_share = prev - hr["pre_close"]
                cash += per_share * pos.shares
                dividends += per_share * pos.shares
        for sym, by_day in bars.items():
            dr = by_day.get(day)
            if dr is not None and dr["trade_status"] == 1 and dr["close"] is not None:
                last_close[sym] = dr["close"]
        held_value = sum(last_close.get(s, 0.0) * p.shares for s, p in positions.items())
        equity_curve.append((day, cash + held_value))
        # 3. decide on rebalance days using data dated <= day
        if day in rebalance_days and next_open_day(day) is not None:
            scored = [(lookback_return(s, day), s) for s in signal_close]
            ranked = sorted(
                ((r, s) for r, s in scored if r is not None),
                key=lambda x: (-x[0] if cand.direction == "high" else x[0], x[1]),
            )
            target = {s for _, s in ranked[: cand.top_k]}
            for sym, pos in sorted(positions.items()):
                if sym not in target:
                    pending.append(Order(sym, "sell", pos.shares, day))
            budget = (cash + held_value) / cand.top_k
            for sym in sorted(target - set(positions)):
                px = last_close.get(sym)
                if not px:
                    continue
                shares = int(budget / px / rules.LOT_SIZE) * rules.LOT_SIZE
                if shares > 0:
                    pending.append(Order(sym, "buy", shares, day))

    stranded = {
        s: {"shares": p.shares, "last_close_value_cny": round(last_close.get(s, 0.0) * p.shares, 2)}
        for s, p in positions.items()
        if s in delisted and days and delisted[s] <= days[-1]
    }
    end_equity = equity_curve[-1][1] if equity_curve else capital_cny
    end_equity_net = end_equity - sum(v["last_close_value_cny"] for v in stranded.values())
    peak, mdd = -1.0, 0.0
    for _, e in equity_curve:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1.0)
    daily_rets = [
        b / a - 1.0 for (_, a), (_, b) in zip(equity_curve, equity_curve[1:], strict=False) if a
    ]
    vol = (
        statistics.pstdev(daily_rets) * math.sqrt(TRADING_DAYS_PER_YEAR)
        if len(daily_rets) > 1
        else None
    )
    costs = {
        k: round(sum(getattr(f.fees, k) for f in fills), 2)
        for k in ("commission", "stamp_duty", "transfer_fee", "handling_fee", "regulatory_fee")
    }
    traded = sum(f.notional_cny for f in fills)
    avg_equity = statistics.fmean(e for _, e in equity_curve) if equity_curve else capital_cny
    ctx = context(exchange="SSE+SZSE", provider=provider, price_basis=PriceBasis.HFQ)
    return {
        "labels": [DESCRIPTIVE, sample_label],
        "candidate": asdict(cand),
        "market_context": ctx.as_dict(),
        "scope": SCOPE,
        "period": {"start": days[0].isoformat(), "end": days[-1].isoformat()} if days else None,
        "universe": {
            "symbols_with_data": len(bars),
            "eligible": len(signal_close),
            "excluded": excluded,
        },
        "capital_cny": capital_cny,
        "commission_assumption": asdict(commission),
        "result": {
            "end_equity_cny": round(end_equity_net, 2),
            "net_return": round(end_equity_net / capital_cny - 1.0, 6),
            "gross_return_before_fees": round((end_equity_net + fees_total) / capital_cny - 1.0, 6),
            "fees_cny": round(fees_total, 2),
            "corporate_action_cash_cny": round(dividends, 2),
            "max_drawdown": round(mdd, 6),
            "costs_cny": {**costs, "total": round(fees_total, 2)},
            "cost_drag": round(fees_total / capital_cny, 6),
            "risk": {
                "max_drawdown": round(mdd, 6),
                "volatility_annualized": None if vol is None else round(vol, 6),
                "worst_day": round(min(daily_rets), 6) if daily_rets else None,
                "best_day": round(max(daily_rets), 6) if daily_rets else None,
                "trading_days": len(equity_curve),
            },
            "turnover": round(traded / avg_equity, 4) if avg_equity else None,
            "fills": len(fills),
            "buys": sum(1 for f in fills if f.order.side == "buy"),
            "sells": sum(1 for f in fills if f.order.side == "sell"),
            "buys_resized_to_cash": resized,
            "refusals": dict(sorted(refusals.items())),
            "refusal_examples": refusal_examples,
            "unexecutable_delisting_exits": stranded,
            "open_positions_at_end": {s: p.shares for s, p in sorted(positions.items())},
        },
        "rules": rules.rule_disclosure(),
        "not_modelled": list(rules.NOT_MODELLED),
        "accounting": [
            "signals on HFQ closes dated <= decision day; fills at next trading day's raw open",
            "marked at raw close; a non-trading day carries the last traded close",
            "corporate actions credited as cash equal to the previous close minus the ex-rights reference price",
            "equal-weight target of equity/top_k at the decision-day close; a buy the cash cannot cover "
            "at the next open is cut to the lots it can cover",
            "dividend tax not modelled",
            "positions stranded by a delisting are valued at zero; last-close value reported separately",
        ],
    }
