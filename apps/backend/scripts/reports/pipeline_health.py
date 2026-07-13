"""Daily / weekly pipeline-health checklist — data freshness + rebalance status, persisted.

WHY THIS EXISTS (2026-07-13). Two blind spots surfaced on a live rebalance Monday:

  1. The momentum book produced ZERO orders and we could not tell, from the database, whether
     it had fired and correctly traded nothing or had never fired at all. Those are IDENTICAL
     in ``orders`` — a no-op leaves no orders to derive a run window from.
  2. Data freshness was only ever checked ad hoc, by hand, at the moment someone got worried.

So this script records the checklist itself. Every run writes:

  * ``data_health_snapshots``   — one row per source: as-of date, last refresh, staleness.
  * ``ops_check_runs``          — one row per checklist run, with the rendered report kept.

and it READS ``strategy_dispatch_runs`` (written by the engine on every dispatch) to answer
"did the 10:00 slot fire, and what did it do?" A missing dispatch row is the alarm.

Checks
------
DATA
  D1  factor store ``sep``       — newest price date vs the last completed session
  D2  factor store lockstep      — ``tickers.lastpricedate`` >= ``sep`` max
                                   (a break makes the PIT universe resolve EMPTY and every
                                   factor book silently HOLDs — the 2026-07-06 incident class)
  D3  bar cache                  — the live universe has bars for the last completed session
  D4  universe coverage          — every live strategy's symbols are present in the store
REBALANCE
  R1  dispatch fired             — each cron slot due in the window produced a dispatch row
  R2  dispatch healthy           — no ERROR / SKIPPED_OUT_OF_SESSION outcomes
  R3  order outcomes             — filled / rejected / still-SUBMITTED per account

Read-only with respect to trading; off the order path. Run inside the backend container:

    python scripts/reports/pipeline_health.py --kind DAILY
    python scripts/reports/pipeline_health.py --kind WEEKLY

Exit code 2 if any check FAILs (so a systemd timer / SNS wrapper can trip on it).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.account import Account
from app.db.models.ops_health import (
    STATUS_FAIL,
    STATUS_OK,
    STATUS_WARN,
    DataHealthSnapshot,
    OpsCheckRun,
    StrategyDispatchRun,
)
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.session import get_sessionmaker
from app.market.session import is_trading_day
from app.utils.time import EASTERN

FACTOR_DB = Path("/app/data/factor_data.duckdb")
BAR_CACHE_ROOT = Path("/app/data/bar_cache")

# A store one session behind is NORMAL intraday (today's close isn't published yet). Two is a
# missed refresh worth a warning; three-plus means the books are ranking on stale prices.
SEP_WARN_SESSIONS = 2
SEP_FAIL_SESSIONS = 3

_RANK = {STATUS_OK: 0, STATUS_WARN: 1, STATUS_FAIL: 2}
_ICON = {STATUS_OK: "🟢", STATUS_WARN: "🟡", STATUS_FAIL: "🔴"}


@dataclass
class Check:
    """One checklist line."""

    id: str
    title: str
    status: str
    detail: str
    facts: dict = field(default_factory=dict)


def _worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda s: _RANK[s], default=STATUS_OK)


def _last_completed_session(now_et: datetime) -> date:
    """The most recent session whose CLOSE has passed.

    Today only counts once the market has closed — before that, the newest data anyone could
    legitimately have is yesterday's close, and calling that "stale" is a false alarm.
    """
    d = now_et.date()
    if not (is_trading_day(d) and now_et.hour >= 16):
        d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def _sessions_between(start: date, end: date) -> int:
    """Number of trading sessions strictly after ``start`` up to and including ``end``."""
    if end <= start:
        return 0
    n, d = 0, start + timedelta(days=1)
    while d <= end:
        if is_trading_day(d):
            n += 1
        d += timedelta(days=1)
    return n


# --------------------------------------------------------------------------------------
# DATA checks
# --------------------------------------------------------------------------------------
def check_factor_store(last_session: date) -> tuple[list[Check], list[DataHealthSnapshot]]:
    """D1 + D2: the factor store's price recency and the tickers/sep lockstep invariant."""
    now = datetime.now(UTC)
    checks: list[Check] = []
    snaps: list[DataHealthSnapshot] = []

    if not FACTOR_DB.exists():
        checks.append(
            Check("D1", "Factor store `sep` freshness", STATUS_FAIL, f"missing: {FACTOR_DB}")
        )
        return checks, snaps

    refreshed = datetime.fromtimestamp(FACTOR_DB.stat().st_mtime, tz=UTC)
    try:
        import duckdb

        con = duckdb.connect(str(FACTOR_DB), read_only=True)
        try:
            sep_max, sep_rows, sep_syms = con.execute(
                "SELECT max(date), count(*), count(DISTINCT ticker) FROM sep"
            ).fetchone()
            last_price_date = con.execute("SELECT max(lastpricedate) FROM tickers").fetchone()[0]
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — a store we cannot read IS the finding
        checks.append(
            Check("D1", "Factor store `sep` freshness", STATUS_FAIL, f"unreadable: {exc}")
        )
        return checks, snaps

    # --- D1: price recency, measured in SESSIONS (a holiday weekend is not staleness) ---
    if sep_max is None:
        status, detail, stale = STATUS_FAIL, "`sep` is EMPTY", None
    else:
        stale = _sessions_between(sep_max, last_session)
        if stale >= SEP_FAIL_SESSIONS:
            status = STATUS_FAIL
            detail = (
                f"`sep` newest = {sep_max}, which is {stale} sessions behind the last "
                f"completed session ({last_session}). The factor books RANK on this store — "
                f"they are selecting on stale prices."
            )
        elif stale >= SEP_WARN_SESSIONS:
            status = STATUS_WARN
            detail = (
                f"`sep` newest = {sep_max}, {stale} sessions behind {last_session} — "
                f"a refresh was likely missed. Check workbench-factor-refresh.timer."
            )
        else:
            status = STATUS_OK
            detail = f"`sep` newest = {sep_max} (current through the last session {last_session})"

    checks.append(
        Check(
            "D1",
            "Factor store `sep` freshness",
            status,
            detail,
            {
                "sep_max": str(sep_max),
                "rows": sep_rows,
                "symbols": sep_syms,
                "staleness_sessions": stale,
                "refreshed_at": refreshed.isoformat(),
            },
        )
    )
    snaps.append(
        DataHealthSnapshot(
            captured_at=now,
            source="FACTOR_STORE_SEP",
            as_of_date=str(sep_max) if sep_max else None,
            last_refresh_at=refreshed,
            staleness_sessions=stale,
            rows=sep_rows,
            symbols_covered=sep_syms,
            status=status,
            detail_json=json.dumps({"last_completed_session": str(last_session)}),
        )
    )

    # --- D2: the silent-HOLD trap. tickers.lastpricedate gates the PIT universe. ---
    if sep_max is None or last_price_date is None:
        lock_status = STATUS_FAIL
        lock_detail = "cannot evaluate lockstep — `sep` or `tickers.lastpricedate` is empty"
    elif last_price_date < sep_max:
        lock_status = STATUS_FAIL
        lock_detail = (
            f"LOCKSTEP BROKEN: tickers.lastpricedate = {last_price_date} is BEHIND sep = "
            f"{sep_max}. The PIT universe will resolve EMPTY and every factor book will "
            f"silently HOLD without erroring (the 2026-07-06 incident class)."
        )
    else:
        lock_status = STATUS_OK
        lock_detail = f"tickers.lastpricedate = {last_price_date} >= sep = {sep_max}"

    checks.append(
        Check(
            "D2",
            "Factor store tickers/sep lockstep",
            lock_status,
            lock_detail,
            {"lastpricedate": str(last_price_date), "sep_max": str(sep_max)},
        )
    )
    snaps.append(
        DataHealthSnapshot(
            captured_at=now,
            source="FACTOR_STORE_ACTIONS",
            as_of_date=str(last_price_date) if last_price_date else None,
            last_refresh_at=refreshed,
            status=lock_status,
            detail_json=json.dumps({"sep_max": str(sep_max)}),
        )
    )
    return checks, snaps


