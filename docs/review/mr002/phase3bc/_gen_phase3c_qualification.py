"""SPQ-1 Phase 3C — executable identity + non-sealed qualification evidence.

Produced for owner step 6: "return with the executable identity and qualification evidence before
requesting a new sealed validation opening."

Nothing here reads the validation or OOS partitions. The whole qualification ran on synthetic
fixtures inside the frozen research image with --network=none.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
SCRATCH = (r"C:\Users\jayw0_ithkvux\AppData\Local\Temp\claude"
           r"\C--LLM-RAG-APP-ai-trading-app\cde206cc-af1b-48ec-b759-f3454beaae60\scratchpad")
LOG = os.path.join(SCRATCH, "phase3c_qualification_log.txt")

PKG = os.path.join("apps", "backend", "app", "research", "mr002", "phase3c")
TESTS = os.path.join("apps", "backend", "tests", "research", "phase3c")

IMAGE = "mr002-research:v1.4"
IMAGE_ID = "sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha_file(rel: str) -> tuple[str, int]:
    with open(os.path.join(REPO, rel), "rb") as fh:
        raw = fh.read()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _tree(rel_dir: str) -> dict:
    out = {}
    for name in sorted(os.listdir(os.path.join(REPO, rel_dir))):
        if not name.endswith(".py"):
            continue
        rel = os.path.join(rel_dir, name).replace("\\", "/")
        sha, n = _sha_file(rel)
        out[rel] = {"sha256": sha, "bytes": n}
    return out


def _code_identity(trees: list[dict]) -> str:
    """One identity over every module, in canonical path order."""
    h = hashlib.sha256()
    for tree in trees:
        for path in sorted(tree):
            h.update(f"{path}:{tree[path]['sha256']}\n".encode("ascii"))
    return h.hexdigest()


def main() -> None:
    pkg = _tree(PKG)
    tests = _tree(TESTS)

    with open(LOG, "rb") as fh:
        log_raw = fh.read()
    log_txt = log_raw.decode("ascii", "replace")
    summary = re.search(r"(\d+) passed", log_txt)
    passed = int(summary.group(1)) if summary else -1
    failed = len(re.findall(r"\bFAILED\b", log_txt))

    record = {
        "record_type": "MR002_Phase3C_ExecutableIdentityAndQualification",
        "version": "1.0",
        "artifact_kind": "PRE_OPENING_QUALIFICATION_EVIDENCE",
        "produced_at": "2026-08-18T00:00:00Z",
        "purpose": (
            "owner step 6 - the executable identity and non-sealed qualification evidence that "
            "must exist BEFORE a new sealed validation opening is requested"
        ),
        "authorized_by": (
            "MR002_Phase3C_OwnerRulings_v1.2.json - Phase 3C implementation and non-sealed "
            "qualification AUTHORIZED; sealed validation opening NOT GRANTED"
        ),
        "affirmations": {
            "validation_bytes_read": False,
            "oos_bytes_read": False,
            "sealed_opening_requested": False,
            "sealed_opening_granted": False,
            "performance_of_any_sealed_partition_computed": False,
            "all_fixtures_synthetic": True,
            "network_disabled_during_qualification": True,
        },
        "executable_identity": {
            "phase3c_code_identity_sha256": _code_identity([pkg]),
            "phase3c_plus_tests_identity_sha256": _code_identity([pkg, tests]),
            "modules": pkg,
            "tests": tests,
        },
        "bound_upstream": {
            "adopted_runner": "apps/backend/scripts/mr002_development_run.py",
            "adopted_runner_sha256": _sha_file(
                "apps/backend/scripts/mr002_development_run.py")[0],
            "adopted_mechanics_block_lines": "251-276",
            "adopted_mechanics_block_sha256":
                "02d9ea7571046419694ec46782c1fdd0e308bfc279c3ca4715681e487bb347b2",
            "governing_construction": "apps/backend/app/research/mr002/joint_portfolio.py",
            "governing_construction_sha256": _sha_file(
                "apps/backend/app/research/mr002/joint_portfolio.py")[0],
            "frozen_primitives": "apps/backend/app/research/mr002/execution.py",
            "frozen_primitives_sha256": _sha_file(
                "apps/backend/app/research/mr002/execution.py")[0],
            "binding_is_enforced_in_code": (
                "app/research/mr002/phase3c/adopted.py re-hashes the adopted runner AND the "
                "mechanics block at import and raises AdoptionBindingViolation on any drift, so "
                "the R5A adoption cannot rot silently"
            ),
        },
        "runtime": {
            "image": IMAGE,
            "image_id": IMAGE_ID,
            "network": "none",
            "why_the_image_is_required": (
                "joint_portfolio._assert_registered_solver refuses to run unless "
                "/manifest/pip_report.json pins quadprog to the registered artifact "
                "cc1996a0...; that refusal is a control, so the qualification runs inside the "
                "frozen image rather than weakening it"
            ),
            "solver_pin_verified": {"quadprog": "0.1.13",
                                    "artifact_sha256":
                                        "cc1996a0e3de1d423f8662fe21368948afdc91d851910b77320caaf7c15357ff"},
        },
        "qualification_run": {
            "command": (
                "docker run --rm --network=none -e PYTHONPATH=/work/apps/backend "
                "-v <repo>:/work -w /work/apps/backend mr002-research:v1.4 "
                "python -m pytest tests/research/phase3c --noconftest -v"
            ),
            "tests_passed": passed,
            "tests_failed": failed,
            "exit_code": 0,
            "log_sha256": hashlib.sha256(log_raw).hexdigest(),
            "log_bytes": len(log_raw),
            "log_retained": "session scratchpad (not committed; the summary and hash are the record)",
            "conftest_note": (
                "--noconftest is required because the repo-wide backend conftest imports "
                "pytest_asyncio, which the research image does not carry. No Phase 3C test uses a "
                "conftest fixture."
            ),
        },
        "coverage_against_the_owner_required_list": {
            "partial_retention_0_lt_y_lt_1": "test_partial_coupling_reduction_trims_without_closing",
            "full_retention_y_eq_1": "test_full_retention_leaves_positions_untouched",
            "full_coupling_liquidation_reduce_to_zero": (
                "test_reduce_to_zero_coupling_is_recorded_as_an_exit"),
            "commission_on_reduced_notional": (
                "test_reduction_charges_commission_on_the_reduced_notional"),
            "retained_share_quantity_correct": "test_retained_quantity_is_the_untrimmed_remainder",
            "short_borrow_basis_follows_remaining_shares": (
                "test_short_borrow_basis_follows_the_remaining_shares"),
            "nav_pnl_reconciles_through_the_trim": "test_nav_reconciles_through_the_trim",
            "deterministic_replay": "test_replay_is_deterministic",
            "r6_drift_still_integrity_failure": (
                "test_synthetic_post_execution_drift_is_an_integrity_failure"),
            "differential_vs_accepted_development_runner": (
                "test_phase3c_agrees_with_the_accepted_development_runner - parameterized over "
                "five regimes: no trim, partial trim, larger partial trim, short-side trim, and "
                "full coupling liquidation"
            ),
        },
        "differential_result": {
            "compared": (
                "the accepted development runner's run_config against Phase 3C's "
                "run_config_validation, on identical synthetic non-sealed inputs"
            ),
            "agreement": "EXACT",
            "fields_compared": [
                "reductions", "entries_long", "entries_short", "exits", "exit_reasons",
                "traded_notional", "costs", "borrow", "nav_curve", "daily_ret",
                "session_hashes", "per-trade reason", "per-trade net_pnl",
            ],
            "tolerance": "none - equality, including the per-session determinism hashes",
            "significance": (
                "this is the evidence that the thin adapter did not move the already-exercised "
                "economics. It is worth more than a general test suite because it compares "
                "against the implementation that produced the accepted v1.1 development evidence."
            ),
        },
        "defects_found_and_fixed_during_qualification": [
            {
                "defect": "the R6 post-execution drift check used an exact ratio test",
                "symptom": (
                    "it fired at |net|/gross == 0.050000 exactly, where the solver had "
                    "legitimately brought the book to the band boundary"
                ),
                "consequence_if_shipped": (
                    "a false-positive INTEGRITY_FAILURE would have halted a perfectly valid "
                    "replay, and the halt would have looked like a genuine governance finding"
                ),
                "fix": (
                    "compare in the solver's own homogeneous weight units against its frozen "
                    "primal feasibility tolerance PRIMAL_RESIDUAL_MAX (1e-9), not by exact ratio"
                ),
                "regression_test": "test_drift_check_does_not_fire_at_the_band_boundary",
            },
        ],
        "rulings_implemented": {
            "ruling_1_retired_3p5_sigma_trigger": (
                "phase3c/exits.exit_reason_validation takes NO confirm parameter and has no "
                "+/-3.5 rung; equivalence with the frozen ladder at confirm=False is proven "
                "across a parameter sweep"
            ),
            "ruling_2_joint_construction_governing": (
                "phase3c/replay calls joint_portfolio.build_joint; the superseded v1.0 cascade "
                "is never invoked"
            ),
            "ruling_3_configs_A_B_C": (
                "the runner is parameterized by CONFIGS[A|B|C]; no parameter search exists"
            ),
            "ruling_4_replay_integrity_reserved": (
                "no replay_integrity metric, threshold or composite score was invented; integrity "
                "is expressed through already-frozen invariants and the typed IntegrityFailure"
            ),
            "ruling_R5A_coupling_reduction_adoption": (
                "the adopted mechanics are reused verbatim and hash-bound at import"
            ),
            "ruling_R6_drift_quantity_undefined": (
                "a surviving drift breach records the frozen ordering with quantity=None and "
                "raises INTEGRITY_FAILURE; coupling semantics are never borrowed for it"
            ),
            "integrity_stop_is_not_an_economic_verdict": (
                "gates.evaluate short-circuits to INTEGRITY_FAILURE and never returns "
                "VALIDATION_DO_NOT_ADVANCE for a replay-definition failure"
            ),
        },
        "not_yet_done": [
            "no run against the sealed validation partition - the opening is NOT granted",
            "the DSR trial-dispersion artifact is emitted only once a real replay produces the "
            "A/B/C annualized net Sharpes",
            "a full-window dry run against a development-window FrozenDataset has not been "
            "executed here; the differential used synthetic fixtures spanning all five reduction "
            "regimes",
        ],
        "grants": "NOTHING. Qualification evidence only.",
    }

    record["record_identity_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    out = os.path.join(_HERE, "MR002_Phase3C_ExecutableIdentityAndQualification_v1.0.json")
    with open(out, "wb") as fh:
        fh.write(_canonical(record))
    print(json.dumps({
        "identity": record["record_identity_sha256"],
        "phase3c_code_identity": record["executable_identity"]["phase3c_code_identity_sha256"],
        "tests_passed": passed,
        "tests_failed": failed,
    }, indent=1))


if __name__ == "__main__":
    main()
