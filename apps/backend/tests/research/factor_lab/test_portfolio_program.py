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


def test_run_program_dispatches_portfolio_to_gated_branch():
    # The construction is recognized (not 'unknown'); the real-data sleeve run is the
    # data-gated §2 remainder, so it raises a clear, directed NotImplementedError.
    with pytest.raises(NotImplementedError, match="data-gated"):
        run_program(PORT_001, store=None)  # type: ignore[arg-type]  # raises before touching store
