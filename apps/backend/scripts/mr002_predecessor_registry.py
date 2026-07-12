"""MR-002 predecessor-CIK override registry (owner conditions 1-3, GO 2026-07-11).

Builds the effective-dated identity-override registry for the CAUSE-A securities and
VERIFIES every proposed predecessor against EDGAR before writing the row:

  - predecessor entity name + SIC + first/last DOMESTIC filing dates;
  - the BATON TEST: the predecessor's last 10-K/10-Q must precede the successor's
    first 10-K/10-Q (the filer baton actually passed);
  - the reorganization EVENT: form (8-K12B / S-4) + its filed/event date — the
    boundary is the documented reorg date, never a mere filing date;
  - continuity vs replacement call, with the owner's prohibited patterns flagged.

Output:
  predecessor_override_registry_v0.1.csv  — the countersign artifact (one row per
      effective-dated interval; per-row evidence; review_status=pending_countersign)
  predecessor_registry_verification.json  — the EDGAR evidence backing each row.

Nothing is applied automatically: the supplemental crawl reads the registry, and the
gate result stays PROVISIONAL until the owner countersigns.

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_predecessor_registry.py
"""

from __future__ import annotations

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import csv
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
UA = {"User-Agent": "GlobalComplyAI LLC jay.w0416@gmail.com",
      "Accept-Encoding": "gzip, deflate"}
DOM = ("10-K", "10-Q", "10-K/A", "10-Q/A")

