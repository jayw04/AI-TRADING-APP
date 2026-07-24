"""Forward per-session evaluator — carries the live production decision into the shadow ledger (R2b).

Option B (owner-ruled): the REAL frozen `MomentumDaily` decides each session (via the §7A-proven
`drift_audit_driver.capture_seam` path against a `DriftCtxAdapter` — production equal weight, 20% cap,
real select / pending-buy / durable state), and the non-ordering shadow ledger BOOKS that decision at
the registered `TURNOVER_COST_BPS = 10.0` (R2a's `book_decision`).

TWO SEPARATE BOOKS, USED FOR SEPARATE PURPOSES (owner ruling 2026-07-23):
  • the INSTRUMENT decision-state book — membership, target/current weights, previous rank, regime state,
    pending-buy + durable state — is the ONLY authority for whether MomentumDaily's drift/membership/
    regime/backstop gate should have fired. It is what `capture_seam` consumes.
  • the SHADOW LEDGER is the governed $100K performance accounting at registered 10-bps turnover cost
    (sealed returns / turnover / cost drag). It intentionally DIVERGES from the instrument book by
    cumulative cost drag, so it must NEVER be used to validate a gate decision.

This module is the seam, and it FAILS CLOSED (owner boundary checks) unless, for each eligible session:
  1. the decision's date exactly equals the session being processed;
  2. the decision came from the real frozen production instrument — an EXACT full-SHA identity match
     against PRODUCTION_STRATEGY_COMMIT (a short frozen binding is honoured only at a governed minimum
     length, and the runtime identity must always be the full SHA);
  3. the decision is structurally the one it claims to be: 0 ≤ regime_gross ≤ 1, no duplicate targets,
     no more targets than the frozen max_names, the weighted names are EXACTLY the target names, the
     weights sum within the regime's own gross, and each weight is the frozen equal-weight/20%-cap
     result the registered production rule would produce (the instrument supplies the weights; this
     check only refuses a sizing shape that rule could not have produced);
  4. `trade_initiated=False` conceals no regime / membership / drift / backstop transition — verified
     against the INSTRUMENT's own decision-state book (LOAD-BEARING). Shadow-ledger drift may be reported
     as a DIAGNOSTIC but never invalidates the run or overrides the instrument decision.
  5. exactly one decision is accepted per eligible session;
  6. no broker / OrderRouter / order-submission / Account-4 mutation path is reachable (structural);
  7. the production durable-state identity and the shadow-ledger accounting identity are distinct;
  8. the registered 10-bps turnover cost is the ONLY performance cost the ledger applies (`book_decision`).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from app.strategies.drift_audit import SeamRecord
from app.validation.first_session import IntegrityStop
from app.validation.forward_window import FROZEN_CONFIG, PRODUCTION_STRATEGY_COMMIT
from app.validation.shadow_ledger import PriceFn, SessionOutcome, ShadowLedger

_GROSS_EPS = 1e-9
_WEIGHT_EPS = 1e-9

# Registered sizing parameters (§2, frozen) — the decision-structure checks are derived from the
# frozen configuration, never from a literal restated here.
_FROZEN_WEIGHTING = str(FROZEN_CONFIG["weighting"])
_MAX_NAMES = int(str(FROZEN_CONFIG["max_names"]))                    # parsed, not asserted: a frozen
_MAX_POSITION_PCT = float(str(FROZEN_CONFIG["max_position_pct"]))    # config that is not numeric fails
                                                                      # loudly at import, not silently

# A full git object name; the runtime identity must always be one.
_SHA_LEN = 40
_HEX = frozenset("0123456789abcdef")
# A frozen binding may legitimately be stored short in legacy configuration, but never shorter than
# this — an arbitrary prefix is not an identity.
_MIN_GOVERNED_SHORT_SHA = 12


class ForwardEvaluationError(IntegrityStop):
    """A per-session boundary check failed. The evaluator fails CLOSED — no decision is booked, the
    session count does not advance. This is a permitted integrity stop, not a performance result."""


@dataclass(frozen=True)
class InstrumentDecisionState:
    """The production instrument's OWN decision-state book — the exact inputs MomentumDaily / capture_seam
    consume for the trade gate. This is the ONLY authority for gate validation. The shadow ledger (a
    cost-adjusted performance overlay) is NEVER used here: it diverges by registered cost drag and would
    raise false drift discrepancies even when the production decision is correct."""
    held: tuple[str, ...]                            # current members in the instrument book
    current_weights: dict[str, float]                 # instrument's CURRENT (drifted) portfolio weights
    last_applied_target_weights: dict[str, float]     # target from the last rebalance (drift baseline)
    prior_applied_gross: float                        # regime state applied before this session
    sessions_since_rebalance: int                     # the instrument's own backstop counter
    weight_drift_threshold: float                     # production drift threshold
    backstop_days: int                                # production backstop


@dataclass(frozen=True)
class ForwardDecision:
    """One session's decision from the live production instrument, with the provenance + instrument
    decision-state the boundary checks require. `record` is the §7A-proven `capture_seam` output;
    `instrument_identity` is the git commit of the frozen production strategy; `durable_state_id`
    identifies the instrument's OWN durable strategy-state store (distinct from the ledger accounting
    store); `instrument_state` is the gate-input snapshot used to verify `trade_initiated`."""
    record: SeamRecord
    instrument_identity: str
    durable_state_id: str
    instrument_state: InstrumentDecisionState
    snapshot_digest: str = ""          # the instrument snapshot this decision was taken under (R5c-2)


DecisionProvider = Callable[[date], ForwardDecision]


@dataclass
class ForwardEvaluator:
    """Drives one governed forward session: obtain the live production decision, run the fail-closed
    boundary checks (gate validation against the INSTRUMENT book), then book it into the shadow ledger
    at the registered turnover cost. `shadow_ledger_drift_diagnostics` records the (non-gating) drift of
    the cost-adjusted ledger book per session — diagnostic only."""
    ledger: ShadowLedger
    decision_provider: DecisionProvider
    shadow_ledger_identity: str
    expected_instrument_identity: str = PRODUCTION_STRATEGY_COMMIT
    _processed_sessions: set[str] = field(default_factory=set)
    shadow_ledger_drift_diagnostics: dict[str, float] = field(default_factory=dict)

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

        # (4) a False trade must conceal no transition — verified against the INSTRUMENT's own book
        _assert_no_concealed_transition(rec, decision.instrument_state)

        # diagnostic only: the cost-adjusted shadow book's drift (never gates, never overrides)
        self.shadow_ledger_drift_diagnostics[iso] = self._shadow_ledger_drift()

        # (8) book at the registered turnover cost ONLY — book_decision (R2a) applies no other cost
        outcome = self.ledger.book_decision(session_date, rec, price_fn=price_fn)

        self._processed_sessions.add(iso)
        return outcome

    def _shadow_ledger_drift(self) -> float:
        """The cost-adjusted ledger book's max weight drift vs its last target — DIAGNOSTIC ONLY."""
        s = self.ledger.state
        if not s.held or s.equity <= 0 or not s.target_w:
            return 0.0
        return max(abs(s.sleeves.get(tk, 0.0) / s.equity - s.target_w.get(tk, 0.0)) for tk in s.held)


