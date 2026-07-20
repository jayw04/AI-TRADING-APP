"""SPQ-1 Phase-0 census generator (specification only; no signal-production implementation).

Builds the rule census, input/output schema draft, qualification-matrix draft, and open-questions
register for the upstream signal & data-production layer that yields the candidate facts Increment 3
consumes. Binds the governing chain by hash; classifies each rule FROZEN / DERIVED_MECHANIC / OPEN /
CONFLICTING / OUT_OF_SCOPE. Incorporates the four owner-accepted Phase-0 clarifications (beta =
market-beta coefficient; registered_sigma_resid = z-normalization sigma; decision/execution seam;
frozen input identities). No real data; no residual/z/sigma/beta/sector/ADV computation.
"""
import hashlib
import json
import os

ROOT = r"C:\LLM-RAG-APP\ai-trading-app"
OUT = os.path.dirname(os.path.abspath(__file__))

SOURCES = {
    "v0.3_design": ("docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md", "1007db8204ad3dff544483614ed40f5fce1573e4dd61b9f6a1cd79d5902bdc59"),
    "v1.0_FROZEN": ("docs/review/mr002/governing_sources/TradingWorkbench_MR002_PreRegistration_v1.0_FROZEN.md", "70108c11f5817158261d17feccc2f8be0519fdc424745eb97ec0fdfbc8cf25fc"),
    "prereg_v1.0.4": ("docs/review/mr002/MR002_ValidationOOS_Preregistration_v1.0.4.json", "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"),
    "trial_ledger": ("docs/review/mr002/MR002_DSR_TrialLedger_v1.0.json", "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b"),
    "dsr_resolution": ("docs/review/mr002/MR002_DSR_Resolution_v1.0.json", "30b812f179128cbb65593de25ee3039916e928a72a6d5d4de2c8051ff83f90a0"),
    "dsr_dispersion_resolution": ("docs/review/mr002/MR002_DSR_DispersionResolution_v1.0.json", "7a601f5b7bc0bea5045755723d7f9b946b01f7eba0eee9191e0f2074b6fb5627"),
    "portfolio_rule_census": ("docs/review/mr002/MR002_Portfolio_Rule_Census_v1.0.json", "91eec2626c584b0f4dd0b184feae9f1f5dc80e5245a823be72a321b5d5f9417e"),
    "increment3_registry": ("docs/review/mr002/MR002_Increment3_RuleRegistry_v1.0.json", "edb7ff22b5215f815b15e64166111604d2b99da91a545729b6c9796928d3b91a"),
    "phase0_resolution": ("docs/review/mr002/MR002_Increment3_Phase0_Resolution_v1.0.json", "860c8cdeb995fadea21359ede189dad27378ab2c553e5a24122bbbd2d2546740"),
    "increment3_qualification": ("docs/review/mr002/evaluator/MR002_Increment3_Qualification.json", "0c077c38b037c771"),
    "oq1_manifest": ("docs/review/mr002/oq1/evidence/MR002_OQ1_Manifest.json", "7b6eb07d286c172e"),
}
validation = {}
for k, (rel, exp) in SOURCES.items():
    got = hashlib.sha256(open(os.path.join(ROOT, rel), "rb").read()).hexdigest()
    ok = got.startswith(exp)
    validation[k] = {"file": rel, "recomputed_sha256": got, "expected_prefix": exp, "match": ok}
assert all(v["match"] for v in validation.values()), "SOURCE HASH MISMATCH"

V03 = "docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md (sha 1007db82)"


def R(rid, area, econ, quote, status, consequence, source=V03, lines="", conflict=None,
      supersession="A new owner-signed decision superseding v0.3-frozen-into-v1.0 (70108c11)."):
    return {"rule_id": rid, "area": area, "economic_meaning": econ, "governing_quote_or_paraphrase": quote,
            "source_file": source, "source_section_lines": lines,
            "status": status, "implementation_consequence": consequence,
            "conflicting_source": conflict, "supersession_authority": supersession}


