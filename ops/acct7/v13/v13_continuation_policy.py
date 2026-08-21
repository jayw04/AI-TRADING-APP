"""Transition Protocol v2 - the stage-continuation policy, in ONE place.

Owner rulings 2026-08-21. This module is imported BY MODULE NAME by both the planner
(which RESOLVES the policy into the hashed manifest, so the owner approves the rule
together with the orders it governs) and the executor (which RE-DERIVES it and refuses a
manifest whose resolved block disagrees). Keeping one implementation is the point: a
planner and an executor that each computed the rule separately could drift, and the
manifest would then record a policy the executor did not apply.

THE QUESTION THIS ANSWERS
-------------------------
Not "is this individual order safe to submit?" - the order-level gates answer that and are
untouched here. This module answers only the second question: "does the failure of this
individual order make continuing the whole transition unsafe?"

An order refused by a gate is NEVER force-submitted by anything in this file. The policy
decides continuation, and nothing else.

EVALUATION ORDER (limits v7 continuation_policy.evaluation_order)
    1. HARD failure          -> halt. No budget, no tolerance; one is enough.
    2. completeness_required -> halt if any logical order failed. JOINT-CONSTRUCTION
       STAGES ONLY (v2.1): a stage whose legs are sized against one another, which in
       v2.1 is B_cross_asset alone.
    3. residual budget       -> halt if the stage residual exceeds the budget.
    4. absolute backstop     -> halt if too many logical orders failed.
    5. count rule            -> mode residual_budget_and_count only.
    (6. stage timeout is evaluated by the executor, which owns the clock.)

COUNTING UNIT
    FAILED LOGICAL ORDERS, never attempt records. One order x two failed attempts is ONE
    failed order. Executor v7 counted attempt records against an order-count denominator
    and, with K=2, halted any stage of any size at two failing orders.
"""
import math

STAGES = ["A_exits", "B_cross_asset", "C_equity"]
STAGE_KEY = {"A_exits": "stage_A_exits",
             "B_cross_asset": "stage_B_cross_asset",
             "C_equity": "stage_C_equity_entries"}

POLICY_VERSION = "v2.1"
COUNTING_UNIT = "failed_logical_orders"
MODES = {"residual_budget", "residual_budget_and_count"}


class PolicyError(ValueError):
    """The limits file does not carry a usable continuation policy."""


def _cp(limits):
    cp = limits.get("continuation_policy")
    if not cp:
        raise PolicyError(
            "limits lack continuation_policy - that is limits v5 or earlier; "
            "regenerate against limits v6")
    if cp.get("version") != POLICY_VERSION:
        raise PolicyError("continuation_policy.version is %r, expected %r"
                          % (cp.get("version"), POLICY_VERSION))
    if cp.get("counting_unit") != COUNTING_UNIT:
        raise PolicyError(
            "continuation_policy.counting_unit is %r, expected %r. Counting attempt "
            "records instead of logical orders is the D1 defect this policy exists to fix."
            % (cp.get("counting_unit"), COUNTING_UNIT))
    # Validate the WHOLE required shape here rather than letting a missing key surface as a
    # KeyError deep inside resolve(). Callers turn PolicyError into a refusal; a KeyError
    # escapes as an unhandled crash, which is not a fail-closed outcome.
    for req in ("residual_budget", "concentration_trigger", "per_stage", "precedence_rule",
                "failure_taxonomy", "evaluation_order"):
        if req not in cp:
            raise PolicyError(
                "continuation_policy lacks %r - that is limits v6 or earlier, or a "
                "truncated policy; regenerate against limits v7" % req)
    for stage_key in STAGE_KEY.values():
        per = cp["per_stage"].get(stage_key)
        if per is None:
            raise PolicyError("continuation_policy.per_stage lacks %r" % stage_key)
        if "joint_construction" not in per:
            raise PolicyError(
                "continuation_policy.per_stage.%s lacks joint_construction - that is the "
                "v2.0 shape, in which concentration-triggered completeness applied to every "
                "stage and a collapsed Stage A was zero-tolerance; regenerate against "
                "limits v7" % stage_key)
    return cp


