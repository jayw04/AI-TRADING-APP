"""The two GENERATED deployment inputs — build_info and deployment_manifest.

What matters about a generator that produces evidence is that it derives rather than asserts, refuses
rather than guesses, and produces the same bytes for the same deployment so a diff means something.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from tests.validation.governed_construction_fixture import install_governed_construction

SPEC = importlib.util.spec_from_file_location(
    "generate_deployment_evidence",
    Path(__file__).resolve().parents[2] / "scripts" / "generate_deployment_evidence.py")
assert SPEC and SPEC.loader
gen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gen)

COMMIT = "b0058bf335628f8dbde09a93915314f3a1f7743b"
SESSION = date(2026, 7, 24)


@pytest.fixture
def repo(monkeypatch, tmp_path):
    """A stand-in git tree: clean, at a known commit, with the frozen replica present."""
    replicas = tmp_path / "apps" / "backend" / "scripts"
    replicas.mkdir(parents=True)
    for rel in gen.REPLICA_SCRIPTS:
        (tmp_path / "apps" / "backend" / rel).write_text("# frozen\n", encoding="utf-8")

    state = {"status": ""}

    def fake_git(*args, repo):
        if args[:2] == ("rev-parse", "HEAD"):
            return COMMIT
        if args[0] == "status":
            return state["status"]
        if args[0] == "ls-files":
            return "apps/backend/app/validation/governed_corpus.py"
        return ""

    monkeypatch.setattr(gen, "_git", fake_git)
    monkeypatch.setattr(gen, "_package_hash", lambda repo: "9" * 64)
    return tmp_path, state


class TestBuildInfo:
    def test_it_records_the_derived_commit_and_a_clean_tree(self, repo):
        root, _ = repo
        info = gen.build_info(root, allow_dirty=False, expect_commit=None, image_digest=None)
        assert info["commit"] == COMMIT
        assert info["tree_clean"] is True
        assert set(info["frozen_replica_sha256"]) == set(gen.REPLICA_SCRIPTS)

    def test_a_dirty_tree_is_refused(self, repo):
        root, state = repo
        state["status"] = " M app/validation/governed_corpus.py"
        with pytest.raises(gen.GenerationError, match="uncommitted changes"):
            gen.build_info(root, allow_dirty=False, expect_commit=None, image_digest=None)

    def test_a_dirty_tree_is_recorded_honestly_when_allowed(self, repo):
        """`--allow-dirty` produces evidence OF a dirty tree; the session gate still refuses it."""
        root, state = repo
        state["status"] = " M x.py"
        info = gen.build_info(root, allow_dirty=True, expect_commit=None, image_digest=None)
        assert info["tree_clean"] is False

    def test_a_pin_that_disagrees_refuses_rather_than_being_recorded(self, repo):
        root, _ = repo
        with pytest.raises(gen.GenerationError, match="narrows the result and never replaces it"):
            gen.build_info(root, allow_dirty=False, expect_commit="a" * 40, image_digest=None)

    def test_a_missing_frozen_replica_is_refused(self, repo):
        root, _ = repo
        (root / "apps" / "backend" / gen.REPLICA_SCRIPTS[0]).unlink()
        with pytest.raises(gen.GenerationError, match="replica is incomplete"):
            gen.build_info(root, allow_dirty=False, expect_commit=None, image_digest=None)


class TestDeploymentManifest:
    def _config(self, tmp_path: Path) -> Path:
        install_governed_construction(tmp_path, SESSION)
        cfg = tmp_path / "forward_validation.json"
        cfg.write_text(json.dumps({
            "dgs3mo_path": str(tmp_path / "DGS3MO.csv"),
            "trial_ledger_path": str(tmp_path / "TrialLedger.json"),
            "strategy_id": 11, "ledger_account_id": 901,
            "witness": {"key_id": "arn:aws:kms:us-east-1:219024422756:key/3691fc60",
                        "profile": "PRODUCTION",
                        "sink": {"options": {"bucket": "witness-bucket", "prefix": "witness/"}}},
        }), encoding="utf-8")
        return cfg

    def _manifest(self, repo_root: Path, tmp_path: Path) -> dict:
        build = {"commit": COMMIT, "created_at": "2026-07-27T12:00:00Z"}
        return gen.deployment_manifest(
            repo_root, build=build, corpus_manifest_path=tmp_path / "corpus_manifest.json",
            dgs3mo_manifest_path=tmp_path / "dgs3mo_manifest.json",
            config_path=self._config(tmp_path), host_identity="ec2-forward-validation",
            image_digest=None)

    def test_it_carries_the_five_construction_identities(self, repo, tmp_path):
        from app.validation.governed_corpus import REQUIRED_MANIFEST_IDENTITIES

        root, _ = repo
        self._config(tmp_path)
        manifest = self._manifest(root, tmp_path)
        for key in REQUIRED_MANIFEST_IDENTITIES:
            assert key in manifest["corpus"], key
        assert manifest["corpus"]["dgs3mo_manifest_sha256"]

    def test_it_does_not_invent_a_store_identity(self, repo, tmp_path):
        """A manifest finalized before observation #1 cannot honestly carry a value that only exists
        once a session has read. Recording one would be exactly the fabricated evidence the
        deployment-identity module exists to refuse."""
        root, _ = repo
        self._config(tmp_path)
        assert "store_identity_sha256" not in self._manifest(root, tmp_path)["corpus"]

    def test_it_records_the_authorization_state_as_standing_denials(self, repo, tmp_path):
        root, _ = repo
        self._config(tmp_path)
        state = self._manifest(root, tmp_path)["authorization_state"]
        assert state == {"forward_window_open": False, "hold_removed": False,
                         "broker_orders_authorized": False,
                         "account4_activation_authorized": False}

    def test_a_drifted_frozen_artifact_refuses_at_generation(self, repo, tmp_path):
        """Catching it here rather than a day later at session start."""
        root, _ = repo
        cfg = self._config(tmp_path)
        (tmp_path / "TrialLedger.json").write_text("{}", encoding="utf-8")
        from app.validation.governed_corpus import FrozenArtifactDrift

        with pytest.raises(FrozenArtifactDrift, match="trial ledger"):
            gen.deployment_manifest(
                root, build={"commit": COMMIT, "created_at": "t"},
                corpus_manifest_path=tmp_path / "corpus_manifest.json",
                dgs3mo_manifest_path=tmp_path / "dgs3mo_manifest.json",
                config_path=cfg, host_identity=None, image_digest=None)


class TestCanonicalOutput:
    def test_the_same_deployment_produces_byte_identical_files(self, tmp_path):
        payload = {"b": 1, "a": [3, 2], "created_at": "2026-07-27T12:00:00Z"}
        first = gen._write_canonical(tmp_path / "a.json", payload)
        second = gen._write_canonical(tmp_path / "b.json", dict(reversed(list(payload.items()))))
        assert first == second
        assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()

    def test_the_generated_manifest_satisfies_the_deployment_verifier(self, repo, tmp_path):
        """End to end: what the generator writes is what `verify_deployment_identity` accepts."""
        from app.validation.deployment_identity import DeploymentModel, verify_deployment_identity

        root, _ = repo
        info = gen.build_info(root, allow_dirty=False, expect_commit=None, image_digest=None)
        gen._write_canonical(tmp_path / "build_info.json", info)
        manifest = self._make_manifest(root, tmp_path, info)
        gen._write_canonical(tmp_path / "deployment_manifest.json", manifest)

        evidence = verify_deployment_identity(
            model=DeploymentModel.SOURCE_CHECKOUT,
            build_info_path=tmp_path / "build_info.json",
            deployment_manifest_path=tmp_path / "deployment_manifest.json")
        assert evidence.agreed_commit == COMMIT

    def _make_manifest(self, root: Path, tmp_path: Path, info: dict) -> dict:
        install_governed_construction(tmp_path, SESSION)
        cfg = tmp_path / "forward_validation.json"
        cfg.write_text(json.dumps({
            "dgs3mo_path": str(tmp_path / "DGS3MO.csv"),
            "trial_ledger_path": str(tmp_path / "TrialLedger.json"),
            "strategy_id": 11, "ledger_account_id": 901,
            "witness": {"key_id": "k", "profile": "PRODUCTION",
                        "sink": {"options": {"bucket": "b", "prefix": "witness/"}}},
        }), encoding="utf-8")
        return gen.deployment_manifest(
            root, build=info, corpus_manifest_path=tmp_path / "corpus_manifest.json",
            dgs3mo_manifest_path=tmp_path / "dgs3mo_manifest.json", config_path=cfg,
            host_identity=None, image_digest=None)
