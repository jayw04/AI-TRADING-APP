"""Shared execution core v3: bounded-re-attempt state machine + unified residual ledger.

v3 = v2 plus the Transition Protocol v2 accounting primitives, ratified by the owner on
2026-08-21. It changes NO gate, NO threshold, NO attempt policy, NO residual valuation and
NO submission behaviour. It adds three things:

  1. A FAILURE TAXONOMY. Every attempt record and order disposition now carries
     failure_class in {"HARD", "EXECUTABILITY", None}. HARD failures (risk refusal, broker
     HTTP error, unestablished terminality) already halted immediately in v2; v3 only names
     them, so the receipt and the continuation policy can distinguish "this order could not
     be priced" from "the system is not in a fit state to trade".

  2. LOGICAL-ORDER FAILURE COUNTING. ResidualLedger.failed_orders(stage) counts ORDER
     dispositions that did not complete, not attempt records.

     WHY THIS EXISTS: executor v7 counted attempt records against an order-count
     denominator. With attempt_policy.max_attempts = 2 one failing order contributed 2, so
     "> 3 aborts" actually meant "more than 1.5 failing orders" and TWO failing orders
     halted a stage of ANY size. Measured live on 2026-08-20: two failing orders (MS, PH)
     produced four abort records and halted a 36-order stage at 5.9% order-level failure.
     Owner ruling 2026-08-21: "Retries are execution mechanics. They must not multiply the
     economic failure count."

  3. DRY-RUN PARITY. record_dry_order() lets a dry run enter an imputed order disposition
     (residual valued at the reviewed manifest reference) into a dry ledger, so dry
     adjudication runs the SAME logical-order continuation semantics as live. In v2, dry
     mode wrote nothing to the ledger at all, so a dry run logged one abort per failing
     order where live logged two and the two could disagree.

v2 = v13_execution_core.py (sha a71720a2..., the artifact the 2026-07-29 SPY canary

proved) plus EXACTLY ONE semantic change, ratified by the owner on 2026-08-13:
the transient quote-freshness re-poll horizon becomes per instrument class, and
cross-asset ETFs may poll until a 30-second WALL-CLOCK DEADLINE. Nothing else moves -
not the 10s cross-asset quote age, not the 25 bps spread cap, not the 1.5% manifest
drift collar, not K=2, not the 120s fill window, not the residual accounting, and
not single-stock behaviour. See v13_frozen_execution_limits_v4.json.

Ratified by the owner 2026-07-29 (Option 2): reference age <= 300s, fill window 120s per
attempt, at most 2 gated attempts, 1.5% drift measured against the REVIEWED MANIFEST price
on every attempt, $250 residual tolerance per stage, no market-order fallback, no automatic
tolerance increase.

Design points that are load-bearing:

* Attempts are FIRST-CLASS STATE, not log annotations. Every attempt carries the full
  record required by the ratification (reference, gate measurements, ids, quantities,
  cancellation confirmation, reconciliation, cumulative stage residual, disposition).

* Attempt N+1 may not be submitted until attempt N is CONCLUSIVELY TERMINAL AT THE BROKER.
  A timeout alone is never sufficient. await_terminal() polls the broker until the order
  reaches a terminal status; if terminality cannot be established the run HALTS rather than
  risking a duplicate live order.

* A re-attempt requests intended_qty MINUS cumulative broker-confirmed filled qty, so a
  late fill during a cancellation race can never be double-ordered.

* ONE residual ledger. Gate-aborted, risk-rejected, expired, cancelled and unfilled
  portions of partial fills all enter the same accounting. Residual notional is valued from
  the BROKER-CONFIRMED remaining quantity at current governed valuation.

Used by the canary first; the transition executor adopts the identical proven core.
"""
import asyncio
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, UTC
from decimal import Decimal

