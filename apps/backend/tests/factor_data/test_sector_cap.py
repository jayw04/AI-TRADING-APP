"""Sector-cap enforcement in the weigher (P10 Phase 3A §3C).

§3A only *recorded* ``max_sector_pct`` on the risk model; §3C makes the weigher
*enforce* it — capping each known sector's aggregate book weight and redistributing
the freed weight, while staying long-only and fully invested (Σ=1). Unknown-sector
names are exempt; the cap fails open when disabled, unreadable, or infeasible.

Unit tests drive ``_apply_sector_cap`` through a tiny sector stub (no DuckDB needed —
the algorithm only calls ``store.get_sectors``); the integration test runs a full
``run_momentum_backtest`` over a store with real sectors and asserts the invariant
holds at every rebalance.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.factor_data.backtest import _apply_sector_cap, run_momentum_backtest
from app.factor_data.portfolio import assert_valid_weights
from app.factor_data.store import FactorDataStore

from .conftest import build_momentum_frames

_EPS = 1e-9


class _SectorStub:
    """Minimal stand-in for FactorDataStore exposing only ``get_sectors`` —
    ``_apply_sector_cap`` touches nothing else."""

    def __init__(self, sectors: dict[str, str | None]) -> None:
        self._sectors = sectors

    def get_sectors(self, tickers: list[str]) -> dict[str, str | None]:
        return {t: self._sectors.get(t) for t in tickers}


def _sector_weights(weights: dict[str, float], sectors: dict[str, str | None]) -> dict[str, float]:
    agg: dict[str, float] = {}
    for t, w in weights.items():
        s = sectors.get(t)
        if s is not None:
            agg[s] = agg.get(s, 0.0) + w
    return agg


# ---- the cap binds, redistributes, and preserves the invariants ------------------

def test_cap_binds_and_redistributes() -> None:
    """3 sectors, cap 0.4. TECH starts at 0.6 (over) → clamped to 0.4; the freed 0.2
    is redistributed pro-rata to the under-cap sectors. Result stays Σ=1, long-only,
    and no sector exceeds the cap. Intra-sector proportions are preserved (A==B)."""
    sectors = {"A": "TECH", "B": "TECH", "C": "FIN", "D": "ENERGY"}
    weights = {"A": 0.30, "B": 0.30, "C": 0.25, "D": 0.15}  # TECH 0.60, FIN 0.25, ENERGY 0.15
    out = _apply_sector_cap(_SectorStub(sectors), weights, max_sector_pct=0.40)

    assert sum(out.values()) == pytest.approx(1.0)
    assert_valid_weights(out, cash=0.0, target_gross=1.0, long_only=True)
    for s, sw in _sector_weights(out, sectors).items():
        assert sw <= 0.40 + _EPS, f"{s} weight {sw} exceeds cap"
    assert out["A"] == pytest.approx(out["B"])              # equal names stay equal
    assert _sector_weights(out, sectors)["TECH"] == pytest.approx(0.40)  # binds exactly


def test_multi_pass_refreeze() -> None:
    """Redistribution can push a previously-under sector over the cap; the next pass
    must catch and freeze it. 4 sectors, cap 0.30, designed so FIN crosses the cap
    only *after* TECH's excess is redistributed."""
    sectors = {"A": "TECH", "B": "TECH", "C": "FIN", "D": "ENERGY", "E": "HEALTH"}
    weights = {"A": 0.30, "B": 0.30, "C": 0.25, "D": 0.10, "E": 0.05}  # TECH 0.60
    out = _apply_sector_cap(_SectorStub(sectors), weights, max_sector_pct=0.30)

    assert sum(out.values()) == pytest.approx(1.0)
    assert_valid_weights(out, cash=0.0, target_gross=1.0, long_only=True)
    for s, sw in _sector_weights(out, sectors).items():
        assert sw <= 0.30 + _EPS, f"{s} weight {sw} exceeds cap after redistribution"


def test_unknown_sector_is_exempt_and_absorbs() -> None:
    """Names with an unknown sector (get_sectors → None) are never capped and are
    eligible receivers — here the lone UNKNOWN name absorbs the excess TECH weight."""
    sectors = {"A": "TECH", "B": "TECH", "C": "TECH", "D": None}
    weights = {"A": 0.30, "B": 0.30, "C": 0.30, "D": 0.10}  # TECH 0.90
    out = _apply_sector_cap(_SectorStub(sectors), weights, max_sector_pct=0.40)

    assert sum(out.values()) == pytest.approx(1.0)
    assert _sector_weights(out, sectors)["TECH"] == pytest.approx(0.40)
    assert out["D"] == pytest.approx(0.60)                  # exempt name took the rest


