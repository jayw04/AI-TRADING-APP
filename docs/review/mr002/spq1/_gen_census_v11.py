"""SPQ-1 Phase-0 census v1.1 generator (specification only; no implementation).

Incorporates the 12 owner rulings (2026-07-20). Reclassifies every previously-OPEN rule to
RESOLVED_BY_OWNER bound to its ruling; adds the owner-rulings artifact, the OLS_WINDOW_INCOMPLETE
refusal, the independently-worked warm-up boundary (SIG-32; 125 return / 126 price, flagged pending
owner ratification vs the summary's 124/125), and the V3-corrected ADV rule (median of raw close x raw
volume; two windows) per the owner's own V3-override clause. No real data; no computation.
"""
import hashlib
import json
import os

ROOT = r"C:\LLM-RAG-APP\ai-trading-app"
OUT = os.path.dirname(os.path.abspath(__file__))

SOURCES = {
    "v0.3_design": ("docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md", "1007db82"),
    "v1.0_FROZEN": ("docs/review/mr002/governing_sources/TradingWorkbench_MR002_PreRegistration_v1.0_FROZEN.md", "70108c11"),
    "prereg_v1.0.4": ("docs/review/mr002/MR002_ValidationOOS_Preregistration_v1.0.4.json", "b2a042d4"),
    "trial_ledger": ("docs/review/mr002/MR002_DSR_TrialLedger_v1.0.json", "deda5cec"),
    "dsr_resolution": ("docs/review/mr002/MR002_DSR_Resolution_v1.0.json", "30b812f1"),
    "dsr_dispersion_resolution": ("docs/review/mr002/MR002_DSR_DispersionResolution_v1.0.json", "7a601f5b"),
    "portfolio_rule_census": ("docs/review/mr002/MR002_Portfolio_Rule_Census_v1.0.json", "91eec262"),
    "increment3_registry": ("docs/review/mr002/MR002_Increment3_RuleRegistry_v1.0.json", "edb7ff22"),
    "phase0_resolution": ("docs/review/mr002/MR002_Increment3_Phase0_Resolution_v1.0.json", "860c8cde"),
    "increment3_qualification": ("docs/review/mr002/evaluator/MR002_Increment3_Qualification.json", "0c077c38"),
    "oq1_manifest": ("docs/review/mr002/oq1/evidence/MR002_OQ1_Manifest.json", "7b6eb07d"),
    "spq1_census_v1.0": ("docs/review/mr002/spq1/MR002_SPQ1_RuleCensus_v1.0.json", "7b5aa756"),
}
validation = {}
for k, (rel, exp) in SOURCES.items():
    got = hashlib.sha256(open(os.path.join(ROOT, rel), "rb").read()).hexdigest()
    validation[k] = {"file": rel, "recomputed_sha256": got, "expected_prefix": exp, "match": got.startswith(exp)}
assert all(v["match"] for v in validation.values()), "SOURCE HASH MISMATCH"

V03 = "docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md (sha 1007db82)"
SUP = "A new owner-signed decision superseding v0.3-frozen-into-v1.0 (70108c11)."


def R(rid, area, econ, quote, status, consequence, source=V03, lines="", conflict=None, resolved_by=None, note=None):
    d = {"rule_id": rid, "area": area, "economic_meaning": econ, "governing_quote_or_paraphrase": quote,
         "source_file": source, "source_section_lines": lines, "status": status,
         "implementation_consequence": consequence, "conflicting_source": conflict, "supersession_authority": SUP}
    if resolved_by:
        d["resolved_by_owner_ruling"] = resolved_by
    if note:
        d["note"] = note
    return d


