"""A-1 price-basis evidence record: is the frozen gap-filter policy uniquely operationalized?

Three permitted outcomes: UNIQUE_OPERATIONALIZATION_PROVEN, MULTIPLE_PLAUSIBLE_OPERATIONALIZATIONS,
SOURCE_SEMANTICS_UNRESOLVED.

Produced under the control adopted after three overturned absence findings: the governing documents
were READ IN FULL rather than grepped for the term already in mind. That is what surfaced v0.4, which
grep-by-expected-term had missed twice.

Zero-data instrument: reads repository files only. No AWS call, no sealed object, no credential.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

V04 = "docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.4.md"
V03 = "docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md"
V10 = "docs/review/mr002/governing_sources/TradingWorkbench_MR002_PreRegistration_v1.0_FROZEN.md"
REVIEW = "docs/implementation/evidence/mr_002/MR002_OwnerReview_v0.3_and_V1V4_Decision_2026-07-11.md"
STAGE3_IMPL = "apps/backend/app/research/mr002/execution.py"
SPQ1_IMPL = "apps/backend/app/research/mr002/spq1/execution_enrichment.py"

FORMULA = "economic_gap_t+1 = (open_t+1 + known_cash_distribution_t+1) / close_t - 1"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256(rel: str) -> str:
    with open(os.path.join(_REPO, rel), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _text(rel: str) -> str:
    with open(os.path.join(_REPO, rel), encoding="utf-8") as fh:
        return fh.read()


def verify() -> dict:
    v04 = _text(V04)
    v10 = _text(V10)
    stage3 = _text(STAGE3_IMPL)
    spq1 = _text(SPQ1_IMPL)

    formula_in_v04 = "economic_gap_t+1 = (open_t+1 + known_cash_distribution_t+1) / close_t" in v04
    v3_verified = "Price-series policy (V3, verified)" in v04
    v04_in_authority_chain = "v0.4 (build-authorizing)" in v10
    rules_closed_since_v03 = "Strategy rules are unchanged and closed since v0.3" in v10
    stage3_conformant = bool(re.search(
        r"return \(open_next \+ cash_distribution\) / close_prev - 1\.0", stage3))
    spq1_uses_distribution_term = "cash_distribution" in spq1 or "known_cash_distribution" in spq1
    spq1_gap_expr = re.search(r"ratio = ([^\n]+)", spq1)

    if not (formula_in_v04 and v04_in_authority_chain):
        raise SystemExit("REFUSED: the v0.4 registration or its authority-chain membership did not "
                         "verify; do not emit a UNIQUE outcome on unverified premises")
    return {
        "formula_registered_in_v04": formula_in_v04,
        "v04_labels_it_V3_verified": v3_verified,
        "v04_named_in_the_signed_v10_authority_chain": v04_in_authority_chain,
        "v10_states_strategy_rules_closed_since_v03": rules_closed_since_v03,
        "stage3_implementation_conformant": stage3_conformant,
        "spq1_implementation_uses_the_distribution_term": spq1_uses_distribution_term,
        "spq1_gap_expression": spq1_gap_expr.group(1).strip() if spq1_gap_expr else None,
        "hashes": {rel: _sha256(rel) for rel in (V03, V04, V10, REVIEW, STAGE3_IMPL, SPQ1_IMPL)},
    }


def build() -> dict:
    v = verify()
    return {
        "record_type": "MR002_Phase3B_A1_PriceBasisEvidence",
        "version": "1.0",
        "artifact_kind": "EVIDENCE_RECORD",
        "date": "2026-08-12",
        "question": (
            "Given the registered price-series policy and the authoritative field semantics, is "
            "there exactly one way to construct the gap-filter numerator and denominator without "
            "introducing an additional economic choice?"
        ),
        "outcome": "UNIQUE_OPERATIONALIZATION_PROVEN",
        "boundary": (
            "Zero-data. No AWS call, no sealed object, no credential, no image change. "
            "validation_authorization remains true at _rev 1; the opening remains UNSPENT."
        ),

        "the_registered_operationalization": {
            "formula": FORMULA,
            "gate": "entry cancelled at the t+1 open if |economic_gap_t+1| >= 6%",
            "registered_in": V04,
            "registered_as": "Price-series policy (V3, verified)",
            "fields": {
                "open_t+1": "split-adjusted open",
                "close_t": "split-adjusted close",
                "known_cash_distribution_t+1": "ACTIONS dividend value",
            },
            "verbatim_qualifier_from_v04": (
                "(split-adjusted fields; the distribution term uses ACTIONS dividend values, whose "
                "split basis is confirmed at Implementation Freeze before the formula is applied "
                "- SS7)"
            ),
        },

        "why_this_is_governing_and_not_a_superseded_draft": (
            "The signed v1.0 FROZEN document names the authority chain explicitly - 'owner proposal "
            "-> reviews 1-2 -> v0.3 (S1-S4) -> v0.4 (build-authorizing) -> v0.5-v0.6 -> v0.7-v0.9 "
            "-> V1/V2 validation -> predecessor-remedy countersign' - so v0.4 is a member of the "
            "chain, not a discarded draft. v1.0 further states 'Strategy rules are unchanged and "
            "closed since v0.3' and describes itself as freezing the DATA layer that v0.4 required. "
            "The economic-gap formula is therefore a live registered rule."
        ),
        "provenance_of_the_formula": (
            "Directed by the owner in the 2026-07-11 V0.3/V1-V4 review: 'The four-series policy is "
            "correct, but register the exact gap formula... Confirm the exact vendor field "
            "semantics before adopting the formula.' v0.4 carried it into the preregistration."
        ),
        "four_series_mapping_resolved": {
            "signal returns": "closeadj (total-return adjusted)",
            "execution fills at the open": "open / close (split-adjusted, non-dividend-adjusted)",
            "gap filter": "CONSTRUCTED: (open + ACTIONS distribution) / close - 1",
            "dollar-volume ranking": "close x volume (owner-approved 2026-07-11 as the "
                                     "consistently split-adjusted pair; closeunadj x volume was "
                                     "REJECTED as mixing adjustment bases)",
            "note": (
                "The gap series is the one registered use with no dedicated vendor column - it is "
                "constructed, which is exactly why v0.4 had to register the construction."
            ),
        },

        "findings_to_discharge_before_freeze": [
            {
                "id": "A1-F1",
                "severity": "UNDISCHARGED PRECONDITION",
                "title": "The ACTIONS dividend split-basis confirmation appears never to have been "
                         "performed",
                "detail": (
                    "v0.4 conditions the formula on the ACTIONS dividend split basis being "
                    "'confirmed at Implementation Freeze BEFORE the formula is applied'. The "
                    "2026-07-11 review separately directed 'Add the ACTIONS dividend-value basis "
                    "check to Implementation Freeze'. No evidence of that confirmation was found."
                ),
                "character": (
                    "A DATA-SEMANTICS VERIFICATION, not an economic choice: does the ACTIONS "
                    "dividend value share the split basis of the SEP close it is added to? It is "
                    "dischargeable on the DEVELOPMENT partition, which is unsealed, and needs no "
                    "validation access."
                ),
            },
            {
                "id": "A1-F2",
                "severity": "IMPLEMENTATION NONCONFORMANCE",
                "title": "The SPQ-1 enricher does not implement the registered economic gap",
                "detail": (
                    "apps/backend/app/research/mr002/execution.py implements the registered formula "
                    "exactly: (open_next + cash_distribution) / close_prev - 1.0. The SPQ-1 "
                    "enricher bound into the Phase 3B path instead computes "
                    f"'{v['spq1_gap_expression']}' - no distribution term in the numerator, and an "
                    "already-distribution-adjusted close in the denominator. It carries no cash "
                    "distribution parameter at all."
                ),
                "consequence": (
                    "The two constructions differ whenever a distribution occurs, and the second "
                    "mixes adjustment bases - the precise defect freeze blocker V3 exists to "
                    "prevent. The contract governs: the Phase 3B layer must implement the "
                    "registered formula. The frozen contract is NOT amended to match the code."
                ),
                "hierarchy_applied": (
                    "frozen price-series policy -> authoritative dataset field semantics -> "
                    "implementation. Never implementation -> inferred policy."
                ),
            },
        ],

        "corrections_to_my_own_earlier_findings": [
            "I first reported that the frozen contract nowhere states the price-series basis. WRONG "
            "- v0.3 SS4 states it for all four uses.",
            "I then reported that the operationalization admitted multiple plausible formulas. ALSO "
            "WRONG - v0.4 registers exactly one, and an implementation of it already exists.",
            "Both errors shared a cause: searching the governing documents for the term I expected "
            "instead of reading them. Reading v0.4 in full is what surfaced the registered formula.",
        ],
        "implication_for_the_grant": (
            "Because the operationalization is UNIQUE and already registered, this is an "
            "execution-contract clarification rather than the selection of a new convention. No "
            "research economics change, so the supplemental execution-identity adjudication remains "
            "sufficient and the preregistration/authorization chain does not require reassessment on "
            "this ground."
        ),
        "verification": v,
        "grants": "NOTHING. Evidence only.",
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_A1_PriceBasisEvidence_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"OUTCOME: {record['outcome']}")
    for f in record["findings_to_discharge_before_freeze"]:
        print(f"  {f['id']}: {f['title']}")


if __name__ == "__main__":
    main()