@pytest.mark.parametrize("cap", [None, 1.0, 1.5])
def test_disabled_cap_is_identity(cap: float | None) -> None:
    """None / ≥1 means 'no cap' → the exact same object is returned, so the default
    leaves every legacy book byte-identical."""
    weights = {"A": 0.5, "B": 0.5}
    out = _apply_sector_cap(_SectorStub({"A": "TECH", "B": "FIN"}), weights, max_sector_pct=cap)
    assert out is weights


def test_all_unknown_sectors_passthrough() -> None:
    """A pre-sector store (all None) has nothing to cap → fail open, unchanged."""
    weights = {"A": 0.5, "B": 0.5}
    out = _apply_sector_cap(_SectorStub({"A": None, "B": None}), weights, max_sector_pct=0.4)
    assert out is weights


def test_infeasible_cap_fails_open() -> None:
    """Only 2 sectors and no exempt names → max achievable under a 0.4 cap is 0.8 < 1.0.
    Infeasible → fail open (return the input unchanged) rather than hold cash / ship a
    degenerate book, preserving the fully-invested invariant."""
    sectors = {"A": "TECH", "B": "TECH", "C": "FIN", "D": "FIN"}
    weights = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}  # TECH 0.5, FIN 0.5
    out = _apply_sector_cap(_SectorStub(sectors), weights, max_sector_pct=0.40)
    assert out is weights


def test_already_within_cap_unchanged_values() -> None:
    """When no sector exceeds the cap, the vector is returned with the same values
    (only a harmless re-normalization)."""
    sectors = {"A": "TECH", "B": "FIN", "C": "ENERGY"}
    weights = {"A": 0.34, "B": 0.33, "C": 0.33}
    out = _apply_sector_cap(_SectorStub(sectors), weights, max_sector_pct=0.40)
    assert out == pytest.approx(weights)


def test_empty_weights() -> None:
    assert _apply_sector_cap(_SectorStub({}), {}, max_sector_pct=0.4) == {}


# ---- integration: the cap binds across a full backtest and holds every rebalance --

@pytest.fixture
def sector_store(tmp_path) -> FactorDataStore:
    """The 25 momentum names with round-robin sectors (TECH/FIN/ENERGY by index%3),
    so the realized top quintile spans ≥3 sectors and a tight cap is both binding and
    feasible."""
    sep, tk = build_momentum_frames()
    tk = tk.copy()
    tk["sector"] = [("TECH", "FIN", "ENERGY")[i % 3] for i in range(len(tk))]
    s = FactorDataStore(db_path=str(tmp_path / "sector.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


def test_backtest_sector_cap_holds_every_rebalance(sector_store: FactorDataStore) -> None:
    """End-to-end: a 0.35 cap binds (uncapped, the concentrated top quintile would push
    a sector to ~0.4), yet every persisted rebalance honors it and the cap changes the
    realized book vs. the uncapped run."""
    start, end = date(2018, 7, 1), date(2020, 12, 31)
    capped = run_momentum_backtest(sector_store, start, end, top_quantile=0.2, max_sector_pct=0.35)
    uncapped = run_momentum_backtest(sector_store, start, end, top_quantile=0.2)

    assert len(capped.holdings) > 50
    for h in capped.holdings:
        assert_valid_weights(h.weights, cash=0.0, target_gross=1.0, long_only=True)
        sectors = sector_store.get_sectors(list(h.weights))
        for s, sw in _sector_weights(h.weights, sectors).items():
            assert sw <= 0.35 + 1e-6, f"{h.rebalance_date} sector {s} weight {sw} > cap"

    assert capped.equity_curve != uncapped.equity_curve     # the cap actually bound


def test_backtest_rejects_out_of_range_cap(sector_store: FactorDataStore) -> None:
    with pytest.raises(ValueError):
        run_momentum_backtest(sector_store, date(2018, 7, 1), date(2020, 12, 31),
                              max_sector_pct=0.0)
    with pytest.raises(ValueError):
        run_momentum_backtest(sector_store, date(2018, 7, 1), date(2020, 12, 31),
                              max_sector_pct=1.5)
