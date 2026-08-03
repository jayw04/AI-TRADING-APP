"""Contract tests for the ADR 0043 WS5 successor authorization verifier.

Written against the structural contract **before** the authorization document
existed, so the document is drafted to satisfy an already-failing test rather
than the verifier being shaped around whatever was drafted.

Negative fixtures are derived from the positive one by mutating exactly one
thing. That keeps each negative case honest about what it is testing: if a
negative passes, it is because the mutated property is genuinely unchecked, not
because two fixtures drifted apart.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_VERIFIER = _REPO_ROOT / "scripts" / "governance" / "hash_adr0043_ws5_successor_authorization.py"
_FIXTURES = _REPO_ROOT / "scripts" / "governance" / "fixtures" / "adr0043_ws5_successor"
_DOCUMENT = _REPO_ROOT / "docs" / "design" / "ADR0043_LIVE_CANARY_WS5_SUCCESSOR_START_001.md"

pytestmark = pytest.mark.skipif(not _VERIFIER.exists(), reason="successor verifier not present")


def _load():
    spec = importlib.util.spec_from_file_location("ws5_successor_verifier", _VERIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def V():
    return _load()


@pytest.fixture
def doc(V) -> str:
    return (_FIXTURES / "valid_authorization.md").read_text(encoding="utf-8")


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "doc.md"
    p.write_text(text, encoding="utf-8", newline="")
    return p


# ---------------------------------------------------------------- authorization: positive


def test_valid_authorization_fixture_verifies_and_hashes(V, doc, tmp_path):
    digest = V.compute_authorization(_write(tmp_path, doc))
    assert len(digest) == 64 and digest == digest.lower()


def test_authorization_hash_is_reproducible(V, doc, tmp_path):
    assert V.compute_authorization(_write(tmp_path, doc)) == V.compute_authorization(
        _write(tmp_path, doc)
    )


def test_only_self_referential_values_are_excluded(V):
    """Exclusions must cover only values that are self-referential or do not yet exist.

    The prior authorization also excluded ``runtime_name`` and ``database_identity``
    because there they were derived-from-hash and named-after-creation. Carrying that
    list over would have left the published identity not binding them.
    """
    assert set(V.NORMATIVE_EXCLUSIONS) == {"authorization_sha", "expires_on"}


def test_identity_has_three_reported_components(V, doc, tmp_path):
    ids = V.compute_identity(_write(tmp_path, doc))
    assert set(ids) == {"normative_body_sha256", "binding_manifest_sha256", "authorization_sha256"}
    assert all(len(v) == 64 for v in ids.values())


def test_authorization_identity_covers_both_components(V, doc, tmp_path):
    ids = V.compute_identity(_write(tmp_path, doc))
    expected = hashlib.sha256(
        (ids["normative_body_sha256"] + ids["binding_manifest_sha256"]).encode()
    ).hexdigest()
    assert ids["authorization_sha256"] == expected


def test_explanatory_prose_outside_the_payload_does_not_move_the_identity(V, doc, tmp_path):
    """Material outside the canonical payload is not part of the authorization identity."""
    mutated = doc.replace(
        "> \U0001f6a7 **DRAFT",
        "> \U0001f6a7 (editorial) **DRAFT",
    )
    assert mutated != doc, "prose anchor not found; this test would be vacuous"
    before = V.compute_identity(_write(tmp_path, doc))["authorization_sha256"]
    after = V.compute_identity(_write(tmp_path, mutated))["authorization_sha256"]
    assert after == before


BOUND_SCALARS = [
    ("runtime_instance", "i-0fff7076ad461aa9a", "i-0000000000000000"),
    ("data_volume", "vol-0710769fb6981102d", "vol-0000000000000000"),
    ("security_group", "sg-08b1284b33d9159c4", "sg-00000000000000000"),
    ("iam_role", "adr0043-canary-ws5-52b3ff136196-role", "some-other-role"),
    ("instance_profile", "adr0043-canary-ws5-52b3ff136196-profile", "some-other-profile"),
    (
        "ecr_repository",
        "219024422756.dkr.ecr.us-east-1.amazonaws.com/adr0043-canary-ws5",
        "219024422756.dkr.ecr.us-east-1.amazonaws.com/other-repo",
    ),
    ("evidence_bucket", "adr0043-ws5-evidence-219024422756-us-east-1", "other-bucket-name"),
    ("broker_account", "PA3E97RWHKQZ", "PA34USW0Q8UO"),
    (
        "alpaca_account_id",
        "0fa55b0d-74d6-4a61-a361-ab154857cfb5",
        "00000000-0000-0000-0000-000000000000",
    ),
    ("credential_key_fp", "ffab8796516a", "aaaaaaaaaaaa"),
    ("credential_secret_fp", "c2cab6509f1b", "bbbbbbbbbbbb"),
    (
        "source_commit",
        "1880fcdb05e367306e81fa96b355b996f73b7819",
        "ffffffffffffffffffffffffffffffffffffffff",
    ),
    (
        "source_archive_sha256",
        "17d24c3ead5ee00029b63b6d8df89cf8122bf078cc227efe6fe539d41731dd7c",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    ),
    (
        "source_object_version_id",
        "dEDhokQBpFY8u9AyF7KM0aHX1wDnEEpu",
        "OTHERVERSIONIDXXXXXXXXXXXXXXXXXX",
    ),
    (
        "dockerfile_sha256",
        "e4ee353aed8abdce98e8ac7881b928dcbb9c30ab1abef04dea0e261ae6be9042",
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    ),
    (
        "image_manifest_digest",
        "sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d",
        "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    ),
    (
        "image_index_digest",
        "sha256:59f3f26123ca0c19174fefc06575f960bb2c50c555c9eba23b0aaeb22f78071d",
        "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    ),
    (
        "image_config_digest",
        "sha256:a3c2081f067bc412061e285661264ab91a3ca20797d9f38c94cf72467cc9f584",
        "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    ),
    ("platform", "linux/arm64", "linux/amd64"),
    ("evidence_directory", "/var/lib/adr0043-ws5/evidence", "/var/lib/adr0043-ws5/other"),
    (
        "reserved_database_path",
        "/var/lib/adr0043-ws5/workbench.sqlite",
        "/var/lib/adr0043-ws5/other.sqlite",
    ),
    (
        "prior_authorization_sha",
        "52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae",
        "9999999999999999999999999999999999999999999999999999999999999999",
    ),
    (
        "expiration_rule",
        "authorization_effective_at + 14 calendar days",
        "authorization_effective_at + 30 calendar days",
    ),
    ("effectiveness_precondition", "owner approval + merge to main", "merge to main only"),
    (
        "permitted_endpoints",
        "GET /v2/account | GET /v2/positions",
        "GET /v2/account | GET /v2/assets",
    ),
    (
        "runtime_stack",
        "runtime_stack                = adr0043-canary-ws5-52b3ff136196",
        "runtime_stack                = other-stack",
    ),
    (
        "evidence_stack",
        "evidence_stack               = adr0043-canary-ws5-52b3ff136196-evidence",
        "evidence_stack               = other-evidence-stack",
    ),
    (
        "runtime_name",
        "runtime_name                 = adr0043-canary-ws5-52b3ff136196",
        "runtime_name                 = adr0043-canary-ws5-other",
    ),
]


@pytest.mark.parametrize("label,old,new", BOUND_SCALARS, ids=[c[0] for c in BOUND_SCALARS])
def test_every_bound_scalar_moves_the_authorization_identity(V, doc, tmp_path, label, old, new):
    """An identity that does not move when an operational value changes does not bind it."""
    assert old in doc, f"fixture lacks {old!r}; this mutation case would be vacuous"
    base = V.compute_identity(_write(tmp_path, doc))["authorization_sha256"]
    mutated = doc.replace(old, new)
    assert mutated != doc
    try:
        after = V.compute_identity(_write(tmp_path, mutated))["authorization_sha256"]
    except V.ContractError:
        return  # refused outright, which binds it at least as strongly
    assert after != base, f"changing {label} did not move the authorization identity"


def test_binding_manifest_moves_independently_of_prose(V, doc, tmp_path):
    """A prose edit moves the body digest but not the binding digest, so a reviewer can
    see which component changed and why."""
    base = V.compute_identity(_write(tmp_path, doc))
    prose = doc.replace("## 5. Infrastructure ceiling", "## 5. Infrastructure ceiling (scope)")
    after = V.compute_identity(_write(tmp_path, prose))
    assert after["binding_manifest_sha256"] == base["binding_manifest_sha256"]
    assert after["normative_body_sha256"] != base["normative_body_sha256"]
    assert after["authorization_sha256"] != base["authorization_sha256"]


@pytest.mark.parametrize("key", ["runtime_instance", "image_manifest_digest", "platform"])
def test_missing_binding_key_is_refused(V, doc, tmp_path, key):
    mutated = re.sub(r"(?m)^" + key + r"\s*=.*$", "", doc)
    with pytest.raises(V.ContractError):
        V.compute_identity(_write(tmp_path, mutated))


def test_duplicate_binding_key_is_refused(V, doc, tmp_path):
    mutated = doc.replace(
        "platform                     = linux/arm64",
        "platform                     = linux/arm64\nplatform                     = linux/amd64",
    )
    with pytest.raises(V.ContractError, match="2 times"):
        V.compute_identity(_write(tmp_path, mutated))


def test_normative_body_change_moves_the_hash(V, doc, tmp_path):
    base = V.compute_authorization(_write(tmp_path, doc))
    mutated = doc.replace("mutation_attempt_count", "mutation_attempts")
    assert V.compute_authorization(_write(tmp_path, mutated)) != base


def test_the_real_document_matches_the_fixture_contract(V):
    """The drafted authorization must satisfy the same contract as the fixture."""
    if not _DOCUMENT.exists():
        pytest.skip("authorization document not present in this checkout")
    assert len(V.compute_authorization(_DOCUMENT)) == 64


# ---------------------------------------------------------------- authorization: negative


@pytest.mark.parametrize(
    "label,old,new",
    [
        ("missing required stage", "### Stage C", "### Stage Q"),
        (
            "missing prior-refusal continuity",
            "does not amend, cure, reopen, extend or erase",
            "supersedes",
        ),
        ("unbounded artifact replacement", "replacement is closed", "replacement stays open"),
        ("invalid stage regression", "return to Stage B", "return to any stage"),
        (
            "clock-laundering omission",
            "does not restart, extend or amend the prior authorization clock",
            "resets the clock",
        ),
        ("anti-laundering omission", "two consecutive REFUSED", "some refusals"),
        ("wrong evidence mount", "/var/lib/adr0043-ws5/evidence", "/var/lib/adr0043-ws5"),
        ("database-root mount permitted", "volume root is not mounted", "volume root is mounted"),
        ("reserved db not declared", "RESERVED_PATH_NOT_CREATED", "CREATED"),
        (
            "stage-c override absent",
            "python -m app.brokers.adr0043_reconcile",
            "python -m app.main",
        ),
        (
            "prior authorization sha absent",
            "52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae",
            "0" * 64,
        ),
        ("source commit absent", "1880fcdb05e367306e81fa96b355b996f73b7819", "f" * 40),
        (
            "deployable digest absent",
            "sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d",
            "sha256:" + "b" * 64,
        ),
        ("broker account absent", "PA3E97RWHKQZ", "PA34USW0Q8UO"),
        ("adopted resource unnamed", "sg-08b1284b33d9159c4", "sg-unnamed"),
        ("execution mode absent", "ADOPT-CLEAN-UNUSED-RESOURCES", "ADOPT-ANYTHING"),
    ],
)
def test_contract_violations_are_refused(V, doc, tmp_path, label, old, new):
    assert old in doc, f"fixture does not contain {old!r}; the negative case is vacuous"
    with pytest.raises(V.ContractError):
        V.compute_authorization(_write(tmp_path, doc.replace(old, new)))


def test_wrong_deployable_digest_kind_is_refused(V, doc, tmp_path):
    """Describing the image INDEX as deployable must fail."""
    mutated = doc.replace(
        "The image index digest is **not** deployable",
        "The image index digest is the deployable identity",
    )
    with pytest.raises(V.ContractError):
        V.compute_authorization(_write(tmp_path, mutated))


def test_missing_body_boundaries_are_refused(V, tmp_path):
    with pytest.raises(V.ContractError):
        V.compute_authorization(_write(tmp_path, "# no sections here\n"))


# ---------------------------------------------------------------- evidence: helpers


def _evidence(V, **over) -> dict:
    rec = json.loads((_FIXTURES / "evidence_ready.json").read_text(encoding="utf-8"))
    rec.update(over)
    rec["artifact_sha256"] = V.record_body_sha256(rec)
    return rec


def _seal(tmp_path: Path, rec: dict) -> tuple[Path, str]:
    body = json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    p = tmp_path / "evidence.json"
    p.write_text(body, encoding="utf-8", newline="")
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- evidence: positive


@pytest.mark.parametrize("name,code", [("ready", 0), ("refused", 2), ("inconclusive", 3)])
def test_valid_evidence_fixtures_verify(V, tmp_path, name, code):
    rec = json.loads((_FIXTURES / f"evidence_{name}.json").read_text(encoding="utf-8"))
    p, digest = _seal(tmp_path, rec)
    assert V.verify_evidence_file(p, exit_code=code, evidence_file_sha256=digest)


def test_artifact_sha256_is_the_record_body_digest(V):
    rec = json.loads((_FIXTURES / "evidence_ready.json").read_text(encoding="utf-8"))
    assert rec["artifact_sha256"] == V.record_body_sha256(rec)


def test_evidence_file_digest_differs_from_record_body_digest(V, tmp_path):
    """The two digests are different by construction; conflating them is the bug."""
    rec = json.loads((_FIXTURES / "evidence_ready.json").read_text(encoding="utf-8"))
    _, file_digest = _seal(tmp_path, rec)
    assert file_digest != rec["artifact_sha256"]


# ---------------------------------------------------------------- evidence: negative


@pytest.mark.parametrize(
    "disp,bad_code",
    [
        ("READY", 2),
        ("READY", 3),
        ("REFUSED", 0),
        ("REFUSED", 3),
        ("INCONCLUSIVE", 0),
        ("INCONCLUSIVE", 2),
    ],
)
def test_exit_code_disposition_mismatch_is_refused(V, tmp_path, disp, bad_code):
    name = {"READY": "ready", "REFUSED": "refused", "INCONCLUSIVE": "inconclusive"}[disp]
    rec = json.loads((_FIXTURES / f"evidence_{name}.json").read_text(encoding="utf-8"))
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="exit code"):
        V.verify_evidence_file(p, exit_code=bad_code, evidence_file_sha256=digest)


def test_record_body_digest_mismatch_is_refused(V, tmp_path):
    rec = json.loads((_FIXTURES / "evidence_ready.json").read_text(encoding="utf-8"))
    rec["artifact_sha256"] = "0" * 64
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="record-body digest mismatch"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


def test_full_file_digest_mismatch_is_refused(V, tmp_path):
    rec = json.loads((_FIXTURES / "evidence_ready.json").read_text(encoding="utf-8"))
    p, _ = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="evidence file digest mismatch"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256="a" * 64)


def test_ready_without_all_four_reads_is_refused(V, tmp_path):
    rec = _evidence(V, approved_calls_in_order=["GET /v2/account", "GET /v2/positions"])
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="all four approved reads"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


def test_invalid_approved_call_order_is_refused(V, tmp_path):
    rec = _evidence(V, approved_calls_in_order=["GET /v2/positions", "GET /v2/account"])
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="approved_calls_in_order"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


@pytest.mark.parametrize("count", [1, 2, -1])
def test_nonzero_mutation_count_is_refused(V, tmp_path, count):
    rec = _evidence(V, mutation_attempt_count=count)
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="mutation_attempt_count"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


def test_identity_mismatch_refusal_with_extra_dispatches_is_refused(V, tmp_path):
    rec = _evidence(
        V,
        terminal_disposition="REFUSED",
        failure_code="account_identity_mismatch: expected X, got Y",
        approved_calls_in_order=["GET /v2/account"],
        transport_dispatch_count=3,
    )
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="dispatch exactly once"):
        V.verify_evidence_file(p, exit_code=2, evidence_file_sha256=digest)


def test_pre_dispatch_refusal_with_dispatches_is_refused(V, tmp_path):
    rec = _evidence(
        V,
        terminal_disposition="REFUSED",
        failure_code="missing_credentials: none",
        approved_calls_in_order=[],
        transport_dispatch_count=1,
    )
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="dispatch 0 times"):
        V.verify_evidence_file(p, exit_code=2, evidence_file_sha256=digest)


def test_unknown_disposition_is_refused(V, tmp_path):
    rec = _evidence(V, terminal_disposition="MAYBE")
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="unknown terminal_disposition"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


def test_index_digest_in_evidence_is_refused(V, tmp_path):
    """Evidence must bind the deployable manifest, never the index."""
    rec = _evidence(V, image_manifest_digest=V.IMAGE_INDEX_DIGEST)
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="INDEX digest"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


def test_authoritative_baseline_true_is_refused(V, tmp_path):
    rec = _evidence(V, authoritative_start_a_baseline=True)
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="authoritative_start_a_baseline"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


def test_missing_required_evidence_field_is_refused(V, tmp_path):
    rec = json.loads((_FIXTURES / "evidence_ready.json").read_text(encoding="utf-8"))
    rec.pop("run_id")
    rec["artifact_sha256"] = V.record_body_sha256(rec)
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="missing required evidence fields"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)


def test_dispatch_without_credential_fingerprint_is_refused(V, tmp_path):
    rec = _evidence(V, credential_key_fingerprint="", transport_dispatch_count=4)
    p, digest = _seal(tmp_path, rec)
    with pytest.raises(V.ContractError, match="without a credential fingerprint"):
        V.verify_evidence_file(p, exit_code=0, evidence_file_sha256=digest)
