"""LOCAL-ONLY helper: fire one rebalance now for ANY strategy/owner, then revert.

Generalization of trigger_rebalance_once.py (which hard-codes id=2's params).
Fetches the strategy's *current* params via the API, ensures timeframe=1Day +
pricing_timeframe=1Day (the engine _dispatch_bar_tick fetches params["timeframe"]
to fire on_bar; momentum needs daily bars), and drives:

  trigger:  login(owner) -> stop -> PUT(params + schedule fires in ~3 min) -> start
  revert:   login(owner) -> stop -> PUT(params + schedule="0 14 * * mon")    -> start

Usage:
  python scripts/trigger_rebalance_generic.py --mode trigger --id 4 \
     --email momentum-conservative@globalcomplyai.com --password '...' --totp-secret <b32>
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pyotp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--totp-secret", default="")
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--mode", choices=["trigger", "revert"], required=True)
    ap.add_argument("--lead-min", type=int, default=3)
    args = ap.parse_args(argv)

    if args.mode == "trigger":
        fire = datetime.now(UTC) + timedelta(minutes=args.lead_min)
        schedule = f"{fire.minute} {fire.hour} * * *"
        when = f"~{fire:%H:%M} UTC today (one-shot)"
    else:
        schedule = "0 14 * * mon"
        when = "weekly Monday 14:00 UTC"

    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as c:
        login: dict[str, object] = {"email": args.email, "password": args.password}
        if args.totp_secret:
            login["totp_code"] = pyotp.TOTP(args.totp_secret).now()
        r = c.post("/api/v1/auth/login", json=login)
        if r.status_code != 200:
            print(f"login failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        print(f"logged in as {args.email}")

        # read current params so the wholesale PUT preserves everything
        r = c.get(f"/api/v1/strategies/{args.id}")
        if r.status_code != 200:
            print(f"get failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        params = dict(r.json().get("params") or {})
        params["timeframe"] = "1Day"
        params.setdefault("pricing_timeframe", "1Day")

        r = c.post(f"/api/v1/strategies/{args.id}/stop")
        print(f"stop: {r.status_code} {r.json() if r.status_code == 200 else r.text[:200]}")

        r = c.put(f"/api/v1/strategies/{args.id}", json={"schedule": schedule, "params": params})
        if r.status_code != 200:
            print(f"update failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        print(f"updated: schedule={schedule!r} ({when}) timeframe={params['timeframe']}")

        r = c.post(f"/api/v1/strategies/{args.id}/start")
        if r.status_code != 200:
            print(f"start failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        body = r.json()
        print(f"started: status={body.get('new_status')} run_id={body.get('run_id')}")
        if body.get("new_status") != "paper":
            print("WARN not paper — check engine logs", file=sys.stderr)
            return 1

    print(f"OK ({args.mode}): id={args.id} schedule={when}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
