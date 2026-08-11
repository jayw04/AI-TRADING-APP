"""Tests for WP-D — the sealed-store export.

The export exists to make the OOS DENY enforceable, so the tests care about two
things above all:

  1. **An object must still mean what the corpus meant.** Parquet is a lossy
     place to be careless: a narrowed float, a NULL collapsed to empty string, a
     timestamp shifted by a session zone. Each would produce a perfectly valid
     object holding subtly different data, and the DENY would then be protecting
     the wrong bytes. So the round-trip check is asserted, and asserted to FAIL
     when the commitment it checks against disagrees.

  2. **Verification must not read an uploaded object.** A GetObject on the
     validation prefix before authorization is the precise event P7 must
     evidence as zero, and CloudTrail is append-only, so committing that
     mistake once would be permanent. One test reads this module's own source
     and asserts no S3 read call exists in it.

Runs against the synthetic fixture from the P9/P6 suite. No network, no AWS.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

# Import the P9/P6 suite FIRST and reuse its module instance. Loading our own copy would
# give the export module a different `sealed_partition_commitment` than the one the shared
# `corpus` fixture patches, and every window would silently resolve to the real frozen
# design instead of the synthetic one.
import test_sealed_partition_commitment as T  # noqa: E402

S = T.S
corpus = T.corpus  # noqa: F811 — shared fixture, re-exported for pytest to collect


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


E = _load("sealed_store_export")


def _p6(corpus):
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        return S.build_records(
            con, custodian="c", authority="a", produced_at="2026-08-11T00:00:00Z"
        )["P6"]


def _export(corpus, tmp_path, p6=None):
    p6 = p6 or _p6(corpus)
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        return E.export_store(con, tmp_path / "store", p6), p6


# ---------------------------------------------------------------------------
# Coverage and correspondence with P6
# ---------------------------------------------------------------------------


def test_every_partition_and_table_gets_exactly_one_object(corpus, tmp_path):
    objects, _ = _export(corpus, tmp_path)
    expected = len(E.PARTITIONS) * len(S.OBSERVATION_TABLES) + len(S.REFERENCE_TABLES)
    assert len(objects) == expected


def test_every_object_matches_the_p6_commitment(corpus, tmp_path):
    objects, _ = _export(corpus, tmp_path)
    assert all(o["matches_p6_commitment"] for o in objects.values())
    assert all(o["round_trip_verified"] for o in objects.values())


def test_parquet_round_trip_preserves_canonical_content(corpus, tmp_path):
    """The property the whole export rests on: object content == corpus content."""
    objects, p6 = _export(corpus, tmp_path)
    committed = p6["validation_partition"]["tables"]["prices"]["content_sha256"]
    assert objects["validation/prices.parquet"]["content_sha256"] == committed


def test_a_disagreeing_commitment_refuses(corpus, tmp_path):
    """If P6 and the object disagree, the export must stop, not prefer one."""
    p6 = _p6(corpus)
    p6["validation_partition"]["tables"]["prices"]["content_sha256"] = "f" * 64
    with pytest.raises(E.ExportRefused) as exc:
        _export(corpus, tmp_path, p6)
    assert "commitment_mismatch" in str(exc.value)


def test_an_object_absent_from_the_commitment_refuses(corpus, tmp_path):
    """Exporting something P6 never committed to would put unverifiable data in the store."""
    p6 = _p6(corpus)
    del p6["validation_partition"]["tables"]["prices"]
    with pytest.raises(E.ExportRefused) as exc:
        _export(corpus, tmp_path, p6)
    assert "uncommitted_object" in str(exc.value)


def test_sealed_and_open_prefixes_are_separated(corpus, tmp_path):
    objects, p6 = _export(corpus, tmp_path)
    manifest = E.build_manifest(
        objects, p6, custodian="c", authority="a", produced_at="2026-08-11T00:00:00Z"
    )
    assert manifest["sealed_prefixes"] == ["validation", "oos"]
    assert set(manifest["prefix_summary"]) == {"development", "validation", "oos", "reference"}


def test_validation_and_oos_objects_are_distinct_files(corpus, tmp_path):
    """If these collided, the DENY would either block validation or expose OOS."""
    objects, _ = _export(corpus, tmp_path)
    assert (
        objects["validation/prices.parquet"]["content_sha256"]
        != objects["oos/prices.parquet"]["content_sha256"]
    )


def test_row_counts_across_partitions_reconcile_with_the_corpus(corpus, tmp_path):
    objects, _ = _export(corpus, tmp_path)
    exported = sum(
        objects[f"{p}/prices.parquet"]["row_count"] for p in E.PARTITIONS
    )
    with S.open_snapshot(corpus["path"], corpus["sha256"]) as con:
        (total,) = con.execute("SELECT COUNT(*) FROM prices").fetchone()
    assert exported == total


# ---------------------------------------------------------------------------
# The P7 trap
# ---------------------------------------------------------------------------


def test_export_module_never_reads_an_object_from_s3():
    """Read-back verification would manufacture the pre-authorization validation read
    that P7 must show is zero, and CloudTrail would record it permanently."""
    source = (MODULE_DIR / "sealed_store_export.py").read_text(encoding="utf-8")
    for forbidden in ("get_object", "download_file", "download_fileobj", "head_object"):
        assert f".{forbidden}(" not in source


def test_export_module_makes_no_aws_call_at_all():
    source = (MODULE_DIR / "sealed_store_export.py").read_text(encoding="utf-8")
    assert "boto3" not in source
    assert "import boto3" not in source


# ---------------------------------------------------------------------------
# Manifest integrity
# ---------------------------------------------------------------------------


def test_manifest_identity_is_stable_and_covers_the_content(corpus, tmp_path):
    objects, p6 = _export(corpus, tmp_path)
    args = {"custodian": "c", "authority": "a", "produced_at": "2026-08-11T00:00:00Z"}
    first = E.build_manifest(objects, p6, **args)
    second = E.build_manifest(objects, p6, **args)
    assert first["manifest_identity_sha256"] == second["manifest_identity_sha256"]

    mutated = dict(objects)
    key = "validation/prices.parquet"
    mutated[key] = {**mutated[key], "row_count": mutated[key]["row_count"] + 1}
    assert E.build_manifest(mutated, p6, **args)["manifest_identity_sha256"] != first[
        "manifest_identity_sha256"
    ]


def test_manifest_binds_the_p6_commitment_it_was_verified_against(corpus, tmp_path):
    objects, p6 = _export(corpus, tmp_path)
    manifest = E.build_manifest(
        objects, p6, custodian="c", authority="a", produced_at="2026-08-11T00:00:00Z"
    )
    assert manifest["bound_p6_commitment_identity_sha256"] == p6["commitment_identity_sha256"]


def test_manifest_grants_nothing(corpus, tmp_path):
    objects, p6 = _export(corpus, tmp_path)
    manifest = E.build_manifest(
        objects, p6, custodian="c", authority="a", produced_at="2026-08-11T00:00:00Z"
    )
    assert "validation_authorization remains false" in manifest["boundary"]


def test_manifest_does_not_leak_sealed_membership(corpus, tmp_path):
    objects, p6 = _export(corpus, tmp_path)
    manifest = E.build_manifest(
        objects, p6, custodian="c", authority="a", produced_at="2026-08-11T00:00:00Z"
    )
    blob = json.dumps(manifest)
    for ticker in ("ZZTOPSECRET", "QQHIDDEN"):
        assert ticker not in blob


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
