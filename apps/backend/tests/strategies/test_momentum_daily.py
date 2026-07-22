"""momentum-daily (Workstream B) — the distinctive daily-evaluation behaviours.

The selection logic (A1 dual filter, A2 rank bands, A5 regime) is shared with v0.9 and covered by
`test_momentum_portfolio`. These tests cover what is NEW: the durable once-per-day latch, condition-
driven trading (trade only when a §5.1 trigger fires), per-trigger reason logging, and the incoherent
-band refusal — all against a state-backed mock context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.strategies.context import Bar, FillEvent, OpenOrderObs
from app.strategies.deployment_state import load_deployment_blob, seed_attempt_to_dict
from app.strategies.seed_reconciliation import SeedAttempt, SeedAttemptStatus
from strategies_user.templates.momentum_daily import (
    _K_LAST_EVAL,
    _K_REGIME,
    MomentumDaily,
)

D1 = datetime(2026, 6, 8, 21, 10, tzinfo=UTC)   # Mon post-close
D2 = datetime(2026, 6, 9, 21, 10, tzinfo=UTC)   # Tue post-close


def _bar(ts, symbol="AAA"):
    return Bar(symbol=symbol, timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order, raw=None):
    tickers = [t for t, _ in order]
    z = [s for _, s in order]
    raw = raw or {}
    mom = [raw.get(t, 0.10 + 0.01 * i) for i, t in enumerate(reversed(tickers))][::-1]
    df = pd.DataFrame({"momentum": mom, "winsorized": z, "zscore": z,
                       "rank": list(range(1, len(tickers) + 1)), "score": z}, index=tickers)
    df.index.name = "ticker"
    return df


def _spy(above=True, n=201):
    closes = [100.0] * (n - 1) + [110.0 if above else 90.0]
    idx = pd.to_datetime([datetime(2026, 6, 8).date()] * n)
    df = pd.DataFrame({"c": closes}, index=idx)
    df.index.name = "t"
    return df


def _dep_blob(state="DEPLOYED", has_ever=True, rev=0, first=None, active=None):
    """A valid deployment blob for the mock store. DEPLOYED+has_ever is the ordinary
    warm-book state under which existing trigger behavior must be preserved."""
    return {
        "schema_version": 1, "_rev": rev, "state": state,
        "has_ever_deployed": has_ever,
        "first_deployed_at": first or ("2026-01-01T00:00:00+00:00" if has_ever else None),
        "active_seed_attempt": active, "last_seed_attempt": None,
    }


def _ctx(symbols, scores, holdings=None, spy_bars=None, price=100.0, equity=100_000,
         deployment=None):
    holdings = holdings or {}
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.momentum_scores = MagicMock(return_value=scores)

    def _pos(s):
        if s not in holdings:
            return None
        p = MagicMock()
        p.side = "long"
        p.qty = Decimal(holdings[s])
        return p
    ctx.get_position_for = AsyncMock(side_effect=_pos)

    def _bars(sym, tf, n):
        return spy_bars if (spy_bars is not None and sym == "SPY") else pd.DataFrame({"c": [price]})
    ctx.get_recent_bars = AsyncMock(side_effect=_bars)
    ctx.get_account_equity = AsyncMock(return_value=equity)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason=None))
    ctx.log_signal = AsyncMock(return_value=1)
    ctx.pending_buy_qty = AsyncMock(return_value={})

    # durable state, dict-backed
    store: dict[str, object] = {}
    ctx._store = store
    ctx.get_state = AsyncMock(side_effect=lambda k, d=None: store.get(k, d))

    async def _set(k, v):
        store[k] = v
    ctx.set_state = AsyncMock(side_effect=_set)

    async def _clear(k):
        store.pop(k, None)
    ctx.clear_state = AsyncMock(side_effect=_clear)

    # P7 §7-A.2b: deployment blob + the read-side ctx seam (real dict-backed CAS so
    # reconcile/CAS-loss tests are exercised for real; fills/orders empty by default).
    store["deployment"] = _dep_blob() if deployment is None else deployment

    async def _cas(k, *, expected_rev, new_value):
        cur = store.get(k)
        cur_rev = cur.get("_rev") if isinstance(cur, dict) else None
        if expected_rev is None:
            if cur is not None:
                return False
            store[k] = new_value
            return True
        if cur_rev != expected_rev:
            return False
        store[k] = new_value
        return True
    ctx.compare_and_set_state = AsyncMock(side_effect=_cas)
    ctx.recent_fills = AsyncMock(return_value=[])
    ctx.open_orders = AsyncMock(return_value=[])
    return ctx


def _strat(ctx, **over):
    params = {**MomentumDaily.default_params, "order_pacing_seconds": 0.0,
              "use_market_regime_filter": False, "exit_confirm_closes": 1, **over}
    return MomentumDaily(ctx=ctx, params=params)


def _orders(ctx):
    out = {}
    for c in ctx.submit_order.call_args_list:
        r = c.args[0]
        out[r.symbol_ticker] = (r.side.value, r.qty)
    return out


def _reasons(ctx):
    return [c.kwargs.get("payload", {}).get("reason", "") for c in ctx.log_signal.call_args_list]


async def test_schema_matches_default_params():
    assert set(MomentumDaily.params_schema) == set(MomentumDaily.default_params)


async def test_incoherent_rank_band_is_refused():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    with pytest.raises(ValueError, match="incoherent rank bands"):
        await _strat(ctx, entry_rank=5, hold_rank=3).on_init()


async def test_the_daily_latch_is_DURABLE_evaluates_once_per_day():
    """The once-per-day latch lives in durable state, so a second tick the SAME day — even from a
    fresh instance (a reload) — does not re-evaluate."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores, holdings={"AAA": 5, "BBB": 5})  # warm DEPLOYED book
    s1 = _strat(ctx, entry_rank=2, max_names=2)
    await s1.on_init()
    await s1.on_bar(_bar(D1))
    calls_after_first = ctx.factors.momentum_scores.call_count
    assert calls_after_first >= 1
    assert ctx._store.get(_K_LAST_EVAL) == "2026-06-08"

    # a FRESH instance (reload) on the same day must NOT re-evaluate
    s2 = _strat(ctx, entry_rank=2, max_names=2)
    await s2.on_init()
    await s2.on_bar(_bar(datetime(2026, 6, 8, 21, 11, tzinfo=UTC)))
    assert ctx.factors.momentum_scores.call_count == calls_after_first  # unchanged -> latched


