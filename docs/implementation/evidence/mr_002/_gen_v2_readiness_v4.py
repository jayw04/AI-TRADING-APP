"""Validation-2 readiness qualification v4.0 — FINAL, after the authorized dependency mount.

Supersedes v3.0, which reported NOT READY on the dependency blocker. That blocker is now closed
and re-qualified end to end with the mount in force.

This record does NOT authorize the opening. It reports that readiness holds.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_ReadinessQualification",
    "version": "4.0",
    "date": "2026-08-20",
    "supersedes": "MR002_Validation2_ReadinessQualification_v3.0 "
                  "(775a8b37020fd92bf9b5acfa6d0c37a64224cbf4322fde0e4c9c313f65608235), "
                  "preserved unmodified — it reported NOT READY on the dependency blocker",
    "what_changed": "the dependency blocker is closed. Everything else is re-verified, not "
                    "carried forward on faith.",
}

# ── the bindings the owner required ──────────────────────────────────────────────────────────
REC["binds"] = {
    "dependency_amendment":
        "12877b32704da2bf4e13cd60599b194789a28d7da4ff9b97584b140ec0f3f86d",
    "bundle_content_identity":
        "26e230493f218aba332b0888f2751def9f143ee136f68a86bdb91aaa03110dc1",
    "mount_source": "/opt/mr002/deps_v12",
    "container_target": "/opt/mr002/deps",
    "execution_package":
        "e22c4d4f9e1007340d7c30385af0ee6a95c0c0be8a1a8cd8b4a4e8140c832d23",
    "deployment_artifact":
        "aab2e7a56acf8dcc15e12e5345110c92e0ab43f04cbafe2e5380c359738e4b93",
    "deployed_live_aggregate":
        "6841756f8026932370531fde49de5dfccda1c2cee964174f1eec1901e3660ae9",
    "execution_closure":
        "3c32bda64dd1cd6efe306bcf7e69e56a78c53b3bd58076d7735ddbe2d516df3b",
    "archive_sha256":
        "c3d3a7e026f65dcf611826f3d9746cee6ba46cd0eb66d8bfa32563bce80cc4df",
    "source_commit": "740a1420ad55c2c2cb74c681fd49b1da2f3c11b2",
    "host": "i-00c1034f7026db45e",
    "image": "mr002-research:v1.4",
    "image_config_digest":
        "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6",
    "tenth_gate": True,
    "dependency_runtime_gate": True,
}

# ── the authoritative invocation ─────────────────────────────────────────────────────────────
REC["bound_runtime_invocation"] = {
    "mount_flag": "-v /opt/mr002/deps_v12:/opt/mr002/deps:ro",
    "pythonpath": "/work/apps/backend:/opt/mr002/deps",
    "source_tree_mount": "-v /opt/mr002/phase3c_src:/work:ro",
    "frozen_thread_env": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                          "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                          "OPENBLAS_CORETYPE": "HASWELL"},
    "what_apply_meant_here": "there is NO persistent launcher, systemd unit or cron entry on the "
        "host that carries the mount — the invocation is constructed at run time. So the "
        "amendment is applied by BINDING the invocation here and using it, which is exactly what "
        "the entire qualification below ran under. No host filesystem was mutated, as required.",
    "host_filesystem_mutated": False,
    "opt_mr002_deps_left_untouched": "the defective bundle remains in place, unmodified, as "
                                     "rollback and evidence",
}

# ── required checks ──────────────────────────────────────────────────────────────────────────
REC["required_checks"] = {
    "mounted bundle identity == 26e23049...": "PASS — computed INSIDE the container at the "
        "container path /opt/mr002/deps: "
        "26e230493f218aba332b0888f2751def9f143ee136f68a86bdb91aaa03110dc1, 2954 files",
    "boto3 / botocore / dateutil / six import": "PASS — 1.43.70 / 1.43.70 / 2.9.0.post0 / "
        "1.17.0, every one resolved FROM THE MOUNT",
    "11 governed module imports resolve": "PASS — 11/11",
    "image config digest unchanged": "PASS — sha256:770553aeae6c...",
    "numpy/scipy/quadprog/piqp/duckdb still resolve from the IMAGE": "PASS — numpy 2.2.6, "
        "scipy 1.18.0, quadprog, piqp 0.6.3, duckdb 1.1.3, all IMAGE",
    "pyarrow resolves from the mount and is byte-identical to the qualified copy": "PASS — "
        "DEPS-MOUNT, 758 files, tree identity "
        "54d0e4dbdb96c53c85178fb38fb355b2ec59910aa1bde96ee03a7ed6b4b3aad7 under the candidate, "
        "and the SAME value computed against the currently bound bundle",
    "deployed-tree rehearsal byte-identical to the qualified report": "PASS — report sha256 "
        "f2635353299fd677f6ff37748b823f17648018a5045b2e4f5187180218cc9b9b, exactly the qualified "
        "value; behavioral digest 1e77f33c52dd3d6e8fbddd1aab192f32ee57e084a58cbc5f7756506a94058311",
    "20/20 launcher invariants": "PASS",
    "10/10 negative cases": "PASS — all fail closed, reader_acquisition_attempted=False",
    "fold/gate rehearsal": "PASS",
    "Stage-3 census A 59 / B 60 / C 55, QUADPROG_SQRT / PRIMARY_QUALIFIED, 0 fallback/stops":
        "PASS — exactly those values",
    "production pre-credential boundary probe reaches its sentinel with 0 read events": "PASS — "
        "reached_credential_boundary True, READ EVENTS 0, journal is run_opened then terminal "
        "FAILED on the intentional sentinel",
    "latch remains 8/CLOSED": "PASS",
    "successful Validation-2 reads remain 0": "PASS",
}

REC["re_verified_not_carried_forward"] = {
    "live_tree_aggregate": "6841756f... — unchanged after all qualification activity",
    "25_member_closure_on_the_live_tree": "25/25 matched, 0 mismatched, 0 governed CRLF",
    "reader_AssumeRole_events_in_window": 0,
    "oos_read_attempts_in_window": "6, all AccessDenied, 0 successful",
}

# ── findings ─────────────────────────────────────────────────────────────────────────────────
REC["findings_recorded_during_this_qualification"] = {
    "1_silent_empty_mount_near_miss": {
        "what": "a first attempt passed the docker flags through a shell variable. The mount "
                "silently resolved to an EMPTY directory inside the container.",
        "why_it_is_worth_recording": "the run still reported `governed_modules_resolved: 11/11`, "
                                     "because the governed modules come from the SOURCE tree, "
                                     "not the bundle. A qualification that checked only module "
                                     "imports would have passed with NO dependency bundle "
                                     "mounted at all.",
        "what_caught_it": "the mounted-bundle content identity, which came back as the SHA-256 "
                          "of the empty string with 0 files.",
        "consequence": "the bundle identity check is not ceremony — it is the only check in the "
                       "set that can detect a mount that did not happen. It is retained as a "
                       "mandatory pre-opening assertion.",
        "resolution": "flags passed inline; identity then matched 26e23049... exactly.",
    },
    "2_orphan_preflight_carries_a_THIRD_bundle": {
        "what": "/opt/mr002/runtime_custody/preflight.py hard-codes "
                "DEPS = \"/opt/mr002/deps_v11_clean\" and mounts it at /opt/mr002/deps using the "
                "same -v pattern.",
        "why_it_matters": "deps_v11_clean is ALSO defective — it lacks dateutil, exactly like "
                          "/opt/mr002/deps. So the host carries three candidate bundles, two of "
                          "them broken, and a stale script that would silently select a broken "
                          "one.",
        "status": "NOT MODIFIED. It is an unreferenced orphan from 2026-08-18; nothing else on "
                  "the host references it. Flagged rather than touched.",
        "why_this_reinforces_the_amendment": "it is the concrete argument for binding the bundle "
                                             "by CONTENT IDENTITY rather than by directory name. "
                                             "A path can drift silently; an identity cannot.",
    },
}

REC["verdict"] = {
    "dependency_blocker": "CLOSED",
    "tenth_gate": "TRUE",
    "dependency_runtime_gate": "TRUE",
    "readiness": "READY",
    "scope_of_that_word": "READY means every registered pre-opening gate passes under the bound "
                          "runtime. It is NOT an authorization and NOT a prediction about the "
                          "economics, which remain unknown by construction until the opening.",
    "residual_limitations_unchanged_from_v2_0": [
        "nothing rehearses the S3 reader, STS acquisition or latch-release propagation — those "
        "are reachable only with the latch open. The boundary probe now proves the path reaches "
        "the credential call, which is as close as it is possible to get without releasing it.",
        "the fold/gate functions are proven on SYNTHETIC inputs; their behaviour on the real "
        "Validation-2 series is unobservable before the opening, by design.",
    ],
}
REC["authorizes"] = ("NOTHING. The opening requires a fresh owner ruling and a latch release, "
                    "neither of which is granted by this record.")
REC["what_was_NOT_done"] = [
    "the latch was NOT released (still 8/CLOSED)",
    "no reader was assumed; no STS call was made",
    "no Validation-2 object was read at any version",
    "/opt/mr002/deps was NOT altered, renamed, replaced or repointed",
    "no host filesystem path was mutated",
    "no source, closure member, threshold, fold, solver or image was changed",
]
REC["boundary"] = {
    "latch": "8 / CLOSED", "withheld_reads": 0, "successful_validation2_reads": 0,
    "opening_consumed": False, "validation_2_population": "UNCONSUMED",
    "validation_2_opening": "NOT AUTHORIZED",
    "host": "i-00c1034f7026db45e — qualified, then stopped",
}
REC["record_status"] = "SEALED"


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ReadinessQualification_v4.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 VALIDATION-2 READINESS QUALIFICATION v4.0 — FINAL")
    print(f"  identity              {ident}")
    print(f"  dependency blocker    {REC['verdict']['dependency_blocker']}")
    print(f"  tenth gate            {REC['verdict']['tenth_gate']}")
    print(f"  dependency gate       {REC['verdict']['dependency_runtime_gate']}")
    print(f"  bundle identity       {REC['binds']['bundle_content_identity']}")
    print(f"  live aggregate        {REC['binds']['deployed_live_aggregate']}")
    print(f"  latch                 {REC['boundary']['latch']}")
    print(f"  V2 reads              {REC['boundary']['successful_validation2_reads']}")
    print(f"  READINESS             {REC['verdict']['readiness']}")
    print(f"  opening               {REC['boundary']['validation_2_opening']}")
    print(f"  wrote                 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
