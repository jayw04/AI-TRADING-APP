"""INSIDER-001 §1 — resumable Form 4 EDGAR ingestion launcher (read-only / off the order path).

The original §2 pull ran ad-hoc in a terminal and was lost when that terminal died at ~34/134
names. This is the committed, **resumable, death-tolerant** replacement (mirrors the SEP
``ingest_full_history_resume.bat`` discipline):

- iterates the 134-name universe **one issuer at a time**;
- after each issuer, **commits + checkpoints the DuckDB WAL** (close) and appends the ticker to
  the done-file — so a crash loses at most the single in-flight issuer, and a re-run skips
  everything already done (the upsert is idempotent on ``event_id`` anyway);
- fail-soft per issuer: a network/parse failure on one name is logged and skipped, never fatal,
  and the name is **not** marked done so the next run retries it.

EDGAR fair-access (ADR 0027): a descriptive User-Agent is mandatory (``SEC_EDGAR_USER_AGENT`` or
``--user-agent``); empty disables the client. OS-trust-store TLS is enabled first so Norton's SSL
inspection doesn't break the fetch (ADR 0017).

Usage (from apps/backend, venv active):
    SEC_EDGAR_USER_AGENT="GlobalComplyAI TradingWorkbench jay.w0416@gmail.com" \
        python scripts/ingest_form4_resume.py
    python scripts/ingest_form4_resume.py --limit 10   # pull only the next 10 remaining names
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.altdata.events.store import EventStore
from app.altdata.sec.cik_map import load_cik_map
from app.altdata.sec.client import EdgarClient
from app.altdata.sec.ingest import ingest_form4
from app.utils.tls_trust import enable_os_trust_store

# A sensible fair-access default if the env var is unset (the owner's contact, per the §2 recipe).
_DEFAULT_UA = "GlobalComplyAI TradingWorkbench jay.w0416@gmail.com"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Resumable Form 4 EDGAR ingestion (INSIDER-001 §1)")
    p.add_argument("--universe-file", default="data/insider_134_universe.txt",
                   help="One ticker per line — the 134-name sibling survivor set.")
    p.add_argument("--events-db", default="data/insider_events.duckdb",
                   help="PIT corporate-event store to write (DuckDB).")
    p.add_argument("--done-file", default="data/insider_pull_done.txt",
                   help="Append-only progress tracker; names here are skipped on resume.")
    p.add_argument("--since", default="2016-01-01",
                   help="Ingest Form 4 filings filed on/after this ISO date (matches the "
                        "existing partial pull — keep the universe consistent).")
    p.add_argument("--user-agent", default=os.environ.get("SEC_EDGAR_USER_AGENT") or _DEFAULT_UA,
                   help="SEC fair-access User-Agent. Defaults to $SEC_EDGAR_USER_AGENT.")
    p.add_argument("--limit", type=int, default=None,
                   help="Process at most this many remaining names this run (default: all).")
    return p.parse_args()


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip().upper() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _mark_done(done_path: Path, ticker: str) -> None:
    with done_path.open("a", encoding="utf-8") as fh:
        fh.write(ticker + "\n")


def main() -> int:
    args = _parse_args()
    enable_os_trust_store()  # ADR 0017 — OS trust store before the first HTTPS connection

    backend_root = Path(__file__).resolve().parents[1]
    universe_path = (backend_root / args.universe_file).resolve()
    done_path = (backend_root / args.done_file).resolve()

    universe = _read_lines(universe_path)
    if not universe:
        raise SystemExit(f"empty/missing universe file: {universe_path}")
    done = set(_read_lines(done_path))
    remaining = [t for t in universe if t not in done]
    if args.limit is not None:
        remaining = remaining[: args.limit]

    print(f"universe {len(universe)} | already done {len(done)} | to pull this run "
          f"{len(remaining)} | since {args.since}", flush=True)
    if not remaining:
        print("nothing remaining — universe fully pulled.", flush=True)
        return 0

    # One CIK map + one throttled client for the whole run (the map fetch is the costly part).
    client = EdgarClient(user_agent=args.user_agent)
    try:
        cmap = load_cik_map(client)
        total_events = 0
        for i, ticker in enumerate(remaining, start=1):
            tag = f"[{len(done) + i}/{len(universe)}] {ticker}"
            try:
                store = EventStore(args.events_db, read_only=False)
                try:
                    rep = ingest_form4(client, store, [ticker], since=args.since, cik_map=cmap)
                finally:
                    store.close()  # commit + WAL checkpoint -> durable before we mark done
            except Exception as exc:  # noqa: BLE001 — one bad issuer must not kill the run
                print(f"{tag}: ERROR {type(exc).__name__}: {exc} — left for retry", flush=True)
                continue

            total_events += rep.events_ingested
            _mark_done(done_path, ticker)
            unresolved = "unresolved" if rep.unresolved_tickers else "resolved"
            print(f"{tag}: {unresolved} | filings={rep.form4_filings_seen} "
                  f"amend={rep.amendments_seen} events+={rep.events_ingested} "
                  f"fails={rep.fetch_failures}", flush=True)

        # Final coverage snapshot
        with EventStore(args.events_db, read_only=True) as store:
            cov = store.coverage()
        print(f"DONE this run: +{total_events} events | store now {cov['n_events']} events, "
              f"{cov['distinct_tickers']} distinct issuers, "
              f"{cov['first_filed']} → {cov['last_filed']}", flush=True)
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