async def test_a_new_day_evaluates_again():
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]),
               holdings={"AAA": 5, "BBB": 5})  # warm DEPLOYED book
    s = _strat(ctx, entry_rank=2, max_names=2)
    await s.on_init()
    await s.on_bar(_bar(D1))
    n1 = ctx.factors.momentum_scores.call_count
    await s.on_bar(_bar(D2))                       # next day -> evaluates again
    assert ctx.factors.momentum_scores.call_count > n1


async def test_no_trigger_means_REVIEW_not_TRADE():
    """The core of the policy: a valid book with nothing breached is reviewed, not traded."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.9)])
    ctx = _ctx(["AAA", "BBB"], scores, holdings={"AAA": 5, "BBB": 5})
    s = _strat(ctx, entry_rank=2, hold_rank=2, max_names=2, weight_drift_pct=0.0)
    await s.on_init()
    await s.on_bar(_bar(D1))
    assert not _orders(ctx), "traded when no trigger fired"
    assert "reviewed_no_trigger" in _reasons(ctx)


async def test_raw_momentum_negative_is_a_trigger_and_is_LOGGED():
    """A holding whose raw momentum turns <= 0 fires raw_momentum_negative and the book trades."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.5)], raw={"AAA": 0.20, "BBB": -0.05})
    ctx = _ctx(["AAA", "BBB"], scores, holdings={"BBB": 5}, equity=100_000)
    s = _strat(ctx, entry_rank=2, hold_rank=2, max_names=2)
    await s.on_init()
    await s.on_bar(_bar(D1))
    orders = _orders(ctx)
    assert "BBB" in orders and orders["BBB"][0] == "sell"   # the falling holding is exited
    assert any("raw_momentum_negative" in r for r in _reasons(ctx))


