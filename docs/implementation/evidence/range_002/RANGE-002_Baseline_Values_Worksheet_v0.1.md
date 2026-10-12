# RANGE-002 baseline values worksheet v0.1 (LANE E)

| Field | Value |
|---|---|
| Purpose | Every owner baseline parameter the RANGE-002 screening spec needs, with the existing proposal (or NONE), its source, who reads it, and whether it is chosen from data. A worksheet for the owner's adoption. |
| Status | **WORKSHEET. NOTHING IS ADOPTED, FROZEN OR SIGNED.** No value below is chosen by the preparer. "Candidate value" is quoted from an existing document; where none exists the cell says NONE. Anything the preparer could not establish is marked UNKNOWN. |
| Reviewer sequencing | The Independent Validator 陈友潼 (Chen Youtong; written acceptance PENDING) must see this worksheet BEFORE any probe or loader output exists. A role whose acceptance is PENDING is VACANT for every gate until an acceptance record exists in Git. |
| Advisory reviewers | 方炳雄 (Fang Bingxiong): exit / take-profit / stop / scale-out / trailing design, advisory, no gate sign-off (marked on the relevant rows). 肖学焦 (Xiao Xuejiao): risk / loss-control, advisory, no gate sign-off (marked on the relevant rows). Neither role is a D08 signatory or a gate. |
| Use | For owner adoption only. This worksheet adopts no value and freezes nothing. |
| Data accessed | None. No market data, no returns, no network. Documents and code were read only. |
| Field set | `apps/backend/app/research/range002/spec/schema.py` on the feature branch checkout (`C:\LLM-APP\AI-TRADING-APP`, branch `feat/range002-screen-kernel`): `SCREEN_V2_REQUIRED` (25), `SCREEN_V2_DEFERRED` (14), `SCREEN_V2_UNMODELLED` (9), `SCREEN_V1_EXEMPT` (18). 25 + 14 + 9 = 48 = `SCREEN_V1_REQUIRED`; 48 + 18 = 66 P0 fields. Group E lists items that are needed but are not spec fields. |
| Base | `origin/main` checkout `C:\LLM-APP\wt-r002-e`; the A-SCREEN amendment is read from the untracked file in `C:\LLM-APP\AI-TRADING-APP` (revision 3). |

## Legend

**Source abbreviations.** A-SCREEN = `RANGE-002_A-SCREEN_Amendment_v0.1.md` (untracked; sections 6 to 8, owner rulings O-1..O-11). Sheets = `RANGE-002_P0_Decision_Sheets_v0.1.md`. Reg = `RANGE-002_P0_Decision_Register_v0.2.md`. vNext = `RANGE-002_P0_Decision_Package_vNext_v0.1.md`. Plan = `RANGE-002_Implementation_Plan_v0.5.md`. A1 = `RANGE-002_Design_Addendum_A1.md`. Backlog = `RANGE-002_P1_P2_Implementation_Backlog_v0.1.md`. ODF = `RANGE-002_OD_Followups_v0.1.md`. RNG = `RNG-001_Rejection_Summary_Report_2026-10-09.md`. Line numbers refer to the files as read.

**Needed for.** D = descriptive screen (P3A stage 1, A-SCREEN 6b item 1). S = statistical selection (stage 2, A-SCREEN 6b item 2 and 6c). A = advancement (P3b, P4, portfolio rerun, P5). "Reads": **G** = the results guard refuses P2/P3A while the field is unset (schema.py lines 583 to 593: `p3.criteria`, `exits.candidates`, `exits.selection.*`, both attempt limits, the exposure binding, the genesis id). **K** = the screen kernel `screen/params.py` raises `ParamsUnsetError` while it is null (and refuses some values, see Note 3). **none** = neither reads it at P2/P3A; it is required only so the profile covers interpretation.

**Status.** UNSET = no proposal exists. PROPOSED = a proposal exists in a document and nothing is adopted (an "owner direction, unsigned" is PROPOSED). PLAN-FIXED = fixed by the plan or design text. OWNER-RULED = an owner ruling fixes the value or default (relayed rulings are noted as such; none is in an authenticated record).

**Chosen from data?** YES = the value is to be fitted or calibrated on data. NO = fixed a priori by the owner. UNKNOWN = the documents do not establish it.

## 1. Table

### A. Descriptive-required (SCREEN_V2_REQUIRED, 25)

