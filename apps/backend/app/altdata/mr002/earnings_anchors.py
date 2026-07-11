"""MR-002 V1 build — EDGAR 8-K Item 2.02 earnings anchors (pre-reg v0.4 §4/§8).

Derives per-security confirmed earnings-release anchors from EDGAR submissions:
every 8-K whose ``items`` include Item 2.02 (Results of Operations and Financial
Condition), with the SEC **acceptance timestamp** as the PIT known-at instant.

Registered semantics implemented here (owner sign-off 2026-07-11; v0.5 §1 timing
correction folded — the earlier "in-session => BMO" rule was NOT PIT-safe):
- acceptance timestamps normalized to **Eastern Time**; every anchor carries an
  ``event_time_basis`` (``edgar_acceptance_proxy`` here; ``verified_release_timestamp``
  reserved for independently verified release times — acceptance-based rows are never
  labelled true BMO/AMC);
- availability classes: ``PRE_OPEN`` (before 09:30 ET -> prohibited execution opens
  s and s+1), ``IN_SESSION`` / ``POST_CLOSE`` (-> prohibited opens s+1 and s+2),
  ``DATE_ONLY_CONSERVATIVE`` (no clock time -> treated as available end-of-day s ->
  prohibited opens s+1 and s+2, the PIT-safe direction). No execution that occurred
  before the recorded availability timestamp is ever retroactively cancelled;
- duplicate 2.02 filings for the same (CIK, report period) collapse to ONE anchor
  (earliest acceptance), later duplicates recorded, not dropped silently;
- an 8-K/A **amends** the matching original anchor (same CIK + report period) and
  never creates a new anchor; a 2.02 amendment with no matching original becomes an
  anchor flagged ``amendment_without_original`` (the first PIT knowledge of that
  release) and is logged as an exception;
- every rejected candidate carries an explicit reason (nothing is silently skipped).

This module is pure transformation + storage; all HTTP goes through the throttled
CAP-015 ``EdgarClient``. No order-path imports (ADR 0037 isolation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from datetime import time as dtime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app.altdata.sec.ingest import older_shard_urls, submissions_url

ET = ZoneInfo("America/New_York")
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)
ITEM_202 = "2.02"

# availability classes (v0.5 §1 — NOT BMO/AMC labels; basis is the acceptance proxy)
PRE_OPEN = "PRE_OPEN"                          # prohibited execution opens: s, s+1
IN_SESSION = "IN_SESSION"                      # prohibited execution opens: s+1, s+2
POST_CLOSE = "POST_CLOSE"                      # prohibited execution opens: s+1, s+2
DATE_ONLY_CONSERVATIVE = "DATE_ONLY_CONSERVATIVE"  # no clock time -> s+1, s+2 (PIT-safe)

EDGAR_ACCEPTANCE_PROXY = "edgar_acceptance_proxy"
VERIFIED_RELEASE_TIMESTAMP = "verified_release_timestamp"  # reserved for manual validation


class _Fetcher(Protocol):
    def get_json(self, url: str) -> Any: ...


@dataclass
class AnchorCandidate:
    """One 8-K / 8-K/A filing carrying Item 2.02, before collapse/amendment logic."""

    cik: int
    ticker: str
    accession: str
    form: str                       # "8-K" | "8-K/A"
    filing_date: str | None         # ISO date string from EDGAR
    acceptance_raw: str | None      # ISO instant from EDGAR (UTC 'Z')
    report_date: str | None         # periodOfReport — the anchor identity key
    items: str = ""

    @property
    def is_amendment(self) -> bool:
        return self.form.endswith("/A")


@dataclass
class Anchor:
    """One confirmed earnings-release event (the blackout anchor)."""

    cik: int
    ticker: str
    permaticker: int | None
    accession: str
    report_date: str | None
    acceptance_utc: datetime
    acceptance_et: datetime
    session_date: date             # the ET calendar date of availability
    availability_class: str        # PRE_OPEN | IN_SESSION | POST_CLOSE | DATE_ONLY_CONSERVATIVE
    event_time_basis: str = EDGAR_ACCEPTANCE_PROXY
    is_amendment_origin: bool = False
    amended_by: list[str] = field(default_factory=list)
    collapsed_duplicates: list[str] = field(default_factory=list)


@dataclass
class Rejection:
    cik: int
    ticker: str
    accession: str
    reason: str


@dataclass
class AnchorBuildResult:
    anchors: list[Anchor]
    rejections: list[Rejection]
    exceptions: list[str]          # amendment_without_original etc., human-readable

    def intervals_days(self) -> list[int]:
        """Days between consecutive anchors per security (the false-anchor detector)."""
        out: list[int] = []
        by_sec: dict[int, list[Anchor]] = {}
        for a in self.anchors:
            by_sec.setdefault(a.cik, []).append(a)
        for anchors in by_sec.values():
            ordered = sorted(anchors, key=lambda a: a.acceptance_utc)
            out.extend(
                (b.acceptance_utc.date() - a.acceptance_utc.date()).days
                for a, b in zip(ordered, ordered[1:], strict=False)
            )
        return out


def _parse_acceptance(raw: str | None, filing_date: str | None) -> tuple[datetime | None, bool]:
    """Return (acceptance UTC, has_clock_time). Falls back to the filing date at
    midnight UTC (time-less -> conservative BMO downstream)."""
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC), True
        except ValueError:
            pass
    if filing_date:
        try:
            d = date.fromisoformat(filing_date)
            return datetime(d.year, d.month, d.day, tzinfo=UTC), False
        except ValueError:
            pass
    return None, False


def classify_availability(acceptance_utc: datetime, *, has_clock_time: bool) -> tuple[date, str]:
    """Frozen availability semantics (pre-reg v0.5 §1 — PIT-safe).

    PRE_OPEN (before 09:30 ET on s): prohibited execution opens are s and s+1.
    IN_SESSION / POST_CLOSE (during or after the session on s): prohibited opens are
    s+1 and s+2 — the s open already traded before the information existed, so it is
    never retroactively affected. DATE_ONLY_CONSERVATIVE (no clock time): treated as
    available end-of-day s -> s+1, s+2. Weekend/holiday placement onto trading
    sessions happens at signal-time against the frozen trading calendar; here we
    record the ET calendar date + availability class.
    """
    et = acceptance_utc.astimezone(ET)
    if not has_clock_time:
        return et.date(), DATE_ONLY_CONSERVATIVE
    t = et.time()
    if t < RTH_OPEN:
        return et.date(), PRE_OPEN
    if t >= RTH_CLOSE:
        return et.date(), POST_CLOSE
    return et.date(), IN_SESSION


def iter_8k202_rows(rows: dict[str, Any]) -> list[tuple[str, str, str | None, str | None, str | None, str]]:
    """Yield (accession, form, filing_date, acceptance, report_date, items) for every
    8-K / 8-K/A whose items include 2.02, from one index-aligned filings block."""
    forms = rows.get("form") or []
    accs = rows.get("accessionNumber") or []
    fdates = rows.get("filingDate") or []
    accepts = rows.get("acceptanceDateTime") or []
    reports = rows.get("reportDate") or []
    items_col = rows.get("items") or []
    out = []
    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue
        items = str(items_col[i]) if i < len(items_col) and items_col[i] else ""
        if ITEM_202 not in [s.strip() for s in items.split(",")]:
            continue
        out.append((
            accs[i] if i < len(accs) else "",
            form,
            fdates[i] if i < len(fdates) else None,
            accepts[i] if i < len(accepts) else None,
            (reports[i] if i < len(reports) else None) or None,
            items,
        ))
    return out


def collect_candidates(
    client: _Fetcher, cik: int, ticker: str, *, since: str | None = None
) -> tuple[list[AnchorCandidate], int]:
    """All Item-2.02 candidates for one CIK across the recent block + older shards.
    Returns (candidates, shards_fetched)."""
    subs = client.get_json(submissions_url(cik))
    blocks = [((subs.get("filings") or {}).get("recent") or {})]
    shards = 0
    for url in older_shard_urls(subs, since=since):
        blocks.append(client.get_json(url))
        shards += 1
    cands: list[AnchorCandidate] = []
    for block in blocks:
        for acc, form, fdate, accept, rdate, items in iter_8k202_rows(block):
            if since and fdate and fdate < since:
                continue
            cands.append(AnchorCandidate(
                cik=cik, ticker=ticker, accession=acc, form=form,
                filing_date=fdate, acceptance_raw=accept, report_date=rdate, items=items,
            ))
    return cands, shards


def build_anchors(
    candidates: list[AnchorCandidate], *, permaticker: int | None = None
) -> AnchorBuildResult:
    """Collapse candidates into confirmed anchors under the registered rules."""
    anchors: dict[tuple[int, str], Anchor] = {}   # (cik, report_key) -> anchor
    rejections: list[Rejection] = []
    exceptions: list[str] = []
    amendments: list[AnchorCandidate] = []

    def report_key(c: AnchorCandidate) -> str | None:
        return c.report_date or c.filing_date

    # pass 1: originals, earliest acceptance wins; later duplicates collapsed
    originals = sorted(
        (c for c in candidates if not c.is_amendment),
        key=lambda c: (c.acceptance_raw or c.filing_date or ""),
    )
    for c in originals:
        acc_utc, has_time = _parse_acceptance(c.acceptance_raw, c.filing_date)
        if acc_utc is None:
            rejections.append(Rejection(c.cik, c.ticker, c.accession,
                                        "missing_acceptance_and_filing_date"))
            continue
        key_val = report_key(c)
        if key_val is None:
            rejections.append(Rejection(c.cik, c.ticker, c.accession, "missing_report_and_filing_date"))
            continue
        key = (c.cik, key_val)
        if key in anchors:
            anchors[key].collapsed_duplicates.append(c.accession)
            rejections.append(Rejection(c.cik, c.ticker, c.accession, "duplicate_collapsed"))
            continue
        session_date, availability = classify_availability(acc_utc, has_clock_time=has_time)
        anchors[key] = Anchor(
            cik=c.cik, ticker=c.ticker, permaticker=permaticker, accession=c.accession,
            report_date=c.report_date, acceptance_utc=acc_utc,
            acceptance_et=acc_utc.astimezone(ET), session_date=session_date,
            availability_class=availability,
        )

    # pass 2: amendments amend the matching original; no-match -> flagged anchor
    for c in (c for c in candidates if c.is_amendment):
        amendments.append(c)
        key_val = report_key(c)
        key = (c.cik, key_val) if key_val is not None else None
        if key is not None and key in anchors:
            anchors[key].amended_by.append(c.accession)
            continue
        acc_utc, has_time = _parse_acceptance(c.acceptance_raw, c.filing_date)
        if acc_utc is None or key_val is None:
            rejections.append(Rejection(c.cik, c.ticker, c.accession,
                                        "amendment_unmatchable_and_undated"))
            continue
        session_date, availability = classify_availability(acc_utc, has_clock_time=has_time)
        anchors[(c.cik, key_val)] = Anchor(
            cik=c.cik, ticker=c.ticker, permaticker=permaticker, accession=c.accession,
            report_date=c.report_date, acceptance_utc=acc_utc,
            acceptance_et=acc_utc.astimezone(ET), session_date=session_date,
            availability_class=availability, is_amendment_origin=True,
        )
        exceptions.append(f"amendment_without_original:{c.ticker}:{c.accession}")

    ordered = sorted(anchors.values(), key=lambda a: (a.ticker, a.acceptance_utc))
    return AnchorBuildResult(anchors=ordered, rejections=rejections, exceptions=exceptions)


def anchor_metrics(result: AnchorBuildResult, *, n_securities_requested: int) -> dict[str, Any]:
    """The owner-required output metrics (pre-reg v0.4 §8 V1)."""
    secs_with_anchor = len({a.cik for a in result.anchors})
    intervals = result.intervals_days()
    n = len(intervals)
    s = sorted(intervals)
    counts = {
        cls: sum(1 for a in result.anchors if a.availability_class == cls)
        for cls in (PRE_OPEN, IN_SESSION, POST_CLOSE, DATE_ONLY_CONSERVATIVE)
    }
    basis_counts = _count([a.event_time_basis for a in result.anchors])
    return {
        "securities_requested": n_securities_requested,
        "securities_with_anchor": secs_with_anchor,
        "pct_securities_with_anchor": round(100.0 * secs_with_anchor / max(1, n_securities_requested), 2),
        "n_anchors": len(result.anchors),
        "n_amendment_origin": sum(1 for a in result.anchors if a.is_amendment_origin),
        "n_amended": sum(1 for a in result.anchors if a.amended_by),
        "n_duplicates_collapsed": sum(len(a.collapsed_duplicates) for a in result.anchors),
        "n_rejections": len(result.rejections),
        "rejection_reasons": _count([r.reason for r in result.rejections]),
        "interval_median_days": (s[n // 2] if n else None),
        "interval_min_days": (s[0] if n else None),
        "interval_max_days": (s[-1] if n else None),
        "pct_intervals_lt_60d": round(100.0 * sum(1 for d in intervals if d < 60) / n, 2) if n else None,
        "pct_intervals_gt_110d": round(100.0 * sum(1 for d in intervals if d > 110) / n, 2) if n else None,
        "availability_class_counts": counts,
        "event_time_basis_counts": basis_counts,
        "exceptions": result.exceptions,
    }


def _count(xs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out
