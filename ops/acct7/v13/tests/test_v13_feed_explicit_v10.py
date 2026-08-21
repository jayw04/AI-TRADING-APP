"""P0-B2 invariant: the market-data regime is GOVERNED BY LIMITS v8 and explicit.

Ported to v9 / limits v7 for Transition Protocol v2.1. The invariant is UNCHANGED:
neither v6 nor v7 moves a numeric gate, so the regime this suite proves is still
byte-identical to the one v5 declared.

P0-B1 (owner 2026-08-14): "Changing an Alpaca subscription must never change Strategy 9
execution semantics by itself." P0-B2 (owner Monday flow, adjudicated 2026-08-17) moves
the declaration into the sealed limits file so the manifest records the regime. This
suite fails if any latest-quote/latest-trade request in the executor omits feed=, if the
executor does not bind to limits v5, or if the declared regime drifts from the governed
values: QUOTE plane = sip (cross-asset gates), TRADE plane = iex (single-stock, unchanged).
"""
import ast
import json
import sys
from pathlib import Path

OPS = Path("/app/data/ops/acct7")
sys.path.insert(0, str(OPS))
sys.path.insert(0, "/app")

MOD = OPS / "v13_transition_executor_v10.py"
EXPECTED_QUOTE_FEED = "sip"    # P0-B2 value, declared in limits v5
EXPECTED_TRADE_FEED = "iex"    # unchanged - single-stock trade reference stays IEX

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


tree = ast.parse(MOD.read_text())

# 1/2. every latest-quote / latest-trade request carries feed=
sites = [n for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
         and n.func.id in ("StockLatestQuoteRequest", "StockLatestTradeRequest")]
check("at least one data request exists", len(sites) >= 2, "found %d" % len(sites))
check("EVERY latest request passes feed=",
      all("feed" in {k.arg for k in n.keywords} for n in sites),
      "sites=%d" % len(sites))

# 3. the module binds the governed values FROM LIMITS v8
import v13_transition_executor_v10 as X  # noqa: E402
check("executor binds limits v5",
      str(X.LIMITS_FILE).endswith("v13_frozen_execution_limits_v8.json"),
      str(X.LIMITS_FILE))
check("EXECUTION_QUOTE_FEED == governed value (sip)",
      X.EXECUTION_QUOTE_FEED == EXPECTED_QUOTE_FEED, repr(X.EXECUTION_QUOTE_FEED))
check("EXECUTION_TRADE_FEED == governed value (iex)",
      X.EXECUTION_TRADE_FEED == EXPECTED_TRADE_FEED, repr(X.EXECUTION_TRADE_FEED))

# 3b. the sealed limits file itself declares exactly that regime
_reg = json.loads(X.LIMITS_FILE.read_text()).get("market_data_regime") or {}
check("limits v5 declares the quote feed", _reg.get("execution_quote_feed") == EXPECTED_QUOTE_FEED)
check("limits v5 declares the trade feed", _reg.get("execution_trade_feed") == EXPECTED_TRADE_FEED)
check("limits v5 asserts entitlement independence",
      _reg.get("depends_on_account_entitlement") is False)

# 4. the feed is not read from settings/env/entitlement anywhere in the module
srctext = MOD.read_text()
for forbidden in ("alpaca_data_feed", "getenv(\"ALPACA", "environ[\"ALPACA"):
    check("feed not sourced from %s" % forbidden, forbidden not in srctext)

# 5. the run evidence reports the regime
check("run evidence records market_data_regime", '"market_data_regime"' in srctext)
check("run evidence asserts entitlement independence",
      '"depends_on_account_entitlement": False' in srctext)

# 6. the request objects actually carry the feed through to the SDK
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest  # noqa: E402
q = StockLatestQuoteRequest(symbol_or_symbols="SPY", feed=X.EXECUTION_QUOTE_FEED)
t = StockLatestTradeRequest(symbol_or_symbols="SPY", feed=X.EXECUTION_TRADE_FEED)


def _feed_value(req):
    """The SDK coerces the plain string into a DataFeed enum; compare the VALUE."""
    f = getattr(req, "feed", None)
    return str(getattr(f, "value", f)).lower()


check("quote request materialises feed=sip", _feed_value(q) == EXPECTED_QUOTE_FEED,
      _feed_value(q))
check("trade request materialises feed=iex", _feed_value(t) == EXPECTED_TRADE_FEED,
      _feed_value(t))

passed = sum(1 for _, ok, _ in results if ok)
for name, ok, detail in results:
    print("%-52s %s %s" % (name, "PASS" if ok else "FAIL", detail))
print("\n%d/%d PASS" % (passed, len(results)))
sys.exit(0 if passed == len(results) else 1)
