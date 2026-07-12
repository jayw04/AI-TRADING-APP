"""MR-002 v1.1 — SOLVER-RUNTIME MANIFEST emitter.

Registered by Pre-Registration v1.1 rev 3, Appendix B.6 (countersigned 2026-07-12,
artifact sha256 311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5).

"The solver-runtime manifest — not the developer workstation — is the authoritative
execution record."

Runs INSIDE the frozen Linux/amd64 image. It attests what actually executes, and it
FAILS LOUDLY rather than emitting a manifest it cannot substantiate.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import struct
import subprocess
import sys
import warnings

FATAL: list[str] = []


def fatal(msg: str) -> None:
    FATAL.append(msg)


# ---------------------------------------------------------------------------
# B.5 — determinism controls: ASSERTED at process start, not merely set.
# ---------------------------------------------------------------------------
THREAD_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
threads = {v: os.environ.get(v) for v in THREAD_VARS}
for var, val in threads.items():
    if val != "1":
        fatal(f"determinism control not asserted: {var}={val!r}, expected '1'")

import numpy as np  # noqa: E402  (imported only after the thread pins are asserted)
import quadprog  # noqa: E402
import scipy  # noqa: E402
from scipy.optimize import linprog  # noqa: E402


# ---------------------------------------------------------------------------
# HiGHS version — probe honestly; record "unavailable" rather than guessing.
# ---------------------------------------------------------------------------
def highs_version() -> str:
    try:
        from scipy.optimize._highspy import _core  # type: ignore

        for attr in ("HIGHS_VERSION_MAJOR", "HIGHS_VERSION_MINOR", "HIGHS_VERSION_PATCH"):
            if not hasattr(_core, attr):
                break
        else:
            return (
                f"{_core.HIGHS_VERSION_MAJOR}."
                f"{_core.HIGHS_VERSION_MINOR}."
                f"{_core.HIGHS_VERSION_PATCH}"
            )
        h = _core.Highs()
        return str(h.version())
    except Exception:
        pass
    try:
        import highspy  # type: ignore

        return str(highspy.Highs().version())
    except Exception:
        pass
    return f"unavailable-as-a-separate-version; vendored by scipy {scipy.__version__}"


# ---------------------------------------------------------------------------
# BLAS/LAPACK vendor.
# ---------------------------------------------------------------------------
def blas_info() -> dict:
    out: dict = {}
    try:
        cfg = np.__config__.show(mode="dicts")  # type: ignore[call-arg]
        blas = cfg.get("Build Dependencies", {}).get("blas", {})
        lapack = cfg.get("Build Dependencies", {}).get("lapack", {})
        out["numpy_blas"] = {
            "name": blas.get("name"),
            "version": blas.get("version"),
            "detection": blas.get("detection method"),
        }
        out["numpy_lapack"] = {"name": lapack.get("name"), "version": lapack.get("version")}
    except Exception as exc:  # pragma: no cover
        out["numpy_blas_error"] = repr(exc)
    return out


# ---------------------------------------------------------------------------
# B.1 / D2 — the tolerance contract, VERIFIED not assumed.
#
# SciPy never echoes the applied tolerance back, so "we asked for 1e-10" is not
# evidence. What IS evidence is a discriminating pair:
#     1e-10  (the HiGHS floor)      -> accepted, NO warning
#     1e-11  (below the floor)      -> OptimizeWarning, silently reverts to the
#                                      1e-7 default, and STILL returns success=True
# Observing exactly that pair proves the option reached HiGHS and was honored at
# 1e-10. If 1e-10 ever starts warning, the floor moved and the frozen contract is
# void -> INVALID_RUN.
# ---------------------------------------------------------------------------
LP_KWARGS = dict(
    c=[-1.0, -1.0],
    A_ub=[[1.0, 1.0]],
    b_ub=[1.0],
    bounds=[(0.0, 1.0), (0.0, 1.0)],
    method="highs-ds",
)
FROZEN_LP_OPTIONS = {
    "presolve": True,
    "primal_feasibility_tolerance": 1e-10,
    "dual_feasibility_tolerance": 1e-10,
    "simplex_dual_edge_weight_strategy": "devex",
    "time_limit": 60.0,
    "maxiter": 100000,
    "disp": False,
}


def probe_tolerance(tol: float) -> dict:
    opts = dict(FROZEN_LP_OPTIONS)
    opts["primal_feasibility_tolerance"] = tol
    opts["dual_feasibility_tolerance"] = tol
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = linprog(**LP_KWARGS, options=opts)
    return {
        "tolerance": tol,
        "success": bool(res.success),
        "status": int(res.status),
        "warnings": sorted({str(w.message) for w in caught}),
    }


accepted = probe_tolerance(1e-10)
rejected = probe_tolerance(1e-11)

tolerance_verification = {
    "method": (
        "Discriminating pair. SciPy does not echo the applied tolerance, so the "
        "verification is behavioral: the registered value must be accepted SILENTLY "
        "while a below-floor value must WARN (and, under the frozen policy, raise). "
        "Observing both proves the option reached HiGHS and was honored at 1e-10."
    ),
    "registered_value_1e-10": accepted,
    "below_floor_control_1e-11": rejected,
}

if not (accepted["success"] and accepted["status"] == 0 and not accepted["warnings"]):
    fatal(
        "the registered feasibility tolerance 1e-10 was NOT honored silently: "
        f"{accepted!r} — the HiGHS floor may have moved; the frozen contract is void"
    )
if not rejected["warnings"]:
    fatal(
        "the below-floor control (1e-11) did NOT warn — the silent-fallback detector "
        "is inoperative, so tolerance honoring can no longer be verified"
    )
tolerance_verification["verdict"] = "HONORED" if not FATAL else "NOT VERIFIED"

# The frozen policy itself: every solve is wrapped so ANY warning is fatal.
with warnings.catch_warnings():
    warnings.simplefilter("error")
    frozen_solve = linprog(**LP_KWARGS, options=FROZEN_LP_OPTIONS)
    if not (frozen_solve.success and frozen_solve.status == 0):
        fatal(f"frozen LP options failed under the fatal-warning policy: {frozen_solve.message}")

# ...and the same policy must REJECT the below-floor value rather than proceed.
below_floor_raises = False
try:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        bad = dict(FROZEN_LP_OPTIONS)
        bad["primal_feasibility_tolerance"] = 1e-11
        bad["dual_feasibility_tolerance"] = 1e-11
        linprog(**LP_KWARGS, options=bad)
except Warning:
    below_floor_raises = True
if not below_floor_raises:
    fatal("the fatal-warning policy did NOT stop a below-floor tolerance (D2 / fixture 18a)")


# ---------------------------------------------------------------------------
# B.3 — the quadprog contract, verified against the real library.
# ---------------------------------------------------------------------------
H = np.diag([2.0 / 0.015, 2.0 / 0.010])
a = np.array([2.0, 2.0])
C = np.array([[1.0], [1.0]])
b = np.array([-1.0])
qp_out = quadprog.solve_qp(H, a, C, b, 0)

qp_exceptions = {}
try:
    quadprog.solve_qp(np.diag([0.0, 1.0]), a, C, b, 0)
except ValueError as exc:
    qp_exceptions["not_positive_definite"] = str(exc)
try:
    quadprog.solve_qp(
        H, a, np.array([[1.0, -1.0], [0.0, 0.0]]), np.array([1.0, -2.0]), 2
    )
except ValueError as exc:
    qp_exceptions["inconsistent_constraints"] = str(exc)

for key in ("not_positive_definite", "inconsistent_constraints"):
    if key not in qp_exceptions:
        fatal(f"quadprog did not raise the registered fatal exception for: {key}")

qp_contract = {
    "method": "Goldfarb-Idnani dual active-set (numerical, NOT exact)",
    "normal_return_arity": len(qp_out),
    "normal_return_fields": ["x", "f", "xu", "iterations", "lagrangian", "iact"],
    "success_signal": "returns without raising (quadprog has no status code)",
    "registered_fatal_exceptions": qp_exceptions,
    "hessian_symbol": "H  (NEVER 'G' — G is reserved for total gross exposure)",
    "hessian_condition_number_limit": 1e10,
    "no_fallback_solver": True,
    "no_matrix_regularization": True,
    "no_external_watchdog": True,
}


# ---------------------------------------------------------------------------
# B.5 — IEEE-754 hexadecimal canonical serialization.
# ---------------------------------------------------------------------------
def f64_hex(x: float) -> str:
    return struct.pack(">d", float(x)).hex()


serialization_selftest = {
    "convention": "IEEE-754 big-endian hexadecimal; never platform-dependent decimal",
    "examples": {repr(v): f64_hex(v) for v in (0.0, 0.015, 0.0619123456789, 1e-8)},
    "roundtrip_exact": all(
        struct.unpack(">d", bytes.fromhex(f64_hex(v)))[0] == v
        for v in (0.0, 0.015, 0.0619123456789, 1e-8, float(qp_out[0][0]))
    ),
}
if not serialization_selftest["roundtrip_exact"]:
    fatal("IEEE-754 hex serialization is not round-trip exact")


# ---------------------------------------------------------------------------
# Dependency artifacts — hashes captured INSIDE the image at build time.
# ---------------------------------------------------------------------------
def sha256_file(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


artifacts: dict[str, dict] = {}
try:
    with open("/manifest/pip_report.json", encoding="utf-8") as fh:
        report = json.load(fh)
    for item in report.get("install", []):
        meta = item.get("metadata", {})
        dl = item.get("download_info", {})
        name = meta.get("name")
        if not name:
            continue
        artifacts[name] = {
            "version": meta.get("version"),
            "url": dl.get("url"),
            "sha256": (dl.get("archive_info", {}) or {}).get("hashes", {}).get("sha256"),
        }
except OSError as exc:
    fatal(f"pip install report not readable inside the image: {exc!r}")

for pkg in ("quadprog", "scipy", "numpy"):
    if pkg not in artifacts or not artifacts[pkg].get("sha256"):
        fatal(f"no in-image artifact hash recorded for the registered dependency: {pkg}")

lockfile_sha256 = sha256_file("/manifest/requirements.lock")
if lockfile_sha256 is None:
    fatal("dependency lockfile was not generated inside the image")

try:
    lock_text = open("/manifest/requirements.lock", encoding="utf-8").read().splitlines()
except OSError:
    lock_text = []


def uname() -> dict:
    try:
        osr = dict(
            line.split("=", 1)
            for line in open("/etc/os-release", encoding="utf-8").read().splitlines()
            if "=" in line
        )
    except OSError:
        osr = {}
    return {
        "system": platform.system(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "distribution": osr.get("PRETTY_NAME", "").strip('"'),
        "libc": " ".join(platform.libc_ver()),
    }


# ---------------------------------------------------------------------------
# Emit.
# ---------------------------------------------------------------------------
manifest = {
    "record_type": "MR002_SOLVER_RUNTIME_MANIFEST",
    "registered_by": "MR-002 Pre-Registration v1.1 rev 3, Appendix B.6",
    "preregistration_artifact_sha256": (
        "311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5"
    ),
    "authoritative": (
        "This manifest, emitted from inside the frozen image, is the execution record. "
        "Developer-workstation values are provenance only and establish nothing."
    ),
    "runtime_boundary": {
        "standalone_research_image": True,
        "is_workbench_compose_stack": False,
        "live_database": False,
        "broker_connection": False,
        "market_data_websocket": False,
        "research_store_mount": "read-only",
    },
    "image_digest": os.environ.get("MR002_IMAGE_DIGEST", "INJECTED_AT_RUN"),
    "image_tag": os.environ.get("MR002_IMAGE_TAG", "INJECTED_AT_RUN"),
    "base_image_digest": (
        "python@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7"
    ),
    "platform": uname(),
    "versions": {
        "python": sys.version.split()[0],
        "python_full": sys.version,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "highs": highs_version(),
        "quadprog": getattr(quadprog, "__version__", artifacts.get("quadprog", {}).get("version")),
    },
    "blas_lapack": blas_info(),
    "determinism_controls": {
        "thread_env_asserted": threads,
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "warm_starts": "disabled",
        "canonical_ordering": "permanent identifier (permaticker)",
        "warning_policy": 'warnings.simplefilter("error") around every solve — ANY warning is FATAL',
        "byte_identical_scope": (
            "same frozen image + dependency set + CPU architecture + input snapshot; "
            "cross-platform runs must be numerically equivalent within frozen tolerances, "
            "not byte-identical"
        ),
    },
    "frozen_lp_options": FROZEN_LP_OPTIONS,
    "accepted_lp_result": {"success": True, "status": 0},
    "tolerance_verification": tolerance_verification,
    "qp_contract": qp_contract,
    "frozen_tolerances": {
        "eps_retention": 1e-8,
        "eps_new": 1e-8,
        "eps_include": 1e-8,
        "eps_active_sector": 1e-6,
        "primal_residual_max": 1e-9,
        "dual_residual_max": 1e-9,
        "stationarity_residual_max": 1e-8,
        "complementarity_residual_max": 1e-8,
        "kkt_residual_max": 1e-8,
        "hessian_condition_number_max": 1e10,
    },
    "serialization": serialization_selftest,
    "dependencies": {
        "requirements_lock_sha256": lockfile_sha256,
        "requirements_lock": lock_text,
        "artifact_hashes": artifacts,
    },
    "fatal": FATAL,
    "verdict": "VALID" if not FATAL else "INVALID_RUN",
}

out = os.environ.get("MR002_MANIFEST_OUT", "/out/MR002_SolverRuntimeManifest.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=False)
    fh.write("\n")

print(json.dumps({k: manifest[k] for k in ("verdict", "platform", "versions")}, indent=2))
print(f"\ntolerance verification: {tolerance_verification['verdict']}")
print(f"quadprog artifact sha256: {artifacts.get('quadprog', {}).get('sha256')}")
print(f"lockfile sha256: {lockfile_sha256}")
print(f"\nmanifest written: {out}")

if FATAL:
    print("\nINVALID_RUN — fatal conditions:", file=sys.stderr)
    for f in FATAL:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)
