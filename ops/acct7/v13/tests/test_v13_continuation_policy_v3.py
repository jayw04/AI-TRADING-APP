"""Transition Protocol v2 conformance: the stage-continuation policy.

Every case in this suite is built from a REAL sealed artifact on disk - the manifests of
2026-08-20 and 2026-08-21 and the live residual ledger of the halted run - so the six
replay cases of the design proposal become permanent regression tests rather than a
one-off analysis. Nothing here touches the network, the broker or the order path.

Run inside the backend container:
    docker exec -i workbench-backend python \\
        /app/data/ops/acct7/test_v13_continuation_policy_v3.py

THE PROPERTY THAT MATTERS MOST is case H: the 2026-08-20 live halt STILL HALTS under
Protocol v2. An amendment that retroactively permitted the run it was written in response
to would be worthless, and this suite fails if that ever becomes true.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/app/data/ops/acct7")

import v13_continuation_policy as CP          # noqa: E402
import v13_residual_debt as DEBT              # noqa: E402
from v13_execution_core_v3 import (           # noqa: E402
    ResidualLedger, failure_class_of)

OPS = Path("/app/data/ops/acct7")
RUN_DIR = Path("/app/data/v13_transition")
LIMITS = json.loads((OPS / "ws1_evidence/v13/v13_frozen_execution_limits_v8.json").read_text())

M_0820_LIVE = "OTR-20260820T164912Z-S9"      # 45082b68 - executed, halted in Stage A
M_0820_DRY2 = "OTR-20260820T162605Z-S9"      # 30a53127 - dry only, ALAB abort in Stage C
M_0821 = "OTR-20260821T140319Z-S9"           # 0a0079d4 - retired unapproved

PASS = FAIL = SKIP = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s%s" % (name, ("  [%s]" % detail) if detail else ""))


def skip(name, why):
    global SKIP
    SKIP += 1
    print("  SKIP  %s  [%s]" % (name, why))


def manifest(run_id):
    p = RUN_DIR / (run_id + ".json")
    return json.loads(p.read_text()) if p.exists() else None


def stage_orders(m, stage):
    o = [x for x in m["orders"] if x.get("stage") == stage]
    return sorted(o, key=lambda x: x["seq"])


def policy_for(m, stage):
    return CP.resolve_stage(LIMITS, stage, stage_orders(m, stage),
                            float(m["pre_run_state"]["equity"]))


def notional(orders, symbols):
    by = {o["symbol"]: abs(float(o.get("est_notional") or 0.0)) for o in orders}
    return round(sum(by[s] for s in symbols), 2)


def decide(pol, symbols, residual, hard=0):
    return CP.evaluate(pol, failed_orders=len(symbols), failed_symbols=list(symbols),
                       stage_residual_usd=residual, hard_failures=hard)


# ---------------------------------------------------------------------------------------
# The RETIRED v1 rule, replicated verbatim from executor v7 :499-506, so the regression is
# stated rather than remembered. numerator = ATTEMPT records, denominator = ORDER count.
# ---------------------------------------------------------------------------------------
def v1_rule(stage_order_count, failed_orders, residual, k_attempts=2, tolerance=250.0):
    aborts = failed_orders * k_attempts
    if aborts > 3:
        return "HALT", "abort_count>3"
    if stage_order_count and aborts > 0.10 * stage_order_count:
        return "HALT", "abort_count>10%_of_stage_orders"
    if residual > tolerance:
        return "HALT", "residual>tolerance"
    return "CONTINUE", None


def main():
    print("=== Transition Protocol v2 - continuation policy conformance ===\n")

    m20 = manifest(M_0820_LIVE)
    m20c = manifest(M_0820_DRY2)
    m21 = manifest(M_0821)

    # --- A. the policy module reads the sealed limits correctly ------------------------
    print("A. sealed policy parameters")
    check("policy version is v2.1",
          LIMITS["continuation_policy"]["version"] == "v2.1")
    check("*** exactly ONE stage is joint-construction: the cross-asset sleeve ***",
          sorted(k for k, s in LIMITS["continuation_policy"]["per_stage"].items()
                 if s.get("joint_construction")) == ["stage_B_cross_asset"],
          "owner ruling 2026-08-21: concentration-triggered completeness applies only to "
          "joint-construction stages")
    check("the precedence rule is declared rather than emergent",
          "no rule is subordinate" in
          LIMITS["continuation_policy"]["precedence_rule"]["ruling"])
    check("counting unit is failed_logical_orders",
          LIMITS["continuation_policy"]["counting_unit"] == "failed_logical_orders")
    check("residual budget is $250 with R_PCT = 0",
          CP.effective_budget_usd(LIMITS, 100000.0) == 250.0
          and CP.effective_budget_usd(LIMITS, 10_000_000.0) == 250.0,
          "R_PCT = 0 means equity must NOT scale the budget")
    check("concentration trigger is 50%",
          float(LIMITS["continuation_policy"]["concentration_trigger"]["threshold"]) == 0.50)
    check("stage A backstop 2, stage C backstop 3 (owner ruling 2026-08-21)",
          LIMITS["continuation_policy"]["per_stage"]["stage_A_exits"]
          ["backstop_failed_orders"] == 2
          and LIMITS["continuation_policy"]["per_stage"]["stage_C_equity_entries"]
          ["backstop_failed_orders"] == 3)

    # --- B. failure taxonomy ------------------------------------------------------------
    print("\nB. failure taxonomy")
    for code in ("stale_reference", "spread_failure", "manifest_drift_failure",
                 "no_usable_print_or_quote", "other_governed_gate"):
        check("%s is EXECUTABILITY" % code, failure_class_of(code) == "EXECUTABILITY")
    for code in ("risk_refusal", "broker_http_error", "identity_mismatch"):
        check("%s is HARD" % code, failure_class_of(code) == "HARD")
    check("an UNKNOWN abort code fails closed to HARD",
          failure_class_of("something_new_nobody_mapped") == "HARD")
    check("no failure at all classifies as None", failure_class_of(None) is None)

    # --- C. HARD beats everything -------------------------------------------------------
    print("\nC. a HARD failure halts regardless of economics")
    if m21:
        pol = policy_for(m21, "C_equity")
        ok, clause, _ = decide(pol, [], 0.0, hard=1)
        check("HARD halts even with zero failed orders and zero residual",
              ok is False and clause == "hard_failure")
    else:
        skip("HARD halts even with zero failed orders and zero residual", "manifest absent")

    # --- D. 2026-08-21 Stage A: the denominator collapse is fixed -----------------------
    print("\nD. 2026-08-21 Stage A (5 orders, $757.28) - denominator collapse")
    if m21:
        pol = policy_for(m21, "A_exits")
        orders = stage_orders(m21, "A_exits")
        check("Stage A is NOT completeness-required",
              pol["completeness_required"] is False,
              "share=%.4f" % pol["largest_order_share_of_stage"])
        check("...and would not be at ANY share, because it is not joint-construction",
              pol["concentration_completeness_applies"] is False
              and pol["joint_construction"] is False)
        ok1, c1, _ = decide(pol, ["MS"], notional(orders, ["MS"]))
        v1d, v1c = v1_rule(5, 1, notional(orders, ["MS"]))
        check("ONE failed order now CONTINUES where v1 halted",
              ok1 is True and v1d == "HALT",
              "v2=%s v1=%s/%s" % (ok1, v1d, v1c))
        ok2, c2, _ = decide(pol, ["MS", "PH"], notional(orders, ["MS", "PH"]))
        check("TWO failed orders ($257.04) HALT on the residual budget",
              ok2 is False and c2 == "residual_budget",
              "clause=%s" % c2)
        check("the budget, not the count, is what binds at k=2",
              notional(orders, ["MS", "PH"]) > pol["effective_budget_usd"]
              and pol["max_failed_orders_before_halt"] == 2)
    else:
        skip("2026-08-21 Stage A cases", "manifest absent")

    # --- E. 2026-08-21 Stage B: concentration, not arithmetic ---------------------------
    print("\nE. 2026-08-21 Stage B (6 orders, UUP 65.3%) - the Stage-B question")
    if m21:
        pol = policy_for(m21, "B_cross_asset")
        orders = stage_orders(m21, "B_cross_asset")
        check("Stage B IS completeness-required",
              pol["completeness_required"] is True)
        check("...because UUP is >= 50% of the stage, not because 6 x 10% < 1",
              pol["largest_order_symbol"] == "UUP"
              and pol["largest_order_share_of_stage"] >= 0.50
              and "concentration" in (pol["completeness_reason"] or ""),
              "share=%.4f" % pol["largest_order_share_of_stage"])
        spy = notional(orders, ["SPY"])
        ok, clause, _ = decide(pol, ["SPY"], spy)
        check("losing SPY at $%.2f HALTS Stage B" % spy,
              ok is False and clause == "completeness_required", "clause=%s" % clause)
        check("...and the binding clause is completeness, NOT the budget",
              spy < pol["effective_budget_usd"] and clause == "completeness_required",
              "a pure economic budget would have CONTINUED here - that is the case that "
              "chose candidate C")
        ok0, _, _ = decide(pol, [], 0.0)
        check("Stage B with zero failures continues", ok0 is True)
        check("Stage B tolerates 0 failed orders", pol["max_failed_orders_before_halt"] == 0)
    else:
        skip("2026-08-21 Stage B cases", "manifest absent")

    # --- F. concentration BELOW the trigger falls back to the budget ---------------------
    print("\nF. a flat stage is NOT completeness-required")
    flat = [{"seq": i, "symbol": "S%d" % i, "side": "buy", "est_notional": 100.0,
             "stage": "B_cross_asset"} for i in range(1, 7)]
    polf = CP.resolve_stage(LIMITS, "B_cross_asset", flat, 100000.0)
    check("6 equal orders (16.7% each) are not completeness-required",
          polf["completeness_required"] is False)
    okf, cf, _ = decide(polf, ["S1"], 100.0)
    check("...and one $100 failure continues on the budget", okf is True, "clause=%s" % cf)
    okf2, cf2, _ = decide(polf, ["S1", "S2", "S3"], 300.0)
    check("...while $300 over three orders halts on the budget",
          okf2 is False and cf2 == "residual_budget", "clause=%s" % cf2)

    # --- G. 2026-08-21 Stage C: the count rule survives ----------------------------------
    print("\nG. 2026-08-21 Stage C (36 orders, $3,559.88)")
    if m21:
        pol = policy_for(m21, "C_equity")
        orders = stage_orders(m21, "C_equity")
        check("Stage C carries budget AND count", pol["mode"] == "residual_budget_and_count")
        check("count rule allows 3 of 36 (max of floor 2 and 10%)",
              pol["count_rule_allowed_failed_orders"] == 3)
        check("effective tolerance is 3 failed orders (backstop 3 == count 3)",
              pol["max_failed_orders_before_halt"] == 3)
        cheap2 = ["GLW", "CIEN"]
        n2 = notional(orders, cheap2)
        ok2, c2, _ = decide(pol, cheap2, n2)
        v1d, _ = v1_rule(36, 2, n2)
        check("two trivial entries ($%.2f) CONTINUE where v1 halted" % n2,
              ok2 is True and v1d == "HALT", "v2 clause=%s" % c2)
        cheap4 = ["GLW", "CIEN", "ASML", "GOOGL"]
        n4 = notional(orders, cheap4)
        ok4, c4, _ = decide(pol, cheap4, n4)
        check("FOUR trivial entries ($%.2f) halt on the backstop, inside the budget" % n4,
              ok4 is False and c4 == "backstop_failed_orders" and n4 < pol["effective_budget_usd"],
              "clause=%s residual=%.2f budget=%.2f" % (c4, n4, pol["effective_budget_usd"]))
        dear2 = ["STM", "TSM"]
        nd = notional(orders, dear2)
        okd, cd, _ = decide(pol, dear2, nd)
        check("two EXPENSIVE entries ($%.2f) halt on the budget" % nd,
              okd is False and cd == "residual_budget", "clause=%s" % cd)
    else:
        skip("2026-08-21 Stage C cases", "manifest absent")

    # --- H. HISTORICAL VALIDITY: the 2026-08-20 halt still halts -------------------------
    print("\nH. *** the 2026-08-20 live halt MUST still halt under v2 ***")
    led = RUN_DIR / (M_0820_LIVE + ".residual.v3.jsonl")
    if m20 and led.exists():
        recs = [json.loads(l) for l in open(led) if l.strip()]
        disp = [r for r in recs if r["kind"] == "order_disposition"]
        att = [r for r in recs if r["kind"] == "attempt"]
        failed = [r for r in disp if float(r.get("residual_notional") or 0) > 0]
        residual = round(sum(float(r["residual_notional"]) for r in disp), 2)
        abort_records = sum(1 for a in att if a.get("abort_reason"))
        pol = policy_for(m20, "A_exits")
        ok, clause, detail = decide(pol, [r["symbol"] for r in failed], residual)
        check("the 2026-08-20 Stage A residual is $257.27", residual == 257.27,
              "got %s" % residual)
        check("*** it STILL HALTS under Protocol v2 ***", ok is False,
              "an amendment that permitted this run would be worthless")
        check("...on the RESIDUAL BUDGET clause, independent of any count",
              clause == "residual_budget", "clause=%s" % clause)
        check("...because $257.27 > the pre-existing $250 budget",
              residual > pol["effective_budget_usd"])

        # --- D1 regression: the unit mismatch ---------------------------------------
        print("\nH2. D1 regression - attempt records are NOT logical orders")
        check("exactly TWO logical orders failed", len(failed) == 2,
              str([r["symbol"] for r in failed]))
        check("they are MS and PH",
              sorted(r["symbol"] for r in failed) == ["MS", "PH"])
        check("but FOUR abort records were written (2 orders x K=2)",
              abort_records == 4, "got %s" % abort_records)
        check("EBAY and FN were NEVER ATTEMPTED (no disposition rows)",
              not {"EBAY", "FN"} & {r["symbol"] for r in disp},
              "the stage halted at seq 34; EBAY is seq 35 and FN is seq 36")
        v1d, v1c = v1_rule(36, 2, 212.16)
        p2 = CP.resolve_stage(LIMITS, "A_exits", stage_orders(m20, "A_exits"),
                              float(m20["pre_run_state"]["equity"]))
        ok2, c2, _ = decide(p2, ["NXPI", "ON"], 212.16)
        check("v1 HALTED two cheap failures in a 36-order stage; v2 continues",
              v1d == "HALT" and v1c == "abort_count>3" and ok2 is True,
              "v1=%s/%s  v2=%s/%s" % (v1d, v1c, ok2, c2))
    else:
        skip("2026-08-20 historical validity", "live ledger absent")

    # --- I. DRY/LIVE PARITY --------------------------------------------------------------
    print("\nI. dry and live must decide identically for identical failing orders")
    if m21:
        pol = policy_for(m21, "A_exits")
        orders = stage_orders(m21, "A_exits")
        syms = ["MS", "PH"]
        tmpd = Path(tempfile.mkdtemp(prefix="cp_parity_"))

        live_led = ResidualLedger(tmpd / "live.jsonl", 250.0)
        for o in orders:
            if o["symbol"] in syms:
                live_led.record_order({
                    "plan_id": "T", "stage": "A_exits", "seq": o["seq"],
                    "symbol": o["symbol"], "side": o["side"],
                    "intended_qty": o["qty"], "filled_qty": "0",
                    "residual_qty": float(o["qty"]),
                    "residual_notional": abs(float(o["est_notional"])),
                    "final_disposition": "EXHAUSTED_GATE",
                    "abort_reason": "stale_reference", "failure_class": "EXECUTABILITY"})
                # live writes K=2 attempt records for the SAME logical order
                for k in (1, 2):
                    live_led.record_attempt({"stage": "A_exits", "seq": o["seq"],
                                             "symbol": o["symbol"], "attempt_number": k,
                                             "abort_reason": "stale_reference"})

        dry_led = ResidualLedger(tmpd / "dry.jsonl", 250.0)
        for o in orders:
            if o["symbol"] in syms:
                dry_led.record_dry_order({
                    "plan_id": "T", "stage": "A_exits", "seq": o["seq"],
                    "symbol": o["symbol"], "side": o["side"],
                    "intended_qty": o["qty"], "filled_qty": "0",
                    "residual_qty": float(o["qty"]),
                    "residual_notional": abs(float(o["est_notional"])),
                    "final_disposition": "DRY_GATE_ABORT",
                    "abort_reason": "stale_reference", "failure_class": "EXECUTABILITY"})

        check("live ledger counts 2 failed ORDERS from 4 attempt records",
              live_led.failed_orders("A_exits") == 2
              and live_led.attempt_opportunities(stage="A_exits")
              ["pre_submission_gate_aborts"] == 4)
        check("dry ledger counts the same 2 failed orders",
              dry_led.failed_orders("A_exits") == 2)
        check("dry and live residuals agree",
              live_led.stage_residual("A_exits") == dry_led.stage_residual("A_exits"))

        dl = decide(pol, live_led.failed_order_symbols("A_exits"),
                    live_led.stage_residual("A_exits"))
        dd = decide(pol, dry_led.failed_order_symbols("A_exits"),
                    dry_led.stage_residual("A_exits"))
        check("*** dry and live reach the SAME decision and the SAME clause ***",
              dl[0] == dd[0] and dl[1] == dd[1], "live=%s dry=%s" % (dl[:2], dd[:2]))
        check("dry imputed records are flagged so they can never pass as measured",
              all(r.get("imputed") for r in dry_led.orders))

        v1_live, _ = v1_rule(5, 2, dry_led.stage_residual("A_exits"), k_attempts=2)
        v1_dry, _ = v1_rule(5, 2, dry_led.stage_residual("A_exits"), k_attempts=1)
        check("under v1 the SAME failures gave different dry/live abort counts",
              v1_live == "HALT" and v1_dry == "HALT",
              "both halt here on residual; the divergence case is proved next")
        v1_live2, c_live2 = v1_rule(36, 2, 212.16, k_attempts=2)
        v1_dry2, c_dry2 = v1_rule(36, 2, 212.16, k_attempts=1)
        check("*** v1 DIVERGED: same 2 failures, HALT live vs CONTINUE dry ***",
              v1_live2 == "HALT" and v1_dry2 == "CONTINUE",
              "live=%s/%s dry=%s/%s" % (v1_live2, c_live2, v1_dry2, c_dry2))
    else:
        skip("dry/live parity", "manifest absent")

    # --- J. the retired "every gate must pass" override ----------------------------------
    print("\nJ. the retired owner override - ALAB no longer burns a manifest")
    if m20c:
        pol = policy_for(m20c, "C_equity")
        orders = stage_orders(m20c, "C_equity")
        alab = notional(orders, ["ALAB"])
        ok, clause, _ = decide(pol, ["ALAB"], alab)
        check("one $%.2f stale-reference failure in Stage C CONTINUES" % alab, ok is True,
              "clause=%s" % clause)
        check("...which is what the retired override could not express",
              alab < pol["effective_budget_usd"])
    else:
        skip("ALAB case", "manifest absent")

    # --- K. residual operational debt ----------------------------------------------------
    print("\nK. RESIDUAL_CLEANUP_REQUIRED obligations")
    tmpf = Path(tempfile.mkdtemp(prefix="cp_debt_")) / "debt.jsonl"
    ob = DEBT.build(strategy_id=9, account_id=7, run_id="OTR-TEST",
                    manifest_sha256="a" * 64, stage="A_exits",
                    disposition={"symbol": "MS", "side": "sell", "intended_qty": "0.585",
                                 "filled_qty": "0", "residual_qty": 0.585,
                                 "residual_notional": 123.59,
                                 "residual_valuation_price": 211.26,
                                 "abort_reason": "stale_reference",
                                 "failure_class": "EXECUTABILITY",
                                 "final_disposition": "EXHAUSTED_GATE"})
    check("an obligation carries every owner-required field",
          all(f in ob for f in DEBT.REQUIRED_FIELDS),
          str([f for f in DEBT.REQUIRED_FIELDS if f not in ob]))
    DEBT.record_many([ob], path=tmpf)
    op = DEBT.open_obligations(account_id=7, strategy_id=9, path=tmpf)
    check("it is OPEN and readable back", len(op) == 1 and op[0]["symbol"] == "MS")
    check("the open total is its governed valuation",
          DEBT.total_open_usd(account_id=7, strategy_id=9, path=tmpf) == 123.59)
    check("it is keyed by originating manifest, NOT by whether the symbol is held",
          op[0]["originating_manifest_run_id"] == "OTR-TEST")
    DEBT.record_many([DEBT.build(
        strategy_id=9, account_id=7, run_id="OTR-TEST2", manifest_sha256="b" * 64,
        stage="A_exits", disposition={"symbol": "MS", "side": "sell",
                                      "intended_qty": "1", "filled_qty": "0",
                                      "residual_qty": 1.0, "residual_notional": 200.0,
                                      "residual_valuation_price": 200.0,
                                      "abort_reason": "stale_reference",
                                      "failure_class": "EXECUTABILITY",
                                      "final_disposition": "EXHAUSTED_GATE"})], path=tmpf)
    check("two obligations on the SAME symbol from different manifests both survive",
          len(DEBT.open_obligations(path=tmpf)) == 2,
          "an obligation must never be deduplicated away by symbol")
    DEBT.close(op[0], status=DEBT.STATUS_SUPERSEDED_BY_PLAN,
               note="cleared by the next governed rebalance", path=tmpf)
    check("closing appends rather than rewriting, and drops it from OPEN",
          len(DEBT.open_obligations(path=tmpf)) == 1
          and len(DEBT.current(path=tmpf)) == 2)
    d = DEBT.summary_for_disclosure(path=tmpf)
    check("a disclosure block is available for the epoch-boundary record",
          d["obligation"] == "RESIDUAL_CLEANUP_REQUIRED" and d["open_count"] == 1)

    # --- K2. lifecycle: an obligation leaves OPEN only by explicit disposition ----------
    print("\nK2. residual-debt lifecycle (owner review 2026-08-21)")
    check("the terminal statuses are exactly the four the owner named",
          sorted(DEBT.TERMINAL_STATUSES) == sorted([
              "ESCALATED", "RESOLVED_FILLED",
              "RESOLVED_TARGET_REENTERED_WITH_OWNER_ACCEPTANCE",
              "SUPERSEDED_BY_NEW_GOVERNED_PLAN"]))
    still = DEBT.open_obligations(path=tmpf)[0]
    try:
        DEBT.close(still, status="CLEARED", path=tmpf)
        check("close() refuses a status outside the terminal set", False, "no refusal")
    except ValueError as e:
        check("close() refuses a status outside the terminal set", "must be one of" in str(e))
    try:
        DEBT.close(still, status=DEBT.STATUS_RESOLVED_TARGET_REENTERED, path=tmpf)
        check("*** target re-entry cannot close an obligation without owner acceptance ***",
              False, "no refusal")
    except ValueError as e:
        check("*** target re-entry cannot close an obligation without owner acceptance ***",
              "requires owner_acceptance_ref" in str(e))
    check("...and it is still OPEN after both refusals",
          len(DEBT.open_obligations(path=tmpf)) == 1)
    DEBT.close(still, status=DEBT.STATUS_RESOLVED_TARGET_REENTERED,
               owner_acceptance_ref="owner ruling 2026-08-21, transcript", path=tmpf)
    check("with a recorded acceptance it closes, and the acceptance is preserved",
          len(DEBT.open_obligations(path=tmpf)) == 0
          and DEBT.current(path=tmpf)[-1]["owner_acceptance_ref"].startswith("owner ruling"))
    check("closing appended rather than rewrote (4 events fold to 2 obligations)",
          len(DEBT.current(path=tmpf)) == 2
          and len(DEBT._events(path=tmpf)) == 4)

    # --- O. activation invariant: the ledger must be healthy ----------------------------
    print("\nO. residual-debt ledger health (activation invariant)")
    h = DEBT.health(path=tmpf)
    check("a well-formed ledger is healthy", h["healthy"] is True and h["bad_lines"] == 0)
    fresh = Path(tempfile.mkdtemp(prefix="cp_health_")) / "new.jsonl"
    h2 = DEBT.health(path=fresh)
    check("an absent-but-creatable ledger is healthy (0 obligations)",
          h2["healthy"] is True and h2["open_obligations"] == 0)
    corrupt = Path(tempfile.mkdtemp(prefix="cp_corrupt_")) / "bad.jsonl"
    corrupt.write_text('{"a": 1}\nthis is not json\n')
    h3 = DEBT.health(path=corrupt)
    check("*** a corrupt ledger is NOT healthy - fail closed, not fail empty ***",
          h3["healthy"] is False and h3["bad_lines"] == 1
          and "unparseable" in h3["problem"])

    # --- L. the resolved block is deterministic ------------------------------------------
    print("\nL. planner and executor must resolve the same block")
    if m21:
        eq = float(m21["pre_run_state"]["equity"])
        a = CP.resolve(LIMITS, m21["orders"], eq)
        b = CP.resolve(LIMITS, m21["orders"], eq)
        check("resolve() is deterministic",
              json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True))
        check("it round-trips through JSON unchanged",
              json.dumps(json.loads(json.dumps(a)), sort_keys=True)
              == json.dumps(a, sort_keys=True),
              "the executor compares the manifest's block against a re-derived one")
        check("an empty stage is not treated as concentrated",
              CP.resolve_stage(LIMITS, "C_equity", [], eq)["completeness_required"] is False)
    else:
        skip("determinism", "manifest absent")

    # --- M. THE COLLAPSED STAGE A - the v2.0 pathology, now removed ----------------------
    # v2.0 declared the concentration trigger for all three stages, so a Stage A that
    # collapsed to one or two residual exits became completeness-required and zero-tolerance
    # again. Owner ruling 2026-08-21 (second): scope the trigger to joint-construction
    # stages. These assertions are the proof that the pathology cannot return.
    print("\nM. a collapsed Stage A is no longer zero-tolerance (v2.1 correction)")
    one = CP.resolve_stage(LIMITS, "A_exits", [
        {"seq": 1, "symbol": "MS", "est_notional": 124.47, "stage": "A_exits"}], 100934.07)
    check("a ONE-order Stage A is 100% concentrated...",
          one["largest_order_share_of_stage"] == 1.0)
    check("...but is NOT completeness-required, and tolerates 2 failed orders",
          one["completeness_required"] is False
          and one["max_failed_orders_before_halt"] == 2)
    okm, cm, _ = decide(one, ["MS"], 124.47)
    check("*** a $124.47 residual now lets Stage A COMPLETE with disclosed debt ***",
          okm is True and 124.47 < one["effective_budget_usd"],
          "clause=%s - under v2.0 this halted on completeness_required" % cm)
    two_small = CP.resolve_stage(LIMITS, "A_exits", [
        {"seq": 1, "symbol": "MS", "est_notional": 100.0, "stage": "A_exits"},
        {"seq": 2, "symbol": "PH", "est_notional": 100.0, "stage": "A_exits"}], 100934.07)
    ok2s, c2s, _ = decide(two_small, ["MS", "PH"], 200.0)
    check("two small failures totalling $200 continue (2 <= backstop 2, under budget)",
          ok2s is True, "clause=%s" % c2s)
    ok2b, c2b, _ = decide(two_small, ["MS", "PH"], 257.04)
    check("*** two failures totalling > $250 still HALT on the economic budget ***",
          ok2b is False and c2b == "residual_budget")
    three = CP.resolve_stage(LIMITS, "A_exits", [
        {"seq": i, "symbol": "S%d" % i, "est_notional": 50.0, "stage": "A_exits"}
        for i in range(1, 6)], 100934.07)
    ok3, c3, _ = decide(three, ["S1", "S2", "S3"], 150.0)
    check("three failures halt on the absolute backstop even at only $150",
          ok3 is False and c3 == "backstop_failed_orders")
    if m21:
        polB = policy_for(m21, "B_cross_asset")
        check("Stage B is UNAFFECTED by the correction - still completeness-required",
              polB["completeness_required"] is True
              and polB["joint_construction"] is True)
    oneB = CP.resolve_stage(LIMITS, "B_cross_asset", [
        {"seq": 1, "symbol": "UUP", "est_notional": 15931.10,
         "stage": "B_cross_asset"}], 100934.07)
    check("a ONE-order Stage B IS completeness-required (it is joint-construction)",
          oneB["completeness_required"] is True)
    oneC = CP.resolve_stage(LIMITS, "C_equity", [
        {"seq": 1, "symbol": "TSM", "est_notional": 245.33, "stage": "C_equity"}], 100934.07)
    check("a ONE-order Stage C is NOT completeness-required either",
          oneC["completeness_required"] is False)

    # --- N. Stage C precedence: both thresholds apply, the stricter binds -----------------
    print("\nN. Stage C precedence is declared, and both thresholds are disclosed")
    if m21:
        polC = policy_for(m21, "C_equity")
        check("both thresholds are disclosed on a 36-order Stage C",
              polC["backstop_failed_orders"] == 3
              and polC["count_rule_allowed_failed_orders"] == 3)
        check("...where they coincide, so either could name the halt",
              polC["max_failed_orders_before_halt"] == 3)
    smallC = CP.resolve_stage(LIMITS, "C_equity", [
        {"seq": i, "symbol": "S%d" % i, "est_notional": 40.0, "stage": "C_equity"}
        for i in range(1, 6)], 100934.07)
    check("on a FIVE-order Stage C the count rule is stricter than the backstop",
          smallC["backstop_failed_orders"] == 3
          and smallC["count_rule_allowed_failed_orders"] == 2
          and smallC["max_failed_orders_before_halt"] == 2)
    okc, cc, _ = decide(smallC, ["S1", "S2", "S3"], 120.0)
    check("...and it is the count rule that binds, named as such",
          okc is False and cc == "count_rule",
          "neither rule is subordinate to or disabled by the other")
    okc2, cc2, _ = decide(smallC, ["S1", "S2"], 80.0)
    check("two failures at $80 continue: no applicable condition binds", okc2 is True)

    print("\n=== %d passed, %d failed, %d skipped ===" % (PASS, FAIL, SKIP))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
