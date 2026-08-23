"""Read-time “Why it left” — frozen-rule re-evaluation, not a sell/exit.

Research plane (ADR 0051). Pure functions — no DB, no factor-store I/O, no
MDQ, no order path. Admission eligibility is imported from ``engine`` so
thresholds cannot drift independently of the live screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.research.disc001.engine import (
    FrozenGateObservation,
    mom_near_eligible,
    mom_near_family_observations,
    mom_near_gate_observations,
    oversold_eligible,
    oversold_family_observations,
    oversold_gate_observations,
    screen_gap,
    screen_mom_core,
)
from app.research.disc001.features import GapRow, MomCoreRow, SymbolFeatures
from app.research.disc001.spec import PRICE_SOURCE_GAP, PRICE_SOURCE_SEP, FamilyId

NOT_A_SIGNAL = "Frozen-rule display, not a sell or exit signal."


def latest_session_after(sessions: Sequence[date], origin: date) -> date | None:
    """Latest session strictly after ``origin``. None if no later bar exists."""
    later = [d for d in sessions if d > origin]
    return later[-1] if later else None


STATE_STILL_MEETS = "still_meets"
STATE_NO_LONGER_MEETS = "no_longer_meets"
STATE_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class WhyLeft:
    family: str
    state: str
    as_of: str | None
    summary: str | None
    details: tuple[str, ...]
    not_a_signal: str = NOT_A_SIGNAL


def _unavailable(family: str, *, as_of: str | None = None, reason: str | None = None) -> WhyLeft:
    return WhyLeft(
        family=family,
        state=STATE_UNAVAILABLE,
        as_of=as_of,
        summary=None,
        details=(reason,) if reason else (),
    )


def _failed_summaries(
    family_obs: Sequence[FrozenGateObservation],
    all_obs: Sequence[FrozenGateObservation],
) -> tuple[str, ...]:
    family_failed = tuple(obs.summary for obs in family_obs if not obs.passed)
    if family_failed:
        return family_failed
    return tuple(obs.summary for obs in all_obs if not obs.passed)


def _no_longer(family: str, as_of: str, clauses: Sequence[str]) -> WhyLeft:
    joined = "; ".join(clauses) if clauses else "frozen rule no longer holds"
    return WhyLeft(
        family=family,
        state=STATE_NO_LONGER_MEETS,
        as_of=as_of,
        summary=f"No longer {family}: {joined}.",
        details=tuple(clauses),
    )


def _still(family: str, as_of: str) -> WhyLeft:
    return WhyLeft(
        family=family,
        state=STATE_STILL_MEETS,
        as_of=as_of,
        summary=f"Still {family}: frozen rule still holds as of {as_of}.",
        details=(),
    )


def explain_oversold(feat: SymbolFeatures | None, *, later_as_of: date | None) -> WhyLeft:
    family = str(FamilyId.OVERSOLD)
    if later_as_of is None or feat is None:
        return _unavailable(family, reason="no later Sharadar SEP bar")
    as_of = later_as_of.isoformat()
    if oversold_eligible(feat):
        return _still(family, as_of)
    clauses = _failed_summaries(
        oversold_family_observations(feat),
        oversold_gate_observations(feat),
    )
    return _no_longer(family, as_of, clauses)


def explain_mom_near(
    feat: SymbolFeatures | None,
    *,
    later_as_of: date | None,
    mom_core_symbols: frozenset[str],
) -> WhyLeft:
    family = str(FamilyId.MOM_NEAR)
    if later_as_of is None or feat is None:
        return _unavailable(family, reason="no later Sharadar SEP bar")
    as_of = later_as_of.isoformat()
    if mom_near_eligible(feat, mom_core_symbols):
        return _still(family, as_of)
    clauses = _failed_summaries(
        mom_near_family_observations(feat, mom_core_symbols),
        mom_near_gate_observations(feat, mom_core_symbols),
    )
    return _no_longer(family, as_of, clauses)


def explain_mom_core(
    symbol: str,
    *,
    later_as_of: date | None,
    later_rows: tuple[MomCoreRow, ...] | None,
    available: bool,
) -> WhyLeft:
    family = str(FamilyId.MOM_CORE)
    if later_as_of is None:
        return _unavailable(family, reason="no later Sharadar SEP bar")
    if not available or later_rows is None:
        return _unavailable(
            family, as_of=later_as_of.isoformat(), reason="later MOM-001 readout unavailable"
        )
    as_of = later_as_of.isoformat()
    result = screen_mom_core(
        later_rows, available=True, unavailable_reason=None, price_source=PRICE_SOURCE_SEP
    )
    members = {card.symbol for card in result.items}
    if symbol in members:
        return _still(family, as_of)
    return _no_longer(family, as_of, ("not in the frozen MOM-001 readout",))


def explain_gap(
    symbol: str,
    *,
    later_as_of: date | None,
    later_rows: tuple[GapRow, ...] | None,
    available: bool,
) -> WhyLeft:
    family = str(FamilyId.GAP)
    if later_as_of is None:
        return _unavailable(family, reason="no later governed gappers file")
    if not available or later_rows is None:
        return _unavailable(
            family, as_of=later_as_of.isoformat(), reason="later governed gappers file unavailable"
        )
    as_of = later_as_of.isoformat()
    result = screen_gap(
        later_rows, available=True, unavailable_reason=None, price_source=PRICE_SOURCE_GAP
    )
    members = {card.symbol for card in result.items}
    if symbol in members:
        return _still(family, as_of)
    return _no_longer(family, as_of, ("not in the later governed gappers file",))


def explain_why_left(
    *,
    family: str,
    symbol: str,
    later_as_of: date | None,
    feat: SymbolFeatures | None = None,
    mom_core_symbols: frozenset[str] = frozenset(),
    mom_core_rows: tuple[MomCoreRow, ...] | None = None,
    mom_core_available: bool = False,
    gap_rows: tuple[GapRow, ...] | None = None,
    gap_available: bool = False,
) -> WhyLeft:
    """Re-evaluate the frozen family rule. Not a sell, exit, or MDQ path."""
    if family == FamilyId.OVERSOLD:
        return explain_oversold(feat, later_as_of=later_as_of)
    if family == FamilyId.MOM_NEAR:
        return explain_mom_near(feat, later_as_of=later_as_of, mom_core_symbols=mom_core_symbols)
    if family == FamilyId.MOM_CORE:
        return explain_mom_core(
            symbol,
            later_as_of=later_as_of,
            later_rows=mom_core_rows,
            available=mom_core_available,
        )
    if family == FamilyId.GAP:
        return explain_gap(
            symbol,
            later_as_of=later_as_of,
            later_rows=gap_rows,
            available=gap_available,
        )
    return _unavailable(family, reason="unknown family")
