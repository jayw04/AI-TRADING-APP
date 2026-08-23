"""Why-it-left uses the same frozen admission gates as the live screen."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.research.disc001 import why_left as why_left_mod
from app.research.disc001.engine import (
    mom_near_eligible,
    mom_near_gate_observations,
    oversold_eligible,
    oversold_gate_observations,
)
from app.research.disc001.features import GapRow, MomCoreRow, SymbolFeatures
from app.research.disc001.spec import SCREEN_VERSION, FamilyId
from app.research.disc001.why_left import (
    NOT_A_SIGNAL,
    STATE_NO_LONGER_MEETS,
    STATE_STILL_MEETS,
    STATE_UNAVAILABLE,
    explain_gap,
    explain_mom_core,
    explain_oversold,
    explain_why_left,
    latest_session_after,
)


def _feat(**over: object) -> SymbolFeatures:
    base: dict[str, object] = dict(
        symbol="GOOD",
        name="Good Inc",
        sector="Technology",
        category="Domestic Common Stock",
        close=50.0,
        sma200=40.0,
        rsi14=24.0,
        rsi14_prev=28.0,
        ret_5d=-0.10,
        ret_20d=0.08,
        ret_60d=0.02,
        rs_20_vs_spy=0.04,
        rs_60_vs_spy=0.01,
        rs_accel=0.03,
        dist_52w=0.05,
        high_52w=52.6,
        adv20=30_000_000.0,
        rvol20=2.0,
        volume_rising_20d=True,
        market_cap=2_000_000_000.0,
    )
    base.update(over)
    return SymbolFeatures(**base)  # type: ignore[arg-type]


def test_oversold_eligible_is_the_gate_observation_conjunction():
    good = _feat()
    assert oversold_eligible(good) is True
    assert oversold_eligible(good) is all(o.passed for o in oversold_gate_observations(good))
    recovered = _feat(rsi14=34.2)
    assert oversold_eligible(recovered) is False
    assert oversold_eligible(recovered) is all(
        o.passed for o in oversold_gate_observations(recovered)
    )


def test_mom_near_eligible_is_the_gate_observation_conjunction():
    core = frozenset({"CORE"})
    good = _feat(symbol="NEW")
    assert mom_near_eligible(good, core) is all(
        o.passed for o in mom_near_gate_observations(good, core)
    )
    dropped = _feat(symbol="CORE")
    assert mom_near_eligible(dropped, core) is False
    assert mom_near_eligible(dropped, core) is all(
        o.passed for o in mom_near_gate_observations(dropped, core)
    )


def test_why_left_oversold_calls_engine_eligible(monkeypatch):
    called: list[SymbolFeatures] = []
    real = why_left_mod.oversold_eligible

    def wrapped(feat: SymbolFeatures) -> bool:
        called.append(feat)
        return real(feat)

    monkeypatch.setattr(why_left_mod, "oversold_eligible", wrapped)
    result = explain_oversold(_feat(rsi14=34.2), later_as_of=date(2026, 8, 21))
    assert called
    assert result.state == STATE_NO_LONGER_MEETS
    assert result.summary == "No longer OVERSOLD: RSI14 = 34.2."
    assert result.not_a_signal == NOT_A_SIGNAL
    assert "sell" not in (result.summary or "").lower()
    assert "exit" not in (result.summary or "").lower()


def test_why_left_still_meets_when_frozen_rule_holds():
    result = explain_oversold(_feat(), later_as_of=date(2026, 8, 21))
    assert result.state == STATE_STILL_MEETS
    assert result.summary is not None and result.summary.startswith("Still OVERSOLD")
    assert result.not_a_signal == NOT_A_SIGNAL


def test_why_left_unavailable_without_later_bar():
    result = explain_oversold(_feat(), later_as_of=None)
    assert result.state == STATE_UNAVAILABLE
    assert result.summary is None
    assert result.not_a_signal == NOT_A_SIGNAL


def test_why_left_gap_uses_screen_gap(monkeypatch):
    called: list[tuple] = []
    real = why_left_mod.screen_gap

    def wrapped(rows, **kwargs):
        called.append(rows)
        return real(rows, **kwargs)

    monkeypatch.setattr(why_left_mod, "screen_gap", wrapped)
    rows = (GapRow(rank=1, symbol="AAA", gap_pct=5.0),)
    still = explain_gap("AAA", later_as_of=date(2026, 8, 21), later_rows=rows, available=True)
    left = explain_gap("BBB", later_as_of=date(2026, 8, 21), later_rows=rows, available=True)
    assert called
    assert still.state == STATE_STILL_MEETS
    assert left.state == STATE_NO_LONGER_MEETS
    assert left.summary is not None and left.summary.startswith("No longer GAP")


def test_why_left_mom_core_uses_screen_mom_core(monkeypatch):
    called: list[tuple] = []
    real = why_left_mod.screen_mom_core

    def wrapped(rows, **kwargs):
        called.append(rows)
        return real(rows, **kwargs)

    monkeypatch.setattr(why_left_mod, "screen_mom_core", wrapped)
    rows = (MomCoreRow(rank=1, symbol="NVDA"),)
    still = explain_mom_core("NVDA", later_as_of=date(2026, 8, 21), later_rows=rows, available=True)
    left = explain_mom_core("AAA", later_as_of=date(2026, 8, 21), later_rows=rows, available=True)
    assert called
    assert still.state == STATE_STILL_MEETS
    assert left.state == STATE_NO_LONGER_MEETS


def test_explain_why_left_dispatch_and_unknown_family():
    later = date(2026, 8, 21)
    oversold = explain_why_left(
        family=str(FamilyId.OVERSOLD),
        symbol="GOOD",
        later_as_of=later,
        feat=_feat(rsi14=34.2),
    )
    assert oversold.summary == "No longer OVERSOLD: RSI14 = 34.2."
    unknown = explain_why_left(family="OTHER", symbol="X", later_as_of=later)
    assert unknown.state == STATE_UNAVAILABLE


def test_latest_session_after_is_strictly_later():
    sessions = [date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21)]
    assert latest_session_after(sessions, date(2026, 8, 19)) == date(2026, 8, 21)
    assert latest_session_after(sessions, date(2026, 8, 21)) is None


def test_why_left_does_not_redeclare_frozen_thresholds():
    text = Path(why_left_mod.__file__).read_text(encoding="utf-8")
    for name in (
        "RSI14_MAX",
        "RET_5D_MAX",
        "DIST_52W_MAX",
        "RVOL20_MIN",
        "MIN_PRICE",
        "MIN_ADV_20D",
        "MIN_MARKET_CAP",
        "RS_20_VS_SPY_MIN",
        "MOM_CORE_TOP_N",
        "MAX_PER_FAMILY",
    ):
        assert name not in text
    assert "30.0" not in text
    assert "-0.08" not in text
    assert "SCREEN_VERSION" not in text
    assert SCREEN_VERSION == "v0.3.0"


def test_why_left_stays_off_db_order_path_and_mdq():
    text = Path(why_left_mod.__file__).read_text(encoding="utf-8")
    assert "app.db" not in text
    assert "app.orders" not in text
    assert "app.risk" not in text
    assert "app.brokers" not in text
    assert "mdq_collector" not in text
    assert "from app.mdq" not in text
    assert "FactorDataStore" not in text
    assert "low_volatility" not in text
    assert "strategies_user" not in text
