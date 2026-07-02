"""Tests for the range self-healing classifier (ADR 0035) — pure classify() logic."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

# Load scripts/range_healthcheck.py by path (scripts/ is not a package). Register in
# sys.modules BEFORE exec so its @dataclass definitions can resolve their module dict.
_MOD_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "range_healthcheck.py"
)
_spec = importlib.util.spec_from_file_location("range_healthcheck", _MOD_PATH)
assert _spec and _spec.loader
rhc = importlib.util.module_from_spec(_spec)
sys.modules["range_healthcheck"] = rhc
_spec.loader.exec_module(rhc)


def _healthy(phase: str):
    return rhc.Health(
        phase=phase, strategy_id=1, strategy_name="Range", registered=True,
        universe=["AAPL", "MSFT"], levels_ok=["AAPL", "MSFT"],
    )


def test_green_when_all_levels_published_and_registered() -> None:
    state, action = rhc.classify(_healthy("post_or"))
    assert state == "GREEN"
    assert action == "none"


def test_missing_levels_post_open_is_orange() -> None:
    h = _healthy("post_or")
    h.levels_ok = ["AAPL"]
    h.levels_missing = ["MSFT"]
    h.findings.append(rhc.Finding(3, "levels_missing", "MSFT missing"))
    state, action = rhc.classify(h)
    assert state == "ORANGE"


def test_no_valid_levels_post_open_is_red() -> None:
    h = _healthy("post_or")
    h.levels_ok = []
    h.levels_missing = ["AAPL", "MSFT"]
    h.findings.append(rhc.Finding(3, "levels_missing", "all missing"))
    state, _ = rhc.classify(h)
    assert state == "RED"  # price-setting fully failed → subsystem can't trade


def test_halt_is_red_and_never_auto_cleared() -> None:
    h = _healthy("intraday")
    h.halted = True
    h.findings.append(rhc.Finding(4, "global_halt", "halt set"))
    state, action = rhc.classify(h)
    assert state == "RED"
    assert action == "none"  # Level-4: never an automatic correction


def test_preopen_not_registered_triggers_rearm_yellow() -> None:
    h = rhc.Health(phase="pre_open", strategy_id=1, strategy_name="Range", registered=False)
    state, action = rhc.classify(h)
    assert action == "rearm"   # the one safe Level-1 operational correction
    assert state == "YELLOW"   # will recover automatically
