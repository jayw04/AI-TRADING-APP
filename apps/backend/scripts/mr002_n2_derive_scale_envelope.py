"""MR-002 Gate N2 — derive the registered Stage-3 target-scale envelope MECHANICALLY.

Owner ruling 2026-08-19: "Do not simply type 0.0171 because that is today's observed maximum."
The envelope must be reproducible from the frozen development population and bound by hash, so that
one discretionary generator choice is not replaced by another.

Authoritative source: the registered 3,895-instance Stage-3 development corpus,
corpus_hash 1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b. The hash is verified
before anything is derived; a mismatch aborts.

Emits T_MAX_REGISTERED and T_MIN_REGISTERED together with the derivation, so the amendment can bind
values that anyone can reproduce rather than values someone chose.

Development domain only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, "/work/apps/backend")

CORPUS_NPZ = "/work/.mr002out/n1/corpus.npz"
OUT = "/work/.mr002out/n2/n2_scale_envelope.json"
REGISTERED_CORPUS_HASH = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"


def main() -> int:
    d = np.load(CORPUS_NPZ, allow_pickle=False)
    got = str(d["corpus_hash"])
    if got != REGISTERED_CORPUS_HASH:
        raise SystemExit(f"ABORT: corpus hash {got} != registered {REGISTERED_CORPUS_HASH}")
    n_inst = int(d["n_instances"])

    t_max_per = np.empty(n_inst)
    t_min_per = np.empty(n_inst)
    kappa_per = np.empty(n_inst)
    upper_equals_t = 0
    for i in range(n_inst):
        t = np.asarray(d[f"{i}_t"], dtype=np.float64)
        t_max_per[i] = t.max()
        t_min_per[i] = t.min()
        kappa_per[i] = t.max() / t.min()
        upper_equals_t += int(np.array_equal(t, np.asarray(d[f"{i}_upper"], dtype=np.float64)))

    T_MAX = float(t_max_per.max())
    T_MIN = float(t_min_per.min())

    rec = {
        "record_type": "MR002_N2_SCALE_ENVELOPE_DERIVATION",
        "authoritative_source": {
            "artifact": "registered Stage-3 development corpus",
            "corpus_hash": REGISTERED_CORPUS_HASH,
            "hash_verified_before_derivation": True,
            "instances": n_inst,
        },
        "derivation": {
            "T_MAX_REGISTERED": "max over all registered instances of max(t)",
            "T_MIN_REGISTERED": "min over all registered instances of min(t)",
            "kappa_definition": "kappa(H) = max_i(2/t_i) / min_i(2/t_i) = max(t)/min(t)",
        },
        "T_MAX_REGISTERED": T_MAX,
        "T_MIN_REGISTERED": T_MIN,
        "T_MAX_REGISTERED_hex": float.hex(T_MAX),
        "T_MIN_REGISTERED_hex": float.hex(T_MIN),
        "observed": {
            "t_max_over_instances": {"min": float(t_max_per.min()),
                                     "median": float(np.median(t_max_per)),
                                     "max": T_MAX},
            "t_min_over_instances": {"min": T_MIN,
                                     "median": float(np.median(t_min_per)),
                                     "max": float(t_min_per.max())},
            "kappa_per_instance": {"min": float(kappa_per.min()),
                                   "median": float(np.median(kappa_per)),
                                   "max": float(kappa_per.max())},
            "upper_equals_t_instances": upper_equals_t,
        },
        "consequence_for_A1": {
            "kappa_reachable_holding_both_registered_bounds": T_MAX / T_MIN,
            "preregistered_A1_kappa_ceiling": 1e10,
            "note": ("holding BOTH registered bounds reaches only max(t)/min(t) above, which is "
                     "below the preregistered 1e10 ceiling. Per the owner ruling the ABSOLUTE UPPER "
                     "scale is the economically meaningful invariant; synthetic t_min may extend "
                     "BELOW the historical minimum solely to reach the preregistered kappa range, "
                     "with kappa still bounded by 1e10. Freezing t_min >= the development minimum "
                     "would destroy the stress the axis exists to perform."),
        },
    }
    rec["record_identity_sha256"] = hashlib.sha256(
        (json.dumps(rec, sort_keys=True, indent=1) + "\n").encode("ascii")).hexdigest()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(rec, fh, indent=1, sort_keys=True)

    print(json.dumps({k: rec[k] for k in (
        "T_MAX_REGISTERED", "T_MIN_REGISTERED", "T_MAX_REGISTERED_hex", "T_MIN_REGISTERED_hex",
        "record_identity_sha256")}, indent=1))
    print("\nobserved:", json.dumps(rec["observed"], indent=1))
    print("\nkappa reachable holding BOTH registered bounds:",
          f"{rec['consequence_for_A1']['kappa_reachable_holding_both_registered_bounds']:.4e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
