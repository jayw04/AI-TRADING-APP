"""Causality at EVERY decision minute, under six perturbations of the future (SYNTHETIC).

Future prices, volume, bar presence and availability states are varied after each cut; no
decision already visible at the cut may change. Three deliberately non-causal simulations must
each be caught, so a pass is not vacuous.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import time
from pathlib import Path

import pytest

from app.research.range002.screen import simulate as _sim
from app.research.range002.screen.causal import _is_end_of_data_valuation, check_causal
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.simulate import simulate_session
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.governance.conftest import synthetic_manifest  # noqa: F401
from tests.research.range002.screen.conftest import (
    EQUITY,
    TICK,
    make_capability,
    session,
    synth_payload,
)
from tests.research.range002.screen.test_eod_cutoff_and_timestamp import (
    CANDS7,
    HALF_CLOSE,
    _at,
    _bars,
    _half,
    _half_eod,
)


@pytest.fixture
def kit(tmp_path: Path):  # type: ignore[no-untyped-def]
    payload = synth_payload(**{"exits__candidates": CANDS7})
    cap, _ = make_capability(tmp_path, payload)
    return cap, extract_params(cap, parse_draft(payload))


def _all_cuts(s):  # type: ignore[no-untyped-def]
    return [b.start for b in s.bars]


def test_full_day_breakout_is_causal_at_every_minute(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    s = session(_bars(time(10, 5), time(15, 59)))
    assert check_causal(cap, p, s, TICK, EQUITY, _all_cuts(s)) == []


def test_half_day_breakout_and_a_stop_path_are_causal_at_every_minute(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    eod = _half_eod(p)
    for ambiguous in (False, True):
        s = _half(_bars(_at(eod, -2), _at(HALF_CLOSE, -1), ambiguous=ambiguous))
        assert check_causal(cap, p, s, TICK, EQUITY, _all_cuts(s)) == []


def test_no_breakout_day_and_a_skipped_late_breakout_are_causal(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    flat = session(_bars(None, time(15, 59)))
    assert check_causal(cap, p, flat, TICK, EQUITY, _all_cuts(flat)) == []
    late = _half(_bars(_half_eod(p), _at(HALF_CLOSE, -1)))
    assert check_causal(cap, p, late, TICK, EQUITY, _all_cuts(late)) == []


def _break_or_levels(p, s, tick, equity):  # type: ignore[no-untyped-def]
    out = _sim._simulate(p, s, tick, equity)
    return replace(out, or_high=max(b.high for b in s.bars))  # peeks at the whole day


def _break_on_volume(p, s, tick, equity):  # type: ignore[no-untyped-def]
    out = _sim._simulate(p, s, tick, equity)
    return replace(out, or_high=out.or_high + 1e-6 * sum(b.volume for b in s.bars))


def _break_on_presence(p, s, tick, equity):  # type: ignore[no-untyped-def]
    out = _sim._simulate(p, s, tick, equity)
    if out.or_high is None:
        return out
    return replace(out, or_high=out.or_high + 1e-6 * len(s.bars))


@pytest.mark.parametrize(
    ("fn", "variant"),
    [
        (_break_or_levels, "price_up"),
        (_break_on_volume, "volume_zero"),
        (_break_on_presence, "drop"),
    ],
)
def test_non_causal_simulations_are_caught_by_the_matching_perturbation(kit, fn, variant) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    s = session(_bars(time(10, 5), time(15, 59)))
    cuts = [time(10, 0), time(10, 5), time(12, 0)]
    problems = check_causal(cap, p, s, TICK, EQUITY, cuts, simulate_fn=fn)
    assert problems and any(f"({variant})" in m for m in problems)


def _hide_real_stop_as_fallback(p, s, tick, equity):  # type: ignore[no-untyped-def]
    """A non-causal sim that tries to hide a future-dependent pre-cut STOP exit by relabelling it
    as the end-of-data fallback (and flagging it unexecutable)."""
    out = _sim._simulate(p, s, tick, equity)
    fut = 1e-3 * max(b.high for b in s.bars)
    hidden = tuple(
        replace(
            t,
            exit_price=t.exit_price + fut,
            exit_reason="EOD_LASTBAR_FALLBACK",
            exit_unexecutable=True,
        )
        for t in out.trades
    )
    return replace(out, trades=hidden)


def test_the_exclusion_cannot_hide_a_real_pre_cut_decision(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    s = session(_bars(time(10, 5), time(15, 59), ambiguous=True))  # stops out on the entry bar
    out = _sim._simulate(p, s, TICK, EQUITY)
    assert out.state == "ENTERED" and all(t.exit_time == t.entry_time for t in out.trades)
    problems = check_causal(
        cap, p, s, TICK, EQUITY, [time(10, 5), time(11, 0)], simulate_fn=_hide_real_stop_as_fallback
    )
    assert problems, "a relabelled pre-cut exit slipped through the end-of-data exclusion"
    assert any("price_up" in m or "price_down" in m for m in problems)


def test_only_a_verified_end_of_data_valuation_is_excluded(kit) -> None:  # type: ignore[no-untyped-def]
    cap, p = kit
    full = session(_bars(time(10, 5), time(15, 59)))
    truncated = replace(full, bars=tuple(b for b in full.bars if b.start <= time(11, 0)))
    gone = simulate_session(cap, p, truncated, TICK, EQUITY)
    assert gone.state == "ENTERED"
    fallback = [t for t in gone.trades if t.exit_unexecutable]
    assert fallback, "the TIME candidate has no EOD bar and must be valued at the fallback"
    for t in gone.trades:
        if t.exit_unexecutable:  # data ended before the EOD time: a genuine end-of-data valuation
            assert _is_end_of_data_valuation(t, truncated, p)
            assert not _is_end_of_data_valuation(t, full, p)  # same trade, but the data did NOT end
        else:  # an executable exit (target / stop) is never excluded
            assert not _is_end_of_data_valuation(t, truncated, p)
    stop = simulate_session(
        cap, p, session(_bars(time(10, 5), time(15, 59), ambiguous=True)), TICK, EQUITY
    )
    assert all(
        not _is_end_of_data_valuation(
            t, session(_bars(time(10, 5), time(15, 59), ambiguous=True)), p
        )
        for t in stop.trades
    )
