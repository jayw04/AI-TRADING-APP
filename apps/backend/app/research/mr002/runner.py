"""MR-002 harness runner — FROZEN v1.0 (immutable spec; window-bounded).

Daily loop, strictly PIT:

  at the CLOSE of session t:
      * compute signals from data through t ONLY (betas t-60..t-1; z normalized
        on windows ending t-1);
      * decide exits and entries for execution at the t+1 OPEN;
  at the t+1 OPEN:
      * exits execute first, then entries (no same-open re-entry);
      * the economic-gap filter cancels entries at the open;
      * fills at the official open; costs on traded notional; borrow accrues per
        calendar day on short market value; positions are marked at the close.

The runner NEVER reads outside its configured window. The development runner is
bounded to 2013-01-02..2019-10-02 (1,700 sessions). Validation and sealed-OOS
windows are NOT read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from app.research.mr002.execution import (
    DailyRecord,
    Fill,
    Ledger,
    borrow_accrual,
    economic_gap,
    execution_cost,
    exit_reason,
    gap_filter_passes,
)
from app.research.mr002.portfolio import (
    Candidate,
    Position,
    build_orders,
    drift_reductions,
)

TOP_DECILE = 0.10          # bottom/top 10% of the side-eligible z pool
ADV_PARTICIPATION = 0.02   # 2% of trailing 20-session median dollar volume


@dataclass
class Config:
    """The three frozen configurations. B is the ONLY verdict configuration."""

    name: str
    z_entry: float


CONFIGS = {"A": Config("A", 1.75), "B": Config("B", 2.00), "C": Config("C", 2.25)}


@dataclass
class DayInputs:
    """Everything the loop may see for one decision session (PIT by construction)."""

    session: date
    next_open_session: date | None
    z: dict[int, float]                  # permaticker -> z at close t
    sigma_resid: dict[int, float]
    beta: dict[int, float]
    sector: dict[int, str]
    long_eligible: set[int]              # PIT universe + all gates passed
    short_eligible: set[int]
    open_next: dict[int, float]          # official open at t+1 (execution price)
    close_t: dict[int, float]            # split-adjusted close at t (gap basis)
    close_next: dict[int, float]         # close at t+1 (mark-to-market)
    cash_dist_next: dict[int, float]     # known cash distribution at t+1
    adv_dollar: dict[int, float]
    tickers: dict[int, str]
    blackout_exit: set[int]              # positions the blackout forces out
    action_exit: set[int]                # announced corporate action
    confirm: dict[int, bool]             # market/sector confirmation for the ±3.5 stop


def _candidates(inp: DayInputs, cfg: Config) -> list[Candidate]:
    """Frozen §4 entry rules: |z| >= z_entry AND in the extreme decile of the
    SIDE-ELIGIBLE pool (percentiles computed within each side, per the frozen
    correction). Ties broken by |z| then permanent identifier."""
    out: list[Candidate] = []
    for side, pool in ((1, inp.long_eligible), (-1, inp.short_eligible)):
        zs = [(pt, inp.z[pt]) for pt in pool
              if pt in inp.z and np.isfinite(inp.z[pt])]
        if not zs:
            continue
        vals = sorted(v for _, v in zs)
        k = max(1, int(len(vals) * TOP_DECILE))
        if side > 0:
            cutoff = vals[k - 1]                       # bottom decile
            sel = [(pt, v) for pt, v in zs
                   if v <= min(cutoff, -cfg.z_entry)]
        else:
            cutoff = vals[-k]                          # top decile
            sel = [(pt, v) for pt, v in zs
                   if v >= max(cutoff, cfg.z_entry)]
        for pt, v in sorted(sel, key=lambda x: (-abs(x[1]), x[0])):
            if pt not in inp.open_next or inp.open_next[pt] <= 0:
                continue
            out.append(Candidate(pt, inp.tickers.get(pt, str(pt)), side, v,
                                 inp.sigma_resid.get(pt, np.nan),
                                 inp.sector.get(pt, ""), inp.beta.get(pt, 0.0),
                                 inp.open_next[pt], inp.adv_dollar.get(pt, 0.0)))
    return [c for c in out if np.isfinite(c.sigma_resid) and c.sigma_resid > 0]


def run(days: list[DayInputs], cfg: Config, starting_nav: float = 10_000_000.0,
        cost_bps: float = 10.0, borrow_bps: float = 50.0) -> Ledger:
    """The frozen daily loop. Returns the immutable ledger."""
    ledger = Ledger()
    nav = starting_nav
    cash = starting_nav
    positions: list[Position] = []
    prev_session: date | None = None

    for idx, inp in enumerate(days):
        nav_open = nav
        realized = costs = borrow = 0.0
        n_entries = n_exits = 0

        # ---------- borrow accrues per CALENDAR day on short market value ----------
        if prev_session is not None and positions:
            smv = sum(abs(p.shares) * inp.close_t.get(p.permaticker, p.entry_price)
                      for p in positions if p.side < 0)
            borrow = borrow_accrual(smv, (inp.session - prev_session).days, borrow_bps)

        # ---------- decisions at the CLOSE of t; execution at the t+1 OPEN ----------
        if inp.next_open_session is not None:
            # 1) EXITS FIRST
            exited: set[int] = set()
            for p in list(positions):
                held = idx - p.entry_session_idx + 1          # entry session = 1
                z_now = inp.z.get(p.permaticker, np.nan)
                reason = exit_reason(
                    z_now, held,
                    p.permaticker in inp.blackout_exit,
                    p.permaticker in inp.action_exit,
                    inp.confirm.get(p.permaticker, False))
                if reason is None:
                    continue
                px = inp.open_next.get(p.permaticker)
                if px is None or px <= 0:                    # missing official open
                    ledger.exceptions.append(
                        {"session": str(inp.session), "permaticker": p.permaticker,
                         "event": "exit_pending_missing_open", "reason": reason})
                    continue                                  # exit stays PENDING
                notional = abs(p.shares) * px
                c = execution_cost(notional, cost_bps)
                # realize only the move since the LAST MARK — earlier P&L was already
                # recognized as unrealized on prior days (no double counting)
                pnl = (px - p.last_mark) * p.shares           # signed shares
                realized += pnl
                costs += c
                cash += pnl - c
                ledger.fills.append(Fill(inp.next_open_session, p.permaticker,
                                         p.ticker, -p.side, -p.shares, px, notional,
                                         c, reason, p.entry_z))
                positions.remove(p)
                exited.add(p.permaticker)
                n_exits += 1

            # 2) DRIFT-BAND reductions (entry-neutral, ±5% of gross)
            prices_now = {p.permaticker: inp.open_next.get(p.permaticker, p.entry_price)
                          for p in positions}
            for o in drift_reductions(positions, prices_now, nav):
                p = next(x for x in positions if x.permaticker == o.permaticker)
                px = o.price
                cut = -o.shares                                # shares to remove
                pnl = (px - p.last_mark) * cut
                c = execution_cost(abs(cut) * px, cost_bps)
                realized += pnl
                costs += c
                cash += pnl - c
                p.shares -= cut
                if abs(p.shares) < 1e-9:
                    positions.remove(p)
                ledger.fills.append(Fill(inp.next_open_session, o.permaticker,
                                         o.ticker, o.side, -cut, px,
                                         abs(cut) * px, c, "reduce_drift_band",
                                         p.entry_z))

            # 3) ENTRIES — gap filter, then the frozen construction
            cands = [c for c in _candidates(inp, cfg) if c.permaticker not in exited]
            passed: list[Candidate] = []
            for c in cands:
                g = economic_gap(inp.open_next.get(c.permaticker, np.nan),
                                 inp.close_t.get(c.permaticker, np.nan),
                                 inp.cash_dist_next.get(c.permaticker, 0.0))
                if gap_filter_passes(g):
                    passed.append(c)
                else:
                    ledger.exceptions.append(
                        {"session": str(inp.session), "permaticker": c.permaticker,
                         "event": "entry_cancelled_gap_filter", "gap": float(g)})
            res = build_orders(passed, positions, prices_now, nav, ADV_PARTICIPATION)
            for o in res.orders:
                c_cost = execution_cost(o.notional, cost_bps)
                costs += c_cost
                cash -= c_cost
                cand = next(x for x in passed if x.permaticker == o.permaticker)
                positions.append(Position(
                    o.permaticker, o.ticker, o.side, o.shares, o.price,
                    inp.next_open_session, o.z, cand.sector_etf, cand.beta,
                    cand.sigma_resid, idx, last_mark=o.price))
                ledger.fills.append(Fill(inp.next_open_session, o.permaticker,
                                         o.ticker, o.side, o.shares, o.price,
                                         o.notional, c_cost, "entry", o.z,
                                         o.clipped_by_adv))
                n_entries += 1

        # ---------- mark to market at the close (DAILY change, then advance) ------
        unreal = 0.0
        long_g = short_g = 0.0
        for p in positions:
            px = inp.close_next.get(p.permaticker,
                                    inp.close_t.get(p.permaticker, p.last_mark))
            unreal += (px - p.last_mark) * p.shares     # daily change only
            p.last_mark = px                            # advance the mark
            v = abs(p.shares) * px
            if p.side > 0:
                long_g += v
            else:
                short_g += v
        net = realized + unreal - costs - borrow
        # cash carries NO return in the primary result (frozen spec)
        nav = nav_open + net
        ret = net / nav_open if nav_open > 0 else 0.0
        ledger.daily.append(DailyRecord(
            inp.session, nav_open, long_g, short_g, cash, realized, unreal,
            costs, borrow, net, nav, ret, len(positions), n_entries, n_exits))
        prev_session = inp.session

    return ledger
