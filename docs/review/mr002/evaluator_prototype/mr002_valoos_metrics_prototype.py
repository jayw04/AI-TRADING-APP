"""MR-002 validation/OOS metric primitives — SYNTHETIC-QUALIFICATION PROTOTYPE.

CLASSIFICATION: review prototype of the frozen §7 (Sharpe estimator) and §8 (date-clustered block
bootstrap) specification in the v0.2 validation/OOS plan. It is NOT the qualified evaluator, NOT
registered execution code, and it NEVER reads development, validation, or OOS data — it operates
only on caller-supplied return vectors (synthetic fixtures in the companion test). Its purpose is
to prove the frozen estimator/bootstrap spec is precise, deterministic (seed 42), and reproducible
by an independent implementation from the same return vector alone.
"""

from __future__ import annotations

import numpy as np

ANNUALIZATION = np.sqrt(252.0)
BLOCK_SESSIONS = 21
RESAMPLES = 2000
SEED = 42
CONFIDENCE = 0.95


class IntegrityStop(Exception):
    """Raised for zero-volatility or non-finite samples (frozen §7 INTEGRITY_STOP)."""


def annualized_sharpe(daily_net_excess: np.ndarray) -> float:
    """§7: arithmetic mean / sample std (ddof=1), annualized by sqrt(252). float64, no NW adj."""
    r = np.asarray(daily_net_excess, dtype=np.float64)
    if r.size == 0 or not np.all(np.isfinite(r)):
        raise IntegrityStop("NONFINITE_OR_EMPTY_RETURN")
    # Zero volatility is detected EXACTLY by peak-to-peak == 0 (all values identical). Relying on
    # std(ddof=1) == 0 would miss a constant series whose std is ~1e-19 from mean rounding and then
    # divide by it, producing a spurious enormous Sharpe.
    if np.ptp(r) == 0.0:
        raise IntegrityStop("ZERO_VOLATILITY")
    sd = r.std(ddof=1)
    return float(r.mean() / sd * ANNUALIZATION)


def _block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Non-overlapping calendar blocks; incomplete final block kept short (no wraparound)."""
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=n_blocks)  # block start positions
    idx = []
    for s in starts:
        idx.extend(range(s, min(s + block, n)))
        if len(idx) >= n:
            break
    return np.array(idx[:n], dtype=np.int64)


def block_bootstrap_mean_ci_lower(daily_net: np.ndarray, *, block: int = BLOCK_SESSIONS,
                                  resamples: int = RESAMPLES, seed: int = SEED,
                                  confidence: float = CONFIDENCE) -> float:
    """§8: date-clustered block bootstrap of the daily mean return; one-sided lower bound at
    `confidence` via the percentile method. Deterministic given (vector, block, resamples, seed)."""
    r = np.asarray(daily_net, dtype=np.float64)
    if r.size == 0 or not np.all(np.isfinite(r)):
        raise IntegrityStop("NONFINITE_OR_EMPTY_RETURN")
    rng = np.random.default_rng(seed)
    means = np.empty(resamples, dtype=np.float64)
    for i in range(resamples):
        means[i] = r[_block_indices(r.size, block, rng)].mean()
    return float(np.percentile(means, (1.0 - confidence) * 100.0))


def sharpe_diff_noninferiority_lower(oos: np.ndarray, valid: np.ndarray, *, block: int = BLOCK_SESSIONS,
                                     resamples: int = RESAMPLES, seed: int = SEED,
                                     confidence: float = CONFIDENCE) -> float:
    """§9 (only if D-NI adopted): jointly resampled lower bound of (Sharpe_OOS - Sharpe_VALIDATION).
    Resamples both windows under one RNG stream; returns the one-sided lower bound of the diff."""
    a = np.asarray(oos, dtype=np.float64)
    b = np.asarray(valid, dtype=np.float64)
    rng = np.random.default_rng(seed)
    diffs = np.empty(resamples, dtype=np.float64)
    for i in range(resamples):
        sa = a[_block_indices(a.size, block, rng)]
        sb = b[_block_indices(b.size, block, rng)]
        diffs[i] = (sa.mean() / sa.std(ddof=1) - sb.mean() / sb.std(ddof=1)) * ANNUALIZATION
    return float(np.percentile(diffs, (1.0 - confidence) * 100.0))