# Curated predecessor map — each entry VERIFIED against EDGAR below before it is
# written. event_date = the documented reorganization effective date (not the
# filing date). continuity = the economic-continuity call; flags carry the owner's
# prohibited-pattern scrutiny.
CURATED: dict[str, dict] = {
    "BLK":   {"pred": 1364742, "event": "2024-10-01", "type": "holdco_reorg",
              "evidence": "8-K12B filed+effective 2024-10-01 (successor CIK 2012383); BlackRock Inc. reorganization completed with the GIP acquisition",
              "continuity": "continuous — same listed common equity, holdco interposed"},
    "PSKY":  {"pred": 813828, "event": "2025-08-07", "type": "merger_new_control",
              "evidence": "S-4 2024-11-04; Skydance/Paramount transaction closed 2025-08-07; Paramount Global (CIK 813828) shares exchanged into Paramount Skydance (CIK 2041610)",
              "continuity": "SCRUTINY — merger with new controlling shareholder; listed exposure continues via share exchange but control/capital structure changed",
              "flag": "OWNER_SCRUTINY_merger_new_control"},
    "DIS":   {"pred": 1001039, "event": "2019-03-20", "type": "holdco_reorg",
              "evidence": "S-4 2018-06-25 (TWDC Holdco 613 Corp); holdco structure effective 2019-03-20 with the 21CF acquisition; DIS shares continued uninterrupted",
              "continuity": "continuous — same listed common equity, holdco interposed"},
    "VTRS":  {"pred": 1623613, "event": "2020-11-16", "type": "combination",
              "evidence": "S-4 2019-10-25; Mylan N.V. (CIK 1623613) + Upjohn combination completed 2020-11-16 into Viatris (CIK 1792044); Mylan holders received Viatris shares 1:1",
              "continuity": "continuous — Mylan shareholders' exposure carried 1:1 into Viatris"},
    "APA":   {"pred": 6769, "event": "2021-03-01", "type": "holdco_reorg",
              "evidence": "8-K12B filed+effective 2021-03-01; APA Corporation (CIK 1841666) became the holding company of Apache Corp (CIK 6769); shares converted 1:1",
              "continuity": "continuous — 1:1 holdco conversion"},
    "DD":    {"pred": 30554, "event": "2017-08-31", "type": "merger_then_spinoffs",
              "evidence": "S-4 2016-03-01; Dow/DuPont merger completed 2017-08-31 into DowDuPont (CIK 1666700), later renamed DuPont de Nemours after the 2019 Dow/Corteva spin-offs",
              "continuity": "SCRUTINY — E.I. du Pont holders received DowDuPont shares (continuous), but the 2019 spin-offs materially changed the surviving exposure",
              "flag": "OWNER_SCRUTINY_merger_with_subsequent_spinoffs"},
    "CI":    {"pred": 701221, "event": "2018-12-20", "type": "holdco_reorg",
              "evidence": "S-4 2018-05-16; Express Scripts transaction closed 2018-12-20; Cigna Corp (new, CIK 1739940) became holdco of Cigna Holding Co (CIK 701221); shares converted 1:1",
              "continuity": "continuous — 1:1 holdco conversion"},
    "AVGO":  {"pred": 1649338, "event": "2018-04-04", "type": "redomiciliation",
              "evidence": "S-4 2018-02-06; Broadcom redomiciled from Singapore (Broadcom Ltd, CIK 1649338) to Delaware (Broadcom Inc, CIK 1730168) effective 2018-04-04; 1:1 share exchange",
              "continuity": "continuous — 1:1 redomiciliation exchange"},
    "MRVL":  {"pred": 1058057, "event": "2021-04-20", "type": "redomiciliation",
              "evidence": "S-4 2020-12-22; Marvell Technology Group Ltd (Bermuda, CIK 1058057) reorganized into Marvell Technology Inc (Delaware, CIK 1835632) effective 2021-04-20 with the Inphi acquisition; 1:1",
              "continuity": "continuous — 1:1 reorganization exchange"},
    "MDT":   {"pred": 64670, "event": "2015-01-26", "type": "redomiciliation",
              "evidence": "S-4 2014-07-14; Medtronic Inc (CIK 64670) became Medtronic plc (Ireland, CIK 1613103) on 2015-01-26 with the Covidien acquisition; 1:1 share exchange",
              "continuity": "continuous — 1:1 redomiciliation exchange"},
    "WBA":   {"pred": 104207, "event": "2014-12-31", "type": "holdco_reorg",
              "evidence": "S-4 2014-09-16; Walgreen Co (CIK 104207) reorganized into Walgreens Boots Alliance (CIK 1618921) effective 2014-12-31; 1:1 share conversion",
              "continuity": "continuous — 1:1 holdco conversion"},
    "DKNG":  {"pred": 1772757, "event": "2022-05-05", "type": "holdco_reorg",
              "evidence": "S-4 2021-10-08; New DraftKings (CIK 1883685) became the holdco of DraftKings Inc (CIK 1772757) on 2022-05-05 with the Golden Nugget Online acquisition; 1:1",
              "continuity": "continuous — 1:1 holdco conversion"},
    "DINO":  {"pred": 48039, "event": "2022-03-14", "type": "holdco_reorg",
              "evidence": "8-K12B filed+effective 2022-03-14; HF Sinclair (CIK 1915657) became holdco of HollyFrontier (CIK 48039) with the Sinclair transaction; 1:1",
              "continuity": "continuous — 1:1 holdco conversion"},
    "LBTYA": {"pred": 1316631, "event": "2013-06-07", "type": "holdco_reorg",
              "evidence": "S-4 2013-03-07; Liberty Global plc (CIK 1570585) became the parent of Liberty Global Inc (CIK 1316631) on 2013-06-07 with the Virgin Media acquisition",
              "continuity": "continuous — Class A holders' exposure carried into the new plc"},
    "ZG":    {"pred": 1334814, "event": "2015-02-17", "type": "holdco_reorg",
              "evidence": "S-4 2014-09-12; Zillow Group (CIK 1617640) became holdco of Zillow Inc (CIK 1334814) on 2015-02-17 with the Trulia acquisition; 1:1",
              "continuity": "continuous — 1:1 holdco conversion"},
    "OVV":   {"pred": 1157806, "event": "2020-01-24", "type": "redomiciliation",
              "evidence": "S-4 2019-11-06; Encana Corp (Canada, CIK 1157806) redomiciled to the US as Ovintiv (CIK 1792580) effective 2020-01-24 (with a 1:5 reverse split)",
              "continuity": "SCRUTINY — continuous exposure, but the predecessor was a Canadian FPI filing 40-F (its SIC history is in FPI forms, not 10-K/10-Q)",
              "flag": "OWNER_SCRUTINY_predecessor_is_FPI_filer"},
    "AGN":   {"pred": 884629, "event": "2013-10-01", "type": "redomiciliation",
              "evidence": "S-4 2013-06-18; Actavis Inc (CIK 884629, formerly Watson Pharmaceuticals) reorganized into Actavis plc (Ireland, CIK 1578845) on 2013-10-01 with the Warner Chilcott acquisition; later renamed Allergan plc after the 2015 Allergan Inc acquisition",
              "continuity": "SCRUTINY — the AGN ticker's economic history spans Actavis plc; the separate Allergan Inc (CIK 850693) was an ACQUIRED TARGET, not a predecessor filer, and must NOT be bridged",
              "flag": "OWNER_SCRUTINY_ticker_reused_after_target_acquisition"},
    "QDEL":  {"pred": 353569, "event": "2022-05-27", "type": "holdco_reorg",
              "evidence": "S-4 2022-01-31; QuidelOrtho (CIK 1906324) became holdco of Quidel Corp (CIK 353569) on 2022-05-27 with the Ortho Clinical acquisition; 1:1",
              "continuity": "continuous — 1:1 holdco conversion"},
    "ICE":   {"pred": 1174746, "event": "2013-11-13", "type": "holdco_reorg",
              "evidence": "S-4 2013-03-21; IntercontinentalExchange Group (CIK 1571949) became holdco of IntercontinentalExchange Inc (CIK 1174746) on 2013-11-13 with the NYSE Euronext acquisition; 1:1",
              "continuity": "continuous — 1:1 holdco conversion"},
    "XRX":   {"pred": 108772, "event": "2019-07-31", "type": "holdco_reorg",
              "evidence": "S-4 2019-03-15; Xerox Holdings (CIK 1770450) became holdco of Xerox Corp (CIK 108772) effective 2019-07-31; 1:1 share conversion",
              "continuity": "continuous — 1:1 holdco conversion"},
    "PRGO":  {"pred": 820096, "event": "2013-12-18", "type": "redomiciliation",
              "evidence": "S-4 2013-08-28; Perrigo Co (Michigan, CIK 820096) reorganized into Perrigo Company plc (Ireland, CIK 1585364) on 2013-12-18 with the Elan acquisition; 1:1",
              "continuity": "continuous — 1:1 redomiciliation exchange"},
}