async def test_regime_flip_to_risk_off_trades_to_cash_and_logs_regime_change():
    scores = _scores([("AAA", 2.0)])
    ctx = _ctx(["AAA", "SPY"], scores, holdings={"AAA": 5},
               spy_bars=_spy(above=False), equity=100_000)
    s = _strat(ctx, use_market_regime_filter=True, regime_mode="binary",
               entry_rank=1, max_names=1)
    await s.on_init()
    # seed the "previous regime" as risk-on so this close is a flip (durable — see _K_REGIME)
    await ctx.set_state(_K_REGIME, {"below": False})
    await s.on_bar(_bar(D1))
    orders = _orders(ctx)
    assert orders.get("AAA", ("", 0))[0] == "sell"          # flattened to cash
    # specifically regime_CHANGE*, not regime_bear_cash*: assert the FLIP was detected, not merely
    # that binary's `below is True` branch re-flattened (which happens regardless of `flipped`).
    assert any(r.startswith("regime_change") for r in _reasons(ctx)), _reasons(ctx)


def _spy_at(last: float, ma: float = 100.0, n: int = 201):
    """SPY bars whose 200d MA == ``ma`` and whose last close == ``last``."""
    closes = [ma] * (n - 1) + [last]
    idx = pd.to_datetime([datetime(2026, 6, 8).date()] * n)
    df = pd.DataFrame({"c": closes}, index=idx)
    df.index.name = "t"
    return df


@pytest.mark.parametrize(("last", "expected_gross"), [
    (110.0, 0.98),   # rel +10% > +2% band  -> clearly above
    (101.0, 0.60),   # rel  +1% within ±2%  -> mid buffer zone
    (90.0, 0.15),    # rel −10% < −2% band  -> clearly below
])
async def test_graduated_regime_steps_gross_with_distance_from_ma(last, expected_gross):
    """Stage-4 winner: graduated gross = 0.98 / 0.60 / 0.15 by distance from the 200d MA."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), spy_bars=_spy_at(last))
    s = _strat(ctx, use_market_regime_filter=True)   # default regime_mode == "graduated"
    await s.on_init()
    below, gross, _ = await s._regime()
    assert below is False                            # graduated never hard-flips to cash while fresh
    assert gross == pytest.approx(expected_gross)


async def test_graduated_regime_degrosses_below_ma_without_going_flat():
    """Below the MA, graduated stays PARTIALLY invested (gross 0.15) — not fully to cash like binary."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), holdings={},
               spy_bars=_spy_at(90.0), equity=100_000)
    s = _strat(ctx, use_market_regime_filter=True, entry_rank=1, max_names=1)
    await s.on_init()
    s._regime_gross = (await s._regime())[1]
    inv = await s._investable_equity()
    # ~ equity * (1 - cash_buffer 0.02) * gross 0.15  ->  clearly > 0 and well below full
    assert Decimal("10000") < inv < Decimal("20000")


