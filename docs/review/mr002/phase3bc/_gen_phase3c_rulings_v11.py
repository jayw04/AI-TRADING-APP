"""SPQ-1 Phase 3C — owner rulings v1.1: adds R5 (existing-position retention) and R6 (drift-repair
quantity), both taken at the integration seam BEFORE any validation P&L exists.

v1.0 is NOT edited. v1.1 supersedes it and carries every v1.0 key byte-identically except the two
additions plus the version/supersession bookkeeping.

Both rulings resolve a MISSING_SEMANTICS discovered while wiring ruling 2's joint construction into
the qualified evaluator. In both cases the owner declined the "reasonable interpretation" and chose
a fail-closed integrity boundary, because each interpretation would have created P&L-affecting
behavior the frozen material does not specify.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
V10 = os.path.join(_HERE, "MR002_Phase3C_OwnerRulings_v1.0.json")


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


with open(V10, "rb") as fh:
    v10_bytes = fh.read()
v10 = json.loads(v10_bytes)

rec = json.loads(v10_bytes)
rec.pop("record_identity_sha256", None)

rec["version"] = "1.1"
rec["supersedes"] = "MR002_Phase3C_OwnerRulings_v1.0.json"
rec["supersedes_sha256"] = hashlib.sha256(v10_bytes).hexdigest()
rec["supersession_note"] = (
    "v1.0 is unedited. v1.1 adds ruling_R5_existing_position_retention and "
    "ruling_R6_drift_repair_quantity, both taken 2026-08-18 at the integration seam. Every other "
    "key is byte-identical to v1.0."
)

rec["ruling_R5_existing_position_retention"] = {
    "id": "PHASE3C_EXISTING_POSITION_RETENTION",
    "owner_label": "R5",
    "disposition": "EXISTING HOLDINGS PINNED AT y = 1",
    "rule": (
        "existing held positions enter joint construction with retention fixed at y = 1. Partial "
        "reduction of an existing position through the joint-construction solver is NOT executable "
        "in MR-002 validation."
    ),
    "scope_of_the_solver": (
        "the joint optimizer may determine desired weights for NEW construction and may size and "
        "select new positions around existing fixed holdings; it may not silently translate y < 1 "
        "for an existing holding into a partial sale."
    ),
    "why": (
        "the execution semantics for such a sale were never frozen. Implementing them would "
        "require manufacturing commission treatment, realized-P&L allocation between the trimmed "
        "and retained parts, partial borrow accrual basis, and share-rounding rules - none of "
        "which exist in the frozen material."
    ),
    "existing_positions_change_only_by": [
        "an already-defined frozen exit",
        "an independently specified mandatory reduction",
    ],
    "frozen_support": (
        "PreRegistration v0.4 line 191: 'Existing positions remain at fixed shares until exit, "
        "except mandatory reductions.'"
    ),
    "on_infeasibility": {
        "disposition": "INTEGRITY_FAILURE",
        "code": "JOINT_CONSTRUCTION_INFEASIBLE_WITH_FROZEN_HOLDINGS",
        "prohibited_fallbacks": [
            "do NOT fall back to the superseded v1.0 removal cascade",
            "do NOT trim holdings heuristically",
        ],
    },
    "resolves_the_apparent_conflict": (
        "grandfathering governs HELD positions; joint construction governs what may be ADDED "
        "around them. The two frozen components are not in conflict once the boundary is drawn "
        "at that line."
    ),
}

rec["ruling_R6_drift_repair_quantity"] = {
    "id": "DRIFT_REPAIR_TRIGGERED_BUT_QUANTITY_UNDEFINED",
    "owner_label": "R6",
    "disposition": "OCCURRENCE => INTEGRITY_FAILURE",
    "what_is_frozen_and_remains_in_force": [
        "the condition: net-dollar drift outside the +/-5%-of-gross band requires repair",
        "next-open timing",
        "the side to reduce (the larger side)",
        "the deterministic reduction ordering: smallest |entry z| -> oldest position -> "
        "permanent_security_id lexical byte ordering",
    ],
    "what_is_missing": "the AMOUNT to reduce",
    "runner_behavior": (
        "the runner MAY detect the drift and MUST record the already-frozen repair instruction and "
        "its deterministic ordering; it MUST NOT execute a reduction without frozen quantity "
        "semantics."
    ),
    "not_retired": (
        "this is stronger than retirement. The registered repair is NOT retired - the frozen rule "
        "genuinely says repair is mandatory. The correct statement is: mandatory repair exists, "
        "execution quantity is undefined, therefore a real occurrence prevents an admissible "
        "replay. That preserves the preregistration rather than pretending the control does not "
        "exist."
    ),
    "rejected_interpretation_whole_position_until_band": {
        "authorized": False,
        "why": (
            "'exit whole positions in order until |net| <= 5% of gross' sounds natural but "
            "introduces a material economic rule. Depending on position sizes the final "
            "whole-position exit could overshoot neutrality substantially, generate different "
            "commissions, change future occupancy, and materially alter returns. Nothing frozen "
            "says that overshoot is intended."
        ),
    },
    "rejected_interpretation_partial_quantity": {
        "authorized": False,
        "why": "a partial quantity reopens R5, whose execution semantics are likewise unfrozen",
    },
    "why_failure_is_preferred_over_amendment": (
        "neither failure condition may occur in the validation replay at all, in which case the "
        "economic answer is obtained without ever needing the missing semantics. If one does "
        "occur, that is itself load-bearing: it shows the frozen MR-002 strategy cannot be "
        "replayed uniquely under the conditions actually encountered, and only then is it worth "
        "deciding whether defining the reduction quantity merits an explicit amendment. There is "
        "no reason to make that economic choice preemptively."
    ),
}

rec["integrity_stop_is_not_an_economic_verdict"] = (
    "a validation result carrying an integrity stop is INTEGRITY_FAILURE, NOT "
    "VALIDATION_DO_NOT_ADVANCE. A replay-definition failure must never be converted into an "
    "economic failure."
)

rec["phase_3c_operating_model"] = [
    "existing holdings: fixed whole shares",
    "normal frozen exits: executable as already defined",
    "+/-3.5 sigma confirmation trigger: explicitly RETIRED by owner ruling (ruling 1)",
    "new entries: joint construction v1.1-rev-3",
    "joint construction may size/select new positions around existing fixed holdings",
    "joint infeasible with fixed holdings: INTEGRITY_FAILURE",
    "net-dollar drift inside +/-5% of gross: continue normally",
    "net-dollar drift outside +/-5%: record the frozen repair ordering, then INTEGRITY_FAILURE "
    "because the repair quantity is undefined",
    "no partial holdings reduction anywhere",
    "zero new P&L semantics",
]

rec["authorization_boundary"] = dict(v10["authorization_boundary"])
rec["authorization_boundary"]["phase_3c_implementation"] = "AUTHORIZED (owner 2026-08-18)"
rec["authorization_boundary"]["sealed_validation_opening"] = "NOT YET GRANTED"
rec["authorization_boundary"]["push_requirement"] = (
    "the governance batch may remain local and be batched with the Phase 3C implementation and "
    "qualification commits. Before any sealed-opening request, the full authority + implementation "
    "chain must be pushed and reproducible."
)

rec["current_disposition"] = {
    "gap_A_partial_retention": "CLOSED - existing positions pinned y=1",
    "gap_B_drift_repair": "CLOSED - triggered repair with undefined quantity => INTEGRITY_FAILURE",
    "whole_position_until_band_interpretation": "NOT AUTHORIZED",
    "partial_reductions": "NOT AUTHORIZED",
    "phase_3c_implementation": "AUTHORIZED",
    "sealed_validation_opening": "NOT YET GRANTED",
}

rec["record_identity_sha256"] = hashlib.sha256(_canonical(
    {k: v for k, v in rec.items() if k != "record_identity_sha256"})).hexdigest()

out = os.path.join(_HERE, "MR002_Phase3C_OwnerRulings_v1.1.json")
with open(out, "wb") as fh:
    fh.write(_canonical(rec))

carried = [k for k in v10 if k not in ("version", "record_identity_sha256")]
drifted = [k for k in carried if _canonical({k: v10[k]}) != _canonical({k: rec[k]})]
print(json.dumps({
    "identity": rec["record_identity_sha256"],
    "v10_keys_carried": len(carried),
    "v10_keys_byte_identical": len(carried) - len(drifted),
    "intentionally_changed": drifted,
}, indent=1))