rules = [
    R("SIG-01", "1_session_price_identity", "Registered exchange calendar / session numbering",
      "Governed session index = registered snapshot session dates; session ordinals not calendar arithmetic.",
      "FROZEN", "Bind the registered session index; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.",
      source="prereg_v1.0.4 (b2a042d4) + v0.3 §2/§4"),
    R("SIG-02", "1_session_price_identity", "Decision cutoff / timing semantics",
      "Signals computed AFTER close t; entry t+1 official open; five-session time-stop at open of session 6.",
      "FROZEN", "Decision cutoff = close of session t; no post-close-t observation in the decision record (SIG-27).", lines="§4"),
    R("SIG-03", "1_session_price_identity", "Registered price-series policy (V3)",
      "Signal returns = total-return-adjusted; execution = split-only open/close; gap = distribution-adjusted; dollar-volume = raw close x raw volume.",
      "FROZEN", "Total-return series for the residual model; raw close x raw volume for ADV; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§4 V3 (lines 31-32, 84)"),
    R("SIG-04", "1_session_price_identity", "IPO / insufficient history / interior missing sessions",
      "60 VALID registered sessions t-60..t-1; no interior observation skipped/compressed/forward-filled/replaced; the producer must not build 'the last 60 available' across gaps.",
      "RESOLVED_BY_OWNER", "IPO/insufficient registered history -> INELIGIBLE:OLS_WINDOW_INSUFFICIENT; missing close WITH governed halt/absence evidence -> INELIGIBLE:KNOWN_MARKET_ABSENCE; interior missing STOCK return WITHOUT governed evidence -> INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE; missing SPY/sector factor -> REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH. These four cannot collapse into one another (Correction 2).", lines="§2/§4", resolved_by="R1",
      note="OWNER-C RATIFIED 2026-07-20: a registered session missing the stock close is INELIGIBLE:KNOWN_MARKET_ABSENCE only with governed halt/absence evidence; an unexplained hole fails closed to INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE (Ruling 9 integrity-first precedence — must not be concealed as an ordinary exclusion)."),
    R("SIG-05", "2_return_series", "Residual-model return definition",
      "Rolling 60-session OLS on DAILY ARITHMETIC TOTAL returns; missing observation => ineligible/integrity; no winsorization.",
      "FROZEN", "Daily arithmetic total returns (total-return-adjusted series).", lines="§3 Step 2/normalization"),
    R("SIG-06", "2_return_series", "Interior missing-observation treatment",
      "No interior missing observation may be skipped, compressed, forward-filled, or replaced within the 60-session window.",
      "RESOLVED_BY_OWNER", "Interior missing stock return -> INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE; never bridge the gap.", lines="§3", resolved_by="R1"),
    R("SIG-07", "3_ols_residual", "Step-1 orthogonalized sector factor",
      "Rolling 60-session regression ending t-1: r_Sector = a + beta_Sector*r_SPY + u_Sector; residual u_Sector is the sector factor.",
      "FROZEN", "Produce u_Sector,t from the frozen sector-ETF series + SPY (SIG-30/31).", lines="§3 Step 1"),
    R("SIG-08", "3_ols_residual", "Step-2 stock residual model",
      "Rolling 60-session OLS on t-60..t-1: r_i = alpha + beta_m*r_SPY + beta_s*u_Sector + eps; day-t residual from t-1 coefficients; intercept included.",
      "FROZEN", "Emit eps_i,t and beta_m,i (SIG-09); window 60 ending t-1; intercept included.", lines="§3 Step 2"),
    R("SIG-09", "3_ols_residual", "Beta = market-beta coefficient",
      "beta_i = beta-hat_m,i, the MARKET-beta coefficient of the same §3 Step-2 60-session stock regression (§5 beta-limit binds 'beta_i = each stock's §3 beta-hat_m').",
      "FROZEN", "beta is a by-product of the residual regression; no separate/secondary beta model.", lines="§3 Step 2 + §5 (line 164)"),
    R("SIG-10", "3_ols_residual", "OLS solver / rank / singular handling",
      "One deterministic registered least-squares implementation, float64, intercept, no regularization/ridge/pseudodata/factor-dropping/alternate-model; preregister solver identity + fixed numerical rank tolerance (a mechanics constant, never selected from results).",
      "RESOLVED_BY_OWNER", "Rank-deficient / numerically singular design fails closed -> INTEGRITY_STOP:OLS_DESIGN_SINGULAR. Census preregisters solver identity + rank tolerance before implementation.", lines="§3", resolved_by="R2"),
    R("SIG-11", "3_ols_residual", "Unresolvable sector -> excluded",
      "PIT sector mapping per V2; an unresolvable sector => excluded, never defaulted.",
      "FROZEN", "No PIT-resolvable sector -> INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING; never a default sector.", lines="§3 Step 2"),
    R("SIG-12", "4_r5_aggregation", "R5 five-residual sum",
      "R5_i,t = eps_i,t-4 + eps_i,t-3 + eps_i,t-2 + eps_i,t-1 + eps_i,t (five CONSECUTIVE registered-session residuals).",
      "FROZEN", "Sum the 5 consecutive registered-session residuals ending at t.", lines="§3 Step 3", resolved_by="R4"),
    R("SIG-13", "4_r5_aggregation", "R5 missing / consecutiveness / first-eligible",
      "Exactly 5 residuals over 5 CONSECUTIVE registered sessions; weekends/holidays irrelevant (use registered sessions); do not bridge an interior data gap; do not use the last five available across a missing registered session.",
      "RESOLVED_BY_OWNER", "Missing residual in the five -> INELIGIBLE; never bridge.", lines="§3", resolved_by="R4"),
    R("SIG-14", "5_zscore", "Z-score normalization",
      "z = (R5_t - mu_t-1)/sigma_t-1; mu,sigma over the 60 complete overlapping R5 ending t-1 (R5_t-60..R5_t-1); ddof=1; current R5_t excluded; one pass; no winsorization/floor/clip.",
      "FROZEN", "One deterministic normalization pass yields mu, sigma, z. Zero sigma -> INELIGIBLE (registered reason); non-finite intermediate -> INTEGRITY_STOP.", lines="§3 Step 3", resolved_by="R5"),
    R("SIG-15", "5_zscore", "registered_signal_value output identity",
      "registered_signal_value = z_i,t exactly (no clip/floor/winsor/rank).",
      "FROZEN", "Emit registered_signal_value = z_i,t; Z_entry threshold + |z| ordering are DOWNSTREAM (Increment-3, closed).", lines="§3 Step 3 + Increment-3 registry (edb7ff22)"),
    R("SIG-16", "6_sigma_resid", "registered_sigma_resid identity",
      "registered_sigma_resid = sigma_i,t-1 = sample std (ddof=1) of the 60 overlapping R5 ending t-1 = the z-normalization denominator.",
      "FROZEN", "Emit sigma from the SAME pass as z (SIG-17). Strictly positive + finite; no floor/imputation.", lines="§3 Step 3 + RC-1 (860c8cde)", resolved_by="R5"),
    R("SIG-17", "6_sigma_resid", "Z / sigma single-pass consistency",
      "registered_signal_value (z) and registered_sigma_resid (sigma) derive from one deterministic pass sharing the same 60-value window identity; current R5_t excluded from mu/sigma.",
      "DERIVED_MECHANIC", "Qualification proves z and sigma_resid share one normalization-window identity + computation record.", source="phase0 clarification (owner) + Ruling 5", resolved_by="R5"),
    R("SIG-18", "7_pit_sector", "Sector taxonomy source",
      "PIT sector/industry history OR historically-effective SIC/NAICS via a FROZEN mapping table whose hash ships in evidence; no present-day backfill; survivorship-free.",
      "FROZEN", "Bind the frozen sector-mapping-table hash; sector_id PIT + evidence-bound; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§2 V2"),
    R("SIG-19", "7_pit_sector", "PIT effective-date + succession",
      "effective classification at t = latest accepted PIT sector record whose availability timestamp <= close t (filing date alone insufficient if a later acceptance/publication timestamp exists); same-timestamp -> source amendment/supersession ordering, else deterministic later-accepted-filing identity; a successor does not inherit the predecessor's sector/history except via the governed lineage registry.",
      "RESOLVED_BY_OWNER", "Ambiguous same-timestamp precedence -> INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT; ambiguous lineage -> INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS. Never select on current classification.", lines="§2 V2", resolved_by="R7+R8"),
    R("SIG-20", "9_eligibility", "Entry eligibility conditions",
      "Two-stage semantics (Correction 3). CLOSE-t decision eligibility = security/universe eligibility AND earnings clearance AND corporate-action clearance AND liquidity AND required signal inputs+provenance (all knowable at close t). DOWNSTREAM selection (Increment 3) = z threshold, cross-sectional percentile, portfolio construction. OPEN-t+1 entry admissibility = official open exists AND gap filter passes AND execution constraints pass. The gap filter is NOT a close-t eligibility fact.",
      "FROZEN", "Emit decision_eligibility_status in {ELIGIBLE, INELIGIBLE} at close t (no z-threshold, no percentile, no gap filter); Increment 3 never recomputes. Gap outcome lives in ExecutionEnrichedCandidateRecord.execution_admissibility_status (ADMISSIBLE|CANCELLED_GAP|CANCELLED_MISSING_OPEN|...).", lines="§4", resolved_by="R9"),
    R("SIG-21", "9_eligibility", "Earnings-clearance rule (V1)",
      "No open when a PIT-known earnings announcement falls between the t+1 open and max exit (open session 6); revised-timestamp availability only; BMO/AMC conservative if indistinguishable.",
      "FROZEN", "INELIGIBLE on earnings-window overlap; requires PIT earnings-calendar availability timestamps.", lines="§4 V1", resolved_by="R9"),
    R("SIG-22", "9_eligibility", "Gap filter (execution-time)",
      "Entry cancelled at t+1 open if |AdjOpen_t+1/AdjClose_t - 1| >= 6% (distribution-adjusted).",
      "FROZEN", "EXECUTION-time (t+1) test -> enrichment step, NOT the decision record (SIG-27).", lines="§4"),
    R("SIG-23", "9_eligibility", "Eligibility timing / precedence / evidence",
      "Every eligibility rule uses source data available by close t. Precedence: (1) integrity/identity, (2) missing mandatory signal input, (3) security/universe ineligibility, (4) event blackout, (5) liquidity/price, (6) signal threshold. Each outcome carries rule ID, observed value, threshold/interval, source identity, availability timestamp, decision cutoff. No fact published after close t affects the session-t record.",
      "RESOLVED_BY_OWNER", "Integrity -> stop (taxonomy); ordinary exclusion -> INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING when evidence absent; below-threshold -> not selected downstream (not a failure).", lines="§4", resolved_by="R9"),
    R("SIG-24", "9_eligibility", "Min-history / security-type / exchange / halts",
      "Min signal history = exactly the derived warm-up (SIG-32), no reduced-history fallback. Eligible = US-listed operating-company common equity + registered common share classes in the frozen universe. Exclude (unless governed): ETF/ETN/CEF/preferred/rights/warrants/units/SPAC-units/OTC/foreign-ordinary/duplicate-listings. Exchange from the frozen PIT universe. Halt known by close t or no valid close-t observation -> INELIGIBLE; valid decision but missing t+1 open -> Increment-2/3 execution-layer cancel/defer; SPQ-1 never invents a next-open.",
      "RESOLVED_BY_OWNER", "INELIGIBLE for excluded security types; INELIGIBLE:OLS_WINDOW_INSUFFICIENT for insufficient history; INELIGIBLE:KNOWN_MARKET_ABSENCE for a governed halt/no-close; execution-layer handles a missing t+1 open (CANCELLED_MISSING_OPEN).", lines="§2/§4", resolved_by="R10"),
    R("SIG-25", "10_adv_open", "Dollar-volume / ADV basis (V3-corrected)",
      "Frozen §4: 'Dollar volume = raw (unadjusted) close x raw volume' (lines 31-32, 84) and the statistic is the MEDIAN dollar volume, over TWO windows: trailing 60-session median (universe top-250/150 + >$25M liquidity screen, lines 30-33) and trailing 20-session median (the 2% execution cap, line 253). trailing_adv_dollars (candidate fact) = the 20-session median. PIT mechanics (Ruling 11): window ends t-1, current session excluded, exactly-N present.",
      "RESOLVED_BY_OWNER", "Bind MEDIAN of (raw close x raw volume); 20-session median = trailing_adv_dollars, 60-session median = universe/liquidity screen. Missing any required session -> INELIGIBLE:ADV_WINDOW_INSUFFICIENT; no mean/median-swap/winsor/zero-fill/short-window fallback.", lines="§4 (30-33, 84, 253)", resolved_by="R11",
      conflict="Ruling 11 recommended mean of adjusted_close x raw_volume over 20 sessions; frozen V3 (§4 lines 31-32/84) specifies raw close x raw volume and §4 (lines 30-33/253) specifies MEDIAN. Per Ruling 11's own override clause, V3 governs.",
      note="OWNER-B RATIFIED 2026-07-20: V3 controls -> MEDIAN of raw close x raw volume, two windows (60-session selection, 20-session cap = trailing_adv_dollars). Ruling 11's mean/adjusted recommendation is superseded by frozen V3 per the ruling's explicit override clause."),
    R("SIG-26", "10_adv_open", "Official next-open identity + missing-open",
      "Entries without a valid official open cancelled; exits without one pend until the next official open. Official open = split-only, non-dividend-adjusted, t+1 regular-session open.",
      "FROZEN", "Session-(t+1) fact; a missing future open is registered ONLY at the execution session, never at decision.", lines="§4 halts + V3", resolved_by="R10"),
    R("SIG-27", "10_adv_open", "Decision/execution seam",
      "SignalDecisionRecord (close t) must NOT contain official_next_open_price, actual_execution_session, or any post-close-t field; the t+1 enrichment step appends the official open + execution timestamp WITHOUT recomputing decision facts.",
      "DERIVED_MECHANIC", "Two structurally distinct records; enriched record = adapter into the CLOSED Increment-3 replay contract. Post-cutoff field/identity in a decision record -> INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED.", source="phase0 clarification (owner) + Increment-3 (edb7ff22, CLOSED)"),
    R("SIG-28", "11_security_identity", "Permanent security id / lineage",
      "permanent_security_id from the frozen PIT identity registry. Ticker change with registry economic continuity -> same permanent id, history continues. New permanent security (merger/spinoff/reincorporation/new share class) -> history does NOT continue unless the governed lineage registry authorizes it. Lineage record binds predecessor/successor permanent id, effective session, corporate-action type, history-continuity authorization, source evidence identity.",
      "RESOLVED_BY_OWNER", "Ambiguous lineage -> INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS. Sector looked up for the active permanent security at the cutoff.", lines="§2", resolved_by="R8+R12"),
    R("SIG-29", "11_security_identity", "candidate_id vs permanent_security_id",
      "candidate_id = unique decision-record identity binding program ID / configuration ID / decision session / permanent security ID / side / signal-record identity; symbol = time-varying display/execution identifier; candidate_id must not replace the permanent security identifier.",
      "FROZEN", "Emit all three distinctly; Increment-3 tie-breaks bind permanent_security_id.", source="phase0 resolution (860c8cde) + increment3 registry (edb7ff22) + Ruling 12", resolved_by="R12"),
    R("SIG-30", "input_identities", "SPY market-factor series identity",
      "The market factor is the SPY total-return series (Step-1 + Step-2 regressor r_SPY).",
      "FROZEN", "SPY total-return series = REQUIRED frozen input; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§3"),
    R("SIG-31", "input_identities", "Sector-ETF proxy + source-series identity",
      "Sector factors = sector-ETF residuals u_Sector; sector-ETF proxy mapping + source series = the FROZEN mapping table whose hash ships in evidence.",
      "FROZEN", "Sector-ETF proxy mapping + source series = REQUIRED frozen inputs; mismatch -> SIGNAL_INPUT_IDENTITY_MISMATCH.", lines="§2 V2 + §3 Step 1"),
    R("SIG-32", "6_first_scoreable", "First scoreable session / warm-up (independently worked)",
      "Derived mechanically from the nested frozen windows (Ruling 6). eps_s needs coefficient returns [s-60,s-1] PLUS the day-s return -> earliest return for eps_s is s-60. Earliest normalization value R5_(t-60) has earliest residual eps_(t-64), whose earliest return is (t-64)-60 = t-124. Latest needed return = t (for R5_t). => return sessions [t-124, t] = 125 registered RETURN sessions (124 prior + current); a return needs one preceding close => 126 registered PRICE observations [t-125, t].",
      "RESOLVED_BY_OWNER", "First scoreable decision session t requires exactly 125 registered return sessions (earliest return index t-124) and 126 registered price observations; one session too early -> INELIGIBLE. Min-history (SIG-24) inherits this exact number; no reduced-history fallback.", source="Ruling 6 (independently worked)", resolved_by="R6",
      note="OWNER-A RATIFIED 2026-07-20: first scoreable boundary = 125 registered return sessions (earliest return index t-124) and 126 registered price observations [t-125, t], correcting the summary tally 124/125. Min-history (SIG-24) inherits this exact number."),
]