async def test_graduated_gross_change_is_a_regime_change_flip():
    """A move across a gross boundary flips the regime (fires the regime_change trigger)."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), spy_bars=_spy_at(110.0))
    s = _strat(ctx, use_market_regime_filter=True)
    await s.on_init()
    await ctx.set_state(_K_REGIME, {"gross": 0.60})   # was in the buffer zone last eval
    _, gross, flipped = await s._regime()
    assert gross == pytest.approx(0.98) and flipped is True


async def test_graduated_regime_flip_survives_a_restart():
    """REGRESSION — the prior gross must be DURABLE, not an instance attribute.

    Graduated has no equivalent of binary's `below is True` branch, which re-flattens on every eval
    regardless of `flipped` and so self-corrects after a restart for free. Graduated re-grosses ONLY
    when `flipped` fires. With an in-memory latch a reloaded instance reads None -> flipped=False ->
    the book is stranded at its pre-restart gross until an unrelated trigger or the backstop review.
    Here: the book was at 0.98, the market fell into the mid band, and the process restarted.
    """
    scores = _scores([("AAA", 2.0)])
    ctx = _ctx(["AAA", "SPY"], scores, spy_bars=_spy_at(101.0))   # now the ±2% mid band -> 0.60
    s1 = _strat(ctx, use_market_regime_filter=True)
    await s1.on_init()
    await ctx.set_state(_K_REGIME, {"gross": 0.98})               # last eval, before the restart

    s2 = _strat(ctx, use_market_regime_filter=True)               # a FRESH instance = the restart
    await s2.on_init()
    _, gross, flipped = await s2._regime()

    assert gross == pytest.approx(0.60)
    assert flipped is True, "restart lost the prior gross — the book would stay at 0.98"


async def test_binary_regime_flip_also_survives_a_restart():
    """The same durability for binary mode: a fresh instance still sees the prior below-MA state."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), spy_bars=_spy(above=False))
    s1 = _strat(ctx, use_market_regime_filter=True, regime_mode="binary")
    await s1.on_init()
    await ctx.set_state(_K_REGIME, {"below": False})              # was risk-on before the restart

    s2 = _strat(ctx, use_market_regime_filter=True, regime_mode="binary")
    await s2.on_init()
    below, _, flipped = await s2._regime()

    assert below is True and flipped is True


@pytest.mark.parametrize("mode,expected_gross", [("graduated", 0.15), ("binary", 1.0)])
async def test_regime_with_no_persisted_state_initializes_deterministically(mode, expected_gross):
    """A book upgraded from v0.1.0 has no `_K_REGIME` row. First eval must be deterministic: report
    `flipped=False` (there is no prior to have flipped FROM — never invent one), compute the correct
    regime anyway, and persist it so the SECOND eval compares against a real prior."""
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), spy_bars=_spy_at(90.0))
    s = _strat(ctx, use_market_regime_filter=True, regime_mode=mode)
    await s.on_init()
    assert await ctx.get_state(_K_REGIME) is None          # nothing persisted yet

    below, gross, flipped = await s._regime()
    assert flipped is False                                # no prior => no fabricated flip
    assert gross == pytest.approx(expected_gross)
    assert below is (mode == "binary")                     # binary hard-flips; graduated de-grosses
    assert await ctx.get_state(_K_REGIME) is not None      # ... and the prior now EXISTS

    # second eval, unchanged market: still no flip, and it read a real prior rather than a default
    _, _, flipped2 = await s._regime()
    assert flipped2 is False


async def test_regime_modes_persist_distinct_unambiguous_values():
    """graduated persists {"gross": float}; binary persists {"below": bool} — disjoint keys.

    So a mode switch cannot MISREAD the other mode's value as its own: the `.get` misses, prev is
    None, and the eval reports flipped=False (a no-op) rather than a spurious flip off a
    type-confused prior.
    """
    ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]), spy_bars=_spy_at(90.0))

    g = _strat(ctx, use_market_regime_filter=True, regime_mode="graduated")
    await g.on_init()
    await g._regime()
    assert set(await ctx.get_state(_K_REGIME)) == {"gross"}

    b = _strat(ctx, use_market_regime_filter=True, regime_mode="binary")
    await b.on_init()
    _, _, flipped = await b._regime()                      # reads the graduated-written state
    assert flipped is False, "binary misread a graduated {'gross': ...} value as its own prior"
    assert set(await ctx.get_state(_K_REGIME)) == {"below"}


