"""MR-002 Gate N1 — capture the immutable 3,895-instance Stage-3 development corpus.

Authorized by MR002_N1_ProspectiveRegistration_v1.0, SEALED identity
7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af (§5.1).

Replays configs A, B, C over the development window 2013-01-02 .. 2019-10-02 with `_solve_qp`
replaced by a capture hook, verifies the registered corpus hash, and persists the instances so
candidate scoring never has to replay again.

⛔ A corpus-hash mismatch ABORTS. Every prior solver report was scored on the registered problem
set; an N1 census computed on a different one would be meaningless.

Development domain only. Opens no sealed reader, no validation store, no OOS.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from datetime import date

import numpy as np

sys.path.insert(0, "/work/apps/backend")

import app.research.mr002.joint_portfolio as jp  # noqa: E402

REGISTERED_CORPUS_HASH = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"
WINDOW = (date(2013, 1, 2), date(2019, 10, 2))
OUT_DIR = "/work/.mr002out/n1"

# ── THE CAPTURE DEVICE IS IMPORTED, NEVER RE-DERIVED ─────────────────────────────────────────────
# The registered corpus hash 1d23193... was produced by ONE specific capture device: the one in
# `mr002_solver_intersection`. Its accepted point feeds forward into the next session's state, so a
# different device produces a DIFFERENT downstream instance sequence and a different hash. Writing a
# fresh capture hook here — even an apparently equivalent one routed through the frozen `_solve_qp`
# cascade — would diverge wherever the two disagree (raw has 70 standalone nonqualifications) and
# would additionally RAISE where the registered device falls back to its LP diagnostic.
#
# This is the same rule the Clarabel path in that module records the hard way: re-deriving a
# validated numeric path is how you manufacture a false verdict. So: import it.
from scripts.mr002_solver_intersection import CORPUS, capture_solver  # noqa: E402


def main() -> int:
    t0 = time.time()
    jp._solve_qp = capture_solver

    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_development_run import run_config

    ds = FrozenDataset("/work/apps/backend/data/mr002_research.duckdb")
    days = ds.day_inputs(*WINDOW)
    print(f"[{time.time()-t0:7.1f}s] loaded {len(days)} development sessions", flush=True)

    for name in ("A", "B", "C"):
        n_before = len(CORPUS)
        run_config(days, CONFIGS[name])
        print(f"[{time.time()-t0:7.1f}s] config {name}: +{len(CORPUS)-n_before} instances "
              f"(total {len(CORPUS)})", flush=True)

    corpus_hash = hashlib.sha256("|".join(i["hash"] for i in CORPUS).encode()).hexdigest()
    print(f"\ncaptured   {len(CORPUS)} instances")
    print(f"hash       {corpus_hash}")
    print(f"registered {REGISTERED_CORPUS_HASH}")

    if corpus_hash != REGISTERED_CORPUS_HASH:
        print("\nABORT: corpus hash MISMATCH — N1 may not be scored on a different problem set.",
              file=sys.stderr)
        return 1
    print("corpus reproduced EXACTLY", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    payload: dict[str, np.ndarray] = {"corpus_hash": np.array(corpus_hash)}
    for i, inst in enumerate(CORPUS):
        for k in ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper"):
            payload[f"{i}_{k}"] = inst[k]
        payload[f"{i}_hash"] = np.array(inst["hash"])
    payload["n_instances"] = np.array(len(CORPUS))
    out = os.path.join(OUT_DIR, "corpus.npz")
    np.savez_compressed(out, **payload)

    ns = [len(i["t"]) for i in CORPUS]
    rows = [i["A_ub"].shape[0] for i in CORPUS]
    print(f"\nwrote      {out}  ({os.path.getsize(out)/1e6:.1f} MB)")
    print(f"n          min={min(ns)} med={int(np.median(ns))} max={max(ns)}")
    print(f"A_ub rows  min={min(rows)} med={int(np.median(rows))} max={max(rows)}")
    print(f"elapsed    {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
