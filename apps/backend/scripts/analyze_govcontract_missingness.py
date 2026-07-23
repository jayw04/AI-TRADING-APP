"""GOVCONTRACT-001 — reconciliation missingness & strategy-coverage analysis (owner next-step 1).

Consumes the per-event JSONL written by ``calibrate_govcontract_lag.py --events-out`` and adjudicates
whether the reconciled subpopulation is a defensible basis for interpreting the lag proxy — i.e.
whether reconciliation failure is *ignorable* or correlates with variables connected to expected
returns (award size, agency, recency). It calls NO external source: every cut is reproduced from the
persisted provenance fields.

Outputs (per the disposition):
  overall_reconciliation_rate
  material_award_reconciliation_rate_ge_250k        (the computable strategy-coverage down-payment)
  strategy_eligible_reconciliation_rate             (RESERVED — null until the full PIT + mktcap join)
  reconciliation_rate_by_stratum                    (categorical levels: reconciled share + n)
  categorical_association                           (chi-square + Cramér's V + max pp gap per stratum)
  continuous_standardized_difference                (SMD + KS + per-group quantiles: amount/recency/density)
  missingness_model_performance                     (multivariate logistic CV-AUC if sklearn, else fallback)

Material imbalance is a pre-declared GOVERNANCE RULE (not proof small differences are harmless):
  |standardized difference| > 0.20   OR   reconciliation-rate gap > 10 percentage points.

    python scripts/analyze_govcontract_missingness.py \
        --events data/govcontract_events.jsonl --out data/govcontract_missingness.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
from typing import Any

# reconciled = recipient FOUND (RECONCILED or AMBIGUOUS_CANDIDATE) — the 75.3% headline definition.
# adjudicated = any SEMANTIC outcome; operational failures are excluded (not a data property).
_RECONCILED = frozenset({"RECONCILED", "AMBIGUOUS_CANDIDATE"})
_SEMANTIC = frozenset({"RECONCILED", "AMBIGUOUS_CANDIDATE", "VALID_NON_RECONCILIATION"})
CATEGORICAL = ["year", "size", "recency_bucket", "name_quality", "agency_normalized"]
# Pre-event covariates only — knowable BEFORE the reconciliation attempt. These are the legitimate
# predictors of missingness.
CONTINUOUS = ["award_amount", "event_density"]
# OUTCOME-DERIVED quantities are produced BY the reconciliation query, so they separate reconciled
# from unreconciled almost tautologically (candidate_count is 0 for a VALID_NON_RECONCILIATION by
# construction). They must NEVER enter the missingness model (target leakage) — reported only as a
# labelled diagnostic.
OUTCOME_DERIVED = ["candidate_count"]
ABS_SMD_THRESHOLD = 0.20
RATE_GAP_PP_THRESHOLD = 10.0
MIN_LEVEL_N = 20  # a stratum level below this is folded into "(small)" so gaps aren't noise-driven


def _reconciled(row: dict[str, Any]) -> int:
    return 1 if row.get("reconcile_outcome") in _RECONCILED else 0


def _chi2_cramers_v(levels: dict[str, tuple[int, int]]) -> tuple[float, int, float]:
    """levels: level -> (n_reconciled, n_unreconciled). Returns (chi2, dof, cramers_v)."""
    rows = [pair for pair in levels.values() if sum(pair) > 0]
    n = sum(sum(r) for r in rows)
    if n == 0 or len(rows) < 2:
        return 0.0, 0, 0.0
    col_tot = [sum(r[j] for r in rows) for j in range(2)]
    chi2 = 0.0
    for r in rows:
        rt = sum(r)
        for j in range(2):
            exp = rt * col_tot[j] / n
            if exp > 0:
                chi2 += (r[j] - exp) ** 2 / exp
    dof = (len(rows) - 1) * (2 - 1)
    k = min(len(rows), 2)
    cramers_v = math.sqrt(chi2 / (n * (k - 1))) if n * (k - 1) > 0 else 0.0
    return round(chi2, 4), dof, round(cramers_v, 4)


def _chi2_pvalue(chi2: float, dof: int) -> float | None:
    try:
        from scipy.stats import chi2 as _c
        return round(float(_c.sf(chi2, dof)), 6)
    except Exception:
        return None


def _smd(a: list[float], b: list[float]) -> float:
    """Standardized mean difference (Cohen's d, pooled SD) between groups a and b. If within-group
    variance is zero but the group means differ (perfect separation), the pooled SD is undefined —
    fall back to the combined SD so maximal separation reads as maximally material, not as zero."""
    if len(a) < 2 or len(b) < 2:
        return 0.0
    va, vb = statistics.variance(a), statistics.variance(b)
    pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2))
    denom = pooled if pooled > 0 else statistics.pstdev(a + b)
    return round((statistics.mean(a) - statistics.mean(b)) / denom, 4) if denom > 0 else 0.0


def _ks(a: list[float], b: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov statistic (max ECDF gap), dependency-free."""
    if not a or not b:
        return 0.0
    xs = sorted(set(a) | set(b))
    sa, sb = sorted(a), sorted(b)

    def _ecdf(s: list[float], x: float) -> float:
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi) // 2
            if s[mid] <= x:
                lo = mid + 1
            else:
                hi = mid
        return lo / len(s)

    return round(max(abs(_ecdf(sa, x) - _ecdf(sb, x)) for x in xs), 4)