# --- Owner rulings artifact ------------------------------------------------
def RULING(rid, title, rules_affected, decision, rationale, code, tests, sources):
    return {"ruling_id": rid, "title": title, "affected_rule_ids": rules_affected, "decision": decision,
            "rationale": rationale, "required_refusal_or_ineligibility_code": code, "required_tests": tests,
            "source_documents": sources, "owner": "Jay Wang", "date": "2026-07-20"}


owner_rulings = [
    RULING("R1", "OLS observation counting and missing sessions", ["SIG-04", "SIG-06"],
        "60 VALID registered sessions t-60..t-1; no interior observation skipped/compressed/forward-filled/replaced; never build 'last 60 available' across gaps.",
        "Interior gaps silently bridged would leak or distort the residual window.",
        ["INELIGIBLE:OLS_WINDOW_INSUFFICIENT (IPO/young)", "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE (interior hole, no evidence)", "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH (missing SPY/sector)", "INELIGIBLE:KNOWN_MARKET_ABSENCE (governed halt/no-close)"],
        ["SPQM-01 60 no compression", "SPQM-29 interior missing OLS session", "SPQM-40 halt-with-evidence vs SPQM-41 hole-without-evidence"], ["v0.3 §2/§4"]),
    RULING("R2", "OLS solver and singular handling", ["SIG-10"],
        "One deterministic float64 least-squares with intercept; no regularization/ridge/pseudodata/factor-dropping/alternate-model; preregister solver identity + fixed rank tolerance (mechanics constant, not result-selected).",
        "Solver ambiguity or a fallback path could change residuals; a singular design must fail closed.",
        ["INTEGRITY_STOP:OLS_DESIGN_SINGULAR"], ["SPQM-05 singular OLS design", "SPQM-20 constant benchmark"], ["v0.3 §3"]),
    RULING("R3", "Day-t residual production", ["SIG-08"],
        "eps_i,t = r_i,t - alpha_hat_t-1 - beta_m_hat_t-1 r_SPY,t - beta_s_hat_t-1 u_sector,t; coefficients end t-1; day-t returns available at close t; no refit including session t.",
        "The single authorized way session-t information enters the decision without look-ahead.",
        [], ["SPQM-03 coefficients end t-1", "SPQM-30 day-t residual uses t-1 coefficients"], ["v0.3 §3 Step 2"]),
    RULING("R4", "R5 definition and missing residuals", ["SIG-12", "SIG-13"],
        "R5 = eps_t-4..eps_t (5 consecutive registered sessions); missing residual in the five -> INELIGIBLE; do not bridge; registered sessions, not calendar days.",
        "Bridging a gap would sum non-adjacent residuals and corrupt the signal.",
        ["INELIGIBLE:R5_WINDOW_INSUFFICIENT"], ["SPQM-07 R5 endpoints", "SPQM-31 missing middle residual no bridge"], ["v0.3 §3 Step 3"]),
    RULING("R5", "Z-score and sigma window", ["SIG-14", "SIG-16", "SIG-17"],
        "mu,sigma over R5_t-60..R5_t-1 (60 values); one pass; current R5_t excluded; sigma finite & >0; zero sigma -> INELIGIBLE (registered reason); non-finite intermediate -> INTEGRITY_STOP; no floor/clip.",
        "z and sigma_resid must share one window identity; the weighting sigma is z's own denominator.",
        ["INELIGIBLE (zero sigma, registered reason)", "INTEGRITY_STOP (non-finite intermediate)"],
        ["SPQM-10 zero z-variance", "SPQM-13 same-pass z/sigma identity"], ["v0.3 §3 Step 3"]),
    RULING("R6", "First scoreable session and warm-up", ["SIG-32", "SIG-24"],
        "Derive mechanically from the nested windows; distinguish return-history vs price-history; include an independently worked boundary example; no vague 'approximately 124'.",
        "Min-history is pinned to the exact derived warm-up; an off-by-one is a leakage/eligibility boundary error.",
        ["INELIGIBLE (one session too early)"], ["SPQM-32 exact first-scoreable boundary", "SPQM-33 one-session-too-early refusal"], ["v0.3 §3 (nested windows)"]),
    RULING("R7", "PIT-sector effective date", ["SIG-19"],
        "effective classification at t = latest accepted PIT record with availability timestamp <= close t; filing date alone insufficient if a later acceptance/publication timestamp exists; same-timestamp -> source supersession ordering, else deterministic later-accepted-filing; ambiguous -> conflict stop; never current classification.",
        "A future-published sector reclassification must not leak into a past decision.",
        ["INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT"], ["SPQM-14 PIT effective-date change", "SPQM-34 sector published after cutoff excluded", "SPQM-15 same-timestamp conflict"], ["v0.3 §2 V2"]),
    RULING("R8", "Security succession and PIT-sector continuity", ["SIG-19", "SIG-28"],
        "Successor does not auto-inherit predecessor sector/history; governed lineage record required; ticker change same security -> continues; new permanent security -> not continued unless authorized; sector looked up for the active permanent security at cutoff.",
        "Automatic inheritance across a corporate action fabricates history and leaks survivorship.",
        ["INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS"], ["SPQM-17 ticker change continuity", "SPQM-35 merger successor without continuity"], ["v0.3 §2"]),
    RULING("R9", "Eligibility evidence timing and precedence", ["SIG-20", "SIG-21", "SIG-23"],
        "Source data available by close t; precedence integrity>missing-input>security/universe>event-blackout>liquidity/price>signal-threshold; each outcome carries rule ID/observed value/threshold/source identity/availability timestamp/decision cutoff; no post-close-t fact affects the session-t record; below-threshold is not a failure.",
        "A fixed precedence + evidence binding makes every exclusion auditable and PIT-safe.",
        ["INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING", "INTEGRITY_STOP (integrity/identity)"], ["SPQM-21 earnings boundary", "SPQM-22 corporate-action exclusion"], ["v0.3 §4"]),
    RULING("R10", "Minimum history, security type, exchange, halts", ["SIG-24", "SIG-26"],
        "Min history = exact derived warm-up (no fallback); eligible = US-listed operating-company common equity + governed share classes; exclude ETF/ETN/CEF/preferred/rights/warrants/units/SPAC-units/OTC/foreign-ordinary/duplicate; exchange from frozen PIT universe; halt or no close-t -> INELIGIBLE; missing t+1 open -> Increment-2/3 execution layer; never invent a next-open.",
        "Type/exchange/halt eligibility must be PIT and fail-closed; SPQ-1 does not fabricate execution prices.",
        ["INELIGIBLE:KNOWN_MARKET_ABSENCE (governed halt/no-close)", "INELIGIBLE:OLS_WINDOW_INSUFFICIENT (insufficient history)", "execution-layer CANCELLED_MISSING_OPEN (Increment 2/3)"], ["SPQM-36 halt/no-close eligibility", "SPQM-40/41 halt-evidence distinction", "SPQM-24 missing official open"], ["v0.3 §2/§4"]),
    RULING("R11", "ADV formula and lag", ["SIG-25"],
        "Trailing dollar volume over sessions completed before the decision session; window ends t-1, current excluded, exactly-N present; missing session -> INELIGIBLE:ADV_WINDOW_INSUFFICIENT; no median-swap/winsor/zero-fill/short-window fallback. OVERRIDE CLAUSE: if governing V3 specifies a different dollar-volume convention it governs and must be cited verbatim.",
        "The candidate's trailing_adv_dollars must be trailing, PIT, and fail-closed. Per the override clause, frozen V3 (§4) governs the price field (raw close x raw volume) and statistic (MEDIAN) over two windows (60-session selection, 20-session cap).",
        ["INELIGIBLE:ADV_WINDOW_INSUFFICIENT"], ["SPQM-23 liquidity/ADV boundary", "SPQM-37 ADV current-session exclusion", "SPQM-38 ADV exactly-N boundary"], ["v0.3 §4 (lines 30-33, 84, 253)"]),
    RULING("R12", "Permanent security identity", ["SIG-28", "SIG-29"],
        "permanent_security_id from the frozen PIT identity registry; candidate_id = decision-record identity; symbol = time-varying; ticker change !-> new permanent id when registry says continuity; merger/successor !-> predecessor identity unless governed lineage says same security; candidate_id binds program/config/session/permanent-security/side/signal-record.",
        "Stable economic identity + record identity must be distinct and registry-governed.",
        ["INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS"], ["SPQM-25 provenance completeness"], ["v0.3 §2 + Increment-3 (edb7ff22)"]),
]

