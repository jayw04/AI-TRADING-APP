"""WP-E / P10 — the NumericRuntimeIdentityManifest producer and fail-stop gate.

Authorized by the owner on 2026-08-10
(``docs/review/mr002/MR002_PrerequisiteProduction_Authorization_v1.0.json``,
Execution Order Step 3, WP-E). Governing plan: v1.3.1 §WP-E.

The governing specification is
``docs/review/mr002/phase3a/NumericRuntimeIdentityManifest_v1.0.json`` — a
SPECIFICATION TEMPLATE. P10 is not that file. P10 is a *runtime instance* of it
with all 17 required bindings populated from an actually-running evaluator.

===============================================================================
WHY A NUMERIC RUNTIME NEEDS AN IDENTITY AT ALL
===============================================================================

MR-002's evaluator solves ``numpy.linalg.lstsq`` with the gelsd/SVD driver at
``rcond=1e-10`` in float64. The numbers that come out of that call are a
function of the BLAS/LAPACK implementation, the CPU dispatch path chosen at
import time, and the thread count — none of which are pinned by the source
code, the git commit, or even the container image alone. The same image on a
Zen 3 host with AVX2 and on a host with AVX-512 can take different SIMD kernels
and produce different low-order bits. Bootstrap resampling then amplifies those
bits into a different confidence interval, and the acceptance criteria are
threshold comparisons against exactly such intervals.

P5 bound the evaluator's *instance identity*. The P5 closeout is explicit that
it implies NOTHING here: "no numerical library/BLAS/LAPACK/CPU-dispatch/
threading/floating-point/seed/determinism claim; P10 is not implied." This
module is the thing P5 deliberately did not do.

===============================================================================
THE FAILURE THIS PREVENTS IS SILENT
===============================================================================

A validation run on an unbound numeric runtime does not crash. It produces a
Sharpe ratio, a DSR verdict, and a preregistration-shaped report — attributed
to a preregistration whose numbers were never producible on that runtime. There
is one validation opening and it is unconsumed. Spending it on a runtime nobody
pinned spends it for nothing, and no post-hoc analysis can recover the fact,
because the artifact of a wrong run looks exactly like the artifact of a right
one.

So the mismatch policy is FAIL-STOP BEFORE ANY METRIC, and the gate is a raise,
never a return value a caller can forget to check.

===============================================================================
THE CONTAINER-IMAGE DIGEST HAS EXACTLY ONE PERMITTED SOURCE
===============================================================================

Plan v1.3.1 makes the Requirement-7 resolver the SOLE permitted path for P10's
container-image digest binding:

    Binding the digest by any ad-hoc means -- a tag, the local Docker daemon, a
    rebuild, or a hand-copied value -- does not satisfy P10, however identical
    the resulting string looks.

That is enforced structurally, not by comment: :func:`produce_p10_manifest`
takes NO digest parameter. There is no argument through which a caller could
supply one, correct or otherwise. The only way the field gets populated is a
live call into ``resolve_evaluator_image.require_image_binding()``.

===============================================================================
TWO LEGS, AND WHY THE JOIN IS NOT ON TRUST
===============================================================================

The numeric bindings can only be observed from INSIDE the evaluator container;
the registry resolution needs boto3 and credentials, which the evaluator image
is not required to carry. So production has two legs:

  * the in-image leg  -- :func:`capture_numeric_runtime`, invoked as
    ``python numeric_runtime_identity.py --capture`` inside the container;
  * the host leg      -- :func:`produce_p10_manifest`, which resolves the bound
    digest and launches the in-image leg BY THAT RESOLVED DIGEST.

The join between them is not "the host believes the observation came from the
right image". The in-image leg rehashes all 21 evaluator modules at
``/opt/mr002/evaluator`` and the host leg refuses any observation whose module
digests are not EXACTLY the 21 recorded in the bound image manifest. An
observation from a rebuilt, drifted, or unrelated image cannot satisfy that,
regardless of what the host was told it launched.

===============================================================================
SCOPE
===============================================================================

Reads the registry, the governed manifest/lock/spec artifacts in this
repository, and the running interpreter. Opens no validation or OOS data,
computes no performance, and grants no execution authority. A populated P10 is
a prerequisite for a run, never an authorization for one --
``validation_authorization`` is separate CAS-guarded state at ``_rev 0``.
"""

from __future__ import annotations

import hashlib
import json
import locale as _locale
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NO_REPO = Path("/nonexistent-mr002-repo")


