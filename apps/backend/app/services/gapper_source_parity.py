"""GAP-NATIVE-001 source-parity accrual (ADR 0041; GAPPER v2.1.1 §3.1, §8.1).

Compares the box-native and external (laptop) gappers files for a single day and
persists the result as a dated artifact, so parity evidence accrues **daily from
probation day 1** rather than being reconstructed later from whatever files
happen to survive.

Why this runs every day instead of on demand
--------------------------------------------
The ADR 0041 Decision-6 guard makes path B (a top-N dollar-volume sweep of the
factor store) the *effective* premarket discovery path. That trades one failure
mode for another: no longer "a confident list from the previous session", but
"a plausible list from an incomplete universe" — the store is small-cap-sparse
and the external scanner's top-10 routinely contains small caps.

§8.1 probation cannot catch that. Probation measures **capture rate**, a transport
property, and the transport would be working perfectly while the universe was
wrong. Parity gates something different: whether path B's output may be treated
as authoritative for the frozen event definition in Stage 0A. Accruing it across
the same 15-day window costs nothing extra and yields both verdicts at once —
transport capture (gates forward accrual) and source parity (gates §3.1 fidelity
conclusions).

Boundary: read-only. Two directory reads and one JSON write; no order path, no
broker, no LLM, no DB. Calibration evidence only — a parity artifact never carries
a performance verdict.
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import date as date_cls
from typing import Any

_DATE_RE = re.compile(r"premarket_gappers_(\d{4}-\d{2}-\d{2})\.json$")

RECORD_SCHEMA = "gap_native_001_source_parity/v1"

# Interpretation rule (ADR 0041 / review §3): consistently low overlap means the two
# sources are DIFFERENT candidate populations, so no pooled GAPPER/SCAN verdict may
# span the source change — the native source starts a new evidence tranche.
INTERPRETATION = (
    "consistently low overlap ⇒ treat native and external as DIFFERENT candidate "
    "sources: no pooled GAPPER/SCAN verdict; the native source starts a new evidence "
    "tranche (ADR 0041). Parity is calibration evidence and never carries a verdict."
)


def dates_present(directory: str) -> set[str]:
    """The ISO dates for which ``directory`` holds a gappers file."""
    out: set[str] = set()
    for p in glob.glob(os.path.join(directory, "premarket_gappers_*.json")):
        m = _DATE_RE.search(p.replace("\\", "/"))
        if m:
            out.add(m.group(1))
    return out


def _read_file(directory: str, day: str) -> dict[str, Any] | None:
    path = os.path.join(directory, f"premarket_gappers_{day}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        return loaded if isinstance(loaded, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def load_gappers(directory: str, day: str) -> list[dict[str, Any]]:
    """That day's gapper rows from ``directory`` — empty when absent/unparseable."""
    payload = _read_file(directory, day)
    return (payload or {}).get("gappers") or []


