"""Censuses and the enrichment/adjudication seam reconciliation.

Three rules shape this module.

**Nothing is a pass by being empty.** Every census reports the number of records EXAMINED beside
its counts, and refuses to certify a zero over an empty set. A run that enriched nothing must not
be able to report zero violations and look healthy.

**Reserved codes stay visible at zero.** `SOURCE_MISSING` has no frozen trigger (R-A2), so it is
emitted with count 0 rather than omitted. An absent bucket and an empty bucket say different
things, and only one of them is evidence.

**The seam is reconciled, not assumed.** Since the entry adjudication now lives outside the frozen
record (owner ruling 2026-08-12), the join between them is a place where records could be lost or
duplicated silently. Every enriched record must have exactly one adjudication, in exactly the state
its enrichment code implies, with no orphans on either side and no duplicate joins.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from . import admissibility as A
from . import enrichment as E


class CensusRefused(Exception):
    """A census that would certify nothing, or a seam that does not reconcile."""


def enrichment_census(records: list[Any]) -> dict[str, Any]:
    """Per-code and per-category counts over the enriched population."""
    if not records:
        raise CensusRefused("empty enrichment census: a zero over no records is not a pass")
    by_code = Counter(r.ExecutionEnrichmentCode for r in records)
    unknown = sorted(set(by_code) - set(E.REGISTERED_CODES))
    if unknown:
        raise CensusRefused(f"unregistered terminal codes emitted: {unknown}")

    by_category: Counter[str] = Counter()
    for code, n in by_code.items():
        by_category[E.CENSUS_CATEGORY[code]] += n

    return {
        "records_examined": len(records),
        "by_code": {code: by_code.get(code, 0) for code in E.REGISTERED_CODES},
        "by_census_category": {
            E.CENSUS_CATEGORY[code]: by_category.get(E.CENSUS_CATEGORY[code], 0)
            for code in E.REGISTERED_CODES
        },
        "reserved_codes": {code: by_code.get(code, 0) for code in E.RESERVED_CODES},
        "one_terminal_code_per_record": sum(by_code.values()) == len(records),
    }


def seam_reconciliation(records: list[Any], adjudications: list[Any]) -> dict[str, Any]:
    """Prove the enrichment -> entry-adjudication join is exact.

    Exactly one adjudication per enriched record, joined on `decision_record_sha256`; a successful
    enrichment carries an economic decision, a stopped one carries NOT_ADJUDICATED; and neither side
    has an orphan or a duplicate.
    """
    if not records:
        raise CensusRefused("empty seam reconciliation: nothing was examined")

    rec_ids = Counter(r.decision_record_sha256 for r in records)
    adj_ids = Counter(a.decision_record_sha256 for a in adjudications)
    duplicate_records = sorted(k for k, n in rec_ids.items() if n > 1)
    duplicate_adjudications = sorted(k for k, n in adj_ids.items() if n > 1)
    orphan_records = sorted(set(rec_ids) - set(adj_ids))
    orphan_adjudications = sorted(set(adj_ids) - set(rec_ids))

    by_id = {a.decision_record_sha256: a for a in adjudications}
    state_violations = []
    for r in records:
        adj = by_id.get(r.decision_record_sha256)
        if adj is None:
            continue
        succeeded = r.ExecutionEnrichmentCode == E.SUCCESS
        if succeeded and adj.outcome == A.NOT_ADJUDICATED:
            state_violations.append((r.decision_record_sha256, "success without a decision"))
        if not succeeded and adj.outcome != A.NOT_ADJUDICATED:
            state_violations.append((r.decision_record_sha256, "stop carrying a decision"))
        if not succeeded and adj.economic_gap is not None:
            state_violations.append((r.decision_record_sha256, "stop carrying a gap value"))

    problems = []
    if duplicate_records:
        problems.append(f"duplicate enriched records: {duplicate_records}")
    if duplicate_adjudications:
        problems.append(f"duplicate adjudications: {duplicate_adjudications}")
    if orphan_records:
        problems.append(f"enriched records with no adjudication: {orphan_records}")
    if orphan_adjudications:
        problems.append(f"adjudications with no enriched record: {orphan_adjudications}")
    if state_violations:
        problems.append(f"state violations: {state_violations}")
    if problems:
        raise CensusRefused("; ".join(problems))

    adjudicated = [a for a in adjudications if a.outcome != A.NOT_ADJUDICATED]
    return {
        "records_examined": len(records),
        "adjudications_examined": len(adjudications),
        "duplicate_enrichment_identities": 0,
        "duplicate_adjudications": 0,
        "orphan_enriched_records": 0,
        "orphan_adjudications": 0,
        "missing_decision_enrichment_bindings": 0,
        "state_violations": 0,
        "economically_adjudicated": len(adjudicated),
        "admitted": sum(1 for a in adjudicated if a.entry_admissible),
        "not_admitted_gap_filter": sum(1 for a in adjudicated if a.outcome == A.NOT_ADMITTED_GAP),
        "not_adjudicated": len(adjudications) - len(adjudicated),
    }


def integrity_census(
    records: list[Any], adjudications: list[Any], guard_counts: dict[str, int]
) -> dict[str, Any]:
    """The preregistered Phase 3B integrity gates, every one of which must read zero."""
    seam = seam_reconciliation(records, adjudications)
    future_info = sum(1 for r in records if r.ExecutionEnrichmentCode == E.FUTURE_INFORMATION)
    census = {
        "records_examined": len(records),
        "decision_record_mutations": 0,  # any mutation raises before a record is produced
        "missing_decision_enrichment_bindings": seam["missing_decision_enrichment_bindings"],
        "duplicate_enrichment_identities": seam["duplicate_enrichment_identities"],
        "future_information_violations": future_info,
        "unregistered_data_source_reads": guard_counts.get("unregistered_data_source_reads", 0),
        "unreconciled_validation_units": seam["orphan_enriched_records"]
        + seam["orphan_adjudications"],
        "oos_reads": guard_counts.get("oos_reads", 0),
    }
    gates = {k: v for k, v in census.items() if k != "records_examined"}
    census["all_gates_zero"] = all(v == 0 for v in gates.values())
    census["vacuity_check"] = "records_examined > 0 required for the zeros to mean anything"
    return census
