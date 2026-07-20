"""Historical feature/label dataset builder for MKT-PROJ-001 (FR-001).

Builds one row per session per horizon from Alpaca SIP-historical bars
(training provenance; live inference is IEX — recorded, and reconciled by the
30-day train/serve diagnostic). Minute data is fetched in MONTHLY chunks — a
naive multi-year intraday request is the bar_cache 10k-truncation footgun.

Pure building blocks + a chunked orchestrator; DB persistence lives in the
research script (scripts/research/mkt_proj_001/build_dataset.py), so nothing
here touches a request path. Sessions and half-day closes come from
pandas_market_calendars (a frozen §0 dependency — the labeler must use the
same authoritative calendar as production inference).

Exclusion policy (FR-001): a session that cannot produce a clean row is stored
with ``valid_for_training=False`` + ``exclusion_reason`` — never silently
dropped. Feature values may be None (e.g. zero-quality premarket gap); the
imputation rule is a training-pipeline concern frozen before §2 runs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd

from app.services.market_projection.features_preclose import preclose_features
from app.services.market_projection.features_preopen import preopen_features
from app.services.market_projection.labels import (
    label_for,
    preclose_realized_return,
    preopen_realized_return,
    threshold_pct_for,
)
from app.services.market_projection.schemas import (
    FEATURE_VERSION,
    FORECAST_OFFSET_MIN,
    GAP_SYMBOLS,
    LABEL_VERSION,
    MARKET_PROXY,
    PREOPEN_FORECAST_ET,
    SECTOR_BASKET,
    VOLUME_TOD_LOOKBACK,
    ProjectionType,
)

ET = "America/New_York"
ALL_SYMBOLS = tuple(dict.fromkeys((MARKET_PROXY, *GAP_SYMBOLS, *SECTOR_BASKET)))
# Free-plan SIP historical excludes the most recent 15 minutes; every request's
# end is clamped behind this margin or the whole request 403s (found live: the
# current-month chunk of the first full-history build).
SIP_RECENT_MARGIN_MIN = 16


def _clamp_sip_end(end_dt: datetime) -> datetime:
    from datetime import UTC as _UTC

    limit = datetime.now(_UTC) - timedelta(minutes=SIP_RECENT_MARGIN_MIN)
    if end_dt.tzinfo is None:
        return min(end_dt, limit.replace(tzinfo=None))
    return min(end_dt, limit)


# --- calendar -----------------------------------------------------------------

def nyse_sessions(start: date, end: date) -> pd.DataFrame:
    """Session table (index = session date) with tz-aware ET open/close — the
    authoritative half-day source (pandas_market_calendars, frozen §0)."""
    import pandas_market_calendars as mcal

    sched = mcal.get_calendar("NYSE").schedule(start_date=start, end_date=end)
    if sched.empty:  # a closed-day-only window has object-dtype columns (no .dt)
        return pd.DataFrame(columns=["open_et", "close_et"])
    out = pd.DataFrame(
        {
            "open_et": sched["market_open"].dt.tz_convert(ET),
            "close_et": sched["market_close"].dt.tz_convert(ET),
        }
    )
    out.index = [ts.date() for ts in sched.index]
    return out


# --- fetching (research path; sync client, called from the build script) ------

def _client():
    from alpaca.data.historical import StockHistoricalDataClient

    from app.brokers.alpaca.credentials import load_credentials

    creds = load_credentials()
    return StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)


def fetch_daily(
    client: Any, symbols: Iterable[str], start: date, end: date, *, feed: str = "sip"
) -> dict[str, pd.DataFrame]:
    """Daily bars per symbol, index = session date. feed="sip" (training; end
    clamped behind the recent-data window) or "iex" (live serving path)."""
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    end_dt = datetime.combine(end, time.max)
    data = client.get_stock_bars(
        StockBarsRequest(symbol_or_symbols=list(symbols), timeframe=TimeFrame.Day,
                         start=datetime.combine(start, time.min),
                         end=_clamp_sip_end(end_dt) if feed == "sip" else end_dt,
                         feed=DataFeed.SIP if feed == "sip" else DataFeed.IEX,
                         adjustment=Adjustment.SPLIT)
    ).data
    out: dict[str, pd.DataFrame] = {}
    for sym, bars in data.items():
        df = pd.DataFrame(
            {
                "open": [b.open for b in bars], "high": [b.high for b in bars],
                "low": [b.low for b in bars], "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
            },
            index=[b.timestamp.astimezone().date() if b.timestamp.tzinfo else b.timestamp.date()
                   for b in bars],
        )
        out[sym] = df[~df.index.duplicated(keep="last")].sort_index()
    return out


def fetch_minute_range(
    client: Any, symbols: Iterable[str], start: date, end: date, *, feed: str = "sip"
) -> dict[str, pd.DataFrame]:
    """Minute bars for [start, end] per symbol, index = tz-aware ET timestamps.
    Callers keep ranges ≤ ~1 month (the bar_cache 10k-truncation footgun guard);
    feed="iex" is the live serving path (no SIP clamp — IEX serves to now)."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    data = client.get_stock_bars(
        StockBarsRequest(symbol_or_symbols=list(symbols),
                         timeframe=TimeFrame(1, TimeFrameUnit.Minute),
                         start=datetime.combine(start, time.min),
                         end=_clamp_sip_end(end_dt) if feed == "sip" else end_dt,
                         feed=DataFeed.SIP if feed == "sip" else DataFeed.IEX)
    ).data
    out: dict[str, pd.DataFrame] = {}
    for sym, bars in data.items():
        idx = pd.DatetimeIndex([b.timestamp for b in bars]).tz_convert(ET)
        df = pd.DataFrame(
            {
                "open": [b.open for b in bars], "high": [b.high for b in bars],
                "low": [b.low for b in bars], "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
            },
            index=idx,
        )
        out[sym] = df[~df.index.duplicated(keep="last")].sort_index()
    return out


