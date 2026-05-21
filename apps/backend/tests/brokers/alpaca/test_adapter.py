"""Adapter tests with the underlying TradingClient mocked.

Session 1 only verifies wiring; the live-paper integration smoke is the
manual REPL step at the end of the session, not run in CI.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.brokers.alpaca.adapter import AlpacaAdapter
from app.brokers.alpaca.credentials import AlpacaCredentials


@pytest.fixture
def paper_creds() -> AlpacaCredentials:
    return AlpacaCredentials(api_key="PK_TEST", api_secret="SECRET_TEST", paper=True)


def test_init_does_not_connect(paper_creds: AlpacaCredentials) -> None:
    a = AlpacaAdapter(credentials=paper_creds)
    assert a.is_paper is True
    assert a.is_connected is False


def test_connect_verifies_by_get_account(paper_creds: AlpacaCredentials) -> None:
    with patch("alpaca.trading.client.TradingClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.get_account.return_value = MagicMock(
            model_dump=lambda mode=None: {"status": "ACTIVE", "buying_power": "100000"}
        )
        MockClient.return_value = mock_instance

        a = AlpacaAdapter(credentials=paper_creds)
        a.connect()

        assert a.is_connected is True
        mock_instance.get_account.assert_called()


def test_disconnect_resets_state(paper_creds: AlpacaCredentials) -> None:
    with patch("alpaca.trading.client.TradingClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.get_account.return_value = MagicMock(
            model_dump=lambda mode=None: {"status": "ACTIVE"}
        )
        MockClient.return_value = mock_instance

        a = AlpacaAdapter(credentials=paper_creds)
        a.connect()
        assert a.is_connected is True
        a.disconnect()
        assert a.is_connected is False


def test_get_positions_returns_list(paper_creds: AlpacaCredentials) -> None:
    with patch("alpaca.trading.client.TradingClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.get_account.return_value = MagicMock(
            model_dump=lambda mode=None: {"status": "ACTIVE"}
        )
        mock_instance.get_all_positions.return_value = [
            MagicMock(model_dump=lambda mode=None: {"symbol": "AAPL", "qty": "5"}),
            MagicMock(model_dump=lambda mode=None: {"symbol": "MSFT", "qty": "3"}),
        ]
        MockClient.return_value = mock_instance

        a = AlpacaAdapter(credentials=paper_creds)
        a.connect()
        positions = a.get_positions()
        assert len(positions) == 2
        assert positions[0]["symbol"] == "AAPL"


def test_submit_order_not_implemented_per_adr0002(paper_creds: AlpacaCredentials) -> None:
    a = AlpacaAdapter(credentials=paper_creds)
    with pytest.raises(NotImplementedError, match="OrderRouter"):
        a.submit_order(symbol="AAPL", qty=1, side="buy")


def test_cancel_order_not_implemented(paper_creds: AlpacaCredentials) -> None:
    a = AlpacaAdapter(credentials=paper_creds)
    with pytest.raises(NotImplementedError, match="Session 4"):
        a.cancel_order("fake-order-id")


def test_replace_order_not_implemented(paper_creds: AlpacaCredentials) -> None:
    a = AlpacaAdapter(credentials=paper_creds)
    with pytest.raises(NotImplementedError, match="Session 4"):
        a.replace_order("fake-order-id", new_qty=2)
