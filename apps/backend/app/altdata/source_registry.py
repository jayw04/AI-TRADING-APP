"""Data Source Registry (EAD; ADR 0037 §6.4, DCAP-007).

A first-class entitlement/metadata record per external data source, populated **before** the
source is ingested. The ``commercial_use_allowed`` / ``derived_signal_allowed`` /
``cache_allowed`` flags are load-bearing: they gate what the Daily Opportunity Report may expose
externally (ADR 0037 §2.4 / §4.3). Read-only, off the order path.

v0 is an in-code registry (a DB table can replace it later without changing consumers).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataSource:
    source_id: str                     # DCAP id, e.g. "DCAP-007"
    source_name: str                   # the CorporateEvent.source value, e.g. "quiver"
    provider: str
    datasets_enabled: tuple[str, ...]
    license_type: str                  # "hobbyist" | "trader" | "commercial" | "public" | ...
    commercial_use_allowed: bool
    redistribution_allowed: bool
    cache_allowed: bool                # may we persist/cache the raw data (internal research)?
    derived_signal_allowed: bool       # may we expose derived scores/alerts/rankings?
    refresh_frequency: str
    known_latency: str
    point_in_time_supported: bool
    contact_owner: str
    renewal_date: str | None           # ISO date, or None for month-to-month

    @property
    def customer_facing_allowed(self) -> bool:
        """A card built on this source may be shown externally ONLY if commercial + derived-signal
        rights are held (redistribution/cache are separately required for raw redistribution).
        Internal R&D use does not require these."""
        return self.commercial_use_allowed and self.derived_signal_allowed


# Quiver Quant — Hobbyist plan (verified 2026-07-05): No Commercial Use Rights on Hobbyist OR
# Trader; Commercial is contact-priced. Internal R&D only until a written Commercial license.
QUIVER_GOVCONTRACTS = DataSource(
    source_id="DCAP-007",
    source_name="quiver",
    provider="Quiver Quant",
    datasets_enabled=("government_contracts",),
    license_type="hobbyist",
    commercial_use_allowed=False,      # ADR 0037 §2.4 — blocks any external card
    redistribution_allowed=False,
    cache_allowed=True,                # internal research caching (the Event Store) is fine
    derived_signal_allowed=False,      # no external derived scores/rankings pre-Commercial
    refresh_frequency="daily",
    known_latency="disclosure lag ~days (uncalibrated — pending USAspending cross-check)",
    point_in_time_supported=True,
    contact_owner="Jay Wang (GlobalComplyAI, LLC)",
    renewal_date=None,                 # month-to-month
)

# Alpaca market data (IEX feed) — movers screener + snapshots feeding the box-native
# premarket gapper screener (GAP-NATIVE-001, ADR 0041). Existing approved dependency;
# conservative flags: internal advisory display only, no redistribution, no external
# derived signals. SIP is NOT entitled (probe 2026-07-10).
ALPACA_SCREENER = DataSource(
    source_id="DCAP-008",
    source_name="alpaca_screener",
    provider="Alpaca Markets",
    datasets_enabled=("market_movers", "stock_snapshots"),
    license_type="brokerage_market_data",
    commercial_use_allowed=False,      # conservative default — internal advisory use only
    redistribution_allowed=False,
    cache_allowed=True,                # the daily gappers JSON is a persisted derivative
    derived_signal_allowed=False,      # no external derived scores/rankings
    refresh_frequency="daily (09:05 ET scan; movers/snapshots are real-time reads)",
    known_latency="IEX feed only — premarket coverage thinner than consolidated tape",
    point_in_time_supported=False,     # live reads; the dated gappers file is the PIT record
    contact_owner="Jay Wang (GlobalComplyAI, LLC)",
    renewal_date=None,
)

_REGISTRY: dict[str, DataSource] = {
    ds.source_name: ds for ds in (QUIVER_GOVCONTRACTS, ALPACA_SCREENER)
}


def get_source(source_name: str) -> DataSource | None:
    """Look up a registered source by its ``CorporateEvent.source`` value (e.g. ``"quiver"``)."""
    return _REGISTRY.get(source_name)


def all_sources() -> tuple[DataSource, ...]:
    return tuple(_REGISTRY.values())