rules = [
    # Area 1 — registered session + price identity
    R("SIG-01", "1_session_price_identity", "Registered exchange calendar / session numbering",
      "Governed session index = registered snapshot session dates (AAPL/Sharadar SEP), 3400 sessions; session ordinals not calendar arithmetic (prereg windows_literal.calendar_authority, governed_session_list_sha256 b873421...).",
      "FROZEN", "SPQ-1 binds the registered session index + governed_session_list_sha256; a mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.",
      source="prereg_v1.0.4 (b2a042d4) + v0.3 §2/§4"),
    R("SIG-02", "1_session_price_identity", "Decision cutoff / timing semantics",
      "Signals computed AFTER the close of session t; entry at the t+1 official open; five-session time-stop at open of session 6; close-to-close execution diagnostic only.",
      "FROZEN", "Decision cutoff = close of session t; no post-close-t observation may enter the decision record (SIG-33).", lines="§4"),
    R("SIG-03", "1_session_price_identity", "Registered price-series policy (V3)",
      "Signal returns = total-return-adjusted (splits+dividends); execution prices = split-adjusted, NON-dividend-adjusted open/close; gap filter = split-adjusted economically-adjusted for cash distributions; dollar-volume ranking = raw close x raw volume.",
      "FROZEN", "SPQ-1 uses total-return-adjusted series for the residual model and raw close x raw volume for ADV; adjustment-identity mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§4 V3"),
    R("SIG-04", "1_session_price_identity", "IPO / delisting / suspended-session boundaries",
      "Mid-month universe departures run to normal exit, no new entries; delisting valuation priority order registered; survivorship-freedom mandatory (PIT membership, never a current constituent list).",
      "OPEN", "IPO entry boundary + how suspended/missing sessions inside the 60-session OLS window are counted is NOT fully specified -> owner question OQ-SPQ-01.", lines="§2/§4"),
    # Area 2 — return series for the residual model
    R("SIG-05", "2_return_series", "Residual-model return definition",
      "Rolling 60-session OLS on DAILY ARITHMETIC TOTAL returns; missing observation => ineligible that day; no winsorization.",
      "FROZEN", "SPQ-1 builds daily arithmetic total returns (total-return-adjusted series); any missing return in the window -> ineligible / RETURN_INPUT_MISSING.", lines="§3 Step 2/normalization"),
    R("SIG-06", "2_return_series", "Missing-observation treatment inside the window",
      "Any missing observation => ineligible that day (§3). Whether a missing interior session shortens/【voids】the 60-window is not spelled out.",
      "OPEN", "The exact handling of an interior missing session within the 60-session window (skip vs void vs shift) needs a ruling -> OQ-SPQ-02.", lines="§3"),
    # Area 3 — rolling OLS residual model (+ beta clarification)
    R("SIG-07", "3_ols_residual", "Step-1 orthogonalized sector factor",
      "For each sector ETF, rolling 60-session regression ENDING at t-1: r_Sector,t = a + beta_Sector*r_SPY,t + u_Sector,t; residual u_Sector,t is the sector-specific factor (beta_Sector from t-60..t-1 applied to day t).",
      "FROZEN", "SPQ-1 Step 1 produces u_Sector,t from the frozen sector-ETF series + SPY; both are frozen input identities (SIG-30/31).", lines="§3 Step 1"),
    R("SIG-08", "3_ols_residual", "Step-2 stock residual model",
      "Rolling 60-session OLS on t-60..t-1 (never day t): r_i,t = alpha_i + beta_m,i*r_SPY,t + beta_s,i*u_Sector,t + eps_i,t; day-t residual from t-1 coefficient estimates; intercept included.",
      "FROZEN", "SPQ-1 Step 2 emits eps_i,t (residual) and beta_m,i (SIG-09); window 60 ending t-1; intercept included.", lines="§3 Step 2"),
    R("SIG-09", "3_ols_residual", "Beta = market-beta coefficient (owner clarification)",
      "beta_i = beta-hat_m,i, the MARKET-beta coefficient of the same §3 Step-2 60-session stock regression that produces the residual (§5 beta-limit binds 'beta_i = each stock's §3 beta-hat_m'). Producer = SPQ-1 residual regression; benchmark = SPY; sector regressor = u_Sector; window 60 ending t-1; intercept included.",
      "FROZEN", "beta is a by-product of the residual regression, NOT a separate model. No secondary beta estimation path is authorized.", lines="§3 Step 2 + §5 (line 164)"),
    R("SIG-10", "3_ols_residual", "OLS solver / rank / singular-design handling",
      "§3 does not specify the OLS solver, numerical tolerance, minimum rank/observation requirement, or singular-design handling.",
      "OPEN", "Solver, tolerance, min-rank, and singular-design behavior need a ruling -> OQ-SPQ-03 (OLS_DESIGN_SINGULAR refusal drafted).", lines="§3"),
    R("SIG-11", "3_ols_residual", "Unresolvable sector -> excluded",
      "PIT sector mapping per V2; an unresolvable sector => excluded, never defaulted.",
      "FROZEN", "A stock without a PIT-resolvable sector is INELIGIBLE (SECTOR_PIT_IDENTITY_MISSING); never assigned a default sector.", lines="§3 Step 2"),
    # Area 4 — five-session R5
    R("SIG-12", "4_r5_aggregation", "R5 five-residual sum",
      "R5_i,t = Sum_{k=0..4} eps_i,t-k (the five residuals through day t).",
      "FROZEN", "SPQ-1 sums the 5 consecutive registered-session residuals ending at t; fewer than 5 valid residuals -> ineligible / R5_WINDOW_INSUFFICIENT.", lines="§3 Step 3"),
    R("SIG-13", "4_r5_aggregation", "R5 missing-session / consecutiveness / first-eligible",
      "§3 defines the 5-sum but not the behavior when a residual in the 5-window is missing, nor the first eligible session, nor whether the 5 must be consecutive REGISTERED sessions.",
      "OPEN", "Missing-residual-in-R5 behavior + first-eligible-session + consecutiveness need a ruling -> OQ-SPQ-04.", lines="§3"),
    # Area 5 — z-score
    R("SIG-14", "5_zscore", "Z-score normalization",
      "z_i,t = (R5_i,t - mu_i,t-1)/sigma_i,t-1; mu,sigma from rolling windows ENDING at t-1, exactly 60 complete overlapping five-day observations, ddof=1, no winsorization. Current R5_t is excluded (window ends t-1).",
      "FROZEN", "One deterministic normalization pass yields mu_i,t-1, sigma_i,t-1, z_i,t; zero-variance/non-finite -> ZSCORE_VARIANCE_INVALID.", lines="§3 Step 3"),
    R("SIG-15", "5_zscore", "registered_signal_value output identity",
      "registered_signal_value = z_i,t exactly (no clipping/flooring/winsorization/rank transform).",
      "FROZEN", "SPQ-1 emits registered_signal_value = z_i,t; downstream Z_entry threshold + |z| ordering consume it (Increment-3 accepted, unchanged).", lines="§3 Step 3 + Increment-3 registry (edb7ff22)"),
    # Area 6 — sigma_resid (owner clarification)
    R("SIG-16", "6_sigma_resid", "registered_sigma_resid identity (owner clarification)",
      "registered_sigma_resid = sigma_i,t-1 = sample std (ddof=1) of the 60 complete overlapping R5 observations ending at t-1 = the z-normalization denominator. Current R5 excluded.",
      "FROZEN", "SPQ-1 emits registered_sigma_resid = sigma_i,t-1 from the SAME normalization pass as z (SIG-14). Strictly positive + finite; no floor/imputation -> SIGMA_RESID_INVALID.", lines="§3 Step 3 + RC-1 (860c8cde)"),
    R("SIG-17", "6_sigma_resid", "Z / sigma single-pass consistency (owner requirement)",
      "registered_signal_value (z) and registered_sigma_resid (sigma) MUST derive from one deterministic normalization pass sharing the same mu/sigma window identity.",
      "DERIVED_MECHANIC", "Qualification must prove z and sigma_resid share the same normalization-window identity + computation record; the 1/sigma_resid weighting Increment 3 uses is exactly z's denominator.", source="phase0 clarification (owner 2026-07-20)"),
    # Area 7 — PIT sector
    R("SIG-18", "7_pit_sector", "Sector taxonomy source",
      "Accept only (1) a genuine PIT sector/industry history OR (2) historically-effective SIC/NAICS via a FROZEN mapping table whose hash ships in the evidence package; no present-day backfill; survivorship-free.",
      "FROZEN", "SPQ-1 binds the frozen sector-mapping-table hash; sector_id must be PIT + evidence-bound; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§2 V2"),
    R("SIG-19", "7_pit_sector", "PIT effective-date / availability / succession mechanics",
      "§2/V2 requires PIT + a frozen mapping table but does NOT specify the effective-date rule, filing/publication availability timestamp, same-day multiple-record handling, predecessor/security succession, or symbol changes.",
      "OPEN", "Effective-date + availability-timestamp + same-day-conflict + succession mechanics need rulings -> OQ-SPQ-05 (SECTOR_EFFECTIVE_DATE_CONFLICT / SECTOR_PIT_IDENTITY_MISSING drafted).", lines="§2 V2"),
    # Area 9 — eligibility
    R("SIG-20", "9_eligibility", "Entry eligibility conditions",
      "Long entry (all at close t): z<=-Z_entry AND bottom 10% of long-eligible pool AND earnings-clearance AND no announced merger/split/delisting/major corporate action AND gap filter passes AND liquidity envelope. Short mirrors.",
      "FROZEN", "SPQ-1 emits eligibility_status in {ELIGIBLE, INELIGIBLE} summarizing these; Increment 3 consumes, never recomputes.", lines="§4"),
    R("SIG-21", "9_eligibility", "Earnings-clearance rule (V1)",
      "Do not open a position when a PIT-known earnings announcement falls between the t+1 open and the max exit (open of session 6); revised-timestamp availability only; BMO/AMC conservative if indistinguishable.",
      "FROZEN", "SPQ-1 marks INELIGIBLE on earnings-window overlap; requires PIT earnings-calendar availability timestamps (input identity).", lines="§4 V1"),
    R("SIG-22", "9_eligibility", "Gap filter (execution-time)",
      "Entry order cancelled at the t+1 open if |AdjOpen_t+1 / AdjClose_t - 1| >= 6% (distribution-adjusted).",
      "FROZEN", "The gap filter is an EXECUTION-time (t+1) test -> it belongs to the enrichment step, NOT the decision record (SIG-33); it uses the t+1 open, unknown at decision cutoff.", lines="§4"),
    R("SIG-23", "9_eligibility", "Eligibility availability-timestamps / precedence / evidence identity",
      "Every exclusion needs an exact PIT rule + availability timestamp + lookback/exclusion window + precedence + refusal-vs-INELIGIBLE + evidence identity. §4 gives the rules but not all timing/precedence mechanics.",
      "OPEN", "Per-exclusion availability timestamp, precedence, evidence identity, and refusal-vs-INELIGIBLE mapping need rulings -> OQ-SPQ-06 (ELIGIBILITY_EVIDENCE_MISSING drafted).", lines="§4"),
    R("SIG-24", "9_eligibility", "Delisting / bankruptcy / halt / min-history / security-type / exchange",
      "§2/§4 touch delisting valuation + survivorship but do not fully census min-trading-history, security-type, exchange-eligibility, bankruptcy/halt status as PIT eligibility rules.",
      "OPEN", "These eligibility dimensions need explicit PIT rules + evidence identities -> OQ-SPQ-07.", lines="§2/§4"),
    # Area 10 — ADV + official-open + seam
    R("SIG-25", "10_adv_open", "Dollar-volume / ADV basis",
      "Dollar-volume ranking = raw close x raw volume (consistent unadjusted pair). ADV lookback length, lag, min observations, and the exact ADV-dollar formula are NOT specified in §3/§4.",
      "OPEN", "ADV formula + lookback + lag + min-obs need a ruling -> OQ-SPQ-08 (ADV_WINDOW_INSUFFICIENT drafted). Raw close x raw volume is FROZEN as the pair.", lines="§4"),
    R("SIG-26", "10_adv_open", "Official next-open identity + missing-open",
      "Entries without a valid official opening price are cancelled; exits without one remain pending until the next available official regular-session open. Official open = split-adjusted non-dividend-adjusted t+1 regular-session open.",
      "FROZEN", "The official next-open is a session-(t+1) fact; the producer may register a missing future open ONLY at the execution session, never at the decision timestamp.", lines="§4 halts + V3"),
    R("SIG-27", "10_adv_open", "Decision/execution seam (owner requirement)",
      "SignalDecisionRecord (decision cutoff = close t) must NOT contain official_next_open_price, actual_execution_session, or any post-close-t observation. The t+1 enrichment step appends the official opening-price fact + execution timestamp WITHOUT recomputing decision facts.",
      "DERIVED_MECHANIC", "Two structurally distinct records; the enriched record is the adapter seam into the CLOSED Increment-3 replay contract. Any post-cutoff field/identity in a decision record -> INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED.", source="phase0 clarification (owner 2026-07-20) + Increment-3 (edb7ff22, CLOSED)"),
    # Area 11 — security identity
    R("SIG-28", "11_security_identity", "Permanent security id / lineage",
      "permanent_security_id source, symbol-to-security mapping, ticker changes, share-class, mergers/successors, duplicate listings, ADR/common distinctions are not specified upstream.",
      "OPEN", "The permanent-security-id source + lineage rules need a ruling -> OQ-SPQ-09 (SECURITY_IDENTITY_AMBIGUOUS drafted). Survivorship-free PIT membership is FROZEN (§2).", lines="§2"),
    R("SIG-29", "11_security_identity", "candidate_id vs permanent_security_id",
      "candidate_id is a record identity; the frozen tie-breaks use permanent_security_id (lexical). candidate_id must not silently replace the permanent security identifier.",
      "FROZEN", "SPQ-1 emits both distinctly; the Increment-3 removal/drift tie-breaks bind permanent_security_id.", source="phase0 resolution (860c8cde) + increment3 registry (edb7ff22)"),
    # Frozen input identities
    R("SIG-30", "input_identities", "SPY market-factor series identity",
      "The market factor is the SPY total-return series (Step-1 + Step-2 regressor r_SPY).",
      "FROZEN", "SPY total-return series is a REQUIRED frozen input identity; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§3"),
    R("SIG-31", "input_identities", "Sector-ETF proxy + source-series identity",
      "Sector factors = sector-ETF residuals u_Sector; the sector-ETF proxy mapping + source series must be the FROZEN mapping table whose hash ships in the evidence package.",
      "FROZEN", "Sector-ETF proxy mapping table + source series are REQUIRED frozen input identities; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§2 V2 + §3 Step 1"),
]

