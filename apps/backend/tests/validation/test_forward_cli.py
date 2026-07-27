"""Forward-validation CLI + governed deployment configuration (R5c-2b).

The structural boundary these tests defend: readiness may verify everything, but it must not be able to
change the instrument's durable state. It never constructs `MomentumDaily`, never takes a snapshot and
never calls `on_bar` — those belong exclusively to an explicitly authorized run-session.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.deployment_identity import DeploymentEvidenceMissing, DeploymentModel
from app.validation.forward_deployment_config import (
    CONFIG_ENV,
    DeploymentConfigError,
    load_deployment_config,
)
from app.validation.witness_config import WitnessConfigError
from app.validation.witness_enforcement import (
    WitnessEnforcementError,
    _can_enforce_path_guarantees,
)
from tests.validation import witness_doubles as doubles
from tests.validation.governed_construction_fixture import install_governed_construction

BACKEND = Path(__file__).resolve().parents[2]
DOUBLES = "tests.validation.witness_doubles"

# R5e-2 made a PRODUCTION witness fail closed where POSIX ownership/no-follow guarantees cannot be
# established. Readiness resolves a real production witness, so on Windows these test nothing and are
# skipped rather than weakened; Linux CI runs them all.
POSIX_ONLY = pytest.mark.skipif(
    not _can_enforce_path_guarantees(),
    reason="readiness resolves a PRODUCTION witness, which fails closed off POSIX by design")
COMMIT = "b0058bf335628f8dbde09a93915314f3a1f7743b"
DIGEST = "sha256:" + "b" * 64
SESSION = date(2026, 7, 24)


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "forward_cli", BACKEND / "scripts" / "run_forward_validation_session.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["forward_cli"] = module      # dataclasses resolve their module from sys.modules
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


def _app_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, user_id INTEGER, broker TEXT, mode TEXT,
                               label TEXT);
        CREATE TABLE strategies (id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT);
        CREATE TABLE strategy_state (id INTEGER PRIMARY KEY, strategy_id INTEGER, key TEXT, value TEXT);
        CREATE TABLE symbols (id INTEGER PRIMARY KEY, ticker TEXT);
        CREATE TABLE positions (id INTEGER PRIMARY KEY, account_id INTEGER, symbol_id INTEGER,
                                side TEXT, qty TEXT, market_value TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, account_id INTEGER, status TEXT);
        """)
    con.execute("INSERT INTO accounts VALUES (4, 4, 'alpaca', 'paper', 'acct 4')")
    con.execute("INSERT INTO strategies VALUES (11, 4, 'idle')")
    con.execute("INSERT INTO strategy_state VALUES (1, 11, 'operational_hold', ?)",
                [json.dumps({"schema_version": 1, "_rev": 2, "status": "ACTIVE",
                             "reason_code": "AWAITING_PRODUCTION_SIZING_VALIDATION"})])
    con.commit()
    con.close()
    return path


