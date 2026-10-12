"""Lane I: strict-xfail tests that DEMONSTRATE four build hazards on SYNTHETIC fixtures.

Each ``xfail(strict=True)`` test asserts the property that SHOULD hold. It fails today (that is the
defect); when a fix lands the test XPASSes, strict mode turns that into a failure, and the xfail
marker must then be removed in the same change. No guard-adjacent file is touched by this module.
Defect records: docs/implementation/evidence/range_002/RANGE-002_Build_Hazard_Defect_Records_v0.1.md
"""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import duckdb
import pytest

from app.research.range002.data.bar_loader import load_session
from app.research.range002.data.pit_universe import BASIS_SPLIT_ADJUSTED, UniverseParams
from app.research.range002.data.store_adapter import build_month_from_store
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.scheduler import PortfolioLimits, schedule_portfolio
from app.research.range002.screen.simulate import simulate_session
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.governance.conftest import synthetic_manifest  # noqa: F401
from tests.research.range002.screen.conftest import (
    DAY,
    EQUITY,
    TICK,
    make_capability,
    minutes_flat,
    mk,
    or_bars,
    session,
    synth_payload,
)
from tests.research.range002.screen.test_stats_scheduler import _trade

COMMON = "Domestic Common Stock"
ADR = "ADR Common Stock"
SESSIONS = [date(2026, 2, 23) + timedelta(days=i) for i in range(5)]
PARAMS = UniverseParams(n=5, adv_window=3, min_price=10.0, basis=BASIS_SPLIT_ADJUSTED)


@pytest.fixture
def cap(tmp_path: Path) -> object:
    return make_capability(tmp_path, synth_payload())[0]


def _store() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    c.execute(
        "CREATE TABLE tickers(permaticker VARCHAR, ticker VARCHAR, category VARCHAR,"
        " isdelisted VARCHAR, firstpricedate DATE, lastpricedate DATE)"
    )
    c.execute(
        f"INSERT INTO tickers VALUES ('P1','CMN','{COMMON}','N','2010-01-04','2026-02-27'),"
        f"('P2','ADRX','{ADR}','N','2010-01-04','2026-02-27')"
    )
    c.execute(
        "CREATE TABLE sep(ticker VARCHAR, date DATE, close DOUBLE, closeunadj DOUBLE, volume DOUBLE)"
    )
    for t, px, v in (("CMN", 50.0, 1_000_000), ("ADRX", 60.0, 2_000_000)):
        for d in SESSIONS:
            c.execute("INSERT INTO sep VALUES (?, ?, ?, ?, ?)", [t, d, px, px, v])
    c.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)"
    )
    return c


def _members(cap: object, categories: list[str]) -> list[str]:
    built = build_month_from_store(
        cap, _store(), date(2026, 3, 2), PARAMS, table_filter=None,
        common_stock_categories=categories, lookback_calendar_days=14,
        raw_vendor_rows_attested=True, exploratory_scope_amendment_id=None,
    )  # fmt: skip
    return [m.permaticker for m in built.universe.members]


# --- (a) price basis and category mapping live outside the spec hash --------------------------


@pytest.mark.xfail(
    strict=True,
    reason="HAZARD-A1: the category->common-stock mapping is a call argument, not a spec field",
)
def test_a1_the_universe_is_a_function_of_the_frozen_spec(cap: object) -> None:
    # same frozen spec, same snapshot: the universe must be identical. Today a caller-chosen
    # category set silently changes membership under one spec hash.
    assert _members(cap, [COMMON]) == _members(cap, [COMMON, ADR])


@pytest.mark.xfail(
    strict=True, reason="HAZARD-A2: no data.adjustment field exists; the basis is a code constant"
)
def test_a2_the_price_basis_is_declared_in_the_spec(tmp_path: Path) -> None:
    draft = parse_draft(synth_payload())
    assert hasattr(draft.data, "adjustment"), "price basis must be inside the hashed spec"