async def test_restart_reproduces_the_uninterrupted_transition_sequence():
    """CHECK 3 — replay equivalence: a run interrupted by a restart must produce the SAME (gross,
    flipped) sequence as one that ran straight through. Same market path, same durable store."""
    path = [110.0, 101.0, 101.0, 90.0, 110.0]              # above -> mid -> mid -> below -> above

    async def _sequence(restart_every_step: bool):
        ctx = _ctx(["AAA", "SPY"], _scores([("AAA", 2.0)]))
        s = _strat(ctx, use_market_regime_filter=True)
        await s.on_init()
        seq = []
        for last in path:
            # a "restart" = a brand-new instance sharing only the durable store
            if restart_every_step:
                s = _strat(ctx, use_market_regime_filter=True)
                await s.on_init()
            ctx.get_recent_bars = AsyncMock(side_effect=(
                lambda sym, tf, n, _l=last: _spy_at(_l) if sym == "SPY"
                else pd.DataFrame({"c": [100.0]})))
            _, gross, flipped = await s._regime()
            seq.append((round(gross, 4), flipped))
        return seq

    uninterrupted = await _sequence(restart_every_step=False)
    with_restarts = await _sequence(restart_every_step=True)

    assert uninterrupted == with_restarts, (
        f"restart changed the regime sequence: {uninterrupted} != {with_restarts}")
    # and it is the sequence the Stage-4 rule actually prescribes
    assert uninterrupted == [(0.98, False), (0.60, True), (0.60, False), (0.15, True), (0.98, True)]


async def test_retries_are_bounded_within_the_day():
    """A failing evaluation is retried a bounded number of times WITHIN the day, then gives up — it
    does not re-run on every one of the ~200 per-symbol ticks (storm guard), and the retry budget is
    durable so a reload cannot reset it."""
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores, holdings={"AAA": 5})
    ctx.factors.momentum_scores = MagicMock(side_effect=RuntimeError("boom"))
    s = _strat(ctx, entry_rank=2, max_names=2, max_daily_retries=3)
    await s.on_init()
    for _ in range(6):                                       # six ticks the same day
        await s.on_bar(_bar(D1))
    fails = [r for r in _reasons(ctx) if r == "daily_eval_failed"]
    exhausted = [r for r in _reasons(ctx) if r == "daily_eval_retries_exhausted"]
    assert len(fails) == 3                                   # exactly the retry budget
    assert exhausted                                         # then it gives up for the day


# ---- P7 §7-A.2b sub-step 1: deployment read-side integration ----

def _active(status=SeedAttemptStatus.ORDERS_OPEN, prefix="seed:1:att-1:"):
    return seed_attempt_to_dict(SeedAttempt(
        attempt_id="att-1", created_at=D1, intended_symbols=("AAA",),
        client_order_id_prefix=prefix, submitted_order_ids=(101,), status=status))


def _seed_fill():
    return FillEvent(fill_id=1, order_id=101, symbol="AAA", side="buy", qty=Decimal(5),
                     price=Decimal(100), filled_at=D1, client_order_id="seed:1:att-1:AAA",
                     account_id=1, source_id="1", order_status="filled")


async def test_substep1_missing_state_submits_nothing():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    del ctx._store["deployment"]  # uninitialized
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))
    assert not _orders(ctx)
    assert "deployment_state_uninitialized" in _reasons(ctx)
    assert ctx.factors.momentum_scores.call_count == 0  # never evaluated


async def test_substep1_malformed_state_submits_nothing():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]),
               deployment={"schema_version": 1, "_rev": 0, "state": "GARBAGE"})
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))
    assert not _orders(ctx)
    assert "deployment_state_invalid" in _reasons(ctx)


async def test_substep1_unexpected_flatten_alerts_without_inventing_intentional_flat():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), holdings={})  # DEPLOYED but flat
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))
    assert not _orders(ctx)
    assert "unexpected_flatten_detected" in _reasons(ctx)
    assert ctx._store["deployment"]["state"] == "DEPLOYED"  # NOT invented INTENTIONALLY_FLAT
    assert ctx.factors.momentum_scores.call_count == 0


