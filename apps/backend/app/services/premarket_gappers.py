"""Read-only resolution of the day's pre-market gappers file.

Two producers write ``premarket_gappers_<YYYY-MM-DD>.json`` files:

* **Native** (authoritative, GAP-NATIVE-001 / ADR 0041) — the box's own Alpaca
  screener (``native_gapper_screener``), writing into ``native_gappers_dir``.
  Produced on the box, so the platform's daily operation never depends on the
  developer's PC being on (owner directive 2026-07-10).
* **External** (enrichment/fallback) — the sibling ``claude-trading-view``
  project's scanner (Yahoo gainers + Benzinga/LLM catalysts), synced from the
  laptop into the read-only ``premarket_gappers_dir`` mount. Its surviving
  operational role is per-symbol ``catalyst``/``headlines`` enrichment; it is
  the payload of record only when the native file for today is missing.

Resolution order (ADR 0041 — provenance must be deterministic, never "whichever
machine happened to be on"):

1. Native file for today's NY date → authoritative; same-date external file
   contributes catalyst/headlines onto matching symbols only.
2. No native today, external today → external (transition safety).
3. Neither → newest file from either directory, ``stale: true``.

Two readers apply that order, differing only in *which day* they resolve and in
whether rule 3 applies. Pick by what the caller means:

* :func:`read_latest_gappers` — *"the operational payload right now"*: resolves
  today's NY date and, failing that, falls back to the newest file from either
  directory (rule 3, ``stale: true``). This is what the advisory Opportunities
  widget wants — show the most recent scan and flag it when it is not today's.
* :func:`read_gappers_for` — *"that day's payload, or nothing"*: point-in-time.
  Same rules 1–2 keyed to the requested date, **but no rule 3** — it never
  substitutes a neighbouring day's file. This is what the SCAN-001 gate wants,
  because an evidence record keyed to ``asof`` must contain ``asof``'s premarket
  data or none at all. Recording a different day's gappers under today's date
  would inject a duplicate into the gate's forward series (it back-fills to
  ``filled`` and counts toward the verdict), which is strictly worse than an
  honest empty record (which back-fills to ``uncovered`` and is excluded).

Boundaries (unchanged from the #221 reader): this module opens no network
connection and imports no LLM SDK; gappers are advisory Opportunities-page
context and never feed the OrderRouter. Fail-soft — a missing directory, absent
file, or malformed JSON degrades to an empty ``stale`` payload, never raises.
"""

from __future__ import annotations

import glob
import json
import os
import re
from datetime import UTC, datetime
from datetime import date as date_cls
from typing import Any

from app.config import get_settings
from app.utils.time import EASTERN

_GAPPER_RE = re.compile(r"premarket_gappers_(\d{4}-\d{2}-\d{2})\.json$")

SOURCE_EXTERNAL = "external_scanner"


def _directory() -> str:
    """The external (laptop-synced) gappers directory."""
    return get_settings().premarket_gappers_dir


def _native_directory() -> str:
    """The box-native screener's output directory (GAP-NATIVE-001)."""
    return get_settings().native_gappers_dir


def _empty(date: str | None = None) -> dict[str, Any]:
    return {
        "date": date,
        "scanned_at": None,
        "count": 0,
        "gappers": [],
        "stale": True,
        "source": None,
    }


def list_gapper_dates(directory: str) -> list[str]:
    """All dates (newest first) that have a gappers file in ``directory``."""
    dates: set[str] = set()
    for path in glob.glob(os.path.join(directory, "premarket_gappers_*.json")):
        match = _GAPPER_RE.search(path.replace("\\", "/"))
        if match:
            dates.add(match.group(1))
    return sorted(dates, reverse=True)


def _safe_dates(directory: str) -> list[str]:
    try:
        return list_gapper_dates(directory)
    except OSError:
        return []


