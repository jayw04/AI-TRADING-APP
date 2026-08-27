"""K1 — scanner/decision materiality. The frame, and an explicit statement of what is missing.

## The registered definition, quoted

    K1 — scanner/decision materiality: SIP changes SCAN-001 eligibility, ranking, or GAPPER-relevant
    upstream classification on >= 10% of evaluated session-days, OR corrects >= 1 predeclared
    gate-material IEX observation defect that would otherwise alter eligibility or risk disposition.
    ΔVolume is a required diagnostic, NOT a keep trigger.

## ⚠ Why this module does not compute a verdict on its own

Unlike K3, K1 is not self-contained. It has two limbs and **neither is executable from the frozen
partitions alone**:

* **Limb A — decision divergence.** Requires replaying SCAN-001 eligibility / ranking (or the
  GAPPER-relevant upstream classification) *twice per session-day*, once on each feed, and comparing
  the decisions. That needs a decision function, and which function is authoritative is a governed
  choice — not something a calculator may pick.
* **Limb B — predeclared defect correction.** Requires a **predeclared** list of gate-material IEX
  observation defects. The registration uses the word "predeclared" but **no such list exists in it**.
  A defect list assembled now, after the corpus exists, would be chosen with knowledge of the data —
  exactly the post-hoc selection the pre-registration quarantine forbids.

So this module implements the *frame* — the session-day denominator, the >= 10% threshold, the
divergence bookkeeping, ΔVolume as a labelled diagnostic — and returns **NOT EVALUABLE with a precise
reason** when the governed inputs are absent.

⛔ It deliberately does not invent a decision function, and it deliberately does not synthesise a
defect list. Either would produce a number that looks like K1 and is not, and the failure would be
invisible: nothing downstream can tell a fabricated definition from a registered one.

⭐ When the owner supplies a governed decision provider, K1 becomes computable through
`evaluate_k1(..., decisions=provider)` with no change to this module's contract.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from app.research.mdq_eval.gate import validate_tokens
from app.research.mdq_eval.results import AdmissibilityToken, KOutcome, KResult

CRITERION = "K1"
THRESHOLD = (
    "decision divergence on >= 10% of evaluated session-days, OR >= 1 predeclared gate-material "
    "IEX observation defect corrected"
)
DEFINITION_SOURCE = "MDQ-001 Registration v1.0 section 4, K1"
DIVERGENCE_THRESHOLD = 0.10


class DecisionProvider(Protocol):
    """A governed replay of the decision under test, for one feed on one session-day.

    The return value is compared for equality across feeds, so it must be a deterministic,
    order-stable description of the decision — eligibility set, ranking, or upstream classification.

    ⛔ Supplying this is a governed choice. This module names the shape; it does not choose the
    function, because which decision is authoritative for K1 is a registration question.
    """

    def __call__(self, *, root: Path, feed: str, session: date) -> Any: ...


def _not_evaluable(reason: str, measures: dict[str, Any], sessions: Sequence[date],
                   tokens: tuple[dict[str, Any], ...]) -> KResult:
    return KResult(
        criterion=CRITERION, outcome=KOutcome.NOT_EVALUABLE, threshold=THRESHOLD, detail=reason,
        measures=measures, sessions=tuple(s.isoformat() for s in sessions),
        evidentiary=bool(tokens), tokens=tokens, definition_source=DEFINITION_SOURCE,
    )


def evaluate_k1(
    root: Path | str,
    sessions: Sequence[date],
    *,
    tokens: Iterable[AdmissibilityToken] | None = None,
    decisions: DecisionProvider | None = None,
    predeclared_defects: Sequence[Any] | None = None,
    defect_corrected: Callable[[Any], bool] | None = None,
    diagnostic: bool = False,
) -> KResult:
    """Evaluate K1 if — and only if — the governed inputs for a limb are present.

    `decisions` drives limb A. `predeclared_defects` + `defect_corrected` drive limb B. With neither,
    the result is NOT EVALUABLE and says exactly which input was missing.
    """
    if not sessions:
        raise ValueError("K1 needs at least one session")
    sessions = sorted(set(sessions))

    if tokens is None and not diagnostic:
        raise ValueError(
            "K1 requires admissibility tokens for an evidentiary result. Obtain them from "
            "mdq_eval.gate.require_admissible, or pass diagnostic=True for a labelled number."
        )
    token_records = validate_tokens(root, sessions, tokens) if tokens is not None else ()

    measures: dict[str, Any] = {
        "evaluated_session_days": len(sessions),
        "divergence_threshold": DIVERGENCE_THRESHOLD,
        "delta_volume_note": (
            "ΔVolume is a REQUIRED DIAGNOSTIC under the registered definition and is explicitly "
            "NOT a keep trigger; it may never be used to satisfy K1"
        ),
    }

    # ── limb B: predeclared gate-material defect correction ─────────────────────────────────────
    limb_b_available = predeclared_defects is not None and defect_corrected is not None
    if limb_b_available:
        corrected = [d for d in (predeclared_defects or []) if defect_corrected(d)]  # type: ignore[misc]
        measures["predeclared_defects"] = len(predeclared_defects or [])
        measures["defects_corrected_by_sip"] = len(corrected)
        if corrected:
            return KResult(
                criterion=CRITERION, outcome=KOutcome.PASS, threshold=THRESHOLD,
                detail=(f"{len(corrected)} predeclared gate-material IEX observation defect(s) "
                        f"corrected by SIP; the registered definition is met on limb B"),
                measures=measures, sessions=tuple(s.isoformat() for s in sessions),
                evidentiary=bool(token_records), tokens=token_records,
                definition_source=DEFINITION_SOURCE,
            )

    # ── limb A: decision divergence across feeds ────────────────────────────────────────────────
    if decisions is None:
        missing = []
        if decisions is None:
            missing.append(
                "limb A needs a governed SCAN-001 / GAPPER decision provider to replay the decision "
                "on each feed; which decision is authoritative for K1 is a registration question and "
                "this module will not choose one"
            )
        if not limb_b_available:
            missing.append(
                "limb B needs a PREDECLARED list of gate-material IEX observation defects. The "
                "registration says 'predeclared' but contains no such list, and assembling one now — "
                "after the corpus exists — would be post-hoc selection barred by the "
                "pre-registration quarantine"
            )
        measures["missing_inputs"] = missing
        return _not_evaluable(
            "K1 is NOT EVALUABLE as registered on the inputs available: " + "; ".join(missing),
            measures, sessions, token_records,
        )

    diverged: list[str] = []
    for session in sessions:
        iex_decision = decisions(root=Path(root), feed="iex", session=session)
        sip_decision = decisions(root=Path(root), feed="sip", session=session)
        if iex_decision != sip_decision:
            diverged.append(session.isoformat())

    share = len(diverged) / len(sessions)
    measures["diverged_session_days"] = len(diverged)
    measures["diverged_sessions"] = diverged
    measures["divergence_share"] = share

    met = share >= DIVERGENCE_THRESHOLD
    return KResult(
        criterion=CRITERION,
        outcome=KOutcome.PASS if met else KOutcome.FAIL,
        threshold=THRESHOLD,
        detail=(
            f"SIP changed the decision on {len(diverged)}/{len(sessions)} evaluated session-days "
            f"({share:.4f}) {'>=' if met else '<'} {DIVERGENCE_THRESHOLD}"
        ),
        measures=measures,
        sessions=tuple(s.isoformat() for s in sessions),
        evidentiary=bool(token_records),
        tokens=token_records,
        definition_source=DEFINITION_SOURCE,
    )
