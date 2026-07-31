"""Native Layer 2 support on the production session-composition path.

The defect this closes: `Layer2CorpusManifest` and `load_any_corpus_manifest` existed, but the only
caller was the readiness runner. `resolve_governed_construction` still went through
`load_corpus_manifest`, and `session_composition._declared_base_cutoff` still demanded a
`base_coverage_through`. So a deployment could pass readiness against a reconstruction and then be
unable to compose a session against the very same corpus.

The second defect: the construction artifact carries `"countersignature": null` and a
construction-time `status` of PROPOSED. A construction cannot countersign itself, so approval is
recorded in an external sidecar that names the manifest digest. The embedded null therefore means "not
self-countersigned" — it can neither override a valid sidecar nor stand in for a missing one, and both
directions are pinned here.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.validation.governed_corpus import (
    CountersignatureError,
    Layer2CorpusManifest,
    ManifestIdentityConflict,
    deployment_corpus_block,
    load_any_corpus_manifest,
    load_layer2_countersignature,
    normalize_corpus_manifest,
)
from tests.validation.governed_construction_fixture import (
    LAYER2_ARTIFACTS,
    LAYER2_SESSION,
    install_governed_construction,
    install_layer2_construction,
)


def _config(tmp_path: Path, block: dict, *, sidecar: bool = True) -> SimpleNamespace:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"commit": "b" * 40, "corpus": block}), encoding="utf-8")
    return SimpleNamespace(
        corpus_manifest_path=tmp_path / "corpus_manifest.json",
        dgs3mo_manifest_path=tmp_path / "dgs3mo_manifest.json",
        dgs3mo_path=tmp_path / "DGS3MO.csv",
        trial_ledger_path=tmp_path / "TrialLedger.json",
        corpus_countersignature_path=(tmp_path / "countersignature.json") if sidecar else None,
        deployment_manifest_path=tmp_path / "manifest.json")


def _resolve(config: SimpleNamespace, session: date = LAYER2_SESSION):
    from app.validation.session_composition import _resolve_governed_construction

    return _resolve_governed_construction(config, session)


class TestLayer2Composes:
    def test_a_layer2_construction_composes_with_a_valid_sidecar(self, tmp_path: Path):
        block = install_layer2_construction(tmp_path)
        got = _resolve(_config(tmp_path, block))

        assert isinstance(got.corpus, Layer2CorpusManifest)
        assert got.normalized.corpus_construction_kind == "layer2_governed_corpus"
        assert got.normalized.coverage_through == LAYER2_SESSION
        assert got.countersignature is not None
        assert got.countersignature.countersignature_status == "CONDITIONALLY_COUNTERSIGNED"
        # the sidecar binds the manifest that was actually loaded
        assert (got.countersignature.corpus_manifest_sha256
                == got.corpus.corpus_manifest_sha256 == got.corpus_manifest_sha256)

    def test_the_construction_identity_may_be_issued_for_a_reconstruction(self, tmp_path: Path):
        """It is recomputed from the manifest's own canonical bytes for BOTH kinds, which is the
        property that makes it independent of the store."""
        from app.validation.governed_corpus import IdentitySource, construction_identity

        got = _resolve(_config(tmp_path, install_layer2_construction(tmp_path)))
        identity = construction_identity(got.corpus)
        assert identity.source is IdentitySource.GOVERNED_CONSTRUCTION_MANIFEST
        assert identity.value == got.corpus_manifest_sha256


class TestCountersignatureIsRequired:
    def test_a_layer2_construction_without_a_sidecar_is_refused(self, tmp_path: Path):
        install_layer2_construction(tmp_path, sidecar=False)
        # a block that looks complete is not enough — the approval is a separate artifact
        corpus = load_any_corpus_manifest(tmp_path / "corpus_manifest.json")
        assert isinstance(corpus, Layer2CorpusManifest)
        with pytest.raises(CountersignatureError, match="no countersignature sidecar is configured"):
            _resolve(_config(tmp_path, {}, sidecar=False))

    def test_a_configured_but_absent_sidecar_is_refused(self, tmp_path: Path):
        install_layer2_construction(tmp_path, sidecar=False)
        with pytest.raises(CountersignatureError, match="countersignature sidecar is absent"):
            _resolve(_config(tmp_path, {}))

    def test_the_embedded_null_countersignature_cannot_substitute_for_the_sidecar(self,
                                                                                 tmp_path: Path):
        """The construction artifact says `countersignature: null` and PROPOSED. That is a statement
        about self-countersignature, and it neither approves nor disapproves: the sidecar is required
        either way."""
        install_layer2_construction(tmp_path, sidecar=False)
        payload = json.loads((tmp_path / "corpus_manifest.json").read_text(encoding="utf-8"))
        assert payload["countersignature"] is None
        assert payload["status"].startswith("PROPOSED")
        with pytest.raises(CountersignatureError):
            _resolve(_config(tmp_path, {}))

    def test_the_embedded_null_cannot_override_a_valid_sidecar(self, tmp_path: Path):
        """The converse, and the reason the embedded field is not consulted at all: the SAME artifact
        that says PROPOSED composes once its external approval is present."""
        block = install_layer2_construction(tmp_path)
        payload = json.loads((tmp_path / "corpus_manifest.json").read_text(encoding="utf-8"))
        assert payload["countersignature"] is None and payload["status"].startswith("PROPOSED")
        got = _resolve(_config(tmp_path, block))
        assert got.countersignature is not None


class TestSidecarBinding:
    def test_a_sidecar_bound_to_the_wrong_manifest_is_refused(self, tmp_path: Path):
        block = install_layer2_construction(tmp_path)
        sidecar = json.loads((tmp_path / "countersignature.json").read_text(encoding="utf-8"))
        sidecar["corpus_manifest_sha256"] = "9" * 64
        _rewrite_canonical(tmp_path / "countersignature.json", sidecar)
        with pytest.raises(CountersignatureError, match="approval of one construction is never"):
            _resolve(_config(tmp_path, block))

    def test_a_superseded_sidecar_does_not_carry_forward(self, tmp_path: Path):
        """The realistic failure: the previous corpus's countersignature left installed across an
        upgrade. It is diagnosed as superseded rather than as a generic mismatch."""
        block = install_layer2_construction(tmp_path)
        manifest = json.loads((tmp_path / "corpus_manifest.json").read_text(encoding="utf-8"))
        superseded = manifest["supersedes"]["corpus_manifest_sha256"]

        sidecar = json.loads((tmp_path / "countersignature.json").read_text(encoding="utf-8"))
        sidecar["corpus_manifest_sha256"] = superseded
        _rewrite_canonical(tmp_path / "countersignature.json", sidecar)
        with pytest.raises(CountersignatureError, match="SUPERSEDES"):
            _resolve(_config(tmp_path, block))

    def test_a_sidecar_approving_a_different_supersession_is_refused(self, tmp_path: Path):
        block = install_layer2_construction(tmp_path)
        sidecar = json.loads((tmp_path / "countersignature.json").read_text(encoding="utf-8"))
        sidecar["supersedes_manifest_sha256"] = "4" * 64
        _rewrite_canonical(tmp_path / "countersignature.json", sidecar)
        with pytest.raises(CountersignatureError, match="not the same event"):
            _resolve(_config(tmp_path, block))

    def test_an_unrecognized_countersignature_status_is_not_approval(self, tmp_path: Path):
        block = install_layer2_construction(tmp_path)
        sidecar = json.loads((tmp_path / "countersignature.json").read_text(encoding="utf-8"))
        sidecar["countersignature_status"] = "PENDING_REVIEW"
        _rewrite_canonical(tmp_path / "countersignature.json", sidecar)
        with pytest.raises(CountersignatureError, match="does not accept as approval"):
            _resolve(_config(tmp_path, block))

    def test_a_non_canonical_sidecar_is_refused(self, tmp_path: Path):
        """Its identity is the digest of its own bytes, so it must re-serialize to itself."""
        block = install_layer2_construction(tmp_path)
        path = tmp_path / "countersignature.json"
        path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2),
                        encoding="utf-8")
        with pytest.raises(CountersignatureError, match="not in its own canonical form"):
            _resolve(_config(tmp_path, block))


class TestNoInventedProvenance:
    def test_a_reconstruction_never_emits_base_or_delta_provenance(self, tmp_path: Path):
        """Not even as nulls: a null `base_corpus_sha256` in governed evidence reads as "there was a
        base and we failed to record it"."""
        got = _resolve(_config(tmp_path, install_layer2_construction(tmp_path)))
        provenance = got.to_open_provenance()

        for absent in ("base_corpus_sha256", "base_coverage_through",
                       "ordered_delta_manifest_sha256s", "actions_manifest_sha256",
                       "tickers_manifest_sha256"):
            assert absent not in provenance, f"{absent} must not appear for a reconstruction"
        assert provenance["has_base_and_deltas"] is False
        assert provenance["corpus_coverage_through"] == LAYER2_SESSION.isoformat()
        assert provenance["countersignature"]["countersignature_status"] == (
            "CONDITIONALLY_COUNTERSIGNED")

    def test_the_deployment_block_names_coverage_as_governed_not_base(self, tmp_path: Path):
        block = install_layer2_construction(tmp_path)
        assert block["governed_coverage_through"] == LAYER2_SESSION.isoformat()
        assert "base_coverage_through" not in block
        assert "base_corpus_sha256" not in block
        assert "ordered_delta_manifest_sha256s" not in block

    def test_the_normalized_construction_answers_none_rather_than_inventing(self, tmp_path: Path):
        got = _resolve(_config(tmp_path, install_layer2_construction(tmp_path)))
        assert got.normalized.has_base_and_deltas is False
        assert got.normalized.base_corpus_sha256 is None
        assert got.normalized.base_coverage_through is None
        assert got.normalized.ordered_delta_manifest_sha256s == ()
        # and it DOES carry what a reconstruction really has
        assert got.normalized.store_file_sha256
        assert got.normalized.source_vintage_sha256


