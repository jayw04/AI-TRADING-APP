"""MR-002 validation/OOS evaluator — governing-identity loader (Increment 1 v1.1).

Fail-closed. Beyond content-hash pinning, it strictly parses each artifact (duplicate JSON keys
rejected; bool never accepted where an int is required) and cross-validates the full identity chain:
prereg <-> ledger <-> resolution all bind the same N=5 countersigned ledger and the same prereg. The
governing N originates from the ledger bytes — there is NO independent fallback constant. Any failure
raises RefusedIdentity(REFUSED_CODE_OR_DATA_IDENTITY) before any evaluator input is accepted.

`_validate_semantics(prereg, ledger, resolution)` is factored out so tests can exercise the semantic
checks on tampered in-memory dicts (not merely the outer file-hash gate).
"""

from __future__ import annotations

import hashlib
import json
import os

PREREG = "MR002_ValidationOOS_Preregistration_v1.0.3.json"
LEDGER = "MR002_DSR_TrialLedger_v1.0.json"
RESOLUTION = "MR002_DSR_Resolution_v1.0.json"
PREREG_SHA = "b840e01cf8f4dc2cf40f43f4fc0f9f70e53712e5f78b3a73346014bbcf2ef468"
LEDGER_SHA = "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b"
RESOLUTION_SHA = "30b812f179128cbb65593de25ee3039916e928a72a6d5d4de2c8051ff83f90a0"

EXPECTED_TRIAL_IDS = ("MR002-A", "MR002-B", "MR002-C", "RNG-001", "RNG-EntryLogic")
PREREG_NAME_IN_RESOLUTION = "MR002_ValidationOOS_Preregistration_v1.0.3"

DEFAULT_IDENTITIES = {PREREG: PREREG_SHA, LEDGER: LEDGER_SHA, RESOLUTION: RESOLUTION_SHA}


class RefusedIdentity(Exception):
    """REFUSED_CODE_OR_DATA_IDENTITY — a governing artifact failed identity/consistency validation."""


def _refuse(detail: str):
    raise RefusedIdentity(f"REFUSED_CODE_OR_DATA_IDENTITY:{detail}")


def _no_dup_keys(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            _refuse(f"DUPLICATE_JSON_KEY:{k}")
        d[k] = v
    return d


def _loads_strict(raw: bytes):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_dup_keys)


def _require_int(value, where: str) -> int:
    # bool is an int subclass — reject it explicitly where an integer is required.
    if isinstance(value, bool) or not isinstance(value, int):
        _refuse(f"NON_INT:{where}:{value!r}")
    return value


def _require_str(value, where: str) -> str:
    if not isinstance(value, str):
        _refuse(f"NON_STR:{where}:{value!r}")
    return value


