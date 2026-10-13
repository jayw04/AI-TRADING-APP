"""Verification of the minutes file a meeting-decision reference points at.

The weekly meeting minutes are the decision record. A :class:`~spec.schema.DecisionRef` names a
committed minutes file by repo-relative path and by the SHA-256 of its bytes; this module is the
one place that re-reads that file and compares. It grants nothing: it only answers "is the file
the decision cites present, inside the repository, and byte-identical to what was cited?".

``_MINUTES_ROOT`` is a TEST SEAM, module-private and deliberately not a parameter of any public
function: ``None`` means the repository root. Production code never sets it.
"""

from __future__ import annotations

from pathlib import Path

from app.research.range002.spec.hashing import file_sha256

#: ``apps/backend/app/research/range002/spec/decision.py`` -> repository root.
_REPO_ROOT = Path(__file__).resolve().parents[6]
_MINUTES_ROOT: Path | None = None


class MinutesError(ValueError):
    """The cited minutes file cannot be used."""


class MinutesMissingError(MinutesError):
    """The cited minutes file does not exist (or is not a regular file inside the root)."""


class MinutesMismatchError(MinutesError):
    """The minutes file's bytes do not hash to the cited ``minutes_sha256``."""


def check_minutes_file(minutes_path: str, minutes_sha256: str) -> None:
    """Raise :class:`MinutesMissingError` / :class:`MinutesMismatchError` unless the file at the
    repo-relative ``minutes_path`` exists inside the root and hashes to ``minutes_sha256``.

    The path is re-validated here (a hand-built reference must not escape the root): absolute
    forms, backslashes, drive letters and ``..`` / ``.`` / empty segments are refused, and the
    resolved file must lie under the resolved root (a symlink out of it is refused).
    """
    if (
        not isinstance(minutes_path, str)
        or not minutes_path.strip()
        or "\\" in minutes_path
        or minutes_path.startswith("/")
        or (len(minutes_path) > 1 and minutes_path[1] == ":")
        or any(seg in ("", ".", "..") for seg in minutes_path.split("/"))
    ):
        raise MinutesMissingError(f"minutes_path {minutes_path!r} is not a repo-relative path")
    root = (_REPO_ROOT if _MINUTES_ROOT is None else Path(_MINUTES_ROOT)).resolve()
    target = (root / minutes_path).resolve()
    if not target.is_relative_to(root):
        raise MinutesMissingError(f"minutes file {minutes_path!r} resolves outside the repository")
    if not target.is_file():
        raise MinutesMissingError(f"minutes file {minutes_path!r} does not exist")
    try:
        actual = file_sha256(target)
    except OSError as exc:
        raise MinutesMissingError(f"minutes file {minutes_path!r} cannot be read: {exc}") from exc
    if actual != minutes_sha256:
        raise MinutesMismatchError(
            f"minutes file {minutes_path!r} hashes to {actual}, but the decision cites "
            f"{minutes_sha256}: the minutes were changed after the decision was recorded"
        )


# Spec handling computes no returns; declared for the range002 import-lint.
PURE_FUNCTIONS = ("check_minutes_file",)