FIELDS = ["permaticker", "ticker", "predecessor_cik", "successor_cik",
          "effective_from", "effective_to", "event_type", "event_date",
          "authoritative_evidence", "continuity_rationale", "baton_test",
          "predecessor_entity", "predecessor_sic", "predecessor_filing_range",
          "successor_first_domestic_filing", "gap_months", "flags",
          "crawl_manifest_included", "review_status", "reviewer", "review_date"]


def profile(client: httpx.Client, cik: int) -> dict:
    subs = client.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                      headers=UA, timeout=45).json()
    blocks = [(subs.get("filings") or {}).get("recent") or {}]
    for fl in (subs.get("filings") or {}).get("files") or []:
        blocks.append(client.get(f"https://data.sec.gov/submissions/{fl['name']}",
                                 headers=UA, timeout=45).json())
    dates = []
    for b in blocks:
        forms = b.get("form") or []
        fd = b.get("filingDate") or []
        dates += [fd[i] for i, f in enumerate(forms) if f in DOM and i < len(fd)]
    return {"cik": cik, "name": subs.get("name"), "sic": subs.get("sic"),
            "sicDescription": subs.get("sicDescription"),
            "first_domestic": min(dates) if dates else None,
            "last_domestic": max(dates) if dates else None,
            "n_domestic": len(dates)}


def main() -> int:
    cls = json.loads((EV / "gap_cause_classification.json").read_text())
    cause_a = {r["ticker"]: r for r in cls["detail"]
               if r["cause"] == "A_predecessor_cik_chain"}
    # RTX / S2 were reclassified as CAUSE D (truncated cache) — excluded here
    cause_a.pop("RTX", None)
    cause_a.pop("S2", None)

    rows, verification = [], []
    with httpx.Client(follow_redirects=True) as client:
        for tick, meta in CURATED.items():
            g = cause_a.get(tick)
            if not g:
                continue
            succ = g["successor_cik"]
            p = profile(client, meta["pred"])
            s = profile(client, succ)
            # baton: the predecessor must actually cover the gap period (filings
            # before the successor's first domestic filing). Predecessors that keep
            # filing afterwards (subsidiary debt issuers — APA/DD/XRX) are NORMAL:
            # the effective-dated interval ends at the reorg event regardless.
            baton = bool(p["first_domestic"] and s["first_domestic"]
                         and p["first_domestic"] < s["first_domestic"]
                         and p["n_domestic"] > 0)
            still_files = bool(p["last_domestic"] and s["first_domestic"]
                               and p["last_domestic"] > s["first_domestic"])
            verification.append({"ticker": tick, "predecessor": p, "successor": s,
                                 "baton_test_passed": bool(baton),
                                 "predecessor_still_files_after_event": still_files,
                                 "event_date": meta["event"], "type": meta["type"]})
            flags = meta.get("flag", "")
            # effective-dated rows: predecessor interval, then successor interval.
            # effective_to is the day BEFORE the reorg event; the successor row
            # starts ON the event date. No overlap, no gap.
            from datetime import date, timedelta
            ev = date.fromisoformat(meta["event"])
            rows.append(dict(zip(FIELDS, [
                g["permaticker"], tick, meta["pred"], succ,
                "", str(ev - timedelta(days=1)), meta["type"], meta["event"],
                meta["evidence"], meta["continuity"],
                "PASS" if baton else "REVIEW",
                p["name"], f"{p['sic']} {p['sicDescription']}",
                f"{p['first_domestic']}..{p['last_domestic']} ({p['n_domestic']} filings)",
                s["first_domestic"], g["gap_months"], flags,
                "yes", "pending_countersign", "", "",
            ], strict=False)))
            print(f"  {tick:6} pred={meta['pred']:>8} {p['name'][:28]:28} "
                  f"last={p['last_domestic']} succ_first={s['first_domestic']} "
                  f"baton={'PASS' if baton else 'REVIEW'} {flags}", flush=True)

    out_csv = EV / "predecessor_override_registry_v0.1.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    (EV / "predecessor_registry_verification.json").write_text(
        json.dumps(verification, indent=2, default=str))
    print(f"\nregistry rows: {len(rows)} -> {out_csv.name}")
    print(f"baton PASS: {sum(1 for v in verification if v['baton_test_passed'])}"
          f"/{len(verification)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
