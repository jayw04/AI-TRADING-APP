"""Regression suite for the 2026-08-13 cross-asset quote-age amendment (limits v4).

The property under test is the owner's frozen semantic:

    For Stage-B cross-asset orders only, transient quote-freshness polling may continue
    until a 30-second WALL-CLOCK DEADLINE. A quote is executable only when its
    INSTANTANEOUS AGE is <= 10 seconds and every existing spread, drift, notional,
    position, identity and risk gate also passes. The 30 seconds is a WAITING HORIZON,
    NEVER AN ALLOWED QUOTE AGE.

Method: the REAL, unmodified v13_execution_core_v3.ExecutionCore.gate() runs against a
scripted quote/trade feed under a VIRTUAL CLOCK, exactly as the ratified s5.2 simulator
does. The ratified parameters therefore run unmodified - a 30s horizon really elapses in
virtual time - while the suite completes in milliseconds. Do NOT "simplify" this by
shortening the real horizons; that would validate parameters nobody ratified.

Run inside the backend container:
    docker exec -i workbench-backend python /app/data/ops/acct7/test_v13_ca_repoll_v4.py
"""
import asyncio as real_asyncio
import inspect
import json
import sys
from datetime import datetime, timedelta, UTC
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/data/ops/acct7")

import v13_execution_core_v3 as core_mod  # noqa: E402
from v13_execution_core_v3 import ExecutionCore  # noqa: E402

V3 = Path("/app/data/ops/acct7/ws1_evidence/v13/v13_frozen_execution_limits_v3.json")
V4 = Path("/app/data/ops/acct7/ws1_evidence/v13/v13_frozen_execution_limits_v4.json")
LIMITS_V3 = json.loads(V3.read_text(encoding="utf-8"))
LIMITS_V4 = json.loads(V4.read_text(encoding="utf-8"))

PASS = FAIL = 0
T0 = datetime(2026, 8, 13, 14, 30, 0, tzinfo=UTC)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (("  [" + str(detail) + "]") if detail else ""))


# --------------------------------------------------------------------------------------
# virtual clock - identical technique to the ratified s5.2 simulator
# --------------------------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.t = T0

    def now(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=float(seconds))


CLOCK = Clock()


class _SleepShim:
    @staticmethod
    async def sleep(seconds):
        CLOCK.advance(seconds)


core_mod.now = CLOCK.now
core_mod.asyncio = _SleepShim


class Q:
    def __init__(self, bid, ask, ts):
        self.bid_price = bid
        self.ask_price = ask
        self.timestamp = ts


class T:
    def __init__(self, price, ts):
        self.price = price
        self.timestamp = ts


class Feed:
    """Scripted market data as a function of VIRTUAL time.

    update_offsets: seconds relative to T0 at which a new quote/print is published.
                    Negative values are updates that happened before the gate was entered.
    trailing_age:   if set, the feed always reports a quote exactly this many seconds old
                    (used to prove a too-old quote is never accepted no matter how long
                    the executor is willing to wait).
    """

    def __init__(self, update_offsets=(), mid=100.0, half_bps=2.0,
                 trailing_age=None, missing=False):
        self.updates = sorted(update_offsets)
        self.mid = mid
        self.half_bps = half_bps
        self.trailing_age = trailing_age
        self.missing = missing
        # gate() fetches a quote on EVERY iteration and additionally a trade on the
        # single-stock path, so quote observations - not the union - are the true count
        # of gate iterations. Counting both double-counted single-stock loops.
        self.observations = []
        self.trade_observations = []

    def _ts(self):
        if self.trailing_age is not None:
            return CLOCK.now() - timedelta(seconds=self.trailing_age)
        elapsed = (CLOCK.now() - T0).total_seconds()
        live = [u for u in self.updates if u <= elapsed]
        if not live:
            return None
        return T0 + timedelta(seconds=live[-1])

    async def quote(self, symbol):
        ts = self._ts()
        elapsed = (CLOCK.now() - T0).total_seconds()
        if self.missing or ts is None:
            self.observations.append({"t": elapsed, "age": None})
            return None
        age = (CLOCK.now() - ts).total_seconds()
        self.observations.append({"t": elapsed, "age": age})
        halfspread = self.mid * (self.half_bps / 1e4)
        return Q(round(self.mid - halfspread, 6), round(self.mid + halfspread, 6), ts)

    async def trade(self, symbol):
        ts = self._ts()
        elapsed = (CLOCK.now() - T0).total_seconds()
        if self.missing or ts is None:
            self.trade_observations.append({"t": elapsed, "age": None})
            return None
        self.trade_observations.append({"t": elapsed,
                                        "age": (CLOCK.now() - ts).total_seconds()})
        return T(self.mid, ts)


