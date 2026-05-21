"""Alpaca broker adapter.

Per ADR 0002, this is the Workbench's ONLY outbound interface to Alpaca.
All order submissions must originate from OrderRouter; no other code path
may import AlpacaAdapter.submit_order directly.
"""

from app.brokers.alpaca.adapter import AlpacaAdapter
from app.brokers.alpaca.credentials import (
    AlpacaCredentials,
    CredentialsError,
    load_credentials,
)
from app.brokers.alpaca.errors import (
    AlpacaError,
    PermanentAlpacaError,
    TransientAlpacaError,
    classify,
)
from app.brokers.alpaca.streaming import TradeUpdatesStream

__all__ = [
    "AlpacaAdapter",
    "AlpacaCredentials",
    "AlpacaError",
    "CredentialsError",
    "PermanentAlpacaError",
    "TradeUpdatesStream",
    "TransientAlpacaError",
    "classify",
    "load_credentials",
]
