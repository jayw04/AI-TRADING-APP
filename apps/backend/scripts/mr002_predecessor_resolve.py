"""MR-002 predecessor-CIK resolution with authoritative evidence (owner conditions 1-3).

For each CAUSE-A security (predecessor-CIK chain), find the predecessor filer and
the documented reorganization boundary:

  1. successor CIK -> its earliest 8-K12B / S-4 (the Rule 12g-3 successor
     registration) -> the reorg EVENT DATE (not merely a filing date);
  2. EDGAR company-name search on the entity-name stem -> candidate CIKs;
  3. for each candidate: name, SIC, first/last DOMESTIC filing dates;
  4. keep candidates whose last domestic filing precedes (or brackets) the
     successor's first domestic filing — i.e. the filer baton actually passed;
  5. record continuity signals: the security's own price history is continuous
     across the boundary (Sharadar), the successor's formerNames, the reorg form.

Emits `predecessor_resolution.json` — a worksheet with the evidence for EVERY
candidate. It decides nothing: the registry rows (drafted next) carry the
continuity/replacement call and go to the owner for countersign.

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_predecessor_resolve.py
"""

from __future__ import annotations

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import json
import re
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
UA = {"User-Agent": "GlobalComplyAI LLC jay.w0416@gmail.com",
      "Accept-Encoding": "gzip, deflate"}
DOM = ("10-K", "10-Q", "10-K/A", "10-Q/A")
REORG = ("8-K12B", "8-K12G3", "S-4", "S-4/A")
STOP = {"inc", "inc.", "corp", "corp.", "corporation", "co", "co.", "company",
        "plc", "ltd", "ltd.", "holdings", "holding", "group", "the", "&", "n.v.",
        "nv", "sa", "ag", "llc", "lp", "&amp;"}


def stem(name: str) -> str:
    toks = [t for t in re.split(r"[\s,]+", (name or "").lower()) if t and t not in STOP]
    return " ".join(toks[:2]) if toks else ""


def submissions(client: httpx.Client, cik: int) -> dict:
    return client.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                      headers=UA, timeout=45).json()


def filing_profile(client: httpx.Client, cik: int) -> dict:
    subs = submissions(client, cik)
    blocks = [(subs.get("filings") or {}).get("recent") or {}]
    for fl in (subs.get("filings") or {}).get("files") or []:
        blocks.append(client.get(f"https://data.sec.gov/submissions/{fl['name']}",
                                 headers=UA, timeout=45).json())
    dom_dates, reorg_events = [], []
    for b in blocks:
        forms = b.get("form") or []
        dates = b.get("filingDate") or []
        reports = b.get("reportDate") or []
        for i, form in enumerate(forms):
            d = dates[i] if i < len(dates) else None
            if not d:
                continue
            if form in DOM:
                dom_dates.append(d)
            if form in REORG:
                reorg_events.append({"form": form, "filed": d,
                                     "event_date": (reports[i] if i < len(reports)
                                                    else None) or None})
    return {
        "cik": cik, "name": subs.get("name"),
        "sic": subs.get("sic"), "sicDescription": subs.get("sicDescription"),
        "formerNames": [(f.get("name"), (f.get("from") or "")[:10],
                         (f.get("to") or "")[:10]) for f in subs.get("formerNames", [])],
        "first_domestic_filing": min(dom_dates) if dom_dates else None,
        "last_domestic_filing": max(dom_dates) if dom_dates else None,
        "n_domestic_filings": len(dom_dates),
        "reorg_filings": sorted(reorg_events, key=lambda x: x["filed"])[:3],
    }


def company_search(client: httpx.Client, q: str) -> dict[int, str]:
    r = client.get("https://www.sec.gov/cgi-bin/browse-edgar",
                   params={"action": "getcompany", "company": q, "type": "10-K",
                           "dateb": "", "owner": "exclude", "count": "40",
                           "output": "atom"}, headers=UA, timeout=40)
    out: dict[int, str] = {}
    for m in re.finditer(r"<company-info>.*?</company-info>", r.text, re.S):
        blk = m.group(0)
        cik_m = re.search(r"<cik>(\d+)</cik>", blk)
        nm = re.search(r"<conformed-name>(.*?)</conformed-name>", blk)
        if cik_m:
            out[int(cik_m.group(1))] = (nm.group(1) if nm else "").strip()
    if not out:  # single-company response shape
        cik_m = re.search(r"CIK=(\d{10})", r.text)
        nm = re.search(r"<conformed-name>(.*?)</conformed-name>", r.text)
        if cik_m:
            out[int(cik_m.group(1))] = (nm.group(1) if nm else "").strip()
    return out


def main() -> int:
    cls = json.loads((EV / "gap_cause_classification.json").read_text())
    disc = {f["ticker"]: f for f in
            json.loads((EV / "predecessor_discovery.json").read_text())["findings"]}
    targets = [r for r in cls["detail"] if r["cause"] == "A_predecessor_cik_chain"]
    out = []
    with httpx.Client(follow_redirects=True) as client:
        for t in targets:
            tick, succ = t["ticker"], t["successor_cik"]
            row = {"ticker": tick, "permaticker": t["permaticker"],
                   "gap_months": t["gap_months"], "successor_cik": succ}
            sp = filing_profile(client, succ)
            row["successor"] = sp
            sec = (disc.get(tick) or {}).get("security_facts") or {}
            row["security_price_history"] = {
                "name": sec.get("name"), "firstpricedate": sec.get("firstpricedate"),
                "lastpricedate": sec.get("lastpricedate"),
                "isdelisted": sec.get("isdelisted")}
            # candidate predecessors by name stem
            q = stem(sp.get("name") or sec.get("name") or tick)
            cands = {}
            try:
                for cik, name in company_search(client, q).items():
                    if cik == succ:
                        continue
                    p = filing_profile(client, cik)
                    if not p["first_domestic_filing"]:
                        continue
                    # baton test: predecessor's domestic filings must precede the
                    # successor's first domestic filing
                    if sp["first_domestic_filing"] and \
                            p["last_domestic_filing"] < sp["first_domestic_filing"]:
                        cands[cik] = p
            except Exception as e:  # noqa: BLE001
                row["search_error"] = repr(e)[:100]
            row["candidate_predecessors"] = cands
            row["search_stem"] = q
            out.append(row)
            best = max(cands.items(), key=lambda kv: kv[1]["n_domestic_filings"],
                       default=(None, {}))
            print(f"  {tick:7} succ={succ} first10x={sp['first_domestic_filing']} "
                  f"reorg={sp['reorg_filings'][:1]} -> cands={len(cands)} "
                  f"best={best[0]} {best[1].get('name', '')[:32]}", flush=True)

    (EV / "predecessor_resolution.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nresolved worksheet -> {EV / 'predecessor_resolution.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
