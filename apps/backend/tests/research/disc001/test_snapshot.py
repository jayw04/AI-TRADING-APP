"""DISC-001 snapshot checksum + retention."""

from __future__ import annotations

from pathlib import Path

from app.research.disc001.snapshot import (
    prune_snapshots,
    read_snapshot,
    snapshot_sha256,
    write_snapshot,
)


def _payload(as_of: str) -> dict:
    return {
        "as_of": as_of,
        "universe_id": "SEP-liquid-v0",
        "families": {},
        "all": {"count": 0, "items": []},
    }


def test_write_read_roundtrip_and_checksum(tmp_path: Path):
    write_snapshot(tmp_path, _payload("2026-08-18"))
    loaded = read_snapshot(tmp_path, "2026-08-18")
    assert loaded is not None
    assert loaded["as_of"] == "2026-08-18"
    assert loaded["sha256"] == snapshot_sha256(loaded)


def test_tampered_checksum_fails_closed(tmp_path: Path):
    path = write_snapshot(tmp_path, _payload("2026-08-18"))
    text = path.read_text(encoding="utf-8").replace("SEP-liquid-v0", "tampered")
    path.write_text(text, encoding="utf-8")
    assert read_snapshot(tmp_path, "2026-08-18") is None


def test_prune_keeps_newest(tmp_path: Path, monkeypatch):
    from app.research.disc001 import snapshot as snap_mod

    monkeypatch.setattr(snap_mod, "SNAPSHOT_MAX_FILES", 2)
    monkeypatch.setattr(snap_mod, "SNAPSHOT_RETENTION_DAYS", 3650)
    write_snapshot(tmp_path, _payload("2026-08-16"))
    write_snapshot(tmp_path, _payload("2026-08-17"))
    write_snapshot(tmp_path, _payload("2026-08-18"))
    dates = sorted(p.name for p in tmp_path.glob("watchlist_*.json"))
    assert "watchlist_2026-08-18.json" in dates
    assert "watchlist_2026-08-16.json" not in dates
    removed = prune_snapshots(tmp_path)
    assert "2026-08-18" not in removed


def test_prune_preserves_pinned_as_of(tmp_path: Path, monkeypatch):
    from app.research.disc001 import snapshot as snap_mod
    from app.research.disc001.spec import SNAPSHOT_PINS_FILENAME

    monkeypatch.setattr(snap_mod, "SNAPSHOT_MAX_FILES", 2)
    monkeypatch.setattr(snap_mod, "SNAPSHOT_RETENTION_DAYS", 3650)
    (tmp_path / SNAPSHOT_PINS_FILENAME).write_text('{"as_of": ["2026-08-16"]}', encoding="utf-8")
    write_snapshot(tmp_path, _payload("2026-08-16"))
    write_snapshot(tmp_path, _payload("2026-08-17"))
    write_snapshot(tmp_path, _payload("2026-08-18"))
    names = {p.name for p in tmp_path.glob("watchlist_*.json")}
    assert "watchlist_2026-08-16.json" in names
    assert "watchlist_2026-08-18.json" in names
    assert "watchlist_2026-08-17.json" not in names


def test_inspect_payload_reports_fail_closed():
    from app.research.disc001.snapshot import inspect_payload

    view = inspect_payload(
        {
            "as_of": "2026-08-18",
            "universe_id": "SEP-liquid-v0",
            "screen_id": "DISC-001-WATCHLIST",
            "screen_version": "v0.3.0",
            "price_source": "sharadar.sep",
            "sha256": "abc",
            "families": {
                "OVERSOLD": {
                    "available": False,
                    "count": 0,
                    "unavailable_reason": "no CandidateSnapshot on disk",
                },
                "GAP": {"available": True, "count": 2, "unavailable_reason": None},
            },
            "all": {"count": 2, "items": []},
        }
    )
    assert view["as_of"] == "2026-08-18"
    assert view["screen_version"] == "v0.3.0"
    assert view["families"]["OVERSOLD"]["available"] is False
    assert view["all_count"] == 2
    assert view["checks"]["no_order_path_markers"] is True
    assert view["inspection_pass"] is True