| # | Field path | What it controls | Candidate value | Source / rationale | Needed for (reads) | Chosen from data? | If YES: partition / trial-ledger entry | Status |
|---|---|---|---|---|---|---|---|---|
| A1 | `costs.accounting_mode` | Whether the 5/15 bps per side is all-in or additive to slippage | `all_in` | Plan 2.5 and Sheets D15 (l.291-300) recommendation (a); A-SCREEN 7 (D15). Kernel accepts only `all_in` (params.py). | D, S, A; K | NO | n/a | PROPOSED |
| A2 | `costs.components` | Itemized cost components (spread, fees, impact, slippage) behind the bps | NONE | A-SCREEN 7: "must be set (required)"; Sheets D15 gives no component values; Plan 2.1 says "itemized and not double-counted". Not read by the kernel. | D, S, A; none | NO | n/a | UNSET |
| A3 | `data.fetch_mode` | Loader approach / enumeration string recorded in the spec | `monthly_chunked_sip_v1` | A-SCREEN 7; Sheets D11 (l.235-245): approach ruled by owner ruling C5 (new monthly-chunked fail-closed SIP loader), the string "is defined in PR 2". Conditional on vendor storage/use answers (A-SCREEN 4). The approach is OWNER-RULED (C5); the string is not. | D, S, A; none | NO | n/a | PROPOSED |
| A4 | `data.vendor` | Historical SIP minute-bar vendor | Alpaca SIP historical (no spec string defined) | Sheets D03 (l.115-124) and A-SCREEN 7: conditional on feasibility F1 (history depth), F2 (delisted), F5 (licence for stored research use). A-SCREEN 4 lists F5 and delisted coverage as not established. | D, S, A; none | NO | n/a | PROPOSED |
| A5 | `execution.bar_timestamp_convention` | Start- or end-stamped bars | `start` | A-SCREEN 7 (D14): vendor FAQ and the probe are consistent with start-of-interval; "verify before RUN". Kernel accepts only `start`. | D, S, A; K | NO | n/a | PROPOSED |
| A6 | `execution.crossed_before_arm_policy` | What happens when price has crossed the trigger before the order is armed | `SKIP` | Sheets D14 (l.277); A-SCREEN 7. Sheets asks for sensitivity under the other policies. | D, S, A; K | NO | n/a | PROPOSED |
| A7 | `exit.halfday_offset_min` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | Minutes before the early close at which the flat exit is issued | `5` (12:55 ET on a 13:00 close) | Sheets D05 5g (l.151); A-SCREEN 7 "five minutes before the applicable session close". Reg l.91 lists the 5g number as possibly BLANK. Needs a verified calendar. | D, S, A; K | NO | n/a | PROPOSED |
| A8 | `exits.candidates` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | The closed exit set (<= 8, four families) | K = 7: E1 time exit; E2a fixed 2R, E2b fixed 3R; E3a breakeven at +1R then trail 1.0R, E3b trail 1.5R; E4a 50% out at +1R remainder EOD, E4b 50% out at +1R remainder trail 1.0R. Kernel param keys `r_multiple`, `trail_r`, `remainder` are the kernel's proposal. | A1 2 item 2 (l.24); Plan 2.2 (l.161-183); Sheets D19 (l.336-345); A-SCREEN 7 "K = 7 declared; freeze every parameter". No further fitting (A-SCREEN O-5). | D, S, A; **G**, K | NO for the set (frozen a priori at P0, R4). The **choice of one member** is data-derived. | Partition `development_selection` 2016-01-01 to 2019-12-31 only; rule `select_exit` (section 3.2); candidates tried K = 7; trial-ledger row per R8 (`registration.trial_ledger_id`), all K recorded; never the holdout 2022-2025 (R3) | PROPOSED |
| A9 | `exits.selection.eligibility.min_pf` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | PF floor for a candidate to be eligible | `1.0` (Sheets D17 / Plan 2.2 step 2) **and** `1.15` (A-SCREEN 6a, exploratory). Two values, not reconciled. | Sheets D17 (l.318): PF > 1.0 at base cost. A-SCREEN 6a: "PF (base) < 1.15 with mean > 0 -> REVISE". | S, A; **G** | NO | n/a | PROPOSED |
| A10 | `exits.selection.eligibility.min_trades` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | Trade floor for eligibility | `300` | Sheets D17 (l.318); A-SCREEN 6a ("< 300 trades or < 100 traded days"); Plan 2.2 step 2. | S, A; **G** | NO | n/a | PROPOSED |
| A11 | `exits.selection.score` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | The score that ranks eligible candidates | One-sided bootstrap lower bound of mean net R per trade (day-clustered). No spec string defined. | A1 2 item 3 (l.25); Plan 2.2 step 3; Sheets D19. A-SCREEN 6b: selection not implemented until adopted. | S, A; **G** | NO | n/a | PROPOSED |
| A12 | `exits.selection.stop_test` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | The selection-aware test that stops the program | Max-statistic bootstrap over K ("`max_stat_bootstrap`"), one-sided, alpha `0.05` (Sheets D17) **or** `0.10` (A-SCREEN 6a). Two levels, not reconciled. No spec string defined. | Plan 2.2 step 5 (l.180); Sheets D17 (l.318); A-SCREEN 6a row "Max-statistic test fails one-sided alpha 0.10". | S, A; **G** | NO | n/a | PROPOSED |
| A13 | `exits.selection.tie_tolerance_r` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | Delta in R within which the simpler family wins | `0` (A-SCREEN 6c, "proposed, not implemented") **or** `0.05` R ("illustrative placeholder", Sheets D19 l.341; vNext A3 row 9: "no basis in the documents"). | A-SCREEN 6c: "The 0.05 R placeholder is not adopted". Sheets D19: "fixed a priori on a cost scale, not from data". | S, A; **G** | NO (stated a priori) | n/a | PROPOSED |
| A14 | `fill.halt_policy` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | Treatment of halts and unavailable intervals for exits | `UNEXECUTABLE_DURING_UNAVAILABLE` (kernel string; kernel accepts only this) | A-SCREEN 7 and 1 item 3 (owner O-9 correction: not `treat_as_no_trade`). Sheets D05 5h (l.152) recommends the label `EXIT_UNAVAILABLE`: names differ. Source of halt flags is open (A-SCREEN 7). | D, S, A; K | NO | n/a | PROPOSED |
| A15 | `gates.basis` | Trade set the gates are computed on | `portfolio_constrained` (Sheets D18 l.330; Plan 5.1) **versus** "signal-level first, portfolio rerun for advancement" (A-SCREEN 7). Conflict. | Sheets D18; A-SCREEN 7 (D18) and 6d. | A (and D for interpretation); none | NO | n/a | PROPOSED |
| A16 | `gates.trade_unit` | What counts as one trade | One entry = one trade; all partial exits aggregated; net R = total net P&L of all exit fills / (entry qty x R_fill). No spec string defined. | Sheets D18 (l.330); A-SCREEN 7. | D, S, A; none | NO | n/a | PROPOSED |
| A17 | `governance.exposure_signed` | The owner's signed exposure ledger binding (who, when, ledger sha256) | NONE | Sheets D01 (l.91-100): sign only after the WP0.6 contact audit. A-SCREEN 5 R-c "Not done"; 6b: P3A exposes 2016-2019, to be recorded before the run. | D; **G** | NO | n/a | UNSET |
| A18 | `governance.registry_genesis_id` | The one registry this spec may open runs in | NONE | Created by `RunRegistry.enroll_new`, copied into the spec and manifest before freezing (schema.py l.455-459; Reg section 2). Manifest `approved_registry_genesis_id` is null. | D; **G** | NO | n/a | UNSET |
| A19 | `p3.criteria` | The P3 criteria the run is evaluated against | A-SCREEN 6a table, exploratory: `min_trades 300`, `min_traded_days 100`, dataset coverage `>= 98%`, bootstrap interval spans zero -> INSUFFICIENT EVIDENCE, max-stat one-sided alpha `0.10`, `PF 1.15`, top-5 removal, best day `> 20%` of net, neighbour PF `< 1.0`, non-positive mean in `>= 2 of 4` years, 15 bps stress. Sheets D17 differs: P3a 300 trades, PF > 1.0, alpha 0.05; P3b = P4 thresholds with 150 trades. | A-SCREEN section 2 row O-4 ("Criteria adopted with changes", relayed in session) and 6a; Sheets D17 (l.313-323). A-SCREEN 8 item 7 still lists "Adoption of 6 criteria" as an open owner act before any result. `screen/criteria.py` `CriteriaConfig` has no defaults. | D, S, A; **G** | NO (stated a priori, "not to be adjusted after seeing results") | n/a | OWNER-RULED (O-4 relayed; authenticated adoption record pending) |
| A20 | `p3.max_p3a_attempts` | Cap on recorded P3A runs for this spec hash | `1` | vNext A3 row 2 (owner-directed, unsigned); Reg M-lim-p3a (l.115, "standing recommendation 1"); A-SCREEN 6b (one attempt, no re-run with changed rules). Must equal the manifest value. Hazard: an unattainable minimum becomes a terminal STOP (vNext A3 row 8). | D; **G** | NO | n/a | PROPOSED |
| A21 | `p3.max_p3b_attempts` | Cap on P3B runs | `1` | Same as A20 (Reg M-lim-p3b l.116). | A; **G** (profile requires it set) | NO | n/a | PROPOSED |
| A22 | `risk.per_trade_pct` **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Risk budget per trade as percent of equity | `0.25` (percent of equity; units explicit) | Plan 2.1 (l.158) "0.25% ... (proposal)"; Sheets D05 5j; A-SCREEN 7 (D05: "portfolio sizing changes executed trades"). Unit hazard: the schema field is a bare float. | D; K | NO | n/a | PROPOSED |
| A23 | `signal.min_or_width_ticks` | Minimum opening-range width for a symbol-day to be eligible | `5` (A-SCREEN 7: "proposed fixed screening baseline, uncalibrated; later change = recorded variant"). Sheets D05 5b and Reg l.651: "NO VALUE PROPOSED (owner chooses after seeing the return-blind distribution)". | A-SCREEN 7; Sheets D05 5b (l.146); Reg section 24 C-EVID (l.1666) and section 32. No document gives a derivation for 5. | D; K | **UNKNOWN**: the Sheets route is YES (a return-blind OR-width distribution); the A-SCREEN route is NO (fixed, uncalibrated). Origin of "5" is undocumented. | If calibrated: see section 3 item 3 | PROPOSED |
| A24 | `signal.or_completeness_rule` | Completeness rule for the opening range | `0` confirmed DATA_GAP minutes in 09:30-09:59 (A-SCREEN 7). Kernel requires an int (max DATA_GAP minutes). Backlog l.693 proposes a different shape (`{max_data_gap_minutes, max_gap_fraction}` or enum). | Sheets D05 5a (l.145); A-SCREEN 6a and 7; screen/params.py. | D; K | NO | n/a | PROPOSED |
| A25 | `universe.n` | Number of names in the monthly PIT universe | `100` | Plan 2.1; Sheets D03 ("no basis to move it return-blind"); A-SCREEN 7 (D03). PIT member source and delisted coverage unverified (A-SCREEN 4). | D; K/data adapters (`pit_universe` takes `n`) | NO | n/a | PROPOSED |

