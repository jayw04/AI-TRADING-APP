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
    """The EXACT bars-call argument set a single frozen evaluation may make.

    The frozen strategy's bars calls are deterministic in KIND, and each kind has a governed argument;
    the only path-dependence is how many per-name price reads a seed day makes. So the governed invariant
    is the exact set of permitted calls, not a broad band:

      * exactly ONE regime call — the market symbol at EXACTLY `regime_window_n` (`market_ma_days + 1`,
        the frozen request); a market read at any other n is a different construction and is refused,
        even one carrying more than enough history for the MA;
      * at most ONE exit-confirmation market read — the market symbol at `exit_confirm_window_n`
        (`exit_confirm_closes + 4`); permitted only when the spec carries that governed n;
      * every other call is a per-NAME price read: its symbol must belong to this session's expected
        universe (or the pre-decision holdings), and its n must be exactly the governed price-read n;
      * every call is as-of the session; no two calls share the same (symbol, n).

    An UNRELATED symbol, or the market proxy at some other n, or a name read at an ungoverned n, is
    refused — those cannot be the frozen strategy's calls, so a decision carrying them cannot be
    attributed to it.
    """
    market_symbol: str
    regime_window_n: int = 201                      # EXACT SPY n for the regime call (market_ma_days + 1)
    exit_confirm_window_n: int | None = None        # SPY n == exit_confirm_closes + 4 (None => forbidden)
    name_read_n: int = 1                            # the governed per-name price-read n
    allowed_security_symbols: frozenset[str] = frozenset()

    def validate(self, calls: list[dict[str, Any]], session_date: date) -> None:
        if not calls:
            raise AssemblyError("the evaluation made no regime/bars call: inputs cannot be identified")
        iso = session_date.isoformat()
        market = self.market_symbol.upper()
        regime = 0
        exit_reads = 0
        seen: set[tuple[str, int]] = set()
        for call in calls:
            symbol = str(call.get("symbol", "")).upper()
            n = int(call.get("requested_n", -1))
            if call.get("as_of") not in (None, iso):
                raise AssemblyError(f"a bars call carries as_of {call.get('as_of')!r}, not {iso}")
            if (symbol, n) in seen:
                raise AssemblyError(f"the evaluation made a duplicate bars call for ({symbol}, n={n})")
            seen.add((symbol, n))
            if symbol == market:
                if n == self.regime_window_n:
                    regime += 1
                elif self.exit_confirm_window_n is not None and n == self.exit_confirm_window_n:
                    exit_reads += 1
                else:
                    raise AssemblyError(
                        f"the market proxy {self.market_symbol} was read at n={n}; the only governed "
                        f"market reads are the regime call (n = {self.regime_window_n}) and the "
                        f"exit-confirmation read (n = {self.exit_confirm_window_n})")
            else:
                if symbol not in self.allowed_security_symbols:
                    raise AssemblyError(
                        f"a bars call reads {symbol!r}, which is not in the session's expected universe "
                        f"or holdings — it cannot be one of the frozen strategy's per-name reads")
                if n != self.name_read_n:
                    raise AssemblyError(
                        f"the per-name bars call for {symbol!r} requested n={n}, not the governed "
                        f"price-read n={self.name_read_n}")
        if regime != 1:
            raise AssemblyError(
                f"the evaluation made {regime} regime call(s) (market proxy {self.market_symbol} at "
                f"n = {self.regime_window_n}), expected exactly 1")
        if exit_reads > 1:
            raise AssemblyError(
                f"the evaluation made {exit_reads} exit-confirmation market reads, expected at most 1")


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
    # The frozen path scores the CURRENT session a deterministic number of times: once in `_evaluate`
    # and once in `capture_seam`'s re-derivation — two calls, the same cross-section. A prior session may
    # be scored ONLY as the exit-confirmation lookback, and ONLY the exact immediately-preceding governed
    # store sessions — `allowed_prior_score_sessions`, an ascending tuple of ISO dates (the preceding
    # `exit_confirm_closes - 1` store sessions). An arbitrary earlier date, a non-store date, a skipped
    # expected date or an extra date is refused: a maximum count alone would let a 2020 read pass.
    expected_current_session_scores_calls: int = 2
    allowed_prior_score_sessions: tuple[str, ...] = ()
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
        current: list[dict[str, Any]] = []
        prior: list[dict[str, Any]] = []
        for evidence in scores_new:
            when = str(evidence.get("session_date"))
            if when > iso:
                raise AssemblyError(
                    f"a scores call reads session {when!r}, later than {iso} — the decision may not "
                    f"see the future")
            (current if when == iso else prior).append(evidence)

        # exactly the governed number of current-session calls, and they must agree — the decision's own
        # cross-section is one consistent frame, read the deterministic number of times.
        if len(current) != self.expected_current_session_scores_calls:
            raise AssemblyError(
                f"the evaluation scored the session {iso} {len(current)} time(s), expected exactly "
                f"{self.expected_current_session_scores_calls} (the `_evaluate` + `capture_seam` reads)")
        distinct = {e.get("frame_digest") for e in current}
        if len(distinct) != 1:
            raise AssemblyError(
                f"the evaluation read {len(distinct)} distinct scored frames for {iso}; the decision's "
                f"own cross-section must be one consistent set")

        # any prior-session call is the governed exit-confirmation lookback: it must read ONLY the exact
        # immediately-preceding governed store sessions — never an arbitrary earlier date, never a
        # non-store date, never a skipped or extra one, and never the same close twice.
        allowed = tuple(self.allowed_prior_score_sessions)
        prior_dates = [str(e.get("session_date")) for e in prior]
        if len(prior) > len(allowed):
            raise AssemblyError(
                f"the evaluation scored {len(prior)} prior session(s), above the governed "
                f"exit-confirmation window of {len(allowed)} session(s) {list(allowed)}")
        if len(set(prior_dates)) != len(prior_dates):
            raise AssemblyError(
                f"the evaluation scored a prior session more than once ({sorted(prior_dates)}); the "
                f"exit-confirmation lookback reads each earlier close at most once")
        # the k prior reads must be exactly the k MOST-RECENT sessions of the allowed window: this
        # rejects an older date, a non-store date, and a skipped expected date all at once.
        expected_prefix = set(list(reversed(allowed))[:len(prior_dates)])
        if set(prior_dates) != expected_prefix:
            raise AssemblyError(
                f"the prior-session score read(s) {sorted(prior_dates)} are not the immediately "
                f"preceding governed store session(s) {sorted(expected_prefix)} — the exit-confirmation "
                f"lookback reads only the exact preceding store sessions")

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
