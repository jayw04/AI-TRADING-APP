"""MR-002 final PIT-SIC coverage gate + integrity review (owner spec, 2026-07-11).

The FINAL V2 gate — computed from PIT SIC (the stage-2 crawl), never the
current-SIC planning approximation. Fixed denominator: 40,750 universe-months.
Coverage requires an EFFECTIVE SIC SEGMENT VALID AS OF THE SPECIFIC MONTH — no
forward fill across the unsupported pre-first-observation interval (segments
begin at their establishing filing's acceptance; open-ended ends are supported
post-observation forward-fill by construction).

Integrity checks (owner): no forward-fill before first observed SIC · effective
dates monotonic (non-overlapping, ordered, contiguous boundaries) · same-day
conflicts remain zero · SIC changes internally consistent (every segment boundary
matches an observation carrying the new SIC).

Stratified review of the SIC-changing issuers: one-change / multiple-change /
changes near taxonomy boundaries (2016-09-01, 2018-10-01) / amendment-established
vs original / same-quarter conflicting filings / UBER + BKNG narratives.

Funnel (single fixed denominator): identity resolved -> PIT SIC available ->
generic mapping eligible / security override / excluded_low / needs_revision /
ETF unavailable -> final V2 eligible. Annual coverage vs the frozen >=95%/year
and >=98% overall gates.

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_pitsic_gate.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
DENOM = 40750
ETF_LIVE = {"XLC": date(2018, 6, 19), "XLRE": date(2015, 10, 8)}
TAXO_BOUNDARIES = (date(2016, 9, 1), date(2018, 10, 1))


def load_mapping():
    rows = []
    with (EV / "sic_sector_etf_mapping_v0.8.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "lo": int(r["sic_start"]), "hi": int(r["sic_end"]),
                "from": date.fromisoformat(r["effective_from"]) if r["effective_from"] else None,
                "to": date.fromisoformat(r["effective_to"]) if r["effective_to"] else None,
                "etf": r["sector_etf"], "conf": r["mapping_confidence"],
                "status": r["review_status"]})
    return rows


def load_overrides():
    rows = []
    with (EV / "security_sector_overrides_v0.6.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "perma": int(r["permaticker"]) if r["permaticker"] else None,
                "from": date.fromisoformat(r["effective_from"]) if r["effective_from"] else None,
                "to": date.fromisoformat(r["effective_to"]) if r["effective_to"] else None,
                "etf": r["sector_etf"], "status": r["review_status"]})
    return rows


def main() -> int:
    con = duckdb.connect()
    segs = con.execute(
        f"SELECT cik, ticker, sic, effective_from, effective_to, source_accession "
        f"FROM read_csv_auto('{EV / 'stage2' / 'sic_segments.csv.gz'}', header=true)"
    ).fetchall()
    obs = con.execute(
        f"SELECT cik, accession, form, accepted_utc, sic FROM read_csv_auto("
        f"'{EV / 'stage2' / 'sic_observations.csv.gz'}', header=true) WHERE sic IS NOT NULL"
    ).fetchall()

    # ---- integrity checks ----
    seg_by_cik: dict[int, list] = {}
    for cik, tick, sic, f, t, acc in segs:
        seg_by_cik.setdefault(int(cik), []).append(
            (f.date() if hasattr(f, "date") else f, t.date() if (t is not None and hasattr(t, "date")) else t,
             str(int(float(sic))).zfill(4) if sic is not None else None, tick, acc))
    obs_by_cik: dict[int, list] = {}
    for cik, acc, form, ts, sic in obs:
        obs_by_cik.setdefault(int(cik), []).append(
            (ts.date() if hasattr(ts, "date") else ts,
             str(int(float(sic))).zfill(4), form, acc))

    integ = Counter()
    for cik, ss in seg_by_cik.items():
        ss.sort(key=lambda x: x[0])
        first_obs = min(o[0] for o in obs_by_cik.get(cik, [(date.max,)]))
        if ss and ss[0][0] != first_obs:
            integ["segment_starts_before_or_after_first_observation"] += 1
        for a, b in zip(ss, ss[1:], strict=False):
            if a[1] is None:
                integ["non_final_open_segment"] += 1
            elif a[1] != b[0]:
                integ["non_contiguous_boundary"] += 1
            if a[1] is not None and a[1] < a[0]:
                integ["negative_duration_segment"] += 1
        # every change boundary must match an observation carrying the new SIC
        for _a, b in zip(ss, ss[1:], strict=False):
            if not any(o[0] == b[0] and o[1] == b[2] for o in obs_by_cik.get(cik, [])):
                integ["boundary_without_matching_observation"] += 1
    # same-day conflicts (recheck from observations)
    for _cik, oo in obs_by_cik.items():
        by_day: dict[date, set] = {}
        for d, sic, _f, _a in oo:
            by_day.setdefault(d, set()).add(sic)
        integ["same_day_conflicts"] += sum(1 for v in by_day.values() if len(v) > 1)

    # ---- stratified review of SIC-changing issuers ----
    changers = {c: ss for c, ss in seg_by_cik.items() if len(ss) > 1}
    strat = {
        "total_changing_issuers": len(changers),
        "one_change": sum(1 for ss in changers.values() if len(ss) == 2),
        "multiple_changes": sum(1 for ss in changers.values() if len(ss) > 2),
        "changes_near_taxonomy_boundaries_180d": sum(
            1 for ss in changers.values()
            if any(abs((seg[0] - b).days) <= 180 for seg in ss[1:] for b in TAXO_BOUNDARIES)),
        "change_established_by_amendment": sum(
            1 for c, ss in changers.items() for seg in ss[1:]
            if any(o[0] == seg[0] and o[2].endswith("/A") for o in obs_by_cik.get(c, []))),
        "same_quarter_conflicting_filings": sum(
            1 for c, oo in obs_by_cik.items()
            if any(len({sic for d2, sic, _f, _a in oo
                        if (d2.year, (d2.month - 1) // 3) == (d.year, (d.month - 1) // 3)}) > 1
                   for d, _s, _f2, _a2 in oo)),
    }
    tick_of = {c: ss[0][3] for c, ss in seg_by_cik.items()}
    for want in ("UBER", "BKNG"):
        for c, ss in changers.items():
            if want in str(tick_of.get(c, "")):
                strat[f"case_{want}"] = [
                    {"sic": s[2], "from": str(s[0]), "to": str(s[1])} for s in ss]

    # ---- coverage funnel over the FIXED 40,750 denominator ----
    urows = con.execute(
        f"SELECT universe_month, permaticker FROM read_csv_auto("
        f"'{EV / 'mr002_preliminary_universe.csv.gz'}', header=true) "
        "WHERE universe_month <= DATE '2026-07-01'").fetchall()
    xw = con.execute(
        f"SELECT permaticker, cik, effective_from, effective_to FROM read_csv_auto("
        f"'{EV / 'identity_crosswalk_v0.1.csv'}', header=true) WHERE cik IS NOT NULL"
    ).fetchall()
    cik_of: dict[int, list] = {}
    for p, c, f, t in xw:
        cik_of.setdefault(int(p), []).append((f, t, int(c)))
    mapping = load_mapping()
    overrides = load_overrides()

    def issuer_at(perma: int, on: date):
        for f, t, c in cik_of.get(perma, []):
            if f <= on and (t is None or on <= t):
                return c
        return None

    def sic_at(cik: int, on: date):
        for f, t, sic, _tk, _a in seg_by_cik.get(cik, []):
            if f <= on and (t is None or on < t):
                return sic
        return None

    def map_tier(perma: int, sic: str, on: date):
        for o in overrides:
            if o["perma"] == perma and (o["from"] is None or on >= o["from"]) \
                    and (o["to"] is None or on <= o["to"]):
                if o["status"] != "approved":
                    return "needs_revision", None
                return "security_override", o["etf"]
        code = int(sic)
        for r in mapping:
            if r["lo"] <= code <= r["hi"] and (r["from"] is None or on >= r["from"]) \
                    and (r["to"] is None or on <= r["to"]):
                if r["conf"] == "LOW":
                    return "excluded_low", None
                live = ETF_LIVE.get(r["etf"])
                if live and on < live:
                    return "etf_unavailable", None
                return ("high" if r["conf"] == "HIGH" else "medium"), r["etf"]
        return "unmapped", None

    funnel = Counter()
    by_year: dict[int, Counter] = {}
    changed_secs: Counter = Counter()
    for m, perma in urows:
        on = m if isinstance(m, date) else date.fromisoformat(str(m)[:10])
        yc = by_year.setdefault(on.year, Counter())
        cik = issuer_at(int(perma), on)
        if cik is None:
            funnel["identity_unresolved"] += 1
            yc["uncovered"] += 1
            continue
        sic = sic_at(cik, on)
        if sic is None:
            funnel["pre_first_observation_gap_or_no_SIC"] += 1
            yc["uncovered"] += 1
            changed_secs[perma] += 1
            continue
        tier, _etf = map_tier(int(perma), sic, on)
        funnel[tier] += 1
        if tier in ("high", "medium", "security_override"):
            yc["covered"] += 1
        else:
            yc["uncovered"] += 1
    eligible = funnel["high"] + funnel["medium"] + funnel["security_override"]
    annual = {str(y): round(100.0 * c["covered"] / (c["covered"] + c["uncovered"]), 2)
              for y, c in sorted(by_year.items())}
    annual_ok = all(v >= 95.0 for v in
                    (100.0 * c["covered"] / (c["covered"] + c["uncovered"])
                     for c in by_year.values()))

    report = {
        "generated": datetime.now().astimezone().isoformat(),
        "sector_source": "PIT SIC (stage-2 EDGAR crawl) — NOT the current-SIC planning approximation",
        "integrity_checks": dict(integ) or {"all_clean": True},
        "stratified_sic_change_review": strat,
        "coverage_funnel_fixed_denominator": {
            "denominator_universe_months": DENOM,
            **dict(funnel),
            "final_v2_eligible": eligible,
        },
        "final_v2_coverage": {
            "covered_over_denominator": f"{eligible} / {DENOM}",
            "coverage_pct": round(100.0 * eligible / DENOM, 2),
            "registered_gate_98pct_met": bool(100.0 * eligible / DENOM >= 98.0),
            "annual_coverage_pct": annual,
            "registered_annual_minimum_95_met_every_year": annual_ok,
        },
        "top_securities_pre_first_observation_or_noSIC":
            dict(changed_secs.most_common(15)),
    }
    (EV / "MR002_PITSIC_Gate_v1.0.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