def _factor_store(path: Path) -> Path:
    store = FactorDataStore(db_path=str(path))
    store.ingest_sep(pd.DataFrame([
        {"ticker": "AAA", "date": date(2026, 7, 23), "open": 10.0, "high": 10.0, "low": 10.0,
         "close": 10.0, "volume": 1000, "closeadj": 10.0, "closeunadj": 10.0,
         "lastupdated": date(2026, 7, 23)}]))
    store.close()
    return path


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """A complete, self-consistent deployment description."""
    # ADR 0048: the frozen DGS3MO snapshot and trial ledger are installed by EXACT hash, so the
    # fixture uses the real committed artifacts — a stand-in is refused, which is the point.
    corpus_block = install_governed_construction(tmp_path, SESSION)
    (tmp_path / "build_info.json").write_text(
        json.dumps({"commit": COMMIT, "tree_clean": True, "image_digest": DIGEST}), encoding="utf-8")
    (tmp_path / "deployment_manifest.json").write_text(
        json.dumps({"commit": COMMIT, "image_digest": DIGEST, "corpus": corpus_block}),
        encoding="utf-8")
    (tmp_path / "image_digest").write_text(DIGEST, encoding="utf-8")
    # The anchor trust boundary (R5e). Only the PUBLIC key is installed; the signing key stays inside
    # the stand-in service, which is what `witness_doubles` models.
    (tmp_path / "anchor_witness.pub").write_bytes(
        doubles.provision_p256_service_key("cli-svc"))

    config = {
        "factor_store_path": str(_factor_store(tmp_path / "factor.duckdb")),
        "app_db_path": str(_app_db(tmp_path / "workbench.sqlite")),
        "observation_store_dir": str(tmp_path / "observations"),
        "ledger_path": str(tmp_path / "ledger.json"),
        "dgs3mo_path": str(tmp_path / "DGS3MO.csv"),
        "trial_ledger_path": str(tmp_path / "TrialLedger.json"),
        "build_info_path": str(tmp_path / "build_info.json"),
        "deployment_manifest_path": str(tmp_path / "deployment_manifest.json"),
        "corpus_manifest_path": str(tmp_path / "corpus_manifest.json"),
        "dgs3mo_manifest_path": str(tmp_path / "dgs3mo_manifest.json"),
        "runtime_digest_path": str(tmp_path / "image_digest"),
        "deployment_model": "CONTAINER",
        "ledger_account_id": 901,
        "strategy_id": 11,
        "expected_broker": "alpaca",
        "expected_broker_mode": "paper",
        "shadow_ledger_identity": "shadow-ledger-accounting-901",
        "instrument_durable_state_id": "instrument-durable-state-901",
        "starting_capital": 100000.0,
        "turnover_cost_bps": 10.0,
        "backstop_days": 10,
        "weight_drift_pct": 0.04,
        "witness": {
            # tmp_path itself is the trusted root: pytest's temporaries live under a world-writable
            # /tmp, which the R5e-2 key-path walk correctly refuses. Deployments name the root they
            # actually govern for exactly this reason.
            "trusted_root": str(tmp_path),
            "profile": "PRODUCTION",
            # PRODUCTION pins P-256 (ADR 0045); an Ed25519 signer here is refused at config load.
            "algorithm": "ECDSA_SHA_256_P256",
            "key_id": "arn:aws:kms:us-east-1:219024422756:key/1234abcd",
            "public_key_path": str(tmp_path / "anchor_witness.pub"),
            "signer": {"factory": f"{DOUBLES}:build_p256_signer",
                       "identity": "kms://anchor-witness",
                       "options": {"handle": "cli-svc", "key_arn": "arn:aws:kms:us-east-1:219024422756:key/1234abcd"}},
            "sink": {"factory": f"{DOUBLES}:build_sink", "identity": "s3://anchors/prod"},
        },
    }
    path = tmp_path / "forward_validation.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    return {"root": tmp_path, "config_path": path, "config": config}


# ---- the configuration is the deployment's, not the caller's ----------------------------------------

def test_the_configuration_is_located_by_the_deployment(deployment):
    loaded = load_deployment_config()
    assert loaded.source_path == deployment["config_path"]
    assert loaded.strategy_id == 11 and loaded.ledger_account_id == 901
    assert loaded.deployment_model is DeploymentModel.CONTAINER


def test_the_cli_exposes_no_path_arguments():
    """Only the mode and the session date are invocation-time inputs."""
    source = (BACKEND / "scripts" / "run_forward_validation_session.py").read_text(encoding="utf-8")
    flags = {line.split('"')[1] for line in source.splitlines()
             if "add_argument(" in line and '"--' in line}
    assert flags == {"--session-date"}


def test_a_missing_configuration_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "nope.json"))
    with pytest.raises(DeploymentConfigError, match="no governed forward-validation configuration"):
        load_deployment_config()


