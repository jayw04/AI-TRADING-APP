"""D1/D5/D10/D20 checkpoints and basis-safe returns. No DB, no MDQ."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.research.disc001 import checkpoints as checkpoints_mod
from app.research.disc001.checkpoints import (
    adjusted_return,
    build_checkpoints,
    nth_session_after,
)
from app.research.disc001.spec import PRICE_SOURCE_GAP, PRICE_SOURCE_SEP


def _sessions() -> list[tuple[date, float]]:
    # Mon 8/10 through Fri 9/4 — enough for D20 after 8/10.
    days = [
        date(2026, 8, 10),
        date(2026, 8, 11),
        date(2026, 8, 12),
        date(2026, 8, 13),
        date(2026, 8, 14),
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
        date(2026, 8, 21),
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
        date(2026, 9, 8),
    ]
    return [(d, 100.0 + i) for i, d in enumerate(days)]


def test_nth_session_after_skips_weekends():
    sessions = [d for d, _p in _sessions()]
    origin = date(2026, 8, 14)  # Friday
    assert nth_session_after(sessions, origin, 1) == date(2026, 8, 17)
    assert nth_session_after(sessions, origin, 5) == date(2026, 8, 21)
    assert nth_session_after(sessions, origin, 20) is None
    assert nth_session_after(sessions, date(2026, 8, 10), 20) == date(2026, 9, 8)


def test_nth_session_pending_when_not_enough_prints():
    sessions = [date(2026, 8, 19), date(2026, 8, 20)]
    assert nth_session_after(sessions, date(2026, 8, 19), 1) == date(2026, 8, 20)
    assert nth_session_after(sessions, date(2026, 8, 19), 5) is None


def test_return_withheld_on_basis_mismatch():
    assert (
        adjusted_return(
            10.0,
            12.0,
            proposal_basis=PRICE_SOURCE_GAP,
            later_basis=PRICE_SOURCE_SEP,
        )
        is None
    )
    assert adjusted_return(
        100.0,
        110.0,
        proposal_basis=PRICE_SOURCE_SEP,
        later_basis=PRICE_SOURCE_SEP,
    ) == pytest.approx(0.1)


def test_sep_checkpoints_fill_d1_and_leave_d20_pending_on_short_series():
    sessions = [
        (date(2026, 8, 19), 120.5),
        (date(2026, 8, 20), 130.0),
        (date(2026, 8, 21), 128.0),
    ]
    facts = build_checkpoints(
        proposal_price=120.5,
        proposal_basis=PRICE_SOURCE_SEP,
        proposal_source=PRICE_SOURCE_SEP,
        candidate_date=date(2026, 8, 19),
        sessions=sessions,
        later_source=PRICE_SOURCE_SEP,
        later_basis=PRICE_SOURCE_SEP,
    )
    by_name = {f.checkpoint: f for f in facts}
    assert by_name["PROPOSAL"].return_pct == 0.0
    assert by_name["D1"].price == 130.0
    assert by_name["D1"].price_as_of == "2026-08-20"
    assert by_name["D1"].return_pct == 130.0 / 120.5 - 1.0
    assert by_name["D5"].price is None
    assert by_name["D10"].price is None
    assert by_name["D20"].price is None
    assert by_name["CURRENT"].price == 128.0
    assert by_name["CURRENT"].return_pct == 128.0 / 120.5 - 1.0


def test_gap_later_sep_print_is_a_fact_without_return():
    facts = build_checkpoints(
        proposal_price=12.0,
        proposal_basis=PRICE_SOURCE_GAP,
        proposal_source=PRICE_SOURCE_GAP,
        candidate_date=date(2026, 8, 19),
        sessions=[(date(2026, 8, 19), 11.5), (date(2026, 8, 20), 13.0)],
        later_source=PRICE_SOURCE_SEP,
        later_basis=PRICE_SOURCE_SEP,
    )
    by_name = {f.checkpoint: f for f in facts}
    assert by_name["D1"].price == 13.0
    assert by_name["D1"].adjustment_basis == PRICE_SOURCE_SEP
    assert by_name["D1"].return_pct is None
    assert by_name["CURRENT"].price == 13.0
    assert by_name["CURRENT"].return_pct is None
    assert by_name["PROPOSAL"].adjustment_basis == PRICE_SOURCE_GAP


def test_d20_on_gap_horizon_is_still_emitted():
    sessions = _sessions()
    facts = build_checkpoints(
        proposal_price=12.0,
        proposal_basis=PRICE_SOURCE_GAP,
        proposal_source=PRICE_SOURCE_GAP,
        candidate_date=date(2026, 8, 10),
        sessions=sessions,
        later_source=PRICE_SOURCE_SEP,
        later_basis=PRICE_SOURCE_SEP,
    )
    d20 = next(f for f in facts if f.checkpoint == "D20")
    assert d20.price is not None
    assert d20.return_pct is None


def test_checkpoints_module_stays_off_db_order_path_and_mdq():
    text = Path(checkpoints_mod.__file__).read_text(encoding="utf-8")
    assert "app.db" not in text
    assert "app.orders" not in text
    assert "app.risk" not in text
    assert "app.brokers" not in text
    assert "mdq_collector" not in text
    assert "from app.mdq" not in text
    assert "FactorDataStore" not in text
