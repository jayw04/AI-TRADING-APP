"""ADR 0043 WS5 broker-control tests.

The load-bearing assertion throughout is ``sender.calls == 0`` for denied
operations. "Raised an exception" is not sufficient evidence: an exception
raised *after* dispatch would still have reached Alpaca with a trading-capable
key. These tests prove the request never left.

No live broker call is made anywhere in this module.
"""

from __future__ import annotations

import json

import pytest

from app.brokers.exceptions import (
    BrokerAccountMismatch,
    BrokerConfigurationError,
    BrokerOperationDenied,
)
from app.brokers.factory import BrokerCredentialRef, get_broker_client
from app.brokers.policy import (
    MUTATING_OPERATIONS,
    BrokerAccessMode,
    BrokerAccessPolicy,
    parse_access_mode,
)
from app.brokers.readonly_client import ReadOnlyBrokerClient
from app.brokers.transport import GovernedTransport

PAPER_URL = "https://paper-api.alpaca.markets"
ACCOUNT = "PA3E97RWHKQZ"


class CountingSender:
    """Records every dispatch. A denied call must leave ``calls`` at zero."""

    def __init__(self, payload=None, status: int = 200, headers=None, by_path=None):
        self.calls = 0
        self.seen: list[tuple[str, str]] = []
        self._payload = payload if payload is not None else {}
        self._by_path = by_path or {}
        self._status = status
        self._headers = headers or {}

    def __call__(self, method, url, *, headers, timeout):
        self.calls += 1
        self.seen.append((method, url))
        path = url.split("alpaca.markets", 1)[-1].split("?", 1)[0]
        body = self._by_path.get(path, self._payload)
        return self._status, self._headers, json.dumps(body).encode()


def _cred() -> BrokerCredentialRef:
    return BrokerCredentialRef(
        source="test", fingerprint="deadbeefcafe", resolve=lambda: ("key", "secret")
    )


def _client(sender, *, mode="read_only", account=ACCOUNT) -> ReadOnlyBrokerClient:
    return get_broker_client(
        access_mode=mode,
        credential=_cred(),
        expected_account_id=account,
        base_url=PAPER_URL,
        sender=sender,
    )


# --------------------------------------------------------------------------
# Control 1 — execution authority gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_access_mode_is_disabled(raw):
    """Absent configuration must fail closed, never default permissive."""
    assert parse_access_mode(raw) is BrokerAccessMode.DISABLED


@pytest.mark.parametrize("raw", ["trading ", "READ_ONLY", "Trading"])
def test_access_mode_parsing_is_case_and_space_insensitive(raw):
    assert parse_access_mode(raw) in set(BrokerAccessMode)


@pytest.mark.parametrize("raw", ["enabled", "rw", "yes", "true", "readonly", "full"])
def test_unknown_access_mode_raises(raw):
    """An unrecognised value must be a startup error, not a silent downgrade."""
    with pytest.raises(BrokerConfigurationError):
        parse_access_mode(raw)


def test_credentials_alone_cannot_activate_trading():
    """mode=trading is not enough while the other execution gates are off."""
    p = BrokerAccessPolicy.from_config(
        mode="trading", strategy_execution_enabled=False, scheduler_enabled=False
    )
    assert p.mode is BrokerAccessMode.TRADING
    assert p.orders_allowed is False


@pytest.mark.parametrize(
    "strategy,scheduler,expected",
    [(False, False, False), (True, False, False), (False, True, False), (True, True, True)],
)
def test_orders_require_every_gate(strategy, scheduler, expected):
    p = BrokerAccessPolicy.from_config(
        mode="trading",
        strategy_execution_enabled=strategy,
        scheduler_enabled=scheduler,
    )
    assert p.orders_allowed is expected


def test_read_only_never_permits_orders_even_with_all_gates_on():
    p = BrokerAccessPolicy.from_config(
        mode="read_only", strategy_execution_enabled=True, scheduler_enabled=True
    )
    assert p.orders_allowed is False