refusal_taxonomy = {
    "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH": "frozen-input identity mismatch (SPY / sector-ETF map / sector source / calendar / adjustment)",
    "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH": "session index / numbering diverges from the registered calendar",
    "INELIGIBLE:OLS_WINDOW_INSUFFICIENT": "the security does not yet have the required registered history (IPO/young) — ordinary ineligibility (Correction 2: moved from the INTEGRITY_STOP family)",
    "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE": "an interior historical stock-return hole WITHOUT governed halt/absence evidence — fails closed (must not be concealed as an ordinary exclusion)",
    "INELIGIBLE:KNOWN_MARKET_ABSENCE": "a missing close WITH governed halt/absence evidence — ordinary ineligibility (Correction 2)",
    "DEPRECATED_NON_EMITTABLE:RETURN_INPUT_MISSING": "RETIRED (Correction 2): too generic; NEVER emit — use OLS_WINDOW_INSUFFICIENT (young), OLS_WINDOW_INCOMPLETE (interior hole, no evidence), KNOWN_MARKET_ABSENCE (governed halt), or SIGNAL_INPUT_IDENTITY_MISMATCH (SPY/sector factor)",
    "INTEGRITY_STOP:OLS_DESIGN_SINGULAR": "the OLS design matrix is rank-deficient / numerically singular",
    "INTEGRITY_STOP:RESIDUAL_NONFINITE": "a computed residual is non-finite",
    "INELIGIBLE:R5_WINDOW_INSUFFICIENT": "fewer than 5 valid consecutive residuals for R5 (never bridge)",
    "INTEGRITY_STOP:ZSCORE_WINDOW_INSUFFICIENT": "fewer than 60 complete overlapping R5 observations for mu/sigma",
    "INELIGIBLE:ZSCORE_VARIANCE_INVALID": "sigma_i,t-1 is zero (z undefined) — INELIGIBLE with a registered reason (Ruling 5)",
    "INTEGRITY_STOP:SIGMA_RESID_NONFINITE": "a non-finite intermediate in the mu/sigma pass (Ruling 5)",
    "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING": "no PIT-resolvable sector at t (never defaulted)",
    "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT": "ambiguous same-availability-timestamp PIT sector records",
    "INTEGRITY_STOP:BETA_INPUT_INVALID": "beta regression inputs invalid (folds into OLS_DESIGN_SINGULAR — same regression)",
    "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING": "a required eligibility evidence identity / availability timestamp is missing",
    "INELIGIBLE:ADV_WINDOW_INSUFFICIENT": "insufficient sessions for the registered ADV window",
    "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS": "ambiguous permanent-security-id / lineage resolution",
    "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED": "any post-decision-cutoff field or identity in a SignalDecisionRecord",
}

