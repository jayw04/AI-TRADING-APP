"""Does the broker's ``last_equity`` agree with an independently reconstructed prior-session close?

⚠ **DORMANT PREPARATORY TOOLING — DELIBERATELY UNREFERENCED.**
Nothing in the runtime imports this module. It has no call site, no scheduler entry, no
persistence, no configuration default, no logging, and it performs NO broker or market-data
reads: every input is passed in. Activation belongs to the evidence-gap acquisition freeze and
a separate acquisition-start decision, not to this file.

**This answers a different question from ADR 0043.** The immutable session baseline answers
*"what baseline did the system capture at the session open?"*. This answers *"is the broker's
reported prior close consistent with one we can rebuild from positions and official closes?"* —
a reconciliation control, not an admission control. Its output must never reach a gate.

    residual = broker_last_equity − reconstructed_prior_close_equity

    residual > 0  ⇒ broker daily P&L reads MORE NEGATIVE than reality ⇒ gate TIGHTER
    residual < 0  ⇒ broker daily P&L reads MORE POSITIVE than reality ⇒ gate WEAKER

Sign is not a matter of degree. A weakening residual is a different failure from a tightening one
of the same size, so it escalates at the reconciliation tolerance rather than at a larger
materiality threshold.

**Boundary-awareness is a precondition, not a detail.** ``Σ qty × prior_close + cash`` is only a
valid reconstruction of the *prior session's* close when the positions and cash are those held
*at* that boundary. Current holdings qualify only when activity since the boundary has been ruled
out; otherwise the caller must say so and the reconstruction is refused rather than approximated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

#: Both baseline constructions agree; nothing to investigate.
STATUS_RECONCILED = "RECONCILED"
#: Broker baseline exceeds the reconstruction ⇒ the daily-loss gate is biased conservative.
STATUS_TIGHTENING = "BROKER_BASELINE_TIGHTENING"
#: Broker baseline falls below the reconstruction ⇒ the daily-loss gate is biased WEAK.
STATUS_WEAKENING = "BROKER_BASELINE_WEAKENING"
#: No defensible reconstruction was possible. Never a number, never a zero.
STATUS_UNAVAILABLE = "RECONSTRUCTION_UNAVAILABLE"

REASON_ACTIVITY_SINCE_BOUNDARY = "activity_since_boundary_not_ruled_out"
REASON_MISSING_PRICE = "missing_prior_close_price"
REASON_NO_BROKER_BASELINE = "no_broker_last_equity"
REASON_NON_POSITIVE_PRICE = "non_positive_prior_close_price"

#: Provisional, derived from the only legitimate disagreement mechanism observed so far:
#: regulatory fees booked against a trade date after that date's close. Absolute, NOT relative —
#: a proportional band grows with the account and would conceal a material defect. To be
#: recalibrated from accrued shadow evidence, not from assumption.
DEFAULT_RECONCILIATION_TOLERANCE = Decimal("1.00")

#: A separate, larger band for operational escalation. Independent of the sign rule below.
DEFAULT_MATERIAL_DIVERGENCE_THRESHOLD = Decimal("100.00")


@dataclass(frozen=True)
class ResidualObservation:
    """One account, one trading date. Evidence only — never an input to a control decision."""

    status: str
    broker_last_equity: Decimal | None
    reconstructed_prior_close_equity: Decimal | None
    residual: Decimal | None
    position_count: int
    reason: str | None = None
    material: bool = False

    @property
    def residual_sign(self) -> int | None:
        """``-1`` weakening, ``+1`` tightening, ``0`` exact. ``None`` when unreconstructed."""
        if self.residual is None:
            return None
        return int(self.residual.compare(Decimal(0)))

    @property
    def reconstructed(self) -> bool:
        return self.status != STATUS_UNAVAILABLE


def reconstruct_prior_close_equity(
    *,
    cash: Decimal,
    quantities: Mapping[str, Decimal],
    prior_closes: Mapping[str, Decimal],
) -> Decimal:
    """``cash + Σ(qty × official prior-session close)``, in exact Decimal arithmetic.

    Raises ``KeyError`` when any held symbol has no price and ``ValueError`` on a non-positive
    price: a partial valuation is not a cheaper answer, it is a wrong one. Callers that want a
    status rather than an exception should use :func:`observe_residual`.
    """
    total = Decimal(cash)
    for symbol, qty in quantities.items():
        if qty == 0:
            continue
        close = prior_closes.get(symbol)
        if close is None:
            raise KeyError(symbol)
        if close <= 0:
            raise ValueError(f"{symbol}: non-positive prior close {close}")
        total += Decimal(qty) * Decimal(close)
    return total


def observe_residual(
    *,
    broker_last_equity: Decimal | None,
    cash: Decimal,
    quantities: Mapping[str, Decimal],
    prior_closes: Mapping[str, Decimal],
    activity_since_boundary: bool,
    tolerance: Decimal = DEFAULT_RECONCILIATION_TOLERANCE,
    material_threshold: Decimal = DEFAULT_MATERIAL_DIVERGENCE_THRESHOLD,
) -> ResidualObservation:
    """Classify the broker baseline against the reconstruction. Pure; performs no I/O.

    ``activity_since_boundary`` must be ``False`` for the reconstruction to be attempted — the
    caller, which knows the fill ledger, asserts that the supplied positions and cash are those
    held at the prior-session boundary. There is no approximation path.
    """
    held = {s: Decimal(q) for s, q in quantities.items() if q != 0}

    if activity_since_boundary:
        return ResidualObservation(
            status=STATUS_UNAVAILABLE, broker_last_equity=broker_last_equity,
            reconstructed_prior_close_equity=None, residual=None,
            position_count=len(held), reason=REASON_ACTIVITY_SINCE_BOUNDARY,
        )
    if broker_last_equity is None:
        return ResidualObservation(
            status=STATUS_UNAVAILABLE, broker_last_equity=None,
            reconstructed_prior_close_equity=None, residual=None,
            position_count=len(held), reason=REASON_NO_BROKER_BASELINE,
        )
    try:
        reconstructed = reconstruct_prior_close_equity(
            cash=cash, quantities=held, prior_closes=prior_closes
        )
    except KeyError:
        return ResidualObservation(
            status=STATUS_UNAVAILABLE, broker_last_equity=broker_last_equity,
            reconstructed_prior_close_equity=None, residual=None,
            position_count=len(held), reason=REASON_MISSING_PRICE,
        )
    except ValueError:
        return ResidualObservation(
            status=STATUS_UNAVAILABLE, broker_last_equity=broker_last_equity,
            reconstructed_prior_close_equity=None, residual=None,
            position_count=len(held), reason=REASON_NON_POSITIVE_PRICE,
        )

    residual = Decimal(broker_last_equity) - reconstructed
    material = abs(residual) > material_threshold

    if abs(residual) <= tolerance:
        status = STATUS_RECONCILED
    elif residual < 0:
        # Weakening escalates AT the reconciliation tolerance, not at the material threshold:
        # a small negative residual still means the gate is looser than it reports.
        status = STATUS_WEAKENING
    else:
        status = STATUS_TIGHTENING

    return ResidualObservation(
        status=status, broker_last_equity=Decimal(broker_last_equity),
        reconstructed_prior_close_equity=reconstructed, residual=residual,
        position_count=len(held), material=material,
    )
