"""P7 §7-A.2b — deployment blob schema + FAIL-CLOSED validation (pure)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategies.deployment_state import (
    SCHEMA_VERSION,
    DeploymentStateInvalid,
    DeploymentStateUninitialized,
    initial_blob,
    load_deployment_blob,
    seed_attempt_from_dict,
    seed_attempt_to_dict,
)
from app.strategies.seed_reconciliation import (
    DeploymentState,
    SeedAttempt,
    SeedAttemptStatus,
)

T = datetime(2026, 8, 3, 19, 50, tzinfo=UTC)


def _valid(**over) -> dict:
    base = {
        "schema_version": SCHEMA_VERSION, "_rev": 0, "state": "NEVER_DEPLOYED",
        "has_ever_deployed": False, "first_deployed_at": None,
        "active_seed_attempt": None, "last_seed_attempt": None,
    }
    base.update(over)
    return base


def _attempt(status=SeedAttemptStatus.ORDERS_OPEN) -> dict:
    return seed_attempt_to_dict(SeedAttempt(
        attempt_id="att-1", created_at=T, intended_symbols=("AAA",),
        client_order_id_prefix="seed:11:att-1:", submitted_order_ids=(101,), status=status,
    ))


def test_initial_blob_is_never_deployed_and_round_trips():
    b = initial_blob()
    assert b.state == DeploymentState.NEVER_DEPLOYED and b.has_ever_deployed is False
    assert load_deployment_blob(b.to_dict()).state == DeploymentState.NEVER_DEPLOYED


def test_missing_blob_is_uninitialized():
    with pytest.raises(DeploymentStateUninitialized):
        load_deployment_blob(None)


def test_non_dict_is_invalid():
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(["not", "a", "dict"])  # type: ignore[arg-type]


def test_unsupported_schema_version_is_invalid():
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(_valid(schema_version=999))


def test_missing_rev_is_invalid():
    d = _valid()
    del d["_rev"]
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(d)


def test_bad_state_enum_is_invalid():
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(_valid(state="WOBBLE"))


def test_deployed_without_has_ever_is_invalid():
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(_valid(state="DEPLOYED", has_ever_deployed=False))


def test_has_ever_without_first_deployed_at_is_invalid():
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(_valid(state="DEPLOYED", has_ever_deployed=True,
                                    first_deployed_at=None))


def test_deployment_pending_without_active_attempt_is_invalid():
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(_valid(state="DEPLOYMENT_PENDING", active_seed_attempt=None))


def test_never_deployed_with_active_nonterminal_attempt_is_invalid():
    with pytest.raises(DeploymentStateInvalid):
        load_deployment_blob(_valid(state="NEVER_DEPLOYED",
                                    active_seed_attempt=_attempt(SeedAttemptStatus.ORDERS_OPEN)))


def test_never_deployed_with_terminal_archived_attempt_is_valid():
    # A terminally-unfilled attempt may co-exist with NEVER_DEPLOYED (retry-eligible).
    b = load_deployment_blob(_valid(
        state="NEVER_DEPLOYED",
        active_seed_attempt=_attempt(SeedAttemptStatus.TERMINALLY_UNFILLED)))
    assert b.state == DeploymentState.NEVER_DEPLOYED


def test_valid_deployed_blob_with_active_attempt_round_trips():
    d = _valid(state="DEPLOYED", has_ever_deployed=True,
               first_deployed_at=T.isoformat(),
               active_seed_attempt=_attempt(SeedAttemptStatus.PARTIALLY_FILLED))
    b = load_deployment_blob(d)
    assert b.state == DeploymentState.DEPLOYED and b.first_deployed_at == T
    assert b.active_seed_attempt.status == SeedAttemptStatus.PARTIALLY_FILLED
    # to_dict -> load is stable
    assert load_deployment_blob(b.to_dict()).to_dict() == b.to_dict()


def test_seed_attempt_serialization_round_trips():
    a = SeedAttempt(
        attempt_id="att-9", created_at=T, intended_symbols=("AAA", "BBB"),
        client_order_id_prefix="seed:11:att-9:", submitted_order_ids=(1, 2),
        status=SeedAttemptStatus.ORDERS_OPEN,
        last_reconciled_fill_at=T, last_reconciled_fill_id=7,
    )
    back = seed_attempt_from_dict(seed_attempt_to_dict(a))
    assert back == a