refusal_taxonomy = {
    "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH": "any frozen-input identity (SPY / sector-ETF mapping / sector source / session calendar / price-adjustment) mismatch",
    "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH": "session index / numbering diverges from the registered calendar",
    "INELIGIBLE:RETURN_INPUT_MISSING": "a required return observation is missing (ineligible that day)",
    "INTEGRITY_STOP:OLS_WINDOW_INSUFFICIENT": "fewer than the exact 60 registered-session observations available",
    "INTEGRITY_STOP:OLS_DESIGN_SINGULAR": "the OLS design matrix is rank-deficient / singular",
    "INTEGRITY_STOP:RESIDUAL_NONFINITE": "a computed residual is non-finite",
    "INELIGIBLE:R5_WINDOW_INSUFFICIENT": "fewer than 5 valid consecutive residuals for R5",
    "INTEGRITY_STOP:ZSCORE_WINDOW_INSUFFICIENT": "fewer than 60 complete overlapping R5 observations for mu/sigma",
    "INTEGRITY_STOP:ZSCORE_VARIANCE_INVALID": "sigma_i,t-1 is zero or non-finite (z undefined)",
    "INTEGRITY_STOP:SIGMA_RESID_INVALID": "registered_sigma_resid is not strictly positive and finite",
    "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING": "no PIT-resolvable sector for the security at t (never defaulted)",
    "REFUSED_CODE_OR_DATA_IDENTITY:SECTOR_EFFECTIVE_DATE_CONFLICT": "ambiguous / conflicting same-day PIT sector records",
    "INTEGRITY_STOP:BETA_INPUT_INVALID": "beta regression inputs invalid (covered by OLS_DESIGN_SINGULAR when the same regression)",
    "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING": "a required eligibility evidence identity / availability timestamp is missing",
    "INELIGIBLE:ADV_WINDOW_INSUFFICIENT": "insufficient observations for the registered ADV window",
    "REFUSED_CODE_OR_DATA_IDENTITY:SECURITY_IDENTITY_AMBIGUOUS": "ambiguous permanent-security-id / lineage resolution",
    "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED": "any post-decision-cutoff field or identity found in a SignalDecisionRecord",
}

