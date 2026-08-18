"""Phase 3C qualification — coupling reductions, R6, determinism, and the differential check.

Every test here needs the FROZEN research image, because `joint_portfolio` refuses to run without
/manifest/pip_report.json pinning quadprog to the registered artifact. That refusal is a control,
so these tests skip rather than weaken it:

    docker run --rm --network=none -e PYTHONPATH=/work/apps/backend \\
        -v "<repo>:/work" -w /work/apps/backend \\
        mr002-research:v1.4 python -m pytest tests/research/phase3c --noconftest -q

All fixtures are synthetic. Nothing reads the validation or OOS partitions.

The book is deliberately six sectors wide with a matched long/short pair in each: a narrower book
cannot clear the 20%-of-gross sector cap, and the joint construction correctly refuses to deploy
into one. Entries are driven by making exactly six names per side extreme in a 60-name eligible
pool, so the frozen decile rule (k = 10% of the side pool) selects precisely those six.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from app.research.mr002.execution import COST_BPS_PER_SIDE, execution_cost
from app.research.mr002.phase3c import DRIFT_REPAIR_QUANTITY_UNDEFINED, NAV0, IntegrityFailure
from app.research.mr002.runner import CONFIGS, DayInputs

FROZEN_RUNTIME = os.path.exists("/manifest/pip_report.json")
pytestmark = pytest.mark.skipif(
    not FROZEN_RUNTIME,
    reason="joint_portfolio requires the frozen research image (/manifest/pip_report.json)",
)

N_SECTORS = 6
POOL = 60
SECTORS = [f"S{i}" for i in range(N_SECTORS)]
LONG_IDS = list(range(1, POOL + 1))
SHORT_IDS = list(range(1001, 1001 + POOL))
ENTRY_LONGS = LONG_IDS[:N_SECTORS]
ENTRY_SHORTS = SHORT_IDS[:N_SECTORS]
ALL = LONG_IDS + SHORT_IDS
PRICE = 100.0
ENTRY_NOTIONAL = 150_000.0        # 1.5% of a 10,000,000 NAV


def _sector_of(pt: int) -> str:
    return SECTORS[(pt % 1000) % N_SECTORS] if pt >= 1001 else SECTORS[pt % N_SECTORS]


def _sessions(n: int, start: date = date(2020, 1, 13)) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _day(s, nxt, px, zs, el=(), es=()) -> DayInputs:
    return DayInputs(
        session=s, next_open_session=nxt,
        z={p: float(zs.get(p, 0.0)) for p in ALL},
        sigma_resid={p: 0.02 for p in ALL},
        beta={p: 1.0 for p in ALL},
        sector={p: _sector_of(p) for p in ALL},
        long_eligible=set(el), short_eligible=set(es),
        open_next=dict(px), close_t=dict(px), close_next=dict(px),
        cash_dist_next={p: 0.0 for p in ALL},
        adv_dollar={p: 1e9 for p in ALL},
        tickers={p: f"T{p}" for p in ALL},
        blackout_exit=set(), action_exit=set(), confirm={},
        exec_open=dict(px), exec_close_next=dict(px), exec_close_t=dict(px),
    )


def build(long_move: float = 0.0, short_move: float = 0.0,
          revert_shorts: bool = False, n_after: int = 4) -> list[DayInputs]:
    """Session 0 enters a matched six-by-six book; later sessions move prices and/or revert z."""
    ss = _sessions(1 + n_after)
    flat = {p: PRICE for p in ALL}
    z0 = {p: -3.0 for p in ENTRY_LONGS}
    z0.update({p: 3.0 for p in ENTRY_SHORTS})
    days = [_day(ss[0], ss[1], flat, z0, el=LONG_IDS, es=SHORT_IDS)]
    for i in range(1, len(ss)):
        nxt = ss[i + 1] if i + 1 < len(ss) else None
        px = dict(flat)
        for p in ENTRY_LONGS:
            px[p] = PRICE * (1 + long_move)
        for p in ENTRY_SHORTS:
            px[p] = PRICE * (1 + short_move)
        zs = {p: -3.0 for p in ENTRY_LONGS}
        zs.update({p: (0.0 if revert_shorts else 3.0) for p in ENTRY_SHORTS})
        days.append(_day(ss[i], nxt, px, zs))
    return days


def _run(days, cfg_name: str = "B"):
    from app.research.mr002.phase3c.replay import run_config_validation

    return run_config_validation(days, CONFIGS[cfg_name], assert_oos_boundary=False)


# ----------------------------------------------------------------- full retention (y == c)

def test_full_retention_leaves_positions_untouched():
    """A balanced book inside every constraint must produce no reduction at all."""
    a = _run(build()).acc
    assert (a.entries_long, a.entries_short) == (N_SECTORS, N_SECTORS)
    assert a.reductions == 0
    assert "reduce_to_zero_coupling" not in a.exit_reasons
    # 12 entries x 150,000 notional x 10 bps
    assert a.costs == pytest.approx(execution_cost(12 * ENTRY_NOTIONAL, COST_BPS_PER_SIDE))


# ----------------------------------------------------------------- partial retention (0 < y < c)

@pytest.mark.parametrize("move", [0.20, 0.80])
def test_partial_coupling_reduction_trims_without_closing(move):
    """An imbalance must trim the larger side and leave every position OPEN."""
    a = _run(build(long_move=move)).acc
    assert a.reductions >= 1, "expected at least one partial coupling reduction"
    assert a.exit_reasons.get("reduce_to_zero_coupling", 0) == 0, "a trim is not an exit"
    assert a.exits == 0


def test_reduction_charges_commission_on_the_reduced_notional():
    """Cost accounting through a trim is 10 bps on exactly the reduced notional, no more."""
    flat = _run(build()).acc
    trimmed = _run(build(long_move=0.20)).acc
    assert trimmed.reductions >= 1
    extra_notional = trimmed.traded_notional - flat.traded_notional
    extra_costs = trimmed.costs - flat.costs
    assert extra_notional > 0
    assert extra_costs == pytest.approx(
        execution_cost(extra_notional, COST_BPS_PER_SIDE), rel=1e-9)


def test_retained_quantity_is_the_untrimmed_remainder():
    """A larger imbalance must trim strictly more notional than a smaller one."""
    small = _run(build(long_move=0.20)).acc
    large = _run(build(long_move=0.80)).acc
    assert large.traded_notional > small.traded_notional
    assert large.costs > small.costs


def test_nav_reconciles_through_the_trim():
    """NAV must roll forward exactly by the recorded daily returns, trims included."""
    a = _run(build(long_move=0.20)).acc
    nav = NAV0
    for r in a.daily_ret:
        nav *= 1.0 + r
    assert nav == pytest.approx(a.nav_curve[-1], rel=1e-9)


# ----------------------------------------------------------------- full coupling liquidation

def test_reduce_to_zero_coupling_is_recorded_as_an_exit():
    """With the shorts gone, an all-long book cannot satisfy dollar neutrality at any positive
    size, so coupling must close it out and record the registered reason."""
    a = _run(build(revert_shorts=True)).acc
    assert a.exit_reasons.get("exit_z_reverted", 0) == N_SECTORS
    assert a.exit_reasons.get("reduce_to_zero_coupling", 0) == N_SECTORS
    assert a.reductions >= N_SECTORS


# ----------------------------------------------------------------- borrow follows remaining shares

def test_short_borrow_basis_follows_the_remaining_shares():
    """Borrow accrues on short market value, so a trimmed short book must accrue strictly less
    than the same book would have accrued untrimmed at identical prices."""
    trimmed = _run(build(short_move=0.35)).acc
    assert trimmed.reductions >= 1

    shares_per_short = ENTRY_NOTIONAL / PRICE
    untrimmed_smv = N_SECTORS * shares_per_short * PRICE * 1.35
    # four one-calendar-day accruals across the consecutive weekday fixture
    untrimmed_borrow = untrimmed_smv * (50.0 / 10_000.0) * (4 / 360.0)

    assert 0.0 < trimmed.borrow < untrimmed_borrow

    # closing the shorts early must reduce it further still
    closed = _run(build(revert_shorts=True)).acc
    assert closed.borrow < trimmed.borrow


# ----------------------------------------------------------------- determinism

@pytest.mark.parametrize("kw", [{}, {"long_move": 0.20}, {"revert_shorts": True}])
def test_replay_is_deterministic(kw):
    a = _run(build(**kw)).acc
    b = _run(build(**kw)).acc
    assert a.session_hashes == b.session_hashes
    assert a.nav_curve == b.nav_curve
    assert a.daily_ret == b.daily_ret


# ----------------------------------------------------------------- ruling R6

def _force_full_retention(monkeypatch):
    """Simulate a book that leaves the band breached after execution."""
    from app.research.mr002.phase3c import replay as r

    real = r.build_joint

    def _patched(holdings, candidates):
        res = real(holdings, candidates)
        res.y = {h.permaticker: h.c for h in holdings}
        return res

    monkeypatch.setattr(r, "build_joint", _patched)


def test_synthetic_post_execution_drift_is_an_integrity_failure(monkeypatch):
    """P3 (non-vacuity): after an APPLIED FEASIBLE construction, surviving drift must STOP the
    replay. R6A narrows the domain; it must not have hollowed out the control."""
    _force_full_retention(monkeypatch)
    with pytest.raises(IntegrityFailure) as exc:
        _run(build(long_move=0.20))
    assert exc.value.code == DRIFT_REPAIR_QUANTITY_UNDEFINED


def _force_execution_constrained_infeasible(monkeypatch):
    """Make the constructor decline to trade, applying nothing -- the registered no-trade state."""
    from app.research.mr002.joint_portfolio import (
        EXECUTION_CONSTRAINED_INFEASIBLE,
        JointResult,
    )
    from app.research.mr002.phase3c import replay as r

    real = r.build_joint

    def _patched(holdings, candidates):
        if holdings:                       # decline once a book exists
            return JointResult(outcome=EXECUTION_CONSTRAINED_INFEASIBLE, y={}, x={},
                               diagnostics={})
        return real(holdings, candidates)

    monkeypatch.setattr(r, "build_joint", _patched)


def test_execution_constrained_infeasible_never_triggers_r6a(monkeypatch):
    """R6A: a registered no-trade outcome must NOT be reclassified as an integrity failure, even
    when the untouched book sits far outside the neutrality band."""
    _force_execution_constrained_infeasible(monkeypatch)
    va = _run(build(long_move=0.80))       # replay completes; no IntegrityFailure

    from app.research.mr002.joint_portfolio import EXECUTION_CONSTRAINED_INFEASIBLE

    eci = [o for o in va.band_observations if o["outcome"] == EXECUTION_CONSTRAINED_INFEASIBLE]
    assert eci, "the fixture must actually produce EXECUTION_CONSTRAINED_INFEASIBLE sessions"
    assert any(o["breached"] for o in eci), "and at least one of them must be out of band"
    assert all(o["r6a_applies"] is False for o in eci)
    assert va.acc.reductions == 0, "an infeasible construction applies nothing"


def test_band_observations_record_every_constructed_session():
    """The R6A evidence trail must exist even when nothing breaches."""
    va = _run(build())
    assert va.band_observations
    assert all(o["r6a_applies"] is True for o in va.band_observations)
    assert not any(o["breached"] for o in va.band_observations)


def test_drift_check_does_not_fire_at_the_band_boundary():
    """The solver legitimately lands ON the band. An exact ratio test would halt a valid replay,
    so the check must use the solver's own primal tolerance."""
    a = _run(build(long_move=0.20)).acc     # would raise if the tolerance were wrong
    assert a.reductions >= 1


