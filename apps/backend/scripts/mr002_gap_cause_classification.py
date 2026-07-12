"""MR-002 gap-cause classification (owner condition 3 — and, first, WHICH cause).

For every security with pre-first-observation months, query its successor CIK's
EDGAR submissions and report the earliest filing of each form family:

  10-K / 10-Q   domestic forms — what the stage-2 V2 crawl fetched
  20-F / 40-F   foreign-private-issuer annual reports — ALSO carry the SIC in the
                SGML header, but were NOT in the crawl's form set
  8-K12B / S-4  holding-company reorganization / merger registrations

This separates the gap population into distinct causes BEFORE any override is drafted:

  CAUSE A — predecessor-CIK chain: the successor CIK has no substantive filings in
            the gap period; history lives under another CIK (identity remedy).
  CAUSE B — form-coverage gap: the SAME CIK filed 20-F/40-F during the gap (foreign
            private issuer that later became a domestic filer). A DATA-COMPLETENESS
            issue, not an identity one — the remedy is extending the form set.
  CAUSE C — bankruptcy / failure / replacement candidates: scrutiny; may legitimately
            remain uncovered (owner: HTZGQ et al.).

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_gap_cause_classification.py
"""

from __future__ import annotations

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
UA = {"User-Agent": "GlobalComplyAI LLC jay.w0416@gmail.com",
      "Accept-Encoding": "gzip, deflate"}

FPI_FORMS = ("20-F", "40-F", "20-F/A", "40-F/A")
DOM_FORMS = ("10-K", "10-Q", "10-K/A", "10-Q/A")
REORG_FORMS = ("8-K12B", "S-4", "S-4/A", "8-K12G3")


def main() -> int:
    disc = json.loads((EV / "predecessor_discovery.json").read_text())
    out = []
    with httpx.Client(follow_redirects=True) as client:
        for f in disc["findings"]:
            cik = f["successor_cik"]
            tick = f["ticker"]
            row = {"ticker": tick, "permaticker": f["permaticker"],
                   "gap_months": f["gap_months"], "successor_cik": cik,
                   "entity_name": (f.get("successor_entity") or {}).get("name")}
            try:
                subs = client.get(
                    f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                    headers=UA, timeout=45).json()
                blocks = [(subs.get("filings") or {}).get("recent") or {}]
                for fl in (subs.get("filings") or {}).get("files") or []:
                    blocks.append(client.get(
                        f"https://data.sec.gov/submissions/{fl['name']}",
                        headers=UA, timeout=45).json())
                earliest: dict[str, str] = {}
                for b in blocks:
                    forms = b.get("form") or []
                    dates = b.get("filingDate") or []
                    for i, form in enumerate(forms):
                        d = dates[i] if i < len(dates) else None
                        if not d:
                            continue
                        fam = ("domestic" if form in DOM_FORMS else
                               "fpi" if form in FPI_FORMS else
                               "reorg" if form in REORG_FORMS else None)
                        if fam and (fam not in earliest or d < earliest[fam]):
                            earliest[fam] = d
                        if "any" not in earliest or d < earliest["any"]:
                            earliest["any"] = d
                row["earliest_filing_by_family"] = earliest
                dom, fpi, any_f = (earliest.get("domestic"), earliest.get("fpi"),
                                   earliest.get("any"))
                if tick.endswith("Q") or tick == "FRCB":
                    cause = "C_bankruptcy_or_failure_scrutiny"
                elif fpi and (not dom or fpi < dom):
                    cause = "B_form_coverage_gap_FPI"
                elif not dom:
                    cause = "B_form_coverage_gap_no_domestic_forms"
                else:
                    cause = "A_predecessor_cik_chain"
                row["cause"] = cause
            except Exception as e:  # noqa: BLE001
                row["error"] = repr(e)[:120]
                row["cause"] = "UNKNOWN"
            out.append(row)
            print(f"  {tick:8} gap={row['gap_months']:4} "
                  f"earliest={row.get('earliest_filing_by_family')} -> {row['cause']}",
                  flush=True)

    by_cause: dict[str, dict] = {}
    for r in out:
        d = by_cause.setdefault(r["cause"],
                                {"securities": 0, "months": 0, "tickers": []})
        d["securities"] += 1
        d["months"] += r["gap_months"]
        d["tickers"].append(r["ticker"])
    report = {"total_gap_securities": len(out),
              "total_gap_months": sum(r["gap_months"] for r in out),
              "by_cause": by_cause, "detail": out}
    (EV / "gap_cause_classification.json").write_text(
        json.dumps(report, indent=2, default=str))
    print("\n" + json.dumps(by_cause, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
