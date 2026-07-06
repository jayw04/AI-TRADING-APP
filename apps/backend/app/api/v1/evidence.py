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
from app.ops.confidence import ConfidenceSignals, compute_confidence
from app.ops.kpis import KpiInputs, build_scorecard, scorecard_summary
from app.research.programs import list_programs, status_counts

router = APIRouter(prefix="/evidence", tags=["evidence"])


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
    return {
        "as_of": datetime.now(UTC).isoformat(),
        "scope": scope,
        "confidence": confidence,
        "kpis": {"rows": kpis, "summary": scorecard_summary(kpis)},
        "research_programs": list_programs(),
        "research_status_counts": status_counts(),
        "strategies": strategies,
    }
