"""Regression tests for the WS5 authorization body-hash verifier (ADR0043 §17).

The hashes pinned here are governance facts, not implementation details. If a
change to the verifier moves either one, the verifier is wrong -- the
authorization body is what it is, and its canonical hash was countersigned.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_VERIFIER = _REPO_ROOT / "scripts" / "governance" / "hash_ws5_authorization.py"

ORIGINAL_HASH = "99f045e0953203a6e03d1d096e3d4a1ba7435f388c50762b701eb6e536738eb0"
AMENDMENT1_HASH = "52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae"


def _load():
    spec = importlib.util.spec_from_file_location("hash_ws5_authorization", _VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.skipif(
    not _VERIFIER.exists(), reason="governance verifier not present in this checkout"
)


@pytest.fixture(scope="module")
def hasher():
    return _load()


@pytest.fixture(scope="module")
def fixtures(hasher):
    return Path(hasher.__file__).with_name("fixtures")


def test_original_authorization_hash(hasher, fixtures):
    """The pre-amendment body hash is the countersigned 99f045e0... value."""
    assert hasher.compute(fixtures / "ws5_authorization_original.md") == ORIGINAL_HASH


def test_amendment1_hash(hasher, fixtures):
    assert hasher.compute(fixtures / "ws5_authorization_amendment1.md") == AMENDMENT1_HASH


def test_selftest_passes(hasher):
    assert hasher.selftest() == 0


def test_live_document_matches_amendment1(hasher):
    """The document under docs/design must hash to the amendment-1 value."""
    doc = (
        _REPO_ROOT
        / "docs"
        / "design"
        / "ADR0043_LIVE_CANARY_WS5_RUNTIME_PREP_START_001_PROPOSAL.md"
    )
    if not doc.exists():  # docs may be S3-resident in some checkouts (ADR 0050)
        pytest.skip("authorization document not present in this checkout")
    assert hasher.compute(doc) == AMENDMENT1_HASH


def test_crlf_does_not_change_the_hash(hasher, fixtures, tmp_path):
    """Canonicalization normalizes line endings, so a CRLF checkout is safe."""
    raw = (fixtures / "ws5_authorization_amendment1.md").read_bytes()
    crlf = tmp_path / "crlf.md"
    crlf.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert hasher.compute(crlf) == AMENDMENT1_HASH


def test_rejects_wrong_alembic_head(hasher, fixtures, tmp_path):
    body = (fixtures / "ws5_authorization_amendment1.md").read_text(encoding="utf-8")
    tampered = tmp_path / "bad_head.md"
    tampered.write_text(
        body.replace(
            "authorized_alembic_head  = b2d8f4c6a901", "authorized_alembic_head  = deadbeef1234"
        ),
        encoding="utf-8",
    )
    with pytest.raises(hasher.CanonicalizationError, match="authorized_alembic_head"):
        hasher.compute(tampered)


def test_rejects_abbreviated_source_commit(hasher, fixtures, tmp_path):
    body = (fixtures / "ws5_authorization_amendment1.md").read_text(encoding="utf-8")
    tampered = tmp_path / "short_sha.md"
    tampered.write_text(
        body.replace(
            "authorized_source_commit = 7342ebbd8e061518ba9bd0524803f8e20d760a78",
            "authorized_source_commit = 7342ebb",
        ),
        encoding="utf-8",
    )
    with pytest.raises(hasher.CanonicalizationError, match="40-char"):
        hasher.compute(tampered)


def test_rejects_missing_stage_2_block(hasher, fixtures, tmp_path):
    """Dropping a §15 operator-record fence must fail, not silently rehash."""
    body = (fixtures / "ws5_authorization_amendment1.md").read_text(encoding="utf-8")
    tampered = tmp_path / "one_fence.md"
    tampered.write_text(
        body.replace(
            "```\nruntime_resource_ids\ndatabase_identity\n",
            "runtime_resource_ids\ndatabase_identity\n",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(hasher.CanonicalizationError, match="fenced block"):
        hasher.compute(tampered)


def test_rejects_duplicated_excluded_scalar(hasher, fixtures, tmp_path):
    body = (fixtures / "ws5_authorization_amendment1.md").read_text(encoding="utf-8")
    tampered = tmp_path / "dup_scalar.md"
    tampered.write_text(
        body.replace(
            "expires_on        = 2026-08-16T23:59:59 America/Chicago",
            "expires_on        = 2026-08-16T23:59:59 America/Chicago\nexpires_on        = 2099-01-01T00:00:00 America/Chicago",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(hasher.CanonicalizationError, match="exactly once"):
        hasher.compute(tampered)


def test_excluded_values_do_not_affect_the_hash(hasher, fixtures, tmp_path):
    """Changing an excluded scalar must not move the hash -- that is why it is excluded."""
    body = (fixtures / "ws5_authorization_amendment1.md").read_text(encoding="utf-8")
    variant = tmp_path / "retagged.md"
    variant.write_text(
        body.replace(
            "authorization_sha = " + AMENDMENT1_HASH,
            "authorization_sha = " + "0" * 64,
        ),
        encoding="utf-8",
    )
    assert hasher.compute(variant) == AMENDMENT1_HASH


def test_normative_body_change_does_move_the_hash(hasher, fixtures, tmp_path):
    """A prohibition edit must change the hash -- the body is what is signed."""
    body = (fixtures / "ws5_authorization_amendment1.md").read_text(encoding="utf-8")
    variant = tmp_path / "weakened.md"
    variant.write_text(
        body.replace(
            "broker_order_adapter_enabled         = false",
            "broker_order_adapter_enabled         = true",
        ),
        encoding="utf-8",
    )
    assert hasher.compute(variant) != AMENDMENT1_HASH
