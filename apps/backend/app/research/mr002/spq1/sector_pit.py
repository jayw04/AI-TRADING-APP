"""Point-in-time sector resolution (SIG-18/19, Ruling 7/8).

At the close-t decision cutoff, select the latest accepted PIT sector record whose availability
timestamp <= close t. A filing date alone is insufficient when a later acceptance/publication
timestamp exists. Same-availability-timestamp records follow the source's registered supersession
ordering; if precedence remains ambiguous -> SECTOR_EFFECTIVE_DATE_CONFLICT. No present-day
backfill. Missing PIT sector -> SECTOR_PIT_IDENTITY_MISSING (never defaulted).
"""
from __future__ import annotations

from dataclasses import dataclass

from .refusals import refuse

__all__ = ["SectorRecord", "resolve_sector"]


@dataclass(frozen=True)
class SectorRecord:
    sector_id: str
    availability_timestamp: str   # ISO 8601; the publication/acceptance time (not the filing date)
    supersession_ordinal: int     # registered ordering for same-timestamp records (higher wins)
    source_evidence_identity: str


def resolve_sector(records: list[SectorRecord], close_t_timestamp: str) -> SectorRecord:
    """Latest accepted PIT sector record available by close t."""
    eligible = [r for r in records if r.availability_timestamp <= close_t_timestamp]
    if not eligible:
        raise refuse(
            "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING",
            f"no PIT sector record available by {close_t_timestamp}",
        )
    latest_ts = max(r.availability_timestamp for r in eligible)
    latest = [r for r in eligible if r.availability_timestamp == latest_ts]
    if len(latest) == 1:
        return latest[0]
    # Same availability timestamp: registered supersession ordering breaks the tie.
    max_ord = max(r.supersession_ordinal for r in latest)
    winners = [r for r in latest if r.supersession_ordinal == max_ord]
    if len(winners) != 1 or len({r.sector_id for r in winners}) != 1:
        raise refuse(
            "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT",
            f"ambiguous same-timestamp PIT sector records at {latest_ts}",
        )
    return winners[0]
