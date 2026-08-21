"""Strategy 9 v1.3/C40 transition - STAGED EXECUTOR v10 (Protocol v2.1, hardened).

v10 = v9 bound to limits v8, plus three enforcement additions from the owner's review of
ADR 0054. No threshold, no per-stage policy and no order-level gate changes.

  1. TAXONOMY GOVERNANCE. The limits DECLARE the HARD/EXECUTABILITY code sets; v9 held them
     only as code. v10 refuses any limits file whose declaration differs from the code, so a
     new EXECUTABILITY code - which is BUDGET-ELIGIBLE, i.e. it lets a transition continue -
     cannot be created by editing a Python set. Widening one code at a time is how a
     fail-closed taxonomy quietly becomes fail-open.

  2. MANIFEST <-> LIMITS BINDING. v9 checked that the manifest's embedded limits SHA matched
     the sealed file on disk, then applied the manifest's EMBEDDED CONTENT. v10 additionally
     requires the embedded content to be identical to the sealed file and applies the DISK
     copy. The manifest discloses the limits it was reviewed under; it never supplies the
     policy that governs it. Same principle already applied to continuation_policy_resolved.

  3. ACTIVATION INVARIANTS (limits v8 continuation_policy.activation_invariants). Before any
     order: the residual-debt ledger must be writable and parseable, and no EARLIER halted
     transition may remain unresolved - every run whose stage status reached
     HALTED_REQUIRES_REVIEW must have a sealed disposition record. Fail-closed: an invariant
     that cannot be evaluated counts as failed.

v9 = v8 bound to limits v7, which scopes concentration-triggered completeness to

JOINT-CONSTRUCTION stages. Owner ruling 2026-08-21 (second ruling): under v2.0 the 50%
trigger was declared for all three stages, so a Stage A that collapsed to one or two
residual exits became completeness-required and zero-tolerance again - the exact
stage-denominator pathology Protocol v2 was built to remove. A one-order Stage A halted on
a $124.47 residual, half the budget, purely because one order is mathematically 100% of its
own stage. Exits are de-risking and independent; the joint-construction justification fits
the cross-asset sleeve, not exits.

In v2.1 exactly one stage is joint_construction: B_cross_asset. That is re-asserted below,
so widening it silently is a refusal rather than a configuration change. Nothing else moves:
the counting unit, the taxonomy, R_ABS/R_PCT, the 50% threshold itself, the residual-debt
rule and every order-level gate are unchanged, and Stage B still comes out
completeness-required at UUP 65.4%.

v8 = v7 with the STAGE-CONTINUATION RULE replaced, and NOTHING ELSE.

Every order-level
gate is byte-identical: 300s single-stock trade age, 10s cross-asset quote age, 25 bps
half-spread, 1.5% manifest drift, the 50 bps marketable-limit collar, K=2 / 120s, the 30s
cross-asset wall-clock horizon, the identity latch, the approval record, the risk engine,
broker-authoritative terminality and the $1.00 inter-stage reconciliation tolerance. The
sealed limits file this binds to (v8) asserts the same thing structurally: it changes no
numeric gate.

WHAT WAS WRONG (owner rulings 2026-08-21, evidence in
PROTOCOL_V2_POLICY_REPLAY_20260821.json)

  D1 UNIT MISMATCH. v7 check_stop_conditions() took `aborts` from
     ResidualLedger.attempt_opportunities(), which counts ATTEMPT records, and compared it
     against 0.10 * stage_order_count, an ORDER count. attempt_policy.max_attempts is 2, so
     one failing order contributed 2 and "> 3 aborts" meant "more than 1.5 failing orders":
     TWO failing orders halted a stage of ANY size. On 2026-08-20 exactly two orders failed
     - MS (seq 20) and PH (seq 34) - producing four abort records and halting a 36-order
     stage at 5.9% order-level failure. EBAY (seq 35) and FN (seq 36) were never attempted.
     Owner ruling: "Retries are execution mechanics. They must not multiply the economic
     failure count. 1 order x 2 failed attempts = 1 failed order."

  D1b DRY/LIVE DIVERGENCE. v7 dry mode called core.gate() once per order and wrote nothing
     to the residual ledger, so dry logged 1 abort per failing order where live logged 2 -
     and dry and live could return DIFFERENT continuation decisions for IDENTICAL failing
     orders. v8 records an imputed disposition per dry gate abort and runs the SAME
     evaluation, so a dry run that would halt live now halts in dry.

  D2 DENOMINATOR COLLAPSE. The >10% rule is denominated on the CURRENT manifest's stage,
     so a fail-closed re-plan after a partial transition shrinks the tolerance with the
     stage: A_exits went 36 -> 4 -> 5 orders and at 5 orders the first failure is 20%.

  D3 SMALL-STAGE ARITHMETIC. B_cross_asset is structurally 6 orders and 6 x 10% = 0.6 < 1,
     so it tolerated zero aborts by integer accident rather than by policy.

WHAT v8 DOES INSTEAD

  Continuation is decided by the per-stage policy declared in limits v6 and RESOLVED into
  the manifest at plan time, so the owner approves the rule together with the orders it
  governs. v8 RE-DERIVES that block from the sealed limits and REFUSES any manifest whose
  resolved block disagrees - the manifest discloses the rule, it never confers it.

      A_exits       residual budget $250 + absolute backstop 2 failed orders
      B_cross_asset the ONLY joint-construction stage: completeness-required whenever
                    its largest single order is >= 50% of the stage (UUP 65.4%)
      C_equity      budget $250 + backstop 3 + the 10%-with-floor count rule, all
                    applicable and the stricter binding

  HARD/system failures (risk refusal, broker HTTP error, unestablished terminality) halt
  immediately and never receive a budget. EXECUTABILITY failures (stale_reference, spread,
  drift, no usable print) refuse the individual order - which is NEVER force-submitted -
  and continuation is decided on the economic residual left behind.

  A PERMITTED residual creates a first-class RESIDUAL_CLEANUP_REQUIRED obligation
  (v13_residual_debt.py) that is carried into subsequent planning and never disappears
  because the symbol later re-enters the target universe.

  The owner-level "every individual gate must PASS" override is RETIRED (owner ruling
  2026-08-21). Hard/global gates still all have to pass; a single ~$65 stale-reference
  failure no longer burns a manifest when the stage is still admissible under its approved
  continuation policy.

HISTORICAL VALIDITY. v2 does not rewrite history: the 2026-08-20 Stage-A residual reached
$257.27 against the pre-existing $250 budget, so that run still halts under v8 on the
economic clause alone. That is asserted as a regression test.

v7 = v6 with the market-data regime MOVED INTO the frozen limits file (limits v5)
and the cross-asset QUOTE plane switched IEX -> SIP. The single-stock TRADE
reference stays IEX - that reference-semantics change was never scoped into P0-B2.
Authorized by the owner Monday-gate flow of 2026-08-17: sealed
P0C_PROSPECTIVE_AUTHORIZATION_20260816.json (a4cd4743...) and
P0A_STEP1_OWNER_ADJUDICATION_20260817.json (9331298b...). The feeds are no longer
module constants: they are READ FROM the sealed limits v5 file at import, the
planner embeds that file into every manifest by content+sha, and __init__ refuses
a manifest whose embedded limits lack or contradict the declared regime - so the
MANIFEST now records the regime it was reviewed under (the P0-B2 objective).
Absence of the market_data_regime block is a REFUSAL, never a default.
Also fixed, disclosed: the receipt "executor" label was stale at v5 since v6.
Limits v5 embeds no other change; execution core v2 is unchanged by v7.

v6 = v5 with the MARKET-DATA FEED MADE EXPLICIT and NO semantic change at the
current entitlement. v5 (and every executor before it) built
StockLatestQuoteRequest / StockLatestTradeRequest with no feed= argument, and
Alpaca documents the default for the latest endpoints as "the best feed available
under the subscription". That makes the Stage-B control semantics a function of a
BILLING state: buying a real-time SIP entitlement would silently move this gate
from IEX to SIP with no code change, no review and no new artifact sha.

OWNER RULING 2026-08-14 (P0-B1): "Changing an Alpaca subscription must never change
Strategy 9 execution semantics by itself." v6 therefore pins the feed EXPLICITLY,
and pins it to IEX - the value in force today - so that this revision is provably
behaviour-preserving. Moving to SIP is a SEPARATE, governed change (P0-B2) that
must be made deliberately and revalidated, never inherited from a purchase.

Limits v4, execution core v2 and planner v4 are unchanged by v6.

v5 = v4 with ONE defect fix and no semantic change. v4 halted the 2026-08-13
live run on the first completed order because run_stage() re-supplied seq,
symbol and side to jlog() that were already present in the core's return
value. The bug was inherited verbatim from v3 and was unreachable by any dry
run, simulator or conformance suite - see test_v13_live_fill_v5.py, which
drives run_stage() through a scripted SUCCESSFUL FILL rather than gates only.
Limits v4, execution core v2 and planner v4 are unchanged.

v4 = executor v3 with its limits and core bindings moved to the 2026-08-13
cross-asset quote-age amendment: limits v4 and v13_execution_core_v2. The ONLY
semantic change in the amendment is that cross-asset ETF orders may poll for a
qualifying quote until a 30-second WALL-CLOCK DEADLINE instead of ~8 seconds.
Quote age (10s), half-spread (25 bps), drift (1.5%), K=2, the 120s fill window,
the Stage-B abort thresholds, the 45-minute Stage-B timeout, single-stock
behaviour and pricing semantics are all UNCHANGED, and this module refuses to run
if the embedded limits say otherwise.

NOTE the 2026-08-12 retired manifest 88b73fdf... needs no additional hash pin here:
it embeds limits v3, so the limits-sha binding below already refuses it.

Authorized by the owner ruling of 2026-08-08 section 3: "build Transition Executor v3
using the already validated components v13_execution_core.py (a71720a2), limits v3
(18cbc436) and the existing 24/24 regression evidence." That authorization permits BUILD
AND VALIDATION ONLY. It is not authorization to submit transition orders.

PROVENANCE
  v1  v13_transition_executor.py     sha 7548526c...  limits v1  - sealed, OBSOLETE
  v2  v13_transition_executor_v2.py  sha ...          limits v2  - sealed, superseded
  v3  this file                                       limits v3

WHAT CHANGES IN v3 - and why each change exists

1. EVERY order is executed by v13_execution_core.ExecutionCore.execute_logical_order.
   v2 carried its own inline gate/settle logic written BEFORE the owner's 2026-07-29
   amendment-by-amendment ratification. The core is the artifact the SPY canary actually
   proved: bounded re-attempt K=2, 300s reference age, 120s fill window, 1.5% drift always
   measured against the REVIEWED MANIFEST price, broker-authoritative terminality, and one
   unified residual ledger. Duplicating that logic here would fork the proven code path,
   so v3 delegates rather than reimplements.

2. Limits v3 binding. A manifest embedding v1 limits (no attempt_policy) or v2 limits
   (fill_policy) is REFUSED - it was reviewed against gates that no longer govern.

3. IDENTITY LATCH (owner ruling section 1). Before any order, the live broker account
   number must equal the pinned value AND the manifest's own account. The 2026-08-08 latch
   established that the laptop variable ALPACA_PAPER_6_API_KEY holds account 7's key, so
   credential-name-based resolution is structurally forbidden here: v3 reads the broker's
   self-reported account_number and compares it to a hard-coded pin.

4. APPROVAL RECORD (owner ruling section 6). Live submission additionally requires an
   approval artifact naming the exact manifest hash. The 2026-07-28 finding that a
   NOT_APPROVED manifest was administratively prohibited but not structurally disabled is
   closed here: absence of an approval record is a refusal, not a warning.

5. Stop conditions are evaluated from the ledger's ratified A4 accounting (attempt
   opportunities = submitted + pre-submission gate aborts), never from submitted-only
   counts, which would hide IEX print sparsity.

UNCHANGED FROM v2 (proven guards, deliberately preserved)
  manifest self-hash == --approve-sha; embedded limits sha == sealed limits file on disk;
  DRY_RUN / NOT_AUTHORIZED / SUPERSEDED artifact_status refusal; per-order max notional and
  per-stage turnover caps enforced AT LOAD; idempotent client ids with resume; the
  four-state stage model persisted to disk; hold-don't-rebuild rollback doctrine on halt.
"""
import argparse
import asyncio
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/data/ops/acct7")