signal_decision_record = {
    "record_type": "MR002_SPQ1_SignalDecisionRecord (draft v1.1)",
    "cutoff": "close of session t (all fields use information through close-t only)",
    "required_fields": ["candidate_id (= program_id | configuration_id | decision_session | permanent_security_id | side | signal_record_identity)",
        "permanent_security_id (frozen PIT identity registry)", "symbol (time-varying)", "decision_session (=t)",
        "signal_origin_session", "side", "registered_signal_value (=z_i,t)", "registered_sigma_resid (=sigma_i,t-1)",
        "sector_id (PIT, availability<=close t)", "beta (=beta_m,i)", "decision_eligibility_status (ELIGIBLE|INELIGIBLE at close t; no z-threshold/percentile/gap filter)",
        "eligibility_evidence_identity", "eligibility_precedence_rank (1..6, Ruling 9)", "configuration_id (A|B|C, Z_entry downstream)",
        "trailing_adv_dollars (20-session MEDIAN of raw close x raw volume, ending t-1)", "normalization_window_identity",
        "computation_record_identity", "warmup_return_sessions (=125)", "warmup_price_observations (=126)"],
    "structurally_forbidden_fields": ["official_next_open_price", "actual_execution_session", "any post-close-t observation"],
    "forbidden_field_disposition": "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
}
execution_enriched_record = {
    "record_type": "MR002_SPQ1_ExecutionEnrichedCandidateRecord (draft v1.1)",
    "timing": "session t+1 (execution) — appends execution facts WITHOUT recomputing decision facts",
    "adds": ["official_next_open_price (t+1 official open, split-only)", "scheduled_execution_session (=t+1)",
        "execution_admissibility_status (ADMISSIBLE|CANCELLED_GAP|CANCELLED_MISSING_OPEN|other governed execution result)",
        "gap_filter_result (|AdjOpen_t+1/AdjClose_t-1| >= 6% -> CANCELLED_GAP)", "missing_open_disposition (cancel entry / defer exit)"],
    "carries_unchanged": "the full SignalDecisionRecord (byte-preserved; enrichment cannot mutate decision facts)",
    "seam": "adapter into the CLOSED Increment-3 accepted replay candidate contract (edb7ff22); Increment 3 is NOT reopened.",
}

