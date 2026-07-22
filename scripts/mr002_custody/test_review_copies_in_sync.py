"""Documentation-integrity check: review copies must match their authoritative source.

`docs/review/mr002/custody_review/` holds review copies of the custody artifacts.
They were byte-identical when created, but a recorded claim of equivalence decays
the moment someone edits one side. This test enforces the equivalence mechanically
instead of asserting it in prose.

This is documentation-integrity enforcement, NOT evaluator production: it touches
nothing under docs/review/mr002/evaluator/ and has no bearing on the §4 inventory
or the resolved P5 binding.

If this fails, fix it by re-copying from scripts/mr002_custody/ — the source of
truth — never by editing the review copy.
"""
import hashlib
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent
REVIEW = SOURCE.parents[1] / "docs" / "review" / "mr002" / "custody_review"

# Files that exist ONLY on the review side and have no authoritative source.
# Governed by an explicit allowlist rather than a silent skip, so a genuinely
# orphaned copy is still caught.
REVIEW_ONLY = {"README.md"}


def _tracked_files():
    return sorted(list(SOURCE.glob("*.py")) + list(SOURCE.glob("aws/*.json")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(not REVIEW.exists(), reason="review copies not present in this checkout")
@pytest.mark.parametrize("source_file", _tracked_files(), ids=lambda p: p.name)
def test_review_copy_matches_source(source_file):
    copy = REVIEW / source_file.relative_to(SOURCE)
    assert copy.exists(), (
        f"review copy missing: {copy}. Re-copy from {source_file} — do not delete the source."
    )
    assert _sha256(copy) == _sha256(source_file), (
        f"review copy has DRIFTED from source: {copy}\n"
        f"Fix by re-copying from {source_file}; never edit the review copy."
    )


@pytest.mark.skipif(not REVIEW.exists(), reason="review copies not present in this checkout")
def test_no_orphaned_review_copies():
    """A review copy with no source is stale evidence and must not linger."""
    expected = {f.relative_to(SOURCE).as_posix() for f in _tracked_files()} | REVIEW_ONLY
    actual = {
        f.relative_to(REVIEW).as_posix()
        for f in REVIEW.rglob("*")
        if f.is_file()
    }
    assert actual - expected == set(), f"orphaned review copies: {sorted(actual - expected)}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
