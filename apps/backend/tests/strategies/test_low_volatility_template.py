"""Phase 2 — low-volatility template (LOW-001 Capability Promotion).

Covers schema parity, weekly rebalance cadence (durable completed + same-process
storm skip), top-quintile lowest-volatility selection (``ceil(N · top_quantile)``),
equal-weight sizing, SPY exclusion, factor-unavailable / factor-stale HOLD,
always-invested (no SPY cash gate), PIT unregistered-name skip, and the
rejection policy — all against a synthetic StrategyContext (no engine, no DB).

The selection mirrors the validated LOW-001 V1 research (``run_momentum_backtest``
with ``score_fn=low_vol_score``, ``top_quantile=0.20``): rank by −(trailing realized
vol), hold the lowest-vol quintile equal-weight. These tests pin that behavior so the
promoted strategy stays faithful to the evidence it was validated on (the
Methodology-Transfer discipline)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from apscheduler.triggers.cron import CronTrigger

from app.factor_data.accessor import FactorDataUnavailable
from app.strategies.context import Bar
from app.strategies.engine import _STRATEGY_SCHEDULE_TZ, _normalize_crontab_dow
from strategies_user.templates.low_volatility import (
    RESEARCH_UNIVERSE_N,
    LowVolatility,
    expected_last_session,
    session_lag,
)

#: The governed live registration for LOW-001 on Account 6 (strategy 8), read from the
#: running system 2026-08-22. Schedule strings are exchange-local: Monday 10:32 ET.
GOVERNED_SCHEDULE = "32 10 * * mon"

WK1_A = datetime(2026, 6, 8, 14, 0, tzinfo=UTC)  # Mon
WK1_B = datetime(2026, 6, 8, 14, 1, tzinfo=UTC)  # same ISO week
WK2 = datetime(2026, 6, 15, 14, 0, tzinfo=UTC)  # next ISO week


def _bar(ts: datetime, symbol: str = "AAA") -> Bar:
    return Bar(symbol=symbol, timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order: list[tuple[str, float]]) -> pd.DataFrame:
    """A low_vol_scores-shaped frame: indexed by ticker, ``score`` column, already
    sorted by score descending (lowest vol first) — exactly what the accessor returns."""
    df = pd.DataFrame({"score": [s for _, s in order]}, index=[t for t, _ in order])
    df.index.name = "ticker"
    return df


def _pos(qty: int):
    p = MagicMock()
    p.side = "long"
    p.qty = Decimal(qty)
    return p


def _params(**over):
    """Sizing knobs neutralized so a test can isolate one behavior."""
    return {
        **LowVolatility.default_params,
        "cash_buffer_pct": 0.0,
        "max_position_pct": 1.0,
        "min_trade_pct": 0.0,
        "order_pacing_seconds": 0.0,  # no real sleeps in tests
        **over,
    }


#: Columns of the empty frame ``StrategyContext.get_recent_bars`` returns for a symbol
#: outside the strategy's universe (see ``app/strategies/context.py``).
_EMPTY_BARS = ["t", "o", "h", "l", "c", "v"]


def _ctx(
    symbols,
    scores,
    holdings=None,
    price=100.0,
    equity=None,
    spy_bars=None,
    latest_price_date: date = date(2026, 6, 19),
    owned=None,
    legacy_context: bool = False,
):
    """Synthetic StrategyContext driving ``ctx.factors.low_vol_scores``.

    Default ``latest_price_date`` is Friday of test week 2 so both WK1 (Mon 6/8)
    and WK2 (Mon 6/15) pass the session-freshness gate. Stale-HOLD tests
    override it.

    **Registration blindness is reproduced faithfully (LOW-PIT-01B).** Production
    ``StrategyContext`` does not enforce the strategy universe by refusing orders --
    ``submit_order`` carries no such check, and neither does OrderRouter nor the risk
    engine. It enforces it by making the strategy *unable to see* anything outside
    ``ctx.symbols``::

        get_position_for(x)  -> None                 when x not in ctx.symbols
        get_positions()      -> filtered to ctx.symbols
        get_recent_bars(x)   -> empty frame          when x not in ctx.symbols
        pending_buy_qty()    -> keys filtered to ctx.symbols
        log_signal(x)        -> warns, but WRITES    (evidence is recordable)
        submit_order(x)      -> reaches the router   (no registration check)

    A fake that hands back a position or a price for an unregistered symbol is
    *more permissive than production*, and an exit-safety test written against it
    passes on code that strands the holding live. That is exactly the false pass
    this harness must not manufacture, so the gates above are modelled here rather
    than assumed away.

    ``owned`` (PR S / S3) is the set of tickers this strategy unambiguously owns and
    currently holds despite their never having been registered. Production widens READ
    authority — and only READ authority — to ``registered ∪ owned``. Note ``owned`` does
    NOT join ``ctx.symbols``: a widened symbol stays outside selection and buy planning,
    which is the property PIT-T16 exists to protect.

    ``legacy_context=True`` strips ``get_holdings`` to emulate a pre-S4 runtime, so the
    template's fallback path stays covered.
    """
    holdings = holdings or {}
    completed: list[dict] = []
    ctx = MagicMock()
    ctx.strategy_id = 1
    ctx.symbols = symbols
    registered = {s.upper() for s in symbols}
    owned_scope = {s.upper() for s in (owned or ())}
    visible = registered | owned_scope  # READ scope, never the buy scope
    ctx.factors = MagicMock()
    ctx.factors.low_vol_scores = MagicMock(return_value=scores)
    ctx.factors.latest_price_date = MagicMock(return_value=latest_price_date)

    async def _position_for(sym):
        if sym.upper() not in visible:
            return None  # production returns None, NOT the position
        return _pos(holdings[sym]) if sym in holdings else None

    async def _positions():
        return [_pos(q) for s, q in holdings.items() if s.upper() in visible]

    async def _holdings():
        return {
            s.upper(): Decimal(q) for s, q in holdings.items() if s.upper() in visible and q > 0
        }

    ctx.get_position_for = AsyncMock(side_effect=_position_for)
    ctx.get_positions = AsyncMock(side_effect=_positions)
    if legacy_context:
        # A MagicMock auto-creates any attribute, so absence has to be explicit.
        ctx.get_holdings = None
    else:
        ctx.get_holdings = AsyncMock(side_effect=_holdings)
    # Buy-side netting is NOT widened by ownership (v0.3 §4.7).
    ctx.pending_buy_qty = AsyncMock(return_value={})

    def _bars(sym, tf, n):
        if sym.upper() not in visible:
            return pd.DataFrame(columns=_EMPTY_BARS)  # unauthorized symbol
        if spy_bars is not None and sym == "SPY":
            return spy_bars
        return pd.DataFrame({"c": [price]})

    ctx.get_recent_bars = AsyncMock(side_effect=_bars)
    ctx.get_account_equity = AsyncMock(return_value=equity)

    async def _log(_sym, _typ, payload=None):
        p = dict(payload or {})
        if p.get("reason") == "rebalance_completed":
            completed.append(p)
        return 1

    ctx.log_signal = AsyncMock(side_effect=_log)
    ctx.recent_payloads = AsyncMock(side_effect=lambda limit=80: list(completed))
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason=None))
    return ctx


def _orders(ctx) -> dict[str, tuple[str, Decimal]]:
    out = {}
    for call in ctx.submit_order.call_args_list:
        req = call.args[0]
        out[req.symbol_ticker] = (req.side.value, req.qty)
    return out


def _strat(ctx, **over):
    return LowVolatility(ctx=ctx, params=_params(**over))


# ---- schema / cadence ----------------------------------------------------------


def test_schema_matches_default_params() -> None:
    """The typed form is derived from params_schema; it must list exactly the
    params the code reads (CLAUDE.md: schema↔code drift breaks the form)."""
    assert set(LowVolatility.params_schema) == set(LowVolatility.default_params)


def test_research_frozen_defaults() -> None:
    """The validated LOW-001 V1 economics must not silently drift.

    These are RESEARCH invariants: the 252-session realized-vol window, the lowest
    quintile, equal weighting, and the weekly cadence. Changing any of them changes what
    LOW-001 *is* and requires a research decision.

    The clock time the weekly cadence fires at is NOT one of them — it is a runtime
    conformance default and is asserted separately below. Grouping it here implied the
    2pm-ET value was research-frozen when it was simply wrong (S7).
    """
    assert LowVolatility.default_params["vol_lookback_days"] == 252
    assert LowVolatility.default_params["top_quantile"] == 0.20
    assert "use_market_regime_filter" not in LowVolatility.default_params
    assert "use_market_regime_filter" not in LowVolatility.params_schema
    # Version tracks the RUNTIME implementation for this strategy (1.0.0 -> 1.0.1 was
    # itself a pure conformance repair). 1.0.2 == PR S; 1.0.3 reserved for Dynamic PIT.
    assert LowVolatility.version == "1.0.2"
    # Weekly cadence IS frozen economics; the hour is not.
    assert LowVolatility.schedule.split()[-1] == "mon"


def test_runtime_schedule_default_matches_the_governed_registration() -> None:
    """Cheap literal guard: catches someone editing the cron string.

    Paired with the timezone-resolution test below, which catches the other failure
    mode — the string staying put while its interpretation moves.
    """
    assert LowVolatility.schedule == GOVERNED_SCHEDULE


@pytest.mark.parametrize(
    ("after", "label"),
    [
        (datetime(2026, 1, 5, 0, 0, tzinfo=ZoneInfo("America/New_York")), "EST"),
        (datetime(2026, 6, 1, 0, 0, tzinfo=ZoneInfo("America/New_York")), "EDT"),
    ],
)
def test_default_schedule_fires_monday_1032_new_york(after, label) -> None:
    """Resolve the class default through the ENGINE's own cron path and check the instant.

    This is the assertion that would have caught S7's defect. A literal string check
    passed throughout the period the semantics silently changed from UTC to ET, because
    the string never moved — the interpretation did.

    Asserted as New York WALL-CLOCK time, deliberately, and across both EST and EDT. A
    hard-coded "14:32Z" would re-encode exactly the timezone fragility that caused the
    defect: it is true for half the year.
    """
    trigger = CronTrigger.from_crontab(
        _normalize_crontab_dow(LowVolatility.schedule), timezone=_STRATEGY_SCHEDULE_TZ
    )
    fire = trigger.get_next_fire_time(None, after)
    local = fire.astimezone(ZoneInfo("America/New_York"))
    assert (local.hour, local.minute) == (10, 32), f"{label}: {local}"
    assert local.weekday() == 0, f"{label}: not a Monday — {local}"


def test_reregistration_from_class_defaults_keeps_the_governed_slot() -> None:
    """The hazard S7 exists to prevent, stated directly.

    Recreating LOW-001 from class defaults must reproduce the governed 10:32 ET slot. With
    the old default it would have scheduled the book at 14:00 ET — a 3.5-hour move, with
    no error and nothing in the diff to notice.
    """
    registered = list(LowVolatility.symbols) or []
    schedule = LowVolatility.schedule  # exactly what StrategyEngine.register would use
    assert registered == []  # symbols come from the DB row, not the class

    trigger = CronTrigger.from_crontab(
        _normalize_crontab_dow(schedule), timezone=_STRATEGY_SCHEDULE_TZ
    )
    after = datetime(2026, 8, 20, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # a Thursday
    local = trigger.get_next_fire_time(None, after).astimezone(ZoneInfo("America/New_York"))
    assert local.strftime("%A %H:%M") == "Monday 10:32"


def test_expected_last_session_skips_weekend() -> None:
    assert expected_last_session(date(2026, 6, 8)) == date(2026, 6, 5)  # Mon → Fri
    assert expected_last_session(date(2026, 6, 9)) == date(2026, 6, 8)  # Tue → Mon


def test_expected_last_session_skips_observed_holiday() -> None:
    """Monday after Friday Independence Day observed → Thursday, not the holiday."""
    assert expected_last_session(date(2026, 7, 6)) == date(2026, 7, 2)


def test_session_lag_counts_trading_sessions_not_weekdays() -> None:
    expected = date(2026, 6, 5)
    assert session_lag(date(2026, 6, 5), expected) == 0
    assert session_lag(date(2026, 6, 4), expected) == 1
    assert session_lag(date(2026, 6, 3), expected) == 2
    # Weekday walk would treat Fri 7/3 as the prior session; NYSE previous is Thu 7/2.
    assert session_lag(date(2026, 7, 2), expected_last_session(date(2026, 7, 6))) == 0


async def test_rebalances_once_per_iso_week() -> None:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", -0.1), ("BBB", -0.2)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week, completed → no second score
    assert ctx.factors.low_vol_scores.call_count == 1
    await strat.on_bar(_bar(WK2))  # new week → rebalances again
    assert ctx.factors.low_vol_scores.call_count == 2


async def test_live_dispatch_seq_storm_skips_other_symbols() -> None:
    """Live engine calls on_bar once per symbol; dispatch_seq must collapse them."""
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", -0.1), ("BBB", -0.2)]), equity=100_000)
    ctx.dispatch_seq = 7
    ctx.session = MagicMock(as_of=WK1_A)
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A, "AAA"))
    await strat.on_bar(_bar(WK1_A, "BBB"))
    assert ctx.factors.low_vol_scores.call_count == 1


def _last_kwargs(ctx) -> dict:
    _, kwargs = ctx.factors.low_vol_scores.call_args
    return kwargs


async def test_vol_window_defaults_to_252() -> None:
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", -0.1), ("BBB", -0.2)]))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _last_kwargs(ctx)["lookback_days"] == 252
    assert _last_kwargs(ctx)["n"] == RESEARCH_UNIVERSE_N


async def test_incomplete_week_retries_after_restart() -> None:
    """A raised rebalance does not write rebalance_completed. The same instance
    storm-skips remaining symbols; a new instance (process restart) retries."""
    ctx = _ctx(["AAA"], _scores([("AAA", -0.1)]))
    ctx.factors.low_vol_scores = MagicMock(side_effect=ValueError("boom"))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same instance → storm skip
    assert ctx.factors.low_vol_scores.call_count == 1
    assert any(
        "rebalance_failed" in str(c.kwargs.get("payload", {}))
        for c in ctx.log_signal.call_args_list
    )

    restarted = _strat(ctx)
    await restarted.on_init()
    await restarted.on_bar(_bar(WK1_B))
    assert ctx.factors.low_vol_scores.call_count == 2


# ---- low-vol selection --------------------------------------------------------


async def test_holds_lowest_vol_quintile() -> None:
    """Top ``ceil(N · top_quantile)`` names by score (= lowest realized vol). With
    10 names and 0.20, ceil(10·0.20)=2 → the two highest-score (lowest-vol) names."""
    order = [(f"S{i:02d}", -0.10 - 0.01 * i) for i in range(10)]  # S00 highest score → lowest vol
    ctx = _ctx([t for t, _ in order], _scores(order), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=0.20)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert set(orders) == {"S00", "S01"}
    assert all(side == "buy" for side, _ in orders.values())


async def test_equal_weight_within_book() -> None:
    """Each held name gets an equal target notional = investable / n_names."""
    order = [("AAA", -0.1), ("BBB", -0.2), ("CCC", -0.3), ("DDD", -0.4)]
    ctx = _ctx([t for t, _ in order], _scores(order), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0)  # hold all 4; $100k / 4 / $100 = 250 each
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert set(orders) == {"AAA", "BBB", "CCC", "DDD"}
    assert all(qty == Decimal(250) for _, qty in orders.values())


async def test_excludes_market_proxy_from_book() -> None:
    """SPY may be registered as a market proxy; it is never selected or
    held as a portfolio position, even with a strong (low-vol) score."""
    order = [("SPY", -0.01), ("AAA", -0.1), ("BBB", -0.2)]  # SPY has the best score
    ctx = _ctx(["SPY", "AAA", "BBB"], _scores(order), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, market_filter_symbol="SPY")
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert "SPY" not in _orders(ctx)


async def test_sells_names_leaving_the_book() -> None:
    """A held name that drops out of the lowest-vol quintile is sold to flat."""
    order = [("AAA", -0.1), ("BBB", -0.2), ("CCC", -0.9)]  # CCC = highest vol → excluded
    ctx = _ctx(
        [t for t, _ in order], _scores(order), holdings={"CCC": 10}, price=100.0, equity=100_000
    )
    strat = _strat(ctx, top_quantile=0.20)  # ceil(3·0.20)=1 → only AAA held
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx).get("CCC") == ("sell", Decimal(10))


# ---- harness fidelity + the exit-stranding characterization (LOW-PIT-01B) ------
#
# These two tests are a matched pair and must be read together.
#
# The first pins the FAKE: it proves `_ctx` reproduces production's registration
# blindness, so it cannot drift back into being more permissive than the real
# StrategyContext. Without it the tightening in `_ctx` is unenforced and a future
# edit could silently restore the false-pass condition.
#
# The second pins the PRODUCT as it behaves TODAY: a held symbol outside
# `ctx.symbols` is never discovered, so no exit intent is ever formed for it. That
# is a defect, not a desired property. It is asserted here so the repair has a
# before/after anchor -- LOW-PIT-04 / PR S will invert this test, and the day it
# starts failing is the day the fix landed.


async def test_fake_context_reproduces_production_registration_blindness() -> None:
    """The harness must hide unregistered symbols exactly as production does.

    Guards the LOW-PIT-01B finding: a fake that answers `get_position_for` or
    `get_recent_bars` for an unregistered ticker is more permissive than the real
    context, and an exit-safety test written against it passes on code that strands
    the holding live.
    """
    ctx = _ctx(["AAA"], _scores([("AAA", -0.1)]), holdings={"XYZ": 10}, price=100.0)

    # Registered -> visible.
    assert await ctx.get_position_for("AAA") is None  # registered, simply not held
    assert not (await ctx.get_recent_bars("AAA", "1Day", 1)).empty

    # Unregistered -> invisible, even though the position exists on the account.
    assert await ctx.get_position_for("XYZ") is None
    assert (await ctx.get_recent_bars("XYZ", "1Day", 1)).empty
    assert await ctx.get_positions() == []

    # ...but the order path itself is NOT gated on registration.
    assert "XYZ" not in (await ctx.pending_buy_qty())


async def test_owned_held_symbol_outside_registration_is_exited() -> None:
    """CLOSES the LOW-PIT-01B stranding defect for the normal rebalance path (PR S / S4).

    History: before S4 this test existed in inverted form
    (``test_held_symbol_outside_registration_is_never_exited_TODAY``) and asserted the
    defect. ``_current_holdings()`` enumerated ``ctx.symbols``, so a holding in an
    unregistered symbol was never a candidate, the ``sym not in target_set -> SELL`` branch
    was never reached for it, and the omission was silent. The order path would have
    accepted the sell; the intent was simply never formed.

    That is the rollback case — v1.0.2 buys XYZ dynamically, roll back to a build that does
    not know XYZ — and, under per-rebalance enrollment, the week-N-to-week-N+1 case.

    S4 makes the position book the candidate set, so the intent forms.
    """
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx(
        [t for t, _ in order],
        _scores(order),
        holdings={"XYZ": 10},  # held, NOT registered...
        owned={"XYZ"},  # ...but unambiguously ours
        price=100.0,
        equity=100_000,
    )
    strat = _strat(ctx, top_quantile=0.50)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))

    assert _orders(ctx).get("XYZ") == ("sell", Decimal(10))


async def test_visibility_alone_does_not_force_liquidation() -> None:
    """A widened holding that is still wanted must not be sold (PIT-T16, exit side).

    Making a holding visible is not a decision to exit it. ``_apply_targets`` is driven
    here directly because v1.0.1 selection cannot place an unregistered name in the target
    set — the point is that the exit rule keys on target membership, not on how the holding
    became visible.
    """
    ctx = _ctx(
        ["AAA"],
        _scores([("AAA", -0.1)]),
        holdings={"XYZ": 10},
        owned={"XYZ"},
        price=100.0,
        equity=100_000,
    )
    strat = _strat(ctx)
    await strat.on_init()
    await strat._apply_targets(["XYZ"], held={"XYZ": Decimal(10)}, reason="rebalance")

    assert _orders(ctx).get("XYZ", ("none", 0))[0] != "sell"


async def test_unowned_holdings_are_not_touched() -> None:
    """Ambiguous / unclaimed / unevidenced holdings never reach the strategy.

    The provider excludes them below ``ctx.get_holdings()``, so LOW-001 does not see them
    and cannot trade them. Modelled here as simply absent from ``owned``.
    """
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx(
        [t for t, _ in order],
        _scores(order),
        holdings={"FOREIGN": 10},  # held on the account, not ours
        owned=set(),
        price=100.0,
        equity=100_000,
    )
    strat = _strat(ctx, top_quantile=0.50)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))

    assert "FOREIGN" not in _orders(ctx)


async def test_flat_position_is_not_a_holding() -> None:
    """qty = 0 yields no holding and therefore no order."""
    ctx = _ctx(
        ["AAA"],
        _scores([("AAA", -0.1)]),
        holdings={"XYZ": 0},
        owned={"XYZ"},
        price=100.0,
        equity=100_000,
    )
    strat = _strat(ctx)
    await strat.on_init()
    assert await strat._current_holdings() == {}
    await strat.on_bar(_bar(WK1_A))
    assert "XYZ" not in _orders(ctx)


async def test_renamed_ticker_exits_under_its_current_ticker() -> None:
    """The holding is keyed by the ticker the position is held under today.

    Identity resolution happens in the provider; by the time LOW-001 sees it, a renamed
    security is simply the current ticker. The exit must be routed there.
    """
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx(
        [t for t, _ in order],
        _scores(order),
        holdings={"NEWTICK": 7},
        owned={"NEWTICK"},
        price=100.0,
        equity=100_000,
    )
    strat = _strat(ctx, top_quantile=0.50)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))

    assert _orders(ctx).get("NEWTICK") == ("sell", Decimal(7))
    assert "OLDTICK" not in _orders(ctx)


async def test_registered_holding_behaviour_is_unchanged() -> None:
    """The existing path must be untouched: a registered name leaving the book still sells."""
    order = [("AAA", -0.1), ("BBB", -0.2), ("CCC", -0.9)]
    ctx = _ctx(
        [t for t, _ in order], _scores(order), holdings={"CCC": 10}, price=100.0, equity=100_000
    )
    strat = _strat(ctx, top_quantile=0.20)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))

    assert _orders(ctx).get("CCC") == ("sell", Decimal(10))


async def test_legacy_context_without_get_holdings_stays_registered_only() -> None:
    """Against a pre-S4 runtime the template falls back to the registered scan.

    v1.0.1 behaviour is preserved exactly, including the stranding — which is why PR S must
    be deployed, not merely merged, before anything can create such a position.
    """
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx(
        [t for t, _ in order],
        _scores(order),
        holdings={"XYZ": 10},
        owned={"XYZ"},
        price=100.0,
        equity=100_000,
        legacy_context=True,
    )
    strat = _strat(ctx, top_quantile=0.50)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))

    assert "XYZ" not in _orders(ctx)


# ---- bail-out taxonomy --------------------------------------------------------


async def test_factor_unavailable_holds() -> None:
    """No factor data → HOLD the book (no orders), don't crash the tick."""
    ctx = _ctx(["AAA"], _scores([("AAA", -0.1)]))
    ctx.factors.low_vol_scores = MagicMock(side_effect=FactorDataUnavailable("no store"))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert ctx.submit_order.await_count == 0
    assert any(
        "factor_unavailable_hold" in str(c.kwargs.get("payload", {}))
        for c in ctx.log_signal.call_args_list
    )


