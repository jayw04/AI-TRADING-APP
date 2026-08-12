"""Bundle v1.1 - the authoritative Linux/container resolution, superseding the Windows one.

v1.0 was resolved on Windows and pinned pyarrow's ``manylinux_2_17`` wheel, sha ``b6953f01...``. The
bound image runs Debian glibc 2.36, so pip inside it prefers ``manylinux_2_28``, sha ``97c8dc98...``.
Those are different wheels. v1.0 therefore bound a file that would never execute, and its 2,919-entry
installed inventory described that same wheel - which is why the fix is a regeneration from the
in-image resolution rather than an edit of one field.

The other five wheels matched exactly, so the correction is genuinely confined to pyarrow.

v1.0 is retained as superseded evidence, not silently replaced: it records what a non-container
resolution produces, which is the whole reason the in-image resolution is the authority.

Everything here comes from the live observation captured inside the bound image on the qualified
host - wheel digests, the complete installed-file inventory, and the before/after numeric snapshot.
Nothing is re-derived locally.

Zero-data instrument: reads a local observation file. No AWS call, no sealed object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

SUPERSEDED = {
    "manifest": "MR002_Phase3B_ExecutionDependencyBundle_v1.0.json",
    "record_identity_sha256": "02701a0a1085723f74b7d7e9803e78220ee72169b5254c840303fd499cb6bdf5",
    "file_sha256": "759f1888c54f0f9496fbd474056ed17d7f68662940cb419d4f424c0633de2212",
    "status": "SUPERSEDED_NON_CONTAINER_RESOLUTION",
    "defect": "pyarrow pinned as manylinux_2_17 sha b6953f01... resolved on Windows; the bound "
              "image (Debian glibc 2.36) resolves manylinux_2_28 sha 97c8dc98... A wheel that "
              "would never execute cannot be the bound identity.",
    "retained_as": "evidence of what a non-container resolution produces",
    "unaffected": "the other five wheels matched the in-image resolution exactly",
}

IMAGE = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
P10_NUMERIC = {"numpy", "scipy", "pandas", "openblas", "blas", "lapack", "mkl"}
P10_IMPORT_NAMES = {
    "iniconfig", "numpy", "packaging", "pandas", "pip", "pluggy", "pygments", "pytest",
    "_pytest", "dateutil", "ruff", "scipy", "six", "setuptools", "wheel", "py",
}
EXPECTED_TOP_LEVEL = {"boto3", "botocore", "jmespath", "pyarrow", "s3transfer", "urllib3"}
EXCLUDED_AS_SHADOWING = {
    "python-dateutil": "2.9.0.post0 - image already provides this exact version",
    "six": "1.17.0 - image already provides this exact version",
}

_HERE = os.path.dirname(os.path.abspath(__file__))


class BundleRefused(Exception):
    """The bundle cannot be certified. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def build(observation: dict) -> dict:
    bundle = observation.get("dependency_bundle") or {}
    inv = bundle.get("installed_inventory") or {}
    wheels = bundle.get("wheels") or {}
    inva = observation.get("p10_invariance") or {}
    runtime = observation.get("runtime") or {}

    if not wheels or not inv:
        raise BundleRefused("observation carries no wheels or no installed inventory")
    if runtime.get("image_digest") != IMAGE:
        raise BundleRefused(f"observation is not from the bound image: {runtime.get('image_digest')}")
    if not inva.get("unchanged"):
        raise BundleRefused(
            f"the P10 numeric stack MOVED: before={inva.get('before')} after={inva.get('after')}"
        )
    if "/opt/mr002/deps" in str(inva.get("numpy_resolved_from", "")):
        raise BundleRefused("numpy resolved FROM THE BUNDLE; the numeric stack would be replaced")
    if not all(inva.get("resolved_from_bundle", {}).values()):
        raise BundleRefused("pyarrow/boto3 did not resolve from the bundle; the mount is inert")

    pins = {}
    for name, sha in sorted(wheels.items()):
        parts = name[:-4].split("-")
        canon = parts[0].lower().replace("_", "-")
        if canon in P10_NUMERIC:
            raise BundleRefused(f"bundle contains a P10 numeric package: {canon}")
        tags = parts[-3:]
        pins[name] = {
            "distribution": canon, "version": parts[1], "python_tag": tags[0],
            "abi_tag": tags[1], "platform_tag": tags[2], "sha256": sha,
        }
        if tags[1] not in ("cp313", "none"):
            raise BundleRefused(f"{name}: abi {tags[1]} does not match the image's cp313")

    tops = set()
    for rel in inv:
        head = rel.split("/", 1)[0]
        if head in ("bin",):
            continue
        tops.add(re.split(r"-\d", head)[0] if head.endswith(".dist-info") else head)
    tops = {t for t in tops if "." not in t or t.endswith(".py") is False}
    tops = {t for t in tops if not t.endswith(".dist-info")}
    shadow = sorted(tops & P10_IMPORT_NAMES)
    if shadow:
        raise BundleRefused(f"bundle would shadow image-provided packages: {shadow}")
    if not EXPECTED_TOP_LEVEL <= tops:
        raise BundleRefused(f"bundle is missing expected packages: {sorted(EXPECTED_TOP_LEVEL - tops)}")

    return {
        "record_type": "MR002_Phase3B_ExecutionDependencyBundle",
        "version": "1.1",
        "artifact_kind": "DEPENDENCY_IDENTITY",
        "status": "SUBMITTED_FOR_ADJUDICATION",
        "supersedes": SUPERSEDED,
        "resolution_authority": (
            "resolved and installed INSIDE the bound image on the qualified host; a resolution "
            "performed anywhere else is not the resolution that executes"
        ),
        "bound_image_unchanged": IMAGE,
        "host_instance_id": observation.get("host_instance_id"),
        "mount": {
            "path": bundle.get("mount"),
            "mode": "read-only",
            "read_only_proven": (observation.get("mounts") or {}).get("deps_read_only"),
        },
        "sys_path_policy": {
            "ordering": bundle.get("sys_path_position"),
            "disjointness": "the bundle shares no top-level name with the image, so no ordering "
                            "can produce a shadow",
        },
        "wheels": pins,
        "wheel_count": len(pins),
        "installed_inventory": {
            "file_count": bundle.get("installed_file_count"),
            "total_bytes": bundle.get("installed_total_bytes"),
            "inventory_sha256": hashlib.sha256(_canonical(dict(sorted(inv.items())))).hexdigest(),
            "files": dict(sorted(inv.items())),
        },
        "isolation_proof": {
            "bundle_top_level_names": sorted(tops),
            "intersection_with_image": [],
            "p10_numeric_packages_in_bundle": [],
            "excluded_as_shadowing": EXCLUDED_AS_SHADOWING,
        },
        "p10_invariance_observed": {
            "packages": inva.get("packages"),
            "before": inva.get("before"),
            "after": inva.get("after"),
            "unchanged": True,
            "numpy_resolved_from": inva.get("numpy_resolved_from"),
            "bundle_packages_resolved_from_bundle": inva.get("resolved_from_bundle"),
            "meaning": "Python, NumPy, SciPy and pandas are byte-identical either side of the "
                       "activation, and numpy still resolves from the image site-packages",
        },
        "runtime_observed": runtime,
        "grants": "NOTHING. This artifact asks the owner for a decision.",
        "boundary": "Zero-data. No AWS call, no sealed object, no credential. Opening UNSPENT.",
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: _gen_execution_dependency_bundle_v11.py <observation.json>")
    with open(sys.argv[1], encoding="utf-8") as fh:
        observation = json.load(fh)
    record = build(observation)
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_ExecutionDependencyBundle_v1.1.json")
    payload = _canonical(record)
    with open(out, "wb") as fh:
        fh.write(payload)
    print(f"wrote {out}")
    print(f"record identity  {record['record_identity_sha256']}")
    print(f"file sha256      {hashlib.sha256(payload).hexdigest()}")
    print(f"wheels           {record['wheel_count']} (in-image resolution)")
    print(f"pyarrow          {[k for k in record['wheels'] if 'pyarrow' in k][0]}")
    print(f"inventory        {record['installed_inventory']['file_count']} files, "
          f"sha {record['installed_inventory']['inventory_sha256'][:16]}")
    print(f"P10 unchanged    {record['p10_invariance_observed']['unchanged']}")
    print(f"supersedes       v1.0 {SUPERSEDED['record_identity_sha256'][:16]} "
          f"({SUPERSEDED['status']})")


if __name__ == "__main__":
    main()
