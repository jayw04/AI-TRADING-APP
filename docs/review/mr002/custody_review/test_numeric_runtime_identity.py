"""Tests for WP-E / P10 — the NumericRuntimeIdentityManifest producer and gate.

P10's whole value is negative: it is a claim about what a validation run will
REFUSE to do. A producer that emits a plausible manifest is worthless if it
would also emit one when the image did not resolve, when the observation came
from a different container, or when a binding was left empty. So most of what
follows tries to obtain a manifest illegitimately and asserts that it cannot be
had.

Three properties get the most attention, because they are the three ways P10
could look satisfied while binding nothing:

  1. the container-image digest has exactly ONE source — the Requirement-7
     resolver — and no argument through which another could be supplied;
  2. the in-image observation must demonstrably come from the bound image,
     proven by rehashing all 21 evaluator modules, not by trusting the launcher;
  3. a mismatch at run time FAIL-STOPS by raising, with no sentinel a caller
     could ignore and no binding silently exempted from comparison.

No network and no Docker. The resolver and the container runner are injected;
neither injection can smuggle a pass, because the module checks the observation
against the real governed image manifest in this repository either way.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


R = _load("resolve_evaluator_image")
N = _load("numeric_runtime_identity")

IMAGE_MANIFEST = json.loads(N.IMAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
BOUND_MODULES = IMAGE_MANIFEST["module_digests_in_image"]
BOUND_DIGEST = R.BOUND_INDEX_DIGEST


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


def _observation(**overrides) -> dict:
    """A well-formed in-image observation from the bound image.

    Values are shaped like the real ones but are not real: what these tests
    check is the producer's handling, and the real values are only obtainable
    from the bound container itself.
    """
    bindings = {
        "python_version": "3.13.14",
        "numpy_version": "2.2.6",
        "scipy_version": "1.18.0",
        "pandas_version": "2.3.3",
        "blas": {"name": "scipy-openblas", "version": "0.3.29"},
        "lapack": {"name": "scipy-openblas", "version": "0.3.29"},
        "cpu_architecture": {"machine": "x86_64", "numpy_cpu_features_enabled": ["AVX2"]},
        "thread_env": {name: "1" for name in N.FROZEN_THREAD_ENV},
        "rng_algorithm": {"default_rng_bit_generator": "PCG64"},
        "locale": {"lc_all": "C", "preferred_encoding": "utf-8"},
        "timezone": {"tzname": ["UTC", "UTC"], "utc_offset_seconds": 0},
        "python_executable_identity": {"path": "/usr/local/bin/python", "sha256": "ab" * 32},
        "numpy_scipy_binary_identities": {"numpy._core._multiarray_umath": {"available": True}},
    }
    bindings.update(overrides.pop("bindings", {}))
    obs = {
        "record_type": "MR002_NumericRuntimeObservation",
        "observed_at": "2026-08-11T00:00:00Z",
        "bindings": bindings,
        "evaluator_modules": dict(BOUND_MODULES),
        "in_image": True,
    }
    obs.update(overrides)
    return obs


def _runner_returning(obs) -> tuple:
    """A fake container runner. Records the image reference it was handed."""
    calls: list[str] = []

    def runner(image_ref, capture_script):
        calls.append(image_ref)
        return obs if isinstance(obs, bytes) else json.dumps(obs).encode()

    return runner, calls


@pytest.fixture
def fake_resolver(monkeypatch):
    """Replace the resolver with a double, in the module the producer imports.

    The producer imports ``resolve_bound_image`` at point of use, so patching
    the attribute on the module object is what a production call would actually
    pick up. Patching a copy would prove nothing.
    """

    def install(record=None, raises=None):
        def resolve_bound_image(*, client=None, **_):
            if raises is not None:
                raise raises
            return record

        monkeypatch.setattr(R, "resolve_bound_image", resolve_bound_image)

    return install


def _resolution(**overrides) -> dict:
    record = {
        "record_type": "MR002_EvaluatorImageResolution",
        "resolved_at": "2026-08-11T00:00:00Z",
        "registry_id": R.REGISTRY_ID,
        "repository": R.REPOSITORY,
        "region": R.REGION,
        "image_digest": BOUND_DIGEST,
        "resolution_method": "live registry batch_get_image by imageDigest, bytes rehashed",
        "cached": False,
        "satisfies_requirement_7": True,
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# The binding set itself
# ---------------------------------------------------------------------------


def test_seventeen_bindings_and_the_spec_still_agrees():
    assert len(N.REQUIRED_BINDINGS) == 17
    assert len(set(N.REQUIRED_BINDINGS)) == 17
    spec = N._load_spec()
    assert len(spec["required_bindings"]) == 17
    N._assert_spec_agrees(spec)  # must not raise


def test_spec_gaining_an_eighteenth_binding_refuses_production():
    """The one drift that would otherwise pass every other test in this file."""
    spec = dict(N._load_spec())
    spec["required_bindings"] = [*spec["required_bindings"], "an eighteenth thing"]
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N._assert_spec_agrees(spec)
    assert exc.value.reason == "binding_count_drift"


def test_in_image_and_host_bindings_partition_the_seventeen():
    assert set(N.IN_IMAGE_BINDINGS) | N.HOST_SUPPLIED_BINDINGS == set(N.REQUIRED_BINDINGS)
    assert not set(N.IN_IMAGE_BINDINGS) & N.HOST_SUPPLIED_BINDINGS
    assert len(N.IN_IMAGE_BINDINGS) == 13


def test_no_binding_is_exempt_from_comparison():
    """If someone exempts a binding, this test is the thing they must edit."""
    assert len(N.NON_IDENTITY_BINDINGS) == 0


# ---------------------------------------------------------------------------
# The container-image digest has exactly one source
# ---------------------------------------------------------------------------


def test_producer_accepts_no_digest_parameter():
    """Structural enforcement of 'the resolver is the sole permitted path'.

    A comment saying "do not pass a digest" is satisfied by not passing one. A
    signature with nowhere to put one is satisfied by the language.
    """
    params = inspect.signature(N.produce_p10_manifest).parameters
    assert not [p for p in params if "digest" in p.lower()]
    assert not [p for p in params if "image" in p.lower() and p != "image_manifest"]
    assert not [p for p in params if "tag" in p.lower()]


def test_resolver_refusal_refuses_production_with_no_fallback(fake_resolver):
    fake_resolver(raises=R.ImageResolutionRefused("registry_unavailable", "no network"))
    runner, calls = _runner_returning(_observation())
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "image_resolution_refused"
    assert "registry_unavailable" in exc.value.detail
    # The decisive assertion: no container was launched. A producer that fell
    # back to a tag or a cached image would have run one anyway.
    assert calls == []


def test_resolution_not_asserting_requirement_7_is_refused(fake_resolver):
    """A custody-monitor receipt is the shape this rejects."""
    fake_resolver(record=_resolution(satisfies_requirement_7=False))
    runner, _ = _runner_returning(_observation())
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "resolution_does_not_satisfy_requirement_7"


def test_container_is_launched_by_the_resolved_digest_never_a_tag(fake_resolver):
    fake_resolver(record=_resolution())
    runner, calls = _runner_returning(_observation())
    N.produce_p10_manifest(runner=runner)
    assert calls == [f"{N.ECR_REPOSITORY_URI}@{BOUND_DIGEST}"]
    assert ":latest" not in calls[0]
    assert "qualify-" not in calls[0]


def test_bound_digest_is_carried_verbatim_into_the_manifest(fake_resolver):
    fake_resolver(record=_resolution())
    runner, _ = _runner_returning(_observation())
    manifest = N.produce_p10_manifest(runner=runner)
    binding = manifest["bindings"]["container_image_digest"]
    assert binding["digest"] == BOUND_DIGEST
    assert binding["digest_kind"] == "OCI image index digest"
    assert binding["sole_permitted_path"] == "resolve_evaluator_image.resolve_bound_image"


# ---------------------------------------------------------------------------
# The observation must come from the bound image
# ---------------------------------------------------------------------------


def test_observation_from_a_different_image_is_refused(fake_resolver):
    """One drifted module out of 21. A rebuild would drift all of them."""
    fake_resolver(record=_resolution())
    modules = dict(BOUND_MODULES)
    victim = sorted(modules)[0]
    modules[victim] = "0" * 64
    runner, _ = _runner_returning(_observation(evaluator_modules=modules))
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "evaluator_module_digest_mismatch"
    assert victim in exc.value.detail


def test_a_subset_of_the_bound_modules_is_refused(fake_resolver):
    """'Close enough' is how a different image gets accepted as this one."""
    fake_resolver(record=_resolution())
    modules = dict(BOUND_MODULES)
    modules.pop(sorted(modules)[0])
    runner, _ = _runner_returning(_observation(evaluator_modules=modules))
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "evaluator_module_set_mismatch"


def test_a_superset_of_the_bound_modules_is_refused(fake_resolver):
    fake_resolver(record=_resolution())
    modules = dict(BOUND_MODULES)
    modules["mr002_valoos_extra.py"] = "1" * 64
    runner, _ = _runner_returning(_observation(evaluator_modules=modules))
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "evaluator_module_set_mismatch"


def test_an_observation_with_no_modules_at_all_is_refused(fake_resolver):
    fake_resolver(record=_resolution())
    runner, _ = _runner_returning(_observation(evaluator_modules={}))
    with pytest.raises(N.NumericRuntimeRefused):
        N.produce_p10_manifest(runner=runner)


def test_malformed_or_mislabelled_observations_are_refused(fake_resolver):
    fake_resolver(record=_resolution())
    for payload, reason in (
        (b"not json", "malformed_observation"),
        (json.dumps({"record_type": "something_else"}).encode(), "malformed_observation"),
    ):
        runner, _ = _runner_returning(payload)
        with pytest.raises(N.NumericRuntimeRefused) as exc:
            N.produce_p10_manifest(runner=runner)
        assert exc.value.reason == reason


def test_an_observation_claiming_a_host_binding_is_refused(fake_resolver):
    """The tempting shortcut: read the digest off the local Docker daemon."""
    fake_resolver(record=_resolution())
    runner, _ = _runner_returning(
        _observation(bindings={"container_image_digest": {"digest": BOUND_DIGEST}})
    )
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "observation_claims_host_bindings"
    assert "container_image_digest" in exc.value.detail


def test_an_observation_missing_an_in_image_binding_is_refused(fake_resolver):
    fake_resolver(record=_resolution())
    obs = _observation()
    obs["bindings"].pop("blas")
    runner, _ = _runner_returning(obs)
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "observation_incomplete"


def test_a_runtime_whose_rng_is_not_the_registered_one_is_refused(fake_resolver):
    fake_resolver(record=_resolution())
    runner, _ = _runner_returning(
        _observation(bindings={"rng_algorithm": {"default_rng_bit_generator": "MT19937"}})
    )
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner)
    assert exc.value.reason == "rng_algorithm_mismatch"


# ---------------------------------------------------------------------------
# The dependency lockfile
# ---------------------------------------------------------------------------


def test_lockfile_binds_to_the_hash_the_image_was_built_from(fake_resolver):
    fake_resolver(record=_resolution())
    runner, _ = _runner_returning(_observation())
    manifest = N.produce_p10_manifest(runner=runner)
    assert (
        manifest["bindings"]["dependency_lockfile_sha256"]
        == IMAGE_MANIFEST["build_inputs"]["dependency_lock_sha256"]
    )


def test_a_drifted_lockfile_is_refused(fake_resolver, tmp_path):
    """Binding a lock the image was not built from records a false provenance."""
    fake_resolver(record=_resolution())
    other = tmp_path / "MR002_Increment1_Dependencies.json"
    other.write_text('{"record_type": "not the bound lock"}', encoding="utf-8")
    runner, _ = _runner_returning(_observation())
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner, lock_path=other)
    assert exc.value.reason == "dependency_lock_mismatch"


def test_an_absent_lockfile_is_refused(fake_resolver, tmp_path):
    fake_resolver(record=_resolution())
    runner, _ = _runner_returning(_observation())
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.produce_p10_manifest(runner=runner, lock_path=tmp_path / "absent.json")
    assert exc.value.reason == "dependency_lock_absent"


# ---------------------------------------------------------------------------
# Completeness — placeholder completion is not completion
# ---------------------------------------------------------------------------


def test_a_produced_manifest_populates_all_seventeen(fake_resolver):
    fake_resolver(record=_resolution())
    runner, _ = _runner_returning(_observation())
    manifest = N.produce_p10_manifest(runner=runner)
    assert manifest["record_type"] == "NumericRuntimeIdentityManifest"
    assert manifest["prerequisite"] == "P10"
    assert set(manifest["bindings"]) == set(N.REQUIRED_BINDINGS)
    assert "FAIL-STOP" in manifest["mismatch_policy"]
    assert manifest["provenance"]["evaluator_modules_verified"] == len(BOUND_MODULES)
    # A prerequisite is never an authorization.
    assert manifest["authorizes"].startswith("NOTHING")


@pytest.mark.parametrize("placeholder", [None, "", {}, []])
def test_placeholder_completion_is_not_completion(placeholder):
    bindings = {k: "populated" for k in N.REQUIRED_BINDINGS}
    bindings["blas"] = placeholder
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N._assert_bindings_complete(bindings)
    assert exc.value.reason == "bindings_incomplete"
    assert "blas" in exc.value.detail


def test_a_missing_binding_is_refused():
    bindings = {k: "populated" for k in N.REQUIRED_BINDINGS if k != "timezone"}
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N._assert_bindings_complete(bindings)
    assert "timezone" in exc.value.detail


def test_a_binding_the_spec_does_not_name_is_refused():
    bindings = {k: "populated" for k in N.REQUIRED_BINDINGS}
    bindings["favourite_colour"] = "blue"
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N._assert_bindings_complete(bindings)
    assert exc.value.reason == "bindings_unexpected"


# ---------------------------------------------------------------------------
# The in-image leg's own refusals
# ---------------------------------------------------------------------------


def test_capture_refuses_when_threading_is_not_frozen(monkeypatch):
    """An unset variable is the host default, and a host default is not frozen."""
    for name in N.FROZEN_THREAD_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.capture_numeric_runtime(require_in_image=False)
    assert exc.value.reason == "threading_not_frozen"
    for name in N.FROZEN_THREAD_ENV:
        assert name in exc.value.detail


def test_capture_refuses_outside_the_evaluator_image(monkeypatch, tmp_path):
    for name in N.FROZEN_THREAD_ENV:
        monkeypatch.setenv(name, "1")
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.capture_numeric_runtime(evaluator_root=str(tmp_path / "nope"))
    assert exc.value.reason == "not_running_in_evaluator_image"


def test_capture_emits_exactly_the_thirteen_in_image_bindings(monkeypatch):
    for name in N.FROZEN_THREAD_ENV:
        monkeypatch.setenv(name, "1")
    observation = N.capture_numeric_runtime(require_in_image=False)
    assert set(observation["bindings"]) == set(N.IN_IMAGE_BINDINGS)
    assert observation["record_type"] == "MR002_NumericRuntimeObservation"


# ---------------------------------------------------------------------------
# The run-time gate — FAIL-STOP before any metric
# ---------------------------------------------------------------------------


def _bound_manifest_from_this_runtime(monkeypatch) -> dict:
    for name in N.FROZEN_THREAD_ENV:
        monkeypatch.setenv(name, "1")
    observation = N.capture_numeric_runtime(require_in_image=False)
    bindings = dict(observation["bindings"])
    bindings["solver_driver"] = {"solver": "numpy.linalg.lstsq"}
    bindings["registered_seeds"] = {"bootstrap_seed": 20260711}
    bindings["dependency_lockfile_sha256"] = "17a7" * 16
    bindings["container_image_digest"] = {"digest": BOUND_DIGEST}
    return {
        "record_type": "NumericRuntimeIdentityManifest",
        "prerequisite": "P10",
        "bindings": bindings,
    }


def test_gate_passes_on_the_runtime_it_was_produced_from(monkeypatch):
    bound = _bound_manifest_from_this_runtime(monkeypatch)
    assert (
        N.require_numeric_runtime(bound, resolve_image_digest=lambda: BOUND_DIGEST)
        is None
    )


def test_gate_returns_none_rather_than_a_boolean(monkeypatch):
    """A boolean return invites `if not verify(): log.warning(...)`."""
    bound = _bound_manifest_from_this_runtime(monkeypatch)
    result = N.require_numeric_runtime(bound, resolve_image_digest=lambda: BOUND_DIGEST)
    assert result is None
    assert not isinstance(result, bool)


@pytest.mark.parametrize(
    "binding",
    ["numpy_version", "blas", "cpu_architecture", "thread_env", "python_version"],
)
def test_gate_fail_stops_on_each_class_of_numeric_drift(monkeypatch, binding):
    bound = _bound_manifest_from_this_runtime(monkeypatch)
    bound["bindings"][binding] = {"deliberately": "different"}
    with pytest.raises(N.NumericRuntimeMismatch) as exc:
        N.require_numeric_runtime(bound, resolve_image_digest=lambda: BOUND_DIGEST)
    assert [d["binding"] for d in exc.value.differences] == [binding]
    assert "FAIL-STOP before any metric" in str(exc.value)


def test_gate_reports_every_difference_not_just_the_first(monkeypatch):
    bound = _bound_manifest_from_this_runtime(monkeypatch)
    for binding in ("numpy_version", "scipy_version", "pandas_version"):
        bound["bindings"][binding] = "0.0.0"
    with pytest.raises(N.NumericRuntimeMismatch) as exc:
        N.require_numeric_runtime(bound, resolve_image_digest=lambda: BOUND_DIGEST)
    assert len(exc.value.differences) == 3


def test_gate_fail_stops_when_the_image_no_longer_resolves_to_the_bound_digest(
    monkeypatch,
):
    """A matching numeric runtime on a different image is still the wrong run."""
    bound = _bound_manifest_from_this_runtime(monkeypatch)
    with pytest.raises(N.NumericRuntimeMismatch) as exc:
        N.require_numeric_runtime(
            bound, resolve_image_digest=lambda: "sha256:" + "0" * 64
        )
    assert [d["binding"] for d in exc.value.differences] == ["container_image_digest"]


def test_gate_requires_a_resolver_and_will_not_default_to_none(monkeypatch):
    bound = _bound_manifest_from_this_runtime(monkeypatch)
    with pytest.raises(TypeError):
        N.require_numeric_runtime(bound)  # resolve_image_digest is keyword-required
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.require_numeric_runtime(bound, resolve_image_digest=None)
    assert exc.value.reason == "no_image_resolver"


def test_gate_refuses_a_manifest_that_is_not_a_p10_instance():
    for candidate in (
        {"record_type": "MR002_NumericRuntimeObservation", "bindings": {}},
        {"record_type": "NumericRuntimeIdentityManifest"},
    ):
        with pytest.raises(N.NumericRuntimeRefused) as exc:
            N.require_numeric_runtime(candidate, resolve_image_digest=lambda: BOUND_DIGEST)
        assert exc.value.reason in {"not_a_p10_manifest", "bindings_incomplete"}


def test_gate_refuses_a_manifest_with_an_incomplete_binding_set():
    bound = {
        "record_type": "NumericRuntimeIdentityManifest",
        "bindings": {k: "x" for k in N.REQUIRED_BINDINGS if k != "blas"},
    }
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N.require_numeric_runtime(bound, resolve_image_digest=lambda: BOUND_DIGEST)
    assert exc.value.reason == "bindings_incomplete"


# ---------------------------------------------------------------------------
# Refusals are distinguishable from mismatches
# ---------------------------------------------------------------------------


def test_refusal_and_mismatch_are_different_exception_types():
    """Conflating them would let an operator retry a mismatch until it passed."""
    assert not issubclass(N.NumericRuntimeMismatch, N.NumericRuntimeRefused)
    assert not issubclass(N.NumericRuntimeRefused, N.NumericRuntimeMismatch)


def test_every_refusal_carries_a_machine_readable_reason():
    exc = N.NumericRuntimeRefused("some_reason", "some detail")
    assert exc.reason == "some_reason"
    assert exc.detail == "some detail"


# ---------------------------------------------------------------------------
# The in-image leg must be IMPORTABLE from outside the repository
#
# Regression: the first real capture on the qualified Phase 3C host failed with
# IndexError before observing a single binding. `REPO` was computed at module
# scope as `parents[2]`, which does not exist when the script is bind-mounted at
# /tmp/mr002_capture.py. Every test above injects a fake runner, so the real
# `_default_runner` bind-mount contract was never executed and the suite stayed
# green against a producer that could not run in the image it binds.
# ---------------------------------------------------------------------------


def test_repo_root_resolves_normally_inside_the_repo_layout():
    resolved = N._repo_root(Path("/srv/checkout/scripts/mr002_custody/mod.py"))
    assert resolved == Path("/srv/checkout")


def test_repo_root_falls_back_when_bind_mounted_outside_the_repo():
    """/tmp/mr002_capture.py has two parents, not three. This must not raise."""
    assert N._repo_root(Path("/tmp/mr002_capture.py").resolve()) == N.NO_REPO


def test_module_level_code_survives_a_shallow_file_path():
    """Execute the module's own top level with a container-style __file__.

    This is the check that would have caught the defect: it exercises real
    module-level execution rather than asserting on a helper.
    """
    source = (MODULE_DIR / "numeric_runtime_identity.py").read_text(encoding="utf-8")
    namespace = {"__file__": str(Path("/tmp/mr002_capture.py")), "__name__": "not_main"}
    exec(compile(source, "/tmp/mr002_capture.py", "exec"), namespace)  # noqa: S102
    assert namespace["REPO"] == namespace["NO_REPO"]


def test_host_leg_paths_still_refuse_under_the_sentinel_root():
    """The fallback must fail CLOSED, not substitute a usable default."""
    with pytest.raises(N.NumericRuntimeRefused) as exc:
        N._load_json(N.NO_REPO / "docs" / "anything.json", "spec_unavailable")
    assert exc.value.reason == "spec_unavailable"


def test_in_image_leg_needs_none_of_the_repo_derived_constants():
    """Why the sentinel is safe: the capture leg never reads them."""
    import inspect

    body = inspect.getsource(N.capture_numeric_runtime)
    for name in ("SPEC_PATH", "IMAGE_MANIFEST_PATH", "DEPENDENCY_LOCK_PATH", "REPO"):
        assert name not in body
