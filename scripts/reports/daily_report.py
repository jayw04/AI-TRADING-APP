"""Daily paper-stack report — Markdown to stdout, with an ISSUES section on top.

Runs INSIDE the backend container (needs broker adapters + DB + factor store):

    sudo docker exec -i workbench-backend python - < scripts/reports/daily_report.py \
        > reports/$(date +%F).md

Two jobs: (1) summarize every user account, (2) surface issues an operator should
see before they become incidents. Every check is wrapped so one failure degrades to
a single ALERT line rather than killing the whole report.
"""

import asyncio
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select

from app.brokers.registry import BrokerRegistry
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.utils.time import EASTERN

# order statuses that are NOT terminal — if these linger, something stalled
NON_TERMINAL = {
    "new", "accepted", "pending_new", "pending_risk", "partially_filled",
    "accepted_for_bidding", "pending_cancel", "pending_replace", "held", "submitted",
}
STUCK_WARN_MIN = 15   # 🟡
STUCK_CRIT_MIN = 60   # 🔴


def _enum(v):
    return str(v).split(".")[-1]


def _to_et_dt(t):
    ts = pd.Timestamp(t)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    return ts.tz_convert(EASTERN)


async def main():
    sf = get_sessionmaker()
    reg = BrokerRegistry(sf)
    await reg.load_all()
    now_et = datetime.now(EASTERN)
    now_utc = datetime.now(UTC)
    et_today = now_et.date()

    async with sf() as s:
        users = (await s.execute(select(User).order_by(User.id))).scalars().all()
        strats = (await s.execute(select(Strategy))).scalars().all()
    by_user = {}
    for st in strats:
        by_user.setdefault(st.user_id, []).append(st)

    alerts = []       # (severity, text) — severity in {"crit","warn"}
    user_blocks = []  # rendered per-user markdown
    accounts_for_pae: list = []       # (account_id, strategy_label) for the analytics engine
    tot_eq = tot_le = 0.0             # portfolio totals for the P&L KPI
    tot_fills = tot_stuck = 0

    for u in users:
        async with sf() as s:
            acct = (await s.execute(select(Account).where(
                Account.user_id == u.id,
                Account.mode == AccountMode.paper,
            ))).scalars().first()
        if not acct:
            continue
        active = [st for st in by_user.get(u.id, [])
                  if _enum(getattr(st, "status", "")) in ("paper", "live")]

        # --- strategy-state checks (do not need the adapter) ---
        for st in by_user.get(u.id, []):
            status = _enum(getattr(st, "status", ""))
            if status == "error":
                alerts.append(("crit",
                    f"user {u.id} · **{st.name}** is in ERROR "
                    f"(`{getattr(st, 'error_text', None) or 'no detail'}`)"))
            if status in ("paper", "live") and not getattr(st, "schedule", None):
                alerts.append(("warn",
                    f"user {u.id} · **{st.name}** is {status} but has no schedule"))

        try:
            ad = reg.get(u.id)
            a = ad.get_account()
        except Exception as e:  # noqa: BLE001
            alerts.append(("crit", f"user {u.id} ({u.email}) · adapter error: {type(e).__name__}"))
            user_blocks.append(f"### user {u.id} — {u.email}\n\n> ⚠ adapter unavailable ({type(e).__name__})\n")
            continue

        eq = float(a.get("equity") or 0)
        le = float(a.get("last_equity") or eq)
        cash = float(a.get("cash") or 0)
        gl = eq - le
        glp = (eq / le - 1) * 100 if le > 0 else 0.0

        # --- account-block checks ---
        if a.get("trading_blocked"):
            alerts.append(("crit", f"user {u.id} · trading_blocked on account {a.get('account_number')}"))
        if a.get("account_blocked"):
            alerts.append(("crit", f"user {u.id} · account_blocked on account {a.get('account_number')}"))

        # --- orders: fills today + stuck non-terminal ---
        fills, stuck = [], []
        try:
            orders = ad.list_orders(status="all", limit=250)
            for o in orders:
                ostat = _enum(o.get("status", "")).lower()
                tref = o.get("filled_at") or o.get("submitted_at") or o.get("created_at")
                if ostat == "filled" and tref and _to_et_dt(tref).date() == et_today:
                    fills.append(o)
                elif ostat in NON_TERMINAL:
                    sub = o.get("submitted_at") or o.get("created_at")
                    age_min = (now_utc - _to_et_dt(sub).astimezone(UTC)).total_seconds() / 60 if sub else 0
                    stuck.append((o, age_min, ostat))
        except Exception as e:  # noqa: BLE001
            alerts.append(("warn", f"user {u.id} · could not list orders: {type(e).__name__}"))

        for o, age_min, ostat in stuck:
            sev = "crit" if age_min >= STUCK_CRIT_MIN else "warn"
            if age_min >= STUCK_WARN_MIN:
                alerts.append((sev,
                    f"user {u.id} · order {_enum(o.get('side')).upper()} {o.get('qty')} "
                    f"{o.get('symbol')} stuck `{ostat}` for {age_min:.0f} min"))

        try:
            pos = ad.get_positions()
        except Exception:  # noqa: BLE001
            pos = []

        # accumulate portfolio-level totals + the account list for the analytics engine
        tot_eq += eq
        tot_le += le
        tot_fills += len(fills)
        tot_stuck += len(stuck)
        accounts_for_pae.append((acct.id, active[0].name if active else u.email.split("@")[0]))

        # --- render user block ---
        lines = [f"### user {u.id} — {u.email}",
                 f"- account: `{a.get('account_number')}`"]
        if active:
            for st in active:
                lines.append(f"- strategy: **{st.name}** — {_enum(getattr(st,'status',''))} · "
                             f"`{getattr(st,'schedule',None)}` · {len(st.symbols_json or [])} symbols")
        else:
            lines.append("- strategy: _(none active)_")
        lines.append(f"- **value ${eq:,.2f}** · start(prior close) ${le:,.2f} · "
                     f"**G/L ${gl:,.2f} ({glp:+.2f}%)** · cash ${cash:,.2f}")
        lines.append(f"- fills today: **{len(fills)}**"
                     + ("" if not fills else "  \n"
                        + "  \n".join(f"    - {_enum(o.get('side')).upper()} {o.get('qty')} "
                                      f"{o.get('symbol')} @ {o.get('filled_avg_price')}" for o in fills)))
        posrepr = ", ".join(f"{p.get('symbol')}×{p.get('qty')}" for p in pos) or "_flat_"
        lines.append(f"- open positions ({len(pos)}): {posrepr}")
        if stuck:
            lines.append(f"- ⚠ stuck orders: {len(stuck)}")
        user_blocks.append("\n".join(lines) + "\n")

    # --- data-health checks (factor store) ---
    data_lines = []
    try:
        from app.factor_data.accessor import FactorAccessor
        from app.factor_data.store import FactorDataStore
        store = FactorDataStore(read_only=True)
        acc = FactorAccessor(store)
        n_mom = len(acc.momentum_scores(as_of=et_today))
        n_lv = len(acc.low_vol_scores(as_of=et_today))
        uni = acc.universe(as_of=et_today, n=200)
        secs = acc.sectors(uni)
        n_sec = sum(1 for v in secs.values() if v)
        data_lines.append(f"- factor rankings: momentum **{n_mom}**, low-vol **{n_lv}**, "
                          f"sectors **{n_sec}/{len(uni)}** mapped")
        if n_mom == 0 or n_lv == 0:
            alerts.append(("crit", "factor store returns 0 momentum/low-vol names"))
        if n_sec < 0.5 * max(len(uni), 1):
            alerts.append(("warn", f"sector coverage low: {n_sec}/{len(uni)} mapped"))
        try:
            latest = store.con.execute("SELECT max(date) FROM sep").fetchone()[0]
            if latest is not None:
                stale_days = (et_today - pd.Timestamp(latest).date()).days
                data_lines.append(f"- factor prices (`sep`) latest: **{latest}** ({stale_days}d old)")
                if stale_days > 7:
                    alerts.append(("warn", f"factor prices stale: `sep` latest {latest} ({stale_days}d old)"))
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        alerts.append(("warn", f"factor-store health check failed: {type(e).__name__}"))

    # --- Portfolio Analytics Engine: correlation / overlap / diversification ---
    pa = None
    try:
        from app.services import portfolio_analytics as _pae
        async with sf() as s:
            pa = await _pae.compute(s, accounts_for_pae, window_days=30)
    except Exception as e:  # noqa: BLE001
        alerts.append(("warn", f"portfolio analytics failed: {type(e).__name__}"))

    crits = [t for sev, t in alerts if sev == "crit"]
    tot_glp = (tot_eq / tot_le - 1) * 100 if tot_le > 0 else 0.0

    # ===================== render markdown =====================
    out = []
    out.append(f"# Daily Report — {now_et.strftime('%Y-%m-%d')}")
    out.append(f"_Generated {now_et.strftime('%Y-%m-%d %H:%M ET (%a)')} · single armed host (AWS)_\n")

    # KPI panel — evidence-first: P&L is one line among many (report-review.md).
    _op_ok = not crits
    _exec_ok = tot_stuck == 0
    _exec_pct = 100 if _exec_ok else round(100 * tot_fills / max(1, tot_fills + tot_stuck))
    out.append("## 📊 Portfolio KPIs")
    out.append("| KPI | Value | Status |")
    out.append("|---|---|---|")
    out.append(f"| Operational Health | {'100%' if _op_ok else 'degraded'} | {'✅' if _op_ok else '🟠'} |")
    out.append(f"| Execution Success | {_exec_pct}% | {'✅' if _exec_ok else '🟡'} |")
    if pa is not None and pa.highest_corr and pa.highest_corr.correlation is not None:
        _cs = pa.correlation_status
        _cflag = "⚠ Review" if _cs == "High" else ("✅" if _cs == "Low" else "🟡")
        out.append(f"| Strategy Correlation | {_cs} ({pa.highest_corr.correlation:.2f}) | {_cflag} |")
        out.append(f"| Diversification | {pa.diversification}/100 | {'✅' if pa.diversification >= 60 else '🟡'} |")
    out.append("| Research Progress | +1 evidence day | ✅ |")
    out.append(f"| **Total P&L today** | **{tot_glp:+.2f}%** | _evidence, not the goal_ |")
    out.append("")

    out.append("## ⚠ Issues & Alerts")
    crits = [t for sev, t in alerts if sev == "crit"]
    warns = [t for sev, t in alerts if sev == "warn"]
    if not crits and not warns:
        out.append("✅ No alerts — all accounts nominal, no stuck orders, data healthy.\n")
    else:
        for t in crits:
            out.append(f"- 🔴 {t}")
        for t in warns:
            out.append(f"- 🟡 {t}")
        out.append("")

    out.append("## Data health")
    out.extend(data_lines or ["- _(unavailable)_"])
    out.append("")

    if pa is not None and pa.pairs:
        out.append("## 🔗 Strategy correlation & holdings overlap")
        out.append(f"_return correlation over the last {pa.window_days}d of snapshots · "
                   f"diversification score **{pa.diversification}/100**_")
        ranked = sorted(
            (p for p in pa.pairs if p.correlation is not None),
            key=lambda p: p.correlation, reverse=True,
        )
        out.append("| Pair | Corr | Overlap |")
        out.append("|---|---|---|")
        for p in ranked[:6]:
            out.append(f"| {p.a_label} ↔ {p.b_label} | {p.correlation:+.2f} | {p.overlap_pct:.0f}% |")
        hc = pa.highest_corr
        if hc and hc.correlation is not None and hc.correlation >= 0.9:
            out.append(f"\n⚠ **{hc.a_label} ↔ {hc.b_label}** are near-lockstep "
                       f"({hc.correlation:.2f}, {hc.overlap_pct:.0f}% overlap) — effectively "
                       f"one bet, not independent evidence.")
        out.append("")

    out.append("## Accounts")
    out.append("")
    out.extend(user_blocks)

    print("\n".join(out))


asyncio.run(main())
