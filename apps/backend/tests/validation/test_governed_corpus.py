"""ADR 0048 — the governed construction contract, and every way it must fail closed.

Two properties carry the weight here and are tested directly rather than inferred:

  * a chain that is missing, duplicated, reordered, future-dated, unhashed, amending history or bound
    to a different universe is REFUSED — each as its own case, because each is a different way for a
    session to consume data nobody authorized;
  * adding the construction identity does NOT disturb the value-level store identity. That digest is
    the runtime proof, its calculation and timing are load-bearing, and this suite pins the exact
    bytes it produces so a future refactor cannot quietly change what an observation attests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from app.validation.governed_corpus import (
    TICKERS_SCHEMA_VERSION,
    CorpusConstructionError,
    CorpusManifest,
    DeltaChainError,
    Dgs3moManifest,
    FrozenArtifactDrift,
    GovernedDelta,
    HistoricalAmendmentRefused,
    ManifestIdentityConflict,
    TickersManifest,
    require_declared_identities,
    require_observation_identities,
    resolve_governed_construction,
    verify_frozen_artifact,
)
from app.validation.security_lineage import SECURITY_IDENTITY_CONTRACT

UNIVERSE = "a" * 64
BASE = "d" * 64
ACTIONS = "e" * 64
TICKERS_ID = "9" * 64
BASE_CUTOFF = date(2026, 7, 24)

# Real XNYS sessions after the base cutoff: Fri 2026-07-24 → Mon 27, Tue 28, Wed 29.
S27, S28, S29 = date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29)


def delta(session: date, *, coverage: date | None = None, sha: str = "b" * 64,
          universe: str | None = UNIVERSE, rows: int = 5767) -> GovernedDelta:
    return GovernedDelta(
        session_date=session, coverage_through=coverage or session, sha256=sha,
        source_sha256="c" * 64, universe_sha256=universe, rows=rows,
        retrieved_at="2026-07-28T22:05:00Z", countersignature="delta-cs-1")


#: The embedded TICKERS block as it appears in a manifest JSON payload.
TICKERS_BLOCK = {
    "schema_version": TICKERS_SCHEMA_VERSION,
    "columns": ["permaticker", "ticker", "firstpricedate", "lastpricedate"],
    "rows": 21_934, "permanent_ids": 21_934,
    "row_identity_sha256": "1" * 64, "coverage_cutoff": "2026-07-29",
    "artifact_sha256": "2" * 64, "source_identity": "SHARADAR/TICKERS (table=SEP)",
    "countersignature": "TickersManifest_v1.0",
}


def tickers_manifest(*, rows: int = 21_934, cutoff: date = S29,
                     schema: str = TICKERS_SCHEMA_VERSION,
                     columns: tuple[str, ...] = ("permaticker", "ticker", "firstpricedate",
                                                 "lastpricedate"),
                     permanent_ids: int | None = None,
                     row_identity: str = "1" * 64) -> TickersManifest:
    return TickersManifest(
        schema_version=schema, columns=columns, rows=rows,
        permanent_ids=rows if permanent_ids is None else permanent_ids,
        row_identity_sha256=row_identity, coverage_cutoff=cutoff, artifact_sha256="2" * 64,
        source_identity="SHARADAR/TICKERS (table=SEP)", countersignature="TickersManifest_v1.0")


def manifest(*deltas: GovernedDelta, authoritative: bool = True,
             universe_size: int = 14_150, tickers: TickersManifest | None = None,
             tickers_authoritative: bool = True,
             contract: str = SECURITY_IDENTITY_CONTRACT) -> CorpusManifest:
    return CorpusManifest(
        base_corpus_sha256=BASE, base_coverage_through=BASE_CUTOFF,
        governed_universe_sha256=UNIVERSE, governed_universe_size=universe_size,
        actions_manifest_sha256=ACTIONS, actions_authoritative=authoritative,
        tickers=tickers or tickers_manifest(), tickers_authoritative=tickers_authoritative,
        security_identity_contract=contract,
        deltas=deltas, base_countersignature="GoverningCorpus_Countersignature_v2.0")


class TestConstructionIdentity:
    def test_the_identity_is_deterministic_over_the_same_construction(self):
        a, b = manifest(delta(S27), delta(S28)), manifest(delta(S27), delta(S28))
        assert a.corpus_manifest_sha256 == b.corpus_manifest_sha256

    def test_a_different_delta_set_is_a_different_construction(self):
        assert (manifest(delta(S27)).corpus_manifest_sha256
                != manifest(delta(S27), delta(S28)).corpus_manifest_sha256)

    def test_delta_order_changes_the_identity(self):
        """Ordering is part of what was authorized, so it must be part of the identity — not merely
        validated and then discarded."""
        assert (manifest(delta(S27), delta(S28)).corpus_manifest_sha256
                != manifest(delta(S28), delta(S27)).corpus_manifest_sha256)

    def test_coverage_follows_the_last_delta(self):
        assert manifest().coverage_through == BASE_CUTOFF
        assert manifest(delta(S27), delta(S28)).coverage_through == S28


class TestTickersIsPartOfTheConstruction:
    """ADR 0048 as amended 2026-07-29. TICKERS is bound because the decision demonstrably depends on
    it: a stale security master yields an EMPTY registered universe and a current one yields 500
    names, and those two constructions must not be able to share an authorized identity."""

    def test_a_tickers_change_moves_the_corpus_identity(self):
        before = manifest(delta(S27)).corpus_manifest_sha256
        after = manifest(delta(S27), tickers=tickers_manifest(rows=21_935)).corpus_manifest_sha256
        assert before != after

    def test_market_data_identical_but_tickers_different_are_not_equivalent(self):
        """The delta chain, base and universe are byte-identical; only the security master differs."""
        d = delta(S27)
        a = manifest(d, tickers=tickers_manifest(row_identity="3" * 64))
        b = manifest(d, tickers=tickers_manifest(row_identity="4" * 64))
        assert a.ordered_delta_manifest_sha256s == b.ordered_delta_manifest_sha256s
        assert a.base_corpus_sha256 == b.base_corpus_sha256
        assert a.corpus_manifest_sha256 != b.corpus_manifest_sha256

    def test_changing_the_identity_contract_moves_the_construction_identity(self):
        """Otherwise a resolver change could reinterpret identical artifacts under the same identity."""
        assert (manifest(delta(S27)).corpus_manifest_sha256
                != manifest(delta(S27), contract="SOMETHING_ELSE_V2").corpus_manifest_sha256)

    def test_a_contract_this_deployment_does_not_implement_is_refused(self):
        with pytest.raises(CorpusConstructionError, match="security identity contract"):
            manifest(delta(S27), contract="SOMETHING_ELSE_V2").validate(
                observation_session=S27, expected_sessions=(S27,))

    def test_a_non_authoritative_tickers_dataset_is_refused(self):
        with pytest.raises(CorpusConstructionError, match="cannot rank securities it cannot identify"):
            manifest(delta(S27), tickers_authoritative=False).validate(
                observation_session=S27, expected_sessions=(S27,))

    def test_tickers_coverage_short_of_the_session_is_refused(self):
        """The exact defect found on 2026-07-29: a security master cut off at 2026-06-12 makes the
        registered universe empty for every later session, including the original forward start."""
        with pytest.raises(CorpusConstructionError, match="cut off"):
            manifest(delta(S27), tickers=tickers_manifest(cutoff=date(2026, 6, 12))).validate(
                observation_session=S27, expected_sessions=(S27,))

    def test_an_unknown_tickers_schema_is_refused(self):
        with pytest.raises(CorpusConstructionError, match="schema"):
            manifest(delta(S27), tickers=tickers_manifest(schema="TICKERS_V1")).validate(
                observation_session=S27, expected_sessions=(S27,))

    def test_a_manifest_omitting_the_permanent_id_column_is_refused(self):
        with pytest.raises(CorpusConstructionError, match="identity-bearing column"):
            manifest(delta(S27), tickers=tickers_manifest(
                columns=("ticker", "firstpricedate", "lastpricedate"))).validate(
                observation_session=S27, expected_sessions=(S27,))

    def test_a_symbol_mapping_to_several_lineages_is_refused(self):
        with pytest.raises(CorpusConstructionError, match="ambiguous by construction"):
            manifest(delta(S27), tickers=tickers_manifest(
                rows=21_934, permanent_ids=21_900)).validate(
                observation_session=S27, expected_sessions=(S27,))


class TestGeneratorAndVerifierShareOneDefinition:
    """The manifest generator writes `to_manifest_json()`; the session reads `from_payload`. Pinning
    the round trip is what stops a producer growing a second, unreviewed idea of the construction."""

    def test_a_corpus_manifest_round_trips_to_the_same_identity(self):
        original = manifest(delta(S27), delta(S28))
        restored = CorpusManifest.from_payload(original.to_manifest_json())
        assert restored.corpus_manifest_sha256 == original.corpus_manifest_sha256
        assert restored.tickers_manifest_sha256 == original.tickers_manifest_sha256
        assert restored.security_identity_contract == original.security_identity_contract

    def test_a_tickers_manifest_round_trips_to_the_same_identity(self):
        original = tickers_manifest()
        restored = TickersManifest.from_payload(original.to_manifest_json())
        assert restored.tickers_manifest_sha256 == original.tickers_manifest_sha256

    def test_the_round_trip_preserves_delta_exclusions(self):
        d = GovernedDelta(
            session_date=S27, coverage_through=S27, sha256="b" * 64, source_sha256="c" * 64,
            universe_sha256=UNIVERSE, rows=5_881, retrieved_at="2026-07-29T12:21:08Z",
            countersignature="GovernedDelta_2026-07-27_v1.0",
            exclusions=("1827 future-dated ACTIONS rows excluded",))
        restored = CorpusManifest.from_payload(manifest(d).to_manifest_json())
        assert restored.deltas[0].exclusions == d.exclusions
        assert restored.corpus_manifest_sha256 == manifest(d).corpus_manifest_sha256


class TestDeltaChainFailsClosed:
    def test_a_gap_is_refused(self):
        with pytest.raises(DeltaChainError, match="missing"):
            manifest(delta(S28)).validate(observation_session=S28,
                                          expected_sessions=(S27, S28))

    def test_a_duplicate_session_is_refused(self):
        with pytest.raises(DeltaChainError, match="repeats session"):
            manifest(delta(S27), delta(S27)).validate(observation_session=S28,
                                                      expected_sessions=(S27,))

    def test_reordering_is_refused(self):
        with pytest.raises(DeltaChainError, match="strictly increasing"):
            manifest(delta(S28), delta(S27)).validate(observation_session=S28,
                                                      expected_sessions=(S27, S28))

    def test_a_delta_after_the_observed_session_is_refused(self):
        with pytest.raises(DeltaChainError, match="after the observed session"):
            manifest(delta(S27), delta(S29)).validate(observation_session=S28,
                                                      expected_sessions=(S27, S28))

    def test_coverage_past_its_own_session_is_refused(self):
        with pytest.raises(DeltaChainError, match="future-dated"):
            manifest(delta(S27, coverage=S29)).validate(observation_session=S29,
                                                        expected_sessions=(S27,))

    def test_a_delta_bound_to_another_universe_is_refused(self):
        with pytest.raises(DeltaChainError, match="universe change is a new base"):
            manifest(delta(S27, universe="f" * 64)).validate(observation_session=S27,
                                                             expected_sessions=(S27,))

    def test_amending_history_is_refused_and_named_as_such(self):
        with pytest.raises(HistoricalAmendmentRefused, match="new corpus version"):
            manifest(delta(BASE_CUTOFF)).validate(observation_session=S27,
                                                  expected_sessions=(BASE_CUTOFF,))

    def test_an_unhashed_delta_cannot_be_parsed(self):
        with pytest.raises(DeltaChainError, match="not a sha256"):
            GovernedDelta.from_payload({"session_date": "2026-07-27",
                                        "coverage_through": "2026-07-27", "sha256": "",
                                        "source_sha256": "c" * 64, "universe_sha256": UNIVERSE,
                                        "rows": 1, "retrieved_at": "t",
                                        "countersignature": "cs"}, index=0)

    def test_a_delta_without_a_countersignature_is_refused(self):
        with pytest.raises(DeltaChainError, match="unattested"):
            GovernedDelta.from_payload({"session_date": "2026-07-27",
                                        "coverage_through": "2026-07-27", "sha256": "b" * 64,
                                        "source_sha256": "c" * 64, "universe_sha256": UNIVERSE,
                                        "rows": 1, "retrieved_at": "t",
                                        "countersignature": ""}, index=0)

    def test_session_contiguity_without_a_calendar_is_refused(self):
        """A chain cannot be proven gap-free against a calendar nobody supplied."""
        with pytest.raises(DeltaChainError, match="calendar that was not supplied"):
            CorpusManifest.validate(manifest(delta(S27)), observation_session=S27,
                                    expected_sessions=None)  # type: ignore[arg-type]

    def test_a_non_authoritative_actions_declaration_is_refused(self):
        with pytest.raises(CorpusConstructionError, match="never ingested"):
            manifest(delta(S27), authoritative=False).validate(observation_session=S27,
                                                               expected_sessions=(S27,))

    def test_a_universe_of_the_wrong_size_is_refused(self):
        with pytest.raises(CorpusConstructionError, match="universe change is a new base"):
            manifest(delta(S27), universe_size=14_719).validate(observation_session=S27,
                                                                 expected_sessions=(S27,))

    def test_a_valid_chain_passes(self):
        manifest(delta(S27), delta(S28)).validate(observation_session=S28,
                                                  expected_sessions=(S27, S28))

    def test_actions_authoritative_must_be_a_real_boolean(self):
        payload = {"base_corpus_sha256": BASE, "base_coverage_through": "2026-07-24",
                   "governed_universe_sha256": UNIVERSE, "governed_universe_size": 14_150,
                   "actions_manifest_sha256": ACTIONS, "actions_authoritative": "true",
                   "tickers": TICKERS_BLOCK, "tickers_authoritative": True,
                   "security_identity_contract": SECURITY_IDENTITY_CONTRACT,
                   "base_countersignature": "v2.0", "deltas": []}
        with pytest.raises(CorpusConstructionError, match="merely reads as one"):
            CorpusManifest.from_payload(payload)


class TestDgs3moConstruction:
    def base(self, *extensions: GovernedDelta) -> Dgs3moManifest:
        return Dgs3moManifest(base_sha256="9" * 64, base_coverage_through=date(2026, 7, 21),
                              extensions=extensions)

    def ext(self, session: date, coverage: date | None = None) -> GovernedDelta:
        return GovernedDelta(session_date=session, coverage_through=coverage or session,
                             sha256="1" * 64, source_sha256="2" * 64, rows=3,
                             retrieved_at="2026-07-28T22:05:00Z", countersignature="fred-cs")

    def test_the_frozen_base_pin_is_not_the_composed_identity(self):
        """ADR 0048 (11): DGS3MO_SNAPSHOT_SHA256 keeps naming the frozen base. The composed identity
        is a separate value, and conflating them would turn a frozen pin into a moving target."""
        m = self.base(self.ext(S27))
        assert m.base_sha256 == "9" * 64
        assert m.dgs3mo_manifest_sha256 != m.base_sha256

    def test_extensions_must_advance_coverage(self):
        with pytest.raises(DeltaChainError, match="must advance coverage"):
            self.base(self.ext(S27, coverage=date(2026, 7, 21))).validate(
                observation_session=S28, frozen_base_sha256="9" * 64)

    def test_a_drifted_base_is_refused(self):
        with pytest.raises(FrozenArtifactDrift, match="installed by exact hash"):
            self.base().validate(observation_session=S28, frozen_base_sha256="8" * 64)

    def test_a_valid_extension_chain_passes(self):
        m = self.base(self.ext(S27), self.ext(S28))
        m.validate(observation_session=S28, frozen_base_sha256="9" * 64)
        assert m.coverage_through == S28


class TestFrozenArtifacts:
    def test_exact_hash_passes(self, tmp_path: Path):
        p = tmp_path / "DGS3MO.csv"
        p.write_bytes(b"DATE,DGS3MO\n2026-07-21,3.87\n")
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        assert verify_frozen_artifact(p, pinned_sha256=digest, what="x") == digest

    def test_a_regenerated_equivalent_looking_file_is_refused(self, tmp_path: Path):
        """A normalized, reordered or reserialized copy is not equivalent. Same information, one
        trailing newline different, different artifact."""
        p = tmp_path / "DGS3MO.csv"
        p.write_bytes(b"DATE,DGS3MO\n2026-07-21,3.87\n")
        pinned = hashlib.sha256(p.read_bytes()).hexdigest()
        p.write_bytes(b"DATE,DGS3MO\n2026-07-21,3.87")
        with pytest.raises(FrozenArtifactDrift, match="not equivalent unless its byte hash is exact"):
            verify_frozen_artifact(p, pinned_sha256=pinned, what="the frozen DGS3MO base")

    def test_an_empty_substitute_trial_ledger_is_refused(self, tmp_path: Path):
        """Synthesizing an empty ledger to satisfy configuration loading is prohibited: N=45 is read
        from that file, so an empty one silently changes the DSR gate's severity."""
        p = tmp_path / "TrialLedger_v1.0.json"
        p.write_text(json.dumps({"trials": []}), encoding="utf-8")
        with pytest.raises(FrozenArtifactDrift):
            verify_frozen_artifact(p, pinned_sha256="b" * 64, what="the governed trial ledger")

    def test_an_absent_artifact_is_refused_not_created(self, tmp_path: Path):
        with pytest.raises(FrozenArtifactDrift, match="installed, never regenerated"):
            verify_frozen_artifact(tmp_path / "nope.csv", pinned_sha256="b" * 64, what="x")


