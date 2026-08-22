"""SCAN-001 premarket-data gate — increment (D): the forward replication verdict.

Reads the back-filled daily evidence records and tests the gate's frozen hypothesis (plan §3):
*the candidate-set mean expansion `E` beats the eligible-field baseline on real premarket data*,
via the same seeded circular-block bootstrap used in v0.2–v0.5. Pure read-only analysis — no
order path, no LLM.

Verdict (frozen §3): **TRANSFERS** (edge CI-separated > 0 → recommend L4) · **DOES-NOT-TRANSFER**
(CI includes/below 0 → the engine is a liquid-universe tool; document the boundary) ·
**INSUFFICIENT** (< the minimum forward window, or too few contributing days → keep accruing).
Until the window clears the verdict is INSUFFICIENT and the live Candidate Report stays advisory
(ADR 0014 — partial forward data is not edge evidence).

Two admission rules stand in front of that classification. Neither adjudicates the hypothesis;
both refuse to let a record contribute evidence it does not carry.

**1. Record admission (evidence integrity).** A record contributes a forward day only if it is
``filled``, not ``stale``, and its ``source_date`` equals its ``asof`` — i.e. the premarket
snapshot it scored was actually captured on the day it claims to measure. ``source_date`` is
additionally unique across admitted records, so one market snapshot cannot be counted twice
under two ``asof`` dates. This exists because a scanner failure upstream can publish yesterday's
snapshot under today's date (see ``deploy/sync-gappers-to-box.sh``); the record schema records
that honestly, and the verdict must not ignore it. Serially duplicated observations would both
overstate the effective sample size and violate the bootstrap's independence assumption.

**2. Selection-contrast admission (identifiability).** ``edge_E`` is
``mean(candidates) − mean(eligible)`` and ``candidates ⊆ eligible``. When
``candidate_count == eligible_count`` the two sets are *identical*, so ``edge_E`` is 0.0 **by
construction** — the day formed no comparison group and measured nothing. Such a day is a
**zero-contrast** day, not a zero-edge day, and it is excluded from the series. If no admitted
day carries selection contrast the gate returns **INVALID-EVIDENCE / NO_SELECTION_CONTRAST**
rather than a pass/fail: under that condition the test cannot distinguish "the edge does not
transfer to the gappers universe" from "the pipeline never formed a comparison group", so it is
non-identifiable and no verdict is available at any sample size. This guard only ever *withholds*
a verdict; it never issues one.

The funnel and the pre-registered ranking design are deliberately untouched here — repairing the
collapse (so that ``candidates ⊊ eligible``) is a governed research-design change, not a bug fix.
``min_contrast_days`` / ``max_mean_selection_ratio`` are the hooks for the stricter
contrast-quality floors that decision will set; both default to ``None`` (not yet governed, so
not enforced) and are reported as diagnostics in the meantime.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any

from app.factor_data import evidence as ev

# Forward floor (gate plan §3): ~2 months of contributing scan days before a pass/fail is allowed.
MIN_FORWARD_DAYS = 40

# Exclusion reasons, in evaluation order (a record is attributed to the first one that fires).
EXCLUDE_NOT_FILLED = "not_filled"
EXCLUDE_STALE = "stale"
EXCLUDE_SOURCE_DATE_MISMATCH = "source_date_mismatch"
EXCLUDE_MISSING_PROVENANCE = "missing_provenance_fields"
EXCLUDE_DUPLICATE_SOURCE_DATE = "duplicate_source_date"
EXCLUDE_MISSING_FUNNEL_COUNTS = "missing_funnel_counts"


def _admission_reason(record: dict[str, Any], seen_source_dates: set[str]) -> str | None:
    """The reason ``record`` may not contribute a forward day, or ``None`` if it may.

    Strict by construction: a record that cannot *prove* it is a distinct, same-day observation
    is excluded. Every record written by ``premarket_evidence`` carries these fields, so a
    missing one signals a hand-edited or foreign record, not a legacy shape to accommodate.
    """
    if record.get("outcome_status") != "filled" or not record.get("outcomes"):
        return EXCLUDE_NOT_FILLED

    asof, source_date = record.get("asof"), record.get("source_date")
    if not asof or not source_date or "stale" not in record:
        return EXCLUDE_MISSING_PROVENANCE
    if record.get("stale") is True:
        return EXCLUDE_STALE
    if source_date != asof:
        return EXCLUDE_SOURCE_DATE_MISMATCH
    if source_date in seen_source_dates:
        return EXCLUDE_DUPLICATE_SOURCE_DATE

    funnel = record.get("funnel") or {}
    if funnel.get("candidate_count") is None or funnel.get("eligible_count") is None:
        return EXCLUDE_MISSING_FUNNEL_COUNTS
    return None


def _has_selection_contrast(record: dict[str, Any]) -> bool:
    """True when the day actually formed a comparison group (``candidates ⊊ eligible``).

    Equal counts mean the candidate set *is* the eligible field, so ``edge_E`` is 0.0 by
    construction and the day measured nothing.
    """
    funnel = record.get("funnel") or {}
    return int(funnel["candidate_count"]) < int(funnel["eligible_count"])


def admit_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure: partition ``records`` into contributing days, zero-contrast days, and exclusions.

    Returns ``{contributing, zero_contrast, excluded, valid_days, contrast_days,
    zero_contrast_days, exclusions, mean_selection_ratio}``. ``valid_days`` counts records that
    passed *record* admission (contrast-bearing or not); ``contrast_days`` counts those that also
    carry selection contrast and therefore enter the statistical series.
    """
    contributing: list[dict[str, Any]] = []
    zero_contrast: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    exclusions: dict[str, int] = {}
    seen_source_dates: set[str] = set()
    ratios: list[float] = []

    for record in records:
        reason = _admission_reason(record, seen_source_dates)
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            excluded.append({"asof": record.get("asof"), "reason": reason})
            continue
        seen_source_dates.add(record["source_date"])

        funnel = record["funnel"]
        eligible = int(funnel["eligible_count"])
        if eligible > 0:
            ratios.append(int(funnel["candidate_count"]) / eligible)
        (contributing if _has_selection_contrast(record) else zero_contrast).append(record)

    valid_days = len(contributing) + len(zero_contrast)
    return {
        "contributing": contributing,
        "zero_contrast": zero_contrast,
        "excluded": excluded,
        "valid_days": valid_days,
        "contrast_days": len(contributing),
        "zero_contrast_days": len(zero_contrast),
        "exclusions": exclusions,
        "mean_selection_ratio": (
            round(sum(ratios) / len(ratios), 4) if ratios else None
        ),
    }


