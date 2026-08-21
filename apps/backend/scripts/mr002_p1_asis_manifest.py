"""MR-002 P1 / track T1 — the machine-readable AS-IS Stage-3 manifest.

Governing protocol: `MR002_P1_NumericalInvestigation_Protocol_v1.0` (docs/design/MR002/P1/).
Plan authority: MR-002 Next-Phase Guidance and Implementation Plan v1.0, P1 detailed task 1 —
"Inventory the exact current Stage-3 cascade, certificates, solver profiles, exception/status
mapping, scaling/conditioning and acceptance taxonomy. Produce a machine-readable as-is manifest."

WHY THIS IS PURELY STATIC. The manifest is an inventory of what the frozen source *says*, and it
must be reproducible by any reviewer on any machine — including one without `quadprog`, `piqp`,
`clarabel` or `mpmath`, none of which are installed outside the pinned research image. So this
script reads FILE BYTES and parses them with `ast`. It imports no research module and calls no
solver, which also guarantees it can never touch a corpus, a dataset, or a sealed reader.

DUAL IDENTITY. Governance hashes derived from a Windows worktree fail closed against an LF
deployment (CRLF), so every file records BOTH:
    sha256_worktree  the bytes as they sit on this filesystem
    sha256_lf        the same bytes with CRLF normalised to LF  <-- the portable identity
    git_blob         `git hash-object` of the worktree file, for cross-reference to Git
Compare `sha256_lf` across environments; `sha256_worktree` is diagnostic only.

Development domain only. Opens no sealed reader, no validation store, no OOS, no corpus.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "apps" / "backend"

OUT = REPO / "docs" / "design" / "MR002" / "P1" / "MR002_P1_Stage3_AsIsManifest_v1.0.json"

#: Every source file that participates in a Stage-3 resolution, by role. The manifest is only as
#: honest as this list, so roles are named explicitly rather than globbed.
INVENTORY: dict[str, list[str]] = {
    "disposition_layer_v1": [
        "apps/backend/app/research/mr002/stage3_cascade.py",
        "apps/backend/app/research/mr002/stage3_route.py",
    ],
    "disposition_layer_v2": [
        "apps/backend/app/research/mr002/n1/method.py",
        "apps/backend/app/research/mr002/n1/seam.py",
        "apps/backend/app/research/mr002/n1/reference.py",
    ],
    "acceptance_authority": [
        "apps/backend/app/research/mr002/certificate.py",
        "apps/backend/scripts/mr002_coverage_signed_gap.py",
    ],
    "problem_construction": [
        "apps/backend/app/research/mr002/joint_portfolio.py",
        "apps/backend/app/research/mr002/portfolio.py",
    ],
    "generators": [
        "apps/backend/scripts/mr002_piqp.py",
        "apps/backend/scripts/mr002_solver_intersection.py",
        "apps/backend/scripts/mr002_characterize_native_qp.py",
    ],
    "repair_paths": [
        "apps/backend/app/research/mr002/repair.py",
        "apps/backend/app/research/mr002/exact_repair.py",
        "apps/backend/app/research/mr002/exact_simplex.py",
    ],
}

#: (file, module-level name) pairs whose VALUE is part of the frozen numerical/acceptance contract.
#: Literal values are evaluated; anything non-literal is recorded as source text, never guessed.
FROZEN_CONSTANTS: list[tuple[str, str]] = [
    ("apps/backend/scripts/mr002_solver_intersection.py", "LIMITS"),
    ("apps/backend/scripts/mr002_solver_intersection.py", "REGISTERED_CORPUS_HASH"),
    ("apps/backend/scripts/mr002_piqp.py", "LIMITS"),
    ("apps/backend/scripts/mr002_piqp.py", "GAP_MAX"),
    ("apps/backend/scripts/mr002_piqp.py", "INF"),
    ("apps/backend/scripts/mr002_piqp.py", "BASE"),
    ("apps/backend/scripts/mr002_piqp.py", "PROFILES"),
    ("apps/backend/app/research/mr002/certificate.py", "SIGNED_GAP_MAX"),
    ("apps/backend/app/research/mr002/certificate.py", "MAX_INTERVAL_WIDTH"),
    ("apps/backend/app/research/mr002/joint_portfolio.py", "HESSIAN_CONDITION_MAX"),
    ("apps/backend/app/research/mr002/joint_portfolio.py", "LP_OPTIONS"),
    ("apps/backend/app/research/mr002/stage3_cascade.py", "CLOSED_ENUM"),
    ("apps/backend/app/research/mr002/stage3_cascade.py", "DEFAULT_FOR_UNRECOGNIZED"),
    ("apps/backend/app/research/mr002/stage3_cascade.py", "PRIMARY_SOLVER_ID"),
    ("apps/backend/app/research/mr002/stage3_cascade.py", "FALLBACK_SOLVER_ID"),
    ("apps/backend/app/research/mr002/stage3_cascade.py", "NUMERICAL_ALLOWLIST"),
    ("apps/backend/app/research/mr002/stage3_cascade.py", "REQUIRED_CERT_FIELDS"),
    ("apps/backend/app/research/mr002/n1/method.py", "GENERATOR_OUTCOMES"),
    ("apps/backend/app/research/mr002/n1/method.py", "REGISTERED_TERMINATION_REASONS"),
    ("apps/backend/app/research/mr002/n1/method.py", "RESOLVED_DISPOSITIONS"),
    ("apps/backend/app/research/mr002/n1/method.py", "SOLVER_LIBRARY_ROOTS"),
    ("apps/backend/app/research/mr002/n1/method.py", "OUR_ROOTS"),
    ("apps/backend/app/research/mr002/n1/method.py", "LIBRARY_BOUNDARIES"),
    ("apps/backend/scripts/mr002_coverage_signed_gap.py", "PRIMARY"),
    ("apps/backend/scripts/mr002_coverage_signed_gap.py", "FALLBACK"),
]


# ── identity ─────────────────────────────────────────────────────────────────────────────────────
def identities(path: Path) -> dict:
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    try:
        blob = subprocess.run(["git", "hash-object", str(path)], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 — git absence is not a manifest failure
        blob = None
    return {
        "bytes": len(raw),
        "crlf": b"\r\n" in raw,
        "sha256_worktree": hashlib.sha256(raw).hexdigest(),
        "sha256_lf": hashlib.sha256(lf).hexdigest(),
        "git_blob": blob,
    }


def tracked(rel: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO,
                       capture_output=True, text=True)
    return r.returncode == 0


# ── static extraction ────────────────────────────────────────────────────────────────────────────
def module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_bytes().decode("utf-8"), filename=str(path))


def top_level_assignments(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level `NAME = value` and `NAME: T = value`, last binding wins."""
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out[tgt.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            out[node.target.id] = node.value
    return out


def render_value(expr: ast.expr) -> dict:
    """Literal where possible; otherwise the exact source text. Never a guess."""
    try:
        value = ast.literal_eval(expr)
        return {"kind": "literal", "value": jsonable(value)}
    except (ValueError, SyntaxError, TypeError):
        return {"kind": "expression", "source": ast.unparse(expr)}


def jsonable(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [jsonable(x) for x in v]
    return repr(v)


def callables_of(tree: ast.Module) -> list[dict]:
    """Every module-level function/class, with its own source identity."""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            src = ast.unparse(node).encode("utf-8")
            out.append({
                "name": node.name,
                "kind": type(node).__name__,
                "lineno": node.lineno,
                "sha256_unparsed": hashlib.sha256(src).hexdigest(),
                "docstring_first_line": (ast.get_docstring(node) or "").split("\n")[0][:200],
            })
    return out


def raises_in(tree: ast.Module) -> list[dict]:
    """Every `raise <Cls>(...)` with the enclosing function — the exception surface a disposition
    layer has to classify. Structural: the message is recorded, never used for matching."""
    out: list[dict] = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.fn: list[str] = []

        def visit_FunctionDef(self, node):  # noqa: N802
            self.fn.append(node.name)
            self.generic_visit(node)
            self.fn.pop()

        visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

        def visit_Raise(self, node):  # noqa: N802
            exc = node.exc
            cls = None
            arg = None
            if isinstance(exc, ast.Call):
                cls = ast.unparse(exc.func)
                if exc.args:
                    arg = ast.unparse(exc.args[0])
            elif exc is not None:
                cls = ast.unparse(exc)
            out.append({"function": self.fn[-1] if self.fn else "<module>",
                        "exception": cls, "first_arg": arg, "lineno": node.lineno})
            self.generic_visit(node)

    V().visit(tree)
    return out


# ── the derived cross-layer comparison ───────────────────────────────────────────────────────────
def taxonomy_comparison() -> dict:
    """The single most decision-relevant fact T1 can state statically: the SAME generator event is
    classified differently by the two disposition layers that exist in the tree.

    Derived clause-by-clause from the sources, not asserted:
      v1 `stage3_cascade.normalize` — an exception is looked up in NUMERICAL_ALLOWLIST keyed by
         (solver_id, exact class object, exact message). A miss is INTEGRITY_DEFECT. The allowlist
         holds exactly one entry, scoped to QUADPROG_SQRT, so PIQP_P2 has NO registered numerical
         status and every PIQP raise is an integrity defect.
      v2 `n1.method.classify_exception` — an exception is attributed STRUCTURALLY by its deepest
         Python frame. `scripts.mr002_piqp:solve_piqp` is a registered LIBRARY_BOUNDARY, so a PIQP
         raise is NO_CERTIFIED_CANDIDATE with a registered reason read from the status OBJECT.
    """
    return {
        "record_type": "MR002_P1_DISPOSITION_TAXONOMY_COMPARISON",
        "version": "1.0",
        "event_under_comparison": {
            "generator": "PIQP_P2",
            "raise_site": "scripts.mr002_piqp.solve_piqp",
            "raise_form": "RuntimeError(f'status {st}')  for any st != piqp.PIQP_SOLVED",
            "instance_status": "piqp.PIQP_MAX_ITER_REACHED",
        },
        "v1_stage3_cascade": {
            "classifier": "app.research.mr002.stage3_cascade.normalize",
            "match_rule": "exact (solver_id, exception class OBJECT, complete message) lookup in "
                          "NUMERICAL_ALLOWLIST; identity match, no substring/regex/subclass",
            "registered_numerical_statuses_for_PIQP_P2": 0,
            "enum": "INTEGRITY_DEFECT",
            "code": "UNREGISTERED_EXCEPTION:RuntimeError:status Status.PIQP_MAX_ITER_REACHED",
            "terminal_disposition": "INVALID_RUN",
            "stop": True,
            "meaning": "an integrity/provenance defect — the evaluation system is impugned",
        },
        "v2_n1_method": {
            "classifier": "app.research.mr002.n1.method.classify_exception",
            "match_rule": "structural provenance of the deepest Python frame; registered "
                          "LIBRARY_BOUNDARIES; reason read from the status OBJECT, never the message",
            "outcome": "NO_CERTIFIED_CANDIDATE",
            "reason": "ITERATION_LIMIT_REACHED",
            "terminal_disposition_when_A_also_uncertified": "UNRESOLVED_INSTANCE",
            "stop": True,
            "meaning": "a legitimate generator termination — no candidate was produced",
        },
        "consequential_difference": (
            "Both layers STOP the run. The difference is what the stop MEANS and therefore what may "
            "be concluded: v1 INVALID_RUN asserts an integrity defect in the evaluation system; v2 "
            "UNRESOLVED_INSTANCE asserts the frozen pair could not resolve the instance. Neither "
            "produces an economic verdict."
        ),
        "not_a_repair_claim": (
            "This comparison does NOT assert that adopting v2 would have produced a Validation-2 "
            "economic verdict. Under v2 the same event yields UNRESOLVED_INSTANCE, which raises "
            "Stage3StopV2 and ends the run. Establishing what the frozen pair can and cannot "
            "resolve is P1 track T3/T6 work, not a corollary of the taxonomy comparison."
        ),
        "which_layer_ran_in_validation_2": {
            "answer": "v1",
            "evidence": "the sealed terminal names the frame `stage3_route._routed_solve_qp`; the "
                        "v2 seam's frame is `n1.seam._routed`. `UNREGISTERED_EXCEPTION` is emitted "
                        "only by stage3_cascade.normalize.",
            "sealed_record": "TerminalOutcome v1.0 "
                             "9c08bfc5cb18d683beeb347243fb657cc24d37d925ad06d5409b76979d5fa53b, "
                             "commit 7a6b6f7",
            "status": "OBSERVATION — the reason the v1 layer was the bound path in the Validation-2 "
                      "execution package is NOT DETERMINED by this manifest and is a named P1 "
                      "question.",
        },
    }


def main() -> int:
    files: dict[str, dict] = {}
    constants: dict[str, dict] = {}
    missing: list[str] = []

    for role, rels in INVENTORY.items():
        for rel in rels:
            p = REPO / rel
            if not p.exists():
                missing.append(rel)
                continue
            tree = module_ast(p)
            files[rel] = {
                "role": role,
                "identity": identities(p),
                "git_tracked": tracked(rel),
                "module_docstring_first_line": (ast.get_docstring(tree) or "").split("\n")[0][:300],
                "callables": callables_of(tree),
                "raise_sites": raises_in(tree),
            }

    for rel, name in FROZEN_CONSTANTS:
        p = REPO / rel
        if not p.exists():
            constants.setdefault(rel, {})[name] = {"kind": "file_missing"}
            continue
        assigns = top_level_assignments(module_ast(p))
        constants.setdefault(rel, {})[name] = (
            render_value(assigns[name]) if name in assigns else {"kind": "not_found"}
        )

    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                                    capture_output=True, text=True, check=True).stdout.strip())
    except Exception:  # noqa: BLE001
        commit = branch = None
        dirty = None

    manifest = {
        "record_type": "MR002_P1_STAGE3_ASIS_MANIFEST",
        "version": "1.0",
        "phase": "P1",
        "track": "T1",
        "governing_protocol": "MR002_P1_NumericalInvestigation_Protocol_v1.0",
        "governing_prior_sha256":
            "3e1e491533a2aeb1a370610dc9854f5ea5a592d71fdff95dd0ec88e8e1536ee2",
        "generator": "apps/backend/scripts/mr002_p1_asis_manifest.py",
        "data_scope": "DEVELOPMENT_SOURCE_ONLY — no solver imported, no corpus, dataset, sealed "
                      "reader, validation store or OOS opened",
        "source": {"commit": commit, "branch": branch, "worktree_dirty": dirty},
        "python": sys.version.split()[0],
        "identity_convention": {
            "compare_across_environments_using": "sha256_lf",
            "sha256_worktree": "diagnostic only — CRLF worktrees do not match an LF deployment",
        },
        "files": files,
        "missing_files": missing,
        "frozen_constants": constants,
        "taxonomy_comparison": taxonomy_comparison(),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8")
    # Self-identity: the record carries the SHA-256 of its own body, appended after the body is
    # fixed, so the identity can be reproduced by stripping the final field.
    manifest["record_sha256_of_body_without_this_field"] = hashlib.sha256(body).hexdigest()
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_bytes(json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
    tmp.replace(OUT)

    print(f"files inventoried   {len(files)}")
    print(f"missing             {missing or 'none'}")
    print(f"frozen constants    {sum(len(v) for v in constants.values())}")
    print(f"body sha256         {manifest['record_sha256_of_body_without_this_field']}")
    print(f"wrote               {OUT.relative_to(REPO)}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
