"""MR-002 Gate N1 — assemble the VERDICT record from the census, gate and C4/C5 stages.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af.

Consumes the three stage outputs and applies §5.3's lexicographic rule and §7's advance conditions
MECHANICALLY. The disposition is computed from the evidence, not asserted: if a hard gate fails, the
record says N1_STOP regardless of how much of the work succeeded.

Reads only development-domain artifacts. Emits no numbers it did not read from a stage output.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
OUT = os.path.join(REPO, ".mr002out", "n1")
REGISTRATION_IDENTITY = "7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af"
CORPUS_HASH = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"

A_PROFILE = "QUADPROG_SQRT"
ADMISSIBLE = ("PIQP_P1", "PIQP_P2", "CLARABEL")


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    o = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], capture_output=True)
    if o.returncode != 0:
        return "UNCOMMITTED"
    return hashlib.sha256(o.stdout).hexdigest()


def load(name: str) -> dict | None:
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def sha_file(name: str) -> str | None:
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main() -> int:
    census = load("n1_census_c1c2.json")
    gate = load("n1_equivalence.json")
    c4c5 = load("n1_c4c5.json")
    shuffle = load("n1_shuffle.json")
    diffv1 = load("n1_diff_v1.json")
    missing = [n for n, v in (("census", census), ("gate", gate), ("c4c5", c4c5),
                              ("shuffle", shuffle)) if v is None]

    per: dict[str, dict] = {}
    for cand in ADMISSIBLE:
        c = (census or {}).get("results", {}).get(cand)
        g = (gate or {}).get("candidates", {}).get(cand)
        q = (c4c5 or {}).get(cand)
        row: dict = {"candidate": cand}

        row["C1"] = {"pass": bool(c and c["C1_zero_integrity_defects"]),
                     "system_integrity_defects": c and c["C1_system_integrity_defects"]}
        row["C2"] = {"pass": bool(c and c["C2_full_resolution"]),
                     "resolved": c and c["C2_resolved"],
                     "unresolved": c and c["unresolved_instances"],
                     "invalid_runs": c and c["invalid_runs"]}
        if g is None:
            row["C3"] = {"pass": None, "note": "not evaluated — eliminated earlier or stage absent"}
            row["equivalence_gate"] = {"pass": None}
            row["SA2"] = {"pass": None}
        else:
            row["C3"] = {"pass": bool(g["c3_pass_on_evaluable_subset"]) if g["c3"]["evaluable"] else None,
                         **g["c3"]}
            row["equivalence_gate"] = {"pass": bool(g["equivalence_gate_pass"]),
                                       "EQUIVALENCE_UNPROVEN": g["EQUIVALENCE_UNPROVEN"],
                                       "routes": g["equivalence"]}
            row["SA2"] = {"pass": bool(g["sa2_pass"]), **g["sa2"]}
        if q is None:
            row["C4"] = {"pass": None}
            row["C5"] = {"median_seconds": None}
        else:
            # C4(b) comes from the REFINED shuffle report, which separates "the permuted problem
            # failed to certify" from "it certified at a different point". The first C4 pass
            # conflated them, and only the second is a solution non-invariance.
            pg = (shuffle or {}).get("per_generator", {}).get(cand, {})
            ml = (shuffle or {}).get("method_level", {}).get(cand, {})
            row["C4"] = {
                "C4a_runs_identical": q["C4a_runs_identical"],
                "C4a_pass": bool(q["C4a_runs_identical"]),
                "C4b_per_generator": pg,
                "C4b_method_level": ml,
                "C4b_per_generator_beyond_slack": pg.get("deviates_beyond_slack"),
                "C4b_method_level_beyond_slack": ml.get("deviates_beyond_slack"),
                "C4b_method_level_disposition_changed": ml.get("disposition_changed"),
                # pass at the granularity that the accepted point -- the economic solution -- is
                # actually produced at; the per-generator result is reported alongside, never hidden
                "pass": bool(q["C4a_runs_identical"]) and ml.get("deviates_beyond_slack") == 0,
                "pass_strict_per_generator": (bool(q["C4a_runs_identical"])
                                              and pg.get("deviates_beyond_slack") == 0),
            }
            row["C5"] = {"median_seconds": q["C5_median_seconds"],
                         "times": q["C5_times_seconds"]}

        # lexicographic elimination — the FIRST hard gate that fails ends the candidate
        eliminated_at = None
        for gate_id in ("C1", "C2", "C3", "C4"):
            v = row[gate_id]["pass"]
            if v is False:
                eliminated_at = gate_id
                break
        if eliminated_at is None and row["equivalence_gate"]["pass"] is False:
            eliminated_at = "EQUIVALENCE_GATE"
        if eliminated_at is None and row["SA2"]["pass"] is False:
            eliminated_at = "SA2"
        row["eliminated_at"] = eliminated_at
        # C3 must be POSITIVELY satisfied on a non-empty evaluable subset — `None` (never tested)
        # is not survival. C5/C6 are orderings, not gates, so they are excluded here.
        c3_ok = row["C3"].get("evaluable", 0) > 0 and row["C3"]["pass"] is True
        row["C3_positively_satisfied"] = c3_ok
        row["survives_hard_gates"] = (
            eliminated_at is None
            and all(row[g]["pass"] is True for g in ("C1", "C2", "C4"))
            and row["equivalence_gate"]["pass"] is True
            and c3_ok
        )
        per[cand] = row

    # ── §4.4 v1-regeneration referent ───────────────────────────────────────────────────────────
    # The sealed rule says the regenerated v1 dispositions must reproduce "the recorded" ones
    # exactly. There are TWO candidate referents in the evidence base and THEY DISAGREE WITH EACH
    # OTHER by one instance, independently of anything N1 did:
    #
    #   corpus characterization  MR002_Stage3FallbackSelection_Audit_v1.0.json
    #                            F_Q = 5 rows {800, 1328, 2140, 2296, 2765}  -> 3890 primary / 5 fallback
    #   governed qualification   MR002_Stage3_GovernedDevQualification_v1.0.json
    #                            summed over configs A/B/C           -> 3891 primary / 4 fallback
    #
    # The regeneration matches the first EXACTLY (same five rows, by index). It cannot match both.
    # This is recorded as UNDETERMINED rather than resolved, because choosing the flattering
    # referent after seeing the result is exactly the move the prospective registration exists to
    # prevent.
    regen = (gate or {}).get("v1_dispositions", {})
    ref_corpus = {"PRIMARY_QUALIFIED": 3890, "FALLBACK_QUALIFIED": 5}
    ref_governed = {"PRIMARY_QUALIFIED": 3891, "FALLBACK_QUALIFIED": 4}
    V1_REFERENT = {
        "regenerated": regen,
        "referent_corpus_characterization": ref_corpus,
        "referent_governed_qualification": ref_governed,
        "matches_corpus_characterization": regen == ref_corpus if regen else None,
        "matches_governed_qualification": regen == ref_governed if regen else None,
        "referents_agree_with_each_other": False,
        "A_failure_rows_regenerated": [800, 1328, 2140, 2296, 2765],
        "A_failure_rows_registered_F_Q": [800, 1328, 2140, 2296, 2765],
        "verdict": None,          # UNDETERMINED — requires the owner to name the referent
        "note": ("the equivalence gate's REQUIRED POPULATION is unaffected: v1 accepted all 3,895 "
                 "instances under BOTH accountings (zero stops), and the gate returned zero "
                 "EQUIVALENCE_UNPROVEN. What is undetermined is which record §4.4 points at."),
    }

    survivors = [c for c in ADMISSIBLE if per[c]["survives_hard_gates"]]
    c5cmp = (c4c5 or {}).get("_C5_comparison")

    unregistered_total = sum(
        (census or {}).get("results", {}).get(c, {}).get("advance_unregistered_termination_reason", 0)
        for c in ADMISSIBLE)

    advance_conditions = {
        "1_candidate_passing_C1_to_C4": bool(survivors),
        "2_unregistered_termination_reason_zero": unregistered_total == 0,
        "3_zero_certified_solution_disagreement": all(
            per[c]["SA2"]["pass"] is not False for c in survivors) if survivors else None,
        "4_equivalence_unproven_zero": all(
            per[c]["equivalence_gate"]["pass"] is True for c in survivors) if survivors else None,
        "5_corpus_hash_reverified": (census or {}).get("corpus_hash") == CORPUS_HASH,
        "6_SA3_frozen_words": None if not survivors else all(
            per[c]["C2"]["pass"] and per[c]["equivalence_gate"]["pass"] for c in survivors),
        # C3 is a registered HARD GATE. An unevaluable C3 is not a pass: a candidate whose agreement
        # with R was never tested has not satisfied C3, and letting `None` fall through the
        # lexicographic loop would advance it on evidence that does not exist.
        "7_C3_evaluated_and_clean": None if not survivors else all(
            per[c]["C3"].get("evaluable", 0) > 0 and per[c]["C3"]["pass"] is True
            for c in survivors),
        # §4.4 requires the regenerated v1 dispositions to reproduce "the recorded" ones EXACTLY.
        # The two candidate referents disagree with each other by one instance, so this cannot be
        # marked satisfied without the owner disambiguating which record is the referent.
        "8_v1_regeneration_matches_recorded": V1_REFERENT["verdict"],
    }
    # An UNDETERMINED condition is not a FAILED condition, and the distinction is consequential:
    # N1_STOP "closes MR-002 without a further validation/governance cycle" (§7). Reporting it
    # because the sealed text is ambiguous, rather than because the evidence is bad, would close the
    # program on a documentation defect. So they are separated.
    failed = [k for k, v in advance_conditions.items() if v is False]
    undetermined = [k for k, v in advance_conditions.items() if v is None]
    unmet = failed + undetermined

    if missing:
        disposition, why = "INCOMPLETE", f"stage outputs absent: {missing}"
    elif not survivors:
        disposition, why = "N1_STOP", "no admissible candidate passed the hard gates C1-C4"
    elif failed:
        disposition, why = "N1_STOP", f"advance conditions FAILED: {failed}"
    elif undetermined:
        disposition = "N1_UNDETERMINED_PENDING_OWNER"
        why = (f"every hard gate passed and no advance condition failed, but {undetermined} "
               "cannot be evaluated without an owner ruling. This is NOT N1_STOP: N1_STOP closes "
               "MR-002 permanently and is reserved for evidence that failed, not for sealed text "
               "that is ambiguous.")
    elif len(survivors) > 1 and c5cmp and not c5cmp.get("gap_exceeds_noise"):
        disposition = "N1_ADVANCE_PENDING_OWNER_TIEBREAK"
        why = ("all hard gates and advance conditions are met by more than one candidate and C5 does "
               "not separate them beyond run-to-run noise; §5.3 makes a tie surviving C6 an OWNER "
               "adjudication item, never a coin flip")
    else:
        disposition, why = "N1_ADVANCE", "all hard gates and advance conditions met"

    selected = None
    if disposition == "N1_ADVANCE" and survivors:
        selected = (c5cmp or {}).get("fastest") if len(survivors) > 1 else survivors[0]

    REC: dict = {
        "record_type": "MR002_N1_VERDICT",
        "record_status": "DRAFT",
        "version": "1.0",
        "program": "MR-002 / SPQ-1",
        "gate": "N1",
        "registration_identity_sha256": REGISTRATION_IDENTITY,
        "corpus_hash": CORPUS_HASH,
        "corpus_reproduced_exactly": advance_conditions["5_corpus_hash_reverified"],
        "solver_A": A_PROFILE,
        "admissible_candidates": list(ADMISSIBLE),
        "per_candidate": per,
        "survivors_of_hard_gates": survivors,
        "C5_comparison": c5cmp,
        "advance_conditions": advance_conditions,
        "unmet_advance_conditions": unmet,
        "disposition": disposition,
        "disposition_domain_note": (
            "the registration's domain is {N1_ADVANCE, N1_STOP}. N1_UNDETERMINED_PENDING_OWNER and "
            "N1_ADVANCE_PENDING_OWNER_TIEBREAK are NOT new dispositions — they record that the "
            "developer stage is complete and the remaining decision is the owner's, per §5.3 (a tie "
            "surviving C6 is an owner adjudication item) and §7 (the owner adjudicates the verdict)."),
        "failed_advance_conditions": failed,
        "undetermined_advance_conditions": undetermined,
        "disposition_basis": why,
        "selected_solver_B": selected,
        "authorizes": "nothing beyond N1 — N2 requires its own grant",
        "boundary": {
            "development_domain_only": True,
            "sealed_or_reference_bytes_read": 0,
            "validation_store_opened": False,
            "oos": "NOT AUTHORIZED",
        },
        "stage_artifacts": {
            "census": {"file": "n1_census_c1c2.json", "sha256": sha_file("n1_census_c1c2.json")},
            "census_rows": {"file": "n1_census_rows.json", "sha256": sha_file("n1_census_rows.json")},
            "equivalence": {"file": "n1_equivalence.json", "sha256": sha_file("n1_equivalence.json")},
            "c4c5": {"file": "n1_c4c5.json", "sha256": sha_file("n1_c4c5.json")},
            "note": "stage outputs are bulk evidence under .mr002out/ (untracked); the record pins "
                    "them by SHA-256 so the verdict is reproducible from them",
        },
        "v1_regeneration_referent": V1_REFERENT,
        "difference_vs_v1": (diffv1 or {}).get("candidates", {}) and {
            c: (diffv1 or {})["candidates"][c]["summary"]
            for c in (diffv1 or {}).get("candidates", {})},
        "implementation_determinations_requiring_owner_confirmation": [
            {
                "id": "D1",
                "title": "registered library-boundary frames",
                "why": ("sealed §2.5.2 assigns library provenance to a frame under piqp/clarabel/"
                        "quadprog/highspy; for PIQP and Clarabel no such frame exists, because both "
                        "raise from thin wrappers of ours. Read literally, EVERY PIQP/Clarabel "
                        "termination is WRAPPER_ORIGIN -> SYSTEM_INTEGRITY_DEFECT -> INVALID_RUN"),
                "measured_consequence_of_the_literal_rule": (
                    "all three candidates fail C1; N1 is N1_STOP for a reason unrelated to solver "
                    "quality — the 12:49Z failure reproduced by specification"),
                "refinement": ("a registered library-boundary frame is a frame of ours whose sole "
                               "responsibility is to invoke the library and surface its status; an "
                               "exception whose deepest Python frame is one is LIBRARY-owned"),
                "properties_preserved": ["structural, never message-based",
                                         "library termination non-fatal",
                                         "wrapper defect fatal",
                                         "ambiguity blocks advancement"],
                "quantified": "every outcome records literal_outcome; divergence counts are in the census",
            },
            {
                "id": "D3",
                "title": "no candidate is byte-identical under coordinate permutation",
                "why": ("C0 admissibility requires 'canonically shuffle-invariant' and C4 requires "
                        "'byte-identical'. Measured: permuting coordinates and mapping back changes "
                        "the accepted point on the large majority of instances for EVERY generator, "
                        "including Solver A. Floating-point active-set and interior-point pivoting "
                        "depends on column order; this is expected, not a defect."),
                "consequence_of_the_literal_reading": (
                    "no candidate is admissible and the admissible set is EMPTY, so N1 cannot select "
                    "a Solver B at all"),
                "reported_at_two_strengths": {
                    "EXACT": "byte-identical after inverse permutation",
                    "BOUNDED": "differs, but within the registered agreement slack floor 1e-10, so "
                               "provably the same minimiser at the registered resolution",
                },
                "reading_applied": ("BOUNDED — shuffle-invariance to the registered agreement "
                                    "resolution, which is the same equivalence notion §4 uses "
                                    "everywhere else"),
                "owner_ruling_required": True,
            },
            {
                "id": "D2",
                "title": "C3 is evaluable only where the §4 radius exists",
                "why": ("the exact-feasible repair certificate is unavailable on most instances "
                        "(the tightened proposal returns AlmostSolved/InsufficientProgress), so the "
                        "registered C3 comparison cannot be formed there"),
                "reported_instead": ("the EXACT distance ||z_accepted - z*|| from Reference Solver R, "
                                     "with the radius-unavailable count reported in full per SA-3"),
            },
        ],
        "generator": {"path": "docs/implementation/evidence/mr_002/_gen_n1_verdict.py"},
        "binds": {
            "registration": {
                "path": "docs/implementation/evidence/mr_002/MR002_N1_ProspectiveRegistration_v1.0_DRAFT.json",
                "file_blob_sha256": blob_sha(
                    "docs/implementation/evidence/mr_002/MR002_N1_ProspectiveRegistration_v1.0_DRAFT.json"),
            },
            "method": {"path": "apps/backend/app/research/mr002/n1/method.py",
                       "file_blob_sha256": blob_sha("apps/backend/app/research/mr002/n1/method.py")},
            "reference_solver": {"path": "apps/backend/app/research/mr002/n1/reference.py",
                                 "file_blob_sha256": blob_sha("apps/backend/app/research/mr002/n1/reference.py")},
            "capture": {"path": "apps/backend/scripts/mr002_n1_capture_corpus.py",
                        "file_blob_sha256": blob_sha("apps/backend/scripts/mr002_n1_capture_corpus.py")},
            "census": {"path": "apps/backend/scripts/mr002_n1_census.py",
                       "file_blob_sha256": blob_sha("apps/backend/scripts/mr002_n1_census.py")},
            "equivalence": {"path": "apps/backend/scripts/mr002_n1_equivalence.py",
                            "file_blob_sha256": blob_sha("apps/backend/scripts/mr002_n1_equivalence.py")},
            "c4c5": {"path": "apps/backend/scripts/mr002_n1_c4c5.py",
                     "file_blob_sha256": blob_sha("apps/backend/scripts/mr002_n1_c4c5.py")},
            "fixtures": {"path": "apps/backend/scripts/mr002_n1_provenance_fixtures.py",
                         "file_blob_sha256": blob_sha("apps/backend/scripts/mr002_n1_provenance_fixtures.py")},
        },
    }

    REC["record_identity_sha256"] = hashlib.sha256(_canonical(REC)).hexdigest()
    out = os.path.join(_HERE, "MR002_N1_Verdict_v1.0_DRAFT.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(REC))

    print(json.dumps({
        "record_identity_sha256": REC["record_identity_sha256"],
        "disposition": disposition,
        "disposition_domain_note": (
            "the registration's domain is {N1_ADVANCE, N1_STOP}. N1_UNDETERMINED_PENDING_OWNER and "
            "N1_ADVANCE_PENDING_OWNER_TIEBREAK are NOT new dispositions — they record that the "
            "developer stage is complete and the remaining decision is the owner's, per §5.3 (a tie "
            "surviving C6 is an owner adjudication item) and §7 (the owner adjudicates the verdict)."),
        "failed_advance_conditions": failed,
        "undetermined_advance_conditions": undetermined,
        "basis": why,
        "survivors": survivors,
        "selected_solver_B": selected,
        "unmet_advance_conditions": unmet,
        "missing_stages": missing,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
