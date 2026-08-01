"""R5e-2 — the enforced witness carrier and the production composition root.

Two properties are under test:

  1. **A `SessionRuntime` cannot be assembled with an unenforced witness.** R5e-1 built the gate; nothing
     required the runner to pass through it, because the signer, verifier and sink were three
     independently injectable fields.

  2. **The composition root resolves everything from the governed configuration**, establishing
     deployment identity and the witness before any data work, and failing closed rather than defaulting.

The carrier's contract is stated as a matrix rather than a slogan, because the first attempt was wrong
in a way a slogan hid: the issuance token was a dataclass FIELD, so `dataclasses.replace()` carried it
forward and `replace(witness, signer=evil)` produced a fully "enforced" witness in one idiomatic call.
Every construction route is now pinned explicitly, including the ones that legitimately survive.

Structural invariants (which module may construct what) live in `test_production_structure.py`, which
scans every production tree with AST resolution rather than substring matching.
"""

from __future__ import annotations

import copy
import json
import os
import pickle
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.validation.forward_deployment_config import load_deployment_config
from app.validation.session_composition import CompositionError, build_session_runtime
from app.validation.session_orchestration import SessionRuntime
from app.validation.witness_enforcement import (
    ProductionWitness,
    WitnessEnforcementError,
    _can_enforce_path_guarantees,
    assert_enforced,
    describe_unenforceable_key_path,
    enforce_production_witness,
    new_invocation_identifier,
    verify_and_read_public_key,
)
from app.validation.witness_platform import PlatformUnsupported, platform_is_supported
from tests.validation import witness_doubles as wd
from tests.validation.governed_construction_fixture import install_governed_construction
from tests.validation.witness_doubles import issue_witness_for_tests

SESSION = date(2026, 7, 24)
CLI_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_forward_validation_session.py"

# The key-path guarantees are POSIX-only and a PRODUCTION witness fails closed without them, so tests
# that drive the real gate are skipped off POSIX rather than weakened. Linux CI runs all of them.
POSIX_ONLY = pytest.mark.skipif(
    not _can_enforce_path_guarantees(),
    reason="a PRODUCTION witness requires POSIX ownership/no-follow guarantees; the gate fails closed "
           "here by design, so exercising it on this platform would test nothing")


def _runtime_with(witness):
    return SessionRuntime(
        store=object(), accessor=object(), store_identity="s", universe_fn=lambda d, n: [],
        proxy_closes={}, session_dates=(), strict_price_fn=lambda s, d: 1.0,
        account4_probe=lambda: None, context_builder=lambda d: None, readiness=object(),
        witness=witness)


# ── the carrier: every construction route, stated explicitly ─────────────────────────────────────────

def test_an_ordinary_direct_construction_is_refused():
    """`ProductionWitness(...)` builds a value, but an unmarked one — and every consumer refuses it.

    The marker is attached by the gate AFTER verification, never by the constructor, precisely so that
    anything reaching `__init__` cannot acquire it.
    """
    hand_built = ProductionWitness(signer=object(), verifier=object(), sink=object(), evidence={})
    assert hand_built._is_enforced() is False
    with pytest.raises(WitnessEnforcementError) as exc:
        assert_enforced(hand_built)
    assert exc.value.code == "WITNESS_NOT_ENFORCED"


def test_dataclasses_replace_with_a_swapped_signer_is_refused():
    """THE bypass the review found. `replace()` re-runs `__init__`, so the rebuilt value has no marker.

    Before the fix this returned a genuine, fully enforced `ProductionWitness` wired to a signer no gate
    had ever seen — one idiomatic call, no private import.
    """
    good = issue_witness_for_tests("REAL-SIGNER", "V", "S")
    assert_enforced(good)                                    # the starting point really is enforced

    forged = replace(good, signer="EVIL-REFERENCE-SIGNER")
    assert forged.signer == "EVIL-REFERENCE-SIGNER"
    with pytest.raises(WitnessEnforcementError) as exc:
        assert_enforced(forged)
    assert exc.value.code == "WITNESS_NOT_ENFORCED"


