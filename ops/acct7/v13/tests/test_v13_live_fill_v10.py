"""Successful-fill regression for the v13 transition executor (owner ruling 2026-08-13).
PORTED v7 -> v8 for Transition Protocol v2. This suite drives run_stage()
through a scripted SUCCESSFUL FILL, which is the only way the v5 jlog defect
was ever reachable; it stays the regression that a dry run cannot give us.


THE COVERAGE HOLE THIS CLOSES
-----------------------------
On 2026-08-13 the live run halted on the FIRST completed order with

    TypeError: jlog() got multiple values for keyword argument 'seq'

after the NVDA exit had already filled at the broker. Four green suites missed it:

  * the DRY RUN structurally cannot reach the line - dry mode journals a `dry_gate`
    record and `continue`s, so execute_logical_order() and everything after it never run;
  * the s5.2 simulator drives ExecutionCore.execute_logical_order DIRECTLY and never
    enters the executor's run_stage();
  * both conformance suites are REFUSAL checks by design;
  * the limits-v4 amendment suite is scoped to gate semantics.

So nothing anywhere drove run_stage() through a SUCCESSFUL FILL. This module does exactly
that, against a scripted broker and platform under a virtual clock, and additionally
proves the executor cannot replay a partially-executed manifest.

Run inside the backend container:
    docker exec -i workbench-backend python /app/data/ops/acct7/test_v13_live_fill_v5.py
"""
import asyncio as real_asyncio
import copy
import json
import sys
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/data/ops/acct7")

import tempfile  # noqa: E402  (Protocol v2: redirect residual debt)
import v13_execution_core_v3 as core_mod          # noqa: E402
import v13_transition_executor_v10 as X           # noqa: E402
import v13_continuation_policy as CP              # noqa: E402
import v13_residual_debt as _DEBT                 # noqa: E402

# This suite runs run_stage() in LIVE mode against a stubbed broker, so the
# executor would append RESIDUAL_CLEANUP_REQUIRED obligations to the GOVERNED
# ledger for any order that did not complete. Redirect it: a conformance run
# must never write operational debt an operator would later have to disprove.
_DEBT.DEBT_PATH = Path(tempfile.mkdtemp(prefix="lf_debt_")) / "debt.jsonl"

REAL_MANIFEST = Path("/app/data/v13_transition/OTR-20260813T145600Z-S9.json")
RUN_DIR = Path("/app/data/v13_transition")

PASS = FAIL = 0
T0 = datetime(2026, 8, 13, 15, 30, 0, tzinfo=UTC)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + (("  [" + str(detail)[:300] + "]") if detail else ""))


# ---------------------------------------------------------------------------- clock ----
class Clock:
    def __init__(self):
        self.t = T0

    def now(self):
        return self.t

    def advance(self, s):
        self.t += timedelta(seconds=float(s))


CLOCK = Clock()


class _Sleep:
    @staticmethod
    async def sleep(s):
        CLOCK.advance(s)


core_mod.now = CLOCK.now
core_mod.asyncio = _Sleep


# --------------------------------------------------------------------- scripted feed ---
class Q:
    def __init__(self, bid, ask, ts):
        self.bid_price, self.ask_price, self.timestamp = bid, ask, ts


class Tr:
    def __init__(self, price, ts):
        self.price, self.timestamp = price, ts


class BrokerOrder:
    def __init__(self, coid, status, filled_qty, ts):
        self.client_order_id = coid
        self.status = status
        self.filled_qty = str(filled_qty)
        self.filled_at = ts if float(filled_qty) > 0 else None
        self.canceled_at = None
        self.updated_at = ts


