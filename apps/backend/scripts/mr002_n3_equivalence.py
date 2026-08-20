"""MR-002 Gate N3 — FULL DEVELOPMENT BEHAVIOURAL / ECONOMIC EQUIVALENCE differential.

Sealed authority: MR002_N3_ProspectiveRegistration_v1.0.
The rule this script implements was frozen BEFORE this script was written; the registration record
names it as `NOT YET WRITTEN AT REGISTRATION TIME` for exactly that reason. Nothing here may add,
relax or reinterpret a criterion.

THE ONE QUESTION
    Does the N1/N2-qualified Stage-3 v2 method (Solver A = QUADPROG_SQRT, Solver B = PIQP_P2)
    preserve the frozen MR-002 development economics end-to-end when substituted for Stage-3 v1?

Three arms per config, over the identical governed development window:

    v1_control      Stage-3 via the countersigned v1 seam, UNINSTRUMENTED
    v1              ... the same, INSTRUMENTED  (the baseline the differential is taken against)
    v2              Stage-3 via the v2 certificate-driven method, B = PIQP_P2, INSTRUMENTED

`v1_control` exists to prove the instrument inert. If the instrumented and uninstrumented v1 arms
disagree on any session hash or any economic field, the differential is measuring the instrument
rather than the method, and that is an N3_STOP for INSTRUMENT DEFECT — never a method result.

⛔ FIREWALLS (registration §firewalls), all load-bearing:
  * ONE frozen pair. No candidate set, no ranking, no solver recommendation. N1 selected B; N2
    confirmed the pair; N3 receives it. Re-scoring PIQP_P1 here would re-open a closed selection on
    replay economics, which is selection on returns.
  * BETTER IS NOT A WIN. Every comparison below is on MAGNITUDE and is SIGN-BLIND. A favourable
    difference cannot pass a test an unfavourable one fails. v2 repairs numerical resolution; it is
    not licensed to move the economics in either direction.
  * N1 already reported byte identity on this window. That is prior evidence and nothing more. It
    lowers no requirement here, and reproducing it is not itself the pass criterion.
  * No new economic statistic. Sharpe and drawdown are quoted only because metrics() already
    computes them, and only as reconciliation evidence.

INSTRUMENTATION IS OBSERVATION ONLY. Nothing below edits the governing construction. The replay's
own modules are untouched; two module-level names are wrapped for the duration of one arm and
restored in a finally block. No tolerance, epsilon, profile, ordering or attempt count is changed.

Development domain only. No sealed reader, no validation store, no OOS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import time
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002 import stage3_route as sr  # noqa: E402
from app.research.mr002.n1 import seam as v2seam  # noqa: E402
from app.research.mr002.phase3c import folds as f3c  # noqa: E402

OUT_DIR = "/work/.mr002out/n3"
WINDOW = (date(2013, 1, 2), date(2019, 10, 2))
COUNTERSIGNATURE = "MR002_Stage3ExecutionCountersignature_v1.0"

# The FROZEN pair. N3 selects nothing.
SOLVER_A = "QUADPROG_SQRT"
SOLVER_B = "PIQP_P2"

REGISTRATION_IDENTITY = "b6b8aaca6fee92292f16d12243fdeace4a909234d12d4215c1c966b2cbb46328"
N1_VERDICT = "629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81"
N2_VERDICT = "27f98548067b3017870937c22196212e5bb1b11fdbd6a961a329f85f82aae471"
DATASET_SHA = "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a"

# The governed Stage-3 census the v1 arm must reproduce (registration §domain).
GOVERNED = {
    "A": {"PRIMARY_QUALIFIED": 1426, "FALLBACK_QUALIFIED": 1, "invocations": 1427},
    "B": {"PRIMARY_QUALIFIED": 1532, "FALLBACK_QUALIFIED": 3, "invocations": 1535},
    "C": {"PRIMARY_QUALIFIED": 933, "FALLBACK_QUALIFIED": 0, "invocations": 933},
}


# ── the registered disposition SEMANTIC CLASS (registration §disposition_semantic_class) ───────
# The v1 cascade and the v2 method reconcile to DISJOINT label vocabularies, so comparing raw
# strings would fail on every invocation by construction. The owner's N1 ruling (D3 clause 5) is
# that "method disposition" means the TERMINAL SEMANTIC CLASS -- resolved certified allocation vs
# unresolved / integrity stop -- not the accepted_by generator attribution. Applied verbatim, not
# extended. The allocation requirement stays STRICT: C1 is still byte identity.
_SEMANTIC_CLASS = {
    "PRIMARY_QUALIFIED": "RESOLVED_CERTIFIED_ALLOCATION",
    "FALLBACK_QUALIFIED": "RESOLVED_CERTIFIED_ALLOCATION",
    "PRIMARY_CERTIFIED": "RESOLVED_CERTIFIED_ALLOCATION",
    "SECONDARY_CERTIFIED": "RESOLVED_CERTIFIED_ALLOCATION",
    "UNRESOLVED_NUMERICAL_FAILURE": "UNRESOLVED",
    "UNRESOLVED_INSTANCE": "UNRESOLVED",
    "INVALID_RUN": "INVALID_RUN",
}


def semantic_class(label) -> str:
    """An unmapped label is UNREGISTERED, which fails C6. It is never silently bucketed."""
    return _SEMANTIC_CLASS.get(str(label), "UNREGISTERED")


def _f64(x) -> str:
    """The replay's own float64 wire form. Byte comparison means THIS, not repr()."""
    return struct.pack(">d", float(x)).hex()


