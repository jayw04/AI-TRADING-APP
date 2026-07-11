"""MR-002 V1 build runner — EDGAR 8-K Item 2.02 earnings anchors (pre-reg v0.4 §8).

Pilot/full runner: resolves tickers -> CIK (SEC company_tickers.json) and
-> permaticker (Sharadar TICKERS), collects Item-2.02 candidates via the throttled
CAP-015 client, applies the registered collapse/amendment rules, persists anchors +
rejections to DuckDB, and writes the owner-required metrics JSON.

Optionally cross-validates anchors against Sharadar EVENTS code 22 (the 8-K item
2.02 analogue) — the quantitative leg of "validate that Item 2.02 represents an
earnings release" (the qualitative leg is the manual validation sample).

Run (host venv, read-only, no stack):
    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/mr002_build_earnings_anchors.py \
        --tickers META,AAPL,GOOGL,GOOG --since 2010-01-01 --validate-events

Data provenance only — no MR-002 signals or backtests (owner directive 2026-07-11).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import truststore

truststore.inject_into_ssl()

import duckdb  # noqa: E402
import httpx  # noqa: E402

try:
    from dotenv import load_dotenv  # noqa: E402

    _root = Path(__file__).resolve().parents[3]
    for env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if env.exists():
            load_dotenv(env, override=False)
except Exception:
    pass

# SEC fair access: descriptive UA. Overridable; empty would disable the client.
os.environ.setdefault("SEC_EDGAR_USER_AGENT", "GlobalComplyAI LLC jay.w0416@gmail.com")

from app.altdata.mr002.earnings_anchors import (  # noqa: E402
    anchor_metrics,
    build_anchors,
    collect_candidates,
)
from app.altdata.sec.cik_map import load_cik_map  # noqa: E402
from app.altdata.sec.client import EdgarClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = ROOT / "apps" / "backend" / "data" / "mr002_provenance.duckdb"
EVIDENCE_DIR = ROOT / "Docs" / "implementation" / "evidence" / "mr_002"
NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"

DDL = """
CREATE TABLE IF NOT EXISTS earnings_anchors (
    cik BIGINT, ticker VARCHAR, permaticker BIGINT, accession VARCHAR,
    report_date VARCHAR, acceptance_utc TIMESTAMPTZ, acceptance_et VARCHAR,
    session_date DATE, availability_class VARCHAR, event_time_basis VARCHAR,
    cooling_start_session DATE, cooling_end_session DATE,
    is_amendment_origin BOOLEAN, amended_by VARCHAR, collapsed_duplicates VARCHAR,
    built_at TIMESTAMPTZ,
    PRIMARY KEY (cik, accession)
);
CREATE TABLE IF NOT EXISTS anchor_rejections (
    cik BIGINT, ticker VARCHAR, accession VARCHAR, reason VARCHAR, built_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS cik_permaticker_crosswalk (
    ticker VARCHAR, cik BIGINT, permaticker BIGINT, built_at TIMESTAMPTZ,
    PRIMARY KEY (ticker)
);
"""


def ndl_rows(client: httpx.Client, dataset: str, **params) -> list[dict]:
    params["api_key"] = os.environ.get("NASDAQ_DATA_LINK_API_KEY", "")
    rows, cursor = [], None
    while True:
        q = dict(params)
        if cursor:
            q["qopts.cursor_id"] = cursor
        r = client.get(f"{NDL_BASE}/{dataset}.json", params=q, timeout=60)
        r.raise_for_status()
        dt = r.json()["datatable"]
        cols = [c["name"] for c in dt["columns"]]
        rows.extend(dict(zip(cols, row, strict=False)) for row in dt["data"])
        cursor = r.json().get("meta", {}).get("next_cursor_id")
        if not cursor:
            return rows


def permatickers_for(tickers: list[str]) -> dict[str, int | None]:
    """ticker -> permaticker via Sharadar TICKERS (explicit None when unresolved)."""
    out: dict[str, int | None] = {t: None for t in tickers}
    with httpx.Client(follow_redirects=True) as c:
        for t in tickers:
            try:
                rows = ndl_rows(c, "TICKERS", table="SEP", ticker=t)
                if rows:
                    out[t] = int(rows[0]["permaticker"])
            except Exception:
                out[t] = None
    return out


def events_code22_dates(ticker: str) -> set[str]:
    """Sharadar EVENTS dates whose codes include 22, for cross-validation."""
    with httpx.Client(follow_redirects=True) as c:
        rows = ndl_rows(c, "EVENTS", ticker=ticker)
    return {
        str(r["date"]) for r in rows
        if "22" in [s.strip() for s in str(r.get("eventcodes", "")).split("|")]
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True, help="comma-separated")
    ap.add_argument("--since", default="2010-01-01")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--validate-events", action="store_true",
                    help="cross-check anchors vs Sharadar EVENTS code 22 (+/-1 day)")
    ap.add_argument("--metrics-out", default=str(EVIDENCE_DIR / "v1_anchor_metrics.json"))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    built_at = datetime.now(UTC)

    with EdgarClient() as edgar:
        cmap = load_cik_map(edgar)
        resolved, unresolved = cmap.resolve_all(tickers)
        print(f"CIK resolved: {len(resolved)}/{len(tickers)}; unresolved={unresolved}")
        permas = permatickers_for(tickers)

        # anchors are ISSUER-level (per CIK); dual-class tickers share one anchor set
        # and map back to distinct permatickers via the crosswalk (pre-reg v0.4 §8 V2).
        by_cik: dict[int, list[str]] = {}
        for ticker, cik in resolved.items():
            by_cik.setdefault(cik, []).append(ticker)

        all_anchors, all_rejections, all_exceptions, shards_total = [], [], [], 0
        for cik, cik_tickers in by_cik.items():
            label = "/".join(sorted(cik_tickers))
            cands, shards = collect_candidates(edgar, cik, label, since=args.since)
            shards_total += shards
            res = build_anchors(cands, permaticker=permas.get(sorted(cik_tickers)[0]))
            all_anchors.extend(res.anchors)
            all_rejections.extend(res.rejections)
            all_exceptions.extend(res.exceptions)
            n_amended = sum(1 for a in res.anchors if a.amended_by)
            print(f"  {label}: {len(cands)} 2.02 candidates -> {len(res.anchors)} anchors "
                  f"({n_amended} amended, {len(res.rejections)} rejected/collapsed)")

    # persist
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            con.execute(stmt)
    ciks = list(by_cik.keys())
    if ciks:
        ph = ",".join("?" * len(ciks))
        con.execute(f"DELETE FROM earnings_anchors WHERE cik IN ({ph})", ciks)
        con.execute(f"DELETE FROM anchor_rejections WHERE cik IN ({ph})", ciks)
    for ticker in tickers:
        con.execute("DELETE FROM cik_permaticker_crosswalk WHERE ticker = ?", [ticker])
        con.execute(
            "INSERT INTO cik_permaticker_crosswalk VALUES (?,?,?,?)",
            [ticker, resolved.get(ticker), permas.get(ticker), built_at],
        )
    for a in all_anchors:
        con.execute(
            "INSERT INTO earnings_anchors VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [a.cik, a.ticker, a.permaticker, a.accession, a.report_date,
             a.acceptance_utc, a.acceptance_et.isoformat(), a.session_date,
             a.availability_class, a.event_time_basis,
             a.cooling_start_session, a.cooling_end_session, a.is_amendment_origin,
             json.dumps(a.amended_by), json.dumps(a.collapsed_duplicates), built_at],
        )
    for r in all_rejections:
        con.execute("INSERT INTO anchor_rejections VALUES (?,?,?,?,?)",
                    [r.cik, r.ticker, r.accession, r.reason, built_at])
    con.close()

    # metrics
    from app.altdata.mr002.earnings_anchors import AnchorBuildResult
    merged = AnchorBuildResult(anchors=all_anchors, rejections=all_rejections,
                               exceptions=all_exceptions)
    metrics = anchor_metrics(merged, n_securities_requested=len(tickers))
    # ticker-level coverage (a dual-class pair counts per security, via the shared CIK)
    ciks_with_anchor = {a.cik for a in all_anchors}
    covered = [t for t in tickers if resolved.get(t) in ciks_with_anchor]
    metrics["securities_with_anchor"] = len(covered)
    metrics["pct_securities_with_anchor"] = round(100.0 * len(covered) / max(1, len(tickers)), 2)
    metrics["unresolved_tickers"] = unresolved
    metrics["older_shards_fetched"] = shards_total
    metrics["since"] = args.since
    metrics["built_at"] = built_at.isoformat()

    # optional Sharadar EVENTS code-22 cross-validation (item-2.02 = earnings check)
    if args.validate_events:
        val = {}
        for ticker in [t for t in tickers if t not in unresolved]:
            ev_dates = {date.fromisoformat(d) for d in events_code22_dates(ticker)}
            if not ev_dates:
                val[ticker] = {"events_code22": 0, "matched_pct": None}
                continue
            anchor_dates = {a.acceptance_et.date() for a in all_anchors
                            if ticker in a.ticker.split("/")}
            matched = sum(
                1 for d in ev_dates
                if any(abs((d - ad).days) <= 1 for ad in anchor_dates)
            )
            val[ticker] = {
                "events_code22": len(ev_dates),
                "anchors": len(anchor_dates),
                "matched_within_1d": matched,
                "matched_pct": round(100.0 * matched / len(ev_dates), 1),
            }
        metrics["events_code22_crosscheck"] = val

    out = Path(args.metrics_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, default=str))
    print(f"\nanchors={len(all_anchors)} rejections={len(all_rejections)} db={db_path}")
    print(f"metrics -> {out}")
    print(json.dumps({k: v for k, v in metrics.items()
                      if k not in ("exceptions", "events_code22_crosscheck")}, indent=2, default=str))
    if "events_code22_crosscheck" in metrics:
        print("EVENTS code-22 cross-check:", json.dumps(metrics["events_code22_crosscheck"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
