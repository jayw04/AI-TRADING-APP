"""Tests for the gappers-file resolution (``app.services.premarket_gappers``).

Covers the original single-dir behaviours (missing/empty/stale/malformed) and the
ADR 0041 two-producer precedence: native-wins for today, external catalyst
enrichment, external fallback, and newest-stale across both directories.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.services import premarket_gappers as pg
from app.utils.time import EASTERN


def _today_ny() -> str:
    return datetime.now(UTC).astimezone(EASTERN).date().isoformat()


def _write(directory, date: str, gappers: list[dict], *, source: str | None = None) -> None:
    payload: dict = {"scanned_at": f"{date}T12:30:00Z", "gappers": gappers}
    if source:
        payload["source"] = source
    (directory / f"premarket_gappers_{date}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """(external_dir, native_dir), both patched into the module."""
    external = tmp_path / "external"
    native = tmp_path / "native"
    external.mkdir()
    native.mkdir()
    monkeypatch.setattr(pg, "_directory", lambda: str(external))
    monkeypatch.setattr(pg, "_native_directory", lambda: str(native))
    return external, native


@pytest.fixture
def gapper_dir(dirs):
    """External dir only — the original single-producer scenarios."""
    return dirs[0]


def test_missing_directories_return_empty_stale(monkeypatch):
    monkeypatch.setattr(pg, "_directory", lambda: "/no/such/dir")
    monkeypatch.setattr(pg, "_native_directory", lambda: "/no/such/native")
    out = pg.read_latest_gappers()
    assert out == {
        "date": None,
        "scanned_at": None,
        "count": 0,
        "gappers": [],
        "stale": True,
        "source": None,
    }


def test_empty_directory_returns_empty_stale(gapper_dir):
    out = pg.read_latest_gappers()
    assert out["count"] == 0
    assert out["gappers"] == []
    assert out["stale"] is True


def test_todays_external_file_is_fresh_and_parsed(gapper_dir):
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
    assert out["source"] == pg.SOURCE_EXTERNAL


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


# --- ADR 0041 precedence: native authoritative, external enriches/falls back ---


def test_native_today_is_authoritative(dirs):
    external, native = dirs
    today = _today_ny()
    _write(native, today, [{"rank": 1, "symbol": "NAT", "price": 12.0, "gap_pct": 9.0,
                            "premarket_volume": 100000, "catalyst": None, "headlines": []}],
           source="box_native_alpaca_v1")
    _write(external, today, [{"rank": 1, "symbol": "EXT", "price": 5.0, "gap_pct": 20.0,
                              "premarket_volume": 900000, "catalyst": "ext news"}])
    out = pg.read_latest_gappers()
    assert out["stale"] is False
    assert out["source"] == "box_native_alpaca_v1"
    # EXT is external-only — it must NOT enter the operational list
    assert [g["symbol"] for g in out["gappers"]] == ["NAT"]


def test_external_catalyst_enriches_matching_native_symbol(dirs):
    external, native = dirs
    today = _today_ny()
    _write(native, today, [{"rank": 1, "symbol": "BOTH", "price": 12.0, "gap_pct": 9.0,
                            "premarket_volume": 100000, "catalyst": None, "headlines": []}],
           source="box_native_alpaca_v1")
    _write(external, today, [{"rank": 3, "symbol": "BOTH", "price": 11.9, "gap_pct": 8.7,
                              "premarket_volume": 90000, "catalyst": "earnings beat",
                              "headlines": ["h1", "h2"]}])
    out = pg.read_latest_gappers()
    row = out["gappers"][0]
    # enrichment only: catalyst/headlines joined, native price/gap/rank kept
    assert row["catalyst"] == "earnings beat"
    assert row["headlines"] == ["h1", "h2"]
    assert row["price"] == 12.0 and row["gap_pct"] == 9.0 and row["rank"] == 1


def test_external_fallback_when_native_missing_today(dirs):
    external, native = dirs
    today = _today_ny()
    _write(native, "2020-01-02", [{"rank": 1, "symbol": "OLDNAT"}], source="box_native_alpaca_v1")
    _write(external, today, [{"rank": 1, "symbol": "EXT", "catalyst": "c"}])
    out = pg.read_latest_gappers()
    assert out["stale"] is False
    assert out["source"] == pg.SOURCE_EXTERNAL
    assert out["gappers"][0]["symbol"] == "EXT"


def test_newest_stale_across_both_dirs(dirs):
    external, native = dirs
    _write(native, "2020-01-02", [{"rank": 1, "symbol": "OLDNAT"}], source="box_native_alpaca_v1")
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "NEWEXT"}])
    out = pg.read_latest_gappers()
    assert out["stale"] is True
    assert out["date"] == "2020-06-15"
    assert out["gappers"][0]["symbol"] == "NEWEXT"
    assert out["source"] == pg.SOURCE_EXTERNAL


def test_same_date_stale_tie_prefers_native(dirs):
    external, native = dirs
    _write(native, "2020-06-15", [{"rank": 1, "symbol": "NAT"}], source="box_native_alpaca_v1")
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "EXT"}])
    out = pg.read_latest_gappers()
    assert out["stale"] is True
    assert out["source"] == "box_native_alpaca_v1"
    assert out["gappers"][0]["symbol"] == "NAT"


def test_unparseable_native_today_falls_back_to_external(dirs):
    external, native = dirs
    today = _today_ny()
    (native / f"premarket_gappers_{today}.json").write_text("{broken", encoding="utf-8")
    _write(external, today, [{"rank": 1, "symbol": "EXT"}])
    out = pg.read_latest_gappers()
    assert out["stale"] is False
    assert out["source"] == pg.SOURCE_EXTERNAL
    assert out["gappers"][0]["symbol"] == "EXT"


# --- read_gappers_for: point-in-time resolution (ADR 0041 rules 1-2, never rule 3) ----------


def test_read_gappers_for_native_is_authoritative_for_that_day(dirs):
    external, native = dirs
    _write(native, "2020-06-15", [{"rank": 1, "symbol": "NAT"}], source="box_native_alpaca_v1")
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "EXT"}])
    out = pg.read_gappers_for("2020-06-15")
    assert out["date"] == "2020-06-15"
    assert [g["symbol"] for g in out["gappers"]] == ["NAT"]
    assert out["source"] == "box_native_alpaca_v1"
    assert out["stale"] is False


def test_read_gappers_for_external_when_no_native_that_day(dirs):
    external, _native = dirs
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "EXT"}])
    out = pg.read_gappers_for("2020-06-15")
    assert [g["symbol"] for g in out["gappers"]] == ["EXT"]
    assert out["source"] == pg.SOURCE_EXTERNAL
    assert out["stale"] is False


def test_read_gappers_for_enriches_catalyst_from_same_day_external(dirs):
    external, native = dirs
    _write(native, "2020-06-15", [{"rank": 1, "symbol": "NAT"}], source="box_native_alpaca_v1")
    _write(external, "2020-06-15",
           [{"rank": 1, "symbol": "NAT", "catalyst": "FDA nod", "headlines": ["h1"]}])
    out = pg.read_gappers_for("2020-06-15")
    assert out["gappers"][0]["catalyst"] == "FDA nod"
    assert out["gappers"][0]["headlines"] == ["h1"]


def test_read_gappers_for_does_not_enrich_from_a_different_day(dirs):
    """Enrichment is same-date only — yesterday's catalyst is not today's."""
    external, native = dirs
    _write(native, "2020-06-16", [{"rank": 1, "symbol": "NAT"}], source="box_native_alpaca_v1")
    _write(external, "2020-06-15",
           [{"rank": 1, "symbol": "NAT", "catalyst": "STALE", "headlines": ["old"]}])
    out = pg.read_gappers_for("2020-06-16")
    assert out["gappers"][0].get("catalyst") is None


def test_read_gappers_for_missing_day_is_empty_and_does_not_fall_back(dirs):
    """Regression (the asof bug): a neighbouring day must never stand in.

    read_latest_gappers deliberately falls back to the newest file (rule 3); read_gappers_for
    must not — for the gate that would record the prior day's candidates under today's asof.
    """
    external, native = dirs
    _write(native, "2020-06-15", [{"rank": 1, "symbol": "YESTERDAY_NAT"}],
           source="box_native_alpaca_v1")
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "YESTERDAY_EXT"}])
    out = pg.read_gappers_for("2020-06-16")
    assert out == {
        "date": None, "scanned_at": None, "count": 0, "gappers": [],
        "stale": True, "source": None,
    }
    # ...and read_latest_gappers still DOES fall back — the two readers stay distinct.
    assert pg.read_latest_gappers()["count"] == 1


def test_read_gappers_for_ignores_a_later_file(dirs):
    external, _native = dirs
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "WANTED"}])
    _write(external, "2020-06-16", [{"rank": 1, "symbol": "NEWER"}])
    assert pg.read_gappers_for("2020-06-15")["gappers"][0]["symbol"] == "WANTED"


def test_read_gappers_for_accepts_a_date_object(dirs):
    from datetime import date

    external, _native = dirs
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "PIT"}])
    assert pg.read_gappers_for(date(2020, 6, 15))["gappers"][0]["symbol"] == "PIT"


def test_read_gappers_for_unparseable_native_falls_through_to_external(dirs):
    external, native = dirs
    (native / "premarket_gappers_2020-06-15.json").write_text("{not json", encoding="utf-8")
    _write(external, "2020-06-15", [{"rank": 1, "symbol": "EXT"}])
    out = pg.read_gappers_for("2020-06-15")
    assert out["gappers"][0]["symbol"] == "EXT"
    assert out["source"] == pg.SOURCE_EXTERNAL


def test_read_gappers_for_missing_directories_are_empty(monkeypatch):
    monkeypatch.setattr(pg, "_directory", lambda: "/no/such/dir")
    monkeypatch.setattr(pg, "_native_directory", lambda: "/no/such/native")
    assert pg.read_gappers_for("2020-06-15")["count"] == 0


def test_read_gappers_for_non_list_gappers_degrades(dirs):
    external, _native = dirs
    (external / "premarket_gappers_2020-06-15.json").write_text(
        json.dumps({"scanned_at": "x", "gappers": "oops"}), encoding="utf-8"
    )
    out = pg.read_gappers_for("2020-06-15")
    assert out["count"] == 0
    assert out["gappers"] == []
