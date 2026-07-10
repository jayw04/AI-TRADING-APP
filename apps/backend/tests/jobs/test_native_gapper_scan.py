"""Tests for the scheduled box-native gapper scan (``app.jobs.native_gapper_scan``)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.jobs import native_gapper_scan as job

FRIDAY = datetime(2026, 7, 10, 13, 5, tzinfo=UTC)     # Fri 09:05 ET
SATURDAY = datetime(2026, 7, 11, 13, 5, tzinfo=UTC)
DATE_STR = "2026-07-10"

_OK_RESULT = {
    "ok": True,
    "date": DATE_STR,
    "discovery_path": "movers",
    "discovered": 3,
    "verified": 2,
    "count": 1,
    "payload": {
        "scanned_at": "2026-07-10T13:05:00Z",
        "source": "box_native_alpaca_v1",
        "gappers": [{"rank": 1, "symbol": "AAA", "price": 10.0, "gap_pct": 8.0,
                     "premarket_volume": 100000, "catalyst": None, "headlines": []}],
    },
}


@pytest.fixture
def native_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        job, "get_settings", lambda: SimpleNamespace(native_gappers_dir=str(tmp_path))
    )
    return tmp_path


def _stub_scan(monkeypatch, result):
    calls = []

    async def _fake(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(job, "scan_native_gappers", _fake)
    return calls


async def test_weekend_skip(native_dir, monkeypatch):
    calls = _stub_scan(monkeypatch, _OK_RESULT)
    assert await job.run_native_gapper_scan(now=SATURDAY) is None
    assert calls == []
    assert list(native_dir.iterdir()) == []


async def test_success_writes_todays_file(native_dir, monkeypatch):
    _stub_scan(monkeypatch, dict(_OK_RESULT))
    result = await job.run_native_gapper_scan(now=FRIDAY)
    assert result is not None and result["ok"] is True
    assert result["status"] == "scan_success_non_empty"
    path = native_dir / f"premarket_gappers_{DATE_STR}.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["source"] == "box_native_alpaca_v1"


async def test_zero_candidates_still_writes_and_is_distinguished(native_dir, monkeypatch):
    """A scan that ran and found nothing writes an honest empty file (review §6) —
    distinct from scan_failed, which writes nothing."""
    empty = dict(_OK_RESULT, count=0,
                 payload={"scanned_at": "x", "source": "box_native_alpaca_v1", "gappers": []})
    _stub_scan(monkeypatch, empty)
    result = await job.run_native_gapper_scan(now=FRIDAY)
    assert result["status"] == "scan_success_zero_candidates"
    path = native_dir / f"premarket_gappers_{DATE_STR}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["gappers"] == []


async def test_existing_file_makes_retry_a_noop(native_dir, monkeypatch):
    (native_dir / f"premarket_gappers_{DATE_STR}.json").write_text("{}", encoding="utf-8")
    calls = _stub_scan(monkeypatch, _OK_RESULT)
    assert await job.run_native_gapper_scan(now=FRIDAY) is None
    assert calls == []  # idempotent: the 09:18 retry never re-scans after a good 09:05


async def test_force_overrides_exists_and_weekend(native_dir, monkeypatch):
    (native_dir / f"premarket_gappers_{DATE_STR}.json").write_text("{}", encoding="utf-8")
    calls = _stub_scan(monkeypatch, _OK_RESULT)
    result = await job.run_native_gapper_scan(now=FRIDAY, force=True)
    assert result is not None and len(calls) == 1
    # the placeholder got atomically replaced with the real payload
    payload = json.loads(
        (native_dir / f"premarket_gappers_{DATE_STR}.json").read_text(encoding="utf-8")
    )
    assert payload["gappers"][0]["symbol"] == "AAA"


async def test_failed_scan_writes_nothing(native_dir, monkeypatch):
    _stub_scan(monkeypatch, {"ok": False, "reason": "no_discovery_symbols"})
    assert await job.run_native_gapper_scan(now=FRIDAY) is None
    assert list(native_dir.iterdir()) == []  # reader falls back to external/stale


async def test_factor_store_is_passed_through(native_dir, monkeypatch):
    calls = _stub_scan(monkeypatch, _OK_RESULT)
    marker = object()
    await job.run_native_gapper_scan(marker, now=FRIDAY)
    assert calls[0]["factor_store"] is marker
