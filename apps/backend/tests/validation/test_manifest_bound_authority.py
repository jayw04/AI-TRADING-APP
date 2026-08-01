"""Manifest-bound source authority for a countersigned Layer 2 reconstruction.

The defect: every `dataset_coverage` row of the Layer 2 store records a BUILD-MACHINE path
(`C:\\LLM-RAG-APP\\layer2-vintage\\v2\\raw\\SHARADAR_ACTIONS_2_….zip`). `declare_action_source`
re-hashes that path to establish authority, which on the Linux deployment host can only ever return
`artifact-missing` — so readiness refused `NOT_READY_ADJUSTMENT_UNVERIFIED` for a corpus that is
countersigned, complete, and correct.

The ruling: for a countersigned whole-corpus reconstruction the source ZIPs were CONSTRUCTION inputs,
not runtime dependencies. Authority moves to the immutable manifest, the countersignature sidecar that
binds it, and store provenance naming the SAME governed vintage. It does not weaken: a missing,
malformed, unbound or conflicting provenance still refuses, and the artifact path is demoted to audit
metadata rather than ignored as a concept.

⚠ These tests are dataset-GENERIC (sep / tickers / actions) because all three coverage rows carry
Windows paths. Production still gates on ACTIONS only — no SEP or TICKERS readiness gate is added
here, and adding one would change readiness semantics.
"""

from __future__ import annotations

import duckdb
import pytest

from app.validation.production_bindings import (
    ManifestBoundAuthorityPolicy,
    declare_action_source,
    parse_source_identity,
)

VINTAGE = "36d247f42210b4dc13873ba7c6e052f4dfaee7d059eacbff59eb2b0ea4ea7798"
OTHER_VINTAGE = "a" * 64
ARTIFACT = "e4ed424fc74dd8837062f5f1235f3db41ca21e6ad028af532e3f39fbfd0f54ce"
#: The real recorded shape: a Windows path that cannot exist on the deployment host.
WINDOWS_PATH = r"C:\LLM-RAG-APP\layer2-vintage\v2\raw\SHARADAR_ACTIONS_2_29fe246cadf.zip"

DATASETS = ("sep", "tickers", "actions")

#: The reference witness doubles, so a configuration-loading test is not blocked by witness assembly.
_DOUBLES = "tests.validation.witness_doubles"


def identity(dataset: str, vintage: str = VINTAGE) -> str:
    return (f"SHARADAR/{dataset.upper()}|source_vintage_sha256={vintage}"
            f"|export_object=SHARADAR_{dataset.upper()}_2_29fe246.zip"
            f"|last_refreshed_time=2026-07-29 23:19:15 UTC"
            f"|reason=HISTORICAL_RECONSTRUCTION_SINGLE_VINTAGE_AND_PERMANENT_LINEAGE")


def policy(vintage: str = VINTAGE) -> ManifestBoundAuthorityPolicy:
    return ManifestBoundAuthorityPolicy(
        source_vintage_sha256=vintage, corpus_manifest_sha256="1" * 64,
        countersignature_sha256="2" * 64, construction_kind="layer2_governed_corpus")


