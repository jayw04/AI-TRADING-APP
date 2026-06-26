"""Bulk SF1 ingest — quarter-end date sweep logic (offline, no network)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_sf1_bulk.py"
_spec = importlib.util.spec_from_file_location("ingest_sf1_bulk", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
quarter_end_dates = _mod.quarter_end_dates


def test_full_years_are_four_quarters_each():
    ds = quarter_end_dates(2016, date(2018, 12, 31))
    assert len(ds) == 12  # 3 full years
    assert ds[0] == "2016-03-31" and ds[-1] == "2018-12-31"
    assert "2017-06-30" in ds and "2017-09-30" in ds


def test_excludes_future_quarters_inclusive_of_today():
    # a mid-quarter 'to' date includes only quarter-ends already passed
    ds = quarter_end_dates(2026, date(2026, 6, 21))
    assert ds == ["2026-03-31"]  # 2026-06-30 is in the future


def test_quarter_end_on_boundary_is_included():
    ds = quarter_end_dates(2025, date(2025, 6, 30))
    assert ds == ["2025-03-31", "2025-06-30"]
