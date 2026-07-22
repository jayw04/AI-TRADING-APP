"""MR-002 validation/OOS evaluator — no-overwrite publication wrapper (operational increment / P3).

Python port of the Run-5 publication pattern: three vacant destinations, exclusive creation, an
exit-code/disposition agreement check, a third no-overwrite publication record, and read-only locks
plus SHA-256 hashes on everything written.

Publication CONTROL only. It never modifies, retries, or reinterprets a qualification result: if the
report says INTEGRITY_STOP the wrapper publishes INTEGRITY_STOP. An occupied destination is refused
rather than overwritten, because the one thing a publication wrapper must never do is make a second
run look like the first.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat

PASS = "PASS"
FAIL = "FAIL"
REFUSED = "REFUSED"
INTEGRITY_STOP = "INTEGRITY_STOP"

# tool exit contract; any wrapper/publication-control failure is 3 (distinct from a tool verdict)
EXIT_BY_DISPOSITION = {PASS: 0, FAIL: 1, REFUSED: 2, INTEGRITY_STOP: 3}
DISPOSITIONS = tuple(EXIT_BY_DISPOSITION)
WRAPPER_FAILURE_EXIT = 3

PUBLICATION_REFUSED = "PUBLICATION_REFUSED"


class PublicationRefused(Exception):
    """A publication precondition failed. Nothing is overwritten; whatever was created is preserved."""


def _refuse(detail: str):
    raise PublicationRefused(f"{PUBLICATION_REFUSED}:{detail}")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _create_exclusive(path: str, data: bytes) -> str:
    """O_CREAT|O_EXCL write. An existing path (or symlink) refuses; it is never truncated."""
    if os.path.lexists(path):
        _refuse(f"destination_occupied:{os.path.basename(path)}")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        _refuse(f"destination_occupied:{os.path.basename(path)}")
    except OSError as exc:
        _refuse(f"destination_uncreatable:{os.path.basename(path)}:{exc.__class__.__name__}")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except OSError as exc:  # pragma: no cover - write failure after successful create
        _refuse(f"write_failed:{os.path.basename(path)}:{exc.__class__.__name__}")
    return _sha_bytes(data)


def _lock_readonly(path: str) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def verify_exit_agreement(disposition: str, exit_code: int) -> None:
    """The owner-required agreement check: the exit code must be the disposition's exit code."""
    if disposition not in EXIT_BY_DISPOSITION:
        _refuse(f"unknown_disposition:{disposition}")
    expected = EXIT_BY_DISPOSITION[disposition]
    if exit_code != expected:
        _refuse(f"exit_disposition_disagreement:disposition={disposition}:"
                f"exit={exit_code}:expected={expected}")


def publish(report: dict, *, report_path: str, publication_path: str, disposition: str,
            exit_code: int, identities: dict, published_at: str,
            stderr_path: str | None = None, stderr_text: str = "") -> dict:
    """Publish a qualification report exactly once. Returns the publication record.

    `published_at` is supplied by the caller rather than read from the clock so a publication is
    reproducible from its inputs.
    """
    if report.get("disposition") not in (None, disposition):
        _refuse(f"report_disposition_conflict:{report.get('disposition')}!={disposition}")
    verify_exit_agreement(disposition, exit_code)
    for key in ("code_identity", "runtime_identity", "governing_identity"):
        if not identities.get(key):
            _refuse(f"identity_absent:{key}")

    report_bytes = _canonical(report)
    report_sha = _create_exclusive(report_path, report_bytes)
    stderr_sha = None
    if stderr_path is not None:
        stderr_sha = _create_exclusive(stderr_path, stderr_text.encode("utf-8"))

    record = {
        "record_type": "MR002_ValOOS_PublicationRecord", "version": "1.0",
        "published_at": published_at,
        "disposition": disposition,
        "exit_code": exit_code,
        "exit_disposition_agreement": True,
        "report_file": os.path.basename(report_path),
        "report_sha256": report_sha,
        "stderr_file": os.path.basename(stderr_path) if stderr_path else None,
        "stderr_sha256": stderr_sha,
        "identities": identities,
        "no_overwrite": True,
        "retry_after_publication": "PROHIBITED",
        "boundary": "publication control only; the qualification result is published verbatim",
    }
    record_sha = _create_exclusive(publication_path, _canonical(record))

    for path in (report_path, stderr_path, publication_path):
        if path:
            _lock_readonly(path)

    return {**record, "publication_sha256": record_sha}


def verify_published(publication_path: str, report_path: str) -> dict:
    """Read-only post-hoc validation: hashes still match and both files are read-only."""
    with open(publication_path, "rb") as fh:
        record = json.loads(fh.read().decode("ascii"))
    with open(report_path, "rb") as fh:
        report_bytes = fh.read()
    writable = [p for p in (publication_path, report_path)
                if os.stat(p).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)]
    return {"report_sha256_matches": _sha_bytes(report_bytes) == record["report_sha256"],
            "locked_readonly": not writable,
            "writable_files": [os.path.basename(p) for p in writable],
            "disposition": record["disposition"], "exit_code": record["exit_code"]}
