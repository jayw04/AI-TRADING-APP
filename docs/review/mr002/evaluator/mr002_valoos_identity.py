"""MR-002 validation/OOS evaluator — governing-identity loader (Increment 1 v1.2).

Fail-closed. Beyond content-hash pinning, it strictly parses each artifact (duplicate JSON keys
rejected; bool never accepted where an int is required) and cross-validates the full identity chain:

  prereg (v1.0.4)  <->  ledger (N=5, countersigned)  <->  correction (v1.0.3 -> v1.0.4)
                                                     <->  dispersion resolution (N=5, A/B/C sigma)

The governing prereg is the bootstrap-corrected v1.0.4 (Ruling 1, 2026-07-20). The CorrectionRecord
binds v1.0.3 -> v1.0.4 and affirms no economic rule changed; the DSR DispersionResolution binds the
dispersion estimator (Ruling 2). The governing N originates from the ledger bytes — there is NO
independent fallback constant. The prereg's frozen stationary-bootstrap spec is cross-checked against
the code's bootstrap constants. Any failure raises RefusedIdentity(REFUSED_CODE_OR_DATA_IDENTITY)
before any evaluator input is accepted.

`_validate_semantics(prereg, ledger, correction, dispersion)` is factored out so tests can exercise
the semantic checks on tampered in-memory dicts (not merely the outer file-hash gate).

The production OOS DSR gate additionally requires the countersigned validation-stage dispersion
artifact via `load_validation_dispersion_artifact` — absent/identity-mismatch fail-closes with
REFUSED_CODE_OR_DATA_IDENTITY (in synthetic qualification the artifact does not yet exist).
"""

from __future__ import annotations

import hashlib
import json
import os

PREREG = "MR002_ValidationOOS_Preregistration_v1.0.4.json"
LEDGER = "MR002_DSR_TrialLedger_v1.0.json"
CORRECTION = "MR002_ValidationOOS_CorrectionRecord_v1.0.4.json"
DISPERSION_RESOLUTION = "MR002_DSR_DispersionResolution_v1.0.json"

PREREG_SHA = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"
PREREG_V103_SHA = "b840e01cf8f4dc2cf40f43f4fc0f9f70e53712e5f78b3a73346014bbcf2ef468"
LEDGER_SHA = "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b"
CORRECTION_SHA = "33fbb78ce7679aaab2afc514cb0164f09e3331f87b8422b4827a0d2587c91b91"
DISPERSION_RESOLUTION_SHA = "7a601f5b7bc0bea5045755723d7f9b946b01f7eba0eee9191e0f2074b6fb5627"

EXPECTED_TRIAL_IDS = ("MR002-A", "MR002-B", "MR002-C", "RNG-001", "RNG-EntryLogic")
DISPERSION_SOURCE_TRIALS = ("MR002-A", "MR002-B", "MR002-C")
PREREG_NAME = "MR002_ValidationOOS_Preregistration_v1.0.4"

# frozen v0.3 stationary bootstrap spec — must match the prereg bytes AND the code constants
BOOTSTRAP_SEED = 20260711
BOOTSTRAP_REPLICATIONS = 10000
BOOTSTRAP_L_PRIMARY = 5
BOOTSTRAP_L_SENSITIVITY = 10

VALIDATION_DISPERSION_ARTIFACT = "MR002_DSR_TrialDispersion_Validation_v1.0.json"