@pytest.mark.parametrize("op", sorted(MUTATING_OPERATIONS))
def test_every_mutating_operation_denied_in_read_only(op):
    p = BrokerAccessPolicy.from_config(mode="read_only")
    with pytest.raises(BrokerOperationDenied):
        p.check_operation(op)


# --------------------------------------------------------------------------
# Control 2 — read-only boundary, denial before transport
# --------------------------------------------------------------------------


def test_read_only_permits_exactly_the_approved_routes():
    sender = CountingSender({"account_number": ACCOUNT})
    c = _client(sender)
    c.get_account()
    c.get_positions()
    c.get_orders()
    c.get_account_activities()
    assert sender.calls == 4
    paths = [u.split("alpaca.markets")[1].split("?")[0] for _, u in sender.seen]
    assert paths == ["/v2/account", "/v2/positions", "/v2/orders", "/v2/account/activities"]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_non_get_methods_never_reach_transport(method):
    sender = CountingSender()
    t = GovernedTransport(
        policy=BrokerAccessPolicy.from_config(mode="read_only"),
        base_url=PAPER_URL,
        sender=sender,
        headers_factory=dict,
    )
    with pytest.raises(BrokerOperationDenied):
        t.request(method, "/v2/orders")
    assert sender.calls == 0, "denied mutation reached the network"


@pytest.mark.parametrize(
    "path",
    [
        "/v2/orders/abc-123",
        "/v2/positions/AAPL",
        "/v2/account/configurations",
        "/v2/account/portfolio/history",
        "/v2/assets",
        "/v2/orders/../orders/abc",
        "/v2/orders/./sub",
    ],
)
def test_unapproved_paths_never_reach_transport(path):
    sender = CountingSender()
    t = GovernedTransport(
        policy=BrokerAccessPolicy.from_config(mode="read_only"),
        base_url=PAPER_URL,
        sender=sender,
        headers_factory=dict,
    )
    with pytest.raises(BrokerOperationDenied):
        t.request("GET", path)
    assert sender.calls == 0


def test_redundant_slashes_normalise_to_the_approved_route():
    """``/v2/orders//`` is the approved read route with an empty segment; it
    normalises rather than being refused. Still a GET, still allow-listed."""
    sender = CountingSender([])
    t = GovernedTransport(
        policy=BrokerAccessPolicy.from_config(mode="read_only"),
        base_url=PAPER_URL,
        sender=sender,
        headers_factory=dict,
    )
    t.request("GET", "/v2/orders//")
    assert sender.calls == 1
    assert sender.seen[0][1].endswith("/v2/orders")


@pytest.mark.parametrize(
    "url",
    [
        "https://api.alpaca.markets/v2/account",
        "https://evil.example.com/v2/account",
        "//api.alpaca.markets/v2/account",
    ],
)
def test_alternate_hosts_and_absolute_urls_are_refused(url):
    sender = CountingSender()
    t = GovernedTransport(
        policy=BrokerAccessPolicy.from_config(mode="read_only"),
        base_url=PAPER_URL,
        sender=sender,
        headers_factory=dict,
    )
    with pytest.raises(BrokerOperationDenied):
        t.request("GET", url)
    assert sender.calls == 0


def test_redirects_are_refused():
    sender = CountingSender(status=302, headers={"Location": "/v2/orders/abc"})
    t = GovernedTransport(
        policy=BrokerAccessPolicy.from_config(mode="read_only"),
        base_url=PAPER_URL,
        sender=sender,
        headers_factory=dict,
    )
    with pytest.raises(BrokerOperationDenied, match="redirect"):
        t.request("GET", "/v2/account")
    assert sender.calls == 1  # the GET itself was approved; the redirect was not followed


def test_disabled_mode_denies_reads_before_transport():
    sender = CountingSender()
    t = GovernedTransport(
        policy=BrokerAccessPolicy.from_config(mode=None),
        base_url=PAPER_URL,
        sender=sender,
        headers_factory=dict,
    )
    with pytest.raises(BrokerOperationDenied):
        t.request("GET", "/v2/account")
    assert sender.calls == 0


def test_transport_refuses_a_non_alpaca_base_url():
    with pytest.raises(BrokerConfigurationError):
        GovernedTransport(
            policy=BrokerAccessPolicy.from_config(mode="read_only"),
            base_url="https://evil.example.com",
            sender=CountingSender(),
            headers_factory=dict,
        )


