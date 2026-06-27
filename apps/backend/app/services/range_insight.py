"""Range Insight (P8 §5): a per-symbol statistical range panel.

Deterministic, descriptive summaries of a symbol's recent daily behavior — ATR,
typical open→high / open→low moves, support/resistance, an 80% confidence band
for today's high/low, today's range so far, and a range-bound vs trending
classification. **Descriptive, not predictive** (Direction Decision 2): the
payload always carries a disclaimer and the service never forecasts.

Never raises — insufficiency / degeneracy is reported via ``status``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.utils.time import EASTERN

WINDOW = 20  # ideal completed-daily-bar window
MIN_BARS = 10  # fewer completed bars than this → insufficient_data
_FETCH_DAYS = 120  # calendar lookback to gather ~WINDOW trading days

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"

DISCLAIMER = "Statistical descriptions of recent behavior, not forecasts."


@dataclass(frozen=True)
class MoveStats:
    mean: float
    median: float
    p80: float


@dataclass(frozen=True)
class Band:
    low: float
    high: float


@dataclass(frozen=True)
class RangeInsight:
    symbol: str
    status: str
    bars_used: int
    low_confidence: bool
    as_of: datetime | None
    anchor: float | None
    anchor_source: str | None  # "today_open" | "last_close"
    last_close: float | None
    atr20: float | None
    atr20_pct: float | None
    adv: float | None  # avg daily $ volume (mean close×volume over the window) — liquidity filter
    typical_move_up: MoveStats | None
    typical_move_down: MoveStats | None
    support: float | None
    resistance: float | None
    high_band: Band | None
    low_band: Band | None
    intraday_range: float | None
    classification: str | None  # "range_bound" | "trending" | "mixed"
    efficiency_ratio: float | None
    disclaimer: str = DISCLAIMER


def _insufficient(
    symbol: str, *, bars_used: int, as_of: datetime | None
) -> RangeInsight:
    return RangeInsight(
        symbol=symbol,
        status=STATUS_INSUFFICIENT,
        bars_used=bars_used,
        low_confidence=True,
        as_of=as_of,
        anchor=None,
        anchor_source=None,
        last_close=None,
        atr20=None,
        atr20_pct=None,
        adv=None,
        typical_move_up=None,
        typical_move_down=None,
        support=None,
        resistance=None,
        high_band=None,
        low_band=None,
        intraday_range=None,
        classification=None,
        efficiency_ratio=None,
    )


def _move_stats(series: pd.Series) -> MoveStats:
    return MoveStats(
        mean=float(series.mean()),
        median=float(series.quantile(0.5)),
        p80=float(series.quantile(0.8)),
    )


def _efficiency_ratio(closes: pd.Series) -> float:
    if len(closes) < 2:
        return 0.0
    net = abs(float(closes.iloc[-1]) - float(closes.iloc[0]))
    path = float(closes.diff().abs().sum())
    return net / path if path > 0 else 0.0


def _classify(er: float) -> str:
    if er < 0.3:
        return "range_bound"
    if er > 0.5:
        return "trending"
    return "mixed"


def _as_et_date(ts: Any) -> Any:
    """ET calendar date of a (tz-aware) bar timestamp."""
    dt = pd.Timestamp(ts)
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    return dt.tz_convert(EASTERN).date()


def range_insight_from_bars(
    symbol: str, bars: pd.DataFrame, now: datetime
) -> RangeInsight:
    """Pure core: compute Range Insight from a daily-bar frame (cols t,o,h,l,c,v)."""
    if bars is None or bars.empty:
        return _insufficient(symbol, bars_used=0, as_of=None)

    bars = bars.sort_values("t").reset_index(drop=True)
    as_of = bars["t"].iloc[-1]
    today_et = now.astimezone(EASTERN).date()

    # Separate today's (partial) bar — it must not pollute the completed-day
    # distributions; it feeds only the anchor + intraday range.
    has_today = _as_et_date(bars["t"].iloc[-1]) == today_et
    today_bar = bars.iloc[-1] if has_today else None
    hist = bars.iloc[:-1] if has_today else bars

    if len(hist) < MIN_BARS:
        return _insufficient(symbol, bars_used=len(hist), as_of=as_of)

    stats = hist.tail(WINDOW)
    bars_used = len(stats)

    last_close = float(hist["c"].iloc[-1])
    up = stats["h"] - stats["o"]  # open → high
    down = stats["o"] - stats["l"]  # open → low

    # ATR(20): mean of the last WINDOW valid true ranges.
    prev_c = hist["c"].shift(1)
    tr = pd.concat(
        [hist["h"] - hist["l"], (hist["h"] - prev_c).abs(), (hist["l"] - prev_c).abs()],
        axis=1,
    ).max(axis=1)
    atr20 = float(tr.dropna().tail(WINDOW).mean())

    if today_bar is not None:
        anchor = float(today_bar["o"])
        anchor_source = "today_open"
        intraday_range: float | None = float(today_bar["h"]) - float(today_bar["l"])
    else:
        anchor = last_close
        anchor_source = "last_close"
        intraday_range = None

    high_band = Band(
        low=anchor + float(up.quantile(0.1)),
        high=anchor + float(up.quantile(0.9)),
    )
    low_band = Band(
        low=anchor - float(down.quantile(0.9)),
        high=anchor - float(down.quantile(0.1)),
    )

    er = _efficiency_ratio(stats["c"])
    # Average daily dollar volume over the window — the liquidity hard filter (ADR 0028 §4).
    adv = float((stats["c"] * stats["v"]).mean())

    return RangeInsight(
        symbol=symbol,
        status=STATUS_OK,
        bars_used=bars_used,
        low_confidence=bars_used < WINDOW,
        as_of=as_of,
        anchor=anchor,
        anchor_source=anchor_source,
        last_close=last_close,
        atr20=atr20,
        atr20_pct=(atr20 / last_close if last_close else None),
        adv=adv,
        typical_move_up=_move_stats(up),
        typical_move_down=_move_stats(down),
        support=float(stats["l"].min()),
        resistance=float(stats["h"].max()),
        high_band=high_band,
        low_band=low_band,
        intraday_range=intraday_range,
        classification=_classify(er),
        efficiency_ratio=er,
    )


async def compute_range_insight(
    symbol: str, *, bar_cache: Any, now: datetime
) -> RangeInsight:
    """Fetch daily bars and compute Range Insight. Never raises."""
    symbol = symbol.upper()
    start = now - timedelta(days=_FETCH_DAYS)
    try:
        bars = await bar_cache.get_bars(symbol, "1Day", start, now)
    except Exception:
        return _insufficient(symbol, bars_used=0, as_of=None)
    return range_insight_from_bars(symbol, bars, now)


# --- Range-candidate ranking (P8 §5a) -----------------------------------------------
# "Which symbols are the best range-trading candidates today?" — rank a universe so a
# user can pick what to range-trade. Ranking is EVIDENCE-FIRST (design §8.4 Evidence
# Engineering): when a symbol has a realized range backtest, it ranks by its **win rate**
# (then Sharpe) — proven performance beats a structural guess. Names without a backtest
# fall back below, ordered by the structural **Range Score** (normalized range × how
# range-bound). Rationale, from this program's own runs: range trading is a marginal edge
# even on structurally "good" names — NVDA's 5-min fade returned Sharpe −1.12 at a 25%
# win rate while AAPL returned +0.46 at 62%, so realized win rate, not structure, must
# lead the ranking.

# Classification weight: a fade strategy thrives on range_bound, is hurt by trend.
_CLASS_WEIGHT = {"range_bound": 1.0, "mixed": 0.5, "trending": 0.1}

# Default candidate universe (liquid large-caps) when the caller passes none.
DEFAULT_CANDIDATE_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "GOOGL", "AMZN", "META", "NFLX",
    "INTC", "MU", "F", "KO", "DIS", "BAC", "XOM", "WMT", "SPY", "QQQ",
)


@dataclass(frozen=True)
class HardFilters:
    """The two-step screen's first stage (ADR 0028 review #4 / design §"hard filters"):
    a name must pass ALL of these to enter the *qualified universe* and receive a Range
    Score — preventing a stock with one strong metric but poor liquidity/range from ranking.

    Only the filters computable from daily bars are enforced (price, avg daily $ volume,
    ATR%). RVOL (>1.5) and average spread (<0.10%) from the owner's list are **deferred** —
    RVOL needs intraday volume (unavailable at the ~09:00 ET pre-open run) and spread needs
    quote data the bar cache does not carry; both join once that data is wired."""

    min_price: float = 10.0
    min_adv: float = 50_000_000.0   # $50M average daily dollar volume
    min_atr_pct: float = 0.03       # 3% ATR


DEFAULT_HARD_FILTERS = HardFilters()


def _qualify_reason(insight: RangeInsight, f: HardFilters) -> str | None:
    """None if the insight clears every (enforced) hard filter, else the first failure
    reason: insufficient_data | price_below_min | adv_below_min | atr_below_min."""
    if insight.status != STATUS_OK:
        return "insufficient_data"
    if insight.last_close is None or insight.last_close < f.min_price:
        return "price_below_min"
    if insight.adv is None or insight.adv < f.min_adv:
        return "adv_below_min"
    if insight.atr20_pct is None or insight.atr20_pct < f.min_atr_pct:
        return "atr_below_min"
    return None


@dataclass(frozen=True)
class CandidateEvidence:
    """Realized range-trading performance for a symbol, taken from its most recent range
    backtest. When present this *overrides* the structural prior in the ranking — the
    candidate ranks by win rate (then Sharpe) above any name without a backtest."""

    win_rate: float | None        # [0, 1]
    sharpe: float | None
    n_trades: int | None
    as_of: datetime | None = None
    label: str | None = None      # backtest label / provenance, for the UI tooltip


@dataclass(frozen=True)
class RangeCandidate:
    """One symbol's range-trading suitability (for the daily candidate ranker)."""

    symbol: str
    status: str
    atr20: float | None
    atr20_pct: float | None        # NORMALIZED range — the price-independent "size" factor
    intraday_range: float | None
    classification: str | None     # range_bound | trending | mixed
    last_close: float | None
    efficiency_ratio: float | None  # Kaufman ER (net/path): high = trending, low = choppy
    oscillation: float | None      # Range Efficiency = 1 − ER (high = oscillating = good)
    suitable: bool                 # range_bound + a usable atr20_pct
    score: float                   # composite Range Score (higher = better range candidate)
    rank: int                      # 1-based, after sorting
    # Realized backtest evidence (None when the symbol has no range backtest). Evidenced
    # names sort above structural-only ones, by win_rate then sharpe.
    win_rate: float | None = None
    sharpe: float | None = None
    n_trades: int | None = None
    backtested: bool = False
    # Two-step screen: avg daily $ volume + whether the name cleared the hard filters
    # (the qualified universe). ``qualified`` defaults True so candidates built without
    # filters (e.g. the descriptive view) are unaffected.
    adv: float | None = None
    qualified: bool = True
    qualify_reason: str | None = None  # why it was excluded from the qualified universe


