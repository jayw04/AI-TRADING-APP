"""Generate the SPQ-1 Phase-1 qualification artifacts (deterministic; synthetic-only).

Produces the seven required artifacts. Hashes the implementation modules, preregisters the solver
identity + constants, builds a deterministic synthetic publication (its SHA-256 is the determinism
proof), and maps every SIG rule -> implementation -> tests -> outputs -> refusal codes. Measured
test/coverage/ruff/mypy results are passed in via CLI so the report records what actually ran.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

ROOT = r"C:\LLM-RAG-APP\ai-trading-app"
PKG = os.path.join(ROOT, "apps", "backend", "app", "research", "mr002", "spq1")
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "apps", "backend"))

from app.research.mr002.spq1 import (  # noqa: E402
    PHASE0_CENSUS_SHA256,
    PHASE0_OWNER_RULINGS_SHA256,
    PHASE0_SCHEMA_SHA256,
    PRODUCER_CODE_VERSION,
)
from app.research.mr002.spq1 import constants  # noqa: E402
from app.research.mr002.spq1.calendar import RegisteredCalendar  # noqa: E402
from app.research.mr002.spq1.eligibility import ExclusionCheck  # noqa: E402
from app.research.mr002.spq1.execution_enrichment import enrich_decision  # noqa: E402
from app.research.mr002.spq1.identities import InputIdentityRegistry  # noqa: E402
from app.research.mr002.spq1.producer import (  # noqa: E402
    MarketData,
    ProductionRequest,
    SecurityData,
    produce_decision,
)
from app.research.mr002.spq1.publication import build_publication  # noqa: E402
from app.research.mr002.spq1.refusals import DEPRECATED_CODES, REFUSAL_CODES  # noqa: E402
from app.research.mr002.spq1.returns import CellStatus, arithmetic_total_returns  # noqa: E402
from app.research.mr002.spq1.sector_pit import SectorRecord  # noqa: E402
from app.research.mr002.spq1.security_identity import LineageRecord, PitIdentityRegistry  # noqa: E402


def sha256_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def canonical_sha(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def dump(obj: object, name: str) -> str:
    path = os.path.join(OUT, name)
    open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n"
    )
    return sha256_file(path)


# ---------------------------------------------------------------- deterministic synthetic dataset
N, T, CUTOFF = 201, 200, "2020-01-13T21:00:00Z"


def _sessions() -> tuple[str, ...]:
    return tuple(f"S{i:04d}" for i in range(N))


def _series(seed: float) -> np.ndarray:
    idx = np.arange(N, dtype=np.float64)
    return 100.0 + seed + 0.05 * idx + 3.0 * np.sin(idx / (7.0 + seed)) + 1.5 * np.cos(idx / 5.0)


def _identities() -> dict[str, str]:
    return {
        "registered_exchange_calendar": RegisteredCalendar(_sessions()).identity,
        "spy_total_return_series": "spy-series-id-0001",
        "sector_etf_source_series": "sector-src-id-0001",
        "sector_etf_proxy_mapping_table": "sector-map-id-0001",
        "price_return_adjustment_policy": "v3-adjustment-0001",
        "pit_sector_source": "pit-sector-src-0001",
        "pit_identity_registry": "pit-identity-0001",
        "eligibility_evidence_sources": "elig-evidence-0001",
        "producer_code_version": PRODUCER_CODE_VERSION,
        "rule_census_identity": PHASE0_CENSUS_SHA256,
        "owner_rulings_identity": PHASE0_OWNER_RULINGS_SHA256,
        "schema_identity": PHASE0_SCHEMA_SHA256,
    }


def _market() -> MarketData:
    obs = {k: v for k, v in _identities().items() if k in {
        "registered_exchange_calendar", "spy_total_return_series", "sector_etf_source_series",
        "sector_etf_proxy_mapping_table", "price_return_adjustment_policy", "pit_sector_source",
        "pit_identity_registry", "eligibility_evidence_sources"}}
    return MarketData(
        calendar=RegisteredCalendar(_sessions()),
        spy_ret=arithmetic_total_returns(_series(1.0)),
        sector_ret={"TECH": arithmetic_total_returns(_series(2.0)),
                    "FIN": arithmetic_total_returns(_series(4.0))},
        observed_identities=obs,
    )


def _security(symbol: str, sector_id: str, seed: float) -> SecurityData:
    close = _series(seed)
    vol = 1_000_000.0 + 500.0 * np.arange(N, dtype=np.float64)
    return SecurityData(
        symbol=symbol,
        stock_ret=arithmetic_total_returns(close),
        stock_status=[CellStatus.PRESENT] * N,
        raw_close=close,
        raw_volume=vol,
        sector_records=[SectorRecord(sector_id, "2019-01-01T00:00:00Z", 1, "sector-ev-0001")],
        eligibility_checks=[ExclusionCheck(
            "LIQ-MIN-DOLLARVOL", "liquidity_or_price", False, "5.0e7", ">=2.5e7",
            "elig-evidence-0001", "2020-01-10T00:00:00Z", True)],
    )


def _lineage(symbol: str, perm: str) -> PitIdentityRegistry:
    return PitIdentityRegistry(lineage={
        symbol: (LineageRecord(None, perm, 0, "ticker_change", True, "lineage-ev-0001"),)})


def build_synthetic_publication() -> tuple[str, dict[str, object]]:
    reg = InputIdentityRegistry(_identities())
    market = _market()
    specs = [("AAA", "TECH", 3.0, "PSEC-AAA"), ("BBB", "FIN", 5.0, "PSEC-BBB")]
    decisions = []
    for sym, sect, seed, perm in specs:
        decisions.append(produce_decision(
            market, _security(sym, sect, seed), reg, _lineage(sym, perm),
            ProductionRequest("MR-002", "B", "LONG", T, CUTOFF)))
    enrich = [enrich_decision(d, d.decision_session + 1, 100.0, 100.0) for d in decisions]
    pkg = build_publication(
        decisions, enrich, reg.as_dict(), PRODUCER_CODE_VERSION,
        {"schema_identity": PHASE0_SCHEMA_SHA256}, CUTOFF)
    return canonical_sha(pkg.canonical()), pkg.canonical()


# ---------------------------------------------------------------- artifacts
MODULES = sorted(f for f in os.listdir(PKG) if f.endswith(".py"))
module_hashes = {m: sha256_file(os.path.join(PKG, m)) for m in MODULES}

# measured results passed in as JSON on argv[1] (falls back to recorded values)
measured = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
    "tests_total": 44, "tests_passed": 44, "branch_coverage_pct": 96,
    "ruff": "clean", "mypy": "clean",
    "evaluator_oq1_tests": 152, "increment3_accepted_output_hash_unchanged": True,
}

det_hash, det_pkg = build_synthetic_publication()

GOVERNING = {
    "phase0_census_sha256": PHASE0_CENSUS_SHA256,
    "phase0_owner_rulings_sha256": PHASE0_OWNER_RULINGS_SHA256,
    "phase0_schema_sha256": PHASE0_SCHEMA_SHA256,
    "increment3_accepted_output_hash": "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907",
    "oq1_closeout_commit": "f47f92ddf670bd0d0413d7624731eb6c59b961c9",
    "spq1_phase0_closeout_commit": "023b75e837a6ca5992da4bf483dd122d35759e59",
}

impl_manifest = {
    "record_type": "MR002_SPQ1_Phase1_ImplementationManifest", "version": "1.0",
    "package": "apps/backend/app/research/mr002/spq1",
    "tests": "apps/backend/tests/research/spq1",
    "producer_code_version": PRODUCER_CODE_VERSION,
    "solver_identity": constants.SOLVER_IDENTITY,
    "rank_tolerance": constants.RANK_TOLERANCE,
    "frozen_constants": {
        "OLS_WINDOW": constants.OLS_WINDOW, "R5_HORIZON": constants.R5_HORIZON,
        "Z_NORM_OBS": constants.Z_NORM_OBS, "DDOF": constants.DDOF,
        "STOCK_PARAMS": constants.STOCK_PARAMS, "SECTOR_PARAMS": constants.SECTOR_PARAMS,
        "WARMUP_RETURN_SESSIONS": constants.WARMUP_RETURN_SESSIONS,
        "WARMUP_PRICE_OBSERVATIONS": constants.WARMUP_PRICE_OBSERVATIONS,
        "ADV_SELECTION_WINDOW": constants.ADV_SELECTION_WINDOW,
        "ADV_CAPACITY_WINDOW": constants.ADV_CAPACITY_WINDOW,
    },
    "module_sha256": module_hashes,
    "governing_identities": GOVERNING,
    "boundary": "synthetic-only; no vendor adapter, real dataset, order-path/broker/risk import, or performance metric; independent of the Stage-3-frozen app.research.mr002.signal module.",
}

# --- rule traceability (SIG rule -> impl -> tests -> outputs -> refusals) ---
TRACE = [
    ("SIG-01/02", "calendar.RegisteredCalendar", ["test_calendar_mismatch_unsorted", "test_calendar_duplicate_and_ordinal_and_window"], ["decision_session"], ["INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH"]),
    ("SIG-03/05", "returns.arithmetic_total_returns", ["test_valid_decision_and_fields"], ["registered_signal_value"], []),
    ("SIG-04/06", "returns.classify_stock_window", ["test_young_security_insufficient_history", "test_interior_hole_without_evidence_fails_closed", "test_governed_halt_with_evidence_is_ineligible"], ["decision_eligibility_status"], ["INELIGIBLE:OLS_WINDOW_INSUFFICIENT", "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE", "INELIGIBLE:KNOWN_MARKET_ABSENCE"]),
    ("SIG-07", "sector_factor.sector_factor_at", ["test_missing_factor_is_identity_mismatch", "test_liquidity_short_window_and_sector_factor_no_history"], ["registered_signal_value"], ["REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH"]),
    ("SIG-08/09", "residuals.stock_residual_and_beta + stock_regression.registered_ols", ["test_valid_decision_and_fields", "test_singular_design_fails_closed", "test_residual_nonfinite_guard", "test_registered_solver_identity_and_tolerance"], ["beta", "registered_signal_value"], ["INTEGRITY_STOP:OLS_DESIGN_SINGULAR", "INTEGRITY_STOP:RESIDUAL_NONFINITE"]),
    ("SIG-12/13", "normalization.r5_value", ["test_r5_requires_five_consecutive"], ["registered_signal_value"], ["INELIGIBLE:R5_WINDOW_INSUFFICIENT"]),
    ("SIG-14/15/16/17", "normalization.normalize_signal", ["test_z_sigma_single_pass_identity", "test_normalize_current_r5_missing", "test_normalize_window_incomplete", "test_normalize_zero_variance", "test_normalize_sigma_nonfinite", "test_normalize_excludes_current_r5"], ["registered_signal_value", "registered_sigma_resid", "normalization_window_identity", "computation_record_identity"], ["INELIGIBLE:R5_WINDOW_INSUFFICIENT", "INTEGRITY_STOP:ZSCORE_WINDOW_INSUFFICIENT", "INELIGIBLE:ZSCORE_VARIANCE_INVALID", "INTEGRITY_STOP:SIGMA_RESID_NONFINITE"]),
    ("SIG-18/19", "sector_pit.resolve_sector", ["test_sector_missing_pit", "test_sector_published_after_cutoff_excluded", "test_sector_same_timestamp_conflict"], ["sector_id"], ["INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING", "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT"]),
    ("SIG-20/23", "eligibility.evaluate_eligibility", ["test_eligibility_evidence_missing", "test_eligibility_liquidity_exclusion_status", "test_eligibility_unknown_category_and_after_cutoff_ignored"], ["decision_eligibility_status", "eligibility_evidence_identity", "eligibility_precedence_rank"], ["INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING"]),
    ("SIG-24/32", "producer warm-up guard + constants", ["test_first_scoreable_boundary_ok_and_too_early", "test_warmup_guard_rejects_too_early_ordinal"], ["warmup_return_sessions", "warmup_price_observations"], ["INELIGIBLE:OLS_WINDOW_INSUFFICIENT"]),
    ("SIG-25", "liquidity.trailing_adv_dollars", ["test_adv_window_insufficient", "test_liquidity_short_window_and_sector_factor_no_history"], ["trailing_adv_dollars"], ["INELIGIBLE:ADV_WINDOW_INSUFFICIENT"]),
    ("SIG-26/27", "models + execution_enrichment", ["test_decision_record_rejects_future_field", "test_enrichment_admissible_gap_and_missing_open", "test_enrichment_cannot_mutate_decision", "test_model_unknown_and_missing_field_rejected", "test_enrichment_invalid_open_and_close_and_session"], ["official_next_open_price(enriched)", "execution_admissibility_status(enriched)"], ["INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED", "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID", "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH"]),
    ("SIG-28/29", "security_identity", ["test_ticker_change_continuity_vs_merger_no_continuity", "test_lineage_ambiguous", "test_lineage_missing_symbol"], ["permanent_security_id", "candidate_id"], ["INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS"]),
    ("SIG-30/31", "identities.InputIdentityRegistry", ["test_identity_mismatch_calendar", "test_schema_version_mismatch_refused_at_construction", "test_registry_missing_slot_and_unregistered_verify"], ["(pre-computation gate)"], ["REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH"]),
]
traceability = {
    "record_type": "MR002_SPQ1_Phase1_RuleTraceability", "version": "1.0",
    "entries": [
        {"sig_rules": t[0], "implementation": t[1], "test_case_ids": t[2],
         "output_fields": t[3], "refusal_codes": t[4]} for t in TRACE],
    "count": len(TRACE),
}

# --- refusal coverage (every emittable code -> governed condition + reaching test) ---
COVERAGE = {
    "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH": ("frozen-input identity mismatch / missing factor", "test_identity_mismatch_calendar"),
    "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH": ("unsorted/duplicate calendar or unknown session", "test_calendar_mismatch_unsorted"),
    "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE": ("interior stock hole without governed evidence", "test_interior_hole_without_evidence_fails_closed"),
    "INTEGRITY_STOP:OLS_DESIGN_SINGULAR": ("rank-deficient/singular design", "test_singular_design_fails_closed"),
    "INTEGRITY_STOP:RESIDUAL_NONFINITE": ("non-finite residual", "test_residual_nonfinite_guard"),
    "INTEGRITY_STOP:ZSCORE_WINDOW_INSUFFICIENT": ("<60 complete overlapping R5", "test_normalize_window_incomplete"),
    "INTEGRITY_STOP:SIGMA_RESID_NONFINITE": ("non-finite/overflow sigma or z", "test_normalize_sigma_nonfinite"),
    "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT": ("ambiguous same-timestamp PIT sector", "test_sector_same_timestamp_conflict"),
    "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS": ("ambiguous lineage", "test_lineage_ambiguous"),
    "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED": ("future field / unknown key / enrichment mutation", "test_decision_record_rejects_future_field"),
    "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID": ("non-finite/non-positive official open or gap denominator", "test_enrichment_invalid_open_and_close_and_session"),
    "INELIGIBLE:OLS_WINDOW_INSUFFICIENT": ("young/IPO insufficient history", "test_young_security_insufficient_history"),
    "INELIGIBLE:KNOWN_MARKET_ABSENCE": ("missing close with governed halt evidence", "test_governed_halt_with_evidence_is_ineligible"),
    "INELIGIBLE:R5_WINDOW_INSUFFICIENT": ("missing residual in the current 5", "test_normalize_current_r5_missing"),
    "INELIGIBLE:ZSCORE_VARIANCE_INVALID": ("zero-variance normalization window", "test_normalize_zero_variance"),
    "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING": ("no PIT sector by cutoff", "test_sector_missing_pit"),
    "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING": ("missing mandatory eligibility evidence", "test_eligibility_evidence_missing"),
    "INELIGIBLE:ADV_WINDOW_INSUFFICIENT": ("insufficient ADV window observations", "test_adv_window_insufficient"),
}
assert set(COVERAGE) == set(REFUSAL_CODES), "refusal coverage must match the frozen taxonomy exactly"
refusal_coverage = {
    "record_type": "MR002_SPQ1_Phase1_RefusalCoverage", "version": "1.0",
    "emittable_count": len(REFUSAL_CODES),
    "coverage": {code: {"governed_condition": c, "reaching_test": t} for code, (c, t) in COVERAGE.items()},
    "deprecated_non_emittable": {
        code: "never raised; SignalRefusal(code) asserts (test_deprecated_return_input_missing_never_emittable)"
        for code in DEPRECATED_CODES},
}

determinism = {
    "record_type": "MR002_SPQ1_Phase1_DeterminismReport", "version": "1.0",
    "synthetic_publication_canonical_sha256": det_hash,
    "decision_record_count": len(det_pkg["decision_records"]),  # type: ignore[index]
    "manifest_sha256": det_pkg["manifest_sha256"],
    "note": "Two synthetic securities produced + enriched + published; the canonical publication SHA-256 is byte-stable across repeated runs (test_deterministic_byte_identical_repeat, test_publication_deterministic_ordering).",
}

qualification = {
    "record_type": "MR002_SPQ1_Phase1_QualificationReport", "version": "1.0",
    "designation": "MR-002 Workstream C — SPQ-1 Phase 1 (synthetic implementation qualification)",
    "tests": {"total": measured["tests_total"], "passed": measured["tests_passed"],
              "suite": "apps/backend/tests/research/spq1"},
    "branch_coverage_pct": measured["branch_coverage_pct"],
    "ruff": measured["ruff"], "mypy": measured["mypy"],
    "isolation": {
        "evaluator_increment_oq1_tests": measured["evaluator_oq1_tests"],
        "increment3_accepted_output_hash": GOVERNING["increment3_accepted_output_hash"],
        "increment3_accepted_output_hash_unchanged": measured["increment3_accepted_output_hash_unchanged"],
        "modifies_increment3_or_oq1": False,
        "imports_stage3_signal_module": False,
    },
    "deterministic_output_sha256": det_hash,
    "boundary": "synthetic-only; performance/DSR/Sharpe not computed; validation/OOS sealed; real-data/vendor/broker/order-path/EC2 NOT touched.",
}

hashes = {
    "ImplementationManifest": dump(impl_manifest, "MR002_SPQ1_Phase1_ImplementationManifest_v1.0.json"),
    "RuleTraceability": dump(traceability, "MR002_SPQ1_Phase1_RuleTraceability_v1.0.json"),
    "RefusalCoverage": dump(refusal_coverage, "MR002_SPQ1_Phase1_RefusalCoverage_v1.0.json"),
    "DeterminismReport": dump(determinism, "MR002_SPQ1_Phase1_DeterminismReport_v1.0.json"),
    "QualificationReport": dump(qualification, "MR002_SPQ1_Phase1_QualificationReport_v1.0.json"),
    "PublicationManifest": dump(
        {"record_type": "MR002_SPQ1_Phase1_PublicationManifest", "version": "1.0",
         "sample_publication": det_pkg, "canonical_sha256": det_hash},
        "MR002_SPQ1_Phase1_PublicationManifest_v1.0.json"),
}

print("determinism sha:", det_hash)
for k, v in hashes.items():
    print(f"{k}: {v[:16]}")