class TestSessionScope:
    """Two scopes that must not be conflated. The corpus countersignature approves the reconstructed
    CORPUS and its coverage; a readiness attestation is valid for its exact session. Composition
    enforces the first, never the second."""

    def test_another_covered_session_composes_against_the_same_corpus(self, tmp_path: Path):
        """A session inside governed coverage is entitled to its own readiness run. Refusing it here
        would deny it on corpus grounds, which is not what the countersignature says."""
        block = install_layer2_construction(tmp_path, session=date(2026, 7, 24))
        got = _resolve(_config(tmp_path, block), date(2026, 7, 24))
        assert got.normalized.corpus_construction_kind == "layer2_governed_corpus"
        assert got.countersignature is not None

    def test_a_session_beyond_governed_coverage_is_still_refused(self, tmp_path: Path):
        """Coverage remains a real bound: the corpus cannot evaluate a session it stops before."""
        from app.validation.governed_corpus import CorpusConstructionError

        beyond = date(2026, 7, 28)
        block = install_layer2_construction(tmp_path, session=beyond)
        with pytest.raises(CorpusConstructionError, match="stops before it"):
            _resolve(_config(tmp_path, block), beyond)


class TestDeclaredIdentities:
    def test_a_deployment_declaring_a_different_corpus_is_refused(self, tmp_path: Path):
        block = install_layer2_construction(tmp_path)
        with pytest.raises(ManifestIdentityConflict):
            _resolve(_config(tmp_path, block | {"corpus_manifest_sha256": "3" * 64}))

    def test_a_deployment_missing_the_countersignature_digest_is_refused(self, tmp_path: Path):
        block = install_layer2_construction(tmp_path)
        del block["countersignature_sha256"]
        with pytest.raises(ManifestIdentityConflict, match="incomplete"):
            _resolve(_config(tmp_path, block))

    def test_a_deployment_declaring_base_plus_delta_fields_does_not_satisfy_layer2(self,
                                                                                  tmp_path: Path):
        """The stale-manifest case: the deployment was generated against the previous construction."""
        block = install_layer2_construction(tmp_path)
        stale = {
            "base_corpus_sha256": "d" * 64,
            "base_coverage_through": LAYER2_SESSION.isoformat(),
            "ordered_delta_manifest_sha256s": [],
            "governed_universe_sha256": block["governed_universe_sha256"],
            "actions_manifest_sha256": "e" * 64,
            "tickers_manifest_sha256": "f" * 64,
            "corpus_manifest_sha256": block["corpus_manifest_sha256"],
            "dgs3mo_manifest_sha256": block["dgs3mo_manifest_sha256"],
        }
        with pytest.raises(ManifestIdentityConflict, match="incomplete"):
            _resolve(_config(tmp_path, stale))


