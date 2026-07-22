"""§8 live-class drift audit — seam comparison + report core (ADR 0044 equivalence).

The trustworthy comparison at the heart of the drift audit: given, for each session, the
decision-seam outputs of the LIVE ``MomentumDaily`` and the Stage 2-4 replica computed on the
SAME input, classify every difference against the §8 bands (repair plan lines 112-116) and
build an adjudication report.

This module is pure and fully testable — no strategy, adapters, or historical data. The driver
(``scripts/drift_audit_momentum_daily.py``) produces the per-session :class:`SeamRecord`s (by
driving the live class through history + running the replica) and feeds them here.

§8 bands:
  * SEMANTIC (zero tolerance — any diff is a reported mismatch): eligible candidate membership,
    ranking order, selected target names + order, trade-initiated (bool).
  * NUMERIC (band): per-name target weight ≤1 bp abs; regime gross ≤5 bps/day abs; and, over the
    run, mean abs daily gross ≤1 bp, max daily gross ≤5 bps.
  * STRUCTURAL (mandatory, identical): first eligible-review date, first trade date, initial
    selected names, initial ranking, cold-start trigger count == 1, duplicate seed attempts == 0.
  * Scores are compared as a DIAGNOSTIC (max abs diff reported) — the gate is the semantic seams
    they feed, not the intermediate score values.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- §8 numeric bands (repair plan lines 112-116) ------------------------------------------
WEIGHT_ABS_TOL = 1e-4        # 1 bp — per-name target weight
GROSS_DAILY_ABS_TOL = 5e-4   # 5 bps/day — regime gross path
GROSS_MEAN_ABS_TOL = 1e-4    # mean abs daily gross ≤ 1 bp (run-level)
GROSS_MAX_ABS_TOL = 5e-4     # max daily gross ≤ 5 bps (run-level)

# Semantic seam categories (zero-tolerance) and the numeric ones.
SEMANTIC_SEAMS = ("eligible", "ranking", "target_names", "trade_initiated")
NUMERIC_SEAMS = ("weights", "regime_gross")


@dataclass(frozen=True)
class SeamRecord:
    """One session's decision-seam outputs from ONE side (live or replica)."""

    date: str                              # ISO session date
    scores: dict[str, float]               # ticker -> score (diagnostic)
    eligible: tuple[str, ...]              # eligible candidates, in ranking order
    ranking: tuple[str, ...]               # full ranking order (== eligible order here)
    target_names: tuple[str, ...]          # selected target set, in order
    weights: dict[str, float]              # ticker -> target weight
    regime_gross: float                    # applied regime-scaled gross
    trade_initiated: bool                  # did a trade fire this session?
    trigger: str = ""                      # reason/trigger label (diagnostic)
    is_seed: bool = False                  # cold-start initial_seed fired this session?


@dataclass
class DaySeamDiff:
    date: str
    semantic_mismatches: list[str] = field(default_factory=list)   # seam names that differ
    numeric_violations: list[str] = field(default_factory=list)     # numeric seams over band
    score_max_abs_diff: float = 0.0                                 # diagnostic
    detail: dict = field(default_factory=dict)

    @property
    def any_mismatch(self) -> bool:
        return bool(self.semantic_mismatches or self.numeric_violations)

    @property
    def economically_material(self) -> bool:
        """A change in the traded portfolio (target names or trade-initiated) or a weight/gross
        band breach moves real exposure; a score-only diagnostic diff does not."""
        return (
            "target_names" in self.semantic_mismatches
            or "trade_initiated" in self.semantic_mismatches
            or bool(self.numeric_violations)
        )