class Harness:
    """Scripted platform + broker. Every submitted order fills COMPLETELY, immediately."""

    def __init__(self, prices):
        self.prices = prices
        self.submissions = []          # every POST /orders body, in order
        self.orders = {}               # order_id -> record
        self.next_id = 9000
        self.platform_terminal_after_s = 5.0

    # --- market data -------------------------------------------------------------------
    async def quote(self, symbol):
        p = self.prices[symbol]
        return Q(p * 0.9999, p * 1.0001, CLOCK.now())

    async def trade(self, symbol):
        return Tr(self.prices[symbol], CLOCK.now())

    # --- the platform HTTP surface the CORE talks to -----------------------------------
    def api(self, path, method="GET", body=None):
        if method == "POST" and path == "/orders":
            self.next_id += 1
            oid = self.next_id
            rec = {"id": oid, "coid": body["client_order_id"], "symbol": body["symbol"],
                   "side": body["side"], "qty": Decimal(str(body["qty"])),
                   "submitted_at": CLOCK.now()}
            self.orders[oid] = rec
            self.submissions.append(dict(body))
            return {"id": oid, "status": "SUBMITTED"}
        if method == "GET" and path.startswith("/orders/"):
            oid = int(path.rsplit("/", 1)[1])
            rec = self.orders[oid]
            aged = (CLOCK.now() - rec["submitted_at"]).total_seconds()
            if aged >= self.platform_terminal_after_s:
                return {"status": "FILLED",
                        "fills": [{"qty": str(rec["qty"]), "price": self.prices[rec["symbol"]]}]}
            return {"status": "SUBMITTED", "fills": []}
        if method == "DELETE":
            return {}
        return {}

    # --- broker truth ------------------------------------------------------------------
    async def broker_order(self, coid):
        for rec in self.orders.values():
            if rec["coid"] == coid:
                return BrokerOrder(coid, "FILLED", rec["qty"], rec["submitted_at"])
        return None


def build_manifest(run_id, n_orders=2, limits_file=None):
    """A faithful 2-order A_exits manifest derived from the REAL 2026-08-13 manifest.

    The real manifest embeds limits v4; the executor under test refuses any manifest
    whose embedded limits sha differs from ITS sealed limits file (v5 since P0-B2), so
    the current sealed limits are re-embedded here. The retired-v4 negative control in
    section [3] passes its own vintage explicitly - v4's executor binds the v4 file.
    """
    m = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    lf = Path(limits_file) if limits_file else X.LIMITS_FILE
    lf_text = lf.read_text(encoding="utf-8")
    m["frozen_execution_limits"] = {"sha256": X.sha256_of(lf_text),
                                    "content": json.loads(lf_text)}
    orders = [o for o in m["orders"] if o["stage"] == "A_exits"][:n_orders]
    m["orders"] = orders
    m["run_id"] = run_id
    positions = {o["symbol"]: str(o["qty"]) for o in orders}
    m["pre_run_state"] = dict(m["pre_run_state"])
    m["pre_run_state"]["positions"] = positions
    m["pre_run_state"]["position_count"] = len(positions)
    # PROTOCOL v2: the resolved continuation rule is part of the hashed body. The
    # v4-vintage negative control in section [3] embeds limits that carry no
    # continuation_policy at all; there the executor refuses at the limits binding
    # first, which is exactly what it does in the field, so omitting the block is right.
    try:
        m["continuation_policy_resolved"] = CP.resolve(
            m["frozen_execution_limits"]["content"], m["orders"],
            float(m["pre_run_state"]["equity"]))
    except CP.PolicyError:
        m.pop("continuation_policy_resolved", None)
    body = dict(m)
    body.pop("manifest_sha256", None)
    m["manifest_sha256"] = X.sha256_of(X.canonical(body))
    p = RUN_DIR / (run_id + ".json")
    p.write_text(json.dumps(m, indent=1), encoding="utf-8")
    return p, m


def wire(ex, h, positions):
    """Replace only the network surface. run_stage() itself is untouched.

    Positions are DERIVED from the harness's fills rather than held static, so the
    executor's own inter-stage reconciliation (expected = before + signed fills, within
    $1.00/position) is exercised for real instead of being trivially satisfied.
    """
    ex.quote = h.quote
    ex.trade = h.trade
    initial = {k: Decimal(str(v)) for k, v in positions.items()}

    async def _positions():
        out = dict(initial)
        for oid, rec in h.orders.items():
            signed = rec["qty"] * (1 if rec["side"] == "buy" else -1)
            out[rec["symbol"]] = out.get(rec["symbol"], Decimal(0)) + signed
        return out

    ex.positions = _positions
    ex.broker_order = h.broker_order
    ex.cookie = "test"
    ex.pacing = 0.0
    core = core_mod.ExecutionCore(
        limits=ex.limits, base_url="http://test", cookie_provider=lambda: "test",
        quote_fn=ex.quote, trade_fn=ex.trade, positions_fn=ex.positions,
        ledger=ex.ledger, plan_id=ex.run_id, account_id=ex.account_id,
        jlog=ex.jlog, broker_order_fn=ex.broker_order)
    core.api = h.api
    return core