async def test_substep1_reconciles_active_attempt_before_the_daily_latch():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), holdings={"AAA": 5},
               deployment=_dep_blob(state="DEPLOYED", active=_active()))
    ctx._store[_K_LAST_EVAL] = D1.date().isoformat()  # latched for today
    ctx.recent_fills = AsyncMock(return_value=[_seed_fill()])
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))
    blob = ctx._store["deployment"]
    assert blob["_rev"] == 1  # reconcile CAS applied DESPITE the latch
    assert blob["active_seed_attempt"] is None
    assert blob["last_seed_attempt"]["status"] == "FILLED"  # archived, not deleted


async def test_substep1_partial_fill_keeps_attempt_reconciling():
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]), holdings={"AAA": 5},
               deployment=_dep_blob(state="DEPLOYED", active=_active()))
    ctx.recent_fills = AsyncMock(return_value=[_seed_fill()])
    ctx.open_orders = AsyncMock(return_value=[OpenOrderObs(102, "BBB")])  # still open
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))
    blob = ctx._store["deployment"]
    assert blob["state"] == "DEPLOYED"
    assert blob["active_seed_attempt"]["status"] == "PARTIALLY_FILLED"


async def test_substep1_reconcile_cas_loss_does_not_evaluate_stale():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), holdings={"AAA": 5},
               deployment=_dep_blob(state="DEPLOYED", active=_active()))
    ctx.recent_fills = AsyncMock(return_value=[_seed_fill()])
    ctx.compare_and_set_state = AsyncMock(return_value=False)  # CAS lost
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))
    assert "reconcile_cas_lost" in _reasons(ctx)
    assert ctx.factors.momentum_scores.call_count == 0  # did NOT evaluate stale state


# ---- P7 §7-A.2b sub-step 2: seed / submission integration ----

def _fill(fid, oid, sym, prefix="seed:1:att-1:"):
    return FillEvent(fill_id=fid, order_id=oid, symbol=sym, side="buy", qty=Decimal(5),
                     price=Decimal(100), filled_at=D1, client_order_id=f"{prefix}{sym}",
                     account_id=1, source_id="1", order_status="filled")


async def test_substep2_initial_seed_fires_writes_ahead_and_tags_orders():
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]), holdings={},
               deployment=_dep_blob(state="NEVER_DEPLOYED", has_ever=False))
    s = _strat(ctx, entry_rank=2, max_names=2)
    await s.on_init()
    await s.on_bar(_bar(D1))
    assert "initial_seed_eval" in _reasons(ctx)
    blob = ctx._store["deployment"]
    assert blob["state"] == "DEPLOYMENT_PENDING"
    assert blob["active_seed_attempt"]["status"] == "ORDERS_OPEN"
    assert _orders(ctx)  # seed buys submitted
    coids = [c.args[0].client_order_id for c in ctx.submit_order.call_args_list]
    assert coids and all(cid and cid.startswith("seed:1:2026-06-08-1:") for cid in coids)


async def test_substep2_concurrent_cas_one_winner_one_submits_zero():
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]), holdings={},
               deployment=_dep_blob(state="NEVER_DEPLOYED", has_ever=False))
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    dep0 = load_deployment_blob(ctx._store["deployment"])  # both callers read _rev 0
    s1, s2 = _strat(ctx, entry_rank=2, max_names=2), _strat(ctx, entry_rank=2, max_names=2)
    await s1.on_init()
    await s2.on_init()
    s1._tick_ts = D1
    s2._tick_ts = D1
    await s1._maybe_initial_seed("2026-06-08", dep0, 1.0, scores, {})
    n1 = len(ctx.submit_order.call_args_list)
    await s2._maybe_initial_seed("2026-06-08", dep0, 1.0, scores, {})  # stale _rev 0
    n2 = len(ctx.submit_order.call_args_list)
    assert n1 > 0                       # winner submitted
    assert n2 == n1                     # loser submitted ZERO
    assert "initial_seed_cas_lost" in _reasons(ctx)


