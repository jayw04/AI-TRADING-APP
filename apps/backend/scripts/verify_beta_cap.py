#!/usr/bin/env python3
"""PORT-001 lever #2 — equity-beta-cap governor demonstrator (offline, synthetic).

Builds a deliberately equity-concentrated book (single stocks carrying most of the risk + a couple of
non-equity hedges) and runs ``cap_equity_beta`` to show the de-risk-only mechanism numerically:
the equity-beta risk contribution is trimmed to the budget, only the equity names are scaled, and the
freed weight becomes cash. Writes a small evidence JSON.

A full *real-book* dry-run isn't possible offline (equity-stock returns come from Alpaca via the live
strategy context, not a committed fixture) — the platform's real-data dry-run is the strategy's
``beta_cap_report_only`` log on the live Monday rebalance. This script is the unit-level demonstration.

Usage:  python scripts/verify_beta_cap.py [--out <dir>]
Exit 0 on the expected de-risk, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/backend on path
from app.research.factor_lab.beta_cap import (  # noqa: E402
    cap_equity_beta,
    default_equity_names,
)

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_OUT = _REPO / "docs" / "implementation" / "evidence" / "port_001"
_CAP = 0.80


def _book(n: int = 250, seed: int = 7) -> tuple[pd.DataFrame, dict[str, float]]:
    """5 equity stocks on a shared market factor (dominant risk) + TLT/GLD/UUP hedges. Weighted so
    the equity-beta risk contribution starts well above the 0.80 budget."""
    rng = np.random.default_rng(seed)
    mkt = rng.standard_normal(n) * 0.02
    cols = {f"EQ{i}": 0.9 * mkt + rng.standard_normal(n) * 0.006 for i in range(5)}
    cols["TLT"] = -0.25 * mkt + rng.standard_normal(n) * 0.004
    cols["GLD"] = rng.standard_normal(n) * 0.004
    cols["UUP"] = -0.15 * mkt + rng.standard_normal(n) * 0.003
    panel = pd.DataFrame(cols, index=pd.date_range("2025-01-01", periods=n, freq="B"))
    w = {f"EQ{i}": 0.13 for i in range(5)}       # 65% equity
    w.update({"TLT": 0.15, "GLD": 0.10, "UUP": 0.10})
    return panel, w


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = ap.parse_args()

    panel, w = _book()
    eq = default_equity_names(list(w))
    new, rep = cap_equity_beta(w, panel, equity_names=eq, cap=_CAP)

    equity_scaled = all(new[s] < w[s] for s in eq)
    hedges_untouched = all(new[s] == w[s] for s in w if s not in eq)
    ok = (
        rep.get("applied") is True
        and rep["equity_beta_rc_before"] > _CAP
        and rep["equity_beta_rc_after"] <= _CAP + 1e-6
        and equity_scaled and hedges_untouched
        and rep["cash_freed"] > 0
    )

    result = {
        "check": "beta_cap_governor_synthetic",
        "passed": ok,
        "cap": _CAP,
        "equity_names": sorted(eq),
        "report": rep,
        "weights_before": {k: round(v, 4) for k, v in w.items()},
        "weights_after": {k: round(v, 4) for k, v in new.items()},
    }
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "port001_beta_cap_synthetic.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"[{'PASS' if ok else 'FAIL'}] equity-beta-cap governor (synthetic)")
    print(f"  equity-beta RC before->after:  {rep['equity_beta_rc_before']:.3f} -> {rep['equity_beta_rc_after']:.3f}  (cap {_CAP})")
    print(f"  equity scaled by:              {rep['scale_equity_beta']:.3f}")
    print(f"  gross before->after:           {rep['gross_before']:.3f} -> {rep['gross_after']:.3f}  (cash freed {rep['cash_freed']:.3f})")
    print(f"  hedges (TLT/GLD/UUP) untouched: {hedges_untouched}")
    print(f"  wrote {out_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
