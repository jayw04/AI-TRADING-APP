"""Forward-validation session runner — one governed observation per eligible session (R4).

This is the wiring between the eligibility calendar, the per-session evaluator (R2b) and the chained
observation store (R3). It is the piece a scheduler invokes: fire it once a day, and it decides —
deterministically, and without ever guessing — whether this date is an eligible session, whether the
session is already recorded, whether the durable state is consistent enough to proceed, and whether the
instrument actually produced a decision.

The run is NON-ORDERING. Nothing here imports the order path, the broker or Account 4's book; Account-4
isolation is re-proved by the authoritative before/after probes inside the commit protocol.

## The four outcomes (there is no fifth, and none of them is a guess)

  NOT_ELIGIBLE       the date is not an XNYS session, or precedes the frozen forward start. No writes.
  ALREADY_RECORDED   this session's observation is already committed AND the durable ledger agrees with
                     the committed record. No writes, no double booking — re-running the scheduler is
                     safe by construction. Note the ledger check: a same-date retry after a crash
                     between the commit and the ledger save is a LEDGER_BEHIND_RECORD stop, never a
                     healthy no-op, because reconciliation runs BEFORE this return.
  RECORDED           the instrument produced exactly one real decision, the ledger booked it at the
                     registered turnover cost, and the observation committed. The count advanced by 1.
  INTEGRITY_STOP     a permitted stop (§5.4). NOTHING is booked, NOTHING is committed, the session count
                     is unchanged, and the operational exception is appended to a log OUTSIDE the sealed
                     performance and OUTSIDE `observations/` (it can touch neither the chain nor count).

## Every security the ledger accounts for must have THIS session's mark

Data-finality proves the registered CONSTRUCTION is complete; it does not prove that the ledger can
value its own book. A name can leave the scoring universe and still be held, so the runner validates
the current holdings' marks before the decision is taken, and the production price function raises on
any missing, null or nonpositive mark it is asked for afterwards — which covers every decision target
as it is sleeved. Either way the session stops with NOT_READY_CURRENT_SESSION_MISSING: no booking, no
observation, count unchanged. A sleeve is never carried at an earlier session's price.

## Account 4 is probed immediately before the decision and again before publication

The authoritative probe runs LAST of everything — after the readiness assessment, after the held-name
price reads, after the pre-session ledger snapshot, and immediately before the instrument is evaluated —
so the interval in which the live book could move unnoticed holds nothing lengthy. It runs again after every decision and data read, before anything is published, and the two must
describe the same live state: a hold cleared, a strategy resumed, an order appearing or a position
moving stops the session (ACCOUNT4_STATE_CHANGED_DURING_SESSION) even when each probe is individually
safe. The probe path only reads; it never touches an Account-4 mutation surface.

## The session's DATA must be final before its decision is taken

The runner refuses to evaluate a session whose inputs are not proven final, complete and correctly
adjusted (R5a/R5b): the readiness verdict becomes the stop code, so `NOT_READY_DATA_STALE` or
`NOT_READY_ADJUSTMENT_UNVERIFIED` appears verbatim in the record rather than a generic failure. With no
gate configured the runner refuses outright. After the decision is taken the store identity is
re-verified, so a store that moved underneath the reads is `DATA_STORE_CHANGED_DURING_SESSION` and
nothing is committed. A committed observation carries the readiness evidence that justified it.

## An eligible session whose instrument did not evaluate is an INTEGRITY_STOP (owner ruling 2026-07-24)

A production path that returns before `_evaluate` has not produced the required instrument decision.
Recording that as an ordinary flat/no-trade observation would falsely claim the strategy was evaluated
and chose not to trade. The runner therefore never synthesizes `weights={}` / `trade_initiated=False`
to stand in for an absent evaluation — the evaluator's boundary checks refuse such a record, and the
runner records the refusal as an operational exception instead of a session.

A genuine zero-gross decision is a different thing and remains valid: the instrument evaluated, emitted
`regime_gross = 0.0` with matching zero-valued weights, and that decision books and commits normally.

## One observation per ELIGIBLE session — a skipped session is refused, never stepped over

A chain that is contiguous by sequence can still have lost a session: commit Monday, never run Tuesday,
run Wednesday, and sequences 1-2-3 look perfect while the governed record silently means something
different from what it claims. So after the first observation exists, the requested session must equal
the next eligible XNYS session after the last committed one. A later date stops with
MISSED_ELIGIBLE_SESSION and names the sessions that were never recorded. Nothing is back-filled — the
hole is closed by governed adjudication, not by a runner deciding to catch up. Weekends and holidays are
not holes: they are simply not sessions. Sequence 1 is exempt (§0 path A: the record begins at the first
eligible session after deployment readiness).

## Durable-state discipline (crash safety, and why nothing is silently repaired)

Committed storage is the source of truth for how many sessions exist. Before anything is booked, the
runner requires the ledger's own `sessions_processed` to equal that committed count. If they disagree —
the two ways a crash mid-commit can leave them — the runner STOPS with a precise diagnosis rather than
re-booking a session or rolling a ledger back on its own:

  LEDGER_AHEAD_OF_RECORD    booked, then died before the observation committed. Re-running would double
                            book. The pre-session snapshot is the audited recovery input.
  LEDGER_BEHIND_RECORD      the observation committed but the ledger save did not land. The committed
                            sealed payload is the audited recovery input.

Recovery is an explicit, audited operation, never an automatic one (ADR 0044 invariant 7: auditable,
never silently repaired). The successful path writes a pre-session snapshot, books in memory, commits
the observation, saves the ledger, and only then drops the snapshot.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.validation.account4_probe import Account4Probe, assert_account4_unchanged
from app.validation.chain_anchor import AnchorError, append_anchor, verify_anchor_consistency
from app.validation.chain_witness import AnchorSigner, AnchorVerifier, ExternalAnchorSink
from app.validation.data_finality import DataFinalityEvidence
from app.validation.eval_calendar import (
    eligible_sessions,
    is_eligible_session,
    next_eligible_session,
)
from app.validation.first_session import open_first_window_session
from app.validation.forward_evaluator import DecisionProvider, ForwardEvaluator
from app.validation.forward_window import ForwardRunContext, IntegrityStop
from app.validation.observation_store import (
    Account4StateProbe,
    Durability,
    committed_observations,
    default_durability,
)
from app.validation.production_bindings import PriceUnavailable
from app.validation.session_recorder import record_forward_session
from app.validation.shadow_ledger import PriceFn, SessionOutcome, ShadowLedger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from typing import Protocol

    class DataReadinessCheck(Protocol):
        """The data-finality gate (R5a/R5b), as the runner consumes it: assess the session before
        anything is booked, and prove afterwards that the store did not move underneath the reads."""

        def assess(self, session_date: date) -> DataFinalityEvidence: ...

        def verify_unchanged(self, session_date: date, evidence: DataFinalityEvidence) -> None: ...

logger = structlog.get_logger(__name__)

STOP_LOG_FILENAME = "integrity_stops.jsonl"        # store ROOT — never under observations/
PRE_SESSION_SNAPSHOT = "ledger.pre-session.json"


class SessionRunStatus(StrEnum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ALREADY_RECORDED = "ALREADY_RECORDED"
    RECORDED = "RECORDED"
    # The observation committed but a post-commit durable write (the instrument book) failed. This is
    # NOT an ordinary session failure and MUST NOT be retried as one: the record advanced. The next run
    # sees BOOK_BEHIND_RECORD and stops for governed recovery.
    RECORDED_BUT_BOOK_UNPERSISTED = "RECORDED_BUT_BOOK_UNPERSISTED"
    # The observation committed but the independent chain-tip anchor (R5d) was not written. Like the book
    # case this is NOT retryable as an ordinary failure: the record advanced. The next run sees
    # ANCHOR_BEHIND_RECORD (or EXTERNAL_WITNESS_AHEAD) and stops for governed adjudication — the anchor
    # is never regenerated.
    RECORDED_BUT_ANCHOR_UNWRITTEN = "RECORDED_BUT_ANCHOR_UNWRITTEN"
    # BOTH post-commit durability writes failed. The anchor and the book attempts are INDEPENDENT (a
    # failure of one never suppresses the other), so this distinct status preserves each component's
    # divergence model for governed adjudication.
    RECORDED_BUT_ANCHOR_AND_BOOK_UNPERSISTED = "RECORDED_BUT_ANCHOR_AND_BOOK_UNPERSISTED"
    INTEGRITY_STOP = "INTEGRITY_STOP"


@dataclass(frozen=True)
class SessionRunResult:
    """What one scheduler invocation did. `session_count` is always the storage-derived count AFTER the
    run, so a scheduler can log the record's true length without reading the store itself."""
    status: SessionRunStatus
    session_date: str
    session_count: int
    sequence: int | None = None                    # the committed sequence when RECORDED
    exception_code: str | None = None              # set on INTEGRITY_STOP
    detail: str = ""
    operational_exceptions: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status is not SessionRunStatus.INTEGRITY_STOP


