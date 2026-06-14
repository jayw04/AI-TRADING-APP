"""P9 §1 — point-in-time, survivorship-free factor-data spine.

A standalone, read-only data subsystem (ADR 0018). It ingests the Sharadar
`SEP` / `TICKERS` / `ACTIONS` datatables into a local DuckDB store and exposes
survivorship-free price access plus a point-in-time tradeable universe.

It does NOT import the order path, the risk engine, or `BarCache` — momentum
(§2) reads this cross-sectional spine, not `BarCache.get_bars`. The `BarCache`
provider-abstraction refactor described in ADR 0018 is deferred (§1 §7).
"""

from app.factor_data.store import FactorDataStore
from app.factor_data.universe import UniverseUnavailable, universe_asof

__all__ = ["FactorDataStore", "UniverseUnavailable", "universe_asof"]
