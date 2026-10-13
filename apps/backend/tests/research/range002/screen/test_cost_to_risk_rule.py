"""Optional cost-to-initial-risk eligibility (cost-aware revision): synthetic correctness only.

A pass here says nothing about any strategy's performance; no market data is used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.research.range002.screen.params import extract_params
from app.research.range002.screen.simulate import run_screen, simulate_session
from app.research.range002.screen.types import STATE_COST_INELIGIBLE, STATE_ENTERED
from app.research.range002.spec.loader import parse_draft, spec_sha256
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


def _bars(or_high: float, or_low: float, breakout: float) -> list:
    return (
        or_bars(or_high, or_low)
        + minutes_flat("10:00", "10:04", 10.05)
        + [mk("10:05", 10.09, breakout, 10.08, 10.12)]
        + minutes_flat("10:06", "15:59", 10.30)
    )


def _params(tmp_path: Path, ceiling: float | None):
    payload = synth_payload()
    if ceiling is not None:
        payload["signal"]["max_cost_to_risk"] = ceiling
    cap, _ = make_capability(tmp_path, payload)
    return cap, extract_params(cap, parse_draft(payload))


def test_absent_rule_leaves_spec_hash_and_funnel_keys_unchanged(tmp_path: Path) -> None:
    base = synth_payload()
    with_null = synth_payload()
    with_null["signal"]["max_cost_to_risk"] = None
    assert spec_sha256(parse_draft(base)) == spec_sha256(parse_draft(with_null))
    with_rule = synth_payload()
    with_rule["signal"]["max_cost_to_risk"] = 0.1
    assert spec_sha256(parse_draft(base)) != spec_sha256(parse_draft(with_rule))
    cap, params = _params(tmp_path, None)
    assert params.max_cost_to_risk is None
    run = run_screen(cap, params, [session(_bars(10.10, 10.00, 10.20))], TICK, EQUITY)
    assert STATE_COST_INELIGIBLE not in run.funnel.states


def test_ineligible_when_estimated_cost_exceeds_ceiling(tmp_path: Path) -> None:
    _, base = _params(tmp_path, None)
    est = 2 * base.base_bps_per_side / 10_000 * 10.11 / (10.11 - 10.00)
    # ceiling just above the estimate: eligible; just below: ineligible
    for ceiling, expect in ((est * 1.01, STATE_ENTERED), (est * 0.99, STATE_COST_INELIGIBLE)):
        sub = tmp_path / f"c{ceiling:.4f}"
        sub.mkdir()
        c, p = _params(sub, ceiling)
        out = simulate_session(c, p, session(_bars(10.10, 10.00, 10.20)), TICK, EQUITY)
        assert out.state == expect
        if expect == STATE_COST_INELIGIBLE:
            assert out.trades == ()


def test_rule_uses_only_the_opening_range_not_later_bars(tmp_path: Path) -> None:
    cap, base = _params(tmp_path, None)
    est = 2 * base.base_bps_per_side / 10_000 * 10.11 / (10.11 - 10.00)
    sub = tmp_path / "r"
    sub.mkdir()
    c, p = _params(sub, est * 0.99)
    a = simulate_session(c, p, session(_bars(10.10, 10.00, 10.20)), TICK, EQUITY)
    b = simulate_session(c, p, session(_bars(10.10, 10.00, 10.60)), TICK, EQUITY)
    assert a.state == b.state == STATE_COST_INELIGIBLE


def test_wide_range_stays_eligible(tmp_path: Path) -> None:
    c, p = _params(tmp_path, 0.05)
    out = simulate_session(c, p, session(_bars(10.50, 10.00, 10.60)), TICK, EQUITY)
    assert out.state == STATE_ENTERED


def test_non_positive_ceiling_refused() -> None:
    payload = synth_payload()
    payload["signal"]["max_cost_to_risk"] = -0.1
    with pytest.raises(ValueError):
        parse_draft(payload)


def test_boundary_is_inclusive(tmp_path: Path) -> None:
    from dataclasses import replace

    _, base = _params(tmp_path, None)
    trigger, risk = 10.11, 10.11 - 10.00
    est = 2.0 * base.base_bps_per_side / 10_000.0 * trigger / risk  # the kernel's expression
    sub = tmp_path / "exact"
    sub.mkdir()
    c, p = _params(sub, est)
    at = simulate_session(c, p, session(_bars(10.10, 10.00, 10.20)), TICK, EQUITY)
    assert at.state == STATE_ENTERED
    below = replace(p, max_cost_to_risk=est * (1 - 1e-12))
    out = simulate_session(c, below, session(_bars(10.10, 10.00, 10.20)), TICK, EQUITY)
    assert out.state == STATE_COST_INELIGIBLE


def test_non_positive_risk_is_invalid_not_eligible(tmp_path: Path) -> None:
    from dataclasses import replace

    from app.research.range002.screen.types import STATE_INVALID_RISK

    c, p = _params(tmp_path, 0.10)
    bad = replace(p, tick_offset=-10_000)  # trigger below the OR low: risk <= 0
    out = simulate_session(c, bad, session(_bars(10.10, 10.00, 10.20)), TICK, EQUITY)
    assert out.state == STATE_INVALID_RISK and out.trades == ()
