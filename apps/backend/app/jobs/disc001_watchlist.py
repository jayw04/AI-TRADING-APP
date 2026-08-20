"""DISC-001 Phase-1 watchlist snapshot job (~16:20 ET, Mon–Fri).

Research-plane only: reads the factor store + gappers file, writes a dated
CandidateSnapshot. Fail-soft — a bad day is logged and skipped.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.research.disc001.adapter import build_and_persist
from app.services.premarket_gappers import read_latest_gappers

logger = structlog.get_logger(__name__)


def run_disc001_watchlist_snapshot(*, factor_store: Any, snapshot_dir: str) -> None:
    try:
        gappers = read_latest_gappers()
    except Exception:
        gappers = None
    vix = None
    if factor_store is not None:
        try:
            from datetime import timedelta

            _, latest = factor_store.price_date_bounds()
            if latest is not None:
                series = factor_store.get_index_series("^VIX", latest - timedelta(days=14), latest)
                if series is not None and not series.empty:
                    vix = round(float(series["close"].iloc[-1]), 1)
        except Exception:
            vix = None
    try:
        build_and_persist(
            factor_store,
            gappers_payload=gappers,
            snapshot_dir=snapshot_dir,
            vix=vix,
        )
    except Exception:
        logger.exception("disc001_watchlist_snapshot_failed")
