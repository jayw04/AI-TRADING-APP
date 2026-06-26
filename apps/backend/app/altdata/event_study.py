"""Event-Study Engine (INSIDER-001 plan §4; owner S3 — equal billing with the data capability).

A **reusable, event-type-agnostic** de-overlapped event-study harness. Given a list of events
(anything with a ``ticker`` and an ``entry_date``) and a price accessor, it builds the standard
event-study book — enter equal-weight on the event, hold a fixed number of trading days, **skip an
event whose name is already held** (de-overlap), exit at the hold horizon — and scores it with the
platform's seeded bootstrap (`factor_data/evidence.py`): a paired Sharpe-diff CI vs a benchmark, a
recentered-null Sharpe p-value, drawdown, and per-event drift.

It is deliberately decoupled from insider specifics:

- prices arrive via an injected ``price_fn(ticker, start, end) -> [(date, close)]`` (the §4 wiring
  passes ``FactorDataStore.get_prices``; tests pass synthetic paths) — so the engine has **no**
  dependency on the corporate-event store or Sharadar, and is reusable for **earnings, dividends,
  buybacks, analyst upgrades, management changes**;
- the benchmark arrives the same way, so the paired test controls for shared market days.

**Construction (faithful to the source, plan §1).** Equal-weight among currently-active positions,
rebalanced daily — the de-overlapped analogue of "buy each new hit at equal-dollar notional, hold
~90 days, exit at the close." No stop (the source showed every stop is a return drag with no
portfolio-DD benefit); a catastrophe cap belongs to the live risk engine, not the study.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from app.factor_data import evidence

PriceFn = Callable[[str, date, date], "Sequence[tuple[date, float]]"]
BenchmarkFn = Callable[[date, date], "Sequence[tuple[date, float]]"]

HOLD_TRADING_DAYS = 90        # source §5.4: 90-day hold optimal (Sharpe 1.41, t 2.18)
_FETCH_CALENDAR_PAD = 200     # calendar days to span ~90 trading days + slack when fetching prices


class EventHit(Protocol):
    """The minimal event contract the engine consumes (``ConvictionHit`` satisfies it)."""

    @property
    def ticker(self) -> str: ...
    @property
    def entry_date(self) -> date: ...


@dataclass(frozen=True)
class EventDrift:
    """One taken position's realized path, entry → exit (at the hold horizon)."""

    ticker: str
    entry_date: date          # the actual first trading day on/after the event's entry anchor
    exit_date: date
    entry_price: float
    exit_price: float
    ret: float                # total return over the hold (exit/entry - 1)
    n_trading_days: int


@dataclass
class EventStudyResult:
    curve: list[tuple[date, float]] = field(default_factory=list)        # the book equity curve
    benchmark_curve: list[tuple[date, float]] = field(default_factory=list)
    drifts: list[EventDrift] = field(default_factory=list)
    n_hits: int = 0
    n_taken: int = 0
    n_skipped_overlap: int = 0      # already held when the event fired (de-overlap)
    n_no_data: int = 0              # no price path available (delisted before entry, etc.)
    # book metrics
    sharpe: float = 0.0
    total_return: float = 0.0
    cagr: float = 0.0
    max_drawdown: float = 0.0
    # event-level metrics
    mean_event_return: float = 0.0
    median_event_return: float = 0.0
    hit_rate: float = 0.0           # fraction of positions with a positive return
    avg_hold_days: float = 0.0
    # significance (None when no benchmark / too few observations)
    sharpe_p_value: float | None = None
    sharpe_diff_vs_benchmark: float | None = None
    sharpe_diff_ci_low: float | None = None
    sharpe_diff_ci_high: float | None = None

    @property
    def edge_excludes_zero(self) -> bool:
        """True iff the paired Sharpe-diff CI lies strictly above zero (a significant edge)."""
        lo = self.sharpe_diff_ci_low
        return lo is not None and lo == lo and lo > 0


def _first_on_or_after(path: Sequence[tuple[date, float]], anchor: date) -> int | None:
    """Index of the first price row dated on/after ``anchor`` (the PIT entry: you can only buy
    once the filing is knowable). ``path`` is ascending by date. None if none."""
    for i, (d, _) in enumerate(path):
        if d >= anchor:
            return i
    return None


