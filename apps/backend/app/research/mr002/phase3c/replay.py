"""The Phase 3C validation session replay.

This mirrors the accepted v1.1 development session loop
(`apps/backend/scripts/mr002_development_run.py::run_config`) and differs from it in exactly three
ways, each required by an owner ruling:

  1. ruling 1  -- the exit ladder is `exits.exit_reason_validation`, which has no `confirm`
                  parameter and no +/-3.5 sigma rung. The retired trigger is ABSENT, not merely
                  unreachable.
  2. ruling R6 -- a post-execution net-dollar drift breach records the frozen repair ordering and
                  then raises INTEGRITY_FAILURE, because the repair QUANTITY was never frozen.
                  Coupling-reduction semantics are NOT borrowed for this; they are a different
                  registered mechanism.
  3. bookkeeping only -- session dates are retained alongside the return series so folds can be
                  assigned, and the sealed OOS boundary is asserted as fatal.

Everything else is deliberately identical, and the identity is enforced rather than asserted:
the sizing helpers, position record, accumulator and cost primitives are IMPORTED from the adopted
runner through `adopted.load()`, which re-hashes the frozen bytes first. The differential
qualification test then proves the whole loop still agrees with the accepted runner on a
non-sealed development window where coupling reductions actually occur.

Coupling reductions follow the ADOPTED mechanics verbatim (owner ruling R5A): the joint
construction determines retention y, the reduction executes at the governed session's exec_open,
reduced notional pays the 10 bps/side cost, P&L is realized against `last_mark`, retained shares
continue as the same position, and a residual that rounds to zero is removed and recorded as
`reduce_to_zero_coupling`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.research.mr002.execution import (
    borrow_accrual,
    economic_gap,
    execution_cost,
    gap_filter_passes,
)
from app.research.mr002.joint_portfolio import (
    DRIFT_BAND,
    PRIMAL_RESIDUAL_MAX,
    Holding,
    NewCandidate,
    build_joint,
)
from app.research.mr002.runner import _candidates

from . import (
    DRIFT_REPAIR_QUANTITY_UNDEFINED,
    OOS_BOUNDARY_VIOLATION,
    OUT_OF_BOUNDS_AFTER,
    IntegrityFailure,
)
from .adopted import load as _load_adopted
from .exits import exit_reason_validation

_adopted = _load_adopted()

# Imported, never re-typed -- see the module docstring.
Acc = _adopted.Acc
Position = _adopted.Position
Trade = _adopted.Trade
_weights = _adopted._weights
_candidate_weights = _adopted._candidate_weights
NAV0 = _adopted.NAV0
COST_BPS = _adopted.COST_BPS
BORROW_BPS = _adopted.BORROW_BPS
TERMINAL_SESSION_NO_EXECUTION_OPEN = _adopted.TERMINAL_SESSION_NO_EXECUTION_OPEN
NO_MATCHED_INCREMENT = _adopted.NO_MATCHED_INCREMENT
NO_TRADABLE_HOLDINGS_NO_CANDIDATES = _adopted.NO_TRADABLE_HOLDINGS_NO_CANDIDATES
VALID_ZERO_ENTRY_OUTCOME = _adopted.VALID_ZERO_ENTRY_OUTCOME
FEASIBLE = _adopted.FEASIBLE
EXECUTION_CONSTRAINED_INFEASIBLE = _adopted.EXECUTION_CONSTRAINED_INFEASIBLE


def _f64_hex(x: float) -> str:
    return _adopted._f64_hex(x)


@dataclass
class ValidationAcc:
    """The adopted accumulator plus only what fold assignment and disclosure require."""

    acc: object
    sessions: list = field(default_factory=list)          # one date per appended return
    drift_instruction: dict | None = None
    # One entry per session that reached a construction with a non-empty book. This is the
    # evidence for R6A: which outcomes carry a post-execution band breach, and which of those
    # the drift rule may fire on.
    band_observations: list = field(default_factory=list)


def _drift_repair_instruction(positions, prices, nav: float, session: date) -> dict:
    """Record the frozen repair ordering. Recording is permitted; executing is not (ruling R6)."""
    longs = [p for p in positions if p.side > 0]
    shorts = [p for p in positions if p.side < 0]
    long_d = sum(abs(p.shares) * prices.get(p.permaticker, p.last_mark) for p in longs)
    short_d = sum(abs(p.shares) * prices.get(p.permaticker, p.last_mark) for p in shorts)
    larger = "long" if long_d >= short_d else "short"
    victims = longs if larger == "long" else shorts
    # frozen ordering: smallest |entry z| -> oldest position -> permanent identifier
    ordered = sorted(victims, key=lambda p: (abs(p.entry_z), p.entry_session_idx, p.permaticker))
    return {
        "session": str(session),
        "band": DRIFT_BAND,
        "larger_side": larger,
        "long_notional": long_d,
        "short_notional": short_d,
        "reduction_order": "smallest |entry z| -> oldest position -> permanent_security_id",
        "ordered_candidates": [
            {"permaticker": p.permaticker, "side": p.side, "entry_z": float(p.entry_z),
             "entry_session_idx": p.entry_session_idx}
            for p in ordered
        ],
        "quantity": None,
        "quantity_status": "UNDEFINED_IN_FROZEN_MATERIAL",
        "executed": False,
    }


def run_config_validation(days, cfg, *, assert_oos_boundary: bool = True) -> ValidationAcc:
    """Replay one configuration over `days`. Returns the adopted accumulator plus session dates.

    Raises IntegrityFailure on a sealed-OOS boundary breach or a triggered drift repair, and
    propagates joint_portfolio.InvalidRun unchanged -- a solver failure is never converted into a
    no-trade day.
    """
    va = ValidationAcc(acc=Acc())
    a = va.acc
    cash = NAV0
    positions: list = []
    entry_w: dict[int, float] = {}
    prev: date | None = None

    for idx, inp in enumerate(days):
        # Amendment C: the interlock is UNCHANGED and still fatal. Only the governed boundary it
        # guards has moved. It is now expressed against the Validation-2 window END, which needs no
        # future calendar: any session beyond the partition is out of bounds, whether unallocated
        # or new OOS. ⛔ assert_oos_boundary=False remains PROHIBITED for Validation-2.
        if assert_oos_boundary and inp.session > OUT_OF_BOUNDS_AFTER:
            raise IntegrityFailure(
                OOS_BOUNDARY_VIOLATION,
                f"session {inp.session} is beyond the Validation-2 window end "
                f"{OUT_OF_BOUNDS_AFTER}; sessions past it are unallocated or sealed new OOS",
            )

        nav_open = a.nav
        realized = costs = borrow = 0.0
        n_exits = n_orders = n_red = 0

        if prev is not None and positions:
            smv = sum(abs(p.shares) * inp.exec_close_t.get(p.permaticker, p.last_mark)
                      for p in positions if p.side < 0)
            borrow = borrow_accrual(smv, (inp.session - prev).days, BORROW_BPS)

        outcome = TERMINAL_SESSION_NO_EXECUTION_OPEN
        diag: dict = {}
        n_cands = 0
        res = None

        if inp.next_open_session is not None:
            # ---- 1) HARD EXITS FIRST (before inclusion-floor classification) --------------
            exited: set[int] = set()
            for p in list(positions):
                held = idx - p.entry_session_idx + 1
                reason = exit_reason_validation(          # ruling 1: no `confirm`, no +/-3.5 rung
                    inp.z.get(p.permaticker, np.nan), held,
                    p.permaticker in inp.blackout_exit,
                    p.permaticker in inp.action_exit)
                if reason is None:
                    continue
                a.hard_exits_due += 1
                px = inp.exec_open.get(p.permaticker)
                if px is None or px <= 0:
                    a.hard_exits_pending_missing_open += 1
                    continue                                     # exit stays PENDING
                a.hard_exits_executed += 1
                notional = abs(p.shares) * px
                c = execution_cost(notional, COST_BPS)
                realized += (px - p.last_mark) * p.shares
                costs += c
                cash += (px - p.last_mark) * p.shares - c
                a.traded_notional += notional
                gross_pnl = (px - p.entry_price) * p.shares
                a.trades.append(Trade(p.permaticker, p.side, str(p.entry_date),
                                      str(inp.next_open_session), reason,
                                      gross_pnl, c, gross_pnl - c))
                a.exit_reasons[reason] += 1
                positions.remove(p)
                entry_w.pop(p.permaticker, None)
                exited.add(p.permaticker)
                n_exits += 1

            # ---- 2) JOINT CONSTRUCTION (v1.1-rev-3, GOVERNING) -----------------------------
            prices = {p.permaticker: inp.exec_open.get(p.permaticker, p.last_mark)
                      for p in positions}
            wmap = _weights(positions, prices, a.nav)
            holdings = [
                Holding(p.permaticker, p.side, wmap[p.permaticker][0], p.sector_etf,
                        p.beta, entry_w.get(p.permaticker, 0.0),
                        (inp.exec_open.get(p.permaticker) or 0) > 0)
                for p in positions
            ]
            raw = [c for c in _candidates(inp, cfg) if c.permaticker not in exited]
            passed = [c for c in raw if gap_filter_passes(economic_gap(
                inp.open_next.get(c.permaticker, np.nan),
                inp.close_t.get(c.permaticker, np.nan),
                inp.cash_dist_next.get(c.permaticker, 0.0)))]
            n_cands = len(passed)
            cw = _candidate_weights(passed, positions, a.nav)
            cands = [NewCandidate(c.permaticker, c.side, cw[c.permaticker][0],
                                  c.sector_etf, c.beta)
                     for c in passed if c.permaticker in cw]

            res = build_joint(holdings, cands)            # InvalidRun propagates -> STOPS
            outcome = res.outcome
            diag = res.diagnostics
            if (diag.get("zero_entry_reason") == NO_TRADABLE_HOLDINGS_NO_CANDIDATES
                    and n_cands > 0):
                diag["zero_entry_reason"] = NO_MATCHED_INCREMENT

            # ---- 3) apply: coupling reductions, then new entries ---------------------------
            #      ADOPTED v1.1 mechanics, owner ruling R5A. Do not improve or reinterpret.
            for p in list(positions):
                y = res.y.get(p.permaticker)
                if y is None:
                    continue
                c_w = wmap[p.permaticker][0]
                if y >= c_w - 1e-12:
                    continue
                px = prices[p.permaticker]
                cut_notional = (c_w - y) * a.nav
                cut_shares = cut_notional / px * p.side
                c = execution_cost(cut_notional, COST_BPS)
                realized += (px - p.last_mark) * cut_shares
                costs += c
                cash += (px - p.last_mark) * cut_shares - c
                a.traded_notional += cut_notional
                gross_pnl = (px - p.entry_price) * cut_shares
                p.shares -= cut_shares
                n_red += 1
                if abs(p.shares) * px / a.nav <= 1e-12:
                    a.trades.append(Trade(p.permaticker, p.side, str(p.entry_date),
                                          str(inp.next_open_session),
                                          "reduce_to_zero_coupling",
                                          gross_pnl, c, gross_pnl - c))
                    a.exit_reasons["reduce_to_zero_coupling"] += 1
                    positions.remove(p)
                    entry_w.pop(p.permaticker, None)

            by = {c.permaticker: c for c in passed}
            for pt, x in sorted(res.x.items()):
                if x <= 1e-12:
                    continue
                c0 = by[pt]
                px = cw[pt][1]
                if cw[pt][2]:
                    a.adv_clipped += 1
                notional = x * a.nav
                c = execution_cost(notional, COST_BPS)
                costs += c
                cash -= c
                a.traded_notional += notional
                positions.append(Position(
                    pt, c0.ticker, c0.side, notional / px * c0.side, px,
                    inp.next_open_session, c0.z, c0.sector_etf, c0.beta,
                    c0.sigma_resid, idx, last_mark=px))
                entry_w[pt] = x
                n_orders += 1
                if c0.side > 0:
                    a.entries_long += 1
                else:
                    a.entries_short += 1

            # ---- ruling R6A: post-execution net-dollar drift, scoped to APPLIED construction --
            # R6A supersedes the unscoped R6 trigger. The drift-repair rule can only sensibly
            # apply once a feasible construction has been APPLIED. When the constructor returns
            # EXECUTION_CONSTRAINED_INFEASIBLE it applies nothing (y == {} and x == {}), which is
            # a REGISTERED no-trade outcome of the accepted v1.1 semantics -- 1,032 of Config B's
            # 1,700 accepted development sessions were exactly this. Treating it as an integrity
            # failure would retrospectively reject the same development behaviour that established
            # the joint construction as governing.
            #
            # Where R6A DOES apply, the original R6 ruling stands unchanged: record the frozen
            # ordering and stop, because the repair QUANTITY is still undefined. This is a
            # scoping correction, not a retirement and not an economic change.
            #
            # The comparison uses the solver's OWN primal feasibility tolerance, in the same
            # homogeneous weight units the constraint row is written in (`|net| - 0.05*G <= 0`).
            # An exact ratio test fires spuriously when the solver has legitimately brought the
            # book to the boundary, which would halt a perfectly valid replay.
            r6a_applies = outcome != EXECUTION_CONSTRAINED_INFEASIBLE
            if positions:
                gross = sum(abs(p.shares) * prices.get(p.permaticker, p.last_mark)
                            for p in positions)
                net = sum(p.shares * prices.get(p.permaticker, p.last_mark) for p in positions)
                residual = (abs(net) - DRIFT_BAND * gross) / a.nav if a.nav > 0 else 0.0
                breached = gross > 0 and residual > PRIMAL_RESIDUAL_MAX
                va.band_observations.append({
                    "session": str(inp.session),
                    "outcome": outcome,
                    "r6a_applies": r6a_applies,
                    "net_over_gross": (abs(net) / gross) if gross > 0 else 0.0,
                    "residual": residual,
                    "breached": breached,
                })
                if breached and r6a_applies:
                    va.drift_instruction = _drift_repair_instruction(
                        positions, prices, a.nav, inp.session)
                    raise IntegrityFailure(
                        DRIFT_REPAIR_QUANTITY_UNDEFINED,
                        f"session {inp.session}: |net|/gross = {abs(net) / gross:.9f} exceeds the "
                        f"{DRIFT_BAND} band by residual {residual:.3e} (> the frozen primal "
                        f"tolerance {PRIMAL_RESIDUAL_MAX:.0e}). The frozen repair ordering is "
                        "recorded; the repair quantity is undefined in the frozen material, so "
                        "the replay cannot continue admissibly.",
                    )

        # ---- mark to market ----------------------------------------------------------------
        unreal = 0.0
        for p in positions:
            px = inp.exec_close_next.get(
                p.permaticker, inp.exec_close_t.get(p.permaticker, p.last_mark))
            unreal += (px - p.last_mark) * p.shares
            p.last_mark = px
        net_pnl = realized + unreal - costs - borrow
        a.nav = nav_open + net_pnl
        a.daily_ret.append(net_pnl / nav_open if nav_open > 0 else 0.0)
        a.nav_curve.append(a.nav)
        va.sessions.append(inp.session)
        a.costs += costs
        a.borrow += borrow
        a.exits += n_exits
        a.reductions += n_red
        prev = inp.session

        # ---- registered session state + canonical determinism hash --------------------------
        a.outcomes[outcome] += 1
        if outcome == VALID_ZERO_ENTRY_OUTCOME:
            a.zero_reasons[diag.get("zero_entry_reason", "UNCLASSIFIED")] += 1
        if diag.get("determinism_hash"):
            a.per_solve_hashes += 1
        if diag.get("total_gross", 0.0) > 1e-6:
            a.gross.append(diag["total_gross"])
        if diag.get("existing_position_over_entry_cap"):
            a.over_cap_days += 1

        h = hashlib.sha256()
        h.update(f"{inp.session}|{outcome}|{diag.get('zero_entry_reason') or ''}".encode())
        for tag, bk in (("y", getattr(res, "y", {}) if inp.next_open_session else {}),
                        ("x", getattr(res, "x", {}) if inp.next_open_session else {})):
            for p_ in sorted(bk):
                h.update(f"|{tag}:{p_}:{_f64_hex(bk[p_])}".encode())
        h.update(f"|exits:{n_exits}|red:{n_red}|ord:{n_orders}".encode())
        a.session_hashes.append(h.hexdigest())

    return va
