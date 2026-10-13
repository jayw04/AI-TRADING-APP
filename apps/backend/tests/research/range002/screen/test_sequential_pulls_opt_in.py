"""Runner opt-in for a v2 ``sequential_pulls_evidence_checked`` snapshot (synthetic world).

Default behaviour is unchanged: a snapshot not declared cross-table consistent is refused. The
opt-in is explicit, needs the manifest's integrity checks to have passed, and the limitation text
is carried into both reports.
"""

from __future__ import annotations

# ruff: noqa: F811
import json
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.data.manifest import (
    CLASS_SEQUENTIAL_PULLS,
    MANIFEST_SCHEMA_V2,
    SEQUENTIAL_PULLS_LIMITATION,
)
from tests.research.range002.screen.test_descriptive_run_rehearsal import (  # noqa: F401, F811
    _runs,
    minutes_root,
    rds,
    world,
)


def _rewrite(world: dict[str, Any], **changes: Any) -> None:
    path: Path = world["kwargs"]["snapshot_manifest"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.update(changes)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _sequential(world: dict[str, Any], *, passed: bool | None = True) -> None:
    changes: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA_V2,
        "cross_table_consistent": False,
        "consistency_class": CLASS_SEQUENTIAL_PULLS,
        "consistency_basis": "sequential vendor pulls; evidence only",
    }
    if passed is not None:
        changes["integrity"] = {"all_passed": passed}
    _rewrite(world, **changes)


def test_sequential_manifest_is_refused_by_default(world: dict[str, Any]) -> None:
    _sequential(world)
    with pytest.raises(rds.DescriptiveRunRefusal, match="not declared cross-table consistent"):
        rds.run(**world["kwargs"])
    assert _runs(world) == ()


def test_opt_in_runs_and_carries_the_limitation(world: dict[str, Any]) -> None:
    _sequential(world)
    out = rds.run(**world["kwargs"], allow_sequential_pulls_ref="owner instruction 2026-10-13")
    sm = out.report["data"]["snapshot_manifest"]
    assert sm["cross_table_consistent"] is False
    assert sm["consistency_class"] == CLASS_SEQUENTIAL_PULLS
    assert sm["limitation"] == SEQUENTIAL_PULLS_LIMITATION
    assert sm["sequential_pulls_opt_in_ref"] == "owner instruction 2026-10-13"
    assert "sequential vendor API pulls" in out.report_md.read_text(encoding="utf-8")


@pytest.mark.parametrize("passed", [False, None])
def test_opt_in_does_not_override_failed_or_absent_integrity(
    world: dict[str, Any], passed: bool | None
) -> None:
    _sequential(world, passed=passed)
    with pytest.raises(rds.DescriptiveRunRefusal, match="integrity checks"):
        rds.run(**world["kwargs"], allow_sequential_pulls_ref="ref")
    assert _runs(world) == ()


def test_opt_in_does_not_rescue_a_v1_manifest_declared_false(world: dict[str, Any]) -> None:
    _rewrite(world, cross_table_consistent=False)
    with pytest.raises(rds.DescriptiveRunRefusal, match="not declared cross-table consistent"):
        rds.run(**world["kwargs"], allow_sequential_pulls_ref="ref")


def test_blank_opt_in_reference_is_refused(world: dict[str, Any]) -> None:
    _sequential(world)
    with pytest.raises(rds.DescriptiveRunRefusal, match="allow-sequential-pulls-ref"):
        rds.run(**world["kwargs"], allow_sequential_pulls_ref="  ")


def test_single_transaction_path_is_unchanged(world: dict[str, Any]) -> None:
    out = rds.run(**world["kwargs"])
    sm = out.report["data"]["snapshot_manifest"]
    assert sm["cross_table_consistent"] is True and sm["limitation"] is None
    assert sm["sequential_pulls_opt_in_ref"] is None
