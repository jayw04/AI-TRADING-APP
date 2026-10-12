"""Criteria classifier and selection rule on SYNTHETIC summaries and configurations.

The thresholds below are test fixtures, not proposals: the classifier has no defaults, and
adopting real values is a separate owner act before any real-data use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.screen.criteria import (
    DEFECT,
    INSUFFICIENT_EVIDENCE,
    REVISE,
    STOP_THIS_VERSION,
    CandidateEvidence,
    CriteriaConfig,
    classify_family,
)
from app.research.range002.screen.selection import CandidateScore, select_candidate
from tests.research.range002.governance.conftest import (
    synthetic_manifest,  # noqa: F401  (autouse manifest seam)
)
from tests.research.range002.screen.conftest import make_capability, synth_payload

CFG = CriteriaConfig(
    min_trades=300,
    min_traded_days=100,
    pf_min=1.15,
    top_n_removed=5,
    best_day_share_max=0.20,
    neighbour_pf_min=1.0,
    min_nonpositive_years=2,
    neighbours=(("E2a", "E2b"),),
)


@pytest.fixture
def cap(tmp_path: Path) -> object:
    return make_capability(tmp_path, synth_payload())[0]


def summary(**over: object) -> dict:  # type: ignore[type-arg]
    s = {
        "trades": 400,
        "traded_days": 150,
        "base": {"mean_net_r": 0.10, "profit_factor": 1.30, "total_net_r": 40.0, "win_rate": 0.5},
        "stress": {"mean_net_r": 0.05, "profit_factor": 1.15, "total_net_r": 20.0, "win_rate": 0.5},
        "net_r_after_removing_top5": 30.0,
        "best_day_share_of_net": 0.05,
        "per_year": {y: {"n": 100, "mean_net_r": 0.1} for y in (2016, 2017, 2018, 2019)},
    }
    s.update(over)
    return s


def ev(
    cand: str = "E1", spans_zero: bool | None = False, defects: tuple[str, ...] = (), **over: object
) -> CandidateEvidence:
    return CandidateEvidence(cand, summary(**over), spans_zero, defects)


def codes(cap: object, e: CandidateEvidence, *, rejects: bool | None = True, extra=()) -> set[str]:  # type: ignore[no-untyped-def]
    out = classify_family(cap, CFG, [e, *extra], max_test_rejects=rejects)
    return {f.code for f in out[e.candidate].findings}


def test_clean_candidate_advances_and_nothing_is_defaulted(cap: object) -> None:
    out = classify_family(cap, CFG, [ev()], max_test_rejects=True)["E1"]
    assert out.advance and out.findings == () and out.classes == ()
    with pytest.raises(TypeError):
        CriteriaConfig()  # type: ignore[call-arg]


def test_each_rule_fires_with_its_class(cap: object) -> None:
    assert "TOO_FEW_TRADES_OR_DAYS" in codes(cap, ev(trades=299))
    assert "TOO_FEW_TRADES_OR_DAYS" in codes(cap, ev(traded_days=99))
    assert "INTERVAL_SPANS_ZERO" in codes(cap, ev(spans_zero=True))
    assert "INTERVAL_SPANS_ZERO" in codes(cap, ev(spans_zero=None))  # not computed != clean
    assert "MAX_TEST_NOT_REJECTED" in codes(cap, ev(), rejects=False)
    assert "MAX_TEST_NOT_REJECTED" in codes(cap, ev(), rejects=None)
    weak = ev(
        base={"mean_net_r": -0.02, "profit_factor": 0.9, "total_net_r": -8.0, "win_rate": 0.4}
    )
    assert "MEAN_NET_R_NON_POSITIVE" in codes(cap, weak)
    fragile = ev(
        stress={"mean_net_r": -0.01, "profit_factor": 0.95, "total_net_r": -4.0, "win_rate": 0.4}
    )
    assert "COST_FRAGILE" in codes(cap, fragile)
    lowpf = ev(
        base={"mean_net_r": 0.02, "profit_factor": 1.05, "total_net_r": 8.0, "win_rate": 0.5}
    )
    assert "PF_BELOW_MIN" in codes(cap, lowpf)
    assert "CONCENTRATION" in codes(cap, ev(net_r_after_removing_top5=-1.0))
    assert "CONCENTRATION" in codes(cap, ev(best_day_share_of_net=0.25))
    bad_years = ev(
        per_year={
            2016: {"n": 1, "mean_net_r": -0.1},
            2017: {"n": 1, "mean_net_r": 0.0},
            2018: {"n": 1, "mean_net_r": 0.1},
            2019: {"n": 1, "mean_net_r": 0.1},
        }
    )
    assert "TEMPORAL_INSTABILITY" in codes(cap, bad_years)


def test_classes_and_defects_are_reported_side_by_side(cap: object) -> None:
    e = ev(
        trades=50,
        defects=("causal look-ahead failure",),
        base={"mean_net_r": -0.05, "profit_factor": 0.8, "total_net_r": -2.5, "win_rate": 0.4},
    )
    out = classify_family(cap, CFG, [e], max_test_rejects=False)["E1"]
    assert out.advance is False
    assert set(out.classes) == {DEFECT, INSUFFICIENT_EVIDENCE, STOP_THIS_VERSION}
    assert REVISE not in out.classes  # concentration/PF rules need a positive mean


def test_neighbour_fragility_uses_the_declared_pair_only(cap: object) -> None:
    weak_neighbour = ev(
        "E2b", base={"mean_net_r": 0.01, "profit_factor": 0.97, "total_net_r": 2.0, "win_rate": 0.5}
    )
    assert "NEIGHBOUR_FRAGILE" in codes(cap, ev("E2a"), extra=[weak_neighbour])
    assert "NEIGHBOUR_FRAGILE" not in codes(cap, ev("E1"), extra=[weak_neighbour])  # E1 has none


def test_classifier_needs_a_capability(cap: object) -> None:
    with pytest.raises(InvalidCapabilityError):
        classify_family(None, CFG, [ev()], max_test_rejects=True)


# --- selection ------------------------------------------------------------------------------

ORDER = ["TIME", "R1", "R2", "TRAIL", "SCALE"]


def sc(c: str, score: float | None, trades: int = 400, pf: float | None = 1.3) -> CandidateScore:
    return CandidateScore(c, score, trades, pf)


def test_best_score_wins_and_exact_ties_go_to_the_simpler_candidate(cap: object) -> None:
    r = select_candidate(
        cap, [sc("R2", 0.12), sc("TIME", 0.10)], ORDER, min_trades=300, min_pf=1.15, delta=0.0
    )
    assert (
        r.winner == "R2"
        and r.reason == "UNIQUE_BEST"
        and r.margin_to_runner_up == pytest.approx(0.02)
    )
    tie = select_candidate(
        cap, [sc("TRAIL", 0.10), sc("R1", 0.10)], ORDER, min_trades=300, min_pf=1.15, delta=0.0
    )
    assert tie.winner == "R1" and tie.reason == "TIE_BROKEN_BY_COMPLEXITY_ORDER"
    assert tie.tied_within_delta == ("R1", "TRAIL")


def test_delta_widens_the_tie_set_and_is_deterministic(cap: object) -> None:
    args = ([sc("R2", 0.12), sc("TIME", 0.115)], ORDER)
    near = select_candidate(cap, *args, min_trades=300, min_pf=1.15, delta=0.01)
    assert near.winner == "TIME"  # within delta of the best: simplest wins
    again = select_candidate(cap, *reversed_input(args), min_trades=300, min_pf=1.15, delta=0.01)
    assert again.winner == near.winner


def reversed_input(args):  # type: ignore[no-untyped-def]
    return (list(reversed(args[0])), args[1])


def test_eligibility_floor_and_empty_result(cap: object) -> None:
    r = select_candidate(
        cap,
        [sc("TIME", 0.5, trades=10), sc("R1", 0.4, pf=1.0), sc("R2", None)],
        ORDER,
        min_trades=300,
        min_pf=1.15,
        delta=0.0,
    )
    assert r.winner is None and r.reason == "NO_ELIGIBLE_CANDIDATE"
    assert r.ineligible == {"TIME": "TOO_FEW_TRADES", "R1": "PF_BELOW_FLOOR", "R2": "NO_SCORE"}


def test_selection_refuses_unknown_or_duplicate_candidates(cap: object) -> None:
    with pytest.raises(ValueError):
        select_candidate(cap, [sc("MYSTERY", 0.1)], ORDER, min_trades=0, min_pf=0, delta=0.0)
    with pytest.raises(ValueError):
        select_candidate(
            cap, [sc("TIME", 0.1), sc("TIME", 0.2)], ORDER, min_trades=0, min_pf=0, delta=0.0
        )
