#!/usr/bin/env python
"""Freeze the SEC-001 V3 crawl driver: pre-package byte check, then digests.

Two controls, both adopted from failures on 2026-08-24.

**Pre-package byte identity (trap #1).** An archive built from a Windows checkout with
``core.autocrlf=true`` delivered CRLF bytes and the arrival gate rejected 5 of 6 blobs. The
rule adopted afterwards was: any archive whose gate requires Git byte identity must be built
from Git objects, or from a checkout *proven* to apply no filter — and the proof must run
before packaging, because the gate must not be the first place the divergence is detected.

This script is that proof. For each file it computes the blob SHA-1 from the raw worktree
bytes and compares it with the SHA-1 Git itself reports through ``git hash-object``, which
applies whatever filters ``.gitattributes`` and ``core.autocrlf`` dictate. If a filter is
touching the bytes, the two disagree and the freeze fails here — on the developer's machine,
minutes after the edit, rather than on the host after an upload.

**Declared-work completeness (trap #4).** A gate reported PASS while an entire section
silently did not execute. Every check below is registered up front in ``REGISTRY`` with an
exact expected count, and the run fails if the executed work does not match the declared
work — see ``app/altdata/sec001_v3/sections.py``.

Usage::

    python scripts/sec001_v3_freeze_driver.py [--out <path>]

Writes a freeze manifest and exits non-zero on any failure. Issues no network request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "apps" / "backend"
sys.path.insert(0, str(BACKEND))

from app.altdata.sec001_v3 import policy  # noqa: E402
from app.altdata.sec001_v3.forbidden import (  # noqa: E402
    FORBIDDEN_COVERAGE_FIELDS,
    ForbiddenCoverageField,
    dumps,
)
from app.altdata.sec001_v3.sections import GateRun, SectionSpec  # noqa: E402

#: The driver's frozen surface. Declaring it explicitly is what makes "a file was added and
#: nobody noticed" a failure rather than a silent widening of what got frozen.
PACKAGE_FILES: tuple[str, ...] = (
    "apps/backend/app/altdata/sec001_v3/__init__.py",
    "apps/backend/app/altdata/sec001_v3/driver.py",
    "apps/backend/app/altdata/sec001_v3/evidence.py",
    "apps/backend/app/altdata/sec001_v3/fetch.py",
    "apps/backend/app/altdata/sec001_v3/forbidden.py",
    "apps/backend/app/altdata/sec001_v3/policy.py",
    "apps/backend/app/altdata/sec001_v3/sections.py",
    "apps/backend/app/altdata/sec001_v3/spine.py",
    "apps/backend/app/altdata/sec001_v3/state.py",
)

#: Read but never modified — recorded so the freeze manifest pins what the driver composes
#: with. ``client.py`` must be the remediated ``6c1d7006…``, not the host's old ``258c570d``.
DEPENDENCY_PINS: dict[str, str] = {
    "apps/backend/app/altdata/sec/client.py": "6c1d7006f42f9e86121dce641af6cea525b235b8",
    "apps/backend/app/altdata/mr002/sic_history.py": "48779adaaaecfeffb9c6a32be8531f784d72058a",
    "apps/backend/app/altdata/mr002/__init__.py": "506870c6fadf6cc86f9a2a1b5441fe551841f435",
}

REGISTRY = (
    SectionSpec("package inventory", len(PACKAGE_FILES) + 1,
                "every declared file exists, and no undeclared file is present"),
    SectionSpec("pre-package byte identity", len(PACKAGE_FILES),
                "raw-byte blob SHA-1 == git-filtered blob SHA-1 (no CRLF filter in play)"),
    SectionSpec("dependency pins", len(DEPENDENCY_PINS),
                "composed-with blobs are the pinned, remediated versions"),
    SectionSpec("frozen policy surface", 7, "fair-access and scope constants"),
    SectionSpec("emission ban", 2, "the ten coverage names cannot be serialized"),
)


def git_blob_sha1(path: Path) -> str:
    """The SHA-1 Git would store, with all filters applied."""
    out = subprocess.run(
        ["git", "hash-object", "--", str(path)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def raw_blob_sha1(data: bytes) -> str:
    """The SHA-1 of the worktree bytes as-is, with no filter applied."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "design" / "SEC-001" / "SEC001_V3_CrawlDriver_Freeze.json"),
    )
    args = parser.parse_args()

    gate = GateRun(REGISTRY)
    entries: list[dict[str, object]] = []

    with gate.section("package inventory"):
        for rel in PACKAGE_FILES:
            gate.check(f"present {Path(rel).name}", (REPO_ROOT / rel).is_file(), rel)
        on_disk = sorted(
            p.relative_to(REPO_ROOT).as_posix()
            for p in (REPO_ROOT / "apps/backend/app/altdata/sec001_v3").glob("*.py")
        )
        gate.check("no undeclared file in the package",
                   on_disk == sorted(PACKAGE_FILES),
                   f"{len(on_disk)} on disk, {len(PACKAGE_FILES)} declared")

    with gate.section("pre-package byte identity"):
        for rel in PACKAGE_FILES:
            path = REPO_ROOT / rel
            data = path.read_bytes()
            raw = raw_blob_sha1(data)
            filtered = git_blob_sha1(path)
            crlf = data.count(b"\r\n")
            # Disagreement means a filter rewrote the bytes between worktree and object
            # store — the exact condition that cost the arrival gate a rebuild.
            ok = raw == filtered and crlf == 0
            gate.check(
                f"bytes unfiltered {Path(rel).name}", ok,
                f"raw={raw[:12]} git={filtered[:12]} crlf_pairs={crlf}",
            )
            entries.append({
                "path": rel,
                "bytes": len(data),
                "blob_sha1": filtered,
                "sha256": hashlib.sha256(data).hexdigest(),
                "crlf_pairs": data.count(b"\r\n"),
            })

    with gate.section("dependency pins"):
        for rel, expected in DEPENDENCY_PINS.items():
            actual = git_blob_sha1(REPO_ROOT / rel)
            gate.check(f"pinned {Path(rel).name}", actual == expected, actual[:12])

    with gate.section("frozen policy surface"):
        gate.check("rate limit 5.0 rps", policy.RATE_LIMIT_PER_SEC == 5.0)
        gate.check("halt on 403 only", policy.HALT_STATUSES == (403,))
        gate.check("cooldown >= 10 min", policy.HALT_COOLDOWN_SECONDS >= 600)
        gate.check("GET only", frozenset({"GET"}) == policy.ALLOWED_METHODS)
        gate.check("declared User-Agent", policy.USER_AGENT.startswith("TradingWorkbench SEC001-V3"))
        gate.check("forms exclude 8-K", "8-K" not in policy.FORMS, str(policy.FORMS))
        gate.check("outputs confined", policy.ALLOWED_OUTPUT_PREFIXES ==
                   (policy.RAW_PREFIX, policy.BUILD_PREFIX))

    with gate.section("emission ban"):
        gate.check("ten names registered", len(FORBIDDEN_COVERAGE_FIELDS) == 10)
        refused = 0
        for name in FORBIDDEN_COVERAGE_FIELDS:
            try:
                dumps({name: 1})
            except ForbiddenCoverageField:
                refused += 1
        gate.check("all ten refused by the serializer", refused == 10, f"{refused}/10")

    report = gate.finish()
    print(gate.render(report))

    manifest = {
        "artifact": "SEC-001 V3 classification crawl driver",
        "crawl_id": policy.CRAWL_ID,
        "capture_date": policy.CAPTURE_DATE,
        "files": entries,
        "dependency_pins": DEPENDENCY_PINS,
        "gate": report,
        "note": (
            "Freeze fingerprint only. No EDGAR request has been issued. The coverage-freeze "
            "token 5b26ffa2... is UNSPENT and is not referenced by this driver."
        ),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    print(f"\nfreeze manifest -> {out_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
