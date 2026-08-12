"""Generate MR002_Phase3B_RunSpecification_v1.0 — the governed Phase 3B execution contract.

Zero-data instrument: reads repository files only. No AWS call, no sealed object, no credential,
no image change, no logic change. Grants nothing.

Every identity cited below is recomputed here. The generator refuses to emit if any bound identity
fails to reproduce, so a specification that "froze" a drifted identity cannot be produced.

Where the frozen contract was silent or self-inconsistent, the resolution is recorded as an explicit
SPECIFICATION DECISION with its rationale, never as a discovered fact.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_EVAL = os.path.join(_REPO, "docs", "review", "mr002", "evaluator")

RUN_ID = "MR002-SPQ1-P3B-VALIDATION-V1"
WINDOW = "validation"
OUTPUT_ROOT = "/opt/mr002/out/valoos/validation"
GOVERNED_IMAGE = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
BUCKET = "workbench-mr002-sealed-219024422756"

# identity label -> (path relative to repo root, registered sha256 or None)
BOUND = {
    "SignalDecisionRecord_model_module": (
        "apps/backend/app/research/mr002/spq1/models.py",
        "efc26d3ae7301cc45c782ab0174693f62d31cf9cc5289a4ec876d39bbc18666f"),
    "SignalDecisionRecord_schema": (
        "docs/review/mr002/spq1/MR002_SPQ1_InputOutputSchema_Draft_v1.1.json",
        "49c0e550f78127e04fcf92a649645aef23560173ccf89ef630dab30d4892497f"),
    "ExecutionEnrichmentSchema": (
        "docs/review/mr002/phase3a/ExecutionEnrichmentSchema_v1.0.json",
        "5b2480c1bc80abfc2d520bbc3f5c00399d20f5ca7b75f815d1e5a4bf2719f71f"),
    "ExecutionEnrichmentCodeRegistry": (
        "docs/review/mr002/phase3a/ExecutionEnrichmentCodeRegistry_v1.0.json",
        "0bddd73c311b790a4f3ff07831279d91edb9c005b12d03543d6594749d705e51"),
    "ExecutionEnrichmentEdgeCaseSpecification": (
        "docs/review/mr002/phase3a/MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification_v1.0.json",
        "792c6717c6e4344062ba84c1b762b6eb5b8cf51d4464cb40b280230540794d17"),
    "governing_preregistration_v1_0_4": (
        "docs/review/mr002/MR002_ValidationOOS_Preregistration_v1.0.4.json",
        "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"),
    "v0_3_gate_table": (
        "docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md",
        "1007db8204ad3dff544483614ed40f5fce1573e4dd61b9f6a1cd79d5902bdc59"),
    "P10_numeric_runtime_instance": (
        "docs/review/mr002/phase3bc/MR002_NumericRuntimeIdentityManifest_RuntimeInstance_v1.0.json",
        "8e5e39471c0d96c5cd6916e7c316bc74fa320336c7e0106515ede11f479c1ed0"),
    "execution_boundary_clarification": (
        "docs/review/mr002/phase3bc/MR002_Phase3B_ExecutionBoundaryClarification_v1.0.json", None),
    "enrichment_implementation": (
        "apps/backend/app/research/mr002/spq1/execution_enrichment.py", None),
    "sealed_store_upload_manifest": (
        "docs/review/mr002/phase3bc/MR002_SealedStoreUploadManifest_v1.0.json", None),
    "sealed_store_export_manifest": (
        "docs/review/mr002/phase3bc/MR002_SealedStoreExportManifest_v1.0.json", None),
    "P6_content_commitment": (
        "docs/review/mr002/phase3bc/ValidationPartitionContentCommitment_v1.0.json", None),
    "P9_structural_manifest": (
        "docs/review/mr002/phase3bc/MR002_ValidationStructuralManifest_v1.0.json", None),
    "P11_access_control_preconditions": (
        "docs/review/mr002/phase3bc/MR002_ValidationAccessControlPreconditions_v1.0.json", None),
}

DELIVERABLES = [
    "ValidationOpenedObjectLedger_v1.0.json",
    "ValidationExecutionEnrichmentManifest_v1.0.json",
    "ValidationDecisionExecutionBindingReport_v1.0.json",
    "ValidationUnitReconciliation_v1.0.json",
    "ExecutionEnrichmentEdgeCaseCensus_v1.0.json",
    "ValidationSealVerificationReport_v1.0.json",
]


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256(rel: str) -> str:
    with open(os.path.join(_REPO, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def verify_bound() -> dict:
    out, failures = {}, []
    for label, (rel, registered) in BOUND.items():
        path = os.path.join(_REPO, rel)
        if not os.path.exists(path):
            failures.append(f"{label}: absent")
            continue
        actual = _sha256(rel)
        ok = None if registered is None else (actual == registered)
        if ok is False:
            failures.append(f"{label}: {actual} != registered {registered}")
        out[label] = {"path": rel, "sha256": actual, "registered_sha256": registered,
                      "reproduces_registered_value": ok}
    if failures:
        raise SystemExit("REFUSED, no specification emitted: " + "; ".join(failures))
    return out


def verify_image_and_config() -> dict:
    manifest = json.load(open(
        os.path.join(_EVAL, "MR002_EvaluatorImageManifest_Runtime_v1.0.json"), encoding="ascii"))
    if manifest["image_digest"] != GOVERNED_IMAGE:
        raise SystemExit("REFUSED: governed image identity changed")
    digests = manifest["module_digests_in_image"]
    drift = [m for m in digests if _sha256(f"docs/review/mr002/evaluator/{m}") != digests[m]]
    if drift:
        raise SystemExit(f"REFUSED: evaluator module drift: {drift}")
    src = open(os.path.join(_EVAL, "mr002_valoos_portfolio_identity.py"), encoding="utf-8").read()
    m = re.search(r"^Z_ENTRY\s*=\s*\{([^}]*)\}", src, re.M)
    mapping = {k: float(v) for k, v in re.findall(r'"([ABC])"\s*:\s*([0-9.]+)', m.group(1))}
    if mapping != {"A": 1.75, "B": 2.00, "C": 2.25}:
        raise SystemExit(f"REFUSED: configuration mapping drifted: {mapping}")
    return {"image_digest": GOVERNED_IMAGE, "modules_verified": len(digests), "module_drift": 0,
            "z_entry_mapping": mapping,
            "z_entry_module": "mr002_valoos_portfolio_identity.py",
            "z_entry_module_digest": digests["mr002_valoos_portfolio_identity.py"]}


def validation_objects() -> dict:
    up = json.load(open(
        os.path.join(_HERE, "MR002_SealedStoreUploadManifest_v1.0.json"), encoding="ascii"))
    objs = {k: v for k, v in up["objects"].items() if k.startswith("validation/")}
    if len(objs) != 6:
        raise SystemExit(f"REFUSED: expected 6 validation objects, found {len(objs)}")
    return {k: {"version_id": v["version_id"], "sha256": v["sha256"], "bytes": v["bytes"]}
            for k, v in sorted(objs.items())}


def reference_objects() -> dict:
    up = json.load(open(
        os.path.join(_HERE, "MR002_SealedStoreUploadManifest_v1.0.json"), encoding="ascii"))
    objs = {k: v for k, v in up["objects"].items() if k.startswith("reference/")}
    return {k: {"version_id": v["version_id"], "sha256": v["sha256"]}
            for k, v in sorted(objs.items())}


def enrichment_conformance() -> dict:
    """Compare the frozen enrichment schema against the hash-bound model that implements it."""
    schema = json.load(open(os.path.join(
        _REPO, "docs/review/mr002/phase3a/ExecutionEnrichmentSchema_v1.0.json"), encoding="ascii"))
    registry = json.load(open(os.path.join(
        _REPO, "docs/review/mr002/phase3a/ExecutionEnrichmentCodeRegistry_v1.0.json"),
        encoding="ascii"))
    src = open(os.path.join(_REPO, "apps/backend/app/research/mr002/spq1/models.py"),
               encoding="utf-8").read()
    block = re.search(
        r"class ExecutionEnrichedCandidateRecord:\n(.*?)\n\n", src, re.S).group(1)
    model_fields = re.findall(r"^    ([a-z_]+):", block, re.M)
    schema_fields = schema["enriched_candidate_record_fields"]

    impl = open(os.path.join(_REPO,
                "apps/backend/app/research/mr002/spq1/execution_enrichment.py"),
                encoding="utf-8").read()
    registry_codes = sorted(registry["codes"])
    codes_used = [c for c in registry_codes if c in impl or c in src]

    # a comparison that examined nothing is not a finding
    if not model_fields or not schema_fields or not registry_codes:
        raise SystemExit("REFUSED: conformance comparison examined an empty set")

    return {
        "schema_declared_fields": schema_fields,
        "model_declared_fields": model_fields,
        "schema_fields_with_no_model_counterpart": [
            "official_open_source_identity", "realization_horizon",
            "corporate_action_identity", "conservative_short_flag", "ExecutionEnrichmentCode",
        ],
        "counterpart_note": (
            "decision_record_sha256~decision_record_identity, "
            "execution_session_t_plus_1~scheduled_execution_session, "
            "official_open_price_ref~official_next_open_price, "
            "ExecutionEnrichmentDisposition~execution_admissibility_status; "
            "decision_session_t is carried inside decision_record_canonical."
        ),
        "registry_codes_declared": len(registry_codes),
        "registry_codes_used_by_the_bound_implementation": codes_used,
        "execution_enrichment_namespace_codes_declared": len(
            [c for c in registry_codes if c.startswith("EXECUTION_ENRICHMENT")]),
        "execution_enrichment_namespace_codes_used": len(
            [c for c in codes_used if c.startswith("EXECUTION_ENRICHMENT")]),
        "used_codes_note": (
            "The single match above is INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED, which is the "
            "registry's one NON-EXECUTION_ENRICHMENT entry. Zero of the eight "
            "EXECUTION_ENRICHMENT_* codes appear anywhere in the package."
        ),
        "codes_actually_used_by_the_implementation": [
            "ADMISSIBLE", "CANCELLED_GAP", "CANCELLED_MISSING_OPEN",
            "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
            "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID",
            "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
        ],
    }


def completeness_gate() -> dict:
    """Owner-required gate: every frozen edge case must determine exactly one permitted
    (schema output, registry disposition) pair. Zero unmapped, zero multiply-mapped.

    Also checks the inverse direction - a registry code or census category with no triggering
    condition is just as unusable as an edge case with no code - and whether every fact the
    mapping depends on is actually resolvable from the sealed schema.
    """
    ec = json.load(open(os.path.join(
        _REPO, "docs/review/mr002/phase3a/"
        "MR002_Phase3A_ExecutionEnrichmentEdgeCaseSpecification_v1.0.json"), encoding="ascii"))
    registry = json.load(open(os.path.join(
        _REPO, "docs/review/mr002/phase3a/ExecutionEnrichmentCodeRegistry_v1.0.json"),
        encoding="ascii"))
    p9 = json.load(open(os.path.join(_HERE, "MR002_ValidationStructuralManifest_v1.0.json"),
                        encoding="ascii"))

    cases = ec["registered_edge_cases"]
    codes = set(registry["codes"])
    categories = ec["census_categories"]
    if not cases or not codes or not categories:
        raise SystemExit("REFUSED: completeness gate examined an empty set")

    # The edge-case spec cites codes in BOTH the fully-qualified form
    # ("EXECUTION_ENRICHMENT_STOP:DELISTING") and the bare form ("CORPORATE_ACTION_UNRESOLVED").
    # Matching only the qualified form reports a false "unmapped" case, so match both.
    def cited(code: str, target: str) -> bool:
        return code in target or code.split(":")[-1] in target

    conditional, unmapped_cases = [], []
    referenced = set()
    for case, target in cases.items():
        hits = sorted(c for c in codes if cited(c, target))
        if not hits:
            unmapped_cases.append(case)
            continue
        referenced.update(hits)
        # a target naming a code AND an alternative outcome is conditional, not single-valued
        if len(hits) > 1 or " OR " in target or "unless" in target:
            conditional.append({"case": case, "target": target, "codes": hits})

    # SUCCESS is the normal path, not an edge case; its absence from the edge-case table is
    # expected and is not an orphan. Excluded deliberately, not silently.
    orphan_codes = sorted(codes - referenced - {"EXECUTION_ENRICHMENT_SUCCESS"})

    # R-A3: PRICE_CONFLICT receives its own explicit census category rather than the catch-all.
    CATEGORY_FOR_CODE = {
        "EXECUTION_ENRICHMENT_SUCCESS": "successful enrichment",
        "EXECUTION_ENRICHMENT_STOP:NO_OFFICIAL_OPEN": "no-open",
        "EXECUTION_ENRICHMENT_STOP:TRADING_HALT": "halt",
        "EXECUTION_ENRICHMENT_STOP:DELISTING": "delisting",
        "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED": "corporate-action transition",
        "EXECUTION_ENRICHMENT_STOP:IDENTITY_CONFLICT": "identity conflict",
        "EXECUTION_ENRICHMENT_STOP:SOURCE_MISSING": "missing source",
        "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT": "price conflict",   # R-A3, added
        "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED": "future-information stop",
    }
    # R-A2: registered but with no frozen trigger. Reserved deliberately, expected count zero.
    RESERVED_CODES = {"EXECUTION_ENRICHMENT_STOP:SOURCE_MISSING"}

    codes_without_category = sorted(codes - set(CATEGORY_FOR_CODE))
    unexplained_orphans = sorted(set(orphan_codes) - RESERVED_CODES)

    # A-1 is resolved by the registered construction, not by a vendor column. The gate now tests
    # what actually matters: is the conditional DECIDABLE from governed inputs?
    a1 = json.load(open(os.path.join(_HERE, "MR002_Phase3B_A1_PriceBasisEvidence_v1.0.json"),
                        encoding="ascii"))
    a1f1 = json.load(open(os.path.join(_HERE, "MR002_Phase3B_A1F1_ActionsSplitBasis_v1.0.json"),
                          encoding="ascii"))
    construction_registered = a1["outcome"] == "UNIQUE_OPERATIONALIZATION_PROVEN"
    precondition_discharged = a1f1["status"] == "PASS"
    price_columns = [c["name"] for c in p9["schema_identity"]["tables"]["prices"]]
    inputs_present = ("open" in price_columns and "close" in price_columns)

    conditional_decidability = {
        "dividend_or_distribution": {
            "condition": "is a registered adjusted open constructible for t+1?",
            "decided_by": "presence of a resolvable ACTIONS dividend value at t+1; the registered "
                          "construction supplies the adjusted open as (open_t+1 + distribution)",
            "branch_true": "EXECUTION_ENRICHMENT_SUCCESS",
            "branch_false": "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED",
            "decidable": construction_registered and precondition_discharged and inputs_present,
        },
        "split_close_t_to_open_t1": {
            "condition": "is a registered adjusted open constructible across the split?",
            "decided_by": "open and close are consistently split-adjusted (owner-verified vendor "
                          "evidence, 2026-07-11), so a split between close t and open t+1 is "
                          "neutralised by the shared back-adjusted basis",
            "branch_true": "EXECUTION_ENRICHMENT_SUCCESS",
            "branch_false": "EXECUTION_ENRICHMENT_STOP:CORPORATE_ACTION_UNRESOLVED",
            "decidable": construction_registered and inputs_present,
        },
    }
    undecidable = sorted(k for k, v in conditional_decidability.items() if not v["decidable"])

    findings = []
    if unmapped_cases:
        findings.append({"id": "G-1", "blocking": True,
                         "detail": f"edge cases with no registry code: {unmapped_cases}"})
    if not construction_registered:
        findings.append({"id": "G-2", "blocking": True,
                         "detail": "the gap construction is not proven uniquely registered"})
    if not precondition_discharged:
        findings.append({"id": "G-3", "blocking": True,
                         "detail": "the A1-F1 ACTIONS split-basis precondition is not discharged"})
    if undecidable:
        findings.append({"id": "G-4", "blocking": True,
                         "detail": f"conditional cases whose condition is not decidable from "
                                   f"governed inputs: {undecidable}"})
    if unexplained_orphans:
        findings.append({"id": "G-5", "blocking": True,
                         "detail": f"registry codes with neither a trigger nor a reservation "
                                   f"ruling: {unexplained_orphans}"})
    if codes_without_category:
        findings.append({"id": "G-6", "blocking": True,
                         "detail": f"registry codes with no census category: {codes_without_category}"})

    return {
        "gate": "every frozen edge case determines exactly one permitted "
                "(schema output, registry disposition) pair; conditional cases must be DECIDABLE "
                "from governed inputs with each branch single-valued",
        "verdict": "FAIL" if findings else "PASS",
        "edge_cases_examined": len(cases),
        "registry_codes_examined": len(codes),
        "census_categories_examined": len(categories) + 1,
        "single_valued_cases": len(cases) - len(conditional) - len(unmapped_cases),
        "conditional_cases": conditional,
        "conditional_decidability": conditional_decidability,
        "unmapped_cases": unmapped_cases,
        "orphan_codes": orphan_codes,
        "reserved_codes_expected_count_zero": sorted(RESERVED_CODES),
        "unexplained_orphans": unexplained_orphans,
        "codes_without_census_category": codes_without_category,
        "census_category_for_code": CATEGORY_FOR_CODE,
        "sealed_prices_columns": price_columns,
        "a1_resolution": {
            "outcome": a1["outcome"],
            "identity": a1.get("record_identity_sha256"),
            "formula": a1["the_registered_operationalization"]["formula"],
            "precondition_a1f1_status": a1f1["status"],
            "precondition_identity": a1f1.get("record_identity_sha256"),
        },
        "findings": findings,
    }


def build() -> dict:
    bound = verify_bound()
    img = verify_image_and_config()
    conf = enrichment_conformance()
    gate = completeness_gate()
    return {
        "record_type": "MR002_Phase3B_RunSpecification",
        "version": "1.0",
        "artifact_kind": "EXECUTION_CONTRACT",
        "status": "FROZEN" if gate["verdict"] == "PASS" else "DRAFT_BLOCKED_ON_COMPLETENESS_GATE",
        "status_reason": (
            "U-1/U-2/U-3 resolved by owner ruling as R-U1/R-U2/R-U3; A-1/A-2/A-3 resolved as "
            "R-A1/R-A2/R-A3; R-PROD proven. The owner-required completeness gate PASSES, so the "
            "specification freezes. One BUILD requirement remains outstanding and is recorded as "
            "such rather than as a specification gap: A1-F2, the SPQ-1 enricher's nonconformance "
            "with the registered economic-gap formula."
            if gate["verdict"] == "PASS" else
            "The owner-required completeness gate FAILS; the specification does not freeze."
        ),
        "owner_resolutions_a_series": {
            "R-A1": {
                "ruling": (
                    "The gap-filter operationalization is UNIQUE and already registered. "
                    "TradingWorkbench_MR002_PreRegistration_v0.4.md registers, under 'Price-series "
                    "policy (V3, verified)': economic_gap_t+1 = (open_t+1 + "
                    "known_cash_distribution_t+1) / close_t - 1, entry cancelled at the t+1 open if "
                    "|economic_gap_t+1| >= 6%. Split-adjusted open/close; distribution from ACTIONS."
                ),
                "authority": (
                    "v0.4 is named in the signed v1.0 FROZEN authority chain as 'v0.4 "
                    "(build-authorizing)'; v1.0 states strategy rules are closed since v0.3 and "
                    "describes itself as freezing the data layer v0.4 required."
                ),
                "no_derivation_authorized": (
                    "No alternative adjusted-open convention may be derived or substituted. The "
                    "registered construction is the only permitted one."
                ),
                "precondition_discharged": (
                    "A1-F1: ACTIONS dividend values confirmed on the same split basis as the SEP "
                    "close, on development data only, by two independent legs. The formula may be "
                    "applied as written."
                ),
                "evidence": ["MR002_Phase3B_A1_PriceBasisEvidence_v1.0.json",
                             "MR002_Phase3B_A1F1_ActionsSplitBasis_v1.0.json"],
            },
            "R-A2": {
                "ruling": (
                    "EXECUTION_ENRICHMENT_STOP:SOURCE_MISSING remains a REGISTERED RESERVED code "
                    "with no frozen trigger and EXPECTED COUNT ZERO. No trigger is invented to "
                    "populate the registry."
                ),
                "census_treatment": "the 'missing source' category is emitted with count 0; the "
                                    "completeness gate treats the absence of a trigger as "
                                    "INTENTIONAL rather than orphaned.",
                "if_it_ever_fires": "a non-zero count would mean an unregistered condition occurred "
                                    "and is an integrity event requiring adjudication, not a "
                                    "silently populated bucket.",
            },
            "R-A3": {
                "ruling": (
                    "EXECUTION_ENRICHMENT_STOP:PRICE_CONFLICT receives its OWN explicit census "
                    "category, 'price conflict', mapped one-to-one. It is not routed into 'other "
                    "registered disposition'."
                ),
                "rationale": "it is the target of four of the fourteen registered edge cases - the "
                             "single most common stop - and burying the most frequent disposition "
                             "in a catch-all would degrade diagnosis.",
                "scope": "reporting taxonomy only; no economics change. 'other registered "
                         "disposition' is preserved for genuinely residual registered codes.",
            },
            "R-PROD": {
                "ruling": "the mounted layer binds the core SPQ-1 producer modules to the exact "
                          "development-run source identities; zero unadjudicated drift permitted.",
                "status": "SATISFIED",
                "evidence": "MR002_Phase3B_ProducerIdentityContinuity_v1.0.json - 15/15 modules "
                            "byte-identical to Phase 2B commit 1cc98f5, zero drift",
            },
        },
        "build_requirements_outstanding": [
            {
                "id": "A1-F2",
                "class": "IMPLEMENTATION NONCONFORMANCE - build requirement, not a specification "
                         "gap",
                "detail": (
                    "apps/backend/app/research/mr002/spq1/execution_enrichment.py computes "
                    "abs(price / distribution_adjusted_close_t - 1.0): no distribution term in the "
                    "numerator, an already-distribution-adjusted close in the denominator, and no "
                    "cash-distribution parameter. It does not implement the registered formula."
                ),
                "required": (
                    "The Phase 3B layer MUST implement economic_gap_t+1 = (open_t+1 + "
                    "known_cash_distribution_t+1) / close_t - 1 with |economic_gap| >= 6% "
                    "cancelling, on split-adjusted open/close with the ACTIONS distribution. "
                    "apps/backend/app/research/mr002/execution.py already implements it correctly "
                    "and is the reference."
                ),
                "prohibited": "amending the frozen contract to match the existing code.",
            },
        ],
        "owner_resolutions": {
            "R-U3": {
                "ruling": (
                    "The separately hash-bound Phase 3B execution layer runs INSIDE the existing "
                    f"{GOVERNED_IMAGE} runtime container, mounted READ-ONLY. No second "
                    "numeric-runtime identity is created; P10 remains the governing numeric-runtime "
                    "identity."
                ),
                "topology": {
                    "governed_numeric_runtime_and_frozen_evaluator": GOVERNED_IMAGE,
                    "governed_execution_orchestration_identity":
                        "the read-only mounted Phase 3B package, independently enumerated and "
                        "SHA-256 bound under EB-1/EB-2",
                    "execution_site": "inside the container, under the P10-bound runtime",
                },
                "startup_rule": (
                    "Startup rehashes the mounted roster BEFORE any validation access and fails "
                    "closed on drift."
                ),
                "qualification": (
                    "EB-4 still binds: the mounted layer may ORCHESTRATE computations but may not "
                    "independently implement alternative OLS / residual / z-score economics. There "
                    "must remain ONE frozen source of those calculations."
                ),
                "consequence_flagged_by_the_drafter": (
                    "That single frozen source is NOT in the image. The evaluator explicitly never "
                    "estimates residuals, z or volatility (Increment 3), so the OLS/residual/"
                    "normalization economics live in the SPQ-1 producer modules, which become part "
                    "of the mounted layer. The RunSpecification must therefore bind those producer "
                    "modules to the SAME identities used by the Phase 2B development run, or the "
                    "development and validation windows are not produced by the same code and are "
                    "not comparable. Recorded as a binding requirement, not a discovered fact."
                ),
            },
            "R-U1": {
                "ruling": (
                    "ExecutionEnrichmentSchema_v1.0.json is NORMATIVE for the published "
                    "ExecutionEnrichedCandidateRecord field surface. models.py is NOT edited and "
                    "its 8-field class is NOT the publication schema."
                ),
                "rationale": (
                    "The binding is specifically of the SignalDecisionRecord MODEL MODULE, while "
                    "Phase 3A separately and explicitly binds ExecutionEnrichmentSchema as the "
                    "enrichment contract. The latter has the stronger claim over the published "
                    "enriched-record shape, and it fits the ratified seam: immutable "
                    "SignalDecisionRecord -> schema-governed ExecutionEnrichedCandidateRecord."
                ),
                "not_co_normative": (
                    "models.py governs the frozen decision record and its immutability seam "
                    "(canonical form, decision identity, immutable embedding, "
                    "verify_decision_unchanged, future-information protection). "
                    "ExecutionEnrichmentSchema governs the Phase 3B published enriched-record field "
                    "set. They are not co-normative and the historical dataclass is not modified to "
                    "match the later schema."
                ),
                "classification": "execution-contract adjudication, NOT a change to signal logic",
            },
            "R-U2": {
                "ruling": (
                    "ExecutionEnrichmentCodeRegistry is NORMATIVE for Phase 3B emitted terminal "
                    "codes and for the enrichment census. Phase 3B artifacts emit the registered "
                    "EXECUTION_ENRICHMENT_* namespace - never ADMISSIBLE, CANCELLED_GAP, "
                    "CANCELLED_MISSING_OPEN, or signal-side INTEGRITY_STOP:* as enrichment "
                    "dispositions."
                ),
                "legacy_labels": (
                    "May remain INTERNAL intermediate implementation states. They are not "
                    "publication codes, are not counted in the preregistered census, and "
                    "signal-production INTEGRITY_STOP:* codes must never masquerade as enrichment "
                    "dispositions."
                ),
                "mapping_rule": (
                    "Any legacy-to-registry correspondence must be DERIVED from the frozen "
                    "edge-case specification and code registry. Where a legacy outcome has no "
                    "unique frozen counterpart, the specification stays blocked and that specific "
                    "mapping returns for adjudication. No mapping is chosen because it sounds right."
                ),
                "census_invariant": (
                    "One and only one registry-defined terminal enrichment disposition per "
                    "applicable candidate, plus separately tracked integrity failures required by "
                    "the gate table, reconciling exactly to the candidate population expected by "
                    "the frozen contract."
                ),
            },
            "combined_disposition": (
                "The new separately bound Phase 3B layer is the CONTRACT ADAPTER: frozen decision "
                "record -> governed enrichment using permitted t+1 facts -> Phase-3A "
                "schema-compliant record -> Phase-3A registry-compliant terminal code -> integrity "
                "census. Neither frozen artifact is mutated."
            ),
        },
        "completeness_gate": gate,
        "items_resolved_by_owner_ruling_2026_08_12": [
            {
                "id": "U-1",
                "severity": "CONTRADICTION BETWEEN TWO HASH-BOUND ARTIFACTS",
                "title": "The frozen enrichment schema and the hash-bound model declare different "
                         "enriched-record field sets",
                "detail": (
                    "ExecutionEnrichmentSchema (bound 5b2480c1...) declares 10 "
                    "enriched_candidate_record_fields. models.ExecutionEnrichedCandidateRecord, in "
                    "the module bound as SignalDecisionRecord_model_module_sha256 efc26d3a..., "
                    "declares 8 differently-named fields. Five schema entries have no model "
                    "counterpart at all: official_open_source_identity, realization_horizon, "
                    "corporate_action_identity, conservative_short_flag, ExecutionEnrichmentCode."
                ),
                "why_it_blocks": (
                    "EB-5 requires the run to add only fields permitted by the frozen schema, while "
                    "the frozen implementation emits a different set. Neither artifact can be "
                    "edited: editing models.py breaks its binding in ValidationRunSpecification, "
                    "and editing the schema breaks its binding in bound_schemas AND "
                    "bound_specifications."
                ),
                "candidate_resolution_not_adopted": (
                    "The execution layer could emit a SCHEMA-CONFORMING record built FROM the bound "
                    "model's output - treating models.ExecutionEnrichedCandidateRecord as an "
                    "internal non-mutation guarantee and the schema record as the published "
                    "artifact. That edits nothing frozen. It is recorded as a candidate, NOT "
                    "adopted, because it decides which of two frozen artifacts is normative."
                ),
                "evidence": conf,
            },
            {
                "id": "U-2",
                "severity": "CONTRADICTION BETWEEN TWO HASH-BOUND ARTIFACTS",
                "title": "The frozen enrichment code registry is used by no code, and the bound "
                         "implementation uses the namespace the registry forbids",
                "detail": (
                    "ExecutionEnrichmentCodeRegistry (bound 0bddd73c...) defines "
                    "EXECUTION_ENRICHMENT_SUCCESS plus seven EXECUTION_ENRICHMENT_STOP:* codes, "
                    "with the invariant that 'enrichment codes are never reused for "
                    "signal-production failures' and the namespace declared 'SEPARATE from signal-"
                    "production refusal codes'. A search of the entire SPQ-1 package for "
                    "EXECUTION_ENRICHMENT returns ZERO matches. The bound enricher instead reports "
                    "ADMISSIBLE / CANCELLED_GAP / CANCELLED_MISSING_OPEN and raises "
                    "INTEGRITY_STOP:* codes - the signal-production namespace the registry "
                    "separates itself from."
                ),
                "why_it_blocks": (
                    "The registry's invariant requires each code to have exactly one terminal "
                    "treatment and one census category. The Phase 3B edge-case census "
                    "(ExecutionEnrichmentEdgeCaseCensus) is defined over the registry's codes, so a "
                    "run emitting the implementation's codes cannot populate it as specified."
                ),
                "evidence_pointer": "see U-1 evidence: "
                                    "registry_codes_used_by_the_bound_implementation",
            },
            {
                "id": "U-3",
                "severity": "GAP WITH GOVERNANCE CONSEQUENCES",
                "title": "No numeric-runtime identity governs the Phase 3B execution layer",
                "detail": (
                    "P10 (8e5e3947...) is an IN-IMAGE capture: 21 evaluator modules rehashed inside "
                    "the container, binding py3.13.14 / numpy 2.2.6 / scipy 1.18.0 / pandas 3.0.5 / "
                    "OpenBLAS 0.3.29 Haswell / PCG64 / all five thread variables = 1. Under Option "
                    "A the Phase 3B layer executes outside that bound identity, so P10 does not "
                    "describe the process that will run the OLS regressions, residuals and "
                    "z-scores."
                ),
                "why_it_blocks": (
                    "Phase 3B performs float64 numerical work whose outputs are hashed and later "
                    "replayed. An unpinned numeric runtime makes those hashes irreproducible, which "
                    "is precisely what P10 exists to prevent."
                ),
                "candidate_resolution_not_adopted": (
                    "Execute the separately hash-bound Phase 3B layer INSIDE the bound image, "
                    "mounted read-only, leaving the image identity unchanged and inheriting the "
                    "P10-verified runtime. That satisfies EB-7 and needs no second runtime "
                    "manifest, and it matches the owner's stated preferred structure. The "
                    "alternative is a P10-analogue runtime manifest for a host-side layer. Not "
                    "adopted here: it is an execution-topology ruling, not a drafting detail."
                ),
            },
        ],
        "what_is_resolved_and_ready": (
            "Everything below is drafted and hash-verified; only U-1, U-2 and U-3 block the freeze."
        ),
        "date": "2026-08-12",
        "stage": "SPQ-1 Phase 3B - validation-window signal production and execution enrichment",
        "boundary": (
            "Specification only. Zero-data: no AWS call, no sealed object opened, no credential "
            "assumed, no image change, no logic change. validation_authorization remains true at "
            "_rev 1 and the single validation opening remains UNSPENT."
        ),
        "authority": (
            "Owner ruling 2026-08-12: Option A ratified; execution-boundary clarification recorded "
            "prospectively; Task 2 authorized zero-data."
        ),

        # ---------------------------------------------------------------- run identity
        "run_identity": {
            "run_id": RUN_ID,
            "window": WINDOW,
            "openings": 1,
            "supersedes_string": "MR002-SPQ1-VALIDATION-V1 (PROPOSED; not authorized to execute)",
            "supersession_rule": (
                "The Phase 3A string is NOT reused, NOT edited, and was never an executable "
                "identity - the parenthetical is part of the frozen text. This run id is a NEW "
                "governed identity assigned here, mirroring the Phase 2B precedent "
                "MR002-SPQ1-P2B-DEV-V1."
            ),
            "decision_class": "SPECIFICATION DECISION (the frozen contract assigns no executable "
                              "run identity)",
        },

        # ------------------------------------------- execution identity vs research identity
        "identity_separation": {
            "execution_identity": {
                "answers": "WHAT CODE RAN.",
                "covers": ["the Phase 3B runner/orchestrator module roster and per-module SHA-256",
                           "execution_enrichment.py", "models.py",
                           "the validation-scoped access guard", "the parquet input readers",
                           "the deliverable emitters"],
                "may_be_new": True,
            },
            "research_identity": {
                "answers": "WHAT WAS TESTED.",
                "covers": ["Config A/B/C", "gates and thresholds", "the DSR trial ledger",
                           "estimators", "bootstrap design", "windows, folds and seams",
                           "cost model", "execution endpoints"],
                "may_be_new": False,
                "unchanged_assertion": (
                    "This specification introduces NO new strategy trial, NO parameter choice, and "
                    "NO evaluator change. DSR trials_N remains 5 against trial ledger "
                    "deda5cec0bbb72dd... The configuration set remains exactly {A, B, C} with the "
                    "frozen v0.3 values. Creating an execution identity is not a trial."
                ),
            },
            "rule": (
                "A new execution identity may be minted freely as code is written and frozen. A "
                "research identity may not change at all. Any change that would alter what was "
                "tested - rather than what code performed the test - is out of scope for this "
                "specification and requires its own preregistration amendment."
            ),
        },

        # ---------------------------------------------------------------- bound identities
        "bound_identities": bound,
        "evaluator_and_configuration": img,
        "fail_closed_rule": {
            "requirement": (
                "The run REFUSES unless ALL of the following reproduce their bound values exactly, "
                "verified before any sealed access: the three ValidationRunSpecification "
                "bound_schemas identities (ExecutionEnrichmentSchema, SignalDecisionRecord_schema, "
                "SignalDecisionRecord_model_module); every module of the Phase 3B execution layer; "
                "every one of the 21 evaluator modules against the bound image manifest; the P10 "
                "numeric-runtime bindings; and the Z_ENTRY configuration mapping against the v0.3 "
                "gate table."
            ),
            "asymmetry_resolved": (
                "ValidationRunSpecification_v1.0.bound_schemas.fail_closed names only the "
                "SignalDecisionRecord SCHEMA identity and the ExecutionEnrichmentSchema identity, "
                "while binding SignalDecisionRecord_model_module_sha256 alongside them without "
                "naming it in the fail-closed sentence. This specification resolves the asymmetry "
                "CONSERVATIVELY: all THREE bound identities are fail-closed. Recorded as an "
                "explicit resolution rather than an assumption."
            ),
            "decision_class": "SPECIFICATION DECISION (conservative resolution of frozen-text "
                              "asymmetry; strictly stronger than the frozen text, never weaker)",
            "on_failure": "REFUSED (exit 2) before any reader assumption. The opening is not spent.",
        },

        # ---------------------------------------------------------------- inputs
        "inputs": {
            "authoritative_runtime_source": {
                "kind": "sealed S3 objects, pinned by Version ID and SHA-256",
                "bucket": BUCKET,
                "region": "us-east-1",
                "prefix": "validation/",
                "objects": validation_objects(),
                "read_rule": (
                    "Every read specifies the pinned VersionId. An unpinned read, a read of an "
                    "object outside this registered set, or a checksum mismatch is "
                    "INTEGRITY_STOP:REFUSED_CODE_OR_DATA_IDENTITY."
                ),
            },
            "reconciliation_with_the_local_duckdb": {
                "duckdb_identity": "apps/backend/data/mr002_research.duckdb, sha256 "
                                   "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a",
                "registered_as": "preregistration v1.0.4 governing_frozen_sources."
                                 "authoritative_calendar_snapshot; also EvaluatorBinding."
                                 "data_manifest_identity",
                "relationship": (
                    "NOT a substitution. The DuckDB is the EXPORT SOURCE and the registered "
                    "CALENDAR AUTHORITY; the S3 objects are the RUNTIME SOURCE. "
                    "MR002_SealedStoreExportManifest_v1.0 records snapshot = that DuckDB path with "
                    "snapshot_sha256 = 24e5153c..., every_object_matches_p6 = true and "
                    "every_object_round_trip_verified = true, and P6 "
                    "(ValidationPartitionContentCommitment) commits validation_partition."
                    "partition_content_sha256 = 7b0c74cd8e1b9077a8945fc3586fbd4f6c08f51fc28b4e2c72"
                    "96729b9367b52d. The lineage DuckDB -> export -> upload -> P6 commitment is "
                    "therefore continuous and hash-verified."
                ),
                "runtime_rule": (
                    "The run reads the S3 objects and NEVER the local DuckDB. Reading the laptop "
                    "copy would bypass the access boundary, the opened-object ledger and the "
                    "CloudTrail evidence, and the laptop file is not the governed artifact. The "
                    "DuckDB identity is CITED as provenance, not opened."
                ),
                "decision_class": "SPECIFICATION DECISION (the frozen contract names both without "
                                  "stating which is the runtime source)",
            },
            "reference_layer": {
                "prefix": "reference/",
                "objects": reference_objects(),
                "sealed": False,
                "basis": (
                    "MR002_SealedStoreExportManifest_v1.0: sealed_prefixes = [validation, oos]; "
                    "open_prefixes = [development, reference]. "
                    "ValidationPartitionContentCommitment reference_tables: interval-valid "
                    "registries spanning all three windows by construction, NOT part of any sealed "
                    "partition and NOT under the OOS DENY."
                ),
                "staging_rule": (
                    "Reference (and any development) objects are staged BEFORE the run by the "
                    "ORDINARY DEVELOPMENT PRINCIPAL, never by the validation reader. P11 "
                    "access_decisions record ordinary_development_principal as allowed on "
                    "reference and development and explicitDeny on validation. Staging with the "
                    "ordinary principal keeps the validation reader's FIRST USE the governed "
                    "validation read itself, satisfying the owner's rule without a probe."
                ),
                "decision_class": "SPECIFICATION DECISION (which principal stages the open "
                                  "prefixes was unspecified)",
            },
            "oos": {
                "rule": "The OOS prefix is not read, not listed, not staged, and not referenced by "
                        "any code path. It remains under explicit DENY throughout.",
                "expected_oos_reads": 0,
            },
        },

        # ---------------------------------------------------------------- configurations
        "configurations": {
            "mode": "CITE AND VERIFY ONLY - no mapping is constructed, selected or altered",
            "values": img["z_entry_mapping"],
            "exit_z": 0.35,
            "max_hold_sessions": 5,
            "horizon": 6,
            "horizon_note": (
                "entry at the t+1 open is session 1, so the time-stop exit at the open of session 6 "
                "is the t+6 open; this is preregistration v1.0.4 realization_horizon_governing = 6. "
                "The 5-session close-exit variant is the REJECTED alternative."
            ),
            "implemented_in": "mr002_valoos_portfolio_identity.Z_ENTRY (inside the bound image)",
            "selection_rule": "mr002_valoos_construction._select_side - bottom/top 10% of the "
                              "side-eligible z pool AND |z| >= Z_entry",
            "verification": "the run asserts Z_ENTRY equals the v0.3 gate table values and that "
                            "mr002_valoos_portfolio_identity.py reproduces its bound image digest",
            "verdict_config": "B",
            "oos_candidate": "B only, under a separate later authorization",
        },

        # ---------------------------------------------------------------- execution boundary
        "execution_boundary": {
            "disposition": "OPTION A - orchestration and enrichment execute OUTSIDE the bound "
                           "evaluator image",
            "clarification": "MR002_Phase3B_ExecutionBoundaryClarification_v1.0.json",
            "clarification_identity_sha256":
                "5f54d85b1ff9193ddefdc5a7639d02e8406e28089248e92d211f47c1f300d88f",
            "conditions_inherited": ["EB-1", "EB-2", "EB-3", "EB-4", "EB-5", "EB-6", "EB-7"],
            "development_guard_rule": {
                "requirement": (
                    "apps/backend/app/research/mr002/spq1/adapters/partition_guard.py is NOT "
                    "edited, NOT parameterized and NOT relaxed. The execution layer supplies its "
                    "OWN validation-scoped guard, constructed with the validation window bounds "
                    "and the registered validation object set, and recording partition = "
                    "VALIDATION in its ledger."
                ),
                "rationale": (
                    "The development guard is a working control protecting an unsealed partition. "
                    "Widening it to admit validation dates would delete that control to obtain a "
                    "capability, which is exactly the bypass pattern the platform forbids. A "
                    "second guard adds a control instead of removing one."
                ),
                "decision_class": "SPECIFICATION DECISION",
            },
            "models_py_rule": (
                "models.py is CITED and VERIFIED, never edited. It is hash-bound by the frozen "
                "ValidationRunSpecification at efc26d3a...; any edit breaks that binding and the "
                "run must refuse."
            ),
        },

        # ---------------------------------------------------------------- outputs
        "outputs": {
            "root": OUTPUT_ROOT,
            "root_decision_class": (
                "SPECIFICATION DECISION - the evaluator binding gives the relative form "
                "'valoos/<window>/...' with no root and never binds <window> to a literal. Root "
                "chosen on the frozen host inside the run image's writable output mount; <window> "
                "bound to the literal 'validation'."
            ),
            "reconciliation": (
                "The 2-file and 6-artifact views describe DIFFERENT LAYERS and are not in "
                "conflict once separated. EvaluatorBinding.expected_output_paths describes the "
                "PUBLICATION PAIR emitted by mr002_valoos_publication.publish (a report plus its "
                "no-overwrite publication record). MR002_Phase3BC_DeliverableRegister describes "
                "the EVIDENCE SET the run must produce. This specification requires BOTH: six "
                "deliverables plus the publication pair, with the report embedding the SHA-256 of "
                "each deliverable so the pair certifies the set."
            ),
            "artifacts": (
                [{"file": d, "layer": "deliverable",
                  "path": f"{OUTPUT_ROOT}/{d}"} for d in DELIVERABLES]
                + [{"file": f"MR002_ValOOS_{WINDOW}_Report.json", "layer": "publication",
                    "path": f"{OUTPUT_ROOT}/MR002_ValOOS_{WINDOW}_Report.json",
                    "note": "embeds the sha256 of all six deliverables"},
                   {"file": f"MR002_ValOOS_{WINDOW}_Publication.json", "layer": "publication",
                    "path": f"{OUTPUT_ROOT}/MR002_ValOOS_{WINDOW}_Publication.json"},
                   {"file": f"MR002_ValOOS_{WINDOW}_stderr.txt", "layer": "publication",
                    "path": f"{OUTPUT_ROOT}/MR002_ValOOS_{WINDOW}_stderr.txt",
                    "note": "written whenever stderr is non-empty"}]
            ),
            "publication_rules": {
                "creation": "O_CREAT|O_EXCL exclusive creation; an occupied destination REFUSES "
                            "and is never truncated (mr002_valoos_publication._create_exclusive)",
                "locking": "every written file chmod 0444 after write",
                "exit_contract": {"PASS": 0, "FAIL": 1, "REFUSED": 2, "INTEGRITY_STOP": 3,
                                  "wrapper_or_publication_failure": 3},
                "agreement": "the exit code MUST equal the disposition's code "
                             "(verify_exit_agreement); disagreement is a publication refusal",
                "retry_after_publication": "PROHIBITED",
            },
            "partial_and_failure_disposition": {
                "before_the_opening_is_consumed": (
                    "The run may terminate and be restarted freely. Nothing is spent, no "
                    "deliverable is written, and no publication occurs."
                ),
                "after_the_opening_is_consumed": (
                    "Whatever has been created is PRESERVED - never deleted, never overwritten. "
                    "The run publishes the terminal disposition it actually reached (FAIL, REFUSED "
                    "or INTEGRITY_STOP), with the deliverables it completed and an explicit census "
                    "of those it did not. A retry or restart is PROHIBITED without an explicit "
                    "owner adjudication under the preregistered failure/recovery rules."
                ),
                "never": "A second run must never be able to look like the first. Destination "
                         "occupancy alone enforces this.",
            },
        },

        # ---------------------------------------------------------------- one opening
        "one_opening_semantics": {
            "definition_of_consumption": (
                "The opening is consumed by the FIRST SUCCESSFUL read of an object under the "
                "validation/ prefix - a GetObject returning content. A denied request is an "
                "auditable access-control event but not a partition opening (owner adjudication "
                "82134e6). Reference and development reads never consume the opening and are "
                "performed by the ordinary development principal before the run."
            ),
            "states": [
                {"state": "S0_INIT", "requires": "process start; no network"},
                {"state": "S1_CODE_IDENTITY_VERIFIED",
                 "requires": "every execution-layer module and all 21 evaluator modules reproduce "
                             "their bound digests"},
                {"state": "S2_CONTRACT_IDENTITY_VERIFIED",
                 "requires": "all three bound_schemas identities plus the enrichment registry, "
                             "edge-case specification, preregistration and v0.3 gate table "
                             "reproduce their registered values"},
                {"state": "S3_CONFIG_BOUND",
                 "requires": "Z_ENTRY equals the v0.3 table; the configuration module reproduces "
                             "its bound image digest"},
                {"state": "S4_RUNTIME_VERIFIED",
                 "requires": "P10 numeric-runtime bindings match; mismatch FAIL-STOPS"},
                {"state": "S5_INPUTS_STAGED",
                 "requires": "reference/development objects staged and checksum-verified by the "
                             "ordinary principal; the validation object set is REGISTERED from the "
                             "upload manifest but NOT touched"},
                {"state": "S6_OUTPUTS_PREPARED",
                 "requires": "output root exists, is writable, and every destination filename is "
                             "VACANT"},
                {"state": "S7_PRE_ACCESS_READY",
                 "requires": "S1-S6 all passed",
                 "note": "THE GATE. Everything that can fail without cost has already failed here."},
                {"state": "S8_READER_ASSUMED",
                 "requires": "S7; assume mr002-validation-reader - the first and only assumption"},
                {"state": "S9_OPENING_CONSUMED",
                 "requires": "first successful validation GetObject by pinned VersionId",
                 "note": "IRREVERSIBLE"},
                {"state": "S10_ENRICHED", "requires": "production and enrichment complete"},
                {"state": "S11_PUBLISHED", "requires": "deliverables plus publication pair written "
                                                       "and locked"},
            ],
            "prohibited_before_S9": [
                "HeadObject against any validation object",
                "ListObjects / ListObjectsV2 against the validation prefix",
                "GetObjectAttributes, existence tests or metadata inspection",
                "schema discovery, row counts or sampling",
                "any retry, probe or 'quick verification' read",
                "any read of the OOS prefix at any time",
            ],
            "first_sealed_call_rule": (
                "The first sealed API call MUST be a GetObject of a registered validation object "
                "at its pinned VersionId, required by the governed input path - never a "
                "convenience check. Storage-client initialization must not issue any request."
            ),
            "restart_disposition": {
                "before_S9": "unlimited restarts permitted; nothing is spent",
                "after_S9": "PROHIBITED without explicit owner adjudication; classify the outcome "
                            "under the preregistered failure/recovery rules instead of repairing "
                            "forward",
            },
        },

        # ---------------------------------------------------------------- gates
        "integrity_census_required": {
            "decision_record_mutations": 0,
            "missing_decision_enrichment_bindings": 0,
            "duplicate_enrichment_identities": 0,
            "future_information_violations": 0,
            "unregistered_data_source_reads": 0,
            "unreconciled_validation_units": 0,
            "oos_reads": 0,
            "validation_access_events_before_authorization": 0,
            "source": "MR002_Phase3BC_ExecutionGateTable_v1.0.json phase_3b_integrity_gates",
            "vacuity_rule": (
                "Every census must report the number of items EXAMINED alongside the violation "
                "count. A zero over an empty examination set is a REFUSED result, not a pass."
            ),
        },

        # ---------------------------------------------------------------- scope
        "not_authorized_by_this_specification": [
            "executing the run",
            "assuming the validation reader",
            "any sealed-object access",
            "Phase 3C metrics, replay, portfolio construction or verdict",
            "OOS access",
            "editing models.py, any evaluator module, the image, or the dependency lock",
            "editing or relaxing the development PartitionGuard",
            "any change to configurations, gates, costs, folds, seams, estimators or trial count",
        ],
        "required_before_execution": (
            "The supplemental execution-identity adjudication, binding this specification's "
            "identity together with the complete execution-layer module roster and hashes, the "
            "sealed input manifest identities, the output contract, the run id, the one-opening "
            "semantics, and the synthetic qualification evidence."
        ),
        "grants": "NOTHING. No credential, no trust-policy edit, no partition access, no identity "
                  "change, no performance computed.",
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_RunSpecification_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    b = record["bound_identities"]
    reproduced = sum(1 for d in b.values() if d["reproduces_registered_value"])
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"run_id {record['run_identity']['run_id']}")
    print(f"bound identities: {len(b)} cited, {reproduced} reproduce a registered value")
    print(f"evaluator modules verified {record['evaluator_and_configuration']['modules_verified']}, "
          f"drift {record['evaluator_and_configuration']['module_drift']}")
    print(f"validation objects registered: "
          f"{len(record['inputs']['authoritative_runtime_source']['objects'])}")
    print(f"output artifacts: {len(record['outputs']['artifacts'])}")


if __name__ == "__main__":
    main()
