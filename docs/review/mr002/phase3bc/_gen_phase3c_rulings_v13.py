"""SPQ-1 Phase 3C — owner rulings v1.3: R6A scopes the drift-repair trigger to APPLIED feasible
construction. R6's unscoped trigger is superseded; nothing economic changes.

v1.0, v1.1 and v1.2 are NOT edited or deleted. R6 stays in the record exactly as ruled, marked
SUPERSEDED_BEFORE_VALIDATION_IMPLEMENTATION, so the reasoning that produced it and the evidence
that narrowed it both remain auditable.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
V12 = os.path.join(_HERE, "MR002_Phase3C_OwnerRulings_v1.2.json")


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


with open(V12, "rb") as fh:
    v12_bytes = fh.read()
v12 = json.loads(v12_bytes)

rec = json.loads(v12_bytes)
rec.pop("record_identity_sha256", None)
rec["version"] = "1.3"
rec["supersedes"] = "MR002_Phase3C_OwnerRulings_v1.2.json"
rec["supersedes_sha256"] = hashlib.sha256(v12_bytes).hexdigest()
rec["supersession_note"] = (
    "v1.0-v1.2 are unedited and retained. v1.3 adds ruling_R6A_drift_scope and marks R6's "
    "UNSCOPED TRIGGER superseded in place. R5A and every economic rule are unchanged."
)

rec["ruling_R6_drift_repair_quantity"] = dict(v12["ruling_R6_drift_repair_quantity"])
rec["ruling_R6_drift_repair_quantity"]["status"] = (
    "TRIGGER SCOPE SUPERSEDED_BEFORE_VALIDATION_IMPLEMENTATION by ruling_R6A_drift_scope"
)
rec["ruling_R6_drift_repair_quantity"]["what_survives"] = (
    "the SUBSTANCE of R6 is untouched: where the rule applies, a breach records the frozen "
    "ordering and stops with INTEGRITY_FAILURE because the repair quantity is undefined. Only the "
    "DOMAIN in which it can fire is narrowed."
)
rec["ruling_R6_drift_repair_quantity"]["original_assumption_that_was_wrong"] = (
    "that ANY post-session band breach entered the drift-repair path"
)

rec["ruling_R6A_drift_scope"] = {
    "id": "PHASE3C_DRIFT_REPAIR_SCOPE",
    "owner_label": "R6A",
    "supersedes": "the UNSCOPED trigger of R6 / DRIFT_REPAIR_TRIGGERED_BUT_QUANTITY_UNDEFINED",
    "disposition": (
        "post-execution drift repair applies ONLY after a feasible joint-construction outcome has "
        "been APPLIED"
    ),
    "rule_by_outcome": {
        "FEASIBLE": (
            "apply the governed orders/reductions, then test the resulting book against the "
            "+/-5%-of-gross band using the solver's frozen tolerance"
        ),
        "VALID_ZERO_ENTRY_OUTCOME": (
            "treat as a valid feasible / no-new-entry outcome; if the resulting book is within "
            "band, continue normally. If a genuine post-application band breach somehow occurs, "
            "R6 still applies"
        ),
        "EXECUTION_CONSTRAINED_INFEASIBLE": (
            "do NOT apply R6. Preserve the registered no-trade state and continue the replay "
            "under the already-accepted development semantics"
        ),
    },
    "if_a_feasible_construction_still_breaches": (
        "the original R6 ruling stands: record the frozen repair ordering and stop with "
        "INTEGRITY_FAILURE, because the repair quantity is still undefined"
    ),
    "does_not": [
        "retire R6",
        "invent a repair quantity",
        "change any order quantity, commission, exit timing, sizing rule, candidate selection or "
        "P&L treatment",
    ],
    "classification": "CLASSIFICATION / SCOPING CORRECTION, not an economic change",
    "structural_reason": (
        "EXECUTION_CONSTRAINED_INFEASIBLE is already a registered no-trade construction outcome. "
        "When the constructor returns y == {} and x == {} it has not produced a feasible "
        "post-construction portfolio to which the evaluator's later drift-repair rule can sensibly "
        "apply. Reclassifying that registered outcome as INTEGRITY_FAILURE would make the accepted "
        "v1.1 development semantics internally contradictory."
    ),
    "evidence_that_narrowed_it": {
        "source": (
            "non-sealed development differential run 2026-08-18, Phase 3C vs the accepted "
            "development runner, development window only"
        ),
        "observation": (
            "post-execution band breaches occur if and ONLY if the session outcome is "
            "EXECUTION_CONSTRAINED_INFEASIBLE. On a 252-session development sample: FEASIBLE 24 "
            "sessions, none breached; VALID_ZERO_ENTRY_OUTCOME 1 session, not breached; "
            "EXECUTION_CONSTRAINED_INFEASIBLE 3 sessions, all breached."
        ),
        "first_breach_detail": (
            "2013-05-14, |net|/gross = 0.2052, y_returned = 0, x_returned = 0 - the solver applied "
            "NOTHING; three exits had left twelve positions unbalanced with no feasible way to "
            "trade back into the band"
        ),
        "why_it_is_decisive": (
            "the accepted development evidence recorded 1,032 EXECUTION_CONSTRAINED_INFEASIBLE "
            "sessions for Config B out of 1,700. Under the unscoped trigger every one of them "
            "would retrospectively become an integrity failure, which would reject the very "
            "development behaviour that established the joint construction as governing."
        ),
    },
    "qualification_required": [
        "P1 - all historical EXECUTION_CONSTRAINED_INFEASIBLE development sessions remain "
        "registered no-trade outcomes and do not trigger R6A",
        "P2 - every applied feasible construction in the tested development window ends inside "
        "the neutrality band within the frozen solver tolerance",
        "P3 - a synthetic feasible-but-post-execution-out-of-band case still raises "
        "INTEGRITY_FAILURE, so the control has not become vacuous",
        "and the complete A/B/C development differential reproduces the accepted development "
        "economics",
    ],
    "on_pass": "the Phase 3C semantic implementation is CLOSED",
}

rec["phase_3c_operating_model"] = [
    "existing holdings: whole shares, reduced ONLY through the adopted coupling-reduction "
    "semantics or a frozen exit",
    "normal frozen exits: executable as already defined",
    "+/-3.5 sigma confirmation trigger: RETIRED (ruling 1); development evidence confirms it "
    "fired zero times",
    "new entries: joint construction v1.1-rev-3",
    "coupling reductions: ADOPTED v1.1 development mechanics, bound by source bytes (R5A)",
    "EXECUTION_CONSTRAINED_INFEASIBLE: registered NO-TRADE outcome; NOT an integrity failure (R6A)",
    "after an APPLIED feasible construction, a band breach beyond the frozen solver tolerance "
    "records the frozen ordering and stops with INTEGRITY_FAILURE (R6 substance, R6A scope)",
    "an integrity stop is INTEGRITY_FAILURE, never VALIDATION_DO_NOT_ADVANCE",
]

rec["current_disposition"] = {
    "R1_3p5_sigma_retirement": "CONFIRMED - development evidence shows it was already inert",
    "R5_y_equals_1": "SUPERSEDED before implementation",
    "coupling_reductions": "ADOPTED v1.1 development semantics (R5A)",
    "R6_unscoped_trigger": "SUPERSEDED",
    "R6A_feasible_construction_scope": "AUTHORIZED",
    "EXECUTION_CONSTRAINED_INFEASIBLE": "registered no-trade, NOT an integrity failure",
    "economic_or_pnl_rule_changed": "NONE",
    "full_window_non_sealed_differential": "AUTHORIZED",
    "config_C_sparsity": "DISCLOSE, do not soften the gate; if cumulative net return <= 0 the "
                         "parameter-stability gate FAILS",
    "on_qualification_pass": "finalize executable identity + evidence and push the coherent batch",
    "new_sealed_validation_opening": "STILL NOT GRANTED",
}

rec["record_identity_sha256"] = hashlib.sha256(_canonical(
    {k: v for k, v in rec.items() if k != "record_identity_sha256"})).hexdigest()

out = os.path.join(_HERE, "MR002_Phase3C_OwnerRulings_v1.3.json")
with open(out, "wb") as fh:
    fh.write(_canonical(rec))

carried = [k for k in v12 if k not in ("version", "record_identity_sha256")]
drifted = [k for k in carried if _canonical({k: v12[k]}) != _canonical({k: rec[k]})]
print(json.dumps({
    "identity": rec["record_identity_sha256"],
    "v12_keys_carried": len(carried),
    "v12_keys_byte_identical": len(carried) - len(drifted),
    "intentionally_changed": drifted,
}, indent=1))