def run_event_study(
    hits: Sequence[EventHit],
    price_fn: PriceFn,
    *,
    benchmark_fn: BenchmarkFn | None = None,
    hold_trading_days: int = HOLD_TRADING_DAYS,
    seed: int = 17,
    n_resamples: int = 2000,
) -> EventStudyResult:
    """Run the de-overlapped event study and score it. ``hits`` are consumed in ``entry_date``
    order; a hit whose ticker is still held (entry ≤ that position's exit) is skipped."""
    ordered = sorted(hits, key=lambda h: (h.entry_date, h.ticker))
    result = EventStudyResult(n_hits=len(ordered))

    # per-position daily returns keyed by date, plus actual entry/exit for de-overlap + activity
    positions: list[dict[date, float]] = []
    held_until: dict[str, date] = {}   # ticker -> exit date of its current open position

    for h in ordered:
        prior_exit = held_until.get(h.ticker)
        if prior_exit is not None and h.entry_date <= prior_exit:
            result.n_skipped_overlap += 1
            continue
        path = list(price_fn(h.ticker, h.entry_date, _add_pad(h.entry_date)))
        i0 = _first_on_or_after(path, h.entry_date)
        if i0 is None or i0 + 1 >= len(path):
            result.n_no_data += 1
            continue
        i1 = min(i0 + hold_trading_days, len(path) - 1)
        seg = path[i0:i1 + 1]
        entry_d, entry_p = seg[0]
        exit_d, exit_p = seg[-1]
        if entry_p <= 0:
            result.n_no_data += 1
            continue
        # per-day simple returns across the held segment (first held day accrues no return)
        day_ret: dict[date, float] = {}
        for (_, p0), (d1, p1) in zip(seg, seg[1:], strict=False):
            if p0 > 0:
                day_ret[d1] = p1 / p0 - 1.0
        positions.append(day_ret)
        held_until[h.ticker] = exit_d
        result.drifts.append(EventDrift(
            ticker=h.ticker, entry_date=entry_d, exit_date=exit_d,
            entry_price=entry_p, exit_price=exit_p, ret=exit_p / entry_p - 1.0,
            n_trading_days=len(seg) - 1,
        ))
        result.n_taken += 1

    if not positions:
        return result

    # master calendar = every date on which any position has a return
    calendar = sorted({d for pos in positions for d in pos})
    book_returns: list[float] = []
    active_days: list[date] = []
    for d in calendar:
        day_rets = [pos[d] for pos in positions if d in pos]
        if day_rets:
            book_returns.append(sum(day_rets) / len(day_rets))   # equal-weight among active
            active_days.append(d)

    result.curve = _compound(active_days, book_returns)
    _fill_book_metrics(result, book_returns)
    _fill_event_metrics(result)

    if benchmark_fn is not None and active_days:
        bench_returns = _benchmark_paired(benchmark_fn, active_days)
        result.benchmark_curve = _compound(active_days, bench_returns)
        _fill_significance(result, book_returns, bench_returns, seed=seed, n_resamples=n_resamples)
    else:
        _fill_significance(result, book_returns, None, seed=seed, n_resamples=n_resamples)

    return result


def _add_pad(anchor: date) -> date:
    return anchor + timedelta(days=_FETCH_CALENDAR_PAD)


def _compound(days: Sequence[date], returns: Sequence[float]) -> list[tuple[date, float]]:
    """Equity curve from daily returns, starting at 1.0 the day before the first return."""
    if not days:
        return []
    curve: list[tuple[date, float]] = [(days[0] - timedelta(days=1), 1.0)]
    equity = 1.0
    for d, r in zip(days, returns, strict=False):
        equity *= 1.0 + r
        curve.append((d, equity))
    return curve


def _benchmark_paired(benchmark_fn: BenchmarkFn, active_days: Sequence[date]) -> list[float]:
    """Benchmark daily returns aligned to the book's active days (0.0 on a day the benchmark has
    no quote) — so ``paired_sharpe_diff_ci`` compares like days for like days."""
    path = list(benchmark_fn(active_days[0], active_days[-1]))
    daily: dict[date, float] = {}
    prev: float | None = None
    for d, p in path:
        if prev is not None and prev > 0:
            daily[d] = p / prev - 1.0
        prev = p
    return [daily.get(d, 0.0) for d in active_days]


def _fill_book_metrics(result: EventStudyResult, book_returns: Sequence[float]) -> None:
    result.sharpe = evidence.sharpe(book_returns)
    result.total_return = evidence.total_return(result.curve)
    result.cagr = evidence.cagr(result.curve)
    result.max_drawdown = evidence.max_drawdown(result.curve)


def _fill_event_metrics(result: EventStudyResult) -> None:
    rets = sorted(d.ret for d in result.drifts)
    if not rets:
        return
    n = len(rets)
    result.mean_event_return = sum(rets) / n
    result.median_event_return = rets[n // 2] if n % 2 else (rets[n // 2 - 1] + rets[n // 2]) / 2
    result.hit_rate = sum(1 for r in rets if r > 0) / n
    result.avg_hold_days = sum(d.n_trading_days for d in result.drifts) / n


def _fill_significance(
    result: EventStudyResult,
    book_returns: Sequence[float],
    bench_returns: Sequence[float] | None,
    *,
    seed: int,
    n_resamples: int,
) -> None:
    boot = evidence.block_bootstrap_ci(book_returns, evidence.sharpe, n_resamples=n_resamples, seed=seed)
    result.sharpe_p_value = boot.p_value
    if bench_returns is not None:
        ci = evidence.paired_sharpe_diff_ci(book_returns, bench_returns, n_resamples=n_resamples, seed=seed)
        result.sharpe_diff_vs_benchmark = ci.delta
        result.sharpe_diff_ci_low = ci.ci_low
        result.sharpe_diff_ci_high = ci.ci_high
