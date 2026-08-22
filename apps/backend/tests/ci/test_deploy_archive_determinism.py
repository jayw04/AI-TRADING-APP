"""Tests for the deploy-archive determinism invariant.

The load-bearing tests are the ones that prove the checker can FAIL. A guard that
cannot fail is not a guard, and this one exists because a real deployment shipped
CRLF runtime bytes on 2026-08-21 while every governed Git blob was LF.

Each test builds a throwaway Git repository, so nothing here depends on the state
of the real one.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[4] / "scripts" / "check_deploy_archive_determinism.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_deploy_archive_determinism", CHECKER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, **kw
    )


def _repo(tmp_path: Path, files: dict[str, str], gitattributes: str | None = None) -> Path:
    """A tiny repo whose blobs are all LF, committed with autocrlf disabled."""
    repo = tmp_path / "r"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.autocrlf", "false")
    for name, body in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    if gitattributes is not None:
        (repo / ".gitattributes").write_text(gitattributes, encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


def _run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CHECKER)], cwd=repo, capture_output=True, text=True)


SRC = "import os\nprint(os.name)\n"


def test_unpinned_text_file_FAILS_the_check(tmp_path: Path) -> None:
    """The regression that actually happened: no eol pin, CRLF ships.

    Without a pin, `git archive` under core.autocrlf=true rewrites the file, so the
    deployed bytes stop being the reviewed bytes. The checker must catch that.
    """
    repo = _repo(tmp_path, {"app.py": SRC}, gitattributes="")
    result = _run_checker(repo)
    assert result.returncode == 1, result.stdout
    assert "NOT identical to blob   : 1" in result.stdout
    assert "app.py" in result.stdout
    assert "the deployed source would not be the reviewed source" in result.stdout.lower()


def test_pinning_the_extension_makes_it_PASS(tmp_path: Path) -> None:
    # .gitattributes is itself an archived text file, so it needs a pin too — the
    # checker catches that omission, which is how the real repo's pin was found.
    repo = _repo(
        tmp_path,
        {"app.py": SRC},
        gitattributes="*.py text eol=lf\n.gitattributes text eol=lf\n",
    )
    result = _run_checker(repo)
    assert result.returncode == 0, result.stdout
    assert "NOT deterministic       : 0" in result.stdout
    assert "NOT identical to blob   : 0" in result.stdout
    assert "PASS" in result.stdout


def test_nondeterminism_is_reported_separately_from_identity(tmp_path: Path) -> None:
    """An unpinned file is BOTH nondeterministic and non-identical.

    The two properties are reported separately on purpose: a file could in principle
    be deterministic yet not blob-identical (that is exactly the .bat case), and the
    operator needs to know which property failed.
    """
    repo = _repo(tmp_path, {"a.py": SRC}, gitattributes="")
    out = _run_checker(repo).stdout
    assert "depends on the builder's core.autocrlf setting" in out
    assert "differ from the Git blob" in out


def test_crlf_pinned_file_is_deterministic_but_not_blob_identical(tmp_path: Path) -> None:
    """The documented exception, proven rather than asserted.

    A file pinned `eol=crlf` never varies with the builder's configuration, so it is
    deterministic — but its archived bytes are deliberately not the blob's. That is
    why identity carries an allowlist and determinism does not.
    """
    mod = _load_checker()
    repo = _repo(tmp_path, {"go.bat": "echo hi\n"}, gitattributes="*.bat text eol=crlf\n")

    cwd = Path.cwd()
    try:
        os.chdir(repo)
        a = mod._archive("HEAD", "true")
        b = mod._archive("HEAD", "false")
        blobs = mod._blobs("HEAD")
        content = mod._read_blobs([blobs["go.bat"]])[0]
    finally:
        os.chdir(cwd)

    assert a["go.bat"] == b["go.bat"], "eol=crlf must still be deterministic"
    assert b"\r\n" in a["go.bat"]
    assert a["go.bat"] != content, "the crlf pin deliberately differs from the LF blob"
    assert mod._allowlist_reason("go.bat") is not None


def test_allowlist_entries_all_carry_a_reason() -> None:
    """An exception with no stated reason is an exception nobody can review."""
    mod = _load_checker()
    assert mod.IDENTITY_ALLOWLIST_SUFFIXES, "the allowlist should not be silently empty"
    for suffix, reason in mod.IDENTITY_ALLOWLIST_SUFFIXES.items():
        assert suffix.startswith("."), suffix
        assert len(reason) > 40, f"{suffix} needs a real reason, got {reason!r}"


def test_generic_rule_after_a_minus_text_rule_overrides_it(tmp_path: Path) -> None:
    """Why ordering in .gitattributes is load-bearing — demonstrated, not asserted.

    The real repository keeps digest-pinned evidence under `-text` because its bytes
    (CRLF included) are hashed. The LAST matching rule wins, so a generic rule placed
    *after* a `-text` protection silently defeats it. This test pins that behaviour so
    the comment in .gitattributes cannot rot into folklore.
    """
    pinned = "pinned/data.json"

    wrong_order = _repo(
        tmp_path / "wrong",
        {pinned: '{"a": 1}\n'},
        gitattributes="pinned/*.json -text\n*.json text eol=lf\n",
    )
    right_order = _repo(
        tmp_path / "right",
        {pinned: '{"a": 1}\n'},
        gitattributes="*.json text eol=lf\npinned/*.json -text\n",
    )

    def text_attr(repo: Path) -> str:
        return _git(repo, "check-attr", "text", "--", pinned).stdout.strip()

    assert text_attr(wrong_order).endswith("text: set"), (
        "a generic rule placed after `-text` overrides it — this is the trap"
    )
    assert text_attr(right_order).endswith("text: unset"), (
        "with the generic rule first, the `-text` protection survives"
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a/b/c.py", ".py"),
        ("Dockerfile", "(no extension)"),
        ("x/.gitignore", ".gitignore"),
    ],
)
def test_extension_labelling(path: str, expected: str) -> None:
    assert _load_checker()._ext(path) == expected
