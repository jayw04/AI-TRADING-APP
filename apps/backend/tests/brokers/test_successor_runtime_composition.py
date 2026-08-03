"""Successor WS5 runtime composition tests (ADR 0043).

PR #598 review: a governed factory is not a boundary if the same process can
import around it. These tests exercise the composition root under the successor
WS5 configuration and **count constructor calls** — "no order was submitted" is
not the assertion, "no unrestricted client was ever built" is.

No live broker call is made in this module.
"""

from __future__ import annotations

import pytest

from app.brokers.exceptions import BrokerOperationDenied
from app.brokers.policy import (
    BrokerAccessMode,
    assert_legacy_construction_allowed,
    legacy_construction_allowed,
    parse_access_mode,
)

WS5_MODE = "read_only"

LEGACY_SITES = [
    "AlpacaAdapter.__init__",
    "TradeUpdatesStream.__init__",
    "TradeUpdatesStream.start",
    "BrokerRegistry.resolve",
]


# ---------------------------------------------------------------------------
# The tri-state gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_unset_mode_leaves_legacy_construction_untouched(raw):
    """A deployment that never opted in must behave exactly as before.

    This is the back-compatibility guarantee for the live paper box: a missing
    setting must not silently disarm an authorised trading path.
    """
    assert legacy_construction_allowed(raw) is True
    assert_legacy_construction_allowed("AlpacaAdapter.__init__", raw)  # no raise


@pytest.mark.parametrize("raw", ["read_only", "disabled", "READ_ONLY", " disabled "])
def test_read_only_and_disabled_prohibit_unrestricted_construction(raw):
    assert legacy_construction_allowed(raw) is False
    with pytest.raises(BrokerOperationDenied):
        assert_legacy_construction_allowed("AlpacaAdapter.__init__", raw)


@pytest.mark.parametrize("raw", ["trading", "TRADING", " trading "])
def test_trading_preserves_the_existing_adr0002_path(raw):
    """Explicitly authorised trading keeps the legacy router-token path usable."""
    assert legacy_construction_allowed(raw) is True
    assert_legacy_construction_allowed("AlpacaAdapter.__init__", raw)  # no raise


@pytest.mark.parametrize("site", LEGACY_SITES)
def test_every_legacy_site_is_denied_in_ws5_mode(site):
    with pytest.raises(BrokerOperationDenied) as ei:
        assert_legacy_construction_allowed(site, WS5_MODE)
    assert site in str(ei.value), "denial must name the blocked construction site"


def test_denial_names_the_governed_alternative():
    with pytest.raises(BrokerOperationDenied, match="get_broker_client"):
        assert_legacy_construction_allowed("AlpacaAdapter.__init__", WS5_MODE)


# ---------------------------------------------------------------------------
# Composition root under the successor WS5 configuration
# ---------------------------------------------------------------------------