qualification_matrix = [
    ("SPQM-01", "60 registered sessions with no compression", "SIG-04", "PASS"),
    ("SPQM-29", "interior missing OLS session (no bridge)", "SIG-04/06", "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE"),
    ("SPQM-02", "59-session window refuses (insufficient history)", "SIG-04", "INELIGIBLE:OLS_WINDOW_INSUFFICIENT"),
    ("SPQM-03", "coefficients end at t-1", "SIG-08", "PASS"),
    ("SPQM-30", "day-t residual uses t-1 coefficients", "SIG-08", "PASS"),
    ("SPQM-04", "decision record rejects next-open price structurally", "SIG-27", "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED"),
    ("SPQM-39", "execution enrichment cannot mutate decision facts", "SIG-27", "PASS (byte-preserved)"),
    ("SPQM-05", "singular OLS design refuses", "SIG-10", "INTEGRITY_STOP:OLS_DESIGN_SINGULAR"),
    ("SPQM-06", "missing factor (SPY/sector) return refuses", "SIG-05/07", "REFUSED_CODE_OR_DATA_IDENTITY"),
    ("SPQM-07", "R5 uses five consecutive registered sessions", "SIG-12", "PASS"),
    ("SPQM-31", "missing middle residual does not bridge", "SIG-13", "INELIGIBLE:R5_WINDOW_INSUFFICIENT"),
    ("SPQM-13", "same-pass z/sigma identity", "SIG-17", "PASS"),
    ("SPQM-10", "zero z-score variance", "SIG-14", "INELIGIBLE:ZSCORE_VARIANCE_INVALID"),
    ("SPQM-32", "exact first scoreable-session boundary (125 return / 126 price)", "SIG-32", "PASS"),
    ("SPQM-33", "one-session-too-early refusal", "SIG-32", "INELIGIBLE"),
    ("SPQM-14", "PIT sector effective-date change respected", "SIG-19", "PASS"),
    ("SPQM-34", "PIT sector record published after cutoff excluded", "SIG-19", "PASS (excluded)"),
    ("SPQM-15", "same-timestamp sector conflict refuses", "SIG-19", "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT"),
    ("SPQM-16", "missing PIT sector -> INELIGIBLE", "SIG-11", "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING"),
    ("SPQM-17", "ticker change with identity continuity", "SIG-28", "PASS (history continues)"),
    ("SPQM-35", "merger successor without continuity", "SIG-28", "history does NOT continue"),
    ("SPQM-19", "beta first eligible session (= residual regression)", "SIG-09", "PASS"),
    ("SPQM-20", "beta singular/constant benchmark refuses", "SIG-09/10", "INTEGRITY_STOP:OLS_DESIGN_SINGULAR"),
    ("SPQM-21", "earnings-window boundary -> INELIGIBLE", "SIG-21", "INELIGIBLE"),
    ("SPQM-22", "corporate-action exclusion", "SIG-20", "INELIGIBLE"),
    ("SPQM-23", "liquidity/ADV boundary", "SIG-25", "INELIGIBLE:ADV_WINDOW_INSUFFICIENT"),
    ("SPQM-37", "ADV current-session exclusion (window ends t-1)", "SIG-25", "PASS"),
    ("SPQM-38", "ADV exactly-20-session boundary (median, raw x raw)", "SIG-25", "PASS"),
    ("SPQM-36", "halt / no-close eligibility (with governed evidence)", "SIG-24", "INELIGIBLE:KNOWN_MARKET_ABSENCE"),
    ("SPQM-40", "missing close WITH governed halt/absence evidence", "SIG-04/24", "INELIGIBLE:KNOWN_MARKET_ABSENCE"),
    ("SPQM-41", "SAME missing close WITHOUT governed evidence (unexplained hole)", "SIG-04/06", "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE"),
    ("SPQM-42", "close-t eligibility excludes the t+1 gap filter (two-stage)", "SIG-20/22", "gap outcome only in execution_admissibility_status"),
    ("SPQM-24", "missing official open (execution step only)", "SIG-26", "cancel/defer at t+1"),
    ("SPQM-25", "candidate provenance completeness", "SignalDecisionRecord", "PASS"),
    ("SPQM-26", "A/B/C differ only by Z_entry downstream", "SIG-15", "PASS"),
    ("SPQM-27", "deterministic synthetic output (byte-identical)", "all", "PASS"),
    ("SPQM-28", "no real-data import or file access (synthetic-only)", "all", "PASS"),
]