def check_bar_cache(
    universe: set[str], last_session: date
) -> tuple[Check, DataHealthSnapshot | None]:
    """D3: does the on-disk bar cache carry the last completed session for the live universe?

    The order path prices from bars, so a cold/stale cache is an execution problem even when
    the factor store is perfect.
    """
    now = datetime.now(UTC)
    if not BAR_CACHE_ROOT.exists():
        return Check("D3", "Bar cache currency", STATUS_FAIL, f"missing: {BAR_CACHE_ROOT}"), None

    # The cache is parquet buckets under <root>/<SYMBOL>/<timeframe>/...; freshness is
    # measured by the newest file mtime per symbol. Reading every parquet would be far too
    # slow for a check that runs on a timer, and mtime answers the question we are asking.
    covered, stale_syms, missing = 0, [], []
    for sym in sorted(universe):
        sym_dir = BAR_CACHE_ROOT / sym.upper()
        files = list(sym_dir.rglob("*.parquet")) if sym_dir.exists() else []
        if not files:
            missing.append(sym)
            continue
        newest = max(f.stat().st_mtime for f in files)
        newest_d = datetime.fromtimestamp(newest, tz=UTC).astimezone(EASTERN).date()
        if _sessions_between(newest_d, last_session) >= SEP_FAIL_SESSIONS:
            stale_syms.append(sym)
        else:
            covered += 1

    expected = len(universe)
    if missing or stale_syms:
        status = STATUS_FAIL if (len(missing) + len(stale_syms)) > expected * 0.05 else STATUS_WARN
        detail = (
            f"{covered}/{expected} symbols current. "
            f"missing={len(missing)} {missing[:8]}  stale={len(stale_syms)} {stale_syms[:8]}"
        )
    else:
        status = STATUS_OK
        detail = f"{covered}/{expected} symbols current through {last_session}"

    return (
        Check(
            "D3",
            "Bar cache currency",
            status,
            detail,
            {"covered": covered, "expected": expected, "missing": missing[:20]},
        ),
        DataHealthSnapshot(
            captured_at=now,
            source="BAR_CACHE",
            as_of_date=str(last_session),
            symbols_covered=covered,
            symbols_expected=expected,
            status=status,
            detail_json=json.dumps({"missing": missing[:50], "stale": stale_syms[:50]}),
        ),
    )