### B. Deferred to stage 2 / advancement (SCREEN_V2_DEFERRED, 14)

The guard (P2/P3A) and the kernel read none of these. Setting them later gives a different spec hash (schema.py l.589-593).

| # | Field path | What it controls | Candidate value | Source / rationale | Needed for (reads) | Chosen from data? | If YES | Status |
|---|---|---|---|---|---|---|---|---|
| B1 | `controls.naive_orb.definition` | The naive-ORB control | "OR-high touch, no tick offset, same exits" (example only) | Plan WP2.5 (l.452); Sheets D13 (l.262-263). | S, A; none | NO | n/a | PROPOSED |
| B2 | `controls.random_entry.invalid_draw_policy` | Random-baseline draws with `R_pre <= 0` | Count as `NOT_EXECUTABLE`, preserve the denominator; redraw procedure frozen | Plan WP2.7A (l.480-486); Sheets D06 (l.166). | S, A; none | NO | n/a | PROPOSED |
| B3 | `controls.random_entry.repetitions` | Random-baseline repetitions | NONE ("at least 10,000" in Sheets D06 refers to the selection test and G4/G5, not stated for this field) | Sheets D06 (l.166); Plan WP2.5 "lock ... repetition count". | S, A; none | NO | n/a | UNSET |
| B4 | `controls.random_entry.seed` | Random-baseline seed | NONE ("fixed seeds") | Sheets D06; A-SCREEN 6c "fixed, recorded seeds". | S, A; none | NO | n/a | UNSET |
| B5 | `exits.complexity_order` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | Family order that breaks exact ties | `[time, fixed_r, trailing, scale_out]` | Plan 2.2 (ranks 1 to 4) and Appendix A comment (l.~957); vNext A3 row 9 (family-level order; per-candidate rank withdrawn). Within-family tie-break is an unset owner item (Backlog l.989). | S, A; none (selection.py would read it) | NO | n/a | PROPOSED |
| B6 | `registration.related_programs` | Relationship to ORM-001 | Option (b): shared trial ledger and multiplicity family, separate specs. No value shape defined; ORM-001 has no spec or code (vNext A1.2d). | Sheets D09 (l.216); Reg l.96. Numeric overlap limit and reviewers: owner-stated, none proposed. | A; none | NO | n/a | PROPOSED |
| B7 | `stats.alpha_one_sided` | One-sided alpha for bootstrap tests | `0.05` (Sheets D06 l.166; Reg l.92) **versus** `0.10` for the exploratory max-statistic test (A-SCREEN 6a). | Same sources. | S, A; none | NO | n/a | PROPOSED |
| B8 | `stats.bootstrap.block_len` | Mean block length (days) of the stationary bootstrap | `10` trading days | A-SCREEN 6c; Sheets D06: "fixed a priori (not estimated from RANGE-002 data)", precedent is the platform's daily `BLOCK_LEN = 10`, validator confirms or replaces. vNext A3 row 6 says "no value proposed". | S, A; none | NO per Sheets D06. The precedent's own origin is **UNKNOWN** (see section 4). | n/a | PROPOSED |
| B9 | `stats.bootstrap.ci_type` | Interval type | "percentile of the recentered null" (Sheets D06 l.166); estimation interval "kept distinct" (A-SCREEN 6c), type not stated. | Sheets D06; A-SCREEN 6c. | S, A; none | NO | n/a | PROPOSED |
| B10 | `stats.bootstrap.confidence_level` | Confidence level | NONE | Not stated in any source (alpha 0.05 is a test level; the preparer does not infer a level). | S, A; none | NO | n/a | UNSET |
| B11 | `stats.bootstrap.method` | Resampling method | Stationary bootstrap of consecutive trading-day clusters | A-SCREEN 6c; Sheets D06 option (a). Ruling C11: method deliberately not chosen in code. | S, A; none | NO | n/a | PROPOSED |
| B12 | `stats.bootstrap.reps` | Resamples | `10,000` | A-SCREEN 6c; Sheets D06 ("at least 10,000"). | S, A; none | NO | n/a | PROPOSED |
| B13 | `stats.bootstrap.seed` | Bootstrap seed | NONE ("fixed, recorded seeds") | A-SCREEN 6c; Sheets D06. | S, A; none | NO | n/a | UNSET |
| B14 | `stats.hypothesis_family` | Confirmatory family and count | Holm over {G4, G5}, count 2 (option (a)); P3a max-statistic over K is separate | Sheets D02 (l.102-113); vNext A3 row 7. Shape open (Backlog l.699 proposes `{members, mode}`). | S, A; none | NO | n/a | PROPOSED |

