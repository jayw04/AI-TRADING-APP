"""Read-only broker client for ADR 0043 WS5 reconciliation.

Exposes exactly the four reads WS5 §6 authorises and nothing else. There is no
``request()``, no ``client`` property, no order method, and no way to reach the
alpaca-py SDK object from here — the absence is the control. A caller that
needs something else must have the authorisation changed, not find a hole.

Results are plain dicts drawn from the broker payload rather than SDK objects,
so callers cannot navigate from a returned value back to a mutable client.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.brokers.exceptions import BrokerAccountMismatch, BrokerOperationDenied
from app.brokers.policy import BrokerAccessMode
from app.brokers.transport import GovernedTransport

logger = structlog.get_logger(__name__)


class ReadOnlyBrokerClient:
    """The only broker surface a WS5 runtime may hold."""

    def __init__(self, transport: GovernedTransport) -> None:
        self._t = transport
        self._identity_verified = False
        self._latched_mismatch: BrokerAccountMismatch | None = None

    @property
    def mode(self) -> BrokerAccessMode:
        return self._t.policy.mode

    # ---- approved reads ----

    def get_account(self) -> dict[str, Any]:
        """``GET /v2/account``. Also performs the identity check (§10)."""
        self._guard()
        data = self._t.request("GET", "/v2/account") or {}
        self._verify_identity(data)
        return data

    def get_positions(self) -> list[dict[str, Any]]:
        """``GET /v2/positions``."""
        self._guard()
        return list(self._t.request("GET", "/v2/positions") or [])

    def get_orders(self, *, status: str = "all", limit: int = 500) -> list[dict[str, Any]]:
        """``GET /v2/orders``. Query parameters only; the route is fixed."""
        self._guard()
        return list(
            self._t.request("GET", "/v2/orders", params={"status": status, "limit": limit}) or []
        )

    def get_account_activities(self) -> list[dict[str, Any]]:
        """``GET /v2/account/activities``."""
        self._guard()
        return list(self._t.request("GET", "/v2/account/activities") or [])

    # ---- identity latch ----

    def _verify_identity(self, account: dict[str, Any]) -> None:
        expected = self._t.policy.expected_account_id
        if not expected:
            self._identity_verified = True
            return
        actual = str(account.get("account_number") or "")
        if actual != expected:
            self._latched_mismatch = BrokerAccountMismatch(expected, actual)
            logger.error("broker_account_identity_mismatch", expected=expected, actual=actual)
            raise self._latched_mismatch
        self._identity_verified = True

    def _guard(self) -> None:
        """Refuse further reads once an identity mismatch has been seen.

        ADR 0043 §10 makes a broker-identity mismatch a stop condition, so the
        client must not keep serving reads from an account it already knows is
        the wrong one.
        """
        if self._latched_mismatch is not None:
            raise self._latched_mismatch
        if not self._t.policy.reads_allowed:
            raise BrokerOperationDenied(
                "read", self._t.policy.mode.value, "broker access is disabled"
            )


def _denied(name: str):  # pragma: no cover - defensive
    def _raise(*_a: Any, **_k: Any) -> Any:
        raise BrokerOperationDenied(name, "read_only", "not available on the read-only client")

    return _raise


# Explicit tombstones. These names exist ONLY to fail loudly and to make the
# deny surface greppable; binding them prevents a future refactor from
# reintroducing a permissive method under a familiar name by accident.
for _op in (
    "submit_order",
    "replace_order",
    "cancel_order",
    "cancel_all_orders",
    "close_position",
    "close_all_positions",
    "update_account_configuration",
    "reset_paper_account",
    "create_transfer",
    "raw_request",
):
    setattr(ReadOnlyBrokerClient, _op, _denied(_op))
del _op
