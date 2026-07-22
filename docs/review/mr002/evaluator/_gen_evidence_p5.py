"""MR-002 prerequisite P5 — SS4 pre-access evaluator binding: qualification + emission.

Emits the AUTHORITATIVE evaluator binding for the then-current tree, plus the qualification record.

Ordering is enforced, not assumed: the binding names a real `source_commit`/`source_tree`, and every
included module must already exist AT THAT COMMIT with a byte-identical blob. A module that is only
in the working tree fail-stops here — which is why the P5 modules are committed BEFORE this runs.
The artifacts this script emits are `EXCLUDED_NON_EVALUATOR`, so committing them cannot change the
bound module inventory.

Opens no partition, releases no credentials, computes no performance, creates no P10, and creates no
authorization event. The container leg stays PENDING because no qualifying image exists.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

import mr002_valoos_binding as B

HERE = os.path.abspath(os.path.dirname(__file__))
RVW = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(RVW, "..", "..", ".."))
REL = "docs/review/mr002/evaluator"

DEP_LOCK = "MR002_Increment1_Dependencies.json"
PREREG = "MR002_ValidationOOS_Preregistration_v1.0.4.json"

# SS4 element -> the module that implements it (all must be inside the qualified inventory)
ELEMENT_MODULES = {
    "benchmark_impl": "mr002_valoos_metrics.py",      # D-BENCH zero benchmark: excess == net
    "cost_model_impl": "mr002_valoos_costmodel.py",
    "metric_impl": "mr002_valoos_metrics.py",
    "bootstrap_impl": "mr002_valoos_metrics.py",
    "pbo_dsr_impl": "mr002_valoos_metrics.py",
    "report_schema": "mr002_valoos_report.py",
}
EXPECTED_OUTPUT_PATHS = ["valoos/<window>/MR002_ValOOS_<window>_Report.json",
                         "valoos/<window>/MR002_ValOOS_<window>_Publication.json"]


def _git(*args) -> str:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _git_bytes(*args) -> bytes:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True).stdout


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# source identity — a real commit and tree, never a placeholder
# ---------------------------------------------------------------------------
source_commit = _git("rev-parse", "HEAD")
source_tree = _git("rev-parse", "HEAD^{tree}")
working_tree_clean = _git("status", "--porcelain", "--", f"{REL}/*.py") == ""

# ---------------------------------------------------------------------------
# qualify the then-current inventory (mechanically; no assumed count)
# ---------------------------------------------------------------------------
qualification = B.require_qualified(HERE)
included = qualification["inventory"]["included_modules"]

# every included module must be COMMITTED at source_commit and byte-identical
committed_at_source, not_committed, blob_mismatch = {}, [], []
for name, digest in sorted(included.items()):
    try:
        blob = _git_bytes("show", f"{source_commit}:{REL}/{name}")
    except subprocess.CalledProcessError:
        not_committed.append(name)
        continue
    committed_at_source[name] = sha_bytes(blob)
    if committed_at_source[name] != digest:
        blob_mismatch.append({"module": name, "worktree": digest,
                              "committed": committed_at_source[name]})
if not_committed or blob_mismatch:
    raise SystemExit(
        f"{B.REFUSED}:binding_would_name_uncommitted_code -> commit the evaluator modules first. "
        f"not_committed={not_committed} blob_mismatch={blob_mismatch}")

# ---------------------------------------------------------------------------
# emit the binding
# ---------------------------------------------------------------------------
prereg = read_json(os.path.join(RVW, PREREG))
calendar = prereg["governing_frozen_sources"]["authoritative_calendar_snapshot"]

binding = B.build_binding(
    HERE,
    source_commit=source_commit, source_tree=source_tree,
    dependency_lock=DEP_LOCK,
    dependency_lock_sha256=sha_file(os.path.join(HERE, DEP_LOCK)),
    data_manifest_identity={"file": calendar["file"], "sha256": calendar["sha256"],
                            "registered_in": f"{PREREG} governing_frozen_sources"},
    expected_output_paths=EXPECTED_OUTPUT_PATHS,
    element_modules=ELEMENT_MODULES,
    container_image_digest=None,  # no qualifying bound image exists -> leg stays PENDING
)
assert binding["binding_state"] == "PARTIALLY_RESOLVED"
assert binding["unresolved_elements"] == ["container_image_digest"]

binding["source_identity_evidence"] = {
    "working_tree_clean_for_modules": working_tree_clean,
    "all_included_modules_committed_at_source_commit": True,
    "committed_blob_digests": committed_at_source,
    "emission_note": "the artifacts emitted by this script are EXCLUDED_NON_EVALUATOR; committing "
                     "them adds no included module, so the bound inventory stays reproducible at "
                     "source_commit",
}
with open(os.path.join(HERE, "MR002_EvaluatorBinding.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(binding, sort_keys=True, indent=2) + "\n")

# ---------------------------------------------------------------------------
# behavioural evidence: the procedure fails closed on each defect class
# ---------------------------------------------------------------------------
import shutil  # noqa: E402
import tempfile  # noqa: E402

defects = {}
with tempfile.TemporaryDirectory() as sandbox:
    work = os.path.join(sandbox, "evaluator")
    os.makedirs(work)
    for name in included:
        shutil.copy2(os.path.join(HERE, name), os.path.join(work, name))
    sandbox_binding = B.build_binding(
        work, source_commit=source_commit, source_tree=source_tree, dependency_lock=DEP_LOCK,
        dependency_lock_sha256=binding["section4_elements"]["dependency_lock"]["sha256"],
        data_manifest_identity={"file": calendar["file"], "sha256": calendar["sha256"]},
        expected_output_paths=EXPECTED_OUTPUT_PATHS, element_modules=ELEMENT_MODULES,
        container_image_digest="sha256:" + "0" * 64)  # resolved so defects are what refuses

    def _attempt(label, mutate):  # noqa: ANN001
        scratch = os.path.join(sandbox, label)
        shutil.copytree(work, scratch)
        mutate(scratch)
        try:
            B.require_binding(scratch, sandbox_binding)
            defects[label] = {"refused": False}
        except B.BindingRefused as exc:
            defects[label] = {"refused": True, "code": str(exc)}

    victim = sorted(included)[0]
    other = sorted(included)[1]
    _attempt("unbound", lambda p: open(os.path.join(p, "mr002_valoos_intruder.py"), "wb")
             .write(b"# not bound\n"))
    _attempt("missing", lambda p: os.remove(os.path.join(p, victim)))
    _attempt("renamed", lambda p: os.rename(os.path.join(p, victim),
                                            os.path.join(p, "mr002_valoos_renamed.py")))
    _attempt("drifted", lambda p: open(os.path.join(p, victim), "ab").write(b"\n# tampered\n"))
    _attempt("duplicate", lambda p: shutil.copy2(os.path.join(p, victim),
                                                 os.path.join(p, "mr002_valoos_dup.py")))
    # an UNRESOLVED leg alone must refuse a run even on a pristine tree
    try:
        B.require_binding(work, binding)
        defects["unresolved_leg"] = {"refused": False}
    except B.BindingRefused as exc:
        defects["unresolved_leg"] = {"refused": True, "code": str(exc)}
    # and a clean tree with every leg resolved must pass
    clean_ok = B.require_binding(work, sandbox_binding)["matches"]

assert all(d["refused"] for d in defects.values()), defects
assert clean_ok is True

# ---------------------------------------------------------------------------
# qualification record
# ---------------------------------------------------------------------------
post_emission = B.enumerate_inventory(HERE)
counts = qualification["inventory"]["counts"]
record = {
    "record_type": "MR002_P5_BindingQualification", "version": "1.0",
    "prerequisite": "P5 (SS4 pre-access evaluator binding)",
    "authorization": "P4 adjudication 2026-07-22 — P5 authorized; proceed with P5 only, then stop",
    "source_identity": {"commit": source_commit, "tree": source_tree,
                        "working_tree_clean_for_modules": working_tree_clean},
    "inventory": {
        "derivation": "mechanically enumerated under the registered SS4 rule; 19 was NOT assumed",
        "included_module_count": len(included),
        "counts_by_class": counts,
        "entry_count_at_qualification": qualification["inventory"]["entry_count"],
        "entries_now": post_emission["entry_count"],
        "entry_delta_explanation": "the emitted artifacts are EXCLUDED_NON_EVALUATOR; the included "
                                   "module set is unchanged",
        "included_module_set_unchanged_after_emission":
            post_emission["included_modules"] == included,
        "inventory_digest": binding["inventory_digest"]},
    "excluded_accounting": {
        "every_entry_classified": (qualification["inventory"]["entry_count"]
                                   == sum(counts[c] for c in B.CLASSES)),
        "excluded": qualification["inventory"]["excluded"]},
    "fail_closed_behaviour": defects,
    "clean_tree_with_all_legs_resolved_passes": clean_ok,
    "binding": {
        "file": "MR002_EvaluatorBinding.json",
        "sha256": sha_file(os.path.join(HERE, "MR002_EvaluatorBinding.json")),
        "state": binding["binding_state"],
        "unresolved_elements": binding["unresolved_elements"],
        "pending_evaluator_bind": binding["pending_evaluator_bind"]},
    "section4_element_status": {k: v["status"] for k, v in binding["section4_elements"].items()},
    "finding_container_leg": {
        "statement": "SS4 requires a container-image digest. No qualifying bound image exists, so "
                     "that leg is UNRESOLVED and the binding is PARTIALLY_RESOLVED.",
        "consequence": "P5 delivers the authoritative CODE binding; SS4 is not fully discharged "
                       "until a bound image exists. require_binding refuses a run while any leg is "
                       "UNRESOLVED, so this cannot be forgotten at run time.",
        "producer": "runtime producer (P10 / deployment) — NOT authorized to me under this "
                    "instruction"},
    "not_done": ["container image creation", "P10 runtime instance", "custodian P6-P9/P11",
                 "P13", "validation/OOS access", "credential release", "performance computation",
                 "D3 authorization event", "grant-readiness verifier"],
    "boundary": "No partition opened, no credential released, no performance computed, no "
                "authorization event created. validation_authorization remains false.",
}
with open(os.path.join(HERE, "MR002_P5_BindingQualification.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(record, sort_keys=True, indent=2) + "\n")

print("P5 SS4 binding emitted")
print(f"  source {source_commit[:12]} tree {source_tree[:12]} clean={working_tree_clean}")
print(f"  included modules = {len(included)} (derived); classes = "
      f"{ {k: v for k, v in counts.items()} }")
print(f"  binding_state = {binding['binding_state']}; unresolved = {binding['unresolved_elements']}")
print(f"  fail-closed refusals: {sorted(defects)} all_refused="
      f"{all(d['refused'] for d in defects.values())}")
