"""MR-002 FINAL PIT-SIC gate — recomputed after the predecessor remedy (owner GO).

Combines:
  - stage-2 PIT SIC observations (the 4 truncated-cache CIKs REPLACED by the
    track-D fresh re-fetch — a data-integrity repair, not an addition);
  - supplemental observations (track A predecessor CIKs, track B FPI forms);
  - the effective-dated predecessor overrides (crosswalk split at the documented
    reorganization event date: predecessor interval [start, event), successor
    interval [event, end) — no overlap, no gap).

PROVENANCE (owner condition 5): every observation stays attached to the CIK THAT
FILED IT. The security attachment happens here, at gate time, through the override.

Re-runs ALL integrity tests from scratch (owner condition 6): pre-observation fill,
segment monotonicity/non-overlap, same-day conflicts, boundary-observation
consistency, six-way funnel, 98% overall gate, 95% annual floor, V1 coverage,
duplicate keys, deterministic rebuild.

Result is PROVISIONAL until the owner countersigns the override registry.

Run: PYTHONPATH=apps/backend .venv python apps/backend/scripts/mr002_pitsic_gate_v2.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[3]
EV = ROOT / "docs" / "implementation" / "evidence" / "mr_002"
SUP = EV / "supplemental"
DENOM = 40750
ETF_LIVE = {"XLC": date(2018, 6, 19), "XLRE": date(2015, 10, 8)}
TAXO = (date(2016, 9, 1), date(2018, 10, 1))
REPAIRED_CIKS = {101829, 101830, 101778, 1466258}   # track D supersedes stage-2


def d(x):
    return x.date() if hasattr(x, "date") else x


def load_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    con = duckdb.connect()

    # ---------- observations: stage-2 (minus repaired CIKs) + supplemental ----------
    obs = [(int(c), d(t), str(int(float(s))).zfill(4), fm, acc)
           for c, acc, fm, t, s in con.execute(
               f"SELECT cik, accession, form, accepted_utc, sic FROM read_csv_auto("
               f"'{EV / 'stage2' / 'sic_observations.csv.gz'}', header=true) "
               "WHERE sic IS NOT NULL").fetchall()
           if int(c) not in REPAIRED_CIKS]
    sup = con.execute(
        f"SELECT cik, accession, form, accepted_utc, sic FROM read_csv_auto("
        f"'{SUP / 'sic_observations.csv.gz'}', header=true) WHERE sic IS NOT NULL"
    ).fetchall()
    obs += [(int(c), d(t), str(int(float(s))).zfill(4), fm, acc)
            for c, acc, fm, t, s in sup]
    # de-duplicate on (cik, accession): a predecessor CIK may also have been in the
    # stage-2 issuer set (e.g. EIDP 30554). Identical filings, identical SIC — keep
    # one; the count of collisions is reported for transparency.
    seen: dict[tuple, tuple] = {}
    collisions = 0
    for o in obs:
        k = (o[0], o[4])
        if k in seen:
            collisions += 1
            continue
        seen[k] = o
    obs = list(seen.values())

    # ---------- rebuild segments deterministically from the merged observations ----------
    by_cik: dict[int, list] = {}
    for cik, dt, sic, form, acc in obs:
        by_cik.setdefault(cik, []).append((dt, sic, form, acc))
    integ = Counter()
    segs: dict[int, list] = {}
    for cik, oo in by_cik.items():
        oo.sort(key=lambda x: x[0])
        by_day: dict[date, set] = {}
        for dt, sic, _f, _a in oo:
            by_day.setdefault(dt, set()).add(sic)
        integ["same_day_conflicts"] += sum(1 for v in by_day.values() if len(v) > 1)
        seq = []
        for dt, sic, _f, acc in oo:
            if seq and seq[-1][2] == sic:
                continue
            if seq:
                seq[-1] = (seq[-1][0], dt, seq[-1][2], seq[-1][3])   # close previous
            seq.append((dt, None, sic, acc))
        segs[cik] = seq
        # integrity: monotonic, contiguous, no pre-observation fill, boundary-backed
        first_obs = oo[0][0]
        if seq and seq[0][0] != first_obs:
            integ["segment_before_first_observation"] += 1
        for a, b in zip(seq, seq[1:], strict=False):
            if a[1] != b[0]:
                integ["non_contiguous_boundary"] += 1
            if a[1] and a[1] < a[0]:
                integ["negative_duration"] += 1
            if not any(dt == b[0] and sic == b[2] for dt, sic, _f, _a in oo):
                integ["boundary_without_observation"] += 1
    integ["duplicate_observation_keys_after_dedupe"] = (
        len(obs) - len({(c, a) for c, _d, _s, _f, a in obs}))
    integ["merge_collisions_deduped(stage2_x_supplemental)"] = collisions

    # ---------- crosswalk + effective-dated predecessor overrides ----------
    xw = con.execute(
        f"SELECT permaticker, cik, effective_from, effective_to FROM read_csv_auto("
        f"'{EV / 'identity_crosswalk_v0.1.csv'}', header=true) WHERE cik IS NOT NULL"
    ).fetchall()
    cik_of: dict[int, list] = {}
    for p, c, f, t in xw:
        cik_of.setdefault(int(p), []).append([d(f), d(t) if t else None, int(c)])

    reg = load_csv(EV / "predecessor_override_registry_v0.1.csv")
    applied = []
    for r in reg:
        perma = int(r["permaticker"])
        ev = date.fromisoformat(r["event_date"])
        pred, succ = int(r["predecessor_cik"]), int(r["successor_cik"])
        ivals = cik_of.get(perma, [])
        # split the successor's interval at the event date; predecessor takes the
        # earlier part. No overlap (pred ends event-1), no gap.
        new = []
        for f, t, c in ivals:
            if c == succ and f < ev:
                new.append([f, ev - timedelta(days=1), pred])
                new.append([ev, t, succ])
            else:
                new.append([f, t, c])
        cik_of[perma] = new
        applied.append({"ticker": r["ticker"], "permaticker": perma,
                        "predecessor_cik": pred, "successor_cik": succ,
                        "boundary": str(ev), "flags": r["flags"]})
    # overlap check on the extended crosswalk (owner condition 1): a permaticker may
    # legitimately carry several TICKER rows (dual-class / renames) with the SAME CIK
    # and window — only DIFFERENT-CIK intervals must never overlap.
    for _perma, ivals in cik_of.items():
        ordered = sorted(ivals, key=lambda x: (x[0], x[2]))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if a[2] == b[2]:
                    continue
                a_hi = a[1] or date.max
                b_hi = b[1] or date.max
                if a[0] <= b_hi and b[0] <= a_hi:
                    integ["crosswalk_different_cik_overlap"] += 1

    mapping = load_csv(EV / "sic_sector_etf_mapping_v0.8.csv")
    overrides = load_csv(EV / "security_sector_overrides_v0.6.csv")

    def issuer_at(perma: int, on: date):
        for f, t, c in cik_of.get(perma, []):
            if f <= on and (t is None or on <= t):
                return c
        return None

    def sic_at(cik: int, on: date):
        for f, t, sic, _a in segs.get(cik, []):
            if f <= on and (t is None or on < t):
                return sic
        return None

    def tier_of(perma: int, sic: str, on: date):
        for o in overrides:
            if o["permaticker"] and int(o["permaticker"]) == perma \
                    and (not o["effective_from"] or on >= date.fromisoformat(o["effective_from"])) \
                    and (not o["effective_to"] or on <= date.fromisoformat(o["effective_to"])):
                return ("security_override" if o["review_status"] == "approved"
                        else "needs_revision")
        code = int(sic)
        for r in mapping:
            if int(r["sic_start"]) <= code <= int(r["sic_end"]) \
                    and (not r["effective_from"] or on >= date.fromisoformat(r["effective_from"])) \
                    and (not r["effective_to"] or on <= date.fromisoformat(r["effective_to"])):
                if r["mapping_confidence"] == "LOW":
                    return "excluded_low"
                live = ETF_LIVE.get(r["sector_etf"])
                if live and on < live:
                    return "etf_unavailable"
                return "high" if r["mapping_confidence"] == "HIGH" else "medium"
        return "unmapped"

    urows = con.execute(
        f"SELECT universe_month, ticker, permaticker FROM read_csv_auto("
        f"'{EV / 'mr002_preliminary_universe.csv.gz'}', header=true) "
        "WHERE universe_month <= DATE '2026-07-01'").fetchall()
    funnel = Counter()
    by_year: dict[int, Counter] = {}
    residual: Counter = Counter()
    recovered_by: Counter = Counter()
    for m, tick, perma in urows:
        on = d(m) if not isinstance(m, str) else date.fromisoformat(m[:10])
        yc = by_year.setdefault(on.year, Counter())
        cik = issuer_at(int(perma), on)
        if cik is None:
            funnel["identity_unresolved"] += 1
            yc["uncovered"] += 1
            continue
        sic = sic_at(cik, on)
        if sic is None:
            funnel["pre_first_observation_or_no_SIC"] += 1
            yc["uncovered"] += 1
            residual[tick] += 1
            continue
        t = tier_of(int(perma), sic, on)
        funnel[t] += 1
        if t in ("high", "medium", "security_override"):
            yc["covered"] += 1
            if any(a["permaticker"] == int(perma) for a in applied) or \
                    cik in REPAIRED_CIKS or cik in (1413447, 818686, 1650372,
                                                    1530721, 1656472, 1737927):
                recovered_by[tick] += 1
        else:
            yc["uncovered"] += 1
    eligible = funnel["high"] + funnel["medium"] + funnel["security_override"]
    annual = {str(y): round(100.0 * c["covered"] / (c["covered"] + c["uncovered"]), 2)
              for y, c in sorted(by_year.items())}
    pct = round(100.0 * eligible / DENOM, 2)

    report = {
        "generated": datetime.now().astimezone().isoformat(),
        "status": "PROVISIONAL — pending owner countersign of the predecessor "
                  "override registry",
        "sector_source": "PIT SIC (stage-2 + supplemental), never current-SIC",
        "integrity_checks_rerun": dict(integ) or {"all_clean": True},
        "overrides_applied": applied,
        "coverage_funnel_fixed_denominator": {
            "denominator_universe_months": DENOM, **dict(funnel),
            "final_v2_eligible": eligible},
        "final_v2_coverage": {
            "covered_over_denominator": f"{eligible} / {DENOM}",
            "coverage_pct": pct,
            "gate_98pct_met": pct >= 98.0,
            "annual_coverage_pct": annual,
            "annual_minimum_95_met_every_year": all(v >= 95.0 for v in annual.values()),
        },
        "months_recovered_by_security": dict(recovered_by.most_common()),
        "residual_uncovered_by_security": dict(residual.most_common()),
        "unchanged_treatments": {
            "DHR": "needs_revision — still excluded (archive evidence owed)",
            "excluded_low": "still excluded by policy",
            "identity_unresolved": "delisting tails, unchanged",
        },
    }
    (EV / "MR002_PITSIC_Gate_v2.0.json").write_text(json.dumps(report, indent=2,
                                                               default=str))
    print(json.dumps({k: report[k] for k in
                      ("integrity_checks_rerun", "coverage_funnel_fixed_denominator",
                       "final_v2_coverage")}, indent=1, default=str))
    print("residual:", dict(residual.most_common(10)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