async def test_substep2_crash_after_submit_recovers_by_prefix_without_reseeding():
    active = seed_attempt_to_dict(SeedAttempt(
        attempt_id="2026-06-08-1", created_at=D1, intended_symbols=("AAA",),
        client_order_id_prefix="seed:1:2026-06-08-1:", submitted_order_ids=(),
        status=SeedAttemptStatus.SUBMITTING))  # crashed mid-submit, persisted
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), holdings={"AAA": 5},
               deployment=_dep_blob(state="DEPLOYMENT_PENDING", has_ever=False, active=active))
    ctx.recent_fills = AsyncMock(return_value=[_fill(1, 1, "AAA", "seed:1:2026-06-08-1:")])
    s = _strat(ctx)
    await s.on_init()
    n_before = len(ctx.submit_order.call_args_list)
    await s.on_bar(_bar(D1))
    blob = ctx._store["deployment"]
    assert blob["state"] == "DEPLOYED" and blob["has_ever_deployed"] is True
    assert len(ctx.submit_order.call_args_list) == n_before  # NO re-seed


async def test_substep2_partial_then_terminal_reconciles_to_archive():
    active = _active(status=SeedAttemptStatus.ORDERS_OPEN)  # prefix seed:1:att-1:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", 2.0), ("BBB", 1.0)]), holdings={"AAA": 5},
               deployment=_dep_blob(state="DEPLOYMENT_PENDING", has_ever=False, active=active))
    ctx.recent_fills = AsyncMock(return_value=[_fill(1, 101, "AAA")])
    ctx.open_orders = AsyncMock(return_value=[OpenOrderObs(102, "BBB")])
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))                       # partial: AAA filled, BBB open
    blob = ctx._store["deployment"]
    assert blob["state"] == "DEPLOYED" and blob["has_ever_deployed"] is True
    assert blob["active_seed_attempt"]["status"] == "PARTIALLY_FILLED"
    # next session: BBB now filled too, nothing open -> archive
    ctx.get_position_for = AsyncMock(side_effect=lambda x: _mk_pos(5) if x in ("AAA", "BBB") else None)
    ctx.recent_fills = AsyncMock(return_value=[_fill(1, 101, "AAA"), _fill(2, 102, "BBB")])
    ctx.open_orders = AsyncMock(return_value=[])
    await s.on_bar(_bar(D2))
    blob = ctx._store["deployment"]
    assert blob["active_seed_attempt"] is None
    assert blob["last_seed_attempt"]["status"] == "FILLED"  # archived, not deleted


def _mk_pos(qty):
    p = MagicMock()
    p.side = "long"
    p.qty = Decimal(qty)
    return p


async def test_substep2_all_submissions_fail_archives_and_returns_never_deployed():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), holdings={},
               deployment=_dep_blob(state="NEVER_DEPLOYED", has_ever=False))
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason="risk_blocked"))
    s = _strat(ctx)
    await s.on_init()
    await s.on_bar(_bar(D1))
    blob = ctx._store["deployment"]
    assert blob["state"] == "NEVER_DEPLOYED"          # safe rollback
    assert blob["active_seed_attempt"] is None
    assert blob["last_seed_attempt"]["status"] == "TERMINALLY_UNFILLED"  # archived
    assert "initial_seed_all_rejected" in _reasons(ctx)


