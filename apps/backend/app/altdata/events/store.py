"""Point-in-time corporate-event store (ADR 0027) — DuckDB-backed.

One generic table, ``corporate_events``, keyed by ``event_id = "{accession}:{event_type}"``
for idempotent ingest. Every event records its ``filed_at`` (the SEC acceptance timestamp),
so ``events_asof(date)`` returns only what was knowable by that date — the point-in-time
guarantee that keeps the downstream event study honest. Read-only / off the order path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from app.config import get_settings


def _utc_naive(dt: datetime) -> datetime:
    """Normalize to a timezone-naive UTC wall-clock so DuckDB ``CAST(... AS DATE)`` yields the
    UTC calendar date **deterministically** (a naive timestamp is not session-tz-converted on
    cast). A tz-aware input is converted to UTC first; a naive input is assumed already UTC.
    Without this the PIT date boundary would silently depend on the server's timezone."""
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo is not None else dt


@dataclass(frozen=True)
class CorporateEvent:
    """One corporate event, as-of its filing. ``payload`` carries event-type-specific fields
    (for an insider buy: role flags, officer title, buy value/shares, owner name)."""

    cik: int
    ticker: str | None
    event_type: str          # e.g. "insider_buy"
    source: str              # e.g. "sec_edgar_form4"
    accession: str
    filed_at: datetime       # SEC acceptance timestamp (the PIT anchor)
    event_date: date | None  # the underlying event/transaction date
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        return f"{self.accession}:{self.event_type}"


_COLUMNS = ("cik", "ticker", "event_type", "source", "accession",
            "filed_at", "event_date", "payload")