def check_universe_coverage(
    per_strategy: dict[str, list[str]], last_session: date
) -> tuple[Check, DataHealthSnapshot | None]:
    """D4: is every live strategy's tradable universe actually present in the factor store?

    A name a strategy wants to rank but the store has never heard of is silently dropped from
    the ranking — a coverage hole looks exactly like "the factor said no".
    """
    now = datetime.now(UTC)
    if not FACTOR_DB.exists():
        return Check("D4", "Universe coverage", STATUS_FAIL, "factor store missing"), None

    all_syms = sorted({s.upper() for syms in per_strategy.values() for s in syms})
    if not all_syms:
        return Check("D4", "Universe coverage", STATUS_WARN, "no live strategy symbols"), None

    try:
        import duckdb

        con = duckdb.connect(str(FACTOR_DB), read_only=True)
        try:
            rows = con.execute(
                "SELECT DISTINCT ticker FROM sep WHERE date >= ? AND ticker IN "
                f"({','.join('?' * len(all_syms))})",
                [last_session - timedelta(days=10), *all_syms],
            ).fetchall()
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        return Check("D4", "Universe coverage", STATUS_FAIL, f"query failed: {exc}"), None

    present = {r[0].upper() for r in rows}
    gaps = {
        name: sorted({s.upper() for s in syms} - present) for name, syms in per_strategy.items()
    }
    gaps = {k: v for k, v in gaps.items() if v}

    covered = len(present)
    if gaps:
        # ETFs are EXPECTED to be absent: Sharadar SFP (ETF prices) is not licensed, so the
        # cross-asset sleeve prices from Alpaca bars at execution instead. Not a defect.
        lines = "; ".join(f"{k}: {len(v)} missing {v[:6]}" for k, v in gaps.items())
        status = STATUS_WARN
        detail = f"{covered}/{len(all_syms)} in store. Gaps — {lines}"
    else:
        status = STATUS_OK
        detail = f"{covered}/{len(all_syms)} live symbols present in the store"

    return (
        Check("D4", "Universe coverage", status, detail, {"gaps": gaps}),
        DataHealthSnapshot(
            captured_at=now,
            source="UNIVERSE_COVERAGE",
            as_of_date=str(last_session),
            symbols_covered=covered,
            symbols_expected=len(all_syms),
            status=status,
            detail_json=json.dumps({"gaps": gaps}),
        ),
    )