# --- per-day building blocks ---------------------------------------------------

def premarket_gaps(
    minute_by_symbol: Mapping[str, pd.DataFrame],
    daily_by_symbol: Mapping[str, pd.DataFrame],
    day: date,
    *,
    forecast_et: time,
) -> dict[str, tuple[float | None, int]]:
    """Symbol → (gap% vs prior close from premarket prints ≤ forecast time, quality
    = premarket minute-bar count). Quality 0 ⇒ (None, 0) — flagged, never faked."""
    out: dict[str, tuple[float | None, int]] = {}
    for sym in GAP_SYMBOLS:
        daily = daily_by_symbol.get(sym)
        minute = minute_by_symbol.get(sym)
        prior_closes = daily.loc[daily.index < day, "close"] if daily is not None else pd.Series([])
        if minute is None or minute.empty or not len(prior_closes):
            out[sym] = (None, 0)
            continue
        mask = [(ts.date() == day and ts.time() <= forecast_et and ts.time() >= time(4, 0))
                for ts in minute.index]
        pre = minute.loc[mask]
        if pre.empty:
            out[sym] = (None, 0)
            continue
        prev_close = float(prior_closes.iloc[-1])
        out[sym] = (float((pre["close"].iloc[-1] - prev_close) / prev_close * 100.0), len(pre))
    return out


def rth_slice(minute: pd.DataFrame, day: date, open_et: datetime, close_et: datetime) -> pd.DataFrame:
    if minute.empty:
        return minute
    return minute.loc[(minute.index >= open_et) & (minute.index <= close_et)]


