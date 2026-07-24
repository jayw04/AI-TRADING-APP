"""Runnable forward session — the assembly (R5c-2b2).

This is where every governed piece is wired into ONE session run. It owns three things the individual
components cannot own alone:

  1. the SINGLE instrument snapshot — taken once, its digest handed to the provider, the evaluator and
     the runner alike, so the decision, the booking and the record all speak of the same instrument;
  2. the STRUCTURAL binding of provider evidence — the evidence of the exact calls the one evaluation
     made, selected by call-count delta rather than by reading a mutable "last" field afterwards;
  3. the WRITE ORDERING and its explicit crash window — the observation is the source of truth, the
     instrument book is written after it, and the gap between them maps onto BOOK_BEHIND_RECORD.

The governed order this assembly preserves:

    readiness + lengthy data work        (the readiness gate, inside the runner)
    → held-name PIT price reads           (the runner's _unmarkable, strict prices)
    → pre-session instrument-book snapshot (the runner's ledger snapshot; the book snapshot is here)
    → authoritative Account-4 probe        (immediately before evaluation)
    → instrument evaluation                (exactly one on_bar via the decision provider)
    → store-unchanged verification
    → second Account-4 probe
    → observation publication + durable-book write

Nothing here reads market data itself, and nothing constructs the instrument until a session is actually
run — readiness (R5c-2b1) never reaches this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.validation.decision_provider import ForwardDecision
from app.validation.forward_window import IntegrityStop
from app.validation.instrument_state_store import (
    InstrumentBook,
    apply_to_adapter,
    capture_from_adapter,
    load_instrument_book,
    reconcile_with_record,
    save_instrument_book,
)


class AssemblyError(IntegrityStop):
    """The runnable session could not be assembled, or a provider was called an unexpected number of
    times during the one evaluation. Fails closed."""


@dataclass
class BoundProviderEvidence:
    """The evidence of exactly the provider calls the decision's evaluation made — selected by
    call-count delta, never by reading a mutable last-call field after the fact."""
    scores: list[dict[str, Any]] = field(default_factory=list)
    bars: list[dict[str, Any]] = field(default_factory=list)

    def to_open_provenance(self) -> dict[str, Any]:
        return {"scores_calls": self.scores, "bars_calls": self.bars}


@dataclass
class EvidenceBindingDecisionProvider:
    """Wraps the production decision provider so the provider evidence bound to a decision is the
    evidence of THIS decision's evaluation, and only it.

    Before the wrapped provider runs the instrument, the scores/bars evidence lists are noted at their
    current length; after, exactly the new entries are bound. A run that made an unexpected number of
    provider calls — extra or missing — is refused, because the record could not then say which inputs
    the decision was taken from.
    """
    inner: Callable[[date], ForwardDecision]
    scores_provider: Any
    bars_provider: Any
    expected_scores_calls: int = 1
    bound_evidence: BoundProviderEvidence | None = field(default=None, init=False)

    def __call__(self, session_date: date) -> ForwardDecision:
        scores_before = len(self.scores_provider.output_evidence)
        bars_before = len(self.bars_provider.output_evidence)

        decision = self.inner(session_date)

        scores_new = self.scores_provider.output_evidence[scores_before:]
        bars_new = self.bars_provider.output_evidence[bars_before:]
        if len(scores_new) != self.expected_scores_calls:
            raise AssemblyError(
                f"the evaluation made {len(scores_new)} scores call(s), expected "
                f"{self.expected_scores_calls}: the decision's inputs cannot be identified")
        if not bars_new:
            raise AssemblyError(
                "the evaluation made no regime/bars call: the decision's inputs cannot be identified")
        for evidence in (*scores_new, *bars_new):
            if evidence.get("session_date") not in (None, session_date.isoformat()) or \
                    evidence.get("as_of") not in (None, session_date.isoformat()):
                raise AssemblyError(
                    f"a provider call bound to session {session_date.isoformat()} carries a different "
                    f"session in its evidence: {evidence}")
        self.bound_evidence = BoundProviderEvidence(scores=list(scores_new), bars=list(bars_new))
        return decision


@dataclass
class InstrumentBookLifecycle:
    """Loads, reconciles and (after commit) persists the instrument's own durable book.

    The book is reconciled with committed storage BEFORE the instrument is restored, and written only
    AFTER the observation commits. A crash between the observation commit and the book write leaves the
    book one session behind, which the next run diagnoses as BOOK_BEHIND_RECORD — never repaired here.
    """
    book_path: Any
    starting_capital: float
    deployment_blob: dict[str, Any]

    def restore(self, adapter: Any, *, committed_count: int,
                last_committed_session: str | None) -> InstrumentBook:
        book = load_instrument_book(self.book_path)
        if book is None:
            from app.validation.instrument_state_store import open_fresh_book

            book = open_fresh_book(starting_capital=self.starting_capital,
                                   deployment_blob=self.deployment_blob,
                                   committed_count=committed_count)
        reconcile_with_record(book, committed_count=committed_count,
                              last_committed_session=last_committed_session,
                              expected_starting_capital=self.starting_capital)
        apply_to_adapter(book, adapter)
        return book

    def persist_after_commit(self, adapter: Any, *, sequence: int, session_date: str) -> InstrumentBook:
        book = capture_from_adapter(adapter, sessions_recorded=sequence,
                                    last_session_date=session_date)
        save_instrument_book(book, self.book_path)
        return book


def assert_single_snapshot(snapshot: Any) -> None:
    """The one snapshot's digest is what ties provider, evaluator and runner together. It must be
    present and non-empty before the run can proceed."""
    digest = getattr(snapshot, "snapshot_digest", "")
    if not str(digest or "").strip():
        raise AssemblyError("the instrument snapshot carries no digest; the run cannot be tied to it")
