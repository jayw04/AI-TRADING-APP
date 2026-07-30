"""Tests for QUALIFIED O34 archive → harness adapter (ord: contract)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.risk.loss_control.phase0_o34_archive_adapter import (
    harness_can_consume_ord_mapping,
    iter_o3_replay_bundles,
    o4a_row_to_decision_time,
    o4b_row_to_forensic,
    open_qualified_archive,
    parse_ord_plan_id,
    sha256_file,
)

REPO = Path(__file__).resolve().parents[4]
ARCHIVE_DIR = (
    REPO
    / "docs"
    / "design"
    / "evidence"
    / "dbox_o34_acq_001"
    / "constructed"
    / "20260730T022316Z"
)

O3_SHA = "53b3310c8db3cdfd3d60a2de3bec990a6eaab8864dd592afc4590e57fc9008b0"
O4A_SHA = "3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49"
O4B_SHA = "e349f49465aa2689e6c24e20d6ae32286f0a447bfbcdf3b2fbbc531c656bae95"


def test_parse_ord_plan_id_accepts_and_refuses() -> None:
    assert parse_ord_plan_id("ord:1080") == 1080
    with pytest.raises(ValueError):
        parse_ord_plan_id("plan:1080")
    with pytest.raises(ValueError):
        parse_ord_plan_id("ord:0")
    with pytest.raises(ValueError):
        parse_ord_plan_id("ord:01")


def test_harness_can_consume_ord_mapping() -> None:
    assert harness_can_consume_ord_mapping() is True


@pytest.mark.skipif(not ARCHIVE_DIR.is_dir(), reason="QUALIFIED archives absent")
def test_open_and_map_qualified_archives() -> None:
    o3 = open_qualified_archive(ARCHIVE_DIR / "O3_CANDIDATE.json", expected_sha256=O3_SHA)
    bundles = iter_o3_replay_bundles(o3)
    assert len(bundles) == 292
    assert bundles[0]["plan_id"].startswith("ord:")

    o4a = open_qualified_archive(
        ARCHIVE_DIR / "O4A_CANDIDATE.json", expected_sha256=O4A_SHA
    )
    row_a = o4a["observations"][0]
    ev_a = o4a_row_to_decision_time(row_a)
    assert ev_a.fills == ()
    assert ev_a.symbols == ("F",)

    o4b = open_qualified_archive(
        ARCHIVE_DIR / "O4B_CANDIDATE.json", expected_sha256=O4B_SHA
    )
    row_b = o4b["observations"][0]
    ev_b = o4b_row_to_forensic(row_b)
    assert len(ev_b.fills) >= 1
    assert isinstance(ev_b.fill_loss_per_round_trip, Decimal)

    assert sha256_file(ARCHIVE_DIR / "O4A_CANDIDATE.json") == O4A_SHA


def test_o4a_refuses_lookahead() -> None:
    with pytest.raises(ValueError, match="look-ahead"):
        o4a_row_to_decision_time(
            {
                "plan_id": "ord:1",
                "quotes": {},
                "symbols": ["X"],
                "fills": [{"qty": "1"}],
                "terminal_broker_state": None,
                "post_submit_quotes": None,
            }
        )
