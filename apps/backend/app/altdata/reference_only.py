"""EAD reference-only guardrail — the codified invariant that a REJECTED alt-data / event pattern
may be shown as context but must never enter ranking, sizing, or the order path.

Four EAD event-driven programs cleared the ≥100-benchmarked gate and were still **Rejected** after
sector/size/liquidity/momentum matching (INSIDER-001, GOVCONTRACT-001, CONGRESS-001, LOBBY-001) —
one finding: *public corporate-disclosure events carry no residual alpha*. Their event labels stay
useful as reference/context (the Opportunity Report, negative-evidence memory, the whitepaper), but
"buy because X spiked" is forbidden. Policy erodes; this is enforced in code — a runtime guard here
plus a CI invariant (`scripts/check_reference_only_invariant.sh`) that keeps the order-path /
ranking / selection modules clear of these labels, the way the single-router and no-LLM-in-order-path
invariants are enforced structurally rather than by reviewer diligence.

Governance: `docs/implementation/TradingWorkbench_EAD_DatasetTriage_v0.1.md` (v0.2, reference-use §).
Keep ``REFERENCE_ONLY_PROGRAMS`` in sync with the rejected EAD programs in
``app/research/programs.py`` — the test asserts each mapped program is ``status='rejected'``.
"""

from __future__ import annotations

from collections.abc import Iterable

# event_type -> the rejected EAD program that produced it (all Rejected as of 2026-07-07).
REFERENCE_ONLY_PROGRAMS: dict[str, str] = {
    "insider_buy": "INSIDER-001",
    "gov_contract_award": "GOVCONTRACT-001",
    "congress_trade": "CONGRESS-001",
    "lobby_spike": "LOBBY-001",
}
REFERENCE_ONLY_EVENT_TYPES: frozenset[str] = frozenset(REFERENCE_ONLY_PROGRAMS)


class ReferenceOnlyViolation(RuntimeError):
    """A rejected EAD event-label reached ranking / sizing / order-path logic — forbidden by the
    EAD reference-only invariant."""


def is_reference_only(event_type: str) -> bool:
    """True if ``event_type`` comes from a REJECTED EAD program (reference/context only)."""
    return event_type in REFERENCE_ONLY_EVENT_TYPES


def assert_usable_for_ranking(event_type: str) -> None:
    """Raise ``ReferenceOnlyViolation`` if ``event_type`` may not enter ranking / sizing / the order
    path. Call this at any boundary where an EAD event would influence selection or sizing."""
    if is_reference_only(event_type):
        raise ReferenceOnlyViolation(
            f"event_type {event_type!r} is from a REJECTED EAD program "
            f"({REFERENCE_ONLY_PROGRAMS[event_type]}) — reference/context only; it must not enter "
            f"ranking, sizing, or the order path (EAD reference-only invariant)."
        )


def partition_reference_only(event_types: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split ``event_types`` into ``(usable, reference_only)``. Display code may render the
    reference-only labels (tagged as such); ranking / sizing code must consume only ``usable``."""
    usable: list[str] = []
    reference_only: list[str] = []
    for event_type in event_types:
        (reference_only if is_reference_only(event_type) else usable).append(event_type)
    return usable, reference_only