def _book(d: dict) -> list:
    return [[int(k), _f64(d[k])] for k in sorted(d)]


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def econ(acc) -> dict:
    """The economic fingerprint, field-for-field as N1's preservation run defined it.

    Kept identical on purpose: it makes the two gates directly comparable, and it means N3 cannot
    be accused of having quietly chosen a friendlier set of fields.
    """
    return {
        "run_hash": hashlib.sha256("|".join(acc.session_hashes).encode()).hexdigest(),
        "nav_final": float(acc.nav),
        "nav_curve_hash": hashlib.sha256(
            np.asarray(acc.nav_curve, dtype=float).tobytes()).hexdigest(),
        "daily_ret_hash": hashlib.sha256(
            np.asarray(acc.daily_ret, dtype=float).tobytes()).hexdigest(),
        "costs": float(acc.costs),
        "borrow": float(acc.borrow),
        "traded_notional": float(acc.traded_notional),
        "entries_long": acc.entries_long,
        "entries_short": acc.entries_short,
        "exits": acc.exits,
        "reductions": acc.reductions,
        "outcomes": dict(acc.outcomes),
        "zero_reasons": dict(acc.zero_reasons),
        "sessions": len(acc.session_hashes),
    }


def trade_rows(acc) -> list:
    """The closed-trade ledger, in order, with floats on the byte wire."""
    return [
        [int(t.permaticker), int(t.side), str(t.entry_session), str(t.exit_session), str(t.reason),
         _f64(t.gross_pnl), _f64(t.costs), _f64(t.net_pnl)]
        for t in acc.trades
    ]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# INSTRUMENTATION — observation only
#
# Two module-level names in `mr002_development_run` are wrapped for the duration of one arm:
#
#   build_joint   wrapped to record the per-session DECISION surface: the holdings and candidate
#                 sets it was given, and the JointResult it returned (outcome, y book, x book,
#                 zero-entry reason). This is the only place the replay learns what Stage-3 decided.
#   Acc           replaced by a subclass whose `session_hashes` list snapshots the accumulator at
#                 the moment the session's determinism hash is appended — which is the LAST
#                 statement of the session loop, so every accumulator is already updated for that
#                 session and successive snapshots difference cleanly into per-session values.
#
# Neither wrapper computes anything the replay consumes. `build_joint`'s return value is passed
# through untouched; the Acc subclass adds no field the loop reads. Inertness is not asserted on
# that reasoning alone — it is MEASURED by the v1_control arm.
# ══════════════════════════════════════════════════════════════════════════════════════════════

_SCALARS = ("costs", "borrow", "traded_notional", "entries_long", "entries_short", "exits",
            "reductions", "adv_clipped", "over_cap_days", "hard_exits_due",
            "hard_exits_executed", "hard_exits_pending_missing_open", "raw_solves",
            "scaled_rescues", "per_solve_hashes")


def install_instrument(mdr, days, rows: list):
    """Wrap build_joint and Acc. Returns a restore() callable; ALWAYS call it in a finally."""
    pending: dict = {}
    real_build = mdr.build_joint
    real_acc = mdr.Acc

    def wrapped_build_joint(holdings, candidates):
        res = real_build(holdings, candidates)
        pending.clear()
        pending.update({
            "holdings": sorted(int(h.permaticker) for h in holdings),
            "candidates": sorted(int(c.permaticker) for c in candidates),
            "outcome": res.outcome,
            "y": _book(res.y),
            "x": _book(res.x),
            "zero_entry_reason": (res.diagnostics or {}).get("zero_entry_reason"),
        })
        return res

    class InstrumentedAcc(real_acc):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            outer = self

            class _SessionHashes(list):
                def append(self, item):
                    i = len(self)
                    list.append(self, item)
                    rows.append(_snapshot(outer, days, i, item, pending))
                    pending.clear()

            self.session_hashes = _SessionHashes()

    mdr.build_joint = wrapped_build_joint
    mdr.Acc = InstrumentedAcc

    def restore():
        mdr.build_joint = real_build
        mdr.Acc = real_acc

    return restore


