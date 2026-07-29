"""WP5 AMD-02 / D2 — statistical design freeze (hermetic; no broker)."""

from __future__ import annotations

from app.risk.loss_control.phase0_statistical_design import (
    FLOOR_PER_SYMBOL_STRATUM,
    FLOOR_POOLED_BINDING_REACHABLE,
    FLOOR_SHADOW_SESSIONS,
    FloorReplaceRefuse,
    SampleFloors,
    SampleGateVerdict,
    StatisticalDesignFreeze,
    assess_sample_gate,
    assert_no_order_path_imports,
    clopper_pearson_one_sided_upper,
    default_freeze,
    stratum_diagnostic_bound_note,
)


def _coverage(n: int = 20) -> dict[str, int]:
    return {"KOKU": n, "IEUS": n}


def test_provisional_floors_are_59_20_10() -> None:
    f = default_freeze().floors
    assert f.pooled_binding_reachable_plans == FLOOR_POOLED_BINDING_REACHABLE == 59
    assert f.per_intended_symbol_stratum == FLOOR_PER_SYMBOL_STRATUM == 20
    assert f.shadow_sessions == FLOOR_SHADOW_SESSIONS == 10


def test_zero_failures_n59_upper_bound_near_five_percent() -> None:
    u = clopper_pearson_one_sided_upper(0, 59)
    assert abs(u - (1.0 - 0.05 ** (1.0 / 59))) < 1e-12
    assert 0.048 < u < 0.051


def test_zero_failures_n20_bound_materially_above_five_percent() -> None:
    u = clopper_pearson_one_sided_upper(0, 20)
    assert u > 0.10
    note = stratum_diagnostic_bound_note(20)
    assert "diagnostic floor only" in note


def test_one_failure_rejects() -> None:
    freeze = default_freeze()
    r = assess_sample_gate(
        freeze=freeze,
        pooled_n_raw=59,
        critical_failures=1,
        stratum_coverage=_coverage(20),
        shadow_sessions=10,
    )
    assert r.verdict == SampleGateVerdict.REJECT


def test_zero_failures_but_floors_unmet_is_inconclusive() -> None:
    freeze = default_freeze()
    r = assess_sample_gate(
        freeze=freeze,
        pooled_n_raw=30,
        critical_failures=0,
        stratum_coverage=_coverage(20),
        shadow_sessions=10,
    )
    assert r.verdict == SampleGateVerdict.INCONCLUSIVE
    assert r.floors_met is False


def test_zero_failures_floors_met_passes() -> None:
    freeze = default_freeze()
    r = assess_sample_gate(
        freeze=freeze,
        pooled_n_raw=59,
        pooled_n_eff=59,
        critical_failures=0,
        stratum_coverage=_coverage(20),
        shadow_sessions=10,
    )
    assert r.verdict == SampleGateVerdict.PASS
    assert r.one_sided_upper_bound is not None
    assert r.one_sided_upper_bound <= freeze.floors.max_one_sided_upper_bound
    assert "assumptions" in r.as_dict()


def test_effective_n_too_small_makes_bound_inconclusive() -> None:
    """Clustering can shrink n_eff so the bound exceeds the frozen threshold."""
    freeze = default_freeze()
    r = assess_sample_gate(
        freeze=freeze,
        pooled_n_raw=59,
        pooled_n_eff=20,  # floors on raw met, but bound uses n_eff
        critical_failures=0,
        stratum_coverage=_coverage(20),
        shadow_sessions=10,
    )
    assert r.floors_met is True
    assert r.verdict == SampleGateVerdict.INCONCLUSIVE
    assert r.one_sided_upper_bound is not None
    assert r.one_sided_upper_bound > freeze.floors.max_one_sided_upper_bound


def test_replace_floors_once_then_lock() -> None:
    freeze = StatisticalDesignFreeze()
    err = freeze.replace_floors_once(
        SampleFloors(pooled_binding_reachable_plans=80, per_intended_symbol_stratum=25),
        note="WP5 exit governed replacement",
    )
    assert err is None
    assert freeze.locked and freeze.replacement_used
    assert freeze.floors.pooled_binding_reachable_plans == 80
    assert freeze.replace_floors_once(SampleFloors(), note="again") is FloorReplaceRefuse.ALREADY_LOCKED


def test_cannot_replace_after_explicit_lock() -> None:
    freeze = StatisticalDesignFreeze()
    freeze.lock()
    assert (
        freeze.replace_floors_once(SampleFloors(pooled_binding_reachable_plans=99), note="x")
        is FloorReplaceRefuse.ALREADY_LOCKED
    )


def test_assumptions_recorded() -> None:
    d = default_freeze().as_dict()
    assert d["assumptions"]["independence_unit"] == "binding_reachable_execution_plan"
    assert d["assumptions"]["per_symbol_floor_is_diagnostic_only"] is True


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