def _row(
    day: date,
    ptype: ProjectionType,
    features: dict[str, float | None],
    realized: float | None,
    threshold: float | None,
) -> dict[str, Any]:
    valid = bool(features) and realized is not None and threshold is not None
    reason = None
    if not features:
        reason = "missing_features"
    elif threshold is None:
        reason = "insufficient_threshold_history"
    elif realized is None:
        reason = "label_not_matured" if ptype == ProjectionType.PRE_CLOSE_TOMORROW else "missing_daily_bar"
    label = (
        label_for(realized, threshold).value
        if realized is not None and threshold is not None and valid
        else None
    )
    return {
        "date": day,
        "projection_type": ptype.value,
        "market_proxy": MARKET_PROXY,
        "features_json": features or None,
        "shadow_features_json": None,  # SCAN/GAPPER shadow rows are a separate later pass (§8.4)
        "label": label,
        "realized_return": realized,
        "threshold": threshold,
        "valid_for_training": valid,
        "exclusion_reason": reason,
        "feature_version": FEATURE_VERSION,
        "label_version": LABEL_VERSION,
    }


def build_rows_for_sessions(
    sessions: pd.DataFrame,
    daily: Mapping[str, pd.DataFrame],
    minute: Mapping[str, pd.DataFrame],
    *,
    spy_cum_vol_at: Mapping[tuple[date, time], float],
    only_days: list[date] | None = None,
) -> list[dict[str, Any]]:
    """Both horizons' rows for sessions in ``sessions`` (index=date, the FULL
    calendar — prior-session lookups cross chunk boundaries), restricted to
    ``only_days`` when the caller processes month chunks.

    ``spy_cum_vol_at``: (session, cutoff-time) → SPY cumulative RTH volume through
    that wall-clock time — accumulated across the full history so each day's
    20-prior-session time-of-day-matched baseline is a cheap lookup."""
    spy_daily = daily[MARKET_PROXY]
    rows: list[dict[str, Any]] = []
    session_dates = list(sessions.index)
    for day in (only_days if only_days is not None else session_dates):
        open_et, close_et = sessions.loc[day, "open_et"], sessions.loc[day, "close_et"]
        cutoff = close_et - timedelta(minutes=FORECAST_OFFSET_MIN)
        thr = threshold_pct_for(spy_daily, day)

        # --- PRE_OPEN_TODAY (secondary): open-to-close target -------------------
        gaps = premarket_gaps(minute, daily, day,
                              forecast_et=time.fromisoformat(PREOPEN_FORECAST_ET))
        f_open = preopen_features(spy_daily, day=day, gaps=gaps)
        rows.append(_row(day, ProjectionType.PRE_OPEN_TODAY, f_open,
                         preopen_realized_return(spy_daily, day), thr))

        # --- PRE_CLOSE_TOMORROW (primary): close(t+1) vs close(t) ---------------
        rth = {sym: rth_slice(df, day, open_et, close_et) for sym, df in minute.items()}
        prior = [d for d in session_dates if d < day][-VOLUME_TOD_LOOKBACK:]
        maybe_vols = (spy_cum_vol_at.get((d, cutoff.time())) for d in prior)
        vols: list[float] = [v for v in maybe_vols if v is not None and v > 0]
        baseline = (sum(vols) / len(vols)) if len(vols) == VOLUME_TOD_LOOKBACK else None
        f_close = preclose_features(rth, spy_daily, day=day, cutoff=cutoff,
                                    spy_cum_vol_20d_tod_avg=baseline)
        rows.append(_row(day, ProjectionType.PRE_CLOSE_TOMORROW, f_close,
                         preclose_realized_return(spy_daily, day), thr))
    return rows


def spy_cum_volume_table(
    minute_spy: pd.DataFrame, sessions: pd.DataFrame
) -> dict[tuple[date, time], float]:
    """(session, cutoff-time) → cumulative RTH volume through that time, for the
    full-day AND half-day cutoffs — the lookup behind spy_volume_vs_20d_tod."""
    out: dict[tuple[date, time], float] = {}
    cutoffs = sorted({(c - timedelta(minutes=FORECAST_OFFSET_MIN)).time()
                      for c in sessions["close_et"]})
    for day in sessions.index:
        bars = rth_slice(minute_spy, day, sessions.loc[day, "open_et"], sessions.loc[day, "close_et"])
        if bars.empty:
            continue
        for cut in cutoffs:
            upto = bars.loc[[ts for ts in bars.index if ts.time() <= cut]]
            if len(upto):
                out[(day, cut)] = float(upto["volume"].sum())
    return out
