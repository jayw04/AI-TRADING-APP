"""MR-002 v1.1 — 124-SESSION STRUCTURAL SLICE.

Registered by Pre-Registration v1.1 rev 3 §11 (countersigned 2026-07-12, artifact
sha256 311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5).

Runs the joint LP/QP construction over the SAME 124 development sessions on which the
v1.0 cascade produced zero orders, and answers exactly one question: IS THE REGISTERED
DESIGN STRUCTURALLY EXECUTABLE?

PROHIBITED INSPECTION -- this script must NEVER emit, print or persist:
    P&L, returns, Sharpe, hit rate, drawdown, or any configuration comparison.
The ledger tracks NAV internally because position weights depend on it; that is
accounting, not inspection. The report below contains ONLY the permitted structural
fields. There is a hard guard at the end that fails the run if a prohibited key ever
appears in the report.

Runs ONLY inside the frozen Linux/amd64 mr002-research image.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass
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
from app.research.mr002.runner import CONFIGS, ADV_PARTICIPATION, _candidates  # noqa: E402

# ---- the registered structural slice: the SAME 124 sessions v1.0 destroyed ----------
SLICE_START = date(2013, 1, 2)
SLICE_END = date(2013, 6, 28)

# The slice's LAST session has no t+1 open INSIDE the window, so no execution decision
# is made. A window-boundary artifact, not a market condition -- named, not hidden.
TERMINAL_SESSION_NO_EXECUTION_OPEN = "TERMINAL_SESSION_NO_EXECUTION_OPEN"
DEV_END = date(2019, 10, 2)          # the development window bound -- never exceeded

def _f64_hex(x: float) -> str:
    return struct.pack(">d", float(x)).hex()


PROHIBITED = (
    "pnl", "p_and_l", "return", "returns", "sharpe", "hit_rate", "drawdown",
    "equity", "profit", "loss",
)

LABEL = (
    "MR-002 v1.1 STRUCTURAL SLICE — executability evidence only. No performance "
    "interpretation, no configuration comparison, and no gate verdict may be drawn "
    "from this artifact. Validation and sealed OOS remain sealed and unread."
)


@dataclass
class DayReport:
    session: str
    outcome: str
    n_candidates: int
    n_orders: int
    n_reductions: int
    n_exits: int
    n_positions_after: int
    retained_existing_gross: float
    new_gross: float
    total_gross: float
    active_sector_count: int
    active_sectors: list
    max_sector_gross_ratio: float
    max_sector_net_ratio: float
    normalized_beta: float
    normalized_net: float
    zero_entry_reason: str | None
    stage3_formulation: str | None
    raw_exception_message: str | None
    feasibility_probe_status: int | None
    session_determinism_hash: str
    binding_constraints: list
    max_homogeneous_violation: float | None
    gross_is_material: bool
    lp1_status: int | None
    lp2_status: int | None
    kkt_residual: float | None
    hessian_condition_number: float | None
    determinism_hash: str | None
    over_entry_cap_count: int
    excluded_mass: dict


def _weights(positions, prices, nav):
    """Absolute NAV weights of the existing book. Direction is carried separately."""
    out = {}
    for p in positions:
        px = prices.get(p.permaticker)
        if px is None or px <= 0:
            px = p.last_mark
        out[p.permaticker] = (abs(p.shares) * px / nav, px)
    return out


def _candidate_weights(cands, positions, nav):
    """The registered inverse-residual-volatility sizing, unchanged from v1.0:
    weights proportional to 1/sigma_resid, normalized to the matched per-side increment,
    then the 1.5% NAV entry cap and the 2% ADV clip. The LP may only REDUCE from here."""
    held = {p.permaticker for p in positions}
    longs = [c for c in cands if c.side > 0 and c.permaticker not in held]
    shorts = [c for c in cands if c.side < 0 and c.permaticker not in held]

    gross = sum(abs(p.shares) * p.last_mark for p in positions)
    headroom = max(0.0, nav - gross)
    long_cap = min(NEW_ENTRY_CAP * nav * len(longs), headroom / 2.0)
    short_cap = min(NEW_ENTRY_CAP * nav * len(shorts), headroom / 2.0)
    matched = min(long_cap, short_cap)
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
            notional = matched * inv[c.permaticker] / tot
            notional = min(notional, NEW_ENTRY_CAP * nav)
            adv_cap = ADV_PARTICIPATION * c.adv_dollar
            clipped = notional > adv_cap
            notional = min(notional, adv_cap)
            if notional <= 0 or c.exec_price <= 0:
                continue
            out[c.permaticker] = (notional / nav, c.exec_price, clipped)
    return out


def main() -> int:
    store = os.environ.get("MR002_STORE", "/work/apps/backend/data/mr002_research.duckdb")
    cfg = CONFIGS["B"]                      # the sole verdict configuration

    ds = FrozenDataset(store)
    days = ds.day_inputs(SLICE_START, SLICE_END)
    assert all(d.session <= DEV_END for d in days), "development window bound violated"
    print(f"sessions: {len(days)}  ({days[0].session} .. {days[-1].session})")

    nav = 10_000_000.0
    cash = nav
    positions: list[Position] = []
    entry_weights: dict[int, float] = {}   # NAV weight AT ENTRY (for the over-cap diagnostic)
    prev: date | None = None
    reports: list[DayReport] = []

    for idx, inp in enumerate(days):
        nav_open = nav
        realized = costs = borrow = 0.0
        n_exits = n_orders = n_reductions = 0

        if prev is not None and positions:
            smv = sum(abs(p.shares) * inp.close_t.get(p.permaticker, p.last_mark)
                      for p in positions if p.side < 0)
            borrow = borrow_accrual(smv, (inp.session - prev).days, 50.0)

        outcome = TERMINAL_SESSION_NO_EXECUTION_OPEN
        diag: dict = {}
        n_cands = 0

        if inp.next_open_session is not None:
            # ---- 1) HARD EXITS FIRST (before inclusion-floor classification) --------
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
                    continue                                   # exit stays PENDING
                pnl = (px - p.last_mark) * p.shares
                c = execution_cost(abs(p.shares) * px, 10.0)
                realized += pnl
                costs += c
                cash += pnl - c
                positions.remove(p)
                entry_weights.pop(p.permaticker, None)
                exited.add(p.permaticker)
                n_exits += 1

            # ---- 2) JOINT CONSTRUCTION (the drift band is now a COUPLING CONSTRAINT;
            #         the separate v1.0 drift-reduction pass is superseded) -----------
            prices = {p.permaticker: inp.open_next.get(p.permaticker, p.last_mark)
                      for p in positions}
            wmap = _weights(positions, prices, nav)

            holdings = []
            for p in positions:
                w, px = wmap[p.permaticker]
                tradable = (inp.open_next.get(p.permaticker) or 0) > 0
                holdings.append(Holding(
                    p.permaticker, p.side, w, p.sector_etf, p.beta,
                    entry_weights.get(p.permaticker, 0.0), tradable))

            raw = [c for c in _candidates(inp, cfg) if c.permaticker not in exited]
            passed = [
                c for c in raw
                if gap_filter_passes(economic_gap(
                    inp.open_next.get(c.permaticker, np.nan),
                    inp.close_t.get(c.permaticker, np.nan),
                    inp.cash_dist_next.get(c.permaticker, 0.0)))
            ]
            n_cands = len(passed)
            cw = _candidate_weights(passed, positions, nav)
            cands = [
                NewCandidate(c.permaticker, c.side, cw[c.permaticker][0],
                             c.sector_etf, c.beta)
                for c in passed if c.permaticker in cw
            ]

            try:
                res = build_joint(holdings, cands)
            except InvalidRun as exc:
                print(f"\nINVALID_RUN on {inp.session}: {exc}", file=sys.stderr)
                return 1

            outcome = res.outcome
            diag = res.diagnostics
            diag["_y"], diag["_x"] = res.y, res.x

            # The slice filters zero-weight candidates BEFORE the solver, so build_joint
            # cannot distinguish "no candidates existed" from "candidates existed but the
            # dollar-neutrality equality admitted no matched increment". Only the caller
            # knows. Correct the label here rather than let the solver mis-report it.
            if (diag.get("zero_entry_reason") == NO_TRADABLE_HOLDINGS_NO_CANDIDATES
                    and n_cands > 0):
                diag["zero_entry_reason"] = NO_MATCHED_INCREMENT

            # ---- 3) apply: reductions to existing, then new entries -----------------
            for p in list(positions):
                y = res.y.get(p.permaticker)
                if y is None:
                    continue                                    # fixed: cannot trade
                c_w = wmap[p.permaticker][0]
                if y >= c_w - 1e-12:
                    continue
                px = prices[p.permaticker]
                cut_notional = (c_w - y) * nav
                cut_shares = cut_notional / px * p.side
                pnl = (px - p.last_mark) * cut_shares
                c = execution_cost(cut_notional, 10.0)
                realized += pnl
                costs += c
                cash += pnl - c
                p.shares -= cut_shares
                n_reductions += 1
                if abs(p.shares) * px / nav <= 1e-12:
                    positions.remove(p)

            by_pt = {c.permaticker: c for c in passed}
            for pt, x in sorted(res.x.items()):
                if x <= 1e-12:
                    continue
                c0 = by_pt[pt]
                px = cw[pt][1]
                notional = x * nav
                cost = execution_cost(notional, 10.0)
                costs += cost
                cash -= cost
                positions.append(Position(
                    pt, c0.ticker, c0.side, notional / px * c0.side, px,
                    inp.next_open_session, c0.z, c0.sector_etf, c0.beta,
                    c0.sigma_resid, idx, last_mark=px))
                entry_weights[pt] = x
                n_orders += 1

        # ---- mark to market (accounting only; never inspected) -----------------------
        unreal = 0.0
        for p in positions:
            px = inp.close_next.get(p.permaticker,
                                    inp.close_t.get(p.permaticker, p.last_mark))
            unreal += (px - p.last_mark) * p.shares
            p.last_mark = px
        nav = nav_open + realized + unreal - costs - borrow
        prev = inp.session

        s3 = diag.get("stage3", {})
        binding = diag.get("unavoidable_coupling_breaches", [])

        # CANONICAL SESSION-LEVEL DETERMINISM HASH -- emitted for EVERY session, including
        # terminal, empty and infeasible ones. IEEE-754 hex, permanent-identifier order.
        # The per-solve hash covers only the solver's output; this covers the session's
        # entire executable decision, so hash coverage is 124/124 by construction.
        h = hashlib.sha256()
        h.update(f"{inp.session}|{outcome}|{diag.get('zero_entry_reason') or ''}".encode())
        for tag, bk in (("y", diag.get("_y", {})), ("x", diag.get("_x", {}))):
            for pt in sorted(bk):
                h.update(f"|{tag}:{pt}:{_f64_hex(bk[pt])}".encode())
        h.update(f"|exits:{n_exits}|red:{n_reductions}|ord:{n_orders}".encode())
        session_hash = h.hexdigest()

        reports.append(DayReport(
            session=str(inp.session),
            outcome=outcome,
            zero_entry_reason=diag.get("zero_entry_reason"),
            stage3_formulation=s3.get("stage3_formulation"),
            raw_exception_message=s3.get("raw_exception_message"),
            feasibility_probe_status=s3.get("feasibility_probe_status"),
            session_determinism_hash=session_hash,
            n_candidates=n_cands,
            n_orders=n_orders,
            n_reductions=n_reductions,
            n_exits=n_exits,
            n_positions_after=len(positions),
            retained_existing_gross=float(diag.get("retained_existing_gross", 0.0)),
            new_gross=float(diag.get("new_gross", 0.0)),
            total_gross=float(diag.get("total_gross", 0.0)),
            active_sector_count=int(diag.get("active_sector_count", 0)),
            active_sectors=list(diag.get("active_sectors", [])),
            max_sector_gross_ratio=diag.get("max_sector_gross_ratio"),
            max_sector_net_ratio=diag.get("max_sector_net_ratio"),
            normalized_beta=diag.get("normalized_beta"),
            normalized_net=diag.get("normalized_net"),
            binding_constraints=list(diag.get("binding_constraints", [])) or binding,
            max_homogeneous_violation=diag.get("max_homogeneous_violation"),
            gross_is_material=bool(diag.get("gross_is_material", False)),
            lp1_status=(diag.get("stage1") or {}).get("status"),
            lp2_status=(diag.get("stage2") or {}).get("status"),
            kkt_residual=s3.get("kkt_residual"),
            hessian_condition_number=s3.get("hessian_condition_number"),
            determinism_hash=diag.get("determinism_hash"),
            over_entry_cap_count=len(diag.get("existing_position_over_entry_cap", [])),
            excluded_mass=diag.get("excluded_mass", {}),
        ))

    # ---------------- structural summary (PERMITTED INSPECTION ONLY) ------------------
    days_with_orders = sum(1 for r in reports if r.n_orders > 0)
    total_orders = sum(r.n_orders for r in reports)
    zero_entry = sum(1 for r in reports if r.outcome == VALID_ZERO_ENTRY_OUTCOME)
    eci = sum(1 for r in reports if r.outcome == EXECUTION_CONSTRAINED_INFEASIBLE)
    MATERIAL = 1e-6            # the frozen reporting threshold; NEVER a constraint input
    gross = [r.total_gross for r in reports if r.total_gross > MATERIAL]
    mat = [r for r in reports if r.gross_is_material]
    viol = [r.max_homogeneous_violation for r in reports
            if r.max_homogeneous_violation is not None]
    kkt = [r.kkt_residual for r in reports if r.kkt_residual is not None]
    kappa = [r.hessian_condition_number for r in reports
             if r.hessian_condition_number is not None]

    from collections import Counter
    oc = Counter(r.outcome for r in reports)
    zr = Counter(r.zero_entry_reason for r in reports if r.zero_entry_reason)
    funnel = {
        "total_scheduled_sessions": len(reports),
        "terminal_session_no_execution_open": oc.get(TERMINAL_SESSION_NO_EXECUTION_OPEN, 0),
        "feasible_positive_entry_sessions": oc.get("FEASIBLE", 0),
        "valid_zero_entry_outcome_sessions": oc.get(VALID_ZERO_ENTRY_OUTCOME, 0),
        "valid_zero_entry_reasons": dict(zr),
        "execution_constrained_infeasible_sessions": oc.get(
            EXECUTION_CONSTRAINED_INFEASIBLE, 0),
        "invalid_run_sessions": 0,
        "unclassified_sessions": 0,
    }
    funnel["sum_of_states"] = (
        funnel["terminal_session_no_execution_open"]
        + funnel["feasible_positive_entry_sessions"]
        + funnel["valid_zero_entry_outcome_sessions"]
        + funnel["execution_constrained_infeasible_sessions"]
    )
    assert funnel["sum_of_states"] == len(reports), (
        f"SESSION FUNNEL DOES NOT RECONCILE: {funnel['sum_of_states']} != {len(reports)}"
    )
    assert oc.get("FEASIBLE", 0) == sum(1 for r in reports if r.n_orders > 0),         "FEASIBLE sessions must be exactly the sessions with new orders"
    assert sum(zr.values()) == oc.get(VALID_ZERO_ENTRY_OUTCOME, 0),         "every zero-entry session must carry exactly one registered reason"

    n_session_hashes = sum(1 for r in reports if r.session_determinism_hash)
    n_solve_hashes = sum(1 for r in reports if r.determinism_hash)
    assert n_session_hashes == len(reports), "every session must carry a determinism hash"

    summary = {
        "label": LABEL,
        "session_funnel": funnel,
        "stage3_cascade": {
            "raw_solves": sum(1 for r in reports if r.stage3_formulation == "RAW"),
            "scaled_rescues": sum(1 for r in reports
                                  if r.stage3_formulation == "SCALED_RESCUE"),
            "erratum_sha256":
                "9ce8f53a4367c5817881cab55d9550db058a171e8ee504f57ad6a7060fe378fb",
        },
        "determinism_hash_coverage": {
            "session_level_hashes": n_session_hashes,
            "of_sessions": len(reports),
            "per_solve_hashes": n_solve_hashes,
            "note": (
                "The canonical SESSION-level hash covers every session by construction, "
                "including terminal, zero-variable and execution-constrained ones. The "
                "per-solve hash is emitted only where a solve occurred; the two are "
                "reported separately rather than conflated."
            ),
        },
        "preregistration_artifact_sha256":
            "311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5",
        "config": "B (sole verdict configuration)",
        "window": {"start": str(SLICE_START), "end": str(SLICE_END),
                   "sessions": len(reports)},
        "executability": {
            "sessions_with_orders": days_with_orders,
            "total_new_orders": total_orders,
            "total_reductions": sum(r.n_reductions for r in reports),
            "total_exits": sum(r.n_exits for r in reports),
            "valid_zero_entry_outcome_days": zero_entry,
            "execution_constrained_infeasible_days": eci,
            "v1_0_comparison": {
                "v1_0_total_orders_same_window": 0,
                "note": "v1.0 produced ZERO orders on all 124 sessions with 8/8 fixtures "
                        "passing. This is the structural question v1.1 exists to answer.",
            },
        },
        "gross": {
            "sessions_with_material_gross": len(gross),
            "material_threshold": MATERIAL,
            "note_on_dust": (
                "Sessions whose gross is below the threshold hold only solver dust "
                "(order 1e-17 NAV weight) left by reductions that did not land on exactly "
                "zero. They are economically empty. Ratios are NOT computed for them: "
                "dividing by dust manufactures meaningless numbers, and that division is "
                "the very pathology the homogeneous constraint form exists to avoid."
            ),
            "min": min(gross) if gross else 0.0,
            "median": float(np.median(gross)) if gross else 0.0,
            "max": max(gross) if gross else 0.0,
            "note": "low gross is a REGISTERED INTENDED CONSEQUENCE, not a defect",
        },
        "sector_topology": {
            "min_active_sectors": min((r.active_sector_count for r in reports
                                       if r.gross_is_material), default=0),
            "max_active_sectors": max((r.active_sector_count for r in reports), default=0),
            "theory": ">= 5 sectors are required for ANY positive feasible portfolio "
                      "(20% sector-gross cap); reported counts use the frozen 1e-6 "
                      "reporting threshold",
        },
        "constraint_compliance": {
            "REGISTERED_MEASURE_division_free": {
                "max_homogeneous_violation": max(viol) if viol else 0.0,
                "limit": 1e-9,
                "note": (
                    "max over every homogeneous coupling row (expr - k*G <= 0) "
                    "re-evaluated on the REALIZED allocation. This -- not any ratio -- "
                    "attests compliance, and it is well-defined at G = 0."
                ),
            },
            "ratios_over_material_gross_days_only": {
                "days": len(mat),
                "max_sector_gross_ratio": max((r.max_sector_gross_ratio for r in mat),
                                              default=None),
                "max_sector_net_ratio": max((r.max_sector_net_ratio for r in mat),
                                            default=None),
                "max_abs_normalized_beta": max((abs(r.normalized_beta) for r in mat),
                                               default=None),
                "max_abs_normalized_net": max((abs(r.normalized_net) for r in mat),
                                              default=None),
            },
            "caps": {"sector_gross": 0.20, "sector_net": 0.05, "beta": 0.10, "net_drift": 0.05},
        },
        "solver": {
            "max_kkt_residual": max(kkt) if kkt else None,
            "kkt_residual_limit": 1e-8,
            "max_hessian_condition_number": max(kappa) if kappa else None,
            "hessian_condition_limit": 1e10,
            "lp_statuses_observed": sorted(
                ({r.lp1_status for r in reports} | {r.lp2_status for r in reports})
                - {None}
            ),
            "invalid_runs": 0,
        },
        "diagnostics": {
            "existing_position_over_entry_cap_days": sum(
                1 for r in reports if r.over_entry_cap_count > 0),
            "below_floor_existing_total": sum(
                r.excluded_mass.get("below_floor_existing_total_weight", 0.0)
                for r in reports),
            "below_floor_candidate_total": sum(
                r.excluded_mass.get("below_floor_candidate_total_weight", 0.0)
                for r in reports),
        },
        "days": [r.__dict__ for r in reports],
    }

    # ---- HARD GUARD: prohibited inspection must be impossible, not merely avoided ----
    for r in reports:
        for k in r.__dict__:
            assert not any(t in k.lower() for t in PROHIBITED), \
                f"PROHIBITED field leaked into the structural report: {k}"
    for k in summary:
        assert not any(t in k.lower() for t in ("pnl", "sharpe", "drawdown", "hit_rate")), \
            f"PROHIBITED field leaked into the structural report: {k}"

    out = os.environ.get(
        "MR002_SLICE_OUT",
        "/out/MR002_StructuralSlice_v1.1.json",
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")

    print(json.dumps({k: summary[k] for k in
                      ("executability", "gross", "sector_topology",
                       "constraint_compliance", "solver", "diagnostics")}, indent=2))
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