def clean(run_id):
    for suffix in (".json", ".execution.v3.jsonl", ".stages.v3.json",
                   ".residual.v3.jsonl", ".receipt.v3.json"):
        p = RUN_DIR / (run_id + suffix)
        if p.exists():
            p.unlink()


def journal(run_id):
    p = RUN_DIR / (run_id + ".execution.v3.jsonl")
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


print("=" * 86)
print("SUCCESSFUL-FILL REGRESSION - executor v5")
print("=" * 86)

# ============================================================================ [1] =======
print("\n[1] run_stage() driven through REAL successful fills ---------------------------")
RID = "TEST-LIVEFILL-A"
clean(RID)
mp, m = build_manifest(RID)
ex = X.TransitionExecutorV3(str(mp), m["manifest_sha256"], False)
h = Harness({o["symbol"]: float(o["sizing_price"]) for o in m["orders"]})
core = wire(ex, h, {o["symbol"]: o["qty"] for o in m["orders"]})

err = None
try:
    filled = real_asyncio.run(ex.run_stage("A_exits", core))
except Exception as e:                                   # noqa: BLE001
    err = e
    filled = None

check("run_stage() completed WITHOUT an exception "
      "(v4 raised TypeError here after a real fill)", err is None, repr(err))
check("specifically, NO duplicate-keyword TypeError - the defect under test",
      not isinstance(err, TypeError), repr(err))
check("the executor's own inter-stage reconciliation PASSED on the derived positions",
      not isinstance(err, core_mod.Halt), repr(err))
if err is not None:
    print("\n*** run_stage did not complete; stopping ***")
    sys.exit(1)

j = journal(RID)
completes = [r for r in j if r.get("event") == "order_complete"]
check("orders actually reached the broker (POST /orders)",
      len(h.submissions) == len(m["orders"]), len(h.submissions))
check("an order_complete journal event was REACHED and written for every order",
      len(completes) == len(m["orders"]), len(completes))

# ============================================================================ [2] =======
print("\n[2] the order_complete record is coherent ---------------------------------------")
for o in m["orders"]:
    rec = [c for c in completes if c.get("seq") == o["seq"]]
    check("exactly ONE order_complete record for seq %d (%s)" % (o["seq"], o["symbol"]),
          len(rec) == 1, len(rec))
    if len(rec) != 1:
        continue
    r = rec[0]
    check("  seq/symbol/side are single, coherent values matching the manifest order",
          r["seq"] == o["seq"] and r["symbol"] == o["symbol"] and r["side"] == o["side"],
          {k: r.get(k) for k in ("seq", "symbol", "side")})
    for k in ("seq", "symbol", "side"):
        check("  %s appears exactly once in the JSON record (no duplicate key)" % k,
              r.get(k) is not None and not isinstance(r.get(k), list))
    check("  the record carries the core's disposition",
          r.get("final_disposition") == "FILLED", r.get("final_disposition"))
    check("  filled qty equals the intended qty",
          Decimal(str(r["filled_qty"])) == Decimal(str(o["qty"])),
          (r.get("filled_qty"), o["qty"]))
    check("  residual is zero on a complete fill",
          float(r.get("residual_notional") or 0) == 0.0, r.get("residual_notional"))

raw = (RUN_DIR / (RID + ".execution.v3.jsonl")).read_text(encoding="utf-8")
oc_lines = [ln for ln in raw.splitlines() if '"order_complete"' in ln]
check("each raw order_complete line contains exactly one \"seq\": key",
      all(ln.count('"seq":') == 1 for ln in oc_lines),
      [ln.count('"seq":') for ln in oc_lines])
check("each raw order_complete line contains exactly one \"symbol\": key",
      all(ln.count('"symbol":') == 1 for ln in oc_lines))
check("each raw order_complete line contains exactly one \"side\": key",
      all(ln.count('"side":') == 1 for ln in oc_lines))

