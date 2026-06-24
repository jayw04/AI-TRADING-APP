"""Factor Lab verdict evaluator — the data-driven A/B/C/D tree (plan v0.2 §3.4).

Mirrors the TREND-001 verdict tree as a VerdictSpec and pins the same A/B/C/D outcomes,
including the exact full-run scenario that the bespoke verdict code first mis-classified.
"""

from __future__ import annotations

import pytest

from app.research.factor_lab.spec import VerdictRule, VerdictSpec
from app.research.factor_lab.verdict import classify

# The TREND-001 tree expressed as data: B triggers on "H1 fails but H2 OR H3 clears
# beyond the regime filter" (no extra correlation gate — the bug the bespoke code had).
_TREND_TREE = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["h1_real"] and m["consistent"],
                    "A - Validated", "standalone book candidate"),
        VerdictRule(
            lambda m: (m["blend_helps"]
                       or (m["dd_vs_mom"] > 0 and m["dd_vs_eqw"] > 0 and m["beats_regime"]))
            and m["beats_regime"],
            "B - Diversifier / Defensive", "participation sleeve / blend candidate"),
        VerdictRule(
            lambda m: (not m["beats_regime"])
            or (not m["blend_helps"] and m["dd_vs_mom"] <= 0 and m["h1_ci_high"] < 0),
            "C - Rejected", "subsumed by the existing regime filter"),
    ),
    default_outcome="D - Inconclusive",
    default_action="research debt -> V2",
)


def _m(**over):
    base = dict(h1_real=False, consistent=False, blend_helps=False,
                dd_vs_mom=0.0, dd_vs_eqw=0.0, beats_regime=False, h1_ci_high=0.0)
    base.update(over)
    return base


def test_outcome_A_when_h1_clears_and_consistent() -> None:
    assert classify(_m(h1_real=True, consistent=True), _TREND_TREE)[0].startswith("A")


def test_outcome_B_on_h3_beyond_regime_even_with_high_correlation() -> None:
    """The actual TREND-001 full-run case: H1 fails, blend doesn't help, but drawdown is
    shallower than momentum AND eqw AND it beats the regime filter → B (no corr gate)."""
    out, _ = classify(_m(dd_vs_mom=0.302, dd_vs_eqw=0.23, beats_regime=True, h1_ci_high=0.33),
                      _TREND_TREE)
    assert out.startswith("B")


def test_outcome_C_when_subsumed_by_regime_filter() -> None:
    out, _ = classify(_m(dd_vs_mom=0.30, dd_vs_eqw=0.20, beats_regime=False, h1_ci_high=-0.05),
                      _TREND_TREE)
    assert out.startswith("C")


def test_outcome_D_default_when_borderline() -> None:
    out, action = classify(_m(beats_regime=True, dd_vs_mom=-0.01, dd_vs_eqw=-0.01, h1_ci_high=0.2),
                           _TREND_TREE)
    assert out.startswith("D")
    assert action == "research debt -> V2"


def test_config_trend_verdict_reproduces_classify_outcome() -> None:
    """The shipped TREND_001.verdict (configs.py) must reproduce trend_research's frozen
    classify_outcome across A/B/C/D — including the H3-beyond-regime B and the
    subsumed/all-fail C splits (the cases that carried the original verdict bug)."""
    from app.research.factor_lab.configs import TREND_001
    v = TREND_001.verdict
    # A — standalone edge + consistent
    assert classify(_m(h1_real=True, consistent=True), v)[0].startswith("A")
    # B — H3 clears beyond the regime filter (no corr gate)
    assert classify(_m(dd_vs_mom=0.30, dd_vs_eqw=0.23, beats_regime=True, h1_ci_high=0.33),
                    v)[0].startswith("B")
    # B — H2 blend helps (and not subsumed)
    assert classify(_m(blend_helps=True, beats_regime=True, h1_ci_high=0.1), v)[0].startswith("B")
    # C — subsumed by the regime filter (beats_regime False)
    assert classify(_m(dd_vs_mom=0.30, dd_vs_eqw=0.20, beats_regime=False, h1_ci_high=-0.05),
                    v)[0].startswith("C")
    # C — all fail: not subsumed but neither H2 nor H3 clears and H1 CI high < 0
    assert classify(_m(beats_regime=True, dd_vs_mom=-0.01, dd_vs_eqw=-0.01, h1_ci_high=-0.10),
                    v)[0].startswith("C")
    # D — borderline (not subsumed, nothing clears, H1 CI high ≥ 0)
    assert classify(_m(beats_regime=True, dd_vs_mom=-0.01, dd_vs_eqw=-0.01, h1_ci_high=0.20),
                    v)[0].startswith("D")


def test_config_sec_verdict_reproduces_sector_rotation_v2() -> None:
    """The shipped SEC_001.verdict (configs.py) reproduces sector_rotation_v2's A/B/C/D:
    A on a consistent standalone edge vs the all-sector control; B when the blend helps;
    C when the all-sector-control CI high < 0; else D."""
    from app.research.factor_lab.configs import SEC_001
    v = SEC_001.verdict
    assert classify(_m(h1_real=True, consistent=True), v)[0].startswith("A")
    assert classify(_m(blend_helps=True), v)[0].startswith("B")
    assert classify(_m(h1_ci_high=-0.1), v)[0].startswith("C")
    assert classify(_m(h1_ci_high=0.2), v)[0].startswith("D")


def test_first_matching_rule_wins() -> None:
    spec = VerdictSpec(
        rules=(
            VerdictRule(lambda m: True, "first", "a"),
            VerdictRule(lambda m: True, "second", "b"),
        ),
        default_outcome="default", default_action="d",
    )
    assert classify({}, spec) == ("first", "a")


def test_missing_metric_raises_loudly() -> None:
    """A predicate referencing a key the runner didn't supply must raise, not silently
    fall through to the default (that would hide a spec/runner mismatch)."""
    spec = VerdictSpec(
        rules=(VerdictRule(lambda m: m["nonexistent"], "x", "y"),),
        default_outcome="d", default_action="d",
    )
    with pytest.raises(KeyError):
        classify({"present": 1}, spec)
