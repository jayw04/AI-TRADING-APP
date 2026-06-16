"""§5b Range-Trader symbol screen (Range Trader paper-activation plan, Finding 3).

Picks range-bound candidates for the RangeTrader fade-the-range strategy by an
**explicit, written** screen — never "NVDA because the idle row said so". Runs
fully offline against the local daily-bar cache (``bars_cache/<SYM>/1Day``), so
it is Norton-safe and needs no network or creds.

For each symbol over the recent window it checks:

  - **No trend:** ADX(14) on the daily < ``--adx-max`` (default 20).
  - **Range-bound:** price has **touched both** the support (recent low) and
    resistance (recent high) bands **>= --min-touches** times (default 2) within
    ``--touch-tol`` of the edge, and the latest close is still **inside** the
    band (not broken out).
  - **Tradeable width:** band width >= ``--min-range-pct`` (default 4%) so there
    is room between entry and exit beyond costs.
  - **Liquid enough:** avg daily dollar volume >= ``--min-dollar-vol`` (default
    $20M) and price >= ``--min-price`` ($5) so 5-min fills are realistic.

For each PASS it suggests fade-the-range levels from the recent close
distribution (entry=25th, exit=75th, stop=10th percentile — same convention as
``backtest_range_trader_alpaca.py``), guaranteed to satisfy the template's
``_levels_ok`` invariant (stop < entry < exit), plus the reward:risk ratio.

    cd apps/backend
    .venv/Scripts/python.exe scripts/screen_range_candidates.py            # whole cache universe
    .venv/Scripts/python.exe scripts/screen_range_candidates.py AAPL KO PEP # specific names
    .venv/Scripts/python.exe scripts/screen_range_candidates.py --csv out.csv

This is a screen, not a verdict: feed the PASS names + suggested levels into the
§5c pre-registered backtest before activating anything. Record this output as
activation evidence (Finding 3/4).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pandas_ta as ta

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BARS_CACHE = BACKEND_ROOT / "bars_cache"


@dataclass(frozen=True)
class ScreenConfig:
    lookback: int = 20          # sessions defining the support/resistance band
    adx_len: int = 14
    adx_max: float = 20.0       # ADX below this = no strong trend
    touch_tol: float = 0.01     # within 1% of an edge counts as a touch
    min_touches: int = 2        # per side
    min_range_pct: float = 0.04 # band width floor (resistance/support - 1)
    min_dollar_vol: float = 20_000_000.0
    min_price: float = 5.0
    min_history: int = 50       # daily bars needed for a stable ADX + band


@dataclass
class ScreenResult:
    adx: float | None = None
    support: float | None = None
    resistance: float | None = None
    range_pct: float | None = None
    touches_support: int = 0
    touches_resistance: int = 0
    dollar_vol: float | None = None
    last_close: float | None = None
    entry: float | None = None
    exit: float | None = None
    stop: float | None = None
    reward_risk: float | None = None
    passed: bool = False
    reasons: list[str] = field(default_factory=list)  # why it FAILED


def screen_symbol(bars: pd.DataFrame, cfg: ScreenConfig | None = None) -> ScreenResult:
    """Apply the §5b screen to one symbol's daily OHLCV (cols t,o,h,l,c,v,
    ascending by t). Pure: no I/O. ``reasons`` lists every failed criterion."""
    cfg = cfg or ScreenConfig()
    res = ScreenResult()
    if bars is None or len(bars) < cfg.min_history:
        res.reasons.append(f"insufficient history (<{cfg.min_history} daily bars)")
        return res

    bars = bars.sort_values("t").reset_index(drop=True)
    window = bars.tail(cfg.lookback)
    closes = window["c"].astype(float)

    # --- ADX(14): no strong trend ---
    adx_df = ta.adx(bars["h"].astype(float), bars["l"].astype(float),
                    bars["c"].astype(float), length=cfg.adx_len)
    adx_col = next((c for c in adx_df.columns if c.startswith("ADX")), None)
    adx_series = adx_df[adx_col].dropna() if adx_col is not None else pd.Series(dtype=float)
    res.adx = float(adx_series.iloc[-1]) if len(adx_series) else None
    if res.adx is None:
        res.reasons.append("ADX unavailable")
    elif res.adx >= cfg.adx_max:
        res.reasons.append(f"trending: ADX {res.adx:.1f} >= {cfg.adx_max}")

    # --- band + touches ---
    support = float(window["l"].min())
    resistance = float(window["h"].max())
    res.support, res.resistance = support, resistance
    res.range_pct = (resistance / support - 1.0) if support > 0 else None
    res.last_close = float(closes.iloc[-1])

    sup_edge = support * (1 + cfg.touch_tol)
    res_edge = resistance * (1 - cfg.touch_tol)
    res.touches_support = int((window["l"].astype(float) <= sup_edge).sum())
    res.touches_resistance = int((window["h"].astype(float) >= res_edge).sum())
    if res.touches_support < cfg.min_touches:
        res.reasons.append(
            f"support touched {res.touches_support}x (<{cfg.min_touches})")
    if res.touches_resistance < cfg.min_touches:
        res.reasons.append(
            f"resistance touched {res.touches_resistance}x (<{cfg.min_touches})")

    # not broken out: latest close still inside the support..resistance band
    if res.last_close > resistance or res.last_close < support:
        res.reasons.append("broken out: last close outside the band")

    # --- tradeable width ---
    if res.range_pct is None or res.range_pct < cfg.min_range_pct:
        res.reasons.append(
            f"band too narrow: {(res.range_pct or 0) * 100:.1f}% "
            f"(<{cfg.min_range_pct * 100:.0f}%)")

    # --- liquidity ---
    res.dollar_vol = float((window["c"].astype(float) * window["v"].astype(float)).mean())
    if res.dollar_vol < cfg.min_dollar_vol:
        res.reasons.append(
            f"thin: ${res.dollar_vol / 1e6:.1f}M ADV (<${cfg.min_dollar_vol / 1e6:.0f}M)")
    if res.last_close < cfg.min_price:
        res.reasons.append(f"price ${res.last_close:.2f} < ${cfg.min_price:.0f}")

    # --- suggested fade-the-range levels (percentiles of recent closes) ---
    entry = float(closes.quantile(0.25))
    exit_ = float(closes.quantile(0.75))
    stop = float(closes.quantile(0.10))
    if stop < entry < exit_:  # the template's _levels_ok invariant
        res.entry, res.exit, res.stop = entry, exit_, stop
        res.reward_risk = (exit_ - entry) / (entry - stop) if entry > stop else None
    else:
        res.reasons.append("degenerate level distribution (stop<entry<exit fails)")

    res.passed = not res.reasons
    return res


# ---- I/O (CLI only; not exercised by the pure-function tests) ----


def _load_daily_bars(symbol: str, cache_dir: Path) -> pd.DataFrame | None:
    files = sorted((cache_dir / symbol / "1Day").glob("*.parquet"))
    if not files:
        return None
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.drop_duplicates("t").sort_values("t").reset_index(drop=True)


def _universe(cache_dir: Path) -> list[str]:
    if not cache_dir.exists():
        return []
    return sorted(p.name for p in cache_dir.iterdir() if (p / "1Day").is_dir())


def main() -> int:
    ap = argparse.ArgumentParser(description="§5b Range-Trader symbol screen (offline).")
    ap.add_argument("symbols", nargs="*", help="Tickers to screen (default: whole cache universe).")
    ap.add_argument("--adx-max", type=float, default=ScreenConfig.adx_max)
    ap.add_argument("--lookback", type=int, default=ScreenConfig.lookback)
    ap.add_argument("--min-touches", type=int, default=ScreenConfig.min_touches)
    ap.add_argument("--min-range-pct", type=float, default=ScreenConfig.min_range_pct)
    ap.add_argument("--min-dollar-vol", type=float, default=ScreenConfig.min_dollar_vol)
    ap.add_argument("--csv", default=None, help="Write the full ranked result to this CSV.")
    ap.add_argument("--cache-dir", default=str(BARS_CACHE),
                    help="Daily-bar cache root (default: this backend's bars_cache/).")
    args = ap.parse_args()
    cache_dir = Path(args.cache_dir)

    cfg = ScreenConfig(
        lookback=args.lookback, adx_max=args.adx_max, min_touches=args.min_touches,
        min_range_pct=args.min_range_pct, min_dollar_vol=args.min_dollar_vol,
    )
    symbols = [s.upper() for s in args.symbols] or _universe(cache_dir)
    if not symbols:
        print(f"No symbols and no cache at {cache_dir}.", file=sys.stderr)
        return 1

    rows = []
    for sym in symbols:
        bars = _load_daily_bars(sym, cache_dir)
        if bars is None:
            rows.append((sym, ScreenResult(reasons=["no cached daily bars"])))
            continue
        rows.append((sym, screen_symbol(bars, cfg)))

    passers = [(s, r) for s, r in rows if r.passed]
    # Rank passers by ADX asc (calmest first), then reward:risk desc.
    passers.sort(key=lambda sr: (sr[1].adx if sr[1].adx is not None else 99,
                                 -(sr[1].reward_risk or 0)))

    print(f"\nScreened {len(symbols)} symbol(s) — {len(passers)} PASS "
          f"(ADX<{cfg.adx_max}, >={cfg.min_touches} touches/side, "
          f">=${cfg.min_dollar_vol / 1e6:.0f}M ADV, range>={cfg.min_range_pct * 100:.0f}%)\n")
    if passers:
        print(f"{'SYM':<7}{'ADX':>6}{'support':>10}{'resist':>10}{'range%':>8}"
              f"{'tch S/R':>9}{'$ADV(M)':>9}{'entry':>9}{'exit':>9}{'stop':>8}{'R:R':>6}")
        for sym, r in passers:
            print(f"{sym:<7}{r.adx:>6.1f}{r.support:>10.2f}{r.resistance:>10.2f}"
                  f"{r.range_pct * 100:>7.1f}%{f'{r.touches_support}/{r.touches_resistance}':>9}"
                  f"{r.dollar_vol / 1e6:>9.0f}{r.entry:>9.2f}{r.exit:>9.2f}{r.stop:>8.2f}"
                  f"{r.reward_risk:>6.2f}")
    else:
        print("(no passers — loosen --adx-max / --min-touches or widen the universe)")

    if args.csv:
        df = pd.DataFrame([{"symbol": s, **vars(r), "reasons": "; ".join(r.reasons)}
                           for s, r in rows])
        df.to_csv(args.csv, index=False)
        print(f"\nFull ranked result ({len(rows)} rows) -> {args.csv}")

    print("\nNext: feed PASS names + suggested levels into the §5c pre-registered "
          "backtest before activating (do NOT activate on the screen alone).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
