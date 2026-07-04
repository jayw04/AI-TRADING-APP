"""P9 §1 — ingest the Sharadar SEP/TICKERS/ACTIONS spine into the DuckDB store.

Host-venv entrypoint (no Docker, no stack) — same posture as the fixture-gen and
range-insight scripts. Idempotent: re-running converges to the same state
(SEP keyed by (ticker,date); TICKERS by ticker; ACTIONS replaced per-ticker).

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/ingest_sharadar.py --tickers AAPL,MSFT,NVDA,LEH

Scope + rate limit (P9 §0): Nasdaq Data Link caps at ~1M rows/day. SEP/ACTIONS
are pulled per-ticker, so a broad universe spans multiple days — re-run with
``--skip-existing`` to resume cheaply (already-ingested SEP tickers are skipped,
not re-fetched). TICKERS is a single full-table pull (~22k rows). There is
deliberately no full-market SEP pull: pass an explicit ticker list/file so a run
can never silently blow the daily limit.

Key hygiene (ADR 0018 §5): the API key is read from NASDAQ_DATA_LINK_API_KEY and
printed as a length only, never a value; it is never written to logs/audit.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# ADR 0017 — OS trust store before any HTTPS (a standalone script must do this
# itself; the app does it at startup). The provider also injects defensively.
import truststore

truststore.inject_into_ssl()

# Load .env (root and backend) before reading the key, mirroring the §0 verifier.
try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parents[3]
    for _env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if _env.exists():
            load_dotenv(_env, override=False)
except Exception:
    pass

from app.factor_data.providers.sharadar import SharadarConfigError, SharadarProvider  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

ALL_DATASETS = ("tickers", "sep", "actions", "sf1")


def _parse_tickers(args: argparse.Namespace) -> list[str]:
    raw: list[str] = []
    if args.tickers:
        raw += [t.strip() for t in args.tickers.split(",")]
    if args.tickers_file:
        text = Path(args.tickers_file).read_text(encoding="utf-8")
        raw += [line.strip() for line in text.replace(",", "\n").splitlines()]
    # de-dupe, preserve order, upper-case, drop blanks
    seen: dict[str, None] = {}
    for t in raw:
        t = t.upper()
        if t and t not in seen:
            seen[t] = None
    return list(seen)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest Sharadar SEP/TICKERS/ACTIONS into DuckDB.")
    ap.add_argument("--tickers", help="comma-separated tickers for SEP/ACTIONS")
    ap.add_argument("--tickers-file", help="file of tickers (comma- or newline-separated)")
    ap.add_argument(
        "--datasets",
        default=",".join(ALL_DATASETS),
        help=f"comma-separated subset of {ALL_DATASETS} (default: all)",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip SEP/ACTIONS for tickers already present in sep (resume across rate-limit days)",
    )
    ap.add_argument("--db", help="override store path (default: WORKBENCH_FACTOR_DATA_DB_PATH)")
    ap.add_argument(
        "--from",
        dest="from_date",
        help="date.gte filter for SEP/ACTIONS (YYYY-MM-DD) — bound the pull so a broad "
        "ticker list stays within the 1M-rows/day cap (e.g. a paper-universe ingest).",
    )
    ap.add_argument(
        "--skip-deep-enough",
        action="store_true",
        help="DEEPEN resume: skip a ticker's SEP only when its existing earliest date is already "
        "<= --from (i.e. deep enough). Unlike --skip-existing (skips on mere presence, so it would "
        "never deepen), this makes a multi-day back-fill re-runnable — each day it pulls only the "
        "tickers still shallower than --from. Requires --from.",
    )
    args = ap.parse_args(argv)
    sep_filters: dict[str, str] = {"date.gte": args.from_date} if args.from_date else {}

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    bad = set(datasets) - set(ALL_DATASETS)
    if bad:
        print(f"unknown dataset(s): {sorted(bad)}; valid: {ALL_DATASETS}", file=sys.stderr)
        return 2

    tickers = _parse_tickers(args)
    per_ticker = [d for d in ("sep", "actions", "sf1") if d in datasets]
    if per_ticker and not tickers:
        print(
            "no tickers given — SEP/ACTIONS/SF1 need an explicit --tickers/--tickers-file scope "
            "(a full-market pull would exceed the 1M/day rate limit). "
            "Use --datasets tickers to ingest only the reference table.",
            file=sys.stderr,
        )
        return 2

    try:
        provider = SharadarProvider()
    except SharadarConfigError as e:
        print(str(e), file=sys.stderr)
        return 1

    store = FactorDataStore(db_path=args.db)
    try:
        if "tickers" in datasets:
            _run(store, "tickers", lambda: store.ingest_tickers(provider.fetch_table("TICKERS", table="SEP")))

        if per_ticker:
            # per-dataset "already ingested" sets for --skip-existing resume across rate-limit
            # days. SEP/ACTIONS resume off `sep` (the original behavior); SF1 off `sf1_fundamentals`.
            existing: dict[str, set[str]] = {}
            if args.skip_existing:
                if "sep" in datasets or "actions" in datasets:
                    existing["sep"] = {
                        r[0] for r in store.con.execute("SELECT DISTINCT ticker FROM sep").fetchall()
                    }
                if "sf1" in datasets:
                    existing["sf1"] = {
                        r[0] for r in
                        store.con.execute("SELECT DISTINCT ticker FROM sf1_fundamentals").fetchall()
                    }
            # DEEPEN resume: a ticker is "deep enough" when its earliest SEP date is already <= --from.
            deep_enough: set[str] = set()
            if args.skip_deep_enough:
                if not args.from_date:
                    print("--skip-deep-enough requires --from", file=sys.stderr)
                    return 2
                target = datetime.fromisoformat(args.from_date).date()
                deep_enough = {
                    r[0] for r in store.con.execute(
                        "SELECT ticker, min(date) FROM sep GROUP BY ticker").fetchall()
                    if r[1] is not None and r[1] <= target
                }
            total = len(tickers)
            for i, tk in enumerate(tickers, 1):
                did: list[str] = []
                if "sep" in datasets:
                    if args.skip_existing and tk in existing.get("sep", set()):
                        did.append("sep=skip")
                    elif args.skip_deep_enough and tk in deep_enough:
                        did.append("sep=deep")
                    else:
                        _run(store, f"sep:{tk}", lambda tk=tk: store.ingest_sep(provider.fetch_table("SEP", ticker=tk, **sep_filters)), quiet=True)
                        did.append("sep")
                if "actions" in datasets:
                    if args.skip_existing and tk in existing.get("sep", set()):
                        did.append("actions=skip")
                    else:
                        _run(store, f"actions:{tk}", lambda tk=tk: store.ingest_actions(provider.fetch_table("ACTIONS", ticker=tk, **sep_filters)), quiet=True)
                        did.append("actions")
                if "sf1" in datasets:
                    if args.skip_existing and tk in existing.get("sf1", set()):
                        did.append("sf1=skip")
                    else:
                        # SF1 is per-ticker across all dimensions; no date filter (the tier floors
                        # at ~2016 anyway, ADR 0023), so a ticker's full fundamental history loads.
                        _run(store, f"sf1:{tk}", lambda tk=tk: store.ingest_sf1(provider.fetch_table("SF1", ticker=tk)), quiet=True)
                        did.append("sf1")
                print(f"[{i}/{total}] {tk}: {', '.join(did)}")

        print("\n--- store row counts ---")
        for t in ("sep", "tickers", "actions", "sf1_fundamentals"):
            print(f"  {t}: {store.row_count(t)}")
    finally:
        store.close()
        provider.close()
    return 0


def _run(store: FactorDataStore, dataset: str, fn, *, quiet: bool = False) -> None:
    started = datetime.now()
    try:
        rows = fn()
        store.record_ingest_run(dataset, started, datetime.now(), rows, "ok")
        if not quiet:
            print(f"  {dataset}: {rows} rows")
    except Exception as e:
        store.record_ingest_run(dataset, started, datetime.now(), 0, "failed")
        print(f"  {dataset}: FAILED {e!r}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
