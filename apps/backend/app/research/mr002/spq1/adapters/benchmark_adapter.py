"""SPY total-return benchmark adapter (Phase 2A domain 4).

Binds the exact SPY series used as the market factor. Any substitution, missing session, or identity
mismatch fails closed REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH. No fallback
benchmark is authorized.
"""
from __future__ import annotations

import numpy as np

from ..calendar import RegisteredCalendar
from ..refusals import refuse

SPY_IDENTITY = "SPY"


def load_spy_adjclose(con, calendar: RegisteredCalendar, ticker: str = SPY_IDENTITY) -> np.ndarray:  # noqa: ANN001
    if ticker != SPY_IDENTITY:
        raise refuse(
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
            f"benchmark must be {SPY_IDENTITY}; no fallback benchmark authorized (got {ticker})",
        )
    rows = con.execute(
        'select "date", adjclose from etf_prices where ticker = ? order by "date"', [ticker]
    ).fetchall()
    by_date = {str(d): float(v) for d, v in rows}
    n = len(calendar)
    out = np.full(n, np.nan, dtype=np.float64)
    for i, ds in enumerate(calendar.sessions):
        if ds in by_date:
            out[i] = by_date[ds]
    return out
