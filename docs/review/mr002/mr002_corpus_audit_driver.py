"""MR-002 corpus reconstruction audit driver — Amended Authorization A (2026-07-18).

Reconstructs the registered 3,895-instance development corpus using the FROZEN capture device
(worktree checkout of 3a37545 — byte-identical mr002_solver_intersection.py, capture_solver,
solve_sqrt, solve_tscaled, run configuration, trajectory logic). Solver calls happen ONLY inside
the frozen capture device, only to advance the historical path-dependent trajectory; outputs are
not adjudicated, no new dispositions are recorded, no solver comparison is made.

Phase A1: materialize inputs, compute ordered per-instance hashes + aggregate corpus hash.
          HARD GATE: instance_count == 3895 AND corpus_hash == REGISTERED. On mismatch: preserve
          the manifest + failure evidence and STOP — no statistics.
Phase A2: structural statistics from the input arrays only (exact float64 comparisons).

Usage: python mr002_corpus_audit_driver.py <frozen_worktree> <dataset_duckdb> <out_dir>
"""

import hashlib
import json
import os
import platform
import sys
from datetime import date

import numpy as np

WORKTREE, DATASET, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, os.path.join(WORKTREE, "apps", "backend"))

EXPECTED_N = 3895
REGISTERED = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    os.makedirs(OUT, exist_ok=True)

    frozen_hashes = {rel: sha_file(os.path.join(WORKTREE, rel)) for rel in (
        "apps/backend/scripts/mr002_solver_intersection.py",
        "apps/backend/scripts/mr002_coverage_signed_gap.py",
        "apps/backend/scripts/mr002_piqp.py",
        "apps/backend/scripts/mr002_characterize_native_qp.py",
        "apps/backend/scripts/mr002_development_run.py",
        "apps/backend/app/research/mr002/joint_portfolio.py",
        "apps/backend/app/research/mr002/dataset.py",
        "apps/backend/app/research/mr002/runner.py",
    )}
    dataset_sha = sha_file(DATASET)

    import importlib.metadata as md
    env_record = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {p: md.version(p) for p in
                     ("numpy", "scipy", "quadprog", "duckdb", "piqp", "mpmath",
                      "clarabel", "highspy")},
        "cmdline": list(sys.argv),
        "frozen_worktree_commit": "3a37545e2dcf201542a5fca6fca29bade828f9c0",
        "frozen_file_sha256": frozen_hashes,
        "dataset_sha256": dataset_sha,
        "blas": json.loads(json.dumps(np.show_config(mode="dicts"), default=str))
        .get("Build Dependencies", {}).get("blas", {}),
    }
    print(json.dumps(env_record, indent=1), flush=True)

    # ── Phase A1 — reconstruction with the FROZEN device ───────────────────────────────────────
    import app.research.mr002.joint_portfolio as jp
    import scripts.mr002_solver_intersection as si
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    jp._solve_qp = si.capture_solver          # the registered capture-the-reference device
    ds = FrozenDataset(DATASET)
    days = ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2))
    print("PHASE A1 — reconstruction with the frozen capture device", flush=True)
    for name in ("A", "B", "C"):
        print(f"  config {name} ...", flush=True)
        run_config(days, CONFIGS[name])

    n_inst = len(si.CORPUS)
    ordered_hashes = [inst["hash"] for inst in si.CORPUS]
    corpus_hash = hashlib.sha256("|".join(ordered_hashes).encode()).hexdigest()
    manifest = {"record_type": "MR002_CORPUS_RECONSTRUCTION_MANIFEST", "version": "1.0",
                "instance_count": n_inst, "corpus_hash": corpus_hash,
                "registered_corpus_hash": REGISTERED,
                "ordered_instance_hashes": ordered_hashes,
                "environment": env_record}
    man_path = os.path.join(OUT, "MR002_CorpusReconstruction_Manifest_v1.0.json")
    with open(man_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=1)
        fh.write("\n")
    print(f"  instances {n_inst}  corpus_hash {corpus_hash}", flush=True)

    if n_inst != EXPECTED_N or corpus_hash != REGISTERED:
        print("PHASE A1 GATE: FAIL — hash/count mismatch. Statistics PROHIBITED. "
              "Manifest preserved for identity-failure diagnosis.", file=sys.stderr)
        return 1
    print("PHASE A1 GATE: PASS — corpus reproduced EXACTLY", flush=True)

    # ── Phase A2 — structural statistics (input arrays only, exact float64) ────────────────────
    rows = []
    agg = {"all_upper_eq_t": 0, "any_upper_ne_t": 0, "any_upper_lt_t": 0, "any_upper_gt_t": 0,
           "rows_with_zero_bound_discrepancy": 0}
    ratios_all = []
    for i, inst in enumerate(si.CORPUS):
        t = np.asarray(inst["t"], float)
        upper = np.asarray(inst["upper"], float)
        s = np.sqrt(t)
        frozen_bound = s                       # the bound frozen solve_sqrt passes
        correct_bound = upper / s              # the correct transform
        eq = upper == t                        # exact float64
        lt, gt = upper < t, upper > t
        disc = np.abs(frozen_bound - correct_bound)
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = np.where(correct_bound != 0.0, disc / np.abs(correct_bound), np.inf)
            ratio = np.where(t != 0.0, upper / t, np.nan)
        finite_pos = ratio[np.isfinite(ratio) & (ratio > 0)]
        ratios_all.append(finite_pos)
        n_mismatch_coords = int(np.count_nonzero(frozen_bound != correct_bound))
        all_eq = bool(eq.all())
        rows.append({
            "row": i, "content_hash": inst["hash"], "n": int(len(t)),
            "coords_upper_lt_t": int(lt.sum()), "coords_upper_eq_t": int(eq.sum()),
            "coords_upper_gt_t": int(gt.sum()),
            "transformed_bound_mismatch_coords": n_mismatch_coords,
            "max_abs_bound_discrepancy": float(disc.max()) if len(t) else 0.0,
            "max_rel_bound_discrepancy": float(np.nanmax(rel)) if len(t) else 0.0,
            "classification": "MASKED_BY_IDENTITY" if all_eq else "MISMATCH_PRESENT",
            "trajectory_risk": None if all_eq else "POTENTIALLY_TRAJECTORY_RELEVANT",
        })
        if all_eq:
            agg["all_upper_eq_t"] += 1
        else:
            agg["any_upper_ne_t"] += 1
        if lt.any():
            agg["any_upper_lt_t"] += 1
        if gt.any():
            agg["any_upper_gt_t"] += 1
        if n_mismatch_coords == 0:
            agg["rows_with_zero_bound_discrepancy"] += 1

    allr = np.concatenate(ratios_all) if ratios_all else np.asarray([])
    quant = {q: float(np.quantile(allr, q)) for q in (0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0)} \
        if allr.size else {}

    artifact = {
        "record_type": "MR002_CORPUS_STRUCTURAL_AUDIT",
        "version": "1.0",
        "record_status": "IMMUTABLE",
        "authorization": "Amended Authorization A (2026-07-18): frozen-device reconstruction + "
                         "structural statistics after exact corpus-hash gate",
        "phase_a1": {"instance_count": n_inst, "corpus_hash": corpus_hash,
                     "registered_corpus_hash": REGISTERED, "gate": "PASS",
                     "manifest_file": "MR002_CorpusReconstruction_Manifest_v1.0.json"},
        "environment": env_record,
        "aggregate": {
            "instances": n_inst,
            "instances_all_coords_upper_eq_t (MASKED_BY_IDENTITY)": agg["all_upper_eq_t"],
            "instances_any_coord_upper_ne_t (MISMATCH_PRESENT)": agg["any_upper_ne_t"],
            "instances_any_coord_upper_lt_t": agg["any_upper_lt_t"],
            "instances_any_coord_upper_gt_t": agg["any_upper_gt_t"],
            "instances_zero_transformed_bound_discrepancy": agg["rows_with_zero_bound_discrepancy"],
            "upper_over_t_quantiles_finite_positive": quant,
            "upper_over_t_min": quant.get(0.0), "upper_over_t_max": quant.get(1.0),
        },
        "rows": rows,
        "trajectory_effect_statement": (
            "A mismatched transformed bound proves the historical SQRT formulation differed from "
            "the intended model. Structural input audit alone cannot establish whether that "
            "difference altered a solver-selected point or the path-dependent downstream "
            "trajectory. Rows labeled MISMATCH_PRESENT are POTENTIALLY_TRAJECTORY_RELEVANT; "
            "whether any historical accepted solution, subsequent state, or later row was changed "
            "is TRAJECTORY_EFFECT_UNDETERMINED without numerical execution, which this audit is "
            "prohibited from performing. Conversely, rows labeled MASKED_BY_IDENTITY with zero "
            "transformed-bound discrepancy could not have been affected by the defect."),
    }
    art_path = os.path.join(OUT, "MR002_CorpusStructuralAudit_v1.0.json")
    blob = json.dumps(artifact, indent=1)
    with open(art_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(blob + "\n")
    print("PHASE A2 — statistics complete", flush=True)
    print(json.dumps(artifact["aggregate"], indent=1))
    print(f"wrote {art_path} sha256 {hashlib.sha256((blob + chr(10)).encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
