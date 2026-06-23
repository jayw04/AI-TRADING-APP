"""Read-only ingest of the external pre-market gappers scanner output.

The *producer* lives in the sibling ``claude-trading-view`` project
(``premarket_gappers.sh``): it scans the Yahoo gainers table, filters for real
gappers, and attaches a per-name news catalyst, writing one
``premarket_gappers_<YYYY-MM-DD>.json`` file per trading day.

TradingWorkbench only **reads** these files. Important boundaries:

* **No new external dependency.** The web fetches (Yahoo / Benzinga) and the LLM
  catalyst summarisation happen entirely inside the external scanner. This module
  reads a local file — it opens no network connection and imports no LLM SDK, so
  it is compatible with the order-path / external-dependency invariants.
* **Advisory only.** Gappers are surfaced on the Opportunities page as a
  watchlist; they never feed the OrderRouter or generate orders.
* **Fail-soft.** A missing directory, absent file, or malformed JSON degrades to
  an empty, ``stale`` payload — it must never raise into the Opportunities
  aggregator and break the page.

The file layout and ``stale`` semantics mirror the producer project's own reader
(``backend/readers.py``): the latest dated file is used, and the payload is
``stale`` whenever its date is not today's New York date.
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.utils.time import EASTERN

_GAPPER_RE = re.compile(r"premarket_gappers_(\d{4}-\d{2}-\d{2})\.json$")


def _directory() -> str:
    return get_settings().premarket_gappers_dir


def _empty(date: str | None = None) -> dict[str, Any]:
    return {"date": date, "scanned_at": None, "count": 0, "gappers": [], "stale": True}


def list_gapper_dates(directory: str) -> list[str]:
    """All dates (newest first) that have a gappers file in ``directory``."""
    dates: set[str] = set()
    for path in glob.glob(os.path.join(directory, "premarket_gappers_*.json")):
        match = _GAPPER_RE.search(path.replace("\\", "/"))
        if match:
            dates.add(match.group(1))
    return sorted(dates, reverse=True)


def read_latest_gappers() -> dict[str, Any]:
    """Return the most recent gappers payload, or an empty/stale one on any error.

    Shape: ``{date, scanned_at, count, gappers, stale}``. Never raises.
    """
    directory = _directory()
    try:
        dates = list_gapper_dates(directory)
    except OSError:
        return _empty()
    if not dates:
        return _empty()

    date = dates[0]
    path = os.path.join(directory, f"premarket_gappers_{date}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return _empty(date)

    gappers = payload.get("gappers") or []
    if not isinstance(gappers, list):
        gappers = []

    today_ny = datetime.now(UTC).astimezone(EASTERN).date().isoformat()
    return {
        "date": date,
        "scanned_at": payload.get("scanned_at"),
        "count": len(gappers),
        "gappers": gappers,
        "stale": date != today_ny,
    }
