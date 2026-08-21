"""Factual D1/D5/D10/D20/CURRENT checkpoints and basis-safe returns.

Research plane (ADR 0051). Pure functions — no DB, no factor-store I/O, no
MDQ, no order path. A return is computed only when the later print uses the
same ``adjustment_basis`` as the proposal. Mixed-basis later prices may still
be shown as labelled facts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

CHECKPOINT_OFFSETS: tuple[tuple[str, int], ...] = (
    ("D1", 1),
    ("D5", 5),
    ("D10", 10),
    ("D20", 20),
)


@dataclass(frozen=True)
class CheckpointFact:
    checkpoint: str
    price: float | None
    price_as_of: str | None
    price_source: str | None
    adjustment_basis: str | None
    return_pct: float | None


def parse_iso_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def nth_session_after(
    sessions: Sequence[date],
    origin: date,
    n: int,
) -> date | None:
    """Nth trading session strictly after ``origin`` (n=1 is D1)."""
    if n < 1:
        return None
    later = [d for d in sessions if d > origin]
    if len(later) < n:
        return None
    return later[n - 1]


def adjusted_return(
    proposal_price: float | None,
    later_price: float | None,
    *,
    proposal_basis: str,
    later_basis: str,
) -> float | None:
    """``(later / proposal) - 1`` when bases match; otherwise None."""
    if proposal_basis != later_basis:
        return None
    if proposal_price is None or later_price is None:
        return None
    if proposal_price == 0:
        return None
    return (later_price / proposal_price) - 1.0


def build_checkpoints(
    *,
    proposal_price: float,
    proposal_basis: str,
    proposal_source: str,
    candidate_date: date,
    sessions: Sequence[tuple[date, float]],
    later_source: str,
    later_basis: str,
) -> tuple[CheckpointFact, ...]:
    """PROPOSAL + D1/D5/D10/D20 + CURRENT.

    ``sessions`` is the symbol's ordered (date, adjusted close) series covering
    at least ``candidate_date`` through the latest available print. D-offsets
    count that symbol's own later sessions, not calendar days.
    """
    ordered = sorted(sessions, key=lambda row: row[0])
    session_dates = [row[0] for row in ordered]
    by_date = {row[0]: row[1] for row in ordered}

    facts: list[CheckpointFact] = [
        CheckpointFact(
            checkpoint="PROPOSAL",
            price=proposal_price,
            price_as_of=candidate_date.isoformat(),
            price_source=proposal_source,
            adjustment_basis=proposal_basis,
            return_pct=0.0,
        )
    ]
    for name, n in CHECKPOINT_OFFSETS:
        when = nth_session_after(session_dates, candidate_date, n)
        price = by_date.get(when) if when is not None else None
        facts.append(
            CheckpointFact(
                checkpoint=name,
                price=price,
                price_as_of=when.isoformat() if when is not None else None,
                price_source=later_source if price is not None else None,
                adjustment_basis=later_basis if price is not None else None,
                return_pct=adjusted_return(
                    proposal_price,
                    price,
                    proposal_basis=proposal_basis,
                    later_basis=later_basis,
                )
                if price is not None
                else None,
            )
        )

    on_or_after = [row for row in ordered if row[0] >= candidate_date]
    current = on_or_after[-1] if on_or_after else None
    current_price = current[1] if current is not None else None
    current_as_of = current[0].isoformat() if current is not None else None
    facts.append(
        CheckpointFact(
            checkpoint="CURRENT",
            price=current_price,
            price_as_of=current_as_of,
            price_source=later_source if current_price is not None else None,
            adjustment_basis=later_basis if current_price is not None else None,
            return_pct=adjusted_return(
                proposal_price,
                current_price,
                proposal_basis=proposal_basis,
                later_basis=later_basis,
            ),
        )
    )
    return tuple(facts)
