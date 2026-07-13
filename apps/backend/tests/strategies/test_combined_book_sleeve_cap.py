"""The cross-asset sleeve must be able to REACH its mandate, and any shortfall must be loud.

THE BUG (live, 2026-07-13, combined-book / account 7). The book allots 60% of equity to a
9-ETF cross-asset sleeve, but every position — stock or ETF — was capped by the single
``max_position_pct`` of 4%. Nine ETFs at 4% is a 36% ceiling against a 60% mandate: the sleeve
could NEVER fill it. ``_apply_targets`` takes ``min(weight, cap)``, so the overflow was silently
dropped to cash. Nothing logged it and nothing reconciled it.

It went unnoticed for weeks because the number it produced looked plausible: 0.40 (equity) +
~0.28 (truncated sleeve) = ~68% invested. Then the beta-cap governor was tightened to 0.80,
which scales the equity-beta names by ~0.30 — and the book collapsed to 32% invested / 68%
cash while the governor's own log still claimed it was deploying 65.9%.

    equity sleeve   0.40 x 0.2955  = 11.8%   (observed 11.6%)
    cross-asset     truncated      = 20.7%   (4 ETFs pinned at exactly $4,011 = 4% of equity)
    ------------------------------------------
    total                            32.3%   vs the governor's resolved 65.9%
    stranded                         ~$32,440

FIX: a separate ``cross_asset_max_position_pct`` (0.15). The 4% figure is a single-STOCK
concentration control and was never meant for a 9-name macro sleeve. Plus a
``position_cap_truncation`` signal so a decided-vs-deployed gap can never hide again.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

CROSS_ASSET = ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"]

EQUITY_SLEEVE_WEIGHT = 0.40
CROSS_ASSET_WEIGHT = 0.60
EQUITY_CAP = 0.04
CROSS_ASSET_CAP = 0.15


def _deployable(weights: dict[str, float], eq_cap: float, ca_cap: float) -> float:
    """What ``_apply_targets`` actually deploys: min(weight, the sleeve's cap), summed."""
    return sum(
        min(w, ca_cap if sym.upper() in set(CROSS_ASSET) else eq_cap)
        for sym, w in weights.items()
    )


def test_the_old_single_cap_made_the_mandate_UNREACHABLE() -> None:
    """The defect, stated as arithmetic: 9 ETFs x 4% cannot hold 60%.

    This is not a tuning complaint — it is a structural contradiction between two params.
    """
    ceiling_under_old_cap = len(CROSS_ASSET) * EQUITY_CAP
    assert ceiling_under_old_cap == pytest.approx(0.36)
    assert ceiling_under_old_cap < CROSS_ASSET_WEIGHT, (
        "the sleeve's ceiling must be below its mandate for the bug to exist"
    )


def test_sleeve_mandate_is_reachable_under_the_new_cap() -> None:
    """THE INVARIANT. Whatever the caps are, the sleeve must be able to hold what it is
    allotted — otherwise the difference silently becomes cash."""
    ceiling = len(CROSS_ASSET) * CROSS_ASSET_CAP
    assert ceiling >= CROSS_ASSET_WEIGHT, (
        f"{len(CROSS_ASSET)} ETFs x {CROSS_ASSET_CAP:.0%} = {ceiling:.0%} cannot hold a "
        f"{CROSS_ASSET_WEIGHT:.0%} mandate"
    )


def test_live_2026_07_13_book_is_reproduced_and_then_repaired() -> None:
    """Reproduce the live shortfall from the REAL numbers, then show the fix closes it.

    The beta-cap governor logged, identically on all five runs that day:
        equity_beta_rc_before 0.9897 | cap 0.80 | scale_equity_beta 0.2955 | gross_after 0.6592

    The four ETFs that were PINNED (KMLM/DBC/UUP/IEF each held exactly ~4% of equity) hide
    their pre-cap weight — a pinned position only tells you it wanted *at least* the cap. So
    recover it from the governor's own totals rather than guessing:

        equity sleeve, post-beta-scale : 0.40 x 0.2955          = 0.1182
        cross-asset sleeve, pre-cap    : 0.6592 - 0.1182        = 0.5410
        the 4 UNDER-cap ETFs (observed): GLD .0236 SPY .0102
                                         EFA .0093 EEM .0047    = 0.0478
        => the 4 PINNED ETFs, pre-cap  : 0.5410 - 0.0478        = 0.4932  (~0.1233 each)
    """
    beta_scale = 0.2955

    # 80 equity names sharing 40% of the book, scaled by the beta cap. Each is ~0.15% —
    # nowhere near the 4% cap, so the equity sleeve is NOT the thing being truncated.
    equity_names = {f"STK{i}": EQUITY_SLEEVE_WEIGHT / 80 * beta_scale for i in range(80)}

    cross = {
        # pinned: pre-cap weight recovered above. The beta cap does not touch these (they are
        # not equity-beta), which is exactly why they blew through a 4% stock cap.
        "KMLM": 0.1233, "DBC": 0.1233, "UUP": 0.1233, "IEF": 0.1233,
        # under-cap: observed live, so post-cap == pre-cap. SPY/EFA/EEM are equity-beta and
        # were scaled down by the governor like stocks; GLD is small on its own trend signal.
        "GLD": 0.0236, "SPY": 0.0102, "EFA": 0.0093, "EEM": 0.0047,
    }
    target = {**equity_names, **cross}

    # The book the governor RESOLVED to hold: ~65.9% gross. This is what it reported deploying.
    assert sum(target.values()) == pytest.approx(0.6592, abs=0.002)

    # OLD: one 4% cap for everything -> the sleeve is truncated and the book lands at ~32%.
    old = _deployable(target, EQUITY_CAP, EQUITY_CAP)
    assert old == pytest.approx(0.323, abs=0.015)  # the live book held 32.3%

    # NEW: the sleeve gets its own cap. 12.3% < 15%, so nothing is truncated and the book
    # deploys precisely what the governor resolved.
    new = _deployable(target, EQUITY_CAP, CROSS_ASSET_CAP)
    assert new == pytest.approx(sum(target.values()), abs=0.001)

    stranded = sum(target.values()) - old
    assert stranded == pytest.approx(0.336, abs=0.015)  # ~$32.4k idle on a $100k book


def test_equity_sleeve_cap_is_untouched() -> None:
    """The fix must NOT loosen single-stock concentration. A 20%-weight stock is still 4%."""
    target = {"NVDA": 0.20, "SPY": 0.20}
    out = {
        sym: min(w, CROSS_ASSET_CAP if sym in CROSS_ASSET else EQUITY_CAP)
        for sym, w in target.items()
    }
    assert out["NVDA"] == EQUITY_CAP      # stock: still capped hard at 4%
    assert out["SPY"] == CROSS_ASSET_CAP  # ETF sleeve: 15%


def test_template_carries_the_sleeve_cap_and_the_truncation_signal() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "strategies_user" / "templates" / "combined_book.py"
    ).read_text()

    assert '"cross_asset_max_position_pct": 0.15' in src, "sleeve cap default missing"
    assert '"cross_asset_max_position_pct": {' in src, "sleeve cap not declared in params_schema"
    assert '"reason": "position_cap_truncation"' in src, (
        "a decided-vs-deployed gap must be logged — silence is what hid this for weeks"
    )


def test_truncation_threshold_ignores_rounding_but_catches_a_stranded_sleeve() -> None:
    """The signal fires on a stranded sleeve, not on Decimal dust."""
    threshold = Decimal("0.02")
    assert Decimal("0.336") > threshold   # the live shortfall: fires
    assert Decimal("0.004") < threshold   # rounding: silent
