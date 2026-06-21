"""Register + activate the momentum-portfolio strategy to PAPER (P9 §4 drive).

Turnkey helper for the Monday paper-activation drive. Logs in, creates the
strategy (IDLE), then starts it (engine.register → PAPER, schedules the weekly
cron). Idempotent-ish: re-running creates a NEW strategy row each time, so run it
once (use --dry-run first to preview the payload).

PREREQUISITES (all must hold before running — see docs/runbook/factor-data.md §5d):
  1. The backend stack is UP and reachable at --base-url (default localhost:8000).
  2. The factor store is ingested (so lifespan provisioned the FactorAccessor) and
     `accounts_state` is populated for the paper account (AccountSyncService) — else
     ctx.factors raises / live-equity sizing falls back to the estimate.
  3. A paper Alpaca account row exists for the user (engine.register resolves
     broker=alpaca, mode=paper). The BFY6 key in .env is what the backend connects
     with.

USAGE (Monday, after the stack is up):
  PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
      apps/backend/scripts/paper_activate_momentum.py \
      --email jay@globalcomplyai.com --password 'WorkbenchDev!2026' \
      --totp 123456 \
      --symbols-file apps/backend/data/paper_symbols.txt

  # preview the create payload without logging in / mutating anything:
  ... --symbols-file apps/backend/data/paper_symbols.txt --dry-run

TOTP: pass the current 6-digit code from your phone via --totp, OR pass
--totp-secret <base32> to compute it here (pyotp). The code is time-based, so
--totp must be fresh (run within its 30s window).

No secrets are hardcoded; everything comes from args. The API key/secret are never
touched by this script — it only drives the authenticated HTTP API.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.strategies.risk_profiles import RISK_PROFILES, profile_name, profile_params  # noqa: E402

DEFAULT_PARAMS = {
    # P9 §4 dry-run-locked sizing for the ~$10k paper account:
    "max_names": 5,
    "max_position_pct": 0.20,  # companion to max_names so per-name isn't capped at 10%
    "top_quantile": 0.20,
    "min_score": 0.0,
    "cash_buffer_pct": 0.02,
    "use_market_regime_filter": True,
    "market_filter_symbol": "SPY",
    "pricing_timeframe": "1Day",
    # initial_equity_estimate is a FALLBACK only — live equity comes from
    # accounts_state via ctx.get_account_equity().
    "initial_equity_estimate": 10000,
}


def _load_symbols(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    out, seen = [], set()
    for line in text.replace(",", "\n").splitlines():
        s = line.strip().upper()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _totp_code(args: argparse.Namespace) -> str:
    if args.totp:
        return args.totp
    if args.totp_secret:
        import pyotp

        return pyotp.TOTP(args.totp_secret).now()
    raise SystemExit("provide --totp <6-digit> or --totp-secret <base32>")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Register + activate momentum-portfolio to PAPER.")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--totp", help="current 6-digit TOTP code")
    ap.add_argument("--totp-secret", help="base32 TOTP secret (computes the code via pyotp)")
    ap.add_argument("--symbols-file", required=True, help="newline/comma-separated tickers (incl. SPY)")
    ap.add_argument("--name", default=None,
                    help="strategy/book name (default: 'momentum-portfolio', or "
                         "'momentum-<profile>' when --risk-profile is set)")
    ap.add_argument("--risk-profile", choices=sorted(RISK_PROFILES), default=None,
                    help="P13.5 Risk Profile preset — turns vol-scaling ON at the profile's vol "
                         "target (conservative=10%% / balanced=15%% / growth=20%%). Each profile "
                         "needs its OWN paper account/user (run on the right login).")
    ap.add_argument("--code-path", default="templates/momentum_portfolio.py")
    ap.add_argument("--version", default="0.3.0")
    ap.add_argument("--schedule", default="0 14 * * 1", help="weekly Mon 14:00 UTC ≈ 10:00 ET")
    ap.add_argument("--dry-run", action="store_true", help="print the create payload and exit")
    args = ap.parse_args(argv)

    # Risk-profile preset (P13.5): vol-scaling ON at the profile's target; default the name too.
    if args.risk_profile:
        params = profile_params(args.risk_profile, DEFAULT_PARAMS)
        name = args.name or profile_name(args.risk_profile)
    else:
        params = DEFAULT_PARAMS
        name = args.name or "momentum-portfolio"

    symbols = _load_symbols(args.symbols_file)
    create_body = {
        "name": name,
        "version": args.version,
        "type": "python",
        "code_path": args.code_path,
        "params": params,
        "symbols": symbols,
        "schedule": args.schedule,
    }

    if args.dry_run:
        print(f"[dry-run] {len(symbols)} symbols (incl. SPY={'SPY' in symbols})")
        print("[dry-run] POST /api/v1/strategies body:")
        print(json.dumps({**create_body, "symbols": symbols[:8] + ["..."]}, indent=2))
        print(f"[dry-run] params: {json.dumps(params)}")
        if args.risk_profile:
            print(f"[dry-run] risk profile: {args.risk_profile} "
                  f"(vol_target_annual={params['vol_target_annual']}, vol-scaling ON) -> name={name!r}")
        return 0

    if not (args.email and args.password):
        raise SystemExit("--email and --password are required (omit only with --dry-run)")

    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as c:
        # 1. login → session cookie on the client
        r = c.post("/api/v1/auth/login", json={
            "email": args.email, "password": args.password, "totp_code": _totp_code(args),
        })
        if r.status_code != 200:
            print(f"login failed: HTTP {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        print(f"logged in as {args.email}")

        # 2. create the strategy (IDLE)
        r = c.post("/api/v1/strategies", json=create_body)
        if r.status_code not in (200, 201):
            print(f"create failed: HTTP {r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        sid = r.json()["id"]
        print(f"created strategy id={sid} status={r.json().get('status')} ({len(symbols)} symbols)")

        # 3. start it → engine.register → PAPER + weekly cron scheduled
        r = c.post(f"/api/v1/strategies/{sid}/start")
        if r.status_code != 200:
            print(f"start failed: HTTP {r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        body = r.json()
        print(f"started: status={body.get('new_status')} run_id={body.get('run_id')}")
        if body.get("new_status") != "paper":
            print(f"WARN expected status 'paper', got {body.get('new_status')} - check engine logs",
                  file=sys.stderr)
            return 1

    print(f"\nOK: {name} is ACTIVE on PAPER (strategy id={sid}).")
    print(f"   The weekly cron '{args.schedule}' fires the rebalance automatically")
    print("   (Mon 14:00 UTC ~ 10:00 ET, i.e. ~30 min after the 09:30 open).")
    print("   To fire SOONER for the validation, re-create with a frequent schedule,")
    print("   e.g. --schedule '*/5 * * * *' (the rebalance-once-per-ISO-week guard means")
    print("   it rebalances ONCE then no-ops; NB each tick fetches bars for all symbols,")
    print("   so revert to the weekly cron after you've seen it work).")
    print("   Watch the audit log / signals for source_type=STRATEGY orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
