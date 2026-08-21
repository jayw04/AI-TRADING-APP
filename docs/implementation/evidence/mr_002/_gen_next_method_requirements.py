"""MR-002 — consolidated PROSPECTIVE requirements for the next method version.

Every requirement here was ruled during 2026-08-21. They are gathered into one record because
this program's characteristic defect is a requirement stated in one place and enforced in another,
which then drifts: six role-transfer defects, a resource policy that kept the pre-Cycle-2C role,
and a durable journal scoped to the artifact that had been lost last time rather than the class.

⛔ THIS RECORD AUTHORIZES NOTHING. It does not resolve the method disposition, does not register a
population, does not freeze anything, and does not permit any opening. It is a specification of
what must be true BEFORE the next freeze, so that the freeze can be evaluated against it rather
than against recollection.

⛔ It also does not license repair of Validation-1 or Validation-2. Both are consumed and closed.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_NextMethodVersion_ProspectiveRequirements",
    "version": "1.0",
    "date": "2026-08-21",
    "status": "PROSPECTIVE SPECIFICATION — not implemented, not frozen, not authorized",
    "authority": "owner rulings 2026-08-21, consolidated",
    "why_consolidated": "this program's characteristic defect is a requirement stated in one "
                        "place and enforced in another. Five prospective requirements were ruled "
                        "across several exchanges today; leaving them scattered would reproduce "
                        "exactly that failure mode.",
    "authorizes": "NOTHING.",
}

REC["context"] = {
    "validation_1": "CONSUMED and CLOSED. Materialization archived, EBS copy removed.",
    "validation_2": "CONSUMED and CLOSED. Terminal = INTEGRITY FAILURE / NOT EVALUATED. "
                    "Materialization archived, EBS copy removed.",
    "economic_verdict": "NONE. MR-002's economics remain unknown; there is no evidence it had "
                        "poor returns, failed its threshold, or would have passed.",
    "method_disposition": "OPEN — the frozen pair did not complete. Whether that reflects an "
                          "inadequate numerical method or a legitimately uncertifiable instance "
                          "is unresolved and must be determined prospectively using "
                          "non-Validation-2 evidence.",
}

# ── R1 ───────────────────────────────────────────────────────────────────────────────────────
REC["R1_numerical_investigation_scope"] = {
    "requirement": "resolve the method disposition using development history and "
                   "synthetic/adversarial cases ONLY.",
    "questions": [
        "under what numerical conditions can PIQP_P2 return PIQP_MAX_ITER_REACHED?",
        "is MAX_ITER a normal non-convergence state that should map to an existing registered "
        "fallback disposition, or does it indicate a genuinely uncertifiable solution?",
        "should the next method change tolerances/iteration limits prospectively, introduce "
        "another frozen fallback, define MAX_ITER as a hard stop, alter conditioning/scaling "
        "before optimization, or change solver architecture?",
        "can a new solver rule survive large synthetic/adversarial numerical stress before "
        "another holdout is registered?",
    ],
    "prohibited": "the consumed Validation-2 instance must not be used to optimize the solution. "
                  "No rerun, no replay from either archived materialization, no allowlist "
                  "widening against the consumed population, no solver substitution or iteration "
                  "increase evaluated on it.",
    "note": "the label must not presuppose the answer. 'METHOD REQUIRES REVISION' was withdrawn "
            "in favour of 'OPEN' precisely because one admissible outcome is that the numerical "
            "method was correct and the EVALUATION PROTOCOL needs a defined policy for legitimate "
            "hard stops.",
}

# ── R2 ───────────────────────────────────────────────────────────────────────────────────────
REC["R2_stage_boundary_evidence"] = {
    "invariant": "every completed governed stage must durably commit sufficient evidence of its "
                 "completion BEFORE the next stage begins. A later failure must not erase "
                 "evidence already established.",
    "why": "the monolithic final report is written once, at the end. When the 2026-08-21 replay "
           "stopped mid-way, the Stage-3 invocation census, fold assignment, window summary, "
           "per-config statistics and decision all vanished together — permanently, on a "
           "population that can never be re-run. This is the SECOND occurrence: the durable read "
           "journal exists because a replay failure destroyed the 2026-08-19 evidence, and it was "
           "scoped to reads. An evidence fix scoped to the last loss is one layer short of the "
           "next one.",
    "minimum_coverage": [
        "run / authority opening",
        "object read intent and verified reads",
        "materialization completion and logical identity",
        "window / session validation",
        "fold assignment completion",
        "each configuration replay start and completion",
        "relevant replay-summary identity",
        "Stage-3 invocation, routing and status evidence",
        "per-configuration completion",
        "gate-input construction",
        "gate evaluation",
        "decision",
        "terminal disposition",
    ],
    "refinement_that_matters": "do NOT stream every intermediate economic value into a "
                               "human-readable journal. That creates a new observational surface "
                               "and makes partial-result inspection easier. Prefer durable stage "
                               "records plus hashes/identities plus the minimum needed to "
                               "reconstruct the evidence chain, with detailed per-stage artifacts "
                               "sealed as they complete where necessary.",
    "access_rule": "during a live holdout evaluation, intermediate journal records are CUSTODY "
                   "EVIDENCE, not an operator feedback channel. They are not inspected for "
                   "economic interpretation before terminal closure. Durability must not become "
                   "incremental holdout peeking.",
    "scope": "implement and test on development data only; freeze before another holdout.",
}

# ── R3 ───────────────────────────────────────────────────────────────────────────────────────
REC["R3_materialization_immutability"] = {
    "requirement": "materialization immutability must become INTENTIONAL and UNIFORM.",
    "evidence_that_it_is_currently_incidental": "the Validation-1 run set chattr +i on its "
        "materialized database; the Validation-2 run did not. The V2 file deleted without "
        "resistance while the V1 file returned EPERM. Neither behaviour was specified — it "
        "differed by cycle.",
    "protocol": [
        "finish and fsync the materialization",
        "compute and JOURNAL its byte/content identity",
        "set the local artifact IMMUTABLE before evaluation begins",
        "record the immutable state as a stage-boundary event",
        "permit removal only under an explicit custody-transfer procedure that temporarily clears "
        "immutability and RE-VERIFIES the artifact before deletion",
    ],
    "why_the_re_verification_step_is_load_bearing": "clearing immutability opens a real mutation "
        "window. The 2026-08-21 V1 transfer re-computed the SHA-256 inside that window and "
        "required it to equal the archived bytes before deleting; without that step, 'the archived "
        "copy matches' and 'the deleted copy matched' are different claims.",
    "belongs_with": "R2, the stage-journaling work. NOT a repair to Validation-1 or Validation-2.",
}

# ── R4 ───────────────────────────────────────────────────────────────────────────────────────
REC["R4_gate_11_is_not_transferable"] = {
    "requirement": "any future holdout must establish its OWN live resource-policy authorization "
                   "decision. The 2026-08-21 HEAD success is scoped to that opening and that "
                   "population and is not a reusable readiness credential.",
    "static_half": "live bucket-policy identity, the governed reader ARN, the exact resource "
                   "scope, absence of any never-provisioned placeholder, a current-role Sid, and "
                   "a combined bucket+identity authorization evaluation that raises on any "
                   "unmodelled construct and is mutation-controlled.",
    "live_half": "metadata-only pinned-version HeadObject probes across the whole registered "
                 "population, BEFORE any content read, with zero content calls and zero body "
                 "bytes. A pinned-version HeadObject authorizes under the same action as the "
                 "pinned content read, so it proves the exact decision the read will receive.",
    "mechanical_not_discretionary": "the transition from probe to content read must abort on "
                                    "failure without anyone deciding to stop.",
    "readiness_v5_0_is_not_amended": "v5.0 records gate_11.is_true = false. That was a truthful "
                                     "PRE-OPENING statement and is deliberately left as written. "
                                     "The scoped live closure lives in the TerminalOutcome.",
}

# ── R5 ───────────────────────────────────────────────────────────────────────────────────────
REC["R5_next_population"] = {
    "sequence": "numerical-method revision -> development qualification -> FREEZE -> new "
                "prospective registration -> new holdout accrual -> one-shot validation",
    "prohibited": "do NOT rename any subset of consumed Validation-2 as Validation-3. The next "
                  "holdout starts STRICTLY AFTER the registered Validation-2 window and is "
                  "defined prospectively, AFTER the method is frozen.",
    "why_that_warning_is_necessary_here": "the Cycle-2C redesignation of the oos/ prefix is this "
                                          "program's own precedent for exactly that move, and it "
                                          "cost six role-transfer defects.",
    "selection_hazard": "knowledge that post-window observations already exist must not become a "
                        "reason to choose a start/end boundary based on their unseen behaviour. "
                        "Determine which accrued dates are admissible only AFTER the prospective "
                        "registration is fixed.",
    "quarantine": "keep the accrued post-Validation-2 period conceptually quarantined while the "
                  "numerical and evidence work proceeds.",
}

REC["custody_is_closed_and_separate"] = {
    "validation_1_materialization": "mr002/consumed-validation1-custody/2026-08-19/ — archived, "
                                    "verified, EBS copy removed",
    "validation_2_materialization": "mr002/consumed-validation2-custody/2026-08-21/ — archived, "
                                    "verified, EBS copy removed",
    "resource_denial":
        "MR002_ConsumedHoldoutCustodyDenial_v2.0 / "
        "4944eb59bc01cc56c1395349cc37843c9f69e43c7c2728efcc5a2e1e9a15f134, deny-only, both "
        "prefixes, proven behaviourally from the evaluator host",
    "host_sweep": "consumed-holdout material remaining solely on EBS: 0. NEEDS_RULING: 0.",
    "standing_rule": "run apps/backend/scripts/mr002_host_decommissioning_sweep.py before "
                     "terminating any MR-002 host. Evidence-linked content identity first, path "
                     "rules second, NEEDS_RULING when unresolved.",
    "both_archives_are": "EVIDENCE ONLY. Querying either for research or diagnosis is prohibited.",
}

REC["boundary"] = {
    "latch": "8 / CLOSED, canonical 44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba"
             "999fab48",
    "host": "stopped",
    "new_holdout_opening": "NOT AUTHORIZED",
    "paper_activation": "NOT AUTHORIZED",
    "production_activation": "NOT AUTHORIZED",
}

if __name__ == "__main__":
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_NextMethodVersion_ProspectiveRequirements_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR002_NextMethodVersion_ProspectiveRequirements_v1.0")
    print("  identity   %s" % ident)
    print("  status     %s" % REC["status"])
    print("  R1 numerical investigation scope (development + synthetic only)")
    print("  R2 stage-boundary evidence, with the no-peeking access rule")
    print("  R3 materialization immutability, intentional and uniform")
    print("  R4 gate 11 is not transferable")
    print("  R5 next population, prospective and strictly after the V2 window")
