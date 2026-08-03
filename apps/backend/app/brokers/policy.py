"""Broker access policy — the ADR 0043 WS5 execution-authority gate (Control 1).

The rule this module exists to enforce: **possessing a trading-capable
credential must not confer trading capability.** Alpaca issues no read-only
scope for paper API keys, so any valid key can submit orders. Separating
"can authenticate" from "may mutate" therefore has to happen here, in code,
not in an operator's environment file.

Failure posture:

* configuration absent      -> :data:`BrokerAccessMode.DISABLED`
* configuration unrecognised -> :class:`BrokerConfigurationError` at startup
* nothing                    -> silently permissive

``TRADING`` additionally requires the strategy-execution and scheduler gates to
be on, so order capability can never rest on a single boolean.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.brokers.exceptions import BrokerConfigurationError, BrokerOperationDenied


class BrokerAccessMode(StrEnum):
    """How much of the broker surface the process may reach."""

    DISABLED = "disabled"
    READ_ONLY = "read_only"
    TRADING = "trading"


#: The only routes reachable in READ_ONLY. Exact paths, no prefixes: a prefix
#: rule would admit ``/v2/orders`` *and* every sub-route beneath it, including
#: the DELETE-all route. Matching is exact and method-scoped.
READ_ONLY_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v2/account"),
        ("GET", "/v2/positions"),
        ("GET", "/v2/orders"),
        ("GET", "/v2/account/activities"),
    }
)

#: Operations that must fail closed in any non-TRADING mode. Named explicitly so
#: the deny list is auditable against ADR 0043 §6 rather than inferred from the
#: absence of an allow entry.
MUTATING_OPERATIONS: frozenset[str] = frozenset(
    {
        "submit_order",
        "replace_order",
        "cancel_order",
        "cancel_all_orders",
        "close_position",
        "close_all_positions",
        "update_account_configuration",
        "reset_paper_account",
        "create_transfer",
        "delete_transfer",
        "raw_request",
    }
)


def parse_access_mode(raw: str | None) -> BrokerAccessMode:
    """Resolve a configured access mode, failing closed.

    ``None`` and ``""`` mean "not configured" and yield ``DISABLED``. Anything
    else must be a known mode; an unrecognised value is a configuration error,
    never a silent downgrade *or* upgrade.
    """
    if raw is None or not str(raw).strip():
        return BrokerAccessMode.DISABLED
    value = str(raw).strip().lower()
    try:
        return BrokerAccessMode(value)
    except ValueError:
        known = ", ".join(sorted(m.value for m in BrokerAccessMode))
        raise BrokerConfigurationError(
            f"unknown broker access mode {raw!r}; expected one of: {known}"
        ) from None


@dataclass(frozen=True)
class BrokerAccessPolicy:
    """An immutable decision about what this process may do at the broker.

    Constructed once from configuration and passed down. Frozen so a call site
    cannot widen its own permissions after the fact.
    """

    mode: BrokerAccessMode
    strategy_execution_enabled: bool = False
    scheduler_enabled: bool = False
    expected_account_id: str | None = None

    @classmethod
    def from_config(
        cls,
        *,
        mode: str | None,
        strategy_execution_enabled: bool = False,
        scheduler_enabled: bool = False,
        expected_account_id: str | None = None,
    ) -> BrokerAccessPolicy:
        return cls(
            mode=parse_access_mode(mode),
            strategy_execution_enabled=bool(strategy_execution_enabled),
            scheduler_enabled=bool(scheduler_enabled),
            expected_account_id=(expected_account_id or None),
        )

    # ---- derived authority ----

    @property
    def reads_allowed(self) -> bool:
        return self.mode in (BrokerAccessMode.READ_ONLY, BrokerAccessMode.TRADING)

    @property
    def orders_allowed(self) -> bool:
        """Order capability needs *every* gate, not merely the mode.

        A trading-capable key plus ``mode=trading`` is still insufficient while
        strategy execution or the scheduler is off.
        """
        return (
            self.mode is BrokerAccessMode.TRADING
            and self.strategy_execution_enabled
            and self.scheduler_enabled
        )

    # ---- enforcement ----

    def check_route(self, method: str, path: str) -> None:
        """Authorise one HTTP route, or raise before anything is dispatched."""
        m = (method or "").upper()
        p = normalise_path(path)

        if self.mode is BrokerAccessMode.DISABLED:
            raise BrokerOperationDenied(f"{m} {p}", self.mode.value, "broker access is disabled")

        if self.mode is BrokerAccessMode.READ_ONLY:
            if m != "GET":
                raise BrokerOperationDenied(f"{m} {p}", self.mode.value, "only GET is permitted")
            if (m, p) not in READ_ONLY_ROUTES:
                raise BrokerOperationDenied(
                    f"{m} {p}", self.mode.value, "route is not on the read-only allow-list"
                )
            return

        # TRADING: mutation still requires the full gate set.
        if m != "GET" and not self.orders_allowed:
            raise BrokerOperationDenied(
                f"{m} {p}",
                self.mode.value,
                "trading mode requires strategy_execution_enabled and scheduler_enabled",
            )

    def check_operation(self, operation: str) -> None:
        """Authorise a named adapter-level operation before it builds a request."""
        if operation in MUTATING_OPERATIONS and not self.orders_allowed:
            raise BrokerOperationDenied(operation, self.mode.value)
        if not self.reads_allowed:
            raise BrokerOperationDenied(operation, self.mode.value, "broker access is disabled")


def normalise_path(path: str) -> str:
    """Reduce a path to the form the allow-list is written in.

    Strips the query string and any trailing slash, and collapses ``.`` / ``..``
    segments so ``/v2/orders/../orders/abc`` cannot masquerade as ``/v2/orders``.
    """
    p = (path or "").split("?", 1)[0].split("#", 1)[0]
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts) if parts else "/"
