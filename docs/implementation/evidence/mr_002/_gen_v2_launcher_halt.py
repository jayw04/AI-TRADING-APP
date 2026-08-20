"""MR-002 — Validation-2 opening HALTED at launcher preflight, plus the sealed launcher/manifest
amendment draft, execution-closure redefinition, and closed-latch rehearsal protocol.

⛔ Validation-2 NOT opened. Latch never touched. Withheld reads 0.
⛔ The amendment here is a DRAFT. It is NOT applied and NOT deployed.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
LAUNCHER = "apps/backend/scripts/mr002_phase3c_validation_run.py"
V2 = [("actions", "oos/actions.parquet", "F6m6am6cBahBd95p41C1.aAVmYd8GuNG",
       "a08c0ed6ba6c6609e67c501a938e0245277e11c82f3d7242e7e2683790acb100"),
      ("anchors", "oos/anchors.parquet", "RsJZG3TkDXvNPERJhZVanJ.Vqg8_dulw",
       "5095149d39d26c7af19de3814a7178e93bf3cc3ab87f92512991a81e64013dc9"),
      ("etf_prices", "oos/etf_prices.parquet", "Z3OsUeuucMYIl2v9JDoVNDx1nw.0avDj",
       "f53f448312f94820d76aad80f378a53ea2b9104654cbb7c69bb82363b2a5da15"),
      ("prices", "oos/prices.parquet", "1ope9PR._oR303.EbZNGPVlIJRy.SZbA",
       "0f45ddc58170bd1131b9820576080eae861dff65b716bc3f03d08fb284f29e9a"),
      ("sic_observations", "oos/sic_observations.parquet", "DPhtWW3Pca3TKtSa1LOnGKA.yrZ98EIt",
       "176a84bc155b5ec8c24444e091b19a78b97c0d31c0da606f22eca44ace7e12cf"),
      ("universe", "oos/universe.parquet", "0gaqJ9TuECc3U_zar99sqls2UHRDnkkY",
       "4c1a2b2e876f7ffdd1f651e5c99079d5fe045e74003af556c3c8b3273d746e0d")]


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob(p: str) -> str:
    r = subprocess.run(["git", "-C", REPO, "show", "HEAD:" + p], capture_output=True)
    return hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else None


REC = {
    "record_type": "MR002_Validation2_LauncherHalt_and_AmendmentDraft",
    "version": "1.0", "date": "2026-08-20",
    "disposition": "OPENING_NOT_BEGUN — LAUNCHER_BINDS_THE_WRONG_POPULATION",
    "amendment_status": "DRAFT PROPOSAL — NOT APPLIED, NOT DEPLOYED",
    "validation_2_opened": False, "opening_consumed": False,
    "latch": "8 / CLOSED — never touched", "withheld_reads": 0, "host": "stopped",
    "fresh_opening_authorization": "SUSPENDED by owner ruling on this finding",

    "verification_pointer_for_the_owner": {
        "note": "the owner could not locate the launcher via the repository search index. It IS "
                "tracked. These coordinates allow independent byte verification.",
        "path": LAUNCHER, "tracked_in_git": True, "gitignored": False,
        "commit": "ff4b79cada7c90bae229c3f5770ab0d74be7557d",
        "blob_sha256": "835325a9a4cbf8cd693a42f2c4051a5f788e660877451b3c0b514f93fd239627",
        "first_introduced_in": "56dc2cc outcome(mr-002): INTEGRITY_FAILURE recorded",
    },

    "FINDING_1_launcher_binds_validation_1_and_refuses_validation_2": {
        "quoted_from_the_launcher": {
            "OOS_PREFIX": "oos/",
            "SEALED": {t: {"key": k, "version_id": v} for t, k, v, _ in [
                ("actions", "validation/actions.parquet", "wJ6QFkebGAidGzoWO.qzUMYjy.b6zLrx", ""),
                ("anchors", "validation/anchors.parquet", "7Br5aFGWFabpIJmPgwUBQRgdhQwc2GIK", ""),
                ("etf_prices", "validation/etf_prices.parquet",
                 ".mZyHPHgamUNlHpdePGQZq.djUapjrpo", ""),
                ("prices", "validation/prices.parquet", "eC8XZGBPXa6vPDW_WKPvwV8HtF05_tty", ""),
                ("sic_observations", "validation/sic_observations.parquet",
                 "OkvwAKSX8W8W3HJiBoxZ9KC4ON6Vgj5t", ""),
                ("universe", "validation/universe.parquet",
                 "8Le8rLdT2wvdSenjEQdPaUAgdmSzx3ZO", "")]},
            "guard": "if key.startswith(OOS_PREFIX): raise IntegrityFailure(OOS_ACCESS_ATTEMPT)"},
        "two_disqualifying_facts": [
            "the six objects it would read are the CONSUMED Validation-1 objects under "
            "validation/*, at the old VersionIds - not partition 3b3910d0...",
            "it RAISES OOS_ACCESS_ATTEMPT on any oos/ key, and all six Validation-2 objects live "
            "under oos/. The launcher would refuse the very population it is now meant to read."],
        "would_it_have_consumed_the_opening": "NO. The refusal occurs during object-set "
            "construction, BEFORE any reader is created or credential issued. It would have been "
            "a pre-read abort - but it would have burned a latch cycle and produced no verdict.",
        "defect_class": "identical to the Amendment-C finding: governance moved the data's role "
            "and the code kept enforcing the old one. One file further out than I had checked.",
    },

    "FINDING_2_the_manifest_is_unversioned_and_my_cutover_removed_it": {
        "what_the_launcher_consumes": "--manifest, default "
            "/opt/mr002/phase3c_src/docs_upload_manifest.json, read by _object_hashes(). It "
            "supplies the VersionId and SHA-256 used to build every PinnedObject and is compared "
            "against SEALED - so it can independently select partition and version.",
        "is_it_tracked_in_git": False,
        "consequence_a": "the manifest that supplies every object identity to the launcher has "
            "NEVER been version-controlled or hash-bound. Same class as the ADR-0051 checkers: "
            "the thing doing the binding was itself unbound.",
        "consequence_b": "the archive I deployed contains ONLY apps/ at top level, while the "
            "manifest sits at the ROOT of phase3c_src. My cutover therefore REMOVED it from the "
            "live tree.",
        "is_anything_lost": "NO. The rollback tree /opt/mr002/phase3c_src_pre_amendmentC is "
            "intact and still holds the file; it is recoverable. But the live tree is currently "
            "missing an execution-critical input, which is itself a reason the opening must not "
            "proceed.",
        "how_I_found_it": "while establishing the manifest's provenance for this record - not by "
            "a gate. My execution-closure definition would not have caught it either.",
    },

    "WHY_MY_NINTH_GATE_MISSED_BOTH": {
        "what_it_bound": "20 execution-critical files, all library modules",
        "what_it_omitted": "the LAUNCHER, which carries the object map, the VersionIds, the "
            "partition refusal and the authority strings; and the MANIFEST, which supplies every "
            "object identity",
        "my_error": "I treated the library as the execution surface and the launcher as mere "
            "orchestration. The launcher is the most execution-critical file there is: it chooses "
            "WHAT IS READ.",
        "consequence_for_the_record": "MR002_Validation2_ReadinessQualification_v2.0 "
            "(3e1e6e29...) is INCOMPLETE for opening purposes and must be superseded once this "
            "finding is sealed. It is preserved unmodified.",
    },
}


REC["prospective_launcher_and_manifest_amendment"] = {
    "framing": "a LAUNCHER + MANIFEST GOVERNANCE AMENDMENT, not a small code fix. It changes what "
               "the one-shot opening reads and under whose authority the terminal record speaks.",
    "status": "DRAFT — NOT APPLIED. Deployment requires the sealed identity and exact diff to be "
              "reviewed first.",
    "binds_together": {
        "launcher_git_blob_identity": "to be re-derived after the edit; the CURRENT value is "
            "835325a9a4cbf8cd693a42f2c4051a5f788e660877451b3c0b514f93fd239627",
        "manifest_identity": "the manifest MUST become a tracked, hash-bound artifact. An "
            "untracked host file cannot supply object identities to a one-shot opening.",
        "SEALED_becomes": [{"table": t, "key": k, "version_id": v, "sha256": s} for t, k, v, s in V2],
        "explicit_refusals": [
            "any key under validation/ — the CONSUMED Validation-1 partition, permanently "
            "inadmissible. This REPLACES the current oos/ refusal; the polarity inverts.",
            "any oos/ key OR VersionId outside the registered six — so a manifest carrying a "
            "seventh object, or a different version of a registered key, fails closed"],
        "authority_strings_corrected": {
            "current_and_WRONG": {
                "authorization": "MR002_Phase3C_ExecutionAuthorization_v2.0 / c53edf89",
                "countersignature": "MR002_Phase3C_ExecutionCountersignature_v2.0 / 410627f2",
                "package": "MR002_Phase3C_ValidationExecutionPackage_v2.2 / pending"},
            "why_it_matters": "the terminal record the launcher emits would SELF-DESCRIBE under "
                "SUPERSEDED Phase-3C v2.0 authority. A one-shot verdict naming the wrong "
                "authority is a governance defect even if every number in it is right.",
            "must_become": "the Cycle-2C / Validation-2 chain: prospective registration "
                "93ee4688..., partition 3b3910d0..., and the governing readiness identity in "
                "force at execution time"},
        "preserved_unchanged": [
            "--reader fixture affordance",
            "--window development affordance",
            "the WINDOW_MISUSE interlock forbidding the development window with the real S3 "
            "reader",
            "the durable EvidenceJournal opened BEFORE any read and fsynced per object",
            "economic thresholds, fold geometry, solver routing and gate semantics — UNTOUCHED"],
    },
}

REC["execution_critical_closure_redefined"] = {
    "old": "an enumerated list of 20 library files",
    "why_that_was_wrong": "an enumeration invites exactly this failure - it is complete until the "
        "relevant file is one step outside it. Twice now the omitted file was the one that "
        "decided behaviour.",
    "new_definition": "the execution CLOSURE: every artifact whose value can select, or cause to "
        "be selected, any of - partition, object key, VersionId, window, fold geometry, "
        "authority/countersignature identity, solver or solver routing, gate threshold, or "
        "terminal disposition.",
    "closure_members_identified_so_far": [
        "the launcher mr002_phase3c_validation_run.py",
        "the manifest it consumes (currently untracked - must be bound)",
        "the 20 previously bound library modules",
        "phase3c constants and folds (bound via Amendment C)",
        "the runtime image, typed identities",
        "the dependency bundle mounted at /opt/mr002/deps",
    ],
    "method_rather_than_list": "the closure must be DERIVED - by tracing what the launcher "
        "imports and reads at runtime - and then bound, rather than hand-enumerated. A list is a "
        "snapshot; a closure is a rule.",
}

REC["closed_latch_rehearsal_protocol"] = {
    "status": "MANDATORY pre-opening gate once the amendment is deployed",
    "invocation": "--reader fixture --window development, with the latch 8/CLOSED throughout",
    "why_it_is_safe": "no Validation-2 credential is obtainable while the latch is closed, the "
        "fixture reader touches no sealed object, and the development window is fixture-only by "
        "the WINDOW_MISUSE interlock. Nothing withheld can be reached and nothing is consumed.",
    "why_it_is_necessary": "I verified the library layer and the import surface, but the "
        "ORCHESTRATION has never been exercised end to end. Both halts came from the "
        "orchestration, not the library.",
    "must_prove_end_to_end": [
        "the launcher loads the AMENDED manifest",
        "the fixture reader is selected",
        "the development window is accepted ONLY in fixture mode",
        "real-reader + development-window still fails WINDOW_MISUSE",
        "object-set construction uses the manifest abstraction as intended",
        "journal creation works and is fsynced before any read",
        "materialization completes",
        "replay completes",
        "five-fold and gate orchestration completes",
        "a terminal record is emitted on the exit path",
        "the terminal record names the CURRENT governing authority, not Phase-3C v2.0",
        "no fallback path silently reaches consumed Validation-1 identifiers",
    ],
    "negative_synthetic_checks_required": [
        "a manifest containing a validation/* key must FAIL CLOSED before reader acquisition",
        "a manifest containing a seventh or unregistered oos/* key must FAIL CLOSED before "
        "reader acquisition",
        "a manifest carrying a registered key at an UNREGISTERED VersionId must FAIL CLOSED",
    ],
}

REC["tenth_gate"] = {
    "name": "launcher_and_manifest_bind_the_registered_validation2_population_and_current_authority",
    "requires_BOTH": [
        "static identity/content verification of launcher and manifest",
        "a SUCCESSFUL closed-latch fixture rehearsal of the ACTUAL launcher"],
    "why_both": "hashing the launcher proves what it says; rehearsing it proves what it does. "
        "This finding is precisely a case where the file was intact and its behaviour was wrong.",
    "supersedes_for_opening_purposes": "MR002_Validation2_ReadinessQualification_v2.0 "
        "(3e1e6e292a02a8b5102842c2fc99baa7d00e0218b0e87679fd959cd5167a3db4), preserved unmodified",
}

REC["lineage"] = [
    "daa1f7ca... READY, eight gates - never asked whether the HOST carried the source",
    "c2f4d8b2... opening NEVER BEGUN - host carried pre-Amendment-C source",
    "ed2ffcf4... deployment preparation FAILED - CRLF archive, cutover not performed",
    "3e1e6e29... READY, nine gates - bound the library surface but not the launcher or manifest",
    "THIS RECORD  opening NOT BEGUN - launcher binds Validation-1 and refuses Validation-2; "
    "manifest unversioned and removed from the live tree by the cutover",
]
REC["what_was_NOT_done"] = ["the latch was NOT released", "no reader was assumed",
                           "no Validation-2 object was read", "no launcher edit was applied",
                           "no manifest was restored or modified on the host"]
REC["authorizes"] = "NOTHING. Deployment of this amendment requires a separate owner ruling after "
REC["authorizes"] += "review of the sealed identity and exact diff."
REC["boundary"] = {"validation_2_opening": "NOT AUTHORIZED", "latch": "8 / CLOSED",
                   "withheld_reads": 0, "opening_consumed": False,
                   "amendment_applied": False, "host": "stopped"}


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_LauncherHalt_and_AmendmentDraft_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 LAUNCHER HALT + AMENDMENT DRAFT")
    print(f"  identity    {ident}")
    print(f"  disposition {REC['disposition']}")
    print(f"  amendment   {REC['amendment_status']}")
    print(f"  launcher    {REC['verification_pointer_for_the_owner']['blob_sha256']}")
    print(f"  wrote       {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
