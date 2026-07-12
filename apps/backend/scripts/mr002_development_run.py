"""MR-002 v1.1 — FULL A/B/C DEVELOPMENT RUN (1,700 sessions).

Authorized 2026-07-12 on the countersigned design:
    Pre-Registration v1.1 rev 3   sha256 311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5
    Structural adjudication       sha256 ba980c4398b51d4ef4a0a3b77f687e62817b18beb5b3c281a7ab0fd1de3b947e

Window: 2013-01-02 .. 2019-10-02 (development ONLY). Validation and sealed OOS are NOT
read -- the data-boundary assertion below is FATAL, not advisory.

Performance inspection inside the development window is now PERMITTED.

EVERY fatal condition -- solver, residual, constraint, determinism, session-reconciliation
or data-boundary -- raises INVALID_RUN and STOPS. No failed computation is ever converted
into a cash or zero-entry outcome.

NO signal, threshold, risk limit, gate, cost assumption, universe rule or construction rule
may be changed in response to these results.

Runs ONLY inside the frozen Linux/amd64 mr002-research image.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.execution import (  # noqa: E402
    borrow_accrual,
    economic_gap,
    execution_cost,
    exit_reason,
    gap_filter_passes,
)
from app.research.mr002.joint_portfolio import (  # noqa: E402
    EXECUTION_CONSTRAINED_INFEASIBLE,
    FEASIBLE,
    NEW_ENTRY_CAP,
    NO_MATCHED_INCREMENT,
    NO_TRADABLE_HOLDINGS_NO_CANDIDATES,
    VALID_ZERO_ENTRY_OUTCOME,
    Holding,
    InvalidRun,
    NewCandidate,
    build_joint,
)
from app.research.mr002.portfolio import Position  # noqa: E402
from app.research.mr002.runner import ADV_PARTICIPATION, CONFIGS, _candidates  # noqa: E402

DEV_START = date(2013, 1, 2)
DEV_END = date(2019, 10, 2)               # HARD BOUNDARY. Validation begins 2019-10-03.
VALIDATION_START = date(2019, 10, 3)

TERMINAL_SESSION_NO_EXECUTION_OPEN = "TERMINAL_SESSION_NO_EXECUTION_OPEN"

NAV0 = 10_000_000.0
COST_BPS = 10.0
BORROW_BPS = 50.0

# Frozen breadth gates -- reported, NEVER adjusted in response to results.
GATE_TRADES = 500
GATE_LONG = 100
GATE_SHORT = 100


def _f64_hex(x: float) -> str:
    return struct.pack(">d", float(x)).hex()


@dataclass
class Trade:
    permaticker: int
    side: int
    entry_session: str
    exit_session: str
    reason: str
    gross_pnl: float
    costs: float
    net_pnl: float


@dataclass
class Acc:
    nav: float = NAV0
    daily_ret: list = field(default_factory=list)
    nav_curve: list = field(default_factory=list)
    costs: float = 0.0
    borrow: float = 0.0
    traded_notional: float = 0.0
    entries_long: int = 0
    entries_short: int = 0
    exits: int = 0
    reductions: int = 0
    trades: list = field(default_factory=list)
    gross: list = field(default_factory=list)
    outcomes: Counter = field(default_factory=Counter)
    zero_reasons: Counter = field(default_factory=Counter)
    session_hashes: list = field(default_factory=list)
    per_solve_hashes: int = 0
    max_kkt: float = 0.0
    max_kappa: float = 0.0
    max_violation: float = 0.0
    lp_statuses: set = field(default_factory=set)
    exit_reasons: Counter = field(default_factory=Counter)
    adv_clipped: int = 0
    over_cap_days: int = 0


def _weights(positions, prices, nav):
    out = {}
    for p in positions:
        px = prices.get(p.permaticker) or p.last_mark
        out[p.permaticker] = (abs(p.shares) * px / nav, px)
    return out


def _candidate_weights(cands, positions, nav):
    """Registered v1.0 sizing, unchanged: 1/sigma_resid within side, normalized to the
    matched increment, then the 1.5% new-entry cap and the 2% ADV clip. The LP may only
    REDUCE from here."""
    held = {p.permaticker for p in positions}
    longs = [c for c in cands if c.side > 0 and c.permaticker not in held]
    shorts = [c for c in cands if c.side < 0 and c.permaticker not in held]
    gross = sum(abs(p.shares) * p.last_mark for p in positions)
    headroom = max(0.0, nav - gross)
    matched = min(min(NEW_ENTRY_CAP * nav * len(longs), headroom / 2.0),
                  min(NEW_ENTRY_CAP * nav * len(shorts), headroom / 2.0))
    if matched <= 0:
        return {}
    out: dict[int, tuple[float, float, bool]] = {}
    for side_cands in (longs, shorts):
        inv = {c.permaticker: (1.0 / c.sigma_resid if c.sigma_resid > 0 else 0.0)
               for c in side_cands}
        tot = sum(inv.values())
        if tot <= 0:
            continue
        for c in side_cands:
            n = min(matched * inv[c.permaticker] / tot, NEW_ENTRY_CAP * nav)
            adv_cap = ADV_PARTICIPATION * c.adv_dollar
            clipped = n > adv_cap
            n = min(n, adv_cap)
            if n <= 0 or c.exec_price <= 0:
                continue
            out[c.permaticker] = (n / nav, c.exec_price, clipped)
    return out


def run_config(days, cfg) -> Acc:
    a = Acc()
    cash = NAV0
    positions: list[Position] = []
    entry_w: dict[int, float] = {}
    prev: date | None = None

    for idx, inp in enumerate(days):
        nav_open = a.nav
        realized = costs = borrow = 0.0
        n_exits = n_orders = n_red = 0

        if prev is not None and positions:
            smv = sum(abs(p.shares) * inp.close_t.get(p.permaticker, p.last_mark)
                      for p in positions if p.side < 0)
            borrow = borrow_accrual(smv, (inp.session - prev).days, BORROW_BPS)

        outcome = TERMINAL_SESSION_NO_EXECUTION_OPEN
        diag: dict = {}
        n_cands = 0

        if inp.next_open_session is not None:
            # ---- 1) HARD EXITS FIRST (before inclusion-floor classification) ----------
            exited: set[int] = set()
            for p in list(positions):
                held = idx - p.entry_session_idx + 1
                reason = exit_reason(
                    inp.z.get(p.permaticker, np.nan), held,
                    p.permaticker in inp.blackout_exit,
                    p.permaticker in inp.action_exit,
                    inp.confirm.get(p.permaticker, False))
                if reason is None:
                    continue
                px = inp.open_next.get(p.permaticker)
                if px is None or px <= 0:
                    continue                                    # exit stays PENDING
                notional = abs(p.shares) * px
                c = execution_cost(notional, COST_BPS)
                realized += (px - p.last_mark) * p.shares
                costs += c
                cash += (px - p.last_mark) * p.shares - c
                a.traded_notional += notional
                # per-trade P&L is measured from ENTRY (a separate statistic from the
                # NAV roll-forward, which uses last_mark deltas and must not double count)
                gross_pnl = (px - p.entry_price) * p.shares
                a.trades.append(Trade(p.permaticker, p.side, str(p.entry_date),
                                      str(inp.next_open_session), reason,
                                      gross_pnl, c, gross_pnl - c))
                a.exit_reasons[reason] += 1
                positions.remove(p)
                entry_w.pop(p.permaticker, None)
                exited.add(p.permaticker)
                n_exits += 1

            # ---- 2) JOINT CONSTRUCTION -------------------------------------------------
            prices = {p.permaticker: inp.open_next.get(p.permaticker, p.last_mark)
                      for p in positions}
            wmap = _weights(positions, prices, a.nav)
            holdings = [
                Holding(p.permaticker, p.side, wmap[p.permaticker][0], p.sector_etf,
                        p.beta, entry_w.get(p.permaticker, 0.0),
                        (inp.open_next.get(p.permaticker) or 0) > 0)
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

            res = build_joint(holdings, cands)          # InvalidRun propagates -> STOPS
            outcome = res.outcome
            diag = res.diagnostics
            if (diag.get("zero_entry_reason") == NO_TRADABLE_HOLDINGS_NO_CANDIDATES
                    and n_cands > 0):
                diag["zero_entry_reason"] = NO_MATCHED_INCREMENT

            # ---- 3) apply: reductions, then new entries --------------------------------
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

        # ---- mark to market ------------------------------------------------------------
        unreal = 0.0
        for p in positions:
            px = inp.close_next.get(p.permaticker,
                                    inp.close_t.get(p.permaticker, p.last_mark))
            unreal += (px - p.last_mark) * p.shares
            p.last_mark = px
        net = realized + unreal - costs - borrow
        a.nav = nav_open + net
        a.daily_ret.append(net / nav_open if nav_open > 0 else 0.0)
        a.nav_curve.append(a.nav)
        a.costs += costs
        a.borrow += borrow
        a.exits += n_exits
        a.reductions += n_red
        prev = inp.session

        # ---- registered session state + canonical session-level determinism hash --------
        a.outcomes[outcome] += 1
        if outcome == VALID_ZERO_ENTRY_OUTCOME:
            a.zero_reasons[diag.get("zero_entry_reason", "UNCLASSIFIED")] += 1
        if diag.get("determinism_hash"):
            a.per_solve_hashes += 1
        if diag.get("total_gross", 0.0) > 1e-6:
            a.gross.append(diag["total_gross"])
        s3 = diag.get("stage3", {})
        a.max_kkt = max(a.max_kkt, s3.get("kkt_residual", 0.0) or 0.0)
        a.max_kappa = max(a.max_kappa, s3.get("hessian_condition_number", 0.0) or 0.0)
        a.max_violation = max(a.max_violation, diag.get("max_homogeneous_violation", 0.0) or 0.0)
        for st in ((diag.get("stage1") or {}).get("status"),
                   (diag.get("stage2") or {}).get("status")):
            if st is not None:
                a.lp_statuses.add(int(st))
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

    return a


def metrics(a: Acc, name: str, n_sessions: int) -> dict:
    r = np.array(a.daily_ret, dtype=float)
    nav = np.array(a.nav_curve, dtype=float)
    ann = float(r.mean() / r.std(ddof=1) * np.sqrt(252)) if r.std(ddof=1) > 0 else 0.0
    peak = np.maximum.accumulate(nav)
    dd = (nav - peak) / peak
    closed = a.trades
    wins = sum(1 for t in closed if t.net_pnl > 0)

    # ---- session funnel: must reconcile with NO residual bucket --------------------------
    funnel = {
        "total_scheduled_sessions": n_sessions,
        "terminal_session_no_execution_open": a.outcomes.get(TERMINAL_SESSION_NO_EXECUTION_OPEN, 0),
        "feasible_positive_entry_sessions": a.outcomes.get(FEASIBLE, 0),
        "valid_zero_entry_outcome_sessions": a.outcomes.get(VALID_ZERO_ENTRY_OUTCOME, 0),
        "valid_zero_entry_reasons": dict(a.zero_reasons),
        "execution_constrained_infeasible_sessions": a.outcomes.get(
            EXECUTION_CONSTRAINED_INFEASIBLE, 0),
        "invalid_run_sessions": 0,
        "unclassified_sessions": 0,
    }
    funnel["sum_of_states"] = (funnel["terminal_session_no_execution_open"]
                               + funnel["feasible_positive_entry_sessions"]
                               + funnel["valid_zero_entry_outcome_sessions"]
                               + funnel["execution_constrained_infeasible_sessions"])
    if funnel["sum_of_states"] != n_sessions:
        raise InvalidRun(f"{name}: SESSION FUNNEL DOES NOT RECONCILE "
                         f"({funnel['sum_of_states']} != {n_sessions})")
    if sum(a.zero_reasons.values()) != funnel["valid_zero_entry_outcome_sessions"]:
        raise InvalidRun(f"{name}: zero-entry reasons do not reconcile")
    if "UNCLASSIFIED" in a.zero_reasons:
        raise InvalidRun(f"{name}: unclassified zero-entry session")
    if len(a.session_hashes) != n_sessions:
        raise InvalidRun(f"{name}: determinism-hash coverage "
                         f"{len(a.session_hashes)} != {n_sessions}")

    trades_total = len(closed)
    return {
        "config": name,
        "z_entry": CONFIGS[name].z_entry,
        "session_funnel": funnel,
        "determinism": {
            "session_level_hashes": len(a.session_hashes),
            "of_sessions": n_sessions,
            "per_solve_hashes": a.per_solve_hashes,
            "run_hash": hashlib.sha256("|".join(a.session_hashes).encode()).hexdigest(),
        },
        "breadth_gates": {
            "trades": trades_total,
            "gate_trades": GATE_TRADES,
            "trades_pass": trades_total >= GATE_TRADES,
            "long_entries": a.entries_long,
            "gate_long": GATE_LONG,
            "long_pass": a.entries_long >= GATE_LONG,
            "short_entries": a.entries_short,
            "gate_short": GATE_SHORT,
            "short_pass": a.entries_short >= GATE_SHORT,
            "all_breadth_gates_pass": (trades_total >= GATE_TRADES
                                       and a.entries_long >= GATE_LONG
                                       and a.entries_short >= GATE_SHORT),
        },
        "performance": {
            "total_return": float(nav[-1] / NAV0 - 1.0),
            "final_nav": float(nav[-1]),
            "annualized_sharpe": ann,
            "annualized_return": float((nav[-1] / NAV0) ** (252.0 / n_sessions) - 1.0),
            "annualized_vol": float(r.std(ddof=1) * np.sqrt(252)),
            "max_drawdown": float(dd.min()),
            "hit_rate": (wins / trades_total) if trades_total else 0.0,
            "winning_trades": wins,
            "losing_trades": trades_total - wins,
            "basis": "sqrt(252); rf = 0; daily return on PRIOR-DAY NAV (frozen)",
        },
        "execution": {
            "new_orders": a.entries_long + a.entries_short,
            "coupling_reductions": a.reductions,
            "exits": a.exits,
            "exit_reasons": dict(a.exit_reasons),
            "adv_clipped_orders": a.adv_clipped,
            "total_traded_notional": a.traded_notional,
            "total_costs": a.costs,
            "total_borrow": a.borrow,
            "cost_bps_per_side": COST_BPS,
            "borrow_bps_per_year": BORROW_BPS,
        },
        "risk": {
            "sessions_with_material_gross": len(a.gross),
            "gross_min": min(a.gross) if a.gross else 0.0,
            "gross_median": float(np.median(a.gross)) if a.gross else 0.0,
            "gross_max": max(a.gross) if a.gross else 0.0,
            "existing_position_over_entry_cap_days": a.over_cap_days,
        },
        "solver": {
            "max_homogeneous_violation": a.max_violation,
            "violation_limit": 1e-9,
            "max_kkt_residual": a.max_kkt,
            "kkt_limit": 1e-8,
            "max_hessian_condition_number": a.max_kappa,
            "kappa_limit": 1e10,
            "lp_statuses_observed": sorted(a.lp_statuses),
            "invalid_runs": 0,
        },
    }


def main() -> int:
    store = os.environ.get("MR002_STORE", "/work/apps/backend/data/mr002_research.duckdb")
    ds = FrozenDataset(store)
    days = ds.day_inputs(DEV_START, DEV_END)

    # ---- DATA-BOUNDARY ASSERTION: FATAL, not advisory ---------------------------------
    if not days:
        raise InvalidRun("no development sessions loaded")
    if days[-1].session > DEV_END or days[0].session < DEV_START:
        raise InvalidRun(f"data-boundary failure: {days[0].session}..{days[-1].session} "
                         f"outside {DEV_START}..{DEV_END}")
    if any(d.session >= VALIDATION_START for d in days):
        raise InvalidRun("data-boundary failure: a VALIDATION session was loaded")
    print(f"development sessions: {len(days)}  ({days[0].session} .. {days[-1].session})")

    results = {}
    for name in ("A", "B", "C"):
        print(f"  running config {name} (z_entry={CONFIGS[name].z_entry}) ...", flush=True)
        acc = run_config(days, CONFIGS[name])
        results[name] = metrics(acc, name, len(days))

    pkg = {
        "record_type": "MR002_DEVELOPMENT_EVIDENCE_PACKAGE",
        "authorized": "2026-07-12 — full A/B/C development run",
        "preregistration_sha256":
            "311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5",
        "structural_adjudication_sha256":
            "ba980c4398b51d4ef4a0a3b77f687e62817b18beb5b3c281a7ab0fd1de3b947e",
        "window": {"start": str(DEV_START), "end": str(DEV_END), "sessions": len(days),
                   "note": "DEVELOPMENT ONLY. Validation and sealed OOS were not read."},
        "verdict_configuration": "B",
        "configs": results,
        "configuration_comparison": {
            c: {
                "z_entry": results[c]["z_entry"],
                "trades": results[c]["breadth_gates"]["trades"],
                "all_breadth_gates_pass": results[c]["breadth_gates"]["all_breadth_gates_pass"],
                "total_return": results[c]["performance"]["total_return"],
                "annualized_sharpe": results[c]["performance"]["annualized_sharpe"],
                "max_drawdown": results[c]["performance"]["max_drawdown"],
                "hit_rate": results[c]["performance"]["hit_rate"],
                "gross_median": results[c]["risk"]["gross_median"],
            }
            for c in ("A", "B", "C")
        },
        "immutability_note": (
            "No signal, threshold, risk limit, gate, cost assumption, universe rule or "
            "construction rule may be changed in response to these results."
        ),
    }

    out = os.environ.get("MR002_DEV_OUT", "/out/MR002_DevelopmentEvidence_v1.1.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pkg, fh, indent=2)
        fh.write("\n")

    print(json.dumps(pkg["configuration_comparison"], indent=2))
    print("\nrun hashes:", {c: results[c]["determinism"]["run_hash"][:16] for c in results})
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InvalidRun as exc:
        print(f"\nINVALID_RUN — RUN STOPPED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
