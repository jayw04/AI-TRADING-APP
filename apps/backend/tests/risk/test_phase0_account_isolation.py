"""CORR-06 / AMD-12 — account isolation gate (hermetic; no broker)."""

from __future__ import annotations

import pytest

from app.risk.loss_control.phase0_account_isolation import (
    CANARY_ZERO_CREDENTIAL_MUTATION_ACCOUNT_ID,
    PHASE0_RETRY_ACCOUNT_ID,
    IsolationRefuseReason,
    OperationKind,
    OperationLog,
    OperationRecord,
    assert_no_order_path_imports,
    assess_canary_acceptance,
    authorize_operation,
    isolation_constants,
    record_authorized,
)


def test_retry_account_is_three() -> None:
    assert PHASE0_RETRY_ACCOUNT_ID == 3
    assert isolation_constants()["phase0_retry_account_id"] == 3


def test_unresolved_account_refused() -> None:
    d = authorize_operation(account_id=None, kind=OperationKind.TRADE_MUTATION)
    assert not d.allowed
    assert d.reason is IsolationRefuseReason.ACCOUNT_NOT_RESOLVED


@pytest.mark.parametrize("acct", [1, 2, 4, 5, 6, 7])
def test_trade_mutation_outside_account_3_refused(acct: int) -> None:
    d = authorize_operation(account_id=acct, kind=OperationKind.TRADE_MUTATION)
    assert not d.allowed
    assert d.reason is IsolationRefuseReason.CROSS_ACCOUNT_TRADE_MUTATION


@pytest.mark.parametrize("acct", [1, 2, 4, 5, 6, 7])
def test_risk_mutation_outside_account_3_refused(acct: int) -> None:
    d = authorize_operation(account_id=acct, kind=OperationKind.RISK_STATE_MUTATION)
    assert not d.allowed
    assert d.reason is IsolationRefuseReason.CROSS_ACCOUNT_RISK_MUTATION


def test_mutations_on_account_3_allowed() -> None:
    assert authorize_operation(account_id=3, kind=OperationKind.TRADE_MUTATION).allowed
    assert authorize_operation(account_id=3, kind=OperationKind.RISK_STATE_MUTATION).allowed
    assert authorize_operation(
        account_id=3, kind=OperationKind.CREDENTIAL_METADATA_MUTATION
    ).allowed


def test_account1_credential_metadata_mutation_refused() -> None:
    d = authorize_operation(
        account_id=CANARY_ZERO_CREDENTIAL_MUTATION_ACCOUNT_ID,
        kind=OperationKind.CREDENTIAL_METADATA_MUTATION,
    )
    assert not d.allowed
    assert d.reason is IsolationRefuseReason.ACCOUNT1_CREDENTIAL_METADATA_MUTATION


def test_shared_read_must_be_declared_and_side_effect_free() -> None:
    assert (
        authorize_operation(account_id=1, kind=OperationKind.SHARED_READ).reason
        is IsolationRefuseReason.SHARED_READ_NOT_DECLARED
    )
    assert (
        authorize_operation(
            account_id=1, kind=OperationKind.SHARED_READ, declared_shared_read=True
        ).reason
        is IsolationRefuseReason.SHARED_READ_HAS_SIDE_EFFECTS
    )
    d = authorize_operation(
        account_id=1,
        kind=OperationKind.SHARED_READ,
        declared_shared_read=True,
        side_effect_free=True,
        disclosure="read account-1 limits digest for freeze compare; no writes",
    )
    assert d.allowed and d.disclosure is not None


def test_local_read_any_account_allowed() -> None:
    assert authorize_operation(account_id=1, kind=OperationKind.LOCAL_READ).allowed
    assert authorize_operation(account_id=7, kind=OperationKind.LOCAL_READ).allowed


def test_canary_acceptance_passes_clean_log() -> None:
    log = OperationLog()
    assert record_authorized(log, account_id=3, kind=OperationKind.TRADE_MUTATION).allowed
    assert record_authorized(
        log,
        account_id=1,
        kind=OperationKind.SHARED_READ,
        declared_shared_read=True,
        side_effect_free=True,
        disclosure="side-effect-free shared read of account 1 digest",
    ).allowed
    result = assess_canary_acceptance(log)
    assert result.accepted
    assert result.account1_credential_mutations == 0
    assert result.disclosures


def test_canary_acceptance_fails_on_account1_credential_mutation() -> None:
    log = OperationLog()
    # Bypass authorize to simulate a leaked mutation that must fail acceptance scoring.
    log.append(
        OperationRecord(
            account_id=1,
            kind=OperationKind.CREDENTIAL_METADATA_MUTATION,
            note="leaked",
        )
    )
    result = assess_canary_acceptance(log)
    assert not result.accepted
    assert result.account1_credential_mutations == 1


def test_canary_acceptance_fails_on_cross_account_trade() -> None:
    log = OperationLog()
    log.append(OperationRecord(account_id=2, kind=OperationKind.TRADE_MUTATION))
    result = assess_canary_acceptance(log)
    assert not result.accepted
    assert result.cross_account_mutations == 1


def test_refused_ops_are_not_logged() -> None:
    log = OperationLog()
    d = record_authorized(log, account_id=1, kind=OperationKind.TRADE_MUTATION)
    assert not d.allowed
    assert log.records == []


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