@dataclass
class ForwardSessionRunner:
    """One governed forward session per invocation. Every collaborator is injected: the decision
    provider (R5 supplies the data-coupled production one), the price function, the Account-4 probe, the
    per-session run context builder, and the ledger factory used ONLY to open a fresh ledger before the
    first session."""
    store_dir: Path
    ledger_path: Path
    decision_provider: DecisionProvider
    price_fn: PriceFn
    account4_probe: Callable[[], Account4StateProbe]
    context_builder: Callable[[date], ForwardRunContext]
    ledger_factory: Callable[[], ShadowLedger]
    deployed_tree_identity: str
    shadow_ledger_identity: str
    readiness: DataReadinessCheck | None = None
    expected_snapshot_digest: str = ""      # a pre-captured digest (the stub path); production captures below
    # The SINGLE instrument snapshot, captured at the pre-evaluation boundary (R5c-2b2): after readiness,
    # the held-name price reads and the pre-session ledger snapshot, and immediately before the
    # authoritative Account-4 probe — so it bounds the instrument state as close to the decision as
    # possible and a lengthy readiness/data check cannot leave it stale. `snapshot_capture` returns the
    # snapshot; `bind_snapshot` hands it to the decision provider. When both are absent the runner uses
    # the pre-configured `expected_snapshot_digest` (the tests' stub path).
    snapshot_capture: Callable[[date], object] | None = None
    bind_snapshot: Callable[[object], None] | None = None
    # The AUTHORITATIVE Account-4 read (R5c-2b). Taken immediately before the instrument is evaluated
    # and again after every decision/data read, before publication: both must describe the same live
    # state. Distinct from `account4_probe`, which the commit protocol uses inside its own staging.
    authoritative_account4_probe: Callable[[], Account4Probe] | None = None
    # Called AFTER the observation has committed and the ledger has saved — the point at which the
    # instrument's own durable book is persisted (R5c-2b2). The observation is the source of truth: if
    # this write is lost the next run sees BOOK_BEHIND_RECORD and stops for governed recovery, and the
    # book is never reconstructed from the ledger. `sequence` is the committed sequence number.
    on_committed: Callable[[int, str], None] | None = None
    # The independent chain-tip witness (R5d). REQUIRED: the record cannot be tamper-evidently anchored
    # without a signer whose private key the store-writer does not hold, the public verifier, and an
    # external append-only sink with separately governed write authority. Absent any of them the runner
    # fails closed rather than committing an unwitnessed record.
    anchor_signer: AnchorSigner | None = None
    anchor_verifier: AnchorVerifier | None = None
    external_anchor_sink: ExternalAnchorSink | None = None
    durability: Durability | None = None

    # ── the entry point a scheduler calls ─────────────────────────────────────────────────────────
    def run_session(self, session_date: date, *, run_timestamp: str) -> SessionRunResult:
        """Run (at most) one observation for `session_date`. `run_timestamp` is the caller-supplied
        ISO8601 UTC instant of this invocation — recorded as the preflight execution timestamp."""
        iso = session_date.isoformat()
        exceptions: list[str] = []

        if not is_eligible_session(session_date):
            return SessionRunResult(status=SessionRunStatus.NOT_ELIGIBLE, session_date=iso,
                                    session_count=self._count(),
                                    detail="not an XNYS session on/after the frozen forward start")

        try:
            records = committed_observations(self.store_dir)     # fail-closed, fully validated
        except IntegrityStop as exc:
            return self._stop(iso, "COMMITTED_RECORD_INVALID", str(exc), -1, exceptions)

        count = len(records)
        last = records[-1] if records else None

        # ── the independent chain-tip anchor must agree with the committed record (R5d) ──
        # Cross-verify the observation chain against the local anchor log, its signatures, AND the
        # external witness BEFORE any outcome, so a rewritten observation (whose independent anchor was
        # not also rewritten), an unwitnessed tip, a forged signature, or a truncation of the local log
        # stops even a no-op re-run. The anchor is never regenerated to paper over a divergence.
        if (self.anchor_signer is None or self.anchor_verifier is None
                or self.external_anchor_sink is None):
            return self._stop(
                iso, "INDEPENDENT_WITNESS_UNAVAILABLE",
                "no independent chain-tip witness (signer, public verifier and external sink) is "
                "configured; the committed record cannot be tamper-evidently anchored", count, exceptions)
        try:
            verify_anchor_consistency(self.store_dir, records, verifier=self.anchor_verifier,
                                      external_sink=self.external_anchor_sink)
        except AnchorError as exc:
            return self._stop(iso, exc.code, str(exc), count, exceptions)

        # ── durable-state reconciliation FIRST — before any no-op return ──
        # A same-date retry must not report a healthy no-op while the ledger is behind the record: that
        # is exactly the crash shape (observation committed, ledger save lost) this runner exists to
        # surface, and hiding it here would defer discovery to some later session.
        try:
            ledger = self._load_or_open_ledger(count)
        except IntegrityStop as exc:
            return self._stop(iso, "LEDGER_UNAVAILABLE", str(exc), count, exceptions)

        processed = ledger.state.sessions_processed
        if processed != count:
            code = "LEDGER_AHEAD_OF_RECORD" if processed > count else "LEDGER_BEHIND_RECORD"
            return self._stop(
                iso, code,
                f"ledger has processed {processed} session(s) but committed storage holds {count}; "
                f"recovery is an explicit audited operation — this runner will not repair it",
                count, exceptions)

        if last and last.session_date == iso:
            return SessionRunResult(status=SessionRunStatus.ALREADY_RECORDED, session_date=iso,
                                    session_count=count, sequence=last.sequence,
                                    detail="this session is already committed and the ledger agrees "
                                           "with the record — nothing to do")
        if last and last.session_date > iso:
            return self._stop(
                iso, "SESSION_OUT_OF_ORDER",
                f"session {iso} precedes the last committed session {last.session_date}",
                count, exceptions)

        # ── no eligible session may be stepped over ──
        # The chain being contiguous by SEQUENCE is not enough: the record claims one observation per
        # eligible session, so the requested session must be the next eligible one after the last
        # committed session. A skipped session is refused, never back-filled — closing the hole is a
        # governed adjudication, not a runner decision. (Sequence 1 is exempt: §0 path A lets the record
        # begin at the first eligible session after deployment readiness.)
        if last:
            try:
                expected = next_eligible_session(date.fromisoformat(last.session_date))
            except IntegrityStop as exc:
                return self._stop(iso, "ELIGIBILITY_UNDETERMINED", str(exc), count, exceptions)
            if session_date != expected:
                skipped = [d.isoformat() for d in eligible_sessions(expected, session_date)
                           if d != session_date]
                return self._stop(
                    iso, "MISSED_ELIGIBLE_SESSION",
                    f"the next eligible session after {last.session_date} is {expected.isoformat()}, "
                    f"not {iso}; eligible session(s) never recorded: {skipped}. The record will not "
                    f"skip a session and will not back-fill one — this needs governed adjudication",
                    count, exceptions)

        # ── the session's DATA must be final before anything is decided or booked ──
        if self.readiness is None:
            return self._stop(
                iso, "DATA_READINESS_UNAVAILABLE",
                "no data-finality gate is configured; the session's inputs cannot be shown to be "
                "final, complete and correctly adjusted", count, exceptions)
        try:
            finality = self.readiness.assess(session_date)
        except IntegrityStop as exc:
            return self._stop(iso, "DATA_READINESS_UNAVAILABLE", str(exc), count, exceptions)
        if not finality.ready:
            return self._stop(iso, str(finality.verdict), finality.detail, count, exceptions)

        # ── every security already on the book must be markable at THIS session ──
        unmarkable = self._unmarkable(ledger.state.held, session_date)
        if unmarkable:
            return self._stop(
                iso, "NOT_READY_CURRENT_SESSION_MISSING",
                f"{len(unmarkable)} held security(ies) have no usable mark on {iso} "
                f"(e.g. {unmarkable[:5]}) — the book cannot be valued without carrying a stale price",
                count, exceptions)

        snapshot = self.store_dir / PRE_SESSION_SNAPSHOT
        if snapshot.exists():
            # A previous attempt died. Reconciliation above already proved ledger == record, so the
            # snapshot is redundant — but the crash is recorded rather than quietly overwritten.
            exceptions.append("STALE_PRE_SESSION_SNAPSHOT")
            self._append_stop_log(iso, "STALE_PRE_SESSION_SNAPSHOT",
                                  "a previous attempt left a pre-session snapshot; state reconciled",
                                  count)

        dur = self.durability or default_durability()
        ledger.save(snapshot, durability=dur)                    # audited rollback input

        # ── the SINGLE instrument snapshot, taken HERE — the pre-evaluation boundary ──
        # After readiness, the held-name price reads and the pre-session ledger snapshot, and immediately
        # before the authoritative Account-4 probe and the evaluation. Taken this late so it bounds the
        # instrument's state as close to the decision as possible: a lengthy readiness or data-finality
        # check cannot leave it stale. A pre-configured digest (the stub path) is used only when no
        # capture is wired.
        expected_digest = str(self.expected_snapshot_digest or "").strip()
        if self.snapshot_capture is not None:
            try:
                instrument_snapshot = self.snapshot_capture(session_date)
            except IntegrityStop as exc:
                return self._stop(iso, "INSTRUMENT_SNAPSHOT_UNAVAILABLE", str(exc), count, exceptions)
            if self.bind_snapshot is not None:
                try:
                    self.bind_snapshot(instrument_snapshot)
                except IntegrityStop as exc:
                    return self._stop(iso, "INSTRUMENT_SNAPSHOT_UNAVAILABLE", str(exc), count,
                                      exceptions)
            expected_digest = str(getattr(instrument_snapshot, "snapshot_digest", "") or "").strip()

        # ── the decision + the booking (nothing is written to the record yet) ──
        if not expected_digest:
            return self._stop(
                iso, "INSTRUMENT_SNAPSHOT_UNAVAILABLE",
                "no instrument snapshot was captured for this run; a decision could not be tied to the "
                "state it was taken under", count, exceptions)
        # ── the AUTHORITATIVE Account-4 read, IMMEDIATELY before the instrument is evaluated ──
        # Last of everything: after the readiness assessment, the held-name price reads and the
        # pre-session snapshot. The unchecked interval between this probe and publication is the window
        # in which the live book could move unnoticed, so nothing lengthy is left inside it.
        account4_before: Account4Probe | None = None
        if self.authoritative_account4_probe is not None:
            try:
                account4_before = self.authoritative_account4_probe()
            except IntegrityStop as exc:
                return self._stop(iso, "ACCOUNT4_STATE_UNSAFE", str(exc), count, exceptions)

        evaluator = ForwardEvaluator(ledger=ledger, decision_provider=self.decision_provider,
                                     shadow_ledger_identity=self.shadow_ledger_identity,
                                     expected_snapshot_digest=expected_digest)
        try:
            outcome = evaluator.evaluate_session(session_date, self.price_fn)
        except PriceUnavailable as exc:
            # A decision target (or a held name being re-sleeved) has no mark this session. The
            # production price function refuses rather than valuing it at an earlier price.
            return self._stop(iso, "NOT_READY_CURRENT_SESSION_MISSING", str(exc), count, exceptions)
        except IntegrityStop as exc:
            # Includes the absent-evaluation case: the instrument produced no real decision, so no
            # session is recorded. The in-memory booking (if any) is discarded — the ledger on disk is
            # untouched because it is saved only after a successful commit.
            return self._stop(iso, "NO_VALID_INSTRUMENT_DECISION", str(exc), count, exceptions)

        ctx = self.context_builder(session_date)
        if ctx.session_date != session_date:
            return self._stop(iso, "CONTEXT_SESSION_MISMATCH",
                              f"context built for {ctx.session_date} but the session is {iso}",
                              count, exceptions)

        # the reads are done: prove the store did not move underneath them
        try:
            self.readiness.verify_unchanged(session_date, finality)
        except IntegrityStop as exc:
            return self._stop(iso, "DATA_STORE_CHANGED_DURING_SESSION", str(exc), count, exceptions)

        # ── and prove Account 4 did not move either, before anything is published ──
        if self.authoritative_account4_probe is not None and account4_before is not None:
            try:
                assert_account4_unchanged(account4_before, self.authoritative_account4_probe())
            except IntegrityStop as exc:
                return self._stop(iso, "ACCOUNT4_STATE_CHANGED_DURING_SESSION", str(exc), count,
                                  exceptions)

        decision_evidence = self._decision_evidence(evaluator, outcome)
        operational = _operational_flags(exceptions)
        sealed = _sealed_performance(outcome, ledger)
        # The shadow ledger routes no orders, so `orders` is 0 by construction — the counter describes
        # the ledger, not a broker.
        rebalances, orders, seeds = (1 if outcome.traded else 0), 0, (1 if outcome.record.is_seed else 0)

        try:
            if count == 0:                                       # the governed window-open transition
                _, first_prov, new_count = open_first_window_session(
                    ctx, preflight_timestamp=run_timestamp,
                    deployed_tree_identity=self.deployed_tree_identity,
                    shadow_ledger_identity=self.shadow_ledger_identity,
                    account4_probe=self.account4_probe,
                    rebalances=rebalances, orders=orders, seeds=seeds, operational=operational,
                    sealed_performance=sealed, store_dir=self.store_dir, durability=self.durability,
                    data_finality=finality.to_open_provenance(), decision_evidence=decision_evidence)
                sequence = first_prov.observation_sequence
            else:
                _, prov, new_count = record_forward_session(
                    ctx, preflight_timestamp=run_timestamp,
                    deployed_tree_identity=self.deployed_tree_identity,
                    shadow_ledger_identity=self.shadow_ledger_identity,
                    account4_probe=self.account4_probe,
                    rebalances=rebalances, orders=orders, seeds=seeds, operational=operational,
                    sealed_performance=sealed, store_dir=self.store_dir, durability=self.durability,
                    data_finality=finality.to_open_provenance(), decision_evidence=decision_evidence)
                sequence = prov.observation_sequence
        except IntegrityStop as exc:
            # Not committed => not booked: the ledger is saved only after a successful commit, so the
            # durable ledger still holds the pre-session state.
            return self._stop(iso, "OBSERVATION_NOT_COMMITTED", str(exc), count, exceptions)

        ledger.save(self.ledger_path, durability=dur)            # durable AFTER the commit
        with contextlib.suppress(OSError):
            snapshot.unlink()

        # ── the two INDEPENDENT post-commit durability writes (R5d review) ──
        # The observation is the source of truth. The chain-tip anchor (its separate tamper-witness) and
        # the instrument's own durable book are each written now, in their own storage. The attempts are
        # INDEPENDENT: a failure of one never suppresses the other, so a crash cannot hide a second
        # divergence. Each unwritten artifact is diagnosed on the next run — ANCHOR_BEHIND_RECORD /
        # EXTERNAL_WITNESS_AHEAD for the anchor, BOOK_BEHIND_RECORD for the book — and never silently
        # repaired.
        # BOTH attempts catch broadly and independently: the observation has already advanced, so
        # whatever concrete client exception the signer/sink raises (KMS/HSM/S3 SDK: timeout,
        # credentials, transport, service) must NOT be allowed to escape and suppress the book write.
        anchor_error: Exception | None = None
        try:
            append_anchor(self.store_dir, signer=self.anchor_signer,
                          external_sink=self.external_anchor_sink,
                          deployed_tree_identity=self.deployed_tree_identity,
                          anchored_at=run_timestamp, durability=self.durability)
        except Exception as exc:      # noqa: BLE001 - post-commit: must not suppress the book attempt
            anchor_error = exc
            logger.error("forward_session_anchor_unwritten", session=iso, sequence=sequence,
                         detail=str(exc))

        book_error: Exception | None = None
        if self.on_committed is not None:
            try:
                self.on_committed(sequence, iso)
            except Exception as exc:      # noqa: BLE001 - post-commit: the record already advanced
                book_error = exc
                logger.error("forward_session_book_unpersisted", session=iso, sequence=sequence,
                             detail=str(exc))

        if anchor_error is not None or book_error is not None:
            return self._post_commit_divergence(iso, sequence, new_count, exceptions,
                                                anchor_error, book_error)

        logger.info("forward_session_recorded", session=iso, sequence=sequence,
                    session_count=new_count, traded=outcome.traded)
        return SessionRunResult(status=SessionRunStatus.RECORDED, session_date=iso,
                                session_count=new_count, sequence=sequence,
                                operational_exceptions=tuple(exceptions),
                                detail="observation committed")

    # ── helpers ───────────────────────────────────────────────────────────────────────────────────
    def _post_commit_divergence(
        self, iso: str, sequence: int, new_count: int, exceptions: list[str],
        anchor_error: Exception | None, book_error: Exception | None,
    ) -> SessionRunResult:
        """The precise post-commit durability status: which of the two INDEPENDENT writes (the chain-tip
        anchor, the instrument book) did not land. The observation is committed either way — the record
        advanced, so none of these is retried as an ordinary session."""
        ops = list(exceptions)
        parts: list[str] = []
        if anchor_error is not None:
            ops.append("ANCHOR_WRITE_FAILED_POST_COMMIT")
            parts.append(f"its independent chain-tip anchor was not written ({anchor_error})")
        if book_error is not None:
            ops.append("BOOK_WRITE_FAILED_POST_COMMIT")
            parts.append(f"the instrument book was not persisted ({book_error})")

        if anchor_error is not None and book_error is not None:
            status = SessionRunStatus.RECORDED_BUT_ANCHOR_AND_BOOK_UNPERSISTED
        elif anchor_error is not None:
            status = SessionRunStatus.RECORDED_BUT_ANCHOR_UNWRITTEN
        else:
            status = SessionRunStatus.RECORDED_BUT_BOOK_UNPERSISTED

        detail = (f"the observation committed (sequence {sequence}) but " + "; and ".join(parts)
                  + ". The record has advanced — do NOT retry this session; the next run stops for "
                  "governed adjudication (ANCHOR_BEHIND_RECORD/EXTERNAL_WITNESS_AHEAD for the anchor, "
                  "BOOK_BEHIND_RECORD for the book).")
        return SessionRunResult(status=status, session_date=iso, session_count=new_count,
                                sequence=sequence, operational_exceptions=tuple(ops), detail=detail)

    def _decision_evidence(self, evaluator: ForwardEvaluator, outcome: SessionOutcome) -> dict | None:
        """The provider-call evidence the decision was taken from, bound into the committed record.

        The digest carried by the immutable ForwardDecision must equal the digest of the evidence the
        decision provider bound for this evaluation — otherwise the record would attest to inputs the
        decision did not use. Absent a binding provider this is simply None (the tests' stub path)."""
        decision = evaluator.last_decision
        bound = getattr(self.decision_provider, "bound_evidence", None)
        if decision is None or bound is None:
            return None
        provenance = bound.to_open_provenance()
        expected = getattr(bound, "digest", lambda: "")()
        if decision.input_evidence_digest and expected and decision.input_evidence_digest != expected:
            raise IntegrityStop(
                "the decision's input-evidence digest does not match the evidence bound for this "
                "evaluation — the record cannot attest to inputs the decision did not use")
        provenance["input_evidence_digest"] = decision.input_evidence_digest
        return provenance

    def _unmarkable(self, names: list[str], session_date: date) -> list[str]:
        """Held securities with no usable exact-session mark. Works with either price function: the
        strict production one raises (caught here), the lenient one returns None."""
        missing: list[str] = []
        for ticker in sorted(names):
            try:
                value = self.price_fn(ticker, session_date)
            except PriceUnavailable:
                missing.append(ticker)
                continue
            if value is None or value <= 0:
                missing.append(ticker)
        return missing

    def _count(self) -> int:
        try:
            return len(committed_observations(self.store_dir))
        except IntegrityStop:
            return -1                                            # unknown: storage is invalid

    def _load_or_open_ledger(self, count: int) -> ShadowLedger:
        if self.ledger_path.exists():
            try:
                return ShadowLedger.load(self.ledger_path)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise IntegrityStop(f"durable ledger at {self.ledger_path} is unreadable: {exc}") from exc
        if count != 0:
            raise IntegrityStop(
                f"committed storage holds {count} observation(s) but the durable ledger is missing — "
                f"a forward record may not continue on a fresh ledger")
        return self.ledger_factory()

    def _stop(self, iso: str, code: str, detail: str, count: int,
              exceptions: list[str]) -> SessionRunResult:
        self._append_stop_log(iso, code, detail, count)
        logger.warning("forward_session_integrity_stop", session=iso, code=code, detail=detail,
                       session_count=count)
        return SessionRunResult(status=SessionRunStatus.INTEGRITY_STOP, session_date=iso,
                                session_count=count, exception_code=code, detail=detail,
                                operational_exceptions=tuple([*exceptions, code]))

    def _append_stop_log(self, iso: str, code: str, detail: str, count: int) -> None:
        """Append the operational exception OUTSIDE the sealed performance and OUTSIDE observations/.
        It carries no performance and cannot alter the chain or the session count. A failure to record
        the exception is itself fatal — a stop that leaves no trace is not a governed stop.

        Durability goes through the SAME injected policy the commit protocol uses: the appended bytes
        are fsynced, and on first creation the parent directory is fsynced too so the new directory
        entry survives a crash."""
        line = json.dumps({"session_date": iso, "code": code, "detail": detail,
                           "session_count_at_stop": count,
                           "deployed_tree_identity": self.deployed_tree_identity}, sort_keys=True)
        path = self.store_dir / STOP_LOG_FILENAME
        dur = self.durability or default_durability()
        try:
            self.store_dir.mkdir(parents=True, exist_ok=True)
            created = not path.exists()
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise IntegrityStop(
                f"could not record the operational exception {code} for {iso}: {exc}") from exc
        dur.fsync_file(path)
        if created:
            dur.fsync_dir(self.store_dir)


def _operational_flags(exceptions: list[str]) -> dict:
    """The OPEN, operator-visible §7H operational counters for this session (the execution counters —
    rebalances / orders / seeds — are passed separately, so there is one source for each)."""
    return {
        "scheduled_eval_completed": True,
        "missed_rebalances": 0,
        "duplicate_orders_or_seeds": 0,
        "cap_breaches": 0,
        "broker_local_divergence": 0,
        "unresolved_reservations": 0,
        "manual_perf_affecting_interventions": 0,
        "operational_exceptions": list(exceptions),
    }


def _sealed_performance(outcome: SessionOutcome, ledger: ShadowLedger) -> dict:
    """The SEALED payload: everything that could inform a performance judgement. It is written to a
    segregated artifact and referenced from the open record by digest only (§5.4 no-peeking)."""
    start = ledger.state.starting_capital
    return {
        "strategy_return": outcome.session_return,
        "turnover": outcome.turnover,
        "turnover_cost": outcome.cost_drag,
        "equity_after": outcome.equity_after,
        "cumulative_return": (outcome.equity_after / start - 1.0) if start > 0 else 0.0,
    }
