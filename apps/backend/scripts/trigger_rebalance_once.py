"""LOCAL-ONLY helper: fire one momentum-portfolio rebalance now, then revert.

NOT committed. Drives the authenticated HTTP API to:
  trigger:  stop -> PUT (params + dispatch timeframe=1Day, schedule fires in ~2 min) -> start
  revert:   stop -> PUT (params + timeframe=1Day, schedule="0 14 * * mon") -> start

Why timeframe=1Day: the engine dispatch uses params["timeframe"] (default "1Min");
the strategy needs daily bars, so daily dispatch makes on_bar fire reliably.
Why "0 14 * * mon": APScheduler from_crontab reads dow 0=Mon and does NOT remap
cron's 1=Mon, so "0 14 * * 1" fires TUESDAY. "mon" is unambiguous.

Usage:
  .venv/Scripts/python.exe scripts/trigger_rebalance_once.py --mode trigger \
     --email <e> --password <p> --totp-secret <b32> --id 2
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pyotp

# Full params for strategy id=2 (PUT replaces params_json wholesale, so send all),
# plus the dispatch-timeframe fix.
PARAMS = {
    "max_names": 5,
    "max_position_pct": 0.20,
    "top_quantile": 0.20,
    "min_score": 0.0,
    "cash_buffer_pct": 0.02,
    "use_market_regime_filter": True,
    "market_filter_symbol": "SPY",
    "pricing_timeframe": "1Day",
    "initial_equity_estimate": 10000,
    "timeframe": "1Day",  # engine _dispatch_bar_tick fetches THIS tf to fire on_bar
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--totp-secret", required=True)
    ap.add_argument("--id", type=int, default=2)
    ap.add_argument("--mode", choices=["trigger", "revert"], required=True)
    args = ap.parse_args(argv)

    if args.mode == "trigger":
        fire = datetime.now(UTC) + timedelta(minutes=2)
        schedule = f"{fire.minute} {fire.hour} * * *"
        when = f"~{fire:%H:%M} UTC today (one-shot)"
    else:
        schedule = "0 14 * * mon"
        when = "weekly Monday 14:00 UTC"

    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as c:
        r = c.post("/api/v1/auth/login", json={
            "email": args.email, "password": args.password,
            "totp_code": pyotp.TOTP(args.totp_secret).now(),
        })
        if r.status_code != 200:
            print(f"login failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        print("logged in")

        # stop -> IDLE (PUT requires IDLE)
        r = c.post(f"/api/v1/strategies/{args.id}/stop")
        print(f"stop: {r.status_code} {r.json() if r.status_code == 200 else r.text[:200]}")

        # update schedule + params
        r = c.put(f"/api/v1/strategies/{args.id}",
                  json={"schedule": schedule, "params": PARAMS})
        if r.status_code != 200:
            print(f"update failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        print(f"updated: schedule={schedule!r} ({when})")

        # start -> PAPER (re-registers the cron)
        r = c.post(f"/api/v1/strategies/{args.id}/start")
        if r.status_code != 200:
            print(f"start failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        body = r.json()
        print(f"started: status={body.get('new_status')} run_id={body.get('run_id')}")
        if body.get("new_status") != "paper":
            print("⚠ not paper — check engine logs", file=sys.stderr)
            return 1

    print(f"\nOK ({args.mode}): id={args.id} schedule set to {when}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
