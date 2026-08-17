"""SPQ-1 Phase 3B — owner label adjudication v2.0 + Semantic Reconciliation Matrix v1.3 (2026-08-17).

Records the owner's adjudication of `relation` and `spinoff` under the frozen prospective frame
MR002_Phase3B_ProspectiveLabelAdjudication_v1.0 (ed56601c...), following Sharadar's support reply
("They are answered by reviewing SHARADAR/INDICATORS and looking at the underlying data") and the
vendor-directed data review executed 2026-08-17. All six frozen questions are answered per label,
each with cited admissible evidence and a stated refusal condition.

Zero-data: no sealed access, no validation read, no OOS read, no host start, no opening requested.
The materiality gate is RETAINED UNCHANGED. The evidence files are bound by recomputed SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = str(Path(_HERE).resolve().parents[3])

ADJUDICATION_DATE = "2026-08-17"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(record: dict, name: str) -> str:
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, name)
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {name}")
    print(f"identity {record['record_identity_sha256']}")
    return record["record_identity_sha256"]


# ---- bind the frame, the superseded attempt, the prior matrix and the evidence -----------------
FRAME = os.path.join(_HERE, "MR002_Phase3B_ProspectiveLabelAdjudication_v1.0.json")
ATTEMPT_V1 = os.path.join(_HERE, "MR002_Phase3B_LabelAdjudicationAttempt_v1.0.json")
MATRIX_V12 = os.path.join(_HERE, "MR002_Phase3B_SemanticReconciliationMatrix_v1.2.json")

EVIDENCE = {
    "vendor_directed_review_doc": "docs/implementation/MR002_Sharadar_VendorDirected_Data_Review_v1.0.md",
    "indicators_actions": "docs/implementation/evidence/sharadar_indicators/indicators_actions.json",
    "indicators_actiontypes": "docs/implementation/evidence/sharadar_indicators/indicators_actiontypes.json",
    "indicators_retrieval_manifest": "docs/implementation/evidence/sharadar_indicators/retrieval_manifest.json",
    "structural_facts_devbound": "docs/implementation/evidence/sharadar_underlying_structural/actions_structural_facts_devbound.json",
    "actiontypes_relation_786f22e": "docs/implementation/evidence/sharadar_actiontypes/relation.json",
    "actiontypes_spinoff_786f22e": "docs/implementation/evidence/sharadar_actiontypes/spinoff.json",
    "actiontypes_spinoffdividend_786f22e": "docs/implementation/evidence/sharadar_actiontypes/spinoffdividend.json",
    "actiontypes_spunofffrom_786f22e": "docs/implementation/evidence/sharadar_actiontypes/spunofffrom.json",
}
evidence_sha = {k: _sha256_file(os.path.join(ROOT, v)) for k, v in EVIDENCE.items()}
frame_sha = _sha256_file(FRAME)
attempt_sha = _sha256_file(ATTEMPT_V1)
matrix12_sha = _sha256_file(MATRIX_V12)

VENDOR_REPLY = (
    "Sharadar support, 2026-08-17, in response to the five escalated questions: 'They are answered "
    "by reviewing SHARADAR/INDICATORS and looking at the underlying data.' The reply is itself a "
    "semantic fact: the vendor deems the published INDICATORS definitions complete and data-level "
    "structure an authorized basis for the remaining answers. The owner ACCEPTED that basis for "
    "these labels specifically; the frame's general prohibition on inferring semantics from "
    "co-occurrence is NOT withdrawn elsewhere."
)

adjudication = {
    "record_type": "MR002_Phase3B_LabelAdjudication",
    "version": "2.0",
    "artifact_kind": "OWNER_ADJUDICATION",
    "produced_at": f"{ADJUDICATION_DATE}T00:00:00Z",
    "authorized_by": (
        "owner adjudication 2026-08-17, given in full after reviewing the vendor-directed data "
        "review. Verbatim dispositions: 'relation -> KNOWN_INFORMATIONAL_LINKAGE / "
        "NO_PHASE3B_EXECUTION_EFFECT'; 'spinoff -> ECONOMICALLY_CONSUMED structural event'; "
        "'spinoffdividend -> ECONOMICALLY_CONSUMED value component of the same event'; "
        "'spunofffrom -> UPSTREAM/CHILD-SIDE METADATA, no independent economic effect'; 'Further "
        "Sharadar inquiry: NOT REQUIRED before implementation'; 'No validation/opening state "
        "changes from this adjudication alone.'"
    ),
    "frame": {
        "record": "MR002_Phase3B_ProspectiveLabelAdjudication_v1.0",
        "record_identity_sha256_of_file": frame_sha,
        "conformance": (
            "both in-scope labels answered on all six frozen questions; evidence cited to "
            "admissible sources only; refusal conditions stated; the gate untouched; "
            "bankruptcyliquidation and listed remain KNOWN_UNADJUDICATED and are NOT adjudicated"
        ),
    },
    "supersedes": {
        "record": "MR002_Phase3B_LabelAdjudicationAttempt_v1.0",
        "record_identity_sha256_of_file": attempt_sha,
        "why": (
            "the v1.0 attempt concluded INCOMPLETE on the then-true premise that no authoritative "
            "vendor semantics were available. The vendor has since published-and-pointed: the "
            "descriptions/INDICATORS metadata (786f22e) plus the vendor-directed underlying-data "
            "review close the evidential gap. v1.0 is preserved, not rewritten."
        ),
    },
    "vendor_reply": VENDOR_REPLY,
    "evidence_bound_by_sha256": evidence_sha,
    "labels": {
        "relation": {
            "classification": "KNOWN_INFORMATIONAL_LINKAGE / NO_PHASE3B_EXECUTION_EFFECT",
            "Q1_vendor_meaning": (
                "'Provides linkage between multiple securities issued by the same issuer. The "
                "ticker field represents what we consider to be the primary security from the "
                "issuer. The contraticker field represents the ticker that is related to the "
                "primary ticker.' (INDICATORS, verbatim; unittype N/A). Per the vendor reply, this "
                "definition is complete."
            ),
            "Q2_category": (
                "inert/context-only: informational issuer/security linkage. NOT identity-changing: "
                "it does not establish predecessor/successor continuity and does not replace the "
                "ticker-change lineage channel."
            ),
            "Q3_execution_consequence": (
                "NONE, stated as a decision: no t+1 execution consequence, no economic consequence, "
                "no identity consequence by itself. Channel 3 only - observable, auditable, never "
                "economic."
            ),
            "Q4_coexistence": (
                "may coexist with economically meaningful actions (bounded incidence: 7/98 rows "
                "co-date with delisted/acquisitionby/dividend) and contributes NO precedence of its "
                "own: the channel-3 audit identity names a relation only when no delisting, "
                "economic or inert kind is present on the session."
            ),
            "Q5_evidence": (
                "convergent, not merely suggestive: relation.value populated in 0/98 bounded rows; "
                "name==contraname in 98/98 (always same-issuer); observed relationship classes are "
                "parallel securities (share classes, preferred series, listed units/notes), not "
                "lineage transitions; ticker-change remains the separate vendor mechanism carrying "
                "the only explicit conjunction rule. Sources: indicators_actiontypes (sha bound), "
                "structural_facts_devbound (sha bound), vendor reply 2026-08-17."
            ),
            "Q6_refusal_condition": (
                "a relation row on a unit's relevant session carrying a POPULATED value is outside "
                "the adjudicated premise: the unit refuses as "
                "CANDIDATE_REFUSED:ACTION_KIND_UNADJUDICATED|KNOWN_UNADJUDICATED - fail closed, "
                "new adjudication required, never silent reinterpretation. relation.date is "
                "retained only as the vendor-record date and must not be assigned execution "
                "meaning; the meaning of a standalone relation.date remains vendor-undocumented "
                "and is deliberately given NO execution semantics."
            ),
        },
        "spinoff": {
            "classification": (
                "ECONOMICALLY_ADJUDICATED composite structural event (parent-side), with "
                "spinoffdividend as the value component of the SAME event and spunofffrom as "
                "child-side metadata (EXPLICITLY_INERT, unchanged)"
            ),
            "Q1_vendor_meaning": (
                "spinoff: parent in ticker, spun-off company in contraticker, value = number of "
                "child shares issued per parent share (ratio). spinoffdividend: same event shape, "
                "value = dollar value of child shares issued per parent share (USD/share). "
                "spunofffrom: the child-side record, same ratio. (INDICATORS, verbatim in the "
                "bound evidence.)"
            ),
            "Q2_category": (
                "economic, composition-dependent: one spinoff EVENT may be published as up to "
                "three vendor rows (parent structural + parent value + child mirror). The scalar "
                "one-kind-per-(ticker,session) abstraction is definitively inadequate here; the "
                "normalizer must recognize the composite."
            ),
            "Q3_execution_consequence": (
                "consumed by the economic channel as ONE event whose structural kind is 'spinoff': "
                "(a) an unconstructible adjusted open on the event session stops the record "
                "(STOP_CORPORATE_ACTION), exactly as for other economic kinds - 'spinoff' joins "
                "enrichment._CORPORATE_ACTION_KINDS; (b) a published spinoffdividend dollar value "
                "is consumed by the registered distribution term of the economic gap (same "
                "USD/share machinery as a cash dividend) WITHOUT collapsing the event identity "
                "into 'dividend' - the published corporate_action_identity remains the spinoff "
                "composition's; (c) a spinoff with NO published dollar value is a VALID event with "
                "the value component absent - it must NOT refuse, and the distribution term is "
                "0.0. Owner caution recorded verbatim: 'do not collapse spinoffdividend into an "
                "ordinary cash dividend... the event identity must remain a spinoff composition so "
                "the parent/child semantics are not lost.'"
            ),
            "Q4_coexistence": (
                "the ONLY authorized composition rule, per the frame's Q4 carve-out: spinoff + "
                "spinoffdividend on one relevant session are complementary records of one event "
                "and normalize to a single economic consumption. NO general composition rule is "
                "created: a spinoff co-occurring with a DIFFERENT economic kind (dev census: "
                "spinoff+split x4) still refuses as ACTION_COMPOSITION_UNRESOLVED. spunofffrom "
                "never creates a second economic action and never conflicts with the parent-side "
                "event."
            ),
            "Q5_evidence": (
                "full-key (ticker,date,contraticker) join over the bounded window: 65/75 spinoff "
                "rows have a matching spinoffdividend, 10 are spinoff-only, ZERO spinoffdividend "
                "rows exist alone; values are the two denominations of the same distribution; "
                "13/75 spunofffrom child mirrors, same date AND identical ratio in 13/13. Sources: "
                "structural_facts_devbound (sha bound), indicators_actiontypes (sha bound), vendor "
                "reply 2026-08-17. The owner rules the 10 spinoff-only rows 'value "
                "unavailable/not published', NOT 'event invalid'."
            ),
            "Q6_refusal_condition": (
                "(a) spinoffdividend on a relevant session WITHOUT its parent-side spinoff row - "
                "never observed in the bounded window - is a value component without its "
                "structural event and refuses the unit as "
                "CANDIDATE_REFUSED:ACTION_COMPOSITION_UNRESOLVED; (b) the spinoff composite "
                "beside any OTHER economically adjudicated kind refuses as before; (c) neither "
                "condition may be silently reinterpreted - widening either needs new adjudication."
            ),
        },
    },
    "residuals_dispositioned_without_vendor_followup": {
        "standalone_relation_date_meaning": "no execution meaning assigned; vendor-undocumented; recorded, not blocking",
        "relation_value_outside_bounded_window": "does not alter current semantics; if encountered, the Q6 refusal fires - fail closed or new adjudication, never silent reinterpretation",
        "spinoff_without_dollar_value": "valid structural event with the value component absent; must not refuse",
        "further_sharadar_inquiry": "NOT REQUIRED before implementation (owner ruling)",
    },
    "unchanged": {
        "materiality_gate": "RETAINED UNCHANGED, including the 1%/5-unique-symbol disjunctive limbs",
        "still_KNOWN_UNADJUDICATED": ["bankruptcyliquidation", "listed"],
        "openings": "4 spent; none requested or granted here; the frame's ordering stands: implement, test, rebind, stage, dry-preflight before a fifth opening is even considered",
        "run_4": "COMPLETED / qualification FAIL / evidence inadmissible / no verdict - unchanged",
        "validation_and_oos": "untouched",
    },
    "grants": "the semantic mappings above, for implementation. NOTHING else - no opening, no gate change, no verdict.",
}

matrix = {
    "record_type": "MR002_Phase3B_SemanticReconciliationMatrix",
    "version": "1.3",
    "artifact_kind": "SEMANTIC_RECONCILIATION",
    "produced_at": f"{ADJUDICATION_DATE}T00:00:00Z",
    "authorized_by": "owner adjudication 2026-08-17 (MR002_Phase3B_LabelAdjudication_v2.0)",
    "boundary": "Zero-data. NO sealed access. Derived entirely from the v2.0 adjudication.",
    "supersedes": {
        "record": "MR002_Phase3B_SemanticReconciliationMatrix_v1.2",
        "record_identity_sha256_of_file": matrix12_sha,
        "scope_of_change": (
            "membership and two frozen rules. Everything else - the three channels, the refusal "
            "scope, the relevance definition, Matrix A, AUDIT-IDENTITY-PRECEDENCE's existing "
            "ordering - carries forward verbatim in substance."
        ),
    },
    "membership_changes": {
        "KNOWN_UNADJUDICATED": {
            "was": ["bankruptcyliquidation", "listed", "relation", "spinoff"],
            "now": ["bankruptcyliquidation", "listed"],
        },
        "KNOWN_INFORMATIONAL_LINKAGE": {
            "was": "class did not exist",
            "now": ["relation"],
            "semantics": (
                "a SIXTH vocabulary class: channel 3 only, outside the economic conflict guard, "
                "outside the uniqueness guard, no execution/economic/identity effect. Distinct "
                "from EXPLICITLY_INERT so the v1.1 frozen membership of that class is not "
                "retroactively rewritten and the adjudication basis (vendor-directed data review) "
                "stays legible per class."
            ),
        },
        "ECONOMICALLY_ADJUDICATED": {
            "was": "enrichment._CORPORATE_ACTION_KINDS without 'spinoff'",
            "now": "enrichment._CORPORATE_ACTION_KINDS including 'spinoff'",
            "single_authority_preserved": (
                "candidates.ECONOMICALLY_ADJUDICATED continues to IMPORT the enrichment set, so "
                "the set gating STOP_CORPORATE_ACTION and the set classified as economic cannot "
                "disagree"
            ),
        },
        "EXPLICITLY_INERT": "unchanged: bankruptcy, regulatorychange, spunofffrom (owner confirms spunofffrom: child-side metadata, no independent economic action)",
        "TERMINAL_DELISTING": "unchanged",
        "UPSTREAM_IDENTITY_LINEAGE": "unchanged",
    },
    "frozen_rule_spinoff_composite": {
        "id": "SPINOFF-COMPOSITE",
        "the_rule": (
            "on a unit's relevant session, {spinoff, spinoffdividend} normalize to ONE economic "
            "event whose structural kind is 'spinoff' BEFORE the economic uniqueness guard runs; "
            "a spinoffdividend without its parent-side spinoff refuses the unit "
            "(ACTION_COMPOSITION_UNRESOLVED); the composite beside any other economic kind "
            "refuses as before. The published spinoffdividend dollar value joins the registered "
            "cash-distribution term (USD/share, summed exactly like a dividend value); the "
            "spinoff RATIO is never summed into that term."
        ),
        "why_not_a_general_composition_rule": (
            "the frame's Q4 carve-out authorizes composition ONLY where these labels require it. "
            "Nothing else composes; differing economic kinds still refuse."
        ),
        "implemented_at": "candidates.py::ProducerCandidateSource._resolve_actions and candidates.py::cash_distributions",
    },
    "frozen_rule_audit_identity_precedence_extension": {
        "id": "AUDIT-IDENTITY-PRECEDENCE (extended)",
        "the_rule": "TERMINAL_DELISTING > ECONOMICALLY_ADJUDICATED > EXPLICITLY_INERT > KNOWN_INFORMATIONAL_LINKAGE",
        "why": (
            "derived from the owner's ruling that relation 'contributes no precedence of its "
            "own': a linkage identity is published only when it is the sole class present, so it "
            "never displaces the action that determined the disposition. The v1.2 ordering among "
            "the first three classes is unchanged."
        ),
    },
    "relation_premise_guard": {
        "id": "RELATION-VALUE-PREMISE",
        "the_rule": (
            "a relation row on the unit's relevant session with a populated value reverts the "
            "label to KNOWN_UNADJUDICATED for that unit (fail closed, "
            "ACTION_KIND_UNADJUDICATED|KNOWN_UNADJUDICATED). The adjudication is conditional on "
            "the 0/98 bounded observation; a populated value is outside its premise."
        ),
        "implemented_at": "candidates.py::relation_value_keys and candidates.py::ProducerCandidateSource._resolve_actions",
    },
    "open_items_carried_forward": {
        "ANCHOR-ACCEPTANCE-SCOPE": "carried forward, OPEN, unchanged",
        "CONTAINMENT-LOCAL-SNAPSHOT": "carried forward, OPEN",
        "HALT-EVIDENCE-INPUT-GAP": "carried forward, OPEN and unchanged",
        "MISSING-PRICE-REFUSAL-TYPING": "carried forward, OPEN, unchanged",
    },
    "grants": "NOTHING. Adjudication reconciliation only.",
}

adj_sha = _write(adjudication, "MR002_Phase3B_LabelAdjudication_v2.0.json")
matrix["derived_from_adjudication_record_identity"] = adj_sha
_write(matrix, "MR002_Phase3B_SemanticReconciliationMatrix_v1.3.json")
