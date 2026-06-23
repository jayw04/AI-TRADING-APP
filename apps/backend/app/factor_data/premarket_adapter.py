"""SCAN-001 premarket-data gate — increment (A): the premarket → engine feature adapter.

Maps a **real** pre-market gapper row (the read-only #221 scanner output) + the symbol's
historical store features into the frozen Candidate Engine's feature-panel row, so the engine
can run on real 09:25 premarket data instead of the daily-bar approximations used throughout
the v0.1–v0.5 research. See the gate plan ``TradingWorkbench_SCAN001_PremarketDataGate_Plan``.

Boundary: this module is **PURE** — no I/O, no network, no store handle, no LLM. Callers supply
the gapper rows (from ``app.services.premarket_gappers.read_latest_gappers``, increment B) and the
per-symbol store features. The resulting panel feeds ``candidate_engine.select_candidates``; the
candidate set is **evidence, not a signal** (SCAN-001 §0a).

Honest feature provenance (gate plan §0b) — what is real vs. proxied:
  * ``gap_pct``    — REAL premarket gap, taken directly from the gapper row (already a percent).
  * ``rvol``       — premarket cumulative volume ÷ the symbol's trailing AVG DAILY volume. This is a
                     premarket-vs-daily **proxy**: a *true* premarket RVOL needs a premarket-volume
                     baseline the feed doesn't yet provide. Flagged so the gate's reading stays honest;
                     the magnitude is not comparable to the daily-bar RVOL used in v0.2–v0.5.
  * ``atr_pct``    — from the historical store (a symbol join); real, not premarket.
  * ``dollar_vol`` — prev-day $-volume from the store (the $20M liquidity gate input).
  * ``price``      — the premarket price from the gapper row (the $10 floor input).
A gapper with no store coverage (no ATR) yields ``None`` — it cannot be ATR-gated, so it is dropped
(and the count of dropped names is the caller's to log: the §0b "eligibility overlap" finding).
"""

from __future__ import annotations

from typing import Any

from app.factor_data import candidate_engine as ce

# Store-feature keys the adapter needs per symbol (the historical-data join).
STORE_FEATURE_KEYS = ("atr_pct", "avg_volume", "prev_dollar_vol")

ATR_N = 14
RVOL_LOOKBACK = 20


def _f(value: Any) -> float:
    """Best-effort float; non-numeric / None → 0.0 (fail-soft, never raises into a scan)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def features_from_bars(bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute the per-symbol store features from prior daily bars (PURE — the testable core
    of the historical join used by the live scan, increment B).

    ``bars`` are the symbol's daily bars **strictly before** the scan day, oldest → newest, each
    with ``high``/``low``/``close``/``volume`` (point-in-time: a premarket scan knows only prior
    closes). Needs ≥ ``ATR_N + 1`` bars; returns ``None`` otherwise (the symbol is then dropped,
    matching ``premarket_feature_row``'s no-ATR rule). Mirrors the v0.2 harness's ``_feature_row``
    so premarket features are computed identically to the validated research."""
    if len(bars) < ATR_N + 1:
        return None
    highs = [_f(b.get("high")) for b in bars]
    lows = [_f(b.get("low")) for b in bars]
    closes = [_f(b.get("close")) for b in bars]
    prev_close = closes[-1]
    if prev_close <= 0:
        return None
    avg_volume = sum(_f(b.get("volume")) for b in bars[-RVOL_LOOKBACK:]) / min(
        RVOL_LOOKBACK, len(bars)
    )
    return {
        "atr_pct": ce.atr_pct(highs, lows, closes, n=ATR_N),
        "avg_volume": avg_volume,
        "prev_dollar_vol": prev_close * _f(bars[-1].get("volume")),
    }


def premarket_feature_row(
    gapper: dict[str, Any], store_feat: dict[str, Any] | None
) -> dict[str, Any] | None:
    """One gapper + its store features → an engine feature-panel row, or ``None`` if uncoverable.

    ``gapper`` keys (from the #221 reader): ``symbol``, ``price``, ``gap_pct``, ``premarket_volume``.
    ``store_feat`` keys (``STORE_FEATURE_KEYS`` + optional ``earnings_today``): ``atr_pct``,
    ``avg_volume``, ``prev_dollar_vol``. Returns ``None`` when the symbol is missing, has no store
    coverage, or lacks a usable price/ATR (it then cannot pass the engine's gates anyway)."""
    symbol = str(gapper.get("symbol") or "").strip()
    if not symbol or store_feat is None:
        return None
    price = _f(gapper.get("price"))
    atr_pct = _f(store_feat.get("atr_pct"))
    if price <= 0 or atr_pct <= 0:
        return None  # no usable premarket price / no store ATR → cannot be gated → drop
    return {
        "symbol": symbol,
        # REAL premarket gap (abs %, matching the engine's |open − prev_close| convention)
        "gap_pct": abs(_f(gapper.get("gap_pct"))),
        # premarket-vs-daily-avg RVOL proxy (documented caveat above)
        "rvol": ce.rvol(_f(gapper.get("premarket_volume")), _f(store_feat.get("avg_volume"))),
        "atr_pct": atr_pct,
        "price": price,
        "dollar_vol": _f(store_feat.get("prev_dollar_vol")),
        "earnings_today": bool(store_feat.get("earnings_today", False)),
    }


def premarket_panel(
    gappers: list[dict[str, Any]], store_features: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Map a day's gapper rows → the engine feature panel, dropping uncoverable symbols.

    ``store_features`` is a ``{symbol: store_feat}`` map (the caller's historical-data join). Rows
    whose symbol has no store coverage, or no usable price/ATR, are silently skipped — feed the
    result straight to ``candidate_engine.select_candidates``."""
    panel: list[dict[str, Any]] = []
    for gapper in gappers:
        symbol = str(gapper.get("symbol") or "").strip()
        row = premarket_feature_row(gapper, store_features.get(symbol))
        if row is not None:
            panel.append(row)
    return panel
