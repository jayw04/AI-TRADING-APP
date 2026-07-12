"""LOCAL-ONLY (not committed): set use_vol_scaling=True on the live Risk Profile books.

Companion to the durable code fix (PR #249, app/strategies/risk_profiles.py): the three
momentum Risk Profiles were provisioned with only use_daily_overlay=True, so they entered each
weekly rebalance at full gross and were de-risked only by the daily overlay. This patches the
already-provisioned LIVE strategy rows to also turn on entry-time vol-scaling.

Goes through the audited API path (PUT /strategies/{id} → AuditAction.STRATEGY_UPDATED), NOT a
direct DB write — the hash-chained audit log must record this strategy-state change. PUT requires
IDLE, so a HALTED book is first deactivated (liquidate=False, KEEPS positions). Leaves every book
IDLE — it never re-activates anything (reactivation is a separate, gated decision).

PUT /strategies/{id} is OWNER-SCOPED (a user can only update their own strategies), and the three
books have different owners — balanced=user 1, conservative=user 3, growth=user 4. So run this
ONCE PER OWNING USER with that user's credentials, scoping the ids with --ids. From the repo root:

    # balanced (id 2, user 1 — jay)
    ! python apps/backend/scripts/apply_profile_vol_scaling.py --email jay@globalcomplyai.com --password '***' --ids 2
    # conservative (id 4, user 3)
    ! python apps/backend/scripts/apply_profile_vol_scaling.py --email <user3-email> --password '***' --ids 4
    # growth (id 5, user 4)
    ! python apps/backend/scripts/apply_profile_vol_scaling.py --email <user4-email> --password '***' --ids 5

Add --totp-secret '***' only if login TOTP is still required in your env (it is currently disabled).
Start with --dry-run to print the planned change without writing.
"""
from __future__ import annotations

import argparse
import sys

import httpx

try:
    import pyotp
except ImportError:  # TOTP optional now (login TOTP disabled)
    pyotp = None

# The three live Risk Profile books (DB strategy ids). Override with --ids if needed.
DEFAULT_IDS = [2, 4, 5]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--totp-secret", default=None)
    ap.add_argument("--ids", default=",".join(str(i) for i in DEFAULT_IDS),
                    help="comma-separated strategy ids (default 2,4,5)")
    ap.add_argument("--activate", action="store_true",
                    help="after the vol param is set, activate the book to PAPER (POST /start)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    base = args.base_url.rstrip("/")

    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as c:
        payload = {"email": args.email, "password": args.password}
        if args.totp_secret:
            if pyotp is None:
                print("pyotp not installed but --totp-secret given", file=sys.stderr)
                return 1
            payload["totp_code"] = pyotp.TOTP(args.totp_secret).now()
        r = c.post("/api/v1/auth/login", json=payload)
        if r.status_code != 200:
            print(f"login failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        print("logged in")

        rc = 0
        for sid in ids:
            r = c.get(f"/api/v1/strategies/{sid}")
            if r.status_code != 200:
                print(f"[{sid}] GET failed: {r.status_code} {r.text[:160]}")
                rc = 1
                continue
            row = r.json()
            name, status = row.get("name"), row.get("status")
            params = dict(row.get("params") or {})
            if params.get("use_vol_scaling") is True:
                print(f"[{sid}] {name}: already use_vol_scaling=True — skip")
                continue

            print(f"[{sid}] {name} (status={status}): "
                  f"use_vol_scaling {params.get('use_vol_scaling')} -> True "
                  f"(vol_target_annual={params.get('vol_target_annual')}, "
                  f"use_daily_overlay={params.get('use_daily_overlay')})"
                  + ("  + ACTIVATE -> PAPER" if args.activate else ""))
            if args.dry_run:
                continue

            # PUT requires IDLE — deactivate a HALTED/active book first (KEEPS positions).
            # /deactivate is the activation-router route that handles HALTED/LIVE -> IDLE
            # (immediate, no cooldown); /stop does NOT clear a breaker-HALT.
            if status != "idle":
                r = c.post(f"/api/v1/strategies/{sid}/deactivate", json={"liquidate": False})
                print(f"    deactivate ({status}) -> {r.status_code} {r.text[:140]}")
                if r.status_code != 200:
                    rc = 1
                    continue

            params["use_vol_scaling"] = True
            r = c.put(f"/api/v1/strategies/{sid}", json={"params": params})
            print(f"    update params -> {r.status_code} {r.text[:120]}")
            if r.status_code != 200:
                rc = 1
                continue
            # verify the param took before any activation
            chk = c.get(f"/api/v1/strategies/{sid}").json().get("params", {})
            if chk.get("use_vol_scaling") is not True:
                print("    verify use_vol_scaling=True -> FALSE (NOT activating)")
                rc = 1
                continue
            print("    verify use_vol_scaling=True -> True")

            if args.activate:
                r = c.post(f"/api/v1/strategies/{sid}/start")
                st = (r.json() or {}).get("new_status") if r.status_code == 200 else None
                print(f"    activate (start) -> {r.status_code} new_status={st}"
                      + ("" if r.status_code == 200 else f" {r.text[:140]}"))
                rc = rc or (0 if (r.status_code == 200 and st in ("paper", "PAPER")) else 1)

    tail = "activated to PAPER" if args.activate else "left IDLE (NOT activated)"
    print(f"\nDONE. Vol param set; books {tail}.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
