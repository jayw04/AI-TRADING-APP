"""P6 §3 paper-order byte-identical smoke (local-only; hardcoded dev creds).

Submits one manual MARKET paper order through the real OrderRouter path
(POST /api/v1/orders -> OrderRouter.submit -> Alpaca paper broker) and confirms
it persists with a real broker_order_id. Paper account only -- NOT real money.
"""

import json
import sys

import pyotp
import requests

BASE = "http://localhost:8000"
EMAIL = "jay@globalcomplyai.com"
PASSWORD = "WorkbenchDev!2026"
TOTP_SECRET = "HLY7NC3UFQFHPTB3G2EAUP3Y3Y2WQTTO"
SYMBOL = "AAPL"
QTY = "1"


def main() -> int:
    s = requests.Session()

    r = s.post(
        f"{BASE}/api/v1/auth/login",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(TOTP_SECRET).now(),
        },
        timeout=20,
    )
    print(f"login -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500])
        return 1

    print(f"submitting MARKET BUY {QTY} {SYMBOL} (paper)...")
    r = s.post(
        f"{BASE}/api/v1/orders",
        json={"symbol": SYMBOL, "side": "buy", "qty": QTY, "type": "market", "tif": "day"},
        timeout=30,
    )
    print(f"create order -> {r.status_code}")
    if r.status_code != 200:
        print(r.text[:800])
        return 1

    o = r.json()
    print(json.dumps(o, indent=2)[:1200])

    broker_id = o.get("broker_order_id")
    oid = o.get("id")
    status = o.get("status")
    print("\n=== VERDICT ===")
    if oid is not None and broker_id:
        print(f"PASS: order id={oid} persisted with real broker_order_id={broker_id} status={status}")
        return 0
    print(f"FAIL: id={oid} broker_order_id={broker_id} status={status} (no real broker id)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
