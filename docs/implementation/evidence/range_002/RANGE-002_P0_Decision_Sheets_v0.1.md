# RANGE-002 — P0 Owner Decision Sheets v0.1

| Field | Value |
|---|---|
| Purpose | Plan v0.5 §11.3 action 8: one sheet per P0 decision (D01-D19) and per open item (C2/D09, C10, C12, A1), so the owner can sign quickly |
| Date | 2026-10-09 |
| Status | **DRAFT FOR OWNER REVIEW. Nothing here is a decision.** Every "Recommendation" is the preparer's proposal, marked *(not a decision)*. Every signature row is blank and must be filled by the named human only. |
| Data accessed | None. No returns, P&L, win rates or profit factors were computed or viewed. |
| Sources | Research design v0.4 (Chinese DOCX, quoted in translation with section numbers; DOCX not copied); Implementation Plan v0.5 (§2.1, §2.2, §5, §10, WP2.1A, WP2.2, App. A); Addendum A1 (draft, unsigned); `governing_reconciliation.md` (C1-C13); `recon.md` |
| Precedence reminder | Design v0.4 + A1 governs. Until A1 is signed, design v0.4's fixed variants A/B govern and **no spec may be frozen under either form** (plan header). |
| Not covered | Gate thresholds are not open: G0-G10 stay as in design §6. Values below only fill spec keys that are `null` in plan Appendix A. |

How to read a sheet: **Statement** (what is being decided) / **Source** (design v0.4, A1, plan) / **Options** / **Recommendation (not a decision)** / **Spec key** / **Blocks** / **Return-blind evidence** / **Owner row**.

---

## 1. Summary table, ordered by downstream blocking

"Blocks" lists PRs from plan §8. All 19 decisions plus A1 are required for the P0 exit gate (plan WP0 exit); the order below is by how much *other* work each one unblocks, i.e. the sequence in which to ask for signatures.

| Rank | Item | One-line ask | Spec key | Directly blocks | Recommendation (not a decision) in brief |
|---|---|---|---|---|---|
| 1 | **A1 signature** | Sign the exit-selection, P3a/P3b split and D13-D19 amendment | (governing doc) | Validity of D02, D13-D19; any spec freeze; PR 13+ | Sign after D19/D17 sheets are reviewed, or amend |
| 2 | **D08 roles** | Name the 4 roles, with segregation | `governance.roles` | Every other sign-off (reviewers of D19, D13, D09/C2, WP0.9-0.12) | Four distinct humans; no AI role; owner = sole P6 approver |
| 3 | **D06 stats parameters** | Bootstrap method, block length, reps, CI, alpha, seeds, baseline reps | `controls.*`, `stats.*` | D19 score, D17 STOP test, D02, PR 9, 11, 12, 12A | Stationary day-clustered bootstrap, one-sided, alpha 0.05, fixed seeds |
| 4 | **D19 exit set + selection** | Confirm/replace the 7 candidates, order, delta, eligibility | `exits.*` | PR 8 (exit mechanics), 11, 13; A1 | Adopt proposed K=7 after trading-expert review; delta set a priori |
| 5 | **D05 fill/risk values** | OR completeness, min OR width, R rules, tick, half-day, halt, risk limits | `fill.*`, `risk.*`, `exit.*`, `signal.*` | PR 6, 8, 12A, 13 | Adverse/skip-on-doubt defaults; numeric limits need owner |
| 6 | **D14 execution contract** | Timestamps, latency, crossed-before-arm, order type, EOD, tie-break | `execution.*` | WP0.12, PR 4A, 8, 12A, 15 | SKIP on crossed-before-arm; order type after broker check |
| 7 | **D15 cost accounting** | All-in vs additive bps | `costs.accounting_mode`, `costs.components` | PR 8, 11 | All-in debit (plan recommends); stress gate G3 binds |
| 8 | **D03 data/universe + D11 + C12** | N, PIT timing, SIP vendor/licence/budget, loader mode, research host | `universe.n`, `data.vendor`, `data.fetch_mode` | PR 5, 6, 7 (all of P1) | N=100; Alpaca SIP if depth/licence verified; host named before PR 5 |
| 9 | **D01 exposure** | Sign exposure conclusions and holdout applicability | `governance.exposure_signed` | PR 3 ledger content; P0 exit; whole P4 | Sign only after WP0.6 contact audit; report unknowns as unknowns |
| 10 | **D09 + C2** | ORM-001 relation; overlap limit; reviewer sign-offs | `governance.related_programs` | PR 4 (no code until approved), P0 exit | Shared ledger and family with ORM-001; tight overlap limit; history for criterion 1 and gate-clause handling are owner options (see sheet) |
| 11 | **D17 P3 criteria** | P3a eligibility/STOP level; P3b criteria | `p3.criteria` | PR 11, 12, 13, 13B | P3a: 300 trades, PF>1.0, alpha 0.05; P3b = P4 thresholds, 150 trades |
| 12 | **D18 gate basis** | Portfolio-constrained vs signal level; trade unit | `gates.basis`, `gates.trade_unit` | PR 12, 13, 13B, 14 | Portfolio-constrained; one entry = one trade |
| 13 | **D02 hypothesis family** | Family size and adjustment | `stats.hypothesis_family` | PR 11, 12, 14 | Owner states the number of confirmatory hypotheses in the Holm family; preparer proposes Holm over {G4, G5} (see sheet) |
| 14 | **D12 regime** | Regime definition and single-regime criterion | `stats.regime.*` | PR 11, G7 | SPY prior close vs 200-day SMA; both regimes and halves reported |
| 15 | **D13 thesis** | Accept economic thesis, naive-ORB definition, binding vs non-binding diagnostics | `governance.economic_thesis_sha`, `controls.naive_orb` | PR 4A, PR 9, C2 criterion 3 | Thesis must be written by humans (WP0.9) |
| 16 | **D10 win rate / drawdown** | Win-rate gate vs deviation; drawdown comparator | `gates.win_rate`, `gates.max_dd` | PR 12, 14, any promotion | Keep platform >50% gate unless owner signs written deviation; random-entry portfolio as comparator |
| 17 | **D04 yearly gate** | 3 of 4 years PF>1.0 | `gates.yearly` | PR 12, 14 | Confirm as designed; undefined year does not pass |
| 18 | **C10 DOCX custody** | Where the authoritative DOCX lives | (policy) | Traceability of the governing doc at sign-off | S3 + versioned SHA-256 manifest once tooling exists |
| 19 | **D16 diagnostics / shadow** | Taxonomy; shadow-run acceptance | `diagnostics.taxonomy`, `p5.shadow_acceptance` | PR 15A | Adopt the 8 labels as explanatory only |
| 20 | **D07 P5 contract** | Paper-account policy, tolerances, cost-ratio contract | `p5.*` | PR 15 | See sheet (account ID cannot exist at P0) |

Critical path to P0 exit: **A1 and D08 -> D06 -> D19/D17/D02 -> D05/D14/D15 (WP0.12 fixtures) -> D01 + D09/C2 (PR 3, PR 4) -> remaining sign-offs -> freeze**. Longest *external* lead time is D03/D11/C12 plus the feasibility items in section 4 (vendor licence and history depth): start those first because they are not governed by anything else.

---

## 2. Which decisions each PR needs

PR numbering per plan §8. "None" means schema fields exist with values unset; per owner instruction 7 and plan header, PR 2 may start now.