DEFAULT_IDENTITIES = {PREREG: PREREG_SHA, LEDGER: LEDGER_SHA,
                      CORRECTION: CORRECTION_SHA, DISPERSION_RESOLUTION: DISPERSION_RESOLUTION_SHA}


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
def _validate_semantics(prereg: dict, ledger: dict, correction: dict, dispersion: dict) -> int:
    # preregistration (v1.0.4, bootstrap-corrected)
    if _require_str(prereg.get("record_type"), "prereg.record_type") != "MR002_VALIDATIONOOS_PREREGISTRATION":
        _refuse("PREREG_RECORD_TYPE")
    if _require_str(prereg.get("version"), "prereg.version") != "1.0.4":
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

    # frozen v0.3 stationary bootstrap spec (Ruling 1) — bind prereg bytes to code constants
    bs = prereg.get("bootstrap", {})
    if "stationary" not in str(bs.get("name", "")).lower():
        _refuse(f"BOOTSTRAP_NOT_STATIONARY:{bs.get('name')!r}")
    if _require_int(bs.get("seed"), "prereg.bootstrap.seed") != BOOTSTRAP_SEED:
        _refuse(f"BOOTSTRAP_SEED:{bs.get('seed')}")
    if _require_int(bs.get("replications_each"), "prereg.bootstrap.replications_each") != BOOTSTRAP_REPLICATIONS:
        _refuse(f"BOOTSTRAP_REPLICATIONS:{bs.get('replications_each')}")
    if _require_int(bs.get("expected_block_length_primary_sessions"), "prereg.bootstrap.L_primary") != BOOTSTRAP_L_PRIMARY:
        _refuse(f"BOOTSTRAP_L_PRIMARY:{bs.get('expected_block_length_primary_sessions')}")
    if _require_int(bs.get("expected_block_length_sensitivity_sessions"), "prereg.bootstrap.L_sensitivity") != BOOTSTRAP_L_SENSITIVITY:
        _refuse(f"BOOTSTRAP_L_SENSITIVITY:{bs.get('expected_block_length_sensitivity_sessions')}")

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

    # correction record (v1.0.3 -> v1.0.4 bootstrap correction)
    if _require_str(correction.get("record_type"), "correction.record_type") != "MR002_VALIDATIONOOS_CORRECTION":
        _refuse("CORRECTION_RECORD_TYPE")
    if correction.get("version") != "1.0.4":
        _refuse(f"CORRECTION_VERSION:{correction.get('version')}")
    if correction.get("supersedes") != "MR002_ValidationOOS_Preregistration_v1.0.3":
        _refuse(f"CORRECTION_SUPERSEDES:{correction.get('supersedes')}")
    pu = correction.get("prereg_update", {})
    if pu.get("from_sha256") != PREREG_V103_SHA:
        _refuse("CORRECTION_FROM_HASH_UNBOUND")
    if pu.get("to_sha256") != PREREG_SHA:
        _refuse("CORRECTION_TO_HASH_UNBOUND")
    if pu.get("to") != PREREG_NAME:
        _refuse(f"CORRECTION_TO_NAME:{pu.get('to')}")
    aff = correction.get("affirmations", {})
    for key in ("economic_rule_changed", "gate_threshold_changed", "dsr_trial_count_changed",
                "window_or_seam_or_fold_changed", "access_restriction_changed",
                "validation_bytes_read", "oos_bytes_read", "performance_computed"):
        if aff.get(key) is not False:
            _refuse(f"CORRECTION_AFFIRMATION:{key}:{aff.get(key)!r}")

    # DSR dispersion resolution (estimator; N unchanged)
    if _require_str(dispersion.get("record_type"), "dispersion.record_type") != "MR002_DSR_DISPERSION_RESOLUTION":
        _refuse("DISPERSION_RECORD_TYPE")
    n_disp = _require_int(dispersion.get("multiplicity_N"), "dispersion.multiplicity_N")
    ctl = dispersion.get("countersigned_trial_ledger", {})
    if ctl.get("sha256") != LEDGER_SHA:
        _refuse("DISPERSION_LEDGER_HASH_UNBOUND")
    disp = dispersion.get("dispersion", {})
    if tuple(disp.get("source_trials", [])) != DISPERSION_SOURCE_TRIALS:
        _refuse(f"DISPERSION_SOURCE_TRIALS:{disp.get('source_trials')}")
    if disp.get("sample") != "validation":
        _refuse(f"DISPERSION_SAMPLE:{disp.get('sample')}")
    if "ddof=1" not in str(disp.get("estimator", "")):
        _refuse(f"DISPERSION_ESTIMATOR:{disp.get('estimator')}")
    if dispersion.get("governing_prereg", {}).get("sha256") != PREREG_SHA:
        _refuse("DISPERSION_PREREG_HASH_UNBOUND")

    # chain coherence: prereg, ledger, dispersion all agree on N == 5
    if not (n_prereg == n_ledger == n_disp):
        _refuse(f"N_CHAIN_INCONSISTENT:prereg={n_prereg},ledger={n_ledger},dispersion={n_disp}")
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
    """Validate the four governing artifacts in `gov_dir` (strict parse + content hash + full semantic
    cross-binding) and return the bound governing values. The returned `dsr_trials_N` is sourced from
    the ledger bytes; there is no code-constant fallback."""
    expected = expected or DEFAULT_IDENTITIES
    prereg = _loads_strict(_check_file(gov_dir, PREREG, expected[PREREG]))
    ledger = _loads_strict(_check_file(gov_dir, LEDGER, expected[LEDGER]))
    correction = _loads_strict(_check_file(gov_dir, CORRECTION, expected[CORRECTION]))
    dispersion = _loads_strict(_check_file(gov_dir, DISPERSION_RESOLUTION, expected[DISPERSION_RESOLUTION]))
    n = _validate_semantics(prereg, ledger, correction, dispersion)

    # bind the code registry to the loaded gates_frozen (fail-closed on divergence)
    from mr002_valoos_registry import cross_validate_registry
    cross_validate_registry(prereg.get("gates_frozen", {}))

    return {
        "prereg_sha256": expected[PREREG], "ledger_sha256": expected[LEDGER],
        "correction_sha256": expected[CORRECTION],
        "dispersion_resolution_sha256": expected[DISPERSION_RESOLUTION],
        "dsr_trials_N": n,                               # sourced from the ledger
        "dsr_status": "READY", "validation_authorization": False,
        "dispersion_source_trials": list(DISPERSION_SOURCE_TRIALS),
        "bootstrap": {"method": "stationary_politis_romano_circular", "seed": BOOTSTRAP_SEED,
                      "replications_each": BOOTSTRAP_REPLICATIONS,
                      "expected_L_primary": BOOTSTRAP_L_PRIMARY,
                      "expected_L_sensitivity": BOOTSTRAP_L_SENSITIVITY},
        "ledger_included_trials": list(EXPECTED_TRIAL_IDS),
        "gates_frozen": prereg.get("gates_frozen", {}),
    }