signal_decision_record = {
    "record_type": "MR002_SPQ1_SignalDecisionRecord (draft)",
    "cutoff": "close of session t (all fields use information through close-t only)",
    "required_fields": ["permanent_security_id", "decision_session (=t)", "signal_origin_session",
                        "symbol", "side", "registered_signal_value (=z_i,t)", "registered_sigma_resid (=sigma_i,t-1)",
                        "sector_id (PIT)", "beta (=beta_m,i)", "eligibility_status (ELIGIBLE|INELIGIBLE)",
                        "eligibility_evidence_identity", "configuration_id (A|B|C, downstream Z_entry only)",
                        "trailing_adv_dollars (decision-time ADV)", "normalization_window_identity",
                        "computation_record_identity"],
    "structurally_forbidden_fields": ["official_next_open_price", "actual_execution_session",
                                     "any post-close-t observation"],
    "forbidden_field_disposition": "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
}
execution_enriched_record = {
    "record_type": "MR002_SPQ1_ExecutionEnrichedCandidateRecord (draft)",
    "timing": "session t+1 (execution) — appends execution facts WITHOUT recomputing decision facts",
    "adds": ["official_next_open_price (t+1 official open)", "scheduled_execution_session (=t+1)",
             "gap_filter_result (|AdjOpen_t+1/AdjClose_t-1| >= 6% -> cancel)", "missing_open_disposition"],
    "carries_unchanged": "the full SignalDecisionRecord (byte-preserved)",
    "seam": "this is the adapter into the CLOSED Increment-3 accepted replay candidate contract (edb7ff22); Increment 3 is NOT reopened.",
}

