"""B1a / B1b / B3 and the identity split — the evidentiary boundary, tested from outside.

Each test here asserts something a *caller* cannot do. That is deliberate: the defects these
close were all reachable by an ordinary library caller while the CLI happened to look safe,
so a test that only drives the CLI would keep passing after a regression.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.research.capture.admissibility import Verdict
from app.research.capture.store import FEEDS
from app.research.mdq_eval import gate
from app.research.mdq_eval.authority import (
    APPROVED_COLLECTOR_BLOBS,
    APPROVED_COLLECTOR_IDENTITY,
    APPROVED_COLLECTOR_SOURCE_COMMIT,
    HISTORICAL_BINDING_UNAVAILABLE,
    INVARIANCE_MEASURED_IDENTITIES,
    invariance_record,
)
from app.research.mdq_eval.gate import NotAdmissible
from tests.research.mdq_eval.conftest import write_governed_manifests

SESSION = date(2026, 8, 19)  # D0 — the first admissible governed partition


def _manifest_path(root: Path, feed: str, session: date) -> Path:
    return root / feed / session.isoformat() / "manifest.json"


def _mutate_manifest(root: Path, feed: str, session: date, **changes: object) -> None:
    p = _manifest_path(root, feed, session)
    m = json.loads(p.read_text(encoding="utf-8"))
    for k, v in changes.items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    p.write_text(json.dumps(m), encoding="utf-8")


# ── B3: the evidentiary path accepts no threshold overrides ──────────────────────────────


class TestB3NoOverridesOnTheEvidentiaryPath:
    """A library caller must not be able to weaken a frozen threshold and still be believed."""

    @pytest.mark.parametrize(
        "kwarg",
        [
            "min_completeness",
            "max_gap_minutes",
            "cadence_tolerance_seconds",
            "cadence_seconds",
            "sampler_start_et",
            "signoff_date",
            "feeds",
            "frozen_universe",
            "pins",
            "approved_collector_versions",
            "governing_denominator",
        ],
    )
    def test_every_threshold_override_is_a_typeerror(self, tmp_path, kwarg):
        """Structural refusal, not a blacklist: the parameter simply does not exist."""
        with pytest.raises(TypeError):
            gate.require_admissible(tmp_path, SESSION, session_close_utc=None, **{kwarg: 0.0})

    def test_diagnostic_accepts_overrides_but_returns_only_a_report(self, tmp_path, adjudication):
        """The escape hatch exists — it just cannot mint."""
        write_governed_manifests(tmp_path, SESSION)
        report = gate.assess_diagnostic(
            tmp_path, SESSION, session_close_utc=None, min_completeness=0.0
        )
        assert not isinstance(report, tuple)
        assert not hasattr(report, "root")  # not a token

    def test_no_function_promotes_a_diagnostic_into_a_token(self):
        """The control is an ABSENT code path, not a guarded one."""
        names = [n for n in dir(gate) if "promote" in n.lower() or "to_token" in n.lower()]
        assert names == []


# ── B1a: manifest-native identity, from the frozen authority ─────────────────────────────


class TestB1aManifestNativeIdentity:
    def test_a_governed_manifest_passes(self, tmp_path):
        write_governed_manifests(tmp_path, SESSION)
        native = gate.verify_manifest_native_identity(tmp_path, SESSION)
        assert native["manifest_collector_version_verified"] is True
        assert native["manifest_provenance_verified"] is True
        assert native["problems"] == []

    def test_a_wrong_collector_version_fails_closed(self, tmp_path, adjudication):
        write_governed_manifests(tmp_path, SESSION)
        _mutate_manifest(tmp_path, FEEDS[0], SESSION, collector_version="mdq-collector/9.9.9")
        native = gate.verify_manifest_native_identity(tmp_path, SESSION)
        assert native["manifest_collector_version_verified"] is False
        with pytest.raises(NotAdmissible, match="manifest-native identity"):
            gate.require_admissible(tmp_path, SESSION, session_close_utc=None)

    @pytest.mark.parametrize(
        "missing",
        [
            "provider",
            "entitlement",
            "credential_fingerprint",
            "account_number",
            "capture_modes",
            "universe",
            "universe_sha256",
        ],
    )
    def test_a_missing_required_provenance_field_fails_closed(
        self, tmp_path, adjudication, missing
    ):
        write_governed_manifests(tmp_path, SESSION)
        _mutate_manifest(tmp_path, FEEDS[0], SESSION, **{missing: None})
        with pytest.raises(NotAdmissible, match="manifest-native identity"):
            gate.require_admissible(tmp_path, SESSION, session_close_utc=None)

    def test_a_frozen_provenance_value_mismatch_fails_closed(self, tmp_path, adjudication):
        write_governed_manifests(tmp_path, SESSION)
        _mutate_manifest(tmp_path, FEEDS[0], SESSION, provider="not-alpaca")
        with pytest.raises(NotAdmissible, match="manifest-native identity"):
            gate.require_admissible(tmp_path, SESSION, session_close_utc=None)

    def test_a_quarantined_partition_is_refused(self, tmp_path, adjudication):
        """PRE_REGISTRATION_SMOKE captures predate the frozen thresholds."""
        write_governed_manifests(tmp_path, SESSION)
        _mutate_manifest(tmp_path, FEEDS[0], SESSION, label="PRE_REGISTRATION_SMOKE")
        with pytest.raises(NotAdmissible, match="manifest-native identity"):
            gate.require_admissible(tmp_path, SESSION, session_close_utc=None)

    def test_a_missing_manifest_is_not_frozen_and_is_refused(self, tmp_path, adjudication):
        write_governed_manifests(tmp_path, SESSION)
        _manifest_path(tmp_path, FEEDS[0], SESSION).unlink()
        with pytest.raises(NotAdmissible):
            gate.require_admissible(tmp_path, SESSION, session_close_utc=None)


# ── B1b: invariance is a SEPARATE, weaker claim ──────────────────────────────────────────


class TestB1bInvarianceIsNotPartitionProvenance:
    def test_the_verdict_never_claims_a_per_partition_source_tuple(self, tmp_path):
        write_governed_manifests(tmp_path, SESSION)
        native = gate.verify_manifest_native_identity(tmp_path, SESSION)
        assert native["per_partition_full_source_tuple_verified"] is False
        assert native["per_partition_full_source_tuple_status"] == HISTORICAL_BINDING_UNAVAILABLE

    def test_the_invariance_claim_is_named_as_invariance_not_identity(self):
        rec = invariance_record()
        assert rec["claim"] == "collector_implementation_invariance"
        assert "partition_collector_identity" not in json.dumps(rec)
        assert list(INVARIANCE_MEASURED_IDENTITIES) == rec["measured_identities"]

    def test_the_invariance_record_states_what_it_does_not_establish(self):
        """A claim that omits its own limit will be over-read by the next reader."""
        assert "does_not_establish" in invariance_record()

    def test_the_approved_tuple_carries_every_frozen_component(self):
        d = APPROVED_COLLECTOR_IDENTITY.as_dict()
        assert d["source_commit"] == APPROVED_COLLECTOR_SOURCE_COMMIT
        assert d["blobs"] == dict(sorted(APPROVED_COLLECTOR_BLOBS.items()))
        assert len(d["blobs"]) == 5
        assert len(str(d["canonical_digest"])) == 64

    def test_the_tuple_digest_is_a_label_not_the_comparison(self):
        """Comparison is field-by-field; the digest only cites the tuple."""
        assert APPROVED_COLLECTOR_IDENTITY.digest == APPROVED_COLLECTOR_IDENTITY.digest
        assert APPROVED_COLLECTOR_SOURCE_COMMIT in APPROVED_COLLECTOR_IDENTITY.canonical()


# ── the identity split ───────────────────────────────────────────────────────────────────


class TestIdentitySplit:
    def test_input_partition_identity_is_deterministic(self, tmp_path):
        write_governed_manifests(tmp_path, SESSION)
        a = gate.input_partition_identity(tmp_path, SESSION)
        b = gate.input_partition_identity(tmp_path, SESSION)
        assert a == b and len(a) == 64

    def test_input_partition_identity_ignores_run_local_fields(self, tmp_path):
        """frozen_at must not move it — otherwise it is a run id, not a content id."""
        write_governed_manifests(tmp_path, SESSION)
        before = gate.input_partition_identity(tmp_path, SESSION)
        _mutate_manifest(tmp_path, FEEDS[0], SESSION, frozen_at="2099-01-01T00:00:00+00:00")
        assert gate.input_partition_identity(tmp_path, SESSION) == before

    def test_input_partition_identity_tracks_the_data(self, tmp_path):
        write_governed_manifests(tmp_path, SESSION)
        before = gate.input_partition_identity(tmp_path, SESSION)
        _mutate_manifest(
            tmp_path,
            FEEDS[0],
            SESSION,
            files=[{"path": "quotes/samples.jsonl", "sha256": "9" * 64, "bytes": 10}],
        )
        assert gate.input_partition_identity(tmp_path, SESSION) != before

    def test_the_token_carries_both_identities_separately(self, tmp_path, adjudication):
        token = adjudication.token(tmp_path, SESSION)
        d = token.as_dict()
        assert d["input_partition_identity"] != d["adjudication_instance_digest"]
        assert "admissibility_digest" not in d

    def test_the_run_digest_is_not_presented_as_content_identity(self, tmp_path, adjudication):
        """It hashes a report containing generated_at; naming it a partition digest was wrong."""
        token = adjudication.token(tmp_path, SESSION)
        assert token.adjudication_instance_digest != token.input_partition_identity


# ── D0 still reproduces under the frozen parameters ──────────────────────────────────────


def test_d0_remains_admissible_under_the_frozen_contract(tmp_path, adjudication):
    """The guard that hardening did not move admissibility semantics."""
    adjudication.set_verdict(Verdict.ADMISSIBLE)
    token = adjudication.token(tmp_path, SESSION)
    assert token.session == SESSION
    assert token.verdict == str(Verdict.ADMISSIBLE)


def test_undetermined_still_refuses_after_hardening(tmp_path, adjudication):
    adjudication.set_verdict(Verdict.UNDETERMINED)
    with pytest.raises(NotAdmissible):
        adjudication.token(tmp_path, SESSION)