question_records = [
    ("OQ-SPQ-01", 1, ["SIG-04", "SIG-06"], "R1", "RESOLVED_BY_OWNER", "IPO/interior-missing-session counting inside the 60-session OLS window."),
    ("OQ-SPQ-02", 2, ["SIG-06"], "R1", "RESOLVED_BY_OWNER", "Interior-missing-session handling within the 60-session return window."),
    ("OQ-SPQ-03", 3, ["SIG-10"], "R2", "RESOLVED_BY_OWNER", "OLS solver, tolerance, rank requirement, singular-design handling."),
    ("OQ-SPQ-04", 4, ["SIG-13"], "R4", "RESOLVED_BY_OWNER", "R5 missing-residual, first eligible, consecutiveness, <5 refusal."),
    ("OQ-SPQ-05", 7, ["SIG-19"], "R7+R8", "RESOLVED_BY_OWNER", "PIT sector effective-date, availability, same-day, succession."),
    ("OQ-SPQ-06", 9, ["SIG-23"], "R9", "RESOLVED_BY_OWNER", "Eligibility availability timestamps, precedence, evidence identity, refusal-vs-INELIGIBLE."),
    ("OQ-SPQ-07", 9, ["SIG-24"], "R10", "RESOLVED_BY_OWNER", "Min-history, security-type, exchange-eligibility, bankruptcy/halt."),
    ("OQ-SPQ-08", 10, ["SIG-25"], "R11", "RESOLVED_BY_OWNER", "ADV formula/lookback/lag (V3-corrected to median of raw x raw, two windows)."),
    ("OQ-SPQ-09", 11, ["SIG-28", "SIG-29"], "R8+R12", "RESOLVED_BY_OWNER", "permanent_security_id source, lineage, succession, share-class, duplicates."),
    ("OQ-SPQ-10", 5, ["SIG-32", "SIG-24"], "R6", "RESOLVED_BY_OWNER", "Compounded warm-up length / first scoreable session (independently worked -> 125 return / 126 price; RATIFIED)."),
]
ratifications = {
    "OWNER-A": "RATIFIED",
    "OWNER-B": "RATIFIED",
    "OWNER-C": "RATIFIED",
    "ratification_date": "2026-07-20",
    "detail": {
        "OWNER-A": "SIG-32 (R6): first scoreable boundary = 125 registered return sessions (earliest return index t-124) and 126 registered price observations.",
        "OWNER-B": "SIG-25 (R11): ADV = MEDIAN of raw close x raw volume over two windows (60-session selection, 20-session cap = trailing_adv_dollars) — frozen V3 controls.",
        "OWNER-C": "SIG-04 (R1): missing close WITH governed halt/absence evidence -> INELIGIBLE:KNOWN_MARKET_ABSENCE; unexplained hole -> INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE.",
    },
}


def dump(obj, name):
    open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return hashlib.sha256(open(os.path.join(OUT, name), "rb").read()).hexdigest()


governing = {k: {"file": v["file"], "sha256": v["recomputed_sha256"]} for k, v in validation.items()}
bound = dict(governing)
bound["oq1_closeout_commit"] = "f47f92ddf670bd0d0413d7624731eb6c59b961c9"
bound["increment3_accepted_output_hash"] = "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907"

status_counts = {}
for r in rules:
    status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

