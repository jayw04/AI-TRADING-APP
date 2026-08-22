"""Frozen Phase-1 product-admission constants (watchlist design v0.3 / state sync v0.4).

These numbers are **product gates**, not research findings. They are discovery-
ledger entry #0: product-motivated, not evidence-motivated. Changing them
requires a version bump. Outcome-motivated changes belong to governed DISC-001
research, not this module.
"""

from __future__ import annotations

from enum import StrEnum

SCREEN_ID = "DISC-001-WATCHLIST"
SCREEN_VERSION = "v0.3.0"
UNIVERSE_ID = "SEP-liquid-v0"
PRICE_SOURCE_SEP = "sharadar.sep"
PRICE_SOURCE_GAP = "scan.premarket"
PROGRAM_ID = "DISC-001"

# Shared eligibility (§6.1)
MIN_PRICE = 10.0
MIN_ADV_20D = 20_000_000.0
MIN_MARKET_CAP = 1_000_000_000.0
LOOKBACK_TRADING_DAYS = 260
CANDIDATE_UNIVERSE_N = 2000
MAX_PER_FAMILY = 15
MAX_ALL = 30
SEP_STALE_CALENDAR_DAYS = 5

# OVERSOLD (§6.2) — Q3 freeze: close > SMA(200)
RSI14_MAX = 30.0
RET_5D_MAX = -0.08
RSI_PERSIST_MAX = 40.0
RSI_PERSIST_DAYS = 2

# MOM-NEAR (§6.3) — Q5 freeze: continuation within 15% of 52-week high
RS_20_VS_SPY_MIN = 0.0
RS_ACCEL_MIN = 0.0
DIST_52W_MAX = 0.15
RVOL20_MIN = 1.5
SPY_TICKER = "SPY"

# MOM-CORE readout
MOM_CORE_TOP_N = 15
MOM_CORE_UNIVERSE_N = 500

# Snapshot retention (§11 / Q13 / v0.4 freeze)
# Rolling local window: 90 daily files / 90 calendar days. Alert before prune.
# Pinned as-of dates (ledger-cited provenance) are never pruned; copy those to
# governed S3 separately — the local pin is a safety net, not the archive.
SNAPSHOT_RETENTION_DAYS = 90
SNAPSHOT_MAX_FILES = 90
SNAPSHOT_WARN_AT_FILES = 80
SNAPSHOT_SIZE_BUDGET_BYTES = 32 * 1024 * 1024  # 32 MiB; typical file is tens of KB
# Same shared-host floor language as MDQ-001 (greater of 10 GiB); watchlist
# writes are tiny — we alert, we still write today's file, we never write into
# a silent failure.
SNAPSHOT_HOST_FREE_SPACE_FLOOR_BYTES = 10 * 1024 * 1024 * 1024
SNAPSHOT_PINS_FILENAME = "watchlist_pins.json"

# §6.1 halt / pending worthless-removal / merger-close — Phase 1 disposition.
# Session trading halt is not in Sharadar ACTIONS (needs SIP/exchange calendar).
# Pending CA requires a PIT announcement calendar not wired into this adapter.
# Names delisted before as_of are already excluded by universe lifetime bounds
# (firstpricedate/lastpricedate). Phase 1 does not imply this safety context
# has been evaluated. Do not treat absence of a halt chip as "not halted."
HALT_CA_GATE = "deferred_phase1b"
HALT_CA_REASON = (
    "Halt/corporate-action exclusion deferred until Phase 1b: no PIT-safe "
    "session-halt feed, and pending merger/worthless-removal is not wired. "
    "Delisted-before-as_of names are excluded by the PIT universe bounds."
)

# Indicator windows
SMA_TREND = 200
RSI_PERIOD = 14
ADV_WINDOW = 20
RET_5D_BARS = 5
RET_20D_BARS = 20
RET_60D_BARS = 60
HIGH_52W_BARS = 252


class FamilyId(StrEnum):
    OVERSOLD = "OVERSOLD"
    MOM_NEAR = "MOM-NEAR"
    MOM_CORE = "MOM-CORE"
    GAP = "GAP"


