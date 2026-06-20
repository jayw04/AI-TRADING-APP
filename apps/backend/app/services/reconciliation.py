"""Reconciliation service (P11 §3, ADR 0021) — broker ⇄ local, ALERT-ONLY.

Determines whether observed reality (the broker) matches expected state (local) and
**surfaces** discrepancies (audit + metric + a `reconciliation_runs` row); it **never
changes portfolio state** — no order path, no position mutation. (Same one-subsystem-
executes discipline as ADR 0019/0020/0021.)

Pipeline: detect (diff) → classify (domain · severity) → persist → surface → owner.

Domains:
- **position** — broker `get_positions()` ⇄ local `positions` table (this session).
- **intent** — the automation's target ⇄ achieved. *Deferred*: the overlay fingerprint is
  not yet persisted to a durable, queryable store (it is logged to a non-resolving signal),
  and the overlays are default-off/NO-GO — so there is nothing to reconcile yet. The domain
  slot + framework are in place; `reconcile_intent` returns no discrepancies until durable
  overlay-target persistence lands (a small future overlay change).

Reconcile ≠ sync: this does an INDEPENDENT fresh broker fetch, so it also catches a stalled
PositionSync (a two-stored-snapshot diff would not).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.models.position import Position
from app.db.models.reconciliation_run import ReconciliationRun
from app.db.models.symbol import Symbol
from app.observability.metrics import (
    automation_runs_total,
    reconciliation_discrepancies_total,
    reconciliation_duration_seconds,
)

logger = structlog.get_logger(__name__)

ALGORITHM_VERSION = "1.0"
_DEFAULT_QTY_EPS = Decimal("0.000001")  # fractional-share epsilon (P10 §7)


@dataclass(frozen=True)
class Discrepancy:
    domain: str       # 'position' | 'intent'
    kind: str         # 'qty_mismatch' | 'missing_local' | 'missing_broker' | 'gross_drift'
    severity: str     # 'low' | 'medium' | 'high' | 'critical'
    symbol: str | None
    local: str | None
    broker: str | None
    note: str = ""


async def _local_qty_by_ticker(session: AsyncSession, account_id: int) -> dict[str, Decimal]:
    rows = (
        await session.execute(
            select(Symbol.ticker, Position.qty)
            .join(Position, Position.symbol_id == Symbol.id)
            .where(Position.account_id == account_id, Position.qty != Decimal(0))
        )
    ).all()
    return {t.upper(): Decimal(str(q)) for t, q in rows}


def _broker_qty_by_ticker(raw: list[dict[str, Any]]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for p in raw:
        sym = str(p.get("symbol") or p.get("ticker") or "").upper()
        if not sym:
            continue
        try:
            out[sym] = Decimal(str(p.get("qty", p.get("quantity", "0"))))
        except Exception:  # noqa: BLE001 — a malformed row is itself a discrepancy-adjacent issue
            out[sym] = Decimal(0)
    return out


def diff_positions(
    local: dict[str, Decimal], broker: dict[str, Decimal], *, qty_eps: Decimal = _DEFAULT_QTY_EPS
) -> list[Discrepancy]:
    """Pure position diff (testable without I/O). Position mismatches are HIGH severity."""
    out: list[Discrepancy] = []
    for sym in sorted(set(local) | set(broker)):
        lq, bq = local.get(sym), broker.get(sym)
        if lq is not None and bq is None:
            out.append(Discrepancy("position", "missing_broker", "high", sym, str(lq), None,
                                   "local holds a position the broker does not"))
        elif bq is not None and lq is None:
            out.append(Discrepancy("position", "missing_local", "high", sym, None, str(bq),
                                   "broker holds a position local does not"))
        elif lq is not None and bq is not None and abs(lq - bq) > qty_eps:
            out.append(Discrepancy("position", "qty_mismatch", "high", sym, str(lq), str(bq),
                                   "quantity mismatch"))
    return out


async def reconcile_intent(session: AsyncSession, account_id: int) -> list[Discrepancy]:
    """Intent domain (deferred — see module docstring). No durable overlay-target source
    exists yet and the overlays are off, so there is nothing to reconcile. Returns []."""
    return []


async def run_reconciliation(
    session: AsyncSession, broker: Any, account_id: int, *, qty_eps: Decimal = _DEFAULT_QTY_EPS
) -> ReconciliationRun:
    """Reconcile the position domain for one account: fetch the broker (read-only),
    diff vs local, persist a `reconciliation_runs` row, and surface any discrepancy
    (audit + metric). NEVER submits orders or mutates positions. Records `unavailable`
    if the broker is unreachable (no conclusion drawn), `error` on an internal failure."""
    started = time.monotonic()
    result = "pass"
    discrepancies: list[Discrepancy] = []
    n_checked = 0
    try:
        local = await _local_qty_by_ticker(session, account_id)
        try:
            raw = await asyncio.to_thread(broker.get_positions)
        except Exception:  # noqa: BLE001 — broker unreachable → no reconciliation occurred
            result = "unavailable"
            raw = None
        if raw is not None:
            broker_q = _broker_qty_by_ticker(raw)
            n_checked = len(set(local) | set(broker_q))
            discrepancies = diff_positions(local, broker_q, qty_eps=qty_eps)
            result = "fail" if discrepancies else "pass"
    except Exception:  # noqa: BLE001 — internal failure (DB, etc.) → error, never raise into the job
        result = "error"

    duration_ms = int((time.monotonic() - started) * 1000)
    run = ReconciliationRun(
        account_id=account_id, ran_at=datetime.now(UTC), domain="position", result=result,
        n_checked=n_checked, n_discrepancies=len(discrepancies), duration_ms=duration_ms,
        algorithm_version=ALGORITHM_VERSION,
        detail_json=json.dumps([asdict(d) for d in discrepancies]) if discrepancies else None,
    )
    session.add(run)

    # Surface (alert-only): audit each discrepancy + metrics. No corrective orders.
    for d in discrepancies:
        AuditLogger.write(
            session, actor_type=AuditActorType.SYSTEM, actor_id="reconciliation",
            action=AuditAction.RECONCILIATION_DISCREPANCY, target_type="account",
            target_id=account_id, payload=asdict(d),
        )
        reconciliation_discrepancies_total.labels(domain=d.domain, severity=d.severity).inc()
    automation_runs_total.labels(actor="reconciliation", outcome=result).inc()
    reconciliation_duration_seconds.observe(time.monotonic() - started)
    await session.commit()
    return run


async def run_reconciliation_pass(
    session_factory: async_sessionmaker[AsyncSession], resolve_broker: Callable[[int], Any]
) -> None:
    """Scheduler entrypoint (P11 §3): reconcile every account with open positions against
    its OWN broker adapter (``resolve_broker(account_id)`` — e.g. ``BrokerRegistry.get``).
    Best-effort per account; never raises into the scheduler. An account with no resolvable
    adapter is skipped. Read-only + alert-only (no order path)."""
    try:
        async with session_factory() as session:
            account_ids = (
                await session.execute(
                    select(Position.account_id).where(Position.qty != Decimal(0)).distinct()
                )
            ).scalars().all()
        for account_id in account_ids:
            broker = resolve_broker(account_id)
            if broker is None:
                continue
            try:
                async with session_factory() as s:
                    await run_reconciliation(s, broker, account_id)
            except Exception:
                logger.exception("reconciliation_account_failed", account_id=account_id)
    except Exception:
        logger.exception("reconciliation_pass_failed")