async def test_factor_stale_holds() -> None:
    """Store more than one completed session behind the previous session → HOLD."""
    ctx = _ctx(
        ["AAA"], _scores([("AAA", -0.1)]), latest_price_date=date(2026, 6, 2)
    )  # Tue; expected Fri 6/5 → lag 3
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert ctx.submit_order.await_count == 0
    ctx.factors.low_vol_scores.assert_not_called()
    assert any(
        "factor_stale_hold" in str(c.kwargs.get("payload", {}))
        for c in ctx.log_signal.call_args_list
    )


async def test_friday_holiday_does_not_stale_hold() -> None:
    """Monday after an observed Friday holiday is fresh if the store has Thursday."""
    monday = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)
    ctx = _ctx(
        ["AAA"],
        _scores([("AAA", -0.1)]),
        latest_price_date=date(2026, 7, 2),
        equity=100_000,
    )
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(monday))
    ctx.factors.low_vol_scores.assert_called_once()
    assert not any(
        "factor_stale_hold" in str(c.kwargs.get("payload", {}))
        for c in ctx.log_signal.call_args_list
    )


async def test_spy_below_ma_does_not_liquidate() -> None:
    """LOW-001 V1 is always invested — a falling SPY is not a cash gate."""
    spy = pd.DataFrame({"c": [300.0 - i for i in range(201)]})
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx(
        ["AAA", "BBB", "SPY"], _scores(order), holdings={"AAA": 5}, equity=100_000, spy_bars=spy
    )
    strat = _strat(ctx, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert any(side == "buy" for side, _ in orders.values())
    assert orders.get("AAA") != ("sell", Decimal(5))


async def test_pit_unregistered_names_are_logged_not_ordered() -> None:
    """PIT quintile may include names outside the registered list; skip + log."""
    order = [("AAA", -0.1), ("ZZZ", -0.2), ("BBB", -0.3), ("CCC", -0.4)]
    ctx = _ctx(["AAA", "BBB", "CCC"], _scores(order), price=100.0, equity=100_000)
    strat = _strat(ctx, top_quantile=0.50)  # ceil(3 scored ex-none * 0.5) wait 4 names → 2
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert "ZZZ" not in _orders(ctx)
    assert any(
        "pit_name_not_registered" in str(c.kwargs.get("payload", {}))
        for c in ctx.log_signal.call_args_list
    )


# ---- rejection policy ---------------------------------------------------------


async def test_order_rejection_is_logged_not_raised() -> None:
    """A risk rejection on one order is logged and the rebalance continues."""
    order = [("AAA", -0.1), ("BBB", -0.2)]
    ctx = _ctx([t for t, _ in order], _scores(order), price=100.0, equity=100_000)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason="position_size_exceeded"))
    strat = _strat(ctx, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))  # must not raise
    assert any(
        "rejected" in str(c.kwargs.get("payload", {})) for c in ctx.log_signal.call_args_list
    )


