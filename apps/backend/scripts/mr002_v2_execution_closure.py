"""DERIVE the Validation-2 execution closure from the launcher. Do not hand-enumerate it.

The previous form of this artifact was a list of 20 library files. An enumeration is complete
until the deciding file is one step outside it, and twice in this program the omitted file was
the one that decided behaviour. So the closure is a RULE:

    every artifact whose value can select, or cause to be selected, any of --
    partition · object key · VersionId · window · fold geometry · authority or countersignature
    identity · solver or solver routing · gate threshold · terminal disposition ·
    custody / consumption status

Membership is DERIVED two ways and the two must agree on the code surface:

  1. STATIC IMPORT TRANSITIVE CLOSURE from the launcher, restricted to first-party `app.*`
     modules. This is what the launcher can execute.
  2. RUNTIME-READ ARTIFACTS the launcher opens by path (the tracked registry), which no import
     trace can find, because they are data rather than code.

Every member is then bound by SHA-256 OVER ITS GIT BLOB CONTENT (LF), and must carry at least
one category justifying its presence. A member that matches no category is reported as
UNJUSTIFIED rather than quietly dropped: it either needs a category or does not belong, and
that is a judgement for the record, not for this script.

⚠ IDENTITY TYPE. The values emitted here are SHA-256 over file CONTENT as stored in Git (LF).
They are NOT Git blob object ids (SHA-1 over "blob <len>\\0" + content). Never compare the two.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAUNCHER = "apps/backend/scripts/mr002_phase3c_validation_run.py"
BACKEND = "apps/backend"

# category -> substrings whose presence means the file can influence that category
CATEGORIES = {
    "partition": ("CONSUMED_PREFIX", "partition", "PARTITION_IDENTITY", "VALIDATION2_CONSUMING"),
    "object_key_or_versionid": ("version_id", "VersionId", "SEALED", ".parquet", "PinnedObject"),
    "window": ("VALIDATION_WINDOW", "SCORING_ELIGIBLE", "OUT_OF_BOUNDS_AFTER", "day_inputs",
               "session"),
    "fold_geometry": ("FROZEN_FOLDS", "verify_assignment", "fold"),
    "authority_identity": ("ProspectiveRegistration", "Countersignature", "COUNTERSIGNATURE",
                           "authorization", "93ee4688"),
    "solver_or_routing": ("routed", "census", "QUADPROG", "PIQP", "solve_qp", "stage3_route",
                          "disposition"),
    "gate_threshold": ("evaluate(", "threshold", "positive_folds", "net_profitable", "sharpe",
                       "Sharpe"),
    "terminal_disposition": ("terminal(", "COMPLETED", "FAILED", "verdict"),
    "custody_or_consumption": ("EvidenceJournal", "JournalingReader", "opened_object_ledger",
                               "row_hash", "prev_hash", "sha256", "consuming"),
}


def git_blob_text(path: str) -> str:
    return subprocess.run(["git", "show", f"HEAD:{path}"], cwd=REPO, check=True,
                          capture_output=True).stdout.decode("utf-8")


def git_blob_bytes(path: str) -> bytes:
    return subprocess.run(["git", "show", f"HEAD:{path}"], cwd=REPO, check=True,
                          capture_output=True).stdout


def module_to_path(mod: str) -> str | None:
    base = mod.replace(".", "/")
    for cand in (f"{BACKEND}/{base}.py", f"{BACKEND}/{base}/__init__.py"):
        try:
            git_blob_bytes(cand)
            return cand
        except subprocess.CalledProcessError:
            continue
    return None


# The SUPERSEDED enumeration this closure replaces. Kept only so the derived closure can be
# DIFFED against it and every difference explained. A silently different closure is worthless.
SUPERSEDED_ENUMERATION = (
    "apps/backend/app/research/mr002/dataset.py",
    "apps/backend/app/research/mr002/execution.py",
    "apps/backend/app/research/mr002/joint_portfolio.py",
    "apps/backend/app/research/mr002/n1/method.py",
    "apps/backend/app/research/mr002/n1/seam.py",
    "apps/backend/app/research/mr002/phase3b/readers.py",
    "apps/backend/app/research/mr002/phase3c/__init__.py",
    "apps/backend/app/research/mr002/phase3c/adopted.py",
    "apps/backend/app/research/mr002/phase3c/credential_readiness.py",
    "apps/backend/app/research/mr002/phase3c/durable_evidence.py",
    "apps/backend/app/research/mr002/phase3c/exits.py",
    "apps/backend/app/research/mr002/phase3c/folds.py",
    "apps/backend/app/research/mr002/phase3c/gates.py",
    "apps/backend/app/research/mr002/phase3c/materialize.py",
    "apps/backend/app/research/mr002/phase3c/replay.py",
    "apps/backend/app/research/mr002/runner.py",
    "apps/backend/app/research/mr002/stage3_cascade.py",
    "apps/backend/app/research/mr002/stage3_route.py",
)


def path_to_module(path: str) -> str:
    """apps/backend/app/x/y.py -> app.x.y ; .../y/__init__.py -> app.x.y"""
    rel = path[len(BACKEND) + 1:]
    rel = rel[:-len("/__init__.py")] if rel.endswith("/__init__.py") else rel[:-len(".py")]
    return rel.replace("/", ".")


def _package_of(path: str) -> str:
    """The package a RELATIVE import inside `path` resolves against."""
    mod = path_to_module(path)
    # inside a package __init__, `.` means that package itself; elsewhere, its parent
    return mod if path.endswith("/__init__.py") else mod.rpartition(".")[0]


def imports_of(path: str) -> set[str]:
    """Every first-party module `path` can import, ABSOLUTE AND RELATIVE.

    ⚠ An earlier version of this function followed only absolute `app.*` imports. This codebase
    uses relative imports pervasively (`from . import exits`, `from ..spq1.calendar import ...`),
    so that version silently dropped edges — and a closure with missing edges is precisely the
    failure this whole artifact exists to prevent. It was caught by diffing the derived closure
    against the superseded 20-file enumeration and asking why four previously bound files had
    disappeared. They had not become unreachable; the tracer had gone blind to them.

    ast.walk also reaches imports nested inside functions and `if TYPE_CHECKING` blocks, which is
    correct here: a deferred import still executes, and still decides behaviour.
    """
    tree = ast.parse(git_blob_text(path))
    pkg = _package_of(path)
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("app."):
                    out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.level:                                  # relative: resolve against the package
                base = pkg
                for _ in range(n.level - 1):
                    base = base.rpartition(".")[0]
                target = f"{base}.{n.module}" if n.module else base
            elif n.module and n.module.startswith("app."):
                target = n.module
            else:
                continue
            out.add(target)
            # `from pkg import mod` — the imported NAME may itself be a submodule
            for a in n.names:
                out.add(f"{target}.{a.name}")
    return {m for m in out if m.startswith("app.")}


def trace(entry: str) -> dict[str, str]:
    """path -> why it entered (which importer pulled it in)."""
    found: dict[str, str] = {entry: "ENTRY POINT - the governed launcher itself"}
    frontier = [entry]
    while frontier:
        cur = frontier.pop()
        for mod in sorted(imports_of(cur)):
            p = module_to_path(mod)
            if p and p not in found:
                found[p] = f"imported (transitively) by {cur}"
                frontier.append(p)
    return found


def categorize(text: str) -> list[str]:
    return sorted(c for c, marks in CATEGORIES.items() if any(m in text for m in marks))


def runtime_reads(launcher_text: str) -> dict[str, str]:
    """Files the launcher opens by PATH. No import trace can find these — they are data."""
    out = {}
    tree = ast.parse(launcher_text)
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str) and "/manifests/" in n.value.value:
            tgt = n.targets[0].id if isinstance(n.targets[0], ast.Name) else "?"
            rel = n.value.value.replace("/work/", "")
            out[rel] = (f"runtime-read data artifact bound to {tgt}; supplies object key, "
                        f"VersionId and SHA-256 — no import trace can reach it")
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            try:
                v = ast.literal_eval(n)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(v, str) and "/manifests/" in v:
                out[v.replace("/work/", "")] = (
                    "runtime-read data artifact; supplies object key, VersionId and SHA-256 — "
                    "no import trace can reach it")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", required=True)
    args = ap.parse_args()

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, check=True,
                          capture_output=True).stdout.decode().strip()
    code = trace(LAUNCHER)
    data = runtime_reads(git_blob_text(LAUNCHER))

    members, unjustified, resolved = [], [], []
    for path, why in sorted({**code, **data}.items()):
        raw = git_blob_bytes(path)
        cats = categorize(raw.decode("utf-8", "replace"))
        rec = {"path": path, "sha256_over_git_blob_content_lf": hashlib.sha256(raw).hexdigest(),
               "bytes": len(raw), "kind": "code" if path in code else "runtime_read_data",
               "provenance": why, "closure_categories": cats}
        if not cats:
            if len(raw) == 0:
                # An EMPTY file is structurally incapable of selecting anything. That is a
                # factual determination about its content, not a suppression of the finding:
                # the rule flagged it, inspection resolved it, and the resolution is recorded
                # here with the evidence (0 bytes) that supports it.
                rec["no_category_resolved"] = (
                    "file is EMPTY (0 bytes; sha256 is the SHA-256 of the empty string). It is a "
                    "package marker and can select no partition, key, VersionId, window, fold, "
                    "authority, solver, threshold, disposition or custody status. It stays in "
                    "the closure so that it becoming NON-empty is a detectable change.")
                resolved.append(path)
            else:
                rec["UNJUSTIFIED"] = (
                    "matches no closure category; either it needs a category or it does not "
                    "belong. Recorded, not silently dropped — this is an owner judgement.")
                unjustified.append(path)
        members.append(rec)

    # ---- diff against the superseded enumeration, with every difference JUSTIFIED ----------
    member_paths = {m["path"] for m in members}
    added = sorted(member_paths - set(SUPERSEDED_ENUMERATION))
    removed = sorted(set(SUPERSEDED_ENUMERATION) - member_paths)
    # a removal is only admissible if NO closure member can import it. Verified, not asserted.
    all_imported = set()
    for mp in sorted(member_paths):
        if mp.endswith(".py"):
            all_imported |= imports_of(mp)
    removal_findings = {}
    for r in removed:
        mod = path_to_module(r)
        # ⚠ NOT `mod.startswith(m + ".")`. Importing a PARENT package does not import its
        # submodules, so that clause made `from app.research.mr002 import joint_portfolio`
        # count as a reachability proof for app.research.mr002.n1.method. It reported both
        # removals as "still reachable" — a false positive that would have forced two
        # instrumentation-only files into the governed closure on bad evidence.
        reachable = [m for m in all_imported if m == mod or m.startswith(mod + ".")]
        removal_findings[r] = {
            "still_imported_by_any_closure_member": bool(reachable),
            "matching_import_targets": sorted(reachable),
            "determination": ("REMOVAL REFUSED - still reachable" if reachable else
                              "NOT REACHABLE from the launcher by any import path. It was "
                              "OVER-INCLUDED in the superseded enumeration; it belongs to the "
                              "N1/N3 differential harness, which is instrumentation and is not "
                              "executed by the governed Validation-2 run."),
        }

    doc = {
        "record_type": "MR002_Validation2_ExecutionClosure", "version": "1.0",
        "derived_at_commit": head,
        "closure_rule": (
            "every artifact whose value can select, or cause to be selected, any of: partition, "
            "object key, VersionId, window, fold geometry, authority/countersignature identity, "
            "solver or solver routing, gate threshold, terminal disposition, or "
            "custody/consumption status"),
        "derivation_method": {
            "code": "static transitive import closure from the launcher over first-party app.* "
                    "modules, parsed from Git blobs (LF), not from the Windows working tree",
            "runtime_read_data": "manifest paths the launcher opens by path; these are DATA and "
                                 "are structurally invisible to an import trace, which is why "
                                 "the previous 20-file enumeration missed the registry twice",
            "why_not_a_list": "a list is a snapshot; a closure is a rule. Both halts in this "
                              "cycle came from an artifact one step outside the enumeration."},
        "identity_type": (
            "SHA-256 over file CONTENT as stored in Git (LF). NOT a Git blob object id "
            "(SHA-1 over 'blob <len>\\0' + content). Never compare unlike identity types."),
        "member_count": len(members),
        "code_members": sum(1 for m in members if m["kind"] == "code"),
        "runtime_read_data_members": sum(1 for m in members if m["kind"] == "runtime_read_data"),
        "superseded_enumeration_diff": {
            "superseded": "the 20-file enumeration carried by "
                          "MR002_Validation2_ExecutionPackage_v1.0",
            "added_by_the_closure": added,
            "why_the_additions_matter": (
                "the additions include THE LAUNCHER ITSELF and BOTH REGISTRIES. Every halt in "
                "this cycle originated in exactly those artifacts, and none of them was in the "
                "enumeration. That is the case for a rule over a list, stated as evidence "
                "rather than as an argument."),
            "removed_from_the_enumeration": removed,
            "removal_findings": removal_findings,
        },
        "unjustified_members": unjustified,
        "no_category_but_resolved_empty": resolved,
        "members": members,
    }
    payload = (json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")
    ident = hashlib.sha256(payload).hexdigest()
    doc["closure_identity_sha256"] = ident
    payload = (json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")
    tmp = args.emit + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(payload)
    os.replace(tmp, args.emit)

    print(f"EXECUTION CLOSURE derived at {head[:12]}")
    print(f"  members {len(members)}  ({doc['code_members']} code, "
          f"{doc['runtime_read_data_members']} runtime-read data)")
    for m in members:
        flag = "  <UNJUSTIFIED>" if "UNJUSTIFIED" in m else ""
        print(f"  {m['sha256_over_git_blob_content_lf'][:12]}  {m['path']}{flag}")
        print(f"       {','.join(m['closure_categories']) or '-'}")
    if unjustified:
        print(f"\n⚠ {len(unjustified)} member(s) match no category — owner judgement required.")
    print(f"\n  closure identity {ident}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