### C. Unmodelled execution settings (SCREEN_V2_UNMODELLED, 9)

The bar-level kernel does not simulate these. They may stay null; if present they are carried as UNMODELLED and imply no execution realism. They are needed before any executor or P5 work (D14).

| # | Field path | What it controls | Candidate value | Source / rationale | Needed for (reads) | Chosen from data? | If YES | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | `execution.ack_latency_ms` | Broker acknowledgement latency | NONE | Sheets D14 (l.280): "owner states numbers after F3/F4", set conservatively high versus measured paper latency. | A; none | NO (a measured paper latency would be execution data, not strategy data; not established) | n/a | UNSET |
| C2 | `execution.eod_lead_s` | Seconds before 15:55 at which the flat intent is issued | NONE | Sheets D14 (l.283): owner states seconds. | A; none | NO | n/a | UNSET |
| C3 | `execution.order_reservation_policy` | Cash/risk reservation | Reserve at submission, release on cancel/expiry/fill | Sheets D14 (l.284); Plan 3.3. | A; none | NO | n/a | PROPOSED |
| C4 | `execution.order_type` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | Stop order type | NONE | Sheets D14 (l.278): decide after the F3 broker capability report; options stop-market, stop-limit, emulated. | A; none | NO | n/a | UNSET |
| C5 | `execution.stop_protection_policy` **[Advisory: 方炳雄 (Fang Bingxiong), exit/take-profit design; advisory only, no gate sign-off]** | When the protective stop is attached | Stop attached only after the entry fill is acknowledged and sized | Sheets D14 (l.281); Plan WP5.2. | A; none | NO | n/a | PROPOSED |
| C6 | `execution.submit_latency_ms` | Order submit latency | NONE | Sheets D14 (l.280). | A; none | NO | n/a | UNSET |
| C7 | `execution.tie_break` | Order of simultaneous events across symbols | NONE. Options in Sheets D14 (l.282): seeded hash order or permaticker ascending; "Owner picks". The kernel scheduler currently breaks ties by symbol ascending (`screen/scheduler.py` l.6), which is neither option (see Note 4). | Sheets D14; Plan R12 (tie-breaking frozen before results). | D (scheduler), A; none | NO | n/a | UNSET |
| C8 | `execution.vendor_delay_ms` | Vendor publication delay | NONE | Sheets D14 (l.279), F4: verify against documentation and a sampled day; "Must not be assumed". | A; none | NO | n/a | UNSET |
| C9 | `fill.slippage_model` | Separate slippage model | "No separate slippage model if D15 = all-in; otherwise itemized" (conditional on A1) | Sheets D05 5i (l.153). | A; none | NO | n/a | PROPOSED |

### D. Exempt under screen profile v1 (SCREEN_V1_EXEMPT, 18): required again for the full profile / portfolio rerun

