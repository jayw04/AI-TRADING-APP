"""Unit tests for the dormant baseline-residual calculation.

Scope note: these exercise ARITHMETIC AND CLASSIFICATION ONLY. The module is unreferenced by the
runtime and performs no I/O, so nothing here characterises any real account, and no conclusion
about broker behaviour may be drawn from these fixtures — that requires an acquisition decision
and real captured evidence, not synthetic inputs.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.daily_baseline_residual import (
    DEFAULT_RECONCILIATION_TOLERANCE,
    REASON_ACTIVITY_SINCE_BOUNDARY,
    REASON_MISSING_PRICE,
    REASON_NO_BROKER_BASELINE,
    REASON_NON_POSITIVE_PRICE,
    STATUS_RECONCILED,
    STATUS_TIGHTENING,
    STATUS_UNAVAILABLE,
    STATUS_WEAKENING,
    observe_residual,
    reconstruct_prior_close_equity,
)

D = Decimal

QTY = {"AAA": D("10"), "BBB": D("3")}
CLOSES = {"AAA": D("100.00"), "BBB": D("50.00")}
CASH = D("250.00")
# 10*100 + 3*50 + 250
EXPECTED = D("1400.00")


def _observe(broker, **kw):
    params = dict(
        broker_last_equity=broker, cash=CASH, quantities=QTY,
        prior_closes=CLOSES, activity_since_boundary=False,
    )
    params.update(kw)
    return observe_residual(**params)


# ------------------------------------------------------------------ reconstruction

def test_reconstruction_is_cash_plus_qty_times_close():
    assert reconstruct_prior_close_equity(
        cash=CASH, quantities=QTY, prior_closes=CLOSES
    ) == EXPECTED


def test_reconstruction_is_exact_in_decimal():
    """Fractional share counts must not accumulate binary-float drift."""
    qty = {f"S{i}": D("0.1") for i in range(10)}
    closes = {f"S{i}": D("3.33") for i in range(10)}

    got = reconstruct_prior_close_equity(cash=D(0), quantities=qty, prior_closes=closes)

    assert got == D("3.330")  # 10 × (0.1 × 3.33), exactly


def test_zero_quantity_positions_need_no_price():
    """A closed-out symbol still present in the map must not force RECONSTRUCTION_UNAVAILABLE."""
    got = reconstruct_prior_close_equity(
        cash=CASH, quantities={**QTY, "GONE": D(0)}, prior_closes=CLOSES
    )

    assert got == EXPECTED


def test_missing_price_raises_rather_than_valuing_partially():
    with pytest.raises(KeyError):
        reconstruct_prior_close_equity(
            cash=CASH, quantities={**QTY, "CCC": D("1")}, prior_closes=CLOSES
        )


def test_non_positive_price_is_rejected():
    with pytest.raises(ValueError):
        reconstruct_prior_close_equity(
            cash=CASH, quantities={"AAA": D("1")}, prior_closes={"AAA": D("0")}
        )


# ------------------------------------------------------------------ classification

def test_exact_agreement_reconciles():
    obs = _observe(EXPECTED)

    assert obs.status == STATUS_RECONCILED
    assert obs.residual == D(0)
    assert obs.residual_sign == 0
    assert obs.position_count == 2
    assert obs.reconstructed


@pytest.mark.parametrize("delta", [D("0.23"), D("-0.23"), DEFAULT_RECONCILIATION_TOLERANCE])
def test_within_tolerance_reconciles_in_both_directions(delta):
    """A late-booked regulatory fee is the mechanism the band exists for."""
    assert _observe(EXPECTED + delta).status == STATUS_RECONCILED


def test_positive_residual_beyond_tolerance_is_tightening():
    obs = _observe(EXPECTED + D("216.73"))

    assert obs.status == STATUS_TIGHTENING
    assert obs.residual == D("216.73")
    assert obs.residual_sign == 1


def test_negative_residual_beyond_tolerance_is_weakening():
    obs = _observe(EXPECTED - D("216.73"))

    assert obs.status == STATUS_WEAKENING
    assert obs.residual == D("-216.73")
    assert obs.residual_sign == -1


def test_weakening_escalates_at_the_reconciliation_band_not_the_material_one():
    """THE SIGN RULE: a small weakening residual is not 'immaterial' — the gate is loose."""
    obs = _observe(EXPECTED - D("1.01"), material_threshold=D("100"))

    assert obs.status == STATUS_WEAKENING
    assert obs.material is False, "sign escalation must not depend on the materiality flag"


def test_material_flag_is_independent_of_direction():
    tightening = _observe(EXPECTED + D("2628.28"), material_threshold=D("100"))
    weakening = _observe(EXPECTED - D("2628.28"), material_threshold=D("100"))

    assert tightening.status == STATUS_TIGHTENING and tightening.material
    assert weakening.status == STATUS_WEAKENING and weakening.material


# ------------------------------------------------------------------- unavailable

def test_activity_since_boundary_refuses_to_reconstruct():
    """Current positions do not describe the prior boundary once trading has occurred."""
    obs = _observe(EXPECTED, activity_since_boundary=True)

    assert obs.status == STATUS_UNAVAILABLE
    assert obs.reason == REASON_ACTIVITY_SINCE_BOUNDARY
    assert obs.residual is None
    assert obs.residual_sign is None
    assert not obs.reconstructed


def test_absent_broker_baseline_is_unavailable_not_zero():
    obs = _observe(None)

    assert obs.status == STATUS_UNAVAILABLE
    assert obs.reason == REASON_NO_BROKER_BASELINE
    assert obs.residual is None


def test_missing_price_is_unavailable():
    obs = _observe(EXPECTED, quantities={**QTY, "CCC": D("1")})

    assert obs.status == STATUS_UNAVAILABLE
    assert obs.reason == REASON_MISSING_PRICE


def test_non_positive_price_is_unavailable():
    obs = _observe(EXPECTED, quantities={"AAA": D("1")}, prior_closes={"AAA": D("-1")})

    assert obs.status == STATUS_UNAVAILABLE
    assert obs.reason == REASON_NON_POSITIVE_PRICE


def test_unavailable_never_reports_a_number():
    """The whole point: no invented baseline, no sentinel zero."""
    for obs in (
        _observe(EXPECTED, activity_since_boundary=True),
        _observe(None),
        _observe(EXPECTED, quantities={**QTY, "CCC": D("1")}),
    ):
        assert obs.reconstructed_prior_close_equity is None
        assert obs.residual is None


# --------------------------------------------------------------------- dormancy

def test_module_is_unreferenced_by_the_runtime():
    """Dormant preparatory tooling: adding a runtime call site is a governed activation step."""
    import pathlib
    import subprocess

    app_dir = pathlib.Path(__file__).resolve().parents[2] / "app"
    hits = subprocess.run(
        ["git", "grep", "-l", "daily_baseline_residual", "--", str(app_dir)],
        capture_output=True, text=True,
    ).stdout.split()

    assert [h for h in hits if not h.endswith("daily_baseline_residual.py")] == []
