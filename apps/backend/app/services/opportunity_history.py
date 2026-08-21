"""Durable Opportunity History ingest and read helpers.

Lives outside ``app.research`` so persistence can use the workbench DB without
violating ADR 0051 (research plane must not import ``app.db.models``). Mapping
from CandidateSnapshot cards is pure and lives in ``app.research.disc001.history``.

Same-as_of re-ingest is idempotent: first write wins. Proposal facts and
first-write provenance are never overwritten. Current price and D1/D5/D10/D20
checkpoints are read-time enrichment from the Sharadar factor store, never
stored on the occurrence row. Returns are withheld when adjustment bases differ.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.opportunity_occurrence import OpportunityOccurrence
from app.research.disc001.history import OccurrenceDraft, occurrences_from_payload
from app.research.disc001.snapshot import list_snapshot_dates, read_snapshot, resolve_snapshot_dir
from app.research.disc001.spec import PRICE_SOURCE_SEP

logger = structlog.get_logger(__name__)

_PRICE_EPS = 1e-9
_CURRENT_PRICE_LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class IngestResult:
    inserted: int
    skipped: int
    conflicts: int


@dataclass(frozen=True)
class PriceQuote:
    price: float
    as_of: str
    source: str
    adjustment_basis: str = PRICE_SOURCE_SEP


def _canonical_reason(reason: dict[str, Any]) -> str:
    return json.dumps(reason, sort_keys=True, separators=(",", ":"), default=str)


def parse_reason_json(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError, ValueError):
        return {"chips": [], "why": ""}
    return value if isinstance(value, dict) else {"chips": [], "why": ""}


def sync_db_url(db_url: str | None = None) -> str:
    url = db_url if db_url is not None else get_settings().db_url
    return url.replace("sqlite+aiosqlite", "sqlite", 1)


def _open_session(db_url: str | None = None) -> tuple[Session, Any]:
    engine = create_engine(sync_db_url(db_url), future=True)
    return Session(engine), engine


def _facts_conflict(existing: OpportunityOccurrence, draft: OccurrenceDraft) -> bool:
    if abs(float(existing.proposal_price) - float(draft.proposal_price)) > _PRICE_EPS:
        return True
    if existing.status_at_proposal != draft.status_at_proposal:
        return True
    if existing.reason_json != _canonical_reason(draft.reason_json):
        return True
    return existing.proposal_price_source != draft.proposal_price_source


def ingest_payload(
    payload: dict[str, Any],
    *,
    session: Session | None = None,
    db_url: str | None = None,
    now: datetime | None = None,
) -> IngestResult:
    """Insert family-row occurrences. Identical identity is a no-op (first write wins)."""
    close_session = False
    engine = None
    if session is None:
        session, engine = _open_session(db_url)
        close_session = True
    inserted = skipped = conflicts = 0
    stamped = now or datetime.now(UTC)
    try:
        for draft in occurrences_from_payload(payload):
            existing = session.execute(
                select(OpportunityOccurrence).where(
                    OpportunityOccurrence.screen_id == draft.screen_id,
                    OpportunityOccurrence.screen_version == draft.screen_version,
                    OpportunityOccurrence.candidate_date == draft.candidate_date,
                    OpportunityOccurrence.family == draft.family,
                    OpportunityOccurrence.symbol == draft.symbol,
                )
            ).scalar_one_or_none()
            if existing is not None:
                skipped += 1
                if _facts_conflict(existing, draft):
                    conflicts += 1
                    logger.warning(
                        "disc001_history_ingest_conflict",
                        symbol=draft.symbol,
                        family=draft.family,
                        candidate_date=draft.candidate_date,
                        kept_sha256=existing.snapshot_sha256,
                        ignored_sha256=draft.snapshot_sha256,
                    )
                continue
            nested = session.begin_nested()
            row = OpportunityOccurrence(
                symbol=draft.symbol,
                candidate_date=draft.candidate_date,
                family=draft.family,
                horizon=draft.horizon,
                status_at_proposal=draft.status_at_proposal,
                proposal_price=draft.proposal_price,
                proposal_price_source=draft.proposal_price_source,
                adjustment_basis=draft.adjustment_basis,
                screen_id=draft.screen_id,
                screen_version=draft.screen_version,
                snapshot_sha256=draft.snapshot_sha256,
                snapshot_generated_at=draft.snapshot_generated_at,
                reason_json=_canonical_reason(draft.reason_json),
                features_json=None,
                created_at=stamped,
            )
            session.add(row)
            try:
                session.flush()
                nested.commit()
            except IntegrityError:
                nested.rollback()
                session.expunge(row)
                skipped += 1
                continue
            inserted += 1
        if close_session:
            session.commit()
    except Exception:
        if close_session:
            session.rollback()
        raise
    finally:
        if close_session:
            session.close()
            if engine is not None:
                engine.dispose()
    return IngestResult(inserted=inserted, skipped=skipped, conflicts=conflicts)


def ingest_snapshot_dir(
    snapshot_dir: str | Path | None = None,
    *,
    db_url: str | None = None,
) -> IngestResult:
    """Idempotent ingest of every CandidateSnapshot JSON still on disk."""
    directory = resolve_snapshot_dir(str(snapshot_dir) if snapshot_dir is not None else None)
    inserted = skipped = conflicts = 0
    session, engine = _open_session(db_url)
    try:
        for as_of in reversed(list_snapshot_dates(directory)):
            payload = read_snapshot(directory, as_of)
            if not payload:
                continue
            result = ingest_payload(payload, session=session)
            inserted += result.inserted
            skipped += result.skipped
            conflicts += result.conflicts
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
    return IngestResult(inserted=inserted, skipped=skipped, conflicts=conflicts)


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    date_fn = getattr(value, "date", None)
    if callable(date_fn):
        try:
            parsed = date_fn()
        except Exception:
            parsed = None
        if isinstance(parsed, datetime):
            return parsed.date()
        if isinstance(parsed, date):
            return parsed
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def history_price_series(
    symbols: Sequence[str],
    *,
    start: date,
    end: date | None = None,
) -> dict[str, tuple[tuple[date, float], ...]]:
    """Read-time split-adjusted SEP closes. Missing store → empty, never written back."""
    tickers = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if not tickers:
        return {}
    until = end or date.today()
    if until < start:
        return {}
    try:
        from app.factor_data.config import resolve_store_path
        from app.factor_data.store import FactorDataStore

        path = resolve_store_path()
        if not path.is_file():
            return {}
        store = FactorDataStore(read_only=True)
    except Exception:
        logger.info("disc001_history_price_store_unavailable")
        return {}
    try:
        frame = store.get_prices_many(tickers, start, until, adjusted=True)
    except Exception:
        logger.info("disc001_history_price_lookup_failed")
        return {}
    finally:
        store.close()
    if frame is None or getattr(frame, "empty", True):
        return {}
    out: dict[str, list[tuple[date, float]]] = {}
    grouped = frame.groupby("ticker")
    for ticker, sub in grouped:
        ordered = sub.sort_values("date")
        rows: list[tuple[date, float]] = []
        for _, row in ordered.iterrows():
            when = _as_date(row.get("date"))
            close = row.get("close")
            if when is None or close is None:
                continue
            try:
                price = float(close)
            except (TypeError, ValueError):
                continue
            rows.append((when, price))
        if rows:
            out[str(ticker).upper()] = rows
    return {key: tuple(value) for key, value in out.items()}


def latest_closes(symbols: Sequence[str]) -> dict[str, PriceQuote]:
    """Read-time SEP close. Missing store or ticker → omitted, never written back."""
    end = date.today()
    start = end - timedelta(days=_CURRENT_PRICE_LOOKBACK_DAYS)
    series = history_price_series(symbols, start=start, end=end)
    out: dict[str, PriceQuote] = {}
    for ticker, rows in series.items():
        when, price = rows[-1]
        out[ticker] = PriceQuote(
            price=price,
            as_of=when.isoformat(),
            source=PRICE_SOURCE_SEP,
            adjustment_basis=PRICE_SOURCE_SEP,
        )
    return out
