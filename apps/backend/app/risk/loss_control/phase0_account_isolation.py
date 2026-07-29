"""ADR-0043 Phase-0 CORR-06 — account isolation gate (offline).

Implements AMD-12 isolation rules (BLOCKING):

* Phase-0 retry: no trading or risk-state mutation outside account 3;
* formal canary acceptance: zero account-1 credential-metadata mutation;
* unavoidable shared reads must be declared and proven side-effect-free.

Does not submit orders or import the order path.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Frozen for Phase-0 retry (Controlling Design §6 / AMD-12).
PHASE0_RETRY_ACCOUNT_ID = 3

# Paper stack accounts that must not receive Phase-0 trade/risk mutations.
PROTECTED_NON_RETRY_ACCOUNT_IDS: frozenset[int] = frozenset({1, 2, 4, 5, 6, 7})

# Formal canary acceptance: zero credential-metadata mutation on this account.
CANARY_ZERO_CREDENTIAL_MUTATION_ACCOUNT_ID = 1


class OperationKind(StrEnum):
    TRADE_MUTATION = "TRADE_MUTATION"
    RISK_STATE_MUTATION = "RISK_STATE_MUTATION"
    CREDENTIAL_METADATA_MUTATION = "CREDENTIAL_METADATA_MUTATION"
    SHARED_READ = "SHARED_READ"
    LOCAL_READ = "LOCAL_READ"


class IsolationRefuseReason(StrEnum):
    ACCOUNT_NOT_RESOLVED = "ACCOUNT_NOT_RESOLVED"
    CROSS_ACCOUNT_TRADE_MUTATION = "CROSS_ACCOUNT_TRADE_MUTATION"
    CROSS_ACCOUNT_RISK_MUTATION = "CROSS_ACCOUNT_RISK_MUTATION"
    ACCOUNT1_CREDENTIAL_METADATA_MUTATION = "ACCOUNT1_CREDENTIAL_METADATA_MUTATION"
    SHARED_READ_NOT_DECLARED = "SHARED_READ_NOT_DECLARED"
    SHARED_READ_HAS_SIDE_EFFECTS = "SHARED_READ_HAS_SIDE_EFFECTS"
    UNKNOWN_OPERATION = "UNKNOWN_OPERATION"


@dataclass(frozen=True)
class IsolationDecision:
    allowed: bool
    reason: IsolationRefuseReason | None = None
    detail: str = ""
    disclosure: str | None = None


@dataclass(frozen=True)
class OperationRecord:
    """One audited Phase-0 operation for canary acceptance scoring."""

    account_id: int | None
    kind: OperationKind
    declared_shared_read: bool = False
    side_effect_free: bool = False
    note: str = ""


@dataclass
class OperationLog:
    records: list[OperationRecord] = field(default_factory=list)

    def append(self, record: OperationRecord) -> None:
        self.records.append(record)


def authorize_operation(
    *,
    account_id: int | None,
    kind: OperationKind | str,
    declared_shared_read: bool = False,
    side_effect_free: bool = False,
    disclosure: str | None = None,
) -> IsolationDecision:
    """Authorize a Phase-0 operation under CORR-06 / AMD-12 isolation rules."""
    try:
        op = kind if isinstance(kind, OperationKind) else OperationKind(str(kind))
    except ValueError:
        return IsolationDecision(
            False, IsolationRefuseReason.UNKNOWN_OPERATION, f"unknown kind {kind!r}"
        )

    if account_id is None:
        return IsolationDecision(
            False,
            IsolationRefuseReason.ACCOUNT_NOT_RESOLVED,
            "targeted account resolution required",
        )

    if op == OperationKind.LOCAL_READ:
        return IsolationDecision(True, detail=f"local read account {account_id}")

    if op == OperationKind.SHARED_READ:
        if not declared_shared_read:
            return IsolationDecision(
                False,
                IsolationRefuseReason.SHARED_READ_NOT_DECLARED,
                "shared read must be explicitly declared",
            )
        if not side_effect_free:
            return IsolationDecision(
                False,
                IsolationRefuseReason.SHARED_READ_HAS_SIDE_EFFECTS,
                "shared read must be proven side-effect-free",
            )
        text = disclosure or f"documented side-effect-free shared read of account {account_id}"
        return IsolationDecision(True, detail=text, disclosure=text)

    if op == OperationKind.CREDENTIAL_METADATA_MUTATION:
        if account_id == CANARY_ZERO_CREDENTIAL_MUTATION_ACCOUNT_ID:
            return IsolationDecision(
                False,
                IsolationRefuseReason.ACCOUNT1_CREDENTIAL_METADATA_MUTATION,
                "formal canary acceptance requires zero account-1 credential-metadata mutation",
            )
        # Credential mutation on the retry account is still a mutation — allowed only on
        # account 3 for Phase-0 tooling that must install canary credentials; refused elsewhere.
        if account_id != PHASE0_RETRY_ACCOUNT_ID:
            return IsolationDecision(
                False,
                IsolationRefuseReason.CROSS_ACCOUNT_RISK_MUTATION,
                f"credential-metadata mutation refused for account {account_id} "
                f"(retry account is {PHASE0_RETRY_ACCOUNT_ID})",
            )
        return IsolationDecision(True, detail="credential-metadata mutation on retry account")

    if op in {OperationKind.TRADE_MUTATION, OperationKind.RISK_STATE_MUTATION}:
        if account_id != PHASE0_RETRY_ACCOUNT_ID:
            reason = (
                IsolationRefuseReason.CROSS_ACCOUNT_TRADE_MUTATION
                if op == OperationKind.TRADE_MUTATION
                else IsolationRefuseReason.CROSS_ACCOUNT_RISK_MUTATION
            )
            return IsolationDecision(
                False,
                reason,
                f"{op} refused for account {account_id}; Phase-0 retry is account "
                f"{PHASE0_RETRY_ACCOUNT_ID} only",
            )
        return IsolationDecision(True, detail=f"{op} on retry account {account_id}")

    return IsolationDecision(
        False, IsolationRefuseReason.UNKNOWN_OPERATION, f"unhandled kind {op}"
    )


def record_authorized(
    log: OperationLog,
    *,
    account_id: int | None,
    kind: OperationKind | str,
    declared_shared_read: bool = False,
    side_effect_free: bool = False,
    disclosure: str | None = None,
    note: str = "",
) -> IsolationDecision:
    """Authorize and, if allowed, append to the operation log."""
    decision = authorize_operation(
        account_id=account_id,
        kind=kind,
        declared_shared_read=declared_shared_read,
        side_effect_free=side_effect_free,
        disclosure=disclosure,
    )
    if decision.allowed:
        op = kind if isinstance(kind, OperationKind) else OperationKind(str(kind))
        log.append(
            OperationRecord(
                account_id=account_id,
                kind=op,
                declared_shared_read=declared_shared_read,
                side_effect_free=side_effect_free,
                note=note or (decision.disclosure or decision.detail),
            )
        )
    return decision


@dataclass(frozen=True)
class CanaryAcceptance:
    accepted: bool
    account1_credential_mutations: int
    cross_account_mutations: int
    detail: str
    disclosures: tuple[str, ...] = ()


def assess_canary_acceptance(log: OperationLog) -> CanaryAcceptance:
    """Formal canary acceptance over a recorded operation log (AMD-12)."""
    acct1_cred = 0
    cross = 0
    disclosures: list[str] = []
    for rec in log.records:
        if (
            rec.kind == OperationKind.CREDENTIAL_METADATA_MUTATION
            and rec.account_id == CANARY_ZERO_CREDENTIAL_MUTATION_ACCOUNT_ID
        ):
            acct1_cred += 1
        if rec.kind in {
            OperationKind.TRADE_MUTATION,
            OperationKind.RISK_STATE_MUTATION,
            OperationKind.CREDENTIAL_METADATA_MUTATION,
        } and rec.account_id not in {None, PHASE0_RETRY_ACCOUNT_ID}:
            cross += 1
        if rec.kind == OperationKind.SHARED_READ and rec.note:
            disclosures.append(rec.note)

    if acct1_cred > 0:
        return CanaryAcceptance(
            False,
            acct1_cred,
            cross,
            f"{acct1_cred} account-1 credential-metadata mutation(s) — acceptance fail",
            tuple(disclosures),
        )
    if cross > 0:
        return CanaryAcceptance(
            False,
            acct1_cred,
            cross,
            f"{cross} mutation(s) outside retry account {PHASE0_RETRY_ACCOUNT_ID}",
            tuple(disclosures),
        )
    return CanaryAcceptance(
        True,
        0,
        0,
        "canary acceptance: zero account-1 credential-metadata mutation; "
        f"no trade/risk mutations outside account {PHASE0_RETRY_ACCOUNT_ID}",
        tuple(disclosures),
    )


def isolation_constants() -> dict[str, Any]:
    return {
        "phase0_retry_account_id": PHASE0_RETRY_ACCOUNT_ID,
        "protected_non_retry_account_ids": sorted(PROTECTED_NON_RETRY_ACCOUNT_IDS),
        "canary_zero_credential_mutation_account_id": CANARY_ZERO_CREDENTIAL_MUTATION_ACCOUNT_ID,
    }


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_account_isolation as mod

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
            raise AssertionError(f"phase0_account_isolation must not reference {needle}")


__all__ = [
    "CANARY_ZERO_CREDENTIAL_MUTATION_ACCOUNT_ID",
    "PHASE0_RETRY_ACCOUNT_ID",
    "PROTECTED_NON_RETRY_ACCOUNT_IDS",
    "CanaryAcceptance",
    "IsolationDecision",
    "IsolationRefuseReason",
    "OperationKind",
    "OperationLog",
    "OperationRecord",
    "assert_no_order_path_imports",
    "assess_canary_acceptance",
    "authorize_operation",
    "isolation_constants",
    "record_authorized",
]
