"""ADR-0043 Phase-0 WP4 — crash consistency / terminal packaging (offline).

Implements AMD-20 / CORR-04 (BLOCKING for WP4 exit):

* interrupted broker interactions must not be forced into ``DRIVER_TERMINAL``;
* states ``DRIVER_RECOVERY_REQUIRED``, ``DRIVER_RECONCILED``, and
  ``UNKNOWN_BROKER_OUTCOME`` express uncertainty honestly;
* evidence completeness accepts a properly recorded recovery-required outcome;
* terminal packages are idempotently reproducible from journal + broker truth.

Does not submit orders or import the order path.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DriverStatus(StrEnum):
    DRIVER_RUNNING = "DRIVER_RUNNING"
    DRIVER_TERMINAL = "DRIVER_TERMINAL"
    DRIVER_RECOVERY_REQUIRED = "DRIVER_RECOVERY_REQUIRED"
    DRIVER_RECONCILED = "DRIVER_RECONCILED"
    UNKNOWN_BROKER_OUTCOME = "UNKNOWN_BROKER_OUTCOME"


class CrashScenario(StrEnum):
    DEATH_BEFORE_PACKAGE = "DEATH_BEFORE_PACKAGE"
    DEATH_AFTER_SUBMIT_BEFORE_LOCAL = "DEATH_AFTER_SUBMIT_BEFORE_LOCAL"
    PACKAGE_WITHOUT_STATUS_UPDATE = "PACKAGE_WITHOUT_STATUS_UPDATE"
    DUPLICATE_TERMINAL_WRITE = "DUPLICATE_TERMINAL_WRITE"
    RESTART_RECONCILIATION = "RESTART_RECONCILIATION"
    OBJECT_STORE_PARTIAL_FAILURE = "OBJECT_STORE_PARTIAL_FAILURE"
    LOCAL_REMOTE_DISAGREEMENT = "LOCAL_REMOTE_DISAGREEMENT"


class CompletenessVerdict(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    FALSE_CERTAINTY_VIOLATION = "FALSE_CERTAINTY_VIOLATION"


@dataclass(frozen=True)
class JournalRecord:
    """Local durable journal for one Phase-0 driver run."""

    run_id: str
    account_id: int
    legs_intent: tuple[str, ...] = ()
    legs_persisted: tuple[str, ...] = ()
    package_written: bool = False
    status_written: DriverStatus | None = None
    object_store_acked: bool = False
    local_evidence_digest: str | None = None


@dataclass(frozen=True)
class BrokerTruth:
    """Observed broker truth at reconciliation time (read-only snapshot)."""

    known: bool
    client_order_ids: tuple[str, ...] = ()
    terminal_fills: tuple[str, ...] = ()


@dataclass(frozen=True)
class RemoteEvidence:
    """Object-store / remote evidence mirror (may be partial or absent)."""

    present: bool
    digest: str | None = None
    partial: bool = False


@dataclass(frozen=True)
class Classification:
    status: DriverStatus
    scenario: CrashScenario | None
    detail: str
    conclusive: bool


@dataclass(frozen=True)
class TerminalPackage:
    run_id: str
    account_id: int
    status: DriverStatus
    journal_digest: str
    broker_client_order_ids: tuple[str, ...]
    package_digest: str
    conclusive: bool
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "account_id": self.account_id,
            "status": str(self.status),
            "journal_digest": self.journal_digest,
            "broker_client_order_ids": list(self.broker_client_order_ids),
            "package_digest": self.package_digest,
            "conclusive": self.conclusive,
            "notes": list(self.notes),
        }


def _journal_digest(journal: JournalRecord) -> str:
    blob = {
        "run_id": journal.run_id,
        "account_id": journal.account_id,
        "legs_intent": list(journal.legs_intent),
        "legs_persisted": list(journal.legs_persisted),
        "package_written": journal.package_written,
        "status_written": str(journal.status_written) if journal.status_written else None,
        "object_store_acked": journal.object_store_acked,
        "local_evidence_digest": journal.local_evidence_digest,
    }
    digest = hashlib.sha256(
        json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"sha256:{digest}"


def _submit_gap(journal: JournalRecord) -> set[str]:
    return set(journal.legs_intent) - set(journal.legs_persisted)


def classify_interrupt(
    journal: JournalRecord,
    broker: BrokerTruth,
    remote: RemoteEvidence | None = None,
) -> Classification:
    """Classify crash / interrupt into a non-lying driver status (AMD-20)."""
    remote = remote or RemoteEvidence(present=False)

    # 7. Local / remote disagreement — never resolve as conclusive terminal.
    if (
        journal.local_evidence_digest
        and remote.present
        and remote.digest
        and remote.digest != journal.local_evidence_digest
    ):
        return Classification(
            DriverStatus.DRIVER_RECOVERY_REQUIRED,
            CrashScenario.LOCAL_REMOTE_DISAGREEMENT,
            "local evidence digest disagrees with remote mirror",
            conclusive=False,
        )

    # 6. Object-store partial failure (partial upload, or ack without remote presence).
    if remote.partial or (journal.object_store_acked and not remote.present):
        return Classification(
            DriverStatus.DRIVER_RECOVERY_REQUIRED,
            CrashScenario.OBJECT_STORE_PARTIAL_FAILURE,
            "object-store evidence incomplete or ack disagrees with presence",
            conclusive=False,
        )

    gap = _submit_gap(journal)

    # 2. Death after broker submission but before local persistence.
    if gap:
        if not broker.known:
            return Classification(
                DriverStatus.UNKNOWN_BROKER_OUTCOME,
                CrashScenario.DEATH_AFTER_SUBMIT_BEFORE_LOCAL,
                "intent recorded; broker truth unknown; local persistence missing",
                conclusive=False,
            )
        overlap = gap & set(broker.client_order_ids)
        detail = (
            f"broker holds unpersisted client_order_id(s) {sorted(overlap)}"
            if overlap
            else "local intent without persistence; broker has no matching id yet or differs"
        )
        return Classification(
            DriverStatus.DRIVER_RECOVERY_REQUIRED,
            CrashScenario.DEATH_AFTER_SUBMIT_BEFORE_LOCAL,
            detail,
            conclusive=False,
        )

    # 1. Death before package creation (no package, no unresolved submit gap).
    if not journal.package_written:
        return Classification(
            DriverStatus.DRIVER_RECOVERY_REQUIRED,
            CrashScenario.DEATH_BEFORE_PACKAGE,
            "run interrupted before terminal package creation"
            if journal.status_written != DriverStatus.DRIVER_TERMINAL
            else "status claims terminal but package was never written",
            conclusive=False,
        )

    # 3. Package written but status update failed.
    if journal.status_written is None:
        return Classification(
            DriverStatus.DRIVER_RECOVERY_REQUIRED,
            CrashScenario.PACKAGE_WITHOUT_STATUS_UPDATE,
            "terminal package present but driver status not durably updated",
            conclusive=False,
        )

    # Broker unknown after package — still not conclusive terminal.
    if not broker.known:
        return Classification(
            DriverStatus.UNKNOWN_BROKER_OUTCOME,
            CrashScenario.RESTART_RECONCILIATION,
            "package present but broker truth unavailable",
            conclusive=False,
        )

    if journal.status_written == DriverStatus.DRIVER_TERMINAL:
        return Classification(
            DriverStatus.DRIVER_TERMINAL,
            None,
            "journal package, status, and broker truth agree",
            conclusive=True,
        )

    if journal.status_written == DriverStatus.DRIVER_RECOVERY_REQUIRED:
        return Classification(
            DriverStatus.DRIVER_RECOVERY_REQUIRED,
            CrashScenario.RESTART_RECONCILIATION,
            "recovery-required status already durably recorded",
            conclusive=False,
        )

    if journal.status_written == DriverStatus.DRIVER_RECONCILED:
        return Classification(
            DriverStatus.DRIVER_RECONCILED,
            CrashScenario.RESTART_RECONCILIATION,
            "prior reconciliation recorded",
            conclusive=True,
        )

    return Classification(
        DriverStatus.DRIVER_RECOVERY_REQUIRED,
        CrashScenario.RESTART_RECONCILIATION,
        f"unresolved interrupt under status={journal.status_written}",
        conclusive=False,
    )


def assess_evidence_completeness(classification: Classification) -> CompletenessVerdict:
    """Section 7 / AMD-20: properly recorded recovery-required is complete.

    Falsely declaring conclusive ``DRIVER_TERMINAL`` under uncertainty is a violation.
    """
    if classification.status == DriverStatus.DRIVER_TERMINAL and not classification.conclusive:
        return CompletenessVerdict.FALSE_CERTAINTY_VIOLATION
    if classification.status in {
        DriverStatus.DRIVER_TERMINAL,
        DriverStatus.DRIVER_RECONCILED,
    } and classification.conclusive:
        return CompletenessVerdict.COMPLETE
    if classification.status in {
        DriverStatus.DRIVER_RECOVERY_REQUIRED,
        DriverStatus.UNKNOWN_BROKER_OUTCOME,
    }:
        return CompletenessVerdict.COMPLETE
    if classification.status == DriverStatus.DRIVER_RUNNING:
        return CompletenessVerdict.INCOMPLETE
    return CompletenessVerdict.INCOMPLETE


def refuse_false_terminal(classification: Classification) -> bool:
    """True when a caller must refuse to emit/accept DRIVER_TERMINAL."""
    return not (
        classification.status == DriverStatus.DRIVER_TERMINAL and classification.conclusive
    )


def reproduce_terminal_package(
    journal: JournalRecord,
    broker: BrokerTruth,
    remote: RemoteEvidence | None = None,
) -> TerminalPackage:
    """Idempotently build the terminal package from journal + broker truth."""
    classification = classify_interrupt(journal, broker, remote)
    notes: list[str] = [classification.detail]
    if classification.scenario:
        notes.append(f"scenario={classification.scenario}")
    body = {
        "run_id": journal.run_id,
        "account_id": journal.account_id,
        "status": str(classification.status),
        "journal_digest": _journal_digest(journal),
        "broker_client_order_ids": list(broker.client_order_ids),
        "conclusive": classification.conclusive,
        "notes": notes,
    }
    package_digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return TerminalPackage(
        run_id=journal.run_id,
        account_id=journal.account_id,
        status=classification.status,
        journal_digest=body["journal_digest"],
        broker_client_order_ids=tuple(broker.client_order_ids),
        package_digest=package_digest,
        conclusive=classification.conclusive,
        notes=tuple(notes),
    )


def reconcile_after_restart(
    journal: JournalRecord,
    broker: BrokerTruth,
    remote: RemoteEvidence | None = None,
) -> Classification:
    """Restart path: re-derive status; never invent DRIVER_TERMINAL under uncertainty.

    When journal/broker/remote now agree after a prior recovery-required (or missing status),
    promote to ``DRIVER_RECONCILED`` — not a silent jump to ``DRIVER_TERMINAL``.
    """
    remote = remote or RemoteEvidence(present=False)
    classified = classify_interrupt(journal, broker, remote)

    if classified.status == DriverStatus.DRIVER_TERMINAL and not classified.conclusive:
        return Classification(
            DriverStatus.DRIVER_RECOVERY_REQUIRED,
            CrashScenario.RESTART_RECONCILIATION,
            "refused non-conclusive terminal on restart",
            conclusive=False,
        )

    can_reconcile = (
        broker.known
        and journal.package_written
        and not _submit_gap(journal)
        and remote.present
        and not remote.partial
        and journal.local_evidence_digest is not None
        and remote.digest == journal.local_evidence_digest
        and journal.status_written
        in {None, DriverStatus.DRIVER_RECOVERY_REQUIRED, DriverStatus.UNKNOWN_BROKER_OUTCOME}
    )
    if can_reconcile:
        return Classification(
            DriverStatus.DRIVER_RECONCILED,
            CrashScenario.RESTART_RECONCILIATION,
            "restart reconciliation: journal, broker, and remote evidence agree",
            conclusive=True,
        )
    return classified


def write_terminal_once(
    existing_package: TerminalPackage | None,
    journal: JournalRecord,
    broker: BrokerTruth,
    remote: RemoteEvidence | None = None,
) -> tuple[TerminalPackage, bool]:
    """Duplicate terminal write: return prior package if digests match (idempotent).

    Returns ``(package, created_new)``. Disagreement forces recovery-required notes.
    """
    fresh = reproduce_terminal_package(journal, broker, remote)
    if existing_package is None:
        return fresh, True
    if existing_package.package_digest == fresh.package_digest:
        return existing_package, False
    recovery = TerminalPackage(
        run_id=journal.run_id,
        account_id=journal.account_id,
        status=DriverStatus.DRIVER_RECOVERY_REQUIRED,
        journal_digest=fresh.journal_digest,
        broker_client_order_ids=fresh.broker_client_order_ids,
        package_digest=fresh.package_digest,
        conclusive=False,
        notes=fresh.notes + ("duplicate terminal write disagreement",),
    )
    return recovery, False


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_crash_consistency as mod

    src = inspect.getsource(mod)
    needles = [
        "from app." + "services.order_router",
        "import app." + "services.order_router",
        "from app." + "brokers",
        "import app." + "brokers",
        "from app." + "orders",
        "submit_" + "order(",
    ]
    for needle in needles:
        if needle in src:
            raise AssertionError(f"phase0_crash_consistency must not reference {needle}")


__all__ = [
    "BrokerTruth",
    "Classification",
    "CompletenessVerdict",
    "CrashScenario",
    "DriverStatus",
    "JournalRecord",
    "RemoteEvidence",
    "TerminalPackage",
    "assert_no_order_path_imports",
    "assess_evidence_completeness",
    "classify_interrupt",
    "reconcile_after_restart",
    "refuse_false_terminal",
    "reproduce_terminal_package",
    "write_terminal_once",
]
