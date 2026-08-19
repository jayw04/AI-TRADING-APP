"""MR-002 Stage-3 v2 — Gate N1 PROSPECTIVE REGISTRATION record.

Freezes, BEFORE any N1 result exists (memo SA-4): the candidate architecture, the candidate set and
profiles, the corpus, the selection rule, the certificate specification, the equivalence rule, the
Reference-Solver-R method, and the N2 stress-generator specification and seed.

Authority: docs/design/MR002/MR002_Stage3v2_AdjudicatedMemo_v1_2.md §5 (Gate N1 grant).
This record AUTHORIZES NOTHING. It produces no result, scores no candidate, and reads nothing
outside the development domain.

IDENTITIES. Every source file is bound by its GIT BLOB sha (never the Windows working tree, which
carries CRLF and fail-closes against an LF deploy). The companion specification markdown is bound by
an LF-normalized working-tree sha marked `enforced: false` until it is committed and pushed; sealing
re-derives it from pushed Git. This mirrors the dual-basis treatment the owner accepted for
`adopted.py` on 2026-08-18.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
REV = "HEAD"

E = "docs/implementation/evidence/mr_002/"
SPEC_MD = E + "MR002_N1_ProspectiveRegistration_v1.0.md"
MEMO = "docs/design/MR002/MR002_Stage3v2_AdjudicatedMemo_v1_2.md"
PENDING_BINDINGS: list[str] = []

STAGE3_CORPUS = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"not committed, cannot bind by Git blob: {path}")
    return hashlib.sha256(out.stdout).hexdigest()


def bound(path: str) -> dict:
    return {"path": path, "file_blob_sha256": blob_sha(path)}


def worktree_lf_sha(path: str) -> str:
    """LF-normalized working-tree sha — equals the future Git blob for a text file."""
    with open(os.path.join(REPO, path), "rb") as fh:
        return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()


def head_is_pushed() -> tuple[bool, str, str]:
    """Is HEAD present on the tracked remote branch?

    A Git-blob identity is only a *pushed* identity once HEAD has reached the remote. Deriving a
    governance identity from a basis that only exists locally is the defect class that produced the
    2026-08-18 source-identity correction; it is checked here rather than remembered.
    """
    def rev(ref: str) -> str:
        out = subprocess.run(["git", "-C", REPO, "rev-parse", ref], capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else ""

    head = rev("HEAD")
    branch = subprocess.run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    remote = rev(f"origin/{branch}")
    return (bool(head) and head == remote), head, remote


def bind_or_pending(path: str, why: str) -> dict:
    """Bind by GIT BLOB once the file is committed; otherwise by LF-normalized worktree sha.

    Self-promoting: no hand-edit is needed after the commit that tracks the file. Until then the
    binding is NON-enforced, because recording it as enforced would assert a Git identity that does
    not exist.
    """
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode == 0:
        return {
            "path": path,
            "file_blob_sha256": hashlib.sha256(out.stdout).hexdigest(),
            "enforced": True,
        }
    PENDING_BINDINGS.append(path)
    return {
        "path": path,
        "worktree_lf_sha256": worktree_lf_sha(path),
        "enforced": False,
        "pending_reason": why,
    }


_pushed, _head, _remote = head_is_pushed()
_IDENTITY_BASIS = {
    "head": _head,
    "remote_head": _remote,
    "head_is_pushed": _pushed,
    "rule": "a Git-blob identity is only a PUSHED identity once HEAD has reached the remote branch",
}

M = "apps/backend/app/research/mr002/"

REG: dict = {
    "record_type": "MR002_N1_PROSPECTIVE_REGISTRATION",
    "record_status": "DRAFT",
    "version": "1.0",
    "program": "MR-002 / SPQ-1",
    "gate": "N1",
    "date": "2026-08-19",

    "authority": {
        "memo": MEMO,
        "section": "5 — Authorization / Gate N1 (DEVELOPMENT PROTOTYPE)",
        "this_record_authorizes": "nothing",
        "scope": "N1 only",
    },

    "specification_document": bind_or_pending(SPEC_MD, "not yet committed — created by this session"),

    # ── §0.1 owner review, applied BEFORE any candidate was scored ───────────────────────────────
    "owner_review": {
        "date": "2026-08-19",
        "reviewed_before_any_result_existed": True,
        "amendments": [
            {
                "id": 1,
                "title": "equivalence proof mandatory for N1_ADVANCE, not part of candidate acceptance",
                "effect": (
                    "BOUND_UNAVAILABLE is an intermediate evidence state, never a post-results escape "
                    "hatch; unresolved equivalence at final N1 adjudication is incompatible with "
                    "N1_ADVANCE — N1_STOP, not owner discretion after seeing the numbers"
                ),
                "sections": ["3.3", "4.3", "4.4", "6", "7"],
            },
            {
                "id": 2,
                "title": "HIGHS_QPASM stays excluded for N1 v1.0, narrative corrected",
                "effect": (
                    "it is the B-CANDIDATE UNIVERSE that fails to diversify away from the demonstrated "
                    "fallback failure family; Solver A is ACTIVE-SET, not interior-point"
                ),
                "sections": ["5.2"],
            },
            {
                "id": 3,
                "title": "exception provenance tightened",
                "effect": (
                    "blanket GENERATOR_INTERNAL_ERROR withdrawn; provenance assigned mechanically by "
                    "traceback ownership; ambiguity blocks advancement"
                ),
                "sections": ["2.2", "2.3", "2.5"],
            },
            {
                "id": 4,
                "title": "N2 axis A2 generalized from PIQP max_iter to iterative convergence burden",
                "effect": "the stress population is not structurally tailored to one implementation",
                "sections": ["8"],
            },
        ],
        "frozen_principles": [
            "generator numerical failure may be non-fatal; provenance ambiguity is not",
            "solver correctness and proof that N1 preserved the economic method are different claims: "
            "a candidate may be accepted without the second; MR-002 may not ADVANCE without it",
        ],
    },

    # ── §0 prior-evidence disclosure ─────────────────────────────────────────────────────────────
    "prior_evidence_disclosure": {
        "known_to_the_author": [
            E + "MR002_Stage3FallbackCandidateUniverse_v1.0.json",
            E + "MR002_Stage3FallbackSelection_Audit_v1.0.json",
        ],
        "why_the_freeze_is_still_meaningful": [
            "the N1 selection rule is the owner-written SA-4 lexicographic ordering, not a rule "
            "derived from that evidence",
            "those counts were produced under the v1 acceptance predicate; N1 re-scores every "
            "candidate under this record's specification, so no v1 count transfers",
        ],
        "citation_discipline": "no N1 output may cite the v1 bakeoff counts as N1 evidence",
    },

    # ── §1 the defect N1 removes ─────────────────────────────────────────────────────────────────
    "defect_under_remedy": {
        "event": "2026-08-19T12:49Z governed validation execution",
        "opening": "CONSUMED",
        "outcome": "INTEGRITY_FAILURE",
        "stop_string": (
            "Stage3Stop: INVALID_RUN: fallback integrity defect: "
            "UNREGISTERED_EXCEPTION:RuntimeError:status Status.PIQP_MAX_ITER_REACHED"
        ),
        "mechanism": (
            "stage3_cascade.normalize decides eligibility from an exact exception-class/message "
            "allowlist scoped to QUADPROG_SQRT; any other raise maps to INTEGRITY_DEFECT, and an "
            "INTEGRITY_DEFECT in the fallback is INVALID_RUN"
        ),
        "correct_classification": (
            "a QP generator terminating without a candidate — memo SA-5 INCIDENT_CLASS_KNOWLEDGE, "
            "permitted knowledge"
        ),
        "prohibited_remedy": (
            "raising PIQP max_iter (frozen at 1000 in the BASE profile) or retuning any tolerance "
            "after observing this failure is a PROFILE CHANGE, prohibited by memo §5 and by the "
            "cascade countersignature §5.1"
        ),
    },

    # ── §2 candidate architecture ────────────────────────────────────────────────────────────────
    "architecture": {
        "principle": (
            "a candidate is accepted because it carries a certificate, never because of how the "
            "generator behaved; generator exceptions/statuses/messages are recorded, never routing "
            "inputs"
        ),
        "generators": 2,
        "generators_permanent": True,
        "per_generator_outcome_enum": {
            "CERTIFIED": "contract-conforming (z, lambda) and the registered predicate is true",
            "NO_CERTIFIED_CANDIDATE": (
                "no certified candidate for a reason whose provenance is MECHANICALLY ASSIGNED TO "
                "THE SOLVER LIBRARY: a registered terminal status; an exception raised inside the "
                "solver library; non-finite values in a correctly shaped return; or certifier "
                "completed with the registered predicate false. SA-5 INCIDENT_CLASS_KNOWLEDGE."
            ),
            "SYSTEM_INTEGRITY_DEFECT": (
                "defect in the system, not the generator's numerics: model-input contract "
                "violation; solver-identity/provenance failure; certifier fault or certifier-"
                "contract violation; the return violating the arity/shape/dtype contract; and ANY "
                "exception whose deepest owned frame is in our mapping, wrapper, certificate "
                "plumbing, or invariants"
            ),
        },
        "failure_class_boundary": "shape is ours (system defect); values are the solver's (no candidate)",
        "baseexception_not_exception": "propagates, never normalized",
        "exception_allowlist": "DELETED — not extended. No registered-message table exists to fall out of.",
        "v1_categories_collapsed_into_NO_CERTIFIED_CANDIDATE": [
            "NUMERICAL_STATUS_NONQUALIFICATION",
            "CERTIFICATE_NONQUALIFICATION",
            "the behavioural half of v1 INTEGRITY_DEFECT",
        ],
        "cost_of_collapsing_and_how_it_is_paid": {
            "cost": (
                "a naive collapse would turn a genuine wrapper bug into NO_CERTIFIED_CANDIDATE, "
                "silently covered by the other generator — the MIRROR IMAGE of the v1 defect"
            ),
            "payment_structural": (
                "provenance decides the class, not the message: only LIBRARY-OWNED exceptions are "
                "eligible for NO_CERTIFIED_CANDIDATE; wrapper-owned exceptions remain "
                "SYSTEM_INTEGRITY_DEFECT and still stop the run"
            ),
            "payment_census": (
                "every NO_CERTIFIED_CANDIDATE carries a reason code from the registered closed "
                "taxonomy; an unattributable exception or an unlisted reason is recorded as "
                "UNREGISTERED_TERMINATION_REASON and counted at the census"
            ),
            "n1_advance_condition": "UNREGISTERED_TERMINATION_REASON == 0 over the whole development corpus",
        },
        "terminal_statuses_are_returned_never_raised": (
            "each generator wrapper translates its library's terminal statuses into an explicit "
            "GeneratorTermination(reason) RETURN VALUE and does not raise for them; a status is data, "
            "so an exception escaping a wrapper is an UNPLANNED event by construction"
        ),
        "registered_termination_reasons": [
            "ITERATION_LIMIT_REACHED",
            "CONSTRAINTS_REPORTED_INCONSISTENT",
            "NUMERICAL_BREAKDOWN",
            "NON_FINITE_CANDIDATE",
            "CERTIFICATE_PREDICATE_FALSE",
            "LIBRARY_RAISED",
        ],
        "withdrawn_reason_codes": {
            "GENERATOR_INTERNAL_ERROR": (
                "WITHDRAWN by owner amendment 3 — 'catch every Exception and downgrade it' recreates "
                "the opposite of the v1 failure mode"
            ),
        },
        "provenance_rule": {
            "principle": "generator numerical failure may be non-fatal; provenance ambiguity is not",
            "never": "the exception message is never read — the v1 defect was routing on text",
            "method": (
                "walk the traceback from the DEEPEST frame outward and take the first frame belonging "
                "to a registered ownership domain"
            ),
            "domains": {
                "solver_library": {
                    "roots": ["piqp", "clarabel", "quadprog", "highspy"],
                    "includes": "their extension modules",
                    "class": "NO_CERTIFIED_CANDIDATE",
                    "reason": "LIBRARY_RAISED",
                },
                "ours": {
                    "roots": ["app.research.mr002.*", "registered wrapper/certifier modules"],
                    "class": "SYSTEM_INTEGRITY_DEFECT",
                    "reason": "WRAPPER_ORIGIN",
                },
                "neither": {
                    "condition": "no frame belongs to any registered domain, or the traceback is absent/unresolvable",
                    "class": "UNREGISTERED_TERMINATION_REASON",
                    "effect": "the instance resolves, but N1 CANNOT ADVANCE",
                },
            },
            "shared_numeric_libraries_are_transparent": (
                "numpy and scipy are NOT ownership domains: a numpy raise inside PIQP's Python layer "
                "resolves outward to piqp (the library's); a numpy raise inside our mapping resolves "
                "outward to us (ours)"
            ),
            "solver_library_root_list_is_frozen": (
                "adding to it after observing a failure is a profile-class change and is prohibited "
                "on the same footing as retuning max_iter"
            ),
        },
        "certificate_predicate_false_carries": "the failing predicate terms verbatim",
        "library_raised_carries": "the exception class and the owning module",
        "run_level_dispositions": {
            "PRIMARY_CERTIFIED": "A certified; accept A's point; B not invoked in production mode",
            "SECONDARY_CERTIFIED": "A NO_CERTIFIED_CANDIDATE, B certified; accept B's point",
            "UNRESOLVED_INSTANCE": "neither certified; STOP; classified individually per SA-3",
            "INVALID_RUN": "any SYSTEM_INTEGRITY_DEFECT; STOP",
            "CERTIFIED_SOLUTION_DISAGREEMENT": (
                "both certified and norm(z_A - z_B) exceeds the equivalence bound; "
                "INTEGRITY_FAILURE per SA-2 — no lower-objective pick, no voting, no re-run"
            ),
        },
        "both_certified_arises_in": "N1 development qualification, where both generators and R run on every instance",
        "prohibited": [
            "a third attempt",
            "jitter",
            "per-instance routing",
            "eligibility by analogy",
            "tolerance or profile change",
        ],
    },

    # ── §3 certificate specification ─────────────────────────────────────────────────────────────
    "certificate_specification": {
        "acceptance_predicate": "UNCHANGED from the registered certifier",
        "why_unchanged": (
            "the accepted point IS the frozen Stage-3 economic solution; changing the predicate "
            "would change which point is accepted and the preservation claim would have to be "
            "re-earned rather than held by construction. N1 changes the disposition of failures."
        ),
        "limits": {
            "primal_residual": 1e-9,
            "dual_residual": 1e-9,
            "stationarity_residual": 1e-8,
            "complementarity_residual": 1e-8,
            "kkt_residual": 1e-8,
        },
        "signed_gap": {
            "SIGNED_GAP_MAX": 1e-10,
            "test": "whole outward-rounded interval contained in [-1e-10, +1e-10]",
            "IV_DPS": 100,
            "MAX_INTERVAL_WIDTH": 1e-30,
        },
        "added_equivalence_certificate": {
            "memo_route": "§2 route (a) — rigorous derivation",
            "dual_lower_bound": "certificate.py — weak duality, valid for any lambda_bar with lambda_bar[meq:] >= 0",
            "feasibility_qualifier": (
                "repair.py profile R2 — an EXACTLY feasible rational point proved by exact absorber "
                "enumeration and exact verification against the ORIGINAL, UNTIGHTENED constraints"
            ),
            "gap": "Ghat_s = f(zhat_s) - d(lambda_bar_s) >= 0",
            "radius": "R_s = delta_s + sqrt(2*Ghat_s/mu), delta_s = norm(z_s - zhat_s), outward-rounded",
            "mu": "2 / max_i t_i  (lambda_min(H) for H = diag(2/t)) — matches the memo's 2/max target_i",
        },
        "repair_certificate_unavailable": {
            "is_acceptance_failure": False,
            "is_integrity_defect": False,
            "candidate_may_be_CERTIFIED_without_it": True,
            "recorded_per_instance": True,
            "census_requires_full_per_instance_list": "SA-3 forbids an aggregate percentage hiding the tail",
            "effect_on_an_agreement_question": "BOUND_UNAVAILABLE — never assumed to agree",
            "is_never_a_route_to_advance": "the preservation claim is gated separately and unconditionally by the equivalence gate",
        },
        "distinction_preserved": (
            "solver correctness and proof that N1 preserved the economic method are different claims "
            "with different evidence. Folding the second into the acceptance predicate would push "
            "resolution below 100% for reasons unrelated to generator correctness; dropping it would "
            "let BOUND_UNAVAILABLE become a post-results escape hatch. The equivalence gate is the "
            "middle rule: acceptance stays clean, advancement does not."
        ),
    },

    # ── §4 equivalence rule ──────────────────────────────────────────────────────────────────────
    "equivalence_rule": {
        "bound": "norm(z_1 - z_2) <= R_1 + R_2 + AGREEMENT_SLACK",
        "lhs_evaluation": "upper endpoint from exact rationals (repair.agreement)",
        "companion_objective_test": "|f(z_1) - f(z_2)| <= U_1 + U_2 + OBJECTIVE_SLACK (repair.objective_agreement)",
        "constant_provenance": {
            "R_s": "DERIVED — weak duality + strong convexity + exact feasibility",
            "mu": "STRUCTURAL — lambda_min(H) for H = diag(2/t)",
            "AGREEMENT_SLACK": "INHERITED — 1e-10, already frozen in repair.py before N1",
            "OBJECTIVE_SLACK": "INHERITED — same provenance",
        },
        "never": ["residual-assumed", "hand-picked", "influenced by validation information"],
        "route_b_usage": "not used for the bound itself (route (a) closes); survives only as BOUND_UNAVAILABLE handling",
        "bound_unavailable": {
            "state": "INTERMEDIATE EVIDENCE STATE ONLY",
            "is_terminal_disposition": False,
            "deferred_to_discretion_at_the_verdict": False,
            "must_be_resolved_by": "the equivalence gate before N1 can advance",
        },
    },

    # ── §4.4 the equivalence gate (owner amendment 1) ────────────────────────────────────────────
    "equivalence_gate": {
        "mandatory_for": "N1_ADVANCE",
        "part_of_candidate_acceptance": False,
        "required_population": (
            "every instance in the registered 3,895-instance corpus for which the v1 method produced "
            "an accepted point (PRIMARY_QUALIFIED or FALLBACK_QUALIFIED); the census establishes the "
            "exact set — under the recorded governed development qualification it is the whole corpus"
        ),
        "v1_point_provenance": (
            "z_v1 is REGENERATED by executing the v1 method on the same frozen corpus in the same "
            "pinned image; the regeneration must reproduce the recorded v1 dispositions exactly, and "
            "a mismatch is a SYSTEM_INTEGRITY_DEFECT that stops N1. Equivalence is never asserted "
            "against a remembered number."
        ),
        "not_the_same_as_SA2": (
            "CERTIFIED_SOLUTION_DISAGREEMENT compares A against B on one instance; this gate compares "
            "v2-accepted against v1-accepted. Two different questions, two different pairs, both required."
        ),
        "routes_in_order": [
            {"route": "E0", "name": "identity", "condition": "z_v2 byte-identical to z_v1",
             "result": "EQUIVALENCE_TRIVIAL"},
            {"route": "E1", "name": "derived bound",
             "condition": "both points carry repair certificates and norm(z_v1 - z_v2) <= R_v1 + R_v2 + AGREEMENT_SLACK",
             "result": "EQUIVALENCE_PROVEN_BOUND"},
            {"route": "E2", "name": "exact reference",
             "condition": "R_EXACT available; rho_s substitutes the exact d_s = norm(z_s - z*) for any "
                          "side lacking a repair certificate, and norm(z_v1 - z_v2) <= rho_v1 + rho_v2 + AGREEMENT_SLACK",
             "result": "EQUIVALENCE_PROVEN_R"},
            {"route": "E3", "name": "neither", "condition": "no route establishes it",
             "result": "EQUIVALENCE_UNPROVEN"},
        ],
        "why_E2_is_rigorous": (
            "the program is strictly convex so z* is UNIQUE, and R_EXACT supplies each side's error "
            "exactly; an exact distance is a TIGHTER radius than the derived R_s, not a looser one"
        ),
        "gate": "ANY EQUIVALENCE_UNPROVEN instance in the required population means N1_STOP",
        "gate_is_not": [
            "owner discretion after seeing the numbers",
            "a deferred adjudication item",
            "an exception granted because the count is small",
        ],
        "registered_now_because": (
            "it is registered before any number exists precisely so it cannot be renegotiated later"
        ),
        "no_ceiling_relief": (
            "if E2 fails because R hit a frozen resource ceiling, the ceiling is NOT raised for that "
            "instance — raising one after observing the instance it stopped on is the same class of "
            "act as retuning a solver profile after observing a failure"
        ),
    },

    # ── §5 selection ─────────────────────────────────────────────────────────────────────────────
    "selection": {
        "solver_A_fixed": "QUADPROG_SQRT",
        "solver_A_under_selection": False,
        "corpus": {
            "instances": 3895,
            "corpus_hash": STAGE3_CORPUS,
            "regeneration": "replay configs A, B, C over the development window from mr002_research.duckdb",
            "window": ["2013-01-02", "2019-10-02"],
            "hash_reverified_at_execution_start": True,
            "on_mismatch": "ABORT N1 before any candidate is scored",
        },
        "runtime": {
            "image": "mr002-research:v1.4",
            "network": "none",
            "frozen_thread_env": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
                "OPENBLAS_CORETYPE": "HASWELL",
            },
            "note": "an unset thread variable is not frozen; a green small-fixture suite is not evidence",
        },
        "boundary": {
            "development_domain_only": True,
            "consumed_validation_duckdb": "OUT OF SCOPE — unread",
            "validation_derived_qp": "OUT OF SCOPE — unread",
            "oos": "NOT AUTHORIZED",
            "historical_returns_may_influence_selection": False,
        },
        "candidate_set": [
            {"profile": "PIQP_P1", "family": "interior-point (proximal)", "admissible": True},
            {"profile": "PIQP_P2", "family": "interior-point (proximal)", "admissible": True},
            {"profile": "CLARABEL", "family": "interior-point (conic, QP-form)", "admissible": True},
            {"profile": "QUADPROG_RAW", "family": "active-set (quadprog)", "admissible": False,
             "reason": "not algorithmically distinct from the active-set primary"},
            {"profile": "QUADPROG_TSCALED", "family": "active-set (quadprog)", "admissible": False,
             "reason": "not algorithmically distinct from the active-set primary"},
            {"profile": "HIGHS_QPASM", "family": "active-set", "admissible": False,
             "reason": "not algorithmically distinct from the active-set primary"},
        ],
        "candidate_set_bounded_by": "the pinned image — no candidate may force a new dependency or a new image",
        "admissibility_gate_C0": [
            "algorithmically distinct from Solver A",
            "exactly one globally fixed configuration",
            "valid primal AND dual mapping under the common certifier",
            "deterministic",
            "canonically shuffle-invariant",
            "no per-instance adjustment",
            "present in the pinned image",
        ],
        "declarations": {
            "clarabel_exact_conic_experiment": (
                "commit 18c55f5, invalid dual transformation — RETIRED, not a candidate, and not "
                "evidence about the admissible QP-form profile"
            ),
            "highs_qpasm_exclusion": {
                "disposition": "REMAINS EXCLUDED for N1 v1.0 (owner amendment 2)",
                "registered_wording": (
                    "The observed validation failure occurred in the v1 interior-point fallback PIQP. "
                    "All currently admissible Solver-B candidates are also interior-point / conic-"
                    "interior-point implementations, so the B-candidate universe does not diversify "
                    "away from the demonstrated fallback failure family. HIGHS_QPASM would add an "
                    "independently implemented active-set candidate, but admitting it would change "
                    "the inherited C0 requirement that B be algorithmically distinct from the "
                    "active-set Solver A. That admissibility rule is not reopened in N1 v1.0."
                ),
                "correction_to_the_earlier_draft": (
                    "SOLVER A IS ACTIVE-SET, NOT INTERIOR-POINT. A and B do not share the demonstrated "
                    "failure family; it is the SET OF AVAILABLE B CANDIDATES that is undiversified. A "
                    "future reader taking the earlier phrasing to mean QUADPROG_SQRT is interior-point "
                    "would be wrong."
                ),
                "why_not_reopened_now": (
                    "broadening the candidate universe in response to the specific observed failure "
                    "family would use the consumed validation incident to reshape N1's frozen inputs. "
                    "SA-5 permits incident-class knowledge for HARDENING, so that knowledge goes into "
                    "the N2 stress design, not into widening N1's candidate set."
                ),
                "if_no_candidate_passes": (
                    "N1_STOP — not 'then add HiGHS'. If active-set implementation diversity is later "
                    "judged an architectural hypothesis worth testing on its own merits, that is a NEW "
                    "prospective N1 registration, not an amendment made after seeing this N1's scores."
                ),
            },
        },
        "rule": "SA-4 lexicographic; a later criterion is consulted only among candidates tied on every earlier one",
        "criteria": [
            {"id": "C1", "name": "zero integrity defects", "type": "hard gate",
             "pass": "SYSTEM_INTEGRITY_DEFECT == 0 over the corpus, both paired and standalone"},
            {"id": "C2", "name": "100% dev-corpus certified resolution", "type": "hard gate",
             "pass": "3895/3895 end PRIMARY_CERTIFIED or SECONDARY_CERTIFIED; zero UNRESOLVED_INSTANCE; zero INVALID_RUN"},
            {"id": "C3", "name": "agreement with R", "type": "hard gate",
             "pass": "zero agreement violations against R on the R-available subset, and zero CERTIFIED_SOLUTION_DISAGREEMENT between A and B"},
            {"id": "C4", "name": "deterministic reproducibility", "type": "hard gate",
             "pass": "two independent runs in the pinned image give byte-identical accepted z and identical dispositions; canonical shuffle-invariance holds"},
            {"id": "C5", "name": "runtime", "type": "ordering", "pass": "lower total corpus wall-clock wins"},
            {"id": "C6", "name": "dependency simplicity", "type": "ordering", "pass": "fewer / lighter dependencies wins"},
        ],
        "tie_surviving_C6": "OWNER ADJUDICATION ITEM — no seventh tiebreak, no coin flip, no undocumented preference",
        "if_no_candidate_passes_C1_to_C4": "N1_STOP — not an invitation to retune a profile or widen the candidate set after seeing results",
        "authority_boundary": {
            "n1_selects": "exactly one Solver B, using development evidence only",
            "n2_may_substitute_solver": False,
            "substitution_consequence": "restarts N1 under a new prospective selection record",
        },
    },

    # ── §6 Reference Solver R ────────────────────────────────────────────────────────────────────
    "reference_solver_R": {
        "role": "establishes numerical truth on development and stress instances",
        "never": [
            "a production generator",
            "a third voter in the cascade",
            "consulted on any validation instance",
        ],
        "prohibition_enforcement": "module-level guard in code, not convention",
        "method": "exact-rational primal active-set QP solver on the registered canonical form",
        "arithmetic": "fractions.Fraction throughout; no tolerance anywhere in R",
        "reuses": [
            M + "exact_simplex.py — Bland's rule over canonical identities, deterministic, no float in the proof path",
            M + "certificate.py / " + M + "repair.py — exact ingestion via as_integer_ratio, never str()",
        ],
        "returns": {
            "R_EXACT": "the exact minimizer z* as a rational vector with an exact KKT certificate "
                       "(stationarity exactly zero, exact primal feasibility, exact lambda >= 0, exact complementarity)",
            "R_UNAVAILABLE": "a frozen resource ceiling was reached",
        },
        "ceilings": "mirror exact_simplex.py — operational stop limits, NOT mathematical tolerances; "
                    "may not be raised after observing a stopped instance without a new adjudication",
        "r_unavailable_handling": {
            "C3_selection_criterion_evaluated_on": "the R-available subset",
            "unavailable_subset": "reported with its FULL per-instance list, individually classified (SA-3)",
            "large_unavailable_subset": "itself an N1 adjudication item — a weak reference weakens C3",
            "cannot_weaken_the_preservation_gate": (
                "R may be unavailable OPERATIONALLY; equivalence may not be unavailable LOGICALLY if "
                "N1 wants to advance (owner amendment 1)"
            ),
            "composition_with_the_equivalence_gate": [
                "repair bound unavailable + R exact -> E2 proves equivalence -> fine",
                "R unavailable + repair bound available -> E1 proves equivalence -> fine",
                "BOTH unavailable -> EQUIVALENCE_UNPROVEN -> N1_STOP",
            ],
            "no_ceiling_raised_after_seeing_the_instance": True,
        },
        "agreement_meaning": "z* is exact, so norm(z_s - z*) <= R_s is a rigorous one-sided statement per certified point; "
                             "C3 tests exactly that using the §4 radius, not a second threshold",
    },

    # ── §7 outputs and disposition ───────────────────────────────────────────────────────────────
    "n1_outputs_exhaustive": [
        "candidate architecture",
        "N1-selected and frozen Solver A/B profiles",
        "Reference-Solver method",
        "certificate specification",
        "equivalence rule",
        "full development census (3,895 rows)",
        "difference-vs-v1 report",
        "preregistered N2 stress-generator specification and seed",
    ],
    "census_row_fields": [
        "instance_index", "instance_hash", "n", "meq", "kappa_H",
        "A_outcome", "A_reason", "A_provenance_domain",
        "B_outcome", "B_reason", "B_provenance_domain",
        "disposition", "accepted_by",
        "certificate_fields", "repair_certificate_available", "radius_upper",
        "R_status", "R_agreement", "agreement_bound", "agreement_lhs",
        "equivalence_route", "equivalence_status",
    ],
    "disposition_domain": ["N1_ADVANCE", "N1_STOP"],
    "n1_advance_requires_all_of": [
        "1. a candidate passing C1-C4",
        "2. UNREGISTERED_TERMINATION_REASON == 0 over the whole development corpus",
        "3. zero CERTIFIED_SOLUTION_DISAGREEMENT",
        "4. EQUIVALENCE_UNPROVEN == 0 over the required population, and zero instances left in "
        "BOUND_UNAVAILABLE — the preservation gate, not subject to discretion",
        "5. the corpus hash re-verified",
        "6. SA-3 frozen words satisfiable: 100% of the registered development population ends in a "
        "preregistered admissible state; previously accepted v1 instances return equivalent "
        "certified allocations; residual unresolved instances individually classified",
    ],
    "n1_advance_note": "condition 4 is what makes condition 6's middle clause PROVABLE rather than asserted",
    "n1_stop_consequence": "closes MR-002 without a further validation/governance cycle",
    "n1_advance_authorizes": "nothing beyond N1 — N2 requires its own grant",

    # ── §8 N2 stress generator ───────────────────────────────────────────────────────────────────
    "n2_stress_generator": {
        "designed_in": "N1",
        "run_in": "N2, under N2's own grant",
        "n1_consumes_n2_results": False,
        "n1_may_use": "development-domain fixtures only, to test generator plumbing",
        "determinism": {
            "rng": "numpy.random.Generator(numpy.random.PCG64(seed))",
            "instances": "one generator instance, emitted in index order",
            "forbidden_inputs": ["dict/set iteration order", "wall clock", "hostname"],
            "requirement": "regenerating from the seed reproduces the population BYTE-IDENTICALLY",
            "population_hash": "recorded at generation, re-verified before use",
        },
        "seed": 20260819,
        "structural_contract": {
            "t_positive_elementwise": True,
            "meq": 1,
            "box": "0 <= z <= u",
            "finite": ["A_ub", "b_ub", "A_eq", "b_eq", "upper"],
            "kappa_H_max": 1e10,
            "on_violation": "rejected at generation — a contract violation is a generator bug, not a stress case",
        },
        "strata": [
            {"axis": "A1", "mechanism": "Hessian conditioning kappa(H) = max t / min t",
             "sweep": "log-spaced decades 1e2 .. 1e10", "instances": 400},
            {"axis": "A2",
             "mechanism": "iterative-solver burden / convergence stress — implementation-agnostic: high "
                          "dimension, dense constraints, many near-active rows. Designed using permitted "
                          "SA-5 INCIDENT_CLASS_KNOWLEDGE; NO parameter is taken from the consumed "
                          "validation instance.",
             "sweep": "wide n, dense A_ub, high near-active fraction", "instances": 600},
            {"axis": "A3", "mechanism": "constraint tightness, slack approaching ETA = 1e-12",
             "sweep": "slack decades 1e-6 .. 1e-13", "instances": 400},
            {"axis": "A4", "mechanism": "equality-slack scarcity — the repair-absorber / REPAIR_CERTIFICATE_UNAVAILABLE mechanism",
             "sweep": "equality coefficients spanning many magnitudes against tight box slack", "instances": 400},
            {"axis": "A5", "mechanism": "active-set size",
             "sweep": "fraction of rows active 0 .. 1", "instances": 300},
            {"axis": "A6", "mechanism": "structurally empty A_ub rows",
             "sweep": "present / absent", "instances": 200},
            {"axis": "A7", "mechanism": "boundary optima, where R1-style projection provably failed",
             "sweep": "coordinates pinned at 0 and at u", "instances": 300},
            {"axis": "A8", "mechanism": "wide-n scaling",
             "sweep": "n across and above the development range", "instances": 400},
        ],
        "population_size": 3000,
        "a2_not_tailored_to_one_implementation": (
            "owner amendment 4 — A2 stresses CONVERGENCE BURDEN, which every iterative method has, "
            "rather than PIQP's particular max_iter knob; the A/B pair N1 freezes might select "
            "CLARABEL, and a stress population shaped around one vendor's iteration counter would "
            "qualify it dishonestly"
        ),
        "candidate_profiles_remain_frozen_under_stress": (
            "each candidate profile retains its own frozen registered limits: the PIQP profiles keep "
            "max_iter = 1000, and every other profile keeps whatever its registered configuration "
            "specifies. Stress changes the INSTANCES, never the PROFILES."
        ),
        "n2_rule": "qualifies the N1-FROZEN A/B pair at 100% registered resolution or STOP (SA-3 frozen words for stress)",
        "n2_may_substitute_solver_B": False,
        "n2_additionally_reports": "an independent regeneration and re-run producing identical dispositions",
    },

    # ── §9 untouched ─────────────────────────────────────────────────────────────────────────────
    "untouched_by_this_record": [
        "A/B/C parameters, costs, constraints, Stage-1 and Stage-2",
        "every Validation-2 design decision (VA-1 sample design, VA-2 merge mechanics, VA-3 accrual "
        "infrastructure, the untouched-sample definition) — all sit behind N3, at Cycle 2C",
        "the consumed opening — no replacement opening is requested, implied, or needed by N1",
        "OOS — remains NOT AUTHORIZED",
    ],
    "sealed_or_reference_bytes_read": 0,

    # ── bindings ─────────────────────────────────────────────────────────────────────────────────
    "binds": {
        "memo": bind_or_pending(MEMO, "the authorizing memo is UNTRACKED in Git; it must be committed and pushed before sealing"),
        "incumbent_cascade": bound(M + "stage3_cascade.py"),
        "incumbent_seam": bound(M + "stage3_route.py"),
        "certifier_construction": bound(M + "joint_portfolio.py"),
        "signed_gap_certificate": bound(M + "certificate.py"),
        "exact_feasible_repair": bound(M + "repair.py"),
        "exact_repair_constructor": bound(M + "exact_repair.py"),
        "exact_rational_simplex": bound(M + "exact_simplex.py"),
        "directed_rounding": bound(M + "directed.py"),
        "prior_candidate_universe": bound(E + "MR002_Stage3FallbackCandidateUniverse_v1.0.json"),
        "prior_selection_audit": bound(E + "MR002_Stage3FallbackSelection_Audit_v1.0.json"),
        "eligibility_status_mapping": bound(E + "MR002_Stage3EligibilityStatusMapping_v1.0.json"),
        "validation_execution_outcome": bound(E + "MR002_Phase3C_ValidationExecutionOutcome_v1.0.json"),
    },

    "identity_basis": _IDENTITY_BASIS,
    "pending_bindings_blocking_seal": PENDING_BINDINGS,
    "sealing_requirements": [
        "owner acceptance",
        "commit",
        "push",
        "re-derivation of the record identity from PUSHED Git blobs",
        "specification_document rebound by Git blob with enforced=true",
    ],
    "gate_before_any_n1_result": "NO N1 CANDIDATE MAY BE SCORED BEFORE THIS RECORD IS SEALED",
}

REG["record_identity_sha256"] = hashlib.sha256(_canonical(REG)).hexdigest()
out = os.path.join(_HERE, "MR002_N1_ProspectiveRegistration_v1.0_DRAFT.json")
with open(out, "wb") as fh:
    fh.write(_canonical(REG))

print(json.dumps({
    "record": "MR002_N1_ProspectiveRegistration_v1.0_DRAFT",
    "record_identity_sha256": REG["record_identity_sha256"],
    "record_status": REG["record_status"],
    "spec_md_worktree_lf_sha256": REG["specification_document"]["worktree_lf_sha256"],
    "spec_md_enforced": REG["specification_document"]["enforced"],
    "corpus_hash": STAGE3_CORPUS,
    "admissible_candidates": [c["profile"] for c in REG["selection"]["candidate_set"] if c["admissible"]],
    "n2_seed": REG["n2_stress_generator"]["seed"],
    "bindings": len(REG["binds"]),
    "pending_bindings_blocking_seal": PENDING_BINDINGS,
    "head_is_pushed": _pushed,
}, indent=1))