| # | Field path | What it controls | Candidate value | Source / rationale | Needed for (reads) | Chosen from data? | If YES | Status |
|---|---|---|---|---|---|---|---|---|
| D1 | `governance.economic_thesis_sha` | Hash of the signed economic thesis | NONE | Sheets D13 (l.263): must be written by humans (WP0.9). | A; none | NO | n/a | UNSET |
| D2 | `governance.roles` | Named role holders | NONE as a spec value. Owner ruling O-1 (relayed): the named person is retained as Independent Validator only; Research Lead appointment pending (A-SCREEN section 2). | Sheets D08 (l.193-208); A-SCREEN O-1, O-10. | A; none | NO | n/a | UNSET |
| D3 | `p5.account_id` | P5 paper account | NONE. Option B (hashed marker `p5.account_binding` = `deferred_to_p5_activation`) is proposed and exists only in a local schema candidate. | Sheets D07 (l.176-178); vNext A3 row 4. | A; none | NO | n/a | UNSET |
| D4 | `p5.cost_ratio_contract` | Cost-ratio calculation | `sum(realized shortfall) / sum(modeled cost)` over trades with positive modeled cost; undefined cases reported, never auto-pass | Sheets D07 (l.178). | A; none | NO | n/a | PROPOSED |
| D5 | `p5.degradation_tolerance` | Allowed degradation | NONE | Sheets D07; Addendum A2 (all values BLANK). | A; none | NO | n/a | UNSET |
| D6 | `p5.shadow_acceptance` | Shadow-run acceptance rule | Zero orphan signals, zero duplicate intents, zero look-ahead discrepancies over a number of sampled days; the number is "not proposed" | Sheets D16 (l.307). | A; none | NO | n/a | PROPOSED |
| D7 | `diagnostics.taxonomy` | Explanatory diagnosis labels | The eight labels in Plan WP3.4 (explanatory only) | Sheets D16 (l.305-307). | A; none | NO | n/a | PROPOSED |
| D8 | `gates.max_dd` | Drawdown comparator | Random-entry portfolio under identical capital, costs and sizing as primary; SPY as reference. No numeric value. | Sheets D10 (l.229). | A; none | NO | n/a | PROPOSED |
| D9 | `gates.win_rate` | Win-rate gate regime | Platform `> 50%` gate applies until a D10 deviation is signed; both evaluations displayed. Required key, no default. | Owner ruling C3; Sheets D10 (l.227); A1 section 8. | A; none | NO | n/a | OWNER-RULED (regime; spec value shape still OpenValue) |
| D10 | `gates.yearly` | Yearly consistency | `>= 3 of 4` years PF > 1.0 (design 6, "recommended, pending approval"); a per-year minimum trade count is not set | Sheets D04 (l.126-135). | A; none | NO | n/a | PROPOSED |
| D11 | `risk.daily_loss_limit` **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Daily loss cap | NONE | Sheets D05 5j (l.154): "owner to state numbers"; conservative defaults per CLAUDE.md. Scheduler reads it and fails closed when null (A-SCREEN 3b). | A (portfolio rerun, 6d); none | NO | n/a | UNSET |
| D12 | `risk.fill_risk_tolerance` **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Tolerance when actual risk exceeds budget | NONE | Sheets D05 5c; Reg l.651 "tolerance value NO VALUE PROPOSED". | A; none | NO | n/a | UNSET |
| D13 | `risk.gross_cap` **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Gross exposure cap | NONE | Sheets D05 5j. Scheduler fails closed when null. | A; none | NO | n/a | UNSET |
| D14 | `risk.max_concurrent` **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Max concurrent positions | NONE | Sheets D05 5j. Scheduler fails closed when null. | A; none | NO | n/a | UNSET |
| D15 | `risk.max_participation` **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Participation cap | NONE | Sheets D05 5j. | A; none | NO | n/a | UNSET |
| D16 | `risk.per_name_cap` **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Per-name cap | NONE | Sheets D05 5j. Scheduler fails closed when null. | A; none | NO | n/a | UNSET |
| D17 | `stats.regime.criterion` | Single-regime-dependence criterion | Both regimes and both halves positive net mean R with a minimum trades-per-cell; a P&L share cap value is NONE | Sheets D12 (l.251-252). | A; none | NO | n/a | PROPOSED |
| D18 | `stats.regime.definition` | Regime definition | SPY prior close vs 200-day SMA (causal, through the prior close) | Sheets D12 (l.252). | A; none | NO | n/a | PROPOSED |

### E. Not a spec field, but needed

| # | Item | What it controls | Candidate value | Source / rationale | Needed for (reads) | Chosen from data? | If YES | Status |
|---|---|---|---|---|---|---|---|---|
| E1 | PIT price basis (`data.adjustment`; no schema field) | The single price basis for OR, stop, fills and the universe | NONE as an owner value. Code hard-codes intraday bars `raw` (`data/fetch_adapter.py` `REQUIRED_ADJUSTMENT`) and the PIT universe on Sharadar SEP split-adjusted `close x volume` with the $10 floor on `closeunadj` (`data/pit_universe.py`). The vendor's adjustment convention is unverified (A-SCREEN 4). Schema proposal: `Literal["raw","split_adjusted","split_dividend_adjusted"]`. | Backlog O-2 (l.383, l.487); Schema Change Batch Proposal item 1 (l.45); Plan WP1.6. | D (a mixed basis corrupts the screen); data adapters | NO | n/a | UNSET (a developer default exists in code, not an owner value) |
| E2 | Category-to-common-stock mapping | Which vendor `category` strings count as common stock | NONE. `store_adapter.build_month_from_store` takes `common_stock_categories` from the caller; no document lists the strings. Plan 2.1 says "US common stocks on major exchanges"; "major exchanges" is not defined. | `data/store_adapter.py` l.272, l.214; `data/manifest.py` l.35; Plan 2.1 (l.148). | D; data adapters | NO (it is a vendor-vocabulary mapping; verification needs the vendor master, not returns) | n/a | UNSET |
| E3 | ADV ranking tie-break | Order among equal-ADV names at the top-N cut | Permaticker ascending (`scored.sort(key=(-adv, permaticker))`, `data/pit_universe.py` l.203); Backlog O-6 proposes the same as "fixed by plan" | Backlog O-6 (l.387, l.491). | D; data adapters | NO | n/a | PROPOSED |
| E4 | PIT rebuild timing and `lookback_calendar_days` | When the monthly universe takes effect; ADV lookback window in calendar days | Effective from the first session of each month using inputs dated <= the prior trading day (Sheets D03 l.120; Backlog O-6). `lookback_calendar_days` is a caller argument with no proposed value (must be >= `adv_window`). | Sheets D03; Backlog O-6; `store_adapter.py` l.272. | D; data adapters | NO | n/a | PROPOSED |
| E5 | `data.exclusion_bound` (proposed field) | Acceptable share of universe exclusions | NONE | `data/pit_universe.py` docstring ("UNSET"); Backlog Q-B4 (l.456, l.522). | D (data-quality blocker) | NO | n/a | UNSET |
| E6 | Manifest `p3_attempt_limits.{p3a,p3b}` | The governed attempt limits; must equal spec A20/A21 | `1` / `1` (owner-directed, unsigned) | `RANGE-002_governance_manifest.json` (all null); Reg M-lim (l.115-116) and section 3; vNext A3 row 2. | D; **G** (freeze and guard require both) | NO | n/a | PROPOSED |
| E7 | Genesis id: manifest `approved_registry_genesis_id`, `approved_by`, `approved_on` | The approved registry identity (all-or-nothing triple) | NONE | Manifest (all null); Reg l.53, l.178-193. Pairs with A18. | D; **G** | NO | n/a | UNSET |
| E8 | Exposure ledger (content) | Signed record of which periods and programs touched which data | NONE; ledger does not exist. Contact audit WP0.6 not done. | Sheets D01; Reg C-EVID section 32 item 7; A-SCREEN R-c and 6b. Pairs with A17. | D; **G** (via A17) | NO | n/a | UNSET |
| E9 | Trial-ledger entry / `registration.trial_ledger_id` | The ledger row for every run (rule R8) | Assigned by `run_registry` at run registration; not a P0 decision (`_NON_P0_NULLABLE`) | Plan R8 (l.106); schema.py l.43, l.265. A-SCREEN R-g "Run registered first". | D; G (registration before compute) | NO | n/a | UNSET |
| E10 | Dataset coverage threshold | Minimum dataset coverage before a run is valid | `98%` (proposed spec field `data.coverage_min` "fixed 0.98") | Plan WP1.8 and 9.3; Sheets 3 table row 7 ("98% threshold already in design"); A-SCREEN 6a; Backlog l.522. | D | NO | n/a | PLAN-FIXED |
| E11 | `risk.initial_equity`, `risk.equity_basis`, `risk.over_budget_rule` (proposed fields) **[Advisory: 肖学焦 (Xiao Xuejiao), risk/loss-control; advisory only, no gate sign-off]** | Starting equity and sizing basis for the portfolio rerun | NONE | Backlog Q-B4 (l.456, l.522); Schema Change Batch O-3. | A (portfolio rerun) | NO | n/a | UNSET |
| E12 | Other Q-B4 proposed fields: `controls.stage1_criteria`, `controls.time_shuffle`, `controls.no_information`, `data.minute_reconciliation.*`, `data.budget`, `universe.pit_rule` | Control definitions and data-quality tolerances | NONE (each needs an individual written definition and independent statistical review; vNext A3 row 6) | Backlog Q-B4 (l.456); vNext A3 row 6. | S, A | NO | n/a | UNSET |
| E13 | NYSE session calendar and early-close list | Session days and close times | NONE as an owner value; `screen/session_calendar.py` holds early closes explicitly, "to be verified against vendor session data before RUN" | A-SCREEN 3b and 8 item 8. | D; K | NO | n/a | UNSET |

