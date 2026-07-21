"""Registered SIC -> sector -> ETF resolution (2B-1; supersedes the Phase-2A placeholder).

Uses the owner-countersigned sic_mapping (hash-bound) + PIT sic_observations. sector = the row whose
inclusive [sic_start, sic_end] contains the latest SIC accepted by close t; among covering rows the
latest effective_from <= close t governs (NULL = always-effective). Same-effective conflict fails
closed SECTOR_EFFECTIVE_DATE_CONFLICT; a missing range / no PIT SIC -> SECTOR_PIT_IDENTITY_MISSING.
No modification to any closed module.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..adapters import normalize_utc_iso
from ..refusals import refuse
from ..sector_pit import SectorRecord


@dataclass(frozen=True)
class SicMapRow:
    sic_start: int
    sic_end: int
    effective_from: str | None   # ISO date or None (always-effective)
    research_sector: str
    sector_etf: str


def load_sic_map(rows: list[tuple]) -> list[SicMapRow]:
    """rows: (sic_start, sic_end, effective_from, research_sector, sector_etf)."""
    out: list[SicMapRow] = []
    for sic_start, sic_end, eff, sector, etf in rows:
        out.append(SicMapRow(int(sic_start), int(sic_end),
                             None if eff is None else str(eff)[:10], str(sector), str(etf)))
    return out


def latest_pit_sic(sic_obs: list[tuple], close_t_iso: str) -> tuple[str, str, str] | None:
    """sic_obs: (accepted_utc, sic, accession). Return (sic, full-UTC availability, accession) for the
    latest observation accepted by close t. Full timestamp (not date-truncated); a same-acceptance-time
    pair with conflicting SIC fails closed SECTOR_EFFECTIVE_DATE_CONFLICT; exact duplicate records
    (same accepted_utc, sic, accession) deterministically dedupe."""
    seen: dict[tuple[str, str, str], None] = {}
    for a, s, acc in sic_obs:
        seen[(normalize_utc_iso(a), str(s), str(acc))] = None   # exact-dup dedupe
    avail = [k for k in seen if k[0] <= close_t_iso]
    if not avail:
        return None
    latest_ts = max(k[0] for k in avail)
    winners = [k for k in avail if k[0] == latest_ts]
    if len({k[1] for k in winners}) != 1:
        raise refuse("INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT",
                     f"conflicting SIC at same acceptance {latest_ts}")
    ts, s, acc = sorted(winners)[0]
    return s, ts, acc


def resolve_sector(sic_map: list[SicMapRow], sic_obs: list[tuple], close_t_iso: str) -> SectorRecord:
    """Resolve the registered sector for close t (raises the governed refusal on failure)."""
    pit = latest_pit_sic(sic_obs, close_t_iso)
    if pit is None:
        raise refuse("INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING", "no PIT SIC by close t")
    sic_str, availability, accession = pit
    sic = int(sic_str)
    close_day = close_t_iso[:10]
    covering = [r for r in sic_map if r.sic_start <= sic <= r.sic_end
                and (r.effective_from is None or r.effective_from <= close_day)]
    if not covering:
        raise refuse("INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING", f"SIC {sic} maps to no registered sector")
    # latest effective_from governs; NULL ranks below any dated row.
    def key(r: SicMapRow) -> str:
        return r.effective_from or ""
    top = max(key(r) for r in covering)
    winners = [r for r in covering if key(r) == top]
    if len({(w.research_sector, w.sector_etf) for w in winners}) != 1:
        raise refuse("INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT",
                     f"SIC {sic} has conflicting same-effective sector rows")
    w = winners[0]
    return SectorRecord(sector_id=w.research_sector, availability_timestamp=availability,
                        supersession_ordinal=0,
                        source_evidence_identity=f"sic_obs:{accession}|sic_map:{w.sic_start}-{w.sic_end}")


def sector_etf(sic_map: list[SicMapRow], sector_id: str) -> str:
    for r in sic_map:
        if r.research_sector == sector_id:
            return r.sector_etf
    raise refuse("REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
                 f"no registered ETF for sector {sector_id}")
