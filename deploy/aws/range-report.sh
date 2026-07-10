#!/usr/bin/env bash
# AWS-side Range Trader recap → SNS email (ADR 0032 ops; range = rejected benchmark).
# Runs on the EC2 paper box via a systemd timer (post-open + EOD). Gathers the range book's
# day state from the backend container and publishes a readable recap to the paper-alarms SNS
# topic, so the owner gets a summary WITHOUT depending on the laptop/session. No secrets: aws
# uses the instance role (granted sns:Publish on this topic).
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
TOPIC="arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"

BODY="$($DOCKER exec -i workbench-backend python - <<'PY' 2>/dev/null
import asyncio
from datetime import datetime
import pandas as pd
from sqlalchemy import select
from app.brokers.registry import BrokerRegistry
from app.db.session import get_sessionmaker
from app.db.models.strategy import Strategy
from app.db.models.account import Account, AccountMode
from app.db.models.equity_snapshot import EquitySnapshot
from app.utils.time import EASTERN

async def main():
    sf = get_sessionmaker()
    reg = BrokerRegistry(sf); await reg.load_all()
    async with sf() as s:
        st = await s.get(Strategy, 1)
        uid = st.user_id; syms = list(st.symbols_json)
        acct = (await s.execute(select(Account).where(
            Account.user_id == uid, Account.mode == AccountMode.paper))).scalars().first()
        start_eq = (await s.execute(select(EquitySnapshot.equity).where(
            EquitySnapshot.account_id == acct.id).order_by(EquitySnapshot.ts.asc()).limit(1))).scalars().first()
    ad = reg.get(uid)
    a = ad.get_account()
    equity = float(a.get("equity") or 0); cash = float(a.get("cash") or 0)
    # Alpaca can return null day_change intraday → derive from last_equity so the recap never breaks.
    last_eq = float(a.get("last_equity") or equity)
    day = float(a.get("day_change") or (equity - last_eq))
    daypct = float(a.get("day_change_pct") or ((equity / last_eq - 1) if last_eq > 0 else 0.0))
    start_eq = float(start_eq) if start_eq else equity
    tot = equity - start_eq
    totpct = (equity / start_eq - 1) * 100 if start_eq > 0 else 0.0
    pos = ad.get_positions()
    et_today = datetime.now(EASTERN).date()
    def et_date(t):
        ts = pd.Timestamp(t)
        if ts.tzinfo is None: ts = ts.tz_localize("UTC")
        return ts.tz_convert(EASTERN).date()
    orders = ad.list_orders(status="all", limit=200)
    filled = [o for o in orders if str(o.get("status", "")).split(".")[-1].lower() == "filled"
              and (o.get("filled_at") or o.get("submitted_at")) and et_date(o.get("filled_at") or o.get("submitted_at")) == et_today]
    buys = [o for o in filled if str(o.get("side", "")).split(".")[-1].lower() == "buy"]
    sells = [o for o in filled if str(o.get("side", "")).split(".")[-1].lower() == "sell"]
    L = []
    L.append(f"Range Trader recap - {datetime.now(EASTERN).strftime('%Y-%m-%d %H:%M ET (%a)')}")
    L.append(f"Account {a.get('account_number')} (paper, rejected-benchmark sleeve)")
    L.append(f"Top-5 today: {', '.join(syms)}")
    L.append("")
    L.append(f"Equity ${equity:,.2f}  |  Cash ${cash:,.2f}")
    L.append(f"Total return ${tot:,.2f} ({totpct:+.2f}%)  [start ${start_eq:,.2f}]")
    L.append(f"Today P&L ${day:,.2f} ({daypct*100:+.2f}%)")
    L.append("")
    if pos:
        L.append(f"Open positions ({len(pos)}):")
        for p in pos:
            L.append(f"  {p.get('symbol')} {p.get('qty')}  uPnL ${float(p.get('unrealized_pl', 0)):,.2f}")
    else:
        L.append("Open positions: none (flat)")
    L.append(f"Filled orders today: {len(filled)}  ({len(buys)} buy / {len(sells)} sell)")
    for o in filled[:12]:
        side = str(o.get("side", "")).split(".")[-1].upper()
        L.append(f"  {side} {o.get('qty')} {o.get('symbol')} @ {o.get('filled_avg_price')}")
    L.append("")
    L.append("Note: RNG-001 is the rejected benchmark - informational, no action expected.")
    print("\n".join(L))

asyncio.run(main())
PY
)"

if [ -z "$BODY" ]; then
  BODY="Range recap - this run could not gather data, likely a transient broker/API hiccup. No action needed: the next scheduled recap (10:15 / 16:15 ET) will retry automatically. Only worth a look if several in a row come back empty."
fi
SUBJECT="Range recap $(TZ=America/New_York date '+%Y-%m-%d %H:%M ET')"
aws sns publish --region "$REGION" --topic-arn "$TOPIC" --subject "$SUBJECT" --message "$BODY" >/dev/null \
  && echo "published: $SUBJECT" || { echo "SNS publish FAILED"; exit 1; }