class TestDeclaredIdentities:
    def block(self, **over) -> dict:
        base = {"base_corpus_sha256": BASE, "ordered_delta_manifest_sha256s": ["b" * 64],
                "governed_universe_sha256": UNIVERSE, "actions_manifest_sha256": ACTIONS,
                "tickers_manifest_sha256": TICKERS_ID,
                "corpus_manifest_sha256": "7" * 64}
        base.update(over)
        return base

    def computed(self, **over) -> dict:
        c = {"base_corpus_sha256": BASE, "ordered_delta_manifest_sha256s": ("b" * 64,),
             "governed_universe_sha256": UNIVERSE, "actions_manifest_sha256": ACTIONS,
             "tickers_manifest_sha256": TICKERS_ID,
             "corpus_manifest_sha256": "7" * 64}
        c.update(over)
        return c

    def test_agreement_passes(self):
        require_declared_identities(self.block(), computed=self.computed())

    def test_an_absent_block_is_refused(self):
        with pytest.raises(ManifestIdentityConflict, match="no corpus identity block"):
            require_declared_identities(None, computed=self.computed())

    def test_a_missing_identity_is_refused(self):
        b = self.block()
        del b["actions_manifest_sha256"]
        with pytest.raises(ManifestIdentityConflict, match="incomplete"):
            require_declared_identities(b, computed=self.computed())

    def test_a_conflicting_identity_is_refused(self):
        with pytest.raises(ManifestIdentityConflict, match="disagree"):
            require_declared_identities(self.block(corpus_manifest_sha256="0" * 64),
                                        computed=self.computed())

    def test_a_conflicting_delta_order_is_refused(self):
        with pytest.raises(ManifestIdentityConflict, match="disagree"):
            require_declared_identities(
                self.block(ordered_delta_manifest_sha256s=["b" * 64, "3" * 64]),
                computed=self.computed())

    def test_store_identity_is_not_required_of_a_deployment_manifest(self):
        """It does not exist until a session reads. Requiring it here would force the generator to
        invent one — the exact failure the deployment-identity module exists to prevent."""
        require_declared_identities(self.block(), computed=self.computed())


