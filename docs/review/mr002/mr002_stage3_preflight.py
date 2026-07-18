"""MR-002 Stage-3 — pre-run provenance / environment validator (review finding 3).

Adjudication §7-C requires INVALID_RUN for source/commit/image/configuration/problem-identity/
manifest/mapping/internal-invariant defects. The cascade module enforces the per-instance runtime
integrity gates; THIS validator enforces the *run-level* provenance and environment gates, and it must
execute and PASS **before any instance is resolved**. It FAILS CLOSED: anything not affirmatively
verified is a FAIL, and the population runner refuses to resolve a single row unless preflight passes.

Design: `evaluate(env, expected, source_defects) -> Report` is a PURE function of an injected `Env`
snapshot + `ExpectedPins`, so every branch is unit-testable without the pinned image. `gather_env()`
reads the real system (git, image digest, interpreter, installed packages, CPU flags, environment
variables, live config, callable fingerprints) and is used by `run_preflight()` in-image.

Checks (all must PASS; UNAVAILABLE ⇒ FAIL):
  source_manifest · git_commit · git_tree · working_tree_clean · image_digest · oci_config_digest ·
  python_version · python_abi · package_versions · cpu_avx2_present · cpu_avx512_absent · thread_env ·
  openblas_coretype · material_config · solver_certifier_fingerprints · corpus_hash · cascade_import_hygiene
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, PASS if ok else FAIL, detail))

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.status == PASS for c in self.checks)

    def summary(self) -> dict:
        return {"passed": self.passed,
                "checks": [{"name": c.name, "status": c.status, "detail": c.detail}
                           for c in self.checks],
                "failed": [c.name for c in self.checks if c.status != PASS]}


@dataclass(frozen=True)
class Env:
    """Everything observed about the running environment. Injected so `evaluate` is pure."""

    git_commit: str | None = None
    git_tree: str | None = None
    working_tree_clean: bool | None = None
    image_digest: str | None = None
    oci_config_digest: str | None = None
    python_version: str | None = None
    python_abi: str | None = None
    package_versions: dict[str, str] = field(default_factory=dict)
    cpu_flags: frozenset[str] = frozenset()
    cpu_flags_available: bool = False
    env_vars: dict[str, str] = field(default_factory=dict)
    live_config: dict = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpectedPins:
    """The identities the execution countersignature pins. A None / placeholder pin FAILS closed."""

    git_commit: str | None = None
    git_tree: str | None = None
    image_digest: str | None = None
    oci_config_digest: str | None = None          # MUST be a full 64-hex digest (finding 22)
    python_version: str | None = None
    python_abi: str | None = None
    package_versions: dict[str, str] = field(default_factory=dict)
    # the CLOSED set of material packages that must all be pinned (finding 18) — no missing, no extra
    required_packages: frozenset[str] = frozenset(
        {"numpy", "scipy", "quadprog", "piqp", "clarabel", "highspy", "mpmath"})
    # the positive allowlist of MR-002 modules the cascade path may load (finding 16)
    approved_modules: frozenset[str] = frozenset({
        "app.research.mr002.stage3_cascade", "app.research.mr002.certificate",
        "app.research.mr002.directed", "app.research.mr002.joint_portfolio",
        "app.research.mr002.repair", "scripts.mr002_coverage_signed_gap",
        "scripts.mr002_piqp", "scripts.mr002_solver_intersection",
        "scripts.mr002_characterize_native_qp", "scripts.mr002_stage3_preflight",
        "scripts.mr002_stage3_source_manifest", "scripts.mr002_stage3_population_runner"})
    required_cpu_flags: frozenset[str] = frozenset({"avx2"})
    forbidden_cpu_flags: frozenset[str] = frozenset(
        {"avx512f", "avx512dq", "avx512cd", "avx512bw", "avx512vl"})
    thread_env: dict[str, str] = field(default_factory=lambda: {
        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    openblas_coretype: str = "HASWELL"
    corpus_hash: str = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"
    material_config: dict = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)


def _is_full_digest(d: str | None) -> bool:
    if not d:
        return False
    h = d.split(":", 1)[-1]
    return len(h) == 64 and all(c in "0123456789abcdef" for c in h.lower())


def evaluate(env: Env, expected: ExpectedPins, source_defects: list[str]) -> Report:
    """Pure evaluation of every gate. FAIL-CLOSED: missing pins, missing observations, and any
    mismatch all FAIL."""
    r = Report()

    # ── source manifest (findings 3, 6) ──────────────────────────────────────────────────────
    r.add("source_manifest", not source_defects,
          "ok" if not source_defects else f"{len(source_defects)} defect(s): {source_defects[:6]}")

    # ── provenance: commit / tree / clean working tree ───────────────────────────────────────
    r.add("git_commit", bool(expected.git_commit) and env.git_commit == expected.git_commit,
          f"observed={env.git_commit} expected={expected.git_commit}")
    r.add("git_tree", bool(expected.git_tree) and env.git_tree == expected.git_tree,
          f"observed={env.git_tree} expected={expected.git_tree}")
    r.add("working_tree_clean", env.working_tree_clean is True,
          f"clean={env.working_tree_clean}")

    # ── container: image + FULL OCI config digest (finding 22) ────────────────────────────────
    r.add("image_digest", bool(expected.image_digest) and env.image_digest == expected.image_digest
          and _is_full_digest(expected.image_digest),
          f"observed={env.image_digest} expected={expected.image_digest}")
    r.add("oci_config_digest",
          _is_full_digest(expected.oci_config_digest)
          and env.oci_config_digest == expected.oci_config_digest,
          f"observed={env.oci_config_digest} expected={expected.oci_config_digest} "
          f"(must be a full 64-hex digest)")

    # ── interpreter ──────────────────────────────────────────────────────────────────────────
    r.add("python_version", bool(expected.python_version)
          and env.python_version == expected.python_version,
          f"observed={env.python_version} expected={expected.python_version}")
    r.add("python_abi", bool(expected.python_abi) and env.python_abi == expected.python_abi,
          f"observed={env.python_abi} expected={expected.python_abi}")

    # ── package versions — EXACTLY the closed set (cycle-3 finding 22): every required package
    # pinned, no EXTRA names in the pin map, and every pinned version matching the observed one.
    # Version strings do not bind native shared objects / BLAS builds — the image digest + launch
    # attestation carry that burden.
    missing_pins = sorted(expected.required_packages - set(expected.package_versions))
    extra_pins = sorted(set(expected.package_versions) - expected.required_packages)
    version_mism = {k: (env.package_versions.get(k), v)
                    for k, v in expected.package_versions.items()
                    if env.package_versions.get(k) != v}
    pkg_ok = not missing_pins and not extra_pins and not version_mism
    r.add("package_versions", pkg_ok,
          "ok" if pkg_ok else f"missing_pins={missing_pins} extra_pins={extra_pins} mismatch={version_mism}")

    # ── CPU capability (AVX2 present, AVX-512 absent) ─────────────────────────────────────────
    if not env.cpu_flags_available:
        r.add("cpu_avx2_present", False, "cpu flags unavailable")
        r.add("cpu_avx512_absent", False, "cpu flags unavailable")
    else:
        r.add("cpu_avx2_present", expected.required_cpu_flags <= env.cpu_flags,
              f"required={sorted(expected.required_cpu_flags)} present={sorted(expected.required_cpu_flags & env.cpu_flags)}")
        present_forbidden = expected.forbidden_cpu_flags & env.cpu_flags
        r.add("cpu_avx512_absent", not present_forbidden,
              "none present" if not present_forbidden else f"FORBIDDEN present: {sorted(present_forbidden)}")

    # ── thread + BLAS kernel env ──────────────────────────────────────────────────────────────
    thread_bad = {k: env.env_vars.get(k) for k, v in expected.thread_env.items()
                  if env.env_vars.get(k) != v}
    r.add("thread_env", not thread_bad, "ok" if not thread_bad else f"mismatch: {thread_bad}")
    r.add("openblas_coretype", env.env_vars.get("OPENBLAS_CORETYPE") == expected.openblas_coretype,
          f"observed={env.env_vars.get('OPENBLAS_CORETYPE')} expected={expected.openblas_coretype}")

    # ── material config (LIMITS / signed-gap band / PIQP BASE / cascade) — TWO-WAY exact match
    # inside each material section (cycle-3 finding 21): extra observed keys inside a material
    # subtree fail, not only missing/mismatched expected keys.
    if not expected.material_config:
        r.add("material_config", False, "no expected material config provided")
    else:
        cfg_bad = []
        for key, exp_sub in expected.material_config.items():
            obs_sub = env.live_config.get(key)
            if isinstance(exp_sub, dict):
                if not isinstance(obs_sub, dict):
                    cfg_bad.append(f"{key}:not-a-dict")
                else:
                    cfg_bad.extend(_dict_diff_exact(exp_sub, obs_sub, prefix=key + "."))
            elif obs_sub != exp_sub:
                cfg_bad.append(f"{key}:{obs_sub}!={exp_sub}")
        r.add("material_config", not cfg_bad, "ok" if not cfg_bad else f"mismatch: {cfg_bad[:6]}")

    # ── corpus identity (SOURCE CONSTANT only) ───────────────────────────────────────────────
    # This checks the registered-corpus-hash CONSTANT in source. The REGENERATED corpus bytes are
    # hashed directly and compared by the population runner's `orchestrate` BEFORE any solve
    # (finding 17); preflight cannot see the not-yet-regenerated corpus.
    r.add("corpus_hash_constant", env.live_config.get("registered_corpus_hash") == expected.corpus_hash,
          f"observed={env.live_config.get('registered_corpus_hash')} expected={expected.corpus_hash}")

    # ── solver / certifier callable fingerprints (NARROW claim — finding 19) ──────────────────
    # These are inspect.getsource hashes of selected Python callables. They do NOT bind native
    # extension binaries, BLAS/LAPACK, closures, module globals, or dynamically-selected solver
    # objects — those are covered by the pinned image digest + the closed package-version set, not
    # by these fingerprints. The pin set is CLOSED (cycle-3 finding 20): it must supply exactly the
    # mandatory keys — a partial or padded set fails.
    from app.research.mr002.stage3_cascade import REQUIRED_FINGERPRINT_KEYS
    fp_missing = sorted(REQUIRED_FINGERPRINT_KEYS - set(expected.fingerprints))
    fp_extra = sorted(set(expected.fingerprints) - REQUIRED_FINGERPRINT_KEYS)
    fp_bad = {k: (env.fingerprints.get(k), v) for k, v in expected.fingerprints.items()
              if env.fingerprints.get(k) != v}
    fp_ok = not fp_missing and not fp_extra and not fp_bad
    r.add("solver_certifier_fingerprints", fp_ok,
          "ok" if fp_ok else f"missing={fp_missing} extra={fp_extra} mismatch={list(fp_bad)}")

    # ── cascade import hygiene — POSITIVE allowlist (finding 16) ──────────────────────────────
    # Evaluated at preflight time, BEFORE any corpus regeneration (which legitimately imports
    # dataset/runner/development_run). Any loaded MR-002 module outside the approved set FAILS — a
    # renamed quarantine loader cannot pass a negative-only check. Caveat: sys.modules reflects
    # process-wide imports, so this is a runtime audit, not static proof; the source manifest +
    # image binding carry the static guarantee.
    imports = set(env.live_config.get("cascade_module_imports", []))
    unapproved = sorted(imports - expected.approved_modules)
    r.add("cascade_import_hygiene", bool(imports) and not unapproved,
          "clean" if imports and not unapproved else f"unapproved modules loaded: {unapproved}"
          if unapproved else "cascade import set not reported")

    return r


def _dict_diff(expected: dict, observed: dict, prefix: str = "") -> list[str]:
    out: list[str] = []
    for k, ev in expected.items():
        ov = observed.get(k)
        key = f"{prefix}{k}"
        if isinstance(ev, dict):
            if not isinstance(ov, dict):
                out.append(f"{key}:not-a-dict")
            else:
                out.extend(_dict_diff(ev, ov, prefix=key + "."))
        elif ov != ev:
            out.append(f"{key}:{ov}!={ev}")
    return out


def _dict_diff_exact(expected: dict, observed: dict, prefix: str = "") -> list[str]:
    """TWO-WAY exact comparison (cycle-3 finding 21): missing, mismatched, AND extra keys all fail."""
    out = _dict_diff(expected, observed, prefix)
    out.extend(f"{prefix}{k}:unexpected" for k in sorted(set(observed) - set(expected)))
    return out


# ── real-system observation (in-image) ───────────────────────────────────────────────────────────
def _read_cpu_flags() -> tuple[frozenset[str], bool]:
    """Best-effort CPU-flag read. /proc/cpuinfo on Linux (the pinned image); otherwise unavailable."""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("flags") or line.startswith("Features"):
                    return frozenset(line.split(":", 1)[1].split()), True
    except OSError:
        pass
    return frozenset(), False


def gather_env(root: str | None = None) -> Env:  # pragma: no cover - exercised in-image
    """Observe the real environment. Imports the solver stack; runs in the pinned image."""
    import importlib.metadata as md
    import inspect
    import platform
    import subprocess
    import sysconfig

    def _git(*a) -> str | None:
        """Run a git command ONCE; require returncode 0 and empty stderr (finding 13)."""
        try:
            p = subprocess.run(["git", *a], capture_output=True, text=True, cwd=root, timeout=30)
        except Exception:  # noqa: BLE001
            return None
        if p.returncode != 0 or p.stderr.strip():
            return None
        return p.stdout.strip()

    _porcelain = _git("status", "--porcelain")     # run ONCE — no time-of-check race
    _head = _git("rev-parse", "HEAD")

    versions = {}
    for pkg in ("numpy", "scipy", "quadprog", "piqp", "clarabel", "highspy", "mpmath"):
        try:
            versions[pkg] = md.version(pkg)
        except Exception:  # noqa: BLE001
            versions[pkg] = None

    flags, flags_ok = _read_cpu_flags()

    live_config: dict = {}
    fingerprints: dict = {}
    try:
        sys.path.insert(0, os.path.join(root or ".", "apps", "backend"))
        import app.research.mr002.stage3_cascade as casc
        from app.research.mr002 import certificate as cert
        from scripts import mr002_coverage_signed_gap as cov
        from scripts import mr002_piqp, mr002_solver_intersection
        live_config = {
            "registered_acceptance_LIMITS": dict(mr002_solver_intersection.LIMITS),
            "signed_gap_band": [-cert.SIGNED_GAP_MAX, cert.SIGNED_GAP_MAX],
            "max_interval_width": cert.MAX_INTERVAL_WIDTH,
            "registered_corpus_hash": mr002_solver_intersection.REGISTERED_CORPUS_HASH,
            "cascade": {"primary": cov.PRIMARY, "fallback": cov.FALLBACK},
            "piqp_P2_BASE": {k: (str(v) if k == "kkt_solver" else v)
                             for k, v in mr002_piqp.BASE.items()
                             if k not in ("verbose", "compute_timings")},
            "cascade_module_imports": sorted(
                n for n in sys.modules if n.startswith(("scripts.mr002", "app.research.mr002"))),
        }
        import hashlib
        fingerprints = {
            "primary_wrapper": hashlib.sha256(
                inspect.getsource(cov._quadprog_variant).encode()).hexdigest(),
            "piqp_solve": hashlib.sha256(inspect.getsource(mr002_piqp.solve_piqp).encode()).hexdigest(),
            "canonical_qualify": hashlib.sha256(
                inspect.getsource(cov.canonical_qualify).encode()).hexdigest(),
            "certify": hashlib.sha256(inspect.getsource(cert.certify).encode()).hexdigest(),
            "resolve": hashlib.sha256(inspect.getsource(casc.resolve).encode()).hexdigest(),
        }
    except Exception as exc:  # noqa: BLE001 — import failure ⇒ empty live_config ⇒ FAIL-closed
        live_config = {"import_error": str(exc)[:200]}

    return Env(
        git_commit=_head,
        git_tree=_git("rev-parse", "HEAD^{tree}"),
        working_tree_clean=(_porcelain == "") if (_head and _porcelain is not None) else None,
        image_digest=os.environ.get("MR002_IMAGE_DIGEST"),
        oci_config_digest=os.environ.get("MR002_OCI_CONFIG_DIGEST"),
        python_version=platform.python_version(),
        python_abi=sysconfig.get_config_var("SOABI"),
        package_versions=versions,
        cpu_flags=flags,
        cpu_flags_available=flags_ok,
        env_vars={k: os.environ.get(k, "") for k in
                  ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_CORETYPE")},
        live_config=live_config,
        fingerprints=fingerprints,
    )


def run_preflight(expected: ExpectedPins, manifest: dict,
                  root: str | None = None) -> Report:  # pragma: no cover - in-image
    from scripts.mr002_stage3_source_manifest import verify_source
    defects = verify_source(manifest, root)
    return evaluate(gather_env(root), expected, defects)


def main() -> int:  # pragma: no cover - in-image
    root = os.environ.get("MR002_ROOT")
    manifest_path = os.environ.get("MR002_SOURCE_MANIFEST", "")
    if manifest_path:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    else:
        manifest = {"files": {}}
    # Expected pins are supplied by the execution countersignature; unset ⇒ FAIL-closed.
    expected = ExpectedPins(
        git_commit=os.environ.get("MR002_COMMIT_SHA"),
        git_tree=os.environ.get("MR002_TREE_SHA"),
        image_digest=os.environ.get("MR002_IMAGE_DIGEST"),
        oci_config_digest=os.environ.get("MR002_OCI_CONFIG_DIGEST"),
    )
    rep = run_preflight(expected, manifest, root)
    print(json.dumps(rep.summary(), indent=2))
    return 0 if rep.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
