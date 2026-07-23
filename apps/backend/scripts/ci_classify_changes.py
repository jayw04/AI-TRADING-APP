#!/usr/bin/env python3
"""CI change classifier — the single source of truth for which Python projects need their FULL suite.

The CI workflow runs LIGHT on pull requests (ruff + mypy + fast invariant checks) and reserves the slow
FULL suite (pytest + coverage gates) for push-to-main / nightly / dispatch. That split let a PR touching
Python code merge green while its pytest was red (the failure only surfaced post-merge on main). This
module closes that gap PER PROJECT: on a PR, for each Python project whose testable paths changed, the
workflow runs that project's FULL suite on the PR so a red suite blocks merge (behind `Python CI Gate`).

It is deliberately a small, pure, UNIT-TESTED function so the classification rule is verifiable off
GitHub and cannot silently drift. The changed-file list arrives as untrusted data (a JSON array from a
pull request) and is treated as data ONLY — never interpolated into a shell. The CLI prints one
`<project>_code=<true|false>` line per project, ready to append to `$GITHUB_OUTPUT`.

FAIL CLOSED: any malformed input / unexpected error exits non-zero and prints nothing to stdout, so the
classifier step fails, which makes `Python CI Gate` fail closed rather than wave a PR through.
"""

from __future__ import annotations

import json
import sys
from fnmatch import fnmatch

# The Python projects, in output order. Keys are underscore-form (output names); dir names differ.
PROJECTS: tuple[str, ...] = ("backend", "mcp_server", "mcp_workbench", "agent")

# GLOBAL paths force the FULL suite for EVERY project (a change here can affect any project's tests).
# Root-level dependency/build manifests are global; each project's OWN nested manifest is attributed to
# that project below (via `apps/<project>/**`).
GLOBAL_PATTERNS: tuple[str, ...] = (
    ".github/workflows/ci.yml",   # a workflow change re-verifies everything
    "pyproject.toml",             # ROOT build/dependency config
    "requirements*.txt",
    "poetry.lock",
    "uv.lock",
)

# Per-project ownership. A change under one of these ⇒ that project's FULL suite runs.
PROJECT_PATTERNS: dict[str, tuple[str, ...]] = {
    "backend": (
        "apps/backend/**",        # backend source AND tests (a test change IS a code change)
        "deploy/**",              # deploy scripts are exercised by the backend test suite
        "scripts/**",             # repo-root operational scripts
        "tests/**",               # repo-root tests, if any
        "**/alembic.ini",         # migration config
    ),
    "mcp_server": ("apps/mcp-server/**",),
    "mcp_workbench": ("apps/mcp-workbench/**",),
    "agent": ("apps/agent/**",),
}


def _matches(path: str, pattern: str) -> bool:
    """Match one POSIX repo-relative path against one pattern. Supported forms:
    `dir/**` (tree), `**/name` (basename anywhere), a slash-less root glob (root-level file only),
    and an exact path."""
    path = path.strip()
    if path.startswith("./"):            # strip a leading "./" only — never the "." of ".github"
        path = path[2:]
    if not path:
        return False
    if pattern.endswith("/**"):
        base = pattern[:-3]
        return path == base or path.startswith(base + "/")
    if pattern.startswith("**/"):
        return fnmatch(path.rsplit("/", 1)[-1], pattern[3:])
    if "/" not in pattern:               # root-level file (exact or glob): only a slash-less path
        return "/" not in path and fnmatch(path, pattern)
    return path == pattern


def classify(changed_paths: list[str]) -> dict[str, bool]:
    """Return {project: needs_full} for every Python project. A GLOBAL-path change flags all projects."""
    if any(_matches(p, pat) for p in changed_paths for pat in GLOBAL_PATTERNS):
        return dict.fromkeys(PROJECTS, True)
    return {
        proj: any(_matches(p, pat) for p in changed_paths for pat in PROJECT_PATTERNS[proj])
        for proj in PROJECTS
    }


def requires_full(changed_paths: list[str]) -> bool:
    """True iff ANY Python project needs its FULL suite (convenience for callers/tests)."""
    return any(classify(changed_paths).values())


def _load(argv: list[str]) -> list[str]:
    """Load the changed-file list from a JSON file path (argv[1]) or stdin. Must be a JSON array of
    strings (as emitted by dorny/paths-filter `list-files: json`). Filenames are DATA, never executed."""
    if len(argv) < 2 or argv[1] == "-":
        raw = sys.stdin.read()
    else:
        with open(argv[1], encoding="utf-8") as fh:
            raw = fh.read()
    raw = raw.strip() or "[]"
    data = json.loads(raw)
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise ValueError("expected a JSON array of path strings")
    return data


def main(argv: list[str]) -> int:
    try:
        paths = _load(argv)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        # FAIL CLOSED: unknown/unparseable input must not be treated as "no code changed".
        print(f"ci_classify_changes: cannot classify changes: {exc}", file=sys.stderr)
        return 2
    flags = classify(paths)
    for proj in PROJECTS:
        print(f"{proj}_code={'true' if flags[proj] else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