def _finality(store_identity: str):
    """A `DataFinalityEvidence` carrying a chosen value-level digest, built the way the real one is."""
    from app.validation.data_finality import DataFinalityEvidence

    fields = {f: 0 for f in DataFinalityEvidence.__dataclass_fields__}
    fields.update({"session_date": "2026-07-27", "verdict": None, "detail": "", "store_path": "x",
                   "store_identity_sha256": store_identity, "ingest_identity_sha256": "i",
                   "ingest_unclean_datasets": (), "max_finalized_session": None,
                   "finality_basis": "", "session_max_lastupdated": None})
    return DataFinalityEvidence(**fields)  # type: ignore[arg-type]


class TestObservationIdentities:
    """Independence is enforced by PROVENANCE, never by comparing two digests. Unequal values do not
    establish separate derivation, and a defect hashing two wrappers around one declaration would
    pass a value comparison."""

    def _pair(self, *, construction_manifest=None, store_identity="8" * 64):
        from app.validation.governed_corpus import construction_identity, consumed_rows_identity

        m = construction_manifest or manifest(delta(S27))
        return construction_identity(m), consumed_rows_identity(_finality(store_identity))

    def test_both_are_required(self):
        c, s = self._pair()
        with pytest.raises(ManifestIdentityConflict, match="both the construction identity"):
            require_observation_identities({"corpus_manifest_sha256": c.value},
                                           construction=c, consumed=s)

    def test_a_declared_value_that_is_not_what_the_session_did_is_refused(self):
        c, s = self._pair()
        with pytest.raises(ManifestIdentityConflict, match="but the session read"):
            require_observation_identities(
                {"corpus_manifest_sha256": c.value, "store_identity_sha256": "0" * 64},
                construction=c, consumed=s)

    def test_agreement_records_both_and_their_sources(self):
        c, s = self._pair()
        out = require_observation_identities(
            {"corpus_manifest_sha256": c.value, "store_identity_sha256": s.value},
            construction=c, consumed=s)
        assert out["corpus_manifest_sha256"] == c.value
        assert out["store_identity_sha256"] == s.value
        assert out["identity_sources"] == {
            "corpus_manifest_sha256": "GOVERNED_CONSTRUCTION_MANIFEST",
            "store_identity_sha256": "STREAMED_CONSUMED_ROWS"}
        assert "audit_condition" not in out

    # ── structural independence ──────────────────────────────────────────────────────────────────

    def test_the_store_identity_may_not_be_sourced_from_the_construction(self):
        from app.validation.governed_corpus import consumed_rows_identity

        with pytest.raises(ManifestIdentityConflict, match="property of what the session READ"):
            consumed_rows_identity(manifest(delta(S27)))

    def test_the_construction_identity_may_not_be_sourced_from_the_store(self):
        from app.validation.governed_corpus import construction_identity

        with pytest.raises(ManifestIdentityConflict,
                           match="recomputed from a governed corpus manifest"):
            construction_identity(_finality("8" * 64))  # type: ignore[arg-type]

    def test_a_hand_built_identity_carries_no_provenance(self):
        from app.validation.governed_corpus import BoundIdentity, IdentitySource

        with pytest.raises(ManifestIdentityConflict, match="carries no provenance"):
            BoundIdentity(value="7" * 64, source=IdentitySource.STREAMED_CONSUMED_ROWS)

    def test_a_construction_identity_in_the_consumed_slot_is_refused(self):
        """The substitution the value comparison was supposed to catch — caught by provenance."""
        from app.validation.governed_corpus import construction_identity

        c = construction_identity(manifest(delta(S27)))
        with pytest.raises(ManifestIdentityConflict, match="streamed consumed-row digest"):
            require_observation_identities(
                {"corpus_manifest_sha256": c.value, "store_identity_sha256": c.value},
                construction=c, consumed=c)

    def test_changing_consumed_values_moves_only_the_store_identity(self):
        c1, s1 = self._pair(store_identity="1" * 64)
        c2, s2 = self._pair(store_identity="2" * 64)
        assert s1.value != s2.value, "the consumed-row digest must track what was read"
        assert c1.value == c2.value, "the authorized construction did not change"

    def test_changing_authorized_construction_moves_only_the_manifest_identity(self):
        c1, s1 = self._pair(construction_manifest=manifest(delta(S27)))
        c2, s2 = self._pair(construction_manifest=manifest(delta(S27), delta(S28)))
        assert c1.value != c2.value, "a different authorized construction is a different identity"
        assert s1.value == s2.value, "the store was read identically"

    def test_equal_digests_are_recorded_as_an_audit_condition_not_refused(self):
        """Astronomically unlikely, and not a governed refusal: with provenance enforced, equality is
        a coincidence rather than a substitution, and stopping a session for it would be wrong."""
        from app.validation.governed_corpus import construction_identity, consumed_rows_identity

        c = construction_identity(manifest(delta(S27)))
        s = consumed_rows_identity(_finality(c.value))
        out = require_observation_identities(
            {"corpus_manifest_sha256": c.value, "store_identity_sha256": c.value},
            construction=c, consumed=s)
        assert out["audit_condition"] == "IDENTITIES_COINCIDENTALLY_EQUAL"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# The regression that matters most: the value-level digest must be BYTE-IDENTICAL to what it was
