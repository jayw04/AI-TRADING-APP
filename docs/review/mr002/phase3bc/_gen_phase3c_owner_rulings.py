"""SPQ-1 Phase 3C — owner rulings 2026-08-18, and the ExecutionGateTable correction they require.

Emits three artifacts:

  1. MR002_Phase3C_OwnerRulings_v1.0.json          — the four rulings + authorized scope + boundary
  2. MR002_Phase3BC_ExecutionGateTable_v1.1.json   — corrected: the 0.70 Sharpe gate is OOS-stage
  3. MR002_Phase3BC_ExecutionGateTableCorrection_v1.0.json — the defect, the diff, the affirmations

Nothing here computes, reads, or inspects any economic result. These are authority closures taken
BEFORE any validation P&L exists, which is the only order in which they can be taken honestly.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
GATE_V10 = os.path.join(_HERE, "MR002_Phase3BC_ExecutionGateTable_v1.0.json")
JOINT_MODULE = os.path.join(REPO, "apps", "backend", "app", "research", "mr002", "joint_portfolio.py")
V11_DOC = os.path.join(
    REPO, "docs", "implementation", "TradingWorkbench_MR002_PreRegistration_v1.1_REFREEZE_CANDIDATE.md")

# ---------------------------------------------------------------- 1. owner rulings

RULINGS = {
    "record_type": "MR002_Phase3C_OwnerRulings",
    "version": "1.0",
    "artifact_kind": "OWNER_RULINGS",
    "produced_at": "2026-08-18T00:00:00Z",
    "authorized_by": "owner rulings 2026-08-18, verbatim in substance",
    "occasion": (
        "the bounded economic-verdict authority census established that the frozen economics are "
        "fully specified, that the Sharpe>=0.70 / bootstrap / DSR / cost-stress gates are "
        "sealed-OOS gates prohibited during validation, and that four blockers required an owner "
        "decision before any implementation."
    ),
    "affirmations": {
        "validation_bytes_read": False,
        "oos_bytes_read": False,
        "validation_pnl_inspected_before_these_rulings": False,
        "performance_computed": False,
        "economic_rule_changed": False,
        "gate_threshold_changed": False,
        "window_or_seam_or_fold_changed": False,
        "dsr_trial_count_changed": False,
        "access_restriction_changed": False,
        "sealed_opening_granted": False,
    },
    "ruling_1_exit_confirmation_3p5sigma": {
        "id": "EXIT_CONFIRMATION_3P5SIGMA",
        "disposition": "RETIRED / NOT EXECUTABLE",
        "reason": (
            "the frozen specification omitted the market/sector sigma estimator required to "
            "determine the confirmation condition"
        ),
        "frozen_text": (
            "PreRegistration v0.4 exit ladder: 'residual beyond +/-3.5 with market/sector "
            "confirmation (>= 1 sigma same-direction move in SPY or the sector ETF)'. The "
            "qualitative condition is stated; the sigma estimation window is not."
        ),
        "why_retirement_and_not_a_parameter_choice": (
            "choosing 20, 60, 126 sessions - or borrowing any other volatility estimator - would "
            "be a post-freeze parameter decision that can alter exits and therefore P&L. "
            "Retirement is preferable to manufacturing a parameter whose profitability "
            "implications cannot be justified."
        ),
        "binding_consequences": [
            "do NOT substitute another confirmation definition",
            "do NOT treat confirm=False as if it were a functioning implementation",
            "REMOVE this branch from the validation replay explicitly, rather than silently "
            "leaving it permanently false",
            "PRESERVE the remaining exit ladder and its ordering exactly",
        ],
        "observed_defect": {
            "always_false": (
                "app/research/mr002/dataset.py:261 initialises `confirm` as an empty dict and "
                "never populates it; :309 passes it through; runner.py:155 reads "
                "`inp.confirm.get(p.permaticker, False)`, so the branch can never fire"
            ),
            "trigger_site": "app/research/mr002/execution.py:132-133 (STOP_Z = 3.5)",
            "not_a_wider_gap": (
                "blackout and corporate-action exits ARE populated (dataset.py:300-304). This "
                "retirement removes exactly one trigger, not the ladder."
            ),
        },
        "exit_ladder_after_retirement": [
            "earnings blackout engages",
            "newly announced prohibited corporate action (exit at next available official open)",
            "|z| back inside +/-0.35",
            "time stop - exit at the open of session 6 (realization horizon 6)",
            "mandatory section-5 reduction",
        ],
        "scope": "this validation program only; the retirement is recorded, not concealed",
    },
    "ruling_2_portfolio_construction": {
        "disposition": "v1.1-rev-3 JOINT CONSTRUCTION ACCEPTED AS GOVERNING",
        "supersedes": "the v1.0 whole-candidate removal cascade",
        "registering_artifact": {
            "path": "docs/implementation/TradingWorkbench_MR002_PreRegistration_v1.1_REFREEZE_CANDIDATE.md",
            "sha256": None,  # bound below from the file itself
            "corroboration": (
                "this sha256 is the same value already cited inside the implementing module's "
                "docstring as the registering artifact, so the code and the document agree "
                "without either being edited"
            ),
        },
        "implementing_module": {
            "path": "apps/backend/app/research/mr002/joint_portfolio.py",
            "sha256": None,  # bound below from the file itself
            "construction_logic_edited": False,
        },
        "reason": (
            "supersession resolves a development-discovered STRUCTURAL INFEASIBILITY - the v1.0 "
            "cascade produced ZERO orders on all 124 development sessions because the ratio "
            "constraints are scale-invariant, so removing a candidate raises every remaining "
            "ratio - and NOT a validation-performance preference. Running the superseded cascade "
            "would answer whether a known-broken construction is profitable, not whether MR-002 is."
        ),
        "nature": (
            "AUTHORITY CLOSURE, not a new optimizer. It supplies the owner signature the v1.1 "
            "artifact was awaiting; it changes no construction logic."
        ),
        "defect_closed": (
            "the v1.1 artifact described itself as countersigned while still reading 'awaiting "
            "the owner's signature and hash'"
        ),
    },
    "ruling_3_configs_A_B_C": {
        "disposition": "A, B and C MUST be produced in the same governed validation replay",
        "why": "both authorized validation gates require them",
        "configurations": {"A": 1.75, "B": 2.00, "C": 2.25},
        "primary": "B = 2.00",
        "not_exploratory": (
            "these are not three exploratory trials; they are the three preregistered "
            "configurations required for ONE frozen validation decision"
        ),
        "parameter_search_authorized": False,
        "required_immutable_outputs": [
            "exact 5-fold assignment",
            "per-fold Config B net return and sign",
            "Config B positive-fold count",
            "cumulative net return for Config A",
            "cumulative net return for Config C",
            "the frozen A/B/C dispersion artifact needed later for OOS DSR",
            "reconciliation of trades, positions, NAV and costs sufficient to reproduce the figures",
        ],
        "must_not_compute": [
            "net_oos_sharpe / the 0.70 gate",
            "the stationary bootstrap gate",
            "DSR significance",
            "cost-stress gates",
        ],
    },
    "ruling_4_replay_integrity": {
        "classification": "RESERVED / NON-INDEPENDENT VERDICT ROLE",
        "no_new_metric": (
            "the frozen material assigns replay_integrity a role but defines no semantics; no "
            "replay_integrity formula, threshold, composite score or new gate may be invented"
        ),
        "what_governs_instead": (
            "ordinary mechanical integrity checks drawn from ALREADY-FROZEN invariants: "
            "accounting balances, deterministic replay, one-position-per-symbol, no pyramiding, "
            "no same-open re-entry, cost reconciliation, NAV reconciliation, fold completeness"
        ),
        "decision_rule": {
            "any_frozen_invariant_fails": "INTEGRITY_FAILURE",
            "all_pass": "the economic gates may be evaluated",
        },
        "residual_condition": (
            "if some higher-authority preregistration explicitly requires replay_integrity to "
            "carry a distinct calculated value, that would remain unresolved. The census found no "
            "such definition."
        ),
    },
    "ruling_5_dividends": {
        "disposition": "DO NOT FIX NOW - record as a limitation",
        "finding": (
            "dividends enter only the signal series and the gap filter; NAV marks on "
            "non-dividend-adjusted official opens and cash earns zero, so holding-period "
            "distributions are structurally omitted - an asymmetric long/short bias"
        ),
        "why_not_now": (
            "the frozen P&L specification says NAV uses non-dividend-adjusted official opens and "
            "does not credit distributions; changing that before validation would alter the "
            "economic model"
        ),
        "required": [
            "record it as a limitation/asymmetry in the validation result",
            "do NOT silently make the long/short book total-return aware",
            "if validation advances, raise it explicitly before OOS authorization unless the "
            "governing OOS specification already resolves it",
        ],
    },
    "authorized_scope_phase_3c": {
        "nature": "THIN real-data wiring of the already-qualified evaluator",
        "may_add_only": (
            "what is necessary to connect: sealed validation inputs -> frozen producer -> A/B/C "
            "candidate selection -> frozen joint construction -> frozen execution/cost/NAV "
            "evaluator -> exact five folds -> validation decision artifact"
        ),
        "the_two_missing_pieces": {
            "fold_assignment": "implement the exact frozen five date ranges mechanically",
            "real_data_wiring": (
                "expose the existing evaluator to the governed validation reader and frozen inputs"
            ),
        },
        "explicitly_not_authorized": [
            "a generic backtester",
            "another platform layer",
            "any parameter search",
            "any OOS-stage gate computation",
            "any new economic or statistical metric",
        ],
    },
    "verdict_domain": {
        "VALIDATION_ADVANCE_REQUEST": (
            "Config B has >= 3 of 5 positive folds AND Config A cumulative net return > 0 AND "
            "Config C cumulative net return > 0, with integrity valid"
        ),
        "VALIDATION_DO_NOT_ADVANCE": (
            "otherwise, unless the frozen rules specifically require VALIDATION_INCONCLUSIVE or "
            "INTEGRITY_FAILURE"
        ),
        "meaning_of_advance": (
            "VALIDATION_ADVANCE_REQUEST authorizes a REQUEST for separate OOS authorization; it "
            "does NOT open OOS, does NOT evaluate any OOS gate, and is NOT a final profitability "
            "claim"
        ),
    },
    "authorization_boundary": {
        "authorized_now": [
            "1. correct the subordinate ExecutionGateTable validation-gate misstatement",
            "2. freeze the +/-3.5 sigma trigger retirement amendment",
            "3. freeze owner acceptance/hash of joint construction v1.1-rev-3",
            "4. implement the thin Phase 3C real-data validation runner (A/B/C, exact five folds, "
            "frozen P&L, validation gates only)",
            "5. qualify it ENTIRELY on non-sealed fixtures first",
            "6. return with the executable identity and qualification evidence",
        ],
        "not_granted": (
            "the sealed validation opening is NOT granted. A new opening must be requested only "
            "after step 6, with the executable identity and qualification evidence in hand."
        ),
        "oos": (
            "only after VALIDATION_ADVANCE_REQUEST would a separate OOS authorization be "
            "considered, where Sharpe >= 0.70, the bootstrap, DSR N=5 and cost-stress finally belong"
        ),
    },
    "grants": (
        "Phase 3C IMPLEMENTATION and non-sealed qualification ONLY. No sealed data access. No "
        "opening."
    ),
}

# ---------------------------------------------------------------- 2. corrected gate table

with open(GATE_V10, "rb") as fh:
    gate_v10_bytes = fh.read()
gate_v10 = json.loads(gate_v10_bytes)
gate_v10_sha = hashlib.sha256(gate_v10_bytes).hexdigest()

gate_v11 = json.loads(gate_v10_bytes)  # independent copy
gate_v11["metric_roles"] = {
    "binding": gate_v10["metric_roles"]["binding"],
    "diagnostics_are_not_gates": gate_v10["metric_roles"]["diagnostics_are_not_gates"],
    "primary_validation_gates": (
        "TWO, and only these: (1) Config B net-positive in >= 3 of 5 folds "
        "[gates_frozen.validation_positive_folds_min_of_5, positive_folds_sample = 'validation, "
        "config B']; (2) Configs A and C each cumulative net return > 0 "
        "[gates_frozen.parameter_stability, stability_sample = 'validation']."
    ),
    "primary_oos_gate": (
        "Config B net Sharpe >= 0.70 together with the one-sided 95% bootstrap lower bound of "
        "daily mean net return > 0. Both are OOS-stage: prereg v1.0.4 keys them under "
        "'oos_pass_requires_BOTH' with sharpe_sample and bootstrap_sample = 'sealed OOS'. They "
        "are PROHIBITED as validation-stage decision metrics."
    ),
    "stage_separation": gate_v10["metric_roles"]["stage_separation"],
    "correction_note": (
        "v1.0 named the OOS Sharpe gate 'primary_validation_gate'. That contradicted this "
        "record's own stage_separation clause and four superior authorities. See "
        "MR002_Phase3BC_ExecutionGateTableCorrection_v1.0.json."
    ),
}
gate_v11["version"] = "1.1"
gate_v11["supersedes"] = "MR002_Phase3BC_ExecutionGateTable_v1.0.json"
gate_v11["supersession_note"] = (
    "the ONLY change is the metric_roles block: the 0.70 Sharpe gate is restated as OOS-stage and "
    "the two real validation gates are named. Every other key is byte-equal to v1.0."
)

# ---------------------------------------------------------------- 3. correction record

_UNCHANGED = sorted(k for k in gate_v10 if k not in ("metric_roles", "version"))

CORRECTION = {
    "record_type": "MR002_PHASE3BC_EXECUTIONGATETABLE_CORRECTION",
    "version": "1.0",
    "artifact_kind": "SUBORDINATE_RECORD_CORRECTION",
    "produced_at": "2026-08-18T00:00:00Z",
    "record_status": "IMMUTABLE",
    "authorized_by": "owner ruling 2026-08-18 (see MR002_Phase3C_OwnerRulings_v1.0.json)",
    "defect_class": (
        "stage mis-anchoring - an OOS-stage gate transcribed as the validation-stage gate. Same "
        "class as the bootstrap transcription drift corrected at prereg v1.0.4."
    ),
    "explicit_statement": (
        "MR002_Phase3BC_ExecutionGateTable_v1.0.json named 'Config B net Sharpe >= 0.70' as the "
        "primary_validation_gate. Sharpe >= 0.70 is a sealed-OOS gate. Following that line would "
        "have caused an OOS primary gate to be computed on validation data - a preregistration "
        "breach - and would have spent the meaning of the OOS seal."
    ),
    "superior_authorities_contradicted": [
        "MR002_ValidationOOS_Preregistration_v1.0.4.json - sharpe_sample = 'sealed OOS'; the "
        "containing key is literally named 'oos_pass_requires_BOTH'",
        "phase3a/MR002_Phase3A_MetricRoleRegistry_v1.0.json - net_oos_sharpe_ge_0.70 carries "
        "sample_stage = 'OOS'",
        "phase3a/MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json - "
        "net_oos_sharpe_ge_0.70 is listed under oos_only_metrics_prohibited_during_validation",
        "phase3a/ValidationMetricSpecification_v1.0.json - every gate carries an explicit "
        "*_sample binding; sharpe_sample, bootstrap_sample and dsr_sample are all 'sealed OOS'",
    ],
    "self_contradiction": (
        "v1.0 line 'stage_separation' already asserted that OOS primary gates are PROHIBITED as "
        "validation-stage decision metrics, directly contradicting its own primary_validation_gate "
        "line."
    ),
    "why_subordinate": (
        "the record's own 'source' field describes it as derived from a development PLAN and "
        "'governed by preregistration v1.0.4'. A derived operational table cannot override the "
        "preregistration it declares itself governed by."
    ),
    "anticipated_by": (
        "MR002_DevPlan_v1_3_ReviewMemo_v1_0.md warned that section 4.2 reproduces the primary OOS "
        "Sharpe gate and must not be read as the validation gate."
    ),
    "correction": {
        "from": "MR002_Phase3BC_ExecutionGateTable_v1.0.json",
        "from_sha256": gate_v10_sha,
        "to": "MR002_Phase3BC_ExecutionGateTable_v1.1.json",
        "to_sha256": None,  # bound below, after v1.1 is serialized
    },
    "machine_diff_proof": {
        "method": "json.loads both files; compare top-level keys",
        "changed_keys": ["metric_roles", "version"],
        "added_keys": ["supersedes", "supersession_note"],
        "removed_keys": [],
        "invariants_byte_equal": _UNCHANGED,
        "metric_roles_subkeys_unchanged": ["binding", "diagnostics_are_not_gates", "stage_separation"],
        "metric_roles_subkeys_replaced": ["primary_validation_gate -> primary_validation_gates + primary_oos_gate"],
    },
    "affirmations": {
        "gate_threshold_changed": False,
        "window_or_seam_or_fold_changed": False,
        "cost_or_D_decision_changed": False,
        "dsr_trial_count_changed": False,
        "access_restriction_changed": False,
        "economic_rule_changed": False,
        "validation_bytes_read": False,
        "oos_bytes_read": False,
        "performance_computed": False,
    },
    "what_did_not_change": (
        "no gate THRESHOLD moved. 0.70 is still 0.70 and the two validation gates are still the "
        "ones the preregistration always specified. Only the STAGE at which each is evaluated is "
        "restated correctly."
    ),
    "grants": "NOTHING. A correction of a subordinate record.",
}


def main() -> None:
    RULINGS["ruling_2_portfolio_construction"]["registering_artifact"]["sha256"] = _sha_file(V11_DOC)
    RULINGS["ruling_2_portfolio_construction"]["implementing_module"]["sha256"] = _sha_file(JOINT_MODULE)

    gate_v11_bytes = _canonical(gate_v11)
    CORRECTION["correction"]["to_sha256"] = hashlib.sha256(gate_v11_bytes).hexdigest()

    outputs = {}
    for name, rec in (
        ("MR002_Phase3C_OwnerRulings_v1.0.json", RULINGS),
        ("MR002_Phase3BC_ExecutionGateTableCorrection_v1.0.json", CORRECTION),
    ):
        rec["record_identity_sha256"] = hashlib.sha256(_canonical(rec)).hexdigest()
        body = _canonical(rec)
        with open(os.path.join(_HERE, name), "wb") as fh:
            fh.write(body)
        outputs[name] = rec["record_identity_sha256"]

    with open(os.path.join(_HERE, "MR002_Phase3BC_ExecutionGateTable_v1.1.json"), "wb") as fh:
        fh.write(gate_v11_bytes)
    outputs["MR002_Phase3BC_ExecutionGateTable_v1.1.json"] = CORRECTION["correction"]["to_sha256"]

    print(json.dumps(outputs, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
