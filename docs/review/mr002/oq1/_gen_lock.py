"""OQ-1 Phase 1 — generate the distribution-resolvable dependency lock from the offline wheelhouse.

Produces requirements.lock (pip --require-hashes format), wheelhouse-manifest.json, and
dependency-resolution-report.json. Exact names/versions/filenames/SHA-256; no floating ranges; the
lock recreates the environment offline (--no-index --find-links) without resolving newer versions.
Reads the local wheelhouse only; no network.
"""
import hashlib
import json
import os
import re

WH = "wheelhouse"
INDEX = "https://pypi.org/simple/ (offline wheelhouse; --no-index --find-links=./wheelhouse at install)"
RUNTIME = {"numpy", "scipy"}
TOOLING = {"pytest", "ruff", "iniconfig", "packaging", "pluggy", "colorama", "pygments"}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def parse(fn):
    # name-version-... .whl
    m = re.match(r"^(?P<name>[A-Za-z0-9_.\-]+?)-(?P<ver>[0-9][^-]*)-", fn)
    return m.group("name").lower().replace("_", "-"), m.group("ver")


wheels = sorted(f for f in os.listdir(WH) if f.endswith(".whl"))
entries = []
for w in wheels:
    name, ver = parse(w)
    entries.append({"name": name, "version": ver, "filename": w, "sha256": sha(os.path.join(WH, w)),
                    "size_bytes": os.path.getsize(os.path.join(WH, w)),
                    "role": "runtime" if name in RUNTIME else "qualification_tooling",
                    "platform_tag": w.split("-", 3)[-1].replace(".whl", "")})

# requirements.lock (pip --require-hashes)
lines = ["# MR-002 OQ-1 locked dependencies — offline wheelhouse; install with:",
         "#   pip install --no-index --find-links=./wheelhouse --require-hashes -r requirements.lock",
         "# No floating ranges; no unverified downloads; recreates the env without resolving newer versions.",
         "# python: CPython 3.13 (cp313)  |  platform target: manylinux2014 / manylinux_2_28 x86_64",
         ""]
for e in entries:
    lines.append(f"{e['name']}=={e['version']} \\")
    lines.append(f"    --hash=sha256:{e['sha256']}")
open("requirements.lock", "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")

manifest = {
    "record_type": "MR002_OQ1_WheelhouseManifest", "version": "1.0",
    "python": {"implementation": "CPython", "version": "3.13", "abi": "cp313"},
    "platform_targets": ["manylinux2014_x86_64", "manylinux_2_28_x86_64", "none-any"],
    "index_identity": INDEX,
    "install_command": "pip install --no-index --find-links=./wheelhouse --require-hashes -r requirements.lock",
    "no_floating_ranges": True, "no_unverified_downloads": True,
    "wheels": entries,
    "wheelhouse_sha256_of_shas": hashlib.sha256(
        "".join(sorted(e["sha256"] for e in entries)).encode()).hexdigest(),
}
open("wheelhouse-manifest.json", "w", encoding="utf-8", newline="\n").write(
    json.dumps(manifest, sort_keys=True, indent=1) + "\n")

report = {
    "record_type": "MR002_OQ1_DependencyResolutionReport", "version": "1.0",
    "resolver": "pip download --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 --python-version 3.13 --implementation cp --abi cp313",
    "runtime": sorted(RUNTIME), "qualification_tooling": sorted(TOOLING),
    "resolved": {e["name"]: e["version"] for e in entries},
    "scipy_1_18_0_availability": "resolvable on PyPI (index latest); local install is a real pip cp313-win_amd64 wheel; linux wheel manylinux_2_28",
    "refusal_codes": {"missing_locked_artifact": "REFUSED_ENVIRONMENT_IDENTITY:MISSING_WHEEL",
                      "hash_mismatch": "REFUSED_ENVIRONMENT_IDENTITY:WHEEL_HASH_MISMATCH",
                      "unexpected_package": "REFUSED_ENVIRONMENT_IDENTITY:UNEXPECTED_PACKAGE",
                      "wrong_version": "REFUSED_ENVIRONMENT_IDENTITY:VERSION_MISMATCH",
                      "wrong_python": "REFUSED_ENVIRONMENT_IDENTITY:PYTHON_MISMATCH",
                      "unsupported_platform": "REFUSED_ENVIRONMENT_IDENTITY:PLATFORM_UNSUPPORTED",
                      "unapproved_source": "REFUSED_ENVIRONMENT_IDENTITY:UNAPPROVED_SOURCE"},
    "no_fallback_to_unpinned_public_package": True,
}
open("dependency-resolution-report.json", "w", encoding="utf-8", newline="\n").write(
    json.dumps(report, sort_keys=True, indent=1) + "\n")

print("wheels:", len(entries))
print("requirements.lock sha:", sha("requirements.lock")[:16])
print("wheelhouse-manifest sha:", sha("wheelhouse-manifest.json")[:16])
print("resolution-report sha:", sha("dependency-resolution-report.json")[:16])