# before ADR 0048 added a second identity. This drives the real `store_identity` over a fixed fake
# store and pins the exact hex it produces.
# ─────────────────────────────────────────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, rows): self._rows = list(rows)
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def fetchmany(self, n):
        out, self._rows = self._rows[:n], self._rows[n:]
        return out


class _Con:
    """Answers each of `store_identity`'s four queries with fixed rows."""
    def __init__(self):
        self.by_table = {
            "FROM sep": [("AAPL", date(2026, 7, 27), 1.0, 2.0, 0.5, 1.5, 100, 1.5, 1.5, "u1")],
            "FROM tickers": [("AAPL", "Tech", 0, date(1997, 12, 31), date(2026, 7, 27), "u1")],
            "FROM actions": [(date(2026, 7, 27), "split", "AAPL", 2.0, None)],
            "FROM ingest_runs": [("sep", "2026-07-27T22:00:00", "2026-07-27T22:05:00", 5767, "ok")],
        }

    def execute(self, sql, params=None):
        for key, rows in self.by_table.items():
            if key in sql:
                return _Cursor(rows)
        return _Cursor([])


class TestValueLevelDigestUnchanged:
    def test_store_identity_produces_the_pinned_digest(self):
        """If this fails, the value-level proof recorded by every observation changed meaning.

        ADR 0048 adds `corpus_manifest_sha256` ALONGSIDE this digest and is not permitted to alter
        its calculation, its inputs, or the order they are streamed in.
        """
        from app.validation.data_finality import _Store, store_identity

        got = store_identity(_Store(_Con()), date(2026, 7, 20), date(2026, 7, 27))
        assert got == "251c5fe40ccb609cade2681a5eb673a6c8124c13517541340cfcbb539a42896d"

    def test_the_construction_identity_does_not_feed_the_value_level_digest(self):
        """The two are computed from disjoint inputs. Changing the construction must not move the
        store identity, or a mutating store could be masked by a manifest edit."""
        from app.validation.data_finality import _Store, store_identity

        first = store_identity(_Store(_Con()), date(2026, 7, 20), date(2026, 7, 27))
        manifest(delta(S27)).corpus_manifest_sha256          # noqa: B018 — exercise the other path
        second = store_identity(_Store(_Con()), date(2026, 7, 20), date(2026, 7, 27))
        assert first == second


