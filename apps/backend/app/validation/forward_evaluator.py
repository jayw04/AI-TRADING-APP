"""Forward per-session evaluator — carries the live production decision into the shadow ledger (R2b).

Option B (owner-ruled): the REAL frozen `MomentumDaily` decides each session (via the §7A-proven
`drift_audit_driver.capture_seam` path against a `DriftCtxAdapter` — production equal weight, 20% cap,
real select / pending-buy / durable state), and the non-ordering shadow ledger BOOKS that decision at
the registered `TURNOVER_COST_BPS = 10.0` (R2a's `book_decision`). The instrument's durable state and the
shadow-ledger accounting state are SEPARATE books (the instrument decides on its own book; the ledger is
the governed performance overlay).

This module is the seam between them, and it FAILS CLOSED (owner boundary checks, 2026-07-23) unless, for
each eligible session:
  1. the decision's date exactly equals the session being processed;
  2. the decision came from the real frozen production instrument (identity == PRODUCTION_STRATEGY_COMMIT);
  3. weights and regime_gross are finite and structurally valid;
  4. `trade_initiated=False` conceals no regime / membership / drift / backstop transition;
  5. exactly one decision is accepted per eligible session;
  6. no broker / OrderRouter / order-submission / Account-4 mutation path is reachable (structural);
  7. the production durable-state identity and the shadow-ledger accounting identity are distinct;
  8. the registered 10-bps turnover cost is the ONLY performance cost the ledger applies (no BacktestContext
     commission / slippage leaks into the sealed performance) — enforced by `book_decision` (R2a).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from app.strategies.drift_audit import SeamRecord
from app.validation.first_session import IntegrityStop
from app.validation.forward_window import PRODUCTION_STRATEGY_COMMIT
from app.validation.shadow_ledger import PriceFn, SessionOutcome, ShadowLedger

_GROSS_EPS = 1e-9
_WEIGHT_SUM_EPS = 1e-9


class ForwardEvaluationError(IntegrityStop):
    """A per-session boundary check failed. The evaluator fails CLOSED — no decision is booked, the
    session count does not advance. This is a permitted integrity stop, not a performance result."""


@dataclass(frozen=True)
class ForwardDecision:
    """One session's decision from the live production instrument, with the provenance the boundary
    checks require. `record` is the §7A-proven `capture_seam` output; `instrument_identity` is the git
    commit of the frozen production strategy that produced it; `durable_state_id` identifies the
    instrument's OWN durable strategy-state store (must be distinct from the ledger accounting store)."""
    record: SeamRecord
    instrument_identity: str
    durable_state_id: str


DecisionProvider = Callable[[date], ForwardDecision]


@dataclass
class ForwardEvaluator:
    """Drives one governed forward session: obtain the live production decision, run the fail-closed
    boundary checks, then book it into the shadow ledger at the registered turnover cost."""
    ledger: ShadowLedger
    decision_provider: DecisionProvider
    shadow_ledger_identity: str
    expected_instrument_identity: str = PRODUCTION_STRATEGY_COMMIT
    _processed_sessions: set[str] = field(default_factory=set)

    def evaluate_session(self, session_date: date, price_fn: PriceFn) -> SessionOutcome:
        iso = session_date.isoformat()

        # (5) exactly one decision per eligible session
        if iso in self._processed_sessions:
            raise ForwardEvaluationError(f"session {iso} already evaluated — exactly one decision per session")

        decision = self.decision_provider(session_date)
        rec = decision.record

        # (1) date must match the session being processed
        if rec.date != iso:
            raise ForwardEvaluationError(f"decision date {rec.date!r} != session {iso!r}")

        # (2) provenance: the real frozen production instrument
        if not _commit_matches(decision.instrument_identity, self.expected_instrument_identity):
            raise ForwardEvaluationError(
                f"decision instrument identity {decision.instrument_identity!r} != frozen production "
                f"{self.expected_instrument_identity!r}")

        # (7) the instrument durable state and the ledger accounting state must be separately identified
        if decision.durable_state_id == self.shadow_ledger_identity:
            raise ForwardEvaluationError(
                "instrument durable-state identity must be DISTINCT from the shadow-ledger accounting "
                f"identity (both {decision.durable_state_id!r})")

        # (3) weights + regime_gross finite and structurally valid
        _validate_decision_values(rec)

        # (4) a False trade must conceal no regime / membership / drift / backstop transition
        self._assert_no_concealed_transition(rec)

        # (8) book at the registered turnover cost ONLY — book_decision (R2a) applies no other cost
        outcome = self.ledger.book_decision(session_date, rec, price_fn=price_fn)

        self._processed_sessions.add(iso)
        return outcome

    def _assert_no_concealed_transition(self, rec: SeamRecord) -> None:
        """If the instrument declares no trade, verify no gate condition is actually present. Membership
        (name set), regime (gross), and backstop (`since`) are book-independent — the ledger's `held`,
        `applied_gross`, and `since` mirror the instrument because the ledger books the instrument's own
        decisions. Drift is checked against the ledger's book as a conservative integrity guard (the two
        books diverge slightly by the cumulative registered cost; see the PR note)."""
        if rec.trade_initiated:
            return
        s = self.ledger.state
        held = set(s.held)

        if set(rec.target_names) != held:
            raise ForwardEvaluationError(
                f"trade_initiated=False conceals a MEMBERSHIP change: targets "
                f"{sorted(rec.target_names)} != held {sorted(held)}")
        if abs(rec.regime_gross - s.applied_gross) > _GROSS_EPS:
            raise ForwardEvaluationError(
                f"trade_initiated=False conceals a REGIME transition: gross {rec.regime_gross} != "
                f"applied {s.applied_gross}")
        if s.since >= self.ledger.backstop_days:
            raise ForwardEvaluationError(
                f"trade_initiated=False conceals a BACKSTOP: since {s.since} >= "
                f"{self.ledger.backstop_days}")
        if held and s.equity > 0 and s.target_w:
            max_drift = max(abs(s.sleeves.get(tk, 0.0) / s.equity - s.target_w.get(tk, 0.0))
                            for tk in held)
            if max_drift > self.ledger.weight_drift_pct:
                raise ForwardEvaluationError(
                    f"trade_initiated=False conceals DRIFT: {max_drift} > {self.ledger.weight_drift_pct}")


def _validate_decision_values(rec: SeamRecord) -> None:
    if not math.isfinite(rec.regime_gross) or rec.regime_gross < 0.0:
        raise ForwardEvaluationError(f"regime_gross not finite/non-negative: {rec.regime_gross}")
    total = 0.0
    for tk, w in rec.weights.items():
        if not math.isfinite(w) or w < 0.0:
            raise ForwardEvaluationError(f"weight for {tk!r} not finite/non-negative: {w}")
        total += w
    if total > 1.0 + _WEIGHT_SUM_EPS:
        raise ForwardEvaluationError(f"weights sum {total} exceeds fully-invested 1.0")


def _commit_matches(actual: str, frozen: str) -> bool:
    """A commit matches if either is a prefix of the other (frozen SHAs may be stored short)."""
    a, f = actual.strip(), frozen.strip()
    return bool(a) and bool(f) and (a.startswith(f) or f.startswith(a))