## 2. Counts

Per group:

| Group | Rows | UNSET | PROPOSED | PLAN-FIXED | OWNER-RULED |
|---|---|---|---|---|---|
| A. Descriptive-required | 25 | 3 | 21 | 0 | 1 |
| B. Deferred | 14 | 4 | 10 | 0 | 0 |
| C. Unmodelled | 9 | 6 | 3 | 0 | 0 |
| D. Exempt under v1 | 18 | 10 | 7 | 0 | 1 |
| E. Not a spec field | 13 | 9 | 3 | 1 | 0 |
| **Total** | **79** | **32** | **44** | **1** | **2** |

(a) Rows per status: **UNSET 32, PROPOSED 44, PLAN-FIXED 1, OWNER-RULED 2** (of 79). The two OWNER-RULED rows are `p3.criteria` (O-4, relayed in session, not yet an authenticated record, A-SCREEN 8 item 7 still open) and `gates.win_rate` (ruling C3, regime only). No row is both signed and frozen: the Reg and vNext report 0 formally approved decisions.

## 3. Parameters selected from data

### 3.1 What the repository establishes

Nothing in the spec baseline is a fitted number. The design is: every value is fixed a priori by the owner at P0 (R4: "Do not tune"; R9; A-SCREEN O-5: "no added fitted parameters"). Exactly **one** choice is made from data, and one more is contested:

| # | Item | Data-derived? | Governing rule and location |
|---|---|---|---|
| 1 | **Which one exit configuration** is used, chosen among the frozen K = 7 candidates | YES (the only sanctioned data-selection) | A1 Amendment 1 item 3 (l.25) and item 4 (l.26): a selection rule frozen in P0 "chooses exactly one configuration on the P3a data"; no configuration may be added, removed or re-parameterized after P0 freeze. Plan WP4.1 (l.587-607): P3a runs all K, `select_exit` and `max_stat_bootstrap` write a `SelectionRecord` hashed and appended to the run registry **before** unsealing. Plan R18 (l.115): "The exit is chosen by the frozen selection function, never by a person or an agent." Plan R4 (l.102). |
| 2 | The **take-profit multiples** (k in {2, 3}), trail multiples (t in {1.0, 1.5}), scale-out fraction (50% at +1R) | **NO.** They are the a priori candidate parameters. A1 2: "Parameters are expressed in R units"; the set is closed at P0. There is no continuous fit. The data picks among members, it does not tune a multiple. | A1 Amendment 1 item 2 and 4; Plan 2.2 (l.161-183); A-SCREEN 7 (D19) and O-5. |
| 3 | `signal.min_or_width_ticks` | **UNKNOWN / contested.** Sheets D05 5b (l.146) and Reg section 24 and 32 say the number is "set from the return-blind distribution of OR width in ticks ... Cannot be chosen blind; must not be tuned on P&L". A-SCREEN 7 proposes a fixed `5`, "uncalibrated". The owner must say which route applies. | Sheets D05 5b; Reg l.651, l.1666 (C-EVID); Reg section 32 (Amendment E1, PROPOSED, NOT SIGNED). |

### 3.2 Item 1: the exit selection

