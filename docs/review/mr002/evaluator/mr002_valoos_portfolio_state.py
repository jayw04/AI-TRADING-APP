"""MR-002 Increment 3 — immutable portfolio state (synthetic only).

Held positions, pending exits, cash, and one-position-per-symbol occupancy (PR-02/PR-16/PR-21, RC-3).
State transitions return a NEW immutable state; the replay module is the only writer. Pending exits
are carried and de-duplicated (RC-3: no duplicate exit orders).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class HeldPosition:
    position_id: str
    symbol: str
    side: str
    shares: int
    entry_session: int
    entry_date: str
    entry_open_price: float
    entry_notional: float
    sector_id: str
    beta: float
    permanent_security_id: str
    signal_origin_session: int
    entry_registered_signal_value: float       # clarification #1: immutable entry-z, drives drift order
    configuration_id: str
    originating_candidate_id: str               # clarification #1: actual field, not narrative
    eligibility_evidence_identity: str          # clarification #1: actual field


@dataclass(frozen=True)
class PendingExit:
    position_id: str
    symbol: str
    scheduled_exit_session: int
    decision_session: int
    decision_type: str                          # EXIT_DECISION | TIME_STOP_SCHEDULED_AT_ENTRY
    shares: int
    reason: str


@dataclass(frozen=True)
class PortfolioState:
    session: int
    cash: float
    held: tuple = field(default_factory=tuple)          # tuple[HeldPosition]
    pending: tuple = field(default_factory=tuple)       # tuple[PendingExit]

    def occupied_symbols(self) -> set:
        """One-position-per-symbol: symbols held OR with a pending exit are ineligible for new entry."""
        return {h.symbol for h in self.held} | {p.symbol for p in self.pending}

    def held_by_symbol(self) -> dict:
        return {h.symbol: h for h in self.held}

    def pending_position_ids(self) -> set:
        return {p.position_id for p in self.pending}

    def with_session(self, session: int) -> "PortfolioState":
        return replace(self, session=session)


def add_pending(state: PortfolioState, pe: PendingExit) -> PortfolioState:
    """Add a pending exit iff not already pending for that position (RC-3 dedup — no duplicate order)."""
    if pe.position_id in state.pending_position_ids():
        return state
    return replace(state, pending=state.pending + (pe,))


def commit_session(prior: PortfolioState, *, session: int, remaining_held: tuple, new_pending: tuple,
                   new_positions: tuple, cash: float) -> PortfolioState:
    """The ONLY writer: build the committed post-session immutable state."""
    return PortfolioState(session=session, cash=cash,
                          held=tuple(remaining_held) + tuple(new_positions),
                          pending=tuple(new_pending))