def _assert_no_concealed_transition(rec: SeamRecord, st: InstrumentDecisionState) -> None:
    """If the instrument declares no trade, verify — against the INSTRUMENT's own decision-state book —
    that no gate condition was actually present. Uses exactly the state and calculations MomentumDaily
    consumes (membership set, regime gross, `since` vs backstop, and current-vs-last-target weight
    drift). The shadow ledger is NOT consulted here."""
    if rec.trade_initiated:
        return
    held = set(st.held)

    if set(rec.target_names) != held:
        raise ForwardEvaluationError(
            f"trade_initiated=False conceals a MEMBERSHIP change: targets "
            f"{sorted(rec.target_names)} != instrument-held {sorted(held)}")
    if abs(rec.regime_gross - st.prior_applied_gross) > _GROSS_EPS:
        raise ForwardEvaluationError(
            f"trade_initiated=False conceals a REGIME transition: gross {rec.regime_gross} != "
            f"instrument prior_applied {st.prior_applied_gross}")
    if st.sessions_since_rebalance >= st.backstop_days:
        raise ForwardEvaluationError(
            f"trade_initiated=False conceals a BACKSTOP: instrument since "
            f"{st.sessions_since_rebalance} >= {st.backstop_days}")
    if held:
        max_drift = max(abs(st.current_weights.get(tk, 0.0) - st.last_applied_target_weights.get(tk, 0.0))
                        for tk in held)
        if max_drift > st.weight_drift_threshold:
            raise ForwardEvaluationError(
                f"trade_initiated=False conceals DRIFT (instrument book): {max_drift} > "
                f"{st.weight_drift_threshold}")