| Question | Answer |
|---|---|
| Partition it may be chosen on | `partitions.development_selection` = **2016-01-01 to 2019-12-31** (P3a). schema.py l.139 `_DEV_SEL`, asserted equal in `Partitions`; A1 Amendment 2 table (l.34-38). |
| Other partitions | `development_confirmation` 2020-01-01 to 2021-12-31 (P3b) runs the **selected exit only**; it must not be used to choose (A1 Amendment 2). |
| Holdout | **Never.** `partitions.holdout` = 2022-01-01 to 2025-12-31 (schema.py l.141) is opened once, for the selected exit only (Plan R3, l.101; WP4.2). The exposed window 2026-01-01 to 2026-07-31 (schema.py l.142) is never used in a decisive run (Plan R2, l.100). |
| Guard authorization for a screen-profile spec | Only `(P2, REPLAY_RNG001)` and `(P3A, DEVELOPMENT_SELECTION)` (A-SCREEN 3a, `_SCREEN_PROFILE_ALLOWED`); P3B, P4, P5 are refused. |
| Trial-ledger entry required | Rule **R8** (Plan l.106): every run is a trial-ledger row, including failed, aborted and defect runs; `run_registry` writes **before** compute; an unledgered result is inadmissible. Plan WP4.2 (l.613): "The trial ledger still records all K P3a candidates." The row is addressed by `registration.trial_ledger_id`, assigned by the registry (schema.py l.43, l.265). A-SCREEN R-g: "Run registered first; trial-ledger row (R8)". Attempt budget: one P3A run (A20); the run consumes it at `capability_issued`. |
| Additional recorded artefacts | The `SelectionRecord` (selected id or STOP, scores, eligibility, tie decision, selection-aware p-value, input hashes), hashed before unsealing (Plan WP4.1 step 3). The exposure ledger records that 2016-2019 is exposed for all K candidates (A1 Amendment 2 "Exposure"; A-SCREEN 6b). |
| Selection rule (verbatim sources) | Among eligible candidates (trades >= D17 minimum and PF > 1.0 at base cost, Plan 2.2 step 2), pick the highest one-sided bootstrap lower bound of mean net R per trade (day-clustered); a candidate within the pre-registered tolerance delta of the best goes to the lower complexity rank; STOP if none is eligible or the selection-aware max-statistic test over K fails at the D17 level. A1 Amendment 1 item 3 (l.25); Plan 2.2 (l.174-181) and WP4.1. Implemented as a pure function `select_exit` (Plan 2.2 step 6). A-SCREEN 6c proposes delta = 0 R and states the rule is not implemented. Every parameter of the rule (delta, eligibility, alpha, block length, reps, seed) is unset or proposed, see A9 to A13 and B7 to B13. |
| Number of candidates tried | **K = 7** in the declared family (E1, E2a, E2b, E3a, E3b, E4a, E4b; cap 8; A1 item 2; Plan 2.2). All K run once on P3a under one attempt (A20 = 1). Prior search over RANGE-002 exits: none is recorded; A1 section 9 and A-SCREEN state no RANGE-002 results exist, so the documented prior count is 0, but whether any informal exploration occurred outside the repository is **UNKNOWN**. The RNG-001 report records its own variant search (baseline A, B, D, E-vwap+gate and several sigma configs) on a different strategy and window; it is not counted as RANGE-002 trials and must not seed the candidate set. The count for the ledger and the multiplicity family is K = 7 (Plan WP4.2 l.613; Sheets D02). |
| Never touches holdout | The selection reads only `development_selection` 2016-01-01 to 2019-12-31. It may never read `holdout` 2022-01-01 to 2025-12-31 (R3), the exposed 2026-01-01 to 2026-07-31 window (R2), or the P3b partition for choosing. |
| Screen-profile qualification | A-SCREEN 6b: the stage-1 descriptive screen "cannot select a formal winner"; selection (stage 2) is not implemented and waits for adoption of 6b and 6c. Results are "not independent confirmation". |

### 3.3 Item 3: `signal.min_or_width_ticks` if it is calibrated

| Question | Answer |
|---|---|
| Partition | Not fixed by the spec. Reg section 32 Amendment E1 item 3 (PROPOSED, NOT SIGNED) permits dates within 2016-01-01 to 2021-12-31 only and excludes holdout and exposed windows. Preparer's observation (not a source rule): 2020-2021 is the P3b confirmation partition, so using it would pre-expose P3b; the conservative reading is 2016-2019 only. The owner should say. |
| Holdout | Never: excluded by Amendment E1 item 3. |
| What may be read | Only 09:30:00 to 09:59:59 high, low, volume and a present flag; no bar at or after 10:00:00; no return, trigger or outcome (E1 items 2, 4, 5). |
| Ledger entry required | Exposure-ledger entry of kind `return_blind_feasibility_pull` written and signed **before** acquisition, with the output summary SHA-256 recorded after release (Reg section 32 item 7). Whether a **trial-ledger** row is also required is **UNKNOWN**: R8 speaks of "runs", and this pull is not a guarded run; the documents do not say. |
| Status of the authorization | Amendment E1 is PROVISIONAL POLICY DIRECTION, NOT SIGNED; "No acquisition is authorized. D05 5a / 5b stay PENDING." (Reg l.2217 area, section 32 "Status of C-EVID"). The A-SCREEN probe was counts and timestamps only and produced no price or width value. |

## 4. Values already derived from data: must not be reused as a priori baselines

| Source | Value(s) | Derived from | Why it must not be used as a baseline |
|---|---|---|---|
| `RNG-001_Rejection_Summary_Report_2026-10-09.md` sections 3.1 to 3.5 and 6 | IS PF 1.37 and OOS PF 0.92; 102 trades, PF 1.271, mean $15.14, win rate 55%, bootstrap CI [-$19.74, +$57.53]; walk-forward PFs 1.691, 1.141, 1.325, 0.886; funnel: 46.7% fills, 29.2% stop, 49.0% "target hit before entry", 62.7% reversed, 17.8% reached target; baseline PF 0.70 to 0.81; E-vwap+gate PF 1.53 full sample, 0.68 train, 2.68 test; day-level CI [-0.010%, +0.181%]; strategy settings `entry_sigma=2.0`, `exit_sigma=0.5`, `stop_sigma=3.0` | Alpaca **IEX 5-minute** bars, 2026-01-02 to 2026-06-12 (PLTR; 18 names / 126 sessions for the entry study). This is `partitions.exposed` (2026-01-01 to 2026-07-31). | Exposed data that gave rise to the RANGE-002 idea (Sheets D01 l.94; R2). None of these figures may set a RANGE-002 threshold, target, width, block length or criterion. Plan WP2.6 uses 102 / 1.271 / the CI only as engine-replay targets under `REPLAY_RNG001`, not as baselines. The report's own caveat: single regime, about 6 months, optimistic fills. |
| Same report, section 3.4 | "49% target hit before entry" | Same exposed archive | Named as the **origin of the hypothesis** (Sheets D01, D09 origin disclosure, vNext). It motivates the idea; it must not calibrate the entry offset, the stop, the exit multiples or the OR rule. |
| Reg / Sheets D06 | `BLOCK_LEN = 10` (platform daily value in `services/market_projection/validate.py`) used as the only precedent for B8 | Another program's daily-layer work; how that value was chosen is **UNKNOWN** from these documents | Not RANGE-002 data, but the origin is not shown to be a priori. If it was fitted on 2016-2025 daily data, that contact belongs in the D01 audit. Validator "confirms or replaces" (Sheets D06 l.166). |

I found **no** RANGE-002 baseline value in the repository documents that is stated to have been computed from RNG-001 or other exposed data. "Not stated to be derived" is not the same as "shown to be a priori": see 4.b.