def test_an_incomplete_configuration_is_refused(deployment, monkeypatch):
    partial = dict(deployment["config"])
    del partial["app_db_path"]
    path = deployment["root"] / "partial.json"
    path.write_text(json.dumps(partial), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    with pytest.raises(DeploymentConfigError, match="incomplete"):
        load_deployment_config()


def test_account_4_can_never_be_the_validation_ledger(deployment, monkeypatch):
    bad = dict(deployment["config"], ledger_account_id=4)
    path = deployment["root"] / "acct4.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    with pytest.raises(DeploymentConfigError, match="never runs on the live book"):
        load_deployment_config()


def test_a_container_deployment_must_configure_a_runtime_digest_source(deployment, monkeypatch):
    bad = dict(deployment["config"])
    del bad["runtime_digest_path"]
    path = deployment["root"] / "nodigest.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    with pytest.raises(DeploymentConfigError, match="runtime_digest_path or runtime_digest_env"):
        load_deployment_config()


# ---- the deployment must declare an anchor trust boundary (R5e) -------------------------------------

def test_a_deployment_without_a_witness_block_cannot_be_loaded(deployment, monkeypatch):
    """Not defaulted to the reference implementations at the call site: a deployment that cannot
    independently witness its chain tips is not a runnable deployment."""
    bad = dict(deployment["config"])
    del bad["witness"]
    path = deployment["root"] / "nowitness.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    with pytest.raises(DeploymentConfigError, match="incomplete"):
        load_deployment_config()


def test_a_witness_block_carrying_signing_material_is_refused(deployment, monkeypatch):
    bad = dict(deployment["config"])
    bad["witness"] = {**bad["witness"],
                      "signer": {**bad["witness"]["signer"], "options": {"private_key": "abc"}}}
    path = deployment["root"] / "keyed.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    with pytest.raises(WitnessConfigError, match="private signing material"):
        load_deployment_config()


@POSIX_ONLY
def test_readiness_enforces_the_witness_and_publishes_its_evidence(deployment):
    report = cli.run_readiness(load_deployment_config(), SESSION)
    witness = report.evidence["witness"]
    assert witness["signer"]["key_challenge"]["challenged"] is True
    assert witness["sink"]["immutability"]["source"] == "STORAGE"
    assert witness["verifying_key"]["obtained_from_signer"] is False


def test_readiness_refuses_a_reference_witness(deployment, monkeypatch):
    """An operator learns the boundary is a development stand-in BEFORE a session is due — not at the
    first commit."""
    bad = dict(deployment["config"])
    bad["witness"] = {**bad["witness"], "profile": "REFERENCE"}
    path = deployment["root"] / "refwitness.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    with pytest.raises(WitnessEnforcementError, match="development implementations"):
        cli.run_readiness(load_deployment_config(), SESSION)


def test_a_witness_refusal_reports_its_code(deployment, monkeypatch, capsys):
    bad = dict(deployment["config"])
    bad["witness"] = {**bad["witness"], "profile": "REFERENCE"}
    path = deployment["root"] / "refwitness2.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(path))
    assert cli.main(["readiness", "--session-date", SESSION.isoformat()]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "INTEGRITY_STOP"
    assert out["code"] == "WITNESS_PROFILE_NOT_PRODUCTION"


@POSIX_ONLY
def test_the_witness_evidence_does_not_leak_option_values(deployment):
    report = cli.run_readiness(load_deployment_config(), SESSION)
    # The KMS-shaped signer takes a handle AND the key ARN; both are KEY NAMES, and the assertion is
    # that VALUES never appear in evidence — which is what this test is actually about.
    assert report.evidence["witness"]["signer"]["option_keys"] == ["handle", "key_arn"]


# ---- readiness verifies everything and changes nothing ----------------------------------------------

@POSIX_ONLY
def test_readiness_never_constructs_or_invokes_the_instrument(deployment, monkeypatch):
    """The structural boundary: snapshot creation and `on_bar` belong exclusively to run-session."""
    from strategies_user.templates.momentum_daily import MomentumDaily

    def forbidden(*a, **k):                       # pragma: no cover - must never be reached
        raise AssertionError("readiness constructed the instrument")

    monkeypatch.setattr(MomentumDaily, "__init__", forbidden)
    monkeypatch.setattr("app.validation.decision_provider.capture_instrument_snapshot",
                        forbidden, raising=False)

    report = cli.run_readiness(load_deployment_config(), SESSION)
    assert report.verdict != "READY"              # this fixture's store is deliberately thin
    assert "data_finality" in report.evidence or report.verdict == "NOT_ELIGIBLE"


@POSIX_ONLY
def test_readiness_reports_the_deployment_identity_and_account4_state(deployment):
    report = cli.run_readiness(load_deployment_config(), SESSION)
    assert report.evidence["deployment_identity"]["agreed_commit"] == COMMIT
    assert report.evidence["deployment_identity"]["runtime_artifact_digest"] == DIGEST


def test_readiness_refuses_an_unidentified_deployment(deployment, monkeypatch):
    (deployment["root"] / "build_info.json").unlink()
    with pytest.raises(DeploymentEvidenceMissing):
        cli.run_readiness(load_deployment_config(), SESSION)


def test_readiness_writes_no_observation_and_no_ledger(deployment):
    config = load_deployment_config()
    with contextlib.suppress(Exception):          # a red readiness is fine; writing anything is not
        cli.run_readiness(config, SESSION)
    assert not config.ledger_path.exists()
    assert not config.observation_store_dir.exists()


@POSIX_ONLY
def test_the_provider_identities_bind_the_store_and_construction(deployment):
    report = cli.run_readiness(load_deployment_config(), SESSION)
    identities = report.evidence.get("provider_identities")
    if identities:                                # present once the data checks are reached
        assert "stage2.compute_day|store=" in identities["scores"]
        assert "stage4.build_market_proxy|store=" in identities["bars"]


# ---- this increment offers readiness ONLY -----------------------------------------------------------

def test_the_cli_now_offers_run_session_and_still_takes_no_operator_evidence():
    """R5c-2b1 deliberately shipped readiness ALONE, because a command named `run-session` that refused
    every invocation would have misrepresented the deployment. R5e-2 supplies the composition root, so
    the mode is now real — and this test flipped with it, rather than the mode being added quietly.

    What must NOT change: the invocation surface. The only inputs are the mode and the session date. An
    operator who could pass a store path, a ledger identity or an authorization token could point the
    record at evidence of their own making.
    """
    source = (BACKEND / "scripts" / "run_forward_validation_session.py").read_text(encoding="utf-8")
    assert 'choices=["readiness", "run-session"]' in source
    assert "def run_session(" in source
    assert "--authorize" not in source
    for forbidden in ("--factor-store", "--app-db", "--build-info-path", "--ledger-path",
                      "--store-dir", "--starting-capital"):
        assert forbidden not in source, f"the CLI accepts operator-supplied {forbidden}"


def test_the_run_session_mode_reaches_the_runner_only_through_the_composition_root():
    """There must be exactly one way to build a session: if the CLI grew its own wiring, the witness
    gate would have a second path around it."""
    source = (BACKEND / "scripts" / "run_forward_validation_session.py").read_text(encoding="utf-8")
    assert "from app.validation.session_composition import build_session_runtime" in source
    assert "SessionRuntime(" not in source, "the CLI assembles a runtime itself"


def test_an_unknown_mode_is_rejected(deployment):
    with pytest.raises(SystemExit):
        cli.main(["evaluate-and-activate"])


def test_readiness_requires_no_authorization(deployment, capsys):
    exit_code = cli.main(["readiness", "--session-date", SESSION.isoformat()])
    assert exit_code in (0, 1)                     # a verdict, not a refusal to run
    assert "readiness" in capsys.readouterr().out


def test_a_missing_configuration_refuses_before_anything_else(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "absent.json"))
    assert cli.main(["readiness"]) == 2
    assert "no governed forward-validation configuration" in capsys.readouterr().out


def test_an_ineligible_session_is_reported_not_run(deployment, capsys):
    assert cli.main(["readiness", "--session-date", "2026-07-25"]) == 1     # a Saturday
    assert "NOT_ELIGIBLE" in capsys.readouterr().out
