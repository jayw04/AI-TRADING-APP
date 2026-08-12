"""Corrigendum to the Phase 3B launch-preflight blocker register (identity 70b3ebd2...).

The register asserted that the Config A/B/C parameter values are carried by no frozen artifact.
That is WRONG. They are carried by two independently hash-registered pre-validation artifacts and
reproduce exactly. The register is corrected here rather than rewritten, because a committed finding
that other decisions were taken against must not silently change.

What survives the correction is narrower and still real: the VALUES exist, but nothing binds them to
an executable configuration identity, and no code maps a configuration_id to them.

Zero-data instrument: reads repository files only. No AWS call, no sealed object, no credential.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

# (repo path, sha256 registered in preregistration v1.0.4, where it is registered)
SOURCES = [
    ("docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md",
     "1007db8204ad3dff544483614ed40f5fce1573e4dd61b9f6a1cd79d5902bdc59",
     "governing_gate_source['v0.3_gate_table_sha256'] (recorded truncated as '1007db8204ad3dff...')"),
    ("docs/implementation/TradingWorkbench_MR002_PreRegistration_v1.1_REFREEZE_CANDIDATE.md",
     "311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5",
     "governing_frozen_sources.windows_design.sha256"),
]


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def verify_sources() -> list[dict]:
    out = []
    for rel, registered, where in SOURCES:
        path = os.path.join(_REPO, rel)
        if not os.path.exists(path):
            raise SystemExit(f"REFUSED: governing source absent: {rel}")
        actual = _sha256_file(path)
        out.append({"file": rel, "registered_sha256": registered, "recomputed_sha256": actual,
                    "matches": actual == registered, "registered_in": where})
    if not all(r["matches"] for r in out):
        raise SystemExit("REFUSED: a governing source does not reproduce its registered hash")
    return out


def build() -> dict:
    sources = verify_sources()
    return {
        "record_type": "MR002_Phase3B_LaunchPreflightCorrigendum",
        "version": "1.0",
        "artifact_kind": "CORRECTION",
        "date": "2026-08-12",
        "corrects": {
            "record": "MR002_Phase3B_LaunchPreflight_BlockerRegister_v1.0.json",
            "identity_sha256":
                "70b3ebd295ded890004100c5d763641c44a7a0d6ae76484ceb0d5a8386d11a38",
            "commit": "fa9fc9a",
            "disposition": (
                "The register is NOT rewritten. It stands as issued, corrected by this record, "
                "because owner decisions were taken against it as written."
            ),
        },
        "boundary": (
            "Zero-data. No AWS call, no sealed object, no credential. validation_authorization "
            "remains true at _rev 1 and the single validation opening remains UNSPENT."
        ),
        "corrected_claims": [
            {
                "location": "parameter_resolution.config_A_B_C_identities.status = UNRESOLVED",
                "as_issued": (
                    "No frozen artifact carries the A/B/C parameter values (Z_entry thresholds) or "
                    "their hashes. Preregistration v1.0.4 names the configs and gates Config B, but "
                    "never defines them."
                ),
                "correction": (
                    "WRONG. The values are carried by the v0.3 gate table SS6 'Frozen parameter "
                    "policy (exactly three configurations - unchanged)' and independently restated "
                    "in the v1.1 refreeze candidate. Preregistration v1.0.4 registers BOTH files by "
                    "SHA-256, and both reproduce exactly. Preregistration v1.0.4 does not restate "
                    "the table because it names the v0.3 gate table as the governing authority, "
                    "'frozen UNCHANGED into v1.0' - I read the pointer as an absence."
                ),
                "corrected_status": "RESOLVED_BY_REGISTERED_GOVERNING_SOURCE",
            },
        ],
        "resolved_configurations": {
            "authority": "v0.3 SS6, frozen unchanged into v1.0; corroborated by v1.1 SS(summary)",
            "exit_z_all_configs": 0.35,
            "max_hold_sessions_all_configs": 5,
            "max_hold_note": (
                "v0.3: the entry session is session 1 and the time-stop exit executes at the OPEN "
                "OF SESSION 6. This is consistent with preregistration v1.0.4 "
                "realization_horizon_governing = 6 (next-open exit t+1..t+6): entry at the t+1 "
                "open is session 1, so session 6 is the t+6 open. The 5-session CLOSE-exit "
                "alternative is the REJECTED variant and is not executable configuration."
            ),
            "configs": {
                "A": {"z_entry": 1.75, "role": "neighborhood sensitivity"},
                "B": {"z_entry": 2.00, "role": "PRIMARY - verdict configuration; the sole "
                                              "eventual OOS candidate"},
                "C": {"z_entry": 2.25, "role": "neighborhood sensitivity"},
            },
            "verdict_rule": "Verdict reads on B only; no other combinations run.",
        },
        "governing_sources_verified": sources,
        "what_remains_true_and_unchanged": [
            "Nothing binds these values to an EXECUTABLE configuration identity with a hash.",
            "configuration_id is an opaque caller-supplied string in both the SPQ-1 producer and "
            "the evaluator; mr002_valoos_candidates.validate_candidate only checks that a record's "
            "configuration_id equals the one passed in - no code maps 'B' to z_entry 2.00.",
            "Therefore the Phase 3B RunSpecification must CREATE that binding (literal values plus "
            "a configuration hash) from these registered sources. It is a specification task, not "
            "an inference, and not an invention.",
        ],
        "effect_on_the_register_verdict": (
            "NONE. The STOP stands on independent grounds: no Phase 3B entry point, no sealed-store "
            "reader, a producer hard-bound to DEVELOPMENT, enrichment outside the bound evaluator "
            "identity, zero emitters for the six deliverables, and the unreconciled output and "
            "input-source contracts. Config A/B/C moves from a STOP item to a specification item."
        ),
        "lesson": (
            "A governing document that names an external authority instead of restating its content "
            "is not silent. Follow the pointer and hash the target before reporting an absence."
        ),
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3B_LaunchPreflight_Corrigendum_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(f"wrote {out}")
    print(f"identity {record['record_identity_sha256']}")
    for s in record["governing_sources_verified"]:
        print(f"  verified {s['matches']}  {s['file']}")


if __name__ == "__main__":
    main()
