"""Generate the Phase 3B execution-dependency bundle manifest.

The bound evaluator image ``sha256:194efbdf...`` has no ``pyarrow`` and no ``boto3``, so the Phase 3B
package cannot decode a sealed table or construct its reader inside it. Rebuilding the image to add
a parquet decoder and an S3 client would churn the evaluator identity for infrastructure that is
outside evaluator economics, and would force the P5->P10->D3->P12 chain again. So the dependencies
are supplied the same way the code is: a separately hash-bound, read-only mount, executed under the
unchanged bound runtime.

That is only safe if the bundle cannot perturb the numeric stack P10 qualified. This manifest binds
the controls that make that checkable rather than assertable:

  * exact wheel filenames, SHA-256s and ABI/platform tags;
  * the complete installed-file inventory with per-file SHA-256;
  * refusal if ANY P10 numeric package (numpy / scipy / pandas / BLAS) appears in the bundle;
  * refusal if ANY bundle top-level name shadows a package the image already provides;
  * a runtime before/after check that the P10-critical package identities are unchanged.

Two wheels pip resolved were DELIBERATELY excluded because the image already ships them at the same
version: python-dateutil 2.9.0.post0 and six 1.17.0. Shipping them would have been shadowing.

Zero-data instrument: hashes local files. No AWS call, no sealed object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

# Observed by `pip list` INSIDE the bound image on the qualified host i-00c1034f7026db45e
# (SSM, 2026-08-12). This is evidence, not an assumption: the bundle is checked against it.
P10_IMAGE_INVENTORY = {
    "iniconfig": "2.3.0", "numpy": "2.2.6", "packaging": "26.3", "pandas": "3.0.5",
    "pip": "26.1.2", "pluggy": "1.6.0", "pygments": "2.20.0", "pytest": "9.0.3",
    "python-dateutil": "2.9.0.post0", "ruff": "0.15.13", "scipy": "1.18.0", "six": "1.17.0",
}
# Import names those distributions provide, for the shadow check.
P10_IMPORT_NAMES = {
    "iniconfig", "numpy", "packaging", "pandas", "pip", "pluggy", "pygments", "pytest",
    "_pytest", "dateutil", "ruff", "scipy", "six", "setuptools", "wheel", "py",
}
# Anything here in the bundle means the numeric stack would move. That is a STOP, not a warning.
P10_NUMERIC = {"numpy", "scipy", "pandas", "openblas", "blas", "lapack", "mkl", "numpy_base"}

EXCLUDED_AS_SHADOWING = {
    "python-dateutil": "2.9.0.post0 - image already provides this exact version",
    "six": "1.17.0 - image already provides this exact version",
}

EXPECTED_TOP_LEVEL = {"boto3", "botocore", "jmespath", "pyarrow", "s3transfer", "urllib3"}

IMAGE = "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51"
MOUNT = "/opt/mr002/deps"

_HERE = os.path.dirname(os.path.abspath(__file__))


class BundleRefused(Exception):
    """The bundle cannot be certified. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wheel_pins(wheel_dir: str) -> dict:
    """Bind each wheel by filename, digest and the tags that decide where it may run."""
    pins = {}
    for name in sorted(os.listdir(wheel_dir)):
        if not name.endswith(".whl"):
            continue
        parts = name[:-4].split("-")
        dist, version, tags = parts[0], parts[1], parts[-3:]
        canon = dist.lower().replace("_", "-")
        if canon in EXCLUDED_AS_SHADOWING:
            continue
        pins[name] = {
            "distribution": canon,
            "version": version,
            "python_tag": tags[0],
            "abi_tag": tags[1],
            "platform_tag": tags[2],
            "sha256": _sha256(os.path.join(wheel_dir, name)),
            "size_bytes": os.path.getsize(os.path.join(wheel_dir, name)),
        }
    if not pins:
        raise BundleRefused("no wheels found; a bundle that binds nothing proves nothing")
    for name, p in pins.items():
        if p["abi_tag"] not in ("cp313", "none"):
            raise BundleRefused(f"{name}: abi {p['abi_tag']} does not match the image's cp313")
        if p["platform_tag"] != "any" and "x86_64" not in p["platform_tag"]:
            raise BundleRefused(f"{name}: platform {p['platform_tag']} is not the host's x86_64")
    return pins