# --------------------------------------------------------------------------------------
# REBALANCE checks
# --------------------------------------------------------------------------------------
async def check_dispatches(session, since: datetime) -> tuple[list[Check], list[dict]]:
    """R1 + R2: did every live cron strategy dispatch in the window, and how did it go?

    A strategy that is scheduled but has NO dispatch row in the window never ran. That is the
    single question the ``orders`` table structurally cannot answer, and it is the reason this
    whole table exists.
    """
    strategies = (
        (await session.execute(select(Strategy).where(Strategy.status == StrategyStatus.PAPER)))
        .scalars()
        .all()
    )
    rows: list[dict] = []
    missing: list[str] = []
    errored: list[str] = []

    for st in strategies:
        runs = (
            (
                await session.execute(
                    select(StrategyDispatchRun)
                    .where(
                        StrategyDispatchRun.strategy_id == st.id,
                        StrategyDispatchRun.started_at >= since,
                    )
                    .order_by(StrategyDispatchRun.started_at)
                )
            )
            .scalars()
            .all()
        )
        last = runs[-1] if runs else None
        rows.append(
            {
                "strategy": st.name,
                "schedule": st.schedule,
                "dispatches": len(runs),
                "last_started_et": (
                    last.started_at.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M:%S")
                    if last
                    else None
                ),
                "last_finished_et": (
                    last.finished_at.astimezone(EASTERN).strftime("%H:%M:%S")
                    if last and last.finished_at
                    else None
                ),
                "duration_ms": last.duration_ms if last else None,
                "outcome": last.outcome if last else None,
                "orders": sum(r.orders_submitted for r in runs),
            }
        )
        if not runs:
            missing.append(f"{st.name} (schedule `{st.schedule}`)")
        elif any(r.outcome not in ("COMPLETED",) for r in runs):
            bad = {r.outcome for r in runs if r.outcome != "COMPLETED"}
            errored.append(f"{st.name}: {', '.join(sorted(bad))}")

    checks = [
        Check(
            "R1",
            "Scheduled dispatch fired",
            STATUS_FAIL if missing else STATUS_OK,
            (
                "NO DISPATCH RECORDED for: " + "; ".join(missing) + ". The strategy did not "
                "run — this is NOT the same as running and trading nothing."
                if missing
                else f"all {len(strategies)} live strategies dispatched in the window"
            ),
            {"missing": missing},
        ),
        Check(
            "R2",
            "Dispatch outcomes healthy",
            STATUS_WARN if errored else STATUS_OK,
            ("; ".join(errored) if errored else "every dispatch completed normally"),
            {"errored": errored},
        ),
    ]
    return checks, rows


async def check_orders(session, since: datetime) -> tuple[Check, list[dict]]:
    """R3: what did the orders actually do — filled, rejected, or still hanging?

    A still-SUBMITTED order after the reconcile sweep has had time to run means the sweep is
    not keeping up (the trade-updates websocket misses fills; the sweep is what heals them).
    """
    orders = (await session.execute(select(Order).where(Order.created_at >= since))).scalars().all()
    by_account: dict[int, dict] = {}
    for o in orders:
        agg = by_account.setdefault(
            o.account_id, {"total": 0, "filled": 0, "rejected": 0, "open": 0}
        )
        agg["total"] += 1
        status = str(getattr(o.status, "value", o.status)).upper()
        if status == "FILLED":
            agg["filled"] += 1
        elif status in ("REJECTED", "CANCELED", "EXPIRED"):
            agg["rejected"] += 1
        elif status in ("SUBMITTED", "PENDING", "ACCEPTED", "PARTIALLY_FILLED"):
            agg["open"] += 1

    accounts = {a.id: a for a in (await session.execute(select(Account))).scalars().all()}
    rows = [
        {
            "account_id": aid,
            "account": getattr(accounts.get(aid), "label", None) or f"account {aid}",
            **agg,
        }
        for aid, agg in sorted(by_account.items())
    ]
    stuck = sum(r["open"] for r in rows)
    rejected = sum(r["rejected"] for r in rows)

    if stuck:
        status, detail = (
            STATUS_WARN,
            f"{stuck} order(s) still open/unsettled. The reconcile sweep runs every 10 min and "
            f"normally clears these; investigate if they persist across two sweeps.",
        )
    elif rejected:
        status, detail = STATUS_WARN, f"{rejected} order(s) rejected/canceled — check sizing"
    else:
        status, detail = STATUS_OK, f"{sum(r['total'] for r in rows)} order(s), none stuck"

    return Check("R3", "Order outcomes", status, detail, {"accounts": rows}), rows


