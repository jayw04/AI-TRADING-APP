"""Second corrigendum: the Config A/B/C mapping IS executable, and it is inside the bound image.

Corrigendum v1.0 corrected the register's claim that the A/B/C parameter values were undefined, and
left a narrower claim standing: that nothing binds them to an executable configuration identity and
that no code maps "B" to 2.00. That narrower claim is ALSO wrong.

Same error twice, same cause: I stopped at a pointer instead of following it. The first time it was
a governing document naming an external authority; the second time it was an `import` at the top of
the file I was reading.

Zero-data instrument: reads repository files only. No AWS call, no sealed object, no credential.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_EVAL = os.path.join(_REPO, "docs", "review", "mr002", "evaluator")

CONFIG_MODULE = "mr002_valoos_portfolio_identity.py"
EXPECTED_MAPPING = {"A": 1.75, "B": 2.00, "C": 2.25}
V03_TABLE = {"A": 1.75, "B": 2.00, "C": 2.25}  # v0.3 SS6, sha256 1007db82...


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def parse_z_entry() -> dict[str, float]:
    """Read the literal Z_ENTRY mapping out of the bound module rather than importing it."""
    src = open(os.path.join(_EVAL, CONFIG_MODULE), encoding="utf-8").read()
    m = re.search(r"^Z_ENTRY\s*=\s*\{([^}]*)\}", src, re.M)
    if not m:
        raise SystemExit("REFUSED: Z_ENTRY literal not found in the bound module")
    pairs = re.findall(r'"([ABC])"\s*:\s*([0-9.]+)', m.group(1))
    if len(pairs) != 3:
        raise SystemExit(f"REFUSED: expected 3 configurations, parsed {len(pairs)}")
    return {k: float(v) for k, v in pairs}


def verify() -> dict:
    manifest = json.load(open(
        os.path.join(_EVAL, "MR002_EvaluatorImageManifest_Runtime_v1.0.json"), encoding="ascii"))
    digests = manifest["module_digests_in_image"]
    if CONFIG_MODULE not in digests:
        raise SystemExit(f"REFUSED: {CONFIG_MODULE} is not a bound image module")
    actual = _sha256(os.path.join(_EVAL, CONFIG_MODULE))
    if actual != digests[CONFIG_MODULE]:
        raise SystemExit("REFUSED: bound module does not reproduce its image digest")
    mapping = parse_z_entry()
    if mapping != EXPECTED_MAPPING or mapping != V03_TABLE:
        raise SystemExit(f"REFUSED: parsed mapping {mapping} disagrees with the v0.3 gate table")
    return {
        "module": CONFIG_MODULE,
        "in_bound_image": True,
        "bound_image_digest": digests[CONFIG_MODULE],
        "recomputed_digest": actual,
        "digest_matches": True,
        "parsed_mapping": mapping,
        "agrees_with_v03_gate_table": True,
        "module_count_in_image": len(digests),
    }


def build() -> dict:
    v = verify()
    return {
        "record_type": "MR002_Phase3B_LaunchPreflightCorrigendum",
        "version": "2.0",
        "artifact_kind": "CORRECTION",
        "date": "2026-08-12",
        "supersedes": (
            "MR002_Phase3B_LaunchPreflight_Corrigendum_v1.0.json (identity c392589988a0...) - "
            "ONLY for its 'what_remains_true_and_unchanged' section. That record is NOT edited and "
            "remains the history of the first correction."
        ),
        "corrects": {
            "record": "MR002_Phase3B_LaunchPreflight_Corrigendum_v1.0.json",
            "identity_sha256":
                "c392589988a0665aec505efe0415e89d22fe16d56c4c798058935333f0c4b1d4",
            "commit": "88c11d0",
        },
        "boundary": (
            "Zero-data. No AWS call, no sealed object, no credential, no image change. "
            "validation_authorization remains true at _rev 1; the opening remains UNSPENT."
        ),
        "corrected_claim": {
            "as_issued_in_corrigendum_v1": [
                "Nothing binds these values to an EXECUTABLE configuration identity with a hash.",
                "configuration_id is an opaque caller-supplied string in both the SPQ-1 producer "
                "and the evaluator; mr002_valoos_candidates.validate_candidate only checks that a "
                "record's configuration_id equals the one passed in - no code maps 'B' to "
                "z_entry 2.00.",
                "Therefore the Phase 3B RunSpecification must CREATE that binding.",
            ],
            "correction": (
                "WRONG on the evaluator side. mr002_valoos_portfolio_identity.py - one of the "
                "bound image modules - defines Z_ENTRY = {'A': 1.75, 'B': 2.00, 'C': 2.25} with "
                "the comment 'PR-20 A/B/C differ ONLY in Z_entry'. "
                "mr002_valoos_candidates.validate_candidate REFUSES a configuration_id absent from "
                "that mapping. mr002_valoos_construction.build_intended_target resolves "
                "z_entry = Z_ENTRY[config] and _select_side applies the frozen rule: bottom/top 10% "
                "of the side-eligible z pool AND |z| >= Z_entry. test_increment3 asserts the "
                "mapping literally. The mapping is folded into the portfolio-identity constants "
                "hash, so it is already part of a computed identity."
            ),
            "corrected_status": "RESOLVED_AND_ALREADY_EXECUTABLE_INSIDE_THE_BOUND_IMAGE",
            "what_was_right": (
                "configuration_id IS an inert pass-through in the SPQ-1 producer - it is carried "
                "onto the SignalDecisionRecord and into candidate_id but influences no computation "
                "there. That is correct by design, not a defect: selection is a portfolio-"
                "construction step, not a signal-production step."
            ),
        },
        "verification": v,
        "architectural_consequence": {
            "seam": (
                "Config-dependent economics live INSIDE the bound evaluator image "
                "(Z_ENTRY + selection); per-security record production lives OUTSIDE it "
                "(the SPQ-1 producer and enrichment). This is a clean and already-implemented "
                "seam, and it strengthens the Option A execution-boundary recommendation."
            ),
            "effect_on_runspecification": (
                "The Phase 3B RunSpecification must CITE and VERIFY the existing mapping - assert "
                "Z_ENTRY equals the v0.3 gate table and that the module reproduces its bound image "
                "digest - rather than construct a mapping. There is nothing to build."
            ),
            "no_new_selection": (
                "No configuration is selected, added, or altered by this record. The values are "
                "the frozen v0.3 values and the code implementing them predates this work."
            ),
        },
        "effect_on_the_register_verdict": (
            "NONE. The STOP stands on independent grounds: no Phase 3B entry point, no sealed-store "
            "reader, a producer hard-bound to DEVELOPMENT, zero emitters for the six deliverables, "
            "and the unreconciled output and input-source contracts. Config A/B/C is now fully "
            "resolved and is no longer a Phase 3B work item at all."
        ),
        "repeat_error_analysis": {
            "pattern": "Reported an absence after stopping at a pointer instead of following it.",
            "occurrence_1": (
                "Preregistration v1.0.4 names the v0.3 gate table as the governing authority "
                "instead of restating it. I read the pointer as an absence."
            ),
            "occurrence_2": (
                "mr002_valoos_candidates.py imports Z_ENTRY from mr002_valoos_portfolio_identity "
                "on line 15. I searched the file's own contents for a mapping, found none, and "
                "reported an absence without following the import."
            ),
            "control": (
                "Before reporting that something is absent, resolve every pointer out of the file "
                "or record examined - imports, cross-references, named authorities - and hash or "
                "read the target. An absence claim is only as good as the closure of its search."
            ),
        },
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_LaunchPreflight_Corrigendum_v2.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    print(f"Z_ENTRY parsed from the bound module: {record['verification']['parsed_mapping']}")
    print(f"module digest matches image: {record['verification']['digest_matches']}")


if __name__ == "__main__":
    main()