def _snapshot(a, days, i, session_hash, pending) -> dict:
    """One per-session row. Cumulative scalars; the differential takes the deltas."""
    sess = days[i].session
    row = {
        "i": i,
        "session": str(sess),
        "session_hash": session_hash,
        "fold": f3c.fold_of(sess),
        "nav": _f64(a.nav),
        "nav_curve": _f64(a.nav_curve[i]),
        "daily_ret": _f64(a.daily_ret[i]),
        "cum": {k: (_f64(getattr(a, k)) if isinstance(getattr(a, k), float) else getattr(a, k))
                for k in _SCALARS},
        "outcomes_cum": dict(a.outcomes),
        "zero_reasons_cum": dict(a.zero_reasons),
        "exit_reasons_cum": dict(a.exit_reasons),
        "trades_cum": len(a.trades),
        "lp_statuses_cum": sorted(a.lp_statuses),
        "max_kkt": _f64(a.max_kkt),
        "max_kappa": _f64(a.max_kappa),
        "max_violation": _f64(a.max_violation),
    }
    if pending:
        row["decision"] = dict(pending)
    else:
        # No build_joint call this session: the loop took the
        # TERMINAL_SESSION_NO_EXECUTION_OPEN branch before Stage-3 could be reached.
        row["decision"] = None
    return row


def row_digest(rows: list) -> str:
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ARMS
# ══════════════════════════════════════════════════════════════════════════════════════════════