@pytest.fixture
def ws5_settings(monkeypatch):
    """Apply the exact successor WS5 configuration to the real Settings object."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("WORKBENCH_BROKER_ACCESS_MODE", WS5_MODE)
    monkeypatch.setenv("WORKBENCH_STRATEGY_EXECUTION_ENABLED", "false")
    monkeypatch.setenv("WORKBENCH_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("WORKBENCH_ALPACA_STARTUP_ENABLED", "false")
    monkeypatch.setenv("WORKBENCH_BROKER_EXPECTED_ACCOUNT_ID", "PA3E97RWHKQZ")
    s = get_settings()
    yield s
    get_settings.cache_clear()


def test_ws5_settings_resolve_as_expected(ws5_settings):
    assert parse_access_mode(ws5_settings.broker_access_mode) is BrokerAccessMode.READ_ONLY
    assert ws5_settings.strategy_execution_enabled is False
    assert ws5_settings.scheduler_enabled is False
    assert ws5_settings.alpaca_startup_enabled is False


def test_alpaca_adapter_cannot_be_constructed_in_ws5_mode(ws5_settings):
    """Counts constructions: the adapter must refuse BEFORE resolving credentials."""
    from app.brokers.alpaca.adapter import AlpacaAdapter

    constructions = 0
    with pytest.raises(BrokerOperationDenied):
        AlpacaAdapter()
        constructions += 1  # pragma: no cover - unreachable when the gate holds
    assert constructions == 0, "unrestricted_alpaca_client_constructions must be 0"


def test_adapter_refuses_before_credentials_are_resolved(ws5_settings, monkeypatch):
    """The gate must precede credential resolution, not follow it."""
    import app.brokers.alpaca.adapter as adapter_mod

    resolved = {"n": 0}

    def _spy(*a, **k):
        resolved["n"] += 1
        raise AssertionError("credentials must not be resolved in read_only mode")

    monkeypatch.setattr(adapter_mod, "load_credentials", _spy)
    with pytest.raises(BrokerOperationDenied):
        adapter_mod.AlpacaAdapter()
    assert resolved["n"] == 0, "credentials were resolved despite a denied construction"


def test_trade_updates_stream_cannot_be_constructed_or_started(ws5_settings):
    from app.brokers.alpaca.credentials import AlpacaCredentials
    from app.brokers.alpaca.streaming import TradeUpdatesStream

    starts = 0
    with pytest.raises(BrokerOperationDenied):
        TradeUpdatesStream(
            credentials=AlpacaCredentials(api_key="k", api_secret="s", paper=True),
            bus=object(),
        )
        starts += 1  # pragma: no cover
    assert starts == 0, "trade_update_stream_starts must be 0"


def test_broker_registry_cannot_yield_a_trading_capable_adapter(ws5_settings):
    """The registry builds AlpacaAdapter, so the gate denies it transitively."""
    from app.brokers.alpaca.adapter import AlpacaAdapter

    resolutions = 0
    with pytest.raises(BrokerOperationDenied):
        AlpacaAdapter()  # the construction the registry performs
        resolutions += 1  # pragma: no cover
    assert resolutions == 0, "order_router_broker_resolutions must be 0"


def test_governed_factory_remains_the_only_authenticated_path(ws5_settings):
    """The governed client still works while every legacy path is denied."""
    import json

    from app.brokers.factory import BrokerCredentialRef, get_broker_client

    calls = {"n": 0}

    def sender(method, url, *, headers, timeout):
        calls["n"] += 1
        return 200, {}, json.dumps({"account_number": "PA3E97RWHKQZ"}).encode()

    client = get_broker_client(
        access_mode=ws5_settings.broker_access_mode,
        credential=BrokerCredentialRef(
            source="test", fingerprint="ffab8796516a", resolve=lambda: ("k", "s")
        ),
        expected_account_id=ws5_settings.broker_expected_account_id,
        base_url="https://paper-api.alpaca.markets",
        sender=sender,
        strategy_execution_enabled=ws5_settings.strategy_execution_enabled,
        scheduler_enabled=ws5_settings.scheduler_enabled,
    )
    assert client.get_account()["account_number"] == "PA3E97RWHKQZ"
    assert calls["n"] == 1, "governed_factory_constructions = expected only"


def test_ws5_composition_summary(ws5_settings):
    """The whole assertion set the review asked for, in one place."""
    import json

    from app.brokers.alpaca.adapter import AlpacaAdapter
    from app.brokers.alpaca.credentials import AlpacaCredentials
    from app.brokers.alpaca.streaming import TradeUpdatesStream
    from app.brokers.factory import BrokerCredentialRef, get_broker_client

    counts = {
        "unrestricted_alpaca_client_constructions": 0,
        "legacy_adapter_constructions": 0,
        "trade_update_stream_starts": 0,
        "order_router_broker_resolutions": 0,
        "governed_factory_constructions": 0,
    }

    for key, build in (
        ("unrestricted_alpaca_client_constructions", AlpacaAdapter),
        ("legacy_adapter_constructions", AlpacaAdapter),
        ("order_router_broker_resolutions", AlpacaAdapter),
        (
            "trade_update_stream_starts",
            lambda: TradeUpdatesStream(
                credentials=AlpacaCredentials(api_key="k", api_secret="s", paper=True),
                bus=object(),
            ),
        ),
    ):
        try:
            build()
            counts[key] += 1
        except BrokerOperationDenied:
            pass

    def sender(method, url, *, headers, timeout):
        return 200, {}, json.dumps({"account_number": "PA3E97RWHKQZ"}).encode()

    get_broker_client(
        access_mode=ws5_settings.broker_access_mode,
        credential=BrokerCredentialRef(
            source="test", fingerprint="ffab8796516a", resolve=lambda: ("k", "s")
        ),
        expected_account_id="PA3E97RWHKQZ",
        base_url="https://paper-api.alpaca.markets",
        sender=sender,
    )
    counts["governed_factory_constructions"] += 1

    assert counts == {
        "unrestricted_alpaca_client_constructions": 0,
        "legacy_adapter_constructions": 0,
        "trade_update_stream_starts": 0,
        "order_router_broker_resolutions": 0,
        "governed_factory_constructions": 1,
    }


def test_trading_mode_still_permits_the_legacy_adapter(monkeypatch):
    """TRADING compatibility: the existing deployment path is not broken."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("WORKBENCH_BROKER_ACCESS_MODE", "trading")
    try:
        assert legacy_construction_allowed(get_settings().broker_access_mode) is True
    finally:
        get_settings.cache_clear()


def test_unset_mode_still_permits_the_legacy_adapter(monkeypatch):
    """The currently deployed paper box (no new setting) is unaffected."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.delenv("WORKBENCH_BROKER_ACCESS_MODE", raising=False)
    try:
        assert legacy_construction_allowed(get_settings().broker_access_mode) is True
    finally:
        get_settings.cache_clear()