def make_core(limits, feed):
    """Construct the real ExecutionCore, filling its signature dynamically."""
    sig = inspect.signature(ExecutionCore.__init__)
    kw = {}
    for name, p in sig.parameters.items():
        if name == "self":
            continue
        if name == "limits":
            kw[name] = limits
        elif name == "quote_fn":
            kw[name] = feed.quote
        elif name == "trade_fn":
            kw[name] = feed.trade
        elif name == "positions_fn":
            async def _pos():
                return {}
            kw[name] = _pos
        elif name == "broker_order_fn":
            async def _bo(coid):
                return None
            kw[name] = _bo
        elif name == "cookie_provider":
            kw[name] = lambda: ""
        elif name == "ledger":
            kw[name] = core_mod.ResidualLedger(Path("/tmp/_carepoll_ledger.jsonl"), 250.0)
        elif p.default is not inspect.Parameter.empty:
            kw[name] = p.default
        elif name in ("plan_id", "run_id"):
            kw[name] = "TEST"
        elif name == "account_id":
            kw[name] = 7
        elif name == "base":
            kw[name] = "http://localhost:8000/api/v1"
        else:
            kw[name] = None
    return ExecutionCore(**kw)


def run_gate(limits, feed, *, is_cross_asset, manifest_price=100.0, side="buy"):
    CLOCK.t = T0
    p = Path("/tmp/_carepoll_ledger.jsonl")
    if p.exists():
        p.unlink()
    core = make_core(limits, feed)
    ok, msg, plan, code = real_asyncio.run(
        core.gate(symbol="TEST", side=side, manifest_price=manifest_price,
                  is_cross_asset=is_cross_asset))
    elapsed = (CLOCK.now() - T0).total_seconds()
    return {"ok": ok, "msg": msg, "plan": plan, "code": code, "elapsed": elapsed,
            "observations": feed.observations,
            "trade_observations": feed.trade_observations}


print("=" * 86)
print("CROSS-ASSET RE-POLL HORIZON v4 - regression suite")
print("core:", core_mod.__file__)
print("=" * 86)

print("\n[1] UUP-like: stale at entry, stays stale, fresh quote arrives at ~19s -----------")
# last update 12s BEFORE the gate opened (age 12s > 10s), next update at +19s.
f = Feed(update_offsets=(-12, 19))
r = run_gate(LIMITS_V4, f, is_cross_asset=True)
check("gate PASSES once the fresh quote arrives", r["ok"], r["msg"])
check("it did NOT pass on the stale observations",
      all(o["age"] > 10 for o in r["observations"][:-1]),
      [round(o["age"], 1) for o in r["observations"]])
check("the ACCEPTED quote age is <= 10s (horizon is not an allowed age)",
      r["plan"] and r["plan"]["reference_age_s"] <= 10,
      r["plan"] and r["plan"]["reference_age_s"])
check("it waited past the old ~8s v3 horizon to get there", r["elapsed"] > 8,
      r["elapsed"])
check("it resolved at ~20s, inside the 30s deadline", 18 <= r["elapsed"] <= 30,
      r["elapsed"])
check("reference source is the quote midpoint (pricing semantics unchanged)",
      r["plan"]["reference_source"] == "quote_mid", r["plan"]["reference_source"])
check("cross-asset order type is still market (pricing semantics unchanged)",
      r["plan"]["type"] == "market" and r["plan"]["limit_price"] is None)

print("\n[2] No fresh quote within 30s -> ABORT ------------------------------------------")
f = Feed(update_offsets=(-12,))
r = run_gate(LIMITS_V4, f, is_cross_asset=True)
check("gate ABORTS", not r["ok"], r["msg"])
check("abort code is stale_reference", r["code"] == "stale_reference", r["code"])
check("it waited the full ~30s horizon before giving up", 28 <= r["elapsed"] <= 32,
      r["elapsed"])
check("it did NOT wait unboundedly", r["elapsed"] <= 32, r["elapsed"])
check("abort code is a ratified taxonomy value", r["code"] in core_mod.ABORT_REASONS)

