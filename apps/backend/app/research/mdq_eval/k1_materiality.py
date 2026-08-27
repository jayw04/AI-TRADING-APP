"""K1 — scanner/decision materiality. The frame, the OR truth table, and the governed-input boundary.

## The registered definition, quoted

    K1 — scanner/decision materiality: SIP changes SCAN-001 eligibility, ranking, or GAPPER-relevant
    upstream classification on >= 10% of evaluated session-days, OR corrects >= 1 predeclared
    gate-material IEX observation defect that would otherwise alter eligibility or risk disposition.
    ΔVolume is a required diagnostic, NOT a keep trigger.

## ⚠ Why this module does not compute a governed verdict

K1 is not self-contained. It has two limbs and **neither is executable from the frozen partitions**:

* **Limb A — decision divergence.** Requires replaying SCAN-001 eligibility / ranking (or the
  GAPPER-relevant upstream classification) once per feed per session-day and comparing. That needs a
  decision function, and which function is authoritative is a governed choice.
* **Limb B — predeclared defect correction.** Requires a **predeclared** list of gate-material IEX
  observation defects. The registration uses the word but **contains no such list**. A list assembled
  now, after the corpus exists, would be chosen with knowledge of the data — the post-hoc selection the
  pre-registration quarantine forbids.

## ⭐ The OR truth table — why FAIL is narrower than it looks

`A OR B` over three-valued outcomes is not "not PASS ⇒ FAIL". A **FAIL is only justified when both
limbs were actually evaluable and neither passed.**

| Limb A | Limb B | K1 |
|---|---|---|
| PASS | anything | PASS |
| anything | PASS | PASS |
| FAIL | FAIL | FAIL |
| FAIL | NOT EVALUABLE | **NOT EVALUABLE** |
| NOT EVALUABLE | FAIL | **NOT EVALUABLE** |
| NOT EVALUABLE | NOT EVALUABLE | **NOT EVALUABLE** |

⛔ An earlier revision returned FAIL when limb A missed the threshold while limb B was unavailable.
That is not merely imprecise: FAIL and NOT EVALUABLE have **different consequences under the frozen
verdict rules**. A NOT-EVALUABLE criterion leaves the keep/cancel denominator entirely, so a false FAIL
changes the evaluable denominator and can alter HOLD/STOP reachability.

## ⛔ Injected inputs are diagnostic, not authority

A caller can supply a decision provider or a defect list, and the algorithm runs. But "a caller passed
a callable" is not "the owner bound a governed K1 authority". Until a separately reviewed provider or a
genuinely pre-existing defect declaration exists, results computed from injected inputs are marked
`ungoverned_inputs` and are therefore **diagnostic even when every session was admissible**.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from app.research.mdq_eval.gate import validate_tokens
from app.research.mdq_eval.results import (
    AdmissibilityToken,
    AuthorityRef,
    InputProvenance,
    KOutcome,
    KResult,
    _mint_result,
)

CRITERION = "K1"
THRESHOLD = (
    "decision divergence on >= 10% of evaluated session-days, OR >= 1 predeclared gate-material "
    "IEX observation defect corrected"
)
DEFINITION_SOURCE = "MDQ-001 Registration v1.0 section 4, K1"
DIVERGENCE_THRESHOLD = 0.10

#: ⛔ No governed K1 authority is bound today. These are the visible CURRENT-STATE declaration; the
#: binding itself is an `AuthorityRef` carrying a governed artifact and its digest. Setting either of
#: these to True does NOT create authority — `InputProvenance` derives binding from the presence of a
#: real `AuthorityRef`, precisely so a one-line constant flip cannot make injected data evidentiary.
DECISION_PROVIDER_BOUND = False
DEFECT_REGISTRY_BOUND = False

#: The bindings themselves. Both None until a separately reviewed governance artifact exists.
DECISION_PROVIDER_AUTHORITY: AuthorityRef | None = None
DEFECT_REGISTRY_AUTHORITY: AuthorityRef | None = None


class DecisionProvider(Protocol):
    """A governed replay of the decision under test, for one feed on one session-day.

    The return value is compared for equality across feeds, so it must be a deterministic,
    order-stable description of the decision — eligibility set, ranking, or upstream classification.
    """

    def __call__(self, *, root: Path, feed: str, session: date) -> Any: ...


def _combine(limb_a: KOutcome, limb_b: KOutcome) -> KOutcome:
    """`A OR B` over three-valued logic. FAIL requires BOTH limbs evaluable and neither passing."""
    if KOutcome.PASS in (limb_a, limb_b):
        return KOutcome.PASS
    if limb_a is KOutcome.FAIL and limb_b is KOutcome.FAIL:
        return KOutcome.FAIL
    return KOutcome.NOT_EVALUABLE


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
    """Evaluate K1 under the OR truth table, with each limb's own evaluability tracked separately."""
    if not sessions:
        raise ValueError("K1 needs at least one session")
    sessions = sorted(set(sessions))

    if tokens is None and not diagnostic:
        raise ValueError(
            "K1 requires admissibility tokens for an evidentiary result. Obtain them from "
            "mdq_eval.gate.require_admissible, or pass diagnostic=True for a labelled number."
        )
    scope = validate_tokens(root, sessions, tokens) if tokens is not None else None

    measures: dict[str, Any] = {
        "evaluated_session_days": len(sessions),
        "divergence_threshold": DIVERGENCE_THRESHOLD,
        "delta_volume_note": (
            "ΔVolume is a REQUIRED DIAGNOSTIC under the registered definition and is explicitly "
            "NOT a keep trigger; it may never be used to satisfy K1"
        ),
    }
    missing_inputs: list[str] = []

    # ── limb A: decision divergence ─────────────────────────────────────────────────────────────
    if decisions is None:
        limb_a = KOutcome.NOT_EVALUABLE
        missing_inputs.append(
            "limb A needs a governed SCAN-001 / GAPPER decision provider to replay the decision on "
            "each feed; which decision is authoritative for K1 is a registration question and this "
            "module will not choose one"
        )
    else:
        diverged = [
            s.isoformat() for s in sessions
            if decisions(root=Path(root), feed="iex", session=s)
            != decisions(root=Path(root), feed="sip", session=s)
        ]
        share = len(diverged) / len(sessions)
        measures.update({
            "diverged_session_days": len(diverged),
            "diverged_sessions": diverged,
            "divergence_share": share,
        })
        limb_a = KOutcome.PASS if share >= DIVERGENCE_THRESHOLD else KOutcome.FAIL

    # ── limb B: predeclared gate-material defect correction ─────────────────────────────────────
    if predeclared_defects is None or defect_corrected is None:
        limb_b = KOutcome.NOT_EVALUABLE
        missing_inputs.append(
            "limb B needs a PREDECLARED list of gate-material IEX observation defects. The "
            "registration says 'predeclared' but contains no such list, and assembling one now — "
            "after the corpus exists — would be post-hoc selection barred by the pre-registration "
            "quarantine"
        )
    else:
        corrected = [d for d in predeclared_defects if defect_corrected(d)]
        measures.update({
            "predeclared_defects": len(predeclared_defects),
            "defects_corrected_by_sip": len(corrected),
        })
        limb_b = KOutcome.PASS if corrected else KOutcome.FAIL

    measures["limb_a"] = str(limb_a)
    measures["limb_b"] = str(limb_b)
    if missing_inputs:
        measures["missing_inputs"] = missing_inputs

    outcome = _combine(limb_a, limb_b)
    if outcome is KOutcome.NOT_EVALUABLE:
        detail = (
            f"K1 is NOT EVALUABLE: limb A {limb_a}, limb B {limb_b}. Under the registered OR, a FAIL "
            f"requires BOTH limbs evaluable and neither passing"
            + (f". Missing: {'; '.join(missing_inputs)}" if missing_inputs else "")
        )
    elif outcome is KOutcome.PASS:
        detail = f"K1 met: limb A {limb_a}, limb B {limb_b}"
    else:
        detail = f"K1 not met: both limbs evaluable and neither passed (limb A {limb_a}, limb B {limb_b})"

    # Provenance is computed from the inputs themselves, so the ungoverned reasons cannot be
    # omitted or cleared by whoever builds the result.
    provenance = InputProvenance(
        decision_provider_supplied=decisions is not None,
        decision_provider_authority=DECISION_PROVIDER_AUTHORITY,
        defect_list_supplied=predeclared_defects is not None and defect_corrected is not None,
        defect_registry_authority=DEFECT_REGISTRY_AUTHORITY,
    )
    return _mint_result(
        criterion=CRITERION, outcome=outcome, threshold=THRESHOLD, detail=detail,
        measures=measures, sessions=tuple(s.isoformat() for s in sessions),
        scope=scope, provenance=provenance,
        definition_source=DEFINITION_SOURCE,
    )
