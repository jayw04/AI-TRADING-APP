"""REST endpoints for the Trade Journal.

GET /api/v1/journal                      — the user's executed trades + notes
PUT /api/v1/journal/{order_id}/note      — upsert the free-text note on a trade

A journal entry is a *filled* order rendered as a trade (symbol, side, qty, avg
fill price, value, source) plus a free-text note the trader owns. Read-only over
the order/fill data; the only write is the note. Per-user scoped, like every
other page.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.schemas.journal import (
    JournalEntry,
    JournalListResponse,
    NoteResponse,
    NoteUpdateRequest,
)
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import OrderSourceType, OrderStatus
from app.db.models.journal_note import JournalNote
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.session import get_session

router = APIRouter(prefix="/journal", tags=["journal"])


def _source_label(
    source_type: OrderSourceType, source_id: str | None, strat_names: dict[str, str]
) -> str:
    """A human label for where a trade came from."""
    if source_type == OrderSourceType.MANUAL:
        return "Manual"
    if source_type == OrderSourceType.STRATEGY:
        return strat_names.get(source_id or "", f"Strategy #{source_id}" if source_id else "Strategy")
    if source_type == OrderSourceType.PINE:
        return "Pine / TradingView"
    # agent_* and any future sources
    label = source_type.value.replace("_", " ").title()
    if source_id:
        label = f"{label} #{source_id}"
    return label


@router.get("", response_model=JournalListResponse)
async def list_journal(
    limit: int = 200,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JournalListResponse:
    limit = max(1, min(limit, 500))
    orders = (
        await session.execute(
            select(Order)
            .options(selectinload(Order.fills))
            .where(
                Order.user_id == current_user.id,
                Order.status == OrderStatus.FILLED,
            )
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    if not orders:
        return JournalListResponse(items=[], count=0)

    # Batch-resolve symbols, strategy names, and notes (avoid N+1).
    symbol_ids = {o.symbol_id for o in orders if o.symbol_id}
    sym_rows = (
        await session.execute(select(Symbol).where(Symbol.id.in_(symbol_ids)))
    ).scalars().all() if symbol_ids else []
    tickers = {s.id: s.ticker for s in sym_rows}

    strat_ids = {
        int(o.source_id)
        for o in orders
        if o.source_type == OrderSourceType.STRATEGY
        and o.source_id
        and o.source_id.isdigit()
    }
    strat_names: dict[str, str] = {}
    if strat_ids:
        for s in (
            await session.execute(select(Strategy).where(Strategy.id.in_(strat_ids)))
        ).scalars().all():
            strat_names[str(s.id)] = s.name

    order_ids = [o.id for o in orders]
    notes = {
        n.order_id: n.note
        for n in (
            await session.execute(
                select(JournalNote).where(JournalNote.order_id.in_(order_ids))
            )
        ).scalars().all()
    }

    items: list[JournalEntry] = []
    for o in orders:
        total_qty = sum((f.qty for f in o.fills), Decimal(0))
        total_val = sum((f.qty * f.price for f in o.fills), Decimal(0))
        avg = (total_val / total_qty) if total_qty else None
        # latest fill time, else submitted/created
        filled_at = None
        if o.fills:
            filled_at = max(f.filled_at for f in o.fills)
        filled_at = filled_at or o.submitted_at or o.created_at
        items.append(
            JournalEntry(
                order_id=o.id,
                symbol=tickers.get(o.symbol_id, "?"),
                side=o.side.value,
                qty=o.qty,
                avg_fill_price=avg,
                value=total_val if total_qty else None,
                source_type=o.source_type.value,
                source_id=o.source_id,
                source_label=_source_label(o.source_type, o.source_id, strat_names),
                filled_at=filled_at,
                note=notes.get(o.id, ""),
            )
        )
    return JournalListResponse(items=items, count=len(items))


@router.put("/{order_id}/note", response_model=NoteResponse)
async def upsert_note(
    order_id: int,
    body: NoteUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NoteResponse:
    # Ownership: the order must exist and belong to the caller.
    order = (
        await session.execute(
            select(Order).where(
                Order.id == order_id, Order.user_id == current_user.id
            )
        )
    ).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    now = datetime.now(UTC)
    existing = (
        await session.execute(
            select(JournalNote).where(JournalNote.order_id == order_id)
        )
    ).scalars().first()
    if existing is None:
        existing = JournalNote(
            user_id=current_user.id,
            order_id=order_id,
            note=body.note,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
    else:
        existing.note = body.note
        existing.updated_at = now
    await session.commit()
    return NoteResponse(order_id=order_id, note=body.note)
