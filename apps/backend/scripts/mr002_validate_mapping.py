"""MR-002 mapping-table automated validation (owner review 2026-07-11 §4).

Runs the required pre-countersign checks on ``sic_sector_etf_mapping_v0.2.csv``:
range/period overlap detection, single-ETF, proxy-inception discipline, XLC/XLRE
transition consistency, MEDIUM-rationale specificity, LOW-row explicit-exclusion
policy, the v0.1 -> v0.2 row reconciliation, and the canonical-key hash (sorted by
``sic_start, sic_end, effective_from, effective_to, research_sector, sector_etf``).

The per-security impact review (coarse-range exposure, MEDIUM universe-months) needs
the preliminary universe and is DEFERRED to the Data Availability Gate — reported
here as deferred, not silently skipped.

Run:
    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/mr002_validate_mapping.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "Docs" / "implementation" / "evidence" / "mr_002"
PREV_CSV = EVIDENCE_DIR / "sic_sector_etf_mapping_v0.4.csv"
V2_CSV = EVIDENCE_DIR / "sic_sector_etf_mapping_v0.6.csv"
OUT = EVIDENCE_DIR / "mapping_validation_report.json"

ETF_INCEPTION = {
    "XLB": date(1998, 12, 16), "XLE": date(1998, 12, 16), "XLF": date(1998, 12, 16),
    "XLI": date(1998, 12, 16), "XLK": date(1998, 12, 16), "XLP": date(1998, 12, 16),
    "XLU": date(1998, 12, 16), "XLV": date(1998, 12, 16), "XLY": date(1998, 12, 16),
    "XLRE": date(2015, 10, 8), "XLC": date(2018, 6, 19),
}
CANONICAL_KEY = ("sic_start", "sic_end", "effective_from", "effective_to",
                 "research_sector", "sector_etf")


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _d(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def windows_overlap(a_from, a_to, b_from, b_to) -> bool:
    a0, a1 = a_from or date.min, a_to or date.max
    b0, b1 = b_from or date.min, b_to or date.max
    return a0 <= b1 and b0 <= a1


def main() -> int:
    rows = load(V2_CSV)
    v1_rows = load(PREV_CSV)
    errors: list[str] = []
    warnings: list[str] = []

    # ---- reconciliation v0.1 -> v0.2 (owner §4: 74-vs-75 must be explained) ----
    key = lambda r: tuple(r[k] for k in CANONICAL_KEY)  # noqa: E731
    v1_keys, v2_keys = {key(r) for r in v1_rows}, {key(r) for r in rows}
    recon = {
        "prev_rows(v0.4)": len(v1_rows), "current_rows(v0.6)": len(rows),
        "added": sorted(map(str, v2_keys - v1_keys)),
        "removed": sorted(map(str, v1_keys - v2_keys)),
        "note": "v0.5+v0.6 content changes are INTENTIONAL (owner countersign 2, "
                "2026-07-11): CLASSIFICATION effective dates replace ETF-availability "
                "dates (XLC boundary -> 2018-10-01 after the 2018-09-28 close; XLRE "
                "-> 2016-09-01 after the 2016-08-31 close; ETF availability is a "
                "separate registered property) + the 3800-3839 instruments split for "
                "LOW-exclusion recovery (3812->XLI, 3826->XLV, 3827->XLK; residuals "
                "stay LOW). Every added/removed key listed above; pre-reg v0.9.",
    }

    # ---- structural checks ----
    for i, r in enumerate(rows):
        lo, hi = int(r["sic_start"]), int(r["sic_end"])
        if lo > hi:
            errors.append(f"row{i}: sic_start>sic_end {lo}>{hi}")
        if not r["sector_etf"] or " " in r["sector_etf"].strip():
            errors.append(f"row{i}: not exactly one ETF: {r['sector_etf']!r}")
        etf = r["sector_etf"].strip()
        if etf not in ETF_INCEPTION:
            errors.append(f"row{i}: unknown ETF {etf}")
            continue
        eff_from = _d(r["effective_from"])
        # proxy-inception discipline: an ETF may not be referenced before it trades.
        # Open-start rows (empty effective_from) are bounded at runtime by the §2
        # proxy-availability universe rule; a row with an EXPLICIT from must respect it.
        if eff_from is not None and eff_from < ETF_INCEPTION[etf]:
            errors.append(f"row{i}: {etf} used from {eff_from} before inception "
                          f"{ETF_INCEPTION[etf]}")
        if eff_from is None and ETF_INCEPTION[etf] > date(1998, 12, 22):
            errors.append(f"row{i}: open-start row maps to late-inception ETF {etf} "
                          f"— needs an explicit effective_from")

    # overlapping SIC ranges within overlapping effective periods
    for i, a in enumerate(rows):
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if int(a["sic_start"]) <= int(b["sic_end"]) \
                    and int(b["sic_start"]) <= int(a["sic_end"]) \
                    and windows_overlap(_d(a["effective_from"]), _d(a["effective_to"]),
                                        _d(b["effective_from"]), _d(b["effective_to"])):
                errors.append(f"overlap: rows {i}/{j} "
                              f"[{a['sic_start']}-{a['sic_end']}]@"
                              f"({a['effective_from']}..{a['effective_to']}) vs "
                              f"[{b['sic_start']}-{b['sic_end']}]@"
                              f"({b['effective_from']}..{b['effective_to']})")

    # XLC / XLRE transition consistency
    for r in rows:
        etf = r["sector_etf"].strip()
        # taxonomy boundaries are CLASSIFICATION effective dates (owner countersign
        # 2): GICS 2018 -> first session 2018-10-01; Real Estate -> 2016-09-01.
        # ETF availability (XLC 2018-06-19 / XLRE 2015-10-08 first usable returns)
        # is a SEPARATE registered property enforced by the universe rule.
        if etf == "XLC" and r["effective_from"] != "2018-10-01":
            errors.append(f"XLC row must start at the classification date 2018-10-01: {key(r)}")
        if etf == "XLRE" and r["effective_from"] != "2016-09-01":
            errors.append(f"XLRE row must start at the classification date 2016-09-01: {key(r)}")
        if etf in ("XLC", "XLRE") and "classification" not in (
                r.get("source_reference", "") + r.get("mapping_rationale", "")).lower():
            errors.append(f"{etf} row must cite the classification effective date: {key(r)}")
        if r["effective_to"] and r["effective_to"] not in ("2018-09-28", "2016-08-31"):
            errors.append(f"unexpected effective_to boundary: {key(r)}")

    # MEDIUM rationale specificity; LOW policy
    n_conf = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for i, r in enumerate(rows):
        c = r.get("mapping_confidence", "")
        n_conf[c] = n_conf.get(c, 0) + 1
        why = r.get("mapping_rationale", "")
        if c == "MEDIUM" and (len(why) < 20 or "best fit" in why.lower()):
            warnings.append(f"row{i}: MEDIUM rationale not specific enough: {why!r}")
    low_policy = ("LOW rows are excluded from primary construction by the runner "
                  "(Mapping.resolve returns None + logs EXCLUDED_LOW_CONFIDENCE hits; "
                  "reported separately, never forced).")

    # canonical hash (sorted by the frozen key) — PROVISIONAL until countersign
    canon = sorted(rows, key=key)
    payload = "\n".join(",".join(r[k] for k in CANONICAL_KEY) +
                        f",{r['mapping_confidence']}" for r in canon)
    canonical_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    report = {
        "csv": str(V2_CSV.relative_to(ROOT)),
        "artifact_sha256": hashlib.sha256(V2_CSV.read_bytes()).hexdigest(),
        "reconciliation_prev_to_current": recon,
        "confidence_counts": n_conf,
        "errors": errors,
        "warnings": warnings,
        "low_confidence_policy": low_policy,
        "impact_review": "DEFERRED to the Data Availability Gate (needs the preliminary "
                         "universe): securities/universe-months per confidence tier, top-20 "
                         "MEDIUM-exposed securities, MEDIUM rows at XLC/XLRE boundaries, "
                         "MEDIUM-removed coverage diagnostic (no strategy signals).",
        "canonical_data_sha256": canonical_hash,
        "canonicalization": {
            "canonicalization_version": 1,
            "canonical_fields": list(CANONICAL_KEY) + ["mapping_confidence"],
            "canonical_sort_key": list(CANONICAL_KEY),
            "line_ending_policy": "LF join, no trailing newline",
        },
        "hash_note": "artifact_sha256 = raw file bytes; canonical_data_sha256 = "
                     "canonically sorted rows. Both PROVISIONAL until owner countersign.",
        "result": "PASS" if not errors else "FAIL",
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in
                      ("reconciliation_prev_to_current", "confidence_counts", "errors",
                       "warnings", "result")}, indent=2))
    print(f"-> {OUT}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