def effective_budget_usd(limits, equity):
    """max(R_ABS, R_PCT x equity). R_PCT is 0.0 in v2.0 by owner ruling."""
    rb = _cp(limits)["residual_budget"]
    return round(max(float(rb["R_ABS_usd"]), float(rb["R_PCT_equity"]) * float(equity)), 2)


def concentration(orders):
    """largest single order notional / total stage notional, and who it is."""
    vals = [(abs(float(o.get("est_notional") or 0.0)), o.get("symbol")) for o in orders]
    total = sum(v for v, _ in vals)
    if not vals or total <= 0:
        return 0.0, None, 0.0, round(total, 2)
    top, sym = max(vals)
    return round(top / total, 6), sym, round(top, 2), round(total, 2)


def resolve_stage(limits, stage, orders, equity):
    cp = _cp(limits)
    per = cp["per_stage"][STAGE_KEY[stage]]
    mode = per["mode"]
    if mode not in MODES:
        raise PolicyError("unknown continuation mode %r for %s" % (mode, stage))
    share, sym, top_usd, total_usd = concentration(orders)
    trigger = float(cp["concentration_trigger"]["threshold"])
    n = len(orders)
    # v2.1 (owner ruling 2026-08-21, second ruling). Concentration-triggered completeness
    # applies ONLY to joint-construction stages. Under v2.0 it was declared for all three,
    # so a Stage A that collapsed to one or two residual exits became completeness-required
    # and zero-tolerance again - the exact stage-denominator pathology Protocol v2 exists to
    # remove, re-entering through the new mechanism. A one-order Stage A halted on a $124.47
    # residual, half the budget, purely because one order is mathematically 100% of its own
    # stage. Exits are independent of one another: a refused exit leaves one measurable
    # legacy position, it does not make the remaining exits a different plan.
    # The SHARE is still measured and disclosed for every stage; only the consequence is scoped.
    joint = bool(per.get("joint_construction", False))
    # An EMPTY stage is not "concentrated"; it is simply nothing to do.
    completeness = joint and bool(n) and share >= trigger
    budget = effective_budget_usd(limits, equity)
    backstop = int(per["backstop_failed_orders"])
    pct = per.get("pct_of_stage_orders")
    floor = per.get("floor_orders")

    if completeness:
        max_failed = 0
    else:
        max_failed = backstop
        if mode == "residual_budget_and_count":
            allowed = max(int(floor or 0), math.floor(float(pct) * n))
            max_failed = min(max_failed, allowed)

    return {
        "stage": stage,
        "mode": mode,
        "counting_unit": COUNTING_UNIT,
        "stage_order_count": n,
        "stage_notional_usd": total_usd,
        "largest_order_symbol": sym,
        "largest_order_notional_usd": top_usd,
        "largest_order_share_of_stage": share,
        "concentration_trigger": trigger,
        "joint_construction": joint,
        "concentration_completeness_applies": joint,
        "completeness_required": completeness,
        "completeness_reason": (
            ("largest single order %s is %.1f%% of the stage, at or above the %.0f%% "
             "concentration trigger, and this stage is JOINT-CONSTRUCTION: its legs are "
             "sized against one another, so a partial stage is a DIFFERENT allocation, "
             "not a smaller one"
             % (sym, share * 100, trigger * 100)) if completeness else None),
        "completeness_not_applicable_reason": (
            None if joint else
            ("this stage is not joint-construction, so concentration never makes it "
             "completeness-required (owner ruling 2026-08-21). Its largest order is %s at "
             "%.1f%% of the stage, recorded for observability only."
             % (sym, share * 100))),
        "effective_budget_usd": budget,
        "backstop_failed_orders": backstop,
        "pct_of_stage_orders": pct,
        "floor_orders": floor,
        "max_failed_orders_before_halt": max_failed,
        "count_rule_allowed_failed_orders": (
            max(int(floor or 0), math.floor(float(pct) * n))
            if (mode == "residual_budget_and_count" and n) else None),
    }