def installed_inventory(bundle_dir: str) -> dict:
    """Every installed file, hashed. The wheel digest proves provenance; this proves what landed."""
    files, total = {}, 0
    for root, dirs, names in os.walk(bundle_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in sorted(names):
            if n.endswith(".pyc"):
                raise BundleRefused("compiled bytecode in the bundle is not reproducible; prune it")
            full = os.path.join(root, n)
            rel = os.path.relpath(full, bundle_dir).replace(os.sep, "/")
            files[rel] = _sha256(full)
            total += os.path.getsize(full)
    if not files:
        raise BundleRefused("bundle directory is empty")
    return {"file_count": len(files), "total_bytes": total, "files": files}


def isolation_proof(bundle_dir: str, pins: dict) -> dict:
    """Prove the bundle cannot move the numeric stack and cannot shadow the image."""
    tops = set()
    for entry in os.listdir(bundle_dir):
        if entry == "bin":
            continue
        tops.add(re.split(r"-\d", entry)[0] if entry.endswith(".dist-info") else entry)

    numeric = sorted(t for t in tops if t.lower() in P10_NUMERIC)
    if numeric:
        raise BundleRefused(
            f"bundle contains P10 numeric packages {numeric}. A bundle that moves numpy/scipy/"
            "pandas/BLAS is not a supplement - stop and take the new image / P10 / P12 route."
        )
    shadow = sorted(t for t in tops if t.lower() in P10_IMPORT_NAMES)
    if shadow:
        raise BundleRefused(f"bundle would shadow image-provided packages: {shadow}")
    for p in pins.values():
        if p["distribution"] in P10_IMAGE_INVENTORY:
            raise BundleRefused(f"{p['distribution']} is already provided by the image")

    if tops != EXPECTED_TOP_LEVEL:
        raise BundleRefused(f"unexpected bundle contents: {sorted(tops)} != {sorted(EXPECTED_TOP_LEVEL)}")

    return {
        "bundle_top_level_names": sorted(tops),
        "image_provided_names": sorted(P10_IMPORT_NAMES),
        "intersection": [],
        "p10_numeric_packages_in_bundle": [],
        "excluded_as_shadowing": EXCLUDED_AS_SHADOWING,
        "conclusion": (
            "The bundle is disjoint from everything the image provides, so no image package can be "
            "shadowed regardless of sys.path order. numpy, scipy, pandas and BLAS are untouched."
        ),
    }


def build(wheel_dir: str, bundle_dir: str) -> dict:
    pins = wheel_pins(wheel_dir)
    return {
        "record_type": "MR002_Phase3B_ExecutionDependencyBundle",
        "version": "1.0",
        "artifact_kind": "DEPENDENCY_IDENTITY",
        "status": "SUBMITTED_FOR_ADJUDICATION",
        "date": "2026-08-12",
        "purpose": (
            "Supply the two runtime dependencies the bound evaluator image lacks - a parquet "
            "decoder and an S3 client - as a separately hash-bound read-only mount, so the image "
            "identity stays unchanged."
        ),
        "bound_image_unchanged": IMAGE,
        "why_not_rebuild_the_image": (
            "Rebuilding to add transport and decoding would churn the evaluator identity for "
            "dependencies outside evaluator economics and force the P5->P10->D3->P12 chain again."
        ),
        "why_not_install_at_runtime": (
            "Installing into a running container destroys reproducibility: the executed environment "
            "would exist only for the duration of that container."
        ),
        "mount": {
            "path": MOUNT,
            "mode": "read-only",
            "rationale": "a writable dependency mount is a mutable runtime, which is what the "
                         "hash binding exists to prevent",
        },
        "sys_path_policy": {
            "rule": "the bundle path is added to sys.path ONLY after the disjointness check below "
                    "passes at runtime",
            "ordering": "append after the image site-packages",
            "why_order_is_not_load_bearing_here": (
                "the bundle shares no top-level name with the image, so no ordering can produce a "
                "shadow. The order is still specified so the property does not depend on luck."
            ),
        },
        "wheels": pins,
        "installed_inventory": installed_inventory(bundle_dir),
        "isolation_proof": isolation_proof(bundle_dir, pins),
        "p10_invariance_check": {
            "requirement": "before and after adding the bundle to sys.path, the resolved __file__ "
                           "and __version__ of numpy, scipy and pandas must be identical",
            "enforced_by": "app/research/mr002/phase3b/deps.py at runtime, and a named test",
            "on_failure": "refuse; the numeric stack P10 qualified would have moved",
        },
        "image_inventory_observed": {
            "packages": P10_IMAGE_INVENTORY,
            "provenance": "pip list inside the bound image on host i-00c1034f7026db45e via SSM, "
                          "2026-08-12; single interpreter /usr/local/bin/python 3.13.14",
        },
        "grants": "NOTHING. This artifact asks the owner for a decision.",
        "boundary": (
            "Zero-data. No AWS call, no sealed object, no credential. The opening remains UNSPENT."
        ),
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: _gen_execution_dependency_bundle.py <wheel_dir> <bundle_dir>")
    record = build(sys.argv[1], sys.argv[2])
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    record["record_identity_covers"] = (
        "the canonical JSON of this record excluding record_identity_sha256 and "
        "record_identity_covers"
    )
    out = os.path.join(_HERE, "MR002_Phase3B_ExecutionDependencyBundle_v1.0.json")
    payload = _canonical(record)
    with open(out, "wb") as fh:
        fh.write(payload)
    inv = record["installed_inventory"]
    print(f"wrote {out}")
    print(f"record identity {record['record_identity_sha256']}")
    print(f"file sha256     {hashlib.sha256(payload).hexdigest()}")
    print(f"wheels          {len(record['wheels'])}")
    print(f"installed       {inv['file_count']} files, {inv['total_bytes']/1e6:.1f} MB")
    print(f"top-level       {record['isolation_proof']['bundle_top_level_names']}")
    print("isolation       no P10 numeric package, no shadowing, disjoint from the image")


if __name__ == "__main__":
    main()
