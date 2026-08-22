"""§3.3 frozen GO thresholds + the guarded verdict seam (memo §6.9).

The thresholds are module-level frozen constants — locked once Stage 0
executes, never configuration. The verdict function is the ONLY verdict path
(the PR #511 lesson: no ad-hoc verdict invocation), and it is triple-guarded:

1. the §3.1 dataset contract must be complete (``dataset_contract``),
2. the owner G4/§9 execution token must verify (``interlock``),
3. every §3.3 measurement input must be present,

and the supplied design hash must equal the approved constant (a superseded or
mismatched design is never evaluable). Any guard failing ⇒ ``NOT_EVALUABLE``
with explicit reasons. The oracle top-subset bound is corroboration only and is
**branded DIAGNOSTIC_ONLY in the output schema itself** — it never gates.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.research.gapper_stage0.dataset_contract import DatasetContract
from app.research.gapper_stage0.design_latch import APPROVED_DESIGN_SHA256, SUPERSEDED_SHA256
from app.research.gapper_stage0.interlock import NOT_AUTHORIZED_REASON, verify_execution_token

# ---- §3.3 frozen GO thresholds (locked once Stage 0 executes) ---------------
GO_MIN_ELIGIBLE_NAMES = 10  # ≥10 eligible names ...
GO_MIN_ELIGIBLE_DAY_FRACTION = 0.50  # ... on ≥50% of usable event days
GO_MIN_PRIMARY_IQR_BPS = 150.0  # primary-horizon dispersion IQR ≥150 bps
GO_MAX_FRICTION_TO_IQR = 0.25  # friction / IQR ≤25%
GO_MIN_ORACLE_NET_POSITIVE = 0.65  # oracle net-positive ≥65% — DIAGNOSTIC ONLY
GO_MIN_CHEAP_SIGNAL_EDGE_BPS = 20.0  # cheap-signal edge ≥20 bps per traded day
GO_MIN_POSITIVE_DAY_FRACTION = 0.55  # positive days ≥55%
GO_MAX_EXECUTION_FAILURE_RATE = 0.10  # serious execution-failure rate ≤10%

#: The oracle metric's permanent brand, embedded in every output schema.
ORACLE_METRIC = "oracle_top_subset"
ORACLE_BRAND = "DIAGNOSTIC_ONLY"

NOT_EVALUABLE = "NOT_EVALUABLE"
VERDICT_SCHEMA = "gapper_stage0/verdict/v1"

#: Measurement inputs the verdict requires — all §3.3 quantities.
REQUIRED_MEASUREMENTS = (
    "eligible_day_fraction",  # fraction of usable days with ≥10 eligible names
    "primary_iqr_bps",
    "friction_to_iqr",
    "oracle_net_positive_fraction",
    "cheap_signal_edge_bps",
    "positive_day_fraction",
    "execution_failure_rate",
)


def evaluate_thresholds(measurements: Mapping[str, float]) -> dict[str, Any]:
    """Pure per-threshold comparison — measurement vs frozen constant.

    Returns per-check records; the oracle record carries its DIAGNOSTIC_ONLY
    brand in-schema and ``gates=False``. Computes no overall verdict.
    """
    m = {k: float(measurements[k]) for k in REQUIRED_MEASUREMENTS}
    checks: dict[str, dict[str, Any]] = {
        "eligible_day_fraction": {
            "value": m["eligible_day_fraction"],
            "threshold": GO_MIN_ELIGIBLE_DAY_FRACTION,
            "direction": ">=",
            "passes": m["eligible_day_fraction"] >= GO_MIN_ELIGIBLE_DAY_FRACTION,
            "gates": True,
            "note": f"days with >= {GO_MIN_ELIGIBLE_NAMES} eligible names",
        },
        "primary_iqr_bps": {
            "value": m["primary_iqr_bps"],
            "threshold": GO_MIN_PRIMARY_IQR_BPS,
            "direction": ">=",
            "passes": m["primary_iqr_bps"] >= GO_MIN_PRIMARY_IQR_BPS,
            "gates": True,
        },
        "friction_to_iqr": {
            "value": m["friction_to_iqr"],
            "threshold": GO_MAX_FRICTION_TO_IQR,
            "direction": "<=",
            "passes": m["friction_to_iqr"] <= GO_MAX_FRICTION_TO_IQR,
            "gates": True,
        },
        "oracle_net_positive_fraction": {
            "metric": ORACLE_METRIC,
            "brand": ORACLE_BRAND,
            "value": m["oracle_net_positive_fraction"],
            "threshold": GO_MIN_ORACLE_NET_POSITIVE,
            "direction": ">=",
            "passes": m["oracle_net_positive_fraction"] >= GO_MIN_ORACLE_NET_POSITIVE,
            "gates": False,  # corroboration only — never gates the verdict
        },
        "cheap_signal_edge_bps": {
            "value": m["cheap_signal_edge_bps"],
            "threshold": GO_MIN_CHEAP_SIGNAL_EDGE_BPS,
            "direction": ">=",
            "passes": m["cheap_signal_edge_bps"] >= GO_MIN_CHEAP_SIGNAL_EDGE_BPS,
            "gates": True,
        },
        "positive_day_fraction": {
            "value": m["positive_day_fraction"],
            "threshold": GO_MIN_POSITIVE_DAY_FRACTION,
            "direction": ">=",
            "passes": m["positive_day_fraction"] >= GO_MIN_POSITIVE_DAY_FRACTION,
            "gates": True,
        },
        "execution_failure_rate": {
            "value": m["execution_failure_rate"],
            "threshold": GO_MAX_EXECUTION_FAILURE_RATE,
            "direction": "<=",
            "passes": m["execution_failure_rate"] <= GO_MAX_EXECUTION_FAILURE_RATE,
            "gates": True,
        },
    }
    return checks


def _not_evaluable(reasons: list[str]) -> dict[str, Any]:
    return {"schema": VERDICT_SCHEMA, "verdict": NOT_EVALUABLE, "reasons": reasons}


def stage0_verdict(
    *,
    contract: DatasetContract,
    measurements: Mapping[str, float] | None,
    token_path: str | Path | None,
    design_sha: str,
) -> dict[str, Any]:
    """THE verdict seam. Returns ``NOT_EVALUABLE`` with explicit reasons unless
    every guard clears; only then evaluates the frozen §3.3 thresholds.

    GO requires every gating check to pass; otherwise HOLD (per §3.1, a data
    shortfall is a HOLD shape — re-entry requires a dataset improvement). The
    early-STOP rule fires during Stage-0 *execution*, which this preparation
    harness never performs, so STOP is not derivable here.
    """
    reasons: list[str] = []
    if design_sha == SUPERSEDED_SHA256:
        reasons.append("design is SUPERSEDED (never approved) — verdict impossible")
    elif design_sha != APPROVED_DESIGN_SHA256:
        reasons.append("design hash does not match the approved v2.1.1 artifact")
    if not contract.is_complete():
        reasons.append(
            "dataset contract incomplete — unset owner terms: " + ", ".join(contract.unset_terms())
        )
    if not verify_execution_token(token_path):
        reasons.append(NOT_AUTHORIZED_REASON)
    missing = [
        k for k in REQUIRED_MEASUREMENTS if measurements is None or measurements.get(k) is None
    ]
    if missing:
        reasons.append(f"measurement inputs missing: {', '.join(missing)}")
    if reasons:
        return _not_evaluable(reasons)

    assert measurements is not None  # guarded above
    checks = evaluate_thresholds(measurements)
    gating_pass = all(c["passes"] for c in checks.values() if c["gates"])
    return {
        "schema": VERDICT_SCHEMA,
        "verdict": "GO" if gating_pass else "HOLD",
        "thresholds": checks,
        "oracle": {
            "metric": ORACLE_METRIC,
            "brand": ORACLE_BRAND,
            "value": checks["oracle_net_positive_fraction"]["value"],
            "passes": checks["oracle_net_positive_fraction"]["passes"],
        },
        "reasons": [],
        "contract_sha256": contract.sha256(),
    }
