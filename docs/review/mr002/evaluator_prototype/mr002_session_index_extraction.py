"""MR-002 validation/OOS — narrow session-index metadata extraction (owner-authorized).

CLASSIFICATION: calendar-metadata extraction ONLY. Reads exactly one column — the session-date
column of the pinned snapshot — DISTINCT and ORDERED. It reads/computes NO prices, returns,
positions, signals, scores, P&L, volatility, summary statistics, or security distributions. It is
NOT an unsealing of economic data. Output: the seam dates and fold boundaries needed to freeze the
v1.0 governance package, plus snapshot pre/post hash proof.

Governing calendar source (owner ruling): the registered snapshot's frozen session index —
apps/backend/data/mr002_research.duckdb, sha256
24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a.

Seam rule (owner ruling): registered session ordinals, not calendar-day arithmetic.
  - formation exclusion at window start: 69 sessions (exclude window-local indices 0..68).
  - complete-realization requirement: next-open (t+1) + registered 5-session MAX hold, exit-ladder
    at next-open. The realization fill is the open AFTER the 5th held session => the horizon spans
    decision t through t+6. Governing last-eligible index = N-1-6. A −5 alternative (return
    realized by the 5th held session's close, no separate exit-open) is REPORTED for owner
    ratification; the −6 (next-open exit) reading is the default, faithful to the frozen
    "next-open execution" applying to the exit ladder.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys

import duckdb

DB = "apps/backend/data/mr002_research.duckdb"
DB_SHA = "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a"
SESSION_QUERY = "SELECT DISTINCT date FROM prices ORDER BY date"
CROSSCHECK_QUERY = "SELECT DISTINCT date FROM etf_prices ORDER BY date"

WINDOWS = {  # inclusive boundaries transcribed from the frozen design (v1.1 refreeze + sealed manifest)
    "development": ("2013-01-02", "2019-10-02", 1700),
    "validation": ("2019-10-03", "2023-02-16", 850),
    "oos": ("2023-02-17", "2026-07-10", 850),
}
FORMATION_EXCLUDE = 69          # owner-ruled formation exclusion at window start
HORIZON_GOVERNING = 6           # next-open exit after 5 held sessions (t+1..t+6)
HORIZON_ALT = 5                 # close-exit alternative (reported for ratification)
N_FOLDS = 5


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _window_slice(all_dates, start, end):
    s = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    return [d for d in all_dates if s <= d <= e]


def _eligible(win_dates, horizon):
    """First eligible index = FORMATION_EXCLUDE; last eligible index = N-1-horizon."""
    n = len(win_dates)
    first_idx = FORMATION_EXCLUDE
    last_idx = n - 1 - horizon
    if last_idx < first_idx:
        return None
    return first_idx, last_idx, win_dates[first_idx], win_dates[last_idx], last_idx - first_idx + 1


def _folds(win_dates, first_idx, last_idx, k):
    """k contiguous, non-overlapping, nearly-equal folds over the eligible span (frozen design:
    'five contiguous, non-overlapping, nearly equal folds'). Remainder distributed to the earliest
    folds (deterministic)."""
    span = last_idx - first_idx + 1
    base, rem = divmod(span, k)
    bounds = []
    cur = first_idx
    for i in range(k):
        size = base + (1 if i < rem else 0)
        f0, f1 = cur, cur + size - 1
        bounds.append({"fold": i + 1, "first_idx": f0, "last_idx": f1,
                       "first_date": str(win_dates[f0]), "last_date": str(win_dates[f1]),
                       "sessions": size})
        cur = f1 + 1
    return bounds


def main() -> int:
    pre = _sha_file(DB)
    if pre != DB_SHA:
        print(json.dumps({"error": f"SNAPSHOT_HASH_MISMATCH:{pre}"}))
        return 2
    con = duckdb.connect(DB, read_only=True)
    all_dates = [r[0] for r in con.execute(SESSION_QUERY).fetchall()]
    cross = [r[0] for r in con.execute(CROSSCHECK_QUERY).fetchall()]
    con.close()
    post = _sha_file(DB)

    # Governed session index = the union of the three window slices (the frozen 3,400). The prices
    # table also carries pre-2013 history (total distinct dates > 3,400); only the in-window
    # sessions are governing. Cross-check prices vs etf_prices WITHIN the governed range.
    gs, ge = datetime.date(2013, 1, 2), datetime.date(2026, 7, 10)
    governed = [d for d in all_dates if gs <= d <= ge]
    cross_gov = [d for d in cross if gs <= d <= ge]
    governed_hash = hashlib.sha256("|".join(str(d) for d in governed).encode()).hexdigest()
    cross_gov_hash = hashlib.sha256("|".join(str(d) for d in cross_gov).encode()).hexdigest()

    out = {
        "record_type": "MR002_SESSION_INDEX_EXTRACTION",
        "version": "1.0",
        "snapshot": DB, "snapshot_sha256_pre": pre, "snapshot_sha256_post": post,
        "snapshot_unchanged": pre == post == DB_SHA,
        "session_query": SESSION_QUERY, "crosscheck_query": CROSSCHECK_QUERY,
        "prices_total_distinct_dates_all_history": len(all_dates),
        "governed_sessions": len(governed),
        "governed_session_list_sha256": governed_hash,
        "etf_governed_list_sha256": cross_gov_hash,
        "prices_equals_etf_within_governed_window": governed == cross_gov,
        "seam_rule": {"formation_exclude_sessions": FORMATION_EXCLUDE,
                      "horizon_governing_sessions": HORIZON_GOVERNING,
                      "horizon_alt_sessions": HORIZON_ALT,
                      "endpoint_convention": "governing = next-open exit (t+1..t+6); alt = close-exit (t+1..t+5)"},
        "windows": {},
    }
    for name, (s, e, expected_n) in WINDOWS.items():
        wd = _window_slice(all_dates, s, e)
        entry = {"declared_start": s, "declared_end": e, "expected_sessions": expected_n,
                 "observed_sessions": len(wd), "count_matches_frozen": len(wd) == expected_n,
                 "first_session": str(wd[0]), "last_session": str(wd[-1])}
        if name != "development":
            gov = _eligible(wd, HORIZON_GOVERNING)
            alt = _eligible(wd, HORIZON_ALT)
            entry["scoring_eligible_governing"] = {
                "first_idx": gov[0], "last_idx": gov[1], "first_date": str(gov[2]),
                "last_date": str(gov[3]), "eligible_sessions": gov[4]}
            entry["scoring_eligible_alt_close_exit"] = {
                "first_date": str(alt[2]), "last_date": str(alt[3]), "eligible_sessions": alt[4]}
            if name == "validation":
                entry["folds_governing"] = _folds(wd, gov[0], gov[1], N_FOLDS)
        out["windows"][name] = entry

    print(json.dumps(out, indent=1, default=str))
    return 0 if all(out["windows"][w].get("count_matches_frozen") for w in out["windows"]) else 1


if __name__ == "__main__":
    sys.exit(main())