qualification_matrix = [
    ("SPQM-01", "exact 60-session OLS boundary passes", "SIG-08", "PASS"),
    ("SPQM-02", "59-session window refuses (OLS_WINDOW_INSUFFICIENT)", "SIG-08", "INTEGRITY_STOP"),
    ("SPQM-03", "decision-session lagging: coefficients from t-60..t-1, residual at t", "SIG-08", "PASS"),
    ("SPQM-04", "future-price leakage rejected (next-open in decision record)", "SIG-27", "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED"),
    ("SPQM-05", "singular OLS design refuses", "SIG-10", "INTEGRITY_STOP:OLS_DESIGN_SINGULAR"),
    ("SPQM-06", "missing factor (SPY/sector) return refuses", "SIG-05/07", "INELIGIBLE:RETURN_INPUT_MISSING"),
    ("SPQM-07", "five-session R5 endpoints (t..t-4)", "SIG-12", "PASS"),
    ("SPQM-08", "R5 across calendar gaps (registered consecutive)", "SIG-13", "OPEN-RULING"),
    ("SPQM-09", "z-score first eligible session", "SIG-14", "OPEN-RULING"),
    ("SPQM-10", "zero z-score variance refuses", "SIG-14", "INTEGRITY_STOP:ZSCORE_VARIANCE_INVALID"),
    ("SPQM-11", "sigma_resid first eligible session", "SIG-16", "OPEN-RULING"),
    ("SPQM-12", "zero/non-finite sigma refuses", "SIG-16", "INTEGRITY_STOP:SIGMA_RESID_INVALID"),
    ("SPQM-13", "z and sigma_resid share one normalization-window identity", "SIG-17", "PASS"),
    ("SPQM-14", "PIT sector effective-date change respected", "SIG-19", "OPEN-RULING"),
    ("SPQM-15", "same-day sector conflict refuses", "SIG-19", "REFUSED:SECTOR_EFFECTIVE_DATE_CONFLICT"),
    ("SPQM-16", "missing PIT sector -> INELIGIBLE", "SIG-11", "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING"),
    ("SPQM-17", "security-symbol change handled by permanent id", "SIG-28", "OPEN-RULING"),
    ("SPQM-18", "permanent-id continuity across lineage", "SIG-28", "OPEN-RULING"),
    ("SPQM-19", "beta first eligible session (= residual regression)", "SIG-09", "PASS"),
    ("SPQM-20", "beta singular/constant benchmark refuses", "SIG-09/10", "INTEGRITY_STOP:OLS_DESIGN_SINGULAR"),
    ("SPQM-21", "earnings-window boundary -> INELIGIBLE", "SIG-21", "INELIGIBLE"),
    ("SPQM-22", "corporate-action exclusion", "SIG-20", "INELIGIBLE"),
    ("SPQM-23", "liquidity/ADV boundary", "SIG-25", "OPEN-RULING"),
    ("SPQM-24", "missing official open (execution step only)", "SIG-26", "cancel/defer at t+1"),
    ("SPQM-25", "candidate provenance completeness (all decision fields present)", "SignalDecisionRecord", "PASS"),
    ("SPQM-26", "A/B/C differ only by Z_entry downstream (no signal-side change)", "SIG-15", "PASS"),
    ("SPQM-27", "deterministic synthetic output (byte-identical)", "all", "PASS"),
    ("SPQM-28", "no real-data import or file access (synthetic-only)", "all", "PASS"),
]

