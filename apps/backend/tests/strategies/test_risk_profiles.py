"""Momentum Risk Profiles (P13.5) — the customer-facing risk dial."""

from __future__ import annotations

import pytest

from app.strategies.risk_profiles import (
    RISK_PROFILES,
    get_profile,
    profile_name,
    profile_params,
)


def test_three_profiles_with_monotonic_vol_targets():
    keys = ["conservative", "balanced", "growth"]
    assert sorted(RISK_PROFILES) == sorted(keys)
    targets = [RISK_PROFILES[k].vol_target_annual for k in keys]
    assert targets == [0.10, 0.15, 0.20]  # monotonic risk dial (P12 §2 grid)


def test_get_profile_case_insensitive_and_unknown_raises():
    assert get_profile("Growth").vol_target_annual == 0.20
    with pytest.raises(ValueError):
        get_profile("aggressive")


def test_profile_name_convention():
    assert profile_name("conservative") == "momentum-conservative"
    assert profile_name("growth") == "momentum-growth"


def test_profile_params_turns_on_vol_scaling_and_preserves_base():
    base = {"max_names": 5, "use_daily_overlay": False, "vol_target_annual": 0.99}
    p = profile_params("conservative", base)
    assert p["use_daily_overlay"] is True            # overlay forced on
    assert p["vol_target_annual"] == 0.10            # set to the profile's target
    assert p["max_names"] == 5                        # base preserved
    assert base["vol_target_annual"] == 0.99          # base not mutated (copy)


def test_balanced_matches_live_default():
    # Balanced is the v1.1 default already running live (BFY6) — 15%.
    assert get_profile("balanced").vol_target_annual == 0.15
