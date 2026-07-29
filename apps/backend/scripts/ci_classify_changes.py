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
`<project>_code=<true|false>` line per project plus an `adr0043_gate=<true|false>` line,
ready to append to `$GITHUB_OUTPUT`.

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
    # The committed deterministic resolutions (GITHUB-OPS-001). A change here alters the exact
    # third-party graph every project installs, so it must re-verify ALL of them — never just
    # the project whose file changed. Also covers the generator/gate, since a change to either
    # can alter or stop validating what lands in constraints/.
    "constraints/**",
    "scripts/regenerate_dependency_locks.py",
    "scripts/check_dependency_locks.py",
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


def requires_adr0043_by_backend_attribution(changed_paths: list[str]) -> bool:
    """True iff the ADR 0043 loss-control test + branch-coverage gate must run.

    NAME: this is **conservative backend attribution**, NOT a precise ADR-0043 risk-path
    classifier. It answers "could a backend change have moved this gate?", which is a
    deliberately wider question than "does this change touch loss control?". The name says
    so on purpose — do not rename it to something that implies precision it does not have.

    That gate runs `pytest tests/risk` with scoped branch coverage on
    `app.risk.loss_control` and enforces a 0.95 floor per module. It measured 96 s and
    fired on every backend LIGHT job (582 runs in July 2026 = 11.7% of the month's
    billable minutes), including on pull requests that could not possibly move it.

    **Only a change under the `backend` project's paths — or a GLOBAL path — can alter
    this gate's outcome.** `tests/risk` and `app.risk.loss_control` live entirely inside
    `apps/backend/`; nothing in the frontend, the three auxiliary Python projects, the
    docs tree, or the S3 manifests is imported by either. So the correct predicate is
    exactly the already-hardened, already-unit-tested `backend` attribution — reusing it
    rather than authoring a second, narrower risk-path list is deliberate: a bespoke list
    would add new path semantics whose failure mode is *skipping a gate that was needed*,
    which is the direction ADR 0043 exists to prevent.

    Two deliberate differences from ``classify(...)["backend"]``:

    * **An empty changeset returns True.** For FULL selection, "nothing changed" correctly
      means LIGHT. Here it means *the changed-file list could not be determined*, and
      classifier ambiguity must default upward — so the gate runs.
    * **It is a named, separately-tested signal.** If ADR 0043's blast radius is later
      narrowed (a genuinely separable risk-path subset), that change lands here with its
      own tests and its own before/after measurement, without touching FULL selection.

    ⚠ DO NOT "SIMPLIFY" THIS TO ``classify(paths)["backend"]``. The empty-changeset branch
    below looks redundant and is not: collapsing it silently converts an *undetermined*
    changed-file list from "run the gate" into "skip the gate", which is the precise
    failure ADR 0043 exists to prevent. The divergence is pinned by
    ``test_adr0043_gate_defaults_UP_on_an_empty_changeset``.

    Narrowing further is a *separate* PR with its own historical replay. Do not inline it.

    Measured (July 2026, 120-PR replay): fires on 80.8% of pull requests — that share is
    legitimate required execution, not waste. Avoidable portion ≈ 178 runner-min/month.
    """
    if not changed_paths:
        return True
    return classify(changed_paths)["backend"]


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
    # ADR 0043 gate selection (see requires_adr0043_by_backend_attribution for why it is separate).
    print(f"adr0043_gate={'true' if requires_adr0043_by_backend_attribution(paths) else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
