"""Regression: the SKIP baseline for entries at/after the EOD flatten cutoff, start-stamped-only
timestamps, and contradictory availability evidence. SYNTHETIC fixtures only; no performance claim.

Baseline note: refusing these entries changes kernel behaviour, so it is a NEW BASELINE. The spec
hash that will govern a market-data RUN must be frozen against this version of the kernel.
"""

from __future__ import annotations

import math
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

from app.research.range002.screen.errors import DataDefectError, ParamsUnsetError
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.report import summarize
from app.research.range002.screen.simulate import run_screen, simulate_session
from app.research.range002.screen.types import Bar
from app.research.range002.spec.loader import parse_draft
from app.research.range002.spec.schema import SCREEN_V2_UNMODELLED
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

CANDS7 = [
    {"id": "TIME", "family": "time", "params": {}},
    {"id": "R1", "family": "fixed_r", "params": {"r_multiple": 1.0}},
    {"id": "R2", "family": "fixed_r", "params": {"r_multiple": 2.0}},
    {"id": "R3", "family": "fixed_r", "params": {"r_multiple": 3.0}},
    {"id": "TRAIL", "family": "trailing", "params": {"trail_r": 1.0}},
    {"id": "SCALE_EOD", "family": "scale_out", "params": {"remainder": "eod"}},
    {"id": "SCALE_TRAIL", "family": "scale_out", "params": {"remainder": "trail", "trail_r": 1.0}},
]
HALF_CLOSE = time(13, 0)


@pytest.fixture
def kit(tmp_path: Path):  # type: ignore[no-untyped-def]
    payload = synth_payload(**{"exits__candidates": CANDS7})
    cap, _ = make_capability(tmp_path, payload)
    return cap, extract_params(cap, parse_draft(payload))


def _hm(t: time) -> str:
    return f"{t.hour}:{t.minute:02d}"


def _at(t: time, delta_min: int) -> time:
    return (datetime.combine(DAY, t) + timedelta(minutes=delta_min)).time()


def _bars(break_at: time | None, last: time, *, ambiguous: bool = False) -> list[Bar]:
    out = or_bars() + minutes_flat(
        "10:00", _hm(_at(break_at, -1)) if break_at else _hm(last), 10.05
    )
    if break_at is not None:
        out.append(
            mk(_hm(break_at), 10.09, 10.20, 9.95, 10.00)
            if ambiguous
            else mk(_hm(break_at), 10.09, 10.20, 10.08, 10.18)
        )
        if _at(break_at, 1) <= last:
            out += minutes_flat(_hm(_at(break_at, 1)), _hm(last), 10.30)
    return out


def _half_eod(params) -> time:  # type: ignore[no-untyped-def]
    return (datetime.combine(DAY, HALF_CLOSE) - timedelta(minutes=params.halfday_offset_min)).time()


def _half(bars: list[Bar], symbol: str = "AAA"):  # type: ignore[no-untyped-def]
    return session(bars, symbol, close=HALF_CLOSE)


def test_breakout_before_the_cutoff_enters_and_never_exits_before_it_entered(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    eod = _half_eod(p)
    out = simulate_session(cap, p, _half(_bars(_at(eod, -1), _at(HALF_CLOSE, -1))), TICK, EQUITY)
    assert out.state == "ENTERED" and {t.candidate_id for t in out.trades} == {
        c["id"] for c in CANDS7
    }
    for t in out.trades:
        assert t.exit_time > t.entry_time, "exit ordered before/at the entry bar"
        assert not (t.exit_reason == "EOD" and t.exit_time <= t.entry_time)
        assert t.exit_time <= HALF_CLOSE
        for v in (t.net_r_base, t.net_r_stress, t.gross_r):
            assert math.isfinite(v)
        assert t.net_r_stress <= t.net_r_base + 1e-12  # 15 bps never beats 5 bps


@pytest.mark.parametrize("delta", [0, 1, 3])
def test_breakout_at_or_after_the_cutoff_is_refused_with_its_own_reason(kit, delta: int) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    eod = _half_eod(p)
    out = simulate_session(cap, p, _half(_bars(_at(eod, delta), _at(HALF_CLOSE, -1))), TICK, EQUITY)
    assert out.state == "ENTRY_AT_OR_AFTER_EOD_CUTOFF" and out.trades == ()
    assert out.or_high is not None and out.entry_time is None


def test_full_day_cutoff_is_outside_the_entry_window_and_a_late_valid_entry_still_enters(
    kit,
) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    late = simulate_session(cap, p, session(_bars(time(15, 55), time(15, 59))), TICK, EQUITY)
    assert late.state == "NO_BREAKOUT"  # beyond entry_end: never an entry candidate
    ok = simulate_session(cap, p, session(_bars(time(14, 59), time(15, 59))), TICK, EQUITY)
    assert ok.state == "ENTERED"
    assert all(t.exit_time > t.entry_time for t in ok.trades)


def test_ambiguous_entry_bar_is_entry_then_stop_never_an_exit_before_the_entry(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    eod = _half_eod(p)
    out = simulate_session(
        cap, p, _half(_bars(_at(eod, -1), _at(HALF_CLOSE, -1), ambiguous=True)), TICK, EQUITY
    )
    assert out.state == "ENTERED"
    for t in out.trades:
        assert t.exit_reason.endswith("STOP") and t.exit_time == t.entry_time
        assert t.exit_price == pytest.approx(10.00)  # the stop, not that bar's open
        assert t.exit_reason != "EOD" and not t.exit_unexecutable


def test_funnel_reports_the_new_reason_and_reconciles(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    eod = _half_eod(p)
    sessions = [
        _half(_bars(_at(eod, -1), _at(HALF_CLOSE, -1)), "AAA"),
        _half(_bars(eod, _at(HALF_CLOSE, -1)), "BBB"),
        session(_bars(None, time(15, 59)), "CCC"),
    ]
    run = run_screen(cap, p, sessions, TICK, EQUITY)
    assert run.funnel.states["ENTRY_AT_OR_AFTER_EOD_CUTOFF"] == 1
    assert run.funnel.states["ENTERED"] == 1 and run.funnel.states["NO_BREAKOUT"] == 1
    assert sum(run.funnel.states.values()) == run.funnel.eligible == 3
    assert all(sum(v.values()) == 1 for v in run.funnel.exits.values())


def test_only_start_stamped_bars_are_accepted(tmp_path: Path) -> None:
    payload = synth_payload(**{"execution__bar_timestamp_convention": "end"})
    cap, _ = make_capability(tmp_path, payload)
    with pytest.raises(ParamsUnsetError, match="start"):
        extract_params(cap, parse_draft(payload))


def test_bar_at_a_minute_declared_gap_or_halt_is_a_defect(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    bars = _bars(time(10, 5), time(15, 59))
    for kw in ({"gaps": frozenset({time(10, 30)})}, {"halts": frozenset({time(11, 0)})}):
        with pytest.raises(DataDefectError, match="contradictory"):
            simulate_session(cap, p, session(bars, **kw), TICK, EQUITY)


def test_unmodelled_execution_settings_are_carried_and_reported(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    assert set(p.unmodelled_execution) <= set(SCREEN_V2_UNMODELLED)
    run = run_screen(cap, p, [session(_bars(time(10, 5), time(15, 59)))], TICK, EQUITY)
    s = summarize(cap, run.trades["TIME"])
    assert s["execution_realism"] == "NOT_MODELLED"
    assert set(s["unmodelled_execution_fields"]) == set(SCREEN_V2_UNMODELLED)
