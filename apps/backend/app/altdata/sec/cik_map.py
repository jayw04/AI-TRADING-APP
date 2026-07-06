"""Ticker <-> CIK resolution (ADR 0027).

EDGAR identifies filers by **CIK** (Central Index Key), not ticker. The SEC publishes the
canonical mapping at ``https://www.sec.gov/files/company_tickers.json``. The sibling system
flags ~11% unresolved CIK as a real coverage hole (it silently shrinks the universe), so the
loader returns an explicit ``CikMap`` that reports which tickers it could and could NOT
resolve — that coverage is checked at the §2 data-validation gate, not swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.altdata.sec.client import EdgarClient

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def cik_to_10digit(cik: int | str) -> str:
    """EDGAR's submissions API needs a zero-padded 10-digit CIK (``CIK0000320193``)."""
    return f"{int(cik):010d}"


@dataclass(frozen=True)
class CikMap:
    """Resolved ticker -> CIK, with explicit unresolved tracking (the coverage hole)."""

    by_ticker: dict[str, int]
    titles: dict[int, str] = field(default_factory=dict)

    def resolve(self, ticker: str) -> int | None:
        return self.by_ticker.get(ticker.strip().upper())

    def resolve_all(self, tickers: list[str]) -> tuple[dict[str, int], list[str]]:
        """Returns ({ticker: cik} for the resolvable ones, [unresolved tickers])."""
        resolved: dict[str, int] = {}
        unresolved: list[str] = []
        for t in tickers:
            cik = self.resolve(t)
            (resolved.__setitem__(t.strip().upper(), cik) if cik is not None
             else unresolved.append(t.strip().upper()))
        return resolved, unresolved

    @property
    def n(self) -> int:
        return len(self.by_ticker)


def parse_company_tickers(raw: dict[str, Any]) -> CikMap:
    """Parse the ``company_tickers.json`` body (``{"0": {"cik_str", "ticker", "title"}, ...}``)
    into a CikMap. Tickers are upper-cased; later duplicates keep the first (lowest index)."""
    by_ticker: dict[str, int] = {}
    titles: dict[int, str] = {}
    for row in raw.values():
        try:
            tick = str(row["ticker"]).strip().upper()
            cik = int(row["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
        if tick and tick not in by_ticker:
            by_ticker[tick] = cik
            titles[cik] = str(row.get("title", ""))
    return CikMap(by_ticker=by_ticker, titles=titles)


def load_cik_map(client: EdgarClient) -> CikMap:
    """Fetch + parse the SEC's canonical ticker->CIK map (read-only)."""
    return parse_company_tickers(client.get_json(COMPANY_TICKERS_URL))
