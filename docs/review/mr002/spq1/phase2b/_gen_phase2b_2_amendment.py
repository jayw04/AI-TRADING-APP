"""SPQ-1 Phase 2B run-spec amendment v1.1 — request-identity non-injective collision rule.

Narrow, controlled amendment (owner-adjudicated). It changes ONLY the treatment of an already-detected
non-injective identity mapping: when >1 distinct request symbol resolves provisionally to the same
(session, permanent_security_id), all claimants terminate INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS
(no winner, unresolved terminal key; claimed id retained only as diagnostics).

It does NOT change universe membership, calendar, crosswalk, lineage data, permaticker values, signal
mathematics, PIT cutoff, sector resolution, eligibility rules, or shard boundaries. The frozen
phase2b_orchestration_code_identity (bb029a96...) is UNCHANGED; detection is runner-side. Produces:
RunSpecification_v1.1, DevelopmentRunManifest_v1.1, and the dedicated CollisionRuleAmendment artifact.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[5])
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "apps", "backend"))

from app.research.mr002.spq1.identities import canonical_sha256  # noqa: E402

RS_BEFORE = "747875e313d11c96e8b203b86db32b5c8032b4857e13f8fa5f2d237d829a758e"
FROZEN_ORCHESTRATION_IDENTITY = "bb029a96bb0c9e31600bd0b7ab068c31f70bbc7ac23afce0a3ffe0cb4412845b"


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def dump(obj, subdir, name):  # noqa: ANN001
    d = os.path.join(OUT, subdir)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return sha_file(p)


def load(subdir, name):  # noqa: ANN001
    return json.load(open(os.path.join(OUT, subdir, name)))


# --- the governed collision rule (bound in the run spec + amendment) ---
COLLISION_RULE = {
    "rule_id": "MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1",
    "predicate": "for a decision session t, if two or more DISTINCT request symbols resolve provisionally "
        "(via the registered PIT lineage resolver ctx.lineage.resolve_permanent_id at session ordinal t) "
        "to the SAME permanent_security_id, that (session, permanent_security_id) is a collision group and "
        "the request->permanent-security mapping is non-injective at t.",
    "terminal_disposition": "INTEGRITY_STOP",
    "terminal_code": "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
    "all_claimants_stop": "every request member of a collision group terminates as the integrity stop; no "
        "claimant is selected as a winner and no signal decision is produced for any member.",
    "no_winner_prohibition": "no tie-break may be applied (base-ticker naming, universe permaticker, row "
        "order, longer trading history, non-suffixed symbol, surviving ticker, or later corporate-action "
        "knowledge). Any such tie-break would introduce an ungoverned identity-selection rule / look-ahead.",
    "terminal_key_treatment": "the provisional permanent_security_id is NOT accepted; the terminal record "
        "carries permanent_security_id = null/empty and terminal key (session, 'UNRESOLVED:<request_symbol>'); "
        "the claimed id is retained ONLY as diagnostic evidence in the CollisionCensus. This preserves both "
        "one-terminal-disposition-per-unit and duplicate-resolved-permanent-security/session-keys = 0.",
    "detection_stage": "runner-side governed pre-production step, AFTER provisional PIT identity resolution "
        "and BEFORE sector lookup, earnings lookup, signal production, record-identity generation, and shard "
        "publication; the frozen run_unit is called ONLY for non-colliding requests.",
    "governed_sequence": ["enumerate request units for the shard",
        "resolve provisional permanent_security_id at each session (same registered resolver + ordinal)",
        "group successful resolutions by (session, provisional permanent_security_id)",
        "mark groups with cardinality > 1 as collisions",
        "emit one unresolved INTEGRITY_STOP for each request in the group",
        "run normal frozen production only for non-colliding requests",
        "reconcile by request key and accepted resolved terminal key"],
    "provisional_resolver_control": "the runner's provisional resolution MUST be the same registered "
        "lineage resolver (adapters.identity_adapter.load_identity_registry.resolve_permanent_id) and the "
        "same session ordinal run_unit uses; the runner implements NO alternative identity logic, caching, "
        "fallback, or tie-break.",
    "cardinality_gt_2": "a collision cardinality > 2 uses the same all-claimants-stop rule but MUST be "
        "separately surfaced (maximum_collision_cardinality in the CollisionCensus).",
    "distinct_from_single_request_ambiguity": "a single request whose lineage resolution independently "
        "fails (SECURITY_IDENTITY_AMBIGUOUS from normal PIT resolution) is NOT a collision; it flows through "
        "frozen run_unit. The CollisionCensus counts ONLY non-injective cross-request collisions; the "
        "RefusalCensus splits SECURITY_IDENTITY_AMBIGUOUS by cause.",
    "collision_census_artifact": "MR002_SPQ1_Phase2B_2B2_CollisionCensus_v1.0.json",
    "collision_census_schema": {
        "per_request_row": ["decision_session", "session_date", "request_symbol", "request_key",
            "collision_group_id", "claimed_permanent_security_id", "colliding_request_symbols",
            "collision_cardinality", "identity_source", "collision_rule_id", "terminal_disposition",
            "terminal_code", "terminal_key", "governing_universe_month"],
        "group_row": ["collision_group_id", "decision_session", "session_date",
            "governing_universe_month", "claimed_permanent_security_id", "colliding_request_symbols",
            "collision_cardinality", "group_disposition_rule"],
        "reconciliation": "affected_request_count == collision-caused SECURITY_IDENTITY_AMBIGUOUS records"},
    "known_development_window_collisions": {
        "status": "registered evidence, NOT a hard expected-count gate; additional groups found in the full "
            "run are handled by the same rule and disclosed + reconciled (a new group is not an automatic "
            "stop after this amendment).",
        "collision_group_count": 35, "collision_request_unit_count": 70,
        "distinct_collision_symbol_sets": 3, "maximum_collision_cardinality": 2,
        "source_identities_for_census": {
            "research_db_sha256": "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a",
            "universe_content_sha256": "f638dfe3d0a2aa9b22a572d8e408faa863355bf8fe4550e624b6cfe660eedf39",
            "crosswalk_via": "research.crosswalk (ticker,cik,effective_from,effective_to)",
            "lineage_resolver": "adapters.identity_adapter.load_identity_registry.resolve_permanent_id"},
        "registered_pairs": {
            "AGN/AGN1": {"claimed_permanent_security_id": "PSEC-198103",
                "governing_months": ["2015-03-01"], "session_range": ["2015-03-16", "2015-03-31"],
                "sessions": 12, "corporate_action": "Allergan / Actavis ticker reassignment"},
            "CB/CB1": {"claimed_permanent_security_id": "PSEC-199850",
                "governing_months": ["2016-01-01"], "session_range": ["2016-01-14", "2016-01-15"],
                "sessions": 2, "corporate_action": "ACE / Chubb merger ticker reassignment"},
            "DD/DD1": {"claimed_permanent_security_id": "PSEC-199769",
                "governing_months": ["2017-08-01", "2017-09-01"], "session_range": ["2017-08-31", "2017-09-29"],
                "sessions": 21, "corporate_action": "DowDuPont merger ticker reassignment"}}},
    "scope_unchanged": ["universe membership", "calendar", "crosswalk contents", "lineage data",
        "permaticker values", "signal mathematics", "PIT cutoff", "sector resolution", "eligibility rules",
        "shard boundaries", "phase2b_orchestration_code_identity (bb029a96...)"],
    "amends_run_spec_sha256_before": RS_BEFORE,
}


def run():  # noqa: ANN201
    runner_identity = sha_file(os.path.join(OUT, "_gen_phase2b_2_run.py"))
    collision_module_identity = sha_file(os.path.join(OUT, "collision_rule.py"))

    # --- DevelopmentRunManifest v1.1 (collision rule added to policies; no runner id -> no run-spec cycle) ---
    drm = copy.deepcopy(load("manifests", "MR002_SPQ1_Phase2B_DevelopmentRunManifest_v1.0.json"))
    drm["version"] = "1.1"
    drm["policies"]["request_identity_collision_rule"] = {
        k: COLLISION_RULE[k] for k in ("rule_id", "predicate", "terminal_disposition", "terminal_code",
                                       "all_claimants_stop", "terminal_key_treatment", "detection_stage")}
    drm["amendment_v1_1"] = ("added the request-identity non-injective collision rule to run policies; "
                             "no input identity / calendar / universe / code identity changed.")
    drm11 = dump(drm, "manifests", "MR002_SPQ1_Phase2B_DevelopmentRunManifest_v1.1.json")

    # --- RunSpecification v1.1 (adds the collision rule; DRM ref -> v1.1; IIM ref unchanged) ---
    rs = copy.deepcopy(load("run_spec", "MR002_SPQ1_Phase2B_RunSpecification_v1.0.json"))
    rs["version"] = "1.1"
    rs["request_identity_collision_rule"] = COLLISION_RULE
    rs["amendment_v1_1"] = {
        "reason": "controlled amendment defining the terminal treatment of an already-detected "
            "non-injective request->permanent-security mapping (surfaced by the SPQ-1 Phase 2B-2 census). "
            "Runner-side detection; frozen phase2b modules unchanged.",
        "amends_run_spec_sha256_before": RS_BEFORE,
        "phase2b_orchestration_code_identity_unchanged": FROZEN_ORCHESTRATION_IDENTITY,
        "scope_unchanged": COLLISION_RULE["scope_unchanged"]}
    rs["bound_identities"] = dict(rs["bound_identities"])
    rs["bound_identities"]["development_run_manifest"] = drm11
    rs["run_specification_sha256"] = None
    rs_after = canonical_sha256(rs)
    rs["run_specification_sha256"] = rs_after
    rs11_file = dump(rs, "run_spec", "MR002_SPQ1_Phase2B_RunSpecification_v1.1.json")

    # --- dedicated amendment artifact (leaf: binds runner + collision identities; no cycle) ---
    amendment = {
        "record_type": "MR002_SPQ1_Phase2B_2B2_CollisionRuleAmendment", "version": "1.1",
        "run_id": rs["run_id"], "stage": "SPQ-1 Phase 2B run-spec amendment (owner-adjudicated)",
        "rule": COLLISION_RULE,
        "run_spec_sha256_before": RS_BEFORE, "run_spec_sha256_after": rs_after,
        "run_specification_v1_1_file_sha256": rs11_file,
        "development_run_manifest_v1_0_sha256": load("run_spec",
            "MR002_SPQ1_Phase2B_RunSpecification_v1.0.json")["bound_identities"]["development_run_manifest"],
        "development_run_manifest_v1_1_sha256": drm11,
        "input_identity_manifest_v1_0_sha256": load("run_spec",
            "MR002_SPQ1_Phase2B_RunSpecification_v1.0.json")["bound_identities"]["input_identity_manifest"],
        "input_identity_manifest_unchanged": True,
        "governed_code_identities": {
            "phase2b_orchestration_code_identity_frozen": FROZEN_ORCHESTRATION_IDENTITY,
            "full_run_runner_identity": runner_identity,
            "collision_rule_module_identity": collision_module_identity},
        "runner_controls": [
            "the provisional-resolution call is the SAME registered lineage resolver + session ordinal "
            "run_unit uses (adapters.identity_adapter.load_identity_registry.resolve_permanent_id)",
            "the runner implements NO alternative identity logic, caching, fallback, or tie-break",
            "detection precedes sector lookup, earnings lookup, producer, record-identity, and publication"],
        "regression_tests": "apps/backend/tests/research/spq1/test_spq1_phase2b_2_collision.py "
            "(11 governed scenarios + real-data fixtures AGN/AGN1, CB/CB1, DD/DD1)",
        "boundary": "amendment only; Phase 2B-2 relaunch is separately authorized by the owner after "
            "amendment adjudication; performance / downstream / validation / OOS remain NOT authorized.",
    }
    amd = dump(amendment, "amendment", "MR002_SPQ1_Phase2B_2B2_CollisionRuleAmendment_v1.1.json")

    return {"run_spec_sha256_after": rs_after, "RunSpecification_v1.1_file": rs11_file,
            "DevelopmentRunManifest_v1.1": drm11, "CollisionRuleAmendment": amd,
            "runner_identity": runner_identity, "collision_module_identity": collision_module_identity}


if __name__ == "__main__":
    out = run()
    for k, v in out.items():
        print(f"{k}: {v}")
