"""ADR-0043 Phase-0 WP7 — Gate O4 decision-time / forensic replay (offline).

Implements AMD-17 + owner D1:

* O4-A uses only pre-first-order evidence → expect INDETERMINATE
  (INSUFFICIENT_EXECUTION_COST or MODEL_UNAVAILABLE);
* O4-B uses complete terminal evidence including fills → expect UNREACHABLE_WITHIN_CAPS;
* decision-time and forensic evidence must not be mixed (look-ahead refuse);
* original instrument termination is preserved separately from counterfactual adjudication;
* Gate O4 requires both O4-A and O4-B to pass.

Does not submit orders or import the order path.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from typing import Any

from app.risk.loss_control.phase0_contracts import (
    REASON_MODEL_UNAVAILABLE,
    REASON_ROUND_TRIP_CAP,
    TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE,
    TIER_D_DISPLAYED_SPREAD,
    VERDICT_INDETERMINATE,
    normalize_round_trip_loss_amount,
    o4a_expected_verdict_and_reason,
    o4b_expected_verdict,
)
from app.risk.loss_control.phase0_reachability import Caps, Reachability, assess


class ReplayKind(StrEnum):
    O4A_DECISION_TIME = "O4A_DECISION_TIME"
    O4B_FORENSIC = "O4B_FORENSIC"


class O4GateVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REFUSED = "REFUSED"


class O4RefuseReason(StrEnum):
    EVIDENCE_MIXED = "EVIDENCE_MIXED"
    LOOKAHEAD_FILLS_IN_DECISION_TIME = "LOOKAHEAD_FILLS_IN_DECISION_TIME"
    FORENSIC_MISSING_FILLS = "FORENSIC_MISSING_FILLS"
    UNEXPECTED_VERDICT = "UNEXPECTED_VERDICT"
    UNEXPECTED_REASON = "UNEXPECTED_REASON"


@dataclass(frozen=True)
class DecisionTimeEvidence:
    """Evidence available before the first broker submission (no fills)."""

    quotes: dict[str, dict[str, Any] | None]
    symbols: tuple[str, ...]
    day_change: Decimal | None
    model_available: bool = True
    evidence_tier: str = TIER_D_DISPLAYED_SPREAD
    fills: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ForensicEvidence:
    """Complete terminal evidence including observed fills."""

    quotes: dict[str, dict[str, Any] | None]
    symbols: tuple[str, ...]
    day_change: Decimal | None
    fills: tuple[dict[str, Any], ...]
    fill_loss_per_round_trip: Decimal
    evidence_tier: str = TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE


@dataclass(frozen=True)
class InstrumentTermination:
    """Original instrument termination — preserved separately from counterfactuals."""

    symbol: str
    reason: str
    at: str | None = None


@dataclass(frozen=True)
class ReplayResult:
    kind: ReplayKind
    gate_verdict: O4GateVerdict
    adjudicated: Reachability | None
    expected_verdict: str
    expected_reason: str | None
    original_termination: InstrumentTermination | None
    refuse_reason: O4RefuseReason | None = None
    detail: str = ""
    counterfactual_notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "gate_verdict": str(self.gate_verdict),
            "expected_verdict": self.expected_verdict,
            "expected_reason": self.expected_reason,
            "refuse_reason": str(self.refuse_reason) if self.refuse_reason else None,
            "detail": self.detail,
            "original_termination": (
                {
                    "symbol": self.original_termination.symbol,
                    "reason": self.original_termination.reason,
                    "at": self.original_termination.at,
                }
                if self.original_termination
                else None
            ),
            "counterfactual_notes": list(self.counterfactual_notes),
            "adjudicated": self.adjudicated.as_dict() if self.adjudicated else None,
        }


@dataclass(frozen=True)
class O4GateResult:
    verdict: O4GateVerdict
    o4a: ReplayResult
    o4b: ReplayResult
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": str(self.verdict),
            "detail": self.detail,
            "o4a": self.o4a.as_dict(),
            "o4b": self.o4b.as_dict(),
        }


def _synthetic_quotes_for_loss(
    symbols: tuple[str, ...],
    loss_per_rt: Decimal,
    caps: Caps,
) -> dict[str, dict[str, Any] | None]:
    """Encode a fill-derived loss/RT as a two-sided book so ``assess`` can project caps."""
    loss = normalize_round_trip_loss_amount(loss_per_rt)
    ask = Decimal("100.00")
    shares = min(
        caps.max_position_qty,
        (caps.max_setup_notional / ask).to_integral_value(rounding=ROUND_DOWN),
    )
    if shares <= 0:
        shares = Decimal("1")
    spread = (loss / shares).quantize(Decimal("0.0001"))
    bid = ask - spread
    return {s: {"bid": str(bid), "ask": str(ask), "age_s": "1"} for s in symbols}


def run_o4a(
    evidence: DecisionTimeEvidence,
    caps: Caps,
    *,
    original_termination: InstrumentTermination | None = None,
) -> ReplayResult:
    """Decision-time replay — Tier D / insufficient cost must refuse to trade."""
    expected_v, expected_r = o4a_expected_verdict_and_reason(
        model_available=evidence.model_available
    )
    if evidence.fills:
        return ReplayResult(
            kind=ReplayKind.O4A_DECISION_TIME,
            gate_verdict=O4GateVerdict.REFUSED,
            adjudicated=None,
            expected_verdict=expected_v,
            expected_reason=expected_r,
            original_termination=original_termination,
            refuse_reason=O4RefuseReason.LOOKAHEAD_FILLS_IN_DECISION_TIME,
            detail="decision-time bundle contains fills (look-ahead); refuse",
        )

    preserve = (
        "counterfactual uses only pre-order evidence; original termination unchanged",
    )

    if not evidence.model_available:
        ok = expected_v == VERDICT_INDETERMINATE and expected_r == REASON_MODEL_UNAVAILABLE
        return ReplayResult(
            kind=ReplayKind.O4A_DECISION_TIME,
            gate_verdict=O4GateVerdict.PASS if ok else O4GateVerdict.FAIL,
            adjudicated=None,
            expected_verdict=expected_v,
            expected_reason=expected_r,
            original_termination=original_termination,
            detail="model unavailable at decision time → INDETERMINATE/MODEL_UNAVAILABLE",
            counterfactual_notes=preserve,
        )

    adj = assess(
        day_change=evidence.day_change,
        quotes=evidence.quotes,
        symbols=list(evidence.symbols),
        caps=caps,
        evidence_tier=evidence.evidence_tier,
    )
    match_v = adj.verdict == expected_v
    match_r = adj.reason_code == expected_r
    if match_v and match_r:
        return ReplayResult(
            kind=ReplayKind.O4A_DECISION_TIME,
            gate_verdict=O4GateVerdict.PASS,
            adjudicated=adj,
            expected_verdict=expected_v,
            expected_reason=expected_r,
            original_termination=original_termination,
            detail="O4-A matched expected INDETERMINATE refusal",
            counterfactual_notes=preserve,
        )
    refuse = (
        O4RefuseReason.UNEXPECTED_VERDICT
        if not match_v
        else O4RefuseReason.UNEXPECTED_REASON
    )
    return ReplayResult(
        kind=ReplayKind.O4A_DECISION_TIME,
        gate_verdict=O4GateVerdict.FAIL,
        adjudicated=adj,
        expected_verdict=expected_v,
        expected_reason=expected_r,
        original_termination=original_termination,
        refuse_reason=refuse,
        detail=(
            f"O4-A got verdict={adj.verdict} reason={adj.reason_code}; "
            f"expected {expected_v}/{expected_r}"
        ),
        counterfactual_notes=preserve,
    )


def run_o4b(
    evidence: ForensicEvidence,
    caps: Caps,
    *,
    original_termination: InstrumentTermination | None = None,
) -> ReplayResult:
    """Forensic replay — complete evidence must yield UNREACHABLE_WITHIN_CAPS."""
    expected_v = o4b_expected_verdict()
    notes = (
        "displayed-spread feasibility premise rejected under fill evidence",
        "original instrument termination preserved separately from counterfactual",
    )
    if not evidence.fills:
        return ReplayResult(
            kind=ReplayKind.O4B_FORENSIC,
            gate_verdict=O4GateVerdict.REFUSED,
            adjudicated=None,
            expected_verdict=expected_v,
            expected_reason=REASON_ROUND_TRIP_CAP,
            original_termination=original_termination,
            refuse_reason=O4RefuseReason.FORENSIC_MISSING_FILLS,
            detail="forensic replay requires observed fills",
            counterfactual_notes=notes,
        )

    syn = _synthetic_quotes_for_loss(
        evidence.symbols, evidence.fill_loss_per_round_trip, caps
    )
    # Prefer fill-derived synthetic projection for the forensic verdict (complete terminal
    # evidence). Caller quotes may be retained for audit but must not inject look-back
    # optimism that overrides fill truth.
    adj = assess(
        day_change=evidence.day_change,
        quotes=syn,
        symbols=list(evidence.symbols),
        caps=caps,
        evidence_tier=evidence.evidence_tier,
    )
    if adj.verdict == expected_v:
        return ReplayResult(
            kind=ReplayKind.O4B_FORENSIC,
            gate_verdict=O4GateVerdict.PASS,
            adjudicated=adj,
            expected_verdict=expected_v,
            expected_reason=REASON_ROUND_TRIP_CAP,
            original_termination=original_termination,
            detail="O4-B matched UNREACHABLE_WITHIN_CAPS",
            counterfactual_notes=notes,
        )
    return ReplayResult(
        kind=ReplayKind.O4B_FORENSIC,
        gate_verdict=O4GateVerdict.FAIL,
        adjudicated=adj,
        expected_verdict=expected_v,
        expected_reason=REASON_ROUND_TRIP_CAP,
        original_termination=original_termination,
        refuse_reason=O4RefuseReason.UNEXPECTED_VERDICT,
        detail=f"O4-B got verdict={adj.verdict}; expected {expected_v}",
        counterfactual_notes=notes,
    )


def run_o4_gate(
    *,
    decision: DecisionTimeEvidence,
    forensic: ForensicEvidence,
    caps: Caps,
    original_termination: InstrumentTermination | None = None,
) -> O4GateResult:
    """Combined Gate O4 — both halves must PASS; mixing is refused up front."""
    # Mixing check: forensic fills must not appear inside the decision-time bundle.
    if decision.fills:
        o4a = run_o4a(decision, caps, original_termination=original_termination)
        o4b = run_o4b(forensic, caps, original_termination=original_termination)
        return O4GateResult(
            verdict=O4GateVerdict.REFUSED,
            o4a=o4a,
            o4b=o4b,
            detail="Gate O4 refused: decision-time and forensic evidence mixed (look-ahead)",
        )

    o4a = run_o4a(decision, caps, original_termination=original_termination)
    o4b = run_o4b(forensic, caps, original_termination=original_termination)
    if o4a.gate_verdict == O4GateVerdict.PASS and o4b.gate_verdict == O4GateVerdict.PASS:
        return O4GateResult(
            verdict=O4GateVerdict.PASS,
            o4a=o4a,
            o4b=o4b,
            detail="Gate O4 PASS: both O4-A and O4-B matched expected verdicts",
        )
    return O4GateResult(
        verdict=O4GateVerdict.FAIL,
        o4a=o4a,
        o4b=o4b,
        detail=(
            f"Gate O4 FAIL: o4a={o4a.gate_verdict} o4b={o4b.gate_verdict} "
            "(both required to pass)"
        ),
    )


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_o4_replay as mod

    src = inspect.getsource(mod)
    needles = [
        "from app." + "services.order_router",
        "import app." + "services.order_router",
        "from app." + "brokers",
        "import app." + "brokers",
        "from app." + "orders",
        "submit_" + "order(",
    ]
    for needle in needles:
        if needle in src:
            raise AssertionError(f"phase0_o4_replay must not reference {needle}")


__all__ = [
    "DecisionTimeEvidence",
    "ForensicEvidence",
    "InstrumentTermination",
    "O4GateResult",
    "O4GateVerdict",
    "O4RefuseReason",
    "ReplayKind",
    "ReplayResult",
    "assert_no_order_path_imports",
    "run_o4_gate",
    "run_o4a",
    "run_o4b",
]