def _load_payload(directory: str, date: str) -> dict[str, Any] | None:
    """Parse one dated file → raw payload dict, or None on any error."""
    path = os.path.join(directory, f"premarket_gappers_{date}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _gapper_list(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    gappers = (payload or {}).get("gappers") or []
    return gappers if isinstance(gappers, list) else []


def _enrich_catalysts(
    gappers: list[dict[str, Any]], external: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join catalyst/headlines from the external rows onto matching native symbols.

    Display enrichment ONLY: symbols, prices, and ranking come from the native
    payload — an external-only symbol does not enter the operational list."""
    by_symbol = {
        str(g.get("symbol") or "").upper(): g for g in external if g.get("symbol")
    }
    out: list[dict[str, Any]] = []
    for g in gappers:
        ext = by_symbol.get(str(g.get("symbol") or "").upper())
        if ext and not g.get("catalyst"):
            g = {**g, "catalyst": ext.get("catalyst"), "headlines": ext.get("headlines") or []}
        out.append(g)
    return out


def _result(
    date: str, payload: dict[str, Any], gappers: list[dict[str, Any]], *, stale: bool, source: str
) -> dict[str, Any]:
    return {
        "date": date,
        "scanned_at": payload.get("scanned_at"),
        "count": len(gappers),
        "gappers": gappers,
        "stale": stale,
        "source": payload.get("source") or source,
    }


def read_latest_gappers() -> dict[str, Any]:
    """Resolve the operational gappers payload per the ADR 0041 precedence.

    Shape: ``{date, scanned_at, count, gappers, stale, source}``. Never raises.
    """
    native_dir, external_dir = _native_directory(), _directory()
    native_dates = _safe_dates(native_dir)
    external_dates = _safe_dates(external_dir)
    if not native_dates and not external_dates:
        return _empty()

    today_ny = datetime.now(UTC).astimezone(EASTERN).date().isoformat()

    # 1. Native today is authoritative; external today enriches catalysts only.
    if today_ny in native_dates:
        payload = _load_payload(native_dir, today_ny)
        if payload is not None:
            gappers = _gapper_list(payload)
            if today_ny in external_dates:
                gappers = _enrich_catalysts(
                    gappers, _gapper_list(_load_payload(external_dir, today_ny))
                )
            return _result(today_ny, payload, gappers, stale=False, source="native")
        # unparseable native file for today: fall through to the external path

    # 2. External today (native missing/failed): the transition-safety fallback.
    if today_ny in external_dates:
        payload = _load_payload(external_dir, today_ny)
        if payload is not None:
            return _result(
                today_ny, payload, _gapper_list(payload), stale=False, source=SOURCE_EXTERNAL
            )

    # 3. Nothing for today: newest available from either dir, marked stale
    #    (native wins a same-date tie — same provenance rule as rule 1).
    candidates = [(d, native_dir, "native") for d in native_dates[:1]]
    candidates += [(d, external_dir, SOURCE_EXTERNAL) for d in external_dates[:1]]
    candidates.sort(key=lambda c: (c[0], c[2] == "native"), reverse=True)
    for date, directory, source in candidates:
        payload = _load_payload(directory, date)
        if payload is not None:
            return _result(date, payload, _gapper_list(payload), stale=True, source=source)
    return _empty(candidates[0][0] if candidates else None)


def read_gappers_for(day: date_cls | str) -> dict[str, Any]:
    """Resolve the gappers payload **for ``day``** — point-in-time, never another date.

    Applies the ADR 0041 precedence (rules 1–2) keyed to ``day`` rather than today:

    1. Native file for ``day`` → authoritative; ``day``'s external file contributes
       catalyst/headlines onto matching symbols only.
    2. No native for ``day``, external for ``day`` → external (transition safety).
    3. **Deliberately absent.** Where :func:`read_latest_gappers` falls back to the newest
       file from either directory, this returns the empty payload — ``date: None``,
       ``stale: True``, ``source: None``. That is the honest answer: *no premarket snapshot
       exists for that day.* A neighbouring day's scan is not a substitute; for the gate it
       would record the previous day's candidates under today's ``asof``.

    Shape matches :func:`read_latest_gappers` (``{date, scanned_at, count, gappers, stale,
    source}``). ``stale`` is False whenever ``day``'s own file was found — by construction the
    payload is that day's data, so the "is it today's?" question :func:`read_latest_gappers`
    answers does not apply here. Never raises.
    """
    iso = day.isoformat() if isinstance(day, date_cls) else str(day)
    native_dir, external_dir = _native_directory(), _directory()

    # 1. Native for `day` is authoritative; that same day's external enriches catalysts only.
    payload = _load_payload(native_dir, iso)
    if payload is not None:
        gappers = _gapper_list(payload)
        external = _load_payload(external_dir, iso)
        if external is not None:
            gappers = _enrich_catalysts(gappers, _gapper_list(external))
        return _result(iso, payload, gappers, stale=False, source="native")

    # 2. External for `day` (native missing or unparseable): transition safety.
    payload = _load_payload(external_dir, iso)
    if payload is not None:
        return _result(iso, payload, _gapper_list(payload), stale=False, source=SOURCE_EXTERNAL)

    # 3. No file for `day` in either directory → empty. No cross-date fallback, by design.
    return _empty()
