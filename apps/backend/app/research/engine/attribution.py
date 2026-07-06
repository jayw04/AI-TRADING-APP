"""Return / turnover / drawdown attribution (P10 §3B).

Decomposes a ``MomentumBacktestReport`` into per-name and per-sector contributions —
*who* drove the book's return, *who* drove its turnover, and *who* drove its worst
drawdown. The 3A evidence bundle showed *what* happened (curves, sector weights); §3B
attribution answers *why*.

Read-only over the store (recomputes each name's segment return from adjusted prices the
store already holds — ADR 0019, off the order path). Return attribution is first-order
(Brinson-style): contribution = Σ weight × name-segment-return, which sums to the book's
gross arithmetic return up to a **reported residual** (intra-segment compounding + the
turnover cost the per-name marks don't carry). The residual is surfaced, not hidden.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.factor_data.backtest import MomentumBacktestReport, _CachedPriceStore
from app.factor_data.store import FactorDataStore
from app.research.engine.orchestrator import ResearchArtifact

_TOP_N = 10  # how many contributors / detractors to surface per artifact


def _name_segment_return(
    store: FactorDataStore, ticker: str, start: date, end: date
) -> float | None:
    """Adjusted-close return for ``ticker`` over ``(start, end]`` — entry at the first
    close on/after ``start``, exit at the last close on/before ``end`` (delisting-frozen,
    mirroring the backtest's last-price-to-cash mark). ``None`` when history is too thin."""
    if end <= start:
        return None
    df = store.get_prices(ticker, start, end, adjusted=True)
    if df.empty or len(df) < 2:
        return None
    closes = [float(c) for c in df["close"] if c is not None and float(c) > 0]
    if len(closes) < 2:
        return None
    entry, exit_ = closes[0], closes[-1]
    return exit_ / entry - 1.0 if entry > 0 else None


def _rebalance_segments(report: MomentumBacktestReport) -> list[tuple[date, date, dict[str, float]]]:
    """(segment_start, segment_end, weights) per rebalance — the segment runs from a
    rebalance to the next one (or the end of the equity curve for the last)."""
    rebs = [h.rebalance_date for h in report.holdings]
    end = report.equity_curve[-1][0] if report.equity_curve else None
    segs: list[tuple[date, date, dict[str, float]]] = []
    for i, h in enumerate(report.holdings):
        seg_end = rebs[i + 1] if i + 1 < len(rebs) else end
        if seg_end is None or seg_end <= h.rebalance_date:
            continue
        segs.append((h.rebalance_date, seg_end, h.weights))
    return segs


def _by_sector(store: FactorDataStore, by_name: dict[str, float]) -> dict[str, float]:
    secs = store.get_sectors(list(by_name))
    out: dict[str, float] = {}
    for tk, v in by_name.items():
        sec = secs.get(tk) or "UNKNOWN"
        out[sec] = out.get(sec, 0.0) + v
    return out


def _fmt_contribs(items: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [{"ticker": t, "contribution": round(v, 8)} for t, v in items]


def _top_bottom(by_name: dict[str, float]) -> dict[str, list[dict[str, Any]]]:
    ranked = sorted(by_name.items(), key=lambda kv: kv[1])
    return {
        "top_contributors": _fmt_contribs(list(reversed(ranked[-_TOP_N:]))),
        "top_detractors": _fmt_contribs(ranked[:_TOP_N]),
    }


# ---- return attribution (the "alpha") -------------------------------------------


def return_attribution(report: MomentumBacktestReport, store: FactorDataStore) -> dict[str, Any]:
    """Per-name / per-sector contribution to the book's gross return.

    contribution(name) = Σ_segments weight × name-segment-return. ``residual`` =
    book gross arithmetic return − Σ contributions (the first-order + cost gap)."""
    cached: FactorDataStore = _CachedPriceStore(store)  # type: ignore[assignment]
    by_name: dict[str, float] = {}
    book_gross = 0.0
    eq = dict(report.equity_curve)
    for seg_start, seg_end, weights in _rebalance_segments(report):
        e0, e1 = eq.get(seg_start), eq.get(seg_end)
        if e0 and e1 and e0 > 0:
            book_gross += e1 / e0 - 1.0
        for tk, w in weights.items():
            r = _name_segment_return(cached, tk, seg_start, seg_end)
            if r is not None:
                by_name[tk] = by_name.get(tk, 0.0) + w * r
    total = sum(by_name.values())
    return {
        "by_name": by_name,
        "by_sector": _by_sector(store, by_name),
        "total_attributed": total,
        "book_gross_return": book_gross,
        "residual": book_gross - total,
        **_top_bottom(by_name),
    }


# ---- turnover attribution -------------------------------------------------------


def turnover_attribution(report: MomentumBacktestReport, store: FactorDataStore) -> dict[str, Any]:
    """Per-name / per-sector share of one-way turnover (Σ|Δweight| across rebalances)."""
    by_name: dict[str, float] = {}
    prev: dict[str, float] = {}
    for h in report.holdings:
        for tk in set(h.weights) | set(prev):
            dw = abs(h.weights.get(tk, 0.0) - prev.get(tk, 0.0))
            if dw > 0:
                by_name[tk] = by_name.get(tk, 0.0) + dw
        prev = h.weights
    total = sum(by_name.values())
    ranked = sorted(by_name.items(), key=lambda kv: -kv[1])
    return {
        "by_name": by_name,
        "by_sector": _by_sector(store, by_name),
        "total_one_way_turnover": total,
        "top_churners": [
            {"ticker": t, "turnover": round(v, 6), "share": round(v / total, 6) if total else 0.0}
            for t, v in ranked[:_TOP_N]
        ],
    }


# ---- drawdown attribution -------------------------------------------------------


def _max_dd_window(curve: list[tuple[date, float]]) -> tuple[date, date, float] | None:
    """(peak_date, trough_date, drawdown_fraction) for the deepest peak→trough decline."""
    if len(curve) < 2:
        return None
    peak_v = curve[0][1]
    peak_d = curve[0][0]
    best = None  # (dd, peak_d, trough_d)
    for d, v in curve:
        if v > peak_v:
            peak_v, peak_d = v, d
        dd = v / peak_v - 1.0 if peak_v > 0 else 0.0
        if best is None or dd < best[0]:
            best = (dd, peak_d, d)
    if best is None or best[0] >= 0:
        return None
    return best[1], best[2], best[0]


def drawdown_attribution(report: MomentumBacktestReport, store: FactorDataStore) -> dict[str, Any]:
    """Per-name / per-sector contribution over the deepest drawdown window (peak→trough).

    Sums weight × name-return over the part of each rebalance segment that overlaps the
    drawdown window — so the names that drove the worst loss are explicit."""
    win = _max_dd_window(report.equity_curve)
    if win is None:
        return {"peak_date": None, "trough_date": None, "drawdown": 0.0,
                "by_name": {}, "by_sector": {}, "top_detractors": []}
    peak_d, trough_d, dd = win
    cached: FactorDataStore = _CachedPriceStore(store)  # type: ignore[assignment]
    by_name: dict[str, float] = {}
    for seg_start, seg_end, weights in _rebalance_segments(report):
        lo, hi = max(seg_start, peak_d), min(seg_end, trough_d)
        if hi <= lo:
            continue
        for tk, w in weights.items():
            r = _name_segment_return(cached, tk, lo, hi)
            if r is not None:
                by_name[tk] = by_name.get(tk, 0.0) + w * r
    ranked = sorted(by_name.items(), key=lambda kv: kv[1])  # most negative first
    return {
        "peak_date": peak_d.isoformat(),
        "trough_date": trough_d.isoformat(),
        "drawdown": round(dd, 6),
        "by_name": by_name,
        "by_sector": _by_sector(store, by_name),
        "top_detractors": [{"ticker": t, "contribution": round(v, 8)} for t, v in ranked[:_TOP_N]],
    }


# ---- artifacts + flat summary ---------------------------------------------------


def build_attribution_artifacts(
    report: MomentumBacktestReport, store: FactorDataStore
) -> list[ResearchArtifact]:
    """The three §3B attribution artifacts, appended to the standard evidence bundle."""
    import json

    ret = return_attribution(report, store)
    trn = turnover_attribution(report, store)
    ddn = drawdown_attribution(report, store)
    return [
        ResearchArtifact("return_attribution", "return_attribution.json", json.dumps(ret)),
        ResearchArtifact("turnover_attribution", "turnover_attribution.json", json.dumps(trn)),
        ResearchArtifact("drawdown_attribution", "drawdown_attribution.json", json.dumps(ddn)),
    ]


def attribution_summary(
    report: MomentumBacktestReport, store: FactorDataStore
) -> dict[str, Any]:
    """Flat reporting keys for ``metrics_summary`` (never gated — attribution is
    explanatory). Names/sectors of the biggest return contributor/detractor, the
    drawdown's top detractor, and the return-attribution residual."""
    ret = return_attribution(report, store)
    ddn = drawdown_attribution(report, store)
    rc = ret["top_contributors"]
    rd = ret["top_detractors"]
    sectors = ret["by_sector"]
    top_sec = max(sectors.items(), key=lambda kv: kv[1])[0] if sectors else None
    bot_sec = min(sectors.items(), key=lambda kv: kv[1])[0] if sectors else None
    dd_det = ddn["top_detractors"]
    return {
        "attr_top_contributor": rc[0]["ticker"] if rc else None,
        "attr_top_detractor": rd[0]["ticker"] if rd else None,
        "attr_top_sector": top_sec,
        "attr_worst_sector": bot_sec,
        "attr_return_residual": round(ret["residual"], 6),
        "attr_dd_top_detractor": dd_det[0]["ticker"] if dd_det else None,
    }
