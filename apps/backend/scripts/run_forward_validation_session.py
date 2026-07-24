#!/usr/bin/env python3
"""Run ONE forward-validation session (R4 scheduler entry point).

This is what a daily timer on the shadow validation runtime invokes. It is NON-ORDERING and never
touches Account 4: it drives the frozen production instrument's decision into the non-ordering shadow
ledger and commits at most one observation per eligible session.

Deliberately NOT an APScheduler job inside the trading engine. The engine process owns live accounts;
the forward validation must be able to stop, fail and be re-run without any interaction with live
dispatch. Running it as a separate, idempotent, once-a-day process is what makes "re-run it" a safe
operational instruction.

Idempotent by construction: an ineligible date is a no-op, an already-recorded session is a no-op, and
every failure is an integrity stop that writes nothing to the record. Firing it twice — or catching up
after a missed timer — cannot double-book a session.

    python scripts/run_forward_validation_session.py \
        --store-dir /var/lib/forward-validation \
        --ledger-path /var/lib/forward-validation/ledger.json \
        --provider <registered-provider> [--session-date YYYY-MM-DD]

Exit codes:
    0  RECORDED / ALREADY_RECORDED / NOT_ELIGIBLE  (the scheduler has nothing to do)
    1  INTEGRITY_STOP — a permitted stop; the exception is recorded, nothing was written
    2  configuration refusal or an unexpected error — the run never reached the record

⚠ No production decision provider is registered yet. Wiring the real `capture_seam` provider (scores,
regime and prices from the registered sources, plus the deployment blob) is R5; until then this script
REFUSES to run rather than inventing a decision source.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.forward_session_runner import (  # noqa: E402
    ForwardSessionRunner,
    SessionRunStatus,
)
from app.validation.forward_window import GOVERNING_TZ, IntegrityStop  # noqa: E402

# name -> factory building a fully wired runner. R5 registers the production, data-coupled provider;
# an empty registry is the honest current state, not an oversight.
PROVIDER_FACTORIES: dict[str, Callable[[argparse.Namespace], ForwardSessionRunner]] = {}


def _governing_today() -> date:
    """Today's session date in the governing timezone (§0: America/New_York)."""
    return datetime.now(ZoneInfo(GOVERNING_TZ)).date()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run one forward-validation session (R4).")
    ap.add_argument("--store-dir", required=True, type=Path,
                    help="the observation store (committed record + stop log)")
    ap.add_argument("--ledger-path", required=True, type=Path,
                    help="the durable non-ordering shadow ledger")
    ap.add_argument("--provider", required=True,
                    help="registered decision provider — the production one is wired in R5")
    ap.add_argument("--session-date", type=date.fromisoformat, default=None,
                    help=f"session to run (default: today in {GOVERNING_TZ})")
    args = ap.parse_args(argv)

    session = args.session_date or _governing_today()
    run_timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    factory = PROVIDER_FACTORIES.get(args.provider)
    if factory is None:
        known = sorted(PROVIDER_FACTORIES) or ["<none registered>"]
        print(json.dumps({
            "status": "REFUSED",
            "reason": f"no decision provider named {args.provider!r} is registered",
            "registered_providers": known,
            "detail": "the production capture_seam provider is wired in R5; this runner will not "
                      "fabricate a decision source",
        }, indent=2))
        return 2

    try:
        runner = factory(args)
        result = runner.run_session(session, run_timestamp=run_timestamp)
    except IntegrityStop as exc:                    # a stop raised before the runner could record it
        print(json.dumps({"status": "INTEGRITY_STOP", "session_date": session.isoformat(),
                          "detail": str(exc)}, indent=2))
        return 1
    except Exception as exc:                        # noqa: BLE001 - the entry point reports, never hides
        print(json.dumps({"status": "ERROR", "session_date": session.isoformat(),
                          "detail": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2

    print(json.dumps({
        "status": str(result.status), "session_date": result.session_date,
        "session_count": result.session_count, "sequence": result.sequence,
        "exception_code": result.exception_code, "detail": result.detail,
        "operational_exceptions": list(result.operational_exceptions),
        "run_timestamp": run_timestamp,
    }, indent=2))
    return 1 if result.status is SessionRunStatus.INTEGRITY_STOP else 0


if __name__ == "__main__":
    raise SystemExit(main())
