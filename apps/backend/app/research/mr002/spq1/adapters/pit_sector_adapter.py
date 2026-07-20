"""PIT sector-classification adapter (Phase 2A domain 6).

Maps registered SIC observations (with acceptance/publication timestamps) to frozen ``SectorRecord``
inputs. The latest record available by close t governs; a future-published record is excluded; a
same-timestamp conflict fails closed (all enforced by the frozen resolver). No present-day backfill.
sector_id is the registered classification value (SIC division) via a frozen mapping.
"""
from __future__ import annotations

from ..sector_pit import SectorRecord
from . import normalize_utc_iso

CLASSIFICATION_SYSTEM = "SIC"

# Frozen SIC leading-digit -> sector_id (division-level). Registered mapping-table identity.
_SIC_DIVISION = {
    "0": "MATERIALS", "1": "ENERGY", "2": "MATERIALS", "3": "TECH", "4": "UTILITIES",
    "5": "DISCRETIONARY", "6": "FIN", "7": "TECH", "8": "HEALTHCARE", "9": "STAPLES",
}


def sic_to_sector(sic: str) -> str:
    return _SIC_DIVISION.get(str(sic).strip()[:1], "MATERIALS")


def load_sector_records(con, cik: int) -> list[SectorRecord]:  # noqa: ANN001
    rows = con.execute(
        "select accepted_utc, sic, accession from sic_observations where cik = ? "
        "order by accepted_utc",
        [cik],
    ).fetchall()
    records: list[SectorRecord] = []
    for i, (accepted_utc, sic, accession) in enumerate(rows):
        records.append(
            SectorRecord(
                sector_id=sic_to_sector(str(sic)),
                availability_timestamp=normalize_utc_iso(accepted_utc),
                supersession_ordinal=i,  # registered acceptance ordering
                source_evidence_identity=f"sic_obs:{accession}",
            )
        )
    return records
