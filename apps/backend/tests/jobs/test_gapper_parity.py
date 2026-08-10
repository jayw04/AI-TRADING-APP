"""Tests for the daily source-parity accrual job (GAP-NATIVE-001, ADR 0041)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.jobs import gapper_parity as job

FRIDAY = datetime(2026, 8, 7, 13, 30, tzinfo=UTC)  # 09:30 ET
DATE_STR = "2026-08-07"


def _write(directory, day: str, symbols: list[str], **extra) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "scanned_at": f"{day}T12:30:00Z",
        "gappers": [
            {"rank": i, "symbol": s, "price": 20.0, "gap_pct": 10.0,
             "premarket_volume": 100_000}
            for i, s in enumerate(symbols, 1)
        ],
        **extra,
    }
    (directory / f"premarket_gappers_{day}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


async def test_writes_a_dated_parity_artifact(tmp_path):
    native, external, ev, out = (tmp_path / n for n in ("n", "e", "ev", "out"))
    _write(native, DATE_STR, ["AAA"], discovery_path="store_sweep",
           discovery_reason="DISCOVERY_STALE", source="box_native_alpaca_v1")
    _write(external, DATE_STR, ["AAA", "BBB"])

    rec = await job.run_gapper_parity_job(
        native_dir=str(native), external_dir=str(external),
        evidence_dir=str(ev), directory=str(out), now=FRIDAY,
    )
    assert rec is not None
    written = json.loads(
        (out / f"gapper_source_parity_{DATE_STR}.json").read_text(encoding="utf-8")
    )
    assert written["asof"] == DATE_STR
    assert written["native_discovery_reason"] == "DISCOVERY_STALE"
    assert written["comparison"]["overlap_pct_of_external"] == 50.0


async def test_runs_on_a_day_with_no_native_file(tmp_path):
    """An absent-source day is parity evidence, not a day to skip — otherwise a
    gap in the series later reads as 'never measured'."""
    native, external, ev, out = (tmp_path / n for n in ("n", "e", "ev", "out"))
    _write(external, DATE_STR, ["AAA"])
    rec = await job.run_gapper_parity_job(
        native_dir=str(native), external_dir=str(external),
        evidence_dir=str(ev), directory=str(out), now=FRIDAY,
    )
    assert rec["both_present"] is False
    assert (out / f"gapper_source_parity_{DATE_STR}.json").exists()


async def test_is_fail_soft(tmp_path, monkeypatch):
    """An advisory measurement job must never break the scheduler."""
    def _boom(*_a, **_k):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(job, "parity_record", _boom)
    assert await job.run_gapper_parity_job(
        native_dir=str(tmp_path), external_dir=str(tmp_path),
        evidence_dir=str(tmp_path), directory=str(tmp_path), now=FRIDAY,
    ) is None