class TestGeneratorAndSessionPathAgree:
    def test_the_generator_and_the_session_path_resolve_the_same_block(self, tmp_path: Path):
        """The one producer, called from both sides. If these ever diverge, a deployment manifest
        declares something the session path never checks."""
        block = install_layer2_construction(tmp_path)
        got = _resolve(_config(tmp_path, block))

        recomputed = deployment_corpus_block(
            got.normalized, dgs3mo_manifest_sha256=got.dgs3mo_manifest_sha256,
            countersignature=got.countersignature)
        assert recomputed == block

    def test_a_layer2_block_cannot_be_produced_without_the_approval(self, tmp_path: Path):
        install_layer2_construction(tmp_path, sidecar=False)
        corpus = load_any_corpus_manifest(tmp_path / "corpus_manifest.json")
        with pytest.raises(CountersignatureError, match="cannot be produced without"):
            deployment_corpus_block(normalize_corpus_manifest(corpus),
                                    dgs3mo_manifest_sha256="7" * 64)


class TestLegacyPathUnchanged:
    def test_base_plus_delta_composition_is_unaffected(self, tmp_path: Path):
        """The whole point of dispatching rather than replacing: the countersigned base-plus-delta
        construction must behave exactly as it did, including needing no sidecar."""
        session = date(2026, 7, 24)
        block = install_governed_construction(tmp_path, session)
        (tmp_path / "manifest.json").write_text(
            json.dumps({"commit": "b" * 40, "corpus": block}), encoding="utf-8")
        config = SimpleNamespace(
            corpus_manifest_path=tmp_path / "corpus_manifest.json",
            dgs3mo_manifest_path=tmp_path / "dgs3mo_manifest.json",
            dgs3mo_path=tmp_path / "DGS3MO.csv",
            trial_ledger_path=tmp_path / "TrialLedger.json",
            corpus_countersignature_path=None,
            deployment_manifest_path=tmp_path / "manifest.json")

        got = _resolve(config, session)
        assert got.countersignature is None
        assert got.normalized.has_base_and_deltas is True
        provenance = got.to_open_provenance()
        assert provenance["base_coverage_through"] == session.isoformat()
        assert provenance["ordered_delta_manifest_sha256s"] == []
        assert "countersignature" not in provenance

    def test_the_legacy_deployment_block_shape_is_byte_stable(self, tmp_path: Path):
        """The generator now builds this block through the shared producer. Its key set and values
        must be exactly what the previous hand-built literal emitted, or every deployed manifest
        silently stops matching."""
        session = date(2026, 7, 24)
        block = install_governed_construction(tmp_path, session)
        corpus = load_any_corpus_manifest(tmp_path / "corpus_manifest.json")
        from app.validation.governed_corpus import load_dgs3mo_manifest

        dgs = load_dgs3mo_manifest(tmp_path / "dgs3mo_manifest.json")
        assert deployment_corpus_block(
            normalize_corpus_manifest(corpus),
            dgs3mo_manifest_sha256=dgs.dgs3mo_manifest_sha256) == block


class TestCommittedArtifactsStillHash:
    def test_the_committed_sidecar_binds_the_committed_manifest(self):
        """Runs against the repository copies, so a normalization or an edit to either artifact fails
        here rather than on the deployed host the morning of an observation."""
        from app.validation.governed_corpus import file_sha256, require_countersignature

        corpus = load_any_corpus_manifest(LAYER2_ARTIFACTS / "corpus_manifest_v2.json")
        assert isinstance(corpus, Layer2CorpusManifest)
        countersignature = load_layer2_countersignature(
            LAYER2_ARTIFACTS / "corpus_countersignature_v1.json")
        require_countersignature(corpus, countersignature)

        assert corpus.corpus_manifest_sha256 == file_sha256(
            LAYER2_ARTIFACTS / "corpus_manifest_v2.json")
        assert countersignature.countersignature_sha256 == file_sha256(
            LAYER2_ARTIFACTS / "corpus_countersignature_v1.json")


def _rewrite_canonical(path: Path, payload: dict) -> None:
    """Rewrite a sidecar so it stays in canonical form — otherwise every mutation would be caught by
    the canonical-form check and the binding checks would never be reached."""
    from app.validation.governed_corpus import canonical_json

    path.write_bytes(canonical_json(payload))