def test_drift_instruction_records_ordering_but_never_a_quantity():
    from app.research.mr002.phase3c.replay import Position, _drift_repair_instruction

    positions = [
        Position(1, "T1", 1, 1500.0, PRICE, date(2020, 1, 13), -3.0, "S1", 1.0, 0.02, 0, PRICE),
        Position(2, "T2", 1, 1500.0, PRICE, date(2020, 1, 13), -9.0, "S2", 1.0, 0.02, 1, PRICE),
        Position(1001, "T1001", -1, 100.0, PRICE, date(2020, 1, 13), 3.0, "S1", 1.0, 0.02, 0, PRICE),
    ]
    instr = _drift_repair_instruction(positions, {1: PRICE, 2: PRICE, 1001: PRICE},
                                      NAV0, date(2020, 1, 14))
    assert instr["executed"] is False
    assert instr["quantity"] is None
    assert instr["quantity_status"] == "UNDEFINED_IN_FROZEN_MATERIAL"
    assert instr["larger_side"] == "long"
    # frozen ordering: smallest |entry z| first
    assert [c["permaticker"] for c in instr["ordered_candidates"]] == [1, 2]


# ----------------------------------------------------------------- THE DIFFERENTIAL CHECK

@pytest.mark.parametrize("kw", [
    {},                          # no trimming
    {"long_move": 0.20},         # partial trim
    {"long_move": 0.80},         # larger partial trim
    {"short_move": 0.35},        # trim on the short side
    {"revert_shorts": True},     # full coupling liquidation
])
def test_phase3c_agrees_with_the_accepted_development_runner(kw):
    """The thin adapter must not have moved the already-exercised economics.

    Identical synthetic inputs through the accepted `run_config` and through Phase 3C. The only
    permitted behavioural difference is the retired +/-3.5 sigma rung, which is unreachable here
    because `confirm` is empty -- exactly as the real dataset builds it. So the two must agree
    EXACTLY on reductions, costs, borrow, NAV and per-session determinism hashes.
    """
    from app.research.mr002.phase3c import adopted

    dev = adopted.load()
    days = build(**kw)

    dev_acc = dev.run_config(days, CONFIGS["B"])
    p3c = _run(days).acc

    assert p3c.reductions == dev_acc.reductions
    assert p3c.entries_long == dev_acc.entries_long
    assert p3c.entries_short == dev_acc.entries_short
    assert p3c.exits == dev_acc.exits
    assert dict(p3c.exit_reasons) == dict(dev_acc.exit_reasons)
    assert p3c.traded_notional == dev_acc.traded_notional
    assert p3c.costs == dev_acc.costs
    assert p3c.borrow == dev_acc.borrow
    assert p3c.nav_curve == dev_acc.nav_curve
    assert p3c.daily_ret == dev_acc.daily_ret
    assert p3c.session_hashes == dev_acc.session_hashes
    assert [t.reason for t in p3c.trades] == [t.reason for t in dev_acc.trades]
    assert [t.net_pnl for t in p3c.trades] == [t.net_pnl for t in dev_acc.trades]
