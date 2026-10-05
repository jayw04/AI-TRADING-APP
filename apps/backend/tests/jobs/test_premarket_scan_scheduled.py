"""SCAN-001 scheduled premarket scan job — regression for the ``.con`` double-unwrap.

The job once passed ``factor_store.con`` into ``record_premarket_scan``, whose scan then read
``store.con`` again → ``AttributeError: 'DuckDBPyConnection' object has no attribute 'con'``
(swallowed fail-soft, so the daily evidence record silently never landed).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.jobs import premarket_scan_scheduled as job


class _Store:
    con = object()


@pytest.mark.asyncio
async def test_passes_the_store_not_its_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_record(store: Any, *, asof: Any, directory: str, top_n: int = 15) -> dict:
        seen["store"] = store
        return {"asof": str(asof), "funnel": {"candidate_count": 0}, "_path": "p"}

    monkeypatch.setattr("app.services.premarket_evidence.record_premarket_scan", fake_record)
    store = _Store()
    rec = await job.run_premarket_scan_scheduled(None, store, directory="evd")  # type: ignore[arg-type]
    assert rec is not None
    assert seen["store"] is store


@pytest.mark.asyncio
async def test_no_factor_store_is_skipped() -> None:
    assert await job.run_premarket_scan_scheduled(None, None) is None  # type: ignore[arg-type]
