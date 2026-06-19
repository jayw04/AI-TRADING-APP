"""P11 §1 — feature-registry integrity (drift guard).

The registry is the static source of truth for operational features; these tests pin it
to the actual code so it can't silently drift — every flag-based feature's enable_flag
must be a real strategy param, every verified value legal, every key unique, and every
infra job-id reference a real infra feature.
"""

from __future__ import annotations

from app.ops.feature_registry import (
    FEATURES,
    INFRA_JOB_IDS,
    VERIFIED_VALUES,
)
from strategies_user.templates.momentum_portfolio import MomentumPortfolio


def test_keys_unique() -> None:
    keys = [f.key for f in FEATURES]
    assert len(keys) == len(set(keys))


def test_verified_values_legal() -> None:
    for f in FEATURES:
        assert f.verified in VERIFIED_VALUES, f"{f.key}: {f.verified!r}"


def test_flag_features_map_to_real_strategy_params() -> None:
    """Every flag-based feature's enable_flag is a real MomentumPortfolio param — so the
    registry can't claim a flag the strategy doesn't have."""
    params = MomentumPortfolio.default_params
    for f in FEATURES:
        if f.enable_flag is not None:
            assert f.enable_flag in params, f"{f.key}: {f.enable_flag} not a strategy param"


def test_infra_features_have_no_flag_and_a_job_id() -> None:
    """Infra features (enable_flag None) must have a job-id mapping, and every
    INFRA_JOB_IDS key must be a real infra feature."""
    infra_keys = {f.key for f in FEATURES if f.enable_flag is None}
    for key in INFRA_JOB_IDS:
        assert key in infra_keys, f"INFRA_JOB_IDS references unknown/non-infra key {key!r}"


def test_regime_overlays_recorded_no_go() -> None:
    """The §5 regime overlays must carry the promotion-backtest NO-GO verdict (kept in
    sync with the P10 roadmap's Implemented-vs-Proven table)."""
    by_key = {f.key: f for f in FEATURES}
    assert by_key["breadth_overlay"].verified == "no_go"
    assert by_key["vix_overlay"].verified == "no_go"
