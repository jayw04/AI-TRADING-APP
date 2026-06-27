"""PORT-001 reproduction harness — run the §2 reproduce-first gate (ADR 0030 #4).

Builds the Workbench Evidence Package for the Combined Book and compares it to the **sibling
reference** through the objective **Onboarding Gate**. On pass, the capability advances L1→L2
(attach the Evidence Package, promote `programs.py` planned→validated, issue the Capability
Certificate Gate-Passed).

Two modes:

  --synthetic     Fabricate two sleeves + a matching reference and run the whole pipeline with
                  NO external data. Verifies the harness wiring + output format end-to-end
                  (this is what CI / a Norton-blocked box can run).

  (default)       REAL reproduction — requires a non-Norton machine with the data:
                    * the Sharadar DuckDB (FactorDataStore) for the equity-momentum sleeve, and
                    * Alpaca market-data (data.alpaca.markets) for the cross-asset ETF bars,
                      post-processed to total-return via the §1 Total-Return Adapter.
                  Plus a sibling-reference JSON (--reference) exported from claude-trading-view:
                    {"sharpe":0.84,"max_drawdown":0.119,"trades":N,
                     "daily_returns":{"YYYY-MM-DD":r,...},"weights":{"SYM":w,...}}

    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/run_port001_reproduction.py \
        --synthetic                         # offline wiring self-test
    apps/backend/.venv/Scripts/python.exe apps/backend/scripts/run_port001_reproduction.py \
        --db data/workbench.sqlite --reference docs/.../sibling_reference.json   # the real run

Read-only research (ADR 0019); no order path. Writes the Evidence Package JSON + the Lifecycle
Fidelity scorecard markdown under docs/implementation/evidence/port_001/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.research.factor_lab.configs import PORT_001  # noqa: E402
from app.research.factor_lab.cross_asset import CROSS_ASSET_UNIVERSE  # noqa: E402
from app.research.factor_lab.reproduction import (  # noqa: E402
    run_reproduction,
)

_OUT = _BACKEND.parents[1] / "docs" / "implementation" / "evidence" / "port_001"


# --------------------------------------------------------------------------- synthetic self-test
def _synthetic_inputs() -> tuple[pd.DataFrame, dict, dict, int]:
    """Two equal-vol, ~uncorrelated sleeves + a reference that MATCHES the Workbench candidate
    (so the gate passes) — proves the pipeline + output format with no external data."""
    rng = np.random.default_rng(11)
    idx = pd.date_range("2018-01-01", periods=1500, freq="B")
    sleeve_returns = pd.DataFrame(
        {"equity": 0.0006 + 0.010 * rng.standard_normal(len(idx)),
         "cross_asset": 0.0004 + 0.008 * rng.standard_normal(len(idx))},
        index=idx,
    )
    internal = {"equity": {"AAPL": 0.5, "MSFT": 0.5},
                "cross_asset": {"TLT": 0.4, "IEF": 0.3, "GLD": 0.2, "UUP": 0.1}}
    # Build the candidate metrics directly, then set the reference == candidate so the gate is
    # exercised end-to-end and passes (proving the wiring + report format).
    from app.research.factor_lab.portfolio import construct_portfolio, portfolio_evidence_package
    pkg = portfolio_evidence_package(sleeve_returns, internal, equity_sleeve="equity")
    book = construct_portfolio(sleeve_returns, internal, equity_sleeve="equity")
    w = np.array([book.sleeve_weights[s] for s in sleeve_returns.columns])
    cand_daily = pd.Series(sleeve_returns.to_numpy() @ w, index=sleeve_returns.index)
    reference = {
        "sharpe": pkg["metrics"]["sharpe"], "max_drawdown": pkg["metrics"]["max_drawdown"],
        "trades": 120,
        "daily_returns": {d.strftime("%Y-%m-%d"): float(v) for d, v in cand_daily.items()},
        "weights": dict(book.weights),
    }
    return sleeve_returns, internal, reference, 120


# --------------------------------------------------------------------------- real-data builders
def _build_real_inputs(db: str) -> tuple[pd.DataFrame, dict, int]:
    """Build the Workbench sleeve return series from real data (data-machine path).

    Sleeve B (cross-asset) is fully wired: build the 8-ETF total-return panel via the §1
    Total-Return Adapter (Alpaca bars + a DistributionsProvider), then `backtest_cross_asset_sleeve`.
    Sleeve A (equity momentum) uses `run_momentum_backtest` over the Sharadar store; the crash
    overlay (ADR 0020 vol-target + VIX/breadth) is applied on top. Both require the data env —
    wire the concrete providers here on the non-Norton machine (see the module docstring)."""
    raise NotImplementedError(
        "real reproduction requires the data env: a Sharadar FactorDataStore + a concrete "
        "Total-Return DistributionsProvider over data.alpaca.markets (Norton-blocked here). Wire "
        "them in _build_real_inputs on the non-Norton machine; the engine "
        "(backtest_cross_asset_sleeve + run_reproduction) + the --synthetic self-test are ready. "
        f"Universe = {list(CROSS_ASSET_UNIVERSE)}."
    )


# --------------------------------------------------------------------------- report
def _write_outputs(result: dict, out_dir: Path, *, synthetic: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = "SYNTHETIC" if synthetic else "REPRODUCTION"
    (out_dir / f"port001_{tag.lower()}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")
    g = result["gate"]
    lines = [
        f"# PORT-001 Reproduction — {tag}",
        "",
        f"**Onboarding Gate: {'PASSED' if result['passed'] else 'FAILED'}**  ·  "
        f"Lifecycle Fidelity **{g['fidelity_pct']}%**",
        "",
        "| Criterion | Value | Threshold | Pass |",
        "|---|---|---|---|",
        *[f"| {c['name']} | {c['value']} | {c['threshold']} | {'✓' if c['passed'] else '✗'} |"
          for c in g["criteria"]],
        "",
        f"- Candidate (Workbench): Sharpe {result['candidate']['sharpe']} · "
        f"MaxDD {result['candidate']['max_drawdown']} · trades {result['candidate']['trades']}",
        f"- Reference (sibling): Sharpe {result['reference']['sharpe']} · "
        f"MaxDD {result['reference']['max_drawdown']} · trades {result['reference']['trades']}",
        "",
        ("_Synthetic self-test — proves the harness wiring, NOT a real reproduction._"
         if synthetic else
         "_On PASS: attach this Evidence Package, promote programs.py planned->validated, and "
         "issue the Capability Certificate as v1.0 (Gate-Passed) advancing L1+L2._"),
    ]
    md = out_dir / f"LifecycleFidelity_{tag}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def main() -> int:
    ap = argparse.ArgumentParser(description="PORT-001 reproduction harness")
    ap.add_argument("--synthetic", action="store_true", help="offline wiring self-test (no data)")
    ap.add_argument("--db", default="data/workbench.sqlite")
    ap.add_argument("--reference", default=None, help="sibling reference JSON (real mode)")
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()

    if args.synthetic:
        sleeve_returns, internal, reference, cand_trades = _synthetic_inputs()
    else:
        sleeve_returns, internal, cand_trades = _build_real_inputs(args.db)
        if not args.reference:
            print("ERROR: --reference <sibling.json> is required for the real reproduction")
            return 2
        reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))

    result = run_reproduction(
        sleeve_returns=sleeve_returns, sleeve_internal_weights=internal,
        equity_sleeve=PORT_001.portfolio.equity_sleeve, reference=reference,
        cand_trades=cand_trades, verdict=PORT_001.verdict,
    )
    md = _write_outputs(result, args.out, synthetic=args.synthetic)
    verdict = "PASSED" if result["passed"] else "FAILED"
    print(f"[port001-reproduction] Onboarding Gate {verdict}  ·  "
          f"fidelity {result['gate']['fidelity_pct']}%  ->  {md}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
