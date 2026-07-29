#!/usr/bin/env python3
"""Dependency-lock drift gate (GITHUB-OPS-001 deterministic resolution).

Fails CI when the committed resolutions in ``constraints/`` no longer correspond to the
project manifests, so a direct-dependency change cannot silently ship against a stale
locked graph. Fail-closed: anything unexpected is an error, never a pass.

Checks, in order of cost:

  1. Every governed project has a constraints file, and no orphan files exist.
  2. Every file declares the governed interpreter tuple in its header, and it matches
     ``GOVERNED_PYTHON`` / ``GOVERNED_PLATFORM`` / the pinned resolver version.
  3. Every project's ``requires-python`` equals the governed line.
  4. Every pinned package carries at least one ``--hash=sha256:`` (``--require-hashes``
     silently degrades to a normal install if a single entry lacks one).
  5. Every direct dependency declared in a manifest appears pinned in that project's file
     — the cheap, offline half of drift detection.
  6. With ``--recompile`` (nightly / on demand, needs network + uv): re-resolve and require
     the output to be byte-identical to what is committed.

Usage:
  python scripts/check_dependency_locks.py              # offline structural gate (PR CI)
  python scripts/check_dependency_locks.py --recompile  # full re-resolution parity
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS_DIR = REPO_ROOT / "constraints"

# The governed resolution tuple. Changing any of these REQUIRES regenerating every file.
GOVERNED_PYTHON = "3.12"
GOVERNED_PYTHON_FULL = "3.12.13"
GOVERNED_PLATFORM = "x86_64-unknown-linux-gnu"
GOVERNED_UV_VERSION = "0.12.0"
GOVERNED_REQUIRES_PYTHON = ">=3.12,<3.13"
GOVERNED_EXTRAS = ("dev",)

PROJECTS: dict[str, str] = {
    "backend": "apps/backend",
    "mcp-server": "apps/mcp-server",
    "mcp-workbench": "apps/mcp-workbench",
    "agent": "apps/agent",
}

PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", re.M)
BACKSLASH = chr(92)


def norm(name: str) -> str:
    """PEP 503 normalisation — `Foo_Bar.baz` and `foo-bar-baz` are the same project."""
    return re.sub(r"[-_.]+", "-", name).lower()


def constraints_path(project: str) -> Path:
    return CONSTRAINTS_DIR / f"{project}-py312.txt"


def direct_deps(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    proj = data.get("project", {})
    out: list[str] = list(proj.get("dependencies", []) or [])
    for extra in GOVERNED_EXTRAS:
        out += list((proj.get("optional-dependencies", {}) or {}).get(extra, []) or [])
    names = set()
    for spec in out:
        m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
        if m:
            names.add(norm(m.group(1)))
    return names


def pinned_names(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in PIN_RE.finditer(text):
        out[norm(m.group(1))] = m.group(2).rstrip(BACKSLASH).strip()
    return out


def unhashed(text: str) -> list[str]:
    """Pinned entries with no --hash line before the next pin."""
    bad, cur, seen = [], None, False
    for ln in text.splitlines():
        m = PIN_RE.match(ln)
        if m:
            if cur and not seen:
                bad.append(cur)
            cur, seen = m.group(1), False
        elif "--hash=sha256:" in ln and cur:
            seen = True
    if cur and not seen:
        bad.append(cur)
    return bad


def recompile_one(project: str, directory: str, out: Path) -> tuple[bool, str]:
    cmd = [
        "uv", "pip", "compile", f"{directory}/pyproject.toml",
        *sum([["--extra", e] for e in GOVERNED_EXTRAS], []),
        "--python-version", GOVERNED_PYTHON,
        "--python-platform", GOVERNED_PLATFORM,
        "--generate-hashes", "--no-header",
        "--output-file", str(out),
    ]
    p = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        return False, f"uv pip compile failed: {p.stderr.strip()[:300]}"
    return True, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recompile", action="store_true",
                    help="Re-resolve with uv and require byte-identical output (needs network)")
    args = ap.parse_args(argv)
    errors: list[str] = []

    if not CONSTRAINTS_DIR.is_dir():
        print(f"ERROR: missing {CONSTRAINTS_DIR}", file=sys.stderr)
        return 1

    expected = {constraints_path(p).name for p in PROJECTS}
    actual = {f.name for f in CONSTRAINTS_DIR.glob("*.txt")}
    for missing in sorted(expected - actual):
        errors.append(f"missing constraints file: constraints/{missing}")
    for orphan in sorted(actual - expected):
        errors.append(f"orphan constraints file (no such governed project): constraints/{orphan}")

    for project, directory in PROJECTS.items():
        cpath, ppath = constraints_path(project), REPO_ROOT / directory / "pyproject.toml"
        if not ppath.is_file():
            errors.append(f"{project}: missing {directory}/pyproject.toml")
            continue

        raw = ppath.read_text(encoding="utf-8")
        m = re.search(r'^requires-python\s*=\s*"([^"]*)"', raw, re.M)
        if not m:
            errors.append(f"{project}: no requires-python declared")
        elif m.group(1) != GOVERNED_REQUIRES_PYTHON:
            errors.append(
                f"{project}: requires-python is {m.group(1)!r}, governed line is "
                f"{GOVERNED_REQUIRES_PYTHON!r} — regenerate constraints/ if this is intentional"
            )

        if not cpath.is_file():
            continue
        text = cpath.read_text(encoding="utf-8")

        for label, value in (("python", GOVERNED_PYTHON_FULL),
                             ("platform", GOVERNED_PLATFORM),
                             ("uv", GOVERNED_UV_VERSION)):
            if value not in text:
                errors.append(
                    f"{cpath.name}: header does not record the governed {label} ({value}); "
                    "the file may have been generated outside the governed tuple"
                )

        if bad := unhashed(text):
            errors.append(f"{cpath.name}: {len(bad)} pinned entr(y/ies) without a sha256 hash: {bad[:5]}")

        pins = pinned_names(text)
        for dep in sorted(direct_deps(ppath)):
            if dep not in pins:
                errors.append(
                    f"{cpath.name}: direct dependency {dep!r} is declared in "
                    f"{directory}/pyproject.toml but is not pinned — regenerate the constraints file"
                )

    if args.recompile and not errors:
        with tempfile.TemporaryDirectory() as td:
            for project, directory in PROJECTS.items():
                out = Path(td) / f"{project}.txt"
                ok, why = recompile_one(project, directory, out)
                if not ok:
                    errors.append(f"{project}: {why}")
                    continue
                committed = constraints_path(project).read_text(encoding="utf-8")
                if out.read_text(encoding="utf-8") != committed:
                    errors.append(
                        f"{project}: re-resolution DIFFERS from the committed file — "
                        "the committed graph is not reproducible; regenerate and review the diff"
                    )

    if errors:
        print("dependency-lock gate FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("\nRegenerate with: python scripts/regenerate_dependency_locks.py", file=sys.stderr)
        return 1

    mode = "structural + re-resolution parity" if args.recompile else "structural (offline)"
    print(f"dependency-lock gate OK ({len(PROJECTS)} projects, {mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