open_questions = [
    {"id": "OQ-SPQ-01", "area": 1, "question": "IPO entry boundary + counting of suspended/missing sessions inside the 60-session OLS window (skip / void / shift)."},
    {"id": "OQ-SPQ-02", "area": 2, "question": "Exact interior-missing-session handling within the 60-session return window."},
    {"id": "OQ-SPQ-03", "area": 3, "question": "OLS solver, numerical tolerance, minimum rank/observation requirement, singular-design handling."},
    {"id": "OQ-SPQ-04", "area": 4, "question": "R5 missing-residual behavior, first eligible session, consecutiveness of registered sessions, <5-valid refusal."},
    {"id": "OQ-SPQ-05", "area": 7, "question": "PIT sector effective-date rule, availability timestamp, same-day multiple-record handling, succession/symbol changes."},
    {"id": "OQ-SPQ-06", "area": 9, "question": "Per-exclusion availability timestamps, precedence order, evidence identity, refusal-vs-INELIGIBLE mapping."},
    {"id": "OQ-SPQ-07", "area": 9, "question": "PIT rules + evidence for min-trading-history, security-type, exchange-eligibility, bankruptcy/halt."},
    {"id": "OQ-SPQ-08", "area": 10, "question": "ADV-dollar formula, lookback length, lag, minimum observations (raw close x raw volume pair is frozen)."},
    {"id": "OQ-SPQ-09", "area": 11, "question": "permanent_security_id source, symbol-to-security mapping, ticker changes, share-class, mergers/successors, duplicates, ADR/common."},
    {"id": "OQ-SPQ-10", "area": 5, "question": "Z-score / sigma first-eligible-session anchoring (needs 60 R5 obs which need 5-day R5 which need residuals which need 60-session OLS): confirm the compounded warm-up length + first scoreable session."},
]