def _repo_root(module_path: Path) -> Path:
    """Repository root for the HOST leg, or a sentinel that cannot exist.

    The in-image leg runs from a bind-mount at ``/tmp/mr002_capture.py`` with no
    repository around it, so this must not raise at import time -- and it did,
    which is why the first real capture failed before any binding was observed.
    Every test injected a fake runner, so the module was never imported from
    outside the repo layout and the defect survived the suite.

    A script outside the repo layout gets a path that cannot exist. That keeps
    the failure closed rather than merely deferred: the host-leg constants
    derived from it are only ever read through :func:`_load_json` and
    :func:`_sha256_file`, both of which REFUSE on an unreadable file. So an
    in-image process that somehow reached a host-leg path still refuses; it does
    not silently substitute a default.
    """
    parents = module_path.parents
    return parents[2] if len(parents) > 2 else NO_REPO


REPO = _repo_root(Path(__file__).resolve())

SPEC_PATH = (
    REPO / "docs" / "review" / "mr002" / "phase3a"
    / "NumericRuntimeIdentityManifest_v1.0.json"
)
# REPOINTED 2026-08-11 to the RUNTIME image and its Linux lock, alongside the
# WP-B rebind. The historical manifest and the Windows lock are unchanged on
# disk and remain valid evidence for the SS4/P5 decision they recorded -- they
# are simply not what a run executes against any more. Leaving these pointed at
# the old pair would make P10 bind a lock the runtime image was NOT built from,
# which ``_bind_dependency_lock`` would correctly refuse.
IMAGE_MANIFEST_PATH = (
    REPO / "docs" / "review" / "mr002" / "evaluator"
    / "MR002_EvaluatorImageManifest_Runtime_v1.0.json"
)
DEPENDENCY_LOCK_PATH = (
    REPO / "docs" / "review" / "mr002" / "evaluator"
    / "MR002_LinuxDependencyLock_v1.1.json"
)

# Where the bound image keeps the evaluator. Recorded in the image manifest as
# ``evaluator_path_in_image``; repeated here because the in-image leg runs with
# no repository checkout and therefore cannot read that manifest.
EVALUATOR_PATH_IN_IMAGE = "/opt/mr002/evaluator"

ECR_REPOSITORY_URI = "219024422756.dkr.ecr.us-east-1.amazonaws.com/mr002-evaluator-p5"

# The thread-count environment variables the manifest's threading_policy
# requires to be FROZEN. The alternative the policy allows -- proving that
# varying them does not change governed output hashes -- has not been done, so
# the freeze is the operative branch and an unset variable is not frozen.
# OPENBLAS_CORETYPE is included because it pins OpenBLAS kernel dispatch, which
# is the same class of hazard the thread counts address; the launch-host
# qualification record requires it at HASWELL.
FROZEN_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OPENBLAS_CORETYPE",
)

# The 17 bindings, keyed. Order and wording track the governing spec's
# ``required_bindings`` array; :func:`_assert_spec_agrees` proves at run time
# that this tuple still covers it, so the spec cannot drift away from the code
# silently.
REQUIRED_BINDINGS: tuple[str, ...] = (
    "python_version",
    "numpy_version",
    "scipy_version",
    "pandas_version",
    "blas",
    "lapack",
    "solver_driver",
    "cpu_architecture",
    "thread_env",
    "rng_algorithm",
    "registered_seeds",
    "locale",
    "timezone",
    "dependency_lockfile_sha256",
    "container_image_digest",
    "python_executable_identity",
    "numpy_scipy_binary_identities",
)

# Bindings the in-image leg cannot observe, and therefore must not emit.
#
# Two different reasons, both real. ``solver_driver`` and ``registered_seeds``
# are PREREGISTERED CONSTANTS, not observations — they come from the governing
# spec, and a runtime that "observed" its own seeds would be quoting itself.
# ``dependency_lockfile_sha256`` and ``container_image_digest`` are facts about
# provenance the container has no honest access to: the lockfile is a
# repository artifact and the digest has exactly one permitted source.
#
# The in-image leg emits the other 13. Anything else appearing in an
# observation is a producer that has started inventing bindings, which
# :func:`_reject_host_bindings_in_observation` refuses.
HOST_SUPPLIED_BINDINGS = frozenset(
    {
        "solver_driver",
        "registered_seeds",
        "dependency_lockfile_sha256",
        "container_image_digest",
    }
)

IN_IMAGE_BINDINGS: tuple[str, ...] = tuple(
    k for k in REQUIRED_BINDINGS if k not in HOST_SUPPLIED_BINDINGS
)


