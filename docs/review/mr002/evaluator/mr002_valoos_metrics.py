"""MR-002 validation/OOS evaluator — metric primitives (Workstream B, Increment 1).

Pure, synthetic-only metric implementations of the v1.0.3 governing gate battery. Every function
takes CALLER-SUPPLIED synthetic arrays/records — NO portfolio construction, NO real data access, NO
sealed-data adapters. Frozen conventions (v1.0.3 §estimator/§bootstrap):
  * daily SIMPLE net returns on fixed $10M NAV; excess = net return (zero benchmark).
  * Sharpe = arithmetic mean / sample std (ddof=1) * sqrt(252); zero-vol (ptp==0) -> IntegrityStop.
  * annualized return = mean(daily) * 252 (simple convention, consistent with the arithmetic Sharpe).
  * moving-block (non-circular) bootstrap: block L=21, 2000 resamples, PCG64 seed 42, one-sided 95%.

DSR uses the loaded, ledger-bound N (=5); this module never hard-codes N — the caller passes it in.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

ANNUALIZATION = np.sqrt(252.0)
TRADING_DAYS = 252.0
BLOCK_SESSIONS = 21
RESAMPLES = 2000
SEED = 42
CONFIDENCE = 0.95
EULER_GAMMA = 0.5772156649015329


class IntegrityStop(Exception):
    """Zero-volatility, non-finite, or otherwise degenerate input (frozen INTEGRITY_STOP)."""


def _finite(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.size == 0 or not np.all(np.isfinite(a)):
        raise IntegrityStop("NONFINITE_OR_EMPTY")
    return a


# ── return aggregation + point metrics ──────────────────────────────────────────────────────────
def daily_net_return(per_name_pnl: np.ndarray, nav: float = 10_000_000.0) -> float:
    """Sum per-name net P&L for one session and divide by fixed NAV -> one daily net return."""
    p = _finite(per_name_pnl)
    if nav <= 0:
        raise IntegrityStop("NONPOSITIVE_NAV")
    return float(p.sum() / nav)


def annualized_return(daily_net: np.ndarray) -> float:
    return float(_finite(daily_net).mean() * TRADING_DAYS)


def annualized_sharpe(daily_net_excess: np.ndarray) -> float:
    r = _finite(daily_net_excess)
    if np.ptp(r) == 0.0:
        raise IntegrityStop("ZERO_VOLATILITY")
    return float(r.mean() / r.std(ddof=1) * ANNUALIZATION)


def max_drawdown(daily_net: np.ndarray) -> float:
    """Max peak-to-trough drawdown of the cumulative simple-return path; returned as a POSITIVE
    fraction (0.15 == 15%)."""
    r = _finite(daily_net)
    cum = np.cumsum(r)          # additive simple returns on fixed NAV
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    return float(dd.max())


def calmar(daily_net: np.ndarray) -> float:
    mdd = max_drawdown(daily_net)
    if mdd == 0.0:
        raise IntegrityStop("ZERO_DRAWDOWN")
    return float(annualized_return(daily_net) / mdd)


# ── moving-block bootstrap (frozen §bootstrap) ────────────────────────────────────────────────────
def _block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    idx: list[int] = []
    while len(idx) < n:
        s = int(rng.integers(0, n))
        idx.extend(range(s, min(s + block, n)))     # truncate at series end, no wraparound
    return np.array(idx[:n], dtype=np.int64)


def block_bootstrap_mean_lower_bound(daily_net: np.ndarray, *, block: int = BLOCK_SESSIONS,
                                     resamples: int = RESAMPLES, seed: int = SEED,
                                     confidence: float = CONFIDENCE) -> float:
    r = _finite(daily_net)
    rng = np.random.default_rng(seed)
    means = np.array([r[_block_indices(r.size, block, rng)].mean() for _ in range(resamples)])
    return float(np.percentile(means, (1.0 - confidence) * 100.0))


# ── fold / concentration / regime / breadth metrics ──────────────────────────────────────────────
def positive_fold_count(fold_daily_returns: list[np.ndarray]) -> int:
    """Number of folds whose net return SUM is > 0."""
    return int(sum(1 for f in fold_daily_returns if _finite(f).sum() > 0.0))


def annual_profile(annual_pnl: dict) -> dict:
    """v1.0.3: >=3 positive calendar years AND largest positive year <= 50% of the SUM of positive
    annual P&L. Returns {positive_years, largest_positive_fraction, gate_pass}."""
    vals = {y: float(v) for y, v in annual_pnl.items()}
    pos = [v for v in vals.values() if v > 0]
    n_pos = len(pos)
    total_pos = sum(pos)
    largest_frac = (max(pos) / total_pos) if total_pos > 0 else 1.0
    return {"positive_years": n_pos, "largest_positive_fraction": largest_frac,
            "gate_pass": bool(n_pos >= 3 and largest_frac <= 0.50)}


def trade_concentration(trade_pnl: np.ndarray, trade_stock_ids) -> dict:
    """v1.0.3: top-10 trades <= 20% of total POSITIVE trade P&L; single stock <= 10% of total
    positive P&L."""
    p = _finite(trade_pnl)
    ids = list(trade_stock_ids)
    pos_mask = p > 0
    total_pos = float(p[pos_mask].sum())
    if total_pos <= 0:
        return {"top10_fraction": 1.0, "single_stock_fraction": 1.0, "gate_pass": False}
    top10 = float(np.sort(p[pos_mask])[::-1][:10].sum()) / total_pos
    by_stock: dict = {}
    for pnl, sid in zip(p, ids, strict=True):
        if pnl > 0:
            by_stock[sid] = by_stock.get(sid, 0.0) + float(pnl)
    single = (max(by_stock.values()) / total_pos) if by_stock else 1.0
    return {"top10_fraction": top10, "single_stock_fraction": single,
            "gate_pass": bool(top10 <= 0.20 and single <= 0.10)}


def regime_gates(trend_regime_pnl: dict, vol_regime_sharpe: dict, *, min_sessions: dict | None = None) -> dict:
    """v1.0.3 regime GATES: positive net P&L in >=2 of 3 trend regimes; no trend regime > 60% of
    total LOSSES; no vol regime Sharpe < -0.50 (regimes with < 60 sessions exposure are n/a)."""
    min_sessions = min_sessions or {}
    tvals = {k: float(v) for k, v in trend_regime_pnl.items()}
    eligible = {k: v for k, v in tvals.items() if min_sessions.get(k, 999) >= 60}
    n_pos = sum(1 for v in eligible.values() if v > 0)
    losses = -sum(v for v in eligible.values() if v < 0)
    max_loss_frac = 0.0
    if losses > 0:
        max_loss_frac = max((-v / losses) for v in eligible.values() if v < 0)
    vol_ok = all(s >= -0.50 for k, s in vol_regime_sharpe.items() if min_sessions.get(k, 999) >= 60)
    return {"trend_positive_count": n_pos, "max_trend_loss_fraction": max_loss_frac,
            "vol_regime_ok": vol_ok,
            "gate_pass": bool(n_pos >= 2 and max_loss_frac <= 0.60 and vol_ok)}


def breadth(trade_records: list[dict]) -> dict:
    """v1.0.3: >=500 completed trades, >=100 distinct entry dates, >=100 long, >=100 short."""
    n = len(trade_records)
    dates = {t["entry_date"] for t in trade_records}
    longs = sum(1 for t in trade_records if t["side"] == "long")
    shorts = sum(1 for t in trade_records if t["side"] == "short")
    return {"trades": n, "distinct_entry_dates": len(dates), "long": longs, "short": shorts,
            "gate_pass": bool(n >= 500 and len(dates) >= 100 and longs >= 100 and shorts >= 100)}


def cost_stress_ingest(stressed_daily_net: np.ndarray) -> dict:
    """Ingest a caller-produced 20 bps/side + 300 bps/yr-borrow stressed return series; gate = still
    net-profitable (cumulative > 0)."""
    r = _finite(stressed_daily_net)
    return {"stressed_total_return": float(r.sum()), "gate_pass": bool(r.sum() > 0.0)}


def capacity_ingest(net_edge_under_cap: float) -> dict:
    """Ingest a caller-produced capacity result (net edge at $10M under the 2% ADV cap); gate =
    positive."""
    v = float(net_edge_under_cap)
    return {"net_edge_under_cap": v, "gate_pass": bool(v > 0.0)}


# ── DSR (GATE) at the loaded, ledger-bound N ─────────────────────────────────────────────────────
def deflated_sharpe(daily_net: np.ndarray, *, trials_n: int, trial_sharpe_std: float,
                    benchmark_sharpe: float = 0.0) -> dict:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado). `trials_n` MUST be the loaded, ledger-bound
    value (N=5) — this function has NO default. Returns {dsr, expected_max_sharpe, gate_pass}.

    SR is the ANNUALIZED Sharpe converted back to per-observation for the DSR z-statistic; skew and
    kurtosis are of the daily net series. expected_max_sharpe (SR0) is the Bailey-LdP expected
    maximum of N trial Sharpes given the cross-trial Sharpe dispersion `trial_sharpe_std`
    (per-observation units)."""
    if not isinstance(trials_n, int) or trials_n < 1:
        raise IntegrityStop(f"INVALID_TRIALS_N:{trials_n}")
    r = _finite(daily_net)
    t = r.size
    if np.ptp(r) == 0.0:
        raise IntegrityStop("ZERO_VOLATILITY")
    sr = r.mean() / r.std(ddof=1)                       # per-observation Sharpe
    # sample skewness / kurtosis (Fisher, i.e. excess kurtosis + 3 for the DSR formula uses raw g2)
    d = (r - r.mean()) / r.std(ddof=0)
    skew = float((d ** 3).mean())
    kurt = float((d ** 4).mean())                        # non-excess (normal == 3)
    # Bailey-LdP expected max Sharpe over N independent trials:
    if trials_n == 1:
        sr0 = benchmark_sharpe
    else:
        z1 = norm.ppf(1.0 - 1.0 / trials_n)
        z2 = norm.ppf(1.0 - 1.0 / (trials_n * np.e))
        sr0 = benchmark_sharpe + trial_sharpe_std * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)
    denom = np.sqrt(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2)
    if denom <= 0 or not np.isfinite(denom):
        raise IntegrityStop("DSR_DENOM_NONPOSITIVE")
    dsr = float(norm.cdf((sr - sr0) * np.sqrt(t - 1) / denom))
    return {"dsr": dsr, "sr_per_obs": float(sr), "expected_max_sharpe": float(sr0),
            "trials_n": trials_n, "gate_pass": bool(dsr >= 0.95)}


