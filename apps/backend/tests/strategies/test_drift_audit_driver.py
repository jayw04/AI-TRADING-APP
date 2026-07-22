"""§8 drift-audit driver — the deterministic adapter faithfully drives the REAL
MomentumDaily through the cold-start seed and captures the decision seams."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd

from app.strategies.context import Bar
from app.strategies.deployment_state import initial_blob
from app.strategies.drift_audit_driver import (
    DriftCtxAdapter,
    capture_replica_seams,
    capture_seam,
    drive_live,
)
from strategies_user.templates.momentum_daily import _K_DEPLOYMENT, MomentumDaily

SYMS = ["SPY", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
DAY = date(2005, 1, 3)
TS = datetime(2005, 1, 3, 21, 10, tzinfo=UTC)


def _scores(_day: date) -> pd.DataFrame:
    """Six strongly-positive momentum names, descending — all eligible, risk-on."""
    tk = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    z = [3.0, 2.5, 2.0, 1.5, 1.0, 0.5]
    mom = [0.40, 0.35, 0.30, 0.25, 0.20, 0.15]
    df = pd.DataFrame({"momentum": mom, "winsorized": z, "zscore": z,
                       "rank": list(range(1, 7)), "score": z}, index=tk)
    df.index.name = "ticker"
    return df


def _bars(sym: str, _as_of: date, n: int) -> pd.DataFrame:
    n = max(n, 220)
    # SPY = strong uptrend (risk-on regime); other names flat.
    closes = [80.0 + 0.2 * i for i in range(n)] if sym == "SPY" else [100.0] * n
    idx = pd.to_datetime([DAY] * n)
    df = pd.DataFrame({"o": closes, "h": closes, "l": closes, "c": closes,
                       "v": [1_000] * n}, index=idx)
    df.index.name = "t"
    return df


def _adapter() -> DriftCtxAdapter:
    a = DriftCtxAdapter(symbols=SYMS, strategy_id=11, scores_provider=_scores,
                        bars_provider=_bars, equity=Decimal(100_000), sim_day=DAY)
    a._state[_K_DEPLOYMENT] = initial_blob().to_dict()   # NEVER_DEPLOYED, rev 0
    return a


def _strategy(adapter: DriftCtxAdapter) -> MomentumDaily:
    params = {**MomentumDaily.default_params, "order_pacing_seconds": 0.0,
              "regime_mode": "graduated", "use_market_regime_filter": True,
              "initial_seed_investable_gross": 0.60}
    return MomentumDaily(ctx=adapter, params=params)


async def test_adapter_drives_real_class_cold_start_seed_on_day_one():
    adapter = _adapter()
    strat = _strategy(adapter)

    await strat.on_bar(Bar(symbol="AAA", timeframe="1Day", t=TS, o=1, h=1, l=1, c=1, v=1))

    # The NEVER_DEPLOYED flat book must SEED on day one (the validated day-1 inception that
    # initial_seed restores) — not sit flat. Seed orders carry the seed client_order_id.
    assert adapter.submitted_today, "cold-start seed submitted no orders"
    assert any((o.client_order_id or "").startswith(f"seed:{11}:") for o in adapter.submitted_today)
    reasons = [s["payload"].get("reason", "") for s in adapter.signals_today]
    assert any("seed" in r for r in reasons)

    # The deployment blob advanced off NEVER_DEPLOYED (a seed attempt is now active/pending).
    dep = adapter._state[_K_DEPLOYMENT]
    assert dep["state"] != "NEVER_DEPLOYED" or dep["active_seed_attempt"] is not None


async def test_capture_seam_produces_a_record_from_the_real_seams():
    adapter = _adapter()
    strat = _strategy(adapter)
    await strat.on_bar(Bar(symbol="AAA", timeframe="1Day", t=TS, o=1, h=1, l=1, c=1, v=1))

    rec = capture_seam(strat, adapter, DAY)
    assert rec.date == "2005-01-03"
    assert rec.eligible == ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")   # real _eligible ranking
    assert rec.target_names == ("AAA", "BBB", "CCC", "DDD", "EEE")      # real _select_targets, max_names=5
    assert rec.regime_gross > 0.0 and rec.trade_initiated is True and rec.is_seed is True
    assert set(rec.weights) == set(rec.target_names)


async def test_settle_evolves_the_book_so_holdings_persist_next_session():
    adapter = _adapter()
    strat = _strategy(adapter)
    await strat.on_bar(Bar(symbol="AAA", timeframe="1Day", t=TS, o=1, h=1, l=1, c=1, v=1))
    n_orders = len(adapter.submitted_today)
    assert n_orders > 0

    # Fill the seed orders at the next session's price; the book must then reflect the holdings.
    adapter.settle({o.symbol: 100.0 for o in adapter._pending})
    held = {k: v for k, v in adapter._positions.items() if v > 0}
    assert held, "no holdings after settling the seed fills"
    # recent_fills must surface the seed fills for the strategy's reconciliation.
    fills = await adapter.recent_fills(client_order_id_prefix=f"seed:{11}:")
    assert len(fills) == n_orders


# ---- multi-day live drive ----

async def test_drive_live_multi_day_seeds_day_one_then_evolves():
    adapter = _adapter()
    strat = _strategy(adapter)
    days = [date(2005, 1, d) for d in (3, 4, 5, 6)]
    records = await drive_live(strat, adapter, days, fill_price_fn=lambda _s, _d: 100.0)

    assert len(records) == 4
    assert records[0].is_seed is True and records[0].trade_initiated is True   # day-1 inception
    assert all(not r.is_seed for r in records[1:])                             # seed is one-shot
    # holdings persist after the day-1 seed fills settle
    held = {k: v for k, v in adapter._positions.items() if v > 0}
    assert held, "no holdings after the multi-day drive"


# ---- replica seam extractor (mirrors Stage 4 simulate) ----

class _DS:
    def __init__(self, ranked):
        self.ranked = ranked
        self.score = {t: float(len(ranked) - i) for i, t in enumerate(ranked)}
        self.rank = {t: i + 1 for i, t in enumerate(ranked)}


def test_replica_trade_gate_changed_regime_flip_and_hold():
    days = [date(2005, 1, d) for d in (3, 4, 5)]
    ranked = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    day_scores = {d: _DS(ranked) for d in days}
    gross = {days[0]: 0.98, days[1]: 0.98, days[2]: 0.50}   # gross flips on day 3
    recs = capture_replica_seams(
        days, day_scores, gross,
        select_fn=lambda ds, held, prev: ds.ranked[:5],
        weigh_fn=lambda chosen, d: {t: 1.0 / len(chosen) for t in chosen},
        price_fn=lambda t, d: 100.0,
        backstop_days=10, weight_drift_pct=0.04, turnover_cost_bps=5.0,
        initial_equity=100_000.0)

    assert len(recs) == 3
    # day 1: flat -> top5 is a change -> trade
    assert recs[0].trade_initiated is True and recs[0].target_names == ("AAA", "BBB", "CCC", "DDD", "EEE")
    assert "changed" in recs[0].trigger
    # day 2: same target, same gross, no drift -> HOLD
    assert recs[1].trade_initiated is False and recs[1].trigger == "reviewed_no_trigger"
    # day 3: gross 0.98 -> 0.50 is a regime flip -> trade
    assert recs[2].trade_initiated is True and "regime_flip" in recs[2].trigger
    # gross-scaled weights on the traded days
    assert abs(sum(recs[0].weights.values()) - 0.98) < 1e-9
    assert abs(sum(recs[2].weights.values()) - 0.50) < 1e-9


async def test_end_to_end_pipeline_live_vs_replica_produces_census():
    """Tiny e2e: drive the real live class + the replica over the same synthetic sessions,
    feed both into build_report, and confirm the diagnostic census is produced with the
    first-cause / downstream separation. (The two are NOT expected to match — the live
    equal-weight vs replica weights and trigger gate differ by construction.)"""
    from app.strategies.drift_audit import build_report

    adapter = _adapter()
    strat = _strategy(adapter)
    days = [date(2005, 1, d) for d in (3, 4, 5, 6)]
    live = await drive_live(strat, adapter, days, fill_price_fn=lambda _s, _d: 100.0)

    ranked = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    replica = capture_replica_seams(
        days, {d: _DS(ranked) for d in days}, {d: 0.98 for d in days},
        select_fn=lambda ds, held, prev: ds.ranked[:5],
        weigh_fn=lambda chosen, d: {t: 1.0 / len(chosen) for t in chosen},
        price_fn=lambda t, d: 100.0, backstop_days=10, weight_drift_pct=0.04,
        turnover_cost_bps=5.0, initial_equity=100_000.0)

    report = build_report(live, replica).to_dict()
    assert report["n_sessions"] == 4
    assert set(report["census"]) >= {"trigger_mismatch_sessions", "target_mismatch_sessions",
                                     "weight_mismatch_sessions", "semantic_mismatch_sessions"}
    # both agree on the day-1 inception target (top-5 momentum names)
    assert live[0].target_names == replica[0].target_names == ("AAA", "BBB", "CCC", "DDD", "EEE")
    # the report separates first-cause from downstream and never omits the note
    assert "first_cause" in report and "downstream_mismatch_sessions" in report
    assert "_note" in report and "DIAGNOSTIC" in report["_note"]


def test_replica_thin_day_emits_no_scores_record():
    days = [date(2005, 1, 3), date(2005, 1, 4)]
    day_scores = {days[0]: _DS(["AAA", "BBB"])}  # day 2 missing -> thin
    recs = capture_replica_seams(
        days, day_scores, {d: 1.0 for d in days},
        select_fn=lambda ds, held, prev: ds.ranked[:5],
        weigh_fn=lambda chosen, d: {t: 1.0 / len(chosen) for t in chosen},
        price_fn=lambda t, d: 100.0, backstop_days=10, weight_drift_pct=0.04,
        turnover_cost_bps=5.0, initial_equity=100_000.0)
    assert recs[1].trigger == "no_scores" and recs[1].trade_initiated is False