| PR | Content | Decisions / items needed before merge | Notes |
|---|---|---|---|
| 2 | Spec schema, hashing, freeze tool (WP0.2-0.3) | **None.** Schema must accept the A1 `exits` block (<=8 candidates, four families, selection fields) with all values unset | Do not freeze or sign any spec |
| 3 | Results guard, run registry, exposure ledger, holdout token (WP0.4, 0.6, 0.7) | Code: none (partition set is fixed in App. A). Ledger *content*: **D01** (exposure audit), **D19** (K candidates), **D09** (related programs), **D08** (who signs) | Guard logic can be built and tested with synthetic partitions before values exist |
| 4 | Non-equivalence output + ORM-001 note, AI provenance (WP0.5, 0.8) | **D09 and C2** (spec approved, overlap limit, reviewers), **D13** (mechanism text for criterion 3), **D08** | **No non-equivalence code until the full specification is approved** (C2). The ADR 0037 automated check does not exist; see D09 sheet for the criterion 1 history dependency |
| 4A | Thesis, feasibility, lineage, order contract (WP0.9-0.12) | **D13, D14, D08**; feasibility items F1-F11 (section 4) | WP0.12 fixtures need D14 values |
| P0 gate | Freeze and sign | **All of D01-D19, A1, C2 spec, C10, C12 named**; the non-equivalence check clause cannot be met until the C2 spec is approved and PR 4 built (D09 sheet) | Plan P0 exit text; the sign-off packet pins the SHA-256 of every document signed |
| 5 | ADR 0033 finding, SIP loader, manifest (WP1.1-1.3) | **D03** (vendor, licence, budget), **D11**, **C12** (named research host), C4 (ruled) | Plus P0 gate; WP1.3 stop if history/delisted short |
| 6 | Calendar, PIT universe, corporate actions, anomalies (WP1.4-1.7) | **D03** (N, PIT timing), **D05** (OR completeness rule; `NO_TRADE_MINUTE` vs `DATA_GAP` evidence rule) | |
| 7 | Return-blind coverage report (WP1.8) | **D03**; 98% threshold already in design | Report must contain no return fields |
| 8 | OR signal, fill model, sizer, position sim (WP2.1-2.4) | **D05, D14, D15, D19** (exit mechanics) | |
| 9 | Controls (WP2.5) | **D06** (baseline), **D13** (`controls.naive_orb`) | |
| 10 | RNG-001 replay + fixtures (WP2.6) | **C12** (host), no new decision | Needs IEX 5-min archive and code state `9e43abe` question |
| 11 | Stats and `selection.py` (WP3) | **D06, D12, D17, D19, D02** | |
| 12 / 12A / 12B | Gates, scheduler, funnel | **D02, D04, D10, D18** (gates); **D14, D06** (scheduler/baseline); **D16** (taxonomy) | |
| 13 / 13B / 14 | P3a, P3b, P4 runs | **Everything above**, A1 signed, D17/D18/D19 signed (plan §9.16) | Results guard refuses otherwise |
| 15 / 15A | Executor, shadow run | **D07, D16**, D14 broker semantics verified | After P4 PASS plus written owner approval |

---

## 3. Decision sheets

### A1 — Governing-Design Addendum A1 (signature)

- **Statement.** Sign (approve / reject / amend) Addendum A1: exit selected from a frozen candidate set (Amendment 1), P3 split into P3a 2016-2019 and P3b 2020-2021 (Amendment 2), decision list D01-D19 (Amendment 3), plus citation and scope corrections (C1, C2, C6, C4, C5, C10, C12).
- **Source.** A1 §2-§4, ruling C7, C13. Design v0.4 §3.1 and §4 fix variants A/B; §7 P3 is one 2016-2021 run; §10.2 lists 12 decisions.
- **Options.** (a) Sign as drafted. (b) Sign with amendments (e.g. resolve the inconsistencies in section 5 first). (c) Reject: design v0.4 A/B governs; plan v0.5 exit machinery is then unusable and the plan reverts to v0.4.
- **Recommendation (not a decision).** (b): sign after the owner has seen the D19, D17 and D02 sheets, and after the wording items in section 5 are settled (status of each is shown there). A1 is the instrument that makes D13-D19 valid; signing it first with open wording risks a second addendum.
- **Spec key.** None directly; `signoff.*` and the `exits` block depend on it.
- **Blocks.** Validity of D02 (rewritten), D17, D19; any spec freeze (plan header, §9.10, §9.16); PR 13+.
- **Return-blind evidence needed.** None. Provenance: the exit change came from the 2026-10-09 fund-manager review; no data or results were seen (A1 §9).
- **Signature (A1 §10 has 3 rows: Owner; Trading-expert reviewer (D19); Independent validator (selection rule, P3a test)).**

| Role | Name | Decision | Signature | Date |
|---|---|---|---|---|
| Owner | | | | |
| Trading-expert reviewer | | | | |
| Independent validator | | | | |

### D01 — Registration, exposure conclusions, holdout applicability

