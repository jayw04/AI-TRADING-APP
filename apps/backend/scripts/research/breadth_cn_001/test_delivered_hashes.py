"""Delivered files must not drift from the 9f3a22d0 reference (plus the recorded updates).  Run: python3 test_delivered_hashes.py

Hashes are over LF-normalised bytes, so the result does not depend on a machine's line-ending settings (the folder also pins
eol=lf in .gitattributes).  REFERENCE is the SHA-256 of each file at commit 9f3a22d0 (the verified delivery 3 after the
owner's lint fixes).  The only sanctioned changes since then are the recorded updates in UPDATES; any other edit to a
delivered file - including a formatter run - fails this test."""

import hashlib
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
REL = "apps/backend/scripts/research/breadth_cn_001"
REFERENCE_COMMIT = "9f3a22d0"

# SHA-256 (LF-normalised) at 9f3a22d0
REFERENCE = {
    "breadth_ic.py": "86ad1330893c18b9b2e1e2af8bdde0e7a21be31e79d48ebd79125189118fd26c",
    "build_indicator.py": "c326c0b09c6633d6d763fe2a5b054a71e4d5c4d6c569d84c85c1380f28034f6e",
    "test_breadth_ic.py": "124ef4b2426ec7f0",
    "test_coverage_sets.py": "46b06ee26a82ca1d",
    "test_build_invariance.py": "508ff818e74c2762",
    "SPEC_BREADTH-CN-001_v0.1.md": "1c5e59af2dc86ee8",
}  # values may be a full digest or its first 16 hex characters

# Recorded updates (the ONLY allowed differences from REFERENCE), as exact line replacements/insertions in build_indicator.py
UPDATES = [
    {
        "id": "board_from_code 30x family -> CHINEXT (commit 5af3027a)",
        "file": "build_indicator.py",
        "remove": ['    out[c.str.match(r"^(300|301)")] = "CHINEXT"'],
        "add": [
            '    out[c.str.match(r"^30")] = "CHINEXT"  # 30x family: 300, 301 and 302 (e.g. 302132); was (300|301) - versioned fix 2026-10-16'
        ],
    },
    {
        "id": "pull-store acceptance guard in load() (this change)",
        "file": "build_indicator.py",
        "remove": [],
        "add": [
            "        import pull_guard  # recorded update 2 (2026-10-16): a pull store is readable only after gate-5 acceptance",
            "        pull_guard.require_accepted(args.duckdb)",
        ],
    },
]
# SHA-256 (LF-normalised) of build_indicator.py after both recorded updates
AFTER_UPDATES = {
    "build_indicator.py": "6763146356305f2c11c8fe640831084f12247df2621b6ef775ccdbcd50717aa0"
}


def norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def sha(b: bytes) -> str:
    return hashlib.sha256(norm(b)).hexdigest()


def matches(full: str, ref: str) -> bool:
    return full == ref or full.startswith(ref)


def test_untouched_files_equal_the_reference() -> None:
    changed = {u["file"] for u in UPDATES}
    for f, ref in REFERENCE.items():
        if f in changed:
            continue
        got = sha((HERE / f).read_bytes())
        assert matches(got, ref), (
            f"{f} differs from the {REFERENCE_COMMIT} reference: {got[:16]} != {ref[:16]}"
        )
    print(
        f"ok {len(REFERENCE) - len(changed)} delivered files are byte-identical (LF-normalised) to {REFERENCE_COMMIT}"
    )


def test_updated_files_equal_reference_plus_recorded_updates() -> None:
    for f, want in AFTER_UPDATES.items():
        got = sha((HERE / f).read_bytes())
        assert got == want, (
            f"{f}: {got} != {want} (an edit outside the recorded updates, or a recorded update changed)"
        )
    print("ok build_indicator.py == reference + the two recorded updates (hash)")


def test_diff_against_reference_is_exactly_the_recorded_updates() -> None:
    try:
        ref = subprocess.run(
            ["git", "show", f"{REFERENCE_COMMIT}:{REL}/build_indicator.py"],
            capture_output=True,
            check=True,
            cwd=HERE,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        print(
            "skip diff check (git history for the reference commit is not available); the hash check above still applies"
        )
        return
    a = norm(ref).decode("utf-8").split("\n")
    b = norm((HERE / "build_indicator.py").read_bytes()).decode("utf-8").split("\n")
    removed = [x for x in a if x not in b or a.count(x) > b.count(x)]
    added = [x for x in b if x not in a or b.count(x) > a.count(x)]
    want_removed = [x for u in UPDATES for x in u["remove"]]
    want_added = [x for u in UPDATES for x in u["add"]]
    assert sorted(removed) == sorted(want_removed), removed
    assert sorted(added) == sorted(want_added), added
    print("ok the line-level diff against the reference is exactly the recorded updates")


if __name__ == "__main__":
    test_untouched_files_equal_the_reference()
    test_updated_files_equal_reference_plus_recorded_updates()
    test_diff_against_reference_is_exactly_the_recorded_updates()
    print("ALL TESTS PASSED")
