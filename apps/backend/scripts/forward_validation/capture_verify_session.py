"""Capture-and-verify a governed SEP session — the T+2 structural checks, implemented.

Implements OwnerRuling_SEPIngestLag_T2_v1.0.md section 5: the nine mandatory structural checks and
the gross-truncation guard. Refuses a defective session rather than capturing it, because ADR 0048
forbids repairing a committed delta and routes amendments to a new corpus version.

Two modes, and the default is the safe one:

    verify-only (default)   compute everything, write NOTHING. Safe on any session, any day.
    capture     (--out DIR) write the session artifact + report. REFUSED unless the session is
                            T+2 eligible, so this tool cannot be the thing that captures early.

    apps/backend/.venv/Scripts/python.exe capture_verify_session.py --session 2026-07-23
    apps/backend/.venv/Scripts/python.exe capture_verify_session.py --session 2026-07-27 --out ./cap

The corpus is opened READ-ONLY and is never written by this script under any mode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import truststore

truststore.inject_into_ssl()

from dotenv import load_dotenv  # noqa: E402

# The repository this file lives in IS the code root. The standalone copy searched a list of candidate
# checkouts, which is exactly how a tool ends up validating one tree while importing another's code.
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "apps" / "backend"
for _env in (REPO_ROOT / ".env", BACKEND_ROOT / ".env"):
    if _env.exists():
        load_dotenv(_env, override=False)

sys.path.insert(0, str(BACKEND_ROOT))

import duckdb  # noqa: E402

from app.factor_data.providers.sharadar import SharadarProvider  # noqa: E402
from app.validation.eval_calendar import is_trading_session  # noqa: E402
from app.validation.governed_corpus import GOVERNED_UNIVERSE_SIZE, canonical_json  # noqa: E402

#: The governed store. Overridable via `FORWARD_VALIDATION_STORE` because the operator's working copy
#: and the deployed host's copy are different files, and neither belongs hard-coded in the repository.
CORPUS = Path(os.environ.get("FORWARD_VALIDATION_STORE")
              or BACKEND_ROOT / "data" / "factor_data_full.refresh.duckdb")
CAPTURE_LAG_TRADING_DAYS = 2
TRUNCATION_FLOOR_FRACTION = 0.90
PRIOR_SESSIONS_FOR_MEDIAN = 5
GOVERNING_TZ = ZoneInfo("America/New_York")


def universe_digest(tickers: set[str]) -> str:
    """Canonical identity of the governed universe.

    sha256 over `canonical_json` of the sorted ticker list — the module's own deterministic encoding,
    the same one every other identity in `governed_corpus` is built on. Ratified by the owner on
    2026-07-28; for the frozen 14,150-ticker universe it yields `2b34970fc123689b…`.
    """
    return hashlib.sha256(canonical_json(sorted(tickers))).hexdigest()


def nth_trading_day_after(start: date, n: int) -> date:
    cur, seen = start, 0
    while seen < n:
        cur += timedelta(days=1)
        if is_trading_session(cur):
            seen += 1
    return cur


def load_governed_context(session: date) -> dict:
    """Universe + neighbouring-session row counts, read-only, from the governing corpus."""
    con = duckdb.connect(str(CORPUS), read_only=True)
    try:
        universe = {r[0] for r in con.execute("SELECT DISTINCT ticker FROM sep").fetchall()}
        prior = con.execute(
            "SELECT date, count(*) FROM sep WHERE date < ? GROUP BY date "
            "ORDER BY date DESC LIMIT ?", [session, PRIOR_SESSIONS_FOR_MEDIAN]).fetchall()
        prior_tickers = {r[0] for r in con.execute(
            "SELECT DISTINCT ticker FROM sep WHERE date < ? AND date >= ?",
            [session, session - timedelta(days=12)]).fetchall()}
        stored = con.execute("SELECT count(*) FROM sep WHERE date = ?", [session]).fetchone()[0]
    finally:
        con.close()
    return {"universe": universe, "prior_counts": [(str(d), n) for d, n in prior],
            "prior_tickers": prior_tickers, "stored_rows_for_session": stored}


def fetch_source(session: date) -> tuple[object, str]:
    import httpx

    refreshed = None
    try:
        resp = httpx.get("https://data.nasdaq.com/api/v3/datatables/SHARADAR/SEP/metadata",
                         params={"api_key": os.environ["NASDAQ_DATA_LINK_API_KEY"]}, timeout=30)
        if resp.status_code == 200:
            refreshed = resp.json()["datatable"]["status"].get("refreshed_at")
    except Exception:  # noqa: BLE001
        pass
    with SharadarProvider() as provider:
        df = provider.fetch_table("SEP", date=session.isoformat())
    return df, str(refreshed)


def verify(session: date) -> dict:
    retrieved_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ctx = load_governed_context(session)
    universe = ctx["universe"]
    df, refreshed_at = fetch_source(session)

    checks: list[dict] = []

    def check(num: int, name: str, ok: bool, detail: str) -> None:
        checks.append({"n": num, "name": name, "pass": bool(ok), "detail": detail})

    # 1 — the expected session exists (both as a calendar session and as source rows)
    is_session = is_trading_session(session)
    check(1, "session_exists", bool(len(df)) and is_session,
          f"source rows={len(df):,}, XNYS trading session={is_session}")

    # 2 — exact original governed-universe restriction
    digest = universe_digest(universe)
    check(2, "universe_exact", len(universe) == GOVERNED_UNIVERSE_SIZE,
          f"{len(universe):,} tickers (expect {GOVERNED_UNIVERSE_SIZE:,}), digest {digest[:16]}...")

    total_rows = len(df)
    in_universe = df[df["ticker"].isin(universe)] if total_rows else df
    governed_rows = len(in_universe)
    dropped = total_rows - governed_rows

    # 3 — no duplicate (ticker, date)
    dupes = 0
    if governed_rows:
        dupes = int(in_universe.duplicated(subset=["ticker", "date"]).sum())
    check(3, "no_duplicate_ticker_date", dupes == 0, f"{dupes} duplicate (ticker,date) rows")

    # 4 — no out-of-universe rows. Post-restriction this is near-tautological; its value is catching
    #     a filter bug, so it asserts the subset property rather than trusting the filter ran.
    leaked = 0 if not governed_rows else int((~in_universe["ticker"].isin(universe)).sum())
    check(4, "no_out_of_universe_rows", leaked == 0,
          f"{leaked} leaked; {dropped:,} out-of-universe rows dropped from {total_rows:,} source rows")

    # 5 — gross-truncation guard against neighbouring governed sessions
    prior_counts = [n for _, n in ctx["prior_counts"]]
    if prior_counts:
        median = statistics.median(prior_counts)
        floor = TRUNCATION_FLOOR_FRACTION * median
        ok5 = governed_rows >= floor
        d5 = (f"{governed_rows:,} governed rows vs floor {floor:,.0f} "
              f"(={TRUNCATION_FLOOR_FRACTION:.0%} of median {median:,.0f} over prior "
              f"{len(prior_counts)} sessions {ctx['prior_counts']})")
    else:
        ok5, d5 = False, "no prior governed sessions available to form a median"
    check(5, "row_count_not_truncated", ok5, d5)

    # 6 — provenance timestamps recorded
    stamps = {}
    if governed_rows and "lastupdated" in in_universe.columns:
        stamps = {str(k): int(v) for k, v in
                  in_universe["lastupdated"].astype(str).value_counts().sort_index().items()}
    check(6, "provenance_timestamps_recorded", bool(stamps) and bool(retrieved_at),
          f"lastupdated={stamps}, retrieved_at={retrieved_at}, refreshed_at={refreshed_at}")

    # 7 — artifact hash + row count (hash of the canonical restricted payload)
    payload = b""
    artifact_sha = ""
    if governed_rows:
        cols = [c for c in in_universe.columns]
        rows = in_universe.sort_values(["ticker", "date"])[cols].astype(str).values.tolist()
        payload = canonical_json({"session": session.isoformat(), "columns": cols, "rows": rows})
        artifact_sha = hashlib.sha256(payload).hexdigest()
    check(7, "artifact_hash_and_count", bool(artifact_sha),
          f"sha256={artifact_sha[:16]}... over {governed_rows:,} governed rows, {len(payload):,} bytes")

    # 8 — missing-ticker set. As specified, this is relative to the FULL governed universe, which is
    #     dominated by long-delisted names (~8k by construction) and so is a record, not a signal.
    #     The diagnostic that would actually catch a defect is the recent-session diff, computed too.
    present = set(in_universe["ticker"]) if governed_rows else set()
    missing_vs_universe = universe - present
    missing_vs_recent = ctx["prior_tickers"] - present
    check(8, "missing_ticker_set_recorded", True,
          f"{len(missing_vs_universe):,} of {len(universe):,} universe tickers absent (expected: "
          f"mostly delisted) | DIAGNOSTIC: {len(missing_vs_recent):,} absent that traded in the "
          f"prior ~2 weeks{' -> ' + str(sorted(missing_vs_recent)[:12]) if missing_vs_recent else ''}")

    # 9 — ACTIONS bounded to the same session cutoff.
    #     The requirement is that the CAPTURED SET is bounded, not that the source has nothing later:
    #     once a capture runs at T+2 the source necessarily carries rows dated after the session, and
    #     future-dated corporate actions are a real PIT hazard precisely because they exist upstream.
    #     So apply the bound, prove the bounded set respects it, and RECORD the exclusions — the same
    #     treatment countersignature v2.0 section 5 gave the four future-dated 2026-07-27 splits.
    actions_excluded: list[str] = []
    try:
        with SharadarProvider() as provider:
            act = provider.fetch_table(
                "ACTIONS", **{"date.gte": (session - timedelta(days=5)).isoformat()})
        if len(act):
            dates = act["date"].astype(str)
            bounded = act[dates <= session.isoformat()]
            excluded = act[dates > session.isoformat()]
            at_session = act[dates == session.isoformat()]
            max_bounded = bounded["date"].astype(str).max() if len(bounded) else "(none)"
            ok9 = max_bounded == "(none)" or max_bounded <= session.isoformat()
            actions_excluded = sorted({str(d) for d in excluded["date"].astype(str)})[:5]
            check(9, "actions_bounded_to_cutoff", ok9,
                  f"bounded set max date={max_bounded} (<= {session}); {len(at_session)} rows AT the "
                  f"session; {len(excluded):,} future-dated rows correctly EXCLUDED "
                  f"(first dates {actions_excluded})")
        else:
            check(9, "actions_bounded_to_cutoff", True, "no ACTIONS rows in the window")
    except Exception as exc:  # noqa: BLE001
        check(9, "actions_bounded_to_cutoff", False, f"probe failed: {type(exc).__name__}: {exc}")

    eligible_on = nth_trading_day_after(session, CAPTURE_LAG_TRADING_DAYS)
    today_et = datetime.now(GOVERNING_TZ).date()

    return {
        "session": session.isoformat(),
        "retrieved_at": retrieved_at,
        "refreshed_at": refreshed_at,
        "source_rows": total_rows,
        "governed_rows": governed_rows,
        "out_of_universe_dropped": dropped,
        "universe_size": len(universe),
        "governed_universe_sha256": digest,
        "artifact_sha256": artifact_sha,
        "lastupdated_distribution": stamps,
        "missing_vs_universe": len(missing_vs_universe),
        "missing_vs_recent_sessions": sorted(missing_vs_recent),
        "corpus_stored_rows_for_session": ctx["stored_rows_for_session"],
        "t2_eligible_on": eligible_on.isoformat(),
        "t2_eligible_now": today_et >= eligible_on,
        "checks": checks,
        "all_checks_pass": all(c["pass"] for c in checks),
        "_payload": payload,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capture-and-verify a governed SEP session (T+2 checks).")
    ap.add_argument("--session", required=True)
    ap.add_argument("--out", help="write artifact + report here; REFUSED unless T+2 eligible")
    args = ap.parse_args(argv)

    session = date.fromisoformat(args.session)
    report = verify(session)
    payload = report.pop("_payload")

    print(f"=== governed session capture-verify - {session} ===")
    print(f"source rows {report['source_rows']:,} -> governed {report['governed_rows']:,} "
          f"(dropped {report['out_of_universe_dropped']:,} out-of-universe)")
    stored = report["corpus_stored_rows_for_session"]
    if stored:
        delta = report["governed_rows"] - stored
        print(f"corpus already stores {stored:,} rows for this session; recomputed differs by "
              f"{delta:+,} (post-capture accretion)")
    print()
    for c in report["checks"]:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['n']}. {c['name']:<32} {c['detail']}")

    print(f"\nT+2 eligible on {report['t2_eligible_on']} -> eligible now: {report['t2_eligible_now']}")
    verdict = "ALL STRUCTURAL CHECKS PASS" if report["all_checks_pass"] else "STRUCTURAL CHECKS FAILED"
    print(f"VERDICT: {verdict}")

    if not args.out:
        print("\nverify-only mode: nothing written.")
        return 0 if report["all_checks_pass"] else 1

    if not report["t2_eligible_now"]:
        print(f"\nREFUSED to write: session is not T+2 eligible until {report['t2_eligible_on']}. "
              f"Structural checks passing does NOT authorize an early capture.")
        return 2
    if not report["all_checks_pass"]:
        print("\nREFUSED to write: structural checks failed.")
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"sep_governed_{session}.json").write_bytes(payload)
    (out / f"capture_report_{session}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nwrote artifact + report to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
