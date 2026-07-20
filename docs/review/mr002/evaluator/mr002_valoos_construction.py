"""MR-002 Increment 3 — deterministic portfolio construction (synthetic only).

Consumes validated candidates (eligibility + registered z + registered 1/sigma) and produces the
INTENDED_TARGET book by the frozen §5 algorithm: side-eligible selection (PR-18/PR-19), inverse-vol
weighting normalized within side (PR-03/PR-04/PR-05), entry dollar-neutral side sizing (PR-06/PR-07),
then the registered reduction cascade position cap -> sector caps -> beta limit (PR-11) with
smallest-|z| removal (PR-12), signal-age/permanent-id tie-breaks (PR-13), NO upward renormalization
and freed capacity -> cash (PR-14). Position cap is a per-name CLIP (excess -> cash); sector/beta are
enforced by removal. Computes no residual/z/sigma.
"""

from __future__ import annotations

import math

from mr002_valoos_exposure import snapshot, worsened_or_new_violations
from mr002_valoos_portfolio_identity import POSITION_CAP_NAV, SIDE_GROSS_CAP


def _select_side(pool: list, side: str, z_entry: float) -> list:
    """Side-eligible selection: bottom/top 10% of the side-eligible z pool AND |z| >= Z_entry."""
    if not pool:
        return []
    k = max(1, math.ceil(0.10 * len(pool)))                 # bottom/top 10% (>=1)
    if side == "long":
        extreme = sorted(pool, key=lambda c: (c.registered_signal_value, c.permanent_security_id))[:k]
        thresh = [c for c in pool if c.registered_signal_value <= -z_entry]
    else:
        extreme = sorted(pool, key=lambda c: (-c.registered_signal_value, c.permanent_security_id))[:k]
        thresh = [c for c in pool if c.registered_signal_value >= z_entry]
    ext_ids = {c.candidate_id for c in extreme}
    return [c for c in thresh if c.candidate_id in ext_ids]


