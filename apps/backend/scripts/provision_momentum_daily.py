"""Provision `momentum-daily` (Workstream B) on user 4 — REGISTRATION ONLY, IDLE.

This registers the new strategy row and STOPS. It deliberately does NOT call `/start`: activation is
a separate, gated decision. Per the proposal §2.2 the new strategy must pass Stages 1-4 plus paper
trading and the promotion gates before any status change, and per the 2026-07-13 risk-gate incident
the momentum book stays halted until the ADR-0042 canary is GREEN. So this script creates the row as
IDLE and prints its id; someone with the authority and the gates satisfied does the activation.

    # SAFE anywhere — prints the payload, touches nothing:
    python scripts/provision_momentum_daily.py --dry-run --symbols-file <top200+SPY>.txt

    # Registers as IDLE on user 4 (requires user-4 credentials; run against the box API):
    python scripts/provision_momentum_daily.py \
        --base-url http://127.0.0.1:8000 --email momentum-growth@globalcomplyai.com \
        --symbols-file <top200+SPY>.txt

The new book runs at the SAME simulated notional as the corrected v0.9 baseline (§2.2 / §10) — user
4's account is $100k, matched by not overriding `initial_equity_estimate` (it sizes off live equity
anyway). The universe is the SAME top-200-liquid + SPY list the baseline uses, so the A-vs-C
comparison isolates the rebalance policy, not the universe.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# The §10 target configuration, pinned explicitly (NOT merged from template defaults — the exact
# mechanism that produced the 252/0 drift on the baseline). Anything omitted here falls to the
# template default, so the fields that MUST NOT drift are named.
PINNED_PARAMS = {
    "momentum_lookback_days": 252,
    "momentum_skip_days": 21,             # 12-1, pinned
    "min_score": 0.0,
    "min_raw_momentum": 0.0,              # A1 dual filter
    "entry_rank": 5,
    "hold_rank": 10,
    "exit_confirm_closes": 2,
    "replace_score_advantage": 0.30,
    "weight_drift_pct": 0.04,
    "backstop_max_days": 10,
    "max_daily_retries": 3,
    "max_names": 5,                       # Stage-3 sweeps 5/8/10; baseline pin = 5
    "max_position_pct": 0.20,
    "max_sector_pct": None,               # Stage-3 turns the sector cap on under test
    "weighting": "equal",                 # Stage-3 tests the inverse-vol hybrid
    "use_market_regime_filter": True,
    "market_filter_symbol": "SPY",
    "market_ma_days": 200,
    "regime_buffer_pct": 0.0,             # Stage-4 tests the buffered variant
    "regime_confirm_days": 1,
    "regime_stale_max_days": 2,
    "regime_degraded_gross": 0.50,
    "regime_degraded_max_days": 4,
    "monthly_universe_refresh": False,    # Stage universe-refresh work turns this on
    "min_trade_pct": 0.03,
    "fractional_shares": True,
    "cash_buffer_pct": 0.02,
    "order_pacing_seconds": 1.0,
    "timeframe": "1Day",
    "pricing_timeframe": "1Day",
}


def _load_symbols(path: str) -> list[str]:
    syms = [ln.strip().upper() for ln in Path(path).read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    if "SPY" not in syms:
        syms.append("SPY")                # the regime filter needs SPY in the registered universe
    seen: dict[str, None] = {}
    for s in syms:
        seen.setdefault(s, None)
    return list(seen)


def _totp(args) -> str | None:
    if not args.totp_secret:
        return None
    import pyotp
    return pyotp.TOTP(args.totp_secret).now()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Register momentum-daily on user 4 (IDLE only).")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--email", help="user-4 login (momentum-growth@globalcomplyai.com)")
    ap.add_argument("--password")
    ap.add_argument("--totp-secret")
    ap.add_argument("--name", default="momentum-daily")
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--code-path", default="strategies_user/templates/momentum_daily.py")
    ap.add_argument("--schedule", default="10 21 * * mon-fri",
                    help="daily post-close eval ~16:10 ET; day names (dow-safe)")
    ap.add_argument("--symbols-file", required=True,
                    help="the SAME top-200-liquid + SPY list the v0.9 baseline uses")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    symbols = _load_symbols(args.symbols_file)
    body = {
        "name": args.name, "version": args.version, "type": "python",
        "code_path": args.code_path, "params": PINNED_PARAMS,
        "symbols": symbols, "schedule": args.schedule,
    }

    if args.dry_run:
        print(f"[dry-run] {len(symbols)} symbols (SPY present={'SPY' in symbols})")
        print("[dry-run] POST /api/v1/strategies (creates IDLE; does NOT start):")
        print(json.dumps({**body, "symbols": symbols[:8] + ["..."]}, indent=2))
        print("\n[dry-run] activation is GATED: not started here. Requires ADR-0042 canary GREEN + "
              "Stages 1-4 + promotion gates.")
        return 0

    if not (args.email and args.password):
        raise SystemExit("--email and --password required (omit only with --dry-run)")

    import httpx
    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as c:
        r = c.post("/api/v1/auth/login", json={
            "email": args.email, "password": args.password, "totp_code": _totp(args)})
        if r.status_code != 200:
            print(f"login failed: HTTP {r.status_code} {r.text[:200]}", file=sys.stderr)
            return 1
        print(f"logged in as {args.email}")

        r = c.post("/api/v1/strategies", json=body)
        if r.status_code not in (200, 201):
            print(f"create failed: HTTP {r.status_code} {r.text[:300]}", file=sys.stderr)
            return 1
        sid = r.json()["id"]
        print(f"created momentum-daily id={sid} status={r.json().get('status')} "
              f"({len(symbols)} symbols) — IDLE, NOT started.")
        print("Activation is a separate gated decision: do NOT /start until the ADR-0042 canary is "
              "GREEN and the validation stages + promotion gates are satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