def store(rows: list[dict]):
    """An in-memory store shaped like the governed one: coverage joined to a completed ingest run."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE ingest_runs (run_id VARCHAR, dataset VARCHAR, status VARCHAR, "
                "finished_at TIMESTAMP, started_at TIMESTAMP, rows BIGINT)")
    con.execute("CREATE TABLE dataset_coverage (dataset VARCHAR, ingest_run_id VARCHAR, "
                "coverage_start DATE, coverage_end DATE, artifact_sha256 VARCHAR, "
                "artifact_path VARCHAR, source_identity VARCHAR, rows_loaded BIGINT, "
                "recorded_at TIMESTAMP, status VARCHAR)")
    for i, r in enumerate(rows):
        run = f"run{i}"
        con.execute("INSERT INTO ingest_runs VALUES (?,?,'ok','2026-07-30','2026-07-29',100)",
                    [run, r["dataset"]])
        con.execute(
            "INSERT INTO dataset_coverage VALUES (?,?,'1997-12-31','2026-07-27',?,?,?,100,"
            "'2026-07-30','ok')",
            [r["dataset"], run, r.get("artifact", ARTIFACT), r.get("path", WINDOWS_PATH),
             r["identity"]])
    return con


class TestParsing:
    def test_the_load_bearing_fields_are_parsed_not_substring_matched(self):
        p = parse_source_identity(identity("actions"))
        assert p is not None
        assert (p.namespace, p.dataset, p.source_vintage_sha256) == ("SHARADAR", "ACTIONS", VINTAGE)

    def test_audit_metadata_may_vary_without_changing_the_binding(self):
        """`export_object`, `last_refreshed_time` and `reason` are audit metadata. A whole-string
        comparison would refuse on drift that means nothing."""
        a = parse_source_identity(identity("actions"))
        b = parse_source_identity(
            f"SHARADAR/ACTIONS|source_vintage_sha256={VINTAGE}|export_object=different.zip"
            f"|last_refreshed_time=2027-01-01 00:00:00 UTC|reason=SOMETHING_ELSE")
        assert a == b

    @pytest.mark.parametrize("raw", [
        "", "   ", "SHARADAR", "SHARADAR/", "/ACTIONS",
        "SHARADAR/A/B|source_vintage_sha256=" + VINTAGE,          # ambiguous namespace
        "SHARADAR/ACTIONS",                                        # no vintage
        "SHARADAR/ACTIONS|source_vintage_sha256=nothex",           # not a digest
        f"SHARADAR/ACTIONS|source_vintage_sha256={VINTAGE}|source_vintage_sha256={OTHER_VINTAGE}",
    ])
    def test_malformed_identities_are_refused(self, raw):
        assert parse_source_identity(raw) is None


class TestManifestBoundAuthority:
    @pytest.mark.parametrize("dataset", DATASETS)
    def test_an_inaccessible_windows_path_with_a_bound_vintage_is_authoritative(self, dataset):
        """★ The case that blocked the July 27 evaluation. The path cannot resolve on this host and is
        deliberately not resolved; the manifest-bound vintage is what confers authority."""
        con = store([{"dataset": dataset, "identity": identity(dataset)}])
        got = declare_action_source(con, dataset=dataset, authority_policy=policy())
        assert got.authoritative is True
        assert str(got.coverage_end) == "2026-07-27"

    @pytest.mark.parametrize("dataset", DATASETS)
    def test_inaccessible_path_plus_mismatched_vintage_still_refuses(self, dataset):
        """★ REQUIRED. Proves the replacement binding is load-bearing rather than the check merely
        having been switched off — same unusable path, wrong vintage, still refused."""
        con = store([{"dataset": dataset, "identity": identity(dataset, OTHER_VINTAGE)}])
        got = declare_action_source(con, dataset=dataset, authority_policy=policy())
        assert got.authoritative is False
        assert got.identity == f"{dataset}:source-vintage-unbound"

    @pytest.mark.parametrize("dataset", DATASETS)
    def test_inaccessible_path_plus_malformed_identity_still_refuses(self, dataset):
        """★ REQUIRED."""
        con = store([{"dataset": dataset, "identity": f"SHARADAR/{dataset.upper()}|garbage"}])
        got = declare_action_source(con, dataset=dataset, authority_policy=policy())
        assert got.authoritative is False
        assert got.identity == f"{dataset}:source-identity-malformed"

    def test_a_row_naming_a_different_dataset_confers_no_authority(self):
        con = store([{"dataset": "actions", "identity": identity("tickers")}])
        got = declare_action_source(con, dataset="actions", authority_policy=policy())
        assert got.authoritative is False
        assert got.identity == "actions:source-identity-wrong-dataset"

    def test_two_rows_from_the_same_governed_vintage_are_accepted(self):
        """Multiple loads of one governed vintage are benign — which is why this is a vintage-agreement
        rule and not a row-count invariant."""
        con = store([{"dataset": "actions", "identity": identity("actions")},
                     {"dataset": "actions", "identity": identity("actions")}])
        assert declare_action_source(con, dataset="actions",
                                     authority_policy=policy()).authoritative is True

    def test_two_distinct_vintages_refuse(self):
        """The conflict a row-count rule would have missed: authority read off the newest row while an
        older authoritative row names a different vintage."""
        con = store([{"dataset": "actions", "identity": identity("actions")},
                     {"dataset": "actions", "identity": identity("actions", OTHER_VINTAGE)}])
        got = declare_action_source(con, dataset="actions", authority_policy=policy())
        assert got.authoritative is False
        assert got.identity == "actions:source-vintage-conflict"

    def test_no_authoritative_row_refuses(self):
        con = store([])
        assert declare_action_source(con, dataset="actions",
                                     authority_policy=policy()).authoritative is False


class TestLegacyPathUnchanged:
    def test_without_a_policy_the_artifact_path_is_still_re_hashed(self):
        """Base-plus-delta passes `authority_policy=None` and keeps the artifact-path check verbatim —
        the same Windows path that manifest-bound authority accepts must still refuse here."""
        con = store([{"dataset": "actions", "identity": identity("actions")}])
        got = declare_action_source(con, dataset="actions")
        assert got.authoritative is False
        assert got.identity == "actions:artifact-missing"

    def test_a_real_artifact_still_confers_legacy_authority(self, tmp_path):
        import hashlib

        artifact = tmp_path / "actions.zip"
        artifact.write_bytes(b"governed bytes")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        con = store([{"dataset": "actions", "identity": identity("actions"),
                      "artifact": digest, "path": str(artifact)}])
        assert declare_action_source(con, dataset="actions").authoritative is True


class TestSharedDerivation:
    def test_base_plus_delta_derives_no_policy(self, tmp_path):
        from datetime import date

        from app.validation.governed_corpus import (
            load_any_corpus_manifest,
            manifest_bound_authority_policy,
            normalize_corpus_manifest,
        )
        from tests.validation.governed_construction_fixture import install_governed_construction

        install_governed_construction(tmp_path, date(2026, 7, 24))
        normalized = normalize_corpus_manifest(
            load_any_corpus_manifest(tmp_path / "corpus_manifest.json"))
        assert manifest_bound_authority_policy(normalized, None) is None

    def test_layer2_derives_the_manifest_bound_vintage(self, tmp_path):
        from app.validation.governed_corpus import (
            load_any_corpus_manifest,
            load_layer2_countersignature,
            manifest_bound_authority_policy,
            normalize_corpus_manifest,
        )
        from tests.validation.governed_construction_fixture import install_layer2_construction

        install_layer2_construction(tmp_path)
        normalized = normalize_corpus_manifest(
            load_any_corpus_manifest(tmp_path / "corpus_manifest.json"))
        cs = load_layer2_countersignature(tmp_path / "countersignature.json")
        got = manifest_bound_authority_policy(normalized, cs)
        assert got is not None
        assert got.construction_kind == "layer2_governed_corpus"
        # the vintage really is the one the committed manifest binds
        assert got.source_vintage_sha256 == VINTAGE
        assert got.countersignature_sha256 == cs.countersignature_sha256

    def test_a_layer2_construction_without_approval_cannot_derive_a_policy(self, tmp_path):
        from app.validation.governed_corpus import (
            CountersignatureError,
            load_any_corpus_manifest,
            manifest_bound_authority_policy,
            normalize_corpus_manifest,
        )
        from tests.validation.governed_construction_fixture import install_layer2_construction

        install_layer2_construction(tmp_path, sidecar=False)
        normalized = normalize_corpus_manifest(
            load_any_corpus_manifest(tmp_path / "corpus_manifest.json"))
        with pytest.raises(CountersignatureError):
            manifest_bound_authority_policy(normalized, None)


class TestAncestryMarkerConfiguration:
    def _config(self, tmp_path, **extra):
        import json

        from app.validation.forward_deployment_config import load_deployment_config
        from tests.validation.governed_construction_fixture import install_layer2_construction

        install_layer2_construction(tmp_path)
        payload = {
            "factor_store_path": str(tmp_path / "s.duckdb"),
            "app_db_path": str(tmp_path / "a.sqlite"),
            "observation_store_dir": str(tmp_path / "obs"),
            "ledger_path": str(tmp_path / "l.json"),
            "dgs3mo_path": str(tmp_path / "DGS3MO.csv"),
            "trial_ledger_path": str(tmp_path / "TrialLedger.json"),
            "build_info_path": str(tmp_path / "b.json"),
            "deployment_manifest_path": str(tmp_path / "m.json"),
            "corpus_manifest_path": str(tmp_path / "corpus_manifest.json"),
            "dgs3mo_manifest_path": str(tmp_path / "dgs3mo_manifest.json"),
            "deployment_model": "SOURCE_CHECKOUT",
            "ledger_account_id": 901, "strategy_id": 11,
            "expected_broker": "alpaca", "expected_broker_mode": "paper",
            "shadow_ledger_identity": "sl", "instrument_durable_state_id": "id",
            "starting_capital": 100000.0, "turnover_cost_bps": 10.0,
            "backstop_days": 10, "weight_drift_pct": 0.04,
            # A complete REFERENCE witness block: this suite is about configuration LOADING, and an
            # incomplete witness would refuse before the field under test is ever read.
            "witness": {
                "profile": "REFERENCE",
                "trusted_root": str(tmp_path),
                "public_key_path": str(tmp_path / "anchor_witness.pub"),
                "signer": {"factory": f"{_DOUBLES}:build_p256_signer",
                           "identity": "reference://signer", "options": {}},
                "sink": {"factory": f"{_DOUBLES}:build_sink", "identity": "file://anchors"},
            },
            **extra,
        }
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return load_deployment_config(p)

    def test_the_ancestry_marker_path_is_read_from_configuration(self, tmp_path):
        """It was declared on the dataclass but never read from the payload, so it was silently always
        None and no deployment could satisfy an ancestry check."""
        marker = tmp_path / "ancestry.json"
        marker.write_text("{}", encoding="utf-8")
        cfg = self._config(tmp_path, ancestry_marker_path=str(marker))
        assert cfg.ancestry_marker_path == marker

    def test_an_absent_field_is_none(self, tmp_path):
        assert self._config(tmp_path).ancestry_marker_path is None

    def test_an_absent_marker_fails_ancestry_closed(self, tmp_path):
        """None must not become permission: the ancestry check refuses rather than assuming descent."""
        from app.validation.measurement_freeze import verify_deployment

        freeze = _freeze()
        fails = verify_deployment(freeze, actual_commit="b" * 40, runtime_root=tmp_path,
                                  ancestry_marker=None)
        assert any("could not be verified" in f for f in fails)

    def test_a_marker_for_a_different_pair_does_not_confer_ancestry(self, tmp_path):
        import json

        from app.validation.measurement_freeze import verify_deployment

        marker = tmp_path / "ancestry.json"
        marker.write_text(json.dumps({"measurement_commit": "c" * 40, "deployed_head": "d" * 40,
                                      "is_ancestor": True}), encoding="utf-8")
        fails = verify_deployment(_freeze(), actual_commit="b" * 40, runtime_root=tmp_path,
                                  ancestry_marker=marker)
        assert any("NOT an ancestor" in f or "could not be verified" in f for f in fails)


def _freeze():
    from app.validation.measurement_freeze import MeasurementFreeze

    return MeasurementFreeze(
        manifest_schema_version="1.0",
        validation_tree_identity_algorithm="PATH_SORTED_SHA256_CRLF_TO_LF_V1",
        measurement_commit="a" * 40, validation_tree_sha256="1" * 64,
        supersedes_measurement_commit="9" * 40, ratified_increment_inventory_sha256="2" * 64,
        amendment_sha256="3" * 64, measured_paths=("app/validation",),
        byte_manifest_sha256="4" * 64, manifest_sha256="5" * 64)
