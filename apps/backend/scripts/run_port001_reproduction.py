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
        --reference docs/.../sibling_reference.json   # the real run (default --db = factor duckdb)

Read-only research (ADR 0019); no order path. Writes the Evidence Package JSON + the Lifecycle
Fidelity scorecard markdown under docs/implementation/evidence/port_001/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.research.factor_lab.configs import PORT_001  # noqa: E402
from app.research.factor_lab.reproduction import (  # noqa: E402
    build_self_stack_inputs,
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
def _build_real_inputs(db: str | None) -> tuple[pd.DataFrame, dict, int]:
    """Self-stack inputs (the platform's OWN data path): Sleeve A over the Sharadar
    ``FactorDataStore`` + Sleeve B over the §1 Total-Return Adapter (Alpaca bars + Sharadar
    distributions). A thin wrapper over the shared ``reproduction.build_self_stack_inputs`` (the
    same code the Factor Lab runner's ``_run_portfolio`` uses — one implementation, no drift)."""
    from app.factor_data.store import FactorDataStore

    with FactorDataStore(db_path=db, read_only=True) as store:
        return build_self_stack_inputs(PORT_001, store)


# --------------------------------------------------------------------------- construction-verify
def _sibling_inputs(sibling_dir: str) -> tuple[pd.DataFrame, dict, dict, int]:
    """Construction-verification inputs (the chosen reproduce-first test): feed the sibling's OWN
    committed sleeve return series through the platform's PCE/ERC + Evidence Package + Gate, vs the
    sibling's combined book. This isolates the *construction engine being onboarded* from
    data-source noise (Alpaca-vs-Yahoo) — it asks "does our blend reproduce the book?", not "does
    our data stack match theirs?". Reads claude-trading-view's ``factor_backtest_*.json``
    (``results.crash_engine.daily``) + ``cross_asset_momentum_*.json`` (``results.daily``)."""
    import glob
    import os

    from app.factor_data import evidence as ev

    def _latest(pat: str) -> str:
        hits = sorted(glob.glob(os.path.join(sibling_dir, pat)))
        if not hits:
            raise FileNotFoundError(f"no {pat} under {sibling_dir}")
        return hits[-1]

    fb = json.loads(Path(_latest("factor_backtest_*.json")).read_text(encoding="utf-8"))
    ca = json.loads(Path(_latest("cross_asset_momentum_*.json")).read_text(encoding="utf-8"))
    eq = dict(fb["results"]["crash_engine"]["daily"])      # date -> daily return
    cad = dict(ca["results"]["daily"])
    common = sorted(set(eq) & set(cad))
    idx = pd.to_datetime(common)
    sleeve_returns = pd.DataFrame(
        {"equity": [eq[d] for d in common], "cross_asset": [cad[d] for d in common]}, index=idx)

    # The sibling cross-asset internal weights (live §7, normalized). The equity sleeve enters the
    # blend as one synthetic instrument (its 150-name internal book is the equity sleeve's own
    # concern, not the cross-sleeve blend's). Both are look-through-comparable to the reference.
    live = {"IEF": 0.158, "UUP": 0.153, "TLT": 0.091, "SPY": 0.056,
            "EFA": 0.041, "DBC": 0.038, "GLD": 0.032, "EEM": 0.024}
    ssum = sum(live.values())
    ca_w = {k: v / ssum for k, v in live.items()}
    internal = {"equity": {"equity_momentum": 1.0}, "cross_asset": ca_w}

    # reference = the sibling COMBINED book (fixed 0.40 equity + 0.60 cross-asset), metrics via the
    # platform's own evidence functions (apples-to-apples with the candidate).
    comb = {d: 0.40 * eq[d] + 0.60 * cad[d] for d in common}
    eqv, curve = 100_000.0, []
    for d in common:
        eqv *= 1.0 + comb[d]
        curve.append((date.fromisoformat(d), eqv))
    ref_w = {"equity_momentum": 0.40, **{k: 0.60 * v for k, v in ca_w.items()}}
    reference = {
        "sharpe": round(ev.sharpe(ev.daily_returns(curve)), 4),
        "max_drawdown": round(abs(ev.max_drawdown(curve)), 4),
        "trades": 0,  # construction-verification feeds return series → no rebalance sim; N/A
        "daily_returns": {d: comb[d] for d in common},
        "weights": ref_w,
    }
    return sleeve_returns, internal, reference, 0  # cand_trades=0 == ref → trade criterion N/A


# --------------------------------------------------------------------------- report
def _write_outputs(result: dict, out_dir: Path, *, tag: str, footer: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"port001_{tag.lower()}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")
    g = result["gate"]
    lines = [
        f"# PORT-001 Reproduction — {tag.replace('_', ' ').title()}",
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
        footer,
    ]
    md = out_dir / f"LifecycleFidelity_{tag.upper()}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def main() -> int:
    ap = argparse.ArgumentParser(description="PORT-001 reproduction harness")
    ap.add_argument("--synthetic", action="store_true", help="offline wiring self-test (no data)")
    ap.add_argument("--from-sibling", default=None, metavar="DIR",
                    help="construction-verification: blend the sibling's OWN committed sleeve "
                         "return series (claude-trading-view dir) through the platform PCE + Gate")
    ap.add_argument("--db", default=None,
                    help="Sharadar FactorDataStore DuckDB path (default: app's factor_data duckdb)")
    ap.add_argument("--reference", default=None, help="sibling reference JSON (real mode)")
    ap.add_argument("--out", type=Path, default=_OUT)
    args = ap.parse_args()

    pf = PORT_001.portfolio
    assert pf is not None, "PORT_001 is a portfolio program"  # noqa: S101 — config invariant

    if args.synthetic:
        tag = "synthetic"
        footer = "_Synthetic self-test — proves the harness wiring, NOT a real reproduction._"
        sleeve_returns, internal, reference, cand_trades = _synthetic_inputs()
    elif args.from_sibling:
        tag = "construction_verification"
        footer = ("_Construction-verification: the sibling's OWN sleeve return series blended "
                  "through the platform PCE/ERC vs its combined book — isolates the construction "
                  "engine from data-source noise. A clean pass is L1+L2 construction evidence; the "
                  "self-stack (Alpaca) data-fidelity port is a separate study._")
        sleeve_returns, internal, reference, cand_trades = _sibling_inputs(args.from_sibling)
    else:
        tag = "reproduction"
        footer = ("_On PASS: attach this Evidence Package, promote programs.py planned->validated, "
                  "and issue the Capability Certificate as v1.0 (Gate-Passed) advancing L1+L2._")
        sleeve_returns, internal, cand_trades = _build_real_inputs(args.db)
        if not args.reference:
            print("ERROR: --reference <sibling.json> is required for the real reproduction")
            return 2
        reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))

    result = run_reproduction(
        sleeve_returns=sleeve_returns, sleeve_internal_weights=internal,
        equity_sleeve=pf.equity_sleeve, reference=reference,
        cand_trades=cand_trades, verdict=PORT_001.verdict,
    )
    md = _write_outputs(result, args.out, tag=tag, footer=footer)
    verdict = "PASSED" if result["passed"] else "FAILED"
    print(f"[port001-reproduction] Onboarding Gate {verdict}  ·  "
          f"fidelity {result['gate']['fidelity_pct']}%  ->  {md}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
