"""One operator vocabulary across all three ownership-refusal paths (PR S / S6).

The point is not that logging exists — it is that an operator asking "why didn't LOW-001
close that position?" gets the same event names and the same fields whether the refusal
happened during a rebalance, a LIVE liquidation, or a PAPER liquidation.

Also pinned: the 200-symbol dispatch storm reports once, and a LATER rebalance reports
again. A persistently unresolved identity that goes quiet after its first sighting is
worse than no diagnostic, because it reads as resolved.
"""

from __future__ import annotations

import pytest
import structlog

from app.universe.diagnostics import (
    OwnershipDiagnostics,
    OwnershipOperation,
    ownership_event_for,
)
from app.universe.owned_holdings import ExcludedHolding, HoldingExclusionReason

AMBIGUOUS = HoldingExclusionReason.OWNERSHIP_AMBIGUOUS
UNCLAIMED = HoldingExclusionReason.OWNERSHIP_UNCLAIMED
MISSING = HoldingExclusionReason.OWNERSHIP_EVIDENCE_MISSING


@pytest.fixture
def captured():
    """Capture structlog events as dicts."""
    events: list[dict] = []

    def sink(_logger, name, event_dict):
        # `name` is the log method ("info"/"warning"), which is the severity under test.
        events.append({**event_dict, "log_level": name})
        raise structlog.DropEvent

    old = structlog.get_config()["processors"]
    structlog.configure(processors=[sink])
    yield events
    structlog.configure(processors=old)


def _emit(diag, exclusions, **over):
    kwargs = {
        "strategy_id": 8,
        "account_id": 6,
        "operation": OwnershipOperation.NORMAL_REBALANCE_EXIT,
        "source": "strategy_context",
        "strategy_name": "low-volatility",
        "account_mode": "paper",
        "scope_id": 1,
    }
    kwargs.update(over)
    return diag.emit_exclusions(exclusions, **kwargs)


# ---- classification ------------------------------------------------------------


def test_identity_unresolved_is_split_out_from_generic_ambiguity():
    """Same automation decision, different remediation: bookkeeping vs lineage data."""
    assert ownership_event_for(AMBIGUOUS, "identity_unresolved") == (
        "ownership_identity_unresolved"
    )
    assert ownership_event_for(AMBIGUOUS, "non_strategy_acquisition") == "ownership_ambiguous"
    assert ownership_event_for(AMBIGUOUS, None) == "ownership_ambiguous"
    assert ownership_event_for(UNCLAIMED, None) == "ownership_unclaimed"
    assert ownership_event_for(MISSING, None) == "ownership_evidence_missing"


def test_every_classification_emits_its_event(captured):
    diag = OwnershipDiagnostics()
    _emit(
        diag,
        [
            ExcludedHolding("A", AMBIGUOUS, "competing_strategy_acquisition", "P-1"),
            ExcludedHolding("B", AMBIGUOUS, "identity_unresolved", None),
            ExcludedHolding("C", UNCLAIMED, None, "P-3"),
            ExcludedHolding("D", MISSING, None, None),
        ],
    )
    assert [e["event"] for e in captured] == [
        "ownership_ambiguous",
        "ownership_identity_unresolved",
        "ownership_unclaimed",
        "ownership_evidence_missing",
    ]


def test_unclaimed_is_informational_and_the_rest_are_warnings(captured):
    """Another owner on a shared account is normal; warning about it trains operators to
    ignore the whole family."""
    diag = OwnershipDiagnostics()
    _emit(
        diag,
        [
            ExcludedHolding("C", UNCLAIMED, None, "P-3"),
            ExcludedHolding("A", AMBIGUOUS, "non_strategy_acquisition", "P-1"),
        ],
    )
    levels = {e["event"]: e["log_level"] for e in captured}
    assert levels["ownership_unclaimed"] == "info"
    assert levels["ownership_ambiguous"] == "warning"


