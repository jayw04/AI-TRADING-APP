"""Stationary day-cluster bootstrap and the max-statistic test for the preliminary screen.

Configuration (proposed starting point, NOT independent statistical approval):
* resampling unit: consecutive TRADING DAYS, stationary bootstrap (geometric block lengths);
* all symbols and all candidates stay together inside each resampled day;
* statistic per candidate: total net R / total trades over the resample (days with zero trades
  contribute zero R and zero trades, so eligible zero-trade days stay in the daily sequence);
* mean block length, replications and seed are explicit arguments and are returned with the
  result (nothing is defaulted; R9).

Two different procedures are kept apart:
* ``mean_interval``: an ESTIMATION interval for one candidate's mean net R (percentile of the
  replicate means, not recentered);
* ``max_statistic_test``: a one-sided TEST of "no candidate has positive mean net R". The
  replicate statistics are RECENTERED under the null (each candidate's replicate mean minus its
  observed mean) and compared with the observed maximum over the candidate family.

Every public entry point requires a results capability. This module never selects a winner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import DataDefectError, ParamsUnsetError
from app.research.range002.screen.types import Trade

_CHUNK = 500


@dataclass(frozen=True)
class DayMatrix:
    """Per eligible day, per candidate: summed net R (base cost) and trade count."""

    days: tuple[date, ...]
    candidates: tuple[str, ...]
    net_r: np.ndarray  # shape (days, candidates)
    trades: np.ndarray  # shape (days, candidates), integer counts


@dataclass(frozen=True)
class BootstrapConfig:
    mean_block_days: float
    reps: int
    seed: int


@dataclass(frozen=True)
class MeanInterval:
    candidate: str
    observed_mean: float | None
    lower: float | None
    upper: float | None
    confidence: float
    zero_trade_replicates: int
    config: BootstrapConfig


@dataclass(frozen=True)
class MaxStatTest:
    observed_max: float | None
    observed_argmax: str | None
    p_value: float | None
    alpha: float
    rejects: bool
    zero_trade_replicates: int
    config: BootstrapConfig


def _check(config: BootstrapConfig) -> None:
    if config.mean_block_days < 1 or config.reps < 1:
        raise ParamsUnsetError("mean_block_days must be >= 1 and reps >= 1")


@requires_capability
def build_day_matrix(
    capability: object,
    trades_by_candidate: Mapping[str, Sequence[Trade]],
    eligible_days: Sequence[date],
) -> DayMatrix:
    days = tuple(sorted(set(eligible_days)))
    if len(days) != len(eligible_days):
        raise DataDefectError("duplicate day in eligible_days")
    index = {d: i for i, d in enumerate(days)}
    cands = tuple(trades_by_candidate)
    net = np.zeros((len(days), len(cands)))
    cnt = np.zeros((len(days), len(cands)), dtype=np.int64)
    for k, cand in enumerate(cands):
        for t in trades_by_candidate[cand]:
            if t.day not in index:
                raise DataDefectError(f"trade on {t.day} is not an eligible day")
            net[index[t.day], k] += t.net_r_base
            cnt[index[t.day], k] += 1
    return DayMatrix(days, cands, net, cnt)


def _resample_means(m: DayMatrix, config: BootstrapConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return (means[reps, K], zero_trade_mask[reps, K]); means are NaN where no trades."""
    d = len(m.days)
    k = len(m.candidates)
    rng = np.random.Generator(np.random.PCG64(config.seed))
    p = 1.0 / config.mean_block_days
    means = np.empty((config.reps, k))
    zero = np.empty((config.reps, k), dtype=bool)
    arange = np.arange(d)
    done = 0
    while done < config.reps:
        n = min(_CHUNK, config.reps - done)
        restart = rng.random((n, d)) < p
        restart[:, 0] = True
        starts = rng.integers(0, d, size=(n, d))
        block_start_t = np.maximum.accumulate(np.where(restart, arange, 0), axis=1)
        start_val = np.take_along_axis(starts, block_start_t, axis=1)
        idx = (start_val + (arange - block_start_t)) % d
        for j in range(k):
            tot_r = m.net_r[:, j][idx].sum(axis=1)
            tot_n = m.trades[:, j][idx].sum(axis=1)
            nz = tot_n > 0
            means[done : done + n, j] = np.where(nz, tot_r / np.where(nz, tot_n, 1), np.nan)
            zero[done : done + n, j] = ~nz
        done += n
    return means, zero