def resolve(limits, orders, equity, stages=STAGES):
    """The block the planner embeds in the hashed manifest body."""
    by_stage = {s: [o for o in orders if o.get("stage") == s] for s in stages}
    return {
        "policy_version": POLICY_VERSION,
        "counting_unit": COUNTING_UNIT,
        "equity_at_plan": round(float(equity), 2),
        "residual_budget_usd": effective_budget_usd(limits, equity),
        "R_PCT_equity": float(_cp(limits)["residual_budget"]["R_PCT_equity"]),
        "concentration_trigger": float(_cp(limits)["concentration_trigger"]["threshold"]),
        "concentration_applies_to": sorted(
            k for k, s in _cp(limits)["per_stage"].items() if s.get("joint_construction")),
        "evaluation_order": list(_cp(limits)["evaluation_order"]),
        "precedence_rule": _cp(limits)["precedence_rule"]["ruling"],
        "stages": {s: resolve_stage(limits, s, by_stage[s], equity) for s in stages},
        "reviewer_note": (
            "This block is the CONTINUATION RULE, resolved at plan time so it is reviewed "
            "and hash-approved together with the orders it governs. The executor "
            "re-derives it from the sealed limits and refuses any manifest whose resolved "
            "block disagrees, so this is a disclosure, never a source of authority."),
    }


def evaluate(pol, *, failed_orders, failed_symbols, stage_residual_usd, hard_failures=0):
    """Decide continuation for ONE stage. Returns (ok, clause, detail).

    `pol` is one entry of resolve()["stages"]. Pure: no I/O, no clock, no broker.
    """
    if hard_failures:
        return (False, "hard_failure",
                "%d HARD/system failure(s) in %s - immediate halt regardless of "
                "economics; a hard failure never receives a residual budget"
                % (hard_failures, pol["stage"]))

    if pol["completeness_required"] and failed_orders > 0:
        return (False, "completeness_required",
                "%s is completeness-required and %d logical order(s) failed (%s). %s"
                % (pol["stage"], failed_orders, ", ".join(failed_symbols) or "-",
                   pol["completeness_reason"]))

    if stage_residual_usd > pol["effective_budget_usd"]:
        return (False, "residual_budget",
                "%s cumulative residual $%.2f exceeds the $%.2f budget (%d failed order(s): %s)"
                % (pol["stage"], stage_residual_usd, pol["effective_budget_usd"],
                   failed_orders, ", ".join(failed_symbols) or "-"))

    if failed_orders > pol["backstop_failed_orders"]:
        return (False, "backstop_failed_orders",
                "%s has %d failed logical order(s) (%s), over the absolute backstop of %d - "
                "many small stale names must not pass merely because the total notional is small"
                % (pol["stage"], failed_orders, ", ".join(failed_symbols) or "-",
                   pol["backstop_failed_orders"]))

    if pol["mode"] == "residual_budget_and_count":
        allowed = pol["count_rule_allowed_failed_orders"]
        if allowed is not None and failed_orders > allowed:
            return (False, "count_rule",
                    "%s has %d failed logical order(s) (%s), over the allowed %d "
                    "(max of floor %s and %.0f%% of %d orders)"
                    % (pol["stage"], failed_orders, ", ".join(failed_symbols) or "-",
                       allowed, pol["floor_orders"], float(pol["pct_of_stage_orders"]) * 100,
                       pol["stage_order_count"]))

    # Every applicable condition above has been evaluated and none binds. No rule is
    # subordinate to or disabled by another; the first binding one would have named the halt.
    return (True, None,
            "%s admissible: %d failed logical order(s) (backstop %s%s), residual $%.2f of "
            "$%.2f budget"
            % (pol["stage"], failed_orders, pol["backstop_failed_orders"],
               ("" if pol["count_rule_allowed_failed_orders"] is None
                else ", count rule %d" % pol["count_rule_allowed_failed_orders"]),
               stage_residual_usd, pol["effective_budget_usd"]))
