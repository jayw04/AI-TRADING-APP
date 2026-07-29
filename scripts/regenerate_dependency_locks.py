#!/usr/bin/env python3
"""Regenerate the committed per-project dependency resolutions (GITHUB-OPS-001).

This is the ONLY sanctioned way to produce ``constraints/*.txt``. It pins every input that
can change the output — Python line, target platform, extras, and the resolver version —
and stamps that tuple into each file so a reviewer can see what produced it and the drift
gate can verify it.

  python scripts/regenerate_dependency_locks.py              # all projects
  python scripts/regenerate_dependency_locks.py --only agent
  python scripts/regenerate_dependency_locks.py --check      # regenerate to temp, diff only

After regenerating, COMMIT the result and review the dependency diff in the PR. Never edit
a constraints file by hand: it is generated, hash-bearing, and the drift gate re-derives it.

ROLLBACK: ``git checkout <previous-commit> -- constraints/`` restores the previous resolved
graph exactly; every entry is version- and hash-pinned, so the restored environment is the
one that was previously reviewed and green.

Requires ``uv`` at the pinned version. Install with:
  pip install uv==0.12.0
On a machine behind a TLS-inspecting proxy, add --system-certs (see NETWORK note below).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS_DIR = REPO_ROOT / "constraints"

# ---- the governed resolution tuple -------------------------------------------------------
# Changing ANY of these changes the resolved graph. Keep in sync with
# scripts/check_dependency_locks.py, .github/workflows/ci.yml (python-version) and the
# Dockerfiles' PYTHON_VERSION.
GOVERNED_PYTHON = "3.12"
GOVERNED_PYTHON_FULL = "3.12.13"
GOVERNED_PLATFORM = "x86_64-unknown-linux-gnu"
GOVERNED_UV_VERSION = "0.12.0"
GOVERNED_EXTRAS = ("dev",)

PROJECTS: dict[str, str] = {
    "backend": "apps/backend",
    "mcp-server": "apps/mcp-server",
    "mcp-workbench": "apps/mcp-workbench",
    "agent": "apps/agent",
}


def header(project: str, directory: str) -> str:
    extras = ",".join(GOVERNED_EXTRAS)
    return (
        f"# GENERATED FILE - DO NOT EDIT BY HAND.\n"
        f"#\n"
        f"# Deterministic dependency resolution for '{project}' (GITHUB-OPS-001).\n"
        f"# Regenerate with: python scripts/regenerate_dependency_locks.py --only {project}\n"
        f"#\n"
        f"# Governed resolution tuple - the output is only valid for exactly this:\n"
        f"#   python        : CPython {GOVERNED_PYTHON_FULL} (line {GOVERNED_PYTHON}, "
        f"requires-python >=3.12,<3.13)\n"
        f"#   platform      : {GOVERNED_PLATFORM}\n"
        f"#   resolver      : uv {GOVERNED_UV_VERSION}\n"
        f"#   source        : {directory}/pyproject.toml\n"
        f"#   extras        : {extras}\n"
        f"#\n"
        f"# Installed in CI as:\n"
        f"#   pip install --require-hashes -r constraints/{project}-py312.txt\n"
        f"#   pip install --no-deps -e \"{directory}[{extras}]\"\n"
        f"#\n"
        f"# The local project is installed separately with --no-deps because it is repository\n"
        f"# source, not a downloadable third-party artifact with a package hash.\n"
        f"#\n"
    )


def uv_cmd() -> list[str]:
    exe = shutil.which("uv")
    if exe:
        return [exe]
    return [sys.executable, "-m", "uv"]


def check_uv_version() -> str | None:
    p = subprocess.run([*uv_cmd(), "--version"], capture_output=True, text=True)
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def compile_one(project: str, directory: str, dest: Path, system_certs: bool) -> None:
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw.txt"
        cmd = [
            *uv_cmd(), "pip", "compile", f"{directory}/pyproject.toml",
            *sum([["--extra", e] for e in GOVERNED_EXTRAS], []),
            "--python-version", GOVERNED_PYTHON,
            "--python-platform", GOVERNED_PLATFORM,
            "--generate-hashes",
            "--no-header",
            "--output-file", str(raw),
        ]
        if system_certs:
            cmd.append("--system-certs")
        p = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            print(f"ERROR: uv pip compile failed for {project}:\n{p.stderr[:1200]}", file=sys.stderr)
            raise SystemExit(1)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(header(project, directory) + raw.read_text(encoding="utf-8"), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="Comma-separated project names")
    ap.add_argument("--check", action="store_true", help="Regenerate to a temp dir and diff only")
    ap.add_argument(
        "--system-certs",
        action="store_true",
        help="Use the OS trust store. NETWORK: required on machines behind a TLS-inspecting "
             "proxy (e.g. the developer laptop running Norton), which otherwise fails with "
             "'invalid peer certificate: UnknownIssuer'. Does not affect resolution output.",
    )
    args = ap.parse_args(argv)

    ver = check_uv_version()
    if ver is None:
        print(f"ERROR: uv not found. Install the governed version: pip install uv=={GOVERNED_UV_VERSION}",
              file=sys.stderr)
        return 1
    if GOVERNED_UV_VERSION not in ver:
        print(f"ERROR: resolver version mismatch.\n  found:    {ver}\n"
              f"  governed: uv {GOVERNED_UV_VERSION}\n"
              f"A resolver upgrade can change the resolved graph even when no manifest changed.\n"
              f"Install the governed version (pip install uv=={GOVERNED_UV_VERSION}), or update "
              f"GOVERNED_UV_VERSION here and in scripts/check_dependency_locks.py and regenerate "
              f"ALL projects in one reviewed change.", file=sys.stderr)
        return 1

    selected = PROJECTS
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = want - set(PROJECTS)
        if unknown:
            print(f"ERROR: unknown project(s): {sorted(unknown)}", file=sys.stderr)
            return 1
        selected = {k: v for k, v in PROJECTS.items() if k in want}

    if args.check:
        drift = []
        with tempfile.TemporaryDirectory() as td:
            for project, directory in selected.items():
                tmp = Path(td) / f"{project}.txt"
                compile_one(project, directory, tmp, args.system_certs)
                cur = CONSTRAINTS_DIR / f"{project}-py312.txt"
                same = cur.is_file() and cur.read_text(encoding="utf-8") == tmp.read_text(encoding="utf-8")
                print(f"  {project:<16}{'up to date' if same else 'DRIFTED'}")
                if not same:
                    drift.append(project)
        if drift:
            print(f"\n{len(drift)} project(s) drifted: {drift}\n"
                  f"Regenerate: python scripts/regenerate_dependency_locks.py", file=sys.stderr)
            return 1
        print("\nall committed resolutions are up to date")
        return 0

    for project, directory in selected.items():
        dest = CONSTRAINTS_DIR / f"{project}-py312.txt"
        compile_one(project, directory, dest, args.system_certs)
        n = sum(1 for ln in dest.read_text(encoding="utf-8").splitlines() if "--hash=sha256:" in ln)
        print(f"  {project:<16}-> constraints/{dest.name}  ({n} hashes)")

    print(f"\nGenerated with uv {GOVERNED_UV_VERSION}, CPython {GOVERNED_PYTHON_FULL}, "
          f"{GOVERNED_PLATFORM}, extras={','.join(GOVERNED_EXTRAS)}")
    print("Commit constraints/ and review the dependency diff in the PR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
