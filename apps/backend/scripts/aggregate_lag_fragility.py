"""GOVCONTRACT-001 — lag-fragility comparison aggregator (owner next-step 2).

The fragility probe re-runs the IDENTICAL economic study at each candidate disclosure lag. This tool
collapses those per-lag runs into ONE comparison artifact aligned by lag — effect size, uncertainty,
sample count, and verdict on one axis — rather than six disconnected reports, and classifies the
result per the disposition tree.

"survives(lag)" = the economic signal is present at that lag, i.e. the net-excess 95% CI EXCLUDES
zero on the favorable side (ci_low > 0). Disposition tree:

  robust through 56-60d           -> lag_not_decision_critical   (conclusion independent of calibration)
  survives 30d but fails 45-56d   -> pit_decision_critical       (PIT assumption is load-bearing)
  only survives 21-27d            -> leakage_concern             (edge needs an implausibly tight lag)
  fails at every lag              -> economic_rejection_reachable(reject WITHOUT deeper calibration)
  otherwise                       -> mixed_requires_review

An economic rejection is recorded SEPARATELY from the calibration-policy failure: they are different
findings and must not be collapsed into one ambiguous failure.

    python scripts/aggregate_lag_fragility.py --results lag21.json lag27.json ... --out fragility.json
"""

from __future__ import annotations

import argparse
import json
from typing import Any

GRID = [21, 27, 30, 45, 56, 60]
HIGH = [56, 60]   # robustness band
MID = [30, 45]
LOW = [21, 27]


def _extract(d: dict[str, Any]) -> dict[str, Any]:
    """Normalise a per-lag study result to (lag, effect_size, ci_low, ci_high, n)."""
    def pick(*names: str) -> Any:
        for n in names:
            if n in d and d[n] is not None:
                return d[n]
        return None
    ci = pick("ci95", "net_excess_ci95", "ci") or [None, None]
    return {
        "lag": pick("lag", "disclosure_lag_days", "lag_days"),
        "effect_size": pick("effect_size", "net_excess", "net_excess_pct", "point_estimate"),
        "ci_low": pick("ci_low") if pick("ci_low") is not None else ci[0],
        "ci_high": pick("ci_high") if pick("ci_high") is not None else ci[1],
        "n": pick("n", "n_benchmarked", "n_events", "sample_count"),
        "verdict": pick("verdict", "status"),
    }


def _survives(r: dict[str, Any]) -> bool:
    lo = r.get("ci_low")
    return lo is not None and lo > 0


def classify(by_lag: dict[int, dict[str, Any]]) -> str:
    surv = {lag: _survives(r) for lag, r in by_lag.items()}

    def s(lag: int) -> bool:
        return surv.get(lag, False)

    present = [lag for lag in GRID if lag in surv]
    if not any(surv.get(lag, False) for lag in present):
        return "economic_rejection_reachable"
    if all(s(lag) for lag in HIGH if lag in surv) and any(lag in surv for lag in HIGH):
        return "lag_not_decision_critical"
    if s(30) and not any(s(lag) for lag in [45, 56] if lag in surv):
        return "pit_decision_critical"
    if (s(21) or s(27)) and not any(s(lag) for lag in [45, 56, 60] if lag in surv):
        return "leakage_concern"
    return "mixed_requires_review"


_DISPOSITION = {
    "lag_not_decision_critical": "Economic conclusion does NOT depend on precise lag calibration; "
                                 "proceed with a conservative global lag.",
    "pit_decision_critical": "The PIT assumption is load-bearing — the edge appears at short lags and "
                             "disappears by 45-56d. Do NOT freeze a lag without the publication-cycle "
                             "cross-check; consider PIID-level reconciliation.",
    "leakage_concern": "Edge survives only at implausibly tight lags (21-27d) — strong look-ahead / "
                       "leakage concern. Treat any positive result as suspect.",
    "economic_rejection_reachable": "Signal fails at EVERY lag — economic rejection is reachable "
                                    "without deeper calibration. Record this as an ECONOMIC rejection, "
                                    "SEPARATE from the calibration-policy FAIL.",
    "mixed_requires_review": "Non-monotone survival across lags — inspect the per-lag artifact "
                             "directly before any decision.",
}


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    extracted = [_extract(d) for d in results]
    by_lag = {int(r["lag"]): r for r in extracted if r.get("lag") is not None}
    aligned = [{**by_lag[lag], "lag": lag, "survives": _survives(by_lag[lag])}
               for lag in sorted(by_lag)]
    classification = classify(by_lag)
    covered = sorted(by_lag)
    missing = [lag for lag in GRID if lag not in by_lag]
    return {
        "grid": GRID,
        "lags_covered": covered,
        "lags_missing": missing,  # never silently treat an un-run lag as passing
        "by_lag": aligned,
        "survives_by_lag": {str(lag): _survives(by_lag[lag]) for lag in covered},
        "classification": classification,
        "disposition": _DISPOSITION[classification],
        "note": ("survives = net-excess 95% CI excludes zero (ci_low > 0). An economic rejection is "
                 "recorded separately from the calibration-policy FAIL; they are distinct findings."),
    }


def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", nargs="+", required=True, help="per-lag study result JSON files")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    result = aggregate([_load(p) for p in args.results])
    print(f"lags covered: {result['lags_covered']}  missing: {result['lags_missing']}")
    for r in result["by_lag"]:
        mark = "SURVIVES" if r["survives"] else "fails"
        print(f"  lag {r['lag']:>3}: effect={r['effect_size']}  CI=[{r['ci_low']},{r['ci_high']}]  "
              f"n={r['n']}  -> {mark}")
    print(f"  CLASSIFICATION: {result['classification']}")
    print(f"  DISPOSITION: {result['disposition']}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
        print(f"  artifact -> {args.out}")


if __name__ == "__main__":
    main()
