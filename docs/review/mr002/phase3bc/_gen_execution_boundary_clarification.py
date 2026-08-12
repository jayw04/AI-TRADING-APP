"""Record the prospective Phase 3B execution-boundary clarification (owner ruling 2026-08-12).

The clarification permits Phase 3B orchestration and execution-enrichment code to run outside the
P5-bound evaluator image, under conditions. It is recorded PROSPECTIVELY - before any such layer
exists - and this generator proves that prospectivity rather than asserting it: it refuses to emit
unless the repository still contains no Phase 3B execution layer, the evaluator image identity is
unchanged, and the configuration mapping still agrees with the v0.3 gate table.

A clarification written after the thing it permits already exists is a rationalization. The checks
below are what make this one a clarification.

Zero-data instrument: reads repository files only. No AWS call, no sealed object, no credential,
no image change. Grants nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_EVAL = os.path.join(_REPO, "docs", "review", "mr002", "evaluator")
_SPQ1 = os.path.join(_REPO, "apps", "backend", "app", "research", "mr002", "spq1")

GOVERNED_IMAGE = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
V03_GATE_TABLE = {"A": 1.75, "B": 2.00, "C": 2.25}
V03_SHA = "1007db8204ad3dff544483614ed40f5fce1573e4dd61b9f6a1cd79d5902bdc59"
ENTRY_POINT = re.compile(r"argparse|__main__|^def main\b", re.MULTILINE)

MEMO = "MR002_Phase3B_ExecutionBoundary_EvidenceMemo_v1.0.md"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _py_files(root: str) -> list[str]:
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ("__pycache__", ".pytest_cache", ".ruff_cache")]
        out.extend(os.path.join(dp, f) for f in fn if f.endswith(".py"))
    return sorted(out)


def prove_prospective() -> dict:
    """Refuse to emit unless the state this clarification speaks about still holds."""
    manifest = json.load(open(
        os.path.join(_EVAL, "MR002_EvaluatorImageManifest_Runtime_v1.0.json"), encoding="ascii"))
    if manifest["image_digest"] != GOVERNED_IMAGE:
        raise SystemExit("REFUSED: the governed evaluator image identity has changed")

    bound = sorted(manifest["module_digests_in_image"])
    bound_paths = [os.path.join(_EVAL, m) for m in bound]
    drifted = [m for m, p in zip(bound, bound_paths)
               if not os.path.exists(p) or _sha256(p) != manifest["module_digests_in_image"][m]]
    if drifted:
        raise SystemExit(f"REFUSED: bound evaluator modules drifted: {drifted}")

    spq1 = _py_files(_SPQ1)
    if not spq1 or not bound_paths:
        raise SystemExit("REFUSED: a zero-file scan proves nothing")
    with_entry = []
    for p in bound_paths + spq1:
        with open(p, encoding="utf-8", errors="replace") as fh:
            if ENTRY_POINT.search(fh.read()):
                with_entry.append(os.path.relpath(p, _REPO).replace("\\", "/"))
    if with_entry:
        raise SystemExit(
            "REFUSED: a Phase 3B execution layer already appears to exist "
            f"({with_entry}); this record would be retrospective, not prospective")

    src = open(os.path.join(_EVAL, "mr002_valoos_portfolio_identity.py"), encoding="utf-8").read()
    m = re.search(r"^Z_ENTRY\s*=\s*\{([^}]*)\}", src, re.M)
    mapping = {k: float(v) for k, v in re.findall(r'"([ABC])"\s*:\s*([0-9.]+)', m.group(1))} if m else {}
    if mapping != V03_GATE_TABLE:
        raise SystemExit(f"REFUSED: configuration mapping {mapping} no longer matches v0.3")

    v03 = os.path.join(_REPO, "docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md")
    if _sha256(v03) != V03_SHA:
        raise SystemExit("REFUSED: the v0.3 gate table no longer reproduces its registered hash")

    return {
        "evaluator_image_unchanged": GOVERNED_IMAGE,
        "bound_modules_verified": len(bound),
        "bound_module_drift": 0,
        "phase3b_execution_layer_present": False,
        "entry_point_scan": {
            "pattern": "argparse | __main__ | ^def main",
            "files_scanned": len(bound_paths) + len(spq1),
            "files_with_entry_point": 0,
        },
        "configuration_mapping_verified": mapping,
        "v03_gate_table_sha256_verified": V03_SHA,
    }


def build() -> dict:
    proof = prove_prospective()
    memo_path = os.path.join(_HERE, MEMO)
    return {
        "record_type": "MR002_Phase3B_ExecutionBoundaryClarification",
        "version": "1.0",
        "artifact_kind": "PROSPECTIVE_CLARIFICATION",
        "date": "2026-08-12",
        "status": "RATIFIED",
        "ratified_by": "Jay Wang (owner), 2026-08-12",
        "disposition": "OPTION A - APPROVED, subject to this clarification",

        "clarification": (
            "Phase 3B orchestration and execution-enrichment code MAY execute outside the P5-bound "
            "evaluator image, provided that the complete execution layer is independently "
            "enumerated, hash-bound before validation access, fails closed on identity drift, does "
            "not recompute or mutate any frozen SignalDecisionRecord fact, adds only fields "
            "permitted by the frozen enrichment schema, and emits the preregistered integrity "
            "census. The evaluator image identity remains unchanged."
        ),

        "classification": (
            "A clarification of the EXECUTION BOUNDARY. It is NOT a change to signal or evaluator "
            "logic, Config A/B/C, the runtime image, the dependency lock, P10, or research "
            "economics."
        ),
        "why_not_an_adr": (
            "This clarifies a research-program contract boundary inside MR-002; it establishes no "
            "platform-wide architectural invariant and relaxes none. Platform invariants change by "
            "ADR; MR-002 contract boundaries are recorded as program artifacts under the frozen "
            "preregistration chain. Recorded here deliberately, not by omission."
        ),

        "conditions": [
            {"id": "EB-1", "requirement": "The complete execution layer is INDEPENDENTLY "
                                          "ENUMERATED - every module named, none implicit."},
            {"id": "EB-2", "requirement": "Every enumerated module is HASH-BOUND (SHA-256) BEFORE "
                                          "any validation access."},
            {"id": "EB-3", "requirement": "The run FAILS CLOSED on identity drift of any bound "
                                          "module, in either the execution layer or the evaluator."},
            {"id": "EB-4", "requirement": "No frozen SignalDecisionRecord fact is recomputed or "
                                          "mutated."},
            {"id": "EB-5", "requirement": "Only fields permitted by the frozen "
                                          "ExecutionEnrichmentSchema are added."},
            {"id": "EB-6", "requirement": "The preregistered Phase 3B integrity census is emitted: "
                                          "decision_record_mutations = 0, "
                                          "missing_decision_enrichment_bindings = 0, "
                                          "duplicate_enrichment_identities = 0, "
                                          "future_information_violations = 0, "
                                          "unregistered_data_source_reads = 0, "
                                          "unreconciled_validation_units = 0, oos reads = 0."},
            {"id": "EB-7", "requirement": "The evaluator image identity is UNCHANGED at "
                                          f"{GOVERNED_IMAGE}."},
        ],
        "conditions_are_conjunctive": (
            "All seven must hold. Satisfying six is not partial compliance; it is non-compliance."
        ),

        "evidential_basis": {
            "memo": MEMO,
            "memo_sha256": _sha256(memo_path),
            "memo_commit": "3e7b502",
            "decisive_finding": (
                "ValidationRunSpecification_v1.0 binds "
                "SignalDecisionRecord_model_module_sha256 = efc26d3a..., which resolves to "
                "apps/backend/app/research/mr002/spq1/models.py - not one of the 21 modules in the "
                "governed image, and the module defining both SignalDecisionRecord and "
                "ExecutionEnrichedCandidateRecord. The frozen contract therefore already binds "
                "runtime-critical Phase 3B code outside the evaluator image, by SHA-256, and fails "
                "closed on its drift. This clarification states the rule that binding already "
                "demonstrates."
            ),
            "why_a_clarification_was_still_required": (
                "The contract DEMONSTRATES the mechanism but never STATES the rule. Without this "
                "record the boundary would rest on inference, and any later reading would be "
                "retrospective. Recorded prospectively, it is a permission; recorded afterwards it "
                "would be a rationalization."
            ),
            "supporting_records": {
                "blocker_register": {
                    "identity_sha256":
                        "70b3ebd295ded890004100c5d763641c44a7a0d6ae76484ceb0d5a8386d11a38",
                    "commit": "fa9fc9a"},
                "corrigendum_v1": {
                    "identity_sha256":
                        "c392589988a0665aec505efe0415e89d22fe16d56c4c798058935333f0c4b1d4",
                    "commit": "88c11d0"},
                "corrigendum_v2": {
                    "identity_sha256":
                        "ab5598f9f6707a54b71dd67cd95f4d2cca0c3b5d9c8927994326ddf2ddce7043",
                    "commit": "35b43dd"},
            },
        },

        "prospectivity_proof": proof,
        "prospectivity_rule": (
            "The generator REFUSES to emit if a Phase 3B execution layer already exists, if the "
            "evaluator image identity has changed, if any bound evaluator module has drifted, or "
            "if the configuration mapping no longer matches the v0.3 gate table. This record can "
            "therefore only have been written before the layer it permits."
        ),

        "p12_consequence": {
            "current_grant_status": "VALID but NOT YET SPENDABLE",
            "reason": (
                "P12 binds the evaluator image index, dependency lock, numeric runtime manifest, "
                "frozen host, resolver and reader role. It names no orchestrator, runner or "
                "execution-package identity. Option A introduces exactly one identity P12 does not "
                "name - a gap, not a violation."
            ),
            "required_before_the_opening_may_be_spent": (
                "A SUPPLEMENTAL EXECUTION-IDENTITY ADJUDICATION binding: the Phase 3B "
                "RunSpecification identity; the complete runner/orchestrator module roster; "
                "execution_enrichment.py; models.py and every other external runtime-critical "
                "module; an exact SHA-256 for every module; the Config A/B/C executable bindings; "
                "the sealed input manifest and version identities; the exact output contract; the "
                "run ID; the one-opening semantics; and the synthetic qualification evidence."
            ),
            "not_required": (
                "A repeat of the full P5 -> custody -> WP-B -> recovery copy -> P10 -> WP-F -> D3 "
                "-> P12 cycle. That would be required only under Option B, which is not adopted."
            ),
        },

        "explicitly_not_authorized_by_this_record": [
            "validation access or any sealed-object read",
            "Phase 3B real execution",
            "rebuilding or rebinding the evaluator image",
            "weakening the development PartitionGuard",
            "changing Config A/B/C, gates, costs, folds, seams or estimators",
            "Phase 3C metrics",
            "OOS access",
        ],
        "grants": (
            "NOTHING beyond the stated execution-boundary permission. It releases no credential, "
            "edits no trust policy, opens no partition, changes no identity, and computes no "
            "performance. validation_authorization remains true at _rev 1 and the single validation "
            "opening remains UNSPENT."
        ),
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_ExecutionBoundaryClarification_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    p = record["prospectivity_proof"]
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"prospective: execution layer present = {p['phase3b_execution_layer_present']}; "
          f"files scanned = {p['entry_point_scan']['files_scanned']}; "
          f"bound modules verified = {p['bound_modules_verified']}, drift = {p['bound_module_drift']}")
    print(f"config mapping verified {p['configuration_mapping_verified']}")


if __name__ == "__main__":
    main()