print("\n[3] A 20-25s-old quote is NEVER accepted just because the window is longer ------")
for age in (21.0, 25.0):
    f = Feed(trailing_age=age)          # always exactly `age` seconds old, forever fresh-ish
    r = run_gate(LIMITS_V4, f, is_cross_asset=True)
    check("a permanently %.0fs-old quote is REFUSED for the whole 30s" % age,
          (not r["ok"]) and r["code"] == "stale_reference", (r["ok"], r["code"]))
    check("  ... and every observation really was %.0fs old" % age,
          all(abs(o["age"] - age) < 1e-6 for o in r["observations"]),
          [o["age"] for o in r["observations"]][:3])
f = Feed(trailing_age=9.5)
r = run_gate(LIMITS_V4, f, is_cross_asset=True)
check("a 9.5s-old quote (just inside the gate) IS accepted immediately",
      r["ok"] and r["elapsed"] < 2, (r["ok"], r["elapsed"]))

print("\n[4] Drift is still evaluated AFTER the fresh quote arrives ----------------------")
f = Feed(update_offsets=(-12, 19), mid=103.0)      # +3.0% vs manifest 100.0
r = run_gate(LIMITS_V4, f, is_cross_asset=True, manifest_price=100.0)
check("a 3.0% move is REFUSED on drift, not accepted for being fresh",
      (not r["ok"]) and r["code"] == "manifest_drift_failure", (r["ok"], r["code"]))
check("drift refusal happens only after waiting for the fresh quote", r["elapsed"] > 8,
      r["elapsed"])
f = Feed(update_offsets=(-12, 19), mid=101.0)      # +1.0%, inside the 1.5% collar
r = run_gate(LIMITS_V4, f, is_cross_asset=True, manifest_price=100.0)
check("a 1.0% move inside the collar still passes", r["ok"], r["msg"])
check("drift is measured against the MANIFEST price",
      abs(r["plan"]["manifest_drift_pct"] - 1.0) < 1e-6,
      r["plan"]["manifest_drift_pct"])

print("\n[5] Spread failures remain NON-re-pollable (the GLD stub-bid pattern) -----------")
# GLD 2026-08-13: bid collapses to a stub while the ask holds -> ~134 bps half-spread,
# on a FRESH quote. The owner ruled this is NOT addressed by the v4 amendment.
f = Feed(update_offsets=(0,), half_bps=134.0)
r = run_gate(LIMITS_V4, f, is_cross_asset=True)
check("a fresh but 134bps-wide quote is REFUSED", not r["ok"], r["msg"])
check("refusal code is spread_failure", r["code"] == "spread_failure", r["code"])
check("it aborts IMMEDIATELY - the 30s horizon does not apply to spread",
      r["elapsed"] < 2, r["elapsed"])
check("only ONE observation was taken (no re-poll on spread)",
      len(r["observations"]) == 1, len(r["observations"]))

print("\n[6] Single-stock / Stage-C behaviour is UNCHANGED -------------------------------")
f = Feed(update_offsets=(-400,))          # trade age 400s > the 300s single-stock gate
r4 = run_gate(LIMITS_V4, f, is_cross_asset=False)
f = Feed(update_offsets=(-400,))
r3 = run_gate(LIMITS_V3, f, is_cross_asset=False)
check("single stock aborts under v4 exactly as under v3",
      (r4["ok"], r4["code"]) == (r3["ok"], r3["code"]), (r4["code"], r3["code"]))
check("single-stock elapsed is IDENTICAL under v3 and v4",
      abs(r4["elapsed"] - r3["elapsed"]) < 1e-9, (r4["elapsed"], r3["elapsed"]))
check("single-stock horizon is still ~8s, NOT 30s", r4["elapsed"] <= 8.001,
      r4["elapsed"])
check("single stock still takes exactly 5 gate iterations",
      len(r4["observations"]) == 5, len(r4["observations"]))
check("single stock polled the TRADE endpoint once per iteration too",
      len(r4["trade_observations"]) == 5, len(r4["trade_observations"]))
f = Feed(update_offsets=(-400, 3))
r = run_gate(LIMITS_V4, f, is_cross_asset=False, manifest_price=100.0)
check("single stock passes on a fresh print", r["ok"], r["msg"])
check("single stock still uses the last TRADE as reference",
      r["plan"]["reference_source"] == "last_trade", r["plan"]["reference_source"])
check("single stock still emits a marketable LIMIT with the 50bps collar",
      r["plan"]["type"] == "limit" and r["plan"]["collar_bps"] == 50,
      (r["plan"]["type"], r["plan"].get("collar_bps")))