class TestTheRepositoryArtifactsStillMatchTheirPins:
    """The frozen inputs are installed by exact hash, so drift in the repository copy is a defect
    that must surface here rather than on the deployed host the morning of an observation."""

    def test_dgs3mo_and_the_trial_ledger_hash_to_the_countersigned_pins(self):
        from app.validation.forward_window import DGS3MO_SNAPSHOT_SHA256, TRIAL_LEDGER_SHA256
        from tests.validation.governed_construction_fixture import GOVERNED_ARTIFACTS

        verify_frozen_artifact(GOVERNED_ARTIFACTS / "data" / "DGS3MO.csv",
                               pinned_sha256=DGS3MO_SNAPSHOT_SHA256, what="the frozen DGS3MO base")
        verify_frozen_artifact(GOVERNED_ARTIFACTS / "TrialLedger_v1.0.json",
                               pinned_sha256=TRIAL_LEDGER_SHA256, what="the governed trial ledger")


class TestCompositionWiring:
    """The composition root's own path, exercised without the POSIX witness gate so it is covered on
    every platform rather than only on Linux CI."""

    def _config(self, tmp_path: Path, session: date):
        from types import SimpleNamespace

        from tests.validation.governed_construction_fixture import install_governed_construction

        block = install_governed_construction(tmp_path, session)
        (tmp_path / "manifest.json").write_text(
            json.dumps({"commit": "b" * 40, "corpus": block}), encoding="utf-8")
        return SimpleNamespace(
            corpus_manifest_path=tmp_path / "corpus_manifest.json",
            dgs3mo_manifest_path=tmp_path / "dgs3mo_manifest.json",
            dgs3mo_path=tmp_path / "DGS3MO.csv",
            trial_ledger_path=tmp_path / "TrialLedger.json",
            # A base-plus-delta deployment legitimately configures no sidecar: its approval travels
            # with each delta's own countersignature reference.
            corpus_countersignature_path=None,
            deployment_manifest_path=tmp_path / "manifest.json")

    def test_the_composition_root_resolves_a_complete_construction(self, tmp_path: Path):
        from app.validation.session_composition import _resolve_governed_construction

        session = date(2026, 7, 24)
        got = _resolve_governed_construction(self._config(tmp_path, session), session)
        assert got.corpus.coverage_through == session
        assert got.dgs3mo.coverage_through == session

    def test_a_deployment_manifest_without_a_corpus_block_is_refused(self, tmp_path: Path):
        from app.validation.session_composition import _resolve_governed_construction

        session = date(2026, 7, 24)
        config = self._config(tmp_path, session)
        (tmp_path / "manifest.json").write_text(json.dumps({"commit": "b" * 40}), encoding="utf-8")
        with pytest.raises(ManifestIdentityConflict, match="no corpus identity block"):
            _resolve_governed_construction(config, session)

    def test_a_session_beyond_the_construction_is_refused(self, tmp_path: Path):
        """The delta chain covers 2026-07-24; asking for 2026-07-27 must refuse rather than evaluate
        against data that stops before the session."""
        from app.validation.session_composition import _resolve_governed_construction

        config = self._config(tmp_path, date(2026, 7, 24))
        with pytest.raises(DeltaChainError, match="missing"):
            _resolve_governed_construction(config, S27)


