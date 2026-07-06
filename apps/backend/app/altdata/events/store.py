"""Point-in-time corporate-event store (ADR 0027; EAD extension ADR 0037) — DuckDB-backed.

One generic table, ``corporate_events``, keyed by ``event_id = "{accession}:{event_type}"``
for idempotent ingest. Every event records its ``filed_at`` (the SEC acceptance timestamp),
so ``events_asof(date)`` returns only what was knowable by that date — the point-in-time
guarantee that keeps the downstream event study honest. Read-only / off the order path.

**EAD (ADR 0037).** Governance/identity/audit fields are first-class *columns* (not buried in
``payload``): ``available_time`` is the canonical PIT anchor for alternative-data reads,
``research_eligible`` gates them, and ``resolved_security_id`` carries the Security-Master
(CAP-024) resolution. The legacy insider path (``events_asof`` filtering on ``filed_at``) is
left byte-identical; EAD reads go through ``events_asof_eligible`` (anchored on
``available_time``). See ``Docs/design/TradingWorkbench_EAD_Phase0A_SchemaReconciliation_v0.1.md``.
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


def _utc_naive_opt(dt: datetime | None) -> datetime | None:
    """``_utc_naive`` that passes ``None`` through (for the nullable EAD timestamp columns)."""
    return None if dt is None else _utc_naive(dt)


@dataclass(frozen=True)
class CorporateEvent:
    """One corporate event, as-of its filing. ``payload`` carries event-type-specific fields
    (for an insider buy: role flags, officer title, buy value/shares, owner name).

    The trailing fields are the EAD governance/identity/audit columns (ADR 0037 Decision 8);
    they default empty so the legacy Form-4 construction (the first nine fields) is unchanged."""

    cik: int
    ticker: str | None
    event_type: str          # e.g. "insider_buy"
    source: str              # e.g. "sec_edgar_form4"
    accession: str
    filed_at: datetime       # SEC acceptance timestamp (the legacy PIT anchor)
    event_date: date | None  # the underlying event/transaction date
    payload: dict[str, Any] = field(default_factory=dict)

    # --- EAD columns (ADR 0037 Decision 8); None/False until an alt-data source populates them ---
    available_time: datetime | None = None   # canonical PIT anchor for EAD reads
    revision_time: datetime | None = None     # late correction / backfill marker
    resolved_security_id: str | None = None   # from the Security Master (CAP-024)
    issuer_name_raw: str | None = None
    ticker_raw: str | None = None
    unresolved_reason: str | None = None      # typed reason when resolution fails
    raw_payload_hash: str | None = None       # provenance / audit
    provider_dataset: str | None = None       # e.g. "government_contracts"
    source_event_id: str | None = None        # vendor id (idempotency key)
    data_source_id: str | None = None         # Data Source Registry ref / license class
    research_eligible: bool = False           # true only with a validated available_time (+ resolution)

    @property
    def event_id(self) -> str:
        return f"{self.accession}:{self.event_type}"


# Legacy read projection — UNCHANGED, so the insider path (``events_asof`` → ``_row_to_event``)
# is byte-identical across the EAD migration (Phase 0A invariance guarantee).
_COLUMNS = ("cik", "ticker", "event_type", "source", "accession",
            "filed_at", "event_date", "payload")

# Full read projection for EAD reads (legacy 8 + the EAD columns).
_EAD_COLUMNS = (
    "available_time", "revision_time", "resolved_security_id", "issuer_name_raw",
    "ticker_raw", "unresolved_reason", "raw_payload_hash", "provider_dataset",
    "source_event_id", "data_source_id", "research_eligible",
)
_COLUMNS_FULL = _COLUMNS + _EAD_COLUMNS

# All persisted columns, in table order (event_id + legacy body + ingested_at + EAD columns).
_INSERT_COLUMNS = (
    "event_id", "cik", "ticker", "event_type", "source", "accession",
    "filed_at", "event_date", "payload", "ingested_at",
) + _EAD_COLUMNS

# Canonical (name, type) DDL for the EAD columns — the single source of truth shared by the
# fresh-DB CREATE, the on-open schema convergence (``ensure_ead_schema``), and the migration
# script (Phase 0A). Order matches the CREATE TABLE below.
EAD_COLUMN_DDL: tuple[tuple[str, str], ...] = (
    ("available_time", "TIMESTAMP"),
    ("revision_time", "TIMESTAMP"),
    ("resolved_security_id", "VARCHAR"),
    ("issuer_name_raw", "VARCHAR"),
    ("ticker_raw", "VARCHAR"),
    ("unresolved_reason", "VARCHAR"),
    ("raw_payload_hash", "VARCHAR"),
    ("provider_dataset", "VARCHAR"),
    ("source_event_id", "VARCHAR"),
    ("data_source_id", "VARCHAR"),
    ("research_eligible", "BOOLEAN DEFAULT FALSE"),
)

_PIT_VIEW_SQL = (
    "CREATE OR REPLACE VIEW corporate_events_pit AS "
    "SELECT *, COALESCE(available_time, filed_at) AS pit_time FROM corporate_events"
)


def ensure_ead_schema(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Idempotently converge an existing ``corporate_events`` table to the EAD schema: ALTER in
    any missing EAD column, then (re)create the ``corporate_events_pit`` compat view. Returns the
    columns added. Safe/inert (nullable columns, defaults) — this is the schema half of the
    migration, run on every write-open so deploying the new code before the migration script can
    never crash on the view. The **backfill** (data change) stays in the signed-off script."""
    present = {
        r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'corporate_events'"
        ).fetchall()
    }
    added: list[str] = []
    for name, coltype in EAD_COLUMN_DDL:
        if name not in present:
            con.execute(f"ALTER TABLE corporate_events ADD COLUMN {name} {coltype}")
            added.append(name)
    con.execute(_PIT_VIEW_SQL)
    return added


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
        # Fresh-DB schema — MUST match a migrated DB exactly: the EAD columns follow ``ingested_at``
        # in the same order the migration script ALTERs them in (Phase 0A §3.2).
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS corporate_events (
                event_id             VARCHAR PRIMARY KEY,
                cik                  BIGINT,
                ticker               VARCHAR,
                event_type           VARCHAR,
                source               VARCHAR,
                accession            VARCHAR,
                filed_at             TIMESTAMP,
                event_date           DATE,
                payload              JSON,
                ingested_at          TIMESTAMP,
                available_time       TIMESTAMP,
                revision_time        TIMESTAMP,
                resolved_security_id VARCHAR,
                issuer_name_raw      VARCHAR,
                ticker_raw           VARCHAR,
                unresolved_reason    VARCHAR,
                raw_payload_hash     VARCHAR,
                provider_dataset     VARCHAR,
                source_event_id      VARCHAR,
                data_source_id       VARCHAR,
                research_eligible    BOOLEAN DEFAULT FALSE
            )
            """
        )
        # Converge an existing (pre-EAD) table's columns + (re)create the compat view. On a fresh
        # DB the CREATE above already has every column, so this only lays down the view.
        ensure_ead_schema(self._con)

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def upsert_events(self, events: list[CorporateEvent], *, ingested_at: datetime | None = None) -> int:
        """Insert events idempotently (dedupe on ``event_id``); returns the count newly inserted.
        Re-ingesting the same filings is a no-op — the foundation for a daily incremental pull.

        The INSERT is **column-explicit** (ADR 0037 Phase 0A): it names every column, so adding
        schema columns can never silently misalign a positional insert. Form-4 events leave the
        EAD columns ``None``/``False``; alt-data normalizers populate them."""
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
        cols = ",".join(_INSERT_COLUMNS)
        marks = ",".join("?" for _ in _INSERT_COLUMNS)
        for e in new:
            self._con.execute(
                f"INSERT INTO corporate_events ({cols}) VALUES ({marks})",
                [
                    e.event_id, e.cik, e.ticker, e.event_type, e.source, e.accession,
                    _utc_naive(e.filed_at), e.event_date, json.dumps(e.payload), _utc_naive(ts),
                    _utc_naive_opt(e.available_time), _utc_naive_opt(e.revision_time),
                    e.resolved_security_id, e.issuer_name_raw, e.ticker_raw, e.unresolved_reason,
                    e.raw_payload_hash, e.provider_dataset, e.source_event_id, e.data_source_id,
                    bool(e.research_eligible),
                ],
            )
        return len(new)

    def events_asof(
        self, as_of: date, *, event_type: str | None = None, ticker: str | None = None,
    ) -> list[CorporateEvent]:
        """**Point-in-time read (legacy / insider path — unchanged):** events whose ``filed_at``
        date is on/before ``as_of`` — i.e. only what was knowable by ``as_of`` (no look-ahead).
        Optionally filtered by type/ticker. EAD callers use ``events_asof_eligible`` instead."""
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

    def events_asof_eligible(
        self, as_of: date, *, event_type: str | None = None, ticker: str | None = None,
    ) -> list[CorporateEvent]:
        """**EAD point-in-time read (ADR 0037 Decision 8):** research-eligible events knowable by
        ``as_of``, anchored on ``available_time`` (never ``filed_at``). Enforces
        ``research_eligible = TRUE AND available_time IS NOT NULL`` — no ``pit_time`` fallback. A
        forward-dated event (``available_time`` after ``as_of``) is excluded even if ``filed_at``
        is earlier, which is the whole point of a distinct availability anchor."""
        conds = ["research_eligible = TRUE", "available_time IS NOT NULL",
                 "CAST(available_time AS DATE) <= ?"]
        params: list[Any] = [as_of]
        if event_type is not None:
            conds.append("event_type = ?")
            params.append(event_type)
        if ticker is not None:
            conds.append("ticker = ?")
            params.append(ticker.strip().upper())
        rows = self._con.execute(
            f"SELECT {', '.join(_COLUMNS_FULL)} FROM corporate_events "
            f"WHERE {' AND '.join(conds)} ORDER BY available_time",
            params,
        ).fetchall()
        return [self._row_to_event_full(r) for r in rows]

    @staticmethod
    def _row_to_event(r: tuple) -> CorporateEvent:
        cik, ticker, etype, source, accession, filed_at, event_date, payload = r
        return CorporateEvent(
            cik=cik, ticker=ticker, event_type=etype, source=source, accession=accession,
            filed_at=filed_at, event_date=event_date,
            payload=json.loads(payload) if isinstance(payload, str) else (payload or {}),
        )

    @staticmethod
    def _row_to_event_full(r: tuple) -> CorporateEvent:
        (cik, ticker, etype, source, accession, filed_at, event_date, payload,
         available_time, revision_time, resolved_security_id, issuer_name_raw, ticker_raw,
         unresolved_reason, raw_payload_hash, provider_dataset, source_event_id,
         data_source_id, research_eligible) = r
        return CorporateEvent(
            cik=cik, ticker=ticker, event_type=etype, source=source, accession=accession,
            filed_at=filed_at, event_date=event_date,
            payload=json.loads(payload) if isinstance(payload, str) else (payload or {}),
            available_time=available_time, revision_time=revision_time,
            resolved_security_id=resolved_security_id, issuer_name_raw=issuer_name_raw,
            ticker_raw=ticker_raw, unresolved_reason=unresolved_reason,
            raw_payload_hash=raw_payload_hash, provider_dataset=provider_dataset,
            source_event_id=source_event_id, data_source_id=data_source_id,
            research_eligible=bool(research_eligible),
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

    def ead_stats(self, *, event_type: str | None = None, source: str | None = None) -> dict[str, Any]:
        """EAD data-quality counters (ADR 0037 §4.0) — eligibility, resolution, availability,
        revisions, raw-hash coverage, and the unresolved-reason breakdown. Scoped by
        event_type/source. Feeds the internal Data-Quality Report."""
        base: list[str] = []
        params: list[Any] = []
        if event_type is not None:
            base.append("event_type = ?")
            params.append(event_type)
        if source is not None:
            base.append("source = ?")
            params.append(source)

        def _count(extra: list[str]) -> int:
            conds = base + extra
            where = (" WHERE " + " AND ".join(conds)) if conds else ""
            row = self._con.execute(f"SELECT COUNT(*) FROM corporate_events{where}", params).fetchone()
            return int(row[0]) if row else 0

        reason_where = " WHERE " + " AND ".join(
            base + ["research_eligible = FALSE", "unresolved_reason IS NOT NULL"])
        reasons = {
            r[0]: int(r[1]) for r in self._con.execute(
                f"SELECT unresolved_reason, COUNT(*) FROM corporate_events{reason_where} "
                "GROUP BY unresolved_reason", params).fetchall()
        }
        return {
            "n_total": _count([]),
            "n_eligible": _count(["research_eligible = TRUE"]),
            "n_ineligible": _count(["research_eligible = FALSE"]),
            "n_missing_available_time": _count(["available_time IS NULL"]),
            "n_revised": _count(["revision_time IS NOT NULL"]),
            "n_with_raw_hash": _count(["raw_payload_hash IS NOT NULL"]),
            "unresolved_reasons": reasons,
        }
