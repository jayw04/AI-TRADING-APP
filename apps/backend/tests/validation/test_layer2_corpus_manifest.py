"""Native loading for the Layer 2 whole-corpus reconstruction manifest.

A `CorpusManifest` describes `immutable base + ordered deltas`. A Layer 2 construction is neither, so
it is supported NATIVELY rather than converted into a synthetic base-plus-delta manifest — a conversion
would have to invent a `base_coverage_through`, a base artifact identity and a delta order that do not
exist, and each invention would be a false statement carried in governed evidence.

⚠ The load-bearing tests here are the REFUSALS and, above all,
`test_a_reconstruction_never_reports_a_base_or_delta_chain`. A normalized representation that quietly
defaulted those fields would reintroduce exactly the falsehood native support exists to prevent, and
nothing else in the system would notice.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.validation.governed_corpus import (
    LAYER2_CORPUS_KIND,
    REQUIRED_LAYER2_ARTIFACTS,
    SUPPORTED_LAYER2_SCHEMA_VERSIONS,
    CorpusConstructionError,
    canonical_json,
    load_any_corpus_manifest,
    load_layer2_corpus_manifest,
    normalize_corpus_manifest,
)

SCHEMA = "LAYER2_SINGLE_VINTAGE_PERMANENT_LINEAGE_v1.0"
PRIOR = "a" * 64


def _sha(n: str) -> str:
    return hashlib.sha256(n.encode()).hexdigest()


def _payload(**over) -> dict:
    p = {
        "kind": LAYER2_CORPUS_KIND,
        "construction_schema_version": SCHEMA,
        "session": "2026-07-27",
        "security_identity_contract": "PERMATICKER_EFFECTIVE_INTERVAL_V1",
        "declared_identities": {
            "legacy_governed_universe_sha256": _sha("legacy"),
            "governed_universe_key_crosswalk_sha256": _sha("crosswalk"),
            "governed_mapped_identity_universe_sha256": _sha("mapped"),
            "governed_price_universe_sha256": _sha("price"),
            "source_vintage_sha256": _sha("vintage"),
        },
        "mapped_identity_universe_size": 14_145,
        "price_universe_size": 14_143,
        "artifacts": {name: {"sha256": _sha(name), "bytes": 10, "path": f"{name}.json"}
                      for name in sorted(REQUIRED_LAYER2_ARTIFACTS)},
        "quarantined_histories": {"SHOP.csv": {"sha256": _sha("shop"), "bytes": 5}},
        # Required since 2026-07-31: a reconstruction that withholds price histories must name the
        # identities it withholds, because that block is the only governed source of the quarantine.
        "governed_quarantine": {
            "class": "UNEXPLAINED_VENDOR_ADJUSTMENT_ANOMALY",
            "kind": "VERSION_SPECIFIC_PRICE_HISTORY_QUARANTINE",
            "names": ["SHOP", "TLN"],
            "permanent_identities": ["167284", "642054"],
            "permanent_universe_removal": False,
            "must_not_say": "SHOP/TLN are decision-irrelevant",
            "statement": ["decision-relevant in raw construction"],
        },
        "store": {"computed": True, "store_file_sha256": _sha("store"), "bytes": 1},
        "supersedes": {"corpus_manifest_sha256": PRIOR, "prior_identity_altered": False,
                       "reason": "HISTORICAL_RECONSTRUCTION_SINGLE_VINTAGE_AND_PERMANENT_LINEAGE"},
        "countersignature": None,
    }
    p.update(over)
    return p


def _write(tmp_path: Path, payload: dict, *, canonical: bool = True) -> Path:
    p = tmp_path / "manifest.json"
    p.write_bytes(canonical_json(payload) if canonical
                  else json.dumps(payload, indent=2).encode())
    return p


# ---- the happy path ---------------------------------------------------------------------------------

def test_a_valid_reconstruction_manifest_loads_natively(tmp_path):
    p = _write(tmp_path, _payload())
    m = load_layer2_corpus_manifest(p)
    assert m.construction_schema_version == SCHEMA
    assert m.corpus_manifest_sha256 == hashlib.sha256(p.read_bytes()).hexdigest()
    assert m.supersedes_corpus_manifest_sha256 == PRIOR
    assert len(m.artifacts) == len(REQUIRED_LAYER2_ARTIFACTS)


def test_the_governed_universe_is_the_PRICE_universe_not_the_mapped_one(tmp_path):
    """⚠ The two universes are never collapsed. The PRICE universe governs SEP restriction, ranking,
    proxy and corpus identity; the mapped-identity universe is a different, larger set."""
    m = load_layer2_corpus_manifest(_write(tmp_path, _payload()))
    assert m.governed_universe_sha256 == _sha("price")
    assert m.governed_universe_size == 14_143
    n = normalize_corpus_manifest(m)
    assert n.mapped_identity_universe_sha256 == _sha("mapped")
    assert n.mapped_identity_universe_size == 14_145
    assert n.governed_universe_sha256 != n.mapped_identity_universe_sha256


def test_the_runtime_exposes_the_construction_kind_and_supersession(tmp_path):
    n = normalize_corpus_manifest(load_layer2_corpus_manifest(_write(tmp_path, _payload())))
    d = n.to_open_provenance()
    assert d["corpus_construction_kind"] == LAYER2_CORPUS_KIND
    assert d["construction_schema_version"] == SCHEMA
    assert d["supersedes_corpus_manifest_sha256"] == PRIOR


def test_a_reconstruction_never_reports_a_base_or_delta_chain(tmp_path):
    """★ THE GUARD THE WHOLE INCREMENT EXISTS FOR.

    A conversion into a synthetic base-plus-delta would make the runtime accept the bytes by claiming
    a base and a delta order that do not exist. The normalized representation must leave them ABSENT,
    not defaulted, and must say so explicitly.
    """
    n = normalize_corpus_manifest(load_layer2_corpus_manifest(_write(tmp_path, _payload())))
    assert n.has_base_and_deltas is False
    assert n.base_corpus_sha256 is None
    assert n.base_coverage_through is None
    assert n.ordered_delta_manifest_sha256s == ()
    d = n.to_open_provenance()
    assert d["has_base_and_deltas"] is False
    for invented in ("base_corpus_sha256", "base_coverage_through",
                     "ordered_delta_manifest_sha256s"):
        assert invented not in d, f"{invented} must not appear for a reconstruction"


# ---- the refusals -----------------------------------------------------------------------------------

def test_an_unknown_schema_version_is_refused_not_best_effort_parsed(tmp_path):
    """A construction whose meaning may have changed must never be read with the old meaning."""
    p = _write(tmp_path, _payload(construction_schema_version="LAYER2_SOMETHING_ELSE_v9.9"))
    with pytest.raises(CorpusConstructionError, match="does not understand"):
        load_layer2_corpus_manifest(p)


def test_the_supported_schema_set_is_explicit():
    assert SCHEMA in SUPPORTED_LAYER2_SCHEMA_VERSIONS


@pytest.mark.parametrize("dropped", sorted(REQUIRED_LAYER2_ARTIFACTS))
def test_every_required_evidence_artifact_is_required(tmp_path, dropped):
    """A manifest naming fewer artifacts than the construction was authorized with describes a
    DIFFERENT construction."""
    arts = {k: v for k, v in _payload()["artifacts"].items() if k != dropped}
    with pytest.raises(CorpusConstructionError, match="missing"):
        load_layer2_corpus_manifest(_write(tmp_path, _payload(artifacts=arts)))


def test_missing_quarantine_histories_are_refused(tmp_path):
    with pytest.raises(CorpusConstructionError, match="quarantined_histories"):
        load_layer2_corpus_manifest(_write(tmp_path, _payload(quarantined_histories={})))


def test_a_store_identity_that_was_not_computed_is_refused(tmp_path):
    """A manifest must not claim a store it did not hash."""
    with pytest.raises(CorpusConstructionError, match="COMPUTED store identity"):
        load_layer2_corpus_manifest(_write(tmp_path, _payload(
            store={"computed": False, "refusal": "skipped"})))


def test_a_missing_supersession_link_is_refused(tmp_path):
    payload = _payload()
    del payload["supersedes"]
    with pytest.raises(CorpusConstructionError, match="no supersession"):
        load_layer2_corpus_manifest(_write(tmp_path, payload))


def test_a_manifest_that_supersedes_itself_is_refused():
    """Exercised at `from_payload`, not through a file: a self-superseding manifest is a FIXED POINT
    (declaring your own digest changes your digest), so it cannot be constructed on disk. The guard
    still matters for any caller that builds the object directly."""
    from app.validation.governed_corpus import Layer2CorpusManifest

    with pytest.raises(CorpusConstructionError, match="its own predecessor"):
        Layer2CorpusManifest.from_payload(_payload(), computed_sha256=PRIOR)


def test_a_supersession_that_admits_mutating_the_prior_identity_is_refused(tmp_path):
    """The prior record is what makes the earlier countersignature checkable; a supersession that
    altered it would destroy the only thing that can be re-verified."""
    with pytest.raises(CorpusConstructionError, match="UNALTERED"):
        load_layer2_corpus_manifest(_write(tmp_path, _payload(supersedes={
            "corpus_manifest_sha256": PRIOR, "prior_identity_altered": True, "reason": "x"})))


def test_a_manifest_not_in_its_own_canonical_form_is_refused(tmp_path):
    """The identity is the digest of the bytes; if the bytes do not re-serialize to themselves the
    identity cannot be reproduced by anyone else."""
    p = _write(tmp_path, _payload(), canonical=False)
    with pytest.raises(CorpusConstructionError, match="canonical form"):
        load_layer2_corpus_manifest(p)


def test_a_missing_universe_identity_is_refused(tmp_path):
    ids = dict(_payload()["declared_identities"])
    del ids["governed_price_universe_sha256"]
    with pytest.raises(CorpusConstructionError, match="governed_price_universe_sha256"):
        load_layer2_corpus_manifest(_write(tmp_path, _payload(declared_identities=ids)))


# ---- dispatch, and the untouched legacy path --------------------------------------------------------

def test_the_dispatcher_routes_a_reconstruction_natively(tmp_path):
    m = load_any_corpus_manifest(_write(tmp_path, _payload()))
    assert type(m).__name__ == "Layer2CorpusManifest"


def test_an_unrecognized_kind_is_refused(tmp_path):
    with pytest.raises(CorpusConstructionError, match="unrecognized kind"):
        load_any_corpus_manifest(_write(tmp_path, _payload(kind="something_else")))


def test_a_base_plus_delta_manifest_carries_no_kind_and_takes_the_original_path(tmp_path):
    """★ The existing construction must load EXACTLY as before. It declares no `kind`, so the
    dispatcher hands it to the unchanged loader."""
    from app.validation.governed_corpus import load_corpus_manifest

    legacy = {
        "base_corpus_sha256": _sha("base"), "base_coverage_through": "2026-07-24",
        "base_countersignature": "GoverningCorpus_Countersignature_v2.0",
        "governed_universe_sha256": _sha("uni"), "governed_universe_size": 14_150,
        "actions_manifest_sha256": _sha("actions"), "actions_authoritative": True,
        "tickers_authoritative": True,
        "security_identity_contract": "PERMATICKER_EFFECTIVE_INTERVAL_V1",
        "tickers": {
            "artifact_sha256": _sha("tart"), "countersignature": "TickersManifest_v1.0",
            "coverage_cutoff": "2026-07-28", "permanent_ids": 21_934, "rows": 21_934,
            "row_identity_sha256": _sha("trow"), "schema_version": "TICKERS_V2_PERMATICKER",
            "source_identity": "SHARADAR/TICKERS (table=SEP slice)",
            "columns": ["ticker", "permaticker", "name", "exchange", "category", "sector",
                        "industry", "isdelisted", "firstpricedate", "lastpricedate", "lastupdated"],
        },
        "deltas": [],
    }
    p = tmp_path / "legacy.json"
    p.write_bytes(canonical_json(legacy))
    assert "kind" not in legacy
    direct = load_corpus_manifest(p)
    dispatched = load_any_corpus_manifest(p)
    assert dispatched.corpus_manifest_sha256 == direct.corpus_manifest_sha256
    n = normalize_corpus_manifest(dispatched)
    assert n.corpus_construction_kind == "governed_corpus"
    assert n.has_base_and_deltas is True
    assert n.construction_schema_version is None


# ---- the RECIPROCAL serialization contract ----------------------------------------------------------
#
# ★ Omitting base/delta keys for a reconstruction is only half the guarantee. The other half is that a
# LEGACY construction still emits them. Pinning only one side would let a future "normalization
# cleanup" make both construction types serialize identically — at which point the runtime could no
# longer tell a reconstruction from a base-plus-delta chain, and the omission that makes the Layer 2
# record truthful would have been silently undone with every existing test still green.

BASE_DELTA_KEYS = ("base_corpus_sha256", "base_coverage_through", "ordered_delta_manifest_sha256s",
                   "actions_manifest_sha256", "tickers_manifest_sha256")
LAYER2_KEYS = ("mapped_identity_universe_sha256", "mapped_identity_universe_size",
               "store_file_sha256", "evidence_artifact_count")


def _legacy_payload() -> dict:
    return {
        "base_corpus_sha256": _sha("base"), "base_coverage_through": "2026-07-24",
        "base_countersignature": "GoverningCorpus_Countersignature_v2.0",
        "governed_universe_sha256": _sha("uni"), "governed_universe_size": 14_150,
        "actions_manifest_sha256": _sha("actions"), "actions_authoritative": True,
        "tickers_authoritative": True,
        "security_identity_contract": "PERMATICKER_EFFECTIVE_INTERVAL_V1",
        "tickers": {
            "artifact_sha256": _sha("tart"), "countersignature": "TickersManifest_v1.0",
            "coverage_cutoff": "2026-07-28", "permanent_ids": 21_934, "rows": 21_934,
            "row_identity_sha256": _sha("trow"), "schema_version": "TICKERS_V2_PERMATICKER",
            "source_identity": "SHARADAR/TICKERS (table=SEP slice)",
            "columns": ["ticker", "permaticker", "name", "exchange", "category", "sector",
                        "industry", "isdelisted", "firstpricedate", "lastpricedate", "lastupdated"],
        },
        "deltas": [],
    }


def test_a_LEGACY_construction_still_emits_its_base_and_delta_provenance(tmp_path):
    """The reciprocal of the omission test. A base-plus-delta construction HAS a base and a delta
    order, so its record must continue to state them."""
    p = tmp_path / "legacy.json"
    p.write_bytes(canonical_json(_legacy_payload()))
    d = normalize_corpus_manifest(load_any_corpus_manifest(p)).to_open_provenance()
    assert d["corpus_construction_kind"] == "governed_corpus"
    assert d["has_base_and_deltas"] is True
    for key in BASE_DELTA_KEYS:
        assert key in d, f"a legacy construction must still report {key}"
    assert d["base_corpus_sha256"] == _sha("base")
    assert d["base_coverage_through"] == "2026-07-24"


def test_the_two_construction_types_never_serialize_identically(tmp_path):
    """★ THE GUARD AGAINST A FUTURE NORMALIZATION CLEANUP.

    If these two ever produce the same key set, the runtime has lost the ability to distinguish a
    reconstruction from a base-plus-delta chain — and every other test here would still pass.
    """
    legacy_p = tmp_path / "legacy.json"
    legacy_p.write_bytes(canonical_json(_legacy_payload()))
    legacy = normalize_corpus_manifest(load_any_corpus_manifest(legacy_p)).to_open_provenance()
    layer2 = normalize_corpus_manifest(
        load_layer2_corpus_manifest(_write(tmp_path, _payload()))).to_open_provenance()

    assert set(legacy) != set(layer2), "the two construction types must not serialize identically"

    # legacy: base/delta present, Layer 2-only keys absent
    assert all(k in legacy for k in BASE_DELTA_KEYS)
    assert not any(k in legacy for k in LAYER2_KEYS)
    assert legacy["construction_schema_version"] is None

    # reconstruction: base/delta ABSENT, Layer 2 keys present
    assert not any(k in layer2 for k in BASE_DELTA_KEYS)
    assert all(k in layer2 for k in LAYER2_KEYS)
    assert layer2["construction_schema_version"] == SCHEMA
    assert layer2["supersedes_corpus_manifest_sha256"] == PRIOR

    # and the discriminator itself is explicit in both
    assert legacy["has_base_and_deltas"] is True
    assert layer2["has_base_and_deltas"] is False


def test_the_countersigned_git_manifest_recomputes_its_identity(tmp_path):
    """The committed manifest is GOVERNED METADATA, not the corpus. Its identity must be RECOMPUTED
    from the bytes, never trusted from a declared field."""
    payload = _payload()
    p = _write(tmp_path, payload)
    m = load_layer2_corpus_manifest(p)
    assert m.corpus_manifest_sha256 == hashlib.sha256(p.read_bytes()).hexdigest()
    assert "corpus_manifest_sha256" not in payload, (
        "the identity must not be a declared field inside the manifest it identifies")
