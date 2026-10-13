"""Named, explicit acceptance of a failing per-ticker vendor-data check (never silent)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.research.range002.data.manifest import parse_snapshot_manifest, verify_snapshot_files
from tests.research.range002.tooling.test_snapshot_manifest_and_fetch_universe import (
    DECISION,
    END,
    START,
    _make_export,
    bsm,
)


def _run(root: Path, out: Path, accept: list[str] | None = None) -> int:
    return bsm.run(
        root,
        out,
        table_filter="SEP",
        coverage_start=START.isoformat(),
        coverage_end=END.isoformat(),
        decision_days=[DECISION.isoformat()],
        accept_exceptions=accept,
    )


@pytest.fixture
def orphan_export(tmp_path: Path) -> Path:
    root = tmp_path / "orphan"
    root.mkdir()
    _make_export(root, orphan_sep_ticker=True)  # GHOST has prices but no TICKERS(SEP) row
    return root


def test_unnamed_failure_still_fails(orphan_export: Path) -> None:
    out = orphan_export / "snapshot_manifest.json"
    assert _run(orphan_export, out) == bsm.EXIT_INTEGRITY_FAILED
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["integrity"]["failed_checks"] == ["sep_tickers_without_tickers_row"]
    assert doc["integrity"]["accepted_exceptions"] == {}


def test_named_acceptance_passes_and_is_recorded_with_its_row_count(orphan_export: Path) -> None:
    out = orphan_export / "snapshot_manifest.json"
    code = _run(orphan_export, out, ["sep_tickers_without_tickers_row=GHOST"])
    assert code == bsm.EXIT_OK
    doc = json.loads(out.read_text(encoding="utf-8"))
    integ = doc["integrity"]
    assert integ["all_passed"] is True and integ["failed_checks"] == []
    rec = integ["accepted_exceptions"]["sep_tickers_without_tickers_row"]
    assert rec["identities"] == ["GHOST"] and rec["rows"] > 0
    assert doc["cross_table_consistent"] is False  # the consistency claim is untouched
    parsed = parse_snapshot_manifest(out.read_text(encoding="utf-8"))
    assert verify_snapshot_files(parsed, orphan_export, allow_sequential_pulls=True).ok
    assert not verify_snapshot_files(parsed, orphan_export).ok  # still needs the runner opt-in


def test_a_name_that_matches_no_failure_is_refused(orphan_export: Path) -> None:
    out = orphan_export / "snapshot_manifest.json"
    with pytest.raises(bsm.ManifestBuildError, match="do not match any failing identity"):
        _run(orphan_export, out, ["sep_tickers_without_tickers_row=NOPE"])
    assert not out.exists()


def test_only_the_two_per_ticker_checks_can_be_accepted(orphan_export: Path) -> None:
    out = orphan_export / "snapshot_manifest.json"
    with pytest.raises(bsm.ManifestBuildError):
        _run(orphan_export, out, ["expected_sessions_missing_from_sep=X"])


def test_naming_one_failing_identity_does_not_cover_another(tmp_path: Path) -> None:
    root = tmp_path / "two"
    root.mkdir()
    _make_export(root, orphan_sep_ticker=True)
    out = root / "snapshot_manifest.json"
    # an unrelated name alongside the right one is still refused (stale name)
    with pytest.raises(bsm.ManifestBuildError):
        _run(
            root,
            out,
            ["sep_tickers_without_tickers_row=GHOST", "sep_tickers_without_tickers_row=OTHER"],
        )
