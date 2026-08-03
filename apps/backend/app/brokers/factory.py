"""The single governed entry point for obtaining a broker client.

Application code asks the factory; it does not construct clients. That
indirection is what makes the access mode enforceable — a call site cannot
widen its own authority without going through :func:`get_broker_client`, and
the factory refuses to hand back anything mutable unless every trading gate is
satisfied.

Scope note (ADR 0043 WS5, 2026-08-03): this factory governs the **new** boundary
used by the successor WS5 runtime. The pre-existing OrderRouter -> AlpacaAdapter
path is inventoried in ``docs/design/ADR0043_BROKER_ACCESS_MODES.md`` and is not
rerouted here — doing so silently would change behaviour on the live paper box,
which the governing ruling forbids. Those sites remain for adjudication.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

from app.brokers.exceptions import BrokerConfigurationError, BrokerOperationDenied
from app.brokers.policy import BrokerAccessMode, BrokerAccessPolicy
from app.brokers.readonly_client import ReadOnlyBrokerClient
from app.brokers.transport import GovernedTransport

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BrokerCredentialRef:
    """A credential *reference*, never a place to park a secret.

    ``fingerprint`` is a SHA-256 prefix used for audit records. The key and
    secret are supplied by ``resolve`` at call time so no long-lived attribute
    holds them.
    """

    source: str
    fingerprint: str
    resolve: Callable[[], tuple[str, str]]
    #: SHA-256 prefix of the secret, for audit records. Optional so existing
    #: call sites are unaffected; the frozen dataclass means it cannot be
    #: attached after construction.
    secret_fingerprint: str = ""


def get_broker_client(
    *,
    access_mode: str | None,
    credential: BrokerCredentialRef,
    expected_account_id: str | None,
    base_url: str,
    sender: Any,
    strategy_execution_enabled: bool = False,
    scheduler_enabled: bool = False,
) -> ReadOnlyBrokerClient:
    """Return a governed broker client for the configured access mode.

    ``READ_ONLY`` yields a :class:`ReadOnlyBrokerClient`. ``DISABLED`` refuses.
    ``TRADING`` is refused *here* by design: this factory does not vend a
    mutating client, so no WS5-era code path can obtain one. Enabling trading
    requires the existing higher-level authorisation controls, not this seam.
    """
    policy = BrokerAccessPolicy.from_config(
        mode=access_mode,
        strategy_execution_enabled=strategy_execution_enabled,
        scheduler_enabled=scheduler_enabled,
        expected_account_id=expected_account_id,
    )

    if policy.mode is BrokerAccessMode.DISABLED:
        raise BrokerOperationDenied(
            "get_broker_client",
            policy.mode.value,
            "broker access is disabled; set a broker access mode to obtain a client",
        )

    if policy.mode is BrokerAccessMode.TRADING:
        raise BrokerConfigurationError(
            "the governed factory does not vend a trading client; order capability "
            "remains behind the existing OrderRouter authorisation controls"
        )

    if not expected_account_id:
        raise BrokerConfigurationError(
            "expected_account_id is required: a read-only client must be able to "
            "detect an account-identity mismatch (ADR 0043 §10)"
        )

    def _headers() -> dict[str, str]:
        key, secret = credential.resolve()
        return {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "accept": "application/json",
        }

    transport = GovernedTransport(
        policy=policy,
        base_url=base_url,
        sender=sender,
        headers_factory=_headers,
    )
    logger.info(
        "governed_broker_client_created",
        mode=policy.mode.value,
        expected_account_id=expected_account_id,
        credential_source=credential.source,
        credential_fingerprint=credential.fingerprint,
    )
    return ReadOnlyBrokerClient(transport)