def test_dataclasses_replace_is_refused_even_with_no_changed_fields():
    """A rebuild is a rebuild. Allowing an unchanged `replace()` would leave a trivial laundering step:
    replace once to strip provenance, then replace again with the swap."""
    good = issue_witness_for_tests("REAL-SIGNER", "V", "S")
    with pytest.raises(WitnessEnforcementError):
        assert_enforced(replace(good))


def test_subclass_construction_is_refused_outright():
    """A subclass could override anything while still satisfying `isinstance`, so it cannot be created
    at all."""
    with pytest.raises(TypeError, match="cannot be subclassed"):
        class _Sneaky(ProductionWitness):
            pass


def test_a_duck_typed_stand_in_is_refused():
    class _LooksLikeAWitness:
        signer = verifier = sink = object()
        evidence: dict = {}

        def _is_enforced(self):
            return True                                      # it can claim whatever it likes

    with pytest.raises(WitnessEnforcementError) as exc:
        assert_enforced(_LooksLikeAWitness())
    assert exc.value.code == "WITNESS_NOT_ENFORCED"
    assert "not an enforced ProductionWitness" in str(exc.value)


def test_a_gate_issued_witness_is_accepted_and_exposes_its_legs():
    """The mirror of every refusal above: a real carrier works, and the three legs stay reachable so the
    runner — written against `anchor_signer`/`anchor_verifier`/`external_anchor_sink` — is unchanged."""
    signer, verifier, sink = object(), object(), object()
    runtime = _runtime_with(issue_witness_for_tests(signer, verifier, sink))
    assert runtime.anchor_signer is signer
    assert runtime.anchor_verifier is verifier
    assert runtime.external_anchor_sink is sink


def test_a_session_runtime_refuses_an_unenforced_carrier():
    with pytest.raises(WitnessEnforcementError):
        _runtime_with(replace(issue_witness_for_tests("S", "V", "K"), signer="EVIL"))


# ── what survives copying, stated and tested rather than assumed ─────────────────────────────────────

def test_a_shallow_copy_of_an_issued_witness_survives():
    """Deliberate, and worth naming: `copy.copy` carries the same sentinel object, so it is an unchanged
    copy of a receipt the gate really did issue. That is not an escalation — nobody gains anything by
    holding a duplicate of a legitimate witness. Forging one the gate never issued is the threat, and
    every route to that is refused above."""
    good = issue_witness_for_tests("S", "V", "K")
    assert_enforced(copy.copy(good))


def test_a_deep_copy_is_refused_because_identity_breaks():
    """`deepcopy` rebuilds the sentinel, so the identity check fails. Fails CLOSED for the right reason
    — identity, not value — which is exactly why the check is `is` and not `==`."""
    good = issue_witness_for_tests("S", "V", "K")
    with pytest.raises(WitnessEnforcementError):
        assert_enforced(copy.deepcopy(good))


def test_a_pickle_round_trip_is_refused():
    """Unpickling reconstructs the sentinel as a new object, so a witness cannot be smuggled across a
    process boundary and presented as enforced."""
    good = issue_witness_for_tests("S", "V", "K")
    with pytest.raises(WitnessEnforcementError):
        assert_enforced(pickle.loads(pickle.dumps(good)))


def test_the_stated_limit_holds_in_process_code_can_still_forge():
    """The claim is "no honest path reaches the runner unenforced", never "the carrier is unforgeable".
    Anyone already executing arbitrary code here can call the private helper — which is exactly what the
    test doubles do, in one visible place."""
    assert_enforced(issue_witness_for_tests(object(), object(), object()))


# ── the fresh invocation identifier ──────────────────────────────────────────────────────────────────

def test_the_invocation_identifier_is_fresh_and_canonical():
    ids = {new_invocation_identifier() for _ in range(200)}
    assert len(ids) == 200                                 # no collisions inside one second
    stamp, _, suffix = next(iter(ids)).partition("-")
    assert stamp.endswith("Z") and len(stamp) == 16        # YYYYMMDDTHHMMSSZ
    assert len(suffix) == 32 and int(suffix, 16) >= 0      # a full uuid4 hex