def gate_candidates(evidence_dir: str, day: str) -> tuple[list[str], str | None]:
    """The gate record's candidate symbols for ``day`` and its ``gappers_source``."""
    path = os.path.join(evidence_dir, f"premarket_scan_{day}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        return [c.get("symbol") for c in rec.get("candidates") or []], rec.get("gappers_source")
    except (OSError, json.JSONDecodeError, ValueError):
        return [], None


def compare_day(native: list[dict[str, Any]], external: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure: one day's native-vs-external comparison.

    ``overlap_pct_of_external`` is deliberately keyed to the EXTERNAL list — the
    question parity has to answer is "what would the native source have missed",
    not "how much of the native list was corroborated". A native source that emits
    two names, both of which the external found, scores 100% on the flattering
    denominator and ~20% on this one."""
    n_syms = {str(g.get("symbol") or "").upper() for g in native if g.get("symbol")}
    e_syms = {str(g.get("symbol") or "").upper() for g in external if g.get("symbol")}
    overlap = n_syms & e_syms
    n_by = {str(g["symbol"]).upper(): g for g in native if g.get("symbol")}
    e_by = {str(g["symbol"]).upper(): g for g in external if g.get("symbol")}
    gap_deltas: list[float] = []
    vol_deltas: list[float] = []
    for s in overlap:
        try:
            gap_deltas.append(abs(float(n_by[s]["gap_pct"]) - float(e_by[s]["gap_pct"])))
            vol_deltas.append(
                abs(float(n_by[s]["premarket_volume"]) - float(e_by[s]["premarket_volume"]))
            )
        except (KeyError, TypeError, ValueError):
            continue
    top_n = {s for s, g in n_by.items() if (g.get("rank") or 99) <= 10}
    top_e = {s for s, g in e_by.items() if (g.get("rank") or 99) <= 10}
    return {
        "native_count": len(n_syms),
        "external_count": len(e_syms),
        "overlap_count": len(overlap),
        "overlap_pct_of_external": round(100 * len(overlap) / len(e_syms), 1) if e_syms else None,
        "top10_rank_overlap": len(top_n & top_e),
        "mean_gap_pct_delta": round(sum(gap_deltas) / len(gap_deltas), 2) if gap_deltas else None,
        "mean_pm_volume_delta": round(sum(vol_deltas) / len(vol_deltas)) if vol_deltas else None,
        "native_only": sorted(n_syms - e_syms),
        "external_only": sorted(e_syms - n_syms),
    }


def parity_record(
    day: date_cls | str,
    *,
    native_dir: str,
    external_dir: str,
    evidence_dir: str,
) -> dict[str, Any]:
    """Build ``day``'s parity record.

    Records the *absence* of either source explicitly (``both_present: False``)
    rather than skipping the day. A day with no comparison is itself parity
    evidence — it is how "the native source ran and the external did not" becomes
    visible instead of leaving a hole that later reads as "never measured"."""
    iso = day.isoformat() if isinstance(day, date_cls) else str(day)
    native_payload = _read_file(native_dir, iso)
    external_payload = _read_file(external_dir, iso)
    native = (native_payload or {}).get("gappers") or []
    external = (external_payload or {}).get("gappers") or []

    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "asof": iso,
        "native_present": native_payload is not None,
        "external_present": external_payload is not None,
        "both_present": native_payload is not None and external_payload is not None,
        # Discovery provenance of the native file under comparison — parity results
        # must be stratifiable by path (a path-B day and a path-A day are not the
        # same experiment). Absent on external-only days by construction.
        "native_discovery_path": (native_payload or {}).get("discovery_path"),
        "native_discovery_reason": (native_payload or {}).get("discovery_reason"),
        "native_source": (native_payload or {}).get("source"),
    }
    if record["both_present"]:
        record["comparison"] = compare_day(native, external)
    else:
        record["comparison"] = None
        record["note"] = (
            "no comparison: "
            + ("native file missing" if native_payload is None else "")
            + (
                " and external file missing"
                if native_payload is None and external_payload is None
                else ("external file missing" if external_payload is None else "")
            )
        ).strip()

    candidates, source = gate_candidates(evidence_dir, iso)
    n_syms = {str(g.get("symbol") or "").upper() for g in native}
    e_syms = {str(g.get("symbol") or "").upper() for g in external}
    record["gate"] = {
        "gappers_source": source,
        "candidates": candidates,
        "candidates_in_native": [c for c in candidates if c and c.upper() in n_syms],
        "candidates_in_external": [c for c in candidates if c and c.upper() in e_syms],
    }
    record["interpretation"] = INTERPRETATION
    return record


def persist_parity_record(record: dict[str, Any], directory: str) -> str:
    """Write ``record`` to ``{directory}/gapper_source_parity_{asof}.json`` atomically.

    Idempotent per day: a re-run for the same day overwrites, because a parity
    record is a derived measurement over two source files, not primary evidence —
    unlike a gate evidence record, which is immutable once written (§5.5)."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"gapper_source_parity_{record['asof']}.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    os.replace(tmp, path)
    return path


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll a set of parity records into the probation-window view."""
    compared = [r for r in records if r.get("comparison")]
    overlaps = [
        r["comparison"]["overlap_pct_of_external"]
        for r in compared
        if r["comparison"].get("overlap_pct_of_external") is not None
    ]
    paths: dict[str, int] = {}
    for r in records:
        key = str(r.get("native_discovery_reason") or "NO_NATIVE_FILE")
        paths[key] = paths.get(key, 0) + 1
    return {
        "days_seen": len(records),
        "days_compared": len(compared),
        "days_native_missing": sum(1 for r in records if not r.get("native_present")),
        "days_external_missing": sum(1 for r in records if not r.get("external_present")),
        "mean_overlap_pct_of_external": (
            round(sum(overlaps) / len(overlaps), 1) if overlaps else None
        ),
        "min_overlap_pct_of_external": min(overlaps) if overlaps else None,
        "discovery_reason_counts": paths,
        "interpretation": INTERPRETATION,
    }
