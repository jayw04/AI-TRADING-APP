"""MDQ-001 account-7 collector CLI (registration §7, Option 2A).

The only process that authenticates to Alpaca for MDQ acquisition. Runs on the
governed AWS host (the laptop is warm standby and must not acquire); Phase A is
REST-only — no websocket is ever armed by this script.

Subcommands:
    sample  --once | --until-close [--cadence 60]   paired IEX/SIP quote sampling
    eod     [--date YYYY-MM-DD]                     1-min session bars, both feeds
    freeze  [--date YYYY-MM-DD]                     hash + manifest both partitions
    verify  --date YYYY-MM-DD                       re-hash frozen partitions
    admissibility --date YYYY-MM-DD [--json]        registration §4 / plan §7.1
    status                                          store overview

``verify`` proves INTEGRITY (the bytes are the frozen bytes). ``admissibility``
proves SUFFICIENCY as well — the full registration §4 "Admissible corpus" /
plan §7.1 condition set, including the frozen completeness thresholds. It is
offline and STRICTLY READ-ONLY: it never writes, moves or mutates anything under
the capture root, and there is deliberately no repair affordance. Exit code
0 = ADMISSIBLE, 1 = NOT ADMISSIBLE (a condition FAILed), 2 = UNDETERMINED (a
condition was NOT EVALUABLE) — 1 and 2 are both "not admissible".

Typical box schedule (cron, ET): sample --until-close at 09:25 weekdays;
eod at 16:30; freeze at 16:45. All subordinate to the account-7 transition
executor — this collector is light by construction (2 REST calls/cycle).

``sample`` runs on the frozen slot grid (09:25 ET inclusive -> official NYSE
close exclusive, 60 s cadence => 395 slots on a normal close, 215 on a 13:00
half day) and schedules FIXED-RATE against each slot's absolute deadline. It
never bursts to catch up: a slot consumed by an overrunning cycle stays missed
and counts against completeness.

    cd apps/backend && .venv/bin/python scripts/mdq_collector.py <cmd> ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.research.capture.admissibility import ET as _ET  # noqa: E402
from app.research.capture.collector import (  # noqa: E402
    CAPTURE_MODE_EOD_BARS,
    CAPTURE_MODE_SAMPLER,
    PHASE_A_UNIVERSE,
    SlotGrid,
    SlotStamp,
    fetch_session_bars,
    iter_scheduled_slots,
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
    """Paired IEX/SIP quote sampling on the frozen slot grid.

    Scheduling is FIXED-RATE against the grid's absolute deadlines (owner ruling
    2026-08-18), not ``sleep(cadence)`` after the work: fixed-delay sleeping
    makes the true start-to-start interval ``cadence + per-cycle work``, so a
    capture with zero outages drifts below the 98% completeness floor once
    per-cycle work exceeds ~1.24 s. The floor and the 10-minute gap rule are
    ratified; the scheduler was the defect. There is no catch-up burst — a slot
    consumed by an overrunning cycle stays missed and counts against
    completeness.
    """
    pins = AcquisitionPins()
    store = CaptureStore(Path(args.root))
    universe = _universe(args)
    today = datetime.now(UTC).date()
    close = _session_close_utc(today)
    if close is None:
        print(f"{today} is not a trading session; nothing to sample")
        return 0
    grid = SlotGrid.for_session(today, close, cadence_seconds=args.cadence)
    client = _bootstrap_client(pins)
    print(
        f"slot grid {today}: {grid.start.astimezone(_ET):%H:%M:%S} ET -> "
        f"{grid.end.astimezone(_ET):%H:%M:%S} ET (exclusive), cadence "
        f"{grid.cadence_seconds}s, expected_cycles={grid.expected_cycles}"
    )

    cycles = 0
    consecutive_failures = 0

    def run_cycle(slot: SlotStamp) -> bool:
        """One scheduled cycle. Returns False to abort (sustained failure)."""
        nonlocal cycles, consecutive_failures
        recs = sample_quotes_cycle(client, universe, slot=slot)
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
                return False
        else:
            consecutive_failures = 0
        return True

    if args.once:
        # Deliberate one-shot probe: it fires now, on whichever slot the current
        # minute belongs to, and is NOT close-gated (a smoke check after the bell
        # must still be able to prove the credential and the write path). Off-grid
        # slots are stamped honestly so the checker can exclude them.
        slot = grid.stamp(grid.slot_index_at(datetime.now(UTC)))
        if not grid.contains(slot.index):
            print(
                f"warning: --once fired outside the {today} slot grid "
                f"(slot {slot.index}, grid is 0..{grid.expected_cycles - 1}); "
                f"this cycle is off-grid and does not count toward completeness"
            )
        ok = run_cycle(slot)
        print(f"sampled {cycles} cycle(s) x {len(universe)} symbols x 2 feeds (--once)")
        return 0 if ok else 1

    def slots_missed(first: int, resumed: int) -> None:
        print(
            f"warning: cycle overran its slot; slots {first}..{resumed - 1} missed "
            f"({resumed - first} slot(s), no catch-up burst by design)"
        )

    for slot in iter_scheduled_slots(
        grid, max_cycles=args.max_cycles, on_slots_missed=slots_missed
    ):
        if not run_cycle(slot):
            return 1
    print(
        f"sampled {cycles} cycle(s) x {len(universe)} symbols x 2 feeds "
        f"({cycles}/{grid.expected_cycles} scheduled slots)"
    )
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


def cmd_admissibility(args: argparse.Namespace) -> int:
    """Adjudicate a session's partitions against registration §4 / plan §7.1.

    Offline and strictly read-only — no Alpaca client is constructed, no
    credential is read, nothing under ``--root`` is written. The NYSE close is
    resolved from the same market calendar the sampler itself stops on; when it
    cannot be resolved the cycle-count conditions are reported NOT EVALUABLE
    rather than guessed.
    """
    from app.research.capture.admissibility import (
        Denominator,
        assess_partition,
        load_frozen_universe,
        render_json,
        render_text,
    )

    session = date.fromisoformat(args.date)
    close: datetime | None
    if args.session_close:
        close = datetime.strptime(f"{args.date} {args.session_close}", "%Y-%m-%d %H:%M").replace(
            tzinfo=_ET
        )
    else:
        try:
            close = _session_close_utc(session)
        except Exception as exc:  # noqa: BLE001 - reported, never guessed around
            print(f"warning: NYSE calendar unavailable ({exc}); cycle counts NOT EVALUABLE")
            close = None

    universe_path = Path(args.universe_file) if args.universe_file else None
    report = assess_partition(
        Path(args.root),
        session,
        session_close_utc=close,
        frozen_universe=load_frozen_universe(universe_path),
        sampler_start_et=datetime.strptime(args.sampler_start, "%H:%M").time(),
        approved_collector_versions=tuple(args.approved_collector_version or ()),
        governing_denominator=Denominator(args.denominator) if args.denominator else None,
        denominator_ruling=args.denominator_ruling,
    )
    print(render_json(report) if args.json else render_text(report))
    return report.exit_code


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

    p = sub.add_parser("sample", help="paired IEX/SIP quote sampling on the slot grid")
    p.add_argument(
        "--once",
        action="store_true",
        help="one immediate cycle on the current slot, then exit (manual probe; "
        "not close-gated, and off-grid cycles are stamped as such)",
    )
    p.add_argument(
        "--until-close",
        action="store_true",
        help="run every scheduled slot until the NYSE close (the default behaviour)",
    )
    p.add_argument(
        "--cadence",
        type=int,
        default=60,
        help="slot spacing in seconds; the grid is anchored at 09:25 ET and the "
        "schedule is fixed-rate against absolute deadlines, so this IS the "
        "start-to-start interval, not a post-cycle sleep",
    )
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

    p = sub.add_parser(
        "admissibility",
        help="registration §4 / plan §7.1 corpus adjudication (offline, read-only)",
    )
    p.add_argument("--date", required=True)
    p.add_argument("--json", action="store_true", help="machine-readable record")
    p.add_argument(
        "--session-close",
        help="NYSE close as HH:MM ET; default resolves it from the market calendar "
        "(pass it explicitly for a half day if the calendar is unavailable)",
    )
    p.add_argument(
        "--sampler-start",
        default="09:25",
        help="first scheduled sampling cycle, HH:MM ET (deployment fact: the "
        "mdq-sample systemd timer; NOT frozen in the registration)",
    )
    p.add_argument(
        "--approved-collector-version",
        action="append",
        help="collector version approved for the period; repeatable. Without it "
        "the collector-code-identity condition is NOT EVALUABLE (no approved "
        "identity is frozen in any governing document yet)",
    )
    p.add_argument(
        "--denominator",
        choices=["sampler_window", "census_window"],
        help="session_scope binding expected_cycles. RULED 2026-08-18: "
        "'sampler_window' — 09:25 ET (inclusive) to the official NYSE close "
        "(exclusive), cadence 60s, expected_cycles = ceil(span / cadence) => 395 "
        "on a normal close, 215 on a 13:00 early close, 0 on a non-session. The "
        "04:00-16:00 ET window is the BAR census scope and is NOT the sampler "
        "denominator; requesting 'census_window' is reinterpreted as a labelled "
        "DIAGNOSTIC and is never scored. The 98%% floor and 10-min gap rule are "
        "unchanged. Omit the flag and the completeness and gap conditions return "
        "NOT EVALUABLE — the ruling must be cited, not assumed.",
    )
    p.add_argument(
        "--denominator-ruling",
        help="citation for the --denominator ruling (who ruled, when, where it is "
        "recorded); copied verbatim into the JSON record",
    )
    p.set_defaults(fn=cmd_admissibility)

    p = sub.add_parser("status", help="store overview")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
