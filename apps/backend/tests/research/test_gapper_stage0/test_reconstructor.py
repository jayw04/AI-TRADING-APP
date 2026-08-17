"""Reconstructor: PIT discipline (strict date < asof), gap math, filters."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.research.gapper_stage0.reconstructor import (
    REASON_GAP_BELOW_MIN,
    REASON_NO_PREMARKET_BARS,
    REASON_NO_PRIOR_CLOSE,
    REASON_PM_VOLUME_BELOW_MIN,
    REASON_PRICE_BELOW_MIN,
    REASON_SECURITY_TYPE_EXCLUDED,
    EventFilters,
    PITViolationError,
    adv,
    premarket_slice,
    prior_close,
    reconstruct_event,
    reconstruct_field,
)

ASOF = date(2026, 8, 14)


def _bars(rows: list[tuple], day: str = "2026-08-14") -> pd.DataFrame:
    """rows = [(et_hh:mm, o, h, l, c, v), ...] with a UTC 't' column."""
    recs = []
    for hhmm, o, h, lo, c, v in rows:
        t = pd.Timestamp(f"{day} {hhmm}", tz="America/New_York").tz_convert("UTC")
        recs.append({"t": t, "o": o, "h": h, "l": lo, "c": c, "v": v})
    return pd.DataFrame(recs)


def _dailies(*rows: tuple[str, float, float]) -> list[dict]:
    return [{"date": d, "close": c, "volume": v} for d, c, v in rows]


# ---- PIT discipline ---------------------------------------------------------


def test_prior_close_raises_on_asof_dated_bar() -> None:
    with pytest.raises(PITViolationError, match="strictly"):
        prior_close(_dailies(("2026-08-14", 10.0, 1e6)), ASOF)


def test_prior_close_raises_on_future_bar() -> None:
    with pytest.raises(PITViolationError):
        prior_close(_dailies(("2026-08-13", 10.0, 1e6), ("2026-08-17", 11.0, 1e6)), ASOF)


def test_adv_raises_on_pit_violation() -> None:
    with pytest.raises(PITViolationError):
        adv(_dailies(("2026-08-14", 10.0, 1e6)), ASOF)


def test_reconstruct_event_propagates_pit_violation() -> None:
    pm = _bars([("08:30", 12, 12.5, 12, 12.4, 40_000)])
    with pytest.raises(PITViolationError):
        reconstruct_event("XYZ", ASOF, pm, _dailies(("2026-08-14", 10.0, 1e6)), EventFilters())


def test_strictly_prior_data_is_accepted() -> None:
    dailies = _dailies(("2026-08-12", 9.5, 1e6), ("2026-08-13", 10.0, 2e6))
    assert prior_close(dailies, ASOF) == 10.0
    assert adv(dailies, ASOF) == pytest.approx(1.5e6)


# ---- gap math + premarket slice --------------------------------------------


def test_premarket_slice_only_takes_pre_0930_bars_on_asof() -> None:
    bars = pd.concat(
        [
            _bars([("08:00", 11, 11, 11, 11, 100), ("09:29", 12, 12, 12, 12, 100)]),
            _bars([("09:30", 13, 13, 13, 13, 100), ("10:00", 14, 14, 14, 14, 100)]),
            _bars([("08:30", 9, 9, 9, 9, 100)], day="2026-08-13"),  # other day
        ]
    )
    pm = premarket_slice(bars, ASOF)
    assert len(pm) == 2
    assert float(pm.iloc[-1]["c"]) == 12.0


def test_gap_pct_vs_prior_close() -> None:
    pm = _bars([("08:30", 11.9, 12.1, 11.8, 12.0, 60_000)])
    r = reconstruct_event("XYZ", ASOF, pm, _dailies(("2026-08-13", 10.0, 1e6)), EventFilters())
    assert r["gap_pct"] == pytest.approx(20.0)
    assert r["prior_close"] == 10.0
    assert r["premarket_last"] == 12.0
    assert r["passes"] is True
    assert r["exclusion_reasons"] == []


# ---- filters → reason codes -------------------------------------------------


def test_no_premarket_bars_reason() -> None:
    r = reconstruct_event("XYZ", ASOF, None, _dailies(("2026-08-13", 10.0, 1e6)), EventFilters())
    assert r["passes"] is False
    assert REASON_NO_PREMARKET_BARS in r["exclusion_reasons"]


def test_no_prior_close_reason() -> None:
    pm = _bars([("08:30", 12, 12, 12, 12, 60_000)])
    r = reconstruct_event("XYZ", ASOF, pm, [], EventFilters())
    assert REASON_NO_PRIOR_CLOSE in r["exclusion_reasons"]
    assert r["gap_pct"] is None


def test_price_volume_gap_and_type_filters() -> None:
    filters = EventFilters(min_price=5.0, min_premarket_volume=50_000, min_gap_pct=10.0)
    # price below min
    pm = _bars([("08:30", 2, 2, 2, 2.0, 60_000)])
    r = reconstruct_event("LOW", ASOF, pm, _dailies(("2026-08-13", 1.0, 1e6)), filters)
    assert REASON_PRICE_BELOW_MIN in r["exclusion_reasons"]
    # volume below min
    pm = _bars([("08:30", 12, 12, 12, 12.0, 1_000)])
    r = reconstruct_event("THIN", ASOF, pm, _dailies(("2026-08-13", 10.0, 1e6)), filters)
    assert REASON_PM_VOLUME_BELOW_MIN in r["exclusion_reasons"]
    # gap below min
    pm = _bars([("08:30", 10.2, 10.2, 10.2, 10.2, 60_000)])
    r = reconstruct_event("FLAT", ASOF, pm, _dailies(("2026-08-13", 10.0, 1e6)), filters)
    assert REASON_GAP_BELOW_MIN in r["exclusion_reasons"]
    # security type excluded
    pm = _bars([("08:30", 12, 12, 12, 12.0, 60_000)])
    r = reconstruct_event(
        "WART", ASOF, pm, _dailies(("2026-08-13", 10.0, 1e6)), filters, security_type="WARRANT"
    )
    assert REASON_SECURITY_TYPE_EXCLUDED in r["exclusion_reasons"]


def test_reconstruct_field_sorts_by_gap_and_keeps_every_symbol() -> None:
    filters = EventFilters(min_premarket_volume=1)
    minute = {
        "AAA": _bars([("08:30", 12, 12, 12, 12.0, 5_000)]),  # +20%
        "BBB": _bars([("08:30", 15, 15, 15, 15.0, 5_000)]),  # +50%
        "CCC": None,  # no premarket bars — still present, reason-coded
    }
    dailies = {
        "AAA": _dailies(("2026-08-13", 10.0, 1e6)),
        "BBB": _dailies(("2026-08-13", 10.0, 1e6)),
        "CCC": _dailies(("2026-08-13", 10.0, 1e6)),
    }
    field = reconstruct_field(ASOF, minute, dailies, filters)
    assert [r["symbol"] for r in field] == ["BBB", "AAA", "CCC"]
    assert field[2]["passes"] is False
