"""SPY / Market benchmark metrics (P10 §3B-3).

The portfolio study's prior "benchmark" was the equal-weight-universe baseline (it feeds
``excess_sharpe`` in the frozen gate). §3B-3 adds a real **Market** benchmark — SPY — loaded
from a committed fixture (``scripts/build_spy_fixture.py``; ADR 0017 truststore). These
metrics are **reporting only** — the frozen gate is untouched — and answer "how did the book
do vs the market": excess return, beta, CAPM alpha, tracking error, information ratio,
correlation.

SPY (Alpaca/IEX) history starts ~2016, so metrics are computed over the book∩SPY date
**overlap** and the window is reported. Read-only, off the order path (ADR 0019). If the
fixture is absent the metrics are simply omitted — never fabricated.
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

_DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "spy_daily.parquet"
_MIN_OVERLAP_DAYS = 30  # below this the beta/alpha estimates are not worth reporting

Curve = list[tuple[date, float]]


def load_spy_curve(path: str | Path | None = None) -> Curve:
    """Load the committed SPY fixture as a sorted ``[(date, close)]`` curve. Empty list if
    the fixture is absent (so callers degrade to no-SPY rather than failing)."""
    p = Path(path) if path is not None else _DEFAULT_FIXTURE
    if not p.exists():
        return []
    df = pd.read_parquet(p)
    out: Curve = []
    for d, c in zip(df["date"], df["close"], strict=False):
        dd = d if isinstance(d, date) and not isinstance(d, pd.Timestamp) else pd.Timestamp(d).date()
        out.append((dd, float(c)))
    out.sort()
    return out


def _returns(vals: list[float]) -> list[float]:
    return [vals[i] / vals[i - 1] - 1.0 for i in range(1, len(vals))]


def benchmark_metrics(book_curve: Curve, bench_curve: Curve) -> dict[str, Any]:
    """SPY-relative metrics over the book∩benchmark date overlap. ``{}`` when either curve
    is empty or the overlap is too short to estimate beta/alpha."""
    if not book_curve or not bench_curve:
        return {}
    book = dict(book_curve)
    bench = dict(bench_curve)
    common = sorted(set(book) & set(bench))
    if len(common) < _MIN_OVERLAP_DAYS:
        return {}
    b = [book[d] for d in common]
    m = [bench[d] for d in common]
    br, mr = _returns(b), _returns(m)

    book_total = b[-1] / b[0] - 1.0 if b[0] > 0 else 0.0
    bench_total = m[-1] / m[0] - 1.0 if m[0] > 0 else 0.0
    mean_b, mean_m = statistics.fmean(br), statistics.fmean(mr)
    var_m = statistics.pvariance(mr) if len(mr) > 1 else 0.0
    cov = sum((x - mean_b) * (y - mean_m) for x, y in zip(br, mr, strict=False)) / len(br)
    beta = cov / var_m if var_m > 0 else 0.0
    alpha_daily = mean_b - beta * mean_m
    diff = [x - y for x, y in zip(br, mr, strict=False)]
    te = statistics.pstdev(diff) * math.sqrt(252.0) if len(diff) > 1 else 0.0
    ir = (statistics.fmean(diff) * 252.0) / te if te > 0 else 0.0
    sb, sm = statistics.pstdev(br), statistics.pstdev(mr)
    corr = cov / (sb * sm) if sb > 0 and sm > 0 else 0.0

    return {
        "spy_overlap_start": common[0].isoformat(),
        "spy_overlap_end": common[-1].isoformat(),
        "spy_overlap_days": len(common),
        "spy_total_return": bench_total,
        "spy_excess_return": book_total - bench_total,
        "spy_beta": beta,
        "spy_alpha_annual": alpha_daily * 252.0,
        "spy_tracking_error": te,
        "spy_information_ratio": ir,
        "spy_correlation": corr,
    }
