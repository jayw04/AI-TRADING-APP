"""SPQ-1 Phase 3C — owner rulings v1.2: R5A supersedes R5, and the coupling-reduction semantics
are ADOPTED from the already-exercised v1.1 development implementation.

v1.0 and v1.1 are NOT edited or deleted. R5 remains in the record exactly as ruled, marked
SUPERSEDED_BEFORE_IMPLEMENTATION, so the reasoning that produced it stays auditable.

The supersession is evidence-driven: R5 assumed coupling reduction might be exceptional. The
owner-authorized v1.1 A/B/C development evidence falsified that assumption - reductions are
structural to the joint construction adopted as governing by ruling 2.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
V11 = os.path.join(_HERE, "MR002_Phase3C_OwnerRulings_v1.1.json")
DEV_RUN = os.path.join(REPO, "apps", "backend", "scripts", "mr002_development_run.py")
EXEC_MOD = os.path.join(REPO, "apps", "backend", "app", "research", "mr002", "execution.py")
JOINT_MOD = os.path.join(REPO, "apps", "backend", "app", "research", "mr002", "joint_portfolio.py")
DEV_EVIDENCE = os.path.join(REPO, "docs", "implementation", "evidence", "mr_002", "runtime",
                            "MR002_DevelopmentEvidence_v1.1.json")

# The exercised mechanics, as a byte range of the accepted development runner.
BLOCK_FIRST, BLOCK_LAST = 251, 276


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return _sha(fh.read())


with open(DEV_RUN, "rb") as fh:
    dev_raw = fh.read()
block = b"\n".join(dev_raw.split(b"\n")[BLOCK_FIRST - 1:BLOCK_LAST])

with open(V11, "rb") as fh:
    v11_bytes = fh.read()
v11 = json.loads(v11_bytes)

rec = json.loads(v11_bytes)
rec.pop("record_identity_sha256", None)
rec["version"] = "1.2"
rec["supersedes"] = "MR002_Phase3C_OwnerRulings_v1.1.json"
rec["supersedes_sha256"] = _sha(v11_bytes)
rec["supersession_note"] = (
    "v1.0 and v1.1 are unedited and retained. v1.2 adds ruling_R5A_supersession and "
    "ruling_R5A_coupling_reduction_adoption, and marks R5 SUPERSEDED in place. R6 is unchanged."
)

# R5 is marked in place - never rewritten, never removed.
rec["ruling_R5_existing_position_retention"] = dict(v11["ruling_R5_existing_position_retention"])
rec["ruling_R5_existing_position_retention"]["status"] = "SUPERSEDED_BEFORE_IMPLEMENTATION"
rec["ruling_R5_existing_position_retention"]["superseded_by"] = "ruling_R5A_supersession"
rec["ruling_R5_existing_position_retention"]["retained_verbatim"] = (
    "this ruling is preserved exactly as issued. It is not deleted or rewritten, so the reasoning "
    "that produced it, and the evidence that falsified its premise, both remain auditable."
)

rec["ruling_R5A_supersession"] = {
    "id": "PHASE3C_EXISTING_POSITION_RETENTION_SUPERSESSION",
    "owner_label": "R5A",
    "supersedes": "R5 / PHASE3C_EXISTING_POSITION_RETENTION",
    "disposition": "R5's y = 1 pinning is SUPERSEDED BEFORE IMPLEMENTATION",
    "falsified_premise": (
        "R5 rested on the assumption that coupling reduction might be exceptional, so that pinning "
        "y = 1 would rarely bind and the economic answer could still be reached. The "
        "owner-authorized v1.1 A/B/C development evidence falsified that assumption."
    ),
    "falsifying_evidence": {
        "source": "docs/implementation/evidence/mr_002/runtime/MR002_DevelopmentEvidence_v1.1.json",
        "source_sha256": _sha_file(DEV_EVIDENCE),
        "window": "development only, 2013-01-02..2019-10-02, 1,700 sessions",
        "counts": {
            "A": {"new_orders": 669, "coupling_reductions": 434, "exits": 600,
                  "reduce_to_zero_coupling_exits": 68, "sessions_with_entries": 59},
            "B": {"new_orders": 398, "coupling_reductions": 320, "exits": 322,
                  "reduce_to_zero_coupling_exits": 75, "sessions_with_entries": 47},
            "C": {"new_orders": 68, "coupling_reductions": 48, "exits": 40,
                  "reduce_to_zero_coupling_exits": 27, "sessions_with_entries": 6},
        },
        "why_it_is_decisive": (
            "reduction is not incidental behavior of build_joint; it is central to the accepted "
            "v1.1-rev-3 construction. Config B shows 320 coupling reductions against 398 new "
            "orders, and Config C shows 27 reduce_to_zero_coupling exits out of 40 total exits. "
            "Pinning all existing holdings to y = 1 would disable a core mechanism of the very "
            "construction adopted as governing by ruling 2, whose Stage 1 objective is literally "
            "to MINIMIZE forced liquidation - an objective that presupposes liquidation occurs."
        ),
        "extrapolation": (
            "at the Config B development rate of roughly 0.19 reductions per session, the 775 "
            "eligible validation sessions would produce on the order of 150 occurrences. Under R5 "
            "the FIRST one terminates the replay, so Phase 3C would almost certainly have halted "
            "before producing any economic result."
        ),
    },
    "no_mixed_lineage": (
        "no Phase 3C implementation ever existed under R5, and no validation P&L had been "
        "observed, so there is no mixed-semantics execution lineage to reconcile."
    ),
    "unchanged_by_this_supersession": [
        "ruling 1 - the +/-3.5 sigma confirmation trigger remains RETIRED (development evidence "
        "shows exit_hypothesis_failure fired ZERO times across all three configs, so the "
        "retirement is empirically free)",
        "ruling R6 - drift-repair quantity remains undefined; occurrence remains INTEGRITY_FAILURE",
        "the two frozen validation gates and the verdict domain",
    ],
}

rec["ruling_R5A_coupling_reduction_adoption"] = {
    "id": "PHASE3C_COUPLING_REDUCTION_SEMANTICS_ADOPTED",
    "owner_label": "R5A (adoption limb)",
    "disposition": (
        "ADOPT the already-exercised v1.1 development reduction mechanics as the frozen MR-002 "
        "validation coupling-reduction semantics"
    ),
    "nature": (
        "a GOVERNANCE ADOPTION of an existing, previously exercised implementation - NOT "
        "authorization to design a new trim algorithm"
    ),
    "why_adopted": (
        "the mechanics produced the owner-authorized v1.1 A/B/C development evidence and are "
        "necessary to execute the subsequently accepted joint-construction design. The adoption "
        "occurs BEFORE validation P&L is observed and does NOT select among alternative mechanics "
        "based on validation performance."
    ),
    "frozen_semantics": [
        "the joint construction determines retention y",
        "the reduction executes at the governed session's exec_open",
        "reduced notional incurs the existing 10 bps/side execution cost",
        "NAV roll-forward realizes P&L on the reduced shares relative to the existing last_mark "
        "treatment",
        "retained shares continue as the same position with their remaining quantity and state",
        "when the residual position rounds to zero under the already-exercised implementation, "
        "remove it and record reduce_to_zero_coupling",
        "borrow subsequently accrues only on the remaining short exposure, using the existing "
        "frozen borrow machinery",
        "use the exact share and rounding behavior already present in mr002_development_run.py - "
        "do NOT improve or reinterpret it",
    ],
    "no_embellishment": (
        "the semantics are frozen exactly as the accepted development runner exercised them. Any "
        "deviation, improvement, reinterpretation or 'obvious fix' is out of scope and would "
        "reintroduce the post-freeze parameter risk this adoption exists to avoid."
    ),
    "bound_source_bytes": {
        "runner_path": "apps/backend/scripts/mr002_development_run.py",
        "runner_sha256": _sha(dev_raw),
        "runner_bytes": len(dev_raw),
        "mechanics_block_lines": f"{BLOCK_FIRST}-{BLOCK_LAST}",
        "mechanics_block_sha256": _sha(block),
        "mechanics_block_bytes": len(block),
        "mechanics_block_first_line": block.split(b"\n")[0].decode("ascii").strip(),
        "mechanics_block_last_line": block.split(b"\n")[-1].decode("ascii").strip(),
        "supporting_primitives": {
            "apps/backend/app/research/mr002/execution.py": _sha_file(EXEC_MOD),
            "apps/backend/app/research/mr002/joint_portfolio.py": _sha_file(JOINT_MOD),
        },
    },
    "drift_repair_is_a_different_mechanism": (
        "coupling-reduction semantics may NOT be reused as drift-repair semantics merely because "
        "both reduce exposure. They are different registered mechanisms. R6 stands."
    ),
    "qualification_required_before_any_sealed_opening": [
        "partial retention 0 < y < 1",
        "full retention y = 1",
        "full coupling liquidation / reduce_to_zero_coupling",
        "commission charged on reduced notional",
        "retained share quantity correct after reduction",
        "short borrow basis follows remaining shares",
        "NAV/P&L reconciles through the trim",
        "deterministic replay reproduces the same result",
        "a synthetically triggered R6 post-execution drift condition still causes "
        "INTEGRITY_FAILURE rather than borrowing coupling semantics",
        "DIFFERENTIAL: on a non-sealed development fixture/window where reductions occur, the "
        "Phase 3C adapter must agree with the accepted development runner on reduction "
        "quantities, costs, position states and NAV progression - exactly, or within whatever "
        "deterministic numerical tolerance is already frozen. This proves the thin adapter has "
        "not subtly changed the already-exercised economics, and is worth more than another "
        "general test suite.",
    ],
}

rec["ruling_C_sparsity_disclosure"] = {
    "disposition": "DISCLOSE, DO NOT MODIFY THE FROZEN GATE",
    "finding": (
        "Config C entered on only 6 of 1,700 development sessions, so the frozen "
        "'C cumulative net return > 0' gate may be decided by inactivity rather than economics"
    ),
    "prohibited": [
        "no minimum-trades exemption",
        "no replacement of > 0 with >= 0",
        "no different annualization",
        "no reinterpretation of inactivity as a pass",
    ],
    "must_disclose_alongside_the_gate": [
        "number of C entries",
        "number of C exits",
        "invested/exposure days",
        "cumulative net return",
        "transaction and borrow costs",
    ],
    "rationale": (
        "this is exactly what the parameter-stability gate is designed to reveal. If C lands at "
        "zero or negative because it rarely trades, the gate fails as frozen, and we then decide "
        "whether that shows MR-002 is too parameter-fragile. It must not be rescued beforehand."
    ),
}

rec["phase_3c_operating_model"] = [
    "existing holdings: whole shares, reduced ONLY through the adopted coupling-reduction "
    "semantics or a frozen exit",
    "normal frozen exits: executable as already defined",
    "+/-3.5 sigma confirmation trigger: explicitly RETIRED by owner ruling (ruling 1); development "
    "evidence confirms it fired zero times",
    "new entries: joint construction v1.1-rev-3",
    "coupling reductions: ADOPTED v1.1 development mechanics, bound by source bytes",
    "net-dollar drift inside +/-5% of gross: continue normally (the solver enforces the band "
    "ex-ante as a constraint)",
    "post-execution drift repair, if actually triggered: record the frozen ordering, then "
    "INTEGRITY_FAILURE because the repair quantity is undefined (R6)",
    "an integrity stop is INTEGRITY_FAILURE, never VALIDATION_DO_NOT_ADVANCE",
]

rec["current_disposition"] = {
    "R1_3p5_sigma_retirement": "CONFIRMED - development evidence shows it was already inert",
    "R5_y_equals_1": "SUPERSEDED before implementation",
    "coupling_reductions": "ADOPT the exact exercised v1.1 development semantics",
    "R6_drift_repair": "UNCHANGED - undefined quantity => INTEGRITY_FAILURE if actually triggered",
    "config_C_sparsity": "DISCLOSE, do not modify the frozen gate",
    "phase_3c_implementation_and_non_sealed_qualification": "AUTHORIZED",
    "new_sealed_validation_opening": "NOT YET GRANTED",
}

rec["record_identity_sha256"] = hashlib.sha256(_canonical(
    {k: v for k, v in rec.items() if k != "record_identity_sha256"})).hexdigest()

out = os.path.join(_HERE, "MR002_Phase3C_OwnerRulings_v1.2.json")
with open(out, "wb") as fh:
    fh.write(_canonical(rec))

carried = [k for k in v11 if k not in ("version", "record_identity_sha256")]
drifted = [k for k in carried
           if _canonical({k: v11[k]}) != _canonical({k: rec[k]})]
print(json.dumps({
    "identity": rec["record_identity_sha256"],
    "v11_keys_carried": len(carried),
    "v11_keys_byte_identical": len(carried) - len(drifted),
    "intentionally_changed": drifted,
    "mechanics_block_sha256": rec["ruling_R5A_coupling_reduction_adoption"]["bound_source_bytes"]["mechanics_block_sha256"],
}, indent=1))
