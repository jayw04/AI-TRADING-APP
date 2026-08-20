"""Idempotent opportunity_occurrence ingest. First write wins."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models.opportunity_occurrence import OpportunityOccurrence
from app.research.disc001.snapshot import write_snapshot
from app.research.disc001.spec import PRICE_SOURCE_SEP, SCREEN_ID, SCREEN_VERSION
from app.services.opportunity_history import ingest_payload, ingest_snapshot_dir


def _db(tmp_path: Path) -> str:
    path = tmp_path / "history.sqlite"
    url = "sqlite:///" + path.resolve().as_posix()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def _card(symbol: str = "NVDA", close: float = 120.5, why: str = "stretched") -> dict:
    return {
        "symbol": symbol,
        "status": "Watch",
        "chips": [{"key": "rsi14", "value": "24"}],
        "why": why,
        "price_source": PRICE_SOURCE_SEP,
        "close": close,
    }


def _payload(*, sha: str = "a" * 64, close: float = 120.5, why: str = "stretched") -> dict:
    return {
        "as_of": "2026-08-19",
        "screen_id": SCREEN_ID,
        "screen_version": SCREEN_VERSION,
        "sha256": sha,
        "built_at": "2026-08-20T20:20:01+00:00",
        "families": {
            "OVERSOLD": {
                "available": True,
                "horizon": "1–10d",
                "items": [_card(close=close, why=why)],
            },
            "MOM-NEAR": {"available": False, "items": []},
            "MOM-CORE": {"available": False, "items": []},
            "GAP": {"available": False, "items": []},
        },
    }


def test_first_write_then_same_as_of_is_noop(tmp_path: Path):
    url = _db(tmp_path)
    first = ingest_payload(_payload(), db_url=url, now=datetime(2026, 8, 20, tzinfo=UTC))
    assert first.inserted == 1
    assert first.skipped == 0
    second = ingest_payload(
        _payload(sha="b" * 64, close=999.0, why="changed"),
        db_url=url,
    )
    assert second.inserted == 0
    assert second.skipped == 1
    assert second.conflicts == 1
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        rows = session.execute(select(OpportunityOccurrence)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.proposal_price == 120.5
        assert row.reason_json.find("stretched") >= 0
        assert row.snapshot_sha256 == "a" * 64
        assert row.snapshot_generated_at == "2026-08-20T20:20:01+00:00"
        assert row.screen_version == "v0.3.0"
    engine.dispose()


def test_identical_reingest_is_skip_not_conflict(tmp_path: Path):
    url = _db(tmp_path)
    ingest_payload(_payload(), db_url=url)
    again = ingest_payload(_payload(), db_url=url)
    assert again.inserted == 0
    assert again.skipped == 1
    assert again.conflicts == 0


def test_json_prune_does_not_delete_durable_history(tmp_path: Path):
    url = _db(tmp_path)
    snap_dir = tmp_path / "snaps"
    old = _payload()
    old["as_of"] = "2026-01-01"
    write_snapshot(snap_dir, old)
    ingest_snapshot_dir(snap_dir, db_url=url)
    newer = _payload(sha="c" * 64)
    newer["as_of"] = "2026-08-19"
    write_snapshot(snap_dir, newer)
    names = {p.name for p in snap_dir.glob("watchlist_*.json")}
    assert "watchlist_2026-01-01.json" not in names
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        dates = {r.candidate_date for r in session.execute(select(OpportunityOccurrence)).scalars()}
        assert "2026-01-01" in dates
    engine.dispose()