# --- (b) stored intraday bars carry no basis; the loader cannot refuse a wrong one ------------


@pytest.mark.xfail(
    strict=True,
    reason="HAZARD-B1: minute_bars has no basis tag, so a split-adjusted table is accepted silently",
)
def test_b1_a_bar_table_of_unknown_basis_is_refused(tmp_path: Path, cap: object) -> None:
    payload = synth_payload()
    params = extract_params(cap, parse_draft(payload))
    c = duckdb.connect(":memory:")
    c.execute(
        "CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE, high DOUBLE,"
        " low DOUBLE, close DOUBLE, volume BIGINT)"
    )
    # prices at a tenth of the traded scale: what a LATER 10:1 split would do to split-adjusted bars
    from datetime import datetime

    t = datetime(2026, 3, 2, 14, 30)
    for i in range(30):
        c.execute(
            "INSERT INTO minute_bars VALUES ('AAA', ?, 1.0, 1.01, 0.99, 1.0, 100)",
            [t + timedelta(minutes=i)],
        )
    with pytest.raises(Exception, match="basis"):
        load_session(
            cap, c, params, "AAA", date(2026, 3, 2), time(16, 0),
            source_feed=params.feed, source_ts_convention=params.bar_timestamp_convention,
            no_trade_evidence=frozenset(), halt_minutes=frozenset(),
        )  # fmt: skip


# --- (c) scheduler tie-break is keyed by the ticker string -------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="HAZARD-C1: same-minute ties are broken by ticker string, not issuer identity",
)
def test_c1_tie_break_is_invariant_to_relabelling_the_same_issuers(cap: object) -> None:
    limits = PortfolioLimits(
        equity=100_000.0, max_concurrent=1, gross_cap=0.9, per_name_cap=0.5, daily_loss_limit_r=9.0
    )

    def accepted_entry_price(sym_a: str, sym_b: str) -> float:
        issuer_a = _trade(
            sym_a, DAY, time(10, 0), time(15, 0), 1.0, px=11.0
        )  # issuer A: entry 11.0
        issuer_b = _trade(
            sym_b, DAY, time(10, 0), time(15, 0), 1.0, px=22.0
        )  # issuer B: entry 22.0
        run = schedule_portfolio(cap, [issuer_a, issuer_b], limits)
        assert len(run.accepted) == 1
        return run.accepted[0].entry_price

    # identical issuers, tickers swapped (e.g. a rename): the SAME issuer must win
    assert accepted_entry_price("AAA", "ZZZ") == accepted_entry_price("ZZZ", "AAA")


# --- (d) risk.per_trade_pct carries no unit ----------------------------------------------------


def test_d0_characterisation_today_the_value_is_percent_of_equity(
    tmp_path: Path, cap: object
) -> None:
    """Passes today: documents what the number means so the hazard is concrete."""
    params = extract_params(cap, parse_draft(synth_payload()))
    bars = (
        or_bars()
        + minutes_flat("10:00", "10:04", 10.05)
        + [mk("10:05", 10.09, 10.20, 10.08, 10.18)]
    )
    bars += minutes_flat("10:06", "15:59", 10.30)
    out = simulate_session(cap, params, session(bars), TICK, EQUITY)
    qty = out.trades[0].qty
    r_fill = out.trades[0].r_fill
    assert qty == int(
        EQUITY * params.per_trade_pct / 100.0 // r_fill
    )  # 0.25 means 0.25 %, not 25 %


@pytest.mark.xfail(
    strict=True,
    reason="HAZARD-D1: the unit of risk.per_trade_pct is implicit in code, absent from the spec and params",
)
def test_d1_the_unit_is_carried_explicitly(tmp_path: Path, cap: object) -> None:
    params = extract_params(cap, parse_draft(synth_payload()))
    assert getattr(params, "per_trade_pct_unit", None) == "percent_of_equity"
