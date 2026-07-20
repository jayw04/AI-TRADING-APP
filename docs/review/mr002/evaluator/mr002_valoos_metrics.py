"""MR-002 validation/OOS evaluator — metric primitives (Increment 1 v1.1).

Pure, synthetic-only. Return/Calmar/drawdown follow the owner's 2026-07-20 convention ruling:
COMPOUNDED wealth path + GEOMETRIC annualization. Arithmetic mean x 252 is DESCRIPTIVE only.

Frozen conventions:
  * wealth_0 = 1; wealth_t = wealth_(t-1) * (1 + r_t)   (r_t = daily simple net return)
  * net annualized return gate  = (prod(1+r_t))^(252/n) - 1
  * MaxDD  = max_t (1 - W_t / max_{s<=t} W_s), a NON-NEGATIVE fraction, off the compounded path
  * combined MaxDD: concatenate validation then OOS chronologically into ONE continuous path (no
    reset of wealth or running peak at the seam)
  * OOS-only MaxDD: separate path starting at wealth 1.0 on the first eligible OOS return
  * Calmar = geometric annualized return / MaxDD (same sealed-OOS compounded series)
  * Sharpe = arithmetic mean / sample std (ddof=1) x sqrt(252)  (unchanged estimator)
  * moving-block (non-circular) bootstrap: block L=21, 2000 resamples, PCG64 seed 42, one-sided 95%
  * DSR (Bailey/Lopez-de-Prado): observed per-obs Sharpe uses ddof=1; skew/raw-kurtosis use the
    population (n) moment estimators; expected-max-Sharpe via the Euler-Mascheroni two-quantile form.

INTEGRITY_STOP codes: ZERO_VOLATILITY, NONFINITE_OR_EMPTY, NONPOSITIVE_WEALTH, NONFINITE_WEALTH,
ZERO_DRAWDOWN_NONPOSITIVE_RETURN, NONPOSITIVE_NAV, INVALID_TRIALS_N, DSR_DENOM_NONPOSITIVE,
BOOTSTRAP_PARAM.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

ANNUALIZATION = float(np.sqrt(252.0))
TRADING_DAYS = 252.0
BLOCK_SESSIONS = 21
RESAMPLES = 2000
SEED = 42
CONFIDENCE = 0.95
EULER_GAMMA = 0.5772156649015329
DSR_MIN_SAMPLE = 20


class IntegrityStop(Exception):
    """Degenerate / out-of-domain input (frozen INTEGRITY_STOP with a specific code)."""


def _finite(a) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.size == 0 or not np.all(np.isfinite(a)):
        raise IntegrityStop("NONFINITE_OR_EMPTY")
    return a


# ── compounded wealth path (the governing convention) ─────────────────────────────────────────────
def compounded_wealth(daily_net) -> np.ndarray:
    """W_t after each session, starting from an implicit W_0 = 1.0. Any r <= -1 => NONPOSITIVE_WEALTH;
    any non-finite wealth => NONFINITE_WEALTH."""
    r = _finite(daily_net)
    if np.any(r <= -1.0):
        raise IntegrityStop("NONPOSITIVE_WEALTH")
    w = np.cumprod(1.0 + r)
    if not np.all(np.isfinite(w)) or np.any(w <= 0.0):
        raise IntegrityStop("NONFINITE_WEALTH")
    return w


def geometric_annualized_return(daily_net) -> float:
    """(prod(1+r))^(252/n) - 1 — the governing >= 3% net annualized-return value."""
    r = _finite(daily_net)
    w = compounded_wealth(r)
    n = r.size
    return float(w[-1] ** (TRADING_DAYS / n) - 1.0)


def arithmetic_annualized_mean(daily_net) -> float:
    """mean(daily) x 252 — DESCRIPTIVE ONLY; NOT the return gate (owner ruling 2026-07-20)."""
    return float(_finite(daily_net).mean() * TRADING_DAYS)


def compounded_max_drawdown(daily_net) -> float:
    """MaxDD off the compounded wealth index; non-negative fraction (0.15 == 15%)."""
    w = compounded_wealth(daily_net)
    peak = np.maximum.accumulate(w)
    dd = 1.0 - w / peak
    return float(dd.max())


def combined_max_drawdown(validation_daily, oos_daily) -> float:
    """One continuous compounded path over validation THEN OOS (chronological); no seam reset."""
    v = _finite(validation_daily)
    o = _finite(oos_daily)
    return compounded_max_drawdown(np.concatenate([v, o]))


def annualized_sharpe(daily_net_excess) -> float:
    r = _finite(daily_net_excess)
    if np.ptp(r) == 0.0:
        raise IntegrityStop("ZERO_VOLATILITY")
    return float(r.mean() / r.std(ddof=1) * ANNUALIZATION)


def calmar(daily_net) -> dict:
    """Calmar = geometric annualized return / compounded MaxDD, same series. Special cases per the
    owner ruling; POSITIVE_INFINITY is a finite-status object, never an IEEE Infinity."""
    r = _finite(daily_net)
    rann = geometric_annualized_return(r)
    mdd = compounded_max_drawdown(r)
    if mdd == 0.0:
        if rann > 0.0:
            return {"value": None, "comparison_value": "POSITIVE_INFINITY",
                    "annualized_return": rann, "max_drawdown": 0.0, "gate_pass": True}
        raise IntegrityStop("ZERO_DRAWDOWN_NONPOSITIVE_RETURN")
    val = rann / mdd
    return {"value": float(val), "comparison_value": None, "annualized_return": rann,
            "max_drawdown": mdd, "gate_pass": bool(val >= 0.75)}


# ── moving-block bootstrap (frozen §bootstrap) ────────────────────────────────────────────────────
def _block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    idx: list[int] = []
    while len(idx) < n:
        s = int(rng.integers(0, n))                  # uniform start in [0, n-1]
        idx.extend(range(s, min(s + block, n)))      # up to L, truncate at series end, no wraparound
    return np.array(idx[:n], dtype=np.int64)


def block_bootstrap_mean_lower_bound(daily_net, *, block: int = BLOCK_SESSIONS,
                                     resamples: int = RESAMPLES, seed: int = SEED,
                                     confidence: float = CONFIDENCE) -> float:
    r = _finite(daily_net)
    n = r.size
    if n < 2:
        raise IntegrityStop("BOOTSTRAP_PARAM:N<2")
    if not (1 <= block <= n):
        raise IntegrityStop(f"BOOTSTRAP_PARAM:BLOCK={block}")
    if resamples < RESAMPLES:
        raise IntegrityStop(f"BOOTSTRAP_PARAM:RESAMPLES<{RESAMPLES}")
    if not (0.0 < confidence < 1.0):
        raise IntegrityStop(f"BOOTSTRAP_PARAM:CONFIDENCE={confidence}")
    rng = np.random.default_rng(seed)
    means = np.array([r[_block_indices(n, block, rng)].mean() for _ in range(resamples)])
    return float(np.percentile(means, (1.0 - confidence) * 100.0))


# ── fold / concentration / regime / breadth metrics ──────────────────────────────────────────────
def positive_fold_count(fold_daily_returns: list) -> int:
    """Folds whose COMPOUNDED terminal wealth > 1 (net-positive over the fold)."""
    return int(sum(1 for f in fold_daily_returns if compounded_wealth(f)[-1] > 1.0))


def annual_profile(annual_pnl: dict) -> dict:
    vals = {y: float(v) for y, v in annual_pnl.items()}
    pos = [v for v in vals.values() if v > 0]
    total_pos = sum(pos)
    largest_frac = (max(pos) / total_pos) if total_pos > 0 else 1.0
    return {"positive_years": len(pos), "largest_positive_fraction": largest_frac,
            "gate_pass": bool(len(pos) >= 3 and largest_frac <= 0.50)}


def trade_concentration(trade_pnl, trade_stock_ids) -> dict:
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
    min_sessions = min_sessions or {}
    tvals = {k: float(v) for k, v in trend_regime_pnl.items()}
    eligible = {k: v for k, v in tvals.items() if min_sessions.get(k, 999) >= 60}
    n_pos = sum(1 for v in eligible.values() if v > 0)
    losses = -sum(v for v in eligible.values() if v < 0)
    max_loss_frac = max(((-v / losses) for v in eligible.values() if v < 0), default=0.0)
    vol_ok = all(s >= -0.50 for k, s in vol_regime_sharpe.items() if min_sessions.get(k, 999) >= 60)
    return {"trend_positive_count": n_pos, "max_trend_loss_fraction": max_loss_frac,
            "vol_regime_ok": vol_ok,
            "gate_pass": bool(n_pos >= 2 and max_loss_frac <= 0.60 and vol_ok)}


def breadth(trade_records: list) -> dict:
    n = len(trade_records)
    dates = {t["entry_date"] for t in trade_records}
    longs = sum(1 for t in trade_records if t["side"] == "long")
    shorts = sum(1 for t in trade_records if t["side"] == "short")
    return {"trades": n, "distinct_entry_dates": len(dates), "long": longs, "short": shorts,
            "gate_pass": bool(n >= 500 and len(dates) >= 100 and longs >= 100 and shorts >= 100)}


def cost_stress_ingest(stressed_daily_net) -> dict:
    """Ingest a caller-produced 20 bps/side + 300 bps/yr-borrow stressed series; gate = net-profitable
    (compounded terminal wealth > 1)."""
    w = compounded_wealth(stressed_daily_net)
    return {"stressed_terminal_wealth": float(w[-1]), "gate_pass": bool(w[-1] > 1.0)}


def capacity_ingest(net_edge_under_cap: float) -> dict:
    v = float(net_edge_under_cap)
    return {"net_edge_under_cap": v, "gate_pass": bool(v > 0.0)}


# ── DSR (GATE) — pinned moment estimators; N supplied by the loaded ledger ─────────────────────────
def expected_max_sharpe(trials_n: int, trial_sharpe_std: float, benchmark_sharpe: float = 0.0) -> float:
    """Bailey/LdP expected maximum of N i.i.d. trial Sharpes (per-observation units). SR0 for N=1 is
    the benchmark. `trial_sharpe_std` is the cross-trial Sharpe dispersion (see the DSR-dispersion
    governance note — its PRODUCTION derivation is an OPEN item; here it is a synthetic fixture arg)."""
    if not isinstance(trials_n, int) or isinstance(trials_n, bool) or trials_n < 1:
        raise IntegrityStop(f"INVALID_TRIALS_N:{trials_n}")
    if trials_n == 1:
        return float(benchmark_sharpe)
    z1 = norm.ppf(1.0 - 1.0 / trials_n)
    z2 = norm.ppf(1.0 - 1.0 / (trials_n * np.e))
    return float(benchmark_sharpe + trial_sharpe_std * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def _sample_moments(r: np.ndarray) -> tuple[float, float, float]:
    """observed per-obs Sharpe (ddof=1), sample skewness, raw (Pearson, normal=3) kurtosis — the
    higher moments use the population (n) normalization."""
    mean = r.mean()
    sd1 = r.std(ddof=1)
    sd0 = r.std(ddof=0)
    sr = mean / sd1
    z = (r - mean) / sd0
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean())
    return float(sr), skew, kurt


def deflated_sharpe(daily_net, *, trials_n: int, trial_sharpe_std: float,
                    benchmark_sharpe: float = 0.0) -> dict:
    """Deflated Sharpe Ratio. `trials_n` MUST be the loaded, ledger-bound value (no default)."""
    if not isinstance(trials_n, int) or isinstance(trials_n, bool) or trials_n < 1:
        raise IntegrityStop(f"INVALID_TRIALS_N:{trials_n}")
    r = _finite(daily_net)
    t = r.size
    if t < DSR_MIN_SAMPLE:
        raise IntegrityStop(f"DSR_SAMPLE_TOO_SHORT:{t}<{DSR_MIN_SAMPLE}")
    if np.ptp(r) == 0.0:
        raise IntegrityStop("ZERO_VOLATILITY")
    sr, skew, kurt = _sample_moments(r)
    sr0 = expected_max_sharpe(trials_n, trial_sharpe_std, benchmark_sharpe)
    denom_sq = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    if not np.isfinite(denom_sq) or denom_sq <= 0.0:     # guard BEFORE sqrt (no RuntimeWarning)
        raise IntegrityStop("DSR_DENOM_NONPOSITIVE")
    denom = np.sqrt(denom_sq)
    dsr = float(norm.cdf((sr - sr0) * np.sqrt(t - 1) / denom))
    return {"dsr": dsr, "sr_per_obs": sr, "skew": skew, "kurtosis": kurt,
            "expected_max_sharpe": sr0, "trials_n": trials_n,
            "trial_sharpe_std": float(trial_sharpe_std), "trial_sharpe_std_provenance": "SYNTHETIC",
            "gate_pass": bool(dsr >= 0.95)}


# ── DIAGNOSTICS (reported, NEVER gate the verdict) ───────────────────────────────────────────────
def pbo_diagnostic(fold_returns_by_config: dict) -> dict:
    from itertools import combinations
    configs = list(fold_returns_by_config)
    n_folds = len(next(iter(fold_returns_by_config.values())))
    mat = np.array([[float(compounded_wealth(fold_returns_by_config[c][f])[-1] - 1.0)
                     for c in configs] for f in range(n_folds)])
    logits = []
    for is_idx in combinations(range(n_folds), max(1, n_folds // 2)):
        oos_idx = [i for i in range(n_folds) if i not in is_idx]
        if not oos_idx:
            continue
        best = int(np.argmax(mat[list(is_idx)].mean(axis=0)))
        oos_perf = mat[oos_idx].mean(axis=0)
        rank = (np.argsort(np.argsort(oos_perf))[best] + 1) / (len(configs) + 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(np.log(rank / (1 - rank)))
    pbo = float(np.mean([1.0 for lg in logits if lg <= 0]) if logits else 0.0)
    return {"pbo": pbo, "classification": "DIAGNOSTIC", "note": "N=3 underpowered"}


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


def severe_cost_stress_diagnostic(stressed_daily_net) -> dict:
    """30 bps/side + 1000 bps/yr borrow stressed series (reported, NEVER gated)."""
    w = compounded_wealth(stressed_daily_net)
    return {"severe_stressed_terminal_wealth": float(w[-1]), "classification": "DIAGNOSTIC"}