from v13_execution_core_v3 import (  # noqa: E402
    ExecutionCore, ResidualLedger, Halt, failure_class_of,
    EXECUTABILITY_ABORTS, HARD_ABORTS)
import v13_identity_latch as latch  # noqa: E402
import v13_continuation_policy as CP  # noqa: E402
import v13_residual_debt as DEBT  # noqa: E402

BASE = "http://localhost:8000/api/v1"
OPS = Path("/app/data/ops/acct7")
LIMITS_FILE = OPS / "ws1_evidence/v13/v13_frozen_execution_limits_v8.json"

# --- P0-B2: GOVERNED MARKET-DATA REGIME - READ FROM THE FROZEN LIMITS FILE ------
# P0-B1 froze the feeds as module constants so a billing event could not move
# execution semantics. P0-B2 moves the declaration INTO the sealed limits file so
# the MANIFEST records the regime (the planner embeds limits by content+sha) while
# preserving the P0-B1 discipline: the values are still part of the reviewed,
# sha-sealed identity and are still never derived from the account entitlement.
# A limits file without the block is limits v4 or earlier: REFUSE, never default.
_ALLOWED_FEEDS = {"iex", "sip"}
_regime = json.loads(LIMITS_FILE.read_text()).get("market_data_regime") or {}
EXECUTION_QUOTE_FEED = _regime.get("execution_quote_feed")
EXECUTION_TRADE_FEED = _regime.get("execution_trade_feed")
if (EXECUTION_QUOTE_FEED not in _ALLOWED_FEEDS
        or EXECUTION_TRADE_FEED not in _ALLOWED_FEEDS):
    raise SystemExit(
        "REFUSED: the sealed limits file must declare market_data_regime."
        "execution_quote_feed/execution_trade_feed in "
        f"{sorted(_ALLOWED_FEEDS)}; found "
        f"{EXECUTION_QUOTE_FEED!r}/{EXECUTION_TRADE_FEED!r} in {LIMITS_FILE}.")