## 5. (b) Parameters whose value is only a proposal derived from, or possibly touched by, exposed data (contamination risk)

None is established as derived from exposed data. The following are flagged because the origin is undocumented or the route to a value would touch data:

1. **`signal.min_or_width_ticks` = 5 (A23).** No derivation is given. If it is later calibrated from OR-width distributions (the Sheets route), it becomes data-derived on development bars and needs Amendment E1 and an exposure-ledger entry first. The A-SCREEN return-blind probe (counts and timestamps only, 2016 to 2021 sampled dates) did not print prices, so it could not have produced 5.
2. **`stats.bootstrap.block_len` = 10 (B8).** Precedent is another program's daily value; its origin is UNKNOWN.
3. **`exits.selection.eligibility.min_pf` = 1.15, `stop_test` alpha 0.10, `min_traded_days` 100, top-5 removal, best-day 20%, 2-of-4 years (A9, A12, A19).** The A-SCREEN calls these "the owner's exploratory screening criteria"; no document states how they were chosen and none ties them to RNG-001. They differ from the D17 sheet values (PF > 1.0, alpha 0.05). Origin UNKNOWN; the preparer asserts neither contamination nor independence.
4. **Exit parameters 2R, 3R, +1R, trail 1.0R and 1.5R (A8).** A1 calls a fixed 2R target "arbitrary hand-set" and states no data were seen (A1 2 and 9). Design v0.4 variant B is 2R. No derivation is documented; the idea came from RNG-001's exposed funnel, so the hypothesis (not these numbers) is exposure-linked.
5. **`tie_tolerance_r` 0.05 R (A13).** Stated to be an illustrative placeholder with "no basis"; flagged so it is not adopted as if it had one.
6. **`risk.per_trade_pct` 0.25 and `universe.n` 100 (A22, A25).** Design proposals ("no basis to move it return-blind"); not data-derived per the documents.
7. **Any value in groups B to D labelled "validator confirms" (B7 to B13).** To be confirmed on synthetic data only (Sheets D06 l.169); using RANGE-002 or exposed data would contaminate it.

## 6. (c) Open owner decisions that change the spec hash

The hash covers everything except `signoff`; `profile` is in the payload when present (schema.py `hashable_payload`). A change to any of the following produces a different spec hash. Manifest values are not in the hash but must equal the spec fields.

1. **Profile choice and version.** v1 vs v2 (different `required_fields_sha256`; v2 also pins `unmodelled_fields_sha256`); full profile (no `profile` key) vs screen. A screen spec and a same-content full spec have different hashes, so a COMPLETED screen P3A cannot satisfy P3B or P4 phase order for a full spec (A-SCREEN 3a).
2. **Deferral.** Leaving group B null in the screen spec and setting it for stage 2 is a different spec hash (schema.py l.589-593); stage 2 on the same run is an owner decision. Attempt budgets are counted per lineage and phase across hashes, so a re-freeze does not reset them (vNext A2.7a).
3. **Every group A value** (A1 to A25), including the unreconciled pairs: `min_pf` 1.0 vs 1.15 (A9), `stop_test` alpha 0.05 vs 0.10 (A12), `tie_tolerance_r` 0 vs 0.05 (A13), `gates.basis` portfolio vs signal-level (A15), `halt_policy` string (A14).
4. **Exit set content:** candidate ids, params, family order (A8, B5). No change after freeze (R4).
5. **`p3.criteria` exact content** (A19), recorded "exactly" (A-SCREEN 7).
6. **Attempt limits** (A20, A21) and manifest equality (E6).
7. **Genesis id and exposure binding** (A17, A18, E7, E8).
8. **Schema-changing decisions** (change the field set or skeleton, hence the hash of any spec): `p5.account_id` vs `p5.account_binding` option B; G10 comparator-policy binding G10-C1 (`governance.comparator_policy_sha256`, P0 count 86 to 87); Q-B4 proposed fields (`data.adjustment` and others, E1, E5, E11, E12); per-candidate `rank` withdrawn. All sequenced before any real freeze (vNext A2.8 K6; Schema Change Batch Proposal).
9. **`stats.adjustment`** (`holm` preset vs `fixed_sequence`, D02), which must be confirmed explicitly, not inherited (Reg l.1660).
10. **Price basis (E1) and category mapping (E2)** if they are placed in the spec; today they live in code and adapters, outside the hash (a gap: the hash would not show a change).

## 7. Notes and source conflicts

1. **Not-yet-adopted status.** A-SCREEN section 7 states "nothing is adopted"; its section 2 row O-9 says "adoption pending". Only O-4 (criteria) is recorded as adopted-with-changes, and section 8 item 7 still lists the adoption act as open. Treat A19 accordingly.
2. **Two sets of criteria.** D17 sheet (PF > 1.0, alpha 0.05, 300 trades, P3b 150) vs A-SCREEN 6a (PF 1.15, alpha 0.10, 300 trades or 100 traded days). A-SCREEN labels its set exploratory and says the governing P3b/P4 criteria are preserved.
3. **Kernel-constrained values.** `screen/params.py` refuses any value other than: `all_in`, `start`, `UNEXECUTABLE_DURING_UNAVAILABLE`, an int `or_completeness_rule`, a SIP feed. The owner cannot adopt a different value for these without a code change. The bar-level kernel also ignores `costs.components`.
4. **Developer defaults in code (R9).** The scheduler ties by symbol ascending (not an offered D14 option and keyed by ticker, not identity), the fetch adapter requires `raw`, and the PIT universe fixes `SEP_SPLIT_ADJUSTED`. These are engineering choices that need an owner decision or an explicit "plan-fixed" declaration (Backlog O-6, O-2).
5. **`risk.per_trade_pct` units.** A-SCREEN 7 says percent of equity with "explicit units"; the schema type is a bare positive float, so 0.25 could be misread as 25%.
6. **Vendor questions block any data step.** Storage, use on the AWS host, sharing, adjustment and delisted coverage (A-SCREEN 4) are unanswered; "Do not fetch or store bulk history until (1)-(3) are answered."
7. **Not covered.** No value was computed, fetched or tested. Counts in section 2 follow the status rules in the Legend and may be re-cut by the owner (for example, A3 could be shown as OWNER-RULED for its approach).
