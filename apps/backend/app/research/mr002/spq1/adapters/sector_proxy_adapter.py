"""Sector-ETF proxy adapter (Phase 2A domain 5).

Binds each registered sector proxy (frozen sector_id -> ETF mapping) to its total-return series.
A missing or mismatched sector-factor input fails closed; no alternate ETF may be selected because
data are missing.
"""
from __future__ import annotations

import numpy as np

from ..calendar import RegisteredCalendar
from ..refusals import refuse

# Frozen sector_id -> sector-ETF proxy mapping (SPDR Select Sector).
SECTOR_ETF_MAP = {
    "TECH": "XLK", "FIN": "XLF", "ENERGY": "XLE", "INDUSTRIAL": "XLI",
    "UTILITIES": "XLU", "HEALTHCARE": "XLV", "STAPLES": "XLP", "REALESTATE": "XLRE",
    "COMMS": "XLC", "MATERIALS": "XLB", "DISCRETIONARY": "XLY",
}


def load_sector_returns(con, calendar: RegisteredCalendar, sector_ids: list[str]) -> dict[str, np.ndarray]:  # noqa: ANN001
    out: dict[str, np.ndarray] = {}
    for sid in sector_ids:
        etf = SECTOR_ETF_MAP.get(sid)
        if etf is None:
            raise refuse(
                "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
                f"no registered sector-ETF proxy for sector {sid}",
            )
        rows = con.execute(
            'select "date", adjclose from etf_prices where ticker = ? order by "date"', [etf]
        ).fetchall()
        if not rows:
            raise refuse(
                "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
                f"sector-ETF {etf} ({sid}) missing from the dev snapshot",
            )
        by_date = {str(d): float(v) for d, v in rows}
        arr = np.full(len(calendar), np.nan, dtype=np.float64)
        for i, ds in enumerate(calendar.sessions):
            if ds in by_date:
                arr[i] = by_date[ds]
        out[sid] = arr
    return out
