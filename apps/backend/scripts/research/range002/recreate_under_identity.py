"""Re-create a branch's commits under a different git identity, preserving every tree SHA.

    recreate_under_identity.py plan   --base BASE --branch BRANCH
    recreate_under_identity.py recreate --base BASE --branch BRANCH --new-ref REF
    recreate_under_identity.py verify --base BASE --branch BRANCH --new-ref REF [--expect-email E]
    recreate_under_identity.py manifest --base BASE --branch BRANCH [--new-ref REF]
    recreate_under_identity.py print-push --new-ref REF --remote R --target-branch B

Identity comes from the environment: ``MACHINE_NAME`` and ``MACHINE_EMAIL`` (placeholders such as
``<TBD>`` are refused). No token is read, stored or used here, and this tool never pushes:
``print-push`` only PRINTS the commands for the owner to run after a separate go-ahead.

Determinism: for each commit (oldest first, linear history only) a new commit is built with
``git commit-tree`` from the ORIGINAL tree, the new parent chain, the ORIGINAL message bytes and
the ORIGINAL author and committer dates, with name and email replaced. The same inputs therefore
always give the same new SHAs. ``verify`` prints, per commit, old tree SHA, new tree SHA and
MATCH/MISMATCH, and exits nonzero on any mismatch, count difference or message difference.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

PLACEHOLDER_MARKERS = ("<", ">", "TBD", "TODO", "placeholder")


def git(*args: str, env: dict[str, str] | None = None, input_bytes: bytes | None = None) -> bytes:
    full_env = None if env is None else {**os.environ, **env}
    res = subprocess.run(
        ["git", *args], capture_output=True, input=input_bytes, env=full_env, check=False
    )
    if res.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed: {res.stderr.decode(errors='replace').strip()}"
        )
    return res.stdout


def rev(ref: str) -> str:
    return git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()


def linear_commits(base: str, branch: str) -> list[str]:
    """Oldest-first commit ids in BASE..BRANCH. Merges are refused: the procedure is for a linear
    branch, and re-creating a merge would need a decision this tool must not make."""
    anc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, branch], capture_output=True, check=False
    )
    if anc.returncode != 0:
        raise SystemExit(
            f"BASE {base} is not an ancestor of {branch}: re-creating onto it would change the "
            "branch's parentage (and its effective diff). Use the branch's merge-base "
            "(git merge-base BASE BRANCH) and rebase as a separate, reviewed step."
        )
    ids = git("rev-list", "--reverse", f"{base}..{branch}").decode().split()
    for c in ids:
        if len(git("rev-list", "--parents", "-n", "1", c).decode().split()) != 2:
            raise SystemExit(f"commit {c[:12]} is a merge or root commit; refusing")
    return ids


def raw_commit(c: str) -> tuple[dict[str, str], bytes]:
    raw = git("cat-file", "commit", c)
    head, _, msg = raw.partition(b"\n\n")
    fields: dict[str, str] = {}
    for line in head.decode().split("\n"):
        k, _, v = line.partition(" ")
        fields.setdefault(k, v)
    return fields, msg


def _date(ident: str) -> str:
    # "Name <email> 1700000000 +0100"  ->  "1700000000 +0100"
    return " ".join(ident.rsplit(" ", 2)[-2:])


def identity_from_env() -> tuple[str, str]:
    name, email = os.environ.get("MACHINE_NAME", ""), os.environ.get("MACHINE_EMAIL", "")
    for label, v in (("MACHINE_NAME", name), ("MACHINE_EMAIL", email)):
        if not v.strip() or any(m in v for m in PLACEHOLDER_MARKERS):
            raise SystemExit(f"{label} is unset or still a placeholder; refusing")
    return name, email


def cmd_plan(a: argparse.Namespace) -> int:
    for c in linear_commits(a.base, a.branch):
        f, _ = raw_commit(c)
        print(f"{c}  tree {f['tree']}  author {f['author'].rsplit(' ', 2)[0]}")
    return 0


def cmd_recreate(a: argparse.Namespace) -> int:
    name, email = identity_from_env()
    parent = rev(a.base)
    for c in linear_commits(a.base, a.branch):
        f, msg = raw_commit(c)
        env = {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_AUTHOR_DATE": _date(f["author"]),
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_COMMITTER_DATE": _date(f["committer"]),
        }
        parent = (
            git("commit-tree", f["tree"], "-p", parent, env=env, input_bytes=msg).decode().strip()
        )
        print(f"{c[:12]} -> {parent[:12]}")
    git("update-ref", a.new_ref, parent)
    print(f"{a.new_ref} = {parent}")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    old = linear_commits(a.base, a.branch)
    new = linear_commits(a.base, a.new_ref)
    ok = True
    if len(old) != len(new):
        print(f"MISMATCH: {len(old)} old commit(s) vs {len(new)} new commit(s)")
        ok = False
    for o, n in zip(old, new, strict=False):
        fo, mo = raw_commit(o)
        fn, mn = raw_commit(n)
        problems = []
        if fo["tree"] != fn["tree"]:
            problems.append("tree")
        if mo != mn:
            problems.append("message")
        if a.expect_email and f"<{a.expect_email}>" not in fn["author"] + fn["committer"]:
            problems.append("identity")
        verdict = "MATCH" if not problems else "MISMATCH(" + ",".join(problems) + ")"
        print(f"old {fo['tree']}  new {fn['tree']}  {verdict}  {o[:12]} -> {n[:12]}")
        ok &= not problems
    print("VERIFIED" if ok else "NOT VERIFIED")
    return 0 if ok else 1


def cmd_manifest(a: argparse.Namespace) -> int:
    """JSON provenance record: ORIGINAL author/committer/dates and tree per commit, the new SHA when
    ``--new-ref`` is given, and the rollback reference to keep. Re-creating changes commit metadata
    only; it does not create reviewer independence and it must not erase who wrote what, so this
    record (committed by the owner alongside the change) preserves the original attribution."""
    import json

    old = linear_commits(a.base, a.branch)
    new = linear_commits(a.base, a.new_ref) if a.new_ref else []
    out = []
    for i, c in enumerate(old):
        f, msg = raw_commit(c)
        row = {
            "old_sha": c,
            "tree": f["tree"],
            "original_author": f["author"],
            "original_committer": f["committer"],
            "subject": msg.decode(errors="replace").splitlines()[0] if msg else "",
        }
        if i < len(new):
            row["new_sha"] = new[i]
        out.append(row)
    tip = old[-1] if old else rev(a.base)
    print(
        json.dumps(
            {
                "branch": a.branch,
                "base": rev(a.base),
                "rollback_ref": f"refs/rollback/{a.branch.split('/')[-1]}-{tip[:12]}",
                "rollback_target": tip,
                "commits": out,
            },
            indent=2,
        )
    )
    return 0


def cmd_print_push(a: argparse.Namespace) -> int:
    print(
        "# PRINT ONLY. Run after the owner's separate go-ahead, with the machine identity's credentials."
    )
    print("# Credentials are NOT read by this tool; configure them in your credential helper.")
    print(f"git push {a.remote} {a.new_ref}:refs/heads/{a.target_branch}")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "recreate", "verify", "manifest"):
        s = sub.add_parser(name)
        s.add_argument("--base", required=True)
        s.add_argument("--branch", required=True)
        if name in ("recreate", "verify"):
            s.add_argument("--new-ref", required=True)
        if name == "manifest":
            s.add_argument("--new-ref", default="")
        if name == "verify":
            s.add_argument("--expect-email", default="")
    s = sub.add_parser("print-push")
    s.add_argument("--new-ref", required=True)
    s.add_argument("--remote", default="origin")
    s.add_argument("--target-branch", required=True)
    a = p.parse_args(argv[1:])
    return {
        "plan": cmd_plan,
        "recreate": cmd_recreate,
        "verify": cmd_verify,
        "manifest": cmd_manifest,
        "print-push": cmd_print_push,
    }[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