def _oscillation(insight: RangeInsight) -> float:
    """The "shape" factor — how much a name *oscillates* vs trends, in [0, 1] (high = good
    for fading). The platform's ``efficiency_ratio`` is Kaufman ER (net move / total path):
    **high ER = directional/trending, low ER = choppy/range-bound**, so oscillation = 1 − ER.
    Falls back to the coarse ``classification`` weight when ER isn't available (keeps callers
    that only set the bucket working)."""
    if insight.efficiency_ratio is not None:
        return max(0.0, min(1.0, 1.0 - insight.efficiency_ratio))
    return _CLASS_WEIGHT.get(insight.classification or "", 0.5)


def _candidate_score(insight: RangeInsight) -> float:
    """Composite **Range Score** = normalized range (``atr20_pct``, the "size") × oscillation
    (the "shape", §8.1a of the design doc). Rewards a wide range that genuinely *oscillates*
    rather than trends — so a high-ATR% trender (NVDA) ranks below a moderate-ATR% oscillator,
    which ATR% alone could not capture. (Liquidity/spread factors are a future extension.)"""
    if insight.status != "ok" or insight.atr20_pct is None:
        return 0.0
    return insight.atr20_pct * _oscillation(insight)


def rank_candidates(
    insights: Iterable[RangeInsight],
    *,
    evidence: dict[str, CandidateEvidence] | None = None,
    hard_filters: HardFilters | None = None,
) -> list[RangeCandidate]:
    """Pure ranking over already-computed insights. Evidence-first (design §8.4): a symbol
    with a realized range backtest (``evidence`` carrying a non-null ``win_rate``) ranks by
    that win rate then Sharpe, ABOVE any name without one; the rest fall back to the
    structural Range Score. ``evidence`` is keyed by uppercased symbol.

    When ``hard_filters`` is given, each candidate is also tagged ``qualified`` (passed the
    price/ADV/ATR% screen) with a ``qualify_reason`` on failure; ranking order is unchanged
    (the qualified universe is applied at selection time). ``None`` → every ``ok`` candidate
    is qualified (descriptive view)."""
    ev_by_symbol = {k.upper(): v for k, v in (evidence or {}).items()}
    rows = []
    for ins in insights:
        score = _candidate_score(ins)
        suitable = (
            ins.status == "ok"
            and ins.classification == "range_bound"
            and ins.atr20_pct is not None
        )
        if hard_filters is None:
            qreason = None if ins.status == "ok" else "insufficient_data"
        else:
            qreason = _qualify_reason(ins, hard_filters)
        qualified = qreason is None
        ev = ev_by_symbol.get(ins.symbol.upper())
        has_ev = ev is not None and ev.win_rate is not None
        rows.append((score, ins, suitable, ev, has_ev, qualified, qreason))

    # Evidenced names first (group 0), ranked by win_rate desc then sharpe desc; the rest
    # (group 1) by structural score desc. Ties: atr20_pct desc, then symbol (deterministic).
    rows.sort(
        key=lambda t: (
            0 if t[4] else 1,
            -((t[3].win_rate if t[3] else None) or 0.0),
            -((t[3].sharpe if t[3] else None) or 0.0),
            -t[0],
            -(t[1].atr20_pct or 0.0),
            t[1].symbol,
        )
    )
    return [
        RangeCandidate(
            symbol=ins.symbol, status=ins.status, atr20=ins.atr20, atr20_pct=ins.atr20_pct,
            intraday_range=ins.intraday_range, classification=ins.classification,
            last_close=ins.last_close, efficiency_ratio=ins.efficiency_ratio,
            oscillation=round(_oscillation(ins), 4) if ins.status == "ok" else None,
            suitable=suitable, score=round(score, 6), rank=i + 1,
            win_rate=(ev.win_rate if ev else None),
            sharpe=(ev.sharpe if ev else None),
            n_trades=(ev.n_trades if ev else None),
            backtested=has_ev,
            adv=ins.adv, qualified=qualified, qualify_reason=qreason,
        )
        for i, (score, ins, suitable, ev, has_ev, qualified, qreason) in enumerate(rows)
    ]


