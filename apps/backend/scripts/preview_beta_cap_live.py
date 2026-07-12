#!/usr/bin/env python3
"""Preview the equity-beta-cap governor on combined-book's LIVE target book (read-only).

The governor (`app.research.factor_lab.beta_cap.cap_equity_beta`) only runs inside the strategy's
weekly rebalance, so its report-only dry-run doesn't fire until the market is open and the book
rebalances. This script reconstructs the book combined-book (PORT-001, id=9) WOULD build right now —
the 40/60 blend of the crash-protected equity-momentum sleeve + the 9-ETF cross-asset TSMOM sleeve
(correlation-aware tilt on) — from live Alpaca daily bars, and runs the governor on it, so the owner
can see the real equity-beta risk contribution + would-be haircut and decide on ``enforce_beta_cap``
WITHOUT waiting for the next RTH rebalance.

Faithful to the live template (`strategies_user/templates/combined_book.py`): same 12-1 momentum
(252/21), top-quantile equal-weight + per-name cap, SPY-MA regime filter, the exact `cross_asset_tsmom`
sleeve, the fixed 40/60 blend, and `cap_equity_beta`. Equity momentum is computed from Alpaca daily
bars here (the live sleeve reads it from the Sharadar factor store) — a small approximation that barely
moves the equity-*as-a-class* risk contribution the governor keys on; flagged in the output.

Run INSIDE the backend container (Alpaca creds + truststore + app modules):
    docker compose exec -T backend python scripts/preview_beta_cap_live.py
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.research.factor_lab.beta_cap import cap_equity_beta, default_equity_names
from app.research.factor_lab.cross_asset import CROSS_ASSET_UNIVERSE, cross_asset_tsmom

# Live combined-book params (mirrors the template default_params).
LOOKBACK, SKIP = 252, 21
TOP_QUANTILE, MAX_POS = 0.40, 0.04
MARKET_MA, MARKET_SYM = 200, "SPY"
EQ_W, CA_W = 0.40, 0.60
CA_VOL_LB, CA_VOL_TARGET = 60, 0.10
CORR_LAMBDA, CORR_LB = 0.5, 60
BETA_CAP, BETA_LB, BETA_SHRINK = 0.80, 120, 0.15
_SYMBOLS_FILE = Path("/app/data/combined_book_symbols.txt")
_OUT = Path("/app/data/port001_beta_cap_live_preview.json")  # data/ is mounted; docs/ is not


def _fetch_daily(symbols: list[str], days: int = 520) -> dict[str, pd.Series]:
    """Batch daily-close series per symbol from Alpaca IEX (total-return-naive close, as the live
    sleeve uses). Truststore-injected (ADR 0017) so it works behind Norton."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from app.market_data.bar_cache import load_credentials
    from app.utils.tls_trust import enable_os_trust_store

    enable_os_trust_store()
    creds = load_credentials()
    client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    out: dict[str, pd.Series] = {}
    for i in range(0, len(symbols), 100):  # chunk to keep requests modest
        chunk = symbols[i:i + 100]
        req = StockBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame(1, TimeFrameUnit.Day),
                               start=start, end=end, feed=DataFeed.IEX, limit=10000)
        data = client.get_stock_bars(req).data
        for sym in chunk:
            bars = data.get(sym, [])
            if bars:
                out[sym] = pd.Series(
                    [float(b.close) for b in bars],
                    index=[pd.Timestamp(b.timestamp).tz_localize(None).normalize() for b in bars])
    return out


def _equity_sleeve(px: dict[str, pd.Series], equity_names: list[str]) -> dict[str, float]:
    """Crash-protected 12-1 momentum: regime filter (SPY<MA → cash), then top-quantile equal-weight,
    per-name capped, summing to 1 (the sleeve's internal weights)."""
    spy = px.get(MARKET_SYM)
    if spy is not None and len(spy) >= MARKET_MA + 1 and spy.iloc[-1] < spy.iloc[-(MARKET_MA + 1):-1].mean():
        return {}  # regime = below MA → equity sleeve to cash
    mom: dict[str, float] = {}
    for s in equity_names:
        c = px.get(s)
        if c is None or len(c) < LOOKBACK + SKIP + 1:
            continue
        p_skip, p_base = c.iloc[-(SKIP + 1)], c.iloc[-(SKIP + LOOKBACK + 1)]
        if p_base > 0:
            mom[s] = float(p_skip / p_base - 1.0)
    if not mom:
        return {}
    ranked = sorted(mom, key=lambda s: mom[s], reverse=True)
    k = max(1, math.ceil(len(ranked) * TOP_QUANTILE))
    picks = ranked[:k]
    w = min(1.0 / len(picks), MAX_POS)
    raw = {s: w for s in picks}
    tot = sum(raw.values()) or 1.0
    return {s: v / tot for s, v in raw.items()}  # normalize to 1 (sleeve-internal)


