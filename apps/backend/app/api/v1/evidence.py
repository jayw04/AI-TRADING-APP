"""Read-only Evidence Dashboard endpoint (P13) — the live evidence summary for the UI.

Surfaces, from the API (not report files), what the platform's evidence story is *right now*: the
**Production Confidence Score** (`app.ops.confidence`), the **Operational KPI scorecard**
(`app.ops.kpis`), the **research-program registry** (`app.research.programs`), and the **live
strategy books**. The dashboard reads this; the report scripts remain the printable artifacts.

Read-only; no order path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.account import Account, AccountMode
from app.db.models.audit_log import AuditLog
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.reconciliation_run import ReconciliationRun
from app.db.models.replay_run import ReplayRun
from app.db.models.strategy import Strategy
from app.db.session import get_session
from app.licensing import ALPACA_MARKET_DATA, OWNER_GENERATED_RECORDS, PERSONAL_FOOTER, footer_for
from app.licensing.gate import safe_effective_scope
from app.licensing.scopes import combine_scopes
from app.ops.confidence import ConfidenceSignals, compute_confidence
from app.ops.kpis import KpiInputs, build_scorecard, scorecard_summary
from app.research.programs import list_programs, status_counts

router = APIRouter(prefix="/evidence", tags=["evidence"])

# PU-1: the page is a presentable surface (it has a Print button), so every PANEL declares its own
# licence scope from what it is actually built from, and the top-level scope is the combined
# most-restrictive one (taint propagates). A panel built only from the owner's own account /
# order / gate-refusal / uptime records is ``owner_generated_records`` (COMMERCIAL_OK); anything
# built on market data, quotes, fills marked to market or backtests carries those vendor sources
# and is PERSONAL/UNKNOWN. Edit ONLY together with the registry.
#
# Panels and why:
#   confidence          counts from audit_log / reconciliation_runs / replay_runs / snapshot dates.
#   kpis                every row is a count or ratio of the same owner records (see _KPI_ROW_SOURCES).
#   research_programs   Sharpe / PF / drawdown headlines from backtests on licensed vendor data.
#   research_status_counts  derived from research_programs, so it inherits that lineage.
#   strategies          the owner's strategy configuration rows (name, status, vol-target params).
_OWNER_RECORDS: tuple[str, ...] = (OWNER_GENERATED_RECORDS,)
_RESEARCH_SOURCES: tuple[str, ...] = (ALPACA_MARKET_DATA, "sharadar", "fmp", "quiver")
_PANEL_SOURCES: dict[str, tuple[str, ...]] = {
    "confidence": _OWNER_RECORDS,
    "kpis": _OWNER_RECORDS,
    "research_programs": _RESEARCH_SOURCES,
    "research_status_counts": _RESEARCH_SOURCES,
    "strategies": _OWNER_RECORDS,
}
# KPI rows split by their own sources. A row that touches market data (slippage vs quotes, fill
# quality, P&L marked to market) must be listed here with the market-data source so it stays PERSONAL.
_KPI_ROW_SOURCES: dict[str, tuple[str, ...]] = {
    "reconciliation_success": _OWNER_RECORDS,
    "reconciliation_drift": _OWNER_RECORDS,
    "replay_consistency": _OWNER_RECORDS,
    "risk_gate_efficacy": _OWNER_RECORDS,
    "breaker_recovery": _OWNER_RECORDS,
    "fill_success": _OWNER_RECORDS,
    "operational_continuity": _OWNER_RECORDS,
}
# A KPI row with no declared sources (a new row nobody classified) is UNKNOWN, never owner records.


def _license_block(sources: tuple[str, ...]) -> dict[str, Any]:
    """``license_scope`` / ``license_sources`` / ``license_footer`` for one panel or row. An empty
    source list is UNKNOWN (fail closed); the footer is present whenever presentation is blocked."""
    scope = safe_effective_scope(sources=sources)
    return {
        "license_scope": scope.name,
        "license_sources": list(sources),
        "license_footer": PERSONAL_FOOTER if footer_for(scope) else None,
    }


async def _scalar(session: AsyncSession, stmt: Any) -> Any:
    return (await session.execute(stmt)).scalar()


async def _resolve_scope(
    session: AsyncSession, strategy_id: int | None
) -> tuple[int | None, int | None]:
    """(user_id, account_id) for a strategy's owner + its dedicated Alpaca paper account, or
    (None, None) for the platform-wide (unscoped) summary. Mirrors ``app.ops.evidence_scope``."""
    if strategy_id is None:
        return None, None
    user_id = await _scalar(session, select(Strategy.user_id).where(Strategy.id == strategy_id))
    account_id = None
    if user_id is not None:
        account_id = await _scalar(session, select(Account.id).where(
            Account.user_id == user_id, Account.broker == "alpaca",
            Account.mode == AccountMode.paper).order_by(Account.id).limit(1))
    return user_id, account_id


@router.get("/summary")
async def evidence_summary(
    strategy_id: int | None = Query(
        None, description="Scope the summary to ONE book (its account/user). Omit = platform-wide."),
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """The live evidence summary: confidence score + operational KPIs + research programs + books.

    Platform-wide by default; pass ``?strategy_id=`` to scope the confidence/KPI/equity aggregations
    to one book (account-scoped equity/reconciliation, user-scoped audit; replay stays platform-wide)."""
    user_id, account_id = await _resolve_scope(session, strategy_id)

    def _audit_stmt() -> Any:
        stmt = select(AuditLog.action, func.count()).group_by(AuditLog.action)
        return stmt.where(AuditLog.user_id == user_id) if user_id is not None else stmt

    def _recon(stmt: Any) -> Any:
        return stmt.where(ReconciliationRun.account_id == account_id) if account_id is not None else stmt

    def _equity(stmt: Any) -> Any:
        return stmt.where(EquitySnapshot.account_id == account_id) if account_id is not None else stmt

    audit = {a: n for a, n in (await session.execute(_audit_stmt())).all()}

    recon_runs = await _scalar(session, _recon(select(func.count()).select_from(ReconciliationRun))) or 0
    recon_pass = await _scalar(
        session, _recon(select(func.count()).select_from(ReconciliationRun).where(
            ReconciliationRun.result == "pass"))) or 0
    recon_disc = await _scalar(
        session, _recon(select(func.coalesce(func.sum(ReconciliationRun.n_discrepancies), 0)))) or 0
    replay_checked = await _scalar(session, select(func.coalesce(func.sum(ReplayRun.n_checked), 0))) or 0
    replay_matched = await _scalar(session, select(func.coalesce(func.sum(ReplayRun.n_matched), 0))) or 0
    replay_mismatched = await _scalar(
        session, select(func.coalesce(func.sum(ReplayRun.n_mismatched), 0))) or 0
    first_snap = await _scalar(session, _equity(select(func.min(EquitySnapshot.ts))))
    actual_days = await _scalar(
        session, _equity(select(func.count(func.distinct(func.date(EquitySnapshot.ts)))))) or 0
    track_days = (datetime.now(UTC).date() - first_snap.date()).days if first_snap else 0

    signals = ConfidenceSignals(
        track_record_days=track_days,
        replay_mismatches=int(replay_mismatched) + audit.get("REPLAY_MISMATCH", 0),
        reconciliation_discrepancies=int(recon_disc) + audit.get("RECONCILIATION_DISCREPANCY", 0),
        reconciliation_runs=int(recon_runs),
        breaker_trips=audit.get("CIRCUIT_BREAKER_TRIPPED", 0),
        breaker_resets=audit.get("CIRCUIT_BREAKER_RESET", 0),
        orders_risk_passed=audit.get("ORDER_RISK_PASSED", 0),
        orders_rejected_by_risk=audit.get("ORDER_REJECTED_BY_RISK", 0),
        orders_rejected_by_broker=audit.get("ORDER_REJECTED_BY_BROKER", 0),
        fills_ingested=audit.get("ORDER_FILL_INGESTED", 0),
    )
    confidence = compute_confidence(signals)

    kpi_inputs = KpiInputs(
        reconciliation_runs=int(recon_runs), reconciliation_passes=int(recon_pass),
        reconciliation_discrepancies=int(recon_disc),
        replay_checked=int(replay_checked), replay_matched=int(replay_matched),
        orders_risk_passed=signals.orders_risk_passed,
        orders_rejected_by_risk=signals.orders_rejected_by_risk,
        orders_rejected_by_broker=signals.orders_rejected_by_broker,
        breaker_trips=signals.breaker_trips, breaker_resets=signals.breaker_resets,
        breaker_recovery_minutes=None,
        orders_submitted=audit.get("ORDER_SUBMITTED", 0), fills_ingested=signals.fills_ingested,
        expected_snapshot_days=(max(int(actual_days), round(track_days * 5 / 7)) if track_days
                                else int(actual_days)),
        actual_snapshot_days=int(actual_days),
    )
    kpis = build_scorecard(kpi_inputs)

    strat_stmt = select(Strategy).order_by(Strategy.id)
    if strategy_id is not None:
        strat_stmt = strat_stmt.where(Strategy.id == strategy_id)
    strat_rows = (await session.execute(strat_stmt)).scalars().all()
    strategies = [
        {"id": s.id, "name": s.name,
         "status": s.status.value if hasattr(s.status, "value") else str(s.status),
         "vol_target": (s.params_json or {}).get("vol_target_annual"),
         "vol_scaling": bool((s.params_json or {}).get("use_daily_overlay"))}
        for s in strat_rows
    ]

    scope = ({"kind": "account", "strategy_id": strategy_id,
              "account_id": account_id, "user_id": user_id}
             if strategy_id is not None else {"kind": "platform"})
    kpi_rows = [{**r, **_license_block(_KPI_ROW_SOURCES.get(str(r.get("key")), ()))} for r in kpis]
    panels = {name: _license_block(srcs) for name, srcs in _PANEL_SOURCES.items()}
    # The kpis panel is the most restrictive of its rows: the union of the rows' sources, or no
    # sources (UNKNOWN) if any row was never classified.
    row_sources = [tuple(r["license_sources"]) for r in kpi_rows]
    panels["kpis"] = _license_block(
        () if (not row_sources or not all(row_sources)) else tuple(sorted({s for r in row_sources for s in r}))
    )
    # Top level = combined most-restrictive scope (taken from the panels' SCOPES, so an
    # unclassified panel cannot be hidden by the other panels' sources).
    top_scope = combine_scopes(*(blk["license_scope"] for blk in panels.values()))
    top = {
        "license_scope": top_scope.name,
        "license_sources": sorted({s for blk in panels.values() for s in blk["license_sources"]}),
        "license_footer": PERSONAL_FOOTER if footer_for(top_scope) else None,
    }
    return {
        "as_of": datetime.now(UTC).isoformat(),
        **top,
        "panels": panels,
        "scope": scope,
        "confidence": confidence,
        "kpis": {"rows": kpi_rows, "summary": scorecard_summary(kpis)},
        "research_programs": list_programs(),
        "research_status_counts": status_counts(),
        "strategies": strategies,
    }
