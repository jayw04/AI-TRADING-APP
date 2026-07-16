"""MR-002 execution & accounting — FROZEN v1.0 §4/§9/§10b (immutable).

Price-series policy (four SEPARATE series; never mixed):
    signal   = closeadj              (total-return adjusted)
    exec     = open / close          (split-adjusted, NOT dividend-adjusted)
    gap      = exec prices + known cash distributions (economic gap)
    ranking  = close x volume        (consistent split-adjusted pair)

Execution:
    signals at the close of t -> orders execute at the t+1 OFFICIAL OPEN.
    economic_gap = (open_{t+1} + known_cash_distribution_{t+1}) / close_t - 1
    |economic_gap| >= 6%  -> the entry order is CANCELLED at the open.
    Entry session = session 1; the 5-session time stop exits at the OPEN of
    session 6. Exits also execute at the next official open.
    No valid official open -> entries CANCELLED; exits remain PENDING and execute
    at the next available official open.

Delisting valuation (registered priority): vendor delisting return is UNAVAILABLE
in this data profile -> (1) verified transaction consideration, (2) final
executable market price, (3) conservative fallback: LONGS marked to ZERO; SHORTS
covered at the GREATER of the last close and any identifiable consideration, else
last close x 1.25.

Costs: 10 bps/side (spread+impact, charged on TRADED NOTIONAL at execution) +
borrow 50 bps/yr accrued per CALENDAR day on short market value (annual/360).

Metrics (frozen §10b): daily return = net P&L / PRIOR-DAY NAV; every exchange
session is in the series including zero-exposure days; Sharpe = mean/std x sqrt(252),
rf = 0, ddof=1; CAGR = (end/start)^(252/N) - 1; maxDD on the cumulative net NAV;
Calmar = CAGR / |maxDD|.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

GAP_LIMIT = 0.06                  # |economic gap| >= 6% cancels the entry
COST_BPS_PER_SIDE = 10.0          # base (registered); stress applied separately
BORROW_ANNUAL_BPS = 50.0          # base borrow on short market value
BORROW_DAYCOUNT = 360.0           # annual rate / 360, per CALENDAR day
MAX_HOLD_SESSIONS = 5             # entry session = 1 -> time-stop exit at open of 6
EXIT_Z = 0.35                     # |z| back inside +/-0.35
STOP_Z = 3.5                      # residual beyond +/-3.5 WITH market/sector confirm
DELIST_SHORT_MARKUP = 1.25        # conservative fallback


@dataclass
class Fill:
    session: date
    permaticker: int
    ticker: str
    side: int                     # +1 buy, -1 sell (signed trade direction)
    shares: float
    price: float
    notional: float               # abs(shares) * price
    cost: float                   # execution cost charged on traded notional
    reason: str
    z: float = 0.0
    clipped_by_adv: bool = False


@dataclass
class DailyRecord:
    session: date
    nav_open: float
    long_gross: float
    short_gross: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float
    execution_costs: float
    borrow_accrual: float
    net_pnl: float
    nav_close: float
    daily_return: float
    n_positions: int
    n_entries: int
    n_exits: int


@dataclass
class Ledger:
    """The immutable trade + position ledgers. The equity curve must reproduce
    EXACTLY from these records (owner evidence requirement 2)."""

    fills: list[Fill] = field(default_factory=list)
    daily: list[DailyRecord] = field(default_factory=list)
    exceptions: list[dict] = field(default_factory=list)

    def equity_curve(self) -> np.ndarray:
        return np.array([d.nav_close for d in self.daily])

    def returns(self) -> np.ndarray:
        return np.array([d.daily_return for d in self.daily])


def economic_gap(open_next: float, close_prev: float, cash_distribution: float) -> float:
    """Frozen §4: the ex-dividend drop is NOT a gap."""
    if close_prev <= 0:
        return float("nan")
    return (open_next + cash_distribution) / close_prev - 1.0


def gap_filter_passes(gap: float) -> bool:
    return bool(np.isfinite(gap)) and abs(gap) < GAP_LIMIT


def execution_cost(notional: float, bps_per_side: float = COST_BPS_PER_SIDE) -> float:
    """Charged against TRADED NOTIONAL at execution (frozen §9)."""
    return abs(notional) * bps_per_side / 10_000.0


def borrow_accrual(short_market_value: float, calendar_days: int,
                   annual_bps: float = BORROW_ANNUAL_BPS) -> float:
    """annual rate / 360, per calendar day, on short market value (frozen §9)."""
    return abs(short_market_value) * (annual_bps / 10_000.0) * (
        calendar_days / BORROW_DAYCOUNT)


def exit_reason(z_now: float, sessions_held: int, blackout: bool,
                action_announced: bool, confirm: bool) -> str | None:
    """Frozen §4 exit ladder — FIRST occurrence wins."""
    if blackout:
        return "exit_earnings_blackout"
    if action_announced:
        return "exit_corporate_action"
    if np.isfinite(z_now) and abs(z_now) <= EXIT_Z:
        return "exit_z_reverted"
    if np.isfinite(z_now) and abs(z_now) >= STOP_Z and confirm:
        return "exit_hypothesis_failure"     # residual extends AND market/sector confirms
    if sessions_held >= MAX_HOLD_SESSIONS:
        return "exit_time_stop"              # exits at the open of session 6
    return None


def delisting_value(side: int, last_close: float,
                    consideration: float | None) -> tuple[float, str]:
    """Registered priority order; vendor delisting return is unavailable here."""
    if consideration is not None and consideration > 0:
        return consideration, "verified_transaction_consideration"
    if side > 0:
        return 0.0, "conservative_fallback_long_marked_to_zero"
    price = max(last_close, consideration or 0.0)
    if price <= 0:
        price = last_close
    return price * DELIST_SHORT_MARKUP, "conservative_fallback_short_markup_1.25x"


def sharpe(returns: np.ndarray) -> float:
    r = returns[np.isfinite(returns)]
    if len(r) < 2:
        return float("nan")
    sd = np.std(r, ddof=1)
    return float(np.mean(r) / sd * np.sqrt(252)) if sd > 0 else float("nan")


def cagr(nav: np.ndarray) -> float:
    if len(nav) < 2 or nav[0] <= 0:
        return float("nan")
    return float((nav[-1] / nav[0]) ** (252.0 / len(nav)) - 1.0)


def max_drawdown(nav: np.ndarray) -> float:
    if len(nav) == 0:
        return float("nan")
    peak = np.maximum.accumulate(nav)
    return float(np.min(nav / peak - 1.0))


def calmar(nav: np.ndarray) -> float:
    mdd = max_drawdown(nav)
    c = cagr(nav)
    return float(c / abs(mdd)) if mdd and mdd < 0 else float("nan")


def reconcile(ledger: Ledger, starting_nav: float) -> dict:
    """INDEPENDENT reconciliation (owner evidence requirement 2): rebuild the equity
    curve from the immutable fill + daily ledgers and require exact agreement."""
    nav = starting_nav
    rebuilt = []
    for d in ledger.daily:
        nav_prev = nav
        nav = nav_prev + d.net_pnl
        rebuilt.append(nav)
        # per-day identity: net = realized + unrealized - costs - borrow
        expect = d.realized_pnl + d.unrealized_pnl - d.execution_costs - d.borrow_accrual
        if abs(expect - d.net_pnl) > 1e-6:
            return {"ok": False, "error": "daily_pnl_identity_violation",
                    "session": str(d.session), "expected": expect, "got": d.net_pnl}
        if abs(d.nav_close - nav) > 1e-6:
            return {"ok": False, "error": "nav_rollforward_violation",
                    "session": str(d.session), "expected": nav, "got": d.nav_close}
        if nav_prev > 0 and abs(d.daily_return - d.net_pnl / nav_prev) > 1e-12:
            return {"ok": False, "error": "return_basis_violation",
                    "session": str(d.session)}
    curve = ledger.equity_curve()
    if len(curve) != len(rebuilt) or not np.allclose(curve, rebuilt, rtol=0, atol=1e-6):
        return {"ok": False, "error": "equity_curve_mismatch"}
    total_cost = sum(f.cost for f in ledger.fills)
    ledger_cost = sum(d.execution_costs for d in ledger.daily)
    if abs(total_cost - ledger_cost) > 1e-6:
        return {"ok": False, "error": "cost_ledger_mismatch",
                "fills": total_cost, "daily": ledger_cost}
    return {"ok": True, "sessions": len(ledger.daily), "fills": len(ledger.fills),
            "total_execution_costs": total_cost,
            "total_borrow": sum(d.borrow_accrual for d in ledger.daily),
            "final_nav": float(curve[-1]) if len(curve) else starting_nav}
