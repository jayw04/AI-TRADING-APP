"""MR-002 Gate N1 — PRESERVATION against the governed v1 development replay.

Sealed authority: MR002_N1_ProspectiveRegistration_v1.0 §4.4
identity 7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af,
as adjudicated by MR002_N1_AdjudicationAddendum_v1.0 §3.

The owner ruled the authoritative v1 baseline is the GOVERNED DEVELOPMENT QUALIFICATION, and the
reconciliation established that it reproduces exactly (3891 PRIMARY / 4 FALLBACK) while being drawn
from a population 73% disjoint from the frozen bakeoff corpus. Preservation is therefore evaluated
HERE, on the replay, not on the bakeoff corpus.

Per config, three replays over the identical development window:

    v1        Stage-3 routed through the countersigned v1 seam (stage3_route)
    v2/P1     Stage-3 routed through the v2 certificate-driven method with B = PIQP_P1
    v2/P2     ... with B = PIQP_P2

and then, for each v2 replay against v1:

    Stage-3 level   invocation count · instance-hash SEQUENCE · accepted allocation · disposition
    economic level  run hash · NAV curve · daily returns · costs · borrow · exits · reductions ·
                    entries · session outcomes · zero reasons

⛔ THE FIREWALL (addendum §3). This run MUST NOT influence which Solver B is selected. Selection is
decided by the sealed rule on the frozen corpus, alone. Preservation asks only whether the
ALREADY-SELECTED method is behaviour-preserving. If preservation fails, the result is "N1 cannot
advance under that method" — never "choose the other B because its replay economics look better."
Choosing a solver on replay economics would be choosing on returns, which the program forbids
outright. This script therefore emits NO ranking and NO recommendation.

Development domain only. No sealed reader, no validation store, no OOS.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402
from app.research.mr002 import stage3_route as sr  # noqa: E402
from app.research.mr002.n1 import seam as v2seam  # noqa: E402

OUT_DIR = "/work/.mr002out/n1"
WINDOW = (date(2013, 1, 2), date(2019, 10, 2))
COUNTERSIGNATURE = "MR002_Stage3ExecutionCountersignature_v1.0"
B_CANDIDATES = ("PIQP_P1", "PIQP_P2")

GOVERNED = {
    "A": {"PRIMARY_QUALIFIED": 1426, "FALLBACK_QUALIFIED": 1, "invocations": 1427},
    "B": {"PRIMARY_QUALIFIED": 1532, "FALLBACK_QUALIFIED": 3, "invocations": 1535},
    "C": {"PRIMARY_QUALIFIED": 933, "FALLBACK_QUALIFIED": 0, "invocations": 933},
}


def _hash_instance(t, A_ub, b_ub, A_eq, b_eq, upper) -> str:
    h = hashlib.sha256()
    for arr in (t, A_ub, b_ub, A_eq, b_eq, upper):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def econ(acc) -> dict:
    """The economic fingerprint of one replay, in the fields the governed record reports."""
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


def observe(hashes: list, accepted: list):
    """Wrap whatever seam is installed, recording instance identity and accepted allocation.

    Observation only — the installed seam is called unchanged.
    """
    inner = jp._solve_qp

    def wrapper(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper):
        hashes.append(_hash_instance(targets, A_ub, b_ub, A_eq, b_eq, upper))
        z, info = inner(H_diag, targets, A_ub, b_ub, A_eq, b_eq, upper)
        accepted.append(np.asarray(z, dtype=float).copy())
        return z, info

    return inner, wrapper


def main() -> int:
    t0 = time.time()
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_coverage_signed_gap import SOLVERS, canonical_qualify
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(*WINDOW)
    print(f"[{time.time()-t0:7.1f}s] loaded {len(days)} development sessions", flush=True)

    report: dict = {"window": [str(WINDOW[0]), str(WINDOW[1])], "per_config": {},
                    "governed_recorded": GOVERNED}

    for cfg in ("A", "B", "C"):
        entry: dict = {}

        # ── v1 baseline ─────────────────────────────────────────────────────────────────────────
        census1: list = []
        h1: list[str] = []
        z1: list = []
        with sr.routed(census1, countersignature=COUNTERSIGNATURE):
            inner, wrapper = observe(h1, z1)
            jp._solve_qp = wrapper
            try:
                acc1 = run_config(days, CONFIGS[cfg])
            finally:
                jp._solve_qp = inner
        s1 = sr.census_summary(census1)
        e1 = econ(acc1)
        entry["v1"] = {"stage3": s1, "econ": e1,
                       "matches_governed": (
                           s1["by_disposition"].get("PRIMARY_QUALIFIED", 0)
                           == GOVERNED[cfg]["PRIMARY_QUALIFIED"]
                           and s1["by_disposition"].get("FALLBACK_QUALIFIED", 0)
                           == GOVERNED[cfg]["FALLBACK_QUALIFIED"])}
        print(f"[{time.time()-t0:7.1f}s] {cfg} v1: {s1['by_disposition']} "
              f"run_hash={e1['run_hash'][:16]} matches_governed={entry['v1']['matches_governed']}",
              flush=True)

        # ── v2, per candidate ───────────────────────────────────────────────────────────────────
        for cand in B_CANDIDATES:
            census2: list = []
            h2: list[str] = []
            z2: list = []
            stopped = None
            with v2seam.routed_v2(census2, candidate=cand, solvers=SOLVERS,
                                  certify_fn=canonical_qualify):
                inner, wrapper = observe(h2, z2)
                jp._solve_qp = wrapper
                try:
                    acc2 = run_config(days, CONFIGS[cfg])
                except Exception as exc:  # noqa: BLE001 — a stop is a RESULT, recorded not hidden
                    stopped = f"{type(exc).__name__}: {str(exc)[:200]}"
                    acc2 = None
                finally:
                    jp._solve_qp = inner

            s2 = v2seam.census_summary(census2)
            if acc2 is None:
                entry[cand] = {"stage3": s2, "stopped": stopped, "preserved": False}
                print(f"[{time.time()-t0:7.1f}s] {cfg} v2/{cand}: STOPPED {stopped}", flush=True)
                continue

            e2 = econ(acc2)
            seq_same = h1 == h2
            n_common = min(len(z1), len(z2))
            alloc_exact = sum(1 for k in range(n_common) if z1[k].tobytes() == z2[k].tobytes())
            alloc_diff = [
                {"k": k, "max_abs": float(np.max(np.abs(z1[k] - z2[k]))),
                 "l2": float(np.linalg.norm(z1[k] - z2[k]))}
                for k in range(n_common)
                if z1[k].shape == z2[k].shape and z1[k].tobytes() != z2[k].tobytes()
            ]
            econ_same = {k: (e1[k] == e2[k]) for k in e1}
            entry[cand] = {
                "stage3": s2,
                "econ": e2,
                "instance_sequence_identical": seq_same,
                "invocations_v1": len(h1),
                "invocations_v2": len(h2),
                "accepted_allocation_byte_identical": alloc_exact,
                "accepted_allocation_differing": len(alloc_diff),
                "allocation_differences": alloc_diff[:25],
                "max_allocation_difference": max((d["l2"] for d in alloc_diff), default=0.0),
                "economic_fields_identical": econ_same,
                "economic_differential_EXACT": all(econ_same.values()),
                "preserved": (seq_same and len(alloc_diff) == 0 and all(econ_same.values())),
            }
            print(f"[{time.time()-t0:7.1f}s] {cfg} v2/{cand}: {s2['by_disposition']} "
                  f"seq_same={seq_same} alloc_identical={alloc_exact}/{n_common} "
                  f"econ_EXACT={entry[cand]['economic_differential_EXACT']} "
                  f"run_hash={e2['run_hash'][:16]}", flush=True)
            if not entry[cand]["economic_differential_EXACT"]:
                bad = [k for k, v in econ_same.items() if not v]
                print(f"          economic fields DIFFERING: {bad}", flush=True)

        report["per_config"][cfg] = entry

    # ── roll-up, with NO ranking (firewall) ─────────────────────────────────────────────────────
    rollup = {}
    for cand in B_CANDIDATES:
        per = [report["per_config"][c].get(cand, {}) for c in ("A", "B", "C")]
        rollup[cand] = {
            "preserved_all_configs": all(p.get("preserved") for p in per),
            "configs_preserved": [c for c in ("A", "B", "C")
                                  if report["per_config"][c].get(cand, {}).get("preserved")],
            "any_stop": any(p.get("stopped") for p in per),
        }
    report["preservation"] = rollup
    report["firewall_note"] = (
        "this report ranks nothing and recommends nothing; Solver B is selected by the sealed "
        "selection rule on the frozen corpus alone. Preservation only asks whether the selected "
        "method is behaviour-preserving.")

    print("\nPRESERVATION ROLL-UP")
    for cand, r in rollup.items():
        print(f"  {cand:10s} preserved_all_configs={r['preserved_all_configs']} "
              f"configs={r['configs_preserved']} any_stop={r['any_stop']}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "n1_preservation.json"), "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True, default=str)
    print(f"\n[{time.time()-t0:7.1f}s] wrote preservation report", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
