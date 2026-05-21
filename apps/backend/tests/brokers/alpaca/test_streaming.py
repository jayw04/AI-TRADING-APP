import pytest

from app.brokers.alpaca.credentials import AlpacaCredentials
from app.brokers.alpaca.streaming import TradeUpdatesStream


async def test_skeleton_start_raises_not_implemented() -> None:
    creds = AlpacaCredentials(api_key="a", api_secret="b", paper=True)

    async def _handler(_event: dict) -> None:
        pass

    stream = TradeUpdatesStream(credentials=creds, on_update=_handler)
    assert stream.is_started is False
    with pytest.raises(NotImplementedError, match="Session 3"):
        await stream.start()


async def test_skeleton_stop_raises_not_implemented() -> None:
    creds = AlpacaCredentials(api_key="a", api_secret="b", paper=True)

    async def _handler(_event: dict) -> None:
        pass

    stream = TradeUpdatesStream(credentials=creds, on_update=_handler)
    with pytest.raises(NotImplementedError, match="Session 3"):
        await stream.stop()
