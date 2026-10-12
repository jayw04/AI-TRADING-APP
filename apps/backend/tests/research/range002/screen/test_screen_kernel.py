"""Synthetic correctness tests for the RANGE-002 screen kernel.

A pass here is an ENGINEERING result (the kernel is causal and arithmetically correct on planted
fixtures). It says nothing about any strategy's performance. No market data is used.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.governance.run_registry import RunStatus
from app.research.range002.screen import simulate as sim
from app.research.range002.screen.causal import check_causal
from app.research.range002.screen.errors import (
    DataDefectError,
    FunnelMismatchError,
    ParamsUnsetError,
    SpecBindingError,
)
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.report import summarize
from app.research.range002.screen.simulate import run_screen, simulate_session
from app.research.range002.screen.types import Bar, Funnel, Outcome, ScreenParams
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.screen.conftest import (
    EQUITY,
    TICK,
    make_capability,
    minutes_flat,
    mk,
    or_bars,
    session,
    synth_payload,
)

Cap = tuple[object, ScreenParams]


def day(
    breakout: Bar | None,
    rest_px: float = 10.30,
    after: list[Bar] | None = None,
    or_high: float = 10.10,
    or_low: float = 10.00,
) -> list[Bar]:
    bars = or_bars(or_high, or_low) + minutes_flat("10:00", "10:04", 10.05)
    if breakout is not None:
        bars.append(breakout)
    start = "10:06" if breakout is not None else "10:05"
    bars += minutes_flat(start, "15:59", rest_px)
    if after:
        keep = {b.start for b in after}
        bars = [b for b in bars if b.start not in keep] + after
    return bars


BREAK = mk("10:05", 10.09, 10.20, 10.08, 10.18)


# --- parameter extraction -----------------------------------------------------------------


def test_params_extracted_typed_and_bound(cap_params: Cap) -> None:
    cap, p = cap_params
    assert p.spec_sha256 == cap.spec_sha256  # type: ignore[attr-defined]
    assert p.or_end == time(9, 59, 59) and p.eod_flat == time(15, 55)
    assert [c.id for c in p.candidates] == ["TIME", "R2"]
    assert p.candidates[1].r_multiple == 2.0
    assert (p.base_bps_per_side, p.stress_bps_per_side) == (5.0, 15.0)


def test_params_fail_closed_on_unset_or_unimplemented(tmp_path: Path) -> None:
    base = synth_payload()
    cap, _ = make_capability(tmp_path, base)
    bad = synth_payload(**{"signal__or_completeness_rule": "SYNTH"})
    with pytest.raises(SpecBindingError):  # different content => different hash
        extract_params(cap, parse_draft(bad))
    for i, (path, value, needle) in enumerate(
        [
            (
                "exits__candidates",
                [{"id": "T", "family": "trailing", "params": {}}],
                "trail_r",
            ),
            ("exits__candidates", [{"id": "F", "family": "fixed_r", "params": {}}], "r_multiple"),
            ("signal__or_completeness_rule", "SYNTH", "or_completeness_rule"),
            ("costs__accounting_mode", "itemized_additive", "all_in"),
            ("execution__crossed_before_arm_policy", "REQUIRE_RETRACE", "crossed_before_arm"),
        ]
    ):
        sub = tmp_path / f"case{i}"
        sub.mkdir(exist_ok=True)
        payload = synth_payload(**{path: value})
        c2, _ = make_capability(sub, payload)
        with pytest.raises(ParamsUnsetError, match=needle):
            extract_params(c2, parse_draft(payload))


def test_extract_params_requires_capability() -> None:
    with pytest.raises(InvalidCapabilityError):
        extract_params(None, parse_draft(synth_payload()))


# --- range, entry, exits, costs ---------------------------------------------------------------


def test_or_levels_and_entry_trigger_and_time_exit(cap_params: Cap) -> None:
    cap, p = cap_params
    out = simulate_session(cap, p, session(day(BREAK)), TICK, EQUITY)
    assert out.state == "ENTERED"
    assert (out.or_high, out.or_low) == (10.10, 10.00)
    t = {x.candidate_id: x for x in out.trades}["TIME"]
    assert t.trigger == pytest.approx(10.11)
    assert t.entry_price == pytest.approx(10.11) and t.entry_time == time(10, 5)
    assert t.r_fill == pytest.approx(0.11) and not t.gapped_entry
    assert (t.exit_time, t.exit_price, t.exit_reason) == (time(15, 55), 10.30, "EOD")
    assert t.gross_r == pytest.approx((10.30 - 10.11) / 0.11)
    assert t.qty == int(EQUITY * 0.1 / 100 // 0.11)
    cost = 0.0005 * (10.11 + 10.30) / 0.11
    assert t.net_r_base == pytest.approx(t.gross_r - cost)
    assert t.net_r_stress == pytest.approx(t.gross_r - 3 * cost)


def test_fixed_r_target_fills_at_target_never_better(cap_params: Cap) -> None:
    cap, p = cap_params
    spike = mk("11:00", 10.30, 10.90, 10.29, 10.50)
    out = simulate_session(cap, p, session(day(BREAK, after=[spike])), TICK, EQUITY)
    r2 = {x.candidate_id: x for x in out.trades}["R2"]
    assert (r2.exit_reason, r2.exit_time) == ("TARGET", time(11, 0))
    assert r2.exit_price == pytest.approx(10.11 + 2 * 0.11)
    assert r2.gross_r == pytest.approx(2.0)


def test_stop_at_or_low_and_same_bar_worst_case(cap_params: Cap) -> None:
    cap, p = cap_params
    both = mk("11:00", 10.30, 10.90, 9.90, 10.30)  # touches target AND stop in one bar
    out = simulate_session(cap, p, session(day(BREAK, after=[both])), TICK, EQUITY)
    r2 = {x.candidate_id: x for x in out.trades}["R2"]
    assert (r2.exit_reason, r2.exit_price) == ("STOP", 10.00)
    assert r2.path_ambiguous and r2.gross_r == pytest.approx((10.00 - 10.11) / 0.11)


def test_entry_bar_reaching_stop_is_stopped_same_bar(cap_params: Cap) -> None:
    cap, p = cap_params
    wild = mk("10:05", 10.09, 10.20, 9.95, 10.18)
    out = simulate_session(cap, p, session(day(wild)), TICK, EQUITY)
    t = {x.candidate_id: x for x in out.trades}["TIME"]
    assert (t.exit_reason, t.exit_time) == ("STOP", time(10, 5))


def test_gap_through_stop_fills_at_open(cap_params: Cap) -> None:
    cap, p = cap_params
    gap = mk("11:00", 9.80, 9.85, 9.70, 9.75)
    out = simulate_session(cap, p, session(day(BREAK, after=[gap])), TICK, EQUITY)
    t = {x.candidate_id: x for x in out.trades}["TIME"]
    assert (t.exit_reason, t.exit_price) == ("STOP_GAP", 9.80)


def test_gap_open_entry_skip_policy_and_no_breakout_and_window(cap_params: Cap) -> None:
    cap, p = cap_params
    gap_open = mk("10:00", 10.20, 10.25, 10.19, 10.22)
    bars = or_bars() + [gap_open] + minutes_flat("10:01", "15:59", 10.22)
    assert (
        simulate_session(cap, p, session(bars), TICK, EQUITY).state == "SKIPPED_CROSSED_BEFORE_ARM"
    )
    assert simulate_session(cap, p, session(day(None, 10.05)), TICK, EQUITY).state == "NO_BREAKOUT"
    late = mk("15:00", 10.20, 10.30, 10.19, 10.25)  # after the entry window (14:59:59)
    bars = (
        or_bars()
        + minutes_flat("10:00", "14:59", 10.05)
        + [late]
        + minutes_flat("15:01", "15:59", 10.25)
    )
    assert simulate_session(cap, p, session(bars), TICK, EQUITY).state == "NO_BREAKOUT"


def test_or_incomplete_and_too_narrow(cap_params: Cap) -> None:
    cap, p = cap_params
    assert p.or_max_gap_minutes == 0  # zero confirmed DATA_GAP minutes in the opening range
    no_bar_at_0940 = [b for b in day(BREAK) if b.start != time(9, 40)]  # a gap has no bar
    one_gap = session(no_bar_at_0940, gaps=frozenset({time(9, 40)}))
    assert simulate_session(cap, p, one_gap, TICK, EQUITY).state == "OR_INCOMPLETE"
    no_bar_at_1020 = [b for b in day(BREAK) if b.start != time(10, 20)]
    outside_or = session(no_bar_at_1020, gaps=frozenset({time(10, 20)}))  # not in the opening range
    assert simulate_session(cap, p, outside_or, TICK, EQUITY).state == "ENTERED"
    narrow = session(day(BREAK, or_high=10.01, or_low=10.00))
    assert simulate_session(cap, p, narrow, TICK, EQUITY).state == "OR_TOO_NARROW"


def test_exit_not_assumed_executable_through_a_halt_to_the_close(cap_params: Cap) -> None:
    cap, p = cap_params
    bars = or_bars() + minutes_flat("10:00", "10:04", 10.05) + [BREAK]
    bars += minutes_flat("10:06", "14:00", 10.30)  # trades stop at 14:00; halted to the close
    halted = frozenset(time(h, m) for h in range(14, 16) for m in range(60) if (h, m) >= (14, 1))
    out = simulate_session(cap, p, session(bars, halts=halted), TICK, EQUITY)
    t = {x.candidate_id: x for x in out.trades}["TIME"]
    assert t.exit_unexecutable and t.exit_reason == "EOD_LASTBAR_FALLBACK"
    assert t.exit_price == pytest.approx(10.00)  # worse of last close 10.30 and the stop 10.00
    assert t.gross_r == pytest.approx((10.00 - 10.11) / 0.11)


def test_reopen_below_stop_after_halt_fills_at_reopen_open_and_is_flagged(cap_params: Cap) -> None:
    cap, p = cap_params
    reopen = mk("11:30", 9.70, 9.75, 9.65, 9.72)
    bars = day(BREAK, rest_px=10.30)
    bars = [b for b in bars if not (time(11, 0) <= b.start <= time(11, 30))] + [reopen]
    halted = frozenset(time(11, m) for m in range(0, 30))
    out = simulate_session(cap, p, session(bars, halts=halted), TICK, EQUITY)
    t = {x.candidate_id: x for x in out.trades}["TIME"]
    assert (t.exit_reason, t.exit_price, t.exit_time) == ("STOP_GAP", 9.70, time(11, 30))
    assert t.exit_after_unavailable and not t.exit_unexecutable


def test_eod_during_halt_fills_at_first_available_bar_after_reopen(cap_params: Cap) -> None:
    cap, p = cap_params
    bars = [b for b in day(BREAK) if not (time(15, 50) <= b.start < time(15, 58))]
    halted = frozenset(time(15, m) for m in range(50, 58))
    out = simulate_session(cap, p, session(bars, halts=halted), TICK, EQUITY)
    t = {x.candidate_id: x for x in out.trades}["TIME"]
    assert (t.exit_reason, t.exit_time) == ("EOD", time(15, 58))
    assert t.exit_after_unavailable and not t.exit_unexecutable


def test_half_day_flattens_before_early_close(cap_params: Cap) -> None:
    cap, p = cap_params
    bars = (
        or_bars()
        + minutes_flat("10:00", "10:04", 10.05)
        + [BREAK]
        + minutes_flat("10:06", "12:59", 10.30)
    )
    out = simulate_session(cap, p, session(bars, close=time(13, 0)), TICK, EQUITY)
    t = {x.candidate_id: x for x in out.trades}["TIME"]
    assert (t.exit_time, t.exit_reason) == (time(12, 56), "EOD")  # 13:00 - halfday_offset 4


# --- funnel, defects, capability -----------------------------------------------------------


def test_funnel_reconciles_over_mixed_sessions(cap_params: Cap) -> None:
    cap, p = cap_params
    sessions = [
        session(day(BREAK), "AAA"),
        session(day(None, 10.05), "BBB"),
        session(day(BREAK, or_high=10.01), "CCC"),
        session(day(BREAK), "DDD", day=date(2026, 3, 3)),
    ]
    run = run_screen(cap, p, sessions, TICK, EQUITY)
    f = run.funnel
    assert f.eligible == 4 and sum(f.states.values()) == 4
    assert f.states["ENTERED"] == 2 and f.states["NO_BREAKOUT"] == 1
    assert sum(f.exits["TIME"].values()) == 2 == len(run.trades["TIME"])
    assert run.citable is False  # REPLAY partition output is never citable
    assert run_screen(cap, p, reversed(sessions), TICK, EQUITY) == run  # order independent


def test_funnel_mismatch_is_refused(cap_params: Cap) -> None:
    cap, _ = cap_params
    with pytest.raises(FunnelMismatchError):
        sim.reconcile_funnel(cap, Funnel(3, {"ENTERED": 1, "NO_BREAKOUT": 1}, {"TIME": {"EOD": 1}}))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: replace(s, feed="iex"),
        lambda s: replace(s, ts_convention="end"),
        lambda s: replace(s, bars=tuple(reversed(s.bars))),
        lambda s: replace(s, day=date(2026, 8, 3)),  # outside the capability's range
        lambda s: replace(s, bars=s.bars[:-1] + (mk("15:59", 10.0, 9.0, 9.5, 9.7),)),
    ],
)
def test_data_defects_raise_not_verdict(cap_params: Cap, mutate: Any) -> None:
    cap, p = cap_params
    with pytest.raises(DataDefectError):
        simulate_session(cap, p, mutate(session(day(BREAK))), TICK, EQUITY)


def test_duplicate_symbol_day_refused(cap_params: Cap) -> None:
    cap, p = cap_params
    with pytest.raises(DataDefectError):
        run_screen(cap, p, [session(day(BREAK)), session(day(BREAK))], TICK, EQUITY)


def test_params_bound_to_capability_spec(tmp_path: Path, cap_params: Cap) -> None:
    cap, p = cap_params
    other_payload = synth_payload(**{"universe__n": 4})
    sub = tmp_path / "other"
    sub.mkdir()
    cap2, _ = make_capability(sub, other_payload)
    with pytest.raises(SpecBindingError):
        simulate_session(cap2, p, session(day(BREAK)), TICK, EQUITY)


def test_every_entry_point_needs_a_capability(cap_params: Cap) -> None:
    _, p = cap_params
    s = session(day(BREAK))
    with pytest.raises(InvalidCapabilityError):
        simulate_session(None, p, s, TICK, EQUITY)
    with pytest.raises(InvalidCapabilityError):
        run_screen(object(), p, [s], TICK, EQUITY)
    with pytest.raises(InvalidCapabilityError):
        summarize(None, [])
    with pytest.raises(InvalidCapabilityError):
        check_causal(None, p, s, TICK, EQUITY, [time(10, 30)])


def test_closed_run_revokes_kernel_use(tmp_path: Path) -> None:
    payload = synth_payload()
    cap, _ = make_capability(tmp_path, payload)
    p = extract_params(cap, parse_draft(payload))
    from app.research.range002.governance.results_guard import _BOUND_REGISTRIES  # noqa: PLC2701

    reg = _BOUND_REGISTRIES[cap]
    reg.close_run(cap.run_id, RunStatus.ABORTED, None)  # type: ignore[attr-defined]
    with pytest.raises(InvalidCapabilityError):
        simulate_session(cap, p, session(day(BREAK)), TICK, EQUITY)


# --- causality (the harness must also FAIL look-ahead code) ------------------------------------

CUTS = [time(9, 45), time(10, 0), time(10, 5), time(10, 30), time(12, 0), time(15, 54)]


def test_builtin_simulation_is_causal(cap_params: Cap) -> None:
    cap, p = cap_params
    spike = mk("11:00", 10.30, 10.90, 10.29, 10.50)
    stop = mk("13:00", 10.20, 10.20, 9.90, 9.95)
    for bars in (day(BREAK), day(None, 10.05), day(BREAK, after=[spike]), day(BREAK, after=[stop])):
        assert check_causal(cap, p, session(bars), TICK, EQUITY, CUTS) == []


def test_harness_detects_or_lookahead(cap_params: Cap) -> None:
    cap, p = cap_params

    def cheat(params: ScreenParams, s: Any, tick: float, eq: float) -> Outcome:
        hi = max(b.high for b in s.bars)  # opening range "contaminated" by the whole day
        fixed = tuple(
            replace(b, high=max(b.high, hi)) if b.start <= params.or_end else b for b in s.bars
        )
        return sim._simulate(params, replace(s, bars=fixed), tick, eq)

    problems = check_causal(cap, p, session(day(BREAK)), TICK, EQUITY, CUTS, simulate_fn=cheat)
    assert problems and "decision visible" in problems[0]


def test_harness_detects_exit_lookahead(cap_params: Cap) -> None:
    cap, p = cap_params
    spike = mk("11:00", 10.30, 10.90, 10.29, 10.50)

    def cheat(params: ScreenParams, s: Any, tick: float, eq: float) -> Outcome:
        out = sim._simulate(params, s, tick, eq)  # exits at the day's high bar: hindsight
        top = max(s.bars, key=lambda b: b.high)
        return replace(
            out,
            trades=tuple(
                replace(t, exit_time=top.start, exit_price=top.high, exit_reason="HINDSIGHT")
                for t in out.trades
            ),
        )

    problems = check_causal(
        cap, p, session(day(BREAK, after=[spike])), TICK, EQUITY, CUTS, simulate_fn=cheat
    )
    assert problems


# --- report ---------------------------------------------------------------------------------


def test_summary_arithmetic_and_undefined_concentration(cap_params: Cap) -> None:
    cap, p = cap_params
    win = [
        session(
            day(BREAK, after=[mk("11:00", 10.30, 10.90, 10.29, 10.50)]), s, day=date(2026, 3, 2 + i)
        )
        for i, s in enumerate(["A", "B", "C", "D", "E", "F", "G"])
    ]
    run = run_screen(cap, p, win, TICK, EQUITY)
    rep = summarize(cap, run.trades["R2"])
    assert rep["trades"] == 7 and rep["traded_days"] == 7
    assert rep["base"]["profit_factor"] is None  # no losing trade: undefined, not infinity
    assert rep["base"]["mean_net_r"] == pytest.approx(rep["base"]["total_net_r"] / 7)
    assert rep["net_r_after_removing_top5"] is not None
    assert rep["best_day_share_of_net"] == pytest.approx(1 / 7)
    losing = run_screen(cap, p, [session(day(replace(BREAK, low=9.9)), "Z")], TICK, EQUITY)
    rep2 = summarize(cap, losing.trades["R2"])
    assert rep2["base"]["total_net_r"] < 0 and rep2["best_day_share_of_net"] is None


def test_trailing_and_scale_out_exits(tmp_path: Path) -> None:
    cands = [
        {"id": "E3A", "family": "trailing", "params": {"trail_r": 1.0}},
        {"id": "E4A", "family": "scale_out", "params": {"remainder": "eod"}},
        {"id": "E4B", "family": "scale_out", "params": {"remainder": "trail", "trail_r": 1.0}},
    ]
    payload = synth_payload(**{"exits__candidates": cands})
    cap, _ = make_capability(tmp_path, payload)
    p = extract_params(cap, parse_draft(payload))
    arm = mk("10:30", 10.20, 10.25, 10.20, 10.24)  # reaches +1R (10.22); close 10.24
    dip = mk("11:00", 10.20, 10.20, 10.12, 10.15)  # trails: stop 10.24 - 0.11 = 10.13
    bars = day(BREAK, rest_px=10.15, after=[arm, dip])
    out = simulate_session(cap, p, session(bars), TICK, EQUITY)
    t = {x.candidate_id: x for x in out.trades}
    assert (t["E3A"].exit_reason, t["E3A"].exit_price) == ("TRAIL_STOP", pytest.approx(10.13))
    assert t["E3A"].gross_r == pytest.approx((10.13 - 10.11) / 0.11)
    assert t["E4A"].scaled_out and t["E4A"].exit_reason == "EOD"
    assert t["E4A"].gross_r == pytest.approx((0.5 * (10.22 - 10.11) + 0.5 * (10.15 - 10.11)) / 0.11)
    assert t["E4B"].exit_reason == "TRAIL_STOP"
    assert t["E4B"].gross_r == pytest.approx((0.5 * 0.11 + 0.5 * 0.02) / 0.11)
    cost = 0.0005 * (10.11 + 0.5 * 10.22 + 0.5 * 10.13) / 0.11
    assert t["E4B"].net_r_base == pytest.approx(t["E4B"].gross_r - cost)
    assert check_causal(cap, p, session(bars), TICK, EQUITY, CUTS) == []
