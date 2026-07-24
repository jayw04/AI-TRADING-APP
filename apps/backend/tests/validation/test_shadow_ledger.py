"""Non-ordering shadow ledger — fidelity to the §7A-proven transition + durability (PREREG v1.0 §5.3).

The load-bearing test drives `ShadowLedger` forward over a session sequence and asserts it reproduces the
frozen `drift_audit_driver.capture_replica_seams` decision seams BYTE-FOR-BYTE — proving the ledger's
transition is the proven Stage-4 transition, not a fork. Plus: hand-computed equity/cost/MTM math, the
starting-capital guard (no retired 84466.41), durable save/reload, and a structural non-ordering check.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from app.strategies.drift_audit_driver import capture_replica_seams
from app.validation import shadow_ledger as sl_mod
from app.validation.first_session import Durability
from app.validation.shadow_ledger import ShadowLedger, ShadowLedgerError


class _Noop(Durability):
    """A durability adapter that no-ops both fsyncs (a 'passing' adapter for happy-path saves)."""

    def fsync_file(self, path):
        pass

    def fsync_dir(self, path):
        pass


class _FailFileFsync(_Noop):
    def fsync_file(self, path):
        raise RuntimeError("injected file fsync failure")


class _FailDirFsync(_Noop):
    def fsync_dir(self, path):
        raise RuntimeError("injected parent-dir fsync failure")


class _OrderSpy(_Noop):
    """Records the fsync call order and whether the destination held the NEW content at dir-fsync time."""

    def __init__(self, dest):
        self.dest = dest
        self.calls: list[str] = []
        self.dir_saw_new_content = False

    def fsync_file(self, path):
        self.calls.append("file")

    def fsync_dir(self, path):
        self.calls.append("dir")
        self.dir_saw_new_content = self.dest.exists() and "sessions_processed" in self.dest.read_text()


@dataclass
class _DS:
    """Duck-typed DayScores: ranked (best-first), score, rank."""
    ranked: list[str]
    score: dict[str, float]
    rank: dict[str, int]


def _scenario():
    """A deterministic multi-session scenario that exercises trade / no-trade / drift / rebalance."""
    days = [date(2020, 1, d) for d in range(2, 20)]           # 18 sessions
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    day_scores = {}
    for i, d in enumerate(days):
        order = tickers[i % len(tickers):] + tickers[:i % len(tickers)]   # rotate to induce changes
        day_scores[d] = _DS(ranked=list(order),
                            score={tk: float(len(order) - j) for j, tk in enumerate(order)},
                            rank={tk: j + 1 for j, tk in enumerate(order)})
    gross = {d: (1.0 if i % 5 else 0.6) for i, d in enumerate(days)}       # occasional regime flip
    return days, day_scores, gross


def _select(ds, held, prev_rank):
    return list(ds.ranked[:2])


def _weigh(target, day):
    return {tk: 1.0 / len(target) for tk in target} if target else {}


def _price(tk, day):
    base = {"AAA": 100.0, "BBB": 50.0, "CCC": 200.0, "DDD": 80.0}[tk]
    return base * (1.0 + 0.0007 * day.day)                    # deterministic per (tk, day)


# ---- fidelity: forward walk == frozen capture_replica_seams (byte-identical decisions) -----------

def test_forward_walk_reproduces_capture_replica_seams():
    days, day_scores, gross = _scenario()
    ref = capture_replica_seams(
        days, day_scores, gross, select_fn=_select, weigh_fn=_weigh, price_fn=_price,
        backstop_days=21, weight_drift_pct=0.02, turnover_cost_bps=10.0, initial_equity=100_000.0)

    ledger = ShadowLedger.start(starting_capital=100_000.0, turnover_cost_bps=10.0,
                                backstop_days=21, weight_drift_pct=0.02)
    got = [ledger.step(d, day_scores.get(d), gross.get(d, 1.0),
                       select_fn=_select, weigh_fn=_weigh, price_fn=_price).record for d in days]

    assert got == ref                                         # BYTE-IDENTICAL seams, day for day
    assert len(got) == len(days)


# ---- equity / turnover-cost / mark-to-market math (hand-computed) --------------------------------

def test_equity_cost_and_mtm_math_hand_computed():
    # controlled prices: day 2 = 1.0x base, day 3 = 1.10x base (a clean +10% MTM)
    px = {date(2020, 1, 2): {"AAA": 100.0, "BBB": 100.0},
          date(2020, 1, 3): {"AAA": 110.0, "BBB": 110.0}}

    def price(tk, d):
        return px[d][tk]

    ds = _DS(ranked=["AAA", "BBB"], score={"AAA": 2.0, "BBB": 1.0}, rank={"AAA": 1, "BBB": 2})
    led = ShadowLedger.start(starting_capital=100_000.0, turnover_cost_bps=10.0,
                             backstop_days=21, weight_drift_pct=0.02)

    # day 2: all-cash → 50/50 AAA/BBB. turnover = 0.5*(0.5+0.5 + |0-1|) = 1.0; cost = 10bps*1.0 = 0.001
    o1 = led.step(date(2020, 1, 2), ds, 1.0, select_fn=_select, weigh_fn=_weigh, price_fn=price)
    assert o1.traded is True
    assert o1.turnover == pytest.approx(1.0)
    assert led.state.equity == pytest.approx(99_900.0)        # 100000 * (1 - 0.001)
    assert o1.cost_drag == pytest.approx(100.0)

    # day 3: same target (no trade), both names +10% → equity = 99900 * 1.10 = 109890
    o2 = led.step(date(2020, 1, 3), ds, 1.0, select_fn=_select, weigh_fn=_weigh, price_fn=price)
    assert o2.traded is False                                 # unchanged target, within drift, since<backstop
    assert led.state.equity == pytest.approx(109_890.0)
    assert o2.session_return == pytest.approx(0.10)


# ---- starting-capital guard ---------------------------------------------------------------------

def test_rejects_retired_baseline():
    with pytest.raises(ShadowLedgerError, match="retired"):
        ShadowLedger.start(starting_capital=84466.41, turnover_cost_bps=10.0,
                           backstop_days=21, weight_drift_pct=0.02)


def test_rejects_nonpositive_capital():
    with pytest.raises(ShadowLedgerError):
        ShadowLedger.start(starting_capital=0.0, turnover_cost_bps=10.0,
                           backstop_days=21, weight_drift_pct=0.02)


def test_default_starting_capital_is_the_governed_100k():
    led = ShadowLedger.start(backstop_days=21, weight_drift_pct=0.02)
    assert led.state.starting_capital == 100_000.0 and led.state.equity == 100_000.0
    assert led.state.cash == 100_000.0 and led.state.held == []


# ---- durable save / reload ----------------------------------------------------------------------

def test_durable_save_reload_roundtrip(tmp_path):
    days, day_scores, gross = _scenario()
    led = ShadowLedger.start(starting_capital=100_000.0, turnover_cost_bps=10.0,
                             backstop_days=21, weight_drift_pct=0.02)
    for d in days[:9]:
        led.step(d, day_scores.get(d), gross.get(d, 1.0),
                 select_fn=_select, weigh_fn=_weigh, price_fn=_price)
    p = tmp_path / "ledger.json"
    led.save(p)
    reloaded = ShadowLedger.load(p)

    assert reloaded.state == led.state                        # full state preserved
    assert reloaded.turnover_cost_bps == led.turnover_cost_bps
    # and it continues identically to an unbroken run
    cont = ShadowLedger.start(starting_capital=100_000.0, turnover_cost_bps=10.0,
                              backstop_days=21, weight_drift_pct=0.02)
    for d in days:
        cont.step(d, day_scores.get(d), gross.get(d, 1.0),
                  select_fn=_select, weigh_fn=_weigh, price_fn=_price)
    for d in days[9:]:
        reloaded.step(d, day_scores.get(d), gross.get(d, 1.0),
                      select_fn=_select, weigh_fn=_weigh, price_fn=_price)
    assert reloaded.state.equity == pytest.approx(cont.state.equity)
    assert reloaded.state.held == cont.state.held


# ---- rename durability: fsync parent dir after replace; fail closed; never lose the real ledger ---

def _fresh():
    return ShadowLedger.start(starting_capital=100_000.0, turnover_cost_bps=10.0,
                              backstop_days=21, weight_drift_pct=0.02)


def test_file_fsync_failure_does_not_replace_the_existing_ledger(tmp_path):
    p = tmp_path / "ledger.json"
    _fresh().save(p, durability=_Noop())                     # an existing authoritative ledger
    before = p.read_text(encoding="utf-8")
    new = _fresh()
    new.step(date(2020, 1, 2), _DS(["AAA", "BBB"], {"AAA": 2.0, "BBB": 1.0}, {"AAA": 1, "BBB": 2}),
             1.0, select_fn=_select, weigh_fn=_weigh, price_fn=_price)      # different state
    with pytest.raises(RuntimeError, match="file fsync"):
        new.save(p, durability=_FailFileFsync())
    assert p.read_text(encoding="utf-8") == before           # existing ledger untouched
    assert not (tmp_path / "ledger.json.tmp").exists()       # temp cleaned up


def test_os_replace_failure_preserves_the_existing_ledger(tmp_path, monkeypatch):
    p = tmp_path / "ledger.json"
    _fresh().save(p, durability=_Noop())
    before = p.read_text(encoding="utf-8")
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError, match="boom"):
        _fresh().save(p, durability=_Noop())
    assert p.read_text(encoding="utf-8") == before           # existing ledger preserved
    assert not (tmp_path / "ledger.json.tmp").exists()       # temp cleaned up


def test_parent_dir_fsync_runs_after_replacement(tmp_path):
    p = tmp_path / "ledger.json"
    spy = _OrderSpy(p)
    _fresh().save(p, durability=spy)
    assert spy.calls == ["file", "dir"]                      # file fsync, THEN dir fsync
    assert spy.dir_saw_new_content is True                   # replace happened before the dir fsync


def test_parent_dir_fsync_failure_is_reported_as_failure(tmp_path):
    p = tmp_path / "ledger.json"
    with pytest.raises(RuntimeError, match="parent-dir fsync"):
        _fresh().save(p, durability=_FailDirFsync())         # NOT silently swallowed


# ---- non-ordering (structural): the shadow ledger never IMPORTS the order path -------------------

def test_shadow_ledger_imports_no_order_path():
    """Structural guard: the module must not import the order router / broker / execution path. Checks
    IMPORTS via AST (not prose — the docstring legitimately explains the ledger is *non*-ordering)."""
    import ast

    tree = ast.parse(Path(sl_mod.__file__).read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    forbidden = ("order_router", "broker", "alpaca", "services.order")
    hits = [m for m in modules if any(f in m for f in forbidden)]
    assert not hits, f"shadow ledger must be non-ordering; forbidden imports: {hits}"
