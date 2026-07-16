"""LOCAL-ONLY: recover after the validation trigger tripped the breaker.

NOT committed. Resets the tripped circuit breaker, deactivates the HALTED
strategy to IDLE (KEEPS the 3 filled positions — liquidate=False), restores the
correct weekly-Monday schedule, and LEAVES it IDLE (does not re-activate).
"""
from __future__ import annotations

import argparse
import sys

import httpx
import pyotp

# Clean original params for id=2 (PUT replaces params_json wholesale). NO
# "timeframe" key — the dispatch-timeframe fix belongs in the strategy's
# default_params (code PR), not the live row.
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
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--totp-secret", required=True)
    ap.add_argument("--id", type=int, default=2)
    ap.add_argument("--account-id", type=int, default=1)
    ap.add_argument("--account-label", default="Alpaca Paper")
    args = ap.parse_args(argv)

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

        # 1. reset the tripped circuit breaker (confirmation = account label)
        r = c.post(f"/api/v1/accounts/{args.account_id}/risk/reset-circuit-breaker",
                   json={"confirmation_text": args.account_label})
        print(f"reset-breaker: {r.status_code} {r.text[:200]}")
        if r.status_code != 200:
            return 1

        # 2. deactivate HALTED -> IDLE, KEEP positions
        r = c.post(f"/api/v1/strategies/{args.id}/deactivate", json={"liquidate": False})
        print(f"deactivate: {r.status_code} {r.text[:200]}")
        if r.status_code != 200:
            return 1

        # 3. restore the correct weekly-Monday schedule (requires IDLE)
        r = c.put(f"/api/v1/strategies/{args.id}",
                  json={"schedule": "0 14 * * mon", "params": PARAMS})
        print(f"update schedule: {r.status_code} {r.text[:200]}")
        if r.status_code != 200:
            return 1

    print("\nOK: breaker reset, id=2 IDLE with schedule '0 14 * * mon' (NOT re-activated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