def _rank_auc(scores: list[float], labels: list[int]) -> float:
    """AUC = P(score | reconciled > score | unreconciled), tie-corrected (Mann-Whitney)."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and scores[order[j]] == scores[order[i]]:
            j += 1
        avg_rank = (i + j - 1) / 2 + 1  # 1-based average rank over the tie block
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        i = j
    sum_pos = sum(ranks[i] for i in range(len(scores)) if labels[i] == 1)
    return round((sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg), 4)


def _quantiles(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {}
    s = sorted(xs)
    def q(p: float) -> float:
        return round(float(s[min(len(s) - 1, int(p * len(s)))]), 2)
    return {"n": len(s), "p10": q(0.10), "p50": q(0.50), "p90": q(0.90),
            "mean": round(statistics.mean(s), 2)}


def _by_stratum(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[int]] = collections.defaultdict(list)
    for r in rows:
        groups[str(r.get(key))].append(_reconciled(r))
    out = []
    for level, labels in groups.items():
        n = len(labels)
        bucket = level if n >= MIN_LEVEL_N else "(small)"
        out.append({"level": level, "bucket": bucket, "n": n,
                    "reconciled_share": round(sum(labels) / n, 3)})
    return sorted(out, key=lambda s: s["n"], reverse=True)


def _categorical_association(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    levels: dict[str, list[int]] = collections.defaultdict(list)
    for r in rows:
        lvl = str(r.get(key))
        levels[lvl if len([x for x in rows if str(x.get(key)) == lvl]) >= MIN_LEVEL_N else "(small)"].append(_reconciled(r))
    counts = {lvl: (sum(v), len(v) - sum(v)) for lvl, v in levels.items() if len(v) >= MIN_LEVEL_N}
    chi2, dof, cv = _chi2_cramers_v(counts)
    shares = [s / (s + f) for s, f in counts.values() if (s + f) > 0]
    max_gap_pp = round((max(shares) - min(shares)) * 100, 1) if len(shares) >= 2 else 0.0
    material = (cv > ABS_SMD_THRESHOLD) or (max_gap_pp > RATE_GAP_PP_THRESHOLD)
    return {"n_levels": len(counts), "chi2": chi2, "dof": dof, "cramers_v": cv,
            "p_value": _chi2_pvalue(chi2, dof), "max_reconciled_gap_pp": max_gap_pp,
            "material_imbalance": material}


def _continuous_diff(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    rec = [float(r[key]) for r in rows if _reconciled(r) and r.get(key) is not None]
    unr = [float(r[key]) for r in rows if not _reconciled(r) and r.get(key) is not None]
    smd = _smd(rec, unr)
    return {"smd": smd, "ks": _ks(rec, unr), "material_imbalance": abs(smd) > ABS_SMD_THRESHOLD,
            "reconciled": _quantiles(rec), "unreconciled": _quantiles(unr)}


def _missingness_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Multivariate: how predictable is reconciliation from the covariates? A high AUC means
    missingness is structured (MNAR concern), not random. sklearn if present; else the strongest
    single-covariate rank-AUC as a documented lower bound."""
    labels = [_reconciled(r) for r in rows]
    if sum(labels) in (0, len(labels)):
        return {"method": "degenerate", "auc": None, "note": "all rows share one label"}
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import StratifiedKFold
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception:
        uni_aucs = {c: _rank_auc([float(r.get(c) or 0) for r in rows], labels) for c in CONTINUOUS}
        best = max(uni_aucs, key=lambda c: abs(uni_aucs[c] - 0.5))
        return {"method": "univariate_fallback_no_sklearn", "auc": uni_aucs[best],
                "best_covariate": best, "per_covariate_auc": uni_aucs,
                "note": "install scikit-learn for the multivariate CV-AUC"}

    # Pre-event continuous only (NO candidate_count — outcome-derived, target leakage). Categoricals
    # are one-hot ONLY if low-cardinality (<=12 levels); high-cardinality identity fields like
    # agency_normalized would let logistic regression memorise the label and inflate CV-AUC toward
    # 1.0. Their association is still measured honestly by the chi-square / Cramer's V above.
    MAX_MODEL_CARDINALITY = 12
    model_cats = [c for c in CATEGORICAL
                  if len({str(r.get(c)) for r in rows}) <= MAX_MODEL_CARDINALITY]
    excluded_high_card = [c for c in CATEGORICAL if c not in model_cats]
    cat_levels = {c: sorted({str(r.get(c)) for r in rows}) for c in model_cats}
    feats = []
    for r in rows:
        row = [math.log1p(float(r.get("award_amount") or 0)), float(r.get("event_density") or 0)]
        for c in model_cats:
            row.extend(1.0 if str(r.get(c)) == lvl else 0.0 for lvl in cat_levels[c])
        feats.append(row)
    y = labels
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    pipe = Pipeline([("sc", StandardScaler(with_mean=False)),
                     ("lr", LogisticRegression(max_iter=1000, C=1.0))])
    aucs = []
    for tr, te in skf.split(feats, y):
        pipe.fit([feats[i] for i in tr], [y[i] for i in tr])
        proba = pipe.predict_proba([feats[i] for i in te])[:, 1]
        if len({y[i] for i in te}) == 2:
            aucs.append(roc_auc_score([y[i] for i in te], proba))
    return {"method": "logistic_5fold_cv", "auc": round(sum(aucs) / len(aucs), 4) if aucs else None,
            "n_folds_scored": len(aucs),
            "model_covariates": ["award_amount", "event_density", *model_cats],
            "excluded_high_cardinality": excluded_high_card,
            "excluded_outcome_derived": OUTCOME_DERIVED,
            "note": "AUC near 0.5 => missingness ~ignorable; high AUC => structured (MNAR) missingness. "
                    "Pre-event covariates only; outcome-derived + high-cardinality identity fields excluded"}


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    adjudicated = [r for r in rows if r.get("reconcile_outcome") in _SEMANTIC]
    nadj = len(adjudicated)
    overall = round(sum(_reconciled(r) for r in adjudicated) / nadj, 4) if nadj else 0.0
    material = [r for r in adjudicated if r.get("amount_ge_250k")]
    mat_rate = round(sum(_reconciled(r) for r in material) / len(material), 4) if material else 0.0

    cat_assoc = {k: _categorical_association(adjudicated, k) for k in CATEGORICAL}
    cont_diff = {k: _continuous_diff(adjudicated, k) for k in CONTINUOUS}
    flags = [f"categorical:{k}" for k, v in cat_assoc.items() if v["material_imbalance"]]
    flags += [f"continuous:{k}" for k, v in cont_diff.items() if v["material_imbalance"]]
    # outcome-derived quantities: reported for transparency but EXCLUDED from the model + the flags
    # (they separate reconciled/unreconciled by construction, not because missingness is structured).
    outcome_diag = {k: {**_continuous_diff(adjudicated, k),
                        "note": "OUTCOME-DERIVED — excluded from missingness model + flags (target leakage)"}
                    for k in OUTCOME_DERIVED}

    return {
        "source": "govcontract per-event reconciliation JSONL",
        "reconciled_definition": "RECONCILED or AMBIGUOUS_CANDIDATE (recipient found; 75.3% headline)",
        "n_total": len(rows), "n_adjudicated": nadj,
        "n_operational_excluded": len(rows) - nadj,
        "overall_reconciliation_rate": overall,
        "material_award_reconciliation_rate_ge_250k": mat_rate,
        "n_material_award_ge_250k": len(material),
        "strategy_eligible_reconciliation_rate": None,  # RESERVED — full PIT + mktcap join
        "reconciliation_rate_by_stratum": {k: _by_stratum(adjudicated, k) for k in CATEGORICAL},
        "categorical_association": cat_assoc,
        "continuous_standardized_difference": cont_diff,
        "outcome_derived_diagnostic": outcome_diag,
        "missingness_model_performance": _missingness_model(adjudicated),
        "thresholds": {"abs_smd": ABS_SMD_THRESHOLD, "rate_gap_pp": RATE_GAP_PP_THRESHOLD,
                       "rule": "governance rule, NOT proof smaller differences are harmless"},
        "material_imbalance_flags": flags,
        "verdict": ("MATERIAL_IMBALANCE — reconciled subset is a biased basis; restrict scope or "
                    "re-architect" if flags else
                    "NO_MATERIAL_IMBALANCE — reconciled subset defensible pending strategy-eligible join"),
    }