def _observed_means(m: DayMatrix) -> np.ndarray:
    tot_r = m.net_r.sum(axis=0)
    tot_n = m.trades.sum(axis=0)
    return np.where(tot_n > 0, tot_r / np.where(tot_n > 0, tot_n, 1), np.nan)


@requires_capability
def mean_interval(
    capability: object,
    matrix: DayMatrix,
    candidate: str,
    confidence: float,
    config: BootstrapConfig,
) -> MeanInterval:
    _check(config)
    if not 0.0 < confidence < 1.0:
        raise ParamsUnsetError("confidence must be in (0, 1)")
    k = matrix.candidates.index(candidate)
    obs = _observed_means(matrix)[k]
    means, zero = _resample_means(matrix, config)
    col = means[:, k]
    col = col[~np.isnan(col)]
    if len(col) == 0 or np.isnan(obs):
        return MeanInterval(candidate, None, None, None, confidence, int(zero[:, k].sum()), config)
    lo, hi = np.quantile(col, [(1 - confidence) / 2, 1 - (1 - confidence) / 2])
    return MeanInterval(
        candidate, float(obs), float(lo), float(hi), confidence, int(zero[:, k].sum()), config
    )


@dataclass(frozen=True)
class LowerBound:
    candidate: str
    observed_mean: float | None
    lower: float | None
    alpha: float
    zero_trade_replicates: int
    config: BootstrapConfig


@requires_capability
def one_sided_lower_bound(
    capability: object,
    matrix: DayMatrix,
    candidate: str,
    alpha: float,
    config: BootstrapConfig,
) -> LowerBound:
    """One-sided (1 - alpha) lower confidence bound for one candidate's mean net R.

    The ``alpha`` quantile of the day-cluster stationary-bootstrap replicate means (not
    recentred): for alpha = 0.05 this is the 95% one-sided lower bound. A bound above zero
    means the interval excludes zero on that side. It is an ESTIMATION bound for one named
    candidate; it is not corrected for the choice among K candidates (that is the
    max-statistic test's job) and a two-sided interval is a different object
    (``mean_interval``). Replicates with no trades are dropped and counted."""
    _check(config)
    if not 0.0 < alpha < 1.0:
        raise ParamsUnsetError("alpha must be in (0, 1)")
    k = matrix.candidates.index(candidate)
    obs = _observed_means(matrix)[k]
    means, zero = _resample_means(matrix, config)
    col = means[:, k]
    col = col[~np.isnan(col)]
    if len(col) == 0 or np.isnan(obs):
        return LowerBound(candidate, None, None, alpha, int(zero[:, k].sum()), config)
    return LowerBound(
        candidate, float(obs), float(np.quantile(col, alpha)), alpha, int(zero[:, k].sum()), config
    )


@requires_capability
def max_statistic_test(
    capability: object, matrix: DayMatrix, alpha: float, config: BootstrapConfig
) -> MaxStatTest:
    _check(config)
    if not 0.0 < alpha < 1.0:
        raise ParamsUnsetError("alpha must be in (0, 1)")
    obs = _observed_means(matrix)
    live = ~np.isnan(obs)
    if not live.any():
        return MaxStatTest(None, None, None, alpha, False, 0, config)
    means, zero = _resample_means(matrix, config)
    centered = means - obs  # recentered under the null: each candidate's null mean is its observed
    centered[:, ~live] = -np.inf
    centered = np.where(np.isnan(centered), -np.inf, centered)
    null_max = centered.max(axis=1)
    t_obs = float(np.nanmax(np.where(live, obs, -np.inf)))
    argmax = matrix.candidates[int(np.nanargmax(np.where(live, obs, -np.inf)))]
    p = (1 + int((null_max >= t_obs).sum())) / (config.reps + 1)
    return MaxStatTest(t_obs, argmax, p, alpha, p <= alpha, int(zero.any(axis=1).sum()), config)
