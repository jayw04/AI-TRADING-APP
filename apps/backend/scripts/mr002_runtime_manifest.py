"""MR-002 — runtime / dependency manifest for the CERTIFIED image (owner ruling §6, §10).

The certificate introduces a new numerical dependency (arbitrary-precision interval arithmetic).
A gap asserted at 1e-10 from that arithmetic is only as trustworthy as the binary that computed
it, so the ruling binds: distribution version, wheel/source artifact SHA-256, installed
package-record hash, Python ABI, and the linux/amd64 image digest.

Runs INSIDE the research image, with networking disabled.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import sysconfig
from importlib.metadata import distribution, version
from pathlib import Path

PINNED = ["mpmath", "numpy", "scipy", "quadprog", "piqp", "clarabel", "highspy"]


def _file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _installed_tree_hash(dist) -> tuple[str, int]:
    """Hash the bytes actually on disk, not the RECORD's own claims.

    A RECORD file is metadata the package ships about itself; hashing the installed FILES is the
    thing that would actually catch a swapped binary. Both are recorded — RECORD separately below.
    """
    files = sorted(dist.files or [], key=lambda f: str(f))
    h = hashlib.sha256()
    n = 0
    for f in files:
        p = Path(dist.locate_file(f))
        if not p.is_file():
            continue
        h.update(str(f).encode())
        h.update(_file_sha256(p).encode())
        n += 1
    return h.hexdigest(), n


def main() -> int:
    out: dict = {
        "purpose": "MR-002 v1.1 Stage-3 certified dual-lower-bound gap",
        "python": {
            "version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "abi": sysconfig.get_config_var("SOABI"),
            "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "packages": {},
    }

    for name in PINNED:
        try:
            dist = distribution(name)
        except Exception:  # noqa: BLE001
            out["packages"][name] = {"present": False}
            continue

        record = None
        for meta in ("RECORD", "METADATA", "WHEEL"):
            p = Path(dist._path) / meta if hasattr(dist, "_path") else None   # noqa: SLF001
            if p and p.is_file() and meta == "RECORD":
                record = _file_sha256(p)

        tree_hash, n_files = _installed_tree_hash(dist)
        out["packages"][name] = {
            "present": True,
            "version": version(name),
            "record_sha256": record,             # the RECORD metadata file itself
            "installed_tree_sha256": tree_hash,  # the bytes actually on disk
            "installed_files": n_files,
        }

    # The image digest is not observable from inside the container; it is stamped by the caller.
    out["image"] = {
        "note": "linux/amd64 image digest is stamped by the build host — see the evidence report",
    }

    blob = json.dumps(out, indent=2, sort_keys=True)
    Path("/out/MR002_RuntimeManifest_Certified.json").write_text(blob, encoding="utf-8")
    print(blob)
    print("\nmanifest sha256:", hashlib.sha256(blob.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
