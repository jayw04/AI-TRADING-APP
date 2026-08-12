"""WP-F — the closed grant-readiness verification run (C1-C10 + C-R7 + K4).

Authorized by the owner on 2026-08-11 for BUILD plus ONE closed execution run,
after register v1.3 was emitted. Not authorized: any trust-policy edit,
credential release, P12, change to ``validation_authorization``/``_rev``, any
validation or OOS read, any live DENY probe, any evaluator or runtime change,
host replacement or P10 regeneration, or Phase 3B/3C execution.

===============================================================================
WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
===============================================================================

This asks one question: is the program grant-READY? It never grants anything.
A PASS here is an input to a future D3/P12 owner decision and nothing else.
``validation_authorization`` is CAS-guarded state this module only ever reads.

The conditions are the owner's, not this module's. C1-C10 are verbatim from the
2026-07-22 adjudication; C-R7 was added by plan v1.3.1; K4 comes from the
2026-08-11 access-event adjudication. Where a condition cannot be fully
discharged without an action this run is forbidden to take, the verifier says
so in the finding rather than quietly weakening the check -- a condition that
silently redefines itself to pass is worse than one that reports its limit.

===============================================================================
K4 IS ENFORCED AGAINST THIS FILE ITSELF
===============================================================================

The adjudication that made P7 survivable also forbade the method that caused
it: DENY must never be proven by a live HeadObject/GetObject against a sealed
object. So this module contains NO S3 object-read call of any kind, and
:func:`check_k4` reads its own source to prove it. That check would be
worthless if it trusted a comment.

===============================================================================
THE STALE ANCHOR IS REJECTED BY NAME
===============================================================================

The 2026-07-22 adjudicated prerequisite digest 088d700b... predates P3/P4/P5,
the evaluator-image rebind and P10. Binding to it would let a changed program
inherit an old approval. It is hard-coded as REJECTED, and the anchor this run
binds is recomputed from register v1.3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REVIEW = REPO / "docs" / "review" / "mr002"
P3BC = REVIEW / "phase3bc"

REGISTER = P3BC / "MR002_Phase3BC_RuntimePrerequisiteRegister_v1.3.json"
AUTH_STATE = P3BC / "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json"
LINEAGE = P3BC / "MR002_Phase3BC_Phase3ALineageProof_v1.0.json"
P6 = P3BC / "ValidationPartitionContentCommitment_v1.0.json"
P7 = P3BC / "ValidationPartitionAccessHistory_v1.1.json"
P8 = P3BC / "ValidationSealVerificationReport_v1.1.json"
P9 = P3BC / "MR002_ValidationStructuralManifest_v1.0.json"
P10 = P3BC / "MR002_NumericRuntimeIdentityManifest_RuntimeInstance_v1.0.json"
P11 = P3BC / "MR002_ValidationAccessControlPreconditions_v1.0.json"
HOST_FREEZE = P3BC / "MR002_Phase3CHostFreeze_v1.0.json"
ADJUDICATION = REVIEW / "MR002_P7AccessEventDefinition_Adjudication_v1.0.json"
BINDING = REVIEW / "evaluator" / "MR002_EvaluatorBinding_Runtime_v1.0.json"
IMAGE_MANIFEST = REVIEW / "evaluator" / "MR002_EvaluatorImageManifest_Runtime_v1.0.json"
ACCEPTANCE = REVIEW / "evaluator" / "MR002_EvaluatorAcceptanceSubmission.json"
CLOSEOUT = REVIEW / "MR002_ResearchSidePrerequisiteCloseout_v1.0.json"
EVALUATOR_DIR = REVIEW / "evaluator"

BOUND_INDEX = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
STALE_ANCHOR = "088d700bb1b3000a707ab58ca880bf6c71319587284161b373064927b6abc7d6"

BLOCKING = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11")
RUNTIME_INSTANCES = {"P6": P6, "P7": P7, "P8": P8, "P9": P9, "P10": P10, "P11": P11}

# The key holding each record's OWN identity. Named explicitly rather than found
# by suffix: P7 also carries bound_upload_manifest_identity_sha256, and matching
# by suffix would compare a record against another artifact's hash.
SELF_IDENTITY_KEY = {
    "P6": "commitment_identity_sha256",
    "P7": "history_identity_sha256",
    "P8": "report_identity_sha256",
    "P9": "manifest_identity_sha256",
    "P11": "snapshot_identity_sha256",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(record: dict) -> str:
    body = {k: v for k, v in record.items() if not k.endswith("_identity_sha256")}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _finding(cid, title, ok, detail, limitation=None):
    f = {"condition": cid, "title": title, "status": "PASS" if ok else "FAIL",
         "detail": detail}
    if limitation:
        f["limitation"] = limitation
    return f


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


def check_c1(reg):
    """Every blocking prerequisite other than the authorization event is satisfied."""
    by_id = {p["id"]: p for p in reg["prerequisites"]}
    unsatisfied = [i for i in BLOCKING if by_id.get(i, {}).get("status") != "SATISFIED"]
    p12 = by_id.get("P12", {}).get("status", "")
    return _finding(
        "C1", "every blocking prerequisite other than the authorization event is satisfied",
        not unsatisfied and p12.startswith("NOT_EXECUTED"),
        f"unsatisfied={unsatisfied or 'none'}; P12={p12} (excluded: it IS the "
        f"authorization event)",
    )


def check_c2():
    """P3-P11 are runtime-produced, identity-bound, and hash-bound."""
    problems = []
    for pid, path in RUNTIME_INSTANCES.items():
        rec = _load(path)
        if rec.get("artifact_kind") != "RUNTIME_INSTANCE" and pid != "P10":
            problems.append(f"{pid}: artifact_kind={rec.get('artifact_kind')}")
        if pid == "P10":
            if rec.get("prerequisite") != "P10":
                problems.append("P10: not marked prerequisite P10")
            continue
        # The SELF-identity key, named explicitly. Several records also carry
        # BOUND references whose names end the same way (P7 carries
        # bound_upload_manifest_identity_sha256), and picking one of those by
        # suffix would compare a record against a different artifact's hash.
        key = SELF_IDENTITY_KEY[pid]
        if key not in rec:
            problems.append(f"{pid}: missing {key}")
            continue
        if _identity(rec) != rec[key]:
            problems.append(f"{pid}: identity does NOT recompute")
    return _finding(
        "C2", "prerequisite instances are runtime-produced, identity-bound, hash-bound",
        not problems, f"instances checked={sorted(RUNTIME_INSTANCES)}; problems="
                      f"{problems or 'none'}",
        limitation=(
            "P10 carries its provenance rather than a self-identity hash; its file digest "
            "is bound by C6 instead."
        ),
    )


def check_c3():
    """SS5 acceptance submission complete and accepted."""
    ok = ACCEPTANCE.exists() and CLOSEOUT.exists()
    detail = "acceptance submission missing"
    if ok:
        closeout = _load(CLOSEOUT)
        state = closeout.get("prerequisite_state", {})
        p4 = str(state.get("P4", ""))
        ok = p4.startswith("SATISFIED")
        detail = f"P4 closeout state={p4!r}; acceptance submission present"
    return _finding("C3", "SS5 acceptance submission complete and accepted", ok, detail)


def check_c4(resolution):
    """SS4 pre-access evaluator binding resolved -- against the CURRENT bound image."""
    binding = _load(BINDING)
    bound = binding.get("bound_image", {}).get("digest")
    ok = bound == BOUND_INDEX == resolution["image_digest"]
    return _finding(
        "C4", "SS4 pre-access evaluator binding resolved",
        ok, f"renewed binding digest={bound}; live resolution={resolution['image_digest']}",
    )


def check_c5():
    """Structural manifest precommitted and reproduces exactly."""
    rec = _load(P9)
    recomputes = _identity(rec) == rec["manifest_identity_sha256"]
    calendar = rec["governed_calendar"]["reproduces_registered_calendar"]
    sessions = rec["window_sessions"]
    ok = recomputes and calendar and sessions["observed_sessions"] == sessions[
        "expected_sessions"]
    return _finding(
        "C5", "structural manifest precommitted and reproduces exactly", ok,
        f"identity recomputes={recomputes}; registered calendar reproduces={calendar}; "
        f"sessions {sessions['observed_sessions']}/{sessions['expected_sessions']}; "
        f"produced_before_sealing={rec.get('produced_before_sealing')}",
        limitation=(
            "Reproduction is verified at the ARTIFACT level: the manifest's identity hash "
            "recomputes and its bound calendar/session identities match. Re-deriving the "
            "aggregates from the corpus would be a fresh read of the validation partition, "
            "which THIS RUN IS NOT AUTHORIZED TO PERFORM."
        ),
    )


def check_c6(resolution):
    """Numeric-runtime instance sealed and reproducible against the frozen host."""
    p10 = _load(P10)
    freeze = _load(HOST_FREEZE)
    b = p10["bindings"]
    fr = freeze["frozen_runtime_identity"]
    mismatches = []
    if b["container_image_digest"]["digest"] != BOUND_INDEX:
        mismatches.append("image digest")
    if b["container_image_digest"]["digest"] != resolution["image_digest"]:
        mismatches.append("live resolution disagrees")
    for key in ("dependency_lockfile_sha256", "python_version", "numpy_version",
                "scipy_version", "pandas_version"):
        if b.get(key) != fr.get(key):
            mismatches.append(key)
    if b["thread_env"] != fr["thread_env"]:
        mismatches.append("thread_env")
    if len(b) != 17:
        mismatches.append(f"bindings={len(b)}")
    if freeze["p10_instance"]["sha256"] != _sha_file(P10):
        mismatches.append("P10 file digest differs from the frozen record")
    modules = p10["provenance"]["evaluator_modules_verified"]
    if modules != 21:
        mismatches.append(f"evaluator_modules_verified={modules}")
    return _finding(
        "C6", "numeric-runtime instance sealed and reproducible", not mismatches,
        f"17/17 bindings; {modules}/21 modules verified in-image; frozen host "
        f"{freeze['frozen_host']['instance_id']}; mismatches={mismatches or 'none'}",
        limitation=(
            "Reproducibility is verified against the FROZEN host record and a live "
            "re-resolution of the image digest. Re-capturing P10 would be a P10 "
            "regeneration, which this run is not authorized to perform and which "
            "SR-HOST-1 requires only if the runtime changes."
        ),
    )


def check_c7():
    """Access-control state proves zero SUCCESSFUL sealed reads, under the ratified rule."""
    p7, p11, adj = _load(P7), _load(P11), _load(ADJUDICATION)
    g = p7["observed_gate_values"]
    gates_zero = (g["validation_access_events_before_authorization"] == 0
                  and g["oos_access_events_before_validation"] == 0)
    chain = p7["hash_chain"]["verifies"]
    denied = g["validation_read_attempts_denied"] + g["oos_read_attempts_denied"]
    ratified = adj.get("status") == "RATIFIED"
    dec = p11["access_decisions"]
    deny_in_force = (dec["dedicated_reader"]["oos"] == "explicitDeny"
                     and dec["ordinary_development_principal"]["validation"] == "explicitDeny"
                     and dec["ordinary_development_principal"]["oos"] == "explicitDeny")
    ok = gates_zero and chain and ratified and deny_in_force
    return _finding(
        "C7", "access-control state proves no prior validation opening occurred", ok,
        f"successful sealed reads=0/0; chain verifies={chain}; denied ATTEMPTS recorded="
        f"{denied} (classified as attempted-access events, not partition accesses, per the "
        f"RATIFIED adjudication {adj.get('record_identity_sha256','')[:16]}...); "
        f"DENY in force={deny_in_force}",
    )


def check_c8():
    """Phase 3A lineage still reproduces from the then-current tree.

    A VACUITY GUARD is the point of this function as much as the hashing is. The
    first build of this check walked the record looking for a ``sha256`` key,
    but the lineage record stores ``bound_sha256`` against bare filenames. It
    therefore matched nothing and reported "0 artifacts re-hashed; drift=0" as a
    PASS -- certifying lineage by examining nothing. Any check that can pass on
    an empty sample is not a check, so this one FAILS when the sample is empty.
    """
    lineage = _load(LINEAGE)
    checked, drift, absent = 0, [], []

    for name, art in (lineage.get("phase3a_artifacts", {}).get("artifacts", {})).items():
        fname, want = art.get("file"), art.get("bound_sha256")
        if not fname or not want:
            continue
        target = REVIEW / "phase3a" / Path(fname).name
        if not target.exists():
            absent.append(name)
            continue
        checked += 1
        if _sha_file(target) != want:
            drift.append(name)

    prereg = lineage.get("governing_preregistration", {})
    if prereg.get("file") and prereg.get("bound_sha256"):
        target = REPO / prereg["file"]
        if target.exists():
            checked += 1
            if _sha_file(target) != prereg["bound_sha256"]:
                drift.append("governing_preregistration")
        else:
            absent.append("governing_preregistration")

    expected = lineage.get("phase3a_artifacts", {}).get("manifest_bound_artifact_count", 0)
    sample_is_meaningful = checked > 0 and checked >= expected
    ok = sample_is_meaningful and not drift and not absent
    return _finding(
        "C8", "Phase 3A lineage still reproduces from the current tree", ok,
        f"{checked} bound artifacts re-hashed from the tree (manifest binds {expected}); "
        f"drift={drift or 'none'}; absent from tree={absent or 'none'}; "
        f"sample_is_meaningful={sample_is_meaningful}",
    )


def check_c9():
    """Zero evaluator drift, zero unbound evaluator code."""
    manifest = _load(IMAGE_MANIFEST)
    bound = manifest["module_digests_in_image"]
    drift, missing = [], []
    for name, want in bound.items():
        f = EVALUATOR_DIR / Path(name).name
        if not f.exists():
            missing.append(name)
        elif _sha_file(f) != want:
            drift.append(name)
    on_disk = {p.name for p in EVALUATOR_DIR.glob("mr002_valoos_*.py")}
    expected = {Path(n).name for n in bound}
    unbound = sorted(on_disk - expected)
    ok = not drift and not missing and not unbound
    return _finding(
        "C9", "zero evaluator drift, zero unbound evaluator code", ok,
        f"{len(bound)} bound modules; drift={drift or 'none'}; missing={missing or 'none'}; "
        f"unbound evaluator modules on disk={unbound or 'none'}",
    )


def check_c10():
    """validation_authorization remains false until the explicit D3 grant event."""
    st = _load(AUTH_STATE)
    ok = st["validation_authorization"] is False and st["_rev"] == 0
    return _finding(
        "C10", "validation_authorization remains false until the explicit grant event", ok,
        f"validation_authorization={st['validation_authorization']}; _rev={st['_rev']}",
    )


def check_cr7(resolver, resolution):
    """The Requirement-7 resolver is the sole path and fails closed."""
    refusals = {}
    for old in resolver.SUPERSEDED_DIGESTS:
        try:
            resolver.resolve_bound_image(expected_digest=old)
            refusals[old] = "RESOLVED"
        except resolver.ImageResolutionRefused as exc:
            refusals[old] = exc.reason
    all_refused = all(v != "RESOLVED" for v in refusals.values())
    # "No registry fallback" must be judged on CODE, not commentary. The resolver
    # deliberately DISCUSSES imageTag in a comment explaining why it is absent, so a
    # naive substring search reports a fallback that does not exist. Strip comments
    # first, then look for a tag key actually being passed.
    source = (Path(__file__).parent / "resolve_evaluator_image.py").read_text(encoding="utf-8")
    code_only = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
    no_tag_fallback = ("imageTag" not in code_only) and ("imageIds" in code_only)
    ok = (resolution["image_digest"] == BOUND_INDEX
          and resolution.get("satisfies_requirement_7") is True
          and all_refused and no_tag_fallback)
    return _finding(
        "C-R7", "Requirement-7 resolver is the sole path and fails closed", ok,
        f"resolves {resolution['image_digest']}; superseded refusals={refusals}; "
        f"no tag fallback in the fetch path={no_tag_fallback}",
    )


def check_k4():
    """This verifier itself contains no live sealed-object read path.

    The forbidden tokens are assembled from fragments rather than written out.
    Spelling them literally would make this function trip over its own
    definition -- and the fix must not be to exempt this function from the
    scan, because the scan is only meaningful if it covers every line
    including these.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]
    forbidden = [
        "get_" + "object(",
        "head_" + "object(",
        "download_" + "file(",
        "download_" + "fileobj(",
        "select_" + "object_content(",
        "get_" + "object_attributes(",
    ]
    hits = [f for f in forbidden if f in body]
    imports_boto = ("import" + " boto3") in body
    return _finding(
        "K4", "verifier contains no path capable of a live sealed-object probe",
        not hits and not imports_boto,
        f"forbidden call sites in body={hits or 'none'}; imports boto3 directly="
        f"{imports_boto} (the resolver is injected and touches ECR only, never S3)",
    )


