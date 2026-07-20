"""MR-002 validation/OOS evaluator — governing-identity loader (Workstream B, Increment 1).

Fail-closed. Reads and validates the three governing artifacts and returns the LEDGER-BOUND DSR N.
It contains NO independent fallback trial-count constant: the governing N originates from the bound
ledger/preregistration bytes. Any mismatch raises RefusedIdentity(REFUSED_CODE_OR_DATA_IDENTITY)
BEFORE any evaluator input is accepted.
"""

from __future__ import annotations

import hashlib
import json
import os

# Governing artifact IDENTITIES (the binding — analogous to the run-4 tool's pinned hashes). These
# are the artifact hashes, NOT the trial count. N is read FROM the artifacts and cross-checked.
PREREG = "MR002_ValidationOOS_Preregistration_v1.0.3.json"
LEDGER = "MR002_DSR_TrialLedger_v1.0.json"
RESOLUTION = "MR002_DSR_Resolution_v1.0.json"
PREREG_SHA = "b840e01cf8f4dc2cf40f43f4fc0f9f70e53712e5f78b3a73346014bbcf2ef468"
LEDGER_SHA = "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b"
RESOLUTION_SHA = "30b812f179128cbb65593de25ee3039916e928a72a6d5d4de2c8051ff83f90a0"


class RefusedIdentity(Exception):
    """REFUSED_CODE_OR_DATA_IDENTITY — a governing artifact failed identity/consistency validation."""


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_governing_identity(gov_dir: str) -> dict:
    """Validate the three governing artifacts in `gov_dir` and return the bound governing values.

    Refuses (REFUSED_CODE_OR_DATA_IDENTITY) unless ALL hold:
      prereg/ledger/resolution sha256 == the pinned identities;
      prereg.dsr.status == READY; prereg.dsr.trials_N == 5; prereg.dsr.trial_ledger_sha256 == LEDGER_SHA;
      ledger.trials_N == 5; ledger.decision == TRIAL_LEDGER_COUNTERSIGNED; ledger.record_status IMMUTABLE;
      prereg.sequencing.validation_authorization == false.
    The returned trials_N comes FROM the ledger bytes (not a constant); the '== 5' below is an
    assertion, not the source of the value.
    """
    paths = {PREREG: PREREG_SHA, LEDGER: LEDGER_SHA, RESOLUTION: RESOLUTION_SHA}
    for name, want in paths.items():
        p = os.path.join(gov_dir, name)
        if not os.path.isfile(p) or os.path.islink(p):
            raise RefusedIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:MISSING_OR_SYMLINK:{name}")
        got = _sha256(p)
        if got != want:
            raise RefusedIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:HASH_MISMATCH:{name}:{got}")

    prereg = json.load(open(os.path.join(gov_dir, PREREG), encoding="utf-8"))
    ledger = json.load(open(os.path.join(gov_dir, LEDGER), encoding="utf-8"))

    dsr = prereg.get("dsr", {})
    if dsr.get("status") != "READY":
        raise RefusedIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:DSR_NOT_READY:{dsr.get('status')}")
    if dsr.get("trial_ledger_sha256") != LEDGER_SHA:
        raise RefusedIdentity("REFUSED_CODE_OR_DATA_IDENTITY:PREREG_LEDGER_HASH_UNBOUND")
    # governing N originates from the ledger bytes:
    n_ledger = ledger.get("trials_N")
    n_prereg = dsr.get("trials_N")
    if ledger.get("decision") != "TRIAL_LEDGER_COUNTERSIGNED" or ledger.get("record_status") != "IMMUTABLE":
        raise RefusedIdentity("REFUSED_CODE_OR_DATA_IDENTITY:LEDGER_NOT_COUNTERSIGNED")
    if n_ledger != n_prereg:
        raise RefusedIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:N_INCONSISTENT:{n_prereg}!={n_ledger}")
    if n_ledger != 5:                                   # assertion on the loaded value (not a source)
        raise RefusedIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:N_NOT_5:{n_ledger}")
    if prereg.get("sequencing", {}).get("validation_authorization") is not False:
        raise RefusedIdentity("REFUSED_CODE_OR_DATA_IDENTITY:VALIDATION_AUTH_NOT_FALSE")

    return {
        "prereg_sha256": PREREG_SHA, "ledger_sha256": LEDGER_SHA, "resolution_sha256": RESOLUTION_SHA,
        "dsr_trials_N": n_ledger,                       # sourced from the ledger
        "dsr_status": "READY",
        "validation_authorization": False,
        "ledger_included_trials": ledger.get("included_trials_ids"),
    }