census = {
    "record_type": "MR002_SPQ1_RULE_CENSUS", "version": "1.1", "date": "2026-07-20",
    "supersedes": {"version": "1.0", "sha256": validation["spq1_census_v1.0"]["recomputed_sha256"]},
    "record_status": "IMMUTABLE",
    "designation": "MR-002 Workstream C — Signal & Data-Production Qualification (SPQ-1), Phase 0",
    "purpose": "Implementation-binding census for the upstream layer that PRODUCES the candidate facts Increment 3 consumes. v1.1 incorporates the 12 owner rulings (2026-07-20); every previously-OPEN rule is now RESOLVED_BY_OWNER. No implementation; no real data; no computation.",
    "boundary": "Synthetic-only. No real/dev/validation/OOS data opened, no vendor adapter, no residual/z/sigma/beta/sector/ADV computation, no metric, no tuning, no result-driven rule selection.",
    "acceptance_state": "No leakage-critical rule remains OPEN. Final states used: FROZEN / DERIVED_MECHANIC / RESOLVED_BY_OWNER / OUT_OF_SCOPE.",
    "owner_rulings_binding": "MR002_SPQ1_Phase0_OwnerRulings_v1.0.json",
    "ratifications": ratifications,
    "internal_consistency_corrections": {
        "Correction_1": "SIG-33 cross-reference -> SIG-27 (the decision/execution seam rule).",
        "Correction_2": "Missing-input taxonomy frozen into 4 non-collapsing codes (OLS_WINDOW_INSUFFICIENT=INELIGIBLE young; OLS_WINDOW_INCOMPLETE=INTEGRITY_STOP interior hole; KNOWN_MARKET_ABSENCE=INELIGIBLE governed halt; SIGNAL_INPUT_IDENTITY_MISMATCH=REFUSED SPY/sector); RETURN_INPUT_MISSING retired non-emittable.",
        "Correction_3": "SIG-20 close-t decision_eligibility_status excludes the t+1 gap filter and z/percentile; gap outcome moves to ExecutionEnrichedCandidateRecord.execution_admissibility_status.",
    },
    "source_validation": validation,
    "bound_identities": bound,
    "status_legend": {"FROZEN": "explicit in the governing chain; the producer binds it",
        "DERIVED_MECHANIC": "a required deterministic consequence of frozen rules / owner clarification",
        "RESOLVED_BY_OWNER": "was OPEN; resolved by a 2026-07-20 owner ruling (see resolved_by_owner_ruling)",
        "OUT_OF_SCOPE": "not authorized in SPQ-1 Phase 0"},
    "status_counts": status_counts,
    "rules": rules,
    "refusal_taxonomy": refusal_taxonomy,
    "frozen_input_identities": ["SPY total-return series", "sector-ETF proxy mapping table (hash in evidence)",
        "sector-ETF source series", "registered session-calendar", "price/return adjustment convention"],
    "not_authorized": ["real/dev/validation/OOS dataset access", "vendor adapters",
        "real residual/z/beta/ADV/sector/eligibility computation", "performance metrics", "parameter tuning",
        "result-driven rule selection", "SPQ-1 implementation (Phase 1+)"],
    "phase0_stop": "Census + schemas + owner-rulings + draft matrix ONLY. No production signal modules or tests. OWNER-A/B/C RATIFIED (2026-07-20); the three internal-consistency corrections are applied. Awaiting owner final Phase-0 technical closure; SPQ-1 implementation remains NOT AUTHORIZED.",
}

print("census v1.1 sha:", dump(census, "MR002_SPQ1_RuleCensus_v1.1.json"))
print("rulings sha:", dump({"record_type": "MR002_SPQ1_Phase0_OwnerRulings", "version": "1.0", "date": "2026-07-20",
    "owner": "Jay Wang", "count": len(owner_rulings), "rulings": owner_rulings,
    "ratifications": ratifications,
    "note": "Twelve owner rulings resolving the SPQ-1 Phase-0 open questions; OWNER-A (warm-up 125/126), OWNER-B (ADV V3 median raw x raw), and OWNER-C (halt-vs-hole) all RATIFIED 2026-07-20."},
    "MR002_SPQ1_Phase0_OwnerRulings_v1.0.json"))
print("schema v1.1 sha:", dump({"record_type": "MR002_SPQ1_InputOutputSchema_Draft", "version": "1.1",
    "signal_decision_record": signal_decision_record, "execution_enriched_record": execution_enriched_record,
    "seam_principle": "decision facts (close-t) byte-preserved; execution facts appended at t+1; Increment-3 replay contract CLOSED and unchanged."},
    "MR002_SPQ1_InputOutputSchema_Draft_v1.1.json"))
print("matrix v1.1 sha:", dump({"record_type": "MR002_SPQ1_QualificationMatrix_Draft", "version": "1.1",
    "note": "Synthetic-only matrix; all owner-required tests (comments.md lines 408-424) included; no OPEN-RULING remains.",
    "cases": [{"case_id": c[0], "scenario": c[1], "rule": c[2], "expected_disposition": c[3]} for c in qualification_matrix],
    "count": len(qualification_matrix)}, "MR002_SPQ1_QualificationMatrix_Draft_v1.1.json"))
print("open-questions v1.1 sha:", dump({"record_type": "MR002_SPQ1_OpenQuestions", "version": "1.1",
    "note": "All ten questions RESOLVED_BY_OWNER via the 12 rulings; each maps to governing rule IDs + ruling. No REMAINS_OPEN. OWNER-A/B/C RATIFIED 2026-07-20.",
    "questions": [{"question_id": q[0], "area": q[1], "governing_rule_ids": q[2], "owner_ruling": q[3],
        "resolution_state": q[4], "question": q[5]} for q in question_records],
    "resolved_by_owner": sum(1 for q in question_records if q[4] == "RESOLVED_BY_OWNER"),
    "remains_open": sum(1 for q in question_records if q[4] == "REMAINS_OPEN"), "count": len(question_records)},
    "MR002_SPQ1_OpenQuestions_v1.1.json"))
print("status_counts:", status_counts, "| rules:", len(rules), "| rulings:", len(owner_rulings), "| matrix:", len(qualification_matrix))
open_left = [r["rule_id"] for r in rules if r["status"] == "OPEN"]
print("OPEN rules remaining:", open_left, "(must be empty)")
print("source validation:", all(v["match"] for v in validation.values()))