def dump(obj, name):
    open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return hashlib.sha256(open(os.path.join(OUT, name), "rb").read()).hexdigest()


governing = {k: {"file": v["file"], "sha256": v["recomputed_sha256"]} for k, v in validation.items()}
bound = dict(governing)
bound["oq1_closeout_commit"] = "f47f92ddf670bd0d0413d7624731eb6c59b961c9"
bound["increment3_accepted_output_hash"] = "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907"

census = {
    "record_type": "MR002_SPQ1_RULE_CENSUS", "version": "1.0", "date": "2026-07-20",
    "record_status": "IMMUTABLE",
    "designation": "MR-002 Workstream C — Signal & Data-Production Qualification (SPQ-1), Phase 0",
    "purpose": "Implementation-binding specification/census for the upstream layer that PRODUCES the candidate facts Increment 3 consumes. Classifies every signal/candidate-production rule FROZEN / DERIVED_MECHANIC / OPEN / OUT_OF_SCOPE. No implementation; no real data; no residual/z/sigma/beta/sector/ADV computation.",
    "boundary": "Synthetic-only. Phase 0 opens no real/dev/validation/OOS data, imports no vendor adapter, computes no residual/z/beta/ADV/sector/eligibility, runs no metric, tunes no parameter, and never chooses a rule because it produces better results.",
    "owner_accepted_clarifications_2026_07_20": [
        "beta FROZEN = market-beta coefficient beta_m of the §3 Step-2 residual regression (SIG-09)",
        "registered_sigma_resid FROZEN = z-normalization sigma_i,t-1 (SIG-16); z/sigma single-pass consistency REQUIRED (SIG-17)",
        "decision/execution seam REQUIRED: SignalDecisionRecord (no future fields) + ExecutionEnrichedCandidateRecord; FUTURE_INFORMATION_DETECTED (SIG-27)",
        "frozen input identities REQUIRED: SPY, sector-ETF mapping+source, session calendar, price/return adjustment (SIG-30/31; SIGNAL_INPUT_IDENTITY_MISMATCH)"],
    "source_validation": validation,
    "bound_identities": bound,
    "status_legend": {"FROZEN": "explicit in the governing chain; the producer binds it",
        "DERIVED_MECHANIC": "a required deterministic consequence of frozen rules / an owner Phase-0 clarification",
        "OPEN": "needs an owner ruling before SPQ-1 implementation (see open_questions)",
        "OUT_OF_SCOPE": "not authorized in SPQ-1 Phase 0"},
    "rules": rules,
    "refusal_taxonomy": refusal_taxonomy,
    "frozen_input_identities": ["SPY total-return series", "sector-ETF proxy mapping table (hash in evidence)",
        "sector-ETF source series", "registered session-calendar", "price/return adjustment convention"],
    "not_authorized": ["real/dev/validation/OOS dataset access", "vendor adapters",
        "real residual/z/beta/ADV/sector/eligibility computation", "performance metrics", "parameter tuning",
        "result-driven rule selection", "SPQ-1 implementation (Phase 1+)"],
    "phase0_stop": "Census + schemas + open-question register + draft qualification matrix ONLY. No production signal modules or tests. Owner rules the OPEN items (multiple rounds expected) before SPQ-1 implementation.",
}

