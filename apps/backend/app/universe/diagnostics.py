"""One operator vocabulary for ownership refusals, across all three paths (PR S / S6).

Ownership excludes a position in three different places — the normal rebalance exit, LIVE
liquidation, and PAPER liquidation — and until now each was silent or logged in its own
shape. An operator investigating "why didn't LOW-001 close that?" had to know which code
path they were in before they could look. This module gives all three the same event
names and the same fields, so the question is answerable once.

## Events

============================== ======== ==========================================
``ownership_ambiguous``        warning  competing ownership / competing acquisition
``ownership_identity_unresolved`` warning  security-lineage problem
``ownership_evidence_missing`` warning  held, but no acquisition record at all
``ownership_unclaimed``        info     legitimately someone else's
``liquidation_position_excluded`` warning  a liquidation pass declined a position
============================== ======== ==========================================

``ownership_unclaimed`` is **informational**, not a warning: another strategy or a manual
trade legitimately holding a position is normal on a shared account, and warning about it
would train operators to ignore the whole family. The other three describe states where
the platform genuinely cannot answer a question it should be able to answer.

All four produce the same automation decision — do not act — but different remediation.
``ambiguous`` means resolve who owns it; ``identity_unresolved`` means fix the lineage
data. Collapsing them would hide which one you have.

## Deduplication

The engine calls ``on_bar`` once per symbol — 200+ times per rebalance slot — so an
unresolvable holding would otherwise be reported 200 times. Dedupe identity is::

    (strategy_id, account_id, operation, permaticker or ticker, classification, scope_id)

``scope_id`` is the dispatch/rebalance identity, so a *new* rebalance or a *new*
liquidation attempt reports the problem again. That matters: a persistently unresolved
identity must stay visible on later attempts rather than being silenced forever by the
first sighting. Passing ``scope_id=None`` disables dedupe entirely, which is correct for a
liquidation pass — it walks the position book exactly once.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

from app.universe.owned_holdings import HoldingExclusionReason

logger = structlog.get_logger(__name__)

__all__ = [
    "OwnershipDiagnostics",
    "OwnershipOperation",
    "ownership_event_for",
]


class OwnershipOperation(StrEnum):
    """Which path declined to act. Same vocabulary, different remediation urgency."""

    NORMAL_REBALANCE_EXIT = "normal_rebalance_exit"
    LIVE_LIQUIDATION = "live_liquidation"
    PAPER_LIQUIDATION = "paper_liquidation"


#: Classification -> (event name, informational?).
_EVENTS: dict[str, tuple[str, bool]] = {
    "ownership_ambiguous": ("ownership_ambiguous", False),
    "ownership_identity_unresolved": ("ownership_identity_unresolved", False),
    "ownership_evidence_missing": ("ownership_evidence_missing", False),
    "ownership_unclaimed": ("ownership_unclaimed", True),
}


def ownership_event_for(reason: HoldingExclusionReason, detail: str | None) -> str:
    """Classification for one exclusion.

    ``identity_unresolved`` arrives as an ambiguity with a detail, because behaviourally it
    IS one — both fail closed. It is split out here, and only here, because the operator
    response differs: contested ownership is a bookkeeping question, an unresolved lineage
    is a data question.
    """
    if reason is HoldingExclusionReason.OWNERSHIP_AMBIGUOUS and detail == "identity_unresolved":
        return "ownership_identity_unresolved"
    return reason.value


@dataclass(frozen=True)
class _Context:
    strategy_id: int
    strategy_name: str | None
    account_id: int
    account_mode: str | None
    operation: OwnershipOperation
    source: str


class OwnershipDiagnostics:
    """Emits ownership refusals with dispatch-scoped deduplication.

    One instance per long-lived consumer (an engine-bound strategy context, a liquidation
    service). The seen-set is bounded and FIFO-evicted so a long-running process cannot
    grow it without limit; eviction can at worst cause a duplicate emission, never a
    missed one.
    """

    _MAX_SEEN = 4096

    def __init__(self) -> None:
        self._seen: OrderedDict[tuple[Any, ...], None] = OrderedDict()

    def emit_exclusions(
        self,
        exclusions: Any,
        *,
        strategy_id: int,
        account_id: int,
        operation: OwnershipOperation,
        source: str,
        strategy_name: str | None = None,
        account_mode: str | None = None,
        scope_id: Any = None,
    ) -> list[str]:
        """Report each excluded holding once per scope. Returns the events emitted."""
        ctx = _Context(strategy_id, strategy_name, account_id, account_mode, operation, source)
        emitted: list[str] = []
        for ex in exclusions:
            classification = ownership_event_for(ex.reason, ex.detail)
            security_id = getattr(ex, "security_id", None)
            key = (
                strategy_id,
                account_id,
                operation.value,
                security_id or ex.ticker,
                classification,
                scope_id,
            )
            if scope_id is not None and key in self._seen:
                continue
            if scope_id is not None:
                self._seen[key] = None
                if len(self._seen) > self._MAX_SEEN:
                    self._seen.popitem(last=False)
            self._log(ctx, classification, ex.ticker, security_id, ex.detail, scope_id)
            emitted.append(classification)
        return emitted

    def emit_liquidation_exclusion(
        self,
        *,
        strategy_id: int,
        account_id: int,
        operation: OwnershipOperation,
        ticker: str,
        disposition: str,
        detail: str | None,
        security_id: str | None = None,
        strategy_name: str | None = None,
        account_mode: str | None = None,
    ) -> None:
        """A liquidation pass declined one position.

        Emitted in addition to the ownership event so an operator can filter on "a
        liquidation was attempted and skipped something" without reconstructing it from
        the ownership stream.
        """
        logger.warning(
            "liquidation_position_excluded",
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            account_id=account_id,
            account_mode=account_mode,
            current_ticker=ticker,
            permaticker=security_id,
            classification=disposition,
            reason=detail,
            operation=operation.value,
            source="strategy_position_liquidator",
        )

    @staticmethod
    def _log(
        ctx: _Context,
        classification: str,
        ticker: str,
        security_id: str | None,
        detail: str | None,
        scope_id: Any,
    ) -> None:
        event, informational = _EVENTS.get(classification, (classification, False))
        fields = {
            "strategy_id": ctx.strategy_id,
            "strategy_name": ctx.strategy_name,
            "account_id": ctx.account_id,
            "account_mode": ctx.account_mode,
            "current_ticker": ticker,
            "permaticker": security_id,
            "classification": classification,
            "reason": detail,
            "operation": ctx.operation.value,
            "scope_id": scope_id,
            "source": ctx.source,
        }
        if informational:
            logger.info(event, **fields)
        else:
            logger.warning(event, **fields)
