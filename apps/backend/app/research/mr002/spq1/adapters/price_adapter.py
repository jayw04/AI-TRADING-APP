"""Price/return-series adapter (Phase 2A domain 3).

Binds the registered V3 price identities and proves they are NOT interchangeable:
  signal returns          closeadj  (total-return-adjusted)
  raw close (ADV)         closeunadj
  split-adjusted close    close     (gap/execution context)
  execution open          open
  raw volume              volume
Values must be finite; prices positive where required; volume non-negative; one row per
security/session; registered-session membership. A cross-series substitution is a detectable error.
"""
from __future__ import annotations

import numpy as np

from ..calendar import RegisteredCalendar
from ..refusals import refuse

V3_FIELD_IDENTITY = {
    "signal_total_return_close": "closeadj",
    "raw_close": "closeunadj",
    "split_adjusted_close": "close",
    "execution_open": "open",
    "raw_volume": "volume",
}


def load_price_series(con, ticker: str, calendar: RegisteredCalendar) -> dict[str, np.ndarray]:  # noqa: ANN001
    rows = con.execute(
        'select "date", closeadj, closeunadj, close, open, volume from prices '
        "where ticker = ? order by \"date\"",
        [ticker],
    ).fetchall()
    seen: set[str] = set()
    by_date: dict[str, tuple[float, ...]] = {}
    for d, ca, cu, c, o, v in rows:
        ds = str(d)
        if ds in seen:
            raise refuse(
                "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE",
                f"duplicate price row for {ticker} {ds}",
            )
        seen.add(ds)
        by_date[ds] = tuple(float(x) for x in (ca, cu, c, o, v))
    n = len(calendar)
    out = {k: np.full(n, np.nan, dtype=np.float64) for k in
           ("closeadj", "closeunadj", "close", "open", "volume")}
    for i, ds in enumerate(calendar.sessions):
        if ds in by_date:
            ca, cu, c, o, v = by_date[ds]
            out["closeadj"][i], out["closeunadj"][i] = ca, cu
            out["close"][i], out["open"][i], out["volume"][i] = c, o, v
    return out


def assert_series_distinct(series: dict[str, np.ndarray]) -> None:
    """Prove the adjustment conventions are not interchangeable (detectable, not assumed)."""
    finite = np.isfinite(series["closeadj"]) & np.isfinite(series["closeunadj"])
    if not finite.any():
        raise refuse(
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
            "no overlapping finite closeadj/closeunadj to verify V3 distinctness",
        )
    if np.array_equal(series["closeadj"][finite], series["closeunadj"][finite]):
        raise refuse(
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
            "total-return-adjusted and raw close are identical — adjustment identity mismatch",
        )


def cross_series_substitution_guard(field_key: str, expected_column: str) -> None:
    """A named V3 field must map to its registered column; a substitution is refused."""
    if V3_FIELD_IDENTITY.get(field_key) != expected_column:
        raise refuse(
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
            f"V3 field {field_key} must bind {V3_FIELD_IDENTITY.get(field_key)}, not {expected_column}",
        )
