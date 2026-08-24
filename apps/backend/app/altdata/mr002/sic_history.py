"""MR-002 V2 build — EDGAR effective-dated SIC history (pre-reg v0.4 §8).

Extracts each security's SIC code from the SGML header of every processed EDGAR
filing (10-K / 10-Q families by default — annual-to-quarterly resolution; SIC
changes are rare) and assembles an **effective-dated** classification series under
the owner-registered controls (2026-07-11):

- a new SIC becomes effective only at the **acceptance timestamp** of its filing;
- a filing with a **missing SIC never overwrites** the last valid SIC;
- **conflicting same-day SIC values** are logged and resolved by the frozen
  precedence rule: ``10-K > 10-Q > other forms``, then the later acceptance
  timestamp within the same form rank;
- unmapped or conflicting periods are **excluded downstream, never defaulted** to
  current TICKERS classifications (CAP-024 principle).

The header fetch uses the ``…-index-headers.html`` per-accession page, which embeds
the SEC-HEADER block containing ``STANDARD INDUSTRIAL CLASSIFICATION: NAME [CODE]``
as assigned at filing time — the point-in-time record TICKERS lacks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.altdata.sec.ingest import older_shard_urls, submissions_url

WWW_HOST = "https://www.sec.gov"
SIC_RE = re.compile(
    r"STANDARD\s+INDUSTRIAL\s+CLASSIFICATION:\s*(?P<name>[^\[\n<]*)\[(?P<code>\d{3,4})\]",
    re.IGNORECASE,
)

DEFAULT_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")
_FORM_RANK = {"10-K": 0, "10-K/A": 1, "10-Q": 2, "10-Q/A": 3}  # lower = higher precedence


class _Fetcher(Protocol):
    def get_json(self, url: str) -> Any: ...
    def get_text(self, url: str) -> str: ...


@dataclass
class SicObservation:
    cik: int
    ticker: str
    accession: str
    form: str
    accepted_utc: datetime
    sic: str | None                # None = header had no SIC (never overwrites)
    sic_name: str | None = None


@dataclass
class SicSegment:
    """One effective-dated classification segment (forward-filled to the next change)."""

    cik: int
    ticker: str
    sic: str
    sic_name: str | None
    effective_from: datetime       # acceptance timestamp of the establishing filing
    effective_to: datetime | None  # None = open-ended (current)
    source_accession: str


@dataclass
class SicBuildResult:
    observations: list[SicObservation]
    segments: list[SicSegment]
    conflicts: list[str] = field(default_factory=list)   # same-day disagreements (logged)
    missing_sic: int = 0                                 # filings without a SIC header


def header_index_url(cik: int, accession: str) -> str:
    return (f"{WWW_HOST}/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{accession}-index-headers.html")


def full_submission_url(cik: int, accession: str) -> str:
    """The full-submission .txt whose first bytes are the SGML SEC-HEADER — the
    fallback for pre-~2014 accessions that have no -index-headers.html (404)."""
    return (f"{WWW_HOST}/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{accession}.txt")


def fetch_header_text(client: _Fetcher, cik: int, accession: str) -> str:
    """Header page, falling back to a ranged read of the full-submission txt."""
    try:
        return client.get_text(header_index_url(cik, accession))
    except Exception:  # noqa: BLE001 — 404 on older accessions; use the ranged fallback
        return client.get_text(  # type: ignore[call-arg]
            full_submission_url(cik, accession), headers={"Range": "bytes=0-4095"}
        )


def parse_sic(header_text: str) -> tuple[str | None, str | None]:
    m = SIC_RE.search(header_text)
    if not m:
        return None, None
    return m.group("code").zfill(4), (m.group("name") or "").strip() or None


def _parse_accept(raw: str | None, filing_date: str | None) -> datetime | None:
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            pass
    if filing_date:
        try:
            d = date.fromisoformat(filing_date)
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError:
            pass
    return None


def iter_form_rows(rows: dict[str, Any], forms: tuple[str, ...]):
    all_forms = rows.get("form") or []
    accs = rows.get("accessionNumber") or []
    fdates = rows.get("filingDate") or []
    accepts = rows.get("acceptanceDateTime") or []
    for i, form in enumerate(all_forms):
        if form not in forms:
            continue
        yield (
            accs[i] if i < len(accs) else "",
            form,
            fdates[i] if i < len(fdates) else None,
            accepts[i] if i < len(accepts) else None,
        )


def collect_sic_observations(
    client: _Fetcher, cik: int, ticker: str, *,
    since: str | None = None, forms: tuple[str, ...] = DEFAULT_FORMS,
) -> SicBuildResult:
    """Fetch per-filing headers and extract PIT SIC observations for one CIK."""
    subs = client.get_json(submissions_url(cik))
    blocks = [((subs.get("filings") or {}).get("recent") or {})]
    for url in older_shard_urls(subs, since=since):
        blocks.append(client.get_json(url))

    obs: list[SicObservation] = []
    missing = 0
    for block in blocks:
        for acc, form, fdate, accept in iter_form_rows(block, forms):
            if since and fdate and fdate < since:
                continue
            accepted = _parse_accept(accept, fdate)
            if accepted is None or not acc:
                continue
            try:
                sic, sic_name = parse_sic(fetch_header_text(client, cik, acc))
            except Exception:  # noqa: BLE001 — fail-soft per filing; counted below
                sic, sic_name = None, None
            if sic is None:
                missing += 1
            obs.append(SicObservation(cik=cik, ticker=ticker, accession=acc, form=form,
                                      accepted_utc=accepted, sic=sic, sic_name=sic_name))
    return SicBuildResult(observations=obs, segments=[], missing_sic=missing)


def build_segments(result: SicBuildResult) -> SicBuildResult:
    """Assemble effective-dated segments under the frozen rules."""
    # keep only observations that actually carry a SIC (missing never overwrites)
    dated = [o for o in result.observations if o.sic is not None]

    # same-day precedence: 10-K > 10-Q > other; then later acceptance
    by_day: dict[tuple[int, date], list[SicObservation]] = {}
    for o in dated:
        by_day.setdefault((o.cik, o.accepted_utc.date()), []).append(o)
    chosen: list[SicObservation] = []
    for (_cik, day), group in sorted(by_day.items(), key=lambda kv: kv[0][1]):
        if len({o.sic for o in group}) > 1:
            result.conflicts.append(
                f"{group[0].ticker}:{day}:" + ",".join(f"{o.form}={o.sic}" for o in group)
            )
        best = sorted(
            group,
            key=lambda o: (_FORM_RANK.get(o.form, 9), -o.accepted_utc.timestamp()),
        )[0]
        chosen.append(best)

    chosen.sort(key=lambda o: o.accepted_utc)
    segments: list[SicSegment] = []
    for o in chosen:
        if segments and segments[-1].sic == o.sic:
            continue  # unchanged — extend the open segment
        if segments:
            segments[-1].effective_to = o.accepted_utc
        segments.append(SicSegment(
            cik=o.cik, ticker=o.ticker, sic=o.sic or "", sic_name=o.sic_name,
            effective_from=o.accepted_utc, effective_to=None, source_accession=o.accession,
        ))
    result.segments = segments
    return result
