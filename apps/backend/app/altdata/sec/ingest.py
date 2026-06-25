"""Form 4 ingestion orchestrator (ADR 0027): submissions -> Form 4 XML -> parse -> Event Store.

For each requested ticker it resolves the CIK, lists the issuer's recent Form 4 filings (since
a date), fetches + parses each, and persists every filing containing >=1 **open-market buy**
as an ``insider_buy`` corporate event (event-type-agnostic store; the *conviction filter* —
value/role/cluster — is applied later in signal construction, §3, not here). Idempotent via the
store's ``event_id`` dedupe, so a daily incremental pull just appends new filings.

Fail-soft: a bad filing or a CIK that errors is counted, never fatal — the §2 validation gate
reads those counts. The store keeps **raw** events; nothing here is filtered or tuned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.altdata.events.store import CorporateEvent, EventStore
from app.altdata.sec.cik_map import CikMap, cik_to_10digit, load_cik_map
from app.altdata.sec.client import DATA_HOST, WWW_HOST
from app.altdata.sec.form4 import parse_form4

EVENT_TYPE = "insider_buy"
SOURCE = "sec_edgar_form4"


class _Fetcher(Protocol):
    def get_json(self, url: str) -> Any: ...
    def get_text(self, url: str) -> str: ...


@dataclass
class IngestReport:
    tickers_requested: int
    ciks_resolved: int
    unresolved_tickers: list[str] = field(default_factory=list)
    form4_filings_seen: int = 0
    events_ingested: int = 0
    fetch_failures: int = 0


def submissions_url(cik: int) -> str:
    return f"{DATA_HOST}/submissions/CIK{cik_to_10digit(cik)}.json"


def form4_xml_url(cik: int, accession: str, primary_document: str) -> str:
    """The raw Form 4 ``ownershipDocument`` URL in the accession's archive folder."""
    return f"{WWW_HOST}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{primary_document}"


def _parse_acceptance(accept_dt: str | None, filing_date: str | None) -> datetime:
    """The PIT anchor: the SEC acceptance timestamp (ISO, often 'Z'), falling back to the filing
    date at midnight UTC."""
    if accept_dt:
        try:
            return datetime.fromisoformat(accept_dt.replace("Z", "+00:00"))
        except ValueError:
            pass
    if filing_date:
        try:
            d = date.fromisoformat(filing_date)
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _as_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def iter_form4_filings(submissions: dict[str, Any], *, since: str | None):
    """Yield ``(accession, filing_date, acceptance_dt, primary_document)`` for each Form 4 in the
    submissions' ``recent`` block, filed on/after ``since`` (ISO date). The ``recent`` arrays are
    index-aligned."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accs = recent.get("accessionNumber") or []
    fdates = recent.get("filingDate") or []
    accepts = recent.get("acceptanceDateTime") or []
    prims = recent.get("primaryDocument") or []
    for i, form in enumerate(forms):
        if form != "4":
            continue
        fdate = fdates[i] if i < len(fdates) else None
        if since and fdate and fdate < since:
            continue
        yield (
            accs[i] if i < len(accs) else "",
            fdate,
            accepts[i] if i < len(accepts) else None,
            prims[i] if i < len(prims) else "",
        )


def form4_to_event(
    form4: Any, *, cik: int, ticker: str, accession: str,
    filing_date: str | None, acceptance_dt: str | None,
) -> CorporateEvent | None:
    """Build an ``insider_buy`` event from a parsed Form 4 with >=1 open-market buy; else None."""
    if not form4.has_open_market_buy:
        return None
    buys = form4.open_market_buys
    return CorporateEvent(
        cik=cik,
        ticker=ticker,
        event_type=EVENT_TYPE,
        source=SOURCE,
        accession=accession,
        filed_at=_parse_acceptance(acceptance_dt, filing_date),
        event_date=_as_date(buys[0].date) or _as_date(filing_date),
        payload={
            "owner_name": form4.owner_name,
            "is_officer": form4.is_officer,
            "is_director": form4.is_director,
            "is_ten_percent_owner": form4.is_ten_percent_owner,
            "officer_title": form4.officer_title,
            "buy_value": form4.buy_value,
            "buy_shares": form4.buy_shares,
            "n_buys": len(buys),
            "issuer_name": form4.issuer_name,
            "issuer_ticker_reported": form4.issuer_ticker,
        },
    )


def ingest_form4(
    client: _Fetcher, store: EventStore, tickers: list[str], *,
    since: str | None = None, cik_map: CikMap | None = None,
) -> IngestReport:
    """Ingest Form 4 open-market-buy events for ``tickers`` filed since ``since`` (ISO date)."""
    cmap = cik_map or load_cik_map(client)  # type: ignore[arg-type]
    resolved, unresolved = cmap.resolve_all(tickers)
    report = IngestReport(
        tickers_requested=len(tickers), ciks_resolved=len(resolved), unresolved_tickers=unresolved,
    )
    events: list[CorporateEvent] = []
    for ticker, cik in resolved.items():
        try:
            subs = client.get_json(submissions_url(cik))
        except Exception:  # noqa: BLE001 — fail-soft per issuer; counted, never fatal
            report.fetch_failures += 1
            continue
        for accession, fdate, accept_dt, prim in iter_form4_filings(subs, since=since):
            report.form4_filings_seen += 1
            try:
                f4 = parse_form4(client.get_text(form4_xml_url(cik, accession, prim)))
                ev = form4_to_event(f4, cik=cik, ticker=ticker, accession=accession,
                                    filing_date=fdate, acceptance_dt=accept_dt)
            except Exception:  # noqa: BLE001 — a malformed filing must not break the run
                report.fetch_failures += 1
                continue
            if ev is not None:
                events.append(ev)
    report.events_ingested = store.upsert_events(events)
    return report
