"""PORT-001 portfolio ProgramSpec — spec validation, config registration, runner dispatch."""

from __future__ import annotations

from datetime import date

import pytest

from app.research.factor_lab.configs import PORT_001, PROGRAMS
from app.research.factor_lab.runner import run_program
from app.research.factor_lab.spec import PortfolioSpec, ProgramSpec, SleeveSpec, VerdictSpec

_EQ = SleeveSpec("equity", "equity_momentum")
_CA = SleeveSpec("cross_asset", "cross_asset_tsmom")
_V = VerdictSpec(rules=(), default_outcome="B", default_action="x")


def _spec(**kw):
    base = dict(id="X", name="x", philosophy="p", factor="momentum", factor_params={},
                n=20, start=date(2016, 1, 1), end=date(2026, 1, 1), verdict=_V)
    base.update(kw)
    return ProgramSpec(**base)


def test_portfolio_spec_validation():
    PortfolioSpec(sleeves=(_EQ, _CA), equity_sleeve="equity")  # ok
    with pytest.raises(ValueError, match="unique"):
        PortfolioSpec(sleeves=(_EQ, _EQ), equity_sleeve="equity")
    with pytest.raises(ValueError, match="equity_sleeve"):
        PortfolioSpec(sleeves=(_EQ, _CA), equity_sleeve="missing")
    with pytest.raises(ValueError, match="budgets"):
        PortfolioSpec(sleeves=(_EQ, _CA), equity_sleeve="equity", budgets=(0.5,))


def test_program_requires_portfolio_for_portfolio_construction():
    with pytest.raises(ValueError, match="requires a PortfolioSpec"):
        _spec(construction="portfolio")  # no portfolio= given
    # with one it's valid
    _spec(construction="portfolio",
          portfolio=PortfolioSpec(sleeves=(_EQ, _CA), equity_sleeve="equity"))


def test_port001_registered_and_shaped():
    assert PROGRAMS["PORT-001"] is PORT_001
    assert PORT_001.construction == "portfolio"
    assert PORT_001.portfolio is not None
    assert PORT_001.portfolio.equity_sleeve == "equity"
    assert {s.name for s in PORT_001.portfolio.sleeves} == {"equity", "cross_asset"}


def test_run_program_routes_portfolio_through_the_harness(monkeypatch):
    # 'portfolio' construction routes through the shared reproduction harness
    # (build_self_stack_inputs → portfolio_evidence_package), not a NotImplementedError.
    import pandas as pd

    sr = pd.DataFrame({"equity": [0.01, -0.01], "cross_asset": [0.0, 0.02]},
                      index=pd.to_datetime(["2020-01-02", "2020-01-03"]))
    internal = {"equity": {"AAA": 1.0}, "cross_asset": {"TLT": 1.0}}
    monkeypatch.setattr(
        "app.research.factor_lab.reproduction.build_self_stack_inputs",
        lambda spec, store: (sr, internal, 42))
    out = run_program(PORT_001, store=object())  # type: ignore[arg-type]  # store unused by the fake
    assert out["program"] == "PORT-001" and out["construction"] == "portfolio"
    assert out["trades"] == 42 and "metrics" in out and "book" in out