class EventStore:
    """The PIT corporate-event store. ``read_only=True`` for research reads (never writes)."""

    def __init__(self, db_path: str | None = None, *, read_only: bool = False) -> None:
        self.path = Path(db_path or get_settings().event_store_path)
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(str(self.path), read_only=read_only)
        if not read_only:
            self._init_schema()

    def _init_schema(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS corporate_events (
                event_id    VARCHAR PRIMARY KEY,
                cik         BIGINT,
                ticker      VARCHAR,
                event_type  VARCHAR,
                source      VARCHAR,
                accession   VARCHAR,
                filed_at    TIMESTAMP,
                event_date  DATE,
                payload     JSON,
                ingested_at TIMESTAMP
            )
            """
        )

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def upsert_events(self, events: list[CorporateEvent], *, ingested_at: datetime | None = None) -> int:
        """Insert events idempotently (dedupe on ``event_id``); returns the count newly inserted.
        Re-ingesting the same filings is a no-op — the foundation for a daily incremental pull."""
        ts = ingested_at or datetime.now(UTC)
        # de-dupe the batch itself, then against what's already stored
        by_id: dict[str, CorporateEvent] = {}
        for e in events:
            by_id.setdefault(e.event_id, e)
        if not by_id:
            return 0
        ids = list(by_id)
        placeholders = ",".join("?" for _ in ids)
        existing = {
            r[0] for r in self._con.execute(
                f"SELECT event_id FROM corporate_events WHERE event_id IN ({placeholders})", ids
            ).fetchall()
        }
        new = [e for eid, e in by_id.items() if eid not in existing]
        for e in new:
            self._con.execute(
                "INSERT INTO corporate_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                [e.event_id, e.cik, e.ticker, e.event_type, e.source, e.accession,
                 _utc_naive(e.filed_at), e.event_date, json.dumps(e.payload), _utc_naive(ts)],
            )
        return len(new)

    def events_asof(
        self, as_of: date, *, event_type: str | None = None, ticker: str | None = None,
    ) -> list[CorporateEvent]:
        """**Point-in-time read:** events whose ``filed_at`` date is on/before ``as_of`` — i.e.
        only what was knowable by ``as_of`` (no look-ahead). Optionally filtered by type/ticker."""
        conds = ["CAST(filed_at AS DATE) <= ?"]
        params: list[Any] = [as_of]
        if event_type is not None:
            conds.append("event_type = ?")
            params.append(event_type)
        if ticker is not None:
            conds.append("ticker = ?")
            params.append(ticker.strip().upper())
        rows = self._con.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM corporate_events "
            f"WHERE {' AND '.join(conds)} ORDER BY filed_at",
            params,
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(r: tuple) -> CorporateEvent:
        cik, ticker, etype, source, accession, filed_at, event_date, payload = r
        return CorporateEvent(
            cik=cik, ticker=ticker, event_type=etype, source=source, accession=accession,
            filed_at=filed_at, event_date=event_date,
            payload=json.loads(payload) if isinstance(payload, str) else (payload or {}),
        )

    def count(self, *, event_type: str | None = None) -> int:
        if event_type is None:
            row = self._con.execute("SELECT COUNT(*) FROM corporate_events").fetchone()
        else:
            row = self._con.execute(
                "SELECT COUNT(*) FROM corporate_events WHERE event_type = ?", [event_type]
            ).fetchone()
        return int(row[0]) if row else 0

    def coverage(self) -> dict[str, Any]:
        """A health snapshot for the §2 data-validation gate: counts by type, date range,
        distinct issuers."""
        n = self.count()
        if n == 0:
            return {"n_events": 0, "by_type": {}, "first_filed": None, "last_filed": None,
                    "distinct_tickers": 0}
        by_type = {r[0]: int(r[1]) for r in self._con.execute(
            "SELECT event_type, COUNT(*) FROM corporate_events GROUP BY event_type").fetchall()}
        row = self._con.execute(
            "SELECT MIN(CAST(filed_at AS DATE)), MAX(CAST(filed_at AS DATE)), "
            "COUNT(DISTINCT ticker) FROM corporate_events").fetchone()
        lo, hi, ntk = row if row else (None, None, 0)
        return {"n_events": n, "by_type": by_type, "first_filed": str(lo), "last_filed": str(hi),
                "distinct_tickers": int(ntk)}

    def latency_audit(self, *, event_type: str | None = None) -> dict[str, Any]:
        """Filing-latency + PIT-sanity stats: days between the underlying event date and the
        filing (Form 4 must be filed within ~2 business days). A **negative** latency (filed
        BEFORE the event) is impossible and signals a data error / look-ahead — the §2 gate
        tolerates none. ``event_date`` may be NULL on a malformed filing; those are excluded
        from latency but counted as ``n_missing_event_date``."""
        where = "WHERE event_date IS NOT NULL"
        params: list[Any] = []
        if event_type is not None:
            where += " AND event_type = ?"
            params.append(event_type)
        row = self._con.execute(
            f"""
            SELECT COUNT(*),
                   MIN(date_diff('day', event_date, CAST(filed_at AS DATE))),
                   MAX(date_diff('day', event_date, CAST(filed_at AS DATE))),
                   MEDIAN(date_diff('day', event_date, CAST(filed_at AS DATE))),
                   SUM(CASE WHEN date_diff('day', event_date, CAST(filed_at AS DATE)) < 0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN date_diff('day', event_date, CAST(filed_at AS DATE)) > 5 THEN 1 ELSE 0 END)
            FROM corporate_events {where}
            """,
            params,
        ).fetchone()
        n, lo, hi, med, neg, over5 = row if row else (0, None, None, None, 0, 0)
        missing = self._con.execute(
            "SELECT COUNT(*) FROM corporate_events WHERE event_date IS NULL"
            + ("" if event_type is None else " AND event_type = ?"),
            ([] if event_type is None else [event_type]),
        ).fetchone()
        return {
            "n_with_event_date": int(n or 0),
            "min_latency_days": None if lo is None else int(lo),
            "max_latency_days": None if hi is None else int(hi),
            "median_latency_days": None if med is None else float(med),
            "n_pit_violations": int(neg or 0),     # filed BEFORE the transaction — impossible
            "n_latency_over_5d": int(over5 or 0),   # unusually late (late filing / data issue)
            "n_missing_event_date": int((missing or [0])[0]),
        }
