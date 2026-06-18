"""Lifecycle-aware promotion gate + confidence score (P10 Phase 2 §3).

Generalizes the range-trader §5c gate (`scripts/range_5c_gate.py`) into a
metric-agnostic, profile-driven gate that any experiment kind reuses. A
``GateProfile`` is a list of ``Criterion`` (predicates over a flat metrics dict)
plus an *evidence* knob (the §5c trade-count floor/strong pattern). The gate emits:

  - a **verdict** (GO / GO_WARNING / NO-GO / INCONCLUSIVE),
  - the corresponding **research_state** (VALIDATED / REJECTED / RESEARCH),
  - a **confidence score 0–100** (weighted fraction of criteria passed), and
  - per-criterion checks + reasons.

``gate_experiment`` applies a profile to a recorded experiment, stores the
confidence score, and transitions the experiment's research_state **with a reason**
(the registry's "why" audit trail). Deployment transitions stay owner-driven via
the promotion workflow (docs/runbook/promotion-workflow.md) — the gate validates;
it never deploys.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.research.registry import ResearchStore

Metrics = dict[str, Any]


@dataclass(frozen=True)
class Criterion:
    label: str
    passed: Callable[[Metrics], bool]
    detail: Callable[[Metrics], str]
    weight: float = 1.0
    component: str = "overall"           # Phase 3A §4.7: scorecard component group


@dataclass(frozen=True)
class GateProfile:
    name: str
    criteria: list[Criterion]
    evidence_key: str | None = None      # e.g. 'trade_count' — gates INCONCLUSIVE/strength
    evidence_floor: float = 0.0          # < floor → INCONCLUSIVE (can't pass or fail)
    evidence_strong: float = 0.0         # >= strong → GO, else GO_WARNING
    min_confidence: float = 0.0          # Phase 3A §4.7a: confidence floor below which
                                         # the verdict is NO-GO even if every criterion
                                         # passes (default 0 = inert for existing profiles)


@dataclass(frozen=True)
class ComponentScore:
    """Per-component scorecard slice (Phase 3A §4.7) — makes the confidence score
    transparent (e.g. statistical 24/30, drawdown 18/20)."""
    component: str
    passed_weight: float
    total_weight: float

    @property
    def fraction(self) -> float:
        return self.passed_weight / self.total_weight if self.total_weight else 0.0


@dataclass
class GateResult:
    verdict: str                          # GO | GO_WARNING | NO-GO | INCONCLUSIVE
    research_state: str                   # VALIDATED | REJECTED | RESEARCH
    confidence_score: int                 # 0–100
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    component_scores: list[ComponentScore] = field(default_factory=list)


# ---- criterion builders (flat-dict predicates; missing key → fails closed) ----


def _num(m: Metrics, key: str) -> float | None:
    v = m.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def ge(key: str, thr: float, *, weight: float = 1.0, label: str | None = None,
       component: str = "overall") -> Criterion:
    def passed(m: Metrics) -> bool:
        v = _num(m, key)
        return v is not None and v >= thr
    return Criterion(label or f"{key} >= {thr}", passed,
                     lambda m: f"{m.get(key)} vs >= {thr}", weight, component)


def le(key: str, thr: float, *, weight: float = 1.0, label: str | None = None,
       component: str = "overall") -> Criterion:
    def passed(m: Metrics) -> bool:
        v = _num(m, key)
        return v is not None and v <= thr
    return Criterion(label or f"{key} <= {thr}", passed,
                     lambda m: f"{m.get(key)} vs <= {thr}", weight, component)


def predicate(label: str, fn: Callable[[Metrics], bool], detail: Callable[[Metrics], str],
              *, weight: float = 1.0, component: str = "overall") -> Criterion:
    return Criterion(label, fn, detail, weight, component)


# ---- built-in profiles ----

# book_backtest — faithful port of the §5c pre-registered criteria. Operates on a
# flat metrics dict: profit_factor, win_rate, avg_win_loss, expectancy_r,
# max_drawdown (negative frac), is_pf, oos_pf, data_coverage, robust_pf_ratio,
# robust_trade_ratio, trade_count (the evidence key).
def _oos_pf_ok(m: Metrics) -> bool:
    oos, is_pf = _num(m, "oos_pf"), _num(m, "is_pf")
    if oos is None or is_pf is None:
        return False
    return oos >= max(1.0, 0.8 * is_pf)


BOOK_BACKTEST_PROFILE = GateProfile(
    name="book_backtest",
    evidence_key="trade_count", evidence_floor=30, evidence_strong=50,
    criteria=[
        ge("profit_factor", 1.3, label="profit_factor >= 1.3"),
        ge("win_rate", 0.45, label="win_rate >= 0.45"),
        ge("avg_win_loss", 1.0, label="avg_win/avg_loss >= 1.0"),
        ge("expectancy_r", 0.15, label="expectancy >= 0.15R"),
        predicate("max_drawdown <= 8%", lambda m: (_num(m, "max_drawdown") or -1.0) >= -0.08,
                  lambda m: f"{m.get('max_drawdown')} vs >= -0.08", weight=2.0),
        predicate("oos_pf >= max(1.0, 0.8*is_pf)", _oos_pf_ok,
                  lambda m: f"oos {m.get('oos_pf')} vs is {m.get('is_pf')}", weight=2.0),
        ge("data_coverage", 0.97, label="data_coverage >= 0.97"),
        ge("robust_pf_ratio", 0.8, label="robust PF >= 0.8x", weight=2.0),
        ge("robust_trade_ratio", 0.8, label="robust trades >= 0.8x", weight=2.0),
    ],
)

# factor_ic — a flat single-factor profile (oos_ic, oos_ls_sharpe, ic_hit,
# rolling_ic_pct_positive). evidence = n_periods.
FACTOR_IC_PROFILE = GateProfile(
    name="factor_ic",
    evidence_key="n_periods", evidence_floor=24, evidence_strong=60,
    criteria=[
        predicate("oos_ic > 0", lambda m: (_num(m, "oos_ic") or 0.0) > 0,
                  lambda m: f"{m.get('oos_ic')}", weight=2.0),
        ge("oos_ls_sharpe", 0.5, label="oos LS-Sharpe >= 0.5", weight=2.0),
        ge("ic_hit", 0.5, label="IC>0 in >= 50% of months"),
        ge("rolling_ic_pct_positive", 0.6, label="rolling-12m IC positive >= 60%", weight=2.0),
    ],
)

# portfolio_backtest — Phase 3A §4.7a FROZEN GO/NO-GO thresholds (pre-registered
# before the study runs — §5c discipline). Risk-adjusted + downside only; raw return is
# deliberately NOT a criterion. Component-tagged for the transparent scorecard (§4.7).
# min_confidence=70 is a deployable-research bar above the bare weighted average; a
# method scoring <70 is NO-GO even if individual criteria pass. evidence = n_rebalances
# (floor 52 ≈ 1yr weekly → INCONCLUSIVE below; strong 156 ≈ 3yr → GO vs GO_WARNING).
#
# ⚠ A GO here means research-VALIDATED, NOT deployable. It transitions only the
# experiment's research_state → VALIDATED; it does not touch any deployment_state,
# the live paper book (id=2), or authorize trading. Deployment stays an owner decision
# via the promotion-workflow runbook (ADR 0019). (§4.7 do-not-promote reminder.)
PORTFOLIO_BACKTEST_PROFILE = GateProfile(
    name="portfolio_backtest",
    evidence_key="n_rebalances", evidence_floor=52, evidence_strong=156,
    min_confidence=70,
    criteria=[
        ge("sharpe", 0.5, label="book Sharpe >= 0.5", weight=2.0, component="statistical"),
        ge("sortino", 0.7, label="Sortino >= 0.7", weight=1.0, component="statistical"),
        ge("excess_sharpe", 0.0, label="excess Sharpe >= 0 (vs benchmark)",
           weight=1.0, component="statistical"),
        ge("oos_is_sharpe_ratio", 0.8, label="OOS Sharpe >= 0.8x IS Sharpe",
           weight=2.0, component="oos_stability"),
        ge("rolling_sharpe_positive_frac", 0.55, label="rolling Sharpe positive >= 55%",
           weight=1.0, component="oos_stability"),
        ge("excess_max_dd", 0.0, label="max DD <= benchmark maxDD (excess_max_dd >= 0)",
           weight=2.0, component="drawdown"),
        ge("calmar", 0.5, label="Calmar >= 0.5", weight=1.0, component="drawdown"),
        le("turnover_annual", 4.0, label="annual turnover <= 400%",
           weight=1.0, component="turnover"),
        le("max_weight_change", 0.25, label="single-name weight stability <= 0.25",
           weight=1.0, component="turnover"),
        le("avg_adv_participation", 0.02, label="ADV participation <= 2%",
           weight=1.0, component="capacity"),
    ],
)

PROFILES: dict[str, GateProfile] = {
    "book_backtest": BOOK_BACKTEST_PROFILE,
    "factor_ic": FACTOR_IC_PROFILE,
    "portfolio_backtest": PORTFOLIO_BACKTEST_PROFILE,
}


# ---- evaluation ----


def evaluate(metrics: Metrics, profile: GateProfile) -> GateResult:
    """Apply ``profile`` to a flat ``metrics`` dict. Confidence is the
    weight-weighted fraction of criteria passed (0–100). Verdict follows §5c:
    INCONCLUSIVE below the evidence floor; else all-pass → GO (evidence >= strong)
    or GO_WARNING; otherwise NO-GO."""
    checks = [(c.label, c.passed(metrics), c.detail(metrics)) for c in profile.criteria]
    total_w = sum(c.weight for c in profile.criteria) or 1.0
    passed_w = sum(c.weight for c, (_, ok, _) in zip(profile.criteria, checks, strict=True) if ok)
    confidence = round(100 * passed_w / total_w)

    # Per-component breakdown (Phase 3A §4.7) — transparent scorecard.
    comp_total: dict[str, float] = {}
    comp_passed: dict[str, float] = {}
    for c, (_, ok, _) in zip(profile.criteria, checks, strict=True):
        comp_total[c.component] = comp_total.get(c.component, 0.0) + c.weight
        if ok:
            comp_passed[c.component] = comp_passed.get(c.component, 0.0) + c.weight
    component_scores = [
        ComponentScore(comp, comp_passed.get(comp, 0.0), tot) for comp, tot in comp_total.items()
    ]

    def _result(verdict: str, state: str, reasons: list[str]) -> GateResult:
        return GateResult(verdict, state, confidence, checks, reasons, component_scores)

    evidence = _num(metrics, profile.evidence_key) if profile.evidence_key else None
    reasons: list[str] = []
    if profile.evidence_key and (evidence is None or evidence < profile.evidence_floor):
        reasons.append(
            f"{profile.evidence_key}={evidence} < floor {profile.evidence_floor} → not enough evidence"
        )
        return _result("INCONCLUSIVE", "RESEARCH", reasons)

    # §4.7a confidence floor — a "deployable-research" bar above the bare weighted
    # average. Surfaced as a reason whenever it bites, whether the NO-GO is driven by
    # a criterion failure (which dragged confidence below the floor) or — in profiles
    # where criteria are advisory — by the floor alone on an otherwise all-pass run.
    below_floor = confidence < profile.min_confidence

    failed = [label for label, ok, _ in checks if not ok]
    if failed:
        reasons.append("failed: " + ", ".join(failed))
        if below_floor:
            reasons.append(f"confidence {confidence} < min_confidence {profile.min_confidence}")
        return _result("NO-GO", "REJECTED", reasons)

    if below_floor:
        reasons.append(f"confidence {confidence} < min_confidence {profile.min_confidence}")
        return _result("NO-GO", "REJECTED", reasons)

    strong = evidence is None or evidence >= profile.evidence_strong
    verdict = "GO" if strong else "GO_WARNING"
    if not strong:
        reasons.append(
            f"{profile.evidence_key}={evidence} in [{profile.evidence_floor},"
            f"{profile.evidence_strong}) → owner signoff (thin sample)"
        )
    return _result(verdict, "VALIDATED", reasons)


def gate_experiment(
    store: ResearchStore, experiment_id: str, *, profile: GateProfile | str,
    metrics: Metrics | None = None, actor: str = "promotion_gate",
) -> GateResult:
    """Gate a recorded experiment: evaluate the profile against its metrics, store
    the confidence score, and transition the experiment's research_state **with a
    reason**. ``metrics`` defaults to the experiment's ``metrics_summary`` (pass a
    sub-slice for a multi-factor experiment). Returns the ``GateResult``."""
    prof = PROFILES[profile] if isinstance(profile, str) else profile
    exp = store.get_experiment(experiment_id)
    if exp is None:
        raise ValueError(f"experiment {experiment_id} not found")
    result = evaluate(metrics if metrics is not None else exp.metrics_summary, prof)

    store.set_experiment_confidence(experiment_id, result.confidence_score)
    if result.research_state in ("VALIDATED", "REJECTED"):
        reason = f"gate[{prof.name}] {result.verdict} (confidence {result.confidence_score})"
        if result.reasons:
            reason += " — " + "; ".join(result.reasons)
        store.transition(entity_type="experiment", entity_id=experiment_id, axis="research",
                         to_state=result.research_state, reason=reason, actor=actor)
    return result