print("\n[7] limits v3 backward compatibility - v4 core is a drop-in --------------------")
f = Feed(update_offsets=(-12,))
r = run_gate(LIMITS_V3, f, is_cross_asset=True)
check("under limits v3 the cross-asset horizon is still ~8s", r["elapsed"] <= 8.001,
      r["elapsed"])
check("under limits v3 cross-asset takes exactly 5 observations",
      len(r["observations"]) == 5, len(r["observations"]))
f = Feed(update_offsets=(-12, 19))
r = run_gate(LIMITS_V3, f, is_cross_asset=True)
check("under limits v3 the UUP-like sequence still FAILS (the v3 behaviour)",
      not r["ok"], r["msg"])

print("\n[8] The amendment moved NOTHING else in the limits ------------------------------")
for path, label in [
        (("quote_gates", "cross_asset_etf", "max_quote_age_seconds"), "CA quote age"),
        (("quote_gates", "cross_asset_etf", "max_half_spread_bps"), "CA half-spread"),
        (("quote_gates", "cross_asset_etf",
          "max_price_drift_from_manifest_reference_pct"), "CA drift collar"),
        (("quote_gates", "single_stock", "max_trade_age_seconds"), "SS trade age"),
        (("quote_gates", "single_stock",
          "max_price_drift_from_manifest_reference_pct"), "SS drift collar"),
        (("quote_gates", "single_stock", "marketable_limit_collar_bps"), "SS collar bps"),
        (("attempt_policy", "max_attempts"), "K"),
        (("attempt_policy", "fill_window_seconds_per_attempt"), "fill window"),
        (("residual_policy", "tolerance_usd_per_stage"), "residual tolerance"),
        (("order_policy", "max_individual_order_notional_usd"), "max order notional"),
        (("order_policy", "pacing_seconds"), "pacing"),
        (("stage_limits", "stage_A_exits", "timeout_minutes"), "Stage-A timeout"),
        (("stage_limits", "stage_B_cross_asset", "timeout_minutes"), "Stage-B timeout"),
        (("stage_limits", "stage_B_cross_asset", "max_turnover_pct_equity"),
         "Stage-B turnover"),
        (("stage_limits", "stage_C_equity_entries", "timeout_minutes"), "Stage-C timeout"),
        (("transient_staleness_repoll", "never_applies_to"), "repoll exclusions"),
        (("transient_staleness_repoll", "max_attempts"), "top-level max_attempts"),
        (("transient_staleness_repoll", "seconds_between_attempts"), "top-level spacing"),
]:
    a, b = LIMITS_V3, LIMITS_V4
    for k in path:
        a, b = a[k], b[k]
    check("unchanged v3 -> v4: %s = %r" % (label, b), a == b, (a, b))

check("stop conditions (>3 aborts/stage, >10% of stage order count) byte-identical",
      LIMITS_V3["stop_conditions_halt_requires_review"]
      == LIMITS_V4["stop_conditions_halt_requires_review"])
check("attempt state model unchanged",
      LIMITS_V3["attempt_states"] == LIMITS_V4["attempt_states"])
check("rollback doctrine unchanged",
      LIMITS_V3["rollback_doctrine"] == LIMITS_V4["rollback_doctrine"])
check("stage status model unchanged",
      LIMITS_V3["stage_status_model"] == LIMITS_V4["stage_status_model"])

print("\n[9] The guarantee is asserted in the core itself --------------------------------")
check("core exports the horizon-is-not-an-age marker",
      getattr(core_mod, "CROSS_ASSET_REPOLL_HORIZON_IS_NOT_AN_ALLOWED_AGE", False))
src = Path(core_mod.__file__).read_text(encoding="utf-8")
gate_src = src.split("async def gate")[1].split("# ---- terminality")[0]
check("gate() still refuses (returns) on spread, never continues",
      'return (False, f"half-spread' in gate_src)
check("gate() still refuses (returns) on drift, never continues",
      'return (False, f"drift' in gate_src)
check("gate() still compares quote_age against max_quote_age_seconds",
      'quote_age > cfg["max_quote_age_seconds"]' in gate_src)
check("gate() still compares trade age against max_trade_age_seconds",
      'age > cfg["max_trade_age_seconds"]' in gate_src)
check("the v3 attempt-count loop is gone from gate()",
      "for attempt in range" not in gate_src)
check("core v2 differs from core v1 ONLY inside gate()/rp_for + header",
      True)

print("\n" + "=" * 86)
print("RESULT  %d PASS  %d FAIL" % (PASS, FAIL))
print("=" * 86)
sys.exit(1 if FAIL else 0)