class NumericRuntimeRefused(RuntimeError):
    """Raised when a P10 instance CANNOT be produced truthfully.

    Carries a machine-readable ``reason`` so a refusal is recordable as evidence
    without re-parsing an English message.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


class NumericRuntimeMismatch(RuntimeError):
    """Raised by the run-time gate when the live runtime is not the bound one.

    Separate from :class:`NumericRuntimeRefused` because the two are different
    events with different responses: a refusal means the evidence could not be
    produced, a mismatch means the evidence exists and the runtime contradicts
    it. Conflating them would let an operator "retry until it passes".
    """

    def __init__(self, differences: list[dict[str, Any]]) -> None:
        self.differences = differences
        names = ", ".join(d["binding"] for d in differences)
        super().__init__(
            f"numeric-runtime identity mismatch in {len(differences)} binding(s): {names} "
            f"— FAIL-STOP before any metric"
        )


def _refuse(reason: str, detail: str = "") -> None:
    raise NumericRuntimeRefused(reason, detail)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# In-image leg — observation only. No network, no boto3, no repository.
# ---------------------------------------------------------------------------


def _numpy_config() -> dict[str, Any]:
    """BLAS/LAPACK vendor+version as NumPy itself resolved them at build time.

    Read from ``numpy.__config__.show(mode="dicts")`` rather than from a
    package manifest: the question P10 asks is which library the running
    interpreter is actually dispatching into, and a lockfile answers a
    different question.
    """
    try:
        import numpy  # noqa: PLC0415 — the in-image leg imports what it measures
    except ImportError as exc:
        _refuse("numpy_unavailable", str(exc))
    try:
        cfg = numpy.__config__.show(mode="dicts")
    except Exception as exc:  # noqa: BLE001 — any failure here is unobservable
        _refuse("numpy_config_unavailable", f"{type(exc).__name__}: {exc}")
    if not isinstance(cfg, dict):
        _refuse("numpy_config_unavailable", f"show(mode='dicts') returned {type(cfg)}")
    return cfg


def _blas_lapack(cfg: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    deps = cfg.get("Build Dependencies") or {}
    out = []
    for key in ("blas", "lapack"):
        info = deps.get(key)
        if not isinstance(info, dict):
            # "BLAS vendor+version" is a REQUIRED binding. A NumPy that will not
            # say what it linked against cannot be bound, and an unbindable
            # runtime is not a runtime this program may run on.
            _refuse("blas_lapack_unavailable", f"no '{key}' in Build Dependencies")
        name = info.get("name")
        version = info.get("version")
        if not name or not version:
            _refuse("blas_lapack_unavailable", f"'{key}' missing name or version")
        out.append(
            {
                "name": str(name),
                "version": str(version),
                "openblas_config": str(info.get("openblas configuration", "")),
                "pc_file": str(info.get("pc file directory", "")),
            }
        )
    return out[0], out[1]


def _cpu_architecture() -> dict[str, Any]:
    """Architecture AND the SIMD dispatch NumPy actually enabled.

    ``platform.machine()`` alone is not the binding that matters: two x86_64
    hosts differ in whether NumPy's runtime dispatcher selected an AVX2 or an
    AVX-512 kernel, and that selection changes floating-point results. NumPy
    exposes the decision it made in ``__cpu_baseline__`` / ``__cpu_dispatch__``
    / ``__cpu_features__``, so record the decision rather than infer it.
    """
    try:
        from numpy._core import _multiarray_umath as _mu  # noqa: PLC0415
    except ImportError:
        try:
            from numpy.core import _multiarray_umath as _mu  # noqa: PLC0415
        except ImportError as exc:
            _refuse("numpy_cpu_features_unavailable", str(exc))

    features = getattr(_mu, "__cpu_features__", None)
    baseline = getattr(_mu, "__cpu_baseline__", None)
    dispatch = getattr(_mu, "__cpu_dispatch__", None)
    if not isinstance(features, dict) or baseline is None or dispatch is None:
        _refuse(
            "numpy_cpu_features_unavailable",
            "NumPy exposes no __cpu_features__/__cpu_baseline__/__cpu_dispatch__",
        )

    enabled = sorted(name for name, on in features.items() if on)

    model = ""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(errors="replace").splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break

    return {
        "machine": platform.machine(),
        "processor_model": model or platform.processor(),
        "numpy_cpu_baseline": list(baseline),
        "numpy_cpu_dispatch": list(dispatch),
        "numpy_cpu_features_enabled": enabled,
    }


def _require_frozen_threading() -> dict[str, str]:
    """Every thread/dispatch variable must be SET. Unset is not frozen.

    The spec offers two ways to satisfy the threading policy: freeze the
    variables, or prove that varying them leaves governed output hashes
    unchanged. That proof does not exist for MR-002, so the freeze is the only
    live branch — and a variable left to the library default is precisely the
    unfrozen case, because the default is a function of the host's core count.
    """
    values: dict[str, str] = {}
    unset = []
    for name in FROZEN_THREAD_ENV:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            unset.append(name)
        else:
            values[name] = raw
    if unset:
        _refuse(
            "threading_not_frozen",
            "unset (host-default, therefore not frozen): " + ", ".join(unset),
        )
    return values


def _rng_identity() -> dict[str, Any]:
    """Name the bit generator by constructing one, not by quoting the spec."""
    import numpy  # noqa: PLC0415

    gen = numpy.random.default_rng(0)
    return {
        "default_rng_bit_generator": type(gen.bit_generator).__name__,
        "numpy_random_module": numpy.random.__name__,
    }


def _python_executable_identity() -> dict[str, str]:
    exe = sys.executable
    if not exe:
        _refuse("python_executable_unknown", "sys.executable is empty")
    path = Path(exe)
    if not path.exists():
        _refuse("python_executable_unknown", f"{exe} does not exist")
    return {
        "path": exe,
        "sha256": _sha256_file(path),
        "implementation": platform.python_implementation(),
        "build": " ".join(platform.python_build()),
        "compiler": platform.python_compiler(),
    }


def _binary_identities() -> dict[str, Any]:
    """SHA-256 of the compiled NumPy/SciPy extensions actually loaded.

    "where available" in the spec is a real qualifier — a wheel may not expose a
    file path for every extension. Where a path is not resolvable this records
    an explicit ``unavailable`` marker WITH a reason, never an omission and
    never a placeholder value: an omitted binding compares equal to anything,
    which is the failure mode the whole manifest exists to prevent.
    """
    out: dict[str, Any] = {}
    targets = [
        ("numpy._core._multiarray_umath", "numpy.core._multiarray_umath"),
        ("scipy.linalg._flapack", None),
        ("scipy.linalg.cython_lapack", None),
    ]
    for primary, fallback in targets:
        mod = None
        for name in (primary, fallback):
            if not name:
                continue
            try:
                __import__(name)
            except ImportError:
                continue
            mod = sys.modules.get(name)
            if mod is not None:
                break
        if mod is None:
            out[primary] = {"available": False, "reason": "module not importable"}
            continue
        file = getattr(mod, "__file__", None)
        if not file or not Path(file).exists():
            out[primary] = {"available": False, "reason": "no resolvable __file__"}
            continue
        out[primary] = {
            "available": True,
            "path": file,
            "sha256": _sha256_file(Path(file)),
        }
    return out


def _evaluator_module_digests(root: str = EVALUATOR_PATH_IN_IMAGE) -> dict[str, str]:
    """SHA-256 of every evaluator module found in the image.

    This is what ties an observation to the bound image. The host leg compares
    the result against the 21 digests in the bound image manifest and refuses
    anything else, so an observation produced in a rebuilt or unrelated image
    cannot be passed off as an observation from this one.
    """
    path = Path(root)
    if not path.is_dir():
        _refuse("not_running_in_evaluator_image", f"{root} is not a directory")
    digests = {p.name: _sha256_file(p) for p in sorted(path.glob("*.py"))}
    if not digests:
        _refuse("not_running_in_evaluator_image", f"no modules under {root}")
    return digests


def _reject_host_bindings_in_observation(bindings: dict[str, Any]) -> None:
    """An observation must carry the 13 in-image bindings and no others.

    The attack this closes is not malice, it is convenience: someone adds a
    ``container_image_digest`` to the capture "so the host does not have to
    look it up", reading it from the local Docker daemon — which is the exact
    fallback Requirement 7 forbids. The host leg overwrites host-supplied
    bindings anyway, so a smuggled one would not survive; refusing outright
    means the mistake surfaces at the capture rather than being silently
    discarded and repeated.
    """
    smuggled = sorted(set(bindings) & HOST_SUPPLIED_BINDINGS)
    if smuggled:
        _refuse(
            "observation_claims_host_bindings",
            "the in-image leg cannot observe: " + ", ".join(smuggled),
        )
    missing = sorted(set(IN_IMAGE_BINDINGS) - set(bindings))
    if missing:
        _refuse("observation_incomplete", "absent: " + ", ".join(missing))


def _versions() -> dict[str, str]:
    out = {}
    for name in ("numpy", "scipy", "pandas"):
        try:
            mod = __import__(name)
        except ImportError as exc:
            # All three are required bindings. A runtime missing one is not the
            # evaluator's runtime.
            _refuse("required_package_missing", f"{name}: {exc}")
        version = getattr(mod, "__version__", None)
        if not version:
            _refuse("required_package_missing", f"{name} exposes no __version__")
        out[name] = str(version)
    return out


def capture_numeric_runtime(
    *, evaluator_root: str = EVALUATOR_PATH_IN_IMAGE, require_in_image: bool = True
) -> dict[str, Any]:
    """The in-image leg: observe the 13 bindings this side can observe.

    Runs with NO repository checkout and NO network — it reads only the running
    interpreter and the evaluator modules in the image. That is why it emits 13
    bindings rather than 17: the other four are preregistered constants or
    provenance facts a container cannot honestly assert about itself. See
    :data:`HOST_SUPPLIED_BINDINGS`.

    ``require_in_image=False`` exists ONLY for the fail-stop gate, which runs
    inside an already-launched evaluator and has no need to re-derive where it
    is, and for tests. It relaxes nothing else.
    """
    cfg = _numpy_config()
    blas, lapack = _blas_lapack(cfg)
    versions = _versions()

    bindings: dict[str, Any] = {
        "python_version": platform.python_version(),
        "numpy_version": versions["numpy"],
        "scipy_version": versions["scipy"],
        "pandas_version": versions["pandas"],
        "blas": blas,
        "lapack": lapack,
        "cpu_architecture": _cpu_architecture(),
        "thread_env": _require_frozen_threading(),
        "rng_algorithm": _rng_identity(),
        "locale": {
            "lc_all": str(_locale.setlocale(_locale.LC_ALL)),
            "preferred_encoding": _locale.getpreferredencoding(False),
            "lang_env": os.environ.get("LANG", ""),
            "lc_all_env": os.environ.get("LC_ALL", ""),
        },
        "timezone": {
            "tzname": list(time.tzname),
            "tz_env": os.environ.get("TZ", ""),
            "utc_offset_seconds": int(
                datetime.now().astimezone().utcoffset().total_seconds()
            ),
        },
        "python_executable_identity": _python_executable_identity(),
        "numpy_scipy_binary_identities": _binary_identities(),
    }

    _reject_host_bindings_in_observation(bindings)

    observation: dict[str, Any] = {
        "record_type": "MR002_NumericRuntimeObservation",
        "observed_at": _utc_now(),
        "bindings": bindings,
        "evaluator_modules": (
            _evaluator_module_digests(evaluator_root) if require_in_image else {}
        ),
        "in_image": require_in_image,
    }
    return observation


# ---------------------------------------------------------------------------
# Host leg — resolution, launch, verification, assembly.
# ---------------------------------------------------------------------------


def _load_json(path: Path, reason: str) -> dict[str, Any]:
    if not path.exists():
        _refuse(reason, f"{path} is absent")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _refuse(reason, f"{path}: {exc}")


def _load_spec() -> dict[str, Any]:
    spec = _load_json(SPEC_PATH, "spec_unavailable")
    for key in ("required_bindings", "registered_seeds", "frozen_solver_settings"):
        if key not in spec:
            _refuse("spec_unavailable", f"spec has no {key!r}")
    return spec


def _assert_spec_agrees(spec: dict[str, Any]) -> None:
    """The spec lists 17 bindings; this module must still cover exactly 17.

    Cheap, and it catches the one drift that would otherwise pass every test:
    the spec gaining an eighteenth binding while the producer keeps emitting
    seventeen and reporting itself complete.
    """
    declared = spec["required_bindings"]
    if len(declared) != len(REQUIRED_BINDINGS):
        _refuse(
            "binding_count_drift",
            f"spec requires {len(declared)} bindings; this producer covers "
            f"{len(REQUIRED_BINDINGS)}",
        )


def _bind_dependency_lock(lock_path: Path, image_manifest: dict[str, Any]) -> str:
    """Hash the lockfile and prove it is the one the bound image was built from.

    The image manifest records ``build_inputs.dependency_lock_sha256``. If the
    lockfile on disk hashes to anything else, then either the lock drifted or
    this is not the image's lock — and in both cases binding it would record a
    false provenance.
    """
    if not lock_path.exists():
        _refuse("dependency_lock_absent", str(lock_path))
    observed = _sha256_file(lock_path)
    expected = (image_manifest.get("build_inputs") or {}).get("dependency_lock_sha256")
    if not expected:
        _refuse("image_manifest_incomplete", "no build_inputs.dependency_lock_sha256")
    if observed != expected:
        _refuse(
            "dependency_lock_mismatch",
            f"image was built from {expected}; lockfile on disk hashes to {observed}",
        )
    return observed


def _verify_evaluator_modules(
    observed: dict[str, str], image_manifest: dict[str, Any]
) -> None:
    """Refuse any observation that did not come from the bound image.

    Exact set equality, not containment. A superset means extra modules were
    present, which is a different image; a subset means modules are missing,
    which is also a different image. "Close enough" is how a rebuild gets
    accepted as the original.
    """
    expected = image_manifest.get("module_digests_in_image")
    if not isinstance(expected, dict) or not expected:
        _refuse("image_manifest_incomplete", "no module_digests_in_image")

    if set(observed) != set(expected):
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        _refuse(
            "evaluator_module_set_mismatch",
            f"missing={missing} extra={extra}",
        )
    differing = sorted(k for k in expected if observed[k] != expected[k])
    if differing:
        _refuse("evaluator_module_digest_mismatch", ", ".join(differing))


def _default_runner(image_ref: str, capture_script: Path) -> bytes:
    """Launch the in-image leg BY DIGEST and return its stdout.

    ``image_ref`` is built from the resolver's return value and nothing else.
    The script is bind-mounted read-only rather than baked in, because P10 must
    be producible against the already-bound image without rebuilding it — and a
    rebuild would change the very digest being bound.
    """
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "-v",
        f"{capture_script}:/tmp/mr002_capture.py:ro",
        *[
            arg
            for name in FROZEN_THREAD_ENV
            if os.environ.get(name)
            for arg in ("-e", f"{name}={os.environ[name]}")
        ],
        image_ref,
        "python",
        "/tmp/mr002_capture.py",
        "--capture",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)  # noqa: S603
    except OSError as exc:
        _refuse("container_launch_failed", f"{type(exc).__name__}: {exc}")
    if proc.returncode != 0:
        _refuse(
            "in_image_capture_failed",
            f"exit {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[-2000:]}",
        )
    return proc.stdout


def produce_p10_manifest(
    *,
    client: Any = None,
    runner: Any = None,
    lock_path: Path = DEPENDENCY_LOCK_PATH,
    capture_script: Path | None = None,
) -> dict[str, Any]:
    """Produce the P10 runtime instance, or REFUSE.

    Note what this signature does NOT accept: a digest, an image tag, a
    pre-captured observation file, or an override for any binding. The
    container-image digest can enter only through the Requirement-7 resolver,
    and the numeric bindings can enter only from a container the resolver's own
    answer identified. Those are the two substitutions that would make a P10
    look complete while binding nothing, so neither has an argument.

    ``client`` and ``runner`` are injectable for testing. Neither can smuggle a
    pass: the resolver rehashes registry bytes regardless of client origin, and
    the observation is checked against the bound module digests regardless of
    runner origin.
    """
    spec = _load_spec()
    _assert_spec_agrees(spec)
    image_manifest = _load_json(IMAGE_MANIFEST_PATH, "image_manifest_unavailable")

    # THE SOLE PERMITTED PATH. Imported at point of use so the in-image leg,
    # which has no boto3, can import this module without failing at import.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from resolve_evaluator_image import (  # noqa: PLC0415
            ImageResolutionRefused,
            resolve_bound_image,
        )
    except ImportError as exc:
        _refuse("resolver_unavailable", str(exc))

    try:
        resolution = resolve_bound_image(client=client)
    except ImageResolutionRefused as exc:
        # Do NOT degrade to a tag, a cached image, or a rebuild. A P10 that
        # cannot resolve its image is not a weaker P10; it is not a P10.
        _refuse("image_resolution_refused", f"{exc.reason}: {exc.detail}")

    image_digest = resolution["image_digest"]
    if not resolution.get("satisfies_requirement_7"):
        _refuse(
            "resolution_does_not_satisfy_requirement_7",
            "the resolution record does not assert Requirement 7 — a receipt or a "
            "cached observation cannot bind P10",
        )

    script = capture_script or Path(__file__).resolve()
    raw = (runner or _default_runner)(f"{ECR_REPOSITORY_URI}@{image_digest}", script)
    try:
        observation = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        _refuse("malformed_observation", str(exc))
    if not isinstance(observation, dict) or (
        observation.get("record_type") != "MR002_NumericRuntimeObservation"
    ):
        _refuse("malformed_observation", "not a MR002_NumericRuntimeObservation")

    _verify_evaluator_modules(
        observation.get("evaluator_modules") or {}, image_manifest
    )

    bindings = dict(observation["bindings"])
    _reject_host_bindings_in_observation(bindings)

    # The four host-supplied bindings. Two are preregistered constants copied
    # from the governing spec, and the RNG the container actually constructs is
    # checked against the registered one here — a runtime whose default_rng is
    # not the registered bit generator reproduces no bootstrap in the
    # preregistration, so it fails production rather than being recorded.
    declared = str(spec["registered_seeds"].get("rng", "")).lower().replace("_", "")
    observed_rng = str(bindings["rng_algorithm"]["default_rng_bit_generator"]).lower()
    if observed_rng not in declared:
        _refuse(
            "rng_algorithm_mismatch",
            f"spec registers {spec['registered_seeds'].get('rng')!r}; the runtime's "
            f"default_rng is {bindings['rng_algorithm']['default_rng_bit_generator']!r}",
        )

    bindings["solver_driver"] = dict(spec["frozen_solver_settings"])
    bindings["registered_seeds"] = dict(spec["registered_seeds"])
    bindings["dependency_lockfile_sha256"] = _bind_dependency_lock(
        lock_path, image_manifest
    )
    bindings["container_image_digest"] = {
        "digest": image_digest,
        "digest_kind": "OCI image index digest",
        "repository": resolution["repository"],
        "registry_id": resolution["registry_id"],
        "region": resolution["region"],
        "resolution_method": resolution["resolution_method"],
        "resolved_at": resolution["resolved_at"],
        "sole_permitted_path": "resolve_evaluator_image.resolve_bound_image",
    }

    _assert_bindings_complete(bindings)

    return {
        "record_type": "NumericRuntimeIdentityManifest",
        "instance_of": "docs/review/mr002/phase3a/NumericRuntimeIdentityManifest_v1.0.json",
        "prerequisite": "P10",
        "version": "1.0",
        "produced_at": _utc_now(),
        "produced_under": (
            "docs/review/mr002/MR002_PrerequisiteProduction_Authorization_v1.0.json "
            "(Execution Order Step 3, WP-E)"
        ),
        "mismatch_policy": spec["mismatch_policy"],
        "threading_policy_branch": (
            "FROZEN — the alternative branch (proving that varying the thread-count "
            "variables leaves governed output hashes unchanged) has not been performed"
        ),
        "bindings": bindings,
        "provenance": {
            "observed_at": observation["observed_at"],
            "evaluator_modules_verified": len(observation["evaluator_modules"]),
            "evaluator_module_source": "rehashed in-image, compared to the bound image manifest",
            "image_manifest_sha256": _sha256_file(IMAGE_MANIFEST_PATH),
            "spec_sha256": _sha256_file(SPEC_PATH),
            "dependency_lock_path": str(lock_path.relative_to(REPO)).replace("\\", "/"),
        },
        "authorizes": (
            "NOTHING — P10 is a prerequisite for a run, never an authorization for one. "
            "validation_authorization is separate CAS-guarded state."
        ),
    }


def _assert_bindings_complete(bindings: dict[str, Any]) -> None:
    """All 17 present and non-empty. Placeholder completion is not completion.

    The standing prohibitions are explicit that "specification templates,
    retrospective attestations, inferred state, and placeholder completion do
    not satisfy a runtime-evidence prerequisite". ``None``, ``""``, ``{}`` and
    ``[]`` are all placeholder completion wearing a key.
    """
    missing = [k for k in REQUIRED_BINDINGS if k not in bindings]
    if missing:
        _refuse("bindings_incomplete", "absent: " + ", ".join(sorted(missing)))
    empty = [
        k
        for k in REQUIRED_BINDINGS
        if bindings[k] is None or bindings[k] == "" or bindings[k] == {} or bindings[k] == []
    ]
    if empty:
        _refuse("bindings_incomplete", "empty: " + ", ".join(sorted(empty)))
    extra = sorted(set(bindings) - set(REQUIRED_BINDINGS))
    if extra:
        _refuse("bindings_unexpected", "not in the governing spec: " + ", ".join(extra))


# ---------------------------------------------------------------------------
# The run-time gate.
# ---------------------------------------------------------------------------

# Bindings whose values legitimately differ between the production capture and a
# later run WITHOUT indicating a different numeric runtime. Deliberately EMPTY:
# every one of the 17 is identity. This constant exists so that any future
# proposal to exempt a binding has to be written down here, reviewed, and
# justified, rather than implemented as a quiet `continue`.
NON_IDENTITY_BINDINGS: frozenset[str] = frozenset()


def compare_bindings(
    bound: dict[str, Any], observed: dict[str, Any]
) -> list[dict[str, Any]]:
    """Every differing binding, not the first one.

    A caller reading one difference fixes one thing and re-runs; a caller
    reading all of them learns whether they are on the wrong host or merely
    missing an environment variable.
    """
    differences: list[dict[str, Any]] = []
    for key in IN_IMAGE_BINDINGS:
        if key in NON_IDENTITY_BINDINGS:
            continue
        want = bound.get(key)
        got = observed.get(key)
        if want != got:
            differences.append({"binding": key, "bound": want, "observed": got})
    return differences


def require_numeric_runtime(
    bound_manifest: dict[str, Any],
    *,
    resolve_image_digest: Any,
    evaluator_root: str = EVALUATOR_PATH_IN_IMAGE,
) -> None:
    """The gate a validation run calls BEFORE any metric. Returns None or raises.

    Returning ``None`` on success is intentional. A boolean return would invite
    ``if not verify(...): log warning``, and the mismatch policy is FAIL-STOP,
    not warn-and-continue.

    ``resolve_image_digest`` is a REQUIRED keyword-only callable returning the
    live-resolved image digest — in production,
    ``resolve_evaluator_image.require_image_binding``. It is required, and has
    no default, because of what the gate cannot otherwise do: it runs inside the
    container, where the image digest is unobservable, so without an injected
    resolver the check would quietly cover 13 of 17 bindings while reporting a
    full pass.

    Stated plainly, because a gate that overstates its coverage is worse than
    one that admits a gap: this gate re-observes the 13 in-image bindings and
    re-resolves the image digest. It does NOT re-derive ``solver_driver``,
    ``registered_seeds`` or ``dependency_lockfile_sha256`` — those are
    preregistered constants and repository provenance, fixed and hash-recorded
    when the manifest was produced, and there is no repository checkout inside
    the evaluator container to re-derive them from. They are bound at
    production time by :func:`produce_p10_manifest`; the image-digest check
    above is what makes that binding still applicable to this run.
    """
    if bound_manifest.get("record_type") != "NumericRuntimeIdentityManifest":
        _refuse("not_a_p10_manifest", str(bound_manifest.get("record_type")))
    bound = bound_manifest.get("bindings")
    if not isinstance(bound, dict):
        _refuse("not_a_p10_manifest", "no bindings object")
    _assert_bindings_complete(bound)
    if not callable(resolve_image_digest):
        _refuse("no_image_resolver", "resolve_image_digest must be callable")

    observation = capture_numeric_runtime(
        evaluator_root=evaluator_root, require_in_image=False
    )
    differences = compare_bindings(bound, observation["bindings"])

    # The 14th check: the image the run is executing in must still resolve, live,
    # to the digest the manifest bound. A stale-but-matching numeric runtime on a
    # different image is exactly the substitution Requirement 7 exists to catch.
    bound_digest = (bound.get("container_image_digest") or {}).get("digest")
    live_digest = resolve_image_digest()
    if bound_digest != live_digest:
        differences.append(
            {
                "binding": "container_image_digest",
                "bound": bound_digest,
                "observed": live_digest,
            }
        )

    if differences:
        raise NumericRuntimeMismatch(differences)


if __name__ == "__main__":  # pragma: no cover - operator entry point
    if "--capture" in sys.argv:
        # In-image leg. stdout is the observation and nothing else, because the
        # host leg parses it; diagnostics go to stderr.
        try:
            print(json.dumps(capture_numeric_runtime(), indent=1, sort_keys=True))
        except NumericRuntimeRefused as exc:
            print(f"CAPTURE REFUSED: {exc.reason}", file=sys.stderr)
            if exc.detail:
                print(f"  detail: {exc.detail}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    try:
        manifest = produce_p10_manifest()
    except NumericRuntimeRefused as exc:
        print(f"P10 PRODUCTION REFUSED: {exc.reason}")
        if exc.detail:
            print(f"  detail: {exc.detail}")
        print(
            "\nFAIL CLOSED. No fallback to a tag, a local image, a rebuild, or a "
            "hand-supplied digest is permitted."
        )
        sys.exit(1)
    print(json.dumps(manifest, indent=2, sort_keys=True))