def gate_verdict(
    records: list[dict[str, Any]],
    *,
    min_days: int = MIN_FORWARD_DAYS,
    bootstrap: int = 2000,
    min_contrast_days: int | None = None,
    max_mean_selection_ratio: float | None = None,
) -> dict[str, Any]:
    """Pure: classify the forward replication from back-filled records.

    Uses the candidate-vs-field ``edge_E`` of every **admitted, contrast-bearing** day as the
    daily series. See the module docstring for the two admission rules. ``min_contrast_days`` and
    ``max_mean_selection_ratio`` are the governed contrast-quality floors; ``None`` means "not yet
    governed" and is not enforced (the underlying diagnostics are reported regardless).
    """
    admission = admit_records(records)
    diagnostics = {
        "valid_days": admission["valid_days"],
        "contrast_days": admission["contrast_days"],
        "zero_contrast_days": admission["zero_contrast_days"],
        "excluded_days": len(admission["excluded"]),
        "exclusions": admission["exclusions"],
        "mean_selection_ratio": admission["mean_selection_ratio"],
        "min_contrast_days": min_contrast_days,
        "max_mean_selection_ratio": max_mean_selection_ratio,
    }

    # (2) Identifiability guard — withholds a verdict, never issues one.
    if admission["valid_days"] > 0 and admission["contrast_days"] == 0:
        return {
            "verdict": "INVALID-EVIDENCE",
            "reason": "NO_SELECTION_CONTRAST",
            "min_days": min_days,
            **diagnostics,
            "note": (
                f"{admission['zero_contrast_days']}/{admission['valid_days']} admitted days have "
                "candidate_count == eligible_count, so the candidate and baseline sets are "
                "identical and edge_E is 0.0 by construction — no day formed a comparison group. "
                "The test is non-identifiable: it cannot distinguish 'the edge does not transfer' "
                "from 'no comparison group was formed', at any sample size. No pass/fail verdict "
                "is available until the selection funnel is repaired (a governed design change). "
                "Candidate Report stays advisory (ADR 0014)."
            ),
        }

    edges = [r["outcomes"]["edge_E"] for r in admission["contributing"]]
    contrast_days = len(edges)

    # Governed contrast-quality floors, enforced only once set.
    ratio = admission["mean_selection_ratio"]
    unmet: list[str] = []
    if min_contrast_days is not None and contrast_days < min_contrast_days:
        unmet.append(f"contrast_days {contrast_days} < governed minimum {min_contrast_days}")
    if (
        max_mean_selection_ratio is not None
        and ratio is not None
        and ratio > max_mean_selection_ratio
    ):
        unmet.append(
            f"mean_selection_ratio {ratio} > governed maximum {max_mean_selection_ratio}"
        )

    if contrast_days < min_days or unmet:
        note = (
            f"{contrast_days}/{min_days} contributing forward days — keep accruing; "
            "Candidate Report stays advisory (ADR 0014)."
        )
        if unmet:
            note += " Governed contrast floors unmet: " + "; ".join(unmet) + "."
        return {
            "verdict": "INSUFFICIENT",
            "filled_days": contrast_days,   # retained key name for existing consumers
            "min_days": min_days,
            **diagnostics,
            "note": note,
        }

    ci = ev.block_bootstrap_ci(edges, ev._mean, n_resamples=bootstrap)
    if ci.ci_low > 0:
        verdict = "TRANSFERS"
        note = "edge CI-separated > 0 on real premarket data → recommend L4 (owner-gated)."
    else:
        verdict = "DOES-NOT-TRANSFER"
        note = ("edge CI includes/below 0 → the validated edge does not transfer to the gappers "
                "universe; the engine remains a liquid-universe tool (a citable boundary).")
    return {
        "verdict": verdict,
        "filled_days": contrast_days,
        "min_days": min_days,
        **diagnostics,
        "edge_E": {"point": round(ci.point, 4), "ci_low": round(ci.ci_low, 4),
                   "ci_high": round(ci.ci_high, 4), "p_value": round(ci.p_value, 4)},
        "note": note,
    }


def load_records(directory: str) -> list[dict[str, Any]]:
    """Load all ``premarket_scan_*.json`` records from ``directory`` (sorted by date); empty on a
    missing directory (fail-soft)."""
    records: list[dict[str, Any]] = []
    for path in sorted(glob.glob(os.path.join(directory, "premarket_scan_*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                records.append(json.load(fh))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return records


def run_gate_verdict(
    directory: str,
    *,
    min_days: int = MIN_FORWARD_DAYS,
    bootstrap: int = 2000,
    min_contrast_days: int | None = None,
    max_mean_selection_ratio: float | None = None,
) -> dict[str, Any]:
    """Load the accrued records and return the gate verdict (the increment-D entry point)."""
    return gate_verdict(
        load_records(directory),
        min_days=min_days,
        bootstrap=bootstrap,
        min_contrast_days=min_contrast_days,
        max_mean_selection_ratio=max_mean_selection_ratio,
    )
