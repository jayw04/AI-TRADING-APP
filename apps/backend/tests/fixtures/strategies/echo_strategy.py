"""Test fixture: a strategy that records every hook invocation for assertions.

NOT for production use. Lives under tests/fixtures so it's never loaded by
the real engine (which only resolves paths under ``strategies_user/``).
"""

from app.strategies import Strategy


class EchoStrategy(Strategy):
    name = "echo"
    version = "0.0.1"
    symbols = ["AAPL"]
    schedule = "*/1 * * * *"
    default_params = {"timeframe": "1Min"}

    def __init__(self, ctx, params):
        super().__init__(ctx, params)
        self.bars_seen: list = []
        self.fills_seen: list = []
        self.signals_seen: list = []
        self.init_called = False
        self.shutdown_called = False

    async def on_init(self):
        self.init_called = True

    async def on_bar(self, bar):
        self.bars_seen.append(bar)

    async def on_fill(self, fill):
        self.fills_seen.append(fill)

    async def on_signal(self, signal):
        self.signals_seen.append(signal)

    async def on_shutdown(self):
        self.shutdown_called = True
