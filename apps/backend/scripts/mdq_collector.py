"""MDQ-001 account-7 collector CLI (registration §7, Option 2A).

The only process that authenticates to Alpaca for MDQ acquisition. Runs on the
governed AWS host (the laptop is warm standby and must not acquire); Phase A is
REST-only — no websocket is ever armed by this script.

Subcommands:
    sample  --once | --until-close [--cadence 60]   paired IEX/SIP quote sampling
    eod     [--date YYYY-MM-DD]                     1-min session bars, both feeds
    freeze  [--date YYYY-MM-DD]                     hash + manifest both partitions
    verify  --date YYYY-MM-DD                       re-hash frozen partitions
    status                                          store overview

Typical box schedule (cron, ET): sample --until-close at 09:25 weekdays;
eod at 16:30; freeze at 16:45. All subordinate to the account-7 transition
executor — this collector is light by construction (2 REST calls/cycle).

    cd apps/backend && .venv/bin/python scripts/mdq_collector.py <cmd> ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time as time_mod
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.research.capture.collector import (  # noqa: E402
    CAPTURE_MODE_EOD_BARS,
    CAPTURE_MODE_SAMPLER,
    PHASE_A_UNIVERSE,
    fetch_session_bars,
    sample_quotes_cycle,
)
from app.research.capture.identity import AcquisitionPins, verify_identity  # noqa: E402
from app.research.capture.store import CaptureStore, PartitionRef  # noqa: E402

DEFAULT_ROOT = _BACKEND / "mdq_capture"


def _bootstrap_client(pins: AcquisitionPins):
    try:
        import truststore

        truststore.inject_into_ssl()  # ADR 0017
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"warning: truststore unavailable ({exc})")

    from dotenv import load_dotenv

    load_dotenv(_BACKEND.parent.parent / ".env")
    key = os.environ.get(pins.cred_env_key)
    sec = os.environ.get(pins.cred_env_secret)
    if not (key and sec):
        raise SystemExit(f"acquisition creds absent ({pins.cred_env_key} / _SECRET)")

    account = verify_identity(key, sec, pins)  # fail-closed fingerprint + broker latch
    print(f"acquisition identity verified: account {account}, fp {pins.key_fingerprint}")

    from alpaca.data.historical import StockHistoricalDataClient

    return StockHistoricalDataClient(key, sec)


def _universe(args: argparse.Namespace) -> tuple[str, ...]:
    if args.universe_file:
        symbols = json.loads(Path(args.universe_file).read_text(encoding="utf-8"))
        return tuple(str(s).upper() for s in symbols)
    return PHASE_A_UNIVERSE


def _universe_sha(universe: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(sorted(universe)).encode()).hexdigest()


def _session_close_utc(session: date) -> datetime | None:
    """NYSE close for the session (authoritative half-day source), or None if
    not a trading day."""
    import pandas_market_calendars as mcal

    sched = mcal.get_calendar("NYSE").schedule(start_date=session, end_date=session)
    if sched.empty:
        return None
    return sched["market_close"].iloc[0].to_pydatetime().astimezone(UTC)


def cmd_sample(args: argparse.Namespace) -> int:
    pins = AcquisitionPins()
    store = CaptureStore(Path(args.root))
    universe = _universe(args)
    today = datetime.now(UTC).date()
    close = _session_close_utc(today)
    if close is None:
        print(f"{today} is not a trading session; nothing to sample")
        return 0
    client = _bootstrap_client(pins)
    cycles = 0
    consecutive_failures = 0
    while True:
        recs = sample_quotes_cycle(client, universe)
        for feed, records in recs.items():
            store.append_jsonl(PartitionRef(feed=feed, session=today), "quotes", records)
        cycles += 1
        # Frozen retry policy (registration §8): continue on transient failure,
        # abort only on sustained failure so a dead network doesn't spin all day.
        if all(len(r) == 1 and "feed_error" in r[0] for r in recs.values()):
            consecutive_failures += 1
            if consecutive_failures >= args.max_consecutive_failures:
                print(
                    f"aborting after {consecutive_failures} consecutive fully-failed "
                    f"cycles (~{consecutive_failures * args.cadence}s of outage)"
                )
                return 1
        else:
            consecutive_failures = 0
        if args.once or (args.max_cycles and cycles >= args.max_cycles):
            break
        if datetime.now(UTC) >= close:
            break
        time_mod.sleep(args.cadence)
    print(f"sampled {cycles} cycle(s) x {len(universe)} symbols x 2 feeds")
    return 0


def cmd_eod(args: argparse.Namespace) -> int:
    pins = AcquisitionPins()
    store = CaptureStore(Path(args.root))
    universe = _universe(args)
    session = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    if _session_close_utc(session) is None:
        print(f"{session} is not a trading session; no bars to capture")
        return 0
    client = _bootstrap_client(pins)
    for feed in ("iex", "sip"):
        df = fetch_session_bars(client, universe, session, feed)
        store.write_parquet(PartitionRef(feed=feed, session=session), "bars", "bars_1min", df)
        print(f"{feed}: wrote {len(df)} 1-min bar rows for {session}")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    import alpaca

    pins = AcquisitionPins()
    store = CaptureStore(Path(args.root))
    universe = _universe(args)
    session = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    for feed in ("iex", "sip"):
        ref = PartitionRef(feed=feed, session=session)
        if store.is_frozen(ref):
            print(f"{feed}/{session}: already frozen")
            continue
        pdir = store.partition_dir(ref)
        modes = [
            m
            for m, kind in ((CAPTURE_MODE_SAMPLER, "quotes"), (CAPTURE_MODE_EOD_BARS, "bars"))
            if (pdir / kind).exists()
        ]
        mpath = store.freeze(
            ref,
            provenance={
                # PRE_REGISTRATION_SMOKE quarantines a capture from the governed
                # K1–K6 corpus (registration §4: thresholds freeze BEFORE data
                # collection; pre-registration observations are engineering
                # evidence only).
                **({"label": args.label} if args.label else {}),
                "provider": "alpaca",
                "entitlement": "algo_trader_plus (account-7 login)",
                "credential_fingerprint": pins.key_fingerprint,
                "account_number": pins.account_number,
                "alpaca_py_version": getattr(alpaca, "__version__", "unknown"),
                "capture_modes": modes,
                "universe": sorted(universe),
                "universe_sha256": _universe_sha(universe),
            },
        )
        print(f"{feed}/{session}: frozen -> {mpath}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    store = CaptureStore(Path(args.root))
    session = date.fromisoformat(args.date)
    rc = 0
    for feed in ("iex", "sip"):
        problems = store.verify(PartitionRef(feed=feed, session=session))
        if problems:
            rc = 1
            print(f"{feed}/{session}: FAILED")
            for p in problems:
                print(f"  {p}")
        else:
            print(f"{feed}/{session}: verified")
    return rc


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.exists():
        print(f"no capture store at {root}")
        return 0
    store = CaptureStore(root)
    for feed_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for day_dir in sorted(p for p in feed_dir.iterdir() if p.is_dir()):
            ref = PartitionRef(feed=feed_dir.name, session=date.fromisoformat(day_dir.name))
            state = "FROZEN" if store.is_frozen(ref) else "open"
            n = sum(1 for f in day_dir.rglob("*") if f.is_file() and f.name != "manifest.json")
            print(f"{feed_dir.name}/{day_dir.name}: {state}, {n} file(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        default=os.environ.get("WORKBENCH_MDQ_CAPTURE_ROOT", str(DEFAULT_ROOT)),
        help="capture store root (persistent volume on the box)",
    )
    ap.add_argument("--universe-file", help="JSON list of symbols (frozen §8 universe)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sample", help="paired IEX/SIP quote sampling")
    p.add_argument("--once", action="store_true")
    p.add_argument("--until-close", action="store_true")
    p.add_argument("--cadence", type=int, default=60, help="seconds between cycles")
    p.add_argument("--max-cycles", type=int, default=0)
    p.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=30,
        help="abort after this many fully-failed cycles (frozen retry policy)",
    )
    p.set_defaults(fn=cmd_sample)

    p = sub.add_parser("eod", help="end-of-session 1-min bars, both feeds")
    p.add_argument("--date")
    p.set_defaults(fn=cmd_eod)

    p = sub.add_parser("freeze", help="hash + write manifests for both feeds")
    p.add_argument("--date")
    p.add_argument(
        "--label",
        help="provenance label; use PRE_REGISTRATION_SMOKE for any capture made "
        "before MDQ-001 registration sign-off (quarantined from K1-K6)",
    )
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("verify", help="re-hash frozen partitions")
    p.add_argument("--date", required=True)
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("status", help="store overview")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
