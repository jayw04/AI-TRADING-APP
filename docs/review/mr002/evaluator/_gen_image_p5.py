"""MR-002 P5 continuation — build and qualify the SS4 container image, then supersede the binding.

Sequence (each step fail-closed):

  1. enumerate the included modules AT THE BOUND SOURCE COMMIT, byte-exact from git blobs;
  2. build the image from those bytes with no network and no mounts;
  3. observe the modules INSIDE the image and record a content-addressed image manifest;
  4. verify the image against a source-only binding regenerated at the same commit;
  5. run the SS4 binding gate INSIDE the image against the superseding binding;
  6. demonstrate refusal for every required defect class, three of them inside real containers;
  7. emit the superseding binding with the container leg RESOLVED.

Opens no validation, OOS, or sealed data at any point: the build has no mounts, and the only bind
mount used afterwards is the binding record itself, read-only.

This qualifies the SS4 IMAGE IDENTITY leg. It is NOT P10 numeric-runtime production.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

import mr002_valoos_binding as B
import mr002_valoos_image as IMG

HERE = os.path.abspath(os.path.dirname(__file__))
RVW = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(RVW, "..", "..", ".."))
REL = "docs/review/mr002/evaluator"

BASE_IMAGE = "python@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7"
IMAGE_TAG = "mr002-evaluator-p5:qualify"
IMAGE_DIR = "/opt/mr002/evaluator"
DEP_LOCK = "MR002_Increment1_Dependencies.json"
PREREG = "MR002_ValidationOOS_Preregistration_v1.0.4.json"

ELEMENT_MODULES = {
    "benchmark_impl": "mr002_valoos_metrics.py",
    "cost_model_impl": "mr002_valoos_costmodel.py",
    "metric_impl": "mr002_valoos_metrics.py",
    "bootstrap_impl": "mr002_valoos_metrics.py",
    "pbo_dsr_impl": "mr002_valoos_metrics.py",
    "report_schema": "mr002_valoos_report.py",
}
EXPECTED_OUTPUT_PATHS = ["valoos/<window>/MR002_ValOOS_<window>_Report.json",
                         "valoos/<window>/MR002_ValOOS_<window>_Publication.json"]

DOCKERFILE = f"""# MR-002 SS4 evaluator image (identity leg). No network, no mounts, no sealed data.
FROM {BASE_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
COPY evaluator/ {IMAGE_DIR}/
COPY {DEP_LOCK} /opt/mr002/{DEP_LOCK}
WORKDIR {IMAGE_DIR}
"""

# enumerate + digest the included modules inside a container, using the SAME rule as the binding
IN_IMAGE_ENUMERATE = f"""
import hashlib, json, os
d = {IMAGE_DIR!r}
out = {{}}
for n in sorted(os.listdir(d)):
    if n.endswith('.py') and not n.startswith(('test_', '_gen_')):
        with open(os.path.join(d, n), 'rb') as fh:
            out[n] = hashlib.sha256(fh.read()).hexdigest()
print(json.dumps(out, sort_keys=True))
"""


def git(*args) -> str:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True,
                          check=True).stdout


def git_bytes(*args) -> bytes:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True).stdout


def docker(*args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def sha_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


# =====================================================================================
# 1 — source identity and the byte-exact module set at that commit
# =====================================================================================
source_commit = git("rev-parse", "HEAD").strip()
source_tree = git("rev-parse", "HEAD^{tree}").strip()

names = [ln.rsplit("/", 1)[-1] for ln in
         git("ls-tree", "--name-only", f"{source_commit}:{REL}").splitlines()]
module_names = sorted(n for n in names
                      if n.endswith(".py") and not n.startswith(("test_", "_gen_")))

# only INCLUDED modules may block: an uncommitted generator or test is excluded from the binding
dirty = sorted({ln[3:].rsplit("/", 1)[-1]
                for ln in git("status", "--porcelain", "--", f"{REL}/*.py").splitlines()}
               & set(module_names))
if dirty:
    raise SystemExit(f"REFUSED: included modules are dirty; commit before binding an image: {dirty}")
module_bytes = {n: git_bytes("show", f"{source_commit}:{REL}/{n}") for n in module_names}
module_digests_at_source = {n: sha_bytes(b) for n, b in module_bytes.items()}
lock_bytes = git_bytes("show", f"{source_commit}:{REL}/{DEP_LOCK}")
lock_sha = sha_bytes(lock_bytes)

live = B.enumerate_inventory(HERE)["included_modules"]
if live != module_digests_at_source:
    raise SystemExit(f"REFUSED: worktree modules differ from {source_commit[:12]}")

# =====================================================================================
# 2 — build from those exact bytes, no network, no mounts
# =====================================================================================
build_root = tempfile.mkdtemp(prefix="mr002_p5_image_")
os.makedirs(os.path.join(build_root, "evaluator"))
for name, blob in module_bytes.items():
    with open(os.path.join(build_root, "evaluator", name), "wb") as fh:
        fh.write(blob)
with open(os.path.join(build_root, DEP_LOCK), "wb") as fh:
    fh.write(lock_bytes)
dockerfile_bytes = DOCKERFILE.encode("utf-8")
with open(os.path.join(build_root, "Dockerfile"), "wb") as fh:
    fh.write(dockerfile_bytes)

build = docker("build", "--pull=false", "--network=none", "-t", IMAGE_TAG,
               "-f", os.path.join(build_root, "Dockerfile"), build_root, check=False)
if build.returncode != 0:
    raise SystemExit(f"REFUSED: docker build failed\n{build.stderr[-2000:]}")

image_id = docker("inspect", IMAGE_TAG, "--format", "{{.Id}}").stdout.strip()
platform = docker("inspect", IMAGE_TAG, "--format", "{{.Os}}/{{.Architecture}}").stdout.strip()
builder = docker("version", "--format", "{{.Server.Version}}").stdout.strip()

# =====================================================================================
# 3 — observe the modules INSIDE the image
# =====================================================================================
observed = json.loads(docker("run", "--rm", "--network=none", image_id,
                             "python", "-c", IN_IMAGE_ENUMERATE).stdout)
in_image_lock = docker("run", "--rm", "--network=none", image_id, "python", "-c",
                       f"import hashlib;print(hashlib.sha256(open('/opt/mr002/{DEP_LOCK}','rb')"
                       f".read()).hexdigest())").stdout.strip()

manifest = IMG.build_image_manifest(
    image_digest=image_id, base_image_digest=BASE_IMAGE, platform=platform,
    builder=f"docker/{builder}", build_definition="Dockerfile (inline, recorded by hash)",
    build_definition_sha256=sha_bytes(dockerfile_bytes),
    source_commit=source_commit, source_tree=source_tree,
    dependency_lock=DEP_LOCK, dependency_lock_sha256=in_image_lock,
    evaluator_path_in_image=IMAGE_DIR, module_digests=observed,
    build_inputs={"base_image": BASE_IMAGE, "network": "none", "mounts": "none",
                  "context": "git blobs at source_commit only",
                  "module_count": len(module_bytes), "dependency_lock_sha256": lock_sha},
    sealed_data_mounted=False)

# =====================================================================================
# 4 — verify against a source-only binding regenerated at THIS commit
# =====================================================================================
prereg = json.loads((os.path.join(RVW, PREREG) and open(  # noqa: SIM115
    os.path.join(RVW, PREREG), encoding="utf-8").read()))
calendar = prereg["governing_frozen_sources"]["authoritative_calendar_snapshot"]
common = {
    "source_commit": source_commit, "source_tree": source_tree,
    "dependency_lock": DEP_LOCK, "dependency_lock_sha256": lock_sha,
    "data_manifest_identity": {"file": calendar["file"], "sha256": calendar["sha256"],
                               "registered_in": f"{PREREG} governing_frozen_sources"},
    "expected_output_paths": EXPECTED_OUTPUT_PATHS, "element_modules": ELEMENT_MODULES,
}
source_only = B.build_binding(HERE, container_image_digest=None, **common)
assert source_only["unresolved_elements"] == ["container_image_digest"]
image_report = IMG.require_image(manifest, source_only, observed_image_digest=image_id,
                                 observed_modules=observed)

# =====================================================================================
# 5 — the superseding binding, then run the SS4 gate INSIDE the image
# =====================================================================================
superseding = B.build_binding(HERE, container_image_digest=image_id, **common)
assert superseding["binding_state"] == "RESOLVED"
assert superseding["unresolved_elements"] == []
superseding["supersedes"] = {
    "previous_binding_sha256": sha_bytes(
        git_bytes("show", f"HEAD:{REL}/MR002_EvaluatorBinding.json")),
    "previous_source_commit": json.loads(
        git_bytes("show", f"HEAD:{REL}/MR002_EvaluatorBinding.json").decode("utf-8")
    )["section4_elements"]["source_commit"]["value"],
    "reason": "producing the qualifying image required new evaluator source "
              "(mr002_valoos_image.py), so the source binding was regenerated at the new commit "
              "rather than preserved",
}
superseding["container_image_manifest_sha256"] = IMG.manifest_sha256(manifest)
superseding["source_identity_evidence"] = {
    "all_included_modules_committed_at_source_commit": True,
    "committed_blob_digests": module_digests_at_source,
}

bind_path = os.path.join(build_root, "binding.json")
with open(bind_path, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(superseding, sort_keys=True, indent=2) + "\n")

GATE_IN_IMAGE = f"""
import json, sys
sys.path.insert(0, {IMAGE_DIR!r})
import mr002_valoos_binding as B
binding = json.load(open('/binding/binding.json'))
try:
    rep = B.require_binding({IMAGE_DIR!r}, binding)
    print(json.dumps({{'passed': True, 'modules': rep['included_module_count']}}))
except B.BindingRefused as exc:
    print(json.dumps({{'passed': False, 'code': str(exc)}}))
"""
gate = json.loads(docker(
    "run", "--rm", "--network=none",
    "--mount", f"type=bind,src={build_root},dst=/binding,ro",
    image_id, "python", "-c", GATE_IN_IMAGE).stdout)
assert gate["passed"] is True, gate

# =====================================================================================
# 6 — refusals: three inside real containers, four at manifest level
# =====================================================================================
def _in_image_defect(label: str, mutation: str) -> dict:
    script = f"""
import json, shutil, sys, os
shutil.copytree({IMAGE_DIR!r}, '/tmp/e')
{mutation}
sys.path.insert(0, '/tmp/e')
import mr002_valoos_binding as B
binding = json.load(open('/binding/binding.json'))
try:
    B.require_binding('/tmp/e', binding)
    print(json.dumps({{'refused': False}}))
except B.BindingRefused as exc:
    print(json.dumps({{'refused': True, 'code': str(exc)}}))
"""
    out = docker("run", "--rm", "--network=none",
                 "--mount", f"type=bind,src={build_root},dst=/binding,ro",
                 image_id, "python", "-c", script).stdout
    return {"label": label, "where": "inside the produced image", **json.loads(out)}


victim = module_names[0]
refusals = [
    _in_image_defect("module_drift_in_image",
                     f"open('/tmp/e/{victim}','ab').write(b'\\n# tampered\\n')"),
    _in_image_defect("module_omitted_from_image", f"os.remove('/tmp/e/{victim}')"),
    _in_image_defect("additional_unbound_module_in_image",
                     "open('/tmp/e/mr002_valoos_intruder.py','wb').write(b'# extra\\n')"),
]


def _manifest_defect(label: str, **kw) -> dict:
    bad_manifest = dict(manifest, **kw.pop("manifest", {}))
    try:
        IMG.require_image(bad_manifest, source_only, **kw)
        return {"label": label, "where": "manifest", "refused": False}
    except IMG.ImageRefused as exc:
        return {"label": label, "where": "manifest", "refused": True, "code": str(exc)}


refusals += [
    _manifest_defect("altered_image_digest",
                     observed_image_digest="sha256:" + "b" * 64, observed_modules=observed),
    _manifest_defect("wrong_source_commit", manifest={"source_commit": "0" * 40},
                     observed_modules=observed),
    _manifest_defect("wrong_source_tree", manifest={"source_tree": "0" * 40},
                     observed_modules=observed),
    _manifest_defect("changed_dependency_lock", manifest={"dependency_lock_sha256": "0" * 64},
                     observed_modules=observed),
]
try:
    IMG.build_image_manifest(
        image_digest=IMAGE_TAG, base_image_digest=BASE_IMAGE, platform=platform, builder=builder,
        build_definition="x", build_definition_sha256="0" * 64, source_commit=source_commit,
        source_tree=source_tree, dependency_lock=DEP_LOCK, dependency_lock_sha256=lock_sha,
        evaluator_path_in_image=IMAGE_DIR, module_digests=observed, build_inputs={})
    refusals.append({"label": "mutable_tag_only_identity", "where": "manifest", "refused": False})
except IMG.ImageRefused as exc:
    refusals.append({"label": "mutable_tag_only_identity", "where": "manifest",
                     "refused": True, "code": str(exc)})

assert all(r["refused"] for r in refusals), [r for r in refusals if not r["refused"]]

# =====================================================================================
# 7 — emit
# =====================================================================================
with open(os.path.join(HERE, "MR002_EvaluatorImageManifest.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")

shutil.copyfile(os.path.join(HERE, "MR002_EvaluatorBinding.json"),
                os.path.join(HERE, "MR002_EvaluatorBinding_superseded_6708c59.json"))
with open(os.path.join(HERE, "MR002_EvaluatorBinding.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(superseding, sort_keys=True, indent=2) + "\n")

qual = {
    "record_type": "MR002_P5_ContainerQualification", "version": "1.0",
    "prerequisite": "P5 continuation — qualifying container-image leg",
    "authorization": "P5 adjudication 2026-07-22 — container-image completion only, then stop",
    "source_identity": {"commit": source_commit, "tree": source_tree,
                        "modules_byte_exact_from_git_blobs": True,
                        "included_module_count": len(module_names)},
    "image": {"digest": manifest["image_digest"], "base": manifest["base_image_digest"],
              "platform": platform, "builder": manifest["builder"],
              "build_definition_sha256": manifest["build_definition_sha256"],
              "network": "none", "mounts_during_build": "none",
              "sealed_data_mounted": False},
    "image_contents": {
        "modules_in_image": len(observed),
        "byte_identical_to_bound_set": observed == module_digests_at_source,
        "no_additional_included_module": sorted(observed) == sorted(module_digests_at_source),
        "dependency_lock_in_image_sha256": in_image_lock,
        "dependency_lock_matches_source": in_image_lock == lock_sha},
    "image_verification": image_report,
    "section4_gate_inside_image": {"passed": gate["passed"],
                                   "modules_verified": gate.get("modules"),
                                   "method": "require_binding executed by the image's own "
                                             "interpreter against the superseding binding"},
    "refusal_demonstrations": refusals,
    "all_defect_classes_refused": all(r["refused"] for r in refusals),
    "binding": {"state": superseding["binding_state"],
                "unresolved_elements": superseding["unresolved_elements"],
                "supersedes": superseding["supersedes"]},
    "determinism_note": "the image config digest embeds a build timestamp, so a rebuild produces a "
                        "different digest; the binding names the digest ACTUALLY produced. "
                        "Bit-reproducible image builds are not claimed",
    "scope_boundary": "SS4 image-identity leg only. This is NOT P10 numeric-runtime production: the "
                      "image carries the evaluator modules and the dependency lock, and no numeric "
                      "stack was installed or qualified here",
    "not_done": ["P10 numeric-runtime instance", "custodian P6-P9/P11", "P13",
                 "validation/OOS access", "credential release", "performance computation",
                 "grant-readiness verifier", "D3 authorization event"],
    "boundary": "No validation, OOS, or sealed data was mounted or opened. "
                "validation_authorization remains false.",
}
with open(os.path.join(HERE, "MR002_P5_ContainerQualification.json"), "w",
          encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(qual, sort_keys=True, indent=2) + "\n")

shutil.rmtree(build_root, ignore_errors=True)

print("P5 container leg qualified")
print(f"  source {source_commit[:12]} tree {source_tree[:12]} modules={len(module_names)}")
print(f"  image  {manifest['image_digest'][:19]}… platform={platform}")
print(f"  in-image gate passed={gate['passed']} modules={gate.get('modules')}")
print(f"  refusals: {[r['label'] for r in refusals]} all={qual['all_defect_classes_refused']}")
print(f"  binding_state={superseding['binding_state']} unresolved={superseding['unresolved_elements']}")
