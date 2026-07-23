"""ADR-0043 deploy-provenance guard — verify a curated ENFORCE-box deploy source (blob-exact).

WHY THIS EXISTS
The first canary artifact enforced one rule: the deployed ``apps/**`` tree must equal the ADR-0043
implementation baseline (PR8, ``c8b3ac24``) byte-for-byte. That was right then. It is now too strict:
the separately reviewed settlement-barrier extension (#463) legitimately ADDS ``apps/**`` code. But
loosening the rule the wrong way is dangerous — the squash-merge governance commit ``ea6db6e`` is the
full ``origin/main`` tip and carries UNRELATED main-line changes (ADR-0044, a new Alembic migration,
momentum-daily sizing, drift-audit, risk-path deltas). Deploying it would ride all of that into the
isolated ENFORCE validation box, which is exactly what the curated ``80a6c043`` lineage was built to
prevent.

So the gate evolves from "apps == implementation baseline" to:

    apps == implementation baseline  +  the EXPLICITLY APPROVED settlement-barrier delta, and nothing else.

The reviewed executable tree is ``07d3b82`` — the curated descendant of the prior deploy lineage,
NOT main. This is not deploying an unmerged feature: the feature is merged and governed by
``ea6db6e``; ``07d3b82`` is the exact reviewed executable tree that was protected at merge time.

WHAT IT ENFORCES (all must hold, else it refuses):
  1. SOURCE IS THE CURATED COMMIT. The source resolves to EXACTLY
     ``validation_executable_baseline`` — never ``main``, ``HEAD``, a short prefix, or any other ref.
  2. LINEAGE. Both ``implementation_baseline`` and ``prior_deploy_baseline`` are ancestors of the
     validation executable baseline.
  3. NO MIGRATION. No file under a migration path glob changed between prior deploy and the baseline
     (``migration_delta_allowed`` is false).
  4. NO UNAPPROVED DELTA. Every path that changed between prior deploy and the baseline is in the
     approved application inventory (if under ``apps/**``) or the approved operational inventory
     (otherwise). An extra path — of either kind — is a refusal.
  5. BLOB-EXACT CONTENT. Every approved path's git blob at the baseline equals the frozen SHA in the
     manifest. Path membership is not enough; the CONTENT is pinned, so an approved file cannot be
     swapped for a different revision that happens to keep the same path.
  6. MANIFEST INTEGRITY. The manifest exists, parses, and carries every required field.

Runs from the repo root (or pass ``--repo``):
    python3 deploy/aws/verify_deploy_provenance.py <source-ref>
Exit 0 = the source is the approved curated commit and its delta is blob-exact. Nonzero = refusal.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "adr0043_deploy_manifest.json"

REQUIRED_FIELDS = (
    "implementation_baseline",
    "prior_deploy_baseline",
    "validation_executable_baseline",
    "migration_delta_allowed",
    "migration_path_globs",
    "approved_application_paths",
    "approved_operational_paths",
)
APPS_PREFIX = "apps/"


class ManifestError(RuntimeError):
    """The manifest is missing or malformed — a refusal in its own right (no manifest, no build)."""


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str


def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    return proc.returncode, (proc.stdout or "").strip()


def resolve_commit(repo: Path, ref: str) -> str | None:
    code, out = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out if code == 0 and out else None


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    code, _ = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    return code == 0


def blob_sha(repo: Path, ref: str, path: str) -> str | None:
    code, out = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}:{path}")
    return out if code == 0 and out else None


def changed_paths(repo: Path, base: str, target: str) -> list[str]:
    code, out = _git(repo, "diff", "--name-only", base, target)
    if code != 0:
        raise ManifestError(f"git diff {base}..{target} failed: {out}")
    return [line for line in out.splitlines() if line.strip()]


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise ManifestError(f"manifest not found at {path}; no manifest, no build")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ManifestError(f"manifest missing required field(s): {', '.join(missing)}")
    if not isinstance(data["approved_application_paths"], dict) or not data[
        "approved_application_paths"
    ]:
        raise ManifestError("approved_application_paths must be a non-empty {path: blob} map")
    if not isinstance(data["approved_operational_paths"], dict):
        raise ManifestError("approved_operational_paths must be a {path: blob} map")
    return data


def _is_migration(path: str, globs: list[str]) -> bool:
    return any(path.startswith(g) for g in globs)


def verify(source_ref: str, manifest: dict, repo: Path) -> list[Violation]:
    """The whole gate, as a list of violations (empty == approved). Pure over (ref, manifest, repo)
    so the tests can drive it against synthetic curated and contaminated trees."""
    v: list[Violation] = []
    baseline = manifest["validation_executable_baseline"]
    impl = manifest["implementation_baseline"]
    prior = manifest["prior_deploy_baseline"]
    app_paths: dict[str, str] = manifest["approved_application_paths"]
    op_paths: dict[str, str] = manifest["approved_operational_paths"]
    mig_globs: list[str] = manifest["migration_path_globs"]
    mig_allowed: bool = bool(manifest["migration_delta_allowed"])

    # --- 1. source is the curated commit, exactly ---
    resolved_source = resolve_commit(repo, source_ref)
    resolved_baseline = resolve_commit(repo, baseline)
    if resolved_baseline is None:
        v.append(Violation("baseline-unresolved",
                           f"validation_executable_baseline {baseline} does not resolve to a commit"))
        return v  # nothing else is meaningful without the baseline
    if resolved_source is None:
        v.append(Violation("source-unresolved", f"source ref {source_ref!r} does not resolve"))
        return v
    if resolved_source != resolved_baseline:
        v.append(Violation(
            "source-not-curated-commit",
            f"source {resolved_source} != validation_executable_baseline {resolved_baseline}; "
            f"the archive source must be the explicit curated commit, never main/HEAD/another ref"))
        return v  # every downstream check is about the baseline; a wrong source is fatal on its own

    # --- 2. lineage ---
    for name, sha in (("implementation_baseline", impl), ("prior_deploy_baseline", prior)):
        rc = resolve_commit(repo, sha)
        if rc is None:
            v.append(Violation("lineage-unresolved", f"{name} {sha} does not resolve to a commit"))
        elif not is_ancestor(repo, sha, resolved_baseline):
            v.append(Violation(
                "lineage-broken",
                f"{name} {sha} is not an ancestor of the validation executable baseline"))

    # --- 3/4. classify every changed path prior_deploy -> baseline ---
    delta = changed_paths(repo, prior, resolved_baseline)
    for path in delta:
        if _is_migration(path, mig_globs) and not mig_allowed:
            v.append(Violation("migration-changed",
                               f"migration file changed but migration_delta_allowed is false: {path}"))
            continue
        if path.startswith(APPS_PREFIX):
            if path not in app_paths:
                v.append(Violation(
                    "unapproved-application-path",
                    f"apps/** path changed but is not in the approved application inventory: {path}"))
        else:
            if path not in op_paths:
                v.append(Violation(
                    "unapproved-operational-path",
                    f"non-application path changed but is not in the approved operational "
                    f"inventory: {path}"))

    # --- 5. blob-exact content for EVERY approved path (membership is not enough) ---
    for kind, table in (("application", app_paths), ("operational", op_paths)):
        for path, expected in table.items():
            actual = blob_sha(repo, resolved_baseline, path)
            if actual is None:
                v.append(Violation(
                    "approved-path-missing",
                    f"approved {kind} path is absent at the baseline: {path}"))
            elif actual != expected:
                v.append(Violation(
                    "blob-mismatch",
                    f"approved {kind} path {path}: baseline blob {actual} != manifest {expected}"))
    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ADR-0043 deploy-provenance guard")
    ap.add_argument("source_ref", help="the source ref to verify (must be the curated commit)")
    ap.add_argument("--repo", default=".", help="repository root (default: cwd)")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="path to the deploy manifest")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    try:
        manifest = load_manifest(Path(args.manifest))
    except ManifestError as exc:
        print(f"REFUSE: {exc}", file=sys.stderr)
        return 2

    violations = verify(args.source_ref, manifest, repo)
    if violations:
        print("ADR-0043 deploy-provenance guard REFUSES the source:", file=sys.stderr)
        for viol in violations:
            print(f"  [{viol.rule}] {viol.detail}", file=sys.stderr)
        print(
            "\nThe deployed risk-path tree must be the reviewed curated commit and nothing else. "
            "Building from main/HEAD, an unapproved delta, or a changed migration is refused. "
            "Changing the approved inventory requires review.",
            file=sys.stderr,
        )
        return 1

    print(
        "ADR-0043 deploy-provenance guard OK: source is the curated validation executable baseline "
        f"({manifest['validation_executable_baseline']}); delta from prior deploy "
        f"({manifest['prior_deploy_baseline']}) matches the approved inventory blob-for-blob "
        f"({len(manifest['approved_application_paths'])} application + "
        f"{len(manifest['approved_operational_paths'])} operational paths); no migration delta."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
