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

ALL_DATASETS = ("tickers", "sep", "actions")


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
    args = ap.parse_args(argv)
    sep_filters: dict[str, str] = {"date.gte": args.from_date} if args.from_date else {}

    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    bad = set(datasets) - set(ALL_DATASETS)
    if bad:
        print(f"unknown dataset(s): {sorted(bad)}; valid: {ALL_DATASETS}", file=sys.stderr)
        return 2

    tickers = _parse_tickers(args)
    if ("sep" in datasets or "actions" in datasets) and not tickers:
        print(
            "no tickers given — SEP/ACTIONS need an explicit --tickers/--tickers-file scope "
            "(a full-market SEP pull would exceed the 1M/day rate limit). "
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

        if "sep" in datasets or "actions" in datasets:
            existing = set()
            if args.skip_existing:
                existing = {
                    r[0]
                    for r in store.con.execute("SELECT DISTINCT ticker FROM sep").fetchall()
                }
            total = len(tickers)
            for i, tk in enumerate(tickers, 1):
                if args.skip_existing and tk in existing:
                    print(f"[{i}/{total}] {tk}: skip (already in sep)")
                    continue
                if "sep" in datasets:
                    _run(store, f"sep:{tk}", lambda tk=tk: store.ingest_sep(provider.fetch_table("SEP", ticker=tk, **sep_filters)), quiet=True)
                if "actions" in datasets:
                    _run(store, f"actions:{tk}", lambda tk=tk: store.ingest_actions(provider.fetch_table("ACTIONS", ticker=tk, **sep_filters)), quiet=True)
                print(f"[{i}/{total}] {tk}: done")

        print("\n--- store row counts ---")
        for t in ("sep", "tickers", "actions"):
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