def test_the_composition_root_generates_its_own_nonce_per_invocation(monkeypatch, tmp_path):
    """A caller-chosen nonce is a caller-chosen challenge, so the identifier is generated inside the
    resolution and never accepted from an operator."""
    from app.validation import session_composition as sc

    seen: list[str] = []
    config = _governed_config(tmp_path)
    monkeypatch.setattr(sc, "enforce_production_witness",
                        lambda cfg, *, nonce: seen.append(nonce) or issue_witness_for_tests(1, 2, 3))
    sc.resolve_witness(config)
    sc.resolve_witness(config)
    assert len(seen) == 2 and seen[0] != seen[1]


@pytest.mark.skipif(platform_is_supported(), reason="the unsupported-platform refusal")
def test_the_production_path_refuses_a_witness_off_the_supported_platform(tmp_path):
    """ADR 0047 §7: a PRODUCTION witness cannot be resolved on a platform the boundary excludes.

    Before this, the boundary lived in `app/validation/aws/platform_guard.py`, which
    `check_aws_sdk_isolation.sh` forbids the gate and the composition root from importing — so nothing
    on the production path could enforce it, and a Windows deployment would get as far as constructing
    AWS clients before failing obliquely (issue #522).

    What this pins is ORDER, not merely outcome. Off POSIX the key-path check refuses a PRODUCTION
    witness anyway, with `WITNESS_PUBLIC_KEY_PATH_UNENFORCEABLE` — so a test asserting only "it
    refused" would pass with the boundary deleted. Asserting the platform code is what distinguishes
    the two.
    """
    from app.validation import session_composition as sc

    with pytest.raises(PlatformUnsupported) as exc:
        sc.resolve_witness(_governed_config(tmp_path))
    assert exc.value.code == "AWS_WITNESS_PLATFORM_UNSUPPORTED"


