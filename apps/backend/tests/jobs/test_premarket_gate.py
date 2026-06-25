"""Tests for the SCAN-001 gate scheduled jobs (forward-evidence accrual).

The jobs are thin, fail-soft wrappers over ``record_premarket_scan`` (sync) and
``backfill_evidence`` (async); these tests pin the wiring (asof = today ET, directory
threaded through) and the must-never-raise contract.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

from app.jobs import premarket_gate


async def test_scan_job_records_with_today_et_and_directory(monkeypatch):
    seen: dict = {}

    def fake_record(store, *, asof, directory, top_n=15):
        seen.update(store=store, asof=asof, directory=directory)
        return {"candidates": [{"symbol": "AAA"}], "eligible": [{"symbol": "BBB"}],
                "_path": "/tmp/rec.json"}

    monkeypatch.setattr(premarket_gate, "record_premarket_scan", fake_record)
    store = object()
    await premarket_gate.run_premarket_scan_job(factor_store=store, directory="evd")

    assert seen["store"] is store
    assert seen["directory"] == "evd"
    assert isinstance(seen["asof"], date)


async def test_scan_job_swallows_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("scan boom")

    monkeypatch.setattr(premarket_gate, "record_premarket_scan", boom)
    # Must NOT raise — an advisory job can never break the scheduler.
    await premarket_gate.run_premarket_scan_job(factor_store=object(), directory="evd")


async def test_backfill_job_runs_with_directory(monkeypatch):
    rec = {"outcome_status": "filled",
           "outcomes": {"coverage": {"candidates_covered": 1}, "edge_E": 0.12}}
    fake = AsyncMock(return_value=rec)
    monkeypatch.setattr(premarket_gate, "backfill_evidence", fake)

    await premarket_gate.run_premarket_backfill_job(bar_cache=object(), directory="evd")

    fake.assert_awaited_once()
    _, kwargs = fake.await_args
    assert kwargs["directory"] == "evd"
    assert isinstance(kwargs["asof"], date)


async def test_backfill_job_no_record_is_noop(monkeypatch):
    monkeypatch.setattr(premarket_gate, "backfill_evidence", AsyncMock(return_value=None))
    # No record for today (a no-scan day) → clean no-op, no raise.
    await premarket_gate.run_premarket_backfill_job(bar_cache=object(), directory="evd")


async def test_backfill_job_swallows_errors(monkeypatch):
    monkeypatch.setattr(
        premarket_gate, "backfill_evidence", AsyncMock(side_effect=RuntimeError("bf boom"))
    )
    await premarket_gate.run_premarket_backfill_job(bar_cache=object(), directory="evd")
