"""MR-002 Stage-3 — preflight validator tests (review finding 3).

Exercises the PURE `evaluate(env, expected, source_defects)` so every provenance/environment gate's
fail-closed behavior is proven without the pinned image. One matched (env, expected) pair passes; each
test then perturbs a single input and asserts that gate FAILs and the overall report is not passed.
"""

from __future__ import annotations

import dataclasses

from scripts import mr002_stage3_preflight as pf

FULL = "a" * 64
FULL2 = "b" * 64

MATERIAL = {"registered_acceptance_LIMITS": {"kkt_residual": 1e-8}, "signed_gap_band": [-1e-10, 1e-10]}
# the CLOSED mandatory fingerprint set (cycle-3 finding 20)
FINGERPRINTS = {"primary_wrapper": "fp1", "piqp_solve": "fp2", "canonical_qualify": "fp3",
                "certify": "cafef00d", "resolve": "deadbeef"}
# the full closed package set (finding 18)
PKGS = {"numpy": "2.2.6", "scipy": "1.18.0", "quadprog": "0.1.13", "piqp": "0.4.2",
        "clarabel": "0.9.0", "highspy": "1.7.2", "mpmath": "1.3.0"}


def good_expected() -> pf.ExpectedPins:
    return pf.ExpectedPins(
        git_commit="c" * 40, git_tree="t" * 40,
        image_digest=f"sha256:{FULL}", oci_config_digest=f"sha256:{FULL2}",
        python_version="3.12.5", python_abi="cpython-312-x86_64-linux-gnu",
        package_versions=dict(PKGS),
        material_config=MATERIAL, fingerprints=FINGERPRINTS,
    )


def good_env() -> pf.Env:
    return pf.Env(
        git_commit="c" * 40, git_tree="t" * 40, working_tree_clean=True,
        image_digest=f"sha256:{FULL}", oci_config_digest=f"sha256:{FULL2}",
        python_version="3.12.5", python_abi="cpython-312-x86_64-linux-gnu",
        package_versions=dict(PKGS),
        cpu_flags=frozenset({"avx2", "fma", "sse4_2"}), cpu_flags_available=True,
        env_vars={"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
                  "MKL_NUM_THREADS": "1", "OPENBLAS_CORETYPE": "HASWELL"},
        live_config={**MATERIAL,
                     "registered_corpus_hash": pf.ExpectedPins().corpus_hash,
                     "cascade_module_imports": ["scripts.mr002_coverage_signed_gap",
                                                "app.research.mr002.certificate"]},
        fingerprints=FINGERPRINTS,
    )


def test_fully_matched_environment_passes():
    rep = pf.evaluate(good_env(), good_expected(), [])
    assert rep.passed, rep.summary()["failed"]


def _fails(env=None, expected=None, defects=None, check=None):
    rep = pf.evaluate(env or good_env(), expected or good_expected(), defects or [])
    assert not rep.passed
    if check:
        assert check in rep.summary()["failed"], rep.summary()["failed"]
    return rep


def test_source_defects_fail_closed():
    _fails(defects=["SHA256_DRIFT:apps/backend/scripts/mr002_piqp.py"], check="source_manifest")


def test_commit_mismatch_fails():
    _fails(env=dataclasses.replace(good_env(), git_commit="d" * 40), check="git_commit")


def test_tree_mismatch_fails():
    _fails(env=dataclasses.replace(good_env(), git_tree="z" * 40), check="git_tree")


def test_dirty_working_tree_fails():
    _fails(env=dataclasses.replace(good_env(), working_tree_clean=False), check="working_tree_clean")


def test_missing_commit_pin_fails_closed():
    _fails(expected=dataclasses.replace(good_expected(), git_commit=None), check="git_commit")


def test_truncated_oci_digest_fails():
    # finding 22 — a short prefix like sha256:770553aeae6c is not a bindable digest.
    exp = dataclasses.replace(good_expected(), oci_config_digest="sha256:770553aeae6c")
    env = dataclasses.replace(good_env(), oci_config_digest="sha256:770553aeae6c")
    _fails(env=env, expected=exp, check="oci_config_digest")


def test_image_digest_must_be_full_and_match():
    _fails(env=dataclasses.replace(good_env(), image_digest="sha256:aa930021"),
           expected=dataclasses.replace(good_expected(), image_digest="sha256:aa930021"),
           check="image_digest")