def test_readiness_no_longer_uses_a_repeatable_nonce_source():
    """F3: readiness used `_now_iso()` — second resolution, so two runs inside the same second
    challenged with the SAME nonce, and a signature recorded from one satisfied the other. It now
    generates exactly one fresh identifier per invocation and uses it for both challenge and report."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_cli_under_test", CLI_PATH)
    cli = importlib.util.module_from_spec(spec)
    sys.modules["_cli_under_test"] = cli
    try:
        spec.loader.exec_module(cli)
        assert not hasattr(cli, "_now_iso"), "the repeatable nonce source must be gone"
    finally:
        sys.modules.pop("_cli_under_test", None)

    source = CLI_PATH.read_text(encoding="utf-8")
    assert "invocation_id = invocation or new_invocation_identifier()" in source
    assert "nonce=invocation_id" in source
    assert 'evidence["invocation"] = invocation_id' in source


# ── the verifying-key path: validated and read as ONE operation ──────────────────────────────────────

@POSIX_ONLY
def test_the_key_is_read_from_the_descriptor_that_was_validated(tmp_path):
    key = tmp_path / "witness.pub"
    key.write_bytes(b"\x02" * 32)
    result = verify_and_read_public_key(key, trusted_root=tmp_path)
    assert result.raw == b"\x02" * 32
    assert result.evidence.read_from_verified_descriptor is True
    assert result.evidence.ownership_and_mode_enforced is True
    assert result.evidence.components_verified[-1] == "witness.pub"
    assert result.evidence.inode is not None and result.evidence.device is not None


@POSIX_ONLY
def test_a_symlinked_key_is_refused(tmp_path):
    real = tmp_path / "real.pub"
    real.write_bytes(b"\x01" * 32)
    link = tmp_path / "link.pub"
    link.symlink_to(real)
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(link, trusted_root=tmp_path)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNTRUSTED"
    assert "symbolic link" in str(exc.value)


@POSIX_ONLY
def test_a_symlinked_ANCESTOR_is_refused(tmp_path):
    """The partial-ancestry gap: the key and its immediate parent can both be impeccable while a
    grandparent is a link the attacker controls."""
    real_dir = tmp_path / "real"
    (real_dir / "keys").mkdir(parents=True)
    (real_dir / "keys" / "witness.pub").write_bytes(b"\x01" * 32)
    linked = tmp_path / "linked"
    linked.symlink_to(real_dir, target_is_directory=True)
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(linked / "keys" / "witness.pub", trusted_root=tmp_path)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNTRUSTED"


@POSIX_ONLY
def test_a_world_writable_ANCESTOR_is_refused(tmp_path):
    """A writable grandparent lets an attacker replace the whole parent directory, key and all, without
    touching any object the old check looked at."""
    mid = tmp_path / "loose"
    (mid / "keys").mkdir(parents=True)
    key = mid / "keys" / "witness.pub"
    key.write_bytes(b"\x01" * 32)
    mid.chmod(0o777)
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(key, trusted_root=tmp_path)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNTRUSTED"
    assert "writable" in str(exc.value)


@POSIX_ONLY
def test_a_world_writable_key_file_is_refused(tmp_path):
    key = tmp_path / "loose.pub"
    key.write_bytes(b"\x03" * 32)
    key.chmod(0o666)
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(key, trusted_root=tmp_path)
    assert "writable" in str(exc.value)


@POSIX_ONLY
def test_a_key_outside_the_trusted_root_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    key = outside / "witness.pub"
    key.write_bytes(b"\x01" * 32)
    root = tmp_path / "governed"
    root.mkdir()
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(key, trusted_root=root)
    assert "outside the trusted root" in str(exc.value)


@POSIX_ONLY
def test_a_directory_is_not_a_key(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(d, trusted_root=tmp_path)
    assert "not a regular file" in str(exc.value)


@POSIX_ONLY
def test_a_missing_key_is_refused(tmp_path):
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(tmp_path / "absent.pub", trusted_root=tmp_path)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNAVAILABLE"


def test_a_relative_key_path_is_refused():
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(Path("relative/witness.pub"))
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNTRUSTED"
    assert "relative" in str(exc.value)


@pytest.mark.skipif(_can_enforce_path_guarantees(), reason="the non-POSIX fail-closed path")
def test_a_platform_that_cannot_enforce_refuses_a_production_key_path(tmp_path):
    """F5's portability rule: where the guarantees cannot be established, a PRODUCTION witness is
    refused outright rather than proceeding with an unenforced report."""
    key = tmp_path / "witness.pub"
    key.write_bytes(b"\x01" * 32)
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_and_read_public_key(key)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNENFORCEABLE"


def test_the_unenforceable_description_never_claims_a_check_it_did_not_make(tmp_path):
    evidence = describe_unenforceable_key_path(tmp_path / "witness.pub")
    assert evidence.ownership_and_mode_enforced is False
    assert evidence.read_from_verified_descriptor is False
    assert "NO key-path check was performed" in evidence.detail


# ── the composition root ─────────────────────────────────────────────────────────────────────────────

@POSIX_ONLY
def test_the_composition_root_refuses_a_store_it_cannot_open(tmp_path):
    config = _governed_config(tmp_path, factor_store_path=str(tmp_path / "absent.duckdb"))
    with pytest.raises(CompositionError) as exc:
        build_session_runtime(config, SESSION)
    assert "absent.duckdb" in str(exc.value)


@POSIX_ONLY
def test_the_bridge_refusal_lands_before_the_frozen_proxy_is_built(tmp_path, monkeypatch):
    """`build_market_proxy` is frozen and builds its own UNFILTERED basket, so the one finding that
    says its input could fabricate a return has to refuse before it runs.

    Ordering is what is pinned, not merely the outcome: a test asserting only "it refused" would pass
    with the check moved after the proxy — by which point the fabricated return has already been
    averaged into the index and the regime it drives.
    """
    from app.validation import session_composition as sc
    from app.validation.data_finality import DataReadiness

    calls: list[str] = []

    class _BridgeRisk:
        verdict = DataReadiness.NOT_READY_LINEAGE_BRIDGE_RISK
        detail = "1 lineage-excluded symbol(s) ... would bridge those disconnected segments into a " \
                 "fabricated return"

        def to_open_provenance(self):
            return {}

    class _Readiness:
        # `**kwargs` rather than a named parameter: this stub stands in for the real gate's
        # CONSTRUCTION, and the test is about refusal ORDERING, not the gate's signature. Pinning the
        # exact keywords here would make every future composition-root argument a failure in a test
        # that does not care about it.
        def __init__(self, *args, **kwargs):
            pass

        def assess(self, session):
            calls.append("finality")
            return _BridgeRisk()

    class _Store:
        def close(self):
            calls.append("store-closed")

    monkeypatch.setattr(sc, "_open_store", lambda config: _Store())
    monkeypatch.setattr(sc, "_session_calendar", lambda store, session: (session,))
    monkeypatch.setattr(sc, "_GovernedReadiness", _Readiness)
    monkeypatch.setattr(sc, "_build_proxy_closes",
                        lambda *a, **k: calls.append("proxy") or ({}, "identity"))

    with pytest.raises(CompositionError, match="fabricated return"):
        build_session_runtime(_governed_config(tmp_path), SESSION)

    assert "finality" in calls
    assert "proxy" not in calls, "the frozen market proxy was built despite a bridge-risk refusal"


def test_the_composition_root_enforces_the_witness_before_touching_data(tmp_path, monkeypatch):
    """Ordering is load-bearing: a REFERENCE-profile deployment must never reach the store."""
    from app.validation import session_composition as sc

    opened: list[str] = []
    monkeypatch.setattr(sc, "_open_store", lambda config: opened.append("opened"))
    config = _governed_config(tmp_path, profile="REFERENCE")

    with pytest.raises(WitnessEnforcementError) as exc:
        build_session_runtime(config, SESSION)
    assert exc.value.code == "WITNESS_PROFILE_NOT_PRODUCTION"
    assert opened == [], "the store was opened before the witness was enforced"


@POSIX_ONLY
def test_the_fixture_config_really_is_a_production_witness(tmp_path):
    """Guards the tests above: if the fixture stopped satisfying the gate, the ordering test would pass
    for the wrong reason."""
    config = _governed_config(tmp_path)
    witness = enforce_production_witness(config.witness, nonce=new_invocation_identifier())
    assert_enforced(witness)
    assert witness.evidence["profile"] == "PRODUCTION"
    assert witness.evidence["signer"]["key_challenge"]["challenged"] is True
    assert witness.evidence["verifying_key_path"]["read_from_verified_descriptor"] is True


# ── the memoized readiness gate ──────────────────────────────────────────────────────────────────────

def test_the_readiness_gate_assesses_a_session_once(monkeypatch):
    """Two independent assessments could disagree, binding the providers to a store identity the record
    does not attest — so one assessment serves both the composition root and the runner."""
    from app.validation import session_composition as sc

    calls: list[date] = []

    def _fake_assess(store, session_date, *, construction=None, adjustment_verifier=None):
        calls.append(session_date)
        return f"evidence-for-{session_date}"

    monkeypatch.setattr(sc, "assess_data_finality", _fake_assess)
    monkeypatch.setattr(sc, "_adjustment_verifier", lambda store, policy=None: None)
    gate = sc._GovernedReadiness(object(), None, sc.ConstructionSpec())

    first, second = gate.assess(SESSION), gate.assess(SESSION)
    assert first is second and calls == [SESSION]

    other = date(2026, 7, 27)
    gate.assess(other)
    assert calls == [SESSION, other], "a different session must be assessed on its own"


def test_memoized_evidence_cannot_leak_between_stores(monkeypatch):
    """The memo lives on an instance bound to ONE store, and each composition builds a new instance, so
    a second store never sees the first store's evidence."""
    from app.validation import session_composition as sc

    monkeypatch.setattr(sc, "_adjustment_verifier", lambda store, policy=None: None)
    monkeypatch.setattr(sc, "assess_data_finality",
                        lambda store, session_date, **kw: f"evidence-for-{store}")
    a = sc._GovernedReadiness("STORE-A", None, sc.ConstructionSpec())
    b = sc._GovernedReadiness("STORE-B", None, sc.ConstructionSpec())
    assert a.assess(SESSION) == "evidence-for-STORE-A"
    assert b.assess(SESSION) == "evidence-for-STORE-B"


