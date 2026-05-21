import pytest

from app.brokers.alpaca.credentials import (
    AlpacaCredentials,
    CredentialsError,
    load_credentials,
)
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Each test must hit a fresh Settings since env vars change between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_paper_credentials_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "paper")
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "PK_TEST")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "SECRET_TEST")
    get_settings.cache_clear()

    creds = load_credentials()
    assert isinstance(creds, AlpacaCredentials)
    assert creds.paper is True
    assert creds.api_key == "PK_TEST"
    assert "paper-api" in creds.base_url


def test_live_mode_requires_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "live")
    monkeypatch.setenv("WORKBENCH_LIVE_ACK", "")
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "PK_LIVE")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "SECRET_LIVE")
    get_settings.cache_clear()

    with pytest.raises(CredentialsError, match="WORKBENCH_LIVE_ACK"):
        load_credentials()


def test_live_mode_requires_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "live")
    monkeypatch.setenv("WORKBENCH_LIVE_ACK", "I_UNDERSTAND")
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "")
    get_settings.cache_clear()

    with pytest.raises(CredentialsError, match="ALPACA_LIVE_API_KEY"):
        load_credentials()


def test_unknown_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "yolo")
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "PK_TEST")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "SECRET_TEST")
    get_settings.cache_clear()

    with pytest.raises(CredentialsError, match="paper.*live"):
        load_credentials()


def test_paper_mode_requires_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "paper")
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "")
    get_settings.cache_clear()

    with pytest.raises(CredentialsError, match="ALPACA_PAPER_API_KEY"):
        load_credentials()


def test_credentials_base_url_paper_vs_live() -> None:
    paper = AlpacaCredentials(api_key="a", api_secret="b", paper=True)
    live = AlpacaCredentials(api_key="a", api_secret="b", paper=False)
    assert paper.base_url == "https://paper-api.alpaca.markets"
    assert live.base_url == "https://api.alpaca.markets"
