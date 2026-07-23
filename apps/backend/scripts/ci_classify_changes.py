#!/usr/bin/env python3
"""CI change classifier — the single source of truth for "does this PR require the FULL suite?".

The CI workflow runs LIGHT on pull requests (ruff + mypy + fast invariant checks) and reserves the
slow FULL suite (pytest + coverage gates) for push-to-main / nightly / dispatch. That split let a PR
touching backend code merge green while its pytest was red (the failure only surfaced post-merge on
main). This module closes that gap: on a PR, if ANY testable backend/deployment path changed, the
workflow runs the FULL suite on the PR so a red suite blocks merge (behind the `Backend CI Gate`).

It is deliberately a small, pure, UNIT-TESTED function so the classification rule is verifiable off
GitHub and cannot silently drift. The workflow feeds it the PR's changed-file list (JSON array) and
consumes the single token it prints: `true` (FULL required) or `false` (LIGHT sufficient).

FAIL CLOSED: any malformed input / unexpected error exits non-zero so the classifier step fails, which
makes the `Backend CI Gate` fail closed rather than wave a PR through unclassified.
"""

from __future__ import annotations

import json
import sys
from fnmatch import fnmatch

# Paths whose change means the backend FULL suite must run (owner-authorized policy, 2026-07-23).
# `dir/**`      → that directory tree (and the dir itself)
# `**/name`     → a file with that basename anywhere (root or nested)
# exact string  → that exact path
CODE_PATTERNS: tuple[str, ...] = (
    "apps/backend/**",           # all backend code AND tests (a test change IS a code change)
    "deploy/**",                 # deploy scripts are exercised by the backend test suite
    "scripts/**",                # repo-root operational scripts
    "tests/**",                  # repo-root tests, if any
    "**/pyproject.toml",         # dependency / build config
    "**/requirements*.txt",
    "**/poetry.lock",
    "**/uv.lock",
    "**/alembic.ini",            # migration config
    ".github/workflows/ci.yml",  # a workflow change re-verifies everything
)


def _matches(path: str, pattern: str) -> bool:
    """Match one POSIX repo-relative path against one CODE_PATTERNS entry."""
    path = path.strip()
    if path.startswith("./"):            # strip a leading "./" only — never the "." of ".github"
        path = path[2:]
    if not path:
        return False
    if pattern.endswith("/**"):
        base = pattern[:-3]
        return path == base or path.startswith(base + "/")
    if pattern.startswith("**/"):
        # basename glob, matching the file at the repo root or anywhere nested
        return fnmatch(path.rsplit("/", 1)[-1], pattern[3:])
    return path == pattern


def requires_full(changed_paths: list[str]) -> bool:
    """True iff any changed path is a testable backend/deployment path (⇒ run the FULL suite)."""
    return any(_matches(p, pat) for p in changed_paths for pat in CODE_PATTERNS)


def _load(argv: list[str]) -> list[str]:
    """Load the changed-file list from a JSON file path (argv[1]) or from stdin. The JSON must be an
    array of strings (as emitted by dorny/paths-filter `list-files: json`)."""
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
    print("true" if requires_full(paths) else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
