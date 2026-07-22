"""MR-002 validation/OOS evaluator — numeric-runtime identity (operational increment / P3).

Captures the executing numeric runtime and verifies it against a bound NumericRuntimeIdentityManifest
runtime instance. A mismatch FAIL-STOPS before any metric, per the Phase 3A manifest
(`mismatch_policy`). Placeholder completion is rejected: a manifest whose runtime-critical fields are
null, empty, or a TBD/PENDING sentinel is not a runtime instance and fails closed.

Reads no dataset. Observes only the interpreter, the installed numeric stack, and operator-supplied
lockfile / container identities.
"""

from __future__ import annotations

import hashlib
import locale as _locale
import os
import platform
import sys
import time

RUNTIME_STOP = "INTEGRITY_STOP:NUMERIC_RUNTIME_IDENTITY_MISMATCH"
RUNTIME_INCOMPLETE = "INTEGRITY_STOP:NUMERIC_RUNTIME_MANIFEST_INCOMPLETE"

# sentinels that mean "not yet produced"; they may never satisfy a runtime binding
PLACEHOLDERS = frozenset({"", "TBD", "PENDING", "PENDING_EVALUATOR_BIND", "UNKNOWN", "N/A",
                          "PLACEHOLDER", "REQUIRED", "TODO"})

THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS")

# the fields a runtime INSTANCE must carry; a specification template carries none of the last two
REQUIRED_FIELDS = (
    "python", "python_impl", "numpy", "scipy", "pandas", "blas", "blas_version", "lapack",
    "lapack_version", "lapack_driver", "machine", "platform", "rng", "bootstrap_seed", "dtype",
    "rcond", "solver", "thread_env", "locale", "timezone",
    "dependency_lockfile_sha256", "container_image_digest",
)

# frozen solver settings (Phase 3A NumericRuntimeIdentityManifest.frozen_solver_settings)
FROZEN_SOLVER = {"solver": "numpy.linalg.lstsq", "lapack_driver": "gelsd/SVD", "dtype": "float64",
                 "rcond": 1e-10}
FROZEN_RNG = "numpy_PCG64"
BOOTSTRAP_SEED = 20260711


class RuntimeIdentityStop(Exception):
    """Raised with an INTEGRITY_STOP:* code before any metric is computed."""


def _stop(code: str, detail: str):
    raise RuntimeIdentityStop(f"{code}:{detail}")


def _is_placeholder(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in PLACEHOLDERS
    if isinstance(value, dict | list):
        return len(value) == 0
    return False


def _blas_identity() -> tuple[str, str, str, str]:
    """(blas, blas_version, lapack, lapack_version) from numpy's build config, fail-soft to ''."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is a hard dependency of the evaluator
        return ("", "", "", "")
    cfg = {}
    show = getattr(np, "__config__", None)
    if show is not None and hasattr(show, "show"):
        try:
            cfg = show.show(mode="dicts") or {}
        except TypeError:  # older numpy: no dict mode
            cfg = {}
    build = (cfg.get("Build Dependencies") or {}) if isinstance(cfg, dict) else {}
    blas = build.get("blas") or {}
    lapack = build.get("lapack") or {}
    return (str(blas.get("name", "")), str(blas.get("version", "")),
            str(lapack.get("name", "")), str(lapack.get("version", "")))


def capture_runtime(*, lockfile_path: str | None = None,
                    container_image_digest: str | None = None) -> dict:
    """Observe the executing runtime. Missing lockfile/container identities stay absent (never faked)."""
    import numpy as np

    blas, blas_v, lapack, lapack_v = _blas_identity()
    observed = {
        "python": platform.python_version(),
        "python_impl": platform.python_implementation(),
        "python_executable_sha256": _sha_path(sys.executable),
        "numpy": np.__version__,
        "scipy": _version("scipy"),
        "pandas": _version("pandas"),
        "blas": blas, "blas_version": blas_v, "lapack": lapack, "lapack_version": lapack_v,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "thread_env": {v: os.environ.get(v) for v in THREAD_VARS},
        "locale": (_locale.getlocale()[0] or ""),
        "timezone": time.tzname[0] if time.tzname else "",
        "rng": FROZEN_RNG,
        "bootstrap_seed": BOOTSTRAP_SEED,
        **FROZEN_SOLVER,
    }
    if lockfile_path:
        observed["dependency_lockfile_sha256"] = _sha_path(lockfile_path)
        observed["dependency_lockfile_path"] = os.path.basename(lockfile_path)
    if container_image_digest:
        observed["container_image_digest"] = container_image_digest
    return observed


def _version(mod: str) -> str:
    try:
        return __import__(mod).__version__
    except Exception:  # noqa: BLE001 - absence is data, not an error
        return ""


def _sha_path(path: str | None) -> str:
    if not path or not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_completeness(manifest: dict) -> dict:
    """Which REQUIRED_FIELDS are absent or placeholder-filled. Empty `missing` == runtime instance."""
    missing = [f for f in REQUIRED_FIELDS if f not in manifest or _is_placeholder(manifest[f])]
    return {"missing": missing, "is_runtime_instance": not missing,
            "required_field_count": len(REQUIRED_FIELDS)}


def verify_runtime(observed: dict, manifest: dict) -> dict:
    """Compare observed runtime against a bound manifest. Reports; does not raise."""
    completeness = manifest_completeness(manifest)
    mismatches = []
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            continue
        want, got = manifest[field], observed.get(field)
        if want != got:
            mismatches.append({"field": field, "bound": want, "observed": got})
    return {"matches": not mismatches and completeness["is_runtime_instance"],
            "mismatches": mismatches, "completeness": completeness}


def require_runtime(observed: dict, manifest: dict) -> dict:
    """Fail-stop gate. Returns the verification report when the runtime identity holds."""
    report = verify_runtime(observed, manifest)
    if not report["completeness"]["is_runtime_instance"]:
        _stop(RUNTIME_INCOMPLETE, ",".join(report["completeness"]["missing"]))
    if report["mismatches"]:
        _stop(RUNTIME_STOP, ",".join(m["field"] for m in report["mismatches"]))
    return report


def runtime_identity_sha256(observed: dict) -> str:
    """Canonical digest of the observed runtime, for binding into evidence."""
    import json
    return hashlib.sha256(
        json.dumps(observed, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()