def run_arm(mdr, days, cfg_name: str, cfg_obj, arm: str, solvers, certify_fn) -> dict:
    """Execute one replay arm. Returns everything the differential needs, and nothing it doesn't.

    A Stage3Stop / InvalidRun is a RESULT, not an error to be swallowed: it is recorded and the arm
    is marked stopped, so the verdict can distinguish "v2 halted" from "v2 differed".
    """
    rows: list = []
    census: list = []
    inst_hashes: list = []
    accepted: list = []
    instrumented = arm != "v1_control"

    def make_observer(routed_solve):
        """Wrap whatever seam is CURRENTLY installed.

        ⚠ The seam must already be in place when this is called. Capturing `jp._solve_qp` before
        entering the routing context binds the ORIGINAL solver, silently un-routes the arm, and
        makes all three arms agree trivially — a false PASS that looks exactly like a real one.
        The empty Stage-3 census is the tell.
        """
        def observe(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
            inst_hashes.append(_hash_instance(targets, A_ub, b_ub, A_eq, b_eq, upper))
            z, info = routed_solve(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper)
            accepted.append(np.asarray(z, dtype=float).copy())
            return z, info
        return observe

    if arm == "v2":
        ctx = v2seam.routed_v2(census, candidate=SOLVER_B, solvers=solvers, certify_fn=certify_fn)
        summarize = v2seam.census_summary
    else:
        ctx = sr.routed(census, countersignature=COUNTERSIGNATURE)
        summarize = sr.census_summary

    restore = install_instrument(mdr, days, rows) if instrumented else (lambda: None)
    stopped = None
    acc = None
    t0 = time.time()
    try:
        with ctx:
            inner = jp._solve_qp                      # the ROUTED seam, captured inside the ctx
            jp._solve_qp = make_observer(inner)
            try:
                acc = mdr.run_config(days, cfg_obj)
            except Exception as exc:  # noqa: BLE001 - a stop is a RESULT, recorded not hidden
                stopped = f"{type(exc).__name__}: {str(exc)[:400]}"
            finally:
                jp._solve_qp = inner
    finally:
        restore()

    out = {
        "arm": arm,
        "stopped": stopped,
        "seconds": round(time.time() - t0, 1),
        "stage3": summarize(census),
        "invocations": len(inst_hashes),
        # Routing guard. An arm that solved instances but produced NO census row never went
        # through its seam at all, so its "agreement" with the other arms is vacuous. This is
        # checked rather than trusted because the failure mode is a false PASS, not a crash.
        "routing_engaged": bool(len(census) > 0 or len(inst_hashes) == 0),
        "census_rows": len(census),
        "disposition_sequence": [str(r.get("disposition")) for r in census],
        "semantic_class_sequence": [semantic_class(r.get("disposition")) for r in census],
        "accepted_by_sequence": [str(r.get("accepted_by")) for r in census],
        "instance_sequence_hash": hashlib.sha256("|".join(inst_hashes).encode()).hexdigest(),
        "instance_hashes": inst_hashes,
        "accepted": accepted,
        "rows": rows,
        "row_digest": row_digest(rows) if rows else None,
    }
    if acc is not None:
        out["econ"] = econ(acc)
        out["trades"] = trade_rows(acc)
        out["trades_digest"] = row_digest(trade_rows(acc))
        out["session_hashes"] = list(acc.session_hashes)
        # metrics() keys its parameter echo off the CONFIG name, not the arm name.
        out["metrics"] = mdr.metrics(acc, cfg_name, len(days))
        out["cumulative_return"] = _f64(acc.nav_curve[-1] / mdr.NAV0 - 1.0) if acc.nav_curve \
            else None
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE DIFFERENTIAL
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _row_field_diff(r1: dict, r2: dict) -> list:
    """Every field of one session row that differs. Sign-blind by construction: we report THAT a
    field differs and what both values were, never which one is 'better'."""
    out = []
    for k in sorted(set(r1) | set(r2)):
        if r1.get(k) != r2.get(k):
            out.append({"field": k, "v1": r1.get(k), "v2": r2.get(k)})
    return out


def differential(v1: dict, v2: dict) -> dict:
    """Compare the v2 arm against the v1 baseline across the whole registered surface."""
    d: dict = {}

    # ---- Stage-3 layer -------------------------------------------------------------------
    d["stage3_invocations_v1"] = v1["invocations"]
    d["stage3_invocations_v2"] = v2["invocations"]
    d["instance_sequence_identical"] = v1["instance_hashes"] == v2["instance_hashes"]

    z1, z2 = v1["accepted"], v2["accepted"]
    n = min(len(z1), len(z2))
    alloc_diff = [
        {"k": k, "max_abs": float(np.max(np.abs(z1[k] - z2[k]))),
         "l2": float(np.linalg.norm(z1[k] - z2[k]))}
        for k in range(n)
        if z1[k].shape == z2[k].shape and z1[k].tobytes() != z2[k].tobytes()
    ]
    shape_mismatch = [k for k in range(n) if z1[k].shape != z2[k].shape]
    d["accepted_allocation"] = {
        "compared": n,
        "byte_identical": sum(1 for k in range(n)
                              if z1[k].shape == z2[k].shape and z1[k].tobytes() == z2[k].tobytes()),
        "differing": len(alloc_diff),
        "shape_mismatch": shape_mismatch[:25],
        "differences": alloc_diff[:50],
        "max_l2": max((x["l2"] for x in alloc_diff), default=0.0),
        # The registered equivalence vocabulary, not a new one.
        "equivalence": "EQUIVALENCE_TRIVIAL" if not alloc_diff and not shape_mismatch
                       else "REQUIRES_TIER_2_ADJUDICATION",
    }
    # Disposition is compared at the REGISTERED SEMANTIC CLASS, per-invocation and in order.
    sc1, sc2 = v1["semantic_class_sequence"], v2["semantic_class_sequence"]
    scm = min(len(sc1), len(sc2))
    sc_diff = [{"k": k, "v1_label": v1["disposition_sequence"][k], "v1_class": sc1[k],
                "v2_label": v2["disposition_sequence"][k], "v2_class": sc2[k]}
               for k in range(scm) if sc1[k] != sc2[k]]
    d["stage3_semantic_class"] = {
        "compared": scm,
        "identical": (sc1 == sc2),
        "differing": len(sc_diff),
        "differences": sc_diff[:50],
        "counts_v1": {c: sc1.count(c) for c in sorted(set(sc1))},
        "counts_v2": {c: sc2.count(c) for c in sorted(set(sc2))},
        "unregistered_v1": sc1.count("UNREGISTERED"),
        "unregistered_v2": sc2.count("UNREGISTERED"),
    }
    d["stage3_disposition_identical"] = (sc1 == sc2)

    # Generator attribution: DIAGNOSTIC ONLY, never a pass criterion (registration
    # §disposition_semantic_class.generator_attribution_is_diagnostic).
    ab1, ab2 = v1["accepted_by_sequence"], v2["accepted_by_sequence"]
    abm = min(len(ab1), len(ab2))
    d["generator_attribution_DIAGNOSTIC_ONLY"] = {
        "status": "DIAGNOSTIC — not a pass criterion",
        "raw_label_pairs_v1": {x: ab1.count(x) for x in sorted(set(ab1))},
        "raw_label_pairs_v2": {x: ab2.count(x) for x in sorted(set(ab2))},
        "invocations_where_attribution_differs": sum(1 for k in range(abm) if ab1[k] != ab2[k]),
        "raw_disposition_counts_v1": v1["stage3"].get("by_disposition"),
        "raw_disposition_counts_v2": v2["stage3"].get("by_disposition"),
        "note": "the two arms use disjoint label vocabularies, so raw-label differences are "
                "EXPECTED and carry no verdict weight",
    }
    d["stage3_v1"] = v1["stage3"]
    d["stage3_v2"] = v2["stage3"]

    # ---- session layer -------------------------------------------------------------------
    r1, r2 = v1["rows"], v2["rows"]
    d["sessions_v1"], d["sessions_v2"] = len(r1), len(r2)
    m = min(len(r1), len(r2))
    differing = [{"i": i, "session": r1[i]["session"], "fields": _row_field_diff(r1[i], r2[i])}
                 for i in range(m) if r1[i] != r2[i]]
    d["session_rows"] = {
        "compared": m,
        "byte_identical": m - len(differing),
        "differing": len(differing),
        "first_differing": differing[:50],
        "row_digest_v1": v1["row_digest"],
        "row_digest_v2": v2["row_digest"],
        "row_digest_identical": v1["row_digest"] == v2["row_digest"],
    }
    d["session_hash_sequence_identical"] = v1.get("session_hashes") == v2.get("session_hashes")

    # fold membership - vacuous on this domain, and recorded as such (registration disclosure)
    folds1 = [r["fold"] for r in r1]
    folds2 = [r["fold"] for r in r2]
    vacuous = all(x is None for x in folds1) and all(x is None for x in folds2)
    d["fold_membership"] = {
        # ⛔ Deliberately NOT reported as a PASS. A green check here would later be misread as
        # "fold results were reconciled", which is false and unfixable after the fact.
        "status": "NOT_APPLICABLE / STRUCTURALLY_DISJOINT" if vacuous else "EVALUABLE",
        "counts_as_a_passed_check": False,
        "sequences_equal": folds1 == folds2,
        "distinct_values_v1": sorted({str(x) for x in folds1}),
        "reason": "the governed five-fold structure spans 2020-01-13..2023-02-08; the N3 domain "
                  "is the development window 2013-01-02..2019-10-02. The two are chronologically "
                  "DISJOINT, so every replayed session maps to fold None.",
        "fold_level_economic_reconciliation": "NOT EVALUABLE in the N3 development window",
        "no_substitute_folds_created": True,
        "validation_data_accessed": False,
    }

    # ---- dividend / corporate-action channels --------------------------------------------
    # The frozen replay has NO independent cash-dividend ledger: FrozenDataset sets the
    # cash-distribution term to 0.0 for every name, so the distribution argument to economic_gap is
    # identically zero across this window. Dividends and corporate events reach the economic state
    # through two channels instead, NEITHER of which is downstream of Stage-3:
    #   (1) the gap filter, whose surviving candidate set is recorded per session, and
    #   (2) corporate actions -> action_exit -> the `exit_corporate_action` rung of the exit ladder.
    # Those actual channels are reconciled here. No synthetic dividend accumulator is invented to
    # make a checklist look complete.
    cand1 = [r["decision"]["candidates"] if r["decision"] else None for r in r1]
    cand2 = [r["decision"]["candidates"] if r["decision"] else None for r in r2]
    hold1 = [r["decision"]["holdings"] if r["decision"] else None for r in r1]
    hold2 = [r["decision"]["holdings"] if r["decision"] else None for r in r2]
    ca1 = r1[-1]["exit_reasons_cum"].get("exit_corporate_action", 0) if r1 else 0
    ca2 = r2[-1]["exit_reasons_cum"].get("exit_corporate_action", 0) if r2 else 0
    he1 = {k: r1[-1]["cum"][k] for k in ("hard_exits_due", "hard_exits_executed",
                                         "hard_exits_pending_missing_open")} if r1 else {}
    he2 = {k: r2[-1]["cum"][k] for k in ("hard_exits_due", "hard_exits_executed",
                                         "hard_exits_pending_missing_open")} if r2 else {}
    d["dividend_and_corporate_action_channels"] = {
        "direct_cash_distribution_ledger": "NOT INDEPENDENTLY AVAILABLE — the frozen development "
                                           "input carries an all-zero cash-distribution term",
        "gap_filter_candidate_set_identical": cand1 == cand2,
        "holdings_set_identical": hold1 == hold2,
        "corporate_action_exits_v1": ca1,
        "corporate_action_exits_v2": ca2,
        "corporate_action_exits_identical": ca1 == ca2,
        "hard_exit_counters_v1": he1,
        "hard_exit_counters_v2": he2,
        "hard_exit_counters_identical": he1 == he2,
        "all_channels_identical": bool(cand1 == cand2 and hold1 == hold2 and ca1 == ca2
                                       and he1 == he2),
        "note": "these channels are UPSTREAM of Stage-3, so the method under test cannot perturb "
                "them. Reconciling them confirms the two arms saw the same corporate-action and "
                "distribution-driven economics.",
    }

    # ---- trade ledger --------------------------------------------------------------------
    t1, t2 = v1.get("trades", []), v2.get("trades", [])
    tm = min(len(t1), len(t2))
    tdiff = [{"k": k, "v1": t1[k], "v2": t2[k]} for k in range(tm) if t1[k] != t2[k]]
    d["trade_ledger"] = {
        "count_v1": len(t1), "count_v2": len(t2), "compared": tm,
        "byte_identical": tm - len(tdiff), "differing": len(tdiff),
        "differences": tdiff[:50],
        "digest_identical": v1.get("trades_digest") == v2.get("trades_digest"),
    }

    # ---- economic layer ------------------------------------------------------------------
    e1, e2 = v1.get("econ", {}), v2.get("econ", {})
    same = {k: (e1.get(k) == e2.get(k)) for k in sorted(set(e1) | set(e2))}
    d["economic_fields_identical"] = same
    d["economic_differential_EXACT"] = bool(same) and all(same.values())
    d["economic_differences"] = [{"field": k, "v1": e1.get(k), "v2": e2.get(k)}
                                 for k, ok in same.items() if not ok]
    d["cumulative_return_v1"] = v1.get("cumulative_return")
    d["cumulative_return_v2"] = v2.get("cumulative_return")
    d["cumulative_return_identical"] = v1.get("cumulative_return") == v2.get("cumulative_return")

    # ---- reconciliation evidence ONLY - never decisional ---------------------------------
    d["reconciliation_evidence_only"] = {
        "status": "REPORTED, NEVER DECISIONAL - no N3 threshold is derived from any of these",
        "metrics_v1": v1.get("metrics"),
        "metrics_v2": v2.get("metrics"),
    }
    return d


def inertness_control(ctrl: dict, v1: dict) -> dict:
    """Prove the instrument inert, or stop. Registration §scope_disclosures."""
    econ_same = (ctrl.get("econ") == v1.get("econ"))
    hashes_same = (ctrl.get("session_hashes") == v1.get("session_hashes"))
    seq_same = (ctrl["instance_hashes"] == v1["instance_hashes"])
    disp_same = (ctrl["stage3"].get("by_disposition") == v1["stage3"].get("by_disposition"))
    return {
        "econ_identical": econ_same,
        "session_hash_sequence_identical": hashes_same,
        "instance_sequence_identical": seq_same,
        "stage3_disposition_identical": disp_same,
        "INERT": bool(econ_same and hashes_same and seq_same and disp_same),
        "meaning": "if this is false the differential is measuring the instrument, not the "
                   "method, and the result is N3_STOP for INSTRUMENT DEFECT",
    }


class RoutingGuardAbort(RuntimeError):
    """The differential seam was not exercised as registered. Never a method result."""


def routing_guard(arms: dict, cfg: str) -> dict:
    """FAIL-CLOSED. Abort unless every arm actually went through its Stage-3 seam AND the v1 arms
    reproduce the governed invocation count for this config.

    This exists because of a REAL defect caught before the governed execution: an early build
    captured the solver handle before entering the routing context, silently un-routing all three
    arms. Every check passed and every arm agreed -- a false clean result whose only tell was a
    Stage-3 census of zero. A guard that merely RECORDS the count would not have stopped it, so
    this one raises.
    """
    g = GOVERNED[cfg]
    problems = []
    for name, a in arms.items():
        if a["census_rows"] == 0:
            problems.append(f"{name}: ZERO Stage-3 census rows - the seam was never exercised")
        if a["invocations"] == 0:
            problems.append(f"{name}: ZERO Stage-3 invocations")
        if a["census_rows"] != a["invocations"]:
            problems.append(f"{name}: census {a['census_rows']} != invocations {a['invocations']}")
    for name in ("v1_control", "v1"):
        if arms[name]["invocations"] != g["invocations"]:
            problems.append(f"{name}: {arms[name]['invocations']} invocations, "
                            f"governed expects {g['invocations']}")
    if problems:
        raise RoutingGuardAbort(f"config {cfg} routing guard: " + "; ".join(problems))
    return {
        "expected_invocations": g["invocations"],
        "observed_invocations": {k: arms[k]["invocations"] for k in arms},
        "census_rows": {k: arms[k]["census_rows"] for k in arms},
        "all_arms_routed": True,
        "v1_arms_match_governed_invocation_count": True,
    }


def governed_census_check(arm: dict, cfg: str) -> dict:
    g = GOVERNED[cfg]
    by = arm["stage3"].get("by_disposition", {})
    return {
        "expected": g,
        "observed": {"PRIMARY_QUALIFIED": by.get("PRIMARY_QUALIFIED", 0),
                     "FALLBACK_QUALIFIED": by.get("FALLBACK_QUALIFIED", 0),
                     "invocations": arm["invocations"]},
        "reproduces_governed": (by.get("PRIMARY_QUALIFIED", 0) == g["PRIMARY_QUALIFIED"]
                                and by.get("FALLBACK_QUALIFIED", 0) == g["FALLBACK_QUALIFIED"]
                                and arm["invocations"] == g["invocations"]),
    }


def registered_checks(diff: dict, v2: dict) -> dict:
    """The six checks registered in MR002_N3_ProspectiveRegistration_v1.0 §pass_rule. No more, no
    fewer, and none reinterpreted."""
    s3 = v2["stage3"]
    # Counts come from the REGISTERED semantic classes, not from substring-matching labels.
    cls2 = diff["stage3_semantic_class"]["counts_v2"]
    cls1 = diff["stage3_semantic_class"]["counts_v1"]
    unresolved = cls2.get("UNRESOLVED", 0)
    unresolved_v1 = cls1.get("UNRESOLVED", 0)
    invalid = cls2.get("INVALID_RUN", 0)
    unregistered = cls2.get("UNREGISTERED", 0)
    # the v2 seam counts these itself; both are consulted rather than one trusted
    unreg_reason = s3.get("unregistered_termination_reasons", 0) or 0
    unrecognized = s3.get("unrecognized_outcomes", 0) or 0
    all_reconcile = bool(s3.get("all_reconcile_to_a_registered_disposition", False))

    alloc_ok = diff["accepted_allocation"]["equivalence"] == "EQUIVALENCE_TRIVIAL"
    behavioural_ok = bool(
        diff["instance_sequence_identical"]
        and diff["stage3_disposition_identical"]
        and diff["session_rows"]["differing"] == 0
        and diff["session_hash_sequence_identical"]
        and diff["trade_ledger"]["differing"] == 0
        and diff["trade_ledger"]["count_v1"] == diff["trade_ledger"]["count_v2"]
        and diff["dividend_and_corporate_action_channels"]["all_channels_identical"])
    # Fold membership is NOT part of this conjunction: it is structurally disjoint on this domain,
    # so counting it as satisfied would be counting a vacuity as evidence.
    economic_ok = bool(diff["economic_differential_EXACT"]
                       and diff["cumulative_return_identical"])

    return {
        "C1_allocation_equivalent": {"pass": alloc_ok,
                                     "basis": diff["accepted_allocation"]["equivalence"],
                                     "differing": diff["accepted_allocation"]["differing"]},
        "C2_behavioural_reconciles": {"pass": behavioural_ok,
                                      "session_rows_differing":
                                          diff["session_rows"]["differing"],
                                      "trades_differing": diff["trade_ledger"]["differing"]},
        "C3_economic_within_bound": {
            "pass": economic_ok,
            "tier": "TIER_1_BYTE_IDENTITY" if economic_ok else "TIER_2_REQUIRED",
            "bound_applied": 0.0,
            "bound_basis": "mechanically derived: conditional on instance-sequence and accepted-"
                           "allocation identity under FROZEN_THREAD_ENV, the downstream arithmetic "
                           "is the same IEEE-754 operations on the same operands in the same "
                           "order, so the bound is EXACTLY ZERO - not a chosen tolerance",
            "differences": diff["economic_differences"],
        },
        "C4_no_new_unresolved_numerical_failure": {
            "pass": (unresolved == 0 and unresolved <= unresolved_v1),
            "unresolved_v2": unresolved,
            "unresolved_v1": unresolved_v1,
            "basis": "the governed v1 census resolves every invocation, so 'no NEW unresolved "
                     "failure' means v2 must also carry zero",
        },
        "C5_no_integrity_defect": {
            "pass": (invalid == 0 and all_reconcile and unrecognized == 0),
            "invalid_run": invalid,
            "unrecognized_outcomes": unrecognized,
            "all_reconcile_to_a_registered_disposition": all_reconcile,
        },
        "C6_no_unregistered_termination_reason": {
            "pass": (unregistered == 0 and unreg_reason == 0),
            "unregistered_semantic_classes": unregistered,
            "unregistered_termination_reasons": unreg_reason,
        },
    }


def disposition_for(cfg_result: dict) -> str:
    if cfg_result.get("v2_stopped"):
        return "N3_STOP"
    if not cfg_result.get("routing_engaged_all_arms", True):
        return "N3_STOP_ROUTING_DEFECT"
    if not cfg_result["inertness"]["INERT"]:
        return "N3_STOP_INSTRUMENT_DEFECT"
    checks = cfg_result["registered_checks"]
    if all(c["pass"] for c in checks.values()):
        return "N3_PASS"
    # C1/C2 are the primary gate; a failure there is not a numerical-tolerance question.
    if not checks["C1_allocation_equivalent"]["pass"] or \
            not checks["C2_behavioural_reconciles"]["pass"]:
        return "N3_STOP"
    return "N3_STOP_PENDING_TIER_2_ADJUDICATION"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="A,B,C")
    ap.add_argument("--tag", default="n3")
    args = ap.parse_args()

    t0 = time.time()
    import scripts.mr002_development_run as mdr
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(*WINDOW)
    print(f"[{time.time()-t0:7.1f}s] loaded {len(days)} development sessions", flush=True)

    report: dict = {
        "gate": "N3",
        "registration_identity": REGISTRATION_IDENTITY,
        "N1_verdict_identity": N1_VERDICT,
        "N2_verdict_identity": N2_VERDICT,
        "dataset_sha256": DATASET_SHA,
        "solver_A": SOLVER_A,
        "solver_B": SOLVER_B,
        "selection_occurred": False,
        "window": [str(WINDOW[0]), str(WINDOW[1])],
        "sessions": len(days),
        "per_config": {},
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    timing: dict = {}

    for cfg in [c for c in args.configs.split(",") if c]:
        print(f"\n=== config {cfg} ===", flush=True)
        arms = {}
        for arm in ("v1_control", "v1", "v2"):
            a = run_arm(mdr, days, cfg, CONFIGS[cfg], arm, SOLVERS, canonical_qualify)
            arms[arm] = a
            print(f"[{time.time()-t0:7.1f}s] {cfg} {arm:10s} {a['seconds']:7.1f}s "
                  f"inv={a['invocations']} {a['stage3'].get('by_disposition')} "
                  f"stopped={a['stopped']}", flush=True)

        timing[cfg] = {k: arms[k]["seconds"] for k in arms}
        entry: dict = {
            "routing_guard": routing_guard(arms, cfg),          # raises rather than records
            "routing_engaged_all_arms": all(arms[k]["routing_engaged"] for k in arms),
            "census_rows": {k: arms[k]["census_rows"] for k in arms},
            "governed_census_check": governed_census_check(arms["v1_control"], cfg),
            "inertness": inertness_control(arms["v1_control"], arms["v1"]),
            "v2_stopped": arms["v2"]["stopped"],
        }
        if arms["v2"]["stopped"] is None:
            diff = differential(arms["v1"], arms["v2"])
            entry["differential"] = diff
            entry["registered_checks"] = registered_checks(diff, arms["v2"])
        entry["disposition"] = disposition_for(entry)
        report["per_config"][cfg] = entry

        # the bulk row-level differential goes to its own file - S3 custody, not Git
        with open(os.path.join(OUT_DIR, f"n3_rows_{cfg}.json"), "w") as fh:
            json.dump({"config": cfg,
                       "v1": arms["v1"]["rows"], "v2": arms["v2"]["rows"],
                       "trades_v1": arms["v1"].get("trades"),
                       "trades_v2": arms["v2"].get("trades"),
                       "instance_hashes_v1": arms["v1"]["instance_hashes"],
                       "instance_hashes_v2": arms["v2"]["instance_hashes"]},
                      fh, sort_keys=True, separators=(",", ":"))

        print(f"[{time.time()-t0:7.1f}s] {cfg} DISPOSITION = {entry['disposition']}", flush=True)
        if "registered_checks" in entry:
            for k, v in entry["registered_checks"].items():
                print(f"          {k:42s} {'PASS' if v['pass'] else 'FAIL'}", flush=True)

    dispositions = {c: report["per_config"][c]["disposition"] for c in report["per_config"]}
    report["dispositions"] = dispositions
    report["overall"] = ("N3_PASS" if set(dispositions.values()) == {"N3_PASS"}
                         else "N3_STOP")
    report["firewall_note"] = (
        "this report ranks nothing, recommends no solver, and derives no threshold from any "
        "economic statistic. A difference beyond the registered bound is a STOP in EITHER "
        "direction: v2 repairs numerical resolution and is not licensed to move the economics.")

    # Wall-clock NEVER enters the evidence payload. Excluding a field from a digest AFTER seeing
    # a mismatch is exactly the improvisation this program forbids, so the evidence set carries no
    # nondeterministic metadata at all and the determinism comparison needs NO exclusion rule.
    # Timings are written separately as telemetry and are not evidence.
    report["result_digest"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    report["result_digest_basis"] = (
        "sha256 over the canonical JSON of this entire report. The report contains NO wall-clock "
        "or other nondeterministic metadata, so NO field is excluded.")

    with open(os.path.join(OUT_DIR, "n3_report.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True, default=str)
    with open(os.path.join(OUT_DIR, "n3_timing_TELEMETRY_NOT_EVIDENCE.json"), "w") as fh:
        json.dump(timing, fh, indent=1, sort_keys=True)
    print(f"result_digest = {report['result_digest']}")

    print(f"\nN3 OVERALL = {report['overall']}   {dispositions}")
    print(f"[{time.time()-t0:7.1f}s] wrote {OUT_DIR}/n3_report.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