def _size_book(selected: list, nav: float) -> dict:
    """Weights within side (normalized 1/sigma) -> entry-neutral side gross -> per-name position-cap
    clip (excess -> cash). Returns legs, intended orders, raw targets, and cash freed by the cap."""
    longs = [c for c in selected if c.side == "long"]
    shorts = [c for c in selected if c.side == "short"]
    # entry dollar-neutrality: min(feasible long, feasible short, 50% NAV); no book if a side is empty
    feasible_long = SIDE_GROSS_CAP * nav if longs else 0.0
    feasible_short = SIDE_GROSS_CAP * nav if shorts else 0.0
    side_gross = min(feasible_long, feasible_short)
    legs, intended, raw, cash_from_cap = [], [], [], 0.0
    for side_list in (longs, shorts):
        tot = sum(c.inverse_vol_weight for c in side_list)
        for c in side_list:
            w = (c.inverse_vol_weight / tot) if tot > 0 else 0.0
            target_notional = w * side_gross
            raw.append({"candidate_id": c.candidate_id, "side": c.side, "symbol": c.symbol,
                        "z": c.registered_signal_value, "raw_inverse_vol_weight": c.inverse_vol_weight,
                        "normalized_weight": w, "raw_notional": target_notional,
                        "sector_id": c.sector_id, "beta": c.beta})
            capped_notional = min(target_notional, POSITION_CAP_NAV * nav)     # PR-08 clip
            cash_from_cap += target_notional - capped_notional                 # excess -> cash (no renorm)
            shares = int(capped_notional // c.official_next_open_price)        # whole shares
            filled_notional = shares * c.official_next_open_price
            binding = "position_cap" if capped_notional < target_notional else None
            legs.append({"symbol": c.symbol, "side": c.side, "notional": filled_notional,
                         "sector_id": c.sector_id, "beta": c.beta})
            intended.append({"candidate_id": c.candidate_id, "symbol": c.symbol, "side": c.side,
                             "intended_shares": shares, "intended_notional": filled_notional,
                             "target_weight": w, "official_next_open_price": c.official_next_open_price,
                             "sector_id": c.sector_id, "beta": c.beta, "binding_constraint": binding,
                             "permanent_security_id": c.permanent_security_id,
                             "signal_origin_session": c.signal_origin_session,
                             "registered_signal_value": c.registered_signal_value})
    return {"legs": legs, "intended": intended, "raw_targets": raw, "cash_from_cap": cash_from_cap,
            "side_gross_target": side_gross}


def removal_victim(orders: list):
    """PR-12/PR-13 removal key: smallest |z|, tie -> older signal (smaller signal_origin_session),
    tie -> permanent_security_id lexical byte ordering."""
    return min(orders, key=lambda o: (abs(o["registered_signal_value"]), o["signal_origin_session"],
                                      o["permanent_security_id"]))


def _legs(orders: list) -> list:
    return [{"symbol": o["symbol"], "side": o["side"], "notional": o["intended_notional"],
             "sector_id": o["sector_id"], "beta": o["beta"]} for o in orders]


def build_intended_target(candidates: list, nav: float, occupied: set, held_legs=None) -> dict:
    """Held-aware frozen construction (Increment-3 v1.1). `occupied` = symbols held or pending
    (PR-02/PR-21); `held_legs` = the provisional post-exit held book marked at session opens (its
    exposure is the pre-existing BASELINE). Weights computed ONCE (PR-05). The cascade constrains the
    TOTAL held+new book and removes the smallest-|z| NEW candidate (freed -> cash, no upward
    renormalization, PR-14) whenever a new entry would create or WORSEN a hard-cap breach vs baseline
    (numeric grandfathering). Emits RAW_TARGET evidence + ConstraintDecision records."""
    held_legs = held_legs or []
    baseline = snapshot("HELD_BASELINE", held_legs, nav)
    config = candidates[0].configuration_id if candidates else None
    from mr002_valoos_portfolio_identity import Z_ENTRY
    z_entry = Z_ENTRY[config] if config else 0.0
    eligible = [c for c in candidates if c.eligibility_status == "ELIGIBLE" and c.symbol not in occupied]
    selected = _select_side([c for c in eligible if c.side == "long"], "long", z_entry) + \
        _select_side([c for c in eligible if c.side == "short"], "short", z_entry)
    book = _size_book(selected, nav)                      # weights fixed here; removal never re-runs this

    # RAW_TARGET (pre-constraint) exposure evidence + the position-cap ConstraintDecisions
    raw_legs = [{"symbol": r["symbol"], "side": r["side"], "notional": r["raw_notional"],
                 "sector_id": r["sector_id"], "beta": r["beta"]} for r in book["raw_targets"]]
    raw_snapshot = snapshot("RAW_TARGET", raw_legs, nav)
    constraint_decisions = []
    for o in book["intended"]:
        raw_n = next(r["raw_notional"] for r in book["raw_targets"] if r["candidate_id"] == o["candidate_id"])
        if o["intended_notional"] < raw_n:
            constraint_decisions.append({"constraint": "per_name", "stage": "INTENDED", "subject": o["symbol"],
                                         "raw_value": raw_n, "construction_constrained_value": o["intended_notional"],
                                         "binding_rule": "position_cap", "removed_or_clipped_amount": raw_n - o["intended_notional"]})

    active = list(book["intended"])
    removal_events, cash_from_removal = [], 0.0
    while True:
        snap = snapshot("INTENDED_TARGET", held_legs + _legs(active), nav)
        viol = worsened_or_new_violations(baseline, snap, realized=False)
        removable = [v for v in viol if "SECTOR_CONSTRAINT" in v[0] or "BETA_CONSTRAINT" in v[0] or "GROSS_CONSTRAINT" in v[0]]
        if not removable or not active:
            return {"legs": _legs(active), "intended": active, "raw_targets": book["raw_targets"],
                    "raw_target_exposure": raw_snapshot, "baseline_exposure": baseline,
                    "cash_from_cap": book["cash_from_cap"], "cash_from_removal": cash_from_removal,
                    "side_gross_target": book["side_gross_target"], "exposure": snap,
                    "constraint_decisions": constraint_decisions, "removal_events": removal_events,
                    "residual_intended_violations": viol, "config_id": config, "z_entry": z_entry}
        victim = removal_victim(active)                   # freed capacity -> cash; NO renormalization
        cash_from_removal += victim["intended_notional"]
        removal_events.append({"removed_candidate_id": victim["candidate_id"], "reason": "SMALLEST_ABS_Z",
                               "z": victim["registered_signal_value"],
                               "signal_origin_session": victim["signal_origin_session"],
                               "permanent_security_id": victim["permanent_security_id"],
                               "binding_violation": removable[0][0]})
        constraint_decisions.append({"constraint": removable[0][0], "stage": "INTENDED",
                                     "subject": removable[0][1], "binding_rule": "removal",
                                     "removed_candidate_id": victim["candidate_id"]})
        active = [o for o in active if o["candidate_id"] != victim["candidate_id"]]