RUN_DIR = Path("/app/data/v13_transition")
STAGES = ["A_exits", "B_cross_asset", "C_equity"]
CA_SET = {"SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"}

# Owner ruling 2026-08-08. Pinned in v13_identity_latch, never derived from a credential
# NAME; re-exported here so the module's own guards read from the single definition.
PINNED_BROKER_ACCOUNT = latch.EXPECTED_BROKER_ACCOUNT
PINNED_WORKBENCH_ACCOUNT_ID = latch.EXPECTED_WORKBENCH_ACCOUNT_ID
PINNED_STRATEGY_ID = latch.EXPECTED_STRATEGY_ID
PINNED_KEY_FINGERPRINT = latch.EXPECTED_KEY_FINGERPRINT
RETIRED_MANIFEST_SHA = (
    "1e9e0f949b112f57dc73aa245f4cec5f3e63d3e7c1670b03364c46102bf2bb36")

# ---------------------------------------------------------------------------------------
# ARTIFACT STATUS IS AN ALLOWLIST, NOT A DENYLIST.
#
# v1 and v2 both refuse on the substrings ("DRY_RUN", "NOT_AUTHORIZED", "SUPERSEDED").
# The disposition the owner actually applied to the 2026-07-28 manifest was
# NOT_APPROVED_FOR_EXECUTION, which contains none of them - the rehearsal labels used
# NOT_AUTHORIZED_FOR_EXECUTION while the owner's ruling used NOT_APPROVED_FOR_EXECUTION.
# A denylist that has to enumerate every future spelling of "no" fails open on the one it
# has not seen. v3 inverts it: a manifest executes only if its status is explicitly known
# to be executable, so an unrecognised label refuses instead of running.
#
# PLAN_PENDING_REVIEW stays executable because that is what the planner emits and the
# governing manifest carries; it is not self-approving - the section 6 approval record is
# an independent second gate that must name this exact manifest hash.
# ---------------------------------------------------------------------------------------
EXECUTABLE_STATUSES = {"PLAN_PENDING_REVIEW", "APPROVED_FOR_EXECUTION"}

RECON_TOLERANCE_USD = Decimal("1.00")   # inter_stage rule in limits v3
STAGE_KEY = CP.STAGE_KEY


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_of(text):
    return hashlib.sha256(text.encode()).hexdigest()


def iso():
    return datetime.now(UTC).isoformat()


class Refused(SystemExit):
    """Load-time refusal. Distinct from Halt, which is a mid-run stop."""


