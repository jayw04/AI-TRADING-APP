"""Conformance suite for Transition Executor v10 - refusal guards, v3 + Protocol v2.1
hardened.

NOTE ON THE LIMITS NEGATIVE TESTS. v10 requires the manifest's embedded limits to be
identical to the sealed file and then applies the DISK copy, so mutating a manifest's
embedded content no longer reaches the downstream assertions - it is refused outright.
Those tests now mutate the SEALED FILE the executor reads, via sealed_as(), which is a
stronger statement of the same property: the executor validates the file it applies.

Ported from the v7 suite. Every v3-era guard is retained verbatim; section 10 adds
the Protocol v2 guards, whose shared property is that the executor refuses a
manifest that DISCLOSES a continuation rule different from the one it would apply.

Every check here is a REFUSAL check: the property being proven is that the executor
declines to act, because for this component declining is the safety property. Network is
not required; the identity latch is exercised against a stubbed broker so that both the
match and mismatch branches are covered without touching a live account.

Run inside the backend container:
    docker exec -i workbench-backend python /app/data/ops/acct7/test_v13_executor_v3.py
"""
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/data/ops/acct7")

import v13_transition_executor_v10 as X  # noqa: E402
import v13_continuation_policy as CP  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def refuses(name, fn, expect_substr):
    try:
        fn()
        check(name, False, "no refusal raised")
    except SystemExit as e:          # Refused subclasses SystemExit
        check(name, expect_substr.lower() in str(e).lower(), str(e)[:160])
    except Exception as e:
        check(name, False, f"{type(e).__name__}: {e}")


LIMITS_V3 = json.load(open(X.LIMITS_FILE))
LIMITS_V3_SHA = hashlib.sha256(X.LIMITS_FILE.read_bytes()).hexdigest()


def make_manifest(tmp, *, limits_content=None, limits_sha=None, status="PLAN_PENDING_REVIEW",
                  account_id=7, orders=None, equity=100000.0, stage_totals=None,
                  run_id="OTR-TEST-V3", break_self_hash=False, cp_resolved=None,
                  drop_cp_resolved=False):
    orders = orders if orders is not None else [
        {"seq": 1, "symbol": "AAPL", "side": "sell", "qty": "0.5", "type": "market",
         "tif": "day", "sizing_price": 200.0, "intent": "exit", "est_notional": 100.0,
         "stage": "A_exits"},
        {"seq": 2, "symbol": "UUP", "side": "buy", "qty": "10", "type": "market",
         "tif": "day", "sizing_price": 27.0, "intent": "entry", "est_notional": 270.0,
         "stage": "B_cross_asset"},
    ]
    body = {
        "artifact_status": status,
        "run_id": run_id,
        "frozen_execution_limits": {
            "sha256": limits_sha if limits_sha is not None else LIMITS_V3_SHA,
            "content": limits_content if limits_content is not None else LIMITS_V3,
        },
        "pre_run_state": {"account_id": account_id, "equity": equity,
                          "positions": {"AAPL": "0.5"}},
        "orders": orders,
        "stage_totals_usd": stage_totals or {"A_exits": 100.0, "B_cross_asset": 270.0,
                                             "C_equity": 0.0},
    }
    # PROTOCOL v2: the resolved continuation rule is part of the hashed body. Built with
    # the SAME shared module the executor re-derives with, so a correct manifest matches
    # by construction and only a deliberately tampered one diverges. Limits shapes that
    # carry no continuation_policy refuse earlier, at the limits binding, so omitting the
    # block for them is what the executor will actually see in the field.
    if cp_resolved is not None:
        body["continuation_policy_resolved"] = cp_resolved
    else:
        try:
            body["continuation_policy_resolved"] = CP.resolve(
                body["frozen_execution_limits"]["content"], body["orders"], equity)
        except CP.PolicyError:
            pass
    if drop_cp_resolved:
        body.pop("continuation_policy_resolved", None)
    body["manifest_sha256"] = X.sha256_of(X.canonical(body if not break_self_hash
                                                      else {**body, "run_id": "TAMPERED"}))
    p = Path(tmp) / f"{run_id}.json"
    json.dump(body, open(p, "w"), indent=1)
    return p, body["manifest_sha256"]


