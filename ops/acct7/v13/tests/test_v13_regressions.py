"""Regression suite for the ratified v1.3 execution amendments.

A1 — planner stage classification. The owner's ratification requires that the record
     preserve the PRE-FIX misclassification case and a regression proving the corrected
     mapping. Stage identity is safety-critical: it determines the applicable residual
     tolerance, execution order, reconciliation boundary, halt behaviour, and whether
     subsequent exposure-increasing stages may begin.

A4 — abort rate denominated over ATTEMPT OPPORTUNITIES (submitted + pre-submission gate
     aborts), with the reason taxonomy reported separately, and stage/symbol summaries so
     K=2 cannot inflate the denominator into apparent reliability.

A8 — platform state may never authorize a retry; broker state is authoritative.

No network, no orders, no account state.
"""
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/data/ops/acct7")

FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        FAILS.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


print("A1 — planner stage classification -------------------------------------------")
planner = load("/app/data/ops/acct7/v13_transition_planner.py", "planner_mod")
CA = {"SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"}


def old_predicate(o):
    """The PRE-FIX classifier, preserved as the regression's negative case."""
    if o.get("side", "").lower().startswith("sell") and o.get("reason", "").endswith("_exit"):
        return "A_exits"
    return "B_cross_asset" if o["symbol"].upper() in CA else "C_equity"


# the exact shape this planner emits: key is "intent", there is no "reason" key
equity_exit = {"symbol": "NVDA", "side": "sell", "intent": "exit"}
ca_exit = {"symbol": "UUP", "side": "sell", "intent": "exit"}
ca_trim = {"symbol": "EEM", "side": "sell", "intent": "trim"}
ca_entry = {"symbol": "KMLM", "side": "buy", "intent": "entry"}
eq_entry = {"symbol": "AMD", "side": "buy", "intent": "entry"}
legacy_exit = {"symbol": "NVDA", "side": "sell", "reason": "rebalance_exit"}

check("PRE-FIX case reproduced: an equity exit was misfiled into C_equity",
      old_predicate(equity_exit) == "C_equity", old_predicate(equity_exit))
check("PRE-FIX case reproduced: a cross-asset exit was misfiled into B_cross_asset",
      old_predicate(ca_exit) == "B_cross_asset", old_predicate(ca_exit))

check("FIXED: equity exit -> A_exits",
      planner.classify_stage(equity_exit, CA) == "A_exits",
      planner.classify_stage(equity_exit, CA))
check("FIXED: cross-asset exit -> A_exits (exits lead regardless of sleeve)",
      planner.classify_stage(ca_exit, CA) == "A_exits",
      planner.classify_stage(ca_exit, CA))
check("cross-asset TRIM stays in B_cross_asset (a trim is not an exit)",
      planner.classify_stage(ca_trim, CA) == "B_cross_asset",
      planner.classify_stage(ca_trim, CA))
check("cross-asset entry -> B_cross_asset",
      planner.classify_stage(ca_entry, CA) == "B_cross_asset")
check("equity entry -> C_equity",
      planner.classify_stage(eq_entry, CA) == "C_equity")
check("backward compatible: legacy 'reason' key still classifies as an exit",
      planner.classify_stage(legacy_exit, CA) == "A_exits",
      planner.classify_stage(legacy_exit, CA))
check("a BUY is never an exit even if intent says so (side is required)",
      planner.classify_stage({"symbol": "AMD", "side": "buy", "intent": "exit"}, CA)
      == "C_equity")
check("A1 scope: classification only — no quantity/threshold/target fields consulted",
      "qty" not in open("/app/data/ops/acct7/v13_transition_planner.py").read()
      .split("def classify_stage")[1].split("def ")[0])

print("\nA4 — abort rate over attempt opportunities ------------------------------------")
core = load("/app/data/ops/acct7/v13_execution_core.py", "core_mod")
led = core.ResidualLedger(Path("/tmp/test_ledger.jsonl"), 250.0)
if Path("/tmp/test_ledger.jsonl").exists():
    Path("/tmp/test_ledger.jsonl").unlink()

# 3 submitted attempts, 2 pre-submission gate aborts, across two stages
led.record_attempt({"stage": "A_exits", "symbol": "AAA", "broker_order_id": "1",
                    "attempt_number": 1, "attempt_state": "FILLED"})
led.record_attempt({"stage": "A_exits", "symbol": "BBB", "abort_reason": "stale_reference",
                    "attempt_number": 1, "attempt_state": "RETRY_ELIGIBLE"})
led.record_attempt({"stage": "A_exits", "symbol": "BBB", "broker_order_id": "2",
                    "attempt_number": 2, "attempt_state": "FILLED"})
led.record_attempt({"stage": "C_equity", "symbol": "CCC",
                    "abort_reason": "no_usable_print_or_quote",
                    "attempt_number": 1, "attempt_state": "EXHAUSTED"})
led.record_attempt({"stage": "C_equity", "symbol": "DDD", "broker_order_id": "3",
                    "attempt_number": 1, "attempt_state": "FILLED"})

o = led.attempt_opportunities()
check("denominator = submitted + pre-submission aborts (3 + 2 = 5)",
      o["attempt_opportunities"] == 5, json.dumps(o))
check("abort_rate = aborts / opportunities = 2/5 = 0.40",
      abs(o["abort_rate"] - 0.4) < 1e-9, str(o["abort_rate"]))
check("rate is NOT computed over submitted orders only (would have been 2/3)",
      abs(o["abort_rate"] - (2 / 3)) > 1e-6)
check("retries count as separate opportunities (BBB contributes 2)",
      led.attempt_opportunities(symbol="BBB")["attempt_opportunities"] == 2)
check("reasons reported separately",
      led.abort_reason_breakdown() == {"stale_reference": 1,
                                       "no_usable_print_or_quote": 1},
      json.dumps(led.abort_reason_breakdown()))
summ = led.summary()
check("stage-level summary present", set(summ["by_stage"]) == {"A_exits", "C_equity"})
check("symbol-level summary present so K=2 cannot mask reliability",
      set(summ["by_symbol"]) == {"AAA", "BBB", "CCC", "DDD"})
check("A_exits rate = 1 abort / 3 opportunities",
      abs(summ["by_stage"]["A_exits"]["abort_rate"] - 1 / 3) < 1e-6,
      str(summ["by_stage"]["A_exits"]))
check("every taxonomy code is one of the ratified reasons",
      all(r in core.ABORT_REASONS for r in led.abort_reason_breakdown()))

print("\nA8 — platform state may not authorize a retry ---------------------------------")
check("invariant constant present and true", core.PLATFORM_STATE_MAY_NOT_AUTHORIZE_RETRY)
src = Path("/app/data/ops/acct7/v13_execution_core.py").read_text()
retry_block = src.split("async def await_terminal")[1].split("async def observe_platform")[0]
check("await_terminal decides terminality from broker_state, not the platform ledger",
      "broker_state" in retry_block and 'self.api(f"/orders/{order_id}")' in retry_block
      and "return" in retry_block)
check("platform status inside await_terminal is only recorded, never gating",
      "platform_status" in retry_block and "if plat not in TERMINAL" in retry_block)
check("observe_platform_settlement polls to a condition rather than sleeping blindly",
      "max_wait_s" in src and "outstanding" in src and "timed_out" in src)
check("latency telemetry exposes both terminality and fill-ingestion lag",
      "broker_to_platform_terminality_lag" in src and "fill_ingestion_lag" in src)

print()
print("RESULT:", "ALL PASS" if not FAILS else f"{len(FAILS)} FAILURES: {FAILS}")
sys.exit(1 if FAILS else 0)
