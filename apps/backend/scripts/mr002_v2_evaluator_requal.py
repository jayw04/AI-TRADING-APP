"""MR-002 Blocker 3 — FULL evaluator re-qualification on the DEVELOPMENT surrogate.

Sealed authority: MR002_Validation2_ProspectiveRegistration_v1.0, as amended by Amendment C.

⛔ Development/surrogate content ONLY. Zero withheld Validation-2 bytes. The sealed store is never
contacted and no Validation-2 object key appears anywhere in this file.

WHY THIS EXISTS AND WHAT IT IS NOT
    The 34 phase3c unit tests establish that the implementation is internally consistent. They do
    NOT establish that the whole evaluator PROTOCOL works. This exercises the protocol: the real
    replay path the consumed opening used, the frozen solver pair, the fold and gate wiring, the
    3-of-5 decision rule, the routing/census guard, terminal-state suppression, and the evidence
    handoff.

A SCOPE PROPERTY THAT MUST BE DISCLOSED, NOT PAPERED OVER
    Amendment C moved the folds to 2023-05-30..2026-07-01. The development surrogate is
    2013..2019, so NO development session maps to a Validation-2 fold -- fold_of() returns None for
    every one of them. The fold and gate wiring therefore CANNOT be exercised by re-dating
    development economics into the Validation-2 calendar; doing that would be inventing a mapping
    and dressing development returns as validation ones.

    So the qualification is split, and the split is stated:
      LEG 1  the REAL replay, on real development data, through the real evaluator path
      LEG 2  the fold/gate/decision wiring, on the REAL Validation-2 fold dates, driven by
             explicit synthetic NAV fixtures that are labelled synthetic everywhere they appear
    Neither leg is presented as the other.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, "/work/apps/backend")

OUT_DIR = "/work/.mr002out/v2"
DEV_WINDOW = (date(2013, 1, 2), date(2019, 10, 2))
SOLVER_A, SOLVER_B = "QUADPROG_SQRT", "PIQP_P2"
REGISTRATION = "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57"
AMENDMENT_C_COMMIT = "1498039"


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True, default=str)
            + "\n").encode("ascii")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LEG 1 — the REAL evaluator path on real development data
# ══════════════════════════════════════════════════════════════════════════════════════════════

def leg1_real_replay(sessions: int) -> dict:
    import app.research.mr002.joint_portfolio as jp
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.n1 import seam as v2seam
    from app.research.mr002.phase3c import replay as p3c
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(*DEV_WINDOW)[:sessions]

    out: dict = {"sessions_replayed": len(days), "per_config": {}}
    for cfg in ("A", "B", "C"):
        census: list = []
        inv = {"n": 0}
        t0 = time.time()
        with v2seam.routed_v2(census, candidate=SOLVER_B, solvers=SOLVERS,
                              certify_fn=canonical_qualify):
            inner = jp._solve_qp                      # captured INSIDE the ctx — the N3 lesson

            def _make(routed, counter):
                # Bound explicitly rather than closed over the loop variable. Ruff B023 flags the
                # late-binding form, and it is the same defect class as the N3 routing bug: the
                # wrapper would silently call whatever `inner` happened to be at call time.
                def observe(H, t, A_ub, b_ub, A_eq, b_eq, upper):
                    counter["n"] += 1
                    return routed(H, t, A_ub, b_ub, A_eq, b_eq, upper)
                return observe

            jp._solve_qp = _make(inner, inv)
            stopped = None
            try:
                # the REAL Validation-2 evaluator entry point, with the fatal interlock ARMED
                va = p3c.run_config_validation(days, CONFIGS[cfg], assert_oos_boundary=True)
            except Exception as exc:  # noqa: BLE001 — a stop is a RESULT
                stopped, va = f"{type(exc).__name__}: {str(exc)[:300]}", None
            finally:
                jp._solve_qp = inner

        summary = v2seam.census_summary(census)
        entry = {"stopped": stopped, "seconds": round(time.time() - t0, 1),
                 "stage3": summary, "invocations": inv["n"], "census_rows": len(census)}
        if va is not None:
            a = va.acc
            entry.update({
                "nav_final": float(a.nav),
                "sessions_scored": len(a.nav_curve),
                "costs": float(a.costs), "borrow": float(a.borrow),
                "traded_notional": float(a.traded_notional),
                "entries_long": a.entries_long, "entries_short": a.entries_short,
                "exits": a.exits, "reductions": a.reductions,
                "exit_reasons": dict(a.exit_reasons),
                "outcomes": dict(a.outcomes),
                "closed_trades": len(a.trades),
                "hard_exits_due": a.hard_exits_due,
                "hard_exits_executed": a.hard_exits_executed,
                "run_hash": hashlib.sha256("|".join(a.session_hashes).encode()).hexdigest(),
            })
        out["per_config"][cfg] = entry

    # the frozen pair was genuinely routed, not merely configured
    vocab = set()
    for cfg in out["per_config"].values():
        vocab |= set((cfg["stage3"] or {}).get("by_disposition", {}))
    out["frozen_pair_routed"] = bool(vocab & {"PRIMARY_CERTIFIED", "SECONDARY_CERTIFIED"})
    out["disposition_vocabulary_observed"] = sorted(vocab)
    out["interlock_armed"] = True
    out["interlock_did_not_fire_on_development"] = all(
        c["stopped"] is None for c in out["per_config"].values())
    out["formation_and_exits_exercised"] = any(
        c.get("exit_reasons") for c in out["per_config"].values())
    out["corporate_action_exits"] = {
        cfg: c.get("exit_reasons", {}).get("exit_corporate_action", 0)
        for cfg, c in out["per_config"].items()}
    return out


def leg1_interlock_negative_control() -> dict:
    """The interlock must still be FATAL. Prove it fires rather than trusting that it would."""
    from app.research.mr002.phase3c import OUT_OF_BOUNDS_AFTER, IntegrityFailure
    from app.research.mr002.phase3c import replay as p3c
    from app.research.mr002.runner import CONFIGS

    class _Day:
        def __init__(self, s):
            self.session = s
            self.next_open_session = None

    beyond = OUT_OF_BOUNDS_AFTER + timedelta(days=1)
    try:
        p3c.run_config_validation([_Day(beyond)], CONFIGS["B"], assert_oos_boundary=True)
        fired, detail = False, "INTERLOCK DID NOT FIRE"
    except IntegrityFailure as exc:
        fired, detail = True, str(exc)[:200]
    except Exception as exc:  # noqa: BLE001
        fired, detail = False, f"wrong exception: {type(exc).__name__}: {exc}"
    return {"probe_session": str(beyond), "boundary": str(OUT_OF_BOUNDS_AFTER),
            "interlock_fired": fired, "detail": detail,
            "why": "Amendment C moved the boundary but must NOT have weakened the control. A "
                   "boundary that no longer stops anything is worse than the old one."}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LEG 2 — fold / gate / decision wiring on the REAL Validation-2 fold dates.
#
# Driven by EXPLICIT SYNTHETIC NAV fixtures. Development economics are NOT re-dated into the
# Validation-2 calendar: that would invent a mapping and dress development returns as validation
# ones. Every number in this leg is synthetic and labelled so.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _fixture(fold_signs: list, a_sign: float, c_sign: float) -> dict:
    """Build sessions + NAV curves over the REAL fold dates, with chosen per-fold directions."""
    from app.research.mr002.phase3c import NAV0
    from app.research.mr002.phase3c.folds import FROZEN_FOLDS

    sessions, nav_b = [], []
    nav = NAV0
    for f, sign in zip(FROZEN_FOLDS, fold_signs, strict=True):
        step = (1.0 + 0.0002 * sign)
        d, n = f.first, 0
        while d <= f.last and n < f.sessions:
            sessions.append(d)
            nav *= step
            nav_b.append(nav)
            d += timedelta(days=1)
            n += 1
    def curve(sign):
        v, out = NAV0, []
        for _ in sessions:
            v *= (1.0 + 0.0002 * sign)
            out.append(v)
        return out
    return {
        "A": {"sessions": sessions, "nav_curve": curve(a_sign), "daily_ret": []},
        "B": {"sessions": sessions, "nav_curve": nav_b, "daily_ret": []},
        "C": {"sessions": sessions, "nav_curve": curve(c_sign), "daily_ret": []},
    }


def leg2_gate_wiring() -> dict:
    from app.research.mr002.phase3c import gates
    from app.research.mr002.phase3c.folds import FROZEN_FOLDS

    results = {}

    # every fixture below is SYNTHETIC; only the fold DATES are real
    cases = {
        "ADVANCE_4_of_5_positive": ([1, 1, 1, -1, 1], 1.0, 1.0, "VALIDATION_ADVANCE_REQUEST"),
        "ADVANCE_exactly_3_of_5": ([1, 1, 1, -1, -1], 1.0, 1.0, "VALIDATION_ADVANCE_REQUEST"),
        "REJECT_only_2_of_5": ([1, 1, -1, -1, -1], 1.0, 1.0, "VALIDATION_DO_NOT_ADVANCE"),
        "REJECT_folds_pass_but_A_negative": ([1, 1, 1, 1, 1], -1.0, 1.0,
                                             "VALIDATION_DO_NOT_ADVANCE"),
        "REJECT_folds_pass_but_C_negative": ([1, 1, 1, 1, 1], 1.0, -1.0,
                                             "VALIDATION_DO_NOT_ADVANCE"),
    }
    for name, (signs, a, c, expect) in cases.items():
        v = gates.evaluate(_fixture(signs, a, c), integrity_ok=True)
        g = v["gate_validation_positive_folds_ge_3_of_5"]
        results[name] = {
            "verdict": v["verdict"], "expected": expect, "matches": v["verdict"] == expect,
            "gates_evaluated": v["gates_evaluated"],
            "observed_positive_folds": g["observed_positive_folds"],
            "folds_with_sessions": sum(1 for f in g["per_fold"] if f["sessions"] > 0),
            "SYNTHETIC": True,
        }

    # integrity short-circuit: excellent economics must NOT produce a verdict
    v = gates.evaluate(_fixture([1, 1, 1, 1, 1], 1.0, 1.0), integrity_ok=False,
                       integrity_detail="synthetic replay-integrity stop")
    results["INTEGRITY_FAILURE_suppresses_excellent_economics"] = {
        "verdict": v["verdict"], "expected": "INTEGRITY_FAILURE",
        "matches": v["verdict"] == "INTEGRITY_FAILURE",
        "gates_evaluated": v["gates_evaluated"],
        "not_mislabelled_as_reject": v["verdict"] != "VALIDATION_DO_NOT_ADVANCE",
        "SYNTHETIC": True,
    }

    # the fold wiring itself: all five folds must actually receive sessions
    fx = _fixture([1, 1, 1, 1, 1], 1.0, 1.0)
    fr = gates.fold_net_returns(fx["B"]["sessions"], fx["B"]["nav_curve"])
    results["fold_wiring"] = {
        "folds": len(FROZEN_FOLDS),
        "all_five_populated": all(fr[f.index]["sessions"] > 0 for f in FROZEN_FOLDS),
        "per_fold_sessions": {f.index: fr[f.index]["sessions"] for f in FROZEN_FOLDS},
        "fold_dates_are_REAL_validation2_dates": [
            {"fold": f.index, "first": str(f.first), "last": str(f.last)} for f in FROZEN_FOLDS],
        "nav_curves_are_SYNTHETIC": True,
    }
    results["all_cases_match"] = all(
        r.get("matches") for r in results.values() if isinstance(r, dict) and "matches" in r)
    return results


def leg3_terminal_and_handoff(report: dict) -> dict:
    """Terminal-state suppression via the registered harness, and the evidence handoff."""
    from scripts.mr002_v2_harness import (
        CONFORMANT,
        NOT_EVALUATED,
        OpenedObjectLedger,
        combine,
        conformance,
        routing_guard,
    )

    lg = OpenedObjectLedger(os.path.join(OUT_DIR, "requal_ledger.jsonl"))
    conf = conformance(instances_required=10, instances_resolved=10, integrity_defects=0,
                       unregistered_terminations=0, registered_terminations=3,
                       source_identity_ok=True, runtime_identity_ok=True, evidence_complete=True)
    nonconf = conformance(instances_required=10, instances_resolved=9, integrity_defects=0,
                          unregistered_terminations=0, registered_terminations=0,
                          source_identity_ok=True, runtime_identity_ok=True,
                          evidence_complete=True)
    r_ok = combine(conf, {"verdict": "VALIDATION_DO_NOT_ADVANCE", "gates": {}, "observed": {}},
                   ledger=lg)
    r_bad = combine(nonconf, {"verdict": "VALIDATION_ADVANCE_REQUEST", "gates": {},
                              "observed": {}}, ledger=lg)

    # the guard, against the REAL census the live replay produced
    disp = report["leg1_real_replay"]["per_config"]["B"]["stage3"].get("by_disposition", {})
    inv = report["leg1_real_replay"]["per_config"]["B"]["invocations"]
    rows = report["leg1_real_replay"]["per_config"]["B"]["census_rows"]
    guard = routing_guard(census_rows=rows, invocations=inv, dispositions=disp)

    # evidence handoff: the package the evaluator would stage for the publisher
    pkg = {"schema": "mr002-validation2-evidence/1.0", "surrogate": True,
           "validation_2_bytes": 0, "leg1": report["leg1_real_replay"],
           "leg2": report["leg2_gate_wiring"]}
    staging = os.path.join(OUT_DIR, "staging")
    os.makedirs(staging, exist_ok=True)
    path = os.path.join(staging, "validation2_evidence_package.json")
    body = _canonical(pkg)
    with open(path, "wb") as fh:
        fh.write(body)
        fh.flush()
        os.fsync(fh.fileno())
    return {
        "conformant_run_keeps_its_verdict": r_ok["terminal_state"] == "VALIDATION_DO_NOT_ADVANCE",
        "nonconformant_run_suppresses_verdict": (
            r_bad["terminal_state"] == "INTEGRITY_FAILURE"
            and r_bad["economic_verdict"] == NOT_EVALUATED),
        "conformance_state_with_registered_terminations": conf["state"] == CONFORMANT,
        "routing_guard_on_the_real_census": guard,
        "evidence_package": {
            "staged_at": path, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "fsynced": True,
            "handoff_protocol": "written to a staging path the evaluator may only PutObject to; "
                                "the publisher reads it GetObject-only. Amendment B v1.1 is NOT "
                                "APPLIED, so this leg exercises the PROTOCOL SHAPE locally and "
                                "does not prove the deployed IAM separation.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Blocker 3 — evaluator re-qualification")
    ap.add_argument("--sessions", type=int, default=900)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "evaluator_requal.json"))
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    report: dict = {
        "record_type": "MR002_Validation2_EvaluatorRequalification",
        "version": "1.0",
        "authority": REGISTRATION,
        "amendment_C_commit": AMENDMENT_C_COMMIT,
        "solver_A": SOLVER_A, "solver_B": SOLVER_B,
        "domain": "DEVELOPMENT SURROGATE ONLY",
        "validation_2_bytes_read": 0,
        "sealed_store_touched": False,
        "no_tuning_performed": "nothing in this run feeds back into any parameter, threshold or "
                               "selection. It is a protocol test.",
    }

    print("LEG 1 — real evaluator path on real development data")
    report["leg1_real_replay"] = leg1_real_replay(args.sessions)
    for cfg, e in report["leg1_real_replay"]["per_config"].items():
        print(f"  {cfg}: {e['seconds']:6.1f}s inv={e['invocations']:5d} "
              f"{e['stage3'].get('by_disposition')} stopped={e['stopped']}")
    print(f"  frozen pair routed : {report['leg1_real_replay']['frozen_pair_routed']}")

    print("\nLEG 1b — interlock negative control")
    report["leg1b_interlock"] = leg1_interlock_negative_control()
    print(f"  interlock fired on a beyond-boundary session: "
          f"{report['leg1b_interlock']['interlock_fired']}")

    print("\nLEG 2 — fold / gate / 3-of-5 wiring on REAL fold dates (SYNTHETIC nav)")
    report["leg2_gate_wiring"] = leg2_gate_wiring()
    for k, v in report["leg2_gate_wiring"].items():
        if isinstance(v, dict) and "matches" in v:
            print(f"  {k:46s} {v['verdict']:28s} {'OK' if v['matches'] else 'FAIL'}")
    print(f"  all_five_folds_populated: "
          f"{report['leg2_gate_wiring']['fold_wiring']['all_five_populated']}")

    print("\nLEG 3 — terminal-state suppression + evidence handoff")
    report["leg3_terminal_and_handoff"] = leg3_terminal_and_handoff(report)
    l3 = report["leg3_terminal_and_handoff"]
    print(f"  conformant keeps verdict      : {l3['conformant_run_keeps_its_verdict']}")
    print(f"  non-conformant suppresses     : {l3['nonconformant_run_suppresses_verdict']}")
    print(f"  registered terminations OK    : "
          f"{l3['conformance_state_with_registered_terminations']}")

    l1 = report["leg1_real_replay"]
    checks = {
        "real_replay_completed_all_configs": l1["interlock_did_not_fire_on_development"],
        "frozen_pair_actually_routed": l1["frozen_pair_routed"],
        "interlock_still_fatal": report["leg1b_interlock"]["interlock_fired"],
        "gate_decision_rule_correct_every_case": report["leg2_gate_wiring"]["all_cases_match"],
        "all_five_folds_populated": report["leg2_gate_wiring"]["fold_wiring"][
            "all_five_populated"],
        "integrity_suppresses_economics": report["leg2_gate_wiring"][
            "INTEGRITY_FAILURE_suppresses_excellent_economics"]["matches"],
        "terminal_suppression_correct": (l3["conformant_run_keeps_its_verdict"]
                                         and l3["nonconformant_run_suppresses_verdict"]),
        "registered_termination_not_a_defect": l3[
            "conformance_state_with_registered_terminations"],
        "evidence_package_staged_and_fsynced": l3["evidence_package"]["fsynced"],
    }
    report["checks"] = checks
    gaps = []
    if not all(checks.values()):
        gaps.append("one or more protocol checks failed")
    gaps.append("deployed IAM reader/publisher separation NOT proven here — Amendment B v1.1 is "
                "not applied; leg 3 exercises the handoff SHAPE only")
    report["open_gaps"] = gaps
    report["disposition"] = ("EVALUATOR_REQUALIFICATION_PASS" if all(checks.values())
                             else "EVALUATOR_REQUALIFICATION_FAIL")
    report["scope_disclosure"] = (
        "LEG 1 is the real evaluator path on real development data. LEG 2 uses SYNTHETIC NAV "
        "fixtures on the REAL Validation-2 fold dates, because no development session maps to a "
        "Validation-2 fold and re-dating development economics into that calendar would invent a "
        "mapping. Neither leg is presented as the other.")

    body = _canonical(report)
    with open(args.out, "wb") as fh:
        fh.write(body)
    print(f"\nchecks passed : {sum(1 for v in checks.values() if v)}/{len(checks)}")
    print(f"disposition   : {report['disposition']}")
    print(f"wrote {args.out}")
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