def test_event_carries_the_full_operator_field_set(captured):
    diag = OwnershipDiagnostics()
    _emit(diag, [ExcludedHolding("A", AMBIGUOUS, "non_strategy_acquisition", "P-1")])
    ev = captured[0]
    for field in (
        "strategy_id",
        "strategy_name",
        "account_id",
        "account_mode",
        "current_ticker",
        "permaticker",
        "classification",
        "reason",
        "operation",
        "scope_id",
        "source",
    ):
        assert field in ev, field
    assert ev["current_ticker"] == "A"
    assert ev["permaticker"] == "P-1"
    assert ev["operation"] == "normal_rebalance_exit"


# ---- dedupe --------------------------------------------------------------------


def test_the_dispatch_storm_reports_once(captured):
    """200 on_bar calls in one slot must not become 200 identical warnings."""
    diag = OwnershipDiagnostics()
    ex = [ExcludedHolding("A", AMBIGUOUS, "non_strategy_acquisition", "P-1")]
    for _ in range(200):
        _emit(diag, ex, scope_id=7)
    assert len(captured) == 1


def test_a_later_rebalance_reports_again(captured):
    """Dedupe is scoped, never permanent. A still-broken holding must stay visible."""
    diag = OwnershipDiagnostics()
    ex = [ExcludedHolding("A", AMBIGUOUS, "non_strategy_acquisition", "P-1")]
    _emit(diag, ex, scope_id=7)
    _emit(diag, ex, scope_id=8)
    assert len(captured) == 2


def test_dedupe_is_per_operation(captured):
    """The same holding refused by a rebalance and by a liquidation is two facts."""
    diag = OwnershipDiagnostics()
    ex = [ExcludedHolding("A", AMBIGUOUS, "non_strategy_acquisition", "P-1")]
    _emit(diag, ex, scope_id=7)
    _emit(diag, ex, scope_id=7, operation=OwnershipOperation.PAPER_LIQUIDATION)
    assert len(captured) == 2


def test_dedupe_keys_on_permanent_identity_not_ticker(captured):
    """A rename mid-slot is one problem, not two."""
    diag = OwnershipDiagnostics()
    _emit(diag, [ExcludedHolding("OLD", AMBIGUOUS, "x", "P-1")], scope_id=7)
    _emit(diag, [ExcludedHolding("NEW", AMBIGUOUS, "x", "P-1")], scope_id=7)
    assert len(captured) == 1


def test_no_scope_disables_dedupe(captured):
    """A liquidation walks the book once; suppressing a retry would hide it."""
    diag = OwnershipDiagnostics()
    ex = [ExcludedHolding("A", AMBIGUOUS, "x", "P-1")]
    _emit(diag, ex, scope_id=None, operation=OwnershipOperation.PAPER_LIQUIDATION)
    _emit(diag, ex, scope_id=None, operation=OwnershipOperation.PAPER_LIQUIDATION)
    assert len(captured) == 2


def test_seen_set_is_bounded(captured):
    """A long-running process must not grow the dedupe set without limit.

    Eviction can at worst duplicate an emission, never suppress a new one.
    """
    diag = OwnershipDiagnostics()
    for i in range(OwnershipDiagnostics._MAX_SEEN + 50):
        _emit(diag, [ExcludedHolding(f"T{i}", AMBIGUOUS, "x", None)], scope_id=1)
    assert len(diag._seen) <= OwnershipDiagnostics._MAX_SEEN


def test_liquidation_exclusion_event_shape(captured):
    diag = OwnershipDiagnostics()
    diag.emit_liquidation_exclusion(
        strategy_id=8,
        account_id=6,
        operation=OwnershipOperation.PAPER_LIQUIDATION,
        ticker="A",
        disposition="excluded_ambiguous",
        detail="non_strategy_acquisition",
        security_id="P-1",
        strategy_name="low-volatility",
        account_mode="paper",
    )
    ev = captured[0]
    assert ev["event"] == "liquidation_position_excluded"
    assert ev["operation"] == "paper_liquidation"
    assert ev["classification"] == "excluded_ambiguous"
    assert ev["permaticker"] == "P-1"