def compare_day(live: SeamRecord, replica: SeamRecord) -> DaySeamDiff:
    """Compare one session's seams. Semantic seams are exact; numeric seams use §8 bands."""
    if live.date != replica.date:
        raise ValueError(f"date mismatch: {live.date} != {replica.date}")
    d = DaySeamDiff(date=live.date)

    if live.eligible != replica.eligible:
        d.semantic_mismatches.append("eligible")
        d.detail["eligible"] = {"live": list(live.eligible), "replica": list(replica.eligible)}
    if live.ranking != replica.ranking:
        d.semantic_mismatches.append("ranking")
        d.detail["ranking"] = {"live": list(live.ranking), "replica": list(replica.ranking)}
    if live.target_names != replica.target_names:
        d.semantic_mismatches.append("target_names")
        d.detail["target_names"] = {"live": list(live.target_names),
                                    "replica": list(replica.target_names)}
    if live.trade_initiated != replica.trade_initiated:
        d.semantic_mismatches.append("trade_initiated")
        d.detail["trade_initiated"] = {"live": live.trade_initiated,
                                       "replica": replica.trade_initiated,
                                       "live_trigger": live.trigger, "replica_trigger": replica.trigger}

    # numeric: per-name weight (union of names)
    wkeys = set(live.weights) | set(replica.weights)
    wmax = max((abs(live.weights.get(k, 0.0) - replica.weights.get(k, 0.0)) for k in wkeys),
               default=0.0)
    if wmax > WEIGHT_ABS_TOL:
        d.numeric_violations.append("weights")
        d.detail["weights"] = {"max_abs_diff": wmax, "tol": WEIGHT_ABS_TOL}
    gdiff = abs(live.regime_gross - replica.regime_gross)
    if gdiff > GROSS_DAILY_ABS_TOL:
        d.numeric_violations.append("regime_gross")
        d.detail["regime_gross"] = {"abs_diff": gdiff, "tol": GROSS_DAILY_ABS_TOL,
                                    "live": live.regime_gross, "replica": replica.regime_gross}

    skeys = set(live.scores) | set(replica.scores)
    d.score_max_abs_diff = max(
        (abs(live.scores.get(k, 0.0) - replica.scores.get(k, 0.0)) for k in skeys), default=0.0)
    return d


@dataclass
class DriftReport:
    n_sessions: int
    first_mismatch_date: str | None
    total_mismatch_sessions: int
    category_counts: dict[str, int]                 # seam -> # sessions it differed
    structural: dict[str, object]                    # structural checks + pass/fail
    gross_mean_abs_diff: float
    gross_max_abs_diff: float
    material_mismatch_sessions: int
    first_mismatch_detail: dict | None
    conformance_verdict: str                          # PASS_STRUCTURAL | MISMATCHES_TO_ADJUDICATE
    # --- first-cause vs downstream (a diagnostic drift census, not a pass gate) ---
    census: dict[str, int]                            # separated mismatch-session counts by kind
    first_cause: dict | None                          # {date, categories} of the FIRST divergence
    sessions_clean_before_divergence: int             # matching sessions before the first mismatch
    downstream_mismatch_sessions: int                 # mismatch sessions AFTER the first (propagation)
    turnover: dict                                    # {live, replica, abs_diff} — diagnostic

    def to_dict(self) -> dict:
        return {
            "n_sessions": self.n_sessions,
            "conformance_verdict": self.conformance_verdict,
            "structural": self.structural,
            "census": self.census,
            "first_cause": self.first_cause,
            "sessions_clean_before_divergence": self.sessions_clean_before_divergence,
            "first_mismatch_date": self.first_mismatch_date,
            "total_mismatch_sessions": self.total_mismatch_sessions,
            "downstream_mismatch_sessions": self.downstream_mismatch_sessions,
            "material_mismatch_sessions": self.material_mismatch_sessions,
            "category_counts": self.category_counts,
            "turnover": self.turnover,
            "gross_mean_abs_diff": self.gross_mean_abs_diff,
            "gross_max_abs_diff": self.gross_max_abs_diff,
            "first_mismatch_detail": self.first_mismatch_detail,
            "_note": ("This is a DIAGNOSTIC drift census, not a pass gate. Counts AFTER "
                      "first_mismatch_date include propagation from holdings divergence — "
                      "read first_cause + sessions_clean_before_divergence for the primary "
                      "divergence, not total_mismatch_sessions alone."),
        }


def _first_true_date(records: list[SeamRecord], pred) -> str | None:
    for r in records:
        if pred(r):
            return r.date
    return None