async def rank_range_candidates(
    symbols: Iterable[str],
    *,
    bar_cache: Any,
    now: datetime,
    evidence: dict[str, CandidateEvidence] | None = None,
    hard_filters: HardFilters | None = None,
) -> list[RangeCandidate]:
    """Compute Range Insight for each symbol concurrently, then rank evidence-first
    (realized backtest win rate, then the structural Range Score), tagging each with whether
    it cleared ``hard_filters``. Fail-soft per symbol (``compute_range_insight`` never raises)."""
    deduped: dict[str, None] = {}
    for s in symbols:
        if s and s.strip():
            deduped.setdefault(s.strip().upper(), None)
    insights = await asyncio.gather(
        *(compute_range_insight(s, bar_cache=bar_cache, now=now) for s in deduped)
    )
    return rank_candidates(insights, evidence=evidence, hard_filters=hard_filters)


def eligible_range_candidates(
    candidates: Iterable[RangeCandidate],
    *,
    require_suitable: bool = True,
    require_qualified: bool = False,
    min_score: float = 0.0,
) -> list[RangeCandidate]:
    """The eligible candidates, in rank order: ``ok``; in the qualified universe when
    ``require_qualified`` (passed the price/ADV/ATR% hard filters); optionally range-bound +
    usable ATR% (``require_suitable``); and clearing the absolute Range-Score floor
    (``min_score``). The two-step screen (ADR 0028 review #4) gates on the **hard filters**;
    ``min_score`` is the optional *absolute* cutoff (0 = off, the research-phase default —
    Top-N is collected regardless of absolute score to gather calibration evidence)."""
    return [
        c
        for c in candidates
        if c.status == "ok"
        and (c.suitable or not require_suitable)
        and (c.qualified or not require_qualified)
        and c.score >= min_score
    ]


