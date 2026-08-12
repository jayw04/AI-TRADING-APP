"""Publication of the nine Phase 3B output artifacts.

Publication control only. It never modifies, retries or reinterprets a result: if the run reached
INTEGRITY_STOP, the wrapper publishes INTEGRITY_STOP.

The one thing a publication wrapper must never do is let a second run look like the first. Every
destination is created exclusively and locked read-only, an occupied destination refuses rather than
truncating, and the exit code must agree with the disposition.

Partial output is PRESERVED. If the run fails after the opening is consumed, whatever was written
stays written and the census records what was not produced. Deleting a partial run would destroy
the only evidence of what the single opening actually bought.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
REFUSED = "REFUSED"
INTEGRITY_STOP = "INTEGRITY_STOP"

EXIT_BY_DISPOSITION = {PASS: 0, FAIL: 1, REFUSED: 2, INTEGRITY_STOP: 3}
WRAPPER_FAILURE_EXIT = 3

DELIVERABLES = (
    "ValidationOpenedObjectLedger_v1.0.json",
    "ValidationExecutionEnrichmentManifest_v1.0.json",
    "ValidationDecisionExecutionBindingReport_v1.0.json",
    "ValidationUnitReconciliation_v1.0.json",
    "ExecutionEnrichmentEdgeCaseCensus_v1.0.json",
    "ValidationSealVerificationReport_v1.0.json",
)
REPORT = "MR002_ValOOS_validation_Report.json"
PUBLICATION = "MR002_ValOOS_validation_Publication.json"
STDERR = "MR002_ValOOS_validation_stderr.txt"

EXPECTED_ARTIFACTS = (*DELIVERABLES, REPORT, PUBLICATION, STDERR)


class PublicationRefused(Exception):
    """A publication precondition failed. Nothing is overwritten; what exists is preserved."""


def _canonical(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _create_exclusive(path: str, data: bytes) -> str:
    if os.path.lexists(path):
        raise PublicationRefused(f"destination_occupied:{os.path.basename(path)}")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        raise PublicationRefused(f"destination_occupied:{os.path.basename(path)}") from exc
    except OSError as exc:
        raise PublicationRefused(
            f"destination_uncreatable:{os.path.basename(path)}:{type(exc).__name__}"
        ) from exc
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return hashlib.sha256(data).hexdigest()


def _lock_readonly(path: str) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def verify_exit_agreement(disposition: str, exit_code: int) -> None:
    if disposition not in EXIT_BY_DISPOSITION:
        raise PublicationRefused(f"unknown_disposition:{disposition}")
    if exit_code != EXIT_BY_DISPOSITION[disposition]:
        raise PublicationRefused(
            f"exit_disposition_disagreement:{disposition}:exit={exit_code}:"
            f"expected={EXIT_BY_DISPOSITION[disposition]}"
        )


def assert_root_vacant(root: str) -> None:
    """Refuse before a single byte is written if any destination is already occupied."""
    occupied = [n for n in EXPECTED_ARTIFACTS if os.path.lexists(os.path.join(root, n))]
    if occupied:
        raise PublicationRefused(f"output_root_occupied:{occupied}")


def publish_deliverable(root: str, name: str, payload: Any) -> str:
    if name not in EXPECTED_ARTIFACTS:
        raise PublicationRefused(f"unregistered_artifact:{name}")
    path = os.path.join(root, name)
    sha = _create_exclusive(path, _canonical(payload))
    _lock_readonly(path)
    return sha


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def publish_run(
    root: str,
    *,
    report: dict,
    disposition: str,
    exit_code: int,
    identities: dict,
    deliverable_hashes: dict[str, str],
    stderr_text: str = "",
    clock: Callable[[], str] | None = None,
) -> dict:
    """Write the report and its no-overwrite publication record, certifying the deliverables.

    `published_at` is STAMPED HERE, at the durable publication transition, and is not an input to
    the run. The frozen contract could not have known it prospectively, so it is publication
    metadata rather than a research configuration parameter: nothing in signal, eligibility,
    enrichment, admissibility, selection, configuration identity or authorization identity may
    depend on it.

    A retry after durable publication must not mint a second timestamp for the same publication
    event, so an existing publication record refuses rather than restamps.
    """
    verify_exit_agreement(disposition, exit_code)
    already = os.path.join(root, PUBLICATION)
    if os.path.exists(already):
        raise PublicationRefused(
            f"already_durably_published:{PUBLICATION}. A retry must reuse the published artifact; "
            "restamping would mint a second published_at for one publication event."
        )
    published_at = (clock or _utc_now)()
    for key in ("code_identity", "runtime_identity", "governing_identity"):
        if not identities.get(key):
            raise PublicationRefused(f"identity_absent:{key}")

    produced = sorted(deliverable_hashes)
    missing = sorted(set(DELIVERABLES) - set(produced))
    report_body = {
        **report,
        "disposition": disposition,
        "deliverable_sha256": dict(sorted(deliverable_hashes.items())),
        "deliverables_produced": produced,
        "deliverables_not_produced": missing,
        "partial_run": bool(missing),
    }
    report_sha = _create_exclusive(os.path.join(root, REPORT), _canonical(report_body))
    _lock_readonly(os.path.join(root, REPORT))

    stderr_sha = None
    if stderr_text:
        stderr_sha = _create_exclusive(os.path.join(root, STDERR), stderr_text.encode("utf-8"))
        _lock_readonly(os.path.join(root, STDERR))

    record = {
        "record_type": "MR002_ValOOS_PublicationRecord",
        "version": "1.0",
        "published_at": published_at,
        "disposition": disposition,
        "exit_code": exit_code,
        "exit_disposition_agreement": True,
        "report_file": REPORT,
        "report_sha256": report_sha,
        "stderr_file": STDERR if stderr_sha else None,
        "stderr_sha256": stderr_sha,
        "deliverable_sha256": dict(sorted(deliverable_hashes.items())),
        "partial_run": bool(missing),
        "identities": identities,
        "no_overwrite": True,
        "retry_after_publication": "PROHIBITED",
        "boundary": "publication control only; the result is published verbatim",
    }
    pub_sha = _create_exclusive(os.path.join(root, PUBLICATION), _canonical(record))
    _lock_readonly(os.path.join(root, PUBLICATION))
    return {**record, "publication_sha256": pub_sha}