# ---------------------------------------------------------------------------
# Anchor
# ---------------------------------------------------------------------------


def compute_anchor(reg) -> dict:
    src = {p["id"]: p["status"] for p in reg["prerequisites"]}
    payload = json.dumps(src, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    anchor = hashlib.sha256(payload.encode("ascii")).hexdigest()
    if anchor == STALE_ANCHOR:
        raise SystemExit("FATAL: recomputed anchor equals the stale adjudicated digest")
    return {
        "prerequisite_anchor_sha256": anchor,
        "definition": "sha256 of the ascii JSON {prerequisite_id: status} sorted by key",
        "computed_from": REGISTER.name,
        "register_identity_sha256": reg["register_identity_sha256"],
        "stale_anchor_rejected": STALE_ANCHOR,
        "stale_anchor_reason": (
            "The 2026-07-22 adjudicated digest predates P3/P4/P5, the evaluator-image "
            "rebind and P10. It is REJECTED by name; binding to it would let a changed "
            "program inherit an old approval."
        ),
        "anchor_differs_from_stale": anchor != STALE_ANCHOR,
    }


def run(resolver) -> dict:
    reg = _load(REGISTER)
    resolution = resolver.resolve_bound_image()
    findings = [
        check_c1(reg), check_c2(), check_c3(), check_c4(resolution), check_c5(),
        check_c6(resolution), check_c7(), check_c8(), check_c9(), check_c10(),
        check_cr7(resolver, resolution), check_k4(),
    ]
    verdict = "PASS" if all(f["status"] == "PASS" for f in findings) else "FAIL"
    return {
        "record_type": "MR002_WPF_GrantReadinessRun",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "verdict": verdict,
        "conditions_evaluated": len(findings),
        "findings": findings,
        "anchor": compute_anchor(reg),
        "bound_evaluator_index": BOUND_INDEX,
        "authorizes": (
            "NOTHING. A PASS is an input to a future D3/P12 owner decision. This run "
            "granted no credential, edited no trust policy, opened no partition and did "
            "not touch validation_authorization."
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WP-F closed grant-readiness run")
    parser.add_argument("--emit", required=True)
    parser.add_argument("--produced-at", required=True)
    parser.add_argument("--custodian", required=True)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import resolve_evaluator_image as resolver  # noqa: PLC0415

    report = run(resolver)
    report["produced_at_utc"] = args.produced_at
    report["custodian"] = args.custodian
    report["verifier_sha256"] = _sha_file(Path(__file__))
    body = json.dumps({k: v for k, v in report.items() if k != "run_identity_sha256"},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    report["run_identity_sha256"] = hashlib.sha256(body.encode("ascii")).hexdigest()

    with open(args.emit, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=1, sort_keys=True, ensure_ascii=True)
        fh.write("\n")

    for f in report["findings"]:
        print(f"  {f['status']:4s} {f['condition']:5s} {f['title']}")
        if f.get("limitation"):
            print(f"       limitation: {f['limitation'][:96]}...")
    print(f"\nVERDICT: {report['verdict']}   anchor={report['anchor']['prerequisite_anchor_sha256']}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