def top_range_symbols(
    candidates: Iterable[RangeCandidate],
    *,
    n: int = 5,
    require_suitable: bool = True,
    require_qualified: bool = False,
    min_score: float = 0.0,
) -> list[str]:
    """The day's Top-N range picks, in rank order — the symbol list the Candidate Engine
    hands to the Range Trader (design §"Top 3–5 candidates"). ``candidates`` must already be
    ranked (output of ``rank_candidates``). See ``eligible_range_candidates`` for the gates.
    A thin day yields FEWER than ``n`` picks rather than padding (no silent padding).
    ``n <= 0`` → none."""
    if n <= 0:
        return []
    picks = eligible_range_candidates(
        candidates, require_suitable=require_suitable,
        require_qualified=require_qualified, min_score=min_score,
    )
    return [c.symbol for c in picks[:n]]


async def select_top_range_symbols(
    symbols: Iterable[str],
    *,
    bar_cache: Any,
    now: datetime,
    n: int = 5,
    evidence: dict[str, CandidateEvidence] | None = None,
    require_suitable: bool = True,
    require_qualified: bool = False,
    min_score: float = 0.0,
    hard_filters: HardFilters | None = None,
) -> list[str]:
    """Rank a universe (evidence-first) and return today's Top-N symbols to range-trade.
    The daily auto-select entry point: ``rank_range_candidates`` → ``top_range_symbols``."""
    ranked = await rank_range_candidates(
        symbols, bar_cache=bar_cache, now=now, evidence=evidence, hard_filters=hard_filters
    )
    return top_range_symbols(
        ranked, n=n, require_suitable=require_suitable,
        require_qualified=require_qualified, min_score=min_score,
    )