def test_verify_unchanged_is_never_memoized(monkeypatch):
    """The store-unchanged property depends on re-streaming AFTER the reads; caching it would make the
    check a tautology."""
    from app.validation import session_composition as sc

    calls = []
    monkeypatch.setattr(sc, "verify_store_unchanged",
                        lambda store, session_date, expected, **kw: calls.append(session_date))
    gate = sc._GovernedReadiness(object(), None, sc.ConstructionSpec())
    gate.verify_unchanged(SESSION, "evidence")
    gate.verify_unchanged(SESSION, "evidence")
    assert calls == [SESSION, SESSION]


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────────

def _governed_config(tmp_path: Path, *, profile: str = "PRODUCTION",
                     factor_store_path: str | None = None):
    """A governed configuration complete enough to resolve, built through `load_deployment_config` so
    the test exercises the same required keys production does.

    `trusted_root` is `tmp_path` itself: pytest's temporary directories sit under a world-writable
    `/tmp`, which the key-path walk correctly refuses. Naming the root the deployment actually governs
    is exactly what the option is for.
    """
    key_path = tmp_path / "witness.pub"
    key_path.write_bytes(wd.provision_p256_service_key("svc-1"))
    if hasattr(os, "chmod"):
        key_path.chmod(0o600)

    commit = "b0058bf335628f8dbde09a93915314f3a1f7743b"
    corpus_block = install_governed_construction(tmp_path, SESSION)
    (tmp_path / "build_info.json").write_text(
        json.dumps({"commit": commit, "tree_clean": True}), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"commit": commit, "corpus": corpus_block}), encoding="utf-8")

    payload = {
        "factor_store_path": factor_store_path or str(tmp_path / "factor.duckdb"),
        "app_db_path": str(tmp_path / "app.sqlite"),
        "observation_store_dir": str(tmp_path / "store"),
        "ledger_path": str(tmp_path / "store" / "ledger.json"),
        "dgs3mo_path": str(tmp_path / "DGS3MO.csv"),
        "trial_ledger_path": str(tmp_path / "TrialLedger.json"),
        "build_info_path": str(tmp_path / "build_info.json"),
        "deployment_manifest_path": str(tmp_path / "manifest.json"),
        "corpus_manifest_path": str(tmp_path / "corpus_manifest.json"),
        "dgs3mo_manifest_path": str(tmp_path / "dgs3mo_manifest.json"),
        "deployment_model": "SOURCE_CHECKOUT",
        "ledger_account_id": 901,
        "strategy_id": 11,
        "expected_broker": "alpaca",
        "expected_broker_mode": "paper",
        "shadow_ledger_identity": "shadow-901",
        "instrument_durable_state_id": "durable-901",
        "starting_capital": 100000.0,
        "turnover_cost_bps": 10.0,
        "backstop_days": 10,
        "weight_drift_pct": 0.04,
        "witness": {
            "profile": profile,
            "trusted_root": str(tmp_path),
            "algorithm": "ECDSA_SHA_256_P256",
            "key_id": "arn:aws:kms:us-east-1:219024422756:key/1234abcd",
            "public_key_path": str(key_path),
            "signer": {"factory": "tests.validation.witness_doubles:build_p256_signer",
                       "identity": "kms://anchor-witness",
                       "options": {"handle": "svc-1", "key_arn": "arn:aws:kms:us-east-1:219024422756:key/1234abcd"}},
            "sink": {"factory": "tests.validation.witness_doubles:build_sink",
                     "identity": "s3://anchors/prod", "options": {}},
        },
    }
    path = tmp_path / "forward_validation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_deployment_config(path)