def _validate_decision_values(rec: SeamRecord) -> None:
    """Prove the decision is STRUCTURALLY the one it claims to be — not merely that its numbers are
    finite. A record may not declare targets AAA/BBB while carrying weights for unrelated names, may
    not exceed the regime's own gross, and (for the frozen equal-weight instrument) may not carry a
    sizing shape the registered production rule could not have produced."""
    g = rec.regime_gross
    if not math.isfinite(g) or not (0.0 <= g <= 1.0):
        raise ForwardEvaluationError(f"regime_gross not finite/in [0, 1]: {g}")

    names = list(rec.target_names)
    if len(set(names)) != len(names):
        raise ForwardEvaluationError(f"target_names contains duplicates: {names}")
    if len(names) > _MAX_NAMES:
        raise ForwardEvaluationError(
            f"{len(names)} targets exceeds the frozen max_names={_MAX_NAMES}: {names}")
    if set(rec.weights) != set(names):
        raise ForwardEvaluationError(
            f"weights describe {sorted(rec.weights)} but the decision targets {sorted(names)} — the "
            f"weights do not describe the stated decision")

    total = 0.0
    for tk, w in rec.weights.items():
        if not math.isfinite(w) or w < 0.0:
            raise ForwardEvaluationError(f"weight for {tk!r} not finite/non-negative: {w}")
        total += w
    if total > g + _WEIGHT_EPS:
        raise ForwardEvaluationError(
            f"weights sum {total} exceeds the regime-allowed gross {g}")

    if not names:
        return
    # Registered sizing conformance. The instrument SUPPLIES the weights (they are never restated as
    # the source of truth — see `drift_audit_driver.capture_seam`); this check only refuses to book a
    # decision whose sizing shape the frozen registered rule could not have produced. If the frozen
    # weighting is ever something other than equal weight, this check must be re-derived, so it fails
    # closed rather than silently passing an unrecognised rule.
    if _FROZEN_WEIGHTING != "equal":
        raise ForwardEvaluationError(
            f"registered sizing conformance covers equal weight only; frozen weighting is "
            f"{_FROZEN_WEIGHTING!r} — re-derive this check before booking any session")
    expected = min(1.0 / len(names), _MAX_POSITION_PCT) * g
    for tk, w in rec.weights.items():
        if abs(w - expected) > _WEIGHT_EPS:
            raise ForwardEvaluationError(
                f"weight for {tk!r} is {w}, not the frozen equal-weight result {expected} "
                f"(min(1/{len(names)}, {_MAX_POSITION_PCT}) × gross {g})")


def _is_full_sha(s: str) -> bool:
    return len(s) == _SHA_LEN and set(s) <= _HEX


def _commit_matches(actual: str, frozen: str) -> bool:
    """Exact commit identity. The RUNTIME identity must always be a full 40-hex git object name, and
    it must equal the frozen binding. A frozen binding stored short in legacy configuration is honoured
    only at a governed minimum length (12 hex characters) and only as a prefix of that full runtime SHA
    — arbitrary bidirectional prefix matching would let an identity like "b" satisfy the production
    provenance boundary."""
    a, f = actual.strip().lower(), frozen.strip().lower()
    if not _is_full_sha(a):
        return False
    if _is_full_sha(f):
        return a == f
    return len(f) >= _MIN_GOVERNED_SHORT_SHA and set(f) <= _HEX and a.startswith(f)
