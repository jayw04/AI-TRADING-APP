"""User-level in-flight paper-variant list (P6b §2c-variant).

GET /api/v1/variants — the in-flight PAPER_VARIANT strategies owned by the user,
for the Dashboard "Active Validations" widget. One call instead of a per-strategy
fan-out (the §1b-drift drift-findings lesson).

A fresh module (not strategies.py) keeps this off the P2 branch-coverage gate,
the same reason §1b/§2b put strategies-scoped reads on proposals.py and
drift-findings on drift.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.session import get_session

router = APIRouter(tags=["variants"])


class InFlightVariant(BaseModel):
    variant_strategy_id: int
    parent_strategy_id: int | None
    parent_strategy_name: str | None
    parent_strategy_status: str | None
    spawn_proposal_id: int | None
    spawned_at: str | None


class InFlightVariantListResponse(BaseModel):
    items: list[InFlightVariant]


@router.get("/variants", response_model=InFlightVariantListResponse)
async def list_in_flight_variants(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> InFlightVariantListResponse:
    """The user's in-flight paper variants (status=PAPER_VARIANT) with their
    parent's name/status + the spawn proposal id. Empty list when none."""
    variants = (
        await session.execute(
            select(Strategy)
            .where(Strategy.user_id == current_user.id)
            .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
            .order_by(Strategy.id.desc())
        )
    ).scalars().all()

    items: list[InFlightVariant] = []
    for variant in variants:
        parent = (
            await session.get(Strategy, variant.parent_strategy_id)
            if variant.parent_strategy_id is not None
            else None
        )
        # Spawn proposal = the parent's EVALUATING proposal (no FK column; the
        # linkage lives on the proposal — mirrors proposals.py's derivation).
        spawn_proposal_id: int | None = None
        if variant.parent_strategy_id is not None:
            prop = (
                await session.execute(
                    select(StrategyProposal)
                    .where(StrategyProposal.strategy_id == variant.parent_strategy_id)
                    .where(StrategyProposal.state == ProposalState.EVALUATING)
                    .order_by(StrategyProposal.id.desc())
                )
            ).scalars().first()
            spawn_proposal_id = prop.id if prop else None

        items.append(
            InFlightVariant(
                variant_strategy_id=variant.id,
                parent_strategy_id=variant.parent_strategy_id,
                parent_strategy_name=parent.name if parent else None,
                parent_strategy_status=parent.status.value if parent else None,
                spawn_proposal_id=spawn_proposal_id,
                spawned_at=(
                    variant.created_at.isoformat() if variant.created_at else None
                ),
            )
        )
    return InFlightVariantListResponse(items=items)
