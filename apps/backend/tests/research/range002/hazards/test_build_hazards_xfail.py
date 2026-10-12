"""Lane B: regressions for the four RANGE-002 build hazards (A-D), on SYNTHETIC fixtures only.

These began life (Lane I) as strict-xfail demonstrations; the fixes landed on branch
``fix/range002-build-hazards`` and every test is now an ordinary passing regression. The file
keeps its historical name. Each hazard keeps explicit NEGATIVE tests proving the original defect
is now detected, not merely absent.

Defect records: docs/implementation/evidence/range_002/RANGE-002_Build_Hazard_Defect_Records_v0.1.md
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest

from app.research.range002.data.bar_loader import load_session
from app.research.range002.data.pit_universe import BASIS_SPLIT_ADJUSTED, UniverseParams
from app.research.range002.data.store_adapter import (
    COMPATIBLE_PRICE_BASIS_PAIRS,
    build_month_from_store,
    universe_params_from_draft,
)
from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.screen.errors import DataDefectError, ParamsUnsetError
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.scheduler import PortfolioLimits, schedule_portfolio
from app.research.range002.screen.simulate import simulate_session
from app.research.range002.spec.loader import SpecSchemaError, parse_draft, spec_sha256
from app.research.range002.spec.schema import SCREEN_V1_REQUIRED_SHA256
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
TIE = "PERMATICKER_ASC"


@pytest.fixture
def cap(tmp_path: Path) -> object:
    return make_capability(tmp_path, synth_payload())[0]


def _cap_for(tmp_path: Path, name: str, payload: dict[str, Any]) -> object:
    d = tmp_path / name
    d.mkdir()
    return make_capability(d, payload)[0]


def _v1_payload(**nulls: Any) -> dict[str, Any]:
    """A screen-profile v1 spec: the hazard A/B/D fields are v1-exempt, so they may be null here
    and still freeze; the data/kernel entry points must then refuse them."""
    payload = synth_payload(**nulls)
    payload["profile"] = {
        "name": "screen",
        "version": 1,
        "required_fields_sha256": SCREEN_V1_REQUIRED_SHA256,
    }
    return payload


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


def _universe_params(cap: object, payload: dict[str, Any]) -> UniverseParams:
    p = universe_params_from_draft(cap, parse_draft(payload))
    # the spec pins adv_window_days=20; the synthetic store has five sessions
    return dataclasses.replace(p, n=5, adv_window=3)


def _members(cap: object, params: UniverseParams) -> list[str]:
    built = build_month_from_store(
        cap, _store(), date(2026, 3, 2), params, table_filter=None,
        lookback_calendar_days=14, raw_vendor_rows_attested=True,
        exploratory_scope_amendment_id=None,
    )  # fmt: skip
    return [m.permaticker for m in built.universe.members]


# --- (a) price basis and category mapping are inside the spec hash ----------------------------


def test_a1_the_universe_is_a_function_of_the_frozen_spec(cap: object) -> None:
    params = _universe_params(cap, synth_payload())
    assert params.category_map == (COMMON,)  # read from the frozen spec, not a call argument
    first = _members(cap, params)
    assert first == ["P1"] and _members(cap, params) == first  # same spec + snapshot, same set


def test_a1n_a_different_category_map_is_a_different_spec_and_a_different_universe(
    tmp_path: Path,
) -> None:
    narrow = synth_payload()
    wide = synth_payload(**{"universe__category_map": [COMMON, ADR]})
    assert spec_sha256(parse_draft(narrow)) != spec_sha256(parse_draft(wide))  # hash-bound
    cap_n, cap_w = _cap_for(tmp_path, "n", narrow), _cap_for(tmp_path, "w", wide)
    assert _members(cap_n, _universe_params(cap_n, narrow)) == ["P1"]
    assert _members(cap_w, _universe_params(cap_w, wide)) == ["P2", "P1"]


def test_a1n_building_with_a_category_set_that_is_not_the_specs_is_impossible(
    cap: object, tmp_path: Path
) -> None:
    params = _universe_params(cap, synth_payload())
    with pytest.raises(InvalidCapabilityError, match="common_stock_categories"):  # arg is gone
        build_month_from_store(
            cap, _store(), date(2026, 3, 2), params, table_filter=None,
            common_stock_categories=[COMMON, ADR],  # type: ignore[call-arg]
            lookback_calendar_days=14, raw_vendor_rows_attested=True,
            exploratory_scope_amendment_id=None,
        )  # fmt: skip
    unset = dataclasses.replace(params, category_map=())  # an unset map is refused, never guessed
    with pytest.raises(ParamsUnsetError, match="category_map"):
        _members(cap, unset)
    null_spec = _v1_payload(**{"universe__category_map": None})
    with pytest.raises(ParamsUnsetError, match="category_map"):  # null in the spec: refused
        universe_params_from_draft(_cap_for(tmp_path, "x", null_spec), parse_draft(null_spec))


def test_a2_the_price_basis_is_declared_in_the_spec() -> None:
    draft = parse_draft(synth_payload())
    assert draft.data.daily_price_basis == BASIS_SPLIT_ADJUSTED
    assert draft.data.intraday_price_basis == "raw"
    assert COMPATIBLE_PRICE_BASIS_PAIRS == ((BASIS_SPLIT_ADJUSTED, "raw"),)


def test_a2n_the_price_basis_is_hash_bound_and_an_incompatible_pair_is_refused(
    tmp_path: Path,
) -> None:
    base = synth_payload()
    other_daily = synth_payload(**{"data__daily_price_basis": "SEP_UNADJUSTED"})
    other_intraday = synth_payload(**{"data__intraday_price_basis": "split_adjusted"})
    h = spec_sha256(parse_draft(base))
    assert h != spec_sha256(parse_draft(other_daily))
    assert h != spec_sha256(parse_draft(other_intraday))
    for i, bad in enumerate((other_daily, other_intraday)):
        cap = _cap_for(tmp_path, f"b{i}", bad)
        with pytest.raises(DataDefectError, match="incompatible join"):
            universe_params_from_draft(cap, parse_draft(bad))
    nulled = _v1_payload(**{"data__daily_price_basis": None})
    with pytest.raises(ParamsUnsetError, match="price_basis"):
        universe_params_from_draft(_cap_for(tmp_path, "c", nulled), parse_draft(nulled))


# --- (b) stored intraday bars carry a basis tag; the loader refuses a wrong one ---------------


def _bars_table(*, basis_column: bool, basis: Any = "raw") -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    extra = ", basis VARCHAR" if basis_column else ""
    c.execute(
        "CREATE TABLE minute_bars(symbol VARCHAR, ts TIMESTAMP, open DOUBLE, high DOUBLE,"
        f" low DOUBLE, close DOUBLE, volume BIGINT{extra})"
    )
    t = datetime(2026, 3, 2, 14, 30)
    for i in range(30):
        ts = t + timedelta(minutes=i)
        if basis_column:
            c.execute(
                "INSERT INTO minute_bars VALUES ('AAA', ?, 1.0, 1.01, 0.99, 1.0, 100, ?)",
                [ts, basis],
            )
        else:
            c.execute("INSERT INTO minute_bars VALUES ('AAA', ?, 1.0, 1.01, 0.99, 1.0, 100)", [ts])
    return c


def _load(cap: object, con: Any, **over: Any) -> Any:
    params = extract_params(cap, parse_draft(synth_payload()))
    kw: dict[str, Any] = {
        "permaticker": "P-AAA",
        "source_feed": params.feed,
        "source_ts_convention": params.bar_timestamp_convention,
        "no_trade_evidence": frozenset(),
        "halt_minutes": frozenset(),
    }
    kw.update(over)
    return load_session(cap, con, params, "AAA", date(2026, 3, 2), time(16, 0), **kw)


def test_b1_a_bar_table_of_unknown_basis_is_refused(cap: object) -> None:
    with pytest.raises(DataDefectError, match="basis"):
        _load(cap, _bars_table(basis_column=False))


def test_b1_a_table_tagged_with_the_specs_basis_loads(cap: object) -> None:
    s = _load(cap, _bars_table(basis_column=True, basis="raw"))
    assert s is not None and len(s.bars) == 30 and s.permaticker == "P-AAA"


@pytest.mark.parametrize("basis", [None, "split_adjusted", "adjusted", "RAW"])
def test_b1n_a_null_or_different_basis_is_refused(cap: object, basis: Any) -> None:
    with pytest.raises(DataDefectError, match="basis"):
        _load(cap, _bars_table(basis_column=True, basis=basis))


def test_b1n_one_stray_row_of_another_basis_poisons_the_session(cap: object) -> None:
    con = _bars_table(basis_column=True, basis="raw")
    con.execute(
        "UPDATE minute_bars SET basis = 'split_adjusted' WHERE ts = TIMESTAMP '2026-03-02 14:45:00'"
    )
    with pytest.raises(DataDefectError, match="basis"):
        _load(cap, con)


def test_b1n_a_missing_permaticker_is_refused(cap: object) -> None:
    with pytest.raises(DataDefectError, match="permaticker"):
        _load(cap, _bars_table(basis_column=True), permaticker=" ")


# --- (c) scheduler tie-break is keyed by issuer identity --------------------------------------

LIMITS = PortfolioLimits(
    equity=100_000.0, max_concurrent=1, gross_cap=0.9, per_name_cap=0.5, daily_loss_limit_r=9.0
)


def _accepted_entry_price(cap: object, sym_a: str, sym_b: str) -> float:
    issuer_a = _trade(sym_a, DAY, time(10, 0), time(15, 0), 1.0, px=11.0, permaticker="P-A")
    issuer_b = _trade(sym_b, DAY, time(10, 0), time(15, 0), 1.0, px=22.0, permaticker="P-B")
    run = schedule_portfolio(cap, [issuer_b, issuer_a], LIMITS, tie_break=TIE)
    assert len(run.accepted) == 1
    return run.accepted[0].entry_price


def test_c1_tie_break_is_invariant_to_relabelling_the_same_issuers(cap: object) -> None:
    # identical issuers, tickers swapped (e.g. a rename): the SAME issuer must win
    assert _accepted_entry_price(cap, "AAA", "ZZZ") == _accepted_entry_price(cap, "ZZZ", "AAA")
    assert _accepted_entry_price(cap, "AAA", "ZZZ") == 11.0  # ascending permaticker: P-A first


def test_c1n_swapping_the_tickers_of_the_same_two_issuers_gives_the_same_accepted_issuer(
    cap: object,
) -> None:
    a = _trade("ZZZ", DAY, time(10, 0), time(15, 0), 1.0, px=11.0, permaticker="P-A")
    b = _trade("AAA", DAY, time(10, 0), time(15, 0), 1.0, px=22.0, permaticker="P-B")
    run = schedule_portfolio(cap, [a, b], LIMITS, tie_break=TIE)
    # the old key (ticker string) would have accepted AAA, i.e. issuer P-B
    assert [t.permaticker for t in run.accepted] == ["P-A"]


def test_c1n_a_trade_with_an_empty_permaticker_is_refused(cap: object) -> None:
    ok = _trade("AAA", DAY, time(10, 0), time(15, 0), 1.0, permaticker="P-A")
    bad = _trade("BBB", DAY, time(10, 0), time(15, 0), 1.0, permaticker=" ")
    with pytest.raises(DataDefectError, match="permaticker"):
        schedule_portfolio(cap, [ok, bad], LIMITS, tie_break=TIE)


@pytest.mark.parametrize("policy", ["TICKER_ASC", "permaticker_asc", "", "RANDOM"])
def test_c1n_any_tie_break_other_than_the_frozen_policy_is_refused(
    cap: object, policy: str
) -> None:
    t = _trade("AAA", DAY, time(10, 0), time(15, 0), 1.0)
    with pytest.raises(ParamsUnsetError, match="tie_break"):
        schedule_portfolio(cap, [t], LIMITS, tie_break=policy)


def test_c1_the_same_issuer_cannot_be_open_twice_under_a_new_ticker(cap: object) -> None:
    first = _trade("OLD", DAY, time(10, 0), time(15, 0), 1.0, permaticker="P-A")
    renamed = _trade("NEW", DAY, time(10, 5), time(15, 0), 1.0, permaticker="P-A")
    lim = dataclasses.replace(LIMITS, max_concurrent=5)
    run = schedule_portfolio(cap, [first, renamed], lim, tie_break=TIE)
    assert [t.symbol for t in run.accepted] == ["OLD"]


# --- (d) risk.per_trade_pct carries an explicit unit ------------------------------------------


def _first_trade_qty(cap: object, payload: dict[str, Any]) -> tuple[int, float]:
    params = extract_params(cap, parse_draft(payload))
    bars = (
        or_bars()
        + minutes_flat("10:00", "10:04", 10.05)
        + [mk("10:05", 10.09, 10.20, 10.08, 10.18)]
    )
    bars += minutes_flat("10:06", "15:59", 10.30)
    out = simulate_session(cap, params, session(bars), TICK, EQUITY)
    return out.trades[0].qty, out.trades[0].r_fill


def test_d0_percent_unit_preserves_the_previous_interpretation(tmp_path: Path) -> None:
    payload = synth_payload(**{"risk__per_trade_pct": 0.25, "risk__per_trade_unit": "percent"})
    cap = _cap_for(tmp_path, "d0", payload)
    qty, r_fill = _first_trade_qty(cap, payload)
    # the kernel's historic result: 0.25 meant 0.25 % of equity
    assert qty == int(EQUITY * 0.25 / 100.0 // r_fill)


def test_d1_the_unit_is_carried_explicitly(cap: object) -> None:
    params = extract_params(cap, parse_draft(synth_payload()))
    assert params.per_trade_pct_unit == "percent"
    assert params.per_trade_fraction == pytest.approx(params.per_trade_pct / 100.0)


def test_d1_percent_and_fraction_spellings_of_one_quantity_are_the_same_size(
    tmp_path: Path,
) -> None:
    pct = synth_payload(**{"risk__per_trade_pct": 0.25, "risk__per_trade_unit": "percent"})
    frac = synth_payload(**{"risk__per_trade_pct": 0.0025, "risk__per_trade_unit": "fraction"})
    q_pct, _ = _first_trade_qty(_cap_for(tmp_path, "p", pct), pct)
    q_frac, _ = _first_trade_qty(_cap_for(tmp_path, "f", frac), frac)
    assert q_pct == q_frac and q_pct > 0


def test_d1n_the_same_number_under_another_unit_is_100x_the_size_and_another_spec(
    tmp_path: Path,
) -> None:
    pct = synth_payload(**{"risk__per_trade_pct": 0.25, "risk__per_trade_unit": "percent"})
    frac = synth_payload(**{"risk__per_trade_pct": 0.25, "risk__per_trade_unit": "fraction"})
    assert spec_sha256(parse_draft(pct)) != spec_sha256(parse_draft(frac))  # unit is hash-bound
    q_pct, r_fill = _first_trade_qty(_cap_for(tmp_path, "p", pct), pct)
    q_frac, _ = _first_trade_qty(_cap_for(tmp_path, "f", frac), frac)
    assert q_frac == int(EQUITY * 0.25 // r_fill)
    assert q_frac / q_pct == pytest.approx(100.0, rel=0.01)


def test_d1n_a_derived_fraction_outside_the_open_unit_interval_is_refused(
    tmp_path: Path,
) -> None:
    cases = [(1.0, "fraction"), (1.5, "fraction"), (100.0, "percent"), (250.0, "percent")]
    for i, (value, unit) in enumerate(cases):
        payload = synth_payload(**{"risk__per_trade_pct": value, "risk__per_trade_unit": unit})
        cap = _cap_for(tmp_path, f"hi{i}", payload)
        with pytest.raises(ParamsUnsetError, match="open interval"):
            extract_params(cap, parse_draft(payload))
    for value in (0.0, -0.25):  # <= 0 is refused at the schema (finite positive)
        with pytest.raises(SpecSchemaError):
            parse_draft(synth_payload(**{"risk__per_trade_pct": value}))


def test_d1n_a_null_or_unknown_unit_is_refused(tmp_path: Path) -> None:
    payload = _v1_payload(**{"risk__per_trade_unit": None})
    cap = _cap_for(tmp_path, "nu", payload)
    with pytest.raises(ParamsUnsetError, match="per_trade_unit"):
        extract_params(cap, parse_draft(payload))
    with pytest.raises(SpecSchemaError):  # unknown unit spelling
        parse_draft(synth_payload(**{"risk__per_trade_unit": "bps"}))
