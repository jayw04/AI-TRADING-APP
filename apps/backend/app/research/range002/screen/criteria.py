"""Exploratory screening-criteria classifier (A-SCREEN section 6a), configurable and synthetic-tested.

Every threshold is an explicit field of ``CriteriaConfig`` with no default, so no value is
chosen here: production adoption of the values is a separate owner act that must precede any
real-data use. The classifier reports EVERY finding; it does not collapse them into one verdict
by an invented precedence. ``advance`` is true only when there is no finding at all, which is
the amendment's "none of the above -> ADVANCE TO P3b" (still subject to the statistical stage
and human review of warnings).

Classes: DEFECT, INSUFFICIENT_EVIDENCE, STOP_THIS_VERSION, REVISE. A small-sample non-positive
mean is reported as observed weakness next to the insufficient-evidence findings, never as
conclusive failure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.research.range002.governance.results_guard import requires_capability

DEFECT = "DEFECT"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STOP_THIS_VERSION = "STOP_THIS_VERSION"
REVISE = "REVISE"


@dataclass(frozen=True)
class CriteriaConfig:
    min_trades: int
    min_traded_days: int
    pf_min: float
    top_n_removed: int
    best_day_share_max: float
    neighbour_pf_min: float
    min_nonpositive_years: int
    neighbours: tuple[tuple[str, str], ...]  # declared pairs, e.g. (("E2a", "E2b"), ...)


@dataclass(frozen=True)
class CandidateEvidence:
    """Facts for one candidate. ``summary`` is ``report.summarize`` output (base cost)."""

    candidate: str
    summary: Mapping[str, Any]
    interval_spans_zero: bool | None  # None = not computed -> insufficient evidence
    defects: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    code: str
    cls: str
    detail: str


@dataclass(frozen=True)
class Classification:
    candidate: str
    findings: tuple[Finding, ...]
    classes: tuple[str, ...]
    advance: bool


def _neighbour_of(cfg: CriteriaConfig, cand: str) -> str | None:
    for a, b in cfg.neighbours:
        if cand == a:
            return b
        if cand == b:
            return a
    return None


@requires_capability
def classify_family(
    capability: object,
    cfg: CriteriaConfig,
    evidence: Sequence[CandidateEvidence],
    *,
    max_test_rejects: bool | None,
) -> dict[str, Classification]:
    if cfg.min_trades <= 0 or cfg.min_traded_days <= 0 or cfg.top_n_removed < 0:
        raise ValueError("count thresholds must be positive")
    by_id = {e.candidate: e for e in evidence}
    if len(by_id) != len(evidence):
        raise ValueError("duplicate candidate in evidence")
    out: dict[str, Classification] = {}
    for e in evidence:
        s = e.summary
        found: list[Finding] = [Finding("DEFECT", DEFECT, d) for d in e.defects]
        base, stress = s["base"], s["stress"]
        mean = base["mean_net_r"]
        if s["trades"] < cfg.min_trades or s["traded_days"] < cfg.min_traded_days:
            found.append(
                Finding(
                    "TOO_FEW_TRADES_OR_DAYS",
                    INSUFFICIENT_EVIDENCE,
                    f"{s['trades']} trades, {s['traded_days']} days",
                )
            )
        if e.interval_spans_zero is None or e.interval_spans_zero:
            found.append(
                Finding("INTERVAL_SPANS_ZERO", INSUFFICIENT_EVIDENCE, "bootstrap interval")
            )
        if max_test_rejects is not True:
            found.append(Finding("MAX_TEST_NOT_REJECTED", INSUFFICIENT_EVIDENCE, "family test"))
        if mean is None or mean <= 0:
            found.append(Finding("MEAN_NET_R_NON_POSITIVE", STOP_THIS_VERSION, f"mean={mean}"))
        else:
            sm = stress["mean_net_r"]
            if sm is None or sm <= 0:
                found.append(Finding("COST_FRAGILE", REVISE, f"stress mean={sm}"))
            pf = base["profit_factor"]
            if pf is not None and pf < cfg.pf_min:
                found.append(Finding("PF_BELOW_MIN", REVISE, f"pf={pf:.3f}"))
            top = s["net_r_after_removing_top5"]
            share = s["best_day_share_of_net"]
            if (top is not None and top <= 0) or (
                share is not None and share > cfg.best_day_share_max
            ):
                found.append(Finding("CONCENTRATION", REVISE, f"after-top={top}, best-day={share}"))
        nb = _neighbour_of(cfg, e.candidate)
        if nb is not None and nb in by_id:
            npf = by_id[nb].summary["base"]["profit_factor"]
            if npf is not None and npf < cfg.neighbour_pf_min:
                found.append(Finding("NEIGHBOUR_FRAGILE", REVISE, f"{nb} pf={npf:.3f}"))
        bad_years = sum(1 for y in s["per_year"].values() if y["mean_net_r"] <= 0)
        if bad_years >= cfg.min_nonpositive_years:
            found.append(Finding("TEMPORAL_INSTABILITY", REVISE, f"{bad_years} non-positive years"))
        classes = tuple(sorted({f.cls for f in found}))
        out[e.candidate] = Classification(e.candidate, tuple(found), classes, not found)
    return out