async def test_substep2_restart_does_not_reseed_a_pending_book():
    active = _active(status=SeedAttemptStatus.ORDERS_OPEN)
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]), holdings={},
               deployment=_dep_blob(state="DEPLOYMENT_PENDING", has_ever=False, active=active))
    ctx.recent_fills = AsyncMock(return_value=[])
    ctx.open_orders = AsyncMock(return_value=[OpenOrderObs(101, "AAA")])
    s = _strat(ctx)  # fresh instance = a restart
    await s.on_init()
    n_before = len(ctx.submit_order.call_args_list)
    await s.on_bar(_bar(D1))
    assert len(ctx.submit_order.call_args_list) == n_before  # NO duplicate/replacement seed
    blob = ctx._store["deployment"]
    assert blob["state"] == "DEPLOYMENT_PENDING"
    assert blob["active_seed_attempt"]["status"] == "ORDERS_OPEN"


# ---- sizing seam (weighting-defect adjudication 2026-07-22) ----------------------
#
# momentum-daily sizes EQUAL WEIGHT ONLY. At max_names=5 with a hard 20% per-name cap, equal
# weight is the only feasible fully-invested portfolio, so no inverse-vol tilt is expressible.
# These tests pin (a) the config surface cannot claim otherwise, and (b) sizing has exactly one
# source of truth that the §8 audit harness can observe.


async def test_weighting_schema_offers_equal_only():
    """The surface must not advertise sizing the code does not implement (schema/code drift)."""
    assert MomentumDaily.params_schema["weighting"]["choices"] == ["equal"]
    assert MomentumDaily.default_params["weighting"] == "equal"


@pytest.mark.parametrize("bad", ["invvol_hybrid", "hybrid_50_50", "EQUAL"])
async def test_unsupported_weighting_fails_closed(bad):
    """A stored param row predating the adjudication must be REJECTED, not silently sized equal."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    with pytest.raises(ValueError, match="unsupported weighting"):
        await _strat(ctx, weighting=bad).on_init()


@pytest.mark.parametrize("k,expected", [(5, 0.20), (4, 0.20), (2, 0.20), (10, 0.10), (1, 0.20)])
async def test_per_name_notional_is_equal_weight_capped_at_max_position_pct(k, expected):
    """Equal weight, hard-capped. The cap binds below 5 names — the book then holds cash rather
    than concentrating past the limit. It NEVER exceeds max_position_pct."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    s = _strat(ctx)
    assert float(s._per_name_notional(Decimal(1), k)) == pytest.approx(expected)


async def test_no_target_weight_ever_breaches_the_position_cap():
    """The defect being corrected: the Stage-3 hybrid emitted up to 20.594% per name on 100% of
    5-name sessions. Production must never produce a target above max_position_pct."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    s = _strat(ctx)
    s._regime_gross = 1.0
    for k in range(1, 12):
        w = s.target_weights([f"T{i}" for i in range(k)])
        assert max(w.values()) <= float(s.params["max_position_pct"]) + 1e-12


async def test_target_weights_are_gross_scaled_and_sum_to_gross():
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    s = _strat(ctx)
    s._regime_gross = 0.60
    w = s.target_weights(["A", "B", "C", "D", "E"])
    assert sum(w.values()) == pytest.approx(0.60)
    assert all(v == pytest.approx(0.12) for v in w.values())
    assert s.target_weights([]) == {}


async def test_target_weights_agree_with_what_the_order_path_actually_sizes():
    """The seam is OBSERVABLE truth, not a parallel restatement: the weights reported must equal
    the notional the order path sizes, divided by investable equity. If these ever diverge the
    audit harness would certify a portfolio production does not hold."""
    ctx = _ctx(["AAA"], _scores([("AAA", 2.0)]))
    s = _strat(ctx)
    s._regime_gross = 0.98
    targets = ["A", "B", "C", "D", "E"]
    equity = Decimal("100000")
    sized = s._per_name_notional(equity, len(targets))
    reported = s.target_weights(targets)["A"]
    # reported weight is a fraction of TOTAL equity (gross-scaled); the order path sizes against
    # already-gross-scaled investable equity, so divide the gross back out for the comparison.
    assert float(sized / equity) == pytest.approx(reported / 0.98)
