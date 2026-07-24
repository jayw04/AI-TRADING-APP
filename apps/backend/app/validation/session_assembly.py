"""Runnable forward session — the assembly (R5c-2b2).

This wires every governed component into ONE session run and owns the four things no component owns
alone:

  1. the SINGLE instrument snapshot — captured exactly once (a second capture is refused), its digest
     handed to the decision provider, the evaluator's `expected_snapshot_digest` and the runner alike;
  2. the immutable BINDING of provider evidence — the evidence of exactly the calls the one evaluation
     made, digested and carried INTO the ForwardDecision and thence into the committed observation;
  3. the exact provider-call CARDINALITY — one scores call and a governed bars-call set (one market
     proxy call, no duplicate symbols, every call as-of the session, n within bounds);
  4. the WRITE ORDERING and its explicit crash window — the observation is the source of truth, the
     instrument book is written after it (a post-commit durability condition, never an ordinary retry),
     and the gap maps onto BOOK_BEHIND_RECORD.

The governed order:

    readiness + lengthy data work        (the readiness gate, inside the runner)
    → held-name PIT price reads           (the runner's _unmarkable, strict prices)
    → pre-session instrument-book snapshot (the ledger snapshot; the book snapshot happens on restore)
    → authoritative Account-4 probe        (immediately before evaluation)
    → instrument evaluation                (exactly one on_bar via the decision provider)
    → store-unchanged verification
    → second Account-4 probe
    → observation publication + durable-book write

Nothing constructs the instrument until a session is actually run — readiness (R5c-2b1) never reaches
this module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from app.validation.decision_provider import ForwardDecision
from app.validation.forward_window import IntegrityStop
from app.validation.instrument_state_store import (
    InstrumentBook,
    apply_to_adapter,
    capture_from_adapter,
    load_instrument_book,
    open_fresh_book,
    reconcile_with_record,
    save_instrument_book,
)


class AssemblyError(IntegrityStop):
    """The runnable session could not be assembled, or a provider was called an unexpected number of
    times (or with unexpected arguments) during the one evaluation. Fails closed."""


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


# ── the single snapshot: captured exactly once, wired everywhere ────────────────────────────────────

@dataclass
class SnapshotOnce:
    """A one-shot wrapper around the snapshot capture. The second call is an integrity stop: exactly one
    snapshot ties the whole run together, and a second would mean two different states could each claim
    to be the one the decision was taken under."""
    capture: Callable[..., Any]
    _captured: Any = field(default=None, init=False)
    _count: int = field(default=0, init=False)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._count += 1
        if self._count > 1:
            raise AssemblyError(
                "the instrument snapshot was captured more than once; exactly one snapshot must tie the "
                "provider, evaluator and runner together")
        self._captured = self.capture(*args, **kwargs)
        return self._captured

    @property
    def captured(self) -> Any:
        if self._captured is None:
            raise AssemblyError("no instrument snapshot has been captured")
        return self._captured


# ── the governed bars-call cardinality ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BarsCallSpec:
    """What a single evaluation's bars calls must look like.

    The frozen strategy legitimately makes several bars calls per session — the REGIME call (the market
    proxy over the MA window), a shorter market read, and one price read per seeded name — and the exact
    number is path-dependent (a seed day fetches per-name bars a non-seed day does not). So the governed
    invariant is not a literal count but the properties that must hold whatever the path:

      * exactly ONE regime call — the market symbol requesting at least the MA window;
      * every call is as-of the session;
      * every call's n is within a governed band;
      * no two calls share the same (symbol, n) — an exact-duplicate call is redundant and suspicious.
    """
    market_symbol: str
    ma_sessions: int = 200
    min_n: int = 1
    max_n: int = 100_000

    def validate(self, calls: list[dict[str, Any]], session_date: date) -> None:
        if not calls:
            raise AssemblyError("the evaluation made no regime/bars call: inputs cannot be identified")
        regime = [c for c in calls
                  if str(c.get("symbol", "")).upper() == self.market_symbol.upper()
                  and int(c.get("requested_n", 0)) >= self.ma_sessions]
        if len(regime) != 1:
            raise AssemblyError(
                f"the evaluation made {len(regime)} regime call(s) (market proxy {self.market_symbol} "
                f"with n >= {self.ma_sessions}), expected exactly 1")
        seen: set[tuple[str, int]] = set()
        for call in calls:
            symbol = str(call.get("symbol", "")).upper()
            n = int(call.get("requested_n", -1))
            if call.get("as_of") not in (None, session_date.isoformat()):
                raise AssemblyError(
                    f"a bars call carries as_of {call.get('as_of')!r}, not {session_date.isoformat()}")
            if n >= 0 and not (self.min_n <= n <= self.max_n):
                raise AssemblyError(
                    f"a bars call requested n={n}, outside the governed band "
                    f"[{self.min_n}, {self.max_n}]")
            if (symbol, n) in seen:
                raise AssemblyError(f"the evaluation made a duplicate bars call for ({symbol}, n={n})")
            seen.add((symbol, n))


# ── the evidence bound into the immutable decision ──────────────────────────────────────────────────

@dataclass(frozen=True)
class BoundProviderEvidence:
    """The evidence of exactly the provider calls the decision's evaluation made. Its digest is carried
    into the ForwardDecision, so the committed record can prove which inputs the decision used."""
    session_date: str
    scores: tuple[dict[str, Any], ...]
    bars: tuple[dict[str, Any], ...]

    def digest(self) -> str:
        return _digest({"session_date": self.session_date,
                        "scores": list(self.scores), "bars": list(self.bars)})

    def to_open_provenance(self) -> dict[str, Any]:
        return {"session_date": self.session_date, "scores_calls": list(self.scores),
                "bars_calls": list(self.bars), "input_evidence_digest": self.digest()}


@dataclass
class EvidenceBindingDecisionProvider:
    """Wraps the production decision provider so the evidence bound to a decision is the evidence of THIS
    decision's evaluation, and only it — selected by call-count delta, digested, and carried into a NEW
    immutable ForwardDecision. A mutable side field would not prove which evidence accompanied the
    committed observation; the digest travelling inside the decision does.
    """
    inner: Callable[[date], ForwardDecision]
    scores_provider: Any
    bars_provider: Any
    bars_call_spec: BarsCallSpec
    bound_evidence: BoundProviderEvidence | None = field(default=None, init=False)

    def __call__(self, session_date: date) -> ForwardDecision:
        scores_before = len(self.scores_provider.output_evidence)
        bars_before = len(self.bars_provider.output_evidence)

        decision = self.inner(session_date)

        scores_new = self.scores_provider.output_evidence[scores_before:]
        bars_new = self.bars_provider.output_evidence[bars_before:]
        if not scores_new:
            raise AssemblyError("the evaluation made no scores call: inputs cannot be identified")

        iso = session_date.isoformat()
        # No scores call may read a FUTURE session — that would be lookahead. The frozen strategy does
        # legitimately read a prior session (the exit-confirmation lookback), so earlier dates are
        # allowed and recorded; only the future is forbidden.
        for evidence in scores_new:
            when = evidence.get("session_date")
            if when is not None and str(when) > iso:
                raise AssemblyError(
                    f"a scores call reads session {when!r}, later than {iso} — the decision may not "
                    f"see the future")
        # The session's OWN cross-section must be present and internally consistent: at least one call
        # as-of the session, and exactly one distinct frame among them.
        session_calls = [e for e in scores_new if str(e.get("session_date")) == iso]
        if not session_calls:
            raise AssemblyError(f"the evaluation never scored the session {iso} itself")
        distinct = {e.get("frame_digest") for e in session_calls}
        if len(distinct) != 1:
            raise AssemblyError(
                f"the evaluation read {len(distinct)} distinct scored frames for {iso}; the decision's "
                f"own cross-section must be one consistent set")
        self.bars_call_spec.validate(bars_new, session_date)

        bound = BoundProviderEvidence(
            session_date=session_date.isoformat(),
            scores=tuple(scores_new), bars=tuple(bars_new))
        self.bound_evidence = bound
        return replace(decision, input_evidence_digest=bound.digest())


# ── the instrument's own durable book, across the session ───────────────────────────────────────────

@dataclass
class InstrumentBookLifecycle:
    """Loads, reconciles and (after commit) persists the instrument's own durable book.

    Reconciled with committed storage BEFORE the instrument is restored; written only AFTER the
    observation commits (via the runner's on_committed hook). A crash between the observation commit and
    the book write leaves the book one session behind, which the next run diagnoses as
    BOOK_BEHIND_RECORD — never repaired here, never reconstructed from the ledger.
    """
    book_path: Any
    starting_capital: float
    deployment_blob: dict[str, Any]

    def restore(self, adapter: Any, *, committed_count: int,
                last_committed_session: str | None) -> InstrumentBook:
        book = load_instrument_book(self.book_path)
        if book is None:
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