def _load(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", required=True, help="per-event JSONL from calibrate --events-out")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    result = analyze(_load(args.events))
    print(f"n={result['n_total']} adjudicated={result['n_adjudicated']}  "
          f"overall_reconciliation={result['overall_reconciliation_rate']:.1%}  "
          f"material($>=250k)={result['material_award_reconciliation_rate_ge_250k']:.1%} "
          f"(n={result['n_material_award_ge_250k']})")
    for k, v in result["categorical_association"].items():
        flag = " *MATERIAL*" if v["material_imbalance"] else ""
        print(f"  cat {k:20} gap={v['max_reconciled_gap_pp']}pp  cramersV={v['cramers_v']}  "
              f"p={v['p_value']}{flag}")
    for k, v in result["continuous_standardized_difference"].items():
        flag = " *MATERIAL*" if v["material_imbalance"] else ""
        print(f"  cont {k:19} SMD={v['smd']}  KS={v['ks']}{flag}")
    for k, v in result["outcome_derived_diagnostic"].items():
        print(f"  [diag] {k:16} SMD={v['smd']}  KS={v['ks']}  (outcome-derived, excluded from model)")
    m = result["missingness_model_performance"]
    print(f"  missingness model [{m['method']}] AUC={m['auc']}  (pre-event covariates only)")
    print(f"  VERDICT: {result['verdict']}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
        print(f"  artifact -> {args.out}")


if __name__ == "__main__":
    main()
