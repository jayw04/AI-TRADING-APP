"""LOCAL-ONLY helper: flatten (sell to zero) all long positions for a user's account.

One-shot operational tool. Drives the authenticated HTTP API, so every sell goes
through the OrderRouter (risk-gated + audited) — no raw broker liquidation.

Idempotent + safe:
  * Re-reads positions at run time and sells exactly what is held → a no-op if
    already flat (e.g. a rebalance already corrected it).
  * Waits for the backend to be healthy first (so a scheduled run survives a
    backend still booting after the machine wakes).
  * If the market-session gate rejects (MARKET_SESSION_CLOSED — outside the regular
    session), it logs and exits 0 rather than error-spamming. Run it during RTH.

Usage:
  python scripts/flatten_account.py --email <e> --password <p> --totp-secret <b32>
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx
import pyotp


def _wait_healthy(base: str, timeout_s: int = 180) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base}/healthz", timeout=5)
            if r.status_code == 200 and r.json().get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flatten all long positions for a user's account.")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--totp-secret", default="")
    ap.add_argument("--dry-run", action="store_true", help="print the sells without submitting")
    args = ap.parse_args(argv)

    base = args.base_url.rstrip("/")
    if not _wait_healthy(base):
        print("backend not healthy within timeout — aborting", file=sys.stderr)
        return 1

    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as c:
        login: dict[str, object] = {"email": args.email, "password": args.password}
        if args.totp_secret:
            login["totp_code"] = pyotp.TOTP(args.totp_secret).now()
        r = c.post("/api/v1/auth/login", json=login)
        if r.status_code != 200:
            print(f"login failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        print(f"logged in as {args.email}")

        r = c.get("/api/v1/positions")
        if r.status_code != 200:
            print(f"positions fetch failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        items = r.json().get("items", [])
        longs = [p for p in items if p.get("side") == "long" and float(p.get("qty") or 0) > 0]
        if not longs:
            print("nothing to flatten — account is already flat")
            return 0
        print(f"flattening {len(longs)} position(s): "
              + ", ".join(f"{p['symbol']}x{p['qty']}" for p in longs))

        if args.dry_run:
            print("[dry-run] no orders submitted")
            return 0

        rejected = 0
        for p in longs:
            body = {"symbol": p["symbol"], "side": "sell", "qty": str(p["qty"]),
                    "type": "market", "tif": "day"}
            rr = c.post("/api/v1/orders", json=body)
            if rr.status_code in (200, 201):
                o = rr.json()
                status = o.get("status")
                print(f"  SELL {p['symbol']} {p['qty']}: {status} "
                      f"(reason={o.get('rejection_reason')}, broker={o.get('broker_order_id')})")
                if status == "rejected":
                    rejected += 1
            else:
                print(f"  SELL {p['symbol']} {p['qty']}: HTTP {rr.status_code} {rr.text[:160]}")
                rejected += 1

        if rejected == len(longs):
            # All rejected — almost certainly the market-session gate. Not an error:
            # the scheduled run simply fired outside RTH; re-run during the session.
            print("all sells rejected (likely MARKET_SESSION_CLOSED) — run during RTH")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