def test_avx512_present_fails():
    env = dataclasses.replace(good_env(), cpu_flags=frozenset({"avx2", "avx512f"}))
    _fails(env=env, check="cpu_avx512_absent")


def test_avx2_absent_fails():
    env = dataclasses.replace(good_env(), cpu_flags=frozenset({"sse4_2"}))
    _fails(env=env, check="cpu_avx2_present")


def test_cpu_flags_unavailable_fails_closed():
    env = dataclasses.replace(good_env(), cpu_flags=frozenset(), cpu_flags_available=False)
    rep = _fails(env=env, check="cpu_avx2_present")
    assert "cpu_avx512_absent" in rep.summary()["failed"]


def test_thread_env_not_pinned_fails():
    env = dataclasses.replace(good_env(),
                              env_vars={**good_env().env_vars, "OMP_NUM_THREADS": "8"})
    _fails(env=env, check="thread_env")


def test_openblas_coretype_wrong_fails():
    env = dataclasses.replace(good_env(),
                              env_vars={**good_env().env_vars, "OPENBLAS_CORETYPE": "SKYLAKEX"})
    _fails(env=env, check="openblas_coretype")


def test_package_version_mismatch_fails():
    env = dataclasses.replace(good_env(), package_versions={**PKGS, "piqp": "9.9.9"})
    _fails(env=env, check="package_versions")


def test_no_package_pins_fails_closed():
    _fails(expected=dataclasses.replace(good_expected(), package_versions={}),
           check="package_versions")


def test_incomplete_package_pins_fail_closed():
    # a countersignature pinning only numpy+piqp leaves scipy/quadprog/clarabel/highspy/mpmath open
    _fails(expected=dataclasses.replace(good_expected(),
                                        package_versions={"numpy": "2.2.6", "piqp": "0.4.2"}),
           check="package_versions")


def test_unapproved_module_loaded_fails():
    env = dataclasses.replace(
        good_env(),
        live_config={**good_env().live_config,
                     "cascade_module_imports": ["scripts.mr002_coverage_signed_gap",
                                                "scripts.mr002_renamed_quarantine_loader"]})
    _fails(env=env, check="cascade_import_hygiene")


def test_material_config_mismatch_fails():
    env = dataclasses.replace(good_env(),
                              live_config={**good_env().live_config,
                                           "registered_acceptance_LIMITS": {"kkt_residual": 1e-6}})
    _fails(env=env, check="material_config")


def test_corpus_hash_mismatch_fails():
    env = dataclasses.replace(good_env(),
                              live_config={**good_env().live_config, "registered_corpus_hash": "beef"})
    _fails(env=env, check="corpus_hash_constant")


def test_fingerprint_mismatch_fails():
    env = dataclasses.replace(good_env(), fingerprints={**FINGERPRINTS, "resolve": "changed"})
    _fails(env=env, check="solver_certifier_fingerprints")


def test_partial_fingerprint_pin_set_fails_closed():
    # cycle-3 finding 20 — a pin set covering only 2 of the 5 mandatory callables must fail
    _fails(expected=dataclasses.replace(good_expected(),
                                        fingerprints={"resolve": "deadbeef", "certify": "cafef00d"}),
           check="solver_certifier_fingerprints")


def test_extra_package_pin_fails_closed():
    # cycle-3 finding 22 — an extra name in the pin map is rejected, the set is exactly closed
    _fails(expected=dataclasses.replace(good_expected(),
                                        package_versions={**PKGS, "leftpad": "1.0"}),
           check="package_versions")


def test_extra_material_config_key_fails_two_way():
    # cycle-3 finding 21 — an extra observed key INSIDE a material section fails
    env = dataclasses.replace(
        good_env(),
        live_config={**good_env().live_config,
                     "registered_acceptance_LIMITS": {"kkt_residual": 1e-8, "extra_gate": 1.0}})
    _fails(env=env, check="material_config")


def test_cascade_import_hygiene_detects_quarantined_import():
    env = dataclasses.replace(
        good_env(),
        live_config={**good_env().live_config,
                     "cascade_module_imports": ["scripts.mr002_coverage_signed_gap",
                                                "scripts.mr002_full_population"]})
    _fails(env=env, check="cascade_import_hygiene")


def test_empty_report_is_not_passed():
    assert pf.Report().passed is False
