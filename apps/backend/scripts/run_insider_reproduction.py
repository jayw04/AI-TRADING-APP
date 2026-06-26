"""INSIDER-001 §4 — end-to-end independent-reproduction driver (owner OQ1).

Wires the four committed §4 components into a single read-only run and emits the evidence
package (plan §4; EvidenceEngineering Methodology v1.2, verdict-as-data per ADR 0026):

    EventStore (Form 4, PIT)  ->  conviction_hits (§3 faithful subset)
        ->  run_insider_reproduction (de-overlapped Event-Study Engine + declared verdict tree)
        ->  render_evidence  ->  docs/implementation/evidence/insider_001_s4_reproduction/

This driver is **off the order path** (ADR 0019, Research Engine — read-only): it opens both
DuckDB stores ``read_only=True`` and never imports the broker / risk / router stack.

PRE-REGISTRATION DISCIPLINE. The verdict is pre-registered (plan §2) and must be computed
**once, on the complete pull**. While the Form 4 ingestion is still in flight (fewer than the
134 target issuers present), this driver stamps the evidence file **INTERIM** and refuses to
mark it as the registered verdict — an interim run validates the pipeline and gives an early
read; it is not the gate result. Pass ``--final`` only when coverage is complete.

Usage (from apps/backend, with the venv active):
    python scripts/run_insider_reproduction.py                     # interim run, today as-of
    python scripts/run_insider_reproduction.py --universe-file data/insider_134.txt --final
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from app.altdata.events.store import EventStore
from app.altdata.insider_program import render_evidence, run_insider_reproduction
from app.altdata.signal import conviction_hits
from app.factor_data.store import FactorDataStore

# The pre-registered first universe (plan §8 OQ resolution: "134-name first"). Coverage below
# this many distinct issuers means the Form 4 pull is still in flight -> INTERIM only.
TARGET_ISSUERS = 134

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_EVIDENCE_DIR = (
    _BACKEND_ROOT.parents[1] / "docs" / "implementation" / "evidence"
    / "insider_001_s4_reproduction"
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="INSIDER-001 §4 reproduction driver")
    p.add_argument("--events-db", default="data/insider_events.duckdb",
                   help="PIT corporate-event store (Form 4).")
    p.add_argument("--prices-db", default="data/factor_data_full.duckdb",
                   help="Survivorship-free SEP price store for the study + benchmark.")
    p.add_argument("--asof", default=None,
                   help="Point-in-time as-of date (ISO). Default: today. Only events filed "
                        "on/before this date are read (no look-ahead).")
    p.add_argument("--universe-file", default=None,
                   help="One ticker per line = the equal-weight benchmark basket (H1). "
                        "Default: the distinct issuers present in the event store.")
    p.add_argument("--done-file", default="data/insider_pull_done.txt",
                   help="The pull's progress tracker. Completeness for --final = every "
                        "--universe-file name appears here (pull processed all of them). Issuer "
                        "count can't measure this — unresolved/zero-buy names never get events.")
    p.add_argument("--hold-days", type=int, default=90,
                   help="Holding horizon in trading days (runner default 90 — NOT re-tuned).")
    p.add_argument("--n-resamples", type=int, default=2000,
                   help="Bootstrap resamples for the Sharpe-diff CI.")
    p.add_argument("--final", action="store_true",
                   help="Assert coverage is complete and write the registered (non-INTERIM) "
                        "evidence package. Refuses if fewer than the target issuers are present.")
    p.add_argument("--no-write", action="store_true",
                   help="Print the evidence package but do not write a file.")
    return p.parse_args()


def _load_universe(path: str | None, fallback: list[str]) -> list[str]:
    if path is None:
        return fallback
    raw = Path(path).read_text(encoding="utf-8").splitlines()
    names = sorted({ln.strip().upper() for ln in raw if ln.strip()})
    return names


def main() -> int:
    args = _parse_args()
    as_of = date.fromisoformat(args.asof) if args.asof else date.today()

    # 1) PIT read of the Form 4 event store -----------------------------------------------
    with EventStore(args.events_db, read_only=True) as events_store:
        coverage = events_store.coverage()
        events = events_store.events_asof(as_of, event_type="insider_buy")

    distinct_issuers = coverage["distinct_tickers"]

    # Completeness = the pull PROCESSED every universe name (done-file ⊇ universe). The distinct
    # issuer count can't measure this: unresolved-CIK names and zero-buy names never produce an
    # event, so issuer count saturates well below the universe size even on a complete pull.
    if args.universe_file:
        want = {ln.strip().upper() for ln in
                Path(args.universe_file).read_text(encoding="utf-8").splitlines() if ln.strip()}
        done = set()
        done_path = Path(args.done_file)
        if done_path.exists():
            done = {ln.strip().upper() for ln in
                    done_path.read_text(encoding="utf-8").splitlines() if ln.strip()}
        unprocessed = sorted(want - done)
        complete = not unprocessed
    else:
        # No declared universe -> fall back to the issuer-count heuristic.
        unprocessed = []
        complete = distinct_issuers >= TARGET_ISSUERS
    interim = not complete

    if args.final and not complete:
        detail = (f"{len(unprocessed)} universe name(s) not yet in {args.done_file}: "
                  f"{', '.join(unprocessed[:20])}{' …' if len(unprocessed) > 20 else ''}"
                  if args.universe_file else
                  f"only {distinct_issuers}/{TARGET_ISSUERS} issuers and no --universe-file given")
        raise SystemExit(
            f"--final refused: the Form 4 pull is not complete — {detail}. "
            f"Finish the pull (scripts/ingest_form4_resume.py) before the registered verdict, "
            f"or drop --final for an interim run."
        )

    # 2) Signal construction (faithful subset, §3) ----------------------------------------
    hits = conviction_hits(events)
    if not hits:
        raise SystemExit("No conviction hits constructed from the event store — nothing to study.")

    event_tickers = sorted({h.ticker for h in hits})
    universe = _load_universe(args.universe_file, event_tickers)
    start = min(h.entry_date for h in hits)
    end = as_of

    # 3) De-overlapped event study + declared verdict -------------------------------------
    with FactorDataStore(args.prices_db, read_only=True) as prices:
        repro = run_insider_reproduction(
            hits, prices, universe=universe, start=start, end=end,
            hold_trading_days=args.hold_days, n_resamples=args.n_resamples,
        )

    # 4) Evidence package ------------------------------------------------------------------
    banner = []
    if interim:
        banner = [
            "> ⚠️ **INTERIM — NOT THE PRE-REGISTERED VERDICT.**",
            f"> Form 4 coverage is {distinct_issuers}/{TARGET_ISSUERS} target issuers "
            f"({coverage['first_filed']} → {coverage['last_filed']}, {coverage['n_events']} events). "
            "The registered gate result must be computed once, on the complete pull (`--final`).",
            "",
        ]
    body = render_evidence(repro)
    doc = "\n".join(banner) + body + "\n" + _provenance(args, coverage, universe, as_of)

    print(doc)

    if not args.no_write:
        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        tag = "FINAL" if complete else "INTERIM"
        out = _EVIDENCE_DIR / f"REPRODUCTION_{as_of.isoformat()}_{tag}.md"
        out.write_text(doc, encoding="utf-8")
        print(f"\n[written] {out}")

    return 0


def _provenance(args: argparse.Namespace, coverage: dict, universe: list[str], as_of: date) -> str:
    return "\n".join([
        "",
        "---",
        "### Provenance",
        f"- **As-of (PIT):** {as_of.isoformat()} — only Form 4 events filed on/before this date.",
        f"- **Event store:** `{args.events_db}` — {coverage['n_events']} events, "
        f"{coverage['distinct_tickers']} distinct issuers, "
        f"{coverage['first_filed']} → {coverage['last_filed']}.",
        f"- **Price store:** `{args.prices_db}` (survivorship-free SEP, split/div-adjusted).",
        f"- **Benchmark universe (H1):** {len(universe)} names "
        f"({'from --universe-file' if args.universe_file else 'distinct event issuers'}).",
        f"- **Hold:** {args.hold_days} trading days; bootstrap resamples {args.n_resamples}.",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