class EvidenceStatus(StrEnum):
    """ADR 0037 whitelist plus the MOM-001 source badge (design §5 / §8.4)."""

    WATCH = "Watch"
    BACKTEST_PENDING = "Backtest Pending"
    SOURCE_MOM001 = "Source: MOM-001 · Pattern validated"


# Weakest-badge rule: lower number wins when a name appears in several families.
STATUS_STRENGTH: dict[EvidenceStatus, int] = {
    EvidenceStatus.WATCH: 1,
    EvidenceStatus.BACKTEST_PENDING: 2,
    EvidenceStatus.SOURCE_MOM001: 3,
}

FAMILY_STATUS: dict[FamilyId, EvidenceStatus] = {
    FamilyId.OVERSOLD: EvidenceStatus.WATCH,
    FamilyId.MOM_NEAR: EvidenceStatus.WATCH,
    FamilyId.GAP: EvidenceStatus.BACKTEST_PENDING,
    FamilyId.MOM_CORE: EvidenceStatus.SOURCE_MOM001,
}

FAMILY_HORIZON: dict[FamilyId, str] = {
    FamilyId.OVERSOLD: "1–10d",
    FamilyId.MOM_NEAR: "days–weeks",
    FamilyId.MOM_CORE: "weeks–months",
    FamilyId.GAP: "hours–1d",
}

FAMILY_OPERATOR_NAME: dict[FamilyId, str] = {
    FamilyId.OVERSOLD: "Oversold pullback",
    FamilyId.MOM_NEAR: "Emerging momentum",
    FamilyId.MOM_CORE: "Governed momentum",
    FamilyId.GAP: "Gap",
}

LEDGER_ENTRY_0: dict[str, object] = {
    "entry": 0,
    "program_id": PROGRAM_ID,
    "motivation": "product-motivated, not evidence-motivated",
    "design_document": (
        "docs/Strategies/TradingWorkbench_Opportunity_Page_Watchlist_Design_v0_3.md"
    ),
    "state_sync_document": (
        "docs/Strategies/TradingWorkbench_Opportunity_Page_Watchlist_Design_v0_4.md"
    ),
    "screen_id": SCREEN_ID,
    "screen_version": SCREEN_VERSION,
    "frozen_conditions": {
        "min_price": MIN_PRICE,
        "min_adv_20d": MIN_ADV_20D,
        "min_market_cap": MIN_MARKET_CAP,
        "oversold_rsi14_max": RSI14_MAX,
        "oversold_trend_gate": "close > SMA(200)",
        "oversold_crash_filter": "ret_5d <= -8% OR RSI<40 for >=2 days",
        "mom_near_rs_20_vs_spy_min": RS_20_VS_SPY_MIN,
        "mom_near_rs_20_vs_spy_rule": "absolute > 0 (beats SPY); not a top-P% cut",
        "mom_near_rs_accel_min": RS_ACCEL_MIN,
        "mom_near_dist_52w_max": DIST_52W_MAX,
        "mom_near_mode": "continuation within 15% of 52w high; not breakout",
        "mom_near_rvol20_min_or_volume_rising": RVOL20_MIN,
        "mom_near_drop_mom_core": True,
        "halt_ca_gate": HALT_CA_GATE,
        "halt_ca_reason": HALT_CA_REASON,
        "max_per_family": MAX_PER_FAMILY,
        "max_all": MAX_ALL,
        "newest_bar": "T-1 Sharadar SEP, labelled",
        "etf_policy": "exclude category containing ETF",
        "snapshot_retention_days": SNAPSHOT_RETENTION_DAYS,
        "snapshot_max_files": SNAPSHOT_MAX_FILES,
        "snapshot_size_budget_bytes": SNAPSHOT_SIZE_BUDGET_BYTES,
        "snapshot_host_free_space_floor_bytes": SNAPSHOT_HOST_FREE_SPACE_FLOOR_BYTES,
        "snapshot_prune": "alert then prune oldest unpinned; never drop newest or pins",
    },
    "disclosure": (
        "Any later pre-registration whose conditions materially match this entry "
        "must disclose the inheritance and state whether thresholds were re-derived "
        "independently or adopted from the product surface."
    ),
}