async def test_fractional_shares_false_still_sizes_fractionally() -> None:
    """V1 always sizes fractionally; OrderRouter floors non-fractionable names."""
    ctx = _ctx(["AAA"], _scores([("AAA", -0.1)]), price=33.0, equity=100_000)
    strat = _strat(ctx, top_quantile=1.0, fractional_shares=False)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    qty = _orders(ctx)["AAA"][1]
    assert qty == (Decimal("100000") / Decimal("33")).quantize(Decimal("0.000001"))


async def test_inflight_buys_are_netted() -> None:
    """A retry must not stack a second basket on in-flight buys."""
    ctx = _ctx(["AAA", "BBB"], _scores([("AAA", -0.1), ("BBB", -0.2)]), price=100.0, equity=20_000)
    ctx.pending_buy_qty = AsyncMock(return_value={"AAA": Decimal("100"), "BBB": Decimal("100")})
    strat = _strat(ctx, top_quantile=1.0)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert _orders(ctx) == {}


async def test_stale_hold_does_not_complete_the_week() -> None:
    """A freshness HOLD leaves the week incomplete so a restart can retry."""
    ctx = _ctx(["AAA"], _scores([("AAA", -0.1)]), latest_price_date=date(2026, 6, 2))
    strat = _strat(ctx)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    restarted = _strat(ctx)
    await restarted.on_init()
    await restarted.on_bar(_bar(WK1_B))
    assert ctx.factors.latest_price_date.call_count == 2
    ctx.factors.low_vol_scores.assert_not_called()