DUST = Decimal("0.000000001")
TERMINAL = {"FILLED", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED", "DONE_FOR_DAY"}
OPEN_STATES = {"NEW", "ACCEPTED", "PENDING_NEW", "PARTIALLY_FILLED", "SUBMITTED",
               "PENDING_CANCEL", "ACCEPTED_FOR_BIDDING"}
STATES = ["PLANNED", "GATE_PASSED", "SUBMITTED", "PARTIALLY_FILLED", "FILLED",
          "CANCEL_REQUESTED", "CANCEL_CONFIRMED", "RETRY_ELIGIBLE", "RETRY_SUBMITTED",
          "EXHAUSTED", "HALTED_REQUIRES_REVIEW"]

# ---- Transition Protocol v2 failure taxonomy (owner ruling 2026-08-21) ----------------
# EXECUTABILITY: the market could not be priced within the governed gates. The order is
#   REFUSED and never force-submitted; whether the transition continues is decided by the
#   per-stage continuation policy on the economic residual left behind.
# HARD: the system is not in a fit state to trade. Immediate halt regardless of economics;
#   a hard failure never receives a residual budget.
EXECUTABILITY_ABORTS = {"stale_reference", "spread_failure", "manifest_drift_failure",
                        "no_usable_print_or_quote", "other_governed_gate"}
HARD_ABORTS = {"risk_refusal", "broker_http_error", "identity_mismatch",
               "terminality_unestablished", "reconciliation_mismatch",
               "unknown_order_state"}


def failure_class_of(abort_reason):
    """None when there is no failure. Unknown codes are HARD: fail closed."""
    if not abort_reason:
        return None
    if abort_reason in EXECUTABILITY_ABORTS:
        return "EXECUTABILITY"
    return "HARD"


class Halt(Exception):
    """HALTED_REQUIRES_REVIEW. Never represented as success."""


def now():
    return datetime.now(UTC)


def iso():
    return now().isoformat()


# Owner ruling 2026-08-13. Asserted by the conformance suite so the guarantee cannot be
# quietly dropped: the cross-asset horizon bounds WAITING, never the accepted quote age.
CROSS_ASSET_REPOLL_HORIZON_IS_NOT_AN_ALLOWED_AGE = True

ABORT_REASONS = [
    "no_usable_print_or_quote",
    "stale_reference",
    "spread_failure",
    "manifest_drift_failure",
    "unresolved_prior_attempt",
    "broker_or_reconciliation_failure",
    "other_governed_gate",
]

# EXECUTION INVARIANT (owner, 2026-07-29, from the canary finding):
# No real-time execution decision may infer "unfilled", "terminal" or "safe to retry"
# from the ABSENCE of a platform fill record. Broker state, keyed by immutable client
# order id, is authoritative for terminality and filled quantity inside the execution
# window. The platform ledger is durable but eventually consistent, and is recorded for
# audit and latency measurement only.
PLATFORM_STATE_MAY_NOT_AUTHORIZE_RETRY = True


class ResidualLedger:
    """One ledger for every category of unexecuted exposure."""

    def __init__(self, path, tolerance_usd):
        self.path = path
        self.tolerance = float(tolerance_usd)
        self.attempts = []
        self.orders = []

    def _append(self, kind, rec):
        rec = {"kind": kind, "ts": iso(), **rec}
        with open(self.path, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        return rec

    def record_attempt(self, rec):
        if "failure_class" not in rec:
            rec["failure_class"] = failure_class_of(rec.get("abort_reason"))
        self.attempts.append(rec)
        return self._append("attempt", rec)

    def record_order(self, rec):
        self.orders.append(rec)
        return self._append("order_disposition", rec)

    def record_dry_order(self, rec):
        """PROTOCOL v2 DRY-RUN PARITY (owner ruling 2026-08-21).

        A dry run submits nothing, so no broker-confirmed residual exists. To adjudicate a
        dry run with the SAME logical-order continuation semantics as live, an imputed
        disposition is entered here, valued at the REVIEWED MANIFEST reference price. The
        record is flagged `imputed: True` and lands in the .dryrun ledger, so it can never
        be mistaken for a measured residual or contaminate a live ledger.
        """
        rec = {**rec, "imputed": True}
        self.orders.append(rec)
        return self._append("order_disposition_dry_imputed", rec)

    def stage_residual(self, stage):
        return round(sum(o["residual_notional"] for o in self.orders
                         if o["stage"] == stage), 2)

    def within_tolerance(self, stage):
        return self.stage_residual(stage) <= self.tolerance

    # ---- Transition Protocol v2: count LOGICAL ORDERS, never attempt records ----------
    # Owner ruling 2026-08-21: "check_stop_conditions must count failed logical orders,
    # not attempt records. Retries are execution mechanics. They must not multiply the
    # economic failure count. 1 order x 2 failed attempts = 1 failed order."
    def failed_order_records(self, stage=None):
        return [o for o in self.orders
                if (stage is None or o.get("stage") == stage)
                and (o.get("final_disposition") != "FILLED"
                     or abs(float(o.get("residual_qty") or 0)) > float(DUST))]

    def failed_orders(self, stage=None):
        return len(self.failed_order_records(stage))

    def failed_order_symbols(self, stage=None):
        return sorted({o["symbol"] for o in self.failed_order_records(stage)})

    def hard_failures(self, stage=None):
        return [a for a in self.attempts
                if (stage is None or a.get("stage") == stage)
                and a.get("failure_class") == "HARD"]

    def failure_class_breakdown(self, stage=None):
        out = {}
        for o in self.failed_order_records(stage):
            k = o.get("failure_class") or "UNCLASSIFIED"
            out[k] = out.get(k, 0) + 1
        return out

    def closes_to_zero(self):
        return all(abs(o["residual_qty"]) <= float(DUST) for o in self.orders)

    # ---- A4 (ratified 2026-07-29): abort rate over ATTEMPT OPPORTUNITIES ----------
    # "Every order-attempt opportunity that enters execution evaluation after the stage
    # plan is frozen, including attempts that abort BEFORE submission." Computing the
    # rate over submitted orders only would hide the IEX print-sparsity problem that
    # motivated the 300s reference age. Retries count as separate opportunities, so
    # stage- and symbol-level summaries are reported alongside, so that K=2 cannot make
    # a run look more reliable merely by inflating the denominator.
    def _select(self, stage=None, symbol=None):
        return [a for a in self.attempts
                if (stage is None or a.get("stage") == stage)
                and (symbol is None or a.get("symbol") == symbol)]

    def attempt_opportunities(self, stage=None, symbol=None):
        sel = self._select(stage, symbol)
        submitted = sum(1 for a in sel if a.get("broker_order_id"))
        aborts = sum(1 for a in sel if a.get("abort_reason"))
        opps = submitted + aborts
        return {"submitted_attempts": submitted,
                "pre_submission_gate_aborts": aborts,
                "attempt_opportunities": opps,
                "abort_rate": round(aborts / opps, 6) if opps else 0.0}

    def abort_reason_breakdown(self, stage=None, symbol=None):
        out = {}
        for a in self._select(stage, symbol):
            r = a.get("abort_reason")
            if r:
                out[r] = out.get(r, 0) + 1
        return out

    def summary(self):
        stages = sorted({a.get("stage") for a in self.attempts if a.get("stage")}
                        | {o.get("stage") for o in self.orders if o.get("stage")})
        syms = sorted({a.get("symbol") for a in self.attempts if a.get("symbol")})
        return {
            "overall": {**self.attempt_opportunities(),
                        "reasons": self.abort_reason_breakdown()},
            "by_stage": {st: {**self.attempt_opportunities(stage=st),
                              "reasons": self.abort_reason_breakdown(stage=st)}
                         for st in stages},
            "by_symbol": {sy: {**self.attempt_opportunities(symbol=sy),
                               "reasons": self.abort_reason_breakdown(symbol=sy)}
                          for sy in syms},
            "latency_telemetry": self.latency_telemetry(),
            # PROTOCOL v2: the ORDER-level view the continuation policy actually consumes.
            # The attempt-level A4 numbers above are retained unchanged for provenance and
            # for the IEX print-sparsity observability they were ratified to give.
            "by_stage_logical_orders": {
                st: {"failed_orders": self.failed_orders(st),
                     "failed_order_symbols": self.failed_order_symbols(st),
                     "stage_residual_usd": self.stage_residual(st),
                     "failure_classes": self.failure_class_breakdown(st)}
                for st in stages},
            "counting_unit": "failed_logical_orders",
        }

    # ---- A8 (ratified): broker-vs-platform latency, measured rather than assumed ---
    def latency_telemetry(self):
        term, fill = [], []
        for a in self.attempts:
            if a.get("terminality_lag_s") is not None:
                term.append(a["terminality_lag_s"])
            if a.get("fill_ingestion_lag_s") is not None:
                fill.append(a["fill_ingestion_lag_s"])

        def stats(v):
            if not v:
                return None
            v = sorted(v)
            return {"n": len(v), "max_s": v[-1], "p50_s": v[len(v) // 2],
                    "p95_s": v[min(len(v) - 1, int(len(v) * 0.95))]}

        return {"broker_to_platform_terminality_lag": stats(term),
                "fill_ingestion_lag": stats(fill)}


class ExecutionCore:
    def __init__(self, *, limits, base_url, cookie_provider, quote_fn, trade_fn,
                 positions_fn, ledger, plan_id, account_id, jlog=None,
                 broker_order_fn=None):
        self.limits = limits
        self.base = base_url
        self.cookie_provider = cookie_provider
        self.quote = quote_fn
        self.trade = trade_fn
        self.positions = positions_fn
        self.ledger = ledger
        self.plan_id = plan_id
        self.account_id = account_id
        self.qg = limits["quote_gates"]
        self.ap = limits["attempt_policy"]
        self.rp = limits["transient_staleness_repoll"]
        self.jlog = jlog or (lambda **k: None)
        # CANARY FINDING 2026-07-29: the PLATFORM order row can remain SUBMITTED with no
        # fill rows after the broker has fully filled the order (trade-updates stream
        # missed the fill). Terminality and filled quantity are therefore read from the
        # BROKER, which is the source of truth. Submission still goes through the
        # OrderRouter, so ADR 0002's single dispatch point is unchanged.
        self.broker_order = broker_order_fn

    # ---- HTTP ------------------------------------------------------------------------
    def api(self, path, method="GET", body=None):
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(body, default=str).encode() if body is not None else None,
            headers={"Content-Type": "application/json",
                     "Cookie": self.cookie_provider() or ""},
            method=method)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}

    @staticmethod
    def status_of(resp):
        return str(resp.get("status", "")).upper().split(".")[-1]

    @staticmethod
    def filled_qty(resp):
        return sum(Decimal(str(f.get("qty", 0))) for f in (resp.get("fills") or []))

    # ---- gates -----------------------------------------------------------------------
    def rp_for(self, is_cross_asset):
        """Transient re-poll policy for this instrument class (limits v4).

        When per_instrument_class is ABSENT - limits v3 and earlier - both classes fall
        back to the shared top-level policy, so a v3 manifest gates byte-identically and
        this core stays a drop-in for the artifact the SPY canary proved.
        """
        per = self.rp.get("per_instrument_class") or {}
        cls = "cross_asset_etf" if is_cross_asset else "single_stock"
        return {**self.rp, **(per.get(cls) or {})}

    async def gate(self, *, symbol, side, manifest_price, is_cross_asset):
        """Every attempt re-verifies freshness, spread and drift vs the MANIFEST price."""
        cfg = self.qg["cross_asset_etf" if is_cross_asset else "single_stock"]
        drift_cap = cfg["max_price_drift_from_manifest_reference_pct"]
        stale, stale_code = "no observation", "no_usable_print_or_quote"
        # LIMITS v4 (owner ruling 2026-08-13). The transient re-poll horizon is now per
        # INSTRUMENT CLASS. Cross-asset ETFs poll until a WALL-CLOCK DEADLINE because the
        # measured constraint on this feed is IEX update SPARSITY, not quote quality: the
        # 2026-08-13 viability protocol measured UUP/KMLM inter-update gaps of 18.51s and
        # 20.35s against a re-poll horizon of only ~8s, while their half-spreads were
        # 1.7-8.7 bps against a 25 bps cap. They produce good quotes less often.
        #
        # THE HORIZON IS NEVER AN ALLOWED AGE. Every observation below must still satisfy
        # max_quote_age_seconds on its own; a longer horizon buys more CHANCES at a fresh
        # quote, it does not make a stale one acceptable. Single stocks keep the v3
        # attempt-count behaviour exactly (5 observations, 2s apart, ~8s horizon).
        rp = self.rp_for(is_cross_asset)
        spacing = float(rp["seconds_between_attempts"])
        horizon = rp.get("max_total_seconds")
        max_attempts = None if horizon is not None else int(rp["max_attempts"])
        started_at = now()
        attempt = 0
        while True:
            if max_attempts is not None:
                if attempt >= max_attempts:
                    break
            elif attempt and (now() - started_at).total_seconds() + spacing > float(horizon):
                break
            if attempt:
                await asyncio.sleep(spacing)
            attempt += 1
            q = await self.quote(symbol)
            quote_rec, half_bps, quote_age = None, None, None
            if q and q.bid_price and q.ask_price and q.ask_price > q.bid_price > 0:
                mid = (q.ask_price + q.bid_price) / 2
                half_bps = round((q.ask_price - q.bid_price) / 2 / mid * 1e4, 3)
                quote_age = round((now() - q.timestamp).total_seconds(), 2)
                quote_rec = {"bid": q.bid_price, "ask": q.ask_price, "mid": round(mid, 6),
                             "half_spread_bps": half_bps, "quote_age_s": quote_age,
                             "quote_ts": str(q.timestamp)}
            if is_cross_asset:
                if quote_rec is None:
                    stale = "missing/one-sided quote"
                    stale_code = "no_usable_print_or_quote"
                    continue
                if quote_age > cfg["max_quote_age_seconds"]:
                    stale = (f"quote age {quote_age}s > "
                             f"{cfg['max_quote_age_seconds']}s")
                    stale_code = "stale_reference"
                    continue
                if half_bps > cfg["max_half_spread_bps"]:
                    return (False, f"half-spread {half_bps}bps > "
                            f"{cfg['max_half_spread_bps']}", None,
                            "spread_failure")
                ref, ref_ts, ref_src = quote_rec["mid"], quote_rec["quote_ts"], "quote_mid"
                age = quote_age
            else:
                t = await self.trade(symbol)
                if not t or not t.price:
                    stale = "no trade print"
                    stale_code = "no_usable_print_or_quote"
                    continue
                age = round((now() - t.timestamp).total_seconds(), 2)
                if age > cfg["max_trade_age_seconds"]:
                    stale = (f"trade age {age}s > "
                             f"{cfg['max_trade_age_seconds']}s")
                    stale_code = "stale_reference"
                    continue
                ref, ref_ts, ref_src = float(t.price), str(t.timestamp), "last_trade"
            drift = abs(ref - manifest_price) / manifest_price * 100
            if drift > drift_cap:
                return (False, f"drift {drift:.3f}% > {drift_cap}% vs manifest "
                        f"{manifest_price}", None, "manifest_drift_failure")
            plan = {"reference_price": ref, "reference_ts": ref_ts,
                    "reference_source": ref_src, "reference_age_s": age,
                    "manifest_drift_pct": round(drift, 4), "quote": quote_rec}
            if is_cross_asset:
                plan.update(type="market", limit_price=None)
            else:
                collar = float(cfg["marketable_limit_collar_bps"]) / 1e4
                buy = side.lower().startswith("b")
                plan.update(type="limit",
                            limit_price=round(ref * (1 + collar if buy else 1 - collar), 2),
                            collar_bps=cfg["marketable_limit_collar_bps"])
            return True, (f"{ref_src} {ref} age {age}s drift {drift:.3f}%"
                          + (f" limit {plan['limit_price']}" if plan["limit_price"] else "")), plan, None
        horizon_desc = (f"{horizon}s wall-clock horizon, {attempt} observations"
                        if horizon is not None else f"{max_attempts} re-polls")
        return False, f"{stale} (after {horizon_desc})", None, stale_code

    # ---- terminality -----------------------------------------------------------------
    async def broker_state(self, coid, want_ts=False):
        """(status, filled_qty[, timestamps]) straight from the broker — source of truth."""
        o = await self.broker_order(coid)
        if o is None:
            return (None, Decimal(0), {}) if want_ts else (None, Decimal(0))
        st = str(o.status).upper().split(".")[-1]
        fq = Decimal(str(o.filled_qty or 0))
        if not want_ts:
            return st, fq
        ts = {"broker_fill_ts": str(o.filled_at) if getattr(o, "filled_at", None) else None,
              "broker_terminal_ts": str(getattr(o, "canceled_at", None) or
                                        getattr(o, "filled_at", None) or
                                        getattr(o, "updated_at", None) or ""),
              "broker_observed_at": iso()}
        return st, fq, ts

    async def await_terminal(self, coid, order_id, bound_s=90):
        """Poll the BROKER until the order is conclusively terminal.

        A timeout is NOT terminality. If we cannot establish a terminal state we halt
        rather than permit a second submission that could duplicate a live order.
        """
        t0 = now()
        last = None
        while (now() - t0).total_seconds() < bound_s:
            st, fq, bts = await self.broker_state(coid, want_ts=True)
            last = st
            if st in TERMINAL:
                plat = self.status_of(self.api(f"/orders/{order_id}"))
                if plat not in TERMINAL:
                    self.jlog(event="platform_broker_state_divergence", coid=coid,
                              order_id=order_id, broker_status=st, platform_status=plat,
                              note="broker is authoritative; platform ledger lagging")
                return {"status": st, "filled": fq, "platform_status": plat, **bts}
            await asyncio.sleep(2)
        raise Halt(f"cannot establish broker terminality for {coid} "
                   f"(last broker status {last or 'unknown'}); "
                   f"refusing to submit another attempt")

    async def observe_platform_settlement(self, max_wait_s=900, poll_s=15):
        """A8: governed ingestion wait before any ledger discrepancy is declared.

        The platform ledger is eventually consistent — measured at 8m31s behind a fill on
        2026-07-29. A post-trade reconciliation that compares immediately produces FALSE
        mismatches. This waits until every submitted attempt is terminal in the platform
        WITH its fill rows present, or until the reconciliation timeout expires. It is a
        poll to an observed condition, never a fixed sleep, and its results are telemetry:
        they never authorize a retry.
        """
        pending = [a for a in self.ledger.attempts if a.get("broker_order_id")]
        if not pending:
            return {"settled": 0, "unsettled": 0, "timed_out": False}
        t0 = now()
        outstanding = {a["broker_order_id"]: a for a in pending}
        while outstanding and (now() - t0).total_seconds() < max_wait_s:
            for oid, a in list(outstanding.items()):
                r = self.api(f"/orders/{oid}")
                st = self.status_of(r)
                fills = r.get("fills") or []
                if st in TERMINAL and (fills or Decimal(str(a.get("filled_qty", 0))) == 0):
                    a["platform_terminal_at"] = r.get("terminal_at") or iso()
                    a["platform_status_final"] = st
                    if fills:
                        a["platform_fill_ingested_at"] = iso()
                        bf = a.get("broker_fill_ts")
                        if bf:
                            try:
                                bt = datetime.fromisoformat(str(bf).replace("Z", "+00:00"))
                                a["fill_ingestion_lag_s"] = round(
                                    (now() - bt).total_seconds(), 2)
                            except ValueError:
                                pass
                    bo = a.get("broker_observed_at")
                    if bo:
                        try:
                            a["terminality_lag_s"] = round(
                                (now() - datetime.fromisoformat(bo)).total_seconds(), 2)
                        except ValueError:
                            pass
                    self.jlog(event="platform_settled", coid=a.get("client_order_id"),
                              order_id=oid, platform_status=st,
                              fill_ingestion_lag_s=a.get("fill_ingestion_lag_s"))
                    outstanding.pop(oid, None)
            if outstanding:
                await asyncio.sleep(poll_s)
        result = {"settled": len(pending) - len(outstanding),
                  "unsettled": len(outstanding),
                  "timed_out": bool(outstanding),
                  "unsettled_order_ids": list(outstanding)}
        self.jlog(event="platform_settlement_complete", **result)
        return result

    # ---- one logical order through up to K gated attempts ----------------------------
    async def execute_logical_order(self, *, symbol, side, intended_qty, manifest_price,
                                    stage, seq, coid_prefix, is_cross_asset,
                                    source="manual", strategy_id=None):
        intended = Decimal(str(intended_qty))
        cum_filled = Decimal(0)
        k_max = int(self.ap["max_attempts"])
        window = float(self.ap["fill_window_seconds_per_attempt"])
        disposition, attempts_used = None, 0

        for k in range(1, k_max + 1):
            attempts_used = k
            remaining = intended - cum_filled
            if remaining <= DUST:
                disposition = "FILLED"
                break

            rec = {"plan_id": self.plan_id, "stage": stage, "seq": seq,
                   "symbol": symbol, "side": side,
                   "intended_qty": str(intended), "requested_qty": str(remaining),
                   "attempt_number": k, "max_attempts": k_max,
                   "attempt_state": "PLANNED", "client_order_id": None,
                   "broker_order_id": None, "submitted_limit_price": None,
                   "reference_price": None, "reference_ts": None,
                   "quote_age_s": None, "spread_bps": None, "manifest_drift_pct": None,
                   "filled_qty": "0", "canceled_qty": "0",
                   "cancel_confirmed_ts": None, "reason": None}

            ok, detail, plan, abort_code = await self.gate(symbol=symbol, side=side,
                                               manifest_price=manifest_price,
                                               is_cross_asset=is_cross_asset)
            if not ok:
                rec["reason"] = f"gate abort: {detail}"
                rec["abort_reason"] = abort_code or "other_governed_gate"
                rec["failure_class"] = failure_class_of(rec["abort_reason"])
                rec["attempt_state"] = "RETRY_ELIGIBLE" if k < k_max else "EXHAUSTED"
                self.ledger.record_attempt(rec)
                self.jlog(event="gate", symbol=symbol, attempt=k, passed=False, detail=detail)
                if k < k_max:
                    continue
                disposition = "EXHAUSTED_GATE"
                break

            rec.update(attempt_state="GATE_PASSED",
                       reference_price=plan["reference_price"],
                       reference_ts=plan["reference_ts"],
                       reference_source=plan["reference_source"],
                       reference_age_s=plan["reference_age_s"],
                       quote_age_s=(plan["quote"] or {}).get("quote_age_s"),
                       spread_bps=(plan["quote"] or {}).get("half_spread_bps"),
                       quote_hash=hashlib.sha256(
                           json.dumps(plan["quote"], sort_keys=True, default=str).encode()
                       ).hexdigest() if plan["quote"] else None,
                       manifest_drift_pct=plan["manifest_drift_pct"],
                       submitted_limit_price=plan["limit_price"])
            self.jlog(event="gate", symbol=symbol, attempt=k, passed=True, detail=detail)

            coid = f"{coid_prefix}-{seq:03d}-a{k}"
            rec["client_order_id"] = coid
            body = {"symbol": symbol, "side": side, "qty": str(remaining),
                    "type": plan["type"], "tif": "day", "account_id": self.account_id,
                    "source": source, "client_order_id": coid}
            if strategy_id is not None:
                body["strategy_id"] = strategy_id
            if plan["limit_price"] is not None:
                body["limit_price"] = plan["limit_price"]

            try:
                resp = self.api("/orders", "POST", body)
            except urllib.error.HTTPError as e:
                rec["attempt_state"] = "HALTED_REQUIRES_REVIEW"
                rec["reason"] = f"HTTP {e.code}: {e.read().decode()[:200]}"
                rec["abort_reason"] = "broker_http_error"
                rec["failure_class"] = "HARD"
                self.ledger.record_attempt(rec)
                raise Halt(f"{symbol} attempt {k}: {rec['reason']}")

            if resp.get("rejection_reason"):
                rec["attempt_state"] = "HALTED_REQUIRES_REVIEW"
                rec["reason"] = f"risk refusal: {resp['rejection_reason']}"
                rec["abort_reason"] = "risk_refusal"
                rec["failure_class"] = "HARD"
                self.ledger.record_attempt(rec)
                raise Halt(f"{symbol} attempt {k}: risk refusal "
                           f"{resp['rejection_reason']}")

            oid = resp.get("id")
            rec["broker_order_id"] = oid
            rec["attempt_state"] = "SUBMITTED" if k == 1 else "RETRY_SUBMITTED"
            self.jlog(event="submitted", symbol=symbol, attempt=k, coid=coid, order_id=oid,
                      type=plan["type"], limit=plan["limit_price"], qty=str(remaining))

            # observe for the fill window — BROKER state, not the platform ledger
            t0, final = now(), None
            while (now() - t0).total_seconds() < window:
                await asyncio.sleep(3)
                st, fq = await self.broker_state(coid)
                if fq > 0 and st not in TERMINAL:
                    rec["attempt_state"] = "PARTIALLY_FILLED"
                if st in TERMINAL:
                    _s, _f, bts = await self.broker_state(coid, want_ts=True)
                    plat = self.status_of(self.api(f"/orders/{oid}"))
                    if plat not in TERMINAL:
                        self.jlog(event="platform_broker_state_divergence", coid=coid,
                                  order_id=oid, broker_status=st, platform_status=plat,
                                  note="broker is authoritative; platform ledger lagging")
                    final = {"status": st, "filled": fq, "platform_status": plat, **bts}
                    break

            if final is None:
                # window expired with the order still live -> cancel and CONFIRM
                rec["attempt_state"] = "CANCEL_REQUESTED"
                try:
                    self.api(f"/orders/{oid}", "DELETE")
                except urllib.error.HTTPError as e:
                    self.jlog(event="cancel_http_error", order_id=oid, code=e.code)
                final = await self.await_terminal(coid, oid)    # terminality, not timeout
                rec["cancel_confirmed_ts"] = iso()
                rec["attempt_state"] = "CANCEL_CONFIRMED"

            fq = final["filled"]
            rec["platform_status_at_settlement"] = final.get("platform_status")
            rec["broker_fill_ts"] = final.get("broker_fill_ts")
            rec["broker_terminal_ts"] = final.get("broker_terminal_ts")
            rec["broker_observed_at"] = final.get("broker_observed_at")
            # platform_* and the lags are filled in by observe_platform_settlement();
            # they are TELEMETRY ONLY and never authorize a retry.
            rec["platform_terminal_at"] = None
            rec["platform_fill_ingested_at"] = None
            rec["terminality_lag_s"] = None
            rec["fill_ingestion_lag_s"] = None
            cum_filled += fq
            rec["filled_qty"] = str(fq)
            rec["canceled_qty"] = str(max(Decimal(0), Decimal(rec["requested_qty"]) - fq))
            rec["broker_final_status"] = final["status"]
            if fq >= Decimal(rec["requested_qty"]) - DUST:
                rec["attempt_state"] = "FILLED"
            elif k < k_max:
                rec["attempt_state"] = "RETRY_ELIGIBLE"
            else:
                rec["attempt_state"] = "EXHAUSTED"
            self.ledger.record_attempt(rec)

            if intended - cum_filled <= DUST:
                disposition = "FILLED"
                break
            if k == k_max:
                disposition = "EXHAUSTED"

        # ---- residual valued from BROKER-CONFIRMED remaining qty ----------------------
        residual_qty = intended - cum_filled
        px = None
        t = await self.trade(symbol)
        if t and t.price:
            px = float(t.price)
        else:
            q = await self.quote(symbol)
            if q and q.bid_price and q.ask_price:
                px = (q.bid_price + q.ask_price) / 2
        residual_notional = float(residual_qty) * (px or manifest_price)
        out = {"plan_id": self.plan_id, "stage": stage, "seq": seq, "symbol": symbol,
               "side": side, "intended_qty": str(intended),
               "filled_qty": str(cum_filled), "residual_qty": float(residual_qty),
               "residual_valuation_price": px, "residual_notional": round(residual_notional, 4),
               "attempts_used": attempts_used, "final_disposition": disposition,
               "stage_tolerance_usd": self.ledger.tolerance}
        # PROTOCOL v2: the disposition carries the class of the LAST failure seen for this
        # logical order, so the continuation policy and the residual-debt record can both
        # read it without re-walking the attempt log.
        _mine = [a for a in self.ledger.attempts
                 if a.get("seq") == seq and a.get("stage") == stage
                 and a.get("abort_reason")]
        out["abort_reason"] = _mine[-1]["abort_reason"] if _mine else None
        out["failure_class"] = _mine[-1].get("failure_class") if _mine else None
        out["cumulative_stage_residual_usd"] = round(
            self.ledger.stage_residual(stage) + residual_notional, 2)
        self.ledger.record_order(out)
        return out
