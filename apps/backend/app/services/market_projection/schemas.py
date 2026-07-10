"""Frozen enums, versions, and manifests for MKT-PROJ-001 (pre-registration v1.0).

These constants ARE the freeze: changing any of them is a new feature/label
version and restarts the affected evidence (pre-registration §5/§10).
"""

from __future__ import annotations

from enum import StrEnum

FEATURE_VERSION = "mktproj-fv1"
LABEL_VERSION = "mktproj-lv1"

# Material-move threshold (pre-registration §2): max(floor, mult × ATR20_pct),
# ATR through the last fully completed regular session before the forecast.
THRESHOLD_FLOOR_PCT = 0.60
THRESHOLD_ATR_MULT = 0.50
ATR_WINDOW = 20

MARKET_PROXY = "SPY"
SECTOR_BASKET = ("XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC")
GAP_SYMBOLS = ("SPY", "QQQ", "IWM")
VOLUME_TOD_LOOKBACK = 20   # sessions for the time-of-day-matched volume baseline
LATE_DAY_START_ET = "14:30"
FORECAST_OFFSET_MIN = 15   # forecast at close − 15 minutes
PREOPEN_FORECAST_ET = "09:20"


class ProjectionType(StrEnum):
    PRE_CLOSE_TOMORROW = "PRE_CLOSE_TOMORROW"  # primary: close(t+1) vs close(t)
    PRE_OPEN_TODAY = "PRE_OPEN_TODAY"          # secondary: close(t) vs open(t)


class Label(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


# The frozen production feature manifests (pre-registration §5). Order is the
# model's column order; infer.py refuses to run on a mismatch.
PREOPEN_FEATURES: tuple[str, ...] = (
    "spy_gap_pct_qf", "qqq_gap_pct_qf", "iwm_gap_pct_qf",
    "spy_gap_quality", "qqq_gap_quality", "iwm_gap_quality",
    "spy_ret_1d", "spy_ret_5d", "spy_realized_vol_20d", "atr20_pct",
    "spy_dist_ma20", "spy_dist_ma50", "spy_dist_ma200",
    "regime_trend", "regime_vol",
)

PRECLOSE_FEATURES: tuple[str, ...] = (
    "spy_intraday_ret", "qqq_intraday_ret", "iwm_intraday_ret", "spy_late_day_ret",
    "sector_breadth", "up_sector_count", "sector_coverage_count",
    "spy_volume_vs_20d_tod", "spy_intraday_vol", "spy_hl_range_pct", "fade_recovery",
    # daily context (same construction as pre-open)
    "spy_ret_1d", "spy_ret_5d", "spy_realized_vol_20d", "atr20_pct",
    "spy_dist_ma20", "spy_dist_ma50", "spy_dist_ma200",
    "regime_trend", "regime_vol",
)
