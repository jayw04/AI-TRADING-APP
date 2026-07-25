"""R5e-2 — the enforced witness carrier and the production composition root.

Two properties are under test, and they are the whole point of the increment:

  1. **A `SessionRuntime` cannot be assembled with an unenforced witness.** R5e-1 built the gate; until
     now nothing required the runner to pass through it, because the signer, verifier and sink were
     three independently injectable fields. These tests pin that the only ordinary way to obtain the
     carrier is `enforce_production_witness`.

  2. **The composition root resolves everything from the governed configuration.** Deployment identity
     and the witness are established before any data work, the store is opened read-only, and a
     configuration that cannot produce a runnable session fails closed rather than running on defaults.

The honest limit is tested too: an actor who imports the private token can still forge a carrier. That
is stated in `ProductionWitness` and pinned here so nobody later mistakes the control for a stronger
one than it is.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.validation.forward_deployment_config import load_deployment_config
from app.validation.session_composition import CompositionError, build_session_runtime
from app.validation.session_orchestration import SessionRuntime
from app.validation.witness_enforcement import (
    ProductionWitness,
    WitnessEnforcementError,
    enforce_production_witness,
    new_invocation_identifier,
    verify_key_path,
)
from tests.validation import witness_doubles as wd
from tests.validation.witness_doubles import issue_witness_for_tests

SESSION = date(2026, 7, 24)


# ── the carrier cannot be forged by ordinary construction ────────────────────────────────────────────

def test_a_production_witness_cannot_be_constructed_directly():
    """The bypass R5e-2 exists to close: assembling the triple without the gate.

    Before this, `ProductionWitness(signer=Ed25519AnchorSigner(...), ...)` produced a carrier the runner
    accepts, wired to exactly the reference implementations the gate refuses — and it would have looked
    deliberate in review.
    """
    with pytest.raises(WitnessEnforcementError) as exc:
        ProductionWitness(signer=object(), verifier=object(), sink=object(), evidence={})
    assert exc.value.code == "WITNESS_NOT_ENFORCED"
    assert "enforce_production_witness" in str(exc.value)


def test_a_session_runtime_refuses_anything_but_an_enforced_carrier():
    """A duck-typed stand-in exposing `.signer`/`.verifier`/`.sink` must not be accepted: it would
    reintroduce the very bypass the single field closes."""

    class _LooksLikeAWitness:
        signer = verifier = sink = object()
        evidence: dict = {}

    with pytest.raises(Exception) as exc:
        SessionRuntime(
            store=object(), accessor=object(), store_identity="s", universe_fn=lambda d, n: [],
            proxy_closes={}, session_dates=(), strict_price_fn=lambda s, d: 1.0,
            account4_probe=lambda: None, context_builder=lambda d: None, readiness=object(),
            witness=_LooksLikeAWitness())
    assert "enforced ProductionWitness" in str(exc.value)


def test_the_enforced_carrier_is_accepted_and_exposes_its_legs():
    """The gate's own output is accepted, and the three legs remain reachable so the runner — which was
    written against `anchor_signer`/`anchor_verifier`/`external_anchor_sink` — is unchanged."""
    signer, verifier, sink = object(), object(), object()
    runtime = SessionRuntime(
        store=object(), accessor=object(), store_identity="s", universe_fn=lambda d, n: [],
        proxy_closes={}, session_dates=(), strict_price_fn=lambda s, d: 1.0,
        account4_probe=lambda: None, context_builder=lambda d: None, readiness=object(),
        witness=issue_witness_for_tests(signer, verifier, sink))
    assert runtime.anchor_signer is signer
    assert runtime.anchor_verifier is verifier
    assert runtime.external_anchor_sink is sink


def test_the_stated_limit_holds_an_actor_with_the_private_token_can_forge():
    """The claim made in `ProductionWitness` is exactly this, and no more.

    Pinned deliberately: a control believed to do more than it does is worse than none. Anyone already
    executing arbitrary code in this process can import the private token — so the guarantee is "no
    honest path reaches the runner unenforced", never "the carrier is unforgeable".
    """
    forged = issue_witness_for_tests(object(), object(), object())
    assert isinstance(forged, ProductionWitness)          # it really does construct


def test_only_the_doubles_module_may_reach_for_the_private_token():
    """No module under `app/` may import the issuance token. If this fails, a production path has
    acquired the ability to mint an unenforced witness."""
    app_dir = Path(__file__).resolve().parents[2] / "app"
    offenders = [p.relative_to(app_dir).as_posix() for p in app_dir.rglob("*.py")
                 if "_ISSUANCE_TOKEN" in p.read_text(encoding="utf-8")
                 and p.name != "witness_enforcement.py"]
    assert offenders == [], (
        f"these production modules reach for the private issuance token: {offenders}; the thing they "
        f"want is enforce_production_witness()")


# ── the fresh invocation identifier ──────────────────────────────────────────────────────────────────

def test_the_invocation_identifier_is_fresh_and_canonical():
    """A nonce derived from the wall clock alone repeats within the same second, and a repeated nonce
    lets a signature recorded from one challenge satisfy another."""
    ids = {new_invocation_identifier() for _ in range(200)}
    assert len(ids) == 200                                 # no collisions inside one second
    sample = next(iter(ids))
    stamp, _, suffix = sample.partition("-")
    assert stamp.endswith("Z") and len(stamp) == 16        # YYYYMMDDTHHMMSSZ
    assert len(suffix) == 32 and int(suffix, 16) >= 0      # a full uuid4 hex


def test_the_composition_root_generates_its_own_nonce_per_invocation(monkeypatch, tmp_path):
    """The nonce is generated inside the resolution, never accepted from an operator: a caller-chosen
    nonce is a caller-chosen challenge."""
    from app.validation import session_composition as sc

    seen: list[str] = []
    config = _witness_only_config(tmp_path, monkeypatch)
    monkeypatch.setattr(sc, "enforce_production_witness",
                        lambda cfg, *, nonce: seen.append(nonce) or _stub_witness())
    sc.resolve_witness(config)
    sc.resolve_witness(config)
    assert len(seen) == 2 and seen[0] != seen[1]


# ── the verifying-key path ───────────────────────────────────────────────────────────────────────────

def test_a_symlinked_verifying_key_is_refused(tmp_path):
    """Whoever can re-point the link chooses which key the signer is challenged against — and a
    substituted signer then passes the challenge perfectly."""
    real = tmp_path / "real.pub"
    real.write_bytes(b"\x01" * 32)
    link = tmp_path / "link.pub"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("this platform does not permit creating symlinks unprivileged")

    with pytest.raises(WitnessEnforcementError) as exc:
        verify_key_path(link)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNTRUSTED"
    assert "symbolic link" in str(exc.value)


def test_a_missing_verifying_key_path_is_refused(tmp_path):
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_key_path(tmp_path / "absent.pub")
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNAVAILABLE"


def test_a_directory_is_not_a_verifying_key(tmp_path):
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_key_path(tmp_path)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNTRUSTED"
    assert "not a regular file" in str(exc.value)


def test_an_ordinary_key_file_passes_and_reports_what_it_could_check(tmp_path):
    """On POSIX the evidence asserts ownership and mode were enforced; on Windows it says plainly that
    they were not, rather than claiming a check that did not happen."""
    key = tmp_path / "witness.pub"
    key.write_bytes(b"\x02" * 32)
    evidence = verify_key_path(key)
    assert evidence.path == str(key)
    assert isinstance(evidence.ownership_and_mode_enforced, bool)
    if not evidence.ownership_and_mode_enforced:
        assert "NOT performed" in evidence.detail
    else:
        assert evidence.mode is not None and evidence.owner_uid is not None


@pytest.mark.skipif(not hasattr(__import__("os"), "geteuid"), reason="POSIX ownership semantics only")
def test_a_world_writable_verifying_key_is_refused(tmp_path):
    """Anyone with write access can substitute the key the signer is challenged against."""
    key = tmp_path / "loose.pub"
    key.write_bytes(b"\x03" * 32)
    key.chmod(0o666)
    with pytest.raises(WitnessEnforcementError) as exc:
        verify_key_path(key)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_PATH_UNTRUSTED"
    assert "world-writable" in str(exc.value)


# ── the composition root resolves from configuration, and fails closed ───────────────────────────────

def test_the_composition_root_refuses_a_configuration_it_cannot_resolve(tmp_path, monkeypatch):
    """A store path that does not exist must be a governed refusal, not a crash and not a default."""
    config = _witness_only_config(tmp_path, monkeypatch,
                                  factor_store_path=str(tmp_path / "absent.duckdb"))
    with pytest.raises(CompositionError) as exc:
        build_session_runtime(config, SESSION)
    # Deployment identity and the witness both passed; the store is where it stops. A runtime must
    # never be built over a store that cannot be opened read-only.
    assert "absent.duckdb" in str(exc.value)


def test_the_composition_root_enforces_the_witness_before_touching_data(tmp_path, monkeypatch):
    """Ordering is load-bearing: a deployment whose signer is unreachable should refuse cheaply, not
    after minutes of reads. A REFERENCE-profile deployment must never reach the store."""
    from app.validation import session_composition as sc

    opened: list[str] = []
    monkeypatch.setattr(sc, "_open_store", lambda config: opened.append("opened"))
    config = _witness_only_config(tmp_path, monkeypatch, profile="REFERENCE")

    with pytest.raises(WitnessEnforcementError) as exc:
        build_session_runtime(config, SESSION)
    assert exc.value.code == "WITNESS_PROFILE_NOT_PRODUCTION"
    assert opened == [], "the store was opened before the witness was enforced"


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────────

def _stub_witness():
    return issue_witness_for_tests(object(), object(), object())


def _witness_only_config(tmp_path: Path, monkeypatch, *, profile: str = "PRODUCTION",
                         factor_store_path: str | None = None):
    """A governed configuration complete enough to resolve, pointing at a real installed public key.

    Built through `load_deployment_config` rather than by hand so the test exercises the same required
    keys production does — a config the loader would reject is not a useful fixture.
    """
    key_path = tmp_path / "witness.pub"
    key_path.write_bytes(wd.provision_service_key("svc-1"))

    # A SOURCE_CHECKOUT deployment that can identify itself. Deployment identity is established BEFORE
    # the witness, so without these the ordering tests below would refuse for the wrong reason.
    commit = "b0058bf335628f8dbde09a93915314f3a1f7743b"
    (tmp_path / "build_info.json").write_text(
        json.dumps({"commit": commit, "tree_clean": True}), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"commit": commit}), encoding="utf-8")

    payload = {
        "factor_store_path": factor_store_path or str(tmp_path / "factor.duckdb"),
        "app_db_path": str(tmp_path / "app.sqlite"),
        "observation_store_dir": str(tmp_path / "store"),
        "ledger_path": str(tmp_path / "store" / "ledger.json"),
        "dgs3mo_path": str(tmp_path / "DGS3MO.csv"),
        "trial_ledger_path": str(tmp_path / "TrialLedger.json"),
        "build_info_path": str(tmp_path / "build_info.json"),
        "deployment_manifest_path": str(tmp_path / "manifest.json"),
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
            "public_key_path": str(key_path),
            "signer": {"factory": "tests.validation.witness_doubles:build_signer",
                       "identity": "kms://anchor-witness", "options": {}},
            "sink": {"factory": "tests.validation.witness_doubles:build_sink",
                     "identity": "s3://anchors/prod", "options": {}},
        },
    }
    path = tmp_path / "forward_validation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_deployment_config(path)


def test_the_fixture_config_really_is_a_production_witness(tmp_path, monkeypatch):
    """Guards the tests above: if the fixture stopped satisfying the gate, the ordering test would pass
    for the wrong reason."""
    config = _witness_only_config(tmp_path, monkeypatch)
    witness = enforce_production_witness(config.witness, nonce=new_invocation_identifier())
    assert isinstance(witness, ProductionWitness)
    assert witness.evidence["profile"] == "PRODUCTION"
    assert witness.evidence["signer"]["key_challenge"]["challenged"] is True


def test_the_composition_root_is_the_only_production_builder_of_a_runtime():
    """`SessionRuntime(` must not be constructed anywhere in `app/` except the composition root. A
    second builder would be a second place the witness could be wired, which is the thing R5e-2
    removes."""
    app_dir = Path(__file__).resolve().parents[2] / "app"
    builders = sorted(p.relative_to(app_dir).as_posix() for p in app_dir.rglob("*.py")
                      if "SessionRuntime(" in p.read_text(encoding="utf-8"))
    assert builders == ["validation/session_composition.py"], (
        f"unexpected SessionRuntime construction sites in app/: {builders}")


def test_the_readiness_gate_assesses_a_session_once(tmp_path, monkeypatch):
    """The composition root assesses to obtain the store identity; the runner assesses as the first
    step of its governed sequence. Two independent assessments could disagree, and the providers would
    then be bound to a store identity the record does not attest — so one assessment serves both."""
    from app.validation import session_composition as sc

    calls: list[date] = []

    def _fake_assess(store, session_date, *, construction=None, adjustment_verifier=None):
        calls.append(session_date)
        return f"evidence-for-{session_date}"

    monkeypatch.setattr(sc, "assess_data_finality", _fake_assess)
    monkeypatch.setattr(sc, "_adjustment_verifier", lambda store: None)
    gate = sc._GovernedReadiness(object(), None, sc.ConstructionSpec())

    first, second = gate.assess(SESSION), gate.assess(SESSION)
    assert first is second and calls == [SESSION]

    other = date(2026, 7, 27)
    gate.assess(other)
    assert calls == [SESSION, other], "a different session must be assessed on its own"


def test_verify_unchanged_is_never_memoized(tmp_path, monkeypatch):
    """The store-unchanged property depends on re-streaming AFTER the reads. Caching that would turn
    the check into a tautology."""
    from app.validation import session_composition as sc

    calls = []
    monkeypatch.setattr(sc, "verify_store_unchanged",
                        lambda store, session_date, expected, **kw: calls.append(session_date))
    gate = sc._GovernedReadiness(object(), None, sc.ConstructionSpec())
    gate.verify_unchanged(SESSION, "evidence")
    gate.verify_unchanged(SESSION, "evidence")
    assert calls == [SESSION, SESSION]


def test_the_runner_has_exactly_one_production_construction_site():
    """`ForwardSessionRunner` still takes the three witness legs as independent optional fields — it is
    the lower-level component, and its own tests construct it directly.

    DISCLOSED RESIDUAL: that means the runner itself is not gated; a caller constructing one by hand
    could pass R5d's reference implementations. What R5e-2 establishes is that the PRODUCTION path to
    it is singular — composition root → SessionRuntime → run_production_session — so no honest route
    reaches the runner unenforced. Gating the runner's own fields would be a further increment, not
    something to assume from this one.
    """
    app_dir = Path(__file__).resolve().parents[2] / "app"
    sites = sorted(p.relative_to(app_dir).as_posix() for p in app_dir.rglob("*.py")
                   if "ForwardSessionRunner(" in p.read_text(encoding="utf-8"))
    assert sites == ["validation/session_orchestration.py"], (
        f"a second production path to the runner appeared: {sites}; it would bypass the enforced "
        f"witness the SessionRuntime carries")