- **Statement.** Register RANGE-002 as an independent program (not live approval) and sign the data-exposure conclusions: which periods are exposed, and whether 2022-2025 is independent enough to be the holdout.
- **Source.** Design decision 01; §3.2 (2016-2021 development, 2022-2025 holdout, 2026-01 to 07 exposed incl. RNG-001 backtest 2026-01-02 to 06-12, the 18-name/126-session entry study, E-vwap+gate splits; the "49% target hit before entry" finding is the idea's origin). Plan WP0.6, R2, R3, stop §9.2.
- **Options.** (a) Sign: 2022-2025 independent. (b) Sign with a stated, bounded exposure (e.g. daily-layer contact from other programs) and an owner ruling that it is not material. (c) Do not sign: 2022-2025 contaminated; the holdout must be replaced (new unexposed sample or longer prospective phase) before P0.
- **Recommendation (not a decision).** Do not sign until the WP0.6 contact audit is complete, including AI-session history on 2016-2025 intraday data. Report unknown contact as unknown, never as "none". Ask explicitly whether other programs' use of the 2022-2025 *daily* layer (momentum, low-vol, FI programs under `docs/implementation/evidence/`) counts as material for an *intraday* breakout hypothesis; that is an owner ruling, not a developer one. Conservative default: record it in the ledger as daily-layer contact, different hypothesis, and state the ruling.
- **Spec key.** `governance.exposure_signed`.
- **Blocks.** P0 exit; PR 3 ledger content; P4 entirely (G0).
- **Return-blind evidence.** `exposure_ledger.yaml`, `hypothesis_lineage.yaml` (WP0.11): list of sessions/programs touching 2016-2025 data, purpose, who. Nothing return-bearing.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D02 — Hypothesis family and adjustment

- **Statement.** Fix the confirmatory family and multiplicity method: the P3a selection-aware test over K; how many confirmatory hypotheses the P4 Holm family contains; PF >= 1.30 and stress mean > 0 confirmed.
- **Source.** Design decision 02 (originally A primary, B secondary, Holm family, gates; the A/B ordering is replaced by A1). Design §5.3: the main test needs positive net mean R **and** a paired difference vs the matched random baseline whose corrected lower bound is > 0; "the Holm-corrected hypothesis family and ruling must be signed before results are seen". Design §6: G4 (mean net R, corrected bound > 0) and G5 (paired difference vs random baseline, corrected lower bound > 0) are both "Required". A1 Amendment 3 and plan §10 D02. Plan §5.1A last bullet: the confirmatory comparisons are "the selected exit vs zero, and vs the random baseline". Ruling C6: Holm.
- **What the design requires, precisely.** Two required tests (G4, G5), each with a multiplicity-corrected bound, with the family and correction method fixed before results. The design does not say whether G4 and G5 are one Holm family. It does require that uncorrected significance not be used as promotion evidence.
- **Terminology fixed by this reconciliation (no value chosen).** "m = 1" in A1 and the plan counts **exit configurations** (one selected exit at P4; K candidates are recorded in the ledger). It does not state the number of **confirmatory hypotheses** in the Holm family, which is an owner value in D02. Wording in A1 Amendment 2/3, plan X5, WP3.3, WP4.2, G4/G5 and App. A has been aligned to this.
- **Options.** (a) One Holm family over {G4, G5}, hypothesis count 2, one-sided alpha 0.05. (b) G4 is the Holm family (count 1); G5 is a separate required gate with its own declared one-sided alpha and bound, no cross-adjustment; all gates must pass (intersection-union). (c) Fixed-sequence: G4 then G5, each at alpha 0.05, G5 evaluated only if G4 passes. The gate function must implement the declared procedure exactly and label it.
- **Recommendation (not a decision).** (a): the stricter reading, consistent with conservative defaults and with plan §5.1A; it costs little because both gates must pass in any case. The independent validator should confirm the statistics. Record K and the family composition in the ledger and the P4 report under any option.
- **Spec key.** `stats.hypothesis_family` (plus `stats.adjustment`).
- **Blocks.** PR 11, 12 (gate function), PR 14.
- **Return-blind evidence.** None; pure procedure choice. Requires D06 decided first.
- **Owner decision (option and hypothesis count) / signature / date:** ____________________ / ____________________ / ________

### D03 — Universe N, PIT timing, SIP vendor and licence, data budget

- **Statement.** Fix N, the PIT timing of the monthly rebuild, the SIP historical minute-bar vendor, licence terms and the data budget.
- **Source.** Design §4 (monthly rebuild from prior-day 20-day average dollar volume, top N, prior close > $10; N = 100 proposal; licensed SIP 1-minute); decision 03. Plan §2.1, WP1.2-1.3; CLAUDE.md: a new external dependency requires an ADR.
- **Options.** N: 100 (proposal) or other. Vendor: (a) Alpaca SIP historical (already the platform's market-data dependency; no new ADR if confirmed to cover the span and licence), (b) a different vendor (new external dependency, needs an ADR).
- **Recommendation (not a decision).** N = 100 as proposed (no basis to move it return-blind; a smaller N tightens liquidity, a larger N dilutes). PIT timing: universe built after the prior trading day's close, effective from the first session of each month, all inputs dated <= prior day. Vendor: use Alpaca SIP only if feasibility items F1, F2, F5 pass; otherwise stop (§9.3). Data budget: owner sets a cap; the sizing formula is rows ~ (union of monthly top-N symbols) x (trading days ~2,500) x (<=390 min). Union size is not known return-blind until PR 6, so ask for a cap, not a point estimate.
- **Spec key.** `universe.n`, `data.vendor`, (PIT timing in `universe.*`/`data.*`).
- **Blocks.** P1 (PR 5, 6, 7).
- **Return-blind evidence.** Vendor history start dates and delisted coverage (F1, F2); licence text for stored research use (F5); daily-layer `dataset_health` for 2016-2025 (F11); union size estimate from the PIT universe once built.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D04 — Yearly consistency gate

- **Statement.** Confirm "at least 3 of the 4 calendar years 2022-2025 with PF > 1.0".
- **Source.** Design §6 ("建议 · 待批准", applies only to this holdout window; a changed window needs a new yearly gate); plan G6.
- **Options.** (a) Confirm as designed. (b) Different count/definition. (c) Drop (not recommended; no basis).
- **Recommendation (not a decision).** (a). Add the plan §5.1A rule that a year with too few trades for a meaningful PF is reported with its count and does not count as passing; the owner or validator sets that minimum per-year trade count.
- **Spec key.** `gates.yearly`.
- **Blocks.** PR 12, 14.
- **Return-blind evidence.** None (a count rule only). Any per-year trade-count expectation is return-derived (trigger frequency) and stays inside `results_guard`.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D05 — Fill, risk and exit-mechanics values

- **Statement.** Freeze the values that change simulated fills and risk. Sub-items: (5a) OR completeness rule; (5b) minimum OR width in ticks; (5c) R_pre/R_fill rules, tolerance, and what happens when actual risk exceeds budget; (5d) gap-through fills; (5e) same-bar order; (5f) tick size source; (5g) half-day exit offset; (5h) halt rule; (5i) slippage model; (5j) risk limits (per-trade %, per-name cap, gross cap, max concurrent, daily loss limit, participation cap).
- **Source.** Design decision 05; §4 (R_pre/R_fill, adverse fill after gap, half-day early exit minute frozen in P0, risk 0.25% proposal, other limits "P0 signed"); §4.1-4.2. Plan §2.1, WP2.2, WP2.3, App. A. Same-bar worst case is already fixed in App. A (`fill.same_bar_policy: worst_case`).
- **Options and Recommendations (not decisions).**

| Sub | Recommendation | Why |
|---|---|---|
| 5a | A symbol-day is eligible only if every minute in 09:30-09:59 is present or classified `NO_TRADE_MINUTE`; any `DATA_GAP` minute makes the day ineligible | Fail-closed; matches F5 of plan v0.4 |
| 5b | A floor expressed in ticks, set from the return-blind distribution of OR width in ticks (price data, no returns) so that sub-tick-noise ranges are excluded; number to be chosen by the owner after seeing that distribution | Cannot be chosen blind; must not be tuned on P&L |
| 5c | `qty = floor(risk_budget / R_pre)`; after fill, if `actual_risk > budget x (1 + tol)` apply the reduce/protective-exit rule; `R_fill <= 0` means immediate exit and log | Plan WP2.3 |
| 5d | Gap through trigger fills at bar open plus adverse slippage; gap below stop fills at bar open minus slippage | Plan WP2.2, never at the trigger/stop price |
| 5e | Entry and stop in same bar: entry then stop; stop and target: stop; `path_ambiguous = True` (already in skeleton) | Worst case |
| 5f | Tick size by price band per exchange rules; sub-$1 asserted excluded | Plan WP2.1 |
| 5g | Same lead before the official early close as on full days (5 minutes before the 13:00 ET early close, i.e. 12:55 ET) | Design leaves the minute to P0; mirrors the 15:55 convention |
| 5h | Label `EXIT_UNAVAILABLE`, accrue gap risk, no assumed exit | Plan WP2.2 |
| 5i | No separate slippage model if D15 = all-in; otherwise itemized | Avoid double count |
| 5j | per_trade_pct 0.25% (design proposal); caps and daily loss limit: owner to state numbers. Defaults must be conservative (lower exposure, tighter daily loss) per CLAUDE.md | No basis to propose numbers |

- **Spec key.** `signal.or_completeness_rule`, `signal.min_or_width_ticks`, `fill.*`, `risk.*`, `exit.halfday_offset_min`.
- **Blocks.** PR 6, 8, 12A, 13.
- **Return-blind evidence.** Distribution of OR width in ticks and in % of price; counts of `NO_TRADE_MINUTE` vs `DATA_GAP` in 09:30-10:00; half-day calendar list; tick-size bands. No post-entry price paths.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D06 — Baselines, bootstrap parameters, adjustment, confidence level, seeds

- **Statement.** Fix: resampling method; mean block length; repetitions; interval type; confidence level; alpha; seeds; random-entry baseline design (repetitions, invalid-draw policy); the bootstrap used for the P3a max-statistic test.
- **Source.** Design decision 06; §5.3 (day-clustered block resampling; fix repetitions, interval type, confidence level, tail convention in P0; random baseline matched on eligible symbols, time window, trade count, capital, risk budget, not conditioned on future breakout; naive ORB). Plan WP3, WP3.3 (recommended default), WP2.5, WP2.7A, ruling C11 (method left unset), App. A. Existing code is design reference only: `factor_data/evidence.py` (circular block), `market_projection/validate.py` (stationary, `BLOCK_LEN=10`); no day-clustered stationary bootstrap exists.
- **Options.** Method: (a) stationary block bootstrap over trading days (geometric blocks), (b) circular fixed-block over days, (c) day-cluster resampling without blocks (iid days). Block length: fixed a priori vs data-driven.
- **Recommendation (not a decision).** (a), one-sided, alpha 0.05, percentile of the recentered null, fixed seeds; mean block length fixed a priori (not estimated from RANGE-002 data) and stated in days; the platform's existing daily value `BLOCK_LEN = 10` is the only precedent in the repo, which the validator should confirm or replace; repetitions at least 10,000 for the selection test and G4/G5. Random-entry repetitions and invalid-draw policy per WP2.7A: invalid draws counted as `NOT_EXECUTABLE`, denominator preserved. Plan WP3.3 G4/G5 estimand (day-level pairing) as written. The independent validator, not the developer, should confirm numbers.
- **Spec key.** `controls.random_entry.*`, `controls.naive_orb`, `stats.bootstrap.*`, `stats.alpha_one_sided`, `stats.adjustment`.
- **Blocks.** D19 score, D17 STOP test, D02; PR 9, 11, 12, 12A. Needed before the selection rule can be frozen.
- **Return-blind evidence.** None. Method choice must not use RANGE-002 data (block length from autocorrelation would be return-derived). Synthetic calibration (size/power on simulated data) is allowed and recommended for the validator.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D07 — P5 paper account, tolerances and cost-ratio contract

- **Statement.** Decide the P5 contract: new dedicated paper account policy; slippage, drawdown and degradation tolerances; extension rules; the cost-quality calculation.
- **Source.** Design decision 07; §9.1-9.2 (>=60 trading days and >=100 trades; realized cost <= 1.5x model with comparable items, aggregation and tail rule defined; degradation tolerance and minimum acceptable net mean R frozen in advance; "not significantly worse" cannot substitute for "meets the bar"). Plan WP5.1, WP5.6, "P5 cost-quality calculation".
- **Inconsistency (section 5, item 4), proposed resolution: option B (PROPOSED / NOT APPROVED; owner direction, unsigned).** The merged schema still has `p5.account_id` as a P0 field that must be set to freeze, but WP5.1 provisions the account in P5, after P4. Under option B the spec would instead carry `p5.account_binding`, a hashed closed marker (`deferred_to_p5_activation`) that the owner would set at P0; the real account id would live only in a separate P5 activation record bound to the same `spec_sha256`. Free-form spec fields would never be an account source.
- **Options.** Account: (a) would record the *policy* (new, dedicated, not user 2) and the deferral marker `p5.account_binding` at P0, and the ID only in the P5 activation record and execution manifest (this is option B, PROPOSED / NOT APPROVED; owner direction, unsigned); (b) provision now (premature, adds account risk before P4); (c) a nullable `p5.account_id` or an unhashed block (rejected: silent null or weaker immutability).
- **Recommendation (not a decision).** (a) is NONBINDING and not an approved decision: option B of the P0 decision register section 22 remains PROPOSED / NOT APPROVED until the owner signs it, and wherever this sheet says "resolved" or "owner choice" for option B it is to be read as proposed, not approved. Current state versus future state: the merged schema (`origin/main`) still requires `p5.account_id` as a P0 field that must be set to freeze; `p5.account_binding` would replace it only if the owner approves option B AND the batched schema change is reviewed and merged before any real freeze. Cost ratio: `sum(realized shortfall) / sum(modeled cost)` over trades with positive modeled cost; zero/negative/missing denominators reported separately as `UNDEFINED`, never auto-pass; an unresolved undefined case blocks promotion (plan text). Degradation and drawdown numbers: owner states; defaults must be the tighter option. Extension rule: owner states a maximum number and length of extensions so P5 cannot extend indefinitely.
- **Spec key.** `p5.*` (`account_binding` would replace `account_id` if option B is approved; the merged schema still has `account_id`; `degradation_tolerance`, `cost_ratio_contract`).
- **Blocks.** P0 exit (listed in plan); PR 15.
- **Return-blind evidence.** None.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D08 — Roles

- **Statement.** Name the research lead, trading-expert reviewer, independent validator, and the sole P6 approver.
- **Source.** Design decision 08, §10.3 (technical team: data/engine/evidence; trading expert: hypothesis, trade logic, execution limits; independent validator: test scope; one final approver). A1 §10 uses the trading expert (D19) and independent validator (selection rule, P3a test).
- **Options.** Same person in several roles vs distinct people.
- **Recommendation (not a decision).** Four distinct humans for the four roles where possible. At minimum the independent validator must not be the research lead or the person who wrote the engine. Because the owner is an experienced trader, flag if the owner is also the trading-expert reviewer: then D19 candidate review is not independent of the final approver, which weakens the A1 §10 control. No AI agent may hold a role or sign (R9, plan §8 definition of done).
- **Spec key.** `governance.roles`, `signoff.*`.
- **Blocks.** Every sign-off that needs a reviewer: A1, D19, D13, D09/C2, WP0.9-0.12.
- **Return-blind evidence.** None.

| Role | Name | Signature | Date |
|---|---|---|---|
| Research lead | | | |
| Trading-expert reviewer | | | |
| Independent validator | | | |
| P6 approver (sole) | | | |

### D09 — ADR 0037 statement and ORM-001 relationship; C2 open items

- **Statement.** (i) Sign the non-equivalence statement. (ii) Choose the relationship to ORM-001: merged registration, shared trial ledger and multiplicity family, or independent. (iii) **C2 open items:** the numeric signal-overlap limit and the reviewer sign-offs for the three-criterion framework.
- **Source.** Design decision 09, §3.4 (RNG-001 = buy near support inside range; RANGE-002 = buy above OR high, stop at OR low, no in-range sell; must be confirmed by "ADR 0037 automated check"; if ORM-001 overlaps, merge or share the ledger and family, "do not each consume the same holdout independently"). Ruling C2: ADR 0037 defines no test; ATP v0.14 §3A.2 three criteria approved (signal distinctness on timestamps and direction only; materially different reject condition; non-reducible mechanism); **numeric overlap limit and reviewer sign-offs open; no code until the full specification is approved.** Plan WP0.5.
- **Options (ii).** (a) Merge into one registration. (b) Shared ledger and shared multiplicity family, separate specs. (c) Independent.
- **Options (iii).** Overlap metric: set-overlap of (symbol, session date, direction) signal sets, or correlation of daily signal indicator series; limit as a maximum; reviewers for criteria 2 and 3.
- **Recommendation (not a decision).** (ii) = (b): ORM-001 is named by the RNG-001 report as the only permitted reuse path for VWAP-confirmation ideas, and both programs draw on overlapping market history; (c) is only defensible with disjoint holdouts. (iii) a tight maximum (conservative = lower), computed on signal timestamps and direction only; the preparer's proposal for the history is option (a) below (the **already-exposed** RNG-001 IEX 5-minute archive), because computing it on 2016-2025 SIP data would require the P1 pull that only starts after the P0 gate (see section 5, item 5); the owner may choose (b) or (c) instead. Criteria 2 and 3: signed findings by the trading-expert reviewer and the independent validator with evidence cited, countersigned by the owner. The numeric limit is the owner's to state; ATP v0.14 §3A.2 asks only for "a pre-declared maximum" and gives none. Origin disclosure: RANGE-002 was generated from RNG-001's "49% target hit before entry" finding and must appear in the non-equivalence record (reconciliation C2).
- **Dependency not yet resolved (see section 5, items 5 and 6).** (1) The ADR 0037 automated check does not exist: ADR 0037 defines no non-equivalence test and the C2 specification is pending, so the P0 exit-gate clause "the non-equivalence check passes" cannot be met by a tool until the specification is approved and PR 4 is built. (2) Criterion 1 needs signal history; SIP data arrives only in P1, after the P0 gate, and before it only the exposed RNG-001 IEX 5-minute archive exists. Owner options for the history (none selected): (a) compute criterion 1 on the exposed IEX archive, signal timestamps and direction only, recording the granularity difference from the 1-minute SIP design; (b) reorder: criteria 2 and 3 and the criterion 1 specification signed at P0, numeric overlap on SIP signal timestamps computed after the P1 pull and before P2 (changes the P0 exit gate; needs an A1 amendment); (c) an owner-authorized early, return-blind SIP pull limited to criterion 1 (needs C12, D03 licence, F1, F5 first). The owner also states what satisfies the gate clause while the tool does not exist (for example signed reviewer findings on all three criteria against the approved specification).
- **Spec key.** `governance.related_programs`.
- **Blocks.** PR 4 (WP0.5 code and output) and P0 exit; stop condition §9.1.
- **Return-blind evidence.** Versioned records of both programs' entry/exit/universe/granularity/falsification condition; signal-timestamp overlap on the exposed archive (no returns).
- **Owner decision / signature / date (ii):** ____________________ / ____________________ / ________
- **Overlap limit (value, owner-stated):** ________  **Criteria 2/3 reviewers (names):** ____________________ / ____________________  **Signed:** ____________________ / ________

### D10 — Win-rate gate and drawdown comparator

- **Statement.** (i) Keep the platform win-rate > 50% gate or sign a formal deviation (win rate diagnostic only). (ii) Fix the drawdown comparator ("no worse than baseline").
- **Source.** Design §6: platform formal gate (trades > 100, PF > 1.2, win rate > 50%, drawdown no worse than baseline, positive expectancy, bootstrap CI > 0); design treats win rate as diagnostic because breakout strategies typically win under half the time, **but the deviation must be signed in P0, and until signed the platform gate applies**. Ruling C3: >50% gate applies until a D10 deviation is signed; display both evaluations. Plan §5.1 G8, D10 alert.
- **Options.** (i) Keep > 50%; or sign deviation (diagnostic only), with or without a compensating requirement. (ii) Comparator: SPY buy-and-hold on same capital/days; naive ORB portfolio; random-entry portfolio under identical capital, costs and sizing; RNG-001 baseline (not comparable per the rejection report).
- **Recommendation (not a decision).** (i) Default stays: gate applies and promotion is blocked until the owner signs. If the owner signs a deviation, record the stated reason (payoff structure of breakouts) and keep both evaluations displayed. A1 §8 and plan §5.1 now state the platform > 50% gate applies until a D10 deviation is signed (both evaluations displayed). The design's claim that the 50% gate rejects "for the wrong reason" is a design assertion, not evidence from RANGE-002 data. (ii) Random-entry portfolio under identical capital, costs, equity sampling and exposure as primary (it is already pre-registered), SPY as a reported reference.
- **Spec key.** `gates.win_rate`, `gates.max_dd`.
- **Blocks.** PR 12, 14; any promotion decision (P6).
- **Return-blind evidence.** None; comparator definition and equity-sampling rule only.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D11 — SIP loader / ADR 0033 handling (ruling already made)

- **Statement.** Record D11 for the spec. Owner ruling C5 (2026-10-09): a new monthly-chunked, fail-closed RANGE-002 SIP loader; the shared `BarCache` is not modified; ADR 0033 points 1-3 stay open for the shared cache.
- **Source.** Design decision 11 (writer meets ADR 0033 points 1-3, **or** approved monthly-chunk rebuild script). Reconciliation C5 noted the variance: the owner chose a third option (new loader) and asked for confirmation that it satisfies decision 11; `scripts/research/rebuild_5min_cache.py` does not exist. Recon: `bar_cache.py` hardcodes IEX at line 428; points 1-3 unimplemented.
- **Options.** (a) New loader (ruled). (b) Fix the shared cache (touches live-box code; own ADR review).
- **Recommendation (not a decision).** Confirm that the C5 ruling satisfies design decision 11 and record `data.fetch_mode` accordingly (the enumeration string is defined in PR 2). Loader requirements are in recon §0 item 2 (explicit SIP, no IEX fallback, monthly chunks, truncation detection, idempotent resume, SHA-256 manifest, delisted coverage where licensed). Intraday coverage uses the dedicated validator (C4, ruled).
- **Note.** A1 §7 and plan §10 now state that the approach is resolved by ruling C5 while the spec value `data.fetch_mode` and this signature are still required for the P0 gate.
- **Spec key.** `data.fetch_mode`.
- **Blocks.** PR 5, 6, 7 (P1).
- **Return-blind evidence.** WP1.1 written finding on `bar_cache.py` (already in recon §2.7).
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D12 — Regime definition and single-regime-dependence criterion

- **Statement.** Define the market regimes and the criterion for "profit not from a single regime or a single half".
- **Source.** Design decision 12; §5.3 ("市场状态与时间拆分": regime e.g. SPY vs its VWAP or 200-day average, frozen in P0; if returns come entirely from one regime or one half, do not promote); lesson from E-vwap+gate (full sample PF 1.53, first half 0.68). Plan G7, `splits.py`.
- **Options.** Regime: SPY prior close vs 200-day SMA (daily, PIT); SPY vs its intraday VWAP at decision time; volatility regime. Criterion: (a) both regimes and both halves must have positive net mean R (and, optionally, PF > 1.0) with a minimum trade count; (b) cap on the share of total net P&L from any one regime/half.
- **Recommendation (not a decision).** SPY prior close vs 200-day SMA computed through the prior close (causal, daily layer already available). Criterion (a), plus a minimum trades-per-cell so an undefined cell cannot pass; add (b) with a share cap the owner states. Define it now, before any returns exist; a regime fitted afterwards repeats the RNG-001 error.
- **Spec key.** `stats.regime.definition`, `stats.regime.criterion`.
- **Blocks.** PR 11 (`splits.py`), G7 in PR 12.
- **Return-blind evidence.** Counts of sessions per regime and per half over 2022-2025 (calendar and SPY daily close only); confirm every cell has enough sessions.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D13 — Economic thesis, competing explanations, binding vs non-binding diagnostics

- **Statement.** Accept the written economic thesis (mechanism, falsifiers, competing explanations), define the naive-ORB control, and state which diagnostics are non-binding.
- **Source.** Design §10.3 (trading expert verifies hypothesis and trade logic), §3.3 (AI provenance), §5.3 (naive ORB frozen in advance). Plan §2.4, WP0.9, App. A.
- **Options.** Thesis accepted / returned for revision. Naive-ORB: "OR-high touch, no tick offset, same exits" (plan WP2.5 example) or other. Diagnostics: only G0-G10 binding (plan §5.1A) or additional ones.
- **Recommendation (not a decision).** The thesis must be written and signed by humans (research lead + trading expert); an agent may summarize but not author the mechanism (WP0.8 provenance). Naive-ORB as in WP2.5. Binding = G0-G10 only; MFE/MAE, funnel, attribution, taxonomy labels, SPY reference all non-binding (plan WP3.2, R4).
- **Spec key.** `governance.economic_thesis_sha`, `controls.naive_orb`, `diagnostics.*`.
- **Blocks.** PR 4 (criterion 3 text), PR 4A, PR 9.
- **Return-blind evidence.** Distributions of OR width, entry-to-stop distance and available time (price geometry, not outcomes); signal-frequency expectations only to the extent they do not depend on future highs (plan §2.4 item 5).
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D14 — Timestamps, latency, order arming, order type, EOD, tie-break

- **Statement.** Freeze the execution contract used by both the simulator and the paper executor. Sub-items: bar timestamp convention (start or end stamp); vendor delay; submit and ack latency; crossed-before-arm policy; stop order type; stop-protection policy; same-time tie-break; EOD lead; order reservation policy.
- **Source.** Design decision 05 and §5.2 (order effective time, trigger is not a fill, partial fills, cancel delay, duplicate orders, restart recovery; conservative same-bar order). A1 Amendment 3 (D14). Plan WP2.1, WP2.1A, WP2.2, WP2.9-2.11, R15, App. A `execution.*`.
- **Options and Recommendations (not decisions).**

| Sub | Options | Recommendation |
|---|---|---|
| Crossed-before-arm | SKIP; MARKET_AT_NEXT_ACTIVE_BAR_OPEN; REQUIRE_RETRACE | **SKIP.** No phantom fills, trivially reproducible by the executor. Report the share of signals affected and results under the other policy as sensitivity (plan WP2.1A). Final choice must match what the broker can reproduce (WP2.11) |
| Order type | stop-market; stop-limit; emulated stop (executor watches bars, sends marketable order) | Decide **after** the broker capability report (F3). Prefer the option whose failure mode is adverse fill rather than non-fill, since non-fill outcomes depend on the future |
| Bar timestamp, vendor delay | start- or end-stamped; delay in ms | Verify against vendor documentation and a sampled day (F4); then record. Must not be assumed |
| Latency | submit_ms, ack_ms | Set conservatively high versus measured paper latency; owner states numbers after F3/F4 |
| Stop protection | stop attached after entry fill acknowledged and sized | As plan WP5.2: protective stop only after confirmed entry fill |
| Tie-break | seeded hash order; permaticker ascending | Either is return-independent. Seeded hash avoids a systematic age/size bias; plan example is permaticker ascending. Owner picks |
| EOD lead | intent issued at 15:55 minus lead | Owner states seconds; fill is the first bar start >= intent + latency, adverse slippage |
| Reservation | reserve cash/risk at submission, release on cancel/expiry/fill | As plan §3.3 |

- **Spec key.** `execution.*`.
- **Blocks.** WP0.12 fixtures, PR 4A, 8, 12A, 15.
- **Return-blind evidence.** F3 (broker semantics), F4 (timestamp convention and delay), F10 (quote availability). Share of signals with crossed-before-arm: counts the owner must first declare return-blind or not (plan WP2.1A); not started.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D15 — Cost accounting mode

- **Statement.** Decide whether the 5 bps (base) / 15 bps (stress) per side is all-in or additive to fill-price slippage, and the itemized components.
- **Source.** Design §4 cost row (itemize spread, commission/fees, impact, slippage; avoid duplication or omission). Plan §2.5, D15 (recommended: all-in bps as a P&L debit, fills at modeled price, no extra slippage; gap-through fills stay adverse as price events), WP2.2.
- **Options.** (a) All-in debit. (b) Additive: bps plus a separate slippage model.
- **Recommendation (not a decision).** (a) as the plan recommends, with the cost bridge labelling price adjustments versus P&L debits. Caveat for the owner: (b) is the more conservative base case; under (a) the conservatism rests on the 15 bps stress gate (G3) and on adverse gap fills, so G3 must stay binding.
- **Spec key.** `costs.accounting_mode`, `costs.components`.
- **Blocks.** PR 8, 11 (`costs.py`).
- **Return-blind evidence.** None; spread/fee schedule of the broker and vendor if the owner wants components justified.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D16 — Diagnosis taxonomy, P5 shadow run, execution-quality evidence

- **Statement.** Approve the explanatory diagnosis labels, the shadow-run acceptance rule, and the minimum broker execution-quality evidence.
- **Source.** Design decision 07 and §9.2 (operational quality: reconcilable signal-order-position-cash chain, no unexplained duplicates, no persistent data gaps). Plan WP3.4 (eight labels: `NO_DEMONSTRATED_EDGE`, `EXECUTION_COST_DOMINATES`, `INSUFFICIENT_SAMPLE`, `REGIME_FRAGILITY`, `CAPACITY_OR_RISK_CONSTRAINT`, `DATA_OR_ENGINE_DEFECT`, `PAPER_OPERATION_FAILURE`, `UNCLASSIFIED`), WP5.9-5.11.
- **Options.** Adopt the labels as listed or modify; shadow run length and tolerance.
- **Recommendation (not a decision).** Adopt the eight labels as explanatory only (never an override of REJECT). Shadow-run acceptance: zero orphan signals, zero duplicate intents, zero look-ahead discrepancies over a number of sampled days the owner states; that count is a number I do not propose. It is an operational dry-run, not a profitability screen.
- **Spec key.** `diagnostics.taxonomy`, `p5.shadow_acceptance`.
- **Blocks.** PR 12B, 15A.
- **Return-blind evidence.** None.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D17 — P3 criteria (P3a eligibility and STOP; P3b)

- **Statement.** Fix: P3a minimum trades, PF threshold and the selection-aware STOP level; P3b advance criteria.
- **Source.** Design §7 P3 row: advance on "pre-approved development-period criteria" but **none are given** (gap). A1 Amendment 3 / D17; plan §2.2, WP4.1. P3b options in plan: (a) same G1-G8 as P4 with G1 scaled to two years (e.g. >= 150 trades); (b) a looser screen; (c) significance only.
- **Options.** P3a STOP alpha: 0.05, 0.10, 0.20. P3b: (a), (b), (c).
- **Recommendation (not a decision).** P3a: minimum trades scaled from the P4 rate (300 trades / 4 years) to the 4-year P3a window, i.e. 300; PF > 1.0 at base cost; STOP test one-sided alpha 0.05 on the max-statistic over K. Rationale: a looser alpha risks sending a noise-selected exit to P3b/P4; a false STOP costs a rejection that is a correct platform outcome. P3b: option (a), G1 = 150. Trade-off for the owner: strict P3a lowers the chance of reaching the holdout.
- **P3b sample-size note.** P3b covers 2020-2021 (two of the design's six development years) for the selected exit only, so its trade count and statistical power are lower than the design §7 single 2016-2021 run. The owner states the P3b trade minimum explicitly; the 150-trade figure above is a scaling proposal, not a decision.
- **Spec key.** `p3.criteria`.
- **Blocks.** PR 11, 12, 13, 13B (`results_guard` refuses P3 while null).
- **Return-blind evidence.** None. Depends on D06 and D18.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D18 — Gate computation basis and trade unit

- **Statement.** Declare the trade set that gates G1-G8 are computed on and what counts as one trade.
- **Source.** Design §6 does not say (gap). A1 D18; plan §5.1 (recommended: portfolio-constrained filled trades; signal-level set as diagnostic; partial fills of one signal = one trade; scale-outs = one trade, WP2.2A).
- **Options.** (a) Portfolio-constrained fills. (b) Signal-level (each first trigger sized independently).
- **Recommendation (not a decision).** (a), because it is the economic claim; report (b) as a diagnostic. One entry = one trade including all exit fills; net R = total net P&L of all exit fills / (entry qty x R_fill).
- **Spec key.** `gates.basis`, `gates.trade_unit`.
- **Blocks.** PR 12, 13, 13B, 14. Note: (a) can bind on G1 if portfolio limits (D05 5j) are tight; D05 limits and D18 should be read together.
- **Return-blind evidence.** None.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### D19 — Exit candidate set and selection rule

- **Statement.** Confirm or replace the closed exit set (<= 8, four families), complexity order, selection score, tie tolerance delta, eligibility, and STOP test.
- **Source.** A1 Amendment 1 (replaces design §3.1 A/B). Plan §2.2: E1 time exit; E2a/b fixed target k in {2, 3}; E3a/b breakeven at +1R then trail t in {1.0, 1.5}; E4a/b 50% scale-out at +1R, remainder EOD or trail 1.0; K = 7; score = one-sided bootstrap lower bound of mean net R per trade; tie to lower complexity rank within delta; `select_exit` pure function. Design v0.4 fixes only A (E1) and B (2R target, E2a).
- **Options.** (a) Adopt K = 7 as proposed. (b) Reduce (e.g. drop scale-out) to cut complexity. (c) Replace after trading-expert review (<= 8, four families only). Delta: a value in R.
- **Recommendation (not a decision).** (a) after trading-expert review, with the validator reviewing `select_exit` and the max-statistic test. Delta must be fixed a priori on a cost scale, not from data; an illustrative placeholder is 0.05 R, with the owner and validator to confirm or replace (I have no basis to set it). Note for the reviewer: all candidates share one entry stream, so they are highly correlated and the max-statistic correction will be mild; every adaptive or extra-feature exit (ATR, VWAP, per-day switching) stays out of scope (A1 item 4, plan §1.2).
- **Spec key.** `exits.candidates`, `exits.complexity_order`, `exits.selection.{score, tie_tolerance_r, eligibility, stop_test}`.
- **Blocks.** A1; PR 8 (exit mechanics WP2.2A), PR 11, 13; stop §9.16-17.
- **Return-blind evidence.** None for the choice. Mechanics fixtures (WP2.7) are synthetic. Do not use MFE/MAE or any outcome to alter the set after P0.
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### C10 — Authoritative DOCX custody

- **Statement.** Decide where and how the authoritative research-design DOCX is held, given that the S3 manifest tooling is not in the repo.
- **Source.** Ruling C10: authoritative DOCX in controlled S3 with versioned SHA-256 manifest; a non-authoritative Markdown extraction allowed. Reconciliation: not done, because `manifests/s3/` and its publish/verify scripts do not exist and the github-ops policy forbids a hand-rolled manifest scheme. Plan §11.3 action 2.
- **Options.** (a) Wait for the manifest tooling, DOCX stays local/untracked. (b) Owner directs an interim custody (e.g. controlled storage with SHA-256 recorded in the sign-off packet). (c) Commit a Markdown extraction now.
- **Recommendation (not a decision).** (a) plus record the DOCX SHA-256 and version in the A1 sign-off packet so the governing text is pinned even before S3; (c) only with the owner's explicit permission for a derived copy. Governing-text traceability is needed at P0 sign-off (reconciliation §4).
- **Spec key / Blocks.** Not a spec key. Blocks traceability of "governing document" at sign-off, not engineering.
- **Return-blind evidence.** SHA-256 of the DOCX (owner or developer computes locally).
- **Owner decision / signature / date:** ____________________ / ____________________ / ________

### C12 — Research environment name

- **Statement.** Name the approved, isolated, non-production environment for SIP pulls and the RNG-001 replay.
- **Source.** Ruling C12: no production-host data workload authorized. CLAUDE.md: runtime is AWS `ec2-paper`; laptop is warm standby and must not run the stack; Norton blocks `data.alpaca.markets` on the laptop. Reconciliation C12: replay needs IEX 5-min archive and code state `9e43abe`.
- **Options.** A separate AWS instance or account, WSL on a non-Norton machine, CI runner. Not allowed: `ec2-paper`.
- **Recommendation (not a decision).** Name it before PR 5 / WP2.6. Requirements: no broker credentials (R7), separate from the production box and DB, storage sized to the D03 budget, manifest-producing, reachable by the loader. The owner names the environment and the person accountable.
- **Blocks.** PR 5, PR 10 (WP2.6).
- **Return-blind evidence.** Network reachability test to the vendor endpoint from that host (metadata call only).
- **Environment name / owner decision / signature / date:** ____________________ / ____________________ / ________

---

## 4. Return-blind feasibility items that can start now (WP0.10)

All are metadata, licence, documentation or capability checks. None reads a return, a P&L, a trigger-hit rate or a strategy metric, and each output goes into `feasibility_report.md` as PASS / BLOCK / UNKNOWN. Nothing below has been done by the preparer.

| # | Item | What to establish | Who must verify | Notes / limits |
|---|---|---|---|---|
| F1 | **SIP 1-minute history depth to 2016-01-01** | Earliest available SIP minute-bar date for the vendor plan, on a few liquid symbols; whether the licence includes history to 2016 | Owner (account/licence holder; vendor plan or support confirmation) and developer (earliest-bar timestamp and row-count query only) | Stop condition §9.3 if short; period may be shortened only by a pre-agreed P0 rule. Not checkable from code (recon item 5) |
| F2 | **Delisted-symbol coverage** | Whether minute bars exist for later-delisted names; ticker-reuse handling via permaticker (`security_lineage.py`) | Developer (sample known delisted permatickers from the Sharadar daily layer, count-only) and vendor documentation or support | Survivorship-free universe is part of the design (§4); WP1.3 |
| F3 | **Broker stop-order semantics** | Buy-stop acceptance and behavior when stop price is below market, stop-market vs stop-limit support, TIF, extended-hours flag, stop/target linkage, bracket behavior when entry is unfilled, partial fills, cancel/replace, reject semantics | Developer from broker documentation; independent validator reviews the capability report. Any paper-order probe needs explicit written owner authorization for that probe (R14: no orders before executor tests); plan WP0.10 and stop condition 18 now say so. Without it the item is UNKNOWN | Do not infer from SDK method names (WP2.11). Feeds D14 order type and crossed-before-arm |
| F4 | **Bar timestamp convention and delivery delay** | Start- vs end-stamped bars; vendor publication delay for 09:59 bars | Developer from vendor documentation and one sampled session; validator reviews | Feeds D14; no price use needed beyond timestamps |
| F5 | **Licence for stored research use, data cost, storage budget** | Whether bulk storage of historical SIP minute data for research is permitted; cost; disk | Owner | Feeds D03 |
| F6 | **Pagination, rate limits, truncation behavior** | Page cap (10,000 rows seen in the cache incident), continuation behavior, limits per minute | Developer (documented limits; a simulated 10,000-row page test per WP1.1) | Required by the loader acceptance test |
| F7 | **Research host (C12)** | Named environment and reachability | Owner | See C12 sheet |
| F8 | **Exchange calendar 2016-2025** | Half-days, DST transitions, closures via `validation/eval_calendar.py` (fail-closed) | Developer; reviewer spot-checks | Do not use `MarketSession` (recon) |
| F9 | **Daily-layer coverage 2016-2025** | `dataset_health` over the Sharadar daily layer (dates, tickers, delisted counts) | Developer | Daily layer only; intraday uses the dedicated validator (C4) |
| F10 | **Quote availability for intrabar validation** | Whether quote-level history exists to validate same-bar assumptions; otherwise record sensitivity-envelope approach | Developer from vendor documentation | Plan WP2.9 |
| F11 | **Crossed-before-arm share** | Share of signals crossed before arming | **Do not start.** Owner must first rule whether this counts as return-blind (plan WP2.1A); otherwise it goes inside `results_guard` | Listed so it is not run by mistake |

---

## 5. Inconsistencies found between design v0.4, Addendum A1 and plan v0.5

None changes a gate threshold. Each is a wording or sequencing issue for the owner to settle, preferably before A1 is signed.

1. **D13-D16 treatment.** Plan v0.5 §10.1 "Interpretation" says D13-D16 are within design v0.4 and "no design addendum is needed"; A1 Amendment 3 and ruling C7 put D13-D18 into the addendum and A1 lists D13-D16 as "refines". Both can be read as compatible, but the plan sentence is stale after C7. Status: plan §0A, §10.1 header and the §10.1 interpretation now say D13-D16 are refined in A1 (ruling C7); values still need owner sign-off.
2. **A1 vs design on D01-D12 numbering.** A1 §4 says the P0 list "becomes D01-D19" yet the table lists only D02 and D13-D19, with "Decisions 01, 03-12 unchanged"; plan §10 reorders D17, D19, D18. Cosmetic, but the sign-off packet should list all 19 in one order. Status: A1 §4 now lists D01-D19 in numeric order (D01, D03-D12 marked unchanged); plan §10 rows are in numeric order with D13-D16 pointed to §10.1.
3. **Hypothesis family size.** A1 D02 and plan WP4.2 say P4 family m = 1; plan §5.1A says the confirmatory comparisons are the selected exit vs zero **and** vs the random baseline, and G4 and G5 are separate required gates with their own Holm-adjusted bounds. Design §5.3 requires both. m = 1 and two required adjusted tests cannot both be literally true; see D02. Status: reconciled without choosing; "m = 1" now counts exit configurations, the hypothesis count in the Holm family is the D02 owner value with options (a)/(b)/(c), and A1, plan X5, WP3.3, WP4.2, G4/G5, App. A and the D02 sheet are aligned.
4. **`p5.account_id` at P0.** Proposed resolution, option B (PROPOSED / NOT APPROVED; owner direction, unsigned): `p5.account_id` would be replaced by the hashed marker `p5.account_binding` (`deferred_to_p5_activation`, D07); the real id would be recorded only in the P5 activation record and execution manifest at WP5.1. See D07 and the schema change batch proposal section 5. Status: implemented in a local schema candidate only; not merged; the merged schema still requires `p5.account_id`.
5. **Non-equivalence check data dependency.** Criterion 1 (signal overlap on overlapping history) needs RANGE-002 signal timestamps on history. SIP data arrives only in P1, after the P0 gate that requires the check to pass. The only history available pre-P0 is the exposed RNG-001 IEX 5-minute archive. The plan does not say which history the overlap is computed on; D09 must (preparer's proposal, not a decision: the exposed archive). Status: documented in WP0.5, the P0 exit gate and the D09 sheet with options (a)/(b)/(c), none selected.
6. **Design says the "ADR 0037 automated check"; no such check exists** (C2). Already ruled; stated here because the P0 exit gate still says "the non-equivalence check passes", which cannot be met until the specification is approved and PR 4 built. Status: stated in WP0.5, the P0 exit gate, A1 §6 and the D09 sheet; how the gate clause is satisfied meanwhile is an owner decision.
7. **Win-rate wording.** Design says win rate is diagnostic *but* the platform gate applies until the deviation is signed; plan §5.1 now matches (C3). Residual risk: Appendix A `gates.win_rate: null` has no default, which is correct, but A1 §8 "gates G0-G10 unchanged" is silent on the win-rate row, so the signed D10 value is what resolves it. Status: A1 §8 now states the platform > 50% gate applies until a D10 deviation is signed.
8. **A1 §7 says "Decision 11 is resolved"** while plan §10 still lists D11 as an open decision requiring a spec value. It is resolved by ruling, but the spec key still needs the recorded value and signature (D11 sheet). Status: A1 §7 and plan §10 D11 reworded accordingly.
9. **Design P3 (2016-2021 single run) vs A1 (P3a 2016-2019, P3b 2020-2021).** Intentional (Amendment 2). Consequence not stated in A1: P3b has half the sample of the design's P3 for the selected exit, which is why D17 needs an explicit P3b trade minimum. Status: noted in A1 §3, plan §10 D17 and the D17 sheet.
10. **Capability checks vs "no orders".** WP0.10/WP2.11 require pinning real broker stop-order semantics before P0 exit, while R14 forbids paper/live orders until executor tests pass. Documentation can answer part; any probe order needs an explicit owner authorization (F3). Status: plan WP0.10 and new stop condition 18 state this; no probe is authorized by these documents.
11. **Governing documents untracked.** Plan v0.5 and Addendum A1 exist only as untracked files in the main checkout (not in the repository HEAD); the design DOCX is untracked by C10. The sign-off packet should pin the SHA-256 of each document signed. Status: stated in the plan P0 exit gate and A1 §7. Plan v0.5 and A1 are now committed on the PR 737 branch; the pinned hash is that of the version actually signed.

---

## 6. Sign-off packet checklist (for the owner's GO / HOLD)

- [ ] Roles named (D08)
- [ ] A1 reviewed (and amended if needed), signed
- [ ] D06 -> D19 -> D17 -> D02 -> D18 signed together (statistics block)
- [ ] D05, D14, D15 signed (fill/execution block); F3, F4 complete
- [ ] D03, D11, C12 signed; F1, F2, F5 complete (else stop per §9.3)
- [ ] D01 signed after WP0.6 contact audit
- [ ] D09 + C2 specification approved, overlap limit stated, reviewers named, history for criterion 1 chosen, handling of the non-equivalence gate clause stated
- [ ] D10, D04, D12, D13, D16, D07 signed
- [ ] C10 custody decided; SHA-256 of every signed document recorded in the packet
- [ ] Economic thesis, feasibility report, hypothesis lineage, order contract signed (WP0.9-0.12)

No signature in this document has been filled by the preparer.
