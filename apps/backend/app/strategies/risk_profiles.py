"""Momentum Risk Profiles (P13.5) — the customer-facing "risk dial".

Three named tiers of the **same** momentum strategy, differing only in the vol-scaling target.
P12 §2's grid validated vol-scaling as a *monotonic* risk dial across 10–20% (every target clears
the enable gate), so a profile is purely a preset that turns vol-scaling on and sets
``vol_target_annual``. Nothing about the alpha changes — only the realized-vol cap, hence the
risk/return trade-off.

"Vol-scaling on" means BOTH vol paths, so the target binds from the first order, not hours later:
- ``use_vol_scaling`` — scales the **rebalance entry** basket to the target at sizing time
  (``_gross_scale`` in the entry path). Without it the book enters every week at full gross (up to
  1×) and is only de-risked later — a "10% vol" book briefly running ~4–5× its target. (This gap
  also amplified the 2026-06-22 leverage incident, where the duplicate baskets stacked at the
  unscaled entry; see ADR 0025.)
- ``use_daily_overlay`` — re-sizes the **held** book toward the target between rebalances (ADR 0020).
Both read ``vol_target_annual`` and cap at 1× (no leverage); they compose (the overlay measures live
gross, so it no-ops once entry already hit target).

| Profile | vol target | character (P12 §2 grid, backtest — survivorship-biased, indicative) |
|---|---|---|
| Conservative | 10% | max drawdown protection, lower return (~−34% maxDD / +4.8% CAGR) |
| Balanced | 15% | the v1.1 default; balanced (~−47% maxDD); what runs live today |
| Growth | 20% | max return, larger drawdown (~−57% maxDD / +8.5% CAGR, Sharpe ~0.52) |

These let the product show the risk dial working *live* across three paper books — each on its own
account (strategies resolve their account via ``(user, broker, mode)``; P5 §7), so the three
profiles run independently rather than competing on one book.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RiskProfile:
    key: str
    label: str
    vol_target_annual: float
    description: str


RISK_PROFILES: dict[str, RiskProfile] = {
    "conservative": RiskProfile(
        "conservative", "Conservative", 0.10,
        "Maximum drawdown protection, lower return (vol target 10%)."),
    "balanced": RiskProfile(
        "balanced", "Balanced", 0.15,
        "The v1.1 default — balanced risk/return (vol target 15%); runs live today."),
    "growth": RiskProfile(
        "growth", "Growth", 0.20,
        "Maximum return, larger drawdown (vol target 20%)."),
}

# the conventional book name for a profile's paper strategy
NAME_PREFIX = "momentum"


def get_profile(key: str) -> RiskProfile:
    try:
        return RISK_PROFILES[key.lower()]
    except KeyError:
        raise ValueError(
            f"unknown risk profile {key!r}; choose from {sorted(RISK_PROFILES)}"
        ) from None


def profile_name(key: str) -> str:
    """Conventional strategy/book name for a profile, e.g. ``momentum-conservative``."""
    return f"{NAME_PREFIX}-{get_profile(key).key}"


def profile_params(key: str, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strategy params for a profile: ``base`` with vol-scaling turned ON at the profile's target.

    Turns on BOTH vol paths so the target binds at entry, not only reactively:
    ``use_vol_scaling`` (scales the rebalance basket at sizing time) and ``use_daily_overlay``
    (re-sizes the held book between rebalances). Without ``use_vol_scaling`` the book enters every
    week at full gross and is de-risked only on the next overlay tick — see the module docstring.

    Only these vol keys are profile-specific; everything else (universe sizing, regime filter,
    pricing) comes from ``base`` so all three profiles share identical alpha logic."""
    params = dict(base or {})
    params["use_vol_scaling"] = True
    params["use_daily_overlay"] = True
    params["vol_target_annual"] = get_profile(key).vol_target_annual
    return params