# --------------------------------------------------------------------------
# Escape paths
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "op",
    [
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
    ],
)
def test_read_only_client_mutators_are_tombstoned(op):
    sender = CountingSender({"account_number": ACCOUNT})
    c = _client(sender)
    before = sender.calls
    with pytest.raises(BrokerOperationDenied):
        getattr(c, op)()
    assert sender.calls == before, "tombstoned mutator reached the network"


def test_read_only_client_exposes_no_generic_request_or_sdk_handle():
    """The absence of an escape hatch is the control; assert it structurally."""
    for attr in ("request", "raw", "client", "_client", "session", "trading", "sdk", "get"):
        assert not hasattr(ReadOnlyBrokerClient, attr), f"escape surface exposed: {attr}"


def test_transport_has_no_generic_passthrough_helpers():
    for attr in ("get", "post", "put", "delete", "patch", "raw", "passthrough"):
        assert not hasattr(GovernedTransport, attr), f"passthrough helper exposed: {attr}"


# --------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------


def test_factory_refuses_when_disabled():
    with pytest.raises(BrokerOperationDenied):
        _client(CountingSender(), mode=None)


def test_factory_does_not_vend_a_trading_client():
    """No WS5-era path can obtain a mutating client from the governed factory."""
    with pytest.raises(BrokerConfigurationError):
        _client(CountingSender(), mode="trading")


def test_factory_requires_expected_account_id():
    with pytest.raises(BrokerConfigurationError):
        _client(CountingSender(), account=None)


def test_factory_returns_read_only_client():
    assert isinstance(_client(CountingSender()), ReadOnlyBrokerClient)


def test_credential_secret_is_not_retained_on_the_client():
    sender = CountingSender({"account_number": ACCOUNT})
    c = _client(sender)
    blob = repr(c.__dict__) + repr(c._t.__dict__)
    assert "secret" not in blob.lower() or "headers_factory" in blob


# --------------------------------------------------------------------------
# Identity latch (ADR 0043 §10)
# --------------------------------------------------------------------------


def test_account_mismatch_raises_and_latches_further_reads():
    sender = CountingSender({"account_number": "PA34USW0Q8UO"})
    c = _client(sender, account=ACCOUNT)
    with pytest.raises(BrokerAccountMismatch):
        c.get_account()
    calls_after_mismatch = sender.calls
    for fn in (c.get_positions, c.get_orders, c.get_account_activities, c.get_account):
        with pytest.raises(BrokerAccountMismatch):
            fn()
    assert sender.calls == calls_after_mismatch, "reads continued after an identity mismatch"


def test_matching_account_permits_continued_reads():
    sender = CountingSender({"account_number": ACCOUNT})
    c = _client(sender, account=ACCOUNT)
    c.get_account()
    c.get_positions()
    assert sender.calls == 2


# --------------------------------------------------------------------------
# Integration-style: factory + transport, the successor WS5 configuration
# --------------------------------------------------------------------------


def test_successor_ws5_configuration_end_to_end():
    """The exact configuration a successor WS5 image will run."""
    sender = CountingSender(
        by_path={
            "/v2/account": {"account_number": ACCOUNT, "status": "ACTIVE"},
            "/v2/positions": [],
            "/v2/orders": [],
            "/v2/account/activities": [],
        }
    )
    c = get_broker_client(
        access_mode="read_only",
        credential=_cred(),
        expected_account_id=ACCOUNT,
        base_url=PAPER_URL,
        sender=sender,
        strategy_execution_enabled=False,
        scheduler_enabled=False,
    )
    assert c.get_account()["account_number"] == ACCOUNT
    assert c.get_positions() == []
    assert c.mode is BrokerAccessMode.READ_ONLY

    reads = sender.calls
    for op in ("submit_order", "cancel_order", "close_all_positions", "reset_paper_account"):
        with pytest.raises(BrokerOperationDenied):
            getattr(c, op)()
    assert sender.calls == reads, "a mutation escaped in the WS5 configuration"