def sealed_as(tmp, limits_dict, run_id):
    """Point the executor at a MUTATED sealed limits file and build a matching manifest.

    v10 applies the limits file on disk, not the manifest's copy, so a negative test about
    limits content has to change the file the executor reads. The manifest embeds the same
    content and its real sha, so the binding check passes and the assertion under test is
    the one that fires. The caller restores X.LIMITS_FILE.
    """
    text = json.dumps(limits_dict, indent=2, ensure_ascii=True) + "\n"
    p = Path(tmp) / ("sealed_%s.json" % run_id)
    p.write_text(text, encoding="ascii", newline="\n")
    real_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    X.LIMITS_FILE = p
    return make_manifest(tmp, run_id=run_id, limits_content=limits_dict,
                         limits_sha=real_sha)


def refuses_sealed(tmp, name, limits_dict, run_id, expect):
    """refuses(), with the sealed limits file swapped for the duration."""
    original = X.LIMITS_FILE
    try:
        p, sha = sealed_as(tmp, limits_dict, run_id)
        refuses(name, lambda: X.TransitionExecutorV3(str(p), sha, dry_run=True), expect)
    finally:
        X.LIMITS_FILE = original


def main():
    tmp = tempfile.mkdtemp(prefix="v3test_")
    print("=== Transition Executor v3 - refusal conformance ===\n")

    # --- 1. happy load ---------------------------------------------------------------
    p, sha = make_manifest(tmp)
    ex = X.TransitionExecutorV3(str(p), sha, dry_run=True)
    check("loads a well-formed limits-v3 manifest", ex.sha == sha)
    check("binds the sealed limits v3 file",
          hashlib.sha256(X.LIMITS_FILE.read_bytes()).hexdigest() == LIMITS_V3_SHA)
    check("pacing defaults from limits order_policy",
          ex.pacing == float(LIMITS_V3["order_policy"]["pacing_seconds"]))

    # --- 2. hash integrity ------------------------------------------------------------
    refuses("refuses a tampered manifest (self-hash mismatch)",
            lambda: X.TransitionExecutorV3(str(make_manifest(
                tmp, run_id="OTR-TAMPER", break_self_hash=True)[0]),
                "0" * 64, dry_run=True),
            "self-hash mismatch")

    p2, sha2 = make_manifest(tmp, run_id="OTR-SHA")
    refuses("refuses when --approve-sha does not match the manifest",
            lambda: X.TransitionExecutorV3(str(p2), "f" * 64, dry_run=True),
            "approve-sha")

    # --- 3. the permanently retired manifest -----------------------------------------
    check("the retired manifest hash is pinned in code",
          X.RETIRED_MANIFEST_SHA ==
          "1e9e0f949b112f57dc73aa245f4cec5f3e63d3e7c1670b03364c46102bf2bb36")

    # --- 4. limits version binding ----------------------------------------------------
    # These mutate the SEALED FILE, not the manifest's copy - see the module docstring.
    refuses_sealed(tmp, "refuses limits with a v2 shape (fill_policy present)",
                   {**LIMITS_V3, "fill_policy": {"legacy": True}}, "OTR-V2", "v2 limits")
    refuses_sealed(tmp, "refuses limits lacking attempt_policy (v1 shape)",
                   {k: v for k, v in LIMITS_V3.items() if k != "attempt_policy"},
                   "OTR-V1", "attempt_policy")
    refuses_sealed(tmp, "refuses limits lacking market_data_regime (v4 shape)",
                   {k: v for k, v in LIMITS_V3.items() if k != "market_data_regime"},
                   "OTR-V4SHAPE", "market_data_regime")

    refuses("refuses when embedded limits sha != sealed file on disk",
            lambda: X.TransitionExecutorV3(*make_manifest(
                tmp, run_id="OTR-SHAMISMATCH", limits_sha="a" * 64)[:2], dry_run=True),
            "sealed limits file")

    # HARDENING: the sha can match while the embedded CONTENT does not. The sha is over the
    # FILE BYTES and the content is parsed JSON; nothing tied them together before v10.
    tampered = json.loads(json.dumps(LIMITS_V3))
    tampered["continuation_policy"]["residual_budget"]["R_ABS_usd"] = 10000.0
    refuses("*** refuses embedded limits CONTENT that differs from the sealed file ***",
            lambda: X.TransitionExecutorV3(*make_manifest(
                tmp, run_id="OTR-CONTENT", limits_content=tampered,
                limits_sha=LIMITS_V3_SHA)[:2], dry_run=True),
            "embedded limits CONTENT differs")

    pok, sok = make_manifest(tmp, run_id="OTR-DISKAUTH")
    exd = X.TransitionExecutorV3(str(pok), sok, dry_run=True)
    check("the executor applies the SEALED file, not the manifest's copy",
          exd.limits_identity["embedded_content_identical_to_sealed_file"] is True
          and exd.limits_identity["sha256"] == LIMITS_V3_SHA
          and X.canonical(exd.limits) == X.canonical(LIMITS_V3))

    # --- 5. artifact_status is an ALLOWLIST -------------------------------------------
    # NOT_APPROVED_FOR_EXECUTION is the label the owner actually applied on 2026-07-28;
    # it contains none of the substrings v1/v2 deny on, which is why v3 allowlists.
    non_executable = ("DRY_RUN_ONLY", "NOT_APPROVED_FOR_EXECUTION",
                      "NOT_AUTHORIZED_FOR_EXECUTION", "SUPERSEDED_BY_X",
                      "REHEARSAL", "", "PLAN_PENDING_REVIEW_DRAFT", "approved")
    for i, label in enumerate(non_executable):
        refuses(f"refuses artifact_status={label!r} when not --dry-run",
                lambda lb=label, n=i: X.TransitionExecutorV3(*make_manifest(
                    tmp, run_id=f"OTR-STATUS{n}", status=lb)[:2], dry_run=False),
                "not an executable status")
    for label in sorted(X.EXECUTABLE_STATUSES):
        p5, s5 = make_manifest(tmp, run_id=f"OTR-OK{label[:4]}", status=label)
        try:
            X.TransitionExecutorV3(str(p5), s5, dry_run=False)
            check(f"accepts executable status {label}", True)
        except SystemExit as e:
            check(f"accepts executable status {label}", False, str(e))
    pl, shl = make_manifest(tmp, run_id="OTR-DRYOK", status="DRY_RUN_ONLY")
    ok = X.TransitionExecutorV3(str(pl), shl, dry_run=True)
    check("a DRY_RUN manifest still loads under --dry-run", ok.dry is True)

    # --- 6. caps enforced at LOAD -----------------------------------------------------
    big = [{"seq": 1, "symbol": "SPY", "side": "buy", "qty": "1", "type": "market",
            "tif": "day", "sizing_price": 600.0, "intent": "entry",
            "est_notional": 25000.01, "stage": "B_cross_asset"}]
    refuses("refuses an order above max_individual_order_notional_usd",
            lambda: X.TransitionExecutorV3(*make_manifest(
                tmp, run_id="OTR-BIGORDER", orders=big)[:2], dry_run=True),
            "exceeds max")

    refuses("refuses a stage above its turnover cap",
            lambda: X.TransitionExecutorV3(*make_manifest(
                tmp, run_id="OTR-TURNOVER", equity=1000.0,
                stage_totals={"A_exits": 0.0, "B_cross_asset": 900.0,
                              "C_equity": 0.0})[:2], dry_run=True),
            "turnover")

    # --- 7. approval record (owner section 6) ------------------------------------------
    p7, sha7 = make_manifest(tmp, run_id="OTR-APPROVAL")
    ex7 = X.TransitionExecutorV3(str(p7), sha7, dry_run=False)
    refuses("refuses live run with NO approval record",
            ex7.require_approval_record, "no approval record")

    ap = Path(tmp) / "APPROVAL_OTR-APPROVAL.json"
    json.dump({"approved_manifest_sha256": "b" * 64, "decision": "APPROVED"},
              open(ap, "w"))
    refuses("refuses an approval record naming a different hash",
            ex7.require_approval_record, "approval record names")

    json.dump({"approved_manifest_sha256": sha7, "decision": "REJECTED"},
              open(ap, "w"))
    refuses("refuses an approval record whose decision is not APPROVED",
            ex7.require_approval_record, "decision")

    json.dump({"approved_manifest_sha256": sha7, "decision": "APPROVED",
               "approved_by": "owner", "approved_at": "2026-08-08T00:00:00Z"},
              open(ap, "w"))
    try:
        rec = ex7.require_approval_record()
        check("accepts a matching APPROVED record", rec["decision"] == "APPROVED")
    except SystemExit as e:
        check("accepts a matching APPROVED record", False, str(e))

    # --- 8. identity latch: the owner's five-point spec --------------------------------
    # Tested against the REAL credential from the encrypted store, because the pinned
    # fingerprint can only be satisfied by the real key - a stub would prove nothing.
    import v13_identity_latch as L
    from app.brokers.alpaca.credentials import credentials_for_mode
    from app.db.session import get_sessionmaker

    real = asyncio.run(credentials_for_mode("paper", 7, get_sessionmaker()))
    real_fp = L.fingerprint(real.api_key)
    check("the stored account-7 credential fingerprints to the pinned value",
          real_fp == L.EXPECTED_KEY_FINGERPRINT, f"{real_fp} vs {L.EXPECTED_KEY_FINGERPRINT}")

    def verify(**over):
        args = dict(workbench_account_id=7, strategy_id=9, api_key=real.api_key,
                    broker_account_number="PA3BGKRLH2AP", context="test")
        args.update(over)
        return L.verify(**args)

    ev = verify()
    check("latch PASSES when all five expectations hold", ev["passed"] is True)
    check("latch records a fingerprint and never the key",
          ev["observed"]["key_fingerprint"] == L.EXPECTED_KEY_FINGERPRINT
          and real.api_key not in json.dumps(ev))
    check("all five checks are individually recorded",
          {"workbench_account_id", "strategy_id", "key_fingerprint",
           "broker_returned_account_number",
           "broker_is_source_of_identity"} <= set(ev["checks"]))

    refuses("latch REFUSES the WSS canary PA3E97RWHKQZ",
            lambda: verify(broker_account_number="PA3E97RWHKQZ"), "identity latch failed")
    refuses("latch REFUSES the stale documented PA3344TNRFYD",
            lambda: verify(broker_account_number="PA3344TNRFYD"), "identity latch failed")
    refuses("latch REFUSES the LIVE low-volatility book PA30T0I3JJV9",
            lambda: verify(broker_account_number="PA30T0I3JJV9"), "identity latch failed")
    refuses("latch REFUSES a wrong workbench account id",
            lambda: verify(workbench_account_id=6), "identity latch failed")
    refuses("latch REFUSES a wrong strategy id",
            lambda: verify(strategy_id=8), "identity latch failed")
    refuses("latch REFUSES a credential whose fingerprint is not the pinned one",
            lambda: verify(api_key="SOME-OTHER-KEY"), "identity latch failed")
    refuses("latch REFUSES a broker-blocked account",
            lambda: verify(trading_blocked=True), "identity latch failed")

    # the WSS key must not unlock strategy 9 even if the broker somehow answered right
    refuses("the WSS credential cannot satisfy the strategy-9 latch",
            lambda: verify(api_key="WSS-KEY-PLACEHOLDER",
                           broker_account_number="PA3E97RWHKQZ"),
            "identity latch failed")

    try:
        e = verify(broker_account_number="PA3E97RWHKQZ")
    except SystemExit as exc:
        check("a mismatch names WHICH wrong account was reached",
              "WSS" in str(exc) or "canary" in str(exc), str(exc)[:120])

    # --- 8b. live end-to-end latch against the real broker ----------------------------
    p8, sha8 = make_manifest(tmp, run_id="OTR-LIVELATCH")
    ex8 = X.TransitionExecutorV3(str(p8), sha8, dry_run=True)
    try:
        live = asyncio.run(ex8.latch_identity())
        check("LIVE latch passes end-to-end against the real broker",
              live["passed"] is True
              and live["observed"]["broker_account_number"] == "PA3BGKRLH2AP")
        check("live latch read the account number FROM THE BROKER",
              live["checks"]["broker_is_source_of_identity"]["passed"] is True)
    except SystemExit as exc:
        check("LIVE latch passes end-to-end against the real broker", False, str(exc))

    # --- 9. structural: the core is the one that executes ------------------------------
    src = Path("/app/data/ops/acct7/RETIRED__v13_transition_executor_v3.py").read_text()
    check("v3 delegates submission to the proven core",
          "core.execute_logical_order(" in src)
    check("v3 contains no independent order-submission path",
          '"/orders", "POST"' not in src and "'/orders', 'POST'" not in src)
    check("v3 pins the broker account rather than resolving a credential name",
          "ALPACA_PAPER" not in src.replace("ALPACA_PAPER_6_API_KEY", "", 1)
          or "PINNED_BROKER_ACCOUNT = " in src)

    # --- 10. PROTOCOL v2: the continuation policy is bound, not advertised ------------
    check("binds the sealed limits v8 file",
          str(X.LIMITS_FILE).endswith("v13_frozen_execution_limits_v8.json"),
          str(X.LIMITS_FILE))
    check("the sealed limits carry a v2.1 continuation policy",
          LIMITS_V3["continuation_policy"]["version"] == "v2.1")
    check("the counting unit is FAILED LOGICAL ORDERS, not attempt records",
          LIMITS_V3["continuation_policy"]["counting_unit"] == "failed_logical_orders")
    check("R_PCT_equity is 0.0 (owner ruling 2026-08-21)",
          float(LIMITS_V3["continuation_policy"]["residual_budget"]["R_PCT_equity"]) == 0.0)
    check("R_ABS_usd is the pre-existing $250 frozen tolerance",
          float(LIMITS_V3["continuation_policy"]["residual_budget"]["R_ABS_usd"]) == 250.0
          == float(LIMITS_V3["residual_policy"]["tolerance_usd_per_stage"]))
    check("the concentration trigger is 50%",
          float(LIMITS_V3["continuation_policy"]["concentration_trigger"]["threshold"]) == 0.50)
    check("the executor no longer reads the superseded attempt-count clauses",
          "pre_submission_gate_aborts" not in
          Path("/app/data/ops/acct7/v13_transition_executor_v10.py").read_text()
          .split("def check_stop_conditions")[1].split("def run_stage")[0])

    refuses("refuses a Protocol v1 manifest (no continuation_policy_resolved)",
            lambda: X.TransitionExecutorV3(*make_manifest(
                tmp, run_id="OTR-NOCP", drop_cp_resolved=True)[:2], dry_run=True),
            "lacks continuation_policy_resolved")

    _good = CP.resolve(LIMITS_V3, [
        {"seq": 1, "symbol": "AAPL", "side": "sell", "qty": "0.5", "type": "market",
         "tif": "day", "sizing_price": 200.0, "intent": "exit", "est_notional": 100.0,
         "stage": "A_exits"},
        {"seq": 2, "symbol": "UUP", "side": "buy", "qty": "10", "type": "market",
         "tif": "day", "sizing_price": 27.0, "intent": "entry", "est_notional": 270.0,
         "stage": "B_cross_asset"}], 100000.0)
    _tampered = json.loads(json.dumps(_good))
    _tampered["stages"]["B_cross_asset"]["completeness_required"] = False
    refuses("refuses a manifest that DISCLOSES a weaker rule than the sealed one",
            lambda: X.TransitionExecutorV3(*make_manifest(
                tmp, run_id="OTR-CPTAMPER", cp_resolved=_tampered)[:2], dry_run=True),
            "does not match the policy re-derived")

    _budget = json.loads(json.dumps(_good))
    _budget["stages"]["A_exits"]["effective_budget_usd"] = 10000.0
    refuses("refuses a manifest that inflates a stage residual budget",
            lambda: X.TransitionExecutorV3(*make_manifest(
                tmp, run_id="OTR-CPBUDGET", cp_resolved=_budget)[:2], dry_run=True),
            "does not match the policy re-derived")

    def mutate(fn):
        d = json.loads(json.dumps(LIMITS_V3))
        fn(d["continuation_policy"])
        return d

    refuses_sealed(tmp, "refuses limits lacking continuation_policy (v5 shape)",
                   {k: v for k, v in LIMITS_V3.items() if k != "continuation_policy"},
                   "OTR-V5SHAPE", "continuation_policy")
    refuses_sealed(tmp, "refuses limits that count ATTEMPT RECORDS (the D1 defect)",
                   mutate(lambda c: c.update(counting_unit="attempt_records")),
                   "OTR-UNIT", "counting_unit")
    refuses_sealed(tmp, "refuses limits that reintroduce R_PCT without a ruling",
                   mutate(lambda c: c["residual_budget"].update(R_PCT_equity=0.0025)),
                   "OTR-RPCT", "R_PCT_equity")
    refuses_sealed(tmp, "refuses limits that move the concentration trigger",
                   mutate(lambda c: c["concentration_trigger"].update(threshold=0.90)),
                   "OTR-CONC", "concentration_trigger")
    refuses_sealed(tmp, "refuses limits whose budget disagrees with residual_policy",
                   mutate(lambda c: c["residual_budget"].update(R_ABS_usd=500.0)),
                   "OTR-TWOBUDGETS", "ONE value")
    refuses_sealed(tmp, "refuses limits that widen joint_construction to A_exits",
                   mutate(lambda c: c["per_stage"]["stage_A_exits"].update(
                       joint_construction=True)),
                   "OTR-WIDEN", "joint_construction stages are")
    refuses_sealed(tmp, "refuses limits lacking precedence_rule (v6 shape)",
                   mutate(lambda c: c.pop("precedence_rule")),
                   "OTR-NOPREC", "precedence_rule")

    # --- HARDENING: taxonomy governance ------------------------------------------------
    check("the limits DECLARE the same taxonomy the executor applies",
          set(LIMITS_V3["continuation_policy"]["failure_taxonomy"]["EXECUTABILITY"]["codes"])
          == set(X.EXECUTABILITY_ABORTS)
          and set(LIMITS_V3["continuation_policy"]["failure_taxonomy"]["HARD"]["codes"])
          == set(X.HARD_ABORTS))
    refuses_sealed(tmp, "*** refuses limits that WIDEN the EXECUTABILITY class ***",
                   mutate(lambda c: c["failure_taxonomy"]["EXECUTABILITY"]["codes"].append(
                       "some_new_budget_eligible_failure")),
                   "OTR-WIDENTAX", "EXECUTABILITY codes")
    refuses_sealed(tmp, "refuses limits that narrow the HARD class",
                   mutate(lambda c: c["failure_taxonomy"]["HARD"]["codes"].remove(
                       "risk_refusal")),
                   "OTR-NARROWTAX", "HARD codes")
    refuses_sealed(tmp, "refuses limits lacking the taxonomy governance block",
                   mutate(lambda c: c["failure_taxonomy"].pop("governance")),
                   "OTR-NOTAXGOV", "governance block")
    refuses_sealed(tmp, "refuses limits lacking activation_invariants (v7 shape)",
                   mutate(lambda c: c.pop("activation_invariants")),
                   "OTR-NOACT", "activation_invariants")
    refuses_sealed(tmp, "refuses limits lacking the residual-debt lifecycle",
                   mutate(lambda c: c["residual_debt_rule"].pop("lifecycle")),
                   "OTR-NOLIFE", "lifecycle block")
    refuses_sealed(tmp, "refuses declared debt statuses the ledger does not enforce",
                   mutate(lambda c: c["residual_debt_rule"]["lifecycle"].update(
                       terminal_statuses=["CLOSED"])),
                   "OTR-BADSTATUS", "terminal statuses differ")

    # a well-formed v2 manifest still loads, and resolves the rule the owner ruled
    pcp, scp = make_manifest(tmp, run_id="OTR-CPOK")
    excp = X.TransitionExecutorV3(str(pcp), scp, dry_run=True)
    check("UUP at 100% of a one-order Stage B is completeness-required",
          excp.cp_stages["B_cross_asset"]["completeness_required"] is True)
    check("*** v2.1: a ONE-order Stage A is NOT completeness-required ***",
          excp.cp_stages["A_exits"]["completeness_required"] is False
          and excp.cp_stages["A_exits"]["max_failed_orders_before_halt"] == 2,
          "under v2.0 a single exit was 100% of its own stage and therefore zero-tolerance "
          "- the collapsed-stage pathology re-entering through the new mechanism")
    check("...and its share is still measured and disclosed, for observability only",
          excp.cp_stages["A_exits"]["largest_order_share_of_stage"] == 1.0
          and excp.cp_stages["A_exits"]["concentration_completeness_applies"] is False
          and "observability" in excp.cp_stages["A_exits"]["completeness_not_applicable_reason"])
    _multiA = CP.resolve_stage(LIMITS_V3, "A_exits", [
        {"seq": i, "symbol": "S%d" % i, "est_notional": 150.0, "stage": "A_exits"}
        for i in range(1, 6)], 100000.0)
    check("a FIVE-order Stage A (the 2026-08-21 shape) tolerates 2 failed orders",
          _multiA["completeness_required"] is False
          and _multiA["max_failed_orders_before_halt"] == 2)
    check("exactly ONE stage is joint-construction, and it is the sleeve",
          sorted(k for k, s in LIMITS_V3["continuation_policy"]["per_stage"].items()
                 if s.get("joint_construction")) == ["stage_B_cross_asset"])
    check("the precedence rule is declared, not emergent",
          "precedence_rule" in LIMITS_V3["continuation_policy"]
          and "no rule is subordinate" in
          LIMITS_V3["continuation_policy"]["precedence_rule"]["ruling"])

    check("Stage C carries the count rule as well as the budget",
          excp.cp_stages["C_equity"]["mode"] == "residual_budget_and_count"
          and excp.cp_stages["C_equity"]["backstop_failed_orders"] == 3)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n=== {PASS} passed, {FAIL} failed ===")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
