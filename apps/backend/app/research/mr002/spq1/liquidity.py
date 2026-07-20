"""Dollar-volume / ADV (SIG-25 / OWNER-B, RATIFIED). Frozen V3: raw close x raw volume; MEDIAN.

Two windows, both ending t-1 (current session excluded), exactly N observations required:
  - 60-session median: universe + liquidity screen
  - 20-session median: trailing_adv_dollars (the 2% execution-capacity cap)
No mean substitution, shortened window, winsorization, or zero-fill.
"""
from __future__ import annotations

import statistics

import numpy as np

from .constants import ADV_CAPACITY_WINDOW, ADV_SELECTION_WINDOW
from .refusals import refuse

__all__ = ["dollar_volume_median", "trailing_adv_dollars", "selection_adv_dollars"]


def dollar_volume_median(
    raw_close: np.ndarray, raw_volume: np.ndarray, t: int, window: int
) -> float:
    """Median of (raw_close * raw_volume) over the registered window t-window..t-1."""
    raw_close = np.asarray(raw_close, dtype=np.float64)
    raw_volume = np.asarray(raw_volume, dtype=np.float64)
    lo = t - window
    if lo < 0:
        raise refuse(
            "INELIGIBLE:ADV_WINDOW_INSUFFICIENT",
            f"insufficient history for {window}-session ADV ending {t - 1}",
        )
    dv = raw_close[lo:t] * raw_volume[lo:t]
    if dv.shape[0] != window or not np.all(np.isfinite(dv)):
        raise refuse(
            "INELIGIBLE:ADV_WINDOW_INSUFFICIENT",
            f"need exactly {window} finite dollar-volume observations",
        )
    # statistics.median on a fixed-length even window averages the two central values —
    # deterministic; raw close x raw volume pair per frozen V3.
    return float(statistics.median(dv.tolist()))


def trailing_adv_dollars(raw_close: np.ndarray, raw_volume: np.ndarray, t: int) -> float:
    """The candidate fact consumed by the 2% execution cap: 20-session median."""
    return dollar_volume_median(raw_close, raw_volume, t, ADV_CAPACITY_WINDOW)


def selection_adv_dollars(raw_close: np.ndarray, raw_volume: np.ndarray, t: int) -> float:
    """The universe/liquidity screen measure: 60-session median."""
    return dollar_volume_median(raw_close, raw_volume, t, ADV_SELECTION_WINDOW)
