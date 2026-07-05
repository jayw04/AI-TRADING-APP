"""Matched-control benchmark engine (EAD; ADR 0037 §3.2) — a reusable event-study capability.

The registry rejected INSIDER-001's early form because its edge was **beta, not alpha**. This
engine is the gate against that: for each event it builds a **matched control basket** (same
sector, market-cap / ADV / momentum decile ±1, clean of the same event type) and tests the
event basket's forward return against the *matched controls'*, not the market. The cross-event
excess-return series is then bootstrapped (reusing the platform's seeded block bootstrap) for a
CI that must exclude zero.

Pure/deterministic and off the order path. The matching layer is data-free (operates on supplied
``CandidateFeatures``), so it unit-tests without the factor store; a thin adapter assembles those
features from the factor spine at run time. See ``…GOVCONTRACT001_Plan_v0.1.md`` §3.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.factor_data.evidence import ConfidenceResult, block_bootstrap_ci


@dataclass(frozen=True)
class CandidateFeatures:
    """One candidate security's matching features, as-of the event's ``available_time``."""

    ticker: str
    sector: str | None
    market_cap: float | None
    adv: float | None            # average dollar volume (liquidity)
    momentum: float | None       # trailing ~6-month total return

    def complete(self) -> bool:
        return None not in (self.sector, self.market_cap, self.adv, self.momentum)


@dataclass(frozen=True)
class MatchedControls:
    event_ticker: str
    controls: tuple[str, ...]
    reason: str | None           # None when sufficient; else why (thin/incomplete)

    @property
    def n(self) -> int:
        return len(self.controls)

    @property
    def sufficient(self) -> bool:
        return self.reason is None


def _deciles(values: dict[str, float]) -> dict[str, int]:
    """Assign each ticker a 0–9 decile by ascending value (ties broken by ticker for determinism)."""
    items = sorted(values.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(items)
    return {t: (min(9, (i * 10) // n) if n else 0) for i, (t, _) in enumerate(items)}


def select_matched_controls(
    event_ticker: str, candidates: Sequence[CandidateFeatures], *,
    n_target: int = 20, min_controls: int = 10, decile_band: int = 1,
    exclude: frozenset[str] = frozenset(),
) -> MatchedControls:
    """Pick up to ``n_target`` controls in the event's sector within ±``decile_band`` on each of
    market-cap / ADV / momentum deciles, closest first. ``exclude`` drops names that are not
    "clean" (e.g. carry the same event type in the lookback). Fewer than ``min_controls`` ⇒ the
    event is flagged ``thin_controls`` (excluded from the study, ADR 0037 §3.2)."""
    feats = {c.ticker: c for c in candidates if c.complete()}
    ev = feats.get(event_ticker)
    if ev is None or ev.sector is None:
        return MatchedControls(event_ticker, (), "event_features_incomplete")

    mcap_d = _deciles({t: c.market_cap for t, c in feats.items()})  # type: ignore[misc]
    adv_d = _deciles({t: c.adv for t, c in feats.items()})           # type: ignore[misc]
    mom_d = _deciles({t: c.momentum for t, c in feats.items()})      # type: ignore[misc]
    e_mcap, e_adv, e_mom = mcap_d[event_ticker], adv_d[event_ticker], mom_d[event_ticker]

    pool: list[tuple[int, str]] = []
    for t, c in feats.items():
        if t == event_ticker or t in exclude or c.sector != ev.sector:
            continue
        d_mcap, d_adv, d_mom = abs(mcap_d[t] - e_mcap), abs(adv_d[t] - e_adv), abs(mom_d[t] - e_mom)
        if max(d_mcap, d_adv, d_mom) > decile_band:
            continue
        pool.append((d_mcap + d_adv + d_mom, t))

    pool.sort(key=lambda x: (x[0], x[1]))
    controls = tuple(t for _, t in pool[:n_target])
    reason = None if len(controls) >= min_controls else "thin_controls"
    return MatchedControls(event_ticker, controls, reason)


# --- excess-return study ----------------------------------------------------------------------

PriceFn = Callable[[str, date, date], Sequence[tuple[date, float]]]
FeatureFn = Callable[[date], Sequence[CandidateFeatures]]
ExcludeFn = Callable[[date], frozenset[str]]


@dataclass(frozen=True)
class EventPoint:
    ticker: str
    entry_date: date


@dataclass(frozen=True)
class MatchedExcessResult:
    n_events: int
    n_benchmarked: int           # events with a sufficient matched basket + valid returns
    n_thin: int                  # events dropped for thin controls / missing prices
    mean_excess: float           # mean (event return − matched-control-basket return)
    ci_low: float
    ci_high: float
    p_value: float
    hold_days: int
    n_resamples: int

    @property
    def excludes_zero_positive(self) -> bool:
        return self.n_benchmarked >= 2 and self.ci_low > 0


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def forward_return(price_fn: PriceFn, ticker: str, entry: date, hold_days: int) -> float | None:
    """Simple return from the first trading day on/after ``entry`` to ``hold_days`` trading days
    later. ``None`` if the price series is too short or the entry price is non-positive."""
    series = price_fn(ticker, entry, entry + timedelta(days=hold_days * 2 + 15))
    if len(series) <= hold_days:
        return None
    p0, p1 = series[0][1], series[hold_days][1]
    if p0 is None or p0 <= 0 or p1 is None:
        return None
    return p1 / p0 - 1.0


def run_matched_excess_study(
    events: Sequence[EventPoint], *, price_fn: PriceFn, feature_fn: FeatureFn,
    exclude_fn: ExcludeFn | None = None, hold_days: int = 20, n_target: int = 20,
    min_controls: int = 10, decile_band: int = 1, seed: int = 17, n_resamples: int = 2000,
    block: int = 1,
) -> MatchedExcessResult:
    """Per event: build the matched control basket, compute (event return − equal-weight control
    return); bootstrap a CI on the cross-event excess-return series. ``block=1`` (i.i.d.) because
    the units are de-overlapped cross-event excesses, not an autocorrelated daily series."""
    excess: list[float] = []
    n_thin = 0
    for ev in events:
        candidates = feature_fn(ev.entry_date)
        exclude = exclude_fn(ev.entry_date) if exclude_fn else frozenset()
        mc = select_matched_controls(
            ev.ticker, candidates, n_target=n_target, min_controls=min_controls,
            decile_band=decile_band, exclude=exclude)
        if not mc.sufficient:
            n_thin += 1
            continue
        ev_ret = forward_return(price_fn, ev.ticker, ev.entry_date, hold_days)
        ctrl_raw = [forward_return(price_fn, c, ev.entry_date, hold_days) for c in mc.controls]
        ctrl_rets = [r for r in ctrl_raw if r is not None]   # narrows to list[float] for mypy
        if ev_ret is None or len(ctrl_rets) < min_controls:
            n_thin += 1
            continue
        excess.append(ev_ret - _mean(ctrl_rets))

    if len(excess) >= 2:
        ci = block_bootstrap_ci(excess, _mean, n_resamples=n_resamples, seed=seed, block=block)
    else:
        ci = ConfidenceResult(_mean(excess), 0.0, 0.0, 1.0, n_resamples, block)
    return MatchedExcessResult(
        n_events=len(events), n_benchmarked=len(excess), n_thin=n_thin,
        mean_excess=ci.point, ci_low=ci.ci_low, ci_high=ci.ci_high, p_value=ci.p_value,
        hold_days=hold_days, n_resamples=n_resamples,
    )