class TransitionExecutorV3:

    # ---- load-time validation ---------------------------------------------------------
    def __init__(self, manifest_path, approve_sha, dry_run, pacing=None):
        self.dry = dry_run
        self.manifest_path = Path(manifest_path)
        self.m = json.load(open(manifest_path))

        status = str(self.m.get("artifact_status", ""))
        if status.upper() not in EXECUTABLE_STATUSES:
            if not dry_run:
                raise Refused(
                    f"REFUSED: manifest artifact_status={status!r} is not an executable "
                    f"status. Executable statuses are {sorted(EXECUTABLE_STATUSES)}.")
            print(f"[dry-run] loading {status} manifest - nothing will be submitted")

        stated = self.m.get("manifest_sha256")
        body = dict(self.m)
        body.pop("manifest_sha256", None)
        if sha256_of(canonical(body)) != stated:
            raise Refused("REFUSED: manifest self-hash mismatch")
        if stated != approve_sha:
            raise Refused("REFUSED: --approve-sha does not match the manifest hash")
        if stated == RETIRED_MANIFEST_SHA:
            raise Refused(
                "REFUSED: this is the permanently retired manifest "
                f"{RETIRED_MANIFEST_SHA[:16]}... (owner instruction: never reuse)")

        # ---- limits v3 binding --------------------------------------------------------
        emb = self.m["frozen_execution_limits"]
        disk_sha = (hashlib.sha256(LIMITS_FILE.read_bytes()).hexdigest()
                    if LIMITS_FILE.exists() else None)
        if emb["sha256"] != disk_sha:
            raise Refused(
                "REFUSED: embedded limits sha != sealed limits file on disk "
                f"(manifest {emb['sha256'][:12]}... vs disk {str(disk_sha)[:12]}...). "
                "Only a manifest generated against limits v5 may be executed by v7.")
        # HARDENING (owner review 2026-08-21). v9 checked the embedded SHA against the
        # sealed file and then applied the manifest's EMBEDDED content. Those are different
        # objects: the sha is over the FILE BYTES, the content is parsed JSON, and nothing
        # tied the two together. v10 requires the embedded content to be identical to the
        # sealed file and applies the DISK copy, so the manifest discloses the limits it was
        # reviewed under and never supplies the policy that governs it.
        disk_limits = json.loads(LIMITS_FILE.read_text())
        if canonical(emb["content"]) != canonical(disk_limits):
            raise Refused(
                "REFUSED: the manifest's embedded limits CONTENT differs from the sealed "
                f"limits file {LIMITS_FILE.name}, even though the embedded sha matched. The "
                "sealed file is the authority; regenerate the manifest against it.")
        self.limits = disk_limits
        self.limits_identity = {
            "path": str(LIMITS_FILE), "sha256": disk_sha,
            "continuation_policy_version": (
                (disk_limits.get("continuation_policy") or {}).get("version")),
            "embedded_content_identical_to_sealed_file": True,
        }
        if "fill_policy" in self.limits:
            raise Refused("REFUSED: manifest embeds v2 limits (fill_policy present); "
                          "regenerate against limits v3")
        for required in ("attempt_policy", "residual_policy", "transient_staleness_repoll"):
            if required not in self.limits:
                raise Refused(f"REFUSED: manifest limits lack '{required}' - not limits v4")

        # ---- limits v4 binding -------------------------------------------------
        # v4 adds the per-instrument-class re-poll horizon (owner ruling
        # 2026-08-13). A manifest reviewed against v3 was reviewed against a ~8s
        # cross-asset horizon and must not be executed by a core that waits 30s,
        # so its absence is a refusal rather than a default.
        rp = self.limits["transient_staleness_repoll"]
        per = rp.get("per_instrument_class")
        if not per:
            raise Refused(
                "REFUSED: manifest limits lack transient_staleness_repoll."
                "per_instrument_class - that is limits v3 or earlier; regenerate "
                "against limits v4")
        ca = per.get("cross_asset_etf") or {}
        if ca.get("max_total_seconds") is None:
            raise Refused("REFUSED: limits v4 cross_asset_etf re-poll horizon "
                          "(max_total_seconds) is absent")

        # THE HORIZON IS NOT AN ALLOWED AGE. The v4 amendment extends only how long
        # the executor WAITS. If a limits file ever arrives with the cross-asset
        # quote-age or spread cap moved, it is not the reviewed amendment and this
        # refuses - the gate values are re-asserted here rather than trusted from
        # the embedded document.
        cae = self.limits["quote_gates"]["cross_asset_etf"]
        if cae["max_quote_age_seconds"] != 10:
            raise Refused("REFUSED: cross-asset max_quote_age_seconds is "
                          f"{cae['max_quote_age_seconds']}, not 10. The v4 "
                          "amendment extends the WAITING HORIZON only; it never "
                          "relaxes quote age.")
        if cae["max_half_spread_bps"] != 25:
            raise Refused("REFUSED: cross-asset max_half_spread_bps is "
                          f"{cae['max_half_spread_bps']}, not 25. Spread policy is "
                          "explicitly NOT changed by the v4 amendment "
                          "(owner ruling, 2026-08-13).")
        for _k in ("cross_asset_etf", "single_stock"):
            _d = self.limits["quote_gates"][_k][
                "max_price_drift_from_manifest_reference_pct"]
            if _d != 1.5:
                raise Refused(f"REFUSED: {_k} drift collar is {_d}, not 1.5")
        if self.limits["stage_limits"]["stage_B_cross_asset"]["timeout_minutes"] != 45:
            raise Refused("REFUSED: Stage-B timeout moved; v4 leaves it at 45 "
                          "minutes")

        # ---- limits v5 binding (P0-B2) ---------------------------------------
        # The regime is re-asserted from the EMBEDDED content against the sealed
        # module values (which come from the disk file). The disk-sha equality
        # above already implies this, but the embedded content is what was
        # REVIEWED - a manifest reviewed under different feed semantics must be
        # regenerated, never reinterpreted.
        reg = self.limits.get("market_data_regime") or {}
        if (reg.get("execution_quote_feed") != EXECUTION_QUOTE_FEED
                or reg.get("execution_trade_feed") != EXECUTION_TRADE_FEED):
            raise Refused(
                "REFUSED: manifest limits market_data_regime "
                f"({reg.get('execution_quote_feed')!r}/"
                f"{reg.get('execution_trade_feed')!r}) != sealed regime "
                f"({EXECUTION_QUOTE_FEED!r}/{EXECUTION_TRADE_FEED!r}); that is "
                "limits v4 or earlier, or a tampered regime - regenerate the "
                "manifest against limits v5.")

        self.qg = self.limits["quote_gates"]
        self.ap = self.limits["attempt_policy"]
        self.op = self.limits["order_policy"]
        self.sha = stated
        self.sha8 = stated[:8]
        self.pacing = pacing if pacing is not None else float(self.op["pacing_seconds"])
        self.run_id = self.m["run_id"]

        # ---- per-order and per-stage caps, enforced AT LOAD ---------------------------
        maxn = self.op["max_individual_order_notional_usd"]
        for o in self.m["orders"]:
            if abs(o.get("est_notional") or 0) > maxn:
                raise Refused(
                    f"REFUSED: order {o['symbol']} seq {o['seq']} notional "
                    f"{o.get('est_notional')} exceeds max {maxn}")
        totals = self.m.get("stage_totals_usd", {})
        equity = float(self.m["pre_run_state"]["equity"])
        for st in ("B_cross_asset", "C_equity"):
            cap = self.limits["stage_limits"][STAGE_KEY[st]]["max_turnover_pct_equity"]
            if totals.get(st, 0) > equity * cap / 100.0:
                raise Refused(
                    f"REFUSED: {st} turnover {totals.get(st)} exceeds the {cap}% cap "
                    f"({equity * cap / 100.0:.2f})")

        # ---- limits v6 binding: the governed continuation policy ----------------------
        # PROTOCOL v2. The policy lives in the SEALED limits file; the manifest carries a
        # RESOLVED copy so the rule is reviewed and hash-approved with the orders. This
        # block re-asserts the ruled parameters against the embedded content and then
        # RE-DERIVES the resolved block. A manifest whose disclosed rule differs from the
        # rule the executor will actually apply is refused, never reconciled.
        # _cp() validates the whole required policy shape - counting unit, the budget,
        # the concentration trigger, per-stage entries and joint_construction, the
        # precedence rule - and raises PolicyError, never a bare KeyError. A malformed
        # policy must refuse, not crash halfway through resolving.
        try:
            cp = CP._cp(self.limits)
        except CP.PolicyError as exc:
            raise Refused(f"REFUSED: {exc}")
        rb = cp["residual_budget"]
        tol = float(self.limits["residual_policy"]["tolerance_usd_per_stage"])
        if float(rb["R_ABS_usd"]) != tol:
            raise Refused(
                f"REFUSED: continuation_policy R_ABS_usd {rb['R_ABS_usd']} != "
                f"residual_policy.tolerance_usd_per_stage {tol}. The residual budget must "
                "have ONE value; two sources of truth is how a tolerance drifts.")
        if float(rb["R_PCT_equity"]) != 0.0:
            raise Refused(
                f"REFUSED: R_PCT_equity is {rb['R_PCT_equity']}, not 0.0. Owner ruling "
                "2026-08-21 set R_PCT = 0 for v2.0: 'Do not invent a percentage threshold "
                "without evidence.' Introducing one needs a new ruling and a new limits "
                "version, not a manifest.")
        if float(cp["concentration_trigger"]["threshold"]) != 0.50:
            raise Refused(
                f"REFUSED: concentration_trigger is "
                f"{cp['concentration_trigger']['threshold']}, not 0.50 (owner ruling "
                "2026-08-21).")
        # HARDENING: the declared taxonomy must equal the taxonomy the code applies.
        # An EXECUTABILITY code is budget-eligible, so widening the class must be a governed
        # limits change, never a Python-set edit that no artifact records.
        ft = cp["failure_taxonomy"]
        declared = {"HARD": set(ft["HARD"]["codes"]),
                    "EXECUTABILITY": set(ft["EXECUTABILITY"]["codes"])}
        actual = {"HARD": set(HARD_ABORTS), "EXECUTABILITY": set(EXECUTABILITY_ABORTS)}
        for cls in ("HARD", "EXECUTABILITY"):
            if declared[cls] != actual[cls]:
                raise Refused(
                    f"REFUSED: the limits declare {cls} codes "
                    f"{sorted(declared[cls])} but the executor applies "
                    f"{sorted(actual[cls])}. Declaration and behaviour must not drift; "
                    "adding an EXECUTABILITY code is a governed limits change, not a code "
                    "edit. Differences: "
                    f"{sorted(declared[cls] ^ actual[cls])}")
        if "governance" not in ft:
            raise Refused(
                "REFUSED: failure_taxonomy lacks the governance block - that is limits v7 "
                "or earlier; regenerate against limits v8.")
        if "activation_invariants" not in cp:
            raise Refused(
                "REFUSED: continuation_policy lacks activation_invariants - that is limits "
                "v7 or earlier; regenerate against limits v8.")
        if "lifecycle" not in cp["residual_debt_rule"]:
            raise Refused(
                "REFUSED: residual_debt_rule lacks the lifecycle block - that is limits v7 "
                "or earlier; regenerate against limits v8.")
        if (sorted(cp["residual_debt_rule"]["lifecycle"]["terminal_statuses"])
                != sorted(DEBT.TERMINAL_STATUSES)):
            raise Refused(
                "REFUSED: the declared residual-debt terminal statuses differ from the ones "
                f"the ledger enforces ({sorted(DEBT.TERMINAL_STATUSES)}).")

        # v2.1. Exactly ONE stage may be joint-construction, and it must be the cross-asset
        # sleeve. Widening this is what re-creates the collapsed-Stage-A pathology, so it is
        # a refusal rather than a configuration choice.
        joint = sorted(k for k, s in cp["per_stage"].items() if s.get("joint_construction"))
        if joint != ["stage_B_cross_asset"]:
            raise Refused(
                f"REFUSED: joint_construction stages are {joint}, not "
                "['stage_B_cross_asset']. Owner ruling 2026-08-21: concentration-triggered "
                "completeness applies only to joint-construction stages, which in v2.1 means "
                "B_cross_asset alone. Applying it to A_exits re-creates the collapsed-stage "
                "pathology this protocol exists to remove.")

        equity_pre = float(self.m["pre_run_state"]["equity"])
        resolved = self.m.get("continuation_policy_resolved")
        if not resolved:
            raise Refused(
                "REFUSED: manifest lacks continuation_policy_resolved - it was planned "
                "under Protocol v1, whose stage-continuation rule counted attempt records "
                "against an order denominator. Regenerate against planner v8.")
        try:
            derived = CP.resolve(self.limits, self.m["orders"], equity_pre)
        except CP.PolicyError as exc:
            raise Refused(f"REFUSED: {exc}")
        if canonical(derived) != canonical(resolved):
            diffs = [k for k in set(derived) | set(resolved)
                     if canonical(derived.get(k)) != canonical(resolved.get(k))]
            raise Refused(
                "REFUSED: the manifest's continuation_policy_resolved does not match the "
                f"policy re-derived from the sealed limits. Differing key(s): {diffs}. "
                "The manifest discloses the rule; it never confers it.")
        self.cpol = derived
        self.cp_stages = derived["stages"]

        # ---- journal / resume ---------------------------------------------------------
        suffix = ".dryrun" if dry_run else ""
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        self.journal_path = RUN_DIR / f"{self.run_id}.execution.v3{suffix}.jsonl"
        self.stages_path = RUN_DIR / f"{self.run_id}.stages.v3{suffix}.json"
        self.ledger_path = RUN_DIR / f"{self.run_id}.residual.v3{suffix}.jsonl"
        self.receipt_path = RUN_DIR / f"{self.run_id}.receipt.v3{suffix}.json"

        self.done_seqs = set()
        if self.journal_path.exists():
            for line in open(self.journal_path):
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("event") == "order_complete":
                    self.done_seqs.add(int(rec["seq"]))
        self.stages = (json.load(open(self.stages_path)) if self.stages_path.exists()
                       else {s: {"status": "NOT_STARTED"} for s in STAGES})

        self.ledger = ResidualLedger(
            self.ledger_path, self.limits["residual_policy"]["tolerance_usd_per_stage"])
        self.cookie = None
        self._creds = None
        self._data = None
        self._adapter = None
        self.account_id = int(self.m["pre_run_state"]["account_id"])
        self.identity = None
        # RESIDUAL_CLEANUP_REQUIRED obligations created by THIS run (live only).
        self.debt_created = []

    # ---- plumbing ---------------------------------------------------------------------
    def jlog(self, **rec):
        rec = {"ts": iso(), **rec}
        with open(self.journal_path, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")

    def set_stage(self, stage, status, **extra):
        self.stages[stage] = {**self.stages.get(stage, {}), "status": status,
                              f"{status.lower()}_at": iso(), **extra}
        json.dump(self.stages, open(self.stages_path, "w"), indent=1)
        self.jlog(event="stage_status", stage=stage, status=status, **extra)

    def login(self):
        pw = (OPS / "user7_password.txt").read_text().strip()
        req = urllib.request.Request(
            f"{BASE}/auth/login",
            data=json.dumps({"email": "combined-book@globalcomplyai.com",
                             "password": pw}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            self.cookie = r.headers.get("set-cookie", "").split(";")[0]

    async def creds(self):
        if self._creds is None:
            from app.brokers.alpaca.credentials import credentials_for_mode
            from app.db.session import get_sessionmaker
            self._creds = await credentials_for_mode(
                "paper", PINNED_WORKBENCH_ACCOUNT_ID, get_sessionmaker())
        return self._creds

    async def adapter(self):
        if self._adapter is None:
            from app.brokers.alpaca import AlpacaAdapter
            a = AlpacaAdapter(await self.creds())
            a.connect()
            self._adapter = a
        return self._adapter

    async def data_client(self):
        if self._data is None:
            from alpaca.data.historical import StockHistoricalDataClient
            c = await self.creds()
            self._data = StockHistoricalDataClient(c.api_key, c.api_secret)
        return self._data

    async def quote(self, symbol):
        from alpaca.data.requests import StockLatestQuoteRequest
        cl = await self.data_client()
        return cl.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=symbol,
                                    feed=EXECUTION_QUOTE_FEED)).get(symbol)

    async def trade(self, symbol):
        from alpaca.data.requests import StockLatestTradeRequest
        cl = await self.data_client()
        return cl.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=symbol,
                                    feed=EXECUTION_TRADE_FEED)).get(symbol)

    async def positions(self):
        a = await self.adapter()
        return {p["symbol"]: Decimal(str(p["qty"])) for p in a.get_positions()}

    async def broker_order(self, coid):
        """Broker-authoritative order lookup by client order id (A8)."""
        a = await self.adapter()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=500)
        for o in a._client().get_orders(filter=req):
            if o.client_order_id == coid:
                return o
        return None

    # ---- section 1: identity latch ----------------------------------------------------
    async def latch_identity(self):
        """The owner's five-point latch, delegated to the shared definition.

        The manifest's own strategy_id is checked too: a manifest planned for another
        strategy must not be executed against strategy 9's account even if the broker
        identity happens to match.
        """
        strategy_id = int(
            (self.m.get("classification") or {}).get("strategy_id")
            or (self.m.get("strategy") or {}).get("id")
            or PINNED_STRATEGY_ID)
        evidence = await latch.verify_live(
            creds=await self.creds(), adapter=await self.adapter(),
            workbench_account_id=self.account_id, strategy_id=strategy_id,
            context="executor v3 preflight")
        self.identity = evidence
        self.jlog(event="identity_latch", **evidence)
        print(f"  identity latch PASS - broker returned "
              f"{evidence['observed']['broker_account_number']}, key fp "
              f"{evidence['observed']['key_fingerprint']}, wb account "
              f"{self.account_id}, strategy {strategy_id}")
        return evidence

    # ---- section 6: approval record ---------------------------------------------------
    def require_approval_record(self):
        """Live submission requires an explicit approval artifact for THIS hash.

        Closes the 2026-07-28 gap where a NOT_APPROVED manifest was administratively
        prohibited but structurally executable.
        """
        path = self.manifest_path.parent / f"APPROVAL_{self.run_id}.json"
        if not path.exists():
            raise Refused(
                f"REFUSED: no approval record at {path}. Owner approval of the exact "
                "manifest hash is required before any transition order.")
        rec = json.load(open(path))
        if rec.get("approved_manifest_sha256") != self.sha:
            raise Refused(
                "REFUSED: approval record names "
                f"{str(rec.get('approved_manifest_sha256'))[:16]}..., manifest is "
                f"{self.sha[:16]}...")
        if str(rec.get("decision", "")).upper() != "APPROVED":
            raise Refused(f"REFUSED: approval record decision={rec.get('decision')}")
        self.jlog(event="approval_record_verified", path=str(path),
                  approved_by=rec.get("approved_by"), approved_at=rec.get("approved_at"))
        return rec

    # ---- preflight --------------------------------------------------------------------
    async def preflight(self):
        print("\n=== PREFLIGHT ===")
        await self.latch_identity()

        a = await self.adapter()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        opens = a._client().get_orders(
            filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))
        if opens:
            raise Refused(f"REFUSED: {len(opens)} open broker orders exist; the manifest "
                          "was planned against a flat order book")
        print(f"  broker open orders: 0")

        live = await self.positions()
        expected = {k: Decimal(str(v))
                    for k, v in self.m["pre_run_state"]["positions"].items()}
        drift = sorted(set(live) ^ set(expected)) + [
            s for s in set(live) & set(expected) if live[s] != expected[s]]
        if drift:
            self.jlog(event="preflight_position_drift", symbols=drift[:40],
                      n=len(drift))
            raise Refused(
                f"REFUSED: broker positions drifted from the manifest's pre_run_state "
                f"in {len(drift)} symbol(s): {drift[:10]}. Regenerate the manifest.")
        print(f"  positions reconcile to manifest pre_run_state: {len(live)} symbols")
        inv = self.check_activation_invariants()
        self.jlog(event="preflight_ok", positions=len(live), open_orders=0,
                  activation_invariants=inv)
        return live

    # ---- activation invariants (limits v8) ---------------------------------------------
    def check_activation_invariants(self):
        """Preconditions for BEGINNING a run - not extra stage-continuation rules.

        Fail-closed: an invariant that cannot be evaluated counts as failed.
        """
        result = {}

        h = DEBT.health()
        result["residual_debt_ledger"] = h
        if not h["healthy"]:
            raise Refused(
                "REFUSED: the residual-debt ledger is not healthy (%s). A run that may need "
                "to record a RESIDUAL_CLEANUP_REQUIRED obligation must not begin unable to "
                "write one." % h["problem"])
        print(f"  residual-debt ledger healthy: {h['open_obligations']} open obligation(s)")

        unresolved = []
        for sp in sorted(RUN_DIR.glob("*.stages.v3.json")):
            run_id = sp.name[:-len(".stages.v3.json")]
            if run_id == self.run_id:
                continue          # resuming THIS run is the sanctioned path, not a blocker
            try:
                stages = json.loads(sp.read_text())
            except ValueError as exc:
                raise Refused(
                    f"REFUSED: cannot evaluate the halted-transition invariant - "
                    f"{sp.name} is unreadable ({exc}). Fail closed.")
            if not any(str(v.get("status")) == "HALTED_REQUIRES_REVIEW"
                       for v in stages.values() if isinstance(v, dict)):
                continue
            if not (RUN_DIR / f"DISPOSITION_{run_id}.json").exists():
                unresolved.append(run_id)
        result["unresolved_halted_transitions"] = unresolved
        if unresolved:
            raise Refused(
                "REFUSED: earlier halted transition(s) remain unresolved: "
                f"{unresolved}. Every run whose stage status reached "
                "HALTED_REQUIRES_REVIEW needs a sealed disposition record before another "
                "transition may begin.")
        print("  no unresolved halted transitions")
        return result

    # ---- stop conditions --------------------------------------------------------------
    def stage_state(self, stage):
        """The order-level facts the continuation policy consumes.

        PROTOCOL v2: FAILED LOGICAL ORDERS, never attempt records. HARD failures are
        collected from both the attempt log (live) and the order dispositions (dry
        parity) and de-duplicated by seq, so one bad order counts once either way.
        """
        hard_seqs = {a.get("seq") for a in self.ledger.hard_failures(stage=stage)}
        hard_seqs |= {o.get("seq") for o in self.ledger.failed_order_records(stage)
                      if o.get("failure_class") == "HARD"}
        return {
            "failed_orders": self.ledger.failed_orders(stage),
            "failed_symbols": self.ledger.failed_order_symbols(stage),
            "stage_residual_usd": self.ledger.stage_residual(stage),
            "hard_failures": len(hard_seqs),
        }

    def check_stop_conditions(self, stage, stage_order_count, started_at):
        st = self.stage_state(stage)
        ok, clause, detail = CP.evaluate(self.cp_stages[stage], **st)
        self.jlog(event="continuation_check", stage=stage, decision=("CONTINUE" if ok
                                                                     else "HALT"),
                  binding_clause=clause, detail=detail, dry_run=self.dry, **st)
        if not ok:
            raise Halt(f"{stage}: [{clause}] {detail}")
        # The stage clock is the executor's, not the policy's - clause 6 of the
        # evaluation order. Unchanged from v7.
        timeout_min = self.limits["stage_limits"][STAGE_KEY[stage]]["timeout_minutes"]
        if (time.time() - started_at) > timeout_min * 60:
            raise Halt(f"{stage}: stage timeout of {timeout_min} minutes expired")

    # ---- one stage --------------------------------------------------------------------
    async def run_stage(self, stage, core):
        orders = [o for o in self.m["orders"] if o.get("stage") == stage]
        orders.sort(key=lambda o: o["seq"])
        if not orders:
            self.set_stage(stage, "COMPLETE", order_count=0, note="no orders in stage")
            return {}

        print(f"\n=== STAGE {stage} - {len(orders)} orders ===")
        self.set_stage(stage, "IN_PROGRESS", order_count=len(orders))
        started_at = time.time()
        before = await self.positions()
        filled_by_symbol = {}

        for o in orders:
            if o["seq"] in self.done_seqs:
                print(f"  seq {o['seq']:3d} {o['symbol']:<6} already settled - skipping")
                continue

            is_ca = o["symbol"] in CA_SET
            if self.dry:
                ok, detail, plan, abort_code = await core.gate(
                    symbol=o["symbol"], side=o["side"],
                    manifest_price=float(o["sizing_price"]), is_cross_asset=is_ca)
                print(f"  seq {o['seq']:3d} {o['symbol']:<6} {o['side']:<4} "
                      f"gate={'PASS' if ok else 'ABORT'}  {detail}")
                # `stage` was missing from this record in v7, which is why the 08-20
                # dry journals report every gate under stage "?" and a per-stage dry
                # adjudication had to be reconstructed from the manifest.
                self.jlog(event="dry_gate", stage=stage, seq=o["seq"],
                          symbol=o["symbol"],
                          side=o["side"], passed=ok, detail=detail,
                          abort_reason=abort_code, is_cross_asset=is_ca,
                          limit_price=(plan or {}).get("limit_price"))
                if not ok:
                    # PROTOCOL v2 DRY-RUN PARITY. Impute the residual at the REVIEWED
                    # manifest reference - a dry run submits nothing, so no broker-
                    # confirmed residual exists - and evaluate the identical policy.
                    code = abort_code or "other_governed_gate"
                    est = o.get("est_notional")
                    if est is None:
                        est = float(o["qty"]) * float(o["sizing_price"])
                    self.ledger.record_dry_order({
                        "plan_id": self.run_id, "stage": stage, "seq": o["seq"],
                        "symbol": o["symbol"], "side": o["side"],
                        "intended_qty": str(o["qty"]), "filled_qty": "0",
                        "residual_qty": float(o["qty"]),
                        "residual_valuation_price": float(o["sizing_price"]),
                        "residual_notional": round(abs(float(est)), 4),
                        "attempts_used": 0,
                        "final_disposition": "DRY_GATE_ABORT",
                        "abort_reason": code,
                        "failure_class": failure_class_of(code),
                        "stage_tolerance_usd": self.ledger.tolerance,
                    })
                self.check_stop_conditions(stage, len(orders), started_at)
                continue

            out = await core.execute_logical_order(
                symbol=o["symbol"], side=o["side"], intended_qty=o["qty"],
                manifest_price=float(o["sizing_price"]), stage=stage, seq=o["seq"],
                coid_prefix=f"twb-v13t-{self.sha8}", is_cross_asset=is_ca,
                source="strategy", strategy_id=PINNED_STRATEGY_ID)

            signed = Decimal(out["filled_qty"]) * (1 if o["side"] == "buy" else -1)
            filled_by_symbol[o["symbol"]] = filled_by_symbol.get(
                o["symbol"], Decimal(0)) + signed
            # DEFECT FIX 2026-08-13 (owner ruling). execute_logical_order() already
            # returns seq, symbol and side inside `out`, so passing them as explicit
            # keywords AND again via **out raised
            #   TypeError: jlog() got multiple values for keyword argument 'seq'
            # on the FIRST completed order of the 2026-08-13 live run - after the
            # NVDA exit had already filled at the broker. The defect was inherited
            # unchanged from executor v3 and could not be reached by any dry run,
            # because dry mode `continue`s above without ever calling
            # execute_logical_order. Build the record instead of splatting over
            # explicit keywords: `out` is authoritative for any field it carries.
            rec = {"seq": o["seq"], "symbol": o["symbol"], "side": o["side"]}
            rec.update(out)
            self.jlog(event="order_complete", **rec)
            print(f"  seq {o['seq']:3d} {o['symbol']:<6} {o['side']:<4} "
                  f"{out['final_disposition']:<14} filled={out['filled_qty']} "
                  f"residual=${out['residual_notional']}")

            self.check_stop_conditions(stage, len(orders), started_at)
            await asyncio.sleep(self.pacing)

        if self.dry:
            self.set_stage(stage, "COMPLETE", note="dry-run: gates only, nothing submitted")
            return {}

        # poll-to-settlement telemetry, then reconcile on BROKER state (A8)
        await core.observe_platform_settlement()
        await self.reconcile(stage, before, filled_by_symbol)
        obligations = self.record_residual_debt(stage)
        self.set_stage(stage, "COMPLETE",
                       residual_usd=self.ledger.stage_residual(stage),
                       failed_orders=self.ledger.failed_orders(stage),
                       failed_order_symbols=self.ledger.failed_order_symbols(stage),
                       residual_cleanup_obligations=len(obligations),
                       attempt_stats=self.ledger.attempt_opportunities(stage=stage))
        return filled_by_symbol

    # ---- residual operational debt ------------------------------------------------------
    def record_residual_debt(self, stage):
        """A PERMITTED residual becomes a RESIDUAL_CLEANUP_REQUIRED obligation.

        Only on a stage that COMPLETED, and only live. A halted stage's residual is
        disclosed in the receipt and goes to owner review, which is a stronger control
        than an obligation; minting debt for a run under review would imply the residual
        had been accepted when it has not.
        """
        if self.dry:
            return []
        created = []
        for d in self.ledger.failed_order_records(stage):
            created.append(DEBT.build(
                strategy_id=PINNED_STRATEGY_ID, account_id=self.account_id,
                run_id=self.run_id, manifest_sha256=self.sha, stage=stage,
                disposition=d))
        if created:
            DEBT.record_many(created)
            self.debt_created.extend(created)
            print(f"  RESIDUAL_CLEANUP_REQUIRED x{len(created)}: "
                  + ", ".join(f"{c['symbol']} ${c['governed_residual_valuation_usd']}"
                              for c in created))
            self.jlog(event="residual_cleanup_required", stage=stage,
                      count=len(created), obligations=created)
        return created

    # ---- inter-stage reconciliation ---------------------------------------------------
    async def reconcile(self, stage, before, filled_by_symbol):
        after = await self.positions()
        symbols = set(before) | set(after) | set(filled_by_symbol)
        problems = []
        for s in sorted(symbols):
            expected = before.get(s, Decimal(0)) + filled_by_symbol.get(s, Decimal(0))
            actual = after.get(s, Decimal(0))
            delta = abs(actual - expected)
            if delta == 0:
                continue
            px = None
            t = await self.trade(s)
            if t and t.price:
                px = Decimal(str(t.price))
            notional = delta * (px or Decimal(0))
            if notional > RECON_TOLERANCE_USD:
                problems.append({"symbol": s, "expected": str(expected),
                                 "actual": str(actual), "delta_qty": str(delta),
                                 "delta_usd": float(round(notional, 2))})
        self.jlog(event="reconciliation", stage=stage, problems=problems,
                  tolerance_usd=float(RECON_TOLERANCE_USD))
        if problems:
            raise Halt(f"{stage}: reconciliation mismatch beyond $1.00/position: "
                       f"{problems[:5]}")
        print(f"  reconciliation PASS (<= ${RECON_TOLERANCE_USD}/position)")

    # ---- receipt ----------------------------------------------------------------------
    def write_receipt(self, result, halted=None):
        receipt = {
            "artifact": "STRATEGY9_V13_C40_TRANSITION_EXECUTION_RECEIPT",
            "executor": "v13_transition_executor_v10.py",
            "executor_sha256": sha256_of(Path(__file__).read_text()),
            "execution_core_sha256": sha256_of(
                (OPS / "v13_execution_core_v3.py").read_text()),
            "continuation_policy_sha256": sha256_of(
                (OPS / "v13_continuation_policy.py").read_text()),
            "market_data_regime": {"quote_feed": EXECUTION_QUOTE_FEED,
                                   "trade_feed": EXECUTION_TRADE_FEED,
                                   "selected_explicitly": True,
                                   "declared_in": LIMITS_FILE.name,
                                   "depends_on_account_entitlement": False},
            "frozen_limits_sha256": hashlib.sha256(
                LIMITS_FILE.read_bytes()).hexdigest(),
            "limits_identity": self.limits_identity,
            "approved_manifest_sha256": self.sha,
            "run_id": self.run_id,
            "dry_run": self.dry,
            "identity_latch": self.identity,
            "stages": self.stages,
            "result": result,
            "halted_reason": halted,
            "residual_summary": self.ledger.summary(),
            "stage_residuals_usd": {s: self.ledger.stage_residual(s) for s in STAGES},
            # PROTOCOL v2. The v1 receipt reported pre_submission_gate_aborts, which is an
            # ATTEMPT count and read 0 for every dry run because dry mode submitted
            # nothing - a receipt that said "DRY_RUN_COMPLETE, zero aborts" over a real
            # abort. These fields are the ORDER-level facts the decision was actually made
            # on, so the receipt can be adjudicated without re-reading the journal.
            "continuation_policy_resolved": self.cpol,
            "counting_unit": CP.COUNTING_UNIT,
            "continuation_evaluation": {
                s: {**self.stage_state(s),
                    "policy": self.cp_stages[s],
                    "decision": ("HALT" if not CP.evaluate(
                        self.cp_stages[s], **self.stage_state(s))[0] else "CONTINUE"),
                    "binding_clause": CP.evaluate(
                        self.cp_stages[s], **self.stage_state(s))[1]}
                for s in STAGES},
            "residual_operational_debt": {
                "created_by_this_run": self.debt_created,
                "open_after_this_run": (DEBT.summary_for_disclosure(
                    account_id=self.account_id, strategy_id=PINNED_STRATEGY_ID)
                    if not self.dry else None),
            },
            "completed_at_utc": iso(),
        }
        receipt["receipt_sha256"] = sha256_of(canonical(receipt))
        json.dump(receipt, open(self.receipt_path, "w"), indent=2, default=str)
        print(f"\nreceipt -> {self.receipt_path}")
        print(f"receipt_sha256 {receipt['receipt_sha256']}")
        return receipt

    # ---- run --------------------------------------------------------------------------
    async def run(self):
        self.login()
        if not self.dry:
            self.require_approval_record()
        await self.preflight()

        core = ExecutionCore(
            limits=self.limits, base_url=BASE, cookie_provider=lambda: self.cookie,
            quote_fn=self.quote, trade_fn=self.trade, positions_fn=self.positions,
            ledger=self.ledger, plan_id=self.run_id, account_id=self.account_id,
            jlog=self.jlog, broker_order_fn=self.broker_order)

        try:
            for stage in STAGES:
                if self.stages.get(stage, {}).get("status") == "COMPLETE" and not self.dry:
                    print(f"\n=== STAGE {stage} already COMPLETE - skipping ===")
                    continue
                await self.run_stage(stage, core)
        except Halt as exc:
            for stage in STAGES:
                if self.stages.get(stage, {}).get("status") == "IN_PROGRESS":
                    self.set_stage(stage, "HALTED_REQUIRES_REVIEW", reason=str(exc))
            print(f"\n*** HALTED_REQUIRES_REVIEW: {exc}")
            print(self.limits["rollback_doctrine"])
            self.write_receipt("HALTED_REQUIRES_REVIEW", halted=str(exc))
            return 2

        result = "DRY_RUN_COMPLETE" if self.dry else "COMPLETE"
        self.write_receipt(result)
        print(f"\n{result}")
        return 0


def main():
    ap = argparse.ArgumentParser(
        description="Strategy 9 v1.3/C40 staged transition executor v10 (Protocol v2.1, hardened)")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--approve-sha", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="run gates and all validation; submit nothing")
    ap.add_argument("--pacing", type=float, default=None)
    args = ap.parse_args()
    ex = TransitionExecutorV3(args.manifest, args.approve_sha, args.dry_run, args.pacing)
    sys.exit(asyncio.run(ex.run()))


if __name__ == "__main__":
    main()