# ============================================================================ [3] =======
print("\n[3] the SAME harness proves executor v4 FAILS (the test really covers the bug) --")
# v4 is RETIRED from execution eligibility (P0-B1, owner 2026-08-14): it omits an
# explicit market-data feed. It is loaded here BY ITS RETIRED PATH purely as the
# negative control that proves this suite really covers the v5 TypeError defect.
import importlib.util as _ilu  # noqa: E402
_v4p = "/app/data/ops/acct7/RETIRED__v13_transition_executor_v4.py"
_spec = _ilu.spec_from_file_location("retired_executor_v4", _v4p)
X4 = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(X4)
RID4 = "TEST-LIVEFILL-V4"
clean(RID4)
mp4, m4 = build_manifest(
    RID4,
    limits_file="/app/data/ops/acct7/ws1_evidence/v13/v13_frozen_execution_limits_v4.json")
ex4 = X4.TransitionExecutorV3(str(mp4), m4["manifest_sha256"], False)
h4 = Harness({o["symbol"]: float(o["sizing_price"]) for o in m4["orders"]})
core4 = wire(ex4, h4, {o["symbol"]: o["qty"] for o in m4["orders"]})
err4 = None
try:
    real_asyncio.run(ex4.run_stage("A_exits", core4))
except Exception as e:                                   # noqa: BLE001
    err4 = e
check("executor v4 raises TypeError on the same successful fill",
      isinstance(err4, TypeError), repr(err4))
check("  ... and it is the 'multiple values for keyword argument' defect",
      err4 is not None and "multiple values for keyword argument" in str(err4), str(err4))
check("  ... v4 had ALREADY submitted the order before failing "
      "(this is why the live book changed)", len(h4.submissions) >= 1, len(h4.submissions))

# ============================================================================ [4] =======
print("\n[4] re-entry: a partially executed manifest cannot be replayed ------------------")
ex_re = X.TransitionExecutorV3(str(mp), m["manifest_sha256"], False)
check("the replay executor rebuilt done_seqs from the existing journal",
      ex_re.done_seqs == {o["seq"] for o in m["orders"]}, ex_re.done_seqs)
h2 = Harness({o["symbol"]: float(o["sizing_price"]) for o in m["orders"]})
core2 = wire(ex_re, h2, {o["symbol"]: 0 for o in m["orders"]})
real_asyncio.run(ex_re.run_stage("A_exits", core2))
check("NO order was re-submitted on replay (no double-sell)",
      len(h2.submissions) == 0, h2.submissions)
check("the replay added no new order_complete records",
      len([r for r in journal(RID) if r.get("event") == "order_complete"])
      == len(m["orders"]))

# ============================================================================ [5] =======
print("\n[5] the real 2026-08-13 partial state cannot be re-executed ---------------------")
# preflight compares live positions against the manifest's pre_run_state. The real
# manifest recorded 84 positions; NVDA has since filled, so the book holds 83.
RID5 = "TEST-DRIFT"
clean(RID5)
mp5, m5 = build_manifest(RID5)
ex5 = X.TransitionExecutorV3(str(mp5), m5["manifest_sha256"], False)
h5 = Harness({o["symbol"]: float(o["sizing_price"]) for o in m5["orders"]})
gone = m5["orders"][0]["symbol"]
survivors = {o["symbol"]: o["qty"] for o in m5["orders"] if o["symbol"] != gone}
core5 = wire(ex5, h5, survivors)


async def _latch_ok():
    return True

ex5.latch_identity = _latch_ok


class _NoOpens:
    def _client(self):
        class C:
            @staticmethod
            def get_orders(filter=None):
                return []
        return C()


async def _adapter():
    return _NoOpens()

ex5.adapter = _adapter
refused = None
try:
    real_asyncio.run(ex5.preflight())
except SystemExit as e:
    refused = str(e)
except Exception as e:                                   # noqa: BLE001
    refused = "UNEXPECTED " + repr(e)
check("preflight REFUSES when a manifest position has already been exited",
      refused is not None and "drift" in str(refused).lower(), refused)
check("  ... and it names the symbol that moved",
      refused is not None and gone in str(refused), refused)
check("  ... and it tells the operator to regenerate the manifest",
      refused is not None and "regenerate" in str(refused).lower(), refused)
check("NO order was submitted while refusing", len(h5.submissions) == 0)

for rid in (RID, RID4, RID5):
    clean(rid)

print("\n" + "=" * 86)
print("RESULT  %d PASS  %d FAIL" % (PASS, FAIL))
print("=" * 86)
sys.exit(1 if FAIL else 0)