print("census sha:", dump(census, "MR002_SPQ1_RuleCensus_v1.0.json"))
print("schema sha:", dump({"record_type": "MR002_SPQ1_InputOutputSchema_Draft", "version": "1.0",
    "signal_decision_record": signal_decision_record, "execution_enriched_record": execution_enriched_record,
    "seam_principle": "decision facts (close-t) are byte-preserved; execution facts are appended at t+1; Increment-3 replay contract is CLOSED and unchanged."},
    "MR002_SPQ1_InputOutputSchema_Draft_v1.0.json"))
print("matrix sha:", dump({"record_type": "MR002_SPQ1_QualificationMatrix_Draft", "version": "1.0",
    "note": "Draft synthetic-only matrix; OPEN-RULING cases await owner rulings on the linked open questions.",
    "cases": [{"case_id": c[0], "scenario": c[1], "rule": c[2], "expected_disposition": c[3]} for c in qualification_matrix],
    "count": len(qualification_matrix)}, "MR002_SPQ1_QualificationMatrix_Draft_v1.0.json"))
print("open-questions sha:", dump({"record_type": "MR002_SPQ1_OpenQuestions", "version": "1.0",
    "note": "Leakage-critical open items requiring owner rulings before SPQ-1 implementation; multiple rounds expected.",
    "questions": open_questions, "count": len(open_questions)}, "MR002_SPQ1_OpenQuestions_v1.0.json"))
print("rules:", len(rules), "| FROZEN:", sum(1 for r in rules if r["status"] == "FROZEN"),
      "| OPEN:", sum(1 for r in rules if r["status"] == "OPEN"),
      "| DERIVED_MECHANIC:", sum(1 for r in rules if r["status"] == "DERIVED_MECHANIC"))
print("source validation:", all(v["match"] for v in validation.values()))