def main() -> int:
    symbols = [s.strip().upper() for s in _SYMBOLS_FILE.read_text().splitlines() if s.strip()]
    ca_syms = [s.upper() for s in CROSS_ASSET_UNIVERSE]
    equity_names = [s for s in symbols if s not in set(ca_syms)]
    print(f"reconstructing combined-book target: {len(equity_names)} equity + {len(ca_syms)} ETFs")

    px = _fetch_daily(symbols)
    print(f"fetched daily bars for {len(px)}/{len(symbols)} symbols")

    # --- equity sleeve (×0.40) ---
    eq_w = _equity_sleeve(px, equity_names)
    # --- cross-asset sleeve (×0.60), exact live engine ---
    ca_panel = pd.DataFrame({s: px[s] for s in ca_syms if s in px}).sort_index().dropna(how="any")
    sleeve = cross_asset_tsmom(ca_panel, lookback=LOOKBACK, skip=SKIP, vol_lookback=CA_VOL_LB,
                               vol_target=CA_VOL_TARGET, corr_aware=True, corr_lambda=CORR_LAMBDA,
                               corr_lookback=CORR_LB)
    ca_w = {k: float(v) for k, v in sleeve.weights.items() if v > 0} if sleeve.status == "ok" else {}

    target: dict[str, float] = {}
    for s, w in eq_w.items():
        target[s] = target.get(s, 0.0) + EQ_W * w
    for s, w in ca_w.items():
        target[s] = target.get(s, 0.0) + CA_W * w
    if not target:
        print("ERROR: empty target book (regime filter to cash or insufficient data)")
        return 1

    # --- governor on the target book ---
    names = list(target)
    ret_panel = pd.DataFrame({s: px[s] for s in names if s in px}).sort_index().pct_change().dropna(how="any")
    eq_set = default_equity_names(names)
    new_target, report = cap_equity_beta(target, ret_panel, equity_names=eq_set,
                                         cap=BETA_CAP, lookback=BETA_LB, shrink=BETA_SHRINK)

    gross = sum(target.values())
    eq_capital = sum(v for s, v in target.items() if s in eq_set)
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "note": "OFFLINE PREVIEW of the report-only governor on the live target book "
                "(equity momentum from Alpaca bars, not the Sharadar factor store — approximation).",
        "book": {"n_names": len(target), "gross": round(gross, 4),
                 "equity_capital_pct": round(eq_capital / gross, 4) if gross else None,
                 "n_equity_names": len(eq_w), "regime_to_cash": not eq_w,
                 "cross_asset": {k: round(v, 4) for k, v in sorted(ca_w.items(), key=lambda x: -x[1])}},
        "governor": report,
        "cap": BETA_CAP,
    }
    try:
        _OUT.write_text(json.dumps(result, indent=2, default=str))
    except OSError:
        pass

    print("\n=== equity-beta-cap governor — LIVE TARGET-BOOK PREVIEW ===")
    print(f"  book: {len(target)} names, gross {gross:.2f}, equity capital {eq_capital / gross:.1%}"
          + ("  (equity sleeve REGIME-TO-CASH)" if not eq_w else ""))
    rc0 = report.get("equity_beta_rc_before")
    print(f"  equity-beta risk contribution: {rc0:.3f}  (cap {BETA_CAP})" if rc0 is not None
          else f"  governor skipped: {report.get('note')}")
    if report.get("applied"):
        print(f"  -> WOULD TRIM: equity scaled x{report['scale_equity_beta']:.3f}, "
              f"gross {report['gross_before']:.3f} -> {report['gross_after']:.3f} "
              f"(cash freed {report['cash_freed']:.3f}), RC -> {report['equity_beta_rc_after']:.3f}")
    else:
        print(f"  -> within budget, no haircut ({report.get('note')})")
    print(f"  wrote {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
