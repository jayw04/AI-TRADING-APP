"""Synthetic, deterministic fixtures for SPQ-1 Phase-1 qualification (no real data).

Builds calendar-aligned market + security series long enough to score a decision at ordinal t=200
(needs 126 stock prices [t-125,t], factor history back to ~t-184, and a 20-session ADV window).
All series are deterministic functions of the session index — no randomness, no files, no network.
"""
from __future__ import annotations

import numpy as np

from app.research.mr002.spq1 import (
    PHASE0_CENSUS_SHA256,
    PHASE0_OWNER_RULINGS_SHA256,
    PHASE0_SCHEMA_SHA256,
    PRODUCER_CODE_VERSION,
)
from app.research.mr002.spq1.calendar import RegisteredCalendar
from app.research.mr002.spq1.eligibility import ExclusionCheck
from app.research.mr002.spq1.identities import InputIdentityRegistry
from app.research.mr002.spq1.producer import MarketData, ProductionRequest, SecurityData
from app.research.mr002.spq1.returns import CellStatus, arithmetic_total_returns
from app.research.mr002.spq1.sector_pit import SectorRecord
from app.research.mr002.spq1.security_identity import LineageRecord, PitIdentityRegistry

N = 201                 # calendar length (ordinals 0..200)
T = 200                 # decision session
CUTOFF = "2020-01-13T21:00:00Z"


def _sessions(n: int = N) -> tuple[str, ...]:
    # Deterministic ascending unique ISO date-like ordinals (not a real calendar).
    return tuple(f"S{i:04d}" for i in range(n))


def _series(seed: float, n: int = N) -> np.ndarray:
    """Deterministic positive price series (smooth + small oscillation), no RNG."""
    idx = np.arange(n, dtype=np.float64)
    return 100.0 + seed + 0.05 * idx + 3.0 * np.sin(idx / (7.0 + seed)) + 1.5 * np.cos(idx / 5.0)


def market_identities() -> dict[str, str]:
    return {
        "registered_exchange_calendar": RegisteredCalendar(_sessions()).identity,
        "spy_total_return_series": "spy-series-id-0001",
        "sector_etf_source_series": "sector-src-id-0001",
        "sector_etf_proxy_mapping_table": "sector-map-id-0001",
        "price_return_adjustment_policy": "v3-adjustment-0001",
        "pit_sector_source": "pit-sector-src-0001",
        "pit_identity_registry": "pit-identity-0001",
        "eligibility_evidence_sources": "elig-evidence-0001",
    }


def build_registry() -> InputIdentityRegistry:
    ids = dict(market_identities())
    ids.update(
        {
            "producer_code_version": PRODUCER_CODE_VERSION,
            "rule_census_identity": PHASE0_CENSUS_SHA256,
            "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
            "schema_identity": PHASE0_SCHEMA_SHA256,
        }
    )
    return InputIdentityRegistry(ids)


def build_market() -> MarketData:
    cal = RegisteredCalendar(_sessions())
    spy = arithmetic_total_returns(_series(1.0))
    tech = arithmetic_total_returns(_series(2.0))
    fin = arithmetic_total_returns(_series(4.0))
    return MarketData(
        calendar=cal,
        spy_ret=spy,
        sector_ret={"TECH": tech, "FIN": fin},
        observed_identities=market_identities(),
    )


def build_lineage(symbol: str = "AAA", permanent_id: str = "PSEC-AAA") -> PitIdentityRegistry:
    return PitIdentityRegistry(
        lineage={
            symbol: (
                LineageRecord(
                    predecessor_permanent_id=None,
                    successor_permanent_id=permanent_id,
                    effective_session_ordinal=0,
                    corporate_action_type="ticker_change",
                    history_continuity_authorized=True,
                    source_evidence_identity="lineage-ev-0001",
                ),
            )
        }
    )


def build_security(
    symbol: str = "AAA",
    sector_id: str = "TECH",
    statuses: list[CellStatus] | None = None,
    excludes_liquidity: bool = False,
) -> SecurityData:
    close = _series(3.0)
    stock = arithmetic_total_returns(close)
    st = statuses if statuses is not None else [CellStatus.PRESENT] * N
    vol = 1_000_000.0 + 500.0 * np.arange(N, dtype=np.float64)
    return SecurityData(
        symbol=symbol,
        stock_ret=stock,
        stock_status=st,
        raw_close=close,
        raw_volume=vol,
        sector_records=[
            SectorRecord(
                sector_id=sector_id,
                availability_timestamp="2019-01-01T00:00:00Z",
                supersession_ordinal=1,
                source_evidence_identity="sector-ev-0001",
            )
        ],
        eligibility_checks=[
            ExclusionCheck(
                rule_id="LIQ-MIN-DOLLARVOL",
                precedence_category="liquidity_or_price",
                excludes=excludes_liquidity,
                observed_value="5.0e7",
                threshold=">=2.5e7",
                source_identity="elig-evidence-0001",
                availability_timestamp="2020-01-10T00:00:00Z",
                evidence_present=True,
            )
        ],
    )


def build_request(side: str = "LONG", config: str = "B") -> ProductionRequest:
    return ProductionRequest(
        program_id="MR-002",
        configuration_id=config,
        side=side,
        t=T,
        decision_cutoff=CUTOFF,
    )