# ── DIAGNOSTICS (reported, NEVER gate the verdict) ───────────────────────────────────────────────
def pbo_diagnostic(fold_returns_by_config: dict, *, n_splits: int = 4) -> dict:
    """PBO via a simplified CSCV over per-fold config performance. DIAGNOSTIC ONLY — its output can
    never change the verdict. Returns {pbo, label}. (Exact CSCV split enumeration is refined later;
    this qualifies the diagnostic plumbing on synthetic input.)"""
    configs = list(fold_returns_by_config)
    mat = np.array([[float(np.sum(fold_returns_by_config[c][f])) for c in configs]
                    for f in range(len(next(iter(fold_returns_by_config.values()))))])
    n_folds = mat.shape[0]
    from itertools import combinations
    logits = []
    for is_idx in combinations(range(n_folds), max(1, n_folds // 2)):
        oos_idx = [i for i in range(n_folds) if i not in is_idx]
        if not oos_idx:
            continue
        is_perf = mat[list(is_idx)].mean(axis=0)
        oos_perf = mat[oos_idx].mean(axis=0)
        best = int(np.argmax(is_perf))
        rank = (np.argsort(np.argsort(oos_perf))[best] + 1) / (len(configs) + 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(np.log(rank / (1 - rank)))
    pbo = float(np.mean([1.0 for lg in logits if lg <= 0]) if logits else 0.0)
    return {"pbo": pbo, "label": "DIAGNOSTIC (N=3 underpowered)", "classification": "DIAGNOSTIC"}


def annual_herfindahl_diagnostic(annual_pnl: dict) -> dict:
    pos = [float(v) for v in annual_pnl.values() if v > 0]
    tot = sum(pos)
    hhi = float(sum((v / tot) ** 2 for v in pos)) if tot > 0 else 1.0
    return {"annual_herfindahl": hhi, "classification": "DIAGNOSTIC"}


def positive_pnl_regime_concentration_diagnostic(regime_pnl: dict) -> dict:
    pos = {k: float(v) for k, v in regime_pnl.items() if v > 0}
    tot = sum(pos.values())
    top = (max(pos.values()) / tot) if tot > 0 else 1.0
    return {"top_regime_positive_fraction": top, "classification": "DIAGNOSTIC"}