class TestExpectedDeltaSessions:
    """The expectation must come from the authoritative calendar, never from the store whose
    construction is being checked — a missing delta means the store lacks that session, so a
    store-derived calendar would validate the gap clean against itself."""

    def test_it_enumerates_governed_sessions_after_the_base_cutoff(self):
        from app.validation.session_composition import _expected_delta_sessions

        # Fri 2026-07-24 cutoff → Mon 27, Tue 28, Wed 29. The weekend is not a session.
        assert _expected_delta_sessions(BASE_CUTOFF, S29) == (S27, S28, S29)

    def test_the_cutoff_itself_is_excluded(self):
        from app.validation.session_composition import _expected_delta_sessions

        assert _expected_delta_sessions(BASE_CUTOFF, BASE_CUTOFF) == ()


class TestResolveGovernedConstruction:
    def _write(self, tmp_path: Path, *, deltas: list[dict] | None = None) -> tuple[Path, Path, Path,
                                                                                   Path]:
        dgs3mo = tmp_path / "DGS3MO.csv"
        dgs3mo.write_bytes(b"DATE,DGS3MO\n2026-07-21,3.87\n")
        ledger = tmp_path / "TrialLedger.json"
        ledger.write_bytes(b'{"trials": 45}')

        corpus_path = tmp_path / "corpus_manifest.json"
        corpus_path.write_text(json.dumps({
            "base_corpus_sha256": BASE, "base_coverage_through": "2026-07-24",
            "governed_universe_sha256": UNIVERSE, "governed_universe_size": 14_150,
            "actions_manifest_sha256": ACTIONS, "actions_authoritative": True,
            "tickers": TICKERS_BLOCK, "tickers_authoritative": True,
            "security_identity_contract": SECURITY_IDENTITY_CONTRACT,
            "base_countersignature": "v2.0",
            "deltas": deltas if deltas is not None else [{
                "session_date": "2026-07-27", "coverage_through": "2026-07-27",
                "sha256": "b" * 64, "source_sha256": "c" * 64, "universe_sha256": UNIVERSE,
                "rows": 5767, "retrieved_at": "2026-07-27T22:05:00Z",
                "countersignature": "delta-cs-1"}],
        }), encoding="utf-8")

        dgs_path = tmp_path / "dgs3mo_manifest.json"
        dgs_path.write_text(json.dumps({
            "base_sha256": hashlib.sha256(dgs3mo.read_bytes()).hexdigest(),
            "base_coverage_through": "2026-07-21",
            "extensions": [{"session_date": "2026-07-27", "coverage_through": "2026-07-27",
                            "sha256": "1" * 64, "source_sha256": "2" * 64, "rows": 3,
                            "retrieved_at": "2026-07-27T22:05:00Z",
                            "countersignature": "fred-cs"}],
        }), encoding="utf-8")
        return corpus_path, dgs_path, dgs3mo, ledger

    def _resolve(self, tmp_path: Path, corpus_path, dgs_path, dgs3mo, ledger, *, block=None,
                 ledger_pin: str | None = None):
        from app.validation.governed_corpus import load_corpus_manifest, load_dgs3mo_manifest

        corpus = load_corpus_manifest(corpus_path)
        dgs = load_dgs3mo_manifest(dgs_path)
        declared = block if block is not None else {
            "base_corpus_sha256": corpus.base_corpus_sha256,
            "ordered_delta_manifest_sha256s": list(corpus.ordered_delta_manifest_sha256s),
            "governed_universe_sha256": corpus.governed_universe_sha256,
            "actions_manifest_sha256": corpus.actions_manifest_sha256,
            "tickers_manifest_sha256": corpus.tickers_manifest_sha256,
            "corpus_manifest_sha256": corpus.corpus_manifest_sha256,
            "dgs3mo_manifest_sha256": dgs.dgs3mo_manifest_sha256,
        }
        return resolve_governed_construction(
            corpus_manifest_path=corpus_path, dgs3mo_manifest_path=dgs_path,
            dgs3mo_path=dgs3mo, trial_ledger_path=ledger,
            frozen_dgs3mo_sha256=hashlib.sha256(dgs3mo.read_bytes()).hexdigest(),
            frozen_trial_ledger_sha256=(ledger_pin
                                        or hashlib.sha256(ledger.read_bytes()).hexdigest()),
            deployment_manifest_corpus_block=declared,
            observation_session=S27, expected_sessions=(S27,))

    def test_a_complete_construction_resolves(self, tmp_path: Path):
        got = self._resolve(tmp_path, *self._write(tmp_path))
        assert got.corpus_manifest_sha256 != got.dgs3mo_manifest_sha256
        assert got.to_open_provenance()["governed_universe_size"] == 14_150

    def test_a_drifted_frozen_ledger_refuses_before_any_manifest_is_trusted(self, tmp_path: Path):
        corpus_path, dgs_path, dgs3mo, ledger = self._write(tmp_path)
        pin = hashlib.sha256(ledger.read_bytes()).hexdigest()   # the pin, taken BEFORE the drift
        ledger.write_bytes(b'{"trials": 3}')
        with pytest.raises(FrozenArtifactDrift, match="trial ledger"):
            self._resolve(tmp_path, corpus_path, dgs_path, dgs3mo, ledger, ledger_pin=pin)

    def test_a_deployment_manifest_that_disagrees_is_refused(self, tmp_path: Path):
        corpus_path, dgs_path, dgs3mo, ledger = self._write(tmp_path)
        with pytest.raises(ManifestIdentityConflict):
            self._resolve(tmp_path, corpus_path, dgs_path, dgs3mo, ledger, block={
                "base_corpus_sha256": BASE, "ordered_delta_manifest_sha256s": ["b" * 64],
                "governed_universe_sha256": UNIVERSE, "actions_manifest_sha256": ACTIONS,
                "tickers_manifest_sha256": TICKERS_ID,
                "corpus_manifest_sha256": "0" * 64, "dgs3mo_manifest_sha256": "0" * 64})

    def test_a_manifest_without_the_dgs3mo_identity_is_refused(self, tmp_path: Path):
        corpus_path, dgs_path, dgs3mo, ledger = self._write(tmp_path)
        from app.validation.governed_corpus import load_corpus_manifest

        corpus = load_corpus_manifest(corpus_path)
        with pytest.raises(ManifestIdentityConflict, match="no dgs3mo_manifest_sha256"):
            self._resolve(tmp_path, corpus_path, dgs_path, dgs3mo, ledger, block={
                "base_corpus_sha256": corpus.base_corpus_sha256,
                "ordered_delta_manifest_sha256s": list(corpus.ordered_delta_manifest_sha256s),
                "governed_universe_sha256": corpus.governed_universe_sha256,
                "actions_manifest_sha256": corpus.actions_manifest_sha256,
                "tickers_manifest_sha256": corpus.tickers_manifest_sha256,
                "corpus_manifest_sha256": corpus.corpus_manifest_sha256})

    def test_coverage_short_of_the_session_is_refused(self, tmp_path: Path):
        """The whole point of the delta model: a session may not be evaluated against data that
        stops before it."""
        corpus_path, dgs_path, dgs3mo, ledger = self._write(tmp_path, deltas=[])
        from app.validation.governed_corpus import load_corpus_manifest, load_dgs3mo_manifest

        corpus, dgs = load_corpus_manifest(corpus_path), load_dgs3mo_manifest(dgs_path)
        with pytest.raises(CorpusConstructionError, match="stops before it"):
            resolve_governed_construction(
                corpus_manifest_path=corpus_path, dgs3mo_manifest_path=dgs_path,
                dgs3mo_path=dgs3mo, trial_ledger_path=ledger,
                frozen_dgs3mo_sha256=hashlib.sha256(dgs3mo.read_bytes()).hexdigest(),
                frozen_trial_ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest(),
                deployment_manifest_corpus_block={
                    "base_corpus_sha256": corpus.base_corpus_sha256,
                    "ordered_delta_manifest_sha256s": [],
                    "governed_universe_sha256": corpus.governed_universe_sha256,
                    "actions_manifest_sha256": corpus.actions_manifest_sha256,
                    "tickers_manifest_sha256": corpus.tickers_manifest_sha256,
                    "corpus_manifest_sha256": corpus.corpus_manifest_sha256,
                    "dgs3mo_manifest_sha256": dgs.dgs3mo_manifest_sha256},
                observation_session=S27, expected_sessions=())
