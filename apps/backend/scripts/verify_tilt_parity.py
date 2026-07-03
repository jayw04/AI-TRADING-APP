#!/usr/bin/env python3
"""PORT-001 delta-parity gate — correlation-aware tilt + KMLM (§5.6/§11 #1).

Construction-verification for the two changes ported into the platform's cross-asset sleeve
(``app/research/factor_lab/cross_asset.py``): the 9th asset (KMLM) and the correlation-aware tilt
(λ=0.5). It feeds the **sibling's own total-return data** (its ``yahoo_daily_cache.json``, the same
adjusted closes the sibling live book uses) into the *platform* ``cross_asset_tsmom`` engine and
asserts the documented directional book, isolating the port from data-source noise (Alpaca-vs-Yahoo).

This is the delta-scoped gate that runs offline today; the full combined-book onboarding gate
against the sibling's regenerated 9-asset reference is ``run_port001_reproduction.py`` (§6).

Gate (all must hold, on the latest common-date as-of):
  1. KMLM participates with a sane sleeve share (documented ~7–11%; band [3%, 20%]).
  2. The tilt LOWERS the sleeve's weighted equity-correlation vs the untilted baseline (its purpose).
  3. The tilt DOWN-weights SPY (the equity proxy, corr→1) vs baseline.
  4. Gross ≤ 1 (de-risk only, never levers up).

Usage:  python scripts/verify_tilt_parity.py [--cache <yahoo_daily_cache.json>] [--out <dir>]
Exit 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/backend on path
from app.research.factor_lab.cross_asset import (  # noqa: E402
    CROSS_ASSET_UNIVERSE,
    cross_asset_tsmom,
)

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = Path(r"C:\LLM-RAG-APP\claude-trading-view\yahoo_daily_cache.json")
_DEFAULT_OUT = _REPO / "docs" / "implementation" / "evidence" / "port_001"
_LAMBDA = 0.5
_CORR_LB = 60


def _panel(cache_path: Path, assets: tuple[str, ...]) -> pd.DataFrame:
    """Total-return close panel (index = date, cols = asset) over the common dates from the
    sibling Yahoo cache (``c`` is Yahoo adjusted close = total-return)."""
    raw = json.loads(cache_path.read_text())
    missing = [a for a in assets if a not in raw]
    if missing:
        raise SystemExit(f"assets absent from cache {cache_path}: {missing}")
    series = {
        a: pd.Series({pd.Timestamp(d): float(bar["c"]) for d, bar in raw[a].items()})
        for a in assets
    }
    return pd.DataFrame(series).sort_index().dropna(how="any")


def _norm(sleeve) -> dict[str, float]:
    """Sleeve weights normalized by gross (share of the invested book), tilt/baseline-comparable."""
    g = sleeve.gross or 1.0
    return {k: v / g for k, v in sleeve.weights.items() if v > 0}


def _sleeve_spy_corr(panel: pd.DataFrame, weights_norm: dict[str, float], proxy: str = "SPY") -> float:
    """Weighted-average asset-vs-proxy 60d correlation at the last date — a single-as-of proxy for
    the sleeve's equity-correlation (what the tilt is designed to reduce)."""
    rets = panel.pct_change().iloc[-_CORR_LB:]
    pr = rets[proxy]
    num = 0.0
    for a, w in weights_norm.items():
        c = rets[a].corr(pr)
        if pd.notna(c):
            num += w * float(c)
    return num


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=_DEFAULT_CACHE)
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = ap.parse_args()

    assets = tuple(CROSS_ASSET_UNIVERSE)
    if "KMLM" not in assets:
        raise SystemExit("CROSS_ASSET_UNIVERSE is missing KMLM — the refresh isn't applied")

    panel = _panel(args.cache, assets)
    asof_date = str(panel.index[-1].date())

    base = cross_asset_tsmom(panel, corr_aware=False)
    tilt = cross_asset_tsmom(panel, corr_aware=True, corr_lambda=_LAMBDA, corr_lookback=_CORR_LB)
    bw, tw = _norm(base), _norm(tilt)

    base_corr = _sleeve_spy_corr(panel, bw)
    tilt_corr = _sleeve_spy_corr(panel, tw)
    kmlm = tw.get("KMLM", 0.0)
    spy_base, spy_tilt = bw.get("SPY", 0.0), tw.get("SPY", 0.0)

    checks = {
        "kmlm_participates": 0.03 <= kmlm <= 0.20,
        "tilt_lowers_equity_corr": tilt_corr < base_corr,
        "tilt_downweights_spy": spy_tilt < spy_base + 1e-9,
        "gross_le_1": tilt.gross <= 1.0 + 1e-9,
    }
    passed = all(checks.values())

    result = {
        "gate": "delta_parity_tilt_kmlm",
        "passed": passed,
        "asof": asof_date,
        "panel_rows": int(panel.shape[0]),
        "assets": list(assets),
        "lambda": _LAMBDA,
        "corr_lookback": _CORR_LB,
        "sleeve_spy_corr": {"baseline": round(base_corr, 4), "tilt": round(tilt_corr, 4)},
        "kmlm_weight_norm": round(kmlm, 4),
        "spy_weight_norm": {"baseline": round(spy_base, 4), "tilt": round(spy_tilt, 4)},
        "gross": {"baseline": round(base.gross, 4), "tilt": round(tilt.gross, 4)},
        "weights_norm_tilt": {k: round(v, 4) for k, v in sorted(tw.items(), key=lambda x: -x[1])},
        "weights_norm_baseline": {k: round(v, 4) for k, v in sorted(bw.items(), key=lambda x: -x[1])},
        "checks": checks,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "port001_delta_parity_tilt.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"[{'PASS' if passed else 'FAIL'}] delta-parity tilt+KMLM gate  (asof {asof_date})")
    print(f"  KMLM sleeve share (tilt):      {kmlm:6.2%}")
    print(f"  sleeve equity-corr base->tilt:  {base_corr:+.3f} -> {tilt_corr:+.3f}")
    print(f"  SPY sleeve share base->tilt:    {spy_base:6.2%} -> {spy_tilt:6.2%}")
    print(f"  gross (tilt):                  {tilt.gross:.3f}")
    for name, ok in checks.items():
        print(f"  {'ok ' if ok else 'FAIL'}  {name}")
    print(f"  wrote {out_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
