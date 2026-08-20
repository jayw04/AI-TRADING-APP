"""DISC-001 snapshot job fail-soft ingests history after a successful write."""

from __future__ import annotations

from app.jobs.disc001_watchlist import run_disc001_watchlist_snapshot
from app.services.opportunity_history import IngestResult


def test_job_ingests_after_successful_snapshot(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.jobs.disc001_watchlist.read_latest_gappers", lambda: None)
    monkeypatch.setattr(
        "app.jobs.disc001_watchlist.build_and_persist",
        lambda *a, **k: {"as_of": "2026-08-19"},
    )
    monkeypatch.setattr(
        "app.services.opportunity_history.ingest_snapshot_dir",
        lambda directory: calls.append(str(directory)) or IngestResult(2, 0, 0),
    )
    run_disc001_watchlist_snapshot(factor_store=None, snapshot_dir="/tmp/snaps")
    assert calls == ["/tmp/snaps"]


def test_job_skips_ingest_when_snapshot_fails(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.jobs.disc001_watchlist.read_latest_gappers", lambda: None)

    def _boom(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr("app.jobs.disc001_watchlist.build_and_persist", _boom)
    monkeypatch.setattr(
        "app.services.opportunity_history.ingest_snapshot_dir",
        lambda directory: calls.append(str(directory)),
    )
    run_disc001_watchlist_snapshot(factor_store=None, snapshot_dir="/tmp/snaps")
    assert calls == []
