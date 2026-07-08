"""Corporate-lobbying spend-spike normalizer (EAD; LOBBY-001; ADR 0037).

Aggregates raw Quiver ``lobbying`` filings into **firm-quarter spend, PIT-cleanly** (only filings
whose ``Date`` is on/before that quarter's LDA filing deadline count — later rows are late/amended
and excluded), then emits one ``lobby_spike`` ``CorporateEvent`` per firm-quarter whose spend
**≥ 2.0× the trailing-4-quarter MEDIAN** (over *nonzero* quarters) **AND ≥ $100k**, given **≥ 4
prior nonzero quarters** (a defined baseline — firms below that are new entrants / intermittent
filers, excluded and counted for LOBBY-002).

``available_time`` = the observable filing **deadline** (by which every counted filing is public);
the study enters the first trading day strictly after it. Each event carries full **aggregation
provenance** (ADR 0037 §2.6) so the firm-quarter total is reproducible and a vendor re-pull is
detectably different. Read-only, off the order path. See the LOBBY-001 plan v0.2.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.altdata.events.store import CorporateEvent
from app.altdata.security_master import ResolutionResult


class SecurityResolver(Protocol):
    """The slice of CAP-024 the normalizer needs (so a fake can stand in for tests)."""

    def resolve_security(
        self, *, issuer_name: str | None = ..., ticker: str | None = ...,
        cik: int | None = ..., as_of: date | None = ...,
    ) -> ResolutionResult: ...


EVENT_TYPE = "lobby_spike"
SOURCE = "quiver"
PROVIDER_DATASET = "lobbying"
DATA_SOURCE_ID = "DCAP-007"

# Locked calibration (plan v0.2 — NO sweep).
SPIKE_RATIO = 2.0
MATERIALITY_ABS_USD = 100_000.0
BASELINE_QUARTERS = 4       # prior NONZERO quarters required for a defined median baseline

Quarter = tuple[int, int]   # (year, qnum) with qnum in 1..4


# --- quarter / deadline calendar -------------------------------------------------------------

def activity_quarter(d: date) -> Quarter:
    """The lobbying-activity quarter a filing dated ``d`` reports on — the quarter ending BEFORE
    ``d`` (an LDA report is filed in the window after its quarter closes; a Jan filing reports the
    prior Q4, an Apr filing reports Q1, etc.)."""
    m = d.month
    if m <= 3:
        return (d.year - 1, 4)   # Q4 prior year (due Jan 20)
    if m <= 6:
        return (d.year, 1)       # Q1 (due Apr 20)
    if m <= 9:
        return (d.year, 2)       # Q2 (due Jul 20)
    return (d.year, 3)           # Q3 (due Oct 20)


def deadline(q: Quarter) -> date:
    """The LDA quarterly filing deadline for quarter ``q`` — the observable PIT anchor."""
    y, n = q
    return {1: date(y, 4, 20), 2: date(y, 7, 20), 3: date(y, 10, 20), 4: date(y + 1, 1, 20)}[n]


def quarter_end(q: Quarter) -> date:
    y, n = q
    return {1: date(y, 3, 31), 2: date(y, 6, 30), 3: date(y, 9, 30), 4: date(y, 12, 31)}[n]


def _as_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _amount(a: Any) -> float | None:
    try:
        v = float(a)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _quarter_index(q: Quarter) -> int:
    return q[0] * 4 + (q[1] - 1)


# --- aggregation (PIT) + data quality --------------------------------------------------------

@dataclass
class FirmQuarter:
    quarter: Quarter
    spend_total: float = 0.0
    filing_row_count: int = 0            # filings counted (Date <= deadline)
    late_rows_excluded: int = 0          # filings for this quarter dated AFTER the deadline
    _amounts: list[float] = field(default_factory=list)   # included amounts → provenance hash

    def rows_included_hash(self) -> str:
        return hashlib.sha256(json.dumps(sorted(self._amounts)).encode()).hexdigest()[:16]


@dataclass
class LobbyDataQuality:
    """Phase-0 data-quality accumulator (plan §7): makes PIT integrity + what v1 drops explicit."""
    tickers: int = 0
    total_filings: int = 0
    filings_on_time: int = 0                  # Date <= deadline (counted)
    late_excluded: int = 0                    # Date > deadline (late/amended, dropped)
    undated_or_unparseable: int = 0
    firm_quarters: int = 0
    spike_events: int = 0
    excluded_new_entrant_quarters: int = 0    # material spend but < 4 prior nonzero quarters

    def merge(self, o: LobbyDataQuality) -> None:
        for f in ("tickers", "total_filings", "filings_on_time", "late_excluded",
                  "undated_or_unparseable", "firm_quarters", "spike_events",
                  "excluded_new_entrant_quarters"):
            setattr(self, f, getattr(self, f) + getattr(o, f))


def aggregate_firm_quarters(
    rows: list[dict[str, Any]],
) -> tuple[dict[Quarter, FirmQuarter], LobbyDataQuality]:
    """Group a firm's raw filings into firm-quarter spend, counting only filings with
    ``Date <= deadline(activity_quarter)`` (PIT). Filings after the deadline are late/amended and
    excluded from the primary as-of-deadline total (but still counted in the data-quality report)."""
    dq = LobbyDataQuality()
    quarters: dict[Quarter, FirmQuarter] = {}
    for r in rows:
        dq.total_filings += 1
        d = _as_date(r.get("Date"))
        amt = _amount(r.get("Amount"))
        if d is None or amt is None:
            dq.undated_or_unparseable += 1
            continue
        q = activity_quarter(d)
        fq = quarters.setdefault(q, FirmQuarter(q))
        if d <= deadline(q):
            fq.spend_total += amt
            fq.filing_row_count += 1
            fq._amounts.append(amt)
            dq.filings_on_time += 1
        else:
            fq.late_rows_excluded += 1
            dq.late_excluded += 1
    dq.firm_quarters = len(quarters)
    return quarters, dq


# --- spike detection + event building --------------------------------------------------------

def build_lobby_events(
    ticker: str, rows: list[dict[str, Any]], *, security_master: SecurityResolver,
) -> tuple[list[CorporateEvent], LobbyDataQuality]:
    """One firm's filings → firm-quarter aggregation → spend-spike detection → ``lobby_spike``
    events with provenance. A spike needs the material floor AND ≥ 4 prior NONZERO quarters for a
    defined median baseline; firms below that are excluded (new-entrant / intermittent, → LOBBY-002)."""
    ticker = ticker.strip().upper()
    quarters, dq = aggregate_firm_quarters(rows)
    dq.tickers = 1
    if not quarters:
        return [], dq

    res = security_master.resolve_security(ticker=ticker)
    ordered = sorted(quarters.values(), key=lambda fq: _quarter_index(fq.quarter))
    events: list[CorporateEvent] = []

    for i, fq in enumerate(ordered):
        if fq.spend_total < MATERIALITY_ABS_USD:
            continue                                         # cheap pre-filter (can't be material)
        prior_nonzero = [p.spend_total for p in ordered[:i] if p.spend_total > 0]
        if len(prior_nonzero) < BASELINE_QUARTERS:
            dq.excluded_new_entrant_quarters += 1
            continue                                         # baseline undefined → new entrant
        base = _median(prior_nonzero[-BASELINE_QUARTERS:])
        if base <= 0 or fq.spend_total < SPIKE_RATIO * base:
            continue
        events.append(_spike_event(ticker, fq, base, res))
        dq.spike_events += 1

    return events, dq


def _spike_event(
    ticker: str, fq: FirmQuarter, baseline: float, res: ResolutionResult,
) -> CorporateEvent:
    y, n = fq.quarter
    dl = deadline(fq.quarter)
    available = datetime(dl.year, dl.month, dl.day, tzinfo=UTC)       # observable PIT anchor
    seid = "qlob_" + hashlib.sha1(f"{ticker}|{y}Q{n}".encode()).hexdigest()[:20]
    payload = {
        "quarter": f"{y}Q{n}",
        "spend_total": round(fq.spend_total, 2),
        "baseline_value": round(baseline, 2),
        "baseline_method": "median_nonzero_4q",
        "spike_ratio": round(fq.spend_total / baseline, 3) if baseline else None,
        "filing_row_count": fq.filing_row_count,
        "rows_included_hash": fq.rows_included_hash(),
        "late_rows_excluded_count": fq.late_rows_excluded,
        "available_time_basis": "quarter_deadline",
    }
    return CorporateEvent(
        cik=res.cik or 0,
        ticker=res.resolved_ticker or ticker,
        event_type=EVENT_TYPE,
        source=SOURCE,
        accession=seid,
        filed_at=available,
        event_date=quarter_end(fq.quarter),               # the lobbying-activity period end
        payload=payload,
        available_time=available,                         # first trading day after is computed in the study
        resolved_security_id=res.resolved_security_id,
        issuer_name_raw=None,
        ticker_raw=ticker,
        unresolved_reason=res.unresolved_reason,
        raw_payload_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        provider_dataset=PROVIDER_DATASET,
        source_event_id=seid,
        data_source_id=DATA_SOURCE_ID,
        research_eligible=res.is_resolved,
    )
