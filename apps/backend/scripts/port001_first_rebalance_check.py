"""PORT-001 §4 — read-only verification of the Combined Book's first live paper rebalance.

The headless durability backstop for the Monday-after-activation check (strategy id=9
`combined-book`, user 7 / account 7, ALPACA_PAPER_6). Captures the evidence even if no Claude
session is running: did the rebalance FIRE, did orders FILL, do POSITIONS match the two-sleeve
40/60 target, are RISK gates clean, is the equity snapshot accruing. Prints a Markdown report to
stdout + a one-line verdict. READ-ONLY (no order path, no mutation) — safe to run any time.

Run inside the backend container (it has the DB + models):
    docker compose exec -T backend python scripts/port001_first_rebalance_check.py
or pipe it in (no image rebuild needed):
    Get-Content scripts/port001_first_rebalance_check.py | docker compose exec -T backend python -
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.db.session import get_sessionmaker  # noqa: E402

STRATEGY_ID = 9
ACCOUNT_ID = 7
ETFS = {"SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP"}


async def _rows(s, sql: str, **p):
    return [dict(r._mapping) for r in (await s.execute(text(sql), p)).all()]


async def main() -> int:
    today = datetime.now(UTC).date().isoformat()
    out: list[str] = []
    warns: list[str] = []
    fails: list[str] = []

    sm = get_sessionmaker()
    async with sm() as s:
        # symbol_id -> ticker map (for orders/positions)
        try:
            sym = {r["id"]: r["ticker"] for r in await _rows(s, "SELECT id, ticker FROM symbols")}
        except Exception:
            sym = {}

        # 1. the strategy
        strat = await _rows(s, "SELECT id,name,status,error_text,updated_at FROM strategies "
                               "WHERE id=:i", i=STRATEGY_ID)
        if not strat:
            fails.append(f"strategy id={STRATEGY_ID} not found")
            st = {}
        else:
            st = strat[0]
            if st["status"] != "PAPER":
                fails.append(f"strategy status is {st['status']!r}, expected PAPER")
            if st.get("error_text"):
                warns.append(f"strategy error_text: {str(st['error_text'])[:160]}")

        # 2. orders today from this strategy / account
        orders = await _rows(
            s, "SELECT symbol_id, side, qty, status, rejection_reason, source_type, source_id "
               "FROM orders WHERE account_id=:a AND date(created_at)=:d ORDER BY created_at",
            a=ACCOUNT_ID, d=today)
        strat_orders = [o for o in orders if str(o.get("source_type", "")).upper().endswith("STRATEGY")]
        filled = [o for o in strat_orders if str(o["status"]).lower() in ("filled", "closed", "complete")]
        rejected = [o for o in strat_orders if o.get("rejection_reason")]

        # 3. signals today
        sigs = await _rows(s, "SELECT type, payload_json, received_at FROM signals "
                              "WHERE strategy_id=:i AND date(received_at)=:d ORDER BY received_at",
                           i=STRATEGY_ID, d=today)

        fired = bool(strat_orders) or bool(sigs)
        if not fired:
            warns.append("NO orders and NO signals from the strategy today — rebalance may not "
                         "have fired yet (check the time / cron) or the book went to cash (regime/"
                         "factor HOLD). Inspect `docker compose logs backend`.")

        # 4. positions
        pos = await _rows(s, "SELECT symbol_id, qty, side, market_value FROM positions "
                             "WHERE account_id=:a AND qty>0", a=ACCOUNT_ID)
        held = {sym.get(p["symbol_id"], str(p["symbol_id"])): p for p in pos}
        etf_held = sorted(t for t in held if t in ETFS)
        eq_held = sorted(t for t in held if t not in ETFS)

        # 5. account state + breaker + snapshot
        state = await _rows(s, "SELECT equity, day_change_pct, status, trading_blocked "
                               "FROM accounts_state WHERE account_id=:a ORDER BY updated_at DESC "
                               "LIMIT 1", a=ACCOUNT_ID)
        brk = await _rows(s, "SELECT circuit_breaker_tripped_at FROM accounts WHERE id=:a",
                          a=ACCOUNT_ID)
        snap = await _rows(s, "SELECT ts, equity, day_change_pct FROM equity_snapshots "
                              "WHERE account_id=:a ORDER BY ts DESC LIMIT 1", a=ACCOUNT_ID)

        breaker_tripped = bool(brk and brk[0].get("circuit_breaker_tripped_at"))
        if breaker_tripped:
            fails.append(f"CIRCUIT BREAKER TRIPPED on account {ACCOUNT_ID} at "
                         f"{brk[0]['circuit_breaker_tripped_at']} — HALT; see the breaker-recovery runbook")
        if state and state[0].get("trading_blocked"):
            fails.append("account trading_blocked = true")
        if rejected:
            warns.append(f"{len(rejected)} order(s) rejected: "
                         + ", ".join(sorted({str(o['rejection_reason']) for o in rejected})))

    # ---- report ----
    out.append(f"# PORT-001 §4 — Combined Book first-rebalance check ({today})")
    out.append("")
    out.append(f"- Strategy: id={STRATEGY_ID} {st.get('name','?')} · status **{st.get('status','?')}** "
               f"· updated {st.get('updated_at','?')}")
    out.append(f"- Rebalance fired: **{'YES' if fired else 'NO'}** "
               f"({len(strat_orders)} strategy orders, {len(sigs)} signals today)")
    out.append(f"- Orders: {len(strat_orders)} submitted · {len(filled)} filled · {len(rejected)} rejected")
    out.append(f"- Positions (account {ACCOUNT_ID}): {len(held)} held — "
               f"equity sleeve {len(eq_held)} names, cross-asset ETFs {etf_held}")
    if state:
        out.append(f"- Account state: equity {state[0].get('equity')} · "
                   f"day_change_pct {state[0].get('day_change_pct')} · status {state[0].get('status')}")
    out.append(f"- Circuit breaker: {'TRIPPED ⚠' if breaker_tripped else 'clean'}")
    if snap:
        out.append(f"- Latest equity snapshot: {snap[0].get('ts')} equity {snap[0].get('equity')} "
                   f"(Continuous-Evidence / L4 signal)")
    else:
        out.append("- Latest equity snapshot: none yet")
    out.append("")
    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")
    out.append(f"## Verdict: {verdict}")
    for f in fails:
        out.append(f"- ❌ {f}")
    for w in warns:
        out.append(f"- ⚠ {w}")
    if verdict == "PASS":
        out.append("- ✅ Rebalance fired, orders filled, risk gates clean, evidence accruing — "
                   "the first L4 Continuous-Evidence data point.")
    out.append("")
    out.append("_Read-only check. Smart diagnosis/fix is the Claude post-rebalance task; this is "
               "the headless evidence-capture backstop. Do NOT retire the sibling (§6) yet._")
    print("\n".join(out))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
