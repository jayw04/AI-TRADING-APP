"""Tests for the read-only pre-market gappers ingest (``app.services.premarket_gappers``)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.services import premarket_gappers as pg
from app.utils.time import EASTERN


def _today_ny() -> str:
    return datetime.now(UTC).astimezone(EASTERN).date().isoformat()


def _write(directory, date: str, gappers: list[dict]) -> None:
    (directory / f"premarket_gappers_{date}.json").write_text(
        json.dumps({"scanned_at": f"{date}T12:30:00Z", "gappers": gappers}),
        encoding="utf-8",
    )


@pytest.fixture
def gapper_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "_directory", lambda: str(tmp_path))
    return tmp_path


def test_missing_directory_returns_empty_stale(monkeypatch):
    monkeypatch.setattr(pg, "_directory", lambda: "/no/such/dir")
    out = pg.read_latest_gappers()
    assert out == {
        "date": None,
        "scanned_at": None,
        "count": 0,
        "gappers": [],
        "stale": True,
    }


def test_empty_directory_returns_empty_stale(gapper_dir):
    out = pg.read_latest_gappers()
    assert out["count"] == 0
    assert out["gappers"] == []
    assert out["stale"] is True


def test_todays_file_is_fresh_and_parsed(gapper_dir):
    today = _today_ny()
    _write(
        gapper_dir,
        today,
        [{"rank": 1, "symbol": "BFLY", "price": 8.9, "gap_pct": 55.87,
          "premarket_volume": 60480000, "catalyst": "x", "headlines": ["h1"]}],
    )
    out = pg.read_latest_gappers()
    assert out["stale"] is False
    assert out["date"] == today
    assert out["count"] == 1
    assert out["gappers"][0]["symbol"] == "BFLY"
    assert out["scanned_at"] == f"{today}T12:30:00Z"


def test_old_file_is_stale(gapper_dir):
    _write(gapper_dir, "2020-01-02", [{"rank": 1, "symbol": "OLD"}])
    out = pg.read_latest_gappers()
    assert out["date"] == "2020-01-02"
    assert out["stale"] is True
    assert out["count"] == 1


def test_latest_date_wins(gapper_dir):
    _write(gapper_dir, "2020-01-02", [{"rank": 1, "symbol": "OLD"}])
    _write(gapper_dir, "2020-06-15", [{"rank": 1, "symbol": "NEW"}])
    out = pg.read_latest_gappers()
    assert out["date"] == "2020-06-15"
    assert out["gappers"][0]["symbol"] == "NEW"


def test_malformed_json_degrades_to_empty(gapper_dir):
    (gapper_dir / "premarket_gappers_2020-06-15.json").write_text("{not json", encoding="utf-8")
    out = pg.read_latest_gappers()
    assert out["count"] == 0
    assert out["gappers"] == []
    assert out["stale"] is True
    assert out["date"] == "2020-06-15"
