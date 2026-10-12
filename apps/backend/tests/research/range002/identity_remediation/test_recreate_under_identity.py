"""Commit re-creation under another identity, on a SYNTHETIC temporary git repository."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"
sys.path.insert(0, str(SCRIPTS))
import recreate_under_identity as rui  # noqa: E402

OWNER = ("Owner Account", "owner@example.invalid")
MACHINE = ("Machine Identity", "machine@example.invalid")


def sh(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    e = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, env=e, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    sh(r, "init", "-q", "-b", "main")
    sh(r, "config", "commit.gpgsign", "false")
    owner_env = {
        "GIT_AUTHOR_NAME": OWNER[0], "GIT_AUTHOR_EMAIL": OWNER[1],
        "GIT_COMMITTER_NAME": OWNER[0], "GIT_COMMITTER_EMAIL": OWNER[1],
        "GIT_AUTHOR_DATE": "2026-10-12T10:00:00+0000", "GIT_COMMITTER_DATE": "2026-10-12T10:00:00+0000",
    }  # fmt: skip
    (r / "a.txt").write_text("base\n")
    sh(r, "add", ".")
    sh(r, "commit", "-q", "-m", "base", env=owner_env)  # noqa: E702
    sh(r, "checkout", "-q", "-b", "feature")
    for i, day in enumerate(("11", "12")):
        (r / f"f{i}.txt").write_text(f"change {i}\n")
        sh(r, "add", ".")
        owner_env |= {
            "GIT_AUTHOR_DATE": f"2026-10-{day}T12:00:00+0000",
            "GIT_COMMITTER_DATE": f"2026-10-{day}T12:00:00+0000",
        }
        sh(
            r,
            "commit",
            "-q",
            "-m",
            f"feat: change {i}\n\nCo-Authored-By: Claude <noreply@example.invalid>",
            env=owner_env,
        )
    monkeypatch.chdir(r)
    monkeypatch.setenv("MACHINE_NAME", MACHINE[0])
    monkeypatch.setenv("MACHINE_EMAIL", MACHINE[1])
    return r


def run(*args: str) -> int:
    return rui.main(["x", *args])


def test_recreate_preserves_trees_messages_and_changes_only_identity(repo: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        run("recreate", "--base", "main", "--branch", "feature", "--new-ref", "refs/heads/remade")
        == 0
    )
    old = sh(repo, "rev-list", "--reverse", "main..feature").split()
    new = sh(repo, "rev-list", "--reverse", "main..remade").split()
    assert len(old) == len(new) == 2 and set(old).isdisjoint(new)
    for o, n in zip(old, new, strict=True):
        assert sh(repo, "rev-parse", f"{o}^{{tree}}") == sh(repo, "rev-parse", f"{n}^{{tree}}")
        assert sh(repo, "log", "-1", "--format=%B", o) == sh(repo, "log", "-1", "--format=%B", n)
        assert sh(repo, "log", "-1", "--format=%ae|%ce", n) == f"{MACHINE[1]}|{MACHINE[1]}"
        assert sh(repo, "log", "-1", "--format=%ad", "--date=iso-strict", o) == sh(
            repo, "log", "-1", "--format=%ad", "--date=iso-strict", n
        )  # original dates kept
    assert sh(repo, "rev-parse", "remade~2") == sh(repo, "rev-parse", "main")  # same base
    capsys.readouterr()
    assert run("verify", "--base", "main", "--branch", "feature", "--new-ref", "remade",
               "--expect-email", MACHINE[1]) == 0  # fmt: skip
    out = capsys.readouterr().out
    assert out.count("MATCH") >= 2 and "VERIFIED" in out and "NOT VERIFIED" not in out


def test_recreation_is_deterministic(repo: Path) -> None:
    run("recreate", "--base", "main", "--branch", "feature", "--new-ref", "refs/heads/one")
    run("recreate", "--base", "main", "--branch", "feature", "--new-ref", "refs/heads/two")
    assert sh(repo, "rev-parse", "one") == sh(repo, "rev-parse", "two")


def test_verify_exits_nonzero_on_a_tree_message_count_or_identity_difference(
    repo: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    run("recreate", "--base", "main", "--branch", "feature", "--new-ref", "refs/heads/remade")
    capsys.readouterr()
    # (1) a different tree
    sh(repo, "checkout", "-q", "-b", "tampered", "remade~1")
    (repo / "extra.txt").write_text("sneaky\n")
    sh(repo, "add", ".")
    sh(
        repo,
        "commit",
        "-q",
        "-m",
        "feat: change 1\n\nCo-Authored-By: Claude <noreply@example.invalid>",
    )
    assert run("verify", "--base", "main", "--branch", "feature", "--new-ref", "tampered") == 1
    assert "MISMATCH(tree" in capsys.readouterr().out
    # (2) a different commit count
    assert run("verify", "--base", "main", "--branch", "feature", "--new-ref", "remade~1") == 1
    assert "NOT VERIFIED" in capsys.readouterr().out
    # (3) identity not the expected one
    assert run("verify", "--base", "main", "--branch", "feature", "--new-ref", "remade",
               "--expect-email", "someone@else.invalid") == 1  # fmt: skip
    assert "MISMATCH(identity" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["", "<TBD>", "TODO machine", "placeholder-name"])
def test_placeholder_or_missing_identity_is_refused(repo: Path, monkeypatch, bad: str) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MACHINE_EMAIL", bad)
    with pytest.raises(SystemExit):
        run("recreate", "--base", "main", "--branch", "feature", "--new-ref", "refs/heads/x")
    assert (
        subprocess.run(
            ["git", "rev-parse", "--verify", "-q", "refs/heads/x"], capture_output=True
        ).returncode
        != 0
    )


def test_merge_commits_are_refused(repo: Path) -> None:
    sh(repo, "checkout", "-q", "main")
    (repo / "m.txt").write_text("m\n")
    sh(repo, "add", ".")
    sh(repo, "commit", "-q", "-m", "main moves")
    sh(repo, "checkout", "-q", "feature")
    sh(repo, "merge", "-q", "--no-ff", "-m", "merge main", "main")
    with pytest.raises(SystemExit, match="merge"):
        run("plan", "--base", "main", "--branch", "feature")


def test_print_push_prints_and_never_pushes(repo: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert run("print-push", "--new-ref", "refs/heads/remade", "--target-branch", "feat/x") == 0
    out = capsys.readouterr().out
    assert "git push origin refs/heads/remade:refs/heads/feat/x" in out and "PRINT ONLY" in out


def test_a_base_that_is_not_an_ancestor_of_the_branch_is_refused(repo: Path) -> None:
    """The case found on a real branch: BASE moved on after the branch was cut. Re-creating onto
    the moved base would silently change the effective diff, so it must be refused."""
    sh(repo, "checkout", "-q", "main")
    (repo / "later.txt").write_text("main moved on\n")
    sh(repo, "add", ".")
    sh(repo, "commit", "-q", "-m", "main moves on")
    with pytest.raises(SystemExit, match="not an ancestor"):
        run("recreate", "--base", "main", "--branch", "feature", "--new-ref", "refs/heads/nope")
    merge_base = sh(repo, "merge-base", "main", "feature")
    assert (
        run("recreate", "--base", merge_base, "--branch", "feature", "--new-ref", "refs/heads/ok")
        == 0
    )


def test_manifest_preserves_original_attribution_and_names_a_rollback_ref(
    repo: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    import json

    run("recreate", "--base", "main", "--branch", "feature", "--new-ref", "refs/heads/remade")
    capsys.readouterr()
    assert run("manifest", "--base", "main", "--branch", "feature", "--new-ref", "remade") == 0
    m = json.loads(capsys.readouterr().out)
    old = sh(repo, "rev-list", "--reverse", "main..feature").split()
    new = sh(repo, "rev-list", "--reverse", "main..remade").split()
    assert [c["old_sha"] for c in m["commits"]] == old and [
        c["new_sha"] for c in m["commits"]
    ] == new
    assert all(
        OWNER[1] in c["original_author"] and OWNER[1] in c["original_committer"]
        for c in m["commits"]
    )
    assert m["rollback_target"] == old[-1] and m["rollback_ref"].startswith(
        "refs/rollback/feature-"
    )
