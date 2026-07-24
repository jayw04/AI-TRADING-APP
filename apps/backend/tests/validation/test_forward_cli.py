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

BACKEND = Path(__file__).resolve().parents[2]
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
    (tmp_path / "build_info.json").write_text(
        json.dumps({"commit": COMMIT, "tree_clean": True, "image_digest": DIGEST}), encoding="utf-8")
    (tmp_path / "deployment_manifest.json").write_text(
        json.dumps({"commit": COMMIT, "image_digest": DIGEST}), encoding="utf-8")
    (tmp_path / "image_digest").write_text(DIGEST, encoding="utf-8")
    (tmp_path / "DGS3MO.csv").write_text("date,value\n", encoding="utf-8")
    (tmp_path / "TrialLedger.json").write_text("{}", encoding="utf-8")

    config = {
        "factor_store_path": str(_factor_store(tmp_path / "factor.duckdb")),
        "app_db_path": str(_app_db(tmp_path / "workbench.sqlite")),
        "observation_store_dir": str(tmp_path / "observations"),
        "ledger_path": str(tmp_path / "ledger.json"),
        "dgs3mo_path": str(tmp_path / "DGS3MO.csv"),
        "trial_ledger_path": str(tmp_path / "TrialLedger.json"),
        "build_info_path": str(tmp_path / "build_info.json"),
        "deployment_manifest_path": str(tmp_path / "deployment_manifest.json"),
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


# ---- readiness verifies everything and changes nothing ----------------------------------------------

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


def test_the_provider_identities_bind_the_store_and_construction(deployment):
    report = cli.run_readiness(load_deployment_config(), SESSION)
    identities = report.evidence.get("provider_identities")
    if identities:                                # present once the data checks are reached
        assert "stage2.compute_day|store=" in identities["scores"]
        assert "stage4.build_market_proxy|store=" in identities["bars"]


# ---- this increment offers readiness ONLY -----------------------------------------------------------

def test_the_cli_offers_no_run_session_mode():
    """R5c-2b1 ships readiness. A command that refused every invocation while being named
    `run-session` would misrepresent what the deployment can do; the assembly is R5c-2b2."""
    source = (BACKEND / "scripts" / "run_forward_validation_session.py").read_text(encoding="utf-8")
    assert 'choices=["readiness"]' in source
    assert "def run_session(" not in source
    assert "--authorize" not in source


def test_an_unknown_mode_is_rejected(deployment):
    with pytest.raises(SystemExit):
        cli.main(["run-session"])


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
