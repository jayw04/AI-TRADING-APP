"""MR-002 Validation-2 — opening protocol, terminal-state machinery and dry-run qualification.

Sealed authority: MR002_Validation2_ProspectiveRegistration_v1.0.

⛔ THIS MODULE NEVER OPENS VALIDATION-2. It contains the machinery that a future authorized opening
would use, and a DRY RUN that exercises that machinery end-to-end against the DEVELOPMENT surrogate.
The reader is not wired to the sealed store here, and no Validation-2 object key is ever fetched.

THE GOVERNING PRINCIPLE (owner grant 2026-08-20)
    The next validation opening must be capable of producing a legitimate economic verdict even if a
    numerical component encounters an expected registered numerical termination. It must never again
    be consumed merely because infrastructure or numerical classification failed.

That principle is implemented by ONE structural decision: conformance and judgment are two
different outputs, computed separately, and neither is allowed to impersonate the other.

    OUTPUT 1  numerical / execution CONFORMANCE   -> CONFORMANT | NON_CONFORMANT
    OUTPUT 2  economic VALIDATION VERDICT         -> ADVANCE_REQUEST | DO_NOT_ADVANCE
                                                     | INCONCLUSIVE | NOT_EVALUATED

A registered numerical termination -- an iteration limit the v2 method classifies as
NO_CERTIFIED_CANDIDATE with a registered reason -- is an EXPECTED outcome. It does not by itself
make the run non-conformant. That is the exact fragility N2 qualified away, and the reason the
consumed opening died with no economic verdict.

WHAT IS DELIBERATELY NOT IMPLEMENTED HERE
    The live reader/publisher IAM separation is provisioned in AWS (mr002-validation-reader, the
    evaluator-publisher policy, the sealed-store bucket policy), not in this file. This module
    asserts the separation as a PRECONDITION it verifies, and the dry run records honestly that a
    live role-assumption test was not performed. Claiming otherwise would be the kind of
    overstatement the registration exists to prevent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/work/apps/backend")

REGISTRATION_IDENTITY = "PENDING_SEAL"          # re-pinned once the registration is sealed
N3_VERDICT = "5a14028024a1f78ca60ebeb174b5ecd7b8a3e1f5027f8768ec93b6f2a8195ec4"

# ── terminal states ────────────────────────────────────────────────────────────────────────────
CONFORMANT = "CONFORMANT"
NON_CONFORMANT = "NON_CONFORMANT"

ADVANCE = "VALIDATION_ADVANCE_REQUEST"
DO_NOT_ADVANCE = "VALIDATION_DO_NOT_ADVANCE"
INCONCLUSIVE = "VALIDATION_INCONCLUSIVE"
NOT_EVALUATED = "NOT_EVALUATED"

INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
INVALID_TEST_HARNESS = "INVALID_TEST_HARNESS"
PRE_READ_ABORT = "PRE_READ_ABORT_NOT_CONSUMED"

TERMINAL_PATHS = (ADVANCE, DO_NOT_ADVANCE, INCONCLUSIVE, INTEGRITY_FAILURE,
                  INVALID_TEST_HARNESS, PRE_READ_ABORT)


class PreReadAbort(RuntimeError):
    """A precondition failed BEFORE any withheld economic byte was exposed.

    This is the ONLY failure that leaves the opening unconsumed, which is exactly why it is a
    distinct exception type rather than a flag someone can set late.
    """


class HarnessInvalid(RuntimeError):
    """The Stage-3 seam was not exercised as registered. Never an economic result."""


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE DURABLE OPENED-OBJECT LEDGER
#
# The consumed opening's launcher serialised its report only after a successful replay, so the
# ledger was never written and was lost when replay raised. For a one-time opening, evidence MUST
# survive the very failures it documents. This ledger therefore appends and FLUSHES per object, and
# its FIRST ENTRY IS THE CONSUMPTION BOUNDARY: no entry means nothing was exposed.
# ══════════════════════════════════════════════════════════════════════════════════════════════

class OpenedObjectLedger:
    def __init__(self, path: str):
        self.path = path
        self._prev = "0" * 64
        self.rows: list = []
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def record_exposure(self, *, key: str, version_id: str, sha256: str, bytes_: int,
                        when: str) -> dict:
        """Called IMMEDIATELY BEFORE the object's bytes reach the evaluator. Ordering matters: a
        ledger written after a successful read cannot record the read that crashed."""
        row = {"seq": len(self.rows) + 1, "key": key, "version_id": version_id,
               "sha256": sha256, "bytes": bytes_, "exposed_at_utc": when,
               "hash_chain_prev": self._prev}
        row["hash_chain_row"] = hashlib.sha256(
            json.dumps(row, sort_keys=True).encode("ascii")).hexdigest()
        self._prev = row["hash_chain_row"]
        self.rows.append(row)
        with open(self.path, "a", encoding="ascii") as fh:      # append, never rewrite
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())                                # survive a hard failure
        return row

    @property
    def consumed(self) -> bool:
        return len(self.rows) > 0

    def summary(self) -> dict:
        return {"objects_exposed": len(self.rows),
                "consumed": self.consumed,
                "chain_head": self._prev if self.rows else None,
                "durability": "appended and fsynced per object, before exposure"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE N3-DERIVED HARNESS INVARIANT  (registration §n3_derived_harness_invariant)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def routing_guard(*, census_rows: int, invocations: int, dispositions: dict,
                  expected_vocabulary=("PRIMARY_CERTIFIED", "SECONDARY_CERTIFIED",
                                       "UNRESOLVED_INSTANCE", "INVALID_RUN")) -> dict:
    """RAISES HarnessInvalid unless the Stage-3 seam was demonstrably exercised by the v2 pair.

    A validation run with ZERO or UNEXPECTED Stage-3 invocation count MUST terminate as
    INVALID_TEST_HARNESS before any economic verdict is produced. This is bound explicitly rather
    than inherited: nothing makes a future runner inherit N3's guard, and assuming inheritance is
    how the guard silently fails to exist where it matters most.

    The expected count is a LOWER BOUND and a structural relationship, never a literal: the Stage-3
    invocation count is a property of the data and cannot be known before the window is replayed.
    Substituting the development counts would be a fabricated threshold.
    """
    problems = []
    if invocations <= 0:
        problems.append("ZERO Stage-3 invocations - the seam was never exercised")
    if census_rows <= 0:
        problems.append("ZERO Stage-3 census rows - the routing context was never entered")
    if census_rows != invocations:
        problems.append(f"census {census_rows} != invocations {invocations}")
    if dispositions and not set(dispositions) & set(expected_vocabulary):
        problems.append(
            f"disposition vocabulary {sorted(dispositions)} contains no v2 label - the frozen "
            f"v2 pair was NOT routed")
    if problems:
        raise HarnessInvalid("; ".join(problems))
    return {"invocations": invocations, "census_rows": census_rows,
            "dispositions": dispositions, "v2_pair_routed": True,
            "basis": "lower bound + structural relationship, not a literal expected count"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CONFORMANCE  (OUTPUT 1) -- kept strictly apart from judgment (OUTPUT 2)
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Registered numerical terminations. These are EXPECTED and are NOT integrity defects. This is the
# exact class that consumed the first opening when it was mapped to UNREGISTERED_EXCEPTION.
REGISTERED_TERMINATIONS = ("ITERATION_LIMIT_REACHED", "NO_CERTIFIED_CANDIDATE",
                           "PRIMAL_INFEASIBLE", "DUAL_INFEASIBLE", "NUMERICAL_TOLERANCE_NOT_MET")


def conformance(*, instances_required: int, instances_resolved: int, integrity_defects: int,
                unregistered_terminations: int, registered_terminations: int,
                source_identity_ok: bool, runtime_identity_ok: bool,
                evidence_complete: bool) -> dict:
    """Numerical / execution conformance. Says NOTHING about economics."""
    checks = {
        "all_required_instances_resolved": instances_resolved == instances_required,
        "no_integrity_defect": integrity_defects == 0,
        "no_unregistered_termination_reason": unregistered_terminations == 0,
        "source_identity_correct": bool(source_identity_ok),
        "runtime_identity_correct": bool(runtime_identity_ok),
        "evidence_complete": bool(evidence_complete),
    }
    return {
        "state": CONFORMANT if all(checks.values()) else NON_CONFORMANT,
        "checks": checks,
        "instances_required": instances_required,
        "instances_resolved": instances_resolved,
        "registered_numerical_terminations": registered_terminations,
        "registered_terminations_are_expected": (
            "a registered numerical termination is an EXPECTED outcome and does NOT by itself make "
            "the run non-conformant. Treating one as an integrity defect is what consumed the "
            "first opening and produced no economic verdict."),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ECONOMIC JUDGMENT  (OUTPUT 2) -- the frozen gates, copied, not reinterpreted
# ══════════════════════════════════════════════════════════════════════════════════════════════

def economic_verdict(*, b_positive_folds: int, a_cumulative_return: float,
                     c_cumulative_return: float, folds: int = 5,
                     indeterminate: bool = False) -> dict:
    """The transferred advance conditions. No new threshold, no discretionary branch."""
    gates = {
        "config_B_positive_folds_ge_3_of_5": b_positive_folds >= 3,
        "config_A_cumulative_net_return_gt_0": a_cumulative_return > 0,
        "config_C_cumulative_net_return_gt_0": c_cumulative_return > 0,
    }
    if indeterminate:
        verdict = INCONCLUSIVE
    elif all(gates.values()):
        verdict = ADVANCE
    else:
        verdict = DO_NOT_ADVANCE
    return {
        "verdict": verdict,
        "gates": gates,
        "observed": {"B_positive_folds": b_positive_folds, "folds": folds,
                     "A_cumulative_return": a_cumulative_return,
                     "C_cumulative_return": c_cumulative_return},
        "advance_meaning": "VALIDATION_ADVANCE_REQUEST authorizes a REQUEST for separate OOS "
                           "authorization. It does not open the new OOS and evaluates no OOS gate.",
    }


def combine(conf: dict, econ: dict | None, *, ledger: OpenedObjectLedger,
            harness_invalid: str | None = None,
            pre_read_abort: str | None = None) -> dict:
    """The ONLY place the two outputs meet. Every forbidden translation is blocked structurally."""
    if pre_read_abort is not None:
        return {
            "terminal_state": PRE_READ_ABORT,
            "conformance": conf,
            "economic_verdict": NOT_EVALUATED,
            "opening_consumed": False,
            "reason": pre_read_abort,
            "another_execution_permissible": True,
            "why": "the precondition failed BEFORE any withheld economic byte was exposed. The "
                   "ledger is empty, so nothing was seen.",
            "ledger": ledger.summary(),
        }
    if harness_invalid is not None:
        return {
            "terminal_state": INVALID_TEST_HARNESS,
            "conformance": conf,
            "economic_verdict": NOT_EVALUATED,
            "opening_consumed": ledger.consumed,
            "reason": harness_invalid,
            "another_execution_permissible": not ledger.consumed,
            "why": "the Stage-3 seam was not exercised as registered, so no economic result "
                   "produced by this run means anything.",
            "ledger": ledger.summary(),
        }
    if conf["state"] == NON_CONFORMANT:
        return {
            "terminal_state": INTEGRITY_FAILURE,
            "conformance": conf,
            "economic_verdict": NOT_EVALUATED,
            "gates_evaluated": False,
            "opening_consumed": ledger.consumed,
            "another_execution_permissible": not ledger.consumed,
            "why": "an integrity stop is NEVER reported as VALIDATION_DO_NOT_ADVANCE, which would "
                   "falsely imply the economic gates ran and failed.",
            "ledger": ledger.summary(),
        }
    return {
        "terminal_state": econ["verdict"],
        "conformance": conf,
        "economic_verdict": econ["verdict"],
        "gates_evaluated": True,
        "gates": econ["gates"],
        "observed": econ["observed"],
        "opening_consumed": ledger.consumed,
        "another_execution_permissible": False,
        "ledger": ledger.summary(),
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NEGATIVE CONTROLS -- one fixture per terminal path.
# A path that has never been observed to fire is not known to work. These drive the machinery to
# every terminal state and assert it lands where it must, including the states nobody wants.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _clean_conf(**over) -> dict:
    base = dict(instances_required=100, instances_resolved=100, integrity_defects=0,
                unregistered_terminations=0, registered_terminations=0,
                source_identity_ok=True, runtime_identity_ok=True, evidence_complete=True)
    base.update(over)
    return conformance(**base)


def negative_controls(tmpdir: str) -> dict:
    results = {}

    def ledger(name, exposed=0):
        lg = OpenedObjectLedger(os.path.join(tmpdir, f"ledger_{name}.jsonl"))
        for i in range(exposed):
            lg.record_exposure(key=f"oos/obj{i}.parquet", version_id=f"v{i}",
                               sha256="0" * 64, bytes_=1, when="1970-01-01T00:00:00Z")
        return lg

    # 1 ── ADVANCE
    r = combine(_clean_conf(), economic_verdict(b_positive_folds=4, a_cumulative_return=0.01,
                                                c_cumulative_return=0.02),
                ledger=ledger("advance", exposed=6))
    results[ADVANCE] = {"fired": r["terminal_state"] == ADVANCE, "consumed": r["opening_consumed"],
                        "gates_evaluated": r.get("gates_evaluated")}

    # 2 ── DO_NOT_ADVANCE: gates ran and failed. Must NOT be an integrity state.
    r = combine(_clean_conf(), economic_verdict(b_positive_folds=2, a_cumulative_return=-0.01,
                                                c_cumulative_return=0.02),
                ledger=ledger("reject", exposed=6))
    results[DO_NOT_ADVANCE] = {"fired": r["terminal_state"] == DO_NOT_ADVANCE,
                               "gates_evaluated": r.get("gates_evaluated"),
                               "consumed": r["opening_consumed"]}

    # 3 ── INCONCLUSIVE: only where the frozen metric spec is indeterminate on an admissible run
    r = combine(_clean_conf(), economic_verdict(b_positive_folds=3, a_cumulative_return=0.01,
                                                c_cumulative_return=0.01, indeterminate=True),
                ledger=ledger("inconc", exposed=6))
    results[INCONCLUSIVE] = {"fired": r["terminal_state"] == INCONCLUSIVE,
                             "consumed": r["opening_consumed"]}

    # 4 ── INTEGRITY_FAILURE: an unregistered termination. Gates must NOT be evaluated, and the
    #      state must NOT be DO_NOT_ADVANCE -- the exact mislabel the consumed opening avoided.
    r = combine(_clean_conf(unregistered_terminations=1),
                economic_verdict(b_positive_folds=5, a_cumulative_return=0.9,
                                 c_cumulative_return=0.9),
                ledger=ledger("integ", exposed=6))
    results[INTEGRITY_FAILURE] = {
        "fired": r["terminal_state"] == INTEGRITY_FAILURE,
        "economic_verdict_suppressed": r["economic_verdict"] == NOT_EVALUATED,
        "gates_evaluated": r.get("gates_evaluated"),
        "not_mislabelled_as_reject": r["terminal_state"] != DO_NOT_ADVANCE,
        "note": "the economics here are deliberately EXCELLENT (5/5 folds, +90%). A conformance "
                "failure must suppress them anyway, or an infrastructure state could smuggle in a "
                "verdict.",
    }

    # 5 ── INVALID_TEST_HARNESS: zero Stage-3 invocations. The N3 defect, reproduced on purpose.
    try:
        routing_guard(census_rows=0, invocations=0, dispositions={})
        guard_raised = False
        detail = "GUARD DID NOT FIRE"
    except HarnessInvalid as exc:
        guard_raised, detail = True, str(exc)
    r = combine(_clean_conf(), None, ledger=ledger("harness", exposed=6),
                harness_invalid=detail)
    results[INVALID_TEST_HARNESS] = {
        "guard_raised": guard_raised, "fired": r["terminal_state"] == INVALID_TEST_HARNESS,
        "economic_verdict_suppressed": r["economic_verdict"] == NOT_EVALUATED, "detail": detail}

    # 5b ── the subtler harness failure: routed, but by the WRONG method (v1 vocabulary)
    try:
        routing_guard(census_rows=933, invocations=933,
                      dispositions={"PRIMARY_QUALIFIED": 933})   # v1 labels, not v2
        wrong_pair_caught = False
    except HarnessInvalid:
        wrong_pair_caught = True
    results["INVALID_TEST_HARNESS_wrong_pair"] = {
        "caught": wrong_pair_caught,
        "why": "a full census with v1 labels means the v2 pair was not routed. Counting rows alone "
               "would pass this."}

    # 6 ── PRE_READ_ABORT: precondition failed before exposure. Ledger EMPTY, NOT consumed.
    lg = ledger("preread", exposed=0)
    r = combine(_clean_conf(source_identity_ok=False), None, ledger=lg,
                pre_read_abort="source identity verification failed")
    results[PRE_READ_ABORT] = {
        "fired": r["terminal_state"] == PRE_READ_ABORT,
        "opening_consumed": r["opening_consumed"],
        "must_be_not_consumed": r["opening_consumed"] is False,
        "ledger_empty": lg.summary()["objects_exposed"] == 0,
        "another_execution_permissible": r["another_execution_permissible"]}

    # 7 ── the consumption boundary itself: one exposure consumes the opening
    lg = ledger("boundary", exposed=1)
    results["CONSUMPTION_BOUNDARY"] = {
        "one_exposure_consumes": lg.consumed,
        "ledger_durable_on_disk": os.path.exists(lg.path) and os.path.getsize(lg.path) > 0,
        "why": "consumed at FIRST successful exposure, not at completion. This removes the "
               "'partial peek, repair, rerun' ambiguity."}

    # 8 ── a registered numerical termination must NOT break conformance (the N2 repair)
    c = _clean_conf(registered_terminations=62)
    results["REGISTERED_TERMINATION_IS_NOT_A_DEFECT"] = {
        "state": c["state"], "conformant": c["state"] == CONFORMANT,
        "why": "62 registered terminations is exactly the N2 stress observation. If this made a "
               "run non-conformant, the governing principle of this cycle would be violated."}
    return results


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LIVE SURROGATE RUN -- the machinery driven by a REAL Stage-3 replay on the DEVELOPMENT corpus.
# The negative controls above prove the state machine. This proves the guard against real routing,
# on data that carries no withheld economic content.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def surrogate_run(sessions: int = 300) -> dict:
    from datetime import date

    import app.research.mr002.joint_portfolio as jp
    import scripts.mr002_development_run as mdr
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.n1 import seam as v2seam
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))[:sessions]

    census: list = []
    invocations = {"n": 0}
    t0 = time.time()
    with v2seam.routed_v2(census, candidate="PIQP_P2", solvers=SOLVERS,
                          certify_fn=canonical_qualify):
        inner = jp._solve_qp                    # captured INSIDE the ctx -- the N3 lesson
        def observe(H, t, A_ub, b_ub, A_eq, b_eq, upper):
            invocations["n"] += 1
            return inner(H, t, A_ub, b_ub, A_eq, b_eq, upper)
        jp._solve_qp = observe
        try:
            mdr.run_config(days, CONFIGS["C"])
        finally:
            jp._solve_qp = inner

    summary = v2seam.census_summary(census)
    disp = summary.get("by_disposition", {})
    guard = routing_guard(census_rows=len(census), invocations=invocations["n"], dispositions=disp)
    return {
        "surrogate": f"development corpus 2013-01-02.. (first {sessions} sessions), config C",
        "carries_withheld_economic_content": False,
        "seconds": round(time.time() - t0, 1),
        "stage3": summary,
        "routing_guard": guard,
        "guard_passed_on_real_routing": True,
    }


def preconditions(*, sealed_store_reachable_by_this_process: bool) -> dict:
    """Capability separation, verified as a PRECONDITION rather than asserted.

    Honest scope: this checks the properties observable from where the harness runs. The live
    role-assumption test (assume mr002-validation-reader, prove the publisher cannot) is AWS work
    that has not been performed, and the dry-run record says so rather than implying coverage.
    """
    return {
        "publisher_cannot_read_the_sealed_store": {
            "observed": not sealed_store_reachable_by_this_process,
            "method": "the dry run never constructs a sealed-store client and never references a "
                      "Validation-2 object key",
            "⚠ scope": "this is a property of THIS process, not a proof about the deployed "
                       "publisher role",
        },
        "reader_cannot_write_governing_evidence": {
            "verified_live": False,
            "⚠": "NOT TESTED HERE. Enforced by the deployed IAM policies "
                 "(scripts/mr002_custody/aws/*.json); a live assume-role test is outstanding.",
        },
        "live_role_assumption_test_performed": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="MR-002 Validation-2 dry-run qualification")
    ap.add_argument("--out", default="/work/.mr002out/v2/dryrun.json")
    ap.add_argument("--sessions", type=int, default=300)
    ap.add_argument("--skip-surrogate", action="store_true")
    args = ap.parse_args()

    tmp = os.path.join(os.path.dirname(args.out) or ".", "ledgers")
    os.makedirs(tmp, exist_ok=True)

    report: dict = {
        "record_type": "MR002_VALIDATION2_DRYRUN",
        "authority": "MR002_Validation2_ProspectiveRegistration_v1.0",
        "N3_verdict_identity": N3_VERDICT,
        "validation_2_bytes_read": 0,
        "sealed_store_touched": False,
        "surrogate_domain": "development only",
    }

    print("NEGATIVE CONTROLS — one fixture per terminal path")
    nc = negative_controls(tmp)
    report["negative_controls"] = nc
    for k, v in nc.items():
        flag = v.get("fired", v.get("caught", v.get("conformant", v.get("one_exposure_consumes"))))
        print(f"  {k:42s} {'OK' if flag else 'FAIL'}")

    covered = {p: bool(nc.get(p, {}).get("fired")) for p in TERMINAL_PATHS}
    report["terminal_path_coverage"] = covered
    report["every_terminal_path_exercised"] = all(covered.values())

    if not args.skip_surrogate:
        print("\nLIVE SURROGATE RUN (development corpus)")
        sr = surrogate_run(args.sessions)
        report["surrogate_run"] = sr
        print(f"  stage3 dispositions {sr['stage3'].get('by_disposition')}")
        print(f"  routing guard       PASSED on real routing "
              f"({sr['routing_guard']['invocations']} invocations)")

    report["preconditions"] = preconditions(sealed_store_reachable_by_this_process=False)

    gaps = []
    if not report["every_terminal_path_exercised"]:
        gaps.append("not every terminal path fired")
    if not report["preconditions"]["live_role_assumption_test_performed"]:
        gaps.append("live reader/publisher role-assumption separation test NOT performed")
    report["open_gaps"] = gaps
    report["disposition"] = ("DRYRUN_PASS_WITH_OPEN_GAPS" if gaps else "DRYRUN_PASS")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    body = json.dumps(report, indent=1, sort_keys=True, default=str)
    with open(args.out, "w", encoding="ascii") as fh:
        fh.write(body + "\n")
    print(f"\nevery terminal path exercised : {report['every_terminal_path_exercised']}")
    print(f"open gaps                     : {gaps or 'none'}")
    print(f"disposition                   : {report['disposition']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
