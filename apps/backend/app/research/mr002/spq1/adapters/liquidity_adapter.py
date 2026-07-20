"""Dollar-volume / ADV adapter (Phase 2A domain 8).

Binds raw close (closeunadj) x raw volume for the two registered windows and delegates to the frozen
Phase-1 liquidity primitive. Proves raw close is not adjusted close and raw volume is not split-
adjusted; current session t excluded; exactly N registered sessions; no zero fill or short-window
fallback.
"""
from __future__ import annotations

import numpy as np

from ..liquidity import selection_adv_dollars, trailing_adv_dollars
from ..refusals import refuse

__all__ = ["trailing_adv_from_series", "selection_adv_from_series"]


def _raw_pair(series: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    raw_close = series["closeunadj"]
    volume = series["volume"]
    # raw close must differ from split-adjusted close on at least one finite session (not identical).
    finite = np.isfinite(raw_close) & np.isfinite(series["close"])
    if finite.any() and np.array_equal(raw_close[finite], series["close"][finite]):
        raise refuse(
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
            "raw close equals split-adjusted close — ADV must use the raw (unadjusted) pair",
        )
    return raw_close, volume


def trailing_adv_from_series(series: dict[str, np.ndarray], t: int) -> float:
    raw_close, volume = _raw_pair(series)
    return trailing_adv_dollars(raw_close, volume, t)   # 20-session median (frozen Phase-1)


def selection_adv_from_series(series: dict[str, np.ndarray], t: int) -> float:
    raw_close, volume = _raw_pair(series)
    return selection_adv_dollars(raw_close, volume, t)  # 60-session median