def _turnover(records: list[SeamRecord]) -> float:
    """Diagnostic turnover proxy: sum over consecutive sessions of 0.5·Σ|Δweight|."""
    total = 0.0
    prev: dict[str, float] = {}
    for r in records:
        keys = set(prev) | set(r.weights)
        total += 0.5 * sum(abs(r.weights.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        prev = r.weights
    return total


def build_report(live: list[SeamRecord], replica: list[SeamRecord]) -> DriftReport:
    """Aggregate per-session comparisons into the §8 adjudication report. ``live`` and
    ``replica`` must be the same sessions in the same order."""
    if len(live) != len(replica):
        raise ValueError(f"session count differs: live {len(live)} != replica {len(replica)}")
    diffs = [compare_day(a, b) for a, b in zip(live, replica, strict=True)]

    cats: dict[str, int] = dict.fromkeys(SEMANTIC_SEAMS + NUMERIC_SEAMS, 0)
    for d in diffs:
        for s in d.semantic_mismatches:
            cats[s] += 1
        for s in d.numeric_violations:
            cats[s] += 1

    mismatch_diffs = [d for d in diffs if d.any_mismatch]
    first = mismatch_diffs[0] if mismatch_diffs else None

    gross_abs = [abs(a.regime_gross - b.regime_gross) for a, b in zip(live, replica, strict=True)]
    gmean = sum(gross_abs) / len(gross_abs) if gross_abs else 0.0
    gmax = max(gross_abs, default=0.0)

    # Structural (mandatory identical) — first-eligible / first-trade / initial names+ranking,
    # cold-start trigger count == 1, duplicate seed attempts == 0.
    live_first_elig = _first_true_date(live, lambda r: bool(r.eligible))
    rep_first_elig = _first_true_date(replica, lambda r: bool(r.eligible))
    live_first_trade = _first_true_date(live, lambda r: r.trade_initiated)
    rep_first_trade = _first_true_date(replica, lambda r: r.trade_initiated)
    live_seed_count = sum(1 for r in live if r.is_seed)
    live_first_trade_rec = next((r for r in live if r.trade_initiated), None)
    rep_first_trade_rec = next((r for r in replica if r.trade_initiated), None)
    structural = {
        "first_eligible_date_identical": live_first_elig == rep_first_elig,
        "first_eligible_date": {"live": live_first_elig, "replica": rep_first_elig},
        "first_trade_date_identical": live_first_trade == rep_first_trade,
        "first_trade_date": {"live": live_first_trade, "replica": rep_first_trade},
        "initial_target_names_identical": (
            live_first_trade_rec is not None and rep_first_trade_rec is not None
            and live_first_trade_rec.target_names == rep_first_trade_rec.target_names),
        "initial_ranking_identical": (
            live_first_trade_rec is not None and rep_first_trade_rec is not None
            and live_first_trade_rec.ranking == rep_first_trade_rec.ranking),
        "cold_start_seed_count": live_seed_count,
        "cold_start_seed_count_is_one": live_seed_count == 1,
        "gross_mean_within_band": gmean <= GROSS_MEAN_ABS_TOL,
        "gross_max_within_band": gmax <= GROSS_MAX_ABS_TOL,
    }
    structural_pass = all(
        v for k, v in structural.items()
        if k.endswith(("_identical", "_is_one", "_within_band")))

    verdict = ("PASS_STRUCTURAL" if structural_pass and not mismatch_diffs
               else "MISMATCHES_TO_ADJUDICATE")

    # First-cause vs downstream: everything from the first mismatch onward is contaminated
    # by holdings divergence, so separate the clean prefix + first cause from the propagation.
    first_idx = next((i for i, d in enumerate(diffs) if d.any_mismatch), None)
    downstream = (sum(1 for d in diffs[first_idx + 1:] if d.any_mismatch)
                  if first_idx is not None else 0)
    census = {
        "structural_incompatible": int(not structural_pass),
        "semantic_mismatch_sessions": sum(1 for d in diffs if d.semantic_mismatches),
        "numeric_only_mismatch_sessions": sum(
            1 for d in diffs if d.numeric_violations and not d.semantic_mismatches),
        "eligible_mismatch_sessions": cats["eligible"],
        "ranking_mismatch_sessions": cats["ranking"],
        "target_mismatch_sessions": cats["target_names"],
        "trigger_mismatch_sessions": cats["trade_initiated"],
        "weight_mismatch_sessions": cats["weights"],
        "regime_gross_mismatch_sessions": cats["regime_gross"],
    }
    tl, tr = _turnover(live), _turnover(replica)
    return DriftReport(
        n_sessions=len(live),
        first_mismatch_date=first.date if first else None,
        total_mismatch_sessions=len(mismatch_diffs),
        category_counts=cats,
        structural=structural,
        gross_mean_abs_diff=gmean,
        gross_max_abs_diff=gmax,
        material_mismatch_sessions=sum(1 for d in mismatch_diffs if d.economically_material),
        first_mismatch_detail=({"date": first.date, "semantic": first.semantic_mismatches,
                                "numeric": first.numeric_violations, "detail": first.detail}
                               if first else None),
        conformance_verdict=verdict,
        census=census,
        first_cause=({"date": first.date,
                      "categories": list(first.semantic_mismatches) + list(first.numeric_violations)}
                     if first else None),
        sessions_clean_before_divergence=(first_idx if first_idx is not None else len(diffs)),
        downstream_mismatch_sessions=downstream,
        turnover={"live": tl, "replica": tr, "abs_diff": abs(tl - tr)},
    )


__all__ = [
    "GROSS_DAILY_ABS_TOL",
    "GROSS_MAX_ABS_TOL",
    "GROSS_MEAN_ABS_TOL",
    "WEIGHT_ABS_TOL",
    "DaySeamDiff",
    "DriftReport",
    "SeamRecord",
    "build_report",
    "compare_day",
]
