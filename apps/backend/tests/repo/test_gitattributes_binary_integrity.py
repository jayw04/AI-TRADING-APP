"""The MR-002 evidence tree must never EOL-convert a binary archive (owner ruling §4).

WHAT WENT WRONG. A single attribute line, written to protect the countersigned markdown whose
SHA-256 binding is over LF bytes:

    docs/implementation/evidence/mr_002/**   text eol=lf

also matched the gzipped archives in that tree. Git marked them text, and its clean filter strips
the CR from any CRLF byte pair inside the COMPRESSED STREAM — where `0d 0a` is data, not a line
ending. Seven of the nine archives carry such pairs. A single `git add` would have deleted those
bytes and destroyed the archive. The only outward symptom was that they showed as permanently
"modified" while being byte-identical to HEAD.

WHY THIS TEST ASKS GIT. The bug was invisible to a reading of `.gitattributes` — every line in it
was individually reasonable, and the defect was in how the patterns COMPOSED. So this test never
parses that file. It asks Git what Git actually resolved (`git check-attr`), and it asks Git's own
object machinery whether a round trip is lossless (`hash-object` = the clean filter, `cat-file` =
what checkout materializes). An assertion about the source of truth, not about our reading of it.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
EVIDENCE = "docs/implementation/evidence/mr_002"

TEXT_SUFFIXES = {".md", ".json", ".csv", ".txt", ".sha256"}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout


def git_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, check=True,
    ).stdout


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    try:
        out = git("ls-files", f"{EVIDENCE}/*")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("not a git checkout")
    files = [ln for ln in out.splitlines() if ln.strip()]
    if not files:
        pytest.skip("evidence tree not present")
    return files


def attrs(path: str) -> dict[str, str]:
    """Git's OWN resolution. Never a re-implementation of its pattern matching — that is the thing
    that was wrong last time."""
    out = git("check-attr", "text", "eol", "--", path)
    got = {}
    for line in out.splitlines():
        _, name, value = line.rsplit(": ", 2)
        got[name] = value
    return got


def test_text_evidence_is_lf_normalised(tracked):
    """The countersigned artifacts: their SHA-256 binding is over LF bytes, so they MUST normalise."""
    checked = 0
    for f in tracked:
        if Path(f).suffix not in TEXT_SUFFIXES:
            continue
        a = attrs(f)
        assert a["text"] == "set", f"{f}: text={a['text']}, expected set"
        assert a["eol"] == "lf", f"{f}: eol={a['eol']}, expected lf"
        checked += 1
    assert checked > 0


def test_binary_evidence_is_never_converted(tracked):
    """Everything that is NOT a whitelisted text format must have text UNSET. This is the assertion
    that would have failed before the fix."""
    checked = 0
    for f in tracked:
        if Path(f).suffix in TEXT_SUFFIXES:
            continue
        a = attrs(f)
        assert a["text"] == "unset", (
            f"{f}: text={a['text']!r} — a non-text evidence artifact is being EOL-converted. "
            f"Git's clean filter will strip CR bytes from inside it.")
        checked += 1
    assert checked > 0


def test_a_new_binary_format_in_the_tree_is_safe_by_default():
    """The regression that re-arms the trap: blacklisting binary extensions fixes today's archives
    and leaves tomorrow's unprotected. A format nobody has whitelisted must default to NO
    conversion, so dropping a .zip/.npz/.pkl in here cannot silently corrupt it."""
    for name in ("future.zip", "future.npz", "future.pkl", "future.bin", "sub/dir/future.arrow"):
        a = attrs(f"{EVIDENCE}/{name}")
        assert a["text"] == "unset", (
            f"{name} would be EOL-converted in the evidence tree — the default there must be "
            f"binary-safe, with text formats named explicitly.")


def test_archives_round_trip_byte_exactly(tracked):
    """checkout -> add -> reset -> checkout must preserve the bytes, proven with Git's own plumbing:

        clean  (`git hash-object --path`)  is what `git add` would store
        smudge (`git cat-file blob`)       is what checkout materializes

    If the clean filter re-hashes to the SAME blob already in HEAD, `git add` is a no-op. If the
    blob's bytes equal the working-tree bytes, checkout is a no-op. Together that is the round trip,
    and it is lossless exactly when neither filter touches the file.
    """
    archives = [f for f in tracked if Path(f).suffix not in TEXT_SUFFIXES]
    with_crlf = 0
    for f in archives:
        disk = (REPO / f).read_bytes()
        n_crlf = disk.count(b"\r\n")
        with_crlf += n_crlf > 0

        head_blob = git("rev-parse", f"HEAD:{f}").strip()
        clean_blob = git("hash-object", "--path", f, str(REPO / f)).strip()
        assert clean_blob == head_blob, (
            f"{f}: `git add` would store a DIFFERENT blob than HEAD ({clean_blob[:12]} != "
            f"{head_blob[:12]}) — the clean filter is rewriting {n_crlf} CRLF byte pair(s) inside "
            f"a binary archive.")

        materialized = git_bytes("cat-file", "blob", head_blob)
        assert hashlib.sha256(materialized).hexdigest() == hashlib.sha256(disk).hexdigest(), (
            f"{f}: checkout does not reproduce the working-tree bytes.")

    assert with_crlf > 0, (
        "no archive in the tree contains an embedded CRLF byte pair, so this fixture is no longer "
        "exercising the defect it was written for — keep one that does.")


def test_the_clean_filter_really_does_corrupt_a_text_marked_archive(tracked, tmp_path):
    """A NEGATIVE CONTROL. The tests above pass trivially if Git never converts anything, which would
    make them worthless. So take real archive bytes and hash them under a path that IS matched by a
    text rule (`.csv`) versus one that is not (`.csv.gz`). If the blobs differ, the corrupting
    mechanism is real, the whitelist is what prevents it, and the assertions above have teeth."""
    src = next(
        (REPO / f for f in tracked
         if f.endswith(".gz") and (REPO / f).read_bytes().count(b"\r\n") > 0),
        None,
    )
    assert src is not None, (
        "no tracked archive carries an embedded CRLF byte pair, so the corruption this suite exists "
        "to prevent can no longer be demonstrated — keep a fixture that does.")
    raw = src.read_bytes()

    probe = tmp_path / "probe.bin"
    probe.write_bytes(raw)

    as_binary = git("hash-object", "--path", f"{EVIDENCE}/x.csv.gz", str(probe)).strip()
    as_text = git("hash-object", "--path", f"{EVIDENCE}/x.csv", str(probe)).strip()

    assert as_binary != as_text, (
        "hashing the same bytes as .csv and as .csv.gz produced the same blob — the EOL filter is "
        "not active at all, so these tests would not detect the corruption they exist to prevent.")
    assert as_binary == hashlib.sha1(  # noqa: S324 — git's blob id is SHA-1 by construction
        b"blob %d\0" % len(raw) + raw).hexdigest(), "the .gz path was converted after all"
