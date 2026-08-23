"""Reconstruction-vs-actual-scanner fidelity check (memo §6.6).

For each comparable day, compares the reconstructed event field against the
live scanner's recorded output: overlap / Jaccard plus per-name disagreement
records. Material disagreement **blocks 0B** (the design's fidelity clause);
the threshold is a frozen module constant, not configuration.

Honest low-N: with fewer than :data:`MIN_COMPARABLE_DAYS` comparable days the
report is ``NOT_EVALUABLE`` — and fails closed (``blocks_0b=True``), because an
unmeasured fidelity is not a passed fidelity.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

#: Frozen: mean per-day disagreement rate (1 - Jaccard) above this blocks 0B.
DISAGREEMENT_THRESHOLD = 0.10
#: Frozen: fewer comparable days than this ⇒ NOT_EVALUABLE (fail closed).
MIN_COMPARABLE_DAYS = 5

STATUS_OK = "OK"
STATUS_BLOCKS_0B = "BLOCKS_0B"
STATUS_NOT_EVALUABLE = "NOT_EVALUABLE"

FIDELITY_SCHEMA = "gapper_stage0/fidelity_report/v1"


def compare_day(
    asof: str,
    reconstructed_symbols: Iterable[str],
    scanner_symbols: Iterable[str],
) -> dict[str, Any]:
    """One day's reconstruction-vs-scanner comparison with per-name records."""
    recon = {s.strip().upper() for s in reconstructed_symbols if s and s.strip()}
    scan = {s.strip().upper() for s in scanner_symbols if s and s.strip()}
    union = recon | scan
    overlap = recon & scan
    jaccard = 1.0 if not union else len(overlap) / len(union)
    disagreements = [
        {"symbol": s, "in_reconstruction": s in recon, "in_scanner": s in scan}
        for s in sorted(union - overlap)
    ]
    return {
        "asof": asof,
        "reconstructed_count": len(recon),
        "scanner_count": len(scan),
        "overlap_count": len(overlap),
        "jaccard": round(jaccard, 6),
        "disagreement_rate": round(1.0 - jaccard, 6),
        "disagreements": disagreements,
    }


def fidelity_report(
    day_comparisons: Sequence[dict[str, Any]],
    *,
    disagreement_threshold: float = DISAGREEMENT_THRESHOLD,
    min_comparable_days: int = MIN_COMPARABLE_DAYS,
) -> dict[str, Any]:
    """Aggregate day comparisons into the fidelity verdict for the 0A→0B gate.

    ``blocks_0b`` is True whenever fidelity is bad **or unmeasurable** — the
    low-N case never reads as a pass.
    """
    n = len(day_comparisons)
    if n < min_comparable_days:
        return {
            "schema": FIDELITY_SCHEMA,
            "status": STATUS_NOT_EVALUABLE,
            "blocks_0b": True,
            "comparable_days": n,
            "min_comparable_days": min_comparable_days,
            "mean_disagreement_rate": None,
            "disagreement_threshold": disagreement_threshold,
            "days": list(day_comparisons),
            "reason": (
                f"only {n} comparable day(s) < required {min_comparable_days} — "
                "fidelity is unmeasured, not passed"
            ),
        }
    mean_rate = sum(float(d["disagreement_rate"]) for d in day_comparisons) / n
    blocks = mean_rate > disagreement_threshold
    return {
        "schema": FIDELITY_SCHEMA,
        "status": STATUS_BLOCKS_0B if blocks else STATUS_OK,
        "blocks_0b": blocks,
        "comparable_days": n,
        "min_comparable_days": min_comparable_days,
        "mean_disagreement_rate": round(mean_rate, 6),
        "disagreement_threshold": disagreement_threshold,
        "days": list(day_comparisons),
        "reason": (
            f"mean disagreement {mean_rate:.4f} > threshold {disagreement_threshold}"
            if blocks
            else None
        ),
    }
