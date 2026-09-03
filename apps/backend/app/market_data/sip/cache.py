"""SipOperationalCache — the durable shared SIP store (SIP-CACHE-001 §2, §8, §16).

Separate from the immutable MDQ evidence archive and separate from the IEX bar cache. Reads and
writes only ``sip_cache_records``; it never touches ``/opt/workbench/data/mdq_capture`` and never
reads ``/app/bars_cache``.

Restart semantics (§16): nothing about readiness is persisted. Freshness is always recomputed from
the stored ``source_timestamp``, so a restart can never promote a stale cache to ``PASS``, and a
previously recorded verdict can never be inherited.

Recovery semantics: a failed refresh is repaired by a **subsequent refresh**. Never by backfill from
the MDQ archive, never by substituting a credential, never by relaxing a tolerance.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select

from app.db.models.sip_cache_record import SipCacheRecord
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.schema import SipRecord

logger = structlog.get_logger(__name__)


def _to_record(row: SipCacheRecord) -> SipRecord:
    ts = row.source_timestamp
    rx = row.received_at_utc
    # SQLite drops tzinfo on round-trip even with DateTime(timezone=True); reattach UTC so the
    # freshness comparison never runs against a naive datetime.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    if rx.tzinfo is None:
        rx = rx.replace(tzinfo=UTC)
    return SipRecord(
        symbol=row.symbol,
        profile=SipProfile(row.profile),
        trading_date=row.trading_date,
        session=row.session,
        source_timestamp=ts,
        received_at_utc=rx,
        price=row.price,
        bid=row.bid,
        ask=row.ask,
        bid_size=row.bid_size,
        ask_size=row.ask_size,
        feed=row.feed,
        source_feed_identity=row.source_feed_identity,
        provider=row.provider,
        entitlement_identity=row.entitlement_identity,
        credential_identity_fingerprint=row.credential_identity_fingerprint,
        cache_schema_version=row.cache_schema_version,
        quality_classification=row.quality_classification,
    )


class SipOperationalCache:
    """Durable per-(symbol, profile, trading_date) SIP store."""

    def __init__(self, session_factory: Any) -> None:
        self._sf = session_factory

    async def upsert(self, records: list[SipRecord]) -> int:
        """Insert or refresh ``records``. Returns the number written.

        A row is only overwritten by an observation with a **newer** ``source_timestamp`` — a late
        or replayed response can never move the cache backwards in time.
        """
        if not records:
            return 0
        written = 0
        async with self._sf() as s:
            for rec in records:
                if not rec.feed_is_authentic:
                    # The provider served something other than what we asked for. That is a
                    # substitution, not a degraded row: refuse it rather than store a record whose
                    # own provenance contradicts itself.
                    logger.warning(
                        "sip_record_rejected_feed_mismatch",
                        symbol=rec.symbol,
                        requested=rec.feed,
                        served=rec.source_feed_identity,
                    )
                    continue
                existing = (
                    await s.execute(
                        select(SipCacheRecord).where(
                            SipCacheRecord.symbol == rec.symbol,
                            SipCacheRecord.profile == str(rec.profile),
                            SipCacheRecord.trading_date == rec.trading_date,
                        )
                    )
                ).scalar_one_or_none()

                if existing is None:
                    s.add(
                        SipCacheRecord(
                            symbol=rec.symbol,
                            profile=str(rec.profile),
                            trading_date=rec.trading_date,
                            session=rec.session,
                            source_timestamp=rec.source_timestamp,
                            received_at_utc=rec.received_at_utc,
                            price=rec.price,
                            bid=rec.bid,
                            ask=rec.ask,
                            bid_size=rec.bid_size,
                            ask_size=rec.ask_size,
                            feed=rec.feed,
                            source_feed_identity=rec.source_feed_identity,
                            provider=rec.provider,
                            entitlement_identity=rec.entitlement_identity,
                            credential_identity_fingerprint=rec.credential_identity_fingerprint,
                            cache_schema_version=rec.cache_schema_version,
                            quality_classification=rec.quality_classification,
                        )
                    )
                    written += 1
                    continue

                prior = existing.source_timestamp
                if prior.tzinfo is None:
                    prior = prior.replace(tzinfo=UTC)
                if rec.source_timestamp <= prior:
                    continue
                existing.source_timestamp = rec.source_timestamp
                existing.received_at_utc = rec.received_at_utc
                existing.price = rec.price
                existing.bid = rec.bid
                existing.ask = rec.ask
                existing.bid_size = rec.bid_size
                existing.ask_size = rec.ask_size
                existing.source_feed_identity = rec.source_feed_identity
                existing.entitlement_identity = rec.entitlement_identity
                existing.credential_identity_fingerprint = rec.credential_identity_fingerprint
                existing.cache_schema_version = rec.cache_schema_version
                existing.quality_classification = rec.quality_classification
                written += 1
            await s.commit()
        return written

    async def get(
        self, symbol: str, profile: SipProfile, trading_date: date | None = None
    ) -> SipRecord | None:
        """Newest cached record for ``symbol`` in ``profile``, optionally pinned to a date."""
        async with self._sf() as s:
            stmt = select(SipCacheRecord).where(
                SipCacheRecord.symbol == symbol,
                SipCacheRecord.profile == str(profile),
            )
            if trading_date is not None:
                stmt = stmt.where(SipCacheRecord.trading_date == trading_date)
            stmt = stmt.order_by(SipCacheRecord.source_timestamp.desc()).limit(1)
            row = (await s.execute(stmt)).scalar_one_or_none()
        return _to_record(row) if row is not None else None

    async def latest_for_profile(self, profile: SipProfile) -> list[SipRecord]:
        """Every symbol's newest record in ``profile`` — the readiness evaluator's input."""
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(SipCacheRecord)
                        .where(SipCacheRecord.profile == str(profile))
                        .order_by(SipCacheRecord.source_timestamp.desc())
                    )
                )
                .scalars()
                .all()
            )
        seen: set[str] = set()
        out: list[SipRecord] = []
        for row in rows:
            if row.symbol in seen:
                continue
            seen.add(row.symbol)
            out.append(_to_record(row))
        return out

    async def prune(
        self,
        retention_days: int,
        *,
        now: datetime | None = None,
        keep_newest_for: Iterable[str] | None = None,
    ) -> int:
        """Delete rows whose ``trading_date`` is older than ``retention_days``.

        Bounded retention (§8). Deliberately keyed on ``trading_date`` rather than insertion time so
        a re-observed old session is still pruned on its own schedule.

        ``keep_newest_for`` (B3): symbols under an ACTIVE demand lease. Their newest row is never
        removed, so retention cannot delete data a registered consumer still depends on.
        """
        if retention_days <= 0:
            return 0
        cutoff = ((now or datetime.now(UTC)) - timedelta(days=retention_days)).date()
        protected = set(keep_newest_for or ())
        async with self._sf() as s:
            if not protected:
                result = await s.execute(
                    delete(SipCacheRecord).where(SipCacheRecord.trading_date < cutoff)
                )
                await s.commit()
                removed = int(result.rowcount or 0)
            else:
                rows = (
                    (
                        await s.execute(
                            select(SipCacheRecord).where(SipCacheRecord.trading_date < cutoff)
                        )
                    )
                    .scalars()
                    .all()
                )
                newest: dict[tuple[str, str], date] = {}
                for r in (await s.execute(select(SipCacheRecord))).scalars().all():
                    key = (r.symbol, r.profile)
                    if r.symbol in protected and (
                        key not in newest or r.trading_date > newest[key]
                    ):
                        newest[key] = r.trading_date
                removed = 0
                for r in rows:
                    if newest.get((r.symbol, r.profile)) == r.trading_date:
                        continue
                    await s.delete(r)
                    removed += 1
                await s.commit()
        if removed:
            logger.info("sip_cache_pruned", removed=removed, cutoff=str(cutoff))
        return removed