# ── production validation-stage dispersion artifact (Ruling 2) ─────────────────────────────────────
def load_validation_dispersion_artifact(gov_dir: str, *, governing_identity: dict,
                                        artifact_name: str = VALIDATION_DISPERSION_ARTIFACT,
                                        expected_sha: str | None = None) -> dict:
    """Fail-closed loader for the countersigned validation-stage dispersion artifact required by the
    production OOS DSR gate. In synthetic qualification the artifact is ABSENT (produced only during
    the authorized validation run) -> REFUSED_CODE_OR_DATA_IDENTITY. Validates schema + identity
    binding (prereg sha, N == governing N) + presence/type of sigma_daily. Numeric finiteness/sign of
    sigma is enforced downstream at compute (INTEGRITY_STOP:DSR_TRIAL_DISPERSION_*)."""
    if os.path.basename(artifact_name) != artifact_name:
        _refuse(f"NON_BASENAME:{artifact_name}")
    p = os.path.join(gov_dir, artifact_name)
    if os.path.islink(p):
        _refuse(f"SYMLINK:{artifact_name}")
    if not os.path.isfile(p):
        _refuse(f"VALIDATION_DISPERSION_ARTIFACT_ABSENT:{artifact_name}")
    raw = open(p, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and got != expected_sha:
        _refuse(f"DISPERSION_ARTIFACT_HASH_MISMATCH:{got}")
    art = _loads_strict(raw)

    if _require_str(art.get("record_type"), "artifact.record_type") != "MR002_DSR_TrialDispersion_Validation":
        _refuse("DISPERSION_ARTIFACT_RECORD_TYPE")
    n = _require_int(art.get("N"), "artifact.N")
    if n != governing_identity.get("dsr_trials_N"):
        _refuse(f"DISPERSION_ARTIFACT_N_MISMATCH:{n}!={governing_identity.get('dsr_trials_N')}")
    if art.get("preregistration_identity") != governing_identity.get("prereg_sha256"):
        _refuse("DISPERSION_ARTIFACT_PREREG_UNBOUND")
    trial_ids = art.get("trial_ids")
    if tuple(trial_ids or ()) != DISPERSION_SOURCE_TRIALS:
        _refuse(f"DISPERSION_ARTIFACT_TRIAL_IDS:{trial_ids}")
    sd = art.get("sigma_daily")
    if isinstance(sd, bool) or not isinstance(sd, (int, float)):
        _refuse(f"DISPERSION_ARTIFACT_SIGMA_TYPE:{sd!r}")
    for req in ("annualization", "ddof", "sigma_annualized", "evaluator_identity",
                "validation_report_identity", "calculation_code_identity", "validation_return_series_hashes"):
        if req not in art:
            _refuse(f"DISPERSION_ARTIFACT_MISSING_FIELD:{req}")

    return {"N": n, "sigma_daily": float(sd),
            "sigma_annualized": float(art["sigma_annualized"]) if isinstance(art.get("sigma_annualized"), (int, float)) and not isinstance(art.get("sigma_annualized"), bool) else None,
            "provenance": "VALIDATION_DERIVED", "artifact_sha256": got,
            "trial_ids": list(trial_ids),
            "synthetic_fixture": bool(art.get("synthetic_fixture", False))}
