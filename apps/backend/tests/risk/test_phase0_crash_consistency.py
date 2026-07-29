"""WP4 AMD-20 — crash consistency / terminal packaging (hermetic; no broker)."""

from __future__ import annotations

from app.risk.loss_control.phase0_crash_consistency import (
    BrokerTruth,
    CompletenessVerdict,
    CrashScenario,
    DriverStatus,
    JournalRecord,
    RemoteEvidence,
    assert_no_order_path_imports,
    assess_evidence_completeness,
    classify_interrupt,
    reconcile_after_restart,
    refuse_false_terminal,
    reproduce_terminal_package,
    write_terminal_once,
)


def test_death_before_package_creation() -> None:
    j = JournalRecord(run_id="r1", account_id=3)
    c = classify_interrupt(j, BrokerTruth(known=True))
    assert c.status == DriverStatus.DRIVER_RECOVERY_REQUIRED
    assert c.scenario == CrashScenario.DEATH_BEFORE_PACKAGE
    assert c.conclusive is False
    assert assess_evidence_completeness(c) == CompletenessVerdict.COMPLETE
    assert refuse_false_terminal(c) is True


def test_death_before_package_with_false_terminal_status() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        status_written=DriverStatus.DRIVER_TERMINAL,
    )
    c = classify_interrupt(j, BrokerTruth(known=True))
    assert c.status == DriverStatus.DRIVER_RECOVERY_REQUIRED
    assert "package was never written" in c.detail


def test_death_after_submit_before_local_persistence() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        legs_intent=("adr0043-r1-l0",),
        legs_persisted=(),
    )
    c = classify_interrupt(
        j, BrokerTruth(known=True, client_order_ids=("adr0043-r1-l0",))
    )
    assert c.status == DriverStatus.DRIVER_RECOVERY_REQUIRED
    assert c.scenario == CrashScenario.DEATH_AFTER_SUBMIT_BEFORE_LOCAL
    assert refuse_false_terminal(c) is True


def test_death_after_submit_broker_unknown() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        legs_intent=("adr0043-r1-l0",),
    )
    c = classify_interrupt(j, BrokerTruth(known=False))
    assert c.status == DriverStatus.UNKNOWN_BROKER_OUTCOME
    assert assess_evidence_completeness(c) == CompletenessVerdict.COMPLETE


def test_package_written_status_update_failed() -> None:
    j = JournalRecord(run_id="r1", account_id=3, package_written=True, status_written=None)
    c = classify_interrupt(j, BrokerTruth(known=True))
    assert c.scenario == CrashScenario.PACKAGE_WITHOUT_STATUS_UPDATE
    assert c.status == DriverStatus.DRIVER_RECOVERY_REQUIRED


def test_duplicate_terminal_write_idempotent() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        package_written=True,
        status_written=DriverStatus.DRIVER_TERMINAL,
        local_evidence_digest="sha256:abc",
        object_store_acked=True,
    )
    broker = BrokerTruth(known=True, client_order_ids=("x",))
    remote = RemoteEvidence(present=True, digest="sha256:abc")
    first, created = write_terminal_once(None, j, broker, remote)
    assert created is True
    second, created2 = write_terminal_once(first, j, broker, remote)
    assert created2 is False
    assert second.package_digest == first.package_digest
    assert second.status == DriverStatus.DRIVER_TERMINAL


def test_duplicate_terminal_write_disagreement_forces_recovery() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        package_written=True,
        status_written=DriverStatus.DRIVER_TERMINAL,
    )
    broker = BrokerTruth(known=True, client_order_ids=("a",))
    first, _ = write_terminal_once(None, j, broker)
    # Simulate a conflicting prior package digest.
    from dataclasses import replace

    conflicting = replace(first, package_digest="sha256:other")
    out, created = write_terminal_once(conflicting, j, broker)
    assert created is False
    assert out.status == DriverStatus.DRIVER_RECOVERY_REQUIRED
    assert "duplicate terminal write disagreement" in out.notes


def test_restart_reconciliation_promotes_to_reconciled() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        package_written=True,
        status_written=DriverStatus.DRIVER_RECOVERY_REQUIRED,
        local_evidence_digest="sha256:abc",
        object_store_acked=True,
    )
    broker = BrokerTruth(known=True, client_order_ids=("x",))
    remote = RemoteEvidence(present=True, digest="sha256:abc")
    c = reconcile_after_restart(j, broker, remote)
    assert c.status == DriverStatus.DRIVER_RECONCILED
    assert c.conclusive is True
    assert c.scenario == CrashScenario.RESTART_RECONCILIATION
    assert assess_evidence_completeness(c) == CompletenessVerdict.COMPLETE


def test_object_store_partial_failure() -> None:
    j = JournalRecord(run_id="r1", account_id=3, package_written=True)
    c = classify_interrupt(
        j, BrokerTruth(known=True), RemoteEvidence(present=True, partial=True, digest="x")
    )
    assert c.scenario == CrashScenario.OBJECT_STORE_PARTIAL_FAILURE
    assert c.status == DriverStatus.DRIVER_RECOVERY_REQUIRED


def test_object_store_ack_without_remote_presence() -> None:
    j = JournalRecord(
        run_id="r1", account_id=3, package_written=True, object_store_acked=True
    )
    c = classify_interrupt(j, BrokerTruth(known=True), RemoteEvidence(present=False))
    assert c.scenario == CrashScenario.OBJECT_STORE_PARTIAL_FAILURE


def test_local_remote_evidence_disagreement() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        package_written=True,
        status_written=DriverStatus.DRIVER_TERMINAL,
        local_evidence_digest="sha256:local",
    )
    c = classify_interrupt(
        j,
        BrokerTruth(known=True),
        RemoteEvidence(present=True, digest="sha256:remote"),
    )
    assert c.scenario == CrashScenario.LOCAL_REMOTE_DISAGREEMENT
    assert c.status == DriverStatus.DRIVER_RECOVERY_REQUIRED
    assert refuse_false_terminal(c) is True


def test_false_certainty_violation_detected() -> None:
    """Inventing conclusive TERMINAL under uncertainty is the AMD-20 violation."""
    false = classify_interrupt(
        JournalRecord(run_id="r1", account_id=3),
        BrokerTruth(known=False),
    )
    # Simulate a lying classification (what AMD-20 forbids callers from emitting).
    from app.risk.loss_control.phase0_crash_consistency import Classification

    lying = Classification(
        status=DriverStatus.DRIVER_TERMINAL,
        scenario=false.scenario,
        detail="lied",
        conclusive=False,
    )
    assert assess_evidence_completeness(lying) == CompletenessVerdict.FALSE_CERTAINTY_VIOLATION


def test_package_reproduction_is_idempotent() -> None:
    j = JournalRecord(
        run_id="r1",
        account_id=3,
        package_written=True,
        status_written=DriverStatus.DRIVER_TERMINAL,
    )
    broker = BrokerTruth(known=True, client_order_ids=("z",))
    a = reproduce_terminal_package(j, broker)
    b = reproduce_terminal_package(j, broker)
    assert a.package_digest == b.package_digest
    assert a.as_dict()["status"] == "DRIVER_TERMINAL"


def test_recovery_required_counts_as_complete_evidence() -> None:
    c = classify_interrupt(
        JournalRecord(run_id="r1", account_id=3),
        BrokerTruth(known=True),
    )
    assert c.status == DriverStatus.DRIVER_RECOVERY_REQUIRED
    assert assess_evidence_completeness(c) is CompletenessVerdict.COMPLETE


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