# ── semantic cross-validation (testable on tampered in-memory dicts) ──────────────────────────────
def _validate_semantics(prereg: dict, ledger: dict, resolution: dict) -> int:
    # preregistration
    if _require_str(prereg.get("record_type"), "prereg.record_type") != "MR002_VALIDATIONOOS_PREREGISTRATION":
        _refuse("PREREG_RECORD_TYPE")
    if _require_str(prereg.get("version"), "prereg.version") != "1.0.3":
        _refuse(f"PREREG_VERSION:{prereg.get('version')}")
    dsr = prereg.get("dsr", {})
    if dsr.get("status") != "READY":
        _refuse(f"DSR_NOT_READY:{dsr.get('status')}")
    n_prereg = _require_int(dsr.get("trials_N"), "prereg.dsr.trials_N")
    if dsr.get("trial_ledger_sha256") != LEDGER_SHA:
        _refuse("PREREG_LEDGER_HASH_UNBOUND")
    va = prereg.get("sequencing", {}).get("validation_authorization")
    if va is not False:                                  # strict: rejects 0, None, "false", 1, True
        _refuse(f"VALIDATION_AUTH_NOT_FALSE:{va!r}")

    # ledger
    if _require_str(ledger.get("record_type"), "ledger.record_type") != "MR002_DSR_TRIAL_LEDGER":
        _refuse("LEDGER_RECORD_TYPE")
    if ledger.get("decision") != "TRIAL_LEDGER_COUNTERSIGNED":
        _refuse(f"LEDGER_NOT_COUNTERSIGNED:{ledger.get('decision')}")
    if ledger.get("record_status") != "IMMUTABLE":
        _refuse(f"LEDGER_NOT_IMMUTABLE:{ledger.get('record_status')}")
    n_ledger = _require_int(ledger.get("trials_N"), "ledger.trials_N")
    ids = ledger.get("included_trials_ids")
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
        _refuse("LEDGER_IDS_TYPE")
    if len(ids) != len(set(ids)):
        _refuse("LEDGER_DUPLICATE_TRIAL_IDS")
    if tuple(ids) != EXPECTED_TRIAL_IDS:
        _refuse(f"LEDGER_ID_SET:{ids}")
    detail_ids = [t.get("trial_id") for t in ledger.get("included_trials", [])]
    if len(detail_ids) != len(set(detail_ids)) or set(detail_ids) != set(EXPECTED_TRIAL_IDS):
        _refuse(f"LEDGER_DETAIL_IDS:{detail_ids}")
    if n_ledger != len(set(ids)):
        _refuse(f"LEDGER_N_NEQ_UNIQUE_IDS:{n_ledger}!={len(set(ids))}")

    # resolution
    if _require_str(resolution.get("record_type"), "resolution.record_type") != "MR002_DSR_RESOLUTION":
        _refuse("RESOLUTION_RECORD_TYPE")
    ctl = resolution.get("countersigned_trial_ledger", {})
    if ctl.get("sha256") != LEDGER_SHA:
        _refuse("RESOLUTION_LEDGER_HASH_UNBOUND")
    n_res = _require_int(ctl.get("trials_N"), "resolution.ctl.trials_N")
    if tuple(ctl.get("included", [])) != EXPECTED_TRIAL_IDS:
        _refuse(f"RESOLUTION_LEDGER_ID_SET:{ctl.get('included')}")
    pu = resolution.get("prereg_update", {})
    if pu.get("to_sha256") != PREREG_SHA:
        _refuse("RESOLUTION_PREREG_HASH_UNBOUND")
    if pu.get("to") != PREREG_NAME_IN_RESOLUTION:
        _refuse(f"RESOLUTION_PREREG_NAME:{pu.get('to')}")

    # chain coherence: all three agree on N, and N == 5
    if not (n_prereg == n_ledger == n_res):
        _refuse(f"N_CHAIN_INCONSISTENT:prereg={n_prereg},ledger={n_ledger},res={n_res}")
    if n_ledger != 5:
        _refuse(f"N_NOT_5:{n_ledger}")
    return n_ledger


def _check_file(gov_dir: str, name: str, want_sha: str) -> bytes:
    if os.path.basename(name) != name:
        _refuse(f"NON_BASENAME:{name}")
    p = os.path.join(gov_dir, name)
    if os.path.islink(p):
        _refuse(f"SYMLINK:{name}")
    if not os.path.isfile(p):
        _refuse(f"MISSING:{name}")
    if os.path.basename(os.path.realpath(p)) != name:
        _refuse(f"PATH_TRAVERSAL:{name}")
    raw = open(p, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if got != want_sha:
        _refuse(f"HASH_MISMATCH:{name}:{got}")
    return raw


def load_governing_identity(gov_dir: str, *, expected: dict | None = None) -> dict:
    """Validate the three governing artifacts in `gov_dir` (strict parse + content hash + full
    semantic cross-binding) and return the bound governing values. The returned `dsr_trials_N` is
    sourced from the ledger bytes; there is no code-constant fallback."""
    expected = expected or DEFAULT_IDENTITIES
    prereg = _loads_strict(_check_file(gov_dir, PREREG, expected[PREREG]))
    ledger = _loads_strict(_check_file(gov_dir, LEDGER, expected[LEDGER]))
    resolution = _loads_strict(_check_file(gov_dir, RESOLUTION, expected[RESOLUTION]))
    n = _validate_semantics(prereg, ledger, resolution)

    # bind the code registry to the loaded gates_frozen (fail-closed on divergence)
    from mr002_valoos_registry import cross_validate_registry
    cross_validate_registry(prereg.get("gates_frozen", {}))

    return {
        "prereg_sha256": expected[PREREG], "ledger_sha256": expected[LEDGER],
        "resolution_sha256": expected[RESOLUTION],
        "dsr_trials_N": n,                               # sourced from the ledger
        "dsr_status": "READY", "validation_authorization": False,
        "ledger_included_trials": list(EXPECTED_TRIAL_IDS),
        "gates_frozen": prereg.get("gates_frozen", {}),
    }
