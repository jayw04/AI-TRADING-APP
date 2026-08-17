"""SPQ-1 Phase 3B — owner corrigendum to LabelAdjudication v2.0 / Matrix v1.3 (2026-08-17, PM).

The owner reviewed the implemented adjudication and ruled that ONE element was an implementation
inference, not an authorized change: the spinoffdividend dollar value entering the registered
economic gap's cash-distribution term. This record freezes that correction, registers the open
economic-semantics finding, and leaves every other v2.0/v1.3 element ACCEPTED verbatim. The
superseded records are preserved, not rewritten.

Zero-data: no sealed access, no validation read, no OOS read, no host start, no opening requested.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


record = {
    "record_type": "MR002_Phase3B_LabelAdjudication_Corrigendum",
    "version": "1.0",
    "artifact_kind": "OWNER_CORRECTION",
    "produced_at": "2026-08-17T00:00:00Z",
    "authorized_by": (
        "owner correction 2026-08-17 (PM), verbatim in substance: 'revert the cash_distributions() "
        "change that adds spinoffdividend to the economic-gap cash adjustment. My prior wording - "
        "\"its value may feed the same economic-adjustment machinery\" - was descriptive caution, "
        "not authorization to change the frozen gap economics.'"
    ),
    "corrects": {
        "MR002_Phase3B_LabelAdjudication_v2.0": {
            "record_identity_sha256_of_file": _sha256_file(
                os.path.join(_HERE, "MR002_Phase3B_LabelAdjudication_v2.0.json")
            ),
            "clause_superseded": (
                "labels.spinoff.Q3_execution_consequence limb (b) - 'a published spinoffdividend "
                "dollar value is consumed by the registered distribution term of the economic gap'. "
                "SUPERSEDED: NOT AUTHORIZED. Limbs (a) and (c) and every other answer stand."
            ),
        },
        "MR002_Phase3B_SemanticReconciliationMatrix_v1.3": {
            "record_identity_sha256_of_file": _sha256_file(
                os.path.join(_HERE, "MR002_Phase3B_SemanticReconciliationMatrix_v1.3.json")
            ),
            "clause_superseded": (
                "frozen_rule_spinoff_composite, the sentence 'The published spinoffdividend dollar "
                "value joins the registered cash-distribution term (USD/share, summed exactly like "
                "a dividend value)'. SUPERSEDED: the distribution term remains `dividend` ONLY. The "
                "rest of SPINOFF-COMPOSITE - the normalization, the standalone-spinoffdividend "
                "refusal, the no-general-composition boundary, the never-sum-the-ratio clause - "
                "stands unchanged."
            ),
        },
    },
    "accepted_unchanged": [
        "composite recognition: spinoff + spinoffdividend are one composite corporate-action event, not conflicting kinds",
        "relation adjudication: KNOWN_INFORMATIONAL_LINKAGE / NO_PHASE3B_EXECUTION_EFFECT",
        "spinoff / spinoffdividend composition machinery, including the standalone-spinoffdividend unit refusal",
        "spunofffrom: EXPLICITLY_INERT child-side metadata",
        "relation.value fail-closed premise guard (RELATION-VALUE-PREMISE)",
        "AUDIT-IDENTITY-PRECEDENCE extension",
        "the spinoff identity remains the composite event exactly as implemented",
    ],
    "why_the_gap_term_is_out_of_scope": (
        "the adjudication establishes (1) one composite event and (2) a value component associated "
        "with it. It does not by itself establish that this value belongs in the preregistered gap "
        "formula (open_t+1 + known_cash_distribution_t+1) / close_t - 1, which was frozen around "
        "the governed cash-distribution semantics. Treating spinoffdividend USD/share as equivalent "
        "to an ordinary cash dividend would change entry admissibility and therefore potentially "
        "validation returns - that requires a separate economic-semantics ruling, not an "
        "implementation inference."
    ),
    "open_finding_registered": {
        "id": "SPINOFF-GAP-SEMANTICS",
        "status": "OPEN - blocks nothing in the current package; blocks any future wiring of spinoffdividend into the gap",
        "governing_question": (
            "whether the vendor's spinoffdividend value is a cash distribution actually received "
            "by the holder and therefore belongs additively in known_cash_distribution, or is "
            "instead a valuation/reference amount describing distributed stock. The structural "
            "evidence (e.g. ABT->ABBV ratio 1.0 with $34.65) is NOT sufficient by itself to "
            "establish the first interpretation."
        ),
        "folds_in": (
            "the 2026-08-14 'spurious-negative-gap' observation (786f22e): SEP open/close are not "
            "spinoff-adjusted, so a spinoff session can carry a mechanical negative gap. That "
            "remains an OPEN economic-semantics finding under this id, adjudicated by the owner "
            "before any gap-formula change - never repaired implicitly."
        ),
    },
    "implementation_disposition": {
        "revert_scope": "cash_distributions() returns to `dividend` ONLY, plus the one dependent test assertion. The composition machinery is NOT undone.",
        "rebind_rule": "the correction lands BEFORE rebind - one clean v3.6 identity; the tree containing the unauthorized behaviour is never bound",
        "capacity": "no new 429x850 capacity run required (owner)",
        "requalification": "no host/runtime/P10 requalification required while the closure changes stay confined to this bridge-semantics work and the bound runtime is unchanged (owner)",
        "validation_oos": "sealed; no opening considered until the corrected v3.6 package is staged and passes the non-consuming ceremony",
    },
    "grants": "NOTHING beyond the correction itself.",
}

body = _canonical(record)
record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
out = os.path.join(_HERE, "MR002_Phase3B_LabelAdjudication_Corrigendum_v1.0.json")
with open(out, "wb") as fh:
    fh.write(_canonical(record))
print(f"wrote {os.path.basename(out)}")
print(f"identity {record['record_identity_sha256']}")
