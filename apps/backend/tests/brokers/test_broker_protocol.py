"""P5 §2 — AlpacaAdapter satisfies the BrokerAdapter Protocol.

Construction is network-free (no connect()), so these run without creds or a
broker connection.
"""

from __future__ import annotations

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.credentials import AlpacaCredentials
from app.brokers.base import BrokerAdapter


def _adapter(paper: bool = True) -> AlpacaAdapter:
    return AlpacaAdapter(
        credentials=AlpacaCredentials(api_key="k", api_secret="s", paper=paper)
    )


def test_alpaca_adapter_satisfies_protocol_paper() -> None:
    a = _adapter(paper=True)
    assert isinstance(a, BrokerAdapter)
    assert a.is_paper is True
    assert a.is_connected is False


def test_alpaca_adapter_satisfies_protocol_live() -> None:
    a = _adapter(paper=False)
    assert isinstance(a, BrokerAdapter)
    assert a.is_paper is False


def test_protocol_is_runtime_checkable_rejects_non_adapter() -> None:
    class NotAnAdapter:
        pass

    assert not isinstance(NotAnAdapter(), BrokerAdapter)