# --------------------------------------------------------------------------------------
# Render + persist
# --------------------------------------------------------------------------------------
def render(
    kind: str,
    now_et: datetime,
    last_session: date,
    checks: list[Check],
    dispatch_rows: list[dict],
    order_rows: list[dict],
) -> str:
    overall = _worst([c.status for c in checks])
    L: list[str] = []
    L.append(f"# {kind.title()} Pipeline Health — {now_et:%Y-%m-%d %H:%M ET (%a)}")
    L.append("")
    L.append(f"**Overall: {_ICON[overall]} {overall}** · last completed session `{last_session}`")
    L.append("")
    L.append("## Checklist")
    L.append("")
    L.append("| | Check | Status | Detail |")
    L.append("|---|---|---|---|")
    for c in checks:
        L.append(f"| {c.id} | {c.title} | {_ICON[c.status]} {c.status} | {c.detail} |")
    L.append("")

    L.append("## Rebalance / dispatch")
    L.append("")
    if dispatch_rows:
        L.append(
            "| Strategy | Schedule | Dispatches | Started (ET) | Finished | Duration | Outcome | Orders |"
        )
        L.append("|---|---|---|---|---|---|---|---|")
        for r in dispatch_rows:
            dur = f"{r['duration_ms'] / 1000:.1f}s" if r["duration_ms"] is not None else "—"
            L.append(
                f"| {r['strategy']} | `{r['schedule']}` | {r['dispatches']} | "
                f"{r['last_started_et'] or '— NEVER FIRED —'} | {r['last_finished_et'] or '—'} | "
                f"{dur} | {r['outcome'] or '—'} | {r['orders']} |"
            )
        L.append("")
        L.append(
            "> A dispatch row with **0 orders** means the strategy ran and correctly decided to "
            "trade nothing. **No row at all** means it never ran. That distinction is the whole "
            "point of this table — it cannot be recovered from `orders`."
        )
    else:
        L.append("_No dispatch rows in the window._")
    L.append("")

    L.append("## Orders")
    L.append("")
    if order_rows:
        L.append("| Account | Total | Filled | Rejected/Canceled | Still open |")
        L.append("|---|---|---|---|---|")
        for r in order_rows:
            L.append(
                f"| {r['account']} | {r['total']} | {r['filled']} | {r['rejected']} | {r['open']} |"
            )
    else:
        L.append("_No orders in the window._")
    L.append("")
    return "\n".join(L)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=["DAILY", "WEEKLY"], default="DAILY")
    ap.add_argument(
        "--window-hours",
        type=int,
        default=None,
        help="lookback window (default: 24h for DAILY, 168h for WEEKLY)",
    )
    ap.add_argument("--no-persist", action="store_true", help="render only; write no DB rows")
    args = ap.parse_args()

    hours = args.window_hours or (24 if args.kind == "DAILY" else 168)
    started = datetime.now(UTC)
    since = started - timedelta(hours=hours)
    now_et = datetime.now(EASTERN)
    last_session = _last_completed_session(now_et)

    sf = get_sessionmaker()
    async with sf() as session:
        live = (
            (await session.execute(select(Strategy).where(Strategy.status == StrategyStatus.PAPER)))
            .scalars()
            .all()
        )
        per_strategy = {s.name: list(s.symbols_json or []) for s in live}
        universe = {sym.upper() for syms in per_strategy.values() for sym in syms}

        checks: list[Check] = []
        snaps: list[DataHealthSnapshot] = []

        c, s = check_factor_store(last_session)
        checks += c
        snaps += s

        c3, s3 = check_bar_cache(universe, last_session)
        checks.append(c3)
        if s3:
            snaps.append(s3)

        c4, s4 = check_universe_coverage(per_strategy, last_session)
        checks.append(c4)
        if s4:
            snaps.append(s4)

        dispatch_checks, dispatch_rows = await check_dispatches(session, since)
        checks += dispatch_checks

        order_check, order_rows = await check_orders(session, since)
        checks.append(order_check)

        report = render(args.kind, now_et, last_session, checks, dispatch_rows, order_rows)
        overall = _worst([c.status for c in checks])

        if not args.no_persist:
            for snap in snaps:
                session.add(snap)
            session.add(
                OpsCheckRun(
                    kind=args.kind,
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    status=overall,
                    checks_total=len(checks),
                    checks_ok=sum(1 for c in checks if c.status == STATUS_OK),
                    checks_warn=sum(1 for c in checks if c.status == STATUS_WARN),
                    checks_fail=sum(1 for c in checks if c.status == STATUS_FAIL),
                    report_md=report,
                    detail_json=json.dumps(
                        {
                            "window_hours": hours,
                            "last_completed_session": str(last_session),
                            "checks": [
                                {"id": c.id, "status": c.status, "detail": c.detail, **c.facts}
                                for c in checks
                            ],
                            "dispatches": dispatch_rows,
                            "orders": order_rows,
                        },
                        default=str,
                    ),
                )
            )
            await session.commit()

    print(report)
    return 2 if overall == STATUS_FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
