# RANGE-002 - P0 Decision Register and Governance Approval Package v0.2

| Field | Value |
|---|---|
| Purpose | One owner-facing register of every formal P0 decision, the controlled genesis-enrollment ceremony, the P3a/P3b attempt-limit analysis, the statistical-validation and data-independence rules, the blocker matrix and critical path, and a blank signature page |
| Supersedes | `RANGE-002_P0_Owner_Decision_Package_v0.1.md` (commit `f5cee030`, local branch only, written before PR #738 and PR #739 merged). Content of v0.1 that is still right is kept and marked "(carried from v0.1)"; corrections to v0.1 are listed in section 0.3 |
| Date | 2026-10-10 |
| Base | `origin/main` at `d61f313a` (PR #737 docs, PR #738 Level 1 spec infrastructure, PR #739 Level 1 governance infrastructure, all merged) |
| Status | **DRAFT FOR OWNER REVIEW. Nothing in this document is a decision, a signature, an approval, an enrollment or a freeze.** Every item labelled "Recommendation (not a decision)" is the preparer's proposal. Every signature row is blank and may be filled only by the named human. No AI agent may hold a role or sign (rule R9). |
| Data accessed | None. No RANGE-002 returns, P&L, win rates or profit factors were computed or viewed. No market data, provider or broker call was made. No registry was enrolled, no genesis id was generated or recorded, no spec was frozen, no governed code was run on real values. The only code executed was `draft_skeleton()` in an isolated interpreter (section 4.5), which contains no real values. |
| Documents relied on | Implementation Plan v0.5 ("Plan"); Design Addendum A1 ("A1", DRAFT, unsigned); P0 Decision Sheets v0.1 ("Sheets"); `governing_reconciliation.md` (rulings C1-C13, items C14-C15); `recon.md`; Governance Hardening Design v0.1 ("Hardening"); `RANGE-002_governance_manifest.json`; merged code under `apps/backend/app/research/range002/{spec,governance}/` and `apps/backend/scripts/research/range002/freeze_spec.py`; the Level 2 design set (commit `79e072d7`, local only) and the Approval Signing design (`d1406ec2`, local only); the PR #739 acceptance records `owner_decisions.md` and `finding_dispositions.md` (read-only, outside the repository) |
| Not covered | No gate threshold is opened or changed (G0-G10 stay as in design v0.4 section 6 and are additionally locked by equality validators in the merged schema). No spec value is chosen here. The Level 2 items accepted or deferred by the owner are not reopened (section 6) |

Abbreviations used in the register: FRZ = a real `freeze_spec` run; ENR = first (genesis) enrollment; P1 = P1 start (first data pull, PR 5); P3A = first governed P3a run; MRG = merge of the distinct-role follow-up PR (commit `57dadd52`, local only, see section 6.1).

## RECOMMENDED RULINGS VERSUS FORMALLY APPROVED DECISIONS

**Formally approved decisions in this document: NONE (0).** Every row below is a recommendation or proposal labelled **RECOMMENDED / PROPOSED -- NOT APPROVED**. Nothing here has been signed, adopted, enrolled or frozen. The owner's approval, where it exists, is recorded only by a signed record in section 11 or section 25 against a pinned SHA-256; a recommendation in this table does not substitute for it.

| # | Subject | RECOMMENDED / PROPOSED -- NOT APPROVED | Formally approved? | Detail |
|---|---|---|---|---|
| 1 | D08 roles | Four **named role slots** (research lead, trading-expert reviewer, independent validator, sole P6 approver). Actual independent human validation and a formal separation-of-duties (SoD) selection are **still required** | NO | section 18 |
| 2 | P3a / P3b attempt limits | **ONE** authorized P3a attempt and **ONE** authorized P3b attempt (limits 1 / 1) | NO | sections 3, 12, 19 |
| 3 | C-DR (defect-only reruns) | **No automatic defect-only retries.** A rerun after authorization needs a **separate recovery authorization** (design-only Level 2 recovery, owner-approved incident process). Plan wording amendments are proposals | NO | section 20 |
| 4 | Canonical registry enrollment | **PENDING.** No ceremony, no id, no location, no operator | NO | sections 2, 21 |
| 5 | `p5.account_id` | Escalated mandatory-field conflict. Proposed design: a freeze-time marker plus a separate P5 activation record (option B) | NO | section 22 |
| 6 | A1 vs design v0.4 vs merged schema | Reconcile in writing **before** A1 is submitted for signature | NO | section 23 |
| 7 | D02, D06 and every other unset statistical parameter | **PENDING.** No default substituted | NO | section 24 |

## OWNER PROVISIONAL POLICY DIRECTIONS (PART IV)

These are the owner's **provisional policy directions** as relayed to the preparer. Each is **PROVISIONAL POLICY DIRECTION -- NOT SIGNED**. Names and signed records are still pending. **Nothing is approved unless a signed record exists; none exists.** Where Part IV differs from Parts I-III, Part IV states the owner's direction and the earlier text is kept for history.

| # | Item | PROVISIONAL POLICY DIRECTION -- NOT SIGNED | Signed record? |
|---|---|---|---|
| P-1 | D08 separation of duties | SoD-A for the three signers plus SoD-C's additional validator-independence requirements. This removes SoD-B as a candidate. Identities and attestations obtained separately (names BLANK) | NO |
| P-2 | C-DR | Option (i): no automatic defect-only reruns; ONE authorized P3a attempt and ONE authorized P3b attempt; do not raise attempts to 2 or 3. A technical defect after authorization may permanently end that phase under the current implementation. The Plan must be corrected to say so (proposed text only) | NO |
| P-3 | A1 | Proceed with the two-development-stage architecture (P3a selection, P3b confirmation), subject to a written reconciliation with v0.4 and the merged schema AND independent review of the exit-selection methodology. A1 must not be signed merely because the code assumes it | NO |
| P-4 | P5 account binding | Option B: hashed deferral marker `p5.account_binding` plus a separate P5 activation record (proposal only, not implemented) | NO |
| P-5 | C-EVID | A controlled pre-freeze return-blind feasibility **amendment**, not an unrestricted early data pull; a separate later authorization is needed for any acquisition | NO |
| P-6 | Genesis | Remains unenrolled pending host, registry path, operator, witness and explicit authorizations | NO |

**Part V (sections 38-46)** records the owner's rulings AR-1 to AR-9 as **proposed policy and drafting direction only** (not signatures): the final C-DR Plan wording, the written A1 reconciliation memo, the independent-methodology-review requirements, the P5 option B amendment text, the E1 step-1 draft, six individual review sheets and the lists of remaining blanks and open items.

---

## 0. What changed since v0.1

### 0.1 Facts now on `main` (were "local branch only" in v0.1)

- The spec schema, hashing, loader, manifest loader and `freeze_spec.py` (PR #738) and the run registry, hash chain, exposure ledger, holdout token and results guard (PR #739) are merged. PR #739 was squash-merged on 2026-10-10 15:00:22Z as `d61f313a` on the owner's explicit instruction. The merge was recorded as an infrastructure merge only: the owner record states that P0 sign-offs, canonical genesis activation, real specification freeze, P1, historical data access, backtesting and broker operations were **not** authorized and not done.
- The committed governance manifest is on `main` and is entirely unset: `approved_registry_genesis_id`, `approved_by`, `approved_on` and `p3_attempt_limits.{p3a,p3b}` are all `null`.
- No enrollment CLI exists. `freeze_spec.py` is the only script under `apps/backend/scripts/research/range002/`. The enrollment ceremony therefore calls a Python API directly (section 2).
- Level 1 acceptance is complete as an infrastructure matter (63 findings: 40 resolved, 8 accepted Level 1 limitations, 10 deferred to Level 2, 5 non-blocking diagnostics, 0 open). Former v0.1 item b12 (acceptance items) is therefore closed except for the R1-L1b obligation in section 6.

### 0.2 Items still not on `main`

- The follow-up that rejects identical sign-off role identifiers (`57dadd52`, branch `fix/range002-signoff-distinct-roles`, local, unpushed).
- The Level 2 design set (`79e072d7`, docs only, local) and the Approval Signing design (`d1406ec2`).
- This register itself.

### 0.3 Corrections to v0.1 (made after reading the merged code)

1. `RunRegistry.enrollment` is a **property** (returns a dict), not a method. v0.1 wrote `.enrollment()`. `count_records()` is a method; `genesis_id` and `head_hash` are properties.
2. The namespace scan in `enroll_new` is not "first 1 MB has no newline". The merged scan (`_other_registry_in`) reads each file's first line up to `MAX_RECORD_BYTES`; a file with an over-long first line, an unreadable file, or a deeply nested JSON first line is assumed to be a registry and blocks enrollment. The operational rule is unchanged: nothing but the registry and the lock file in that directory.
3. `namespace_lock` runs `directory.mkdir(parents=True, exist_ok=True)` before locking, so a mistyped directory is silently created. The ceremony should create and verify the directory by hand first (step 2 of section 2.3).
4. v0.1 section 7 item 8 ("Plan header status stale") and the "not on main" statuses in its WP table are now partly obsolete (code merged). The Plan header still says "PR 2 may start with all decision values unset"; that text is stale but no longer misleading about code state.
5. v0.1 recommended deciding statistics in the order D06, D19, D17, D02, D18. The D17 sheet says D17 depends on D06 **and D18**, and D19 eligibility uses the D17 minimum trade count, so the corrected order is in section 5.4.

---

## 1. DECISION REGISTER

### 1.1 How to read the register

- **Current status.** UNSIGNED = a sheet or document exists with options, no value chosen, signature blank. BLANK = no sheet exists or no value is stated anywhere. RECOMMENDED = the preparer or an earlier document records a recommendation, still unsigned. Every row is unsigned today; the labels only say whether a recommendation exists.
- **Recommendation.** Marked "Recommendation (not a decision)". Where the Sheets say the owner must state a number, no number is proposed here.
- **Blocks.** Direct blocks. Because a real freeze is part of P0 exit, anything that blocks FRZ transitively blocks P1 and P3A. "T" means the merged tooling mechanically refuses without it; "G" means the Plan/A1 governance requires it but no tool checks it.
- **Owner signature/date.** Always blank here. Where a detailed signature block exists in the Sheets or A1, sign there and cross-reference the date in section 7.

### 1.2 Register

| ID | Decision | Current status | Recommendation (not a decision) | Evidence needed | Blocks | Owner signature / date |
|---|---|---|---|---|---|---|
| A1 | Sign Addendum A1 (exit selected from a frozen candidate set; P3 split into P3a 2016-2019 and P3b 2020-2021; decision list D01-D19). Three rows: owner, trading-expert reviewer (D19), independent validator (selection rule and P3a test) | UNSIGNED; RECOMMENDED | Sheets: option (b), sign after the D19, D17 and D02 sheets are seen and the wording items in Sheets section 5 are settled. Add: the merged schema already hard-codes A1's partition layout (section 3.4), so rejecting A1 is no longer only a plan reversion | A1 text; Sheets section 5 wording items; D19/D17/D02 sheets; SHA-256 of the exact A1 bytes | FRZ (G; and T indirectly, because the schema assumes A1), P1, P3A | |
| D01 | Register RANGE-002; sign exposure conclusions and holdout applicability (`governance.exposure_signed`) | UNSIGNED; RECOMMENDED | Do not sign until the WP0.6 contact audit is complete, including AI-session history on 2016-2025 intraday data; report unknown contact as unknown, never as none; owner rules explicitly whether other programs' use of the 2022-2025 daily layer is material for an intraday hypothesis | Signed WP0.6 contact audit; exposure ledger; `hypothesis_lineage.yaml` (WP0.11); owner ruling on daily-layer contact | FRZ (T: `governance.exposure_signed` is a P0 field), P4 (G0) | |
| D02 | Hypothesis family and adjustment: P3a selection-aware test over K; number of confirmatory hypotheses in the P4 Holm family; PF >= 1.30 and stress > 0 confirmed | UNSIGNED; RECOMMENDED | Option (a): one Holm family over {G4, G5}, count 2, one-sided alpha 0.05 (stricter reading). Owner states the count. Depends on D06 | D06 signed first; independent validator confirms the statistics; representation check against the schema (`stats.adjustment` is the closed set `holm` / `fixed_sequence`, skeleton default `holm`) | FRZ (T: `stats.hypothesis_family`), PR 11/12/14 | |
| D03 | Universe N; PIT timing; SIP vendor and licence; data budget | UNSIGNED; RECOMMENDED | N = 100; Alpaca SIP only if F1, F2, F5 pass (else stop per Plan 9.3); owner sets a budget cap, not a point estimate. A different vendor is a new external dependency and needs an ADR | F1 (SIP history to 2016-01-01), F2 (delisted coverage), F5 (licence for stored research use), vendor plan confirmation | FRZ (T: `universe.n`, `data.vendor`), P1 | |
| D04 | Yearly consistency gate (>= 3 of 4 years PF > 1.0) | UNSIGNED; RECOMMENDED | Confirm as designed; add that a year with too few trades for a meaningful PF is reported with its count and does not pass; owner or validator sets that per-year minimum | None return-blind (a count rule); any trigger-frequency expectation is return-derived and stays inside the results guard | FRZ (T: `gates.yearly`), PR 12/14 | |
| D05 | Fill, risk and exit-mechanics values (5a-5j: OR completeness, min OR width in ticks, R_pre/R_fill and tolerance, gap fills, same-bar order, tick size, half-day exit minute, halt rule, slippage model, risk limits) | UNSIGNED; RECOMMENDED (5a, 5c-5i); BLANK (numbers in 5b, 5g?, 5j) | Per Sheets table; numeric risk limits, min OR width and caps are the owner's to state, conservative (lower exposure, tighter loss limit) per CLAUDE.md; 5i is "none" if D15 = all-in. Read with D18 (portfolio limits can bind G1) | Return-blind OR-width distribution in ticks and % of price; counts of `NO_TRADE_MINUTE` vs `DATA_GAP`; half-day calendar; tick bands. No post-entry paths | FRZ (T: `signal.or_completeness_rule`, `signal.min_or_width_ticks`, `exit.halfday_offset_min`, `fill.slippage_model`, `fill.halt_policy`, `risk.*` x7), PR 6/8 | |
| D06 | Baselines, bootstrap parameters, adjustment method, confidence level, seeds (UNSET by design, ruling C11) | UNSIGNED; RECOMMENDED | Stationary bootstrap over trading days, one-sided, alpha 0.05, percentile of the recentered null, fixed seeds, mean block length fixed a priori in days (the repo's daily `BLOCK_LEN = 10` is the only precedent; validator confirms or replaces), repetitions at least 10,000; random-entry invalid draws counted `NOT_EXECUTABLE` with denominator preserved. Validator, not the developer, confirms numbers | Synthetic size/power calibration by the validator (allowed); no RANGE-002 data | FRZ (T: `stats.bootstrap.*` x6, `stats.alpha_one_sided`, `controls.random_entry.*` x3), D19/D17/D02 | |
| D07 | P5 contract: paper-account policy, tolerances, cost-ratio contract, extension rules | UNSIGNED; RECOMMENDED | Record the account **policy** at P0 and the ID at WP5.1; cost ratio = sum(realized shortfall)/sum(modeled cost) over trades with positive modeled cost, undefined cases reported as `UNDEFINED`; owner states degradation/drawdown numbers (tighter option) and a maximum number and length of extensions. **Conflict C-P5 (section 8.2): the merged schema makes `p5.account_id` a required non-null P0 field, so the freeze tool cannot accept "ID at WP5.1"** | None return-blind; owner ruling on how `p5.account_id` is satisfied at freeze | FRZ (T: `p5.account_id`, `p5.degradation_tolerance`, `p5.cost_ratio_contract`), PR 15 | |
| D08 | Roles: research lead, trading-expert reviewer, independent validator, sole P6 approver (`governance.roles`; `signoff.owner`, `signoff.trading_expert`, `signoff.independent_validator`) | UNSIGNED; RECOMMENDED | Four distinct humans; no AI role. See the D08 rows below for the separation rule | Names; confirmation whether the owner is also the trading-expert reviewer | FRZ (T: `governance.roles` and the three signoff names; G: R1-L1b), ENR (G: ceremony operator and `approved_by` consistency), every reviewer sign-off | |
| D08-SoD | Separation-of-duties rule (Approval Signing design section 9: SoD-A three distinct humans; SoD-B owner and trading expert may coincide, validator distinct, recorded waiver; SoD-C validator also distinct from the research lead and engine author; SoD-D any overlap) | BLANK (UNSELECTED) | SoD-A as target, SoD-C as minimum acceptable; the owner records any SoD-B waiver explicitly. A technical check cannot prove two identifiers are two people (the follow-up rejects identical identifiers only) | Owner statement of the chosen option; the independent validator must not be the research lead or the person who wrote the engine; recorded engineer list if SoD-C | FRZ (G; owner ruling 5: a genuinely independent validator is required before formal P0 approval or real freeze), MRG (the follow-up needs only the owner's merge authorization and the choice of what "distinct" means; no D01-D19 value) | |
| D09 | ADR 0037 non-equivalence statement; relationship to ORM-001 (merge / shared ledger and family / independent) (`registration.related_programs`) | UNSIGNED; RECOMMENDED | Option (b): shared ledger and shared multiplicity family with ORM-001, separate specs; origin disclosure ("49% target hit before entry") appears in the non-equivalence record | Versioned records of both programs' entry/exit/universe/granularity/falsification condition | FRZ (T: `registration.related_programs`), PR 4, P0 exit | |
| C2-overlap | Numeric maximum signal-overlap for criterion 1 of the ATP v0.14 3A.2 framework | BLANK (owner-stated; the framework asks for "a pre-declared maximum" and gives none) | Tight maximum (lower is more conservative), computed on signal timestamps and direction only; the number is the owner's to state | Signal-timestamp overlap on the chosen history (D09-hist), no returns | PR 4 (no non-equivalence code until the full specification is approved, ruling C2), P0 exit (G) | |
| C2-reviewers | Named reviewers for criteria 2 (materially different reject condition) and 3 (non-reducible mechanism) | BLANK | Signed findings by the trading-expert reviewer and the independent validator with evidence cited, countersigned by the owner | D13 thesis text; D08 roles | PR 4, P0 exit (G) | |
| D09-hist | Which history criterion 1 is computed on, and what satisfies the P0 exit clause "the non-equivalence check passes" while no tool exists | UNSIGNED; RECOMMENDED | Sheets proposal: (a) the already-exposed RNG-001 IEX 5-minute archive, timestamps and direction only, granularity difference recorded. Alternatives (b) reorder with an A1 amendment, (c) owner-authorized early return-blind SIP pull (needs C12, D03 licence, F1, F5 first). For the gate clause: signed reviewer findings on all three criteria against the approved specification | Owner statement of option and clause handling; if (b), an A1 amendment | PR 4, P0 exit (G) | |
| D10 | Win-rate gate (keep platform > 50% or sign a deviation) and drawdown comparator | UNSIGNED; RECOMMENDED | Gate stays and promotion is blocked until the owner signs otherwise; both evaluations displayed (ruling C3). Comparator: random-entry portfolio under identical capital, costs, equity sampling and exposure as primary, SPY as reference. The schema requires an explicit `gates.win_rate` value (no default) | Comparator definition and equity-sampling rule only | FRZ (T: `gates.win_rate`, `gates.max_dd`), PR 12/14, any P6 promotion | |
| D11 | Loader approach recorded; `data.fetch_mode` | UNSIGNED; RECOMMENDED | Confirm ruling C5 (new monthly-chunked fail-closed SIP loader; shared `BarCache` untouched) satisfies design decision 11; the `data.fetch_mode` enumeration must be defined by the owner (no source defines it) | WP1.1 written finding on `bar_cache.py` (already in `recon.md`) | FRZ (T: `data.fetch_mode`), P1 | |
| D12 | Regime definition and single-regime-dependence criterion | UNSIGNED; RECOMMENDED | SPY prior close vs 200-day SMA (causal); both regimes and both halves must have positive net mean R with a minimum trades-per-cell; plus a share cap the owner states. Define before any returns exist | Counts of sessions per regime and per half over 2022-2025 (calendar and SPY daily close only) | FRZ (T: `stats.regime.definition`, `stats.regime.criterion`), PR 11 (G7) | |
| D13 | Economic thesis, competing explanations, naive-ORB definition, binding vs non-binding diagnostics | UNSIGNED; RECOMMENDED | Thesis written and signed by humans (research lead and trading expert), not authored by an agent; naive ORB as Plan WP2.5; binding = G0-G10 only | WP0.9 `economic_thesis.md`; its SHA-256 goes into `governance.economic_thesis_sha` | FRZ (T: `governance.economic_thesis_sha`, `controls.naive_orb.definition`), PR 4 criterion 3, PR 4A, PR 9 | |
| D14 | Execution contract: bar timestamp convention, vendor delay, submit/ack latency, crossed-before-arm policy, stop order type, stop protection, tie-break, EOD lead, reservation | UNSIGNED; RECOMMENDED (crossed-before-arm = SKIP; stop protection after confirmed entry fill; reservation as Plan 3.3); BLANK (latencies, EOD lead, order type, tie-break pick) | Per Sheets table; order type decided only after the F3 broker capability report; latencies set conservatively high after F3/F4; owner states numbers | F3 (broker semantics; any probe order needs separate written owner authorization, R14), F4 (timestamp convention), F10; F11 must NOT be started until the owner rules it return-blind | FRZ (T: `execution.*` x10), WP0.12, PR 4A/8/12A/15 | |
| D15 | Cost accounting mode (all-in vs additive) and components | UNSIGNED; RECOMMENDED | All-in debit (Plan recommendation); G3 (15 bps stress) must stay binding because the conservatism then rests on it | None return-blind | FRZ (T: `costs.accounting_mode`, `costs.components`), PR 8/11 | |
| D16 | Diagnosis taxonomy; P5 shadow run acceptance; execution-quality evidence | UNSIGNED; RECOMMENDED | Adopt the eight labels as explanatory only (never an override of REJECT); shadow acceptance = zero orphan signals, zero duplicate intents, zero look-ahead discrepancies over a number of sampled days the owner states | None | FRZ (T: `diagnostics.taxonomy`, `p5.shadow_acceptance`), PR 12B/15A | |
| D17 | P3 criteria: P3a minimum trades, PF threshold, selection-aware STOP alpha; P3b criteria and P3b trade minimum (`p3.criteria`; `exits.selection.eligibility.min_trades` / `.min_pf`) | UNSIGNED; RECOMMENDED | P3a: 300 trades, PF > 1.0 at base cost, STOP test one-sided alpha 0.05 on the max-statistic over K. P3b: same thresholds as P4 with G1 scaled to two years (150). The 300/150 figures are scaling proposals, **separate from the attempt limits**. Escalated risk C-N (section 3.5): with one attempt a minimum that proves unattainable is a terminal STOP | Depends on D06 and D18; trade-count feasibility cannot be checked return-blind (trigger frequency is return-derived) | FRZ (T: `p3.criteria`, eligibility fields), PR 11/12/13/13B | |
| D18 | Gate computation basis (portfolio-constrained vs signal-level) and trade unit | UNSIGNED; RECOMMENDED | Portfolio-constrained; one entry = one trade including all exit fills; net R = total net P&L of all exit fills / (entry qty x R_fill). Read with D05 5j (tight limits can bind G1) | None | FRZ (T: `gates.basis`, `gates.trade_unit`), PR 12/13/13B/14 | |
| D19 | Exit candidate set (<= 8, four families), complexity order, selection score, tie tolerance, eligibility, STOP test (`exits.*`) | UNSIGNED; RECOMMENDED | Adopt K = 7 (E1, E2a/b, E3a/b, E4a/b) after trading-expert review; delta fixed a priori on a cost scale (0.05 R is an illustrative placeholder only, owner and validator confirm or replace); no adaptive or extra-feature exits | Trading-expert review; validator review of `select_exit` and the max-statistic test; no outcome data | FRZ (T: `exits.candidates`, `exits.complexity_order`, `exits.selection.*` x5), A1, PR 8/11/13 | |
| C10 | Custody of the authoritative design DOCX | UNSIGNED; RECOMMENDED | Wait for S3 manifest tooling, DOCX stays local and untracked, and its SHA-256 and version are recorded in the sign-off packet; a Markdown extraction only with the owner's explicit permission | SHA-256 of the DOCX bytes | G only (traceability of the governing document at sign-off) | |
| C12 | Name the approved isolated non-production research environment and the accountable person | BLANK | Named before PR 5 / WP2.6: no broker credentials (R7), separate from the production box and DB, storage sized to D03, manifest-producing, reachable by the loader; not `ec2-paper`; the laptop is warm standby and Norton blocks the vendor endpoint | Metadata-only reachability test from that host | P1, WP2.6 replay; D09-hist option (c) | |
| M-loc | Canonical registry location (absolute path on a named host) and who may run the ceremony | BLANK | No location proposed. Criteria the owner may weigh: not an agent-writable tree; a local filesystem on which the OS lock works (the Level 1 lock is `msvcrt` on Windows, `fcntl` elsewhere; network shares are untested); consistent with C12 and CLAUDE.md (`ec2-paper` runs the live app, the laptop is standby); a dedicated directory containing only the registry and the lock file | Owner statement of the path and host | ENR, and every later governed run (the registry path is the lineage) | |
| M-ops | Ceremony operator and witness named (humans) | BLANK | Two people present: an operator and a witness who is not the operator | Names | ENR | |
| M-gen | `approved_registry_genesis_id`, `approved_by`, `approved_on` (all-or-nothing triple) | BLANK | Filled only after enrollment, by the single reviewed manifest change in section 2.4. No value may be pre-supplied | Enrollment evidence record (section 2.7) | FRZ (T), P3A (T: results guard compares registry = spec = manifest) | |
| M-lim-p3a | `p3_attempt_limits.p3a` (and spec `p3.max_p3a_attempts`, which must equal it) | BLANK | **Standing recommendation: 1.** Subject to the conflict in section 3.3 (defect-only reruns) which the owner must resolve first | Owner decision after reading section 3 | FRZ (T), P3A (T) | |
| M-lim-p3b | `p3_attempt_limits.p3b` (and spec `p3.max_p3b_attempts`) | BLANK | **Standing recommendation: 1.** Same dependency | Same | FRZ (T), first P3b run (T) | |
| ACC-R1L1b | Obligation from owner ruling 5 (2026-10-10): a genuinely independent validator is required before formal P0 approval or real specification freeze; separate minimal follow-up rejecting identical role identifiers | BLANK for the obligation; follow-up `57dadd52` exists locally, unpushed, unmerged | Name the independent validator (D08) before any P0 sign-off; merge the follow-up only on the owner's explicit instruction, with the walk-away interval | Validator name; follow-up CI evidence | FRZ (G), MRG | |

Notes on the register:

- Row D05 status text contains "5g?" only to flag that the Sheets recommend a rule (same lead before the official early close as on full days, 12:55 ET) while the spec key `exit.halfday_offset_min` still needs the owner's number; the preparer does not set it.
- A1 and D01-D19 are 20 rows, plus C2 (2 rows), C10, C12, D09-hist, the manifest triple, two limits, the registry location, the ceremony roles, D08 and its separation rule, and the R1-L1b obligation: every formal P0 decision named in the assignment appears once.

---

## 2. GENESIS ENROLLMENT PACKAGE

**This section describes a ceremony. It has not been run and must not be run by the preparer or by any AI agent.** The text is written from the merged source on `main` at `d61f313a` (`governance/run_registry.py`, `governance/hashchain.py`, `spec/manifest.py`, `spec/genesis.py`). Read that source again at the commit actually used; the source, not this description, is authoritative.

### 2.1 What the real API does (carried from v0.1, corrected)

`RunRegistry.enroll_new(path, *, enrolled_by, now=None)` is a classmethod and the **only** creating path. It draws the UUIDv4 internally (`_new_genesis_id()`, i.e. `uuid.uuid4()`) and accepts no id parameter. Consequences:

- **No genesis id can exist before enrollment.** No document, commit message, fixture presented as real, chat message or placeholder may contain one. The id becomes known only by reading it back from the enrolled file.
- The id is an identity marker for the research lineage, **not authentication**; anyone who can read the registry file or the committed manifest can read it, and a copy of the registry keeps it (Level 2 limitation, unchanged).

| Merged behaviour | Ceremony consequence |
|---|---|
| Refuses (`RegistryEnrollmentError`) if `path` already exists, even empty (`os.path.lexists`) | The target path must not exist. Never pre-create the registry file |
| `enrolled_by` must be a non-empty string; at most `MAX_ENROLLED_BY_CHARS` = 256 after stripping (`EnrolledByTooLongError`); stored stripped; free text; the row records `authenticated: false` | Use a role-and-person text of at most 256 characters; it is not identity proof |
| Refuses if the directory already contains a file that is, or must be assumed to be, a RANGE-002 registry: first line is a `registry_genesis` row with the marker; or the first line is longer than `MAX_RECORD_BYTES`; or the file is unreadable; or its first line is deeply nested JSON | The registry directory is a dedicated governance namespace: **no logs, binaries or evidence files in it**. Evidence artefacts go elsewhere |
| Takes a namespace OS lock by creating, if absent, the fixed file `.range002-namespace.lock` in the directory (`msvcrt` on Windows, `fcntl` elsewhere; 30 s timeout, `RegistryNamespaceBusyError`); the empty file stays afterwards. It first runs `directory.mkdir(parents=True, exist_ok=True)` | Expect the lock file in the post-ceremony listing. Create and verify the directory by hand beforehand so a typo cannot create a stray directory. Do not delete the lock file |
| `now` defaults to the real UTC clock; `enrolled_at_utc` is stored | Do not pass `now` |
| On any write failure it unlinks the half-created file | If enrollment raises, stop and escalate; do not retry blindly and do not delete anything |
| Level 1: serialises cooperating callers only; follows directory links; no path confinement | Stated limitation, not a protection claim |
| Opening an existing path with `RunRegistry(path)` validates the chain and raises `RegistryNotEnrolledError` for a missing/empty file; it never creates a registry | A read-back cannot create anything |
| Read side: `genesis_id` (property, re-read from row 1 on each access), `enrollment` (property, dict with `enrolled_by`, `enrolled_at_utc`, `authenticated`), `head_hash` (property), `count_records()` (method) | Record exactly what is printed |

### 2.2 Preconditions (all must hold; nothing is enrolled before)

1. The reviewed code is on `main` at a recorded commit (satisfied for the registry code: `d61f313a`). Any ceremony script added later must itself be reviewed and merged first.
2. The owner has **decided M-loc** (canonical registry location) in writing.
3. The owner has **named the operator and witness** (M-ops). Both are humans. No AI agent runs the ceremony or fills `approved_by` / `approved_on` (R9).
4. The owner has given **explicit written authorization to enroll**. The PR #739 merge authorization does not cover it (the owner record states canonical genesis activation was not authorized).
5. The owner has decided the P3 attempt limits (M-lim) or has at least decided that the manifest change will carry them later; recommended before enrollment so the manifest change is a single event (section 2.4).
6. Recommendation (not a decision): D08 roles are named first, so `approved_by` matches a signed D08 name and the independent validator exists for the ceremony review.
7. The target path does not exist and its directory is empty or holds only the lock file.
8. No run, no authorization and no spec freeze precedes enrollment. Enrollment itself consumes no attempt; attempts are consumed only by a `capability_issued` row.
9. A second enrollment is never a retry. A replacement registry would be a different research lineage and would need an independently approved registration, an exposure review and a documented justification, none of which is implemented.

### 2.3 Ceremony steps

Recommendation (not a decision): two people present, recorded live in the evidence template (2.7).

1. Check out `main` at the recorded commit in a clean working tree on the approved host. Record `git rev-parse HEAD` and `git status --porcelain` (must be empty).
2. Record host identity (hostname, OS version, account), the UTC time and the absolute registry path. Create the directory by hand if needed. Confirm the registry path does not exist and list the directory (expected: empty).
3. Run **one** enrollment call: `RunRegistry.enroll_new(path, enrolled_by="<role and person, <= 256 chars>")` through the project's Python environment. No enrollment script exists on `main`; either the owner approves a one-line invocation that is read out and recorded verbatim, or a minimal ceremony script is first reviewed and merged in its own PR. Do **not** wrap the call in anything that prints or logs the id before step 6.
4. Immediately record the SHA-256 and byte length of the genesis file (it should contain exactly the one genesis row; record what is actually found) and `ls -l` of the directory (expected: the registry file and `.range002-namespace.lock`).
5. In a **fresh process**, open `RunRegistry(path)` and read `genesis_id`, `enrollment`, `head_hash`, `count_records()` (expected 1).
6. Record the id exactly as printed; verify it is a canonical lowercase UUIDv4 with `is_canonical_uuid4` from `spec/genesis.py` (the arbiter).
7. Make the registry file read-only at the OS level and store a copy as **evidence** in controlled storage outside the repository (GITHUB-OPS-001: generated evidence is not committed), recording location and SHA-256. The copy must not sit in the registry directory (it would block a future namespace scan and confuse the namespace). A copy is evidence of the genesis, not a second registry.
8. Do not open a run, call `authorize`, freeze a spec, or run any governed code. Stop. Hand the evidence record to the owner.

### 2.4 Filling the manifest: ONE reviewed git change

File: `docs/implementation/evidence/range_002/RANGE-002_governance_manifest.json` (fixed path; read by `load_manifest()` from the **executing checkout**, owner-accepted Level 1 limitation NF3). Parser rules in `spec/manifest.py`:

- Keys are exactly `schema_version`, `approved_registry_genesis_id`, `approved_by`, `approved_on`, `p3_attempt_limits`, `notes`; unknown or missing keys refuse.
- `approved_registry_genesis_id`, `approved_by`, `approved_on` must be **all null or all set**; a partial triple refuses outright.
- `approved_registry_genesis_id` must be a canonical lowercase UUIDv4; `approved_by` a non-blank string; `approved_on` an ISO `YYYY-MM-DD` date not in the future.
- `p3_attempt_limits` has exactly `p3a` and `p3b`, each null or an integer in 1..10,000 (a technical bound, section 3.4). Limits may technically be set independently of the triple, but `freeze_spec` and the results guard require both limits and the genesis, so a half-filled manifest cannot be used.

The change (Recommendation (not a decision)):

- One PR containing **only** those five values: `approved_registry_genesis_id` = the id read back in step 5; `approved_by` = the owner's name as in the signed D08 roles; `approved_on` = the ISO date of approval; `p3_attempt_limits.p3a` and `.p3b` = the owner's decided values. All five or none.
- `notes` and `schema_version` unchanged. The `notes` text will then read as "UNSET", which becomes stale; the preparer proposes leaving it and recording the staleness in the PR description so the diff is exactly five values. A reviewer may instead allow a one-line `notes` edit; either way the manifest canonical hash (which includes `notes`) is what later `capability_issued` rows record.
- A human copies the id. The reviewer re-reads it independently from the registry file and the evidence record, and the PR description cites the evidence record's SHA-256 and the manifest's pre-change SHA-256.
- Walk-away discipline: this is a consequential governance change; minimum 2 hours open before merge (CLAUDE.md). No push or merge by an agent without the owner's explicit instruction (GITHUB-OPS-001 agent rules).
- Because the manifest is read from the executing checkout, the change must be merged to the checkout that later freezes and authorizes, and the freeze must run on that commit.

### 2.5 The spec link

When the real spec is drafted, `governance.registry_genesis_id` must equal the manifest's approved id **and** `p3.max_p3a_attempts` / `p3.max_p3b_attempts` must equal the manifest limits. `freeze_spec` runs `load_manifest()`, `require_genesis()`, `require_limits()`, builds the frozen spec (naming every unset P0 field), then `check_genesis` and `check_limits`, then requires the sign-off fields. The results guard later requires registry genesis = spec genesis = manifest genesis for every partition and records the manifest SHA-256 on each `capability_issued` row.

### 2.6 What must NOT happen

- No enrollment before M-loc, M-ops, written authorization and the preconditions in 2.2.
- No id generated, invented, reserved or illustrated anywhere before enrollment (documents, fixtures, commit messages, chat). This register contains none.
- No second enrollment because "the first was wrong": it creates a different lineage (2.2 item 9). If enrollment is interrupted before step 5, stop and escalate; do not delete files to retry.
- No partial triple, no manifest edit without the evidence record, no manifest change bundled with any other change.
- No agent holds the operator or witness role or fills `approved_by` / `approved_on`.
- No log, binary, evidence copy or other file in the registry directory; no deletion of `.range002-namespace.lock`.
- No `now=` argument; no printing of the id before the read-back.
- No claim that the id authenticates anything; no committing the registry file itself to git (only the id appears, in the manifest).
- No attempt consumed by the ceremony: no `authorize`, no `open_run`.

### 2.7 Evidence template (blank; filled live during the ceremony)

| Field | Value |
|---|---|
| Ceremony date (UTC) | |
| Operator (human) / witness (human) | |
| Owner written authorization to enroll (document, date) | |
| Owner approval of location M-loc (document, date) | |
| Host (hostname, OS, account) | |
| Repo `main` commit SHA; `git status --porcelain` empty (Y/N) | |
| Registry absolute path; directory created by hand (Y/N) | |
| Directory listing before / after | |
| Exact invocation, verbatim, including the `enrolled_by` string | |
| Wall-clock UTC at invocation vs `enrolled_at_utc` | |
| Genesis file SHA-256 and byte length | |
| Genesis id read back in a fresh process | |
| `enrollment` as printed (`enrolled_by`, `enrolled_at_utc`, `authenticated`) | |
| `head_hash`, `count_records()` | |
| `is_canonical_uuid4` result | |
| Read-only set (Y/N); evidence copy location and SHA-256 | |
| Manifest SHA-256 before the change | |
| Manifest PR number, commit SHA, reviewer, open-to-merge interval, merge time | |
| Diff shows exactly the five values (Y/N, by whom) | |
| Spec `governance.registry_genesis_id` and limits equal the manifest (Y/N, by whom, date) | |
| Operator / witness / owner signatures and dates | |

---

## 3. P3a / P3b ATTEMPT LIMITS

### 3.1 Standing recommendation

**Recommendation (not a decision):** `p3_attempt_limits.p3a = 1` and `p3_attempt_limits.p3b = 1` per research lineage: one governed P3a run and one governed P3b run, each evaluating all frozen exit candidates and baselines together. P4 has no manifest limit; it is limited by the holdout rule (one opening per window, whatever happens after authorization). The values are the owner's to write; none is set here.

### 3.2 Semantics, from the merged code (carried from v0.1, re-verified against `d61f313a`)

- A limit counts **governed evaluation runs per (registry genesis = research lineage, phase)**, across all windows, spec hashes, code versions and worktrees sharing the registry. A re-freeze, a P0 edit, another window or another worktree does not create a new attempt. A budget reset argument is refused by name.
- An attempt is **consumed when authorization is issued** (the `capability_issued` row is written before the capability is returned), not when the run finishes. A request refused earlier, and a run merely opened, consume nothing. A failed, aborted or crashed run after that row still counts.
- With a limit of 1, the first P3a authorization is allowed (0 consumed) and a second raises `AttemptLimitExceededError`. P3b is counted independently.
- The check is repeated atomically under the registry writer lock when the row is written; the manifest limit above 10,000 is refused before any state is written.
- No automatic retry, no reset, no recovery code. Recovery would need a documented incident, independent review, owner authorization and a permanent audit record, and is design-only (Hardening section 1; Recovery Procedure design). The owner accepted recovery being design-only (ruling 3 and the Level 2 deferrals).
- Phase order is enforced from registry rows: P3B needs a COMPLETED P3A with a `capability_issued` row and a verified selection record; P4 additionally needs a COMPLETED P3B. A P3A that was authorized and then aborted cannot become COMPLETED, so P3B is then unreachable for the lineage.

### 3.3 Interaction with A1 versus design v0.4, and what a failed run means

- **Under A1 (once signed).** One governed P3a run evaluates all K candidates (K = 7 proposed) and selects exactly one by the frozen rule, inside the same run, before unsealing (Plan WP4.1 step 3). The K-fold search is accounted for by the selection-aware max-statistic test and by recording K in the ledger, **not** by consuming K attempts. A limit of 1 is therefore consistent with K > 1. P3b runs the selected exit only. P4 tests the selected exit once.
- **Under design v0.4 (governs until A1 is signed).** The exit is two fixed variants A/B and P3 is one 2016-2021 run. No spec may be frozen under either form (Plan header). If A1 were rejected, the same limit semantics could apply (one run evaluates both variants), but the merged code cannot express v0.4's P3 (section 3.4). **v0.4 governs until A1 is signed**; nothing in this register changes that.
- **What "failed run after authorization" means.** For this lineage the phase has ended unless a separately documented recovery/registration decision exists. That decision path does not exist in code. It is not a new spec hash, a new date window or a new worktree. A research STOP (P3a not eligible or selection-aware test fails; P3b fails) is a valid completed outcome and is terminal for the registered candidate under Plan WP4.1 regardless of limits. The consequential case is a **non-research failure** (crash, `INCONCLUSIVE_ENGINE`, `INCONCLUSIVE_DATA`, `INCONCLUSIVE_TECHNICAL`) after authorization.
- Validator item (not asserted here): confirm that the guard refuses P3B after a P3A whose recorded verdict is `STOP`, and that a STOP run can reach COMPLETED; the code shows the verdict transitions (`UNTESTED -> STOP | EXIT_SELECTED`) and a selection-record requirement, but the preparer did not execute governed code.

### 3.4 The 10,000 ceiling

`MAX_ATTEMPT_LIMIT = 10_000` (`spec/limits.py`) is a **technical** upper bound that rejects absurd values at validation time. It does not set, suggest or imply a research budget; commit `8c83e9fc` says so in its message. The owner's values are the research budget. Do not read 10,000 as permission.

### 3.5 Conflicts and risks found (escalated, not resolved)

**C-DR. Defect-only reruns versus limit 1 (Plan vs merged registry).** Plan rule R3 ("defect-only reruns need a logged defect record and owner approval"), WP4.0 step 2 (a failed stage-1 control gives `INCONCLUSIVE_ENGINE`, the defect "goes through the defect-only rerun protocol") and WP4.1 ("Defect-only reruns. Allowed only for a bug... Each rerun is a ledger row") all assume a rerun can follow a defect. The registry counts the attempt at `capability_issued`, which precedes the stage-1 controls, and has no retry or reset path. With limits of 1 a defect-only rerun of P3a or P3b is impossible in code, and for P4 the holdout window is consumed on authorization with no reissue. Hardening section 1 describes a holdout recovery that makes the run count 2, but it is design-only and depends on the sealed store (WP4.0) and an owner key. **The owner must choose, before writing the limits**: (i) limits 1 and 1, with the Plan text conformed so nobody assumes a rerun path exists, and the risk of technical failure reduced by validating the engine only on synthetic fixtures and the `REPLAY_RNG001` partition (engine validation, never citable) before any P3 authorization; (ii) limits above 1, noting that the code cannot tell a defect rerun from an outcome-driven retry, so any value above 1 also permits an outcome-driven retry; (iii) implement and approve the recovery design first. No option is selected here.

**C-SCHEMA. Partition layout is locked to A1 (A1 vs v0.4 vs merged schema).** `schema.py` fixes `partitions.development_selection`, `development_confirmation`, `holdout` and `exposed` by equality validators to the A1 layout, and the registry has phases P3A and P3B and the verdict machine has `EXIT_SELECTED`. A frozen spec under v0.4's single 2016-2021 P3 with fixed A/B exits is therefore not expressible without code changes, and the guard refuses P3 while `exits.candidates` / `exits.selection` are null. The Plan's statement that rejecting A1 leaves "the v0.5 exit machinery unusable" understates this: the infrastructure merged on `main` also assumes A1. Escalation only; A1's signature is the owner's.

**C-P3B-N. P3b sample size and the one-run policy.** P3b covers two of the design's six development years, for the selected exit only. D17 sets its trade minimum (recommended 150, the P4 rate of 75 trades per year over two years). With a limit of 1 a P3b that misses the minimum is a terminal STOP; the window cannot be extended and the run cannot be repeated. Equally, P3a eligibility requires every candidate to reach the P3a minimum (300). Trade counts differ across candidates under D18's portfolio-constrained basis (exit timing changes capital occupancy), and the attainable count cannot be checked return-blind (trigger frequency is return-derived; F11 is not to be started without the owner's return-blind ruling). The sample-size minimums are D17 items and are **not** attempt limits; this register does not set them. The owner should decide the D17 minimums knowing that an unattainable minimum converts directly into a lineage-ending STOP.

**C-P4. "P4 x1" has no manifest key.** Plan WP0.7 plans "P3a x1 covering all K, P3b x1, P4 x1"; the code enforces manifest limits for P3A/P3B only and treats the holdout by the once-per-window rule. Consistent in effect, but the trial-ledger row should state that P4's single run comes from the holdout rule, not from a manifest value.

**C-LEDGER. Ledger vocabulary.** Plan WP2.7A ("control redraws attempts") and Hardening ("trial ledger") use "attempt" in other senses; section 3.2 defines the governance attempt. The registration row (WP0.7) should use the registry's terms.

---

## 4. STATISTICAL VALIDATION RULES AND DATA INDEPENDENCE

### 4.1 Gates G0-G10 (thresholds fixed; not open)

Source: design v0.4 section 6 as reproduced in Plan section 5.1. The merged schema additionally locks `gates.min_trades = 300`, `gates.pf_base = 1.30`, `gates.stress_mean_positive = true`, `gates.redundancy_corr_max = 0.85`, `p5.min_days = 60`, `p5.min_trades = 100`, `p5.max_cost_ratio = 1.5` by equality validators; changing any needs a code change and the v0.4 owner, not a spec edit. Any requested gate modification goes back to the v0.4 owner.

| ID | Gate | Threshold | Open item |
|---|---|---|---|
| G0 | Holdout independence | Exposure audit signed; no material contamination | D01 |
| G1 | Sample | >= 300 trades in 2022-2025 | trade unit and basis: D18 |
| G2 | Profit factor | >= 1.30 at base cost (zero-loss denominator is `UNDEFINED`, never +infinity) | none |
| G3 | Stress cost | Mean net return > 0 at 15 bps per side | accounting mode: D15 |
| G4 | Significance | Adjusted one-sided test of mean net R > 0 at alpha 0.05, day-clustered bootstrap | method D06; family D02 |
| G5 | Random baseline | Mean net R above random entry; adjusted lower bound of the paired difference > 0 | adjustment and family membership D02 |
| G6 | Yearly consistency | >= 3 of 4 calendar years with PF > 1.0 (proposed) | D04 |
| G7 | Regime robustness | Profit not from a single regime or half | D12 |
| G8 | Max drawdown | No worse than the pre-registered comparator | D10 |
| G9 | Data and engine reliability | Coverage, no look-ahead, stage-1 controls passed, engine validation passed | none |
| G10 | Redundancy | Correlation with approved strategies <= 0.85, else flagged and not promotable | none |
| - | Win rate | Platform > 50% gate applies until a D10 deviation is signed; both evaluations displayed (ruling C3) | D10 |

### 4.2 D02 hypothesis family

"m = 1" in A1 and the Plan counts **exit configurations** (one selected exit at P4; K recorded in the ledger). It is not the number of confirmatory hypotheses, which is the owner's D02 value. Design sections 5.3 and 6 require two corrected tests (G4 and G5).

| Option | What is tested | Consequence |
|---|---|---|
| (a) one Holm family over {G4, G5}, count 2, one-sided alpha 0.05 | G4 and G5 jointly adjusted | Strictest pass condition; costs little because both gates are required anyway. Recommendation (not a decision): (a) |
| (b) G4 is the Holm family (count 1); G5 a separate required gate at its own declared alpha (intersection-union) | Each must pass at its own level | No cross-adjustment; less strict than (a) |
| (c) fixed sequence: G4 then G5, each at 0.05, G5 only if G4 passes | Same pass condition as (b) | Differs in what is evaluated and reported when G4 fails |

Under any option the gate function implements the declared procedure exactly and labels it; K and the family composition are recorded in the ledger and the P4 report; uncorrected significance is not promotion evidence; an unadjusted bootstrap interval is never called "Holm-adjusted". Depends on D06. **Representation note:** the schema's `stats.adjustment` is the closed set `holm` / `fixed_sequence` and the skeleton pre-sets it to `holm` (not null), so the freeze tool will not force a D02 decision on that field; option (b) is a mixed procedure whose representation in `hypothesis_family` (an open value) plus `adjustment = holm` the validator must confirm. The draft must state the chosen option explicitly rather than inherit the skeleton default.

### 4.3 D06 bootstrap and baselines (UNSET by design)

Left unset on purpose (ruling C11: the "platform convention adopted from MR-002" claim was not supported by code). The skeleton fixes only the resampling unit (`stats.bootstrap.cluster = "trading_day"`) and the adjustment preset above. The owner must supply:

| Parameter | Spec key | Notes |
|---|---|---|
| Method | `stats.bootstrap.method` | options: stationary over days, circular fixed-block over days, iid day-clusters |
| Mean block length | `stats.bootstrap.block_len` | fixed a priori, in days; must not be estimated from RANGE-002 data (that would be return-derived) |
| Repetitions | `stats.bootstrap.reps` | recommendation: at least 10,000 for the selection test and G4/G5 |
| Interval type | `stats.bootstrap.ci_type` | e.g. percentile of the recentered null |
| Confidence level / alpha | `stats.bootstrap.confidence_level`, `stats.alpha_one_sided` | recommendation: one-sided 0.05 |
| Seed | `stats.bootstrap.seed` | fixed |
| Random-entry baseline | `controls.random_entry.repetitions`, `.seed`, `.invalid_draw_policy` | matched on eligible symbols, time window, trade count, capital and risk budget; not conditioned on future breakout; invalid draws logged, denominator preserved (R16) |
| Naive ORB | `controls.naive_orb.definition` | D13 |

No bootstrap exists today that is day-clustered and stationary; existing code is a design reference only. Synthetic size/power calibration by the independent validator is allowed and recommended. G5 estimand as in Plan WP3.3 (day-level pairing; days with RANGE-002 trades but no valid random draw are counted and reported).

### 4.4 Other statistical items

- **D12 regime.** Define before any returns exist; recommended SPY prior close vs 200-day SMA; both regimes and both halves reported with a minimum trades-per-cell so an undefined cell cannot pass. The RNG-001 lesson: E-vwap+gate showed PF 1.53 on the full sample and 0.68 on its first half.
- **D18 gate basis.** Gates computed on one declared trade set; signal-level reported as a diagnostic; partial fills and scale-outs are one trade.
- **Selection rule (D19/A1).** Eligibility (trades >= D17 P3a minimum, PF > 1.0 at base cost); score = one-sided lower bound of mean net R per trade from the day-clustered bootstrap; pick highest score, ties within delta go to the lower complexity rank; STOP if none eligible or the max-statistic test fails at the D17 level. Pure function `select_exit`; selection record hashed and appended before unsealing (R18).
- **Controls before strategy (R17, WP4.0).** Stage-1 controls are computed with strategy results sealed; a control failure gives `INCONCLUSIVE_ENGINE` and the sealed results are never opened for that run (see C-DR).
- **Verdict states** are a closed set (Plan 5.2). `REJECT` and `STOP` are terminal for the registered spec; `INCONCLUSIVE_*` is not a soft pass.

### 4.5 Inputs the freeze tool requires

Reproduced from the real skeleton with `draft_skeleton()` in an isolated interpreter (`python -I`), which contains no real values. The skeleton has 107 leaf values, 72 of which are `null` and 35 fixed by the plan. Of the 72 nulls, `registration.trial_ledger_id` is exempt (set by the run registry, not a P0 decision) and the five `signoff.*` fields are handled separately (below). That leaves **66 P0 fields** that `FrozenSpec.from_draft` names if unset. Grouped by decision:

| Decision | Dotted paths that must be set |
|---|---|
| D09 | `registration.related_programs` |
| D03 | `universe.n`, `data.vendor` |
| D11 | `data.fetch_mode` |
| D05 | `signal.or_completeness_rule`, `signal.min_or_width_ticks`, `exit.halfday_offset_min`, `fill.slippage_model`, `fill.halt_policy`, `risk.per_trade_pct`, `risk.per_name_cap`, `risk.gross_cap`, `risk.max_concurrent`, `risk.daily_loss_limit`, `risk.max_participation`, `risk.fill_risk_tolerance` |
| D19 (eligibility values come from D17) | `exits.candidates`, `exits.complexity_order`, `exits.selection.score`, `exits.selection.tie_tolerance_r`, `exits.selection.eligibility.min_trades`, `exits.selection.eligibility.min_pf`, `exits.selection.stop_test` |
| D15 | `costs.accounting_mode`, `costs.components` |
| D06 | `controls.random_entry.repetitions`, `controls.random_entry.seed`, `controls.random_entry.invalid_draw_policy`, `stats.bootstrap.method`, `stats.bootstrap.block_len`, `stats.bootstrap.ci_type`, `stats.bootstrap.confidence_level`, `stats.bootstrap.reps`, `stats.bootstrap.seed`, `stats.alpha_one_sided` |
| D13 | `controls.naive_orb.definition`, `governance.economic_thesis_sha` |
| D02 | `stats.hypothesis_family` |
| D12 | `stats.regime.definition`, `stats.regime.criterion` |
| D14 | `execution.bar_timestamp_convention`, `execution.vendor_delay_ms`, `execution.submit_latency_ms`, `execution.ack_latency_ms`, `execution.crossed_before_arm_policy`, `execution.order_type`, `execution.stop_protection_policy`, `execution.tie_break`, `execution.eod_lead_s`, `execution.order_reservation_policy` |
| D17 | `p3.criteria` |
| M-lim | `p3.max_p3a_attempts`, `p3.max_p3b_attempts` (must equal the manifest) |
| D18 | `gates.basis`, `gates.trade_unit` |
| D04 | `gates.yearly` |
| D10 | `gates.win_rate`, `gates.max_dd` |
| D07 | `p5.account_id`, `p5.degradation_tolerance`, `p5.cost_ratio_contract` |
| D16 | `p5.shadow_acceptance`, `diagnostics.taxonomy` |
| D08 | `governance.roles` |
| D01 | `governance.exposure_signed` |
| M-gen | `governance.registry_genesis_id` (must equal the manifest) |

Total 66. In addition `freeze_spec` requires, already present in the draft before freezing, the human sign-off fields `signoff.owner`, `signoff.trading_expert`, `signoff.independent_validator` and `signoff.date` (not in the future); `signoff.spec_sha256` is computed by the tool (a preset that differs from the content hash refuses). The tool refuses unless the manifest is approved (genesis triple and both limits) and equal to the spec; it never overwrites an existing output file and never fabricates a sign-off. The tool checks only that the sign-off strings are present; it does not check A1, the other documents or that the three names are different people (the local follow-up `57dadd52` adds only an identical-identifier check).

Fixed by the skeleton (not owner values): program, spec_version, instrument type, minimum price $10, ADV window 20 days, monthly rebuild, delisted included, SIP 1-minute RTH data with New York time, OR window 09:30:00-09:59:59, entry window 10:00:00-14:59:59, tick offset 1, one entry per symbol-day, stop at OR low, EOD flat 15:55:00, same-bar `worst_case`, costs 5 and 15 bps per side, the four partitions, bootstrap cluster `trading_day`, adjustment preset `holm`, and the locked gate and P5 thresholds in 4.1.

### 4.6 Data independence and holdout exposure

Partitions (fixed by the schema, per A1):

| Phase | Window | Runs |
|---|---|---|
| P3a selection | 2016-01-01 to 2019-12-31 | all K candidates, deterministic selection |
| P3b confirmation | 2020-01-01 to 2021-12-31 | selected exit only |
| P4 holdout | 2022-01-01 to 2025-12-31 | selected exit only, once |
| Exposed (R2) | 2026-01-01 to 2026-07-31 | never in a decisive run (R2); `REPLAY_RNG001` engine validation only, never citable; PAPER must start strictly after R2 end |

Known exposure: the RNG-001 backtest (2026-01-02 to 06-12), the 18-name / 126-session entry study (through July 2026), the E-vwap+gate splits, and the "49% target hit before entry" finding as the idea's origin (per the Sheets and Plan WP0.6; RNG-001 report). **D01 evidence** (from v0.1 section 4.2, carried): a completed and signed WP0.6 contact audit of every session or program that touched 2016-2025 data, with unknown contact reported as unknown, including AI-session history; the owner's explicit ruling on whether other programs' use of the 2022-2025 **daily** layer (momentum, low-vol, FI) is material for an **intraday** hypothesis; the exposure ledger and `hypothesis_lineage.yaml` as return-blind evidence; `governance.exposure_signed` as the spec key. If 2022-2025 is materially exposed, Plan stop condition 9.2 applies and the holdout must be replaced by owner decision.

How the merged code enforces independence (Level 1): the guard refuses a partition overlapping R2, the spec `exposed` list or the signed exposure ledger; all overlapping exposure refuses (severity stays BLOCKING until an approved policy exists, ruling a7 in v0.1); the holdout opens once per window, whatever happens after authorization, for any spec hash with an overlapping window; PAPER and REPLAY ranges are bounded. This register accessed no data and adds no exposure; neither does any step in section 2.

Format note: the Plan and Sheets say the exposure ledger is `exposure_ledger.yaml` and the frozen spec is YAML; the merged code uses JSON for the ledger loader and `freeze_spec` writes JSON (`--out FROZEN`). Wording conformance is a follow-up, not a decision.

---

## 5. BLOCKER MATRIX AND CRITICAL PATH

### 5.1 Matrix

Legend: T = tooling refuses without it; G = governance requires it, no tool checks it; (T/G) both; blank = not a blocker for that milestone. Items blocking FRZ transitively block P1 and P3A. Rows not listed (D04, D10-D12, D15, D16, D18 etc.) follow the same pattern as the first row group.

| Item | (a) real freeze | (b) first enrollment | (c) P1 start | (d) first P3a run | (e) distinct-role PR merge |
|---|---|---|---|---|---|
| A1 signature | G (and the schema assumes A1) | | via P0 exit | G (Plan stop 9.16; guard refuses null criteria) | |
| D01 | T (`exposure_signed`) + G (audit) | | via P0 exit | via spec | |
| D02, D04, D06, D10, D12, D13, D14, D15, D16, D17, D18, D19, D05, D07, D09 | T (each owns spec keys, section 4.5) | | via P0 exit | via spec hash | |
| D03, D11 | T | | G (vendor, licence, budget before any pull) | | |
| C12 | | | G (before PR 5 / WP2.6) | | |
| C2 overlap, reviewers, D09-hist | G | | G (P0 exit) | | |
| C10 | G | | | | |
| D08 roles | T (roles, three names) | G (operator, `approved_by`) | via P0 exit | via spec | |
| D08-SoD / R1-L1b independent validator | G | | | | owner merge authorization; the SoD choice defines "distinct" |
| M-loc, M-ops, authorization to enroll | | G (all three) | | | |
| M-gen (triple), M-lim (both limits) | T | | | T (guard compares registry = spec = manifest; limits equal) | |
| Signed WP0.5-WP0.12 artefacts | G | | | | |
| F1, F2, F5 (data feasibility) | | | G (else stop per Plan 9.3) | | |
| F3, F4 (broker, timestamps) | G via D14 | | | | |

Additional P3A prerequisites outside the decision list: P1 data and manifests, the P2 engine and exit mechanics, D17/D18/D19 signed, the stage-1 control machinery, and a COMPLETED nothing before it (P3A is the first phase).

### 5.2 Critical path (Recommendation (not a decision) on order)

1. **Name the D08 roles and select the separation rule** (including the independent validator). Everything needing a reviewer waits on it, and ruling 5 requires the validator before any P0 approval or freeze.
2. **Start the long-lead external items in parallel** (not governed by anything else): C12 environment, D03 vendor/licence/history (F1, F2, F5), C10 custody, F3/F4 documentation checks. These gate P1.
3. **Decide the attempt-limit question** (section 3, including conflict C-DR), then **M-loc, M-ops and written authorization to enroll**; run the section 2 ceremony; merge the single manifest change (genesis triple plus both limits).
4. **Statistics block in corrected order**: D06, then D18 (read with D05 5j), then D19 and D17 together (D19 eligibility uses the D17 minimum), then D02, then the A1 signature after the validator has reviewed `select_exit` and the P3a test.
5. **Fill/execution block**: D05, D14, D15, after F3/F4.
6. **WP0.6 contact audit, then D01**; D09 and C2 (overlap limit, reviewers, history option, gate-clause handling), then PR 4 and the non-equivalence record; D13 thesis (human-written); then D10, D04, D12, D16, D07 (including the `p5.account_id` question, conflict C-P5).
7. **Draft the real spec** with `governance.registry_genesis_id` and both limits equal to the manifest; sign-off fields filled by the named humans; pin the SHA-256 of every signed document (section 7); only then a real `freeze_spec`.
8. **P0 exit, then P1** (PR 5 onward) in the approved environment.

---

## 6. RECONCILIATION WITH ACCEPTED LEVEL 1 LIMITATIONS AND DEFERRED LEVEL 2 ITEMS

This section records status only. None of these items is reopened. The Level 1 claim wording must not imply any Level 2 control.

### 6.1 Accepted Level 1 behaviour limitations relevant to P0

| Item | Owner ruling (2026-10-10, via the acceptance record) | Consequence for this register |
|---|---|---|
| R1-L1b: the same person can occupy all three sign-off roles | Accepted for the infrastructure merge. **A genuinely independent validator is required before formal RANGE-002 P0 approval or real specification freeze.** Follow-up (reject identical role identifiers, not identity verification) prepared as `57dadd52`, local, unpushed; conflict check: no conflict with the governing design | Register rows D08, D08-SoD and ACC-R1L1b. The tool does not enforce it today. It must be satisfied procedurally before FRZ, and the follow-up merges only on explicit owner instruction. A technical check cannot prove two identifiers are two people |
| PH3-fork: a capability is run-bound, not process-bound | Accepted | The first governed run must not be started in a process whose forks are uncontrolled; no register item |
| PH3-A5: directory aliases, no physical path confinement | Accepted with documented limitation | M-loc: a linked directory is followed, so record the real path and the host; do not rely on the path for confinement |
| Torn-tail fail-closed lockout (R4-N6, R6-NF8) | Accepted; recovery is a separate owner-authorized procedure, design only | An interrupted write to the registry locks it closed; see C-DR for why this raises the cost of a technical failure |
| NF3: manifest approved out of band / read from the executing checkout | Accepted; enforcement is Level 2 | The manifest change must be merged to, and the freeze and runs executed from, the same reviewed checkout (section 2.4); editing the file on disk is not defended |
| R1-M4 import-lint bypasses | Accepted as a developer safeguard | none |

Related accepted facts: sign-off today is three typed strings and a content hash, not an authenticated signature (H4 deferred), so the SHA-256 pinning in section 7 is the procedural substitute; `enrolled_by` and `approved_by` are unauthenticated text; a copied registry keeps the (public) genesis id.

### 6.2 Deferred Level 2 items (design only, not implemented, not authorized)

H4 signed approvals (KMS, two-phase freeze); M1 trusted execution boundary; M3 external anchoring of registry and recovery heads; copied-registry (genesis copy) detection; holdout recovery implementation; exposure severity policy (everything overlapping stays BLOCKING); registry torn-tail recovery. Their designs live on unmerged local branches (`79e072d7`, `d1406ec2`); the Level 2 design index maps each to its document and open owner questions. D08's separation-of-duties options are the one place where the signing design bears directly on a P0 decision, and nothing in it is selected.

### 6.3 Statement of effect

The PR #739 merge is not a P0 approval, a genesis activation, a freeze authorization or a data-access authorization. The owner record lists the genesis id, the attempt limits, A1, D01-D19, D08, C12 and SIP vendor/licence as "separate, still open P0 owner decisions".

---

## 7. SIGNATURE PAGE (all rows blank)

No row below has been filled by the preparer. No AI agent may sign, hold a role or fill a row (R9). Where an item has a detailed signature block in the Sheets or A1, sign **there** and record the date here as a cross-reference; do not sign twice with different wording.

### 7.1 Formal decisions

| Ref | Decision | Option / value stated by the owner | Signer (role, name) | Signature | Date |
|---|---|---|---|---|---|
| A1 | Approve / reject / amend (A1 section 10 has three rows) | | | | |
| D01 | Exposure conclusions and holdout applicability | | | | |
| D02 | Option (a)/(b)/(c) and confirmatory hypothesis count | | | | |
| D03 | N; PIT timing; vendor; licence; data budget | | | | |
| D04 | Yearly gate | | | | |
| D05 | Fill, risk and exit-mechanics values (5a-5j) | | | | |
| D06 | Bootstrap, baselines, seeds, alpha | | | | |
| D07 | P5 policy, tolerances, cost-ratio contract; resolution of `p5.account_id` at freeze | | | | |
| D08 | Roles (7.2) | | | | |
| D08-SoD | Separation-of-duties option and any recorded waiver | | | | |
| D09 | ADR 0037 statement; ORM-001 relationship | | | | |
| D09-hist | History for criterion 1; handling of the gate clause | | | | |
| C2 | Numeric overlap limit | | | | |
| C2 | Reviewers for criteria 2 and 3 | | | | |
| D10 | Win-rate gate or deviation; drawdown comparator | | | | |
| D11 | Loader approach; `data.fetch_mode` | | | | |
| D12 | Regime definition and criterion | | | | |
| D13 | Economic thesis; naive ORB; binding vs non-binding diagnostics | | | | |
| D14 | Execution contract | | | | |
| D15 | Cost accounting mode | | | | |
| D16 | Diagnosis taxonomy; shadow acceptance | | | | |
| D17 | P3a and P3b criteria and trade minimums | | | | |
| D18 | Gate basis and trade unit | | | | |
| D19 | Exit candidate set and selection rule | | | | |
| C10 | DOCX custody | | | | |
| C12 | Research environment name and accountable person | | | | |
| M-loc | Canonical registry location and host | | | | |
| M-ops | Ceremony operator and witness named | | | | |
| M-auth | Written authorization to run the enrollment ceremony | | | | |
| M-gen | Genesis triple (filled **after** enrollment, via the manifest PR) | | | | |
| M-lim | `p3_attempt_limits.p3a` | | | | |
| M-lim | `p3_attempt_limits.p3b` | | | | |
| C-DR | Ruling on defect-only reruns versus the attempt limit (section 3.5) | | | | |
| ACC-R1L1b | Independent validator named; merge instruction for `57dadd52` (if any) | | | | |

### 7.2 D08 roles

| Role | Name | Signature | Date |
|---|---|---|---|
| Research lead | | | |
| Trading-expert reviewer | | | |
| Independent validator | | | |
| P6 approver (sole) | | | |

### 7.3 SHA-256 pinning requirement for every signed document

Every document a signature relies on is pinned by the SHA-256 of its **exact bytes at a named git commit** (LF line endings), recorded in the sign-off packet (Plan P0 exit gate; A1 section 7). The packet is invalid if any pinned hash differs from the bytes actually signed, or if a signed document changes afterwards without a new signature. Hashes are computed at signing time, not now, because the documents may still be amended. A hash proves which bytes were signed; it does not authenticate the signer (H4 is deferred).

| Document | Git commit SHA | SHA-256 | Computed by / date |
|---|---|---|---|
| Research design v0.4 DOCX (C10 custody pending; not in git) | n/a | | |
| Addendum A1 | | | |
| Implementation Plan v0.5 | | | |
| P0 Decision Sheets v0.1 | | | |
| This register v0.2 | | | |
| `governing_reconciliation.md` | | | |
| `recon.md` | | | |
| RNG-001 Rejection Summary Report | | | |
| Economic thesis (WP0.9) | | | |
| Exposure ledger (signed) | | | |
| Governance manifest (after fill) | | | |
| Genesis evidence file (section 2.3 step 7; not in git) | n/a | | |
| Frozen spec (`spec_sha256`, after freeze) | | | |

### 7.4 Acknowledgement of already-approved directions (optional, carried from v0.1 section 6.4)

I acknowledge the Level 1 governance direction, UUIDv4 genesis as an identity marker, the attempt-budget semantics (consumed at `capability_issued`, per lineage and phase, no reset), the 10,000 technical ceiling, holdout-once-per-window, exposure severity BLOCKING, recovery design-only and the CI verifier as the approved basis for Level 1, and that the Level 2 controls in section 6.2 are not in force.

| Owner | Signature | Date |
|---|---|---|
| | | |

---

## 8. Inconsistencies found (escalated; none changes a gate)

### 8.1 Carried from v0.1 and still open

1. Sheets and Plan Appendix A do not list the manifest triple or `p3_attempt_limits` as owner values, although `freeze_spec` refuses without them. Added here as M-gen and M-lim.
2. Exposure severity: Hardening section 3 proposes three levels with a downgrade path; the owner's direction keeps everything BLOCKING until a policy is approved. Read Hardening section 3 as a proposal.
3. Hardening section 1.8 uses "m = 1" for the family and describes a holdout recovery; recovery is design-only and "m = 1" counts exit configurations, not hypotheses.
4. Plan WP0.7 "P4 x1" has no manifest key (C-P4).
5. Plan status text ("PR 2 may start...") is stale.
6. Plan P0 gate vs PR 5: P1 starts after P0 exit; D03/D11 labelled "P1" in the Plan must not be read as signable late.
7. Class-a directions (Level 1, UUIDv4, attempt semantics, recovery design-only) are recorded in commit messages and docstrings, not in a signed owner document; section 7.4 offers one acknowledgement.

### 8.2 New in v0.2

- **C-DR** defect-only reruns versus limit 1 (section 3.5).
- **C-SCHEMA** partition layout, exit-selection fields and phases on `main` assume A1 (section 3.5).
- **C-P3B-N** P3b/P3a trade minimums under a single attempt (section 3.5).
- **C-P5** `p5.account_id` is a required non-null P0 field in the merged schema, but D07 and Plan WP5.1 provision the account in P5. The freeze tool will refuse with the field null, and the preparer will not invent a value. Owner ruling needed on how the field is satisfied at freeze (the Sheets already flagged the timing; the schema now makes it blocking).
- **C-D02-REPR** the skeleton pre-sets `stats.adjustment = holm`, so the tool does not force the D02 choice, and the closed set may not express option (b) cleanly (section 4.2).
- **C-ORDER** D17 depends on D18 and D19 on D17's minimum; v0.1's order was corrected (section 5.2).
- **C-TOOL-NO-CHECK** `freeze_spec` verifies sign-off presence and hash only; it does not check A1, document hashes, distinct roles (until `57dadd52`) or the independent-validator obligation. These are procedural controls in this register.
- **C-ENROLL-CLI** no enrollment script exists; the ceremony call must be read out verbatim or a reviewed ceremony script merged first (section 2.3 step 3).
- **C-FORMAT** Plan/Sheets say YAML for the exposure ledger and frozen spec; code uses JSON.
- **C-NOTES** the manifest `notes` field will read "UNSET" after fill (section 2.4).

---

## 9. Owner actions needed now (short list)

1. Name the four D08 roles and choose the separation rule; name the independent validator.
2. Rule on the attempt-limit question (conflict C-DR) and state the two limit values.
3. Decide the registry location, host, operator and witness, and give written authorization for the ceremony (or defer it).
4. Start the long-lead items: C12 environment, SIP vendor/licence/history checks (D03, F1, F2, F5), C10 custody.
5. Decide whether the local follow-up `57dadd52` is to be pushed and merged.
6. Rule on `p5.account_id` at freeze (C-P5).

Nothing else is requested before those; all other decisions follow the critical path in section 5.2.

---

# PART II - OWNER-READY FORMAL APPROVAL PACKAGE (added on the owner directive)

Part II extends Part I (sections 0-9). It adds, in order: per-decision reconciliation blocks (section 10), blank draft approval records (section 11), reconciliation of the one-run policy to the real windows (section 12), the statistical validation decision matrix (section 13), the freeze-field trace (section 14), validator independence and the signature matrix (section 15), the ordered blocker list (section 16) and the GO/NO-GO recommendation (section 17). Section 2 of Part I remains the description of the genesis enrollment ceremony; nothing in Part II executes it.

Conventions for section 10. "Governing text" cites the research design v0.4 **as quoted in the repository documents** (the DOCX is not in the repository, ruling C10; every v0.4 citation below is second-hand through the Sheets, the Plan or A1) plus the Plan section and the merged code. Every value is labelled **PROPOSED / NOT APPROVED** and traced to its source; where the documents give no value the text says **NO VALUE PROPOSED**. "Decision authority" and "Required signatures" follow design s10.3 (technical team: data/engine/evidence; trading expert: hypothesis, trade logic, execution limits; independent validator: test scope; one final approver) and A1 s10; apart from A1's three rows, the signature sets are the preparer's proposal (not a decision). Status for every block: **UNSIGNED**.

---

## 10. PER-DECISION RECONCILIATION (A1 and D01-D19)

### A1 - Governing-Design Addendum A1

| Item | Content |
|---|---|
| Governing text | Design v0.4 (DOCX, not in repo; quoted via Sheets/Plan) s3.1 variants A/B, s4 rule row, s7 P3 row (one 2016-2021 run), s10.2 (decisions 01-12). A1 s2-s4, s10. Plan v0.5 header 'Precedence', s2.2, s0A. Recon C7, C13. Merged code: `spec/schema.py` partitions locked to the A1 layout; registry phases P3A/P3B; verdict `EXIT_SELECTED` |
| What is proposed (values) | A1 proposes (DRAFT, unsigned): exit chosen from a frozen closed set of <= 8 configurations by a frozen selection rule; P3a 2016-01-01..2019-12-31 (all K), P3b 2020-01-01..2021-12-31 (selected exit), P4 unchanged; P0 list D01-D19. PROPOSED / NOT APPROVED. No numeric parameter is set by A1 itself (values live in D17/D19). |
| Spec keys | (governing document; `signoff.*`, `exits` block depend on it) |
| Evidence required | Owner review of A1 plus Sheets s5 wording items; D19/D17/D02 sheets seen first (Sheets rec.). No data. |
| Dependencies / blocks | Precedes validity of D02 (rewritten), D13-D19 and any freeze. Until signed, v0.4 A/B governs and no spec may be frozen (Plan header). |
| Decision authority | Owner approves / rejects / amends. Trading-expert reviewer reviews the candidate set (D19). Independent validator reviews the selection rule and P3a test (A1 s10). |
| Required signatures | Owner; trading-expert reviewer; independent validator (three rows, A1 s10). |
| Status | UNSIGNED |

### D01 - Registration, exposure conclusions, holdout applicability

| Item | Content |
|---|---|
| Governing text | Design decision 01; s3.2 (2016-2021 development, 2022-2025 holdout, 2026-01..07 exposed). Sheets D01. Plan WP0.6, R2, R3, stop 9.2. Code: `governance/exposure_ledger.py`, `results_guard` partition/ledger checks |
| What is proposed (values) | No numeric value. Recommendation: do not sign until the WP0.6 contact audit (incl. AI-session history on 2016-2025 intraday data) is complete; unknown contact is reported as unknown. Owner rules whether other programs' use of the 2022-2025 daily layer is material for an intraday hypothesis. NO VALUE PROPOSED for the ruling. |
| Spec keys | `governance.exposure_signed` |
| Evidence required | Signed WP0.6 contact audit; exposure ledger; `hypothesis_lineage.yaml` (WP0.11). |
| Dependencies / blocks | After WP0.6. Blocks P0 exit, PR 3 ledger content, all of P4 (G0). |
| Decision authority | Owner. Independent validator co-sign of the ledger is a recommendation in the signing design (Q-A6). |
| Required signatures | Owner (required); independent validator (recommended). |
| Status | UNSIGNED |

### D02 - Hypothesis family and multiplicity adjustment

| Item | Content |
|---|---|
| Governing text | Design decision 02, s5.3, s6 (G4, G5). A1 s4 D02. Plan s5.1A, WP3.3, WP4.2. Ruling C6 (Holm). Code: `stats.adjustment` closed set holm/fixed_sequence, skeleton default holm; `stats.hypothesis_family` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: option (a) one Holm family over {G4, G5}, hypothesis count 2, one-sided alpha 0.05 (Sheets D02). PF >= 1.30 and stress mean > 0 are fixed gate thresholds, not open. Count under (b)/(c) is 1 for G4 with G5 separate. |
| Spec keys | `stats.hypothesis_family` (and `stats.adjustment`) |
| Evidence required | D06 decided first; validator confirms the statistics and the representation of the chosen option in the spec. |
| Dependencies / blocks | D06 -> D02. Feeds PR 11, 12, 14. |
| Decision authority | Owner decides; independent validator confirms. |
| Required signatures | Owner; independent validator. |
| Status | UNSIGNED |

### D03 - Universe N, PIT timing, SIP vendor and licence, data budget

| Item | Content |
|---|---|
| Governing text | Design s4 (monthly rebuild, top N by prior-day 20-day average dollar volume, prior close > $10, licensed SIP 1-minute); decision 03. Plan s2.1, WP1.2-1.3. CLAUDE.md (new external dependency needs an ADR). Code: skeleton fixes min_price 10.0, adv_window 20, rebuild monthly, feed sip |
| What is proposed (values) | PROPOSED / NOT APPROVED: N = 100 (design s4 / Sheets D03). PIT timing: universe built after the prior trading day's close, effective from the first session of each month (Sheets rec.). Vendor: Alpaca SIP only if F1, F2, F5 pass. Data budget: NO VALUE PROPOSED (owner states a cap). |
| Spec keys | `universe.n`, `data.vendor` |
| Evidence required | F1 (history to 2016-01-01), F2 (delisted coverage), F5 (licence for stored research use), vendor plan confirmation, cost and storage figures. |
| Dependencies / blocks | Long-lead external. Blocks all of P1 (PR 5, 6, 7). |
| Decision authority | Owner (account/licence holder). |
| Required signatures | Owner. |
| Status | UNSIGNED |

### D04 - Yearly consistency gate

| Item | Content |
|---|---|
| Governing text | Design s6 ('proposed, pending approval'); Plan G6, s5.1A. Code: `gates.yearly` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: >= 3 of 4 calendar years 2022-2025 with PF > 1.0 (design s6); undefined or too-few-trade year does not pass; per-year minimum trade count: NO VALUE PROPOSED. |
| Spec keys | `gates.yearly` |
| Evidence required | None return-blind (count rule). |
| Dependencies / blocks | Feeds PR 12/14. |
| Decision authority | Owner; independent validator reviews the validity rule. |
| Required signatures | Owner. |
| Status | UNSIGNED |

### D05 - Fill, risk and exit-mechanics values (5a-5j)

| Item | Content |
|---|---|
| Governing text | Design decision 05, s4 (R_pre/R_fill, adverse gap fills, half-day exit minute frozen in P0, risk 0.25% proposal, other limits 'P0 signed'), s4.1-4.2, s5.2. Plan s2.1, WP2.1A, WP2.2, WP2.3, App. A. Code: `fill.same_bar_policy = worst_case`, `exit.eod_flat = 15:55:00` fixed; 12 keys open |
| What is proposed (values) | PROPOSED / NOT APPROVED (Sheets D05): 5a day eligible only if every minute 09:30-09:59 is present or `NO_TRADE_MINUTE`, any `DATA_GAP` minute makes it ineligible; 5b min OR width in ticks: NO VALUE PROPOSED (owner chooses after seeing the return-blind distribution); 5c qty = floor(risk_budget / R_pre), reduce/protect if actual risk > budget x (1 + tolerance), tolerance value NO VALUE PROPOSED, R_fill <= 0 means immediate exit; 5d gap fills at bar open plus adverse slippage; 5e entry-then-stop, stop before target, path_ambiguous = True; 5f tick by price band, sub-$1 excluded; 5g half-day exit 5 minutes before the 13:00 ET early close, i.e. 12:55 ET; 5h `EXIT_UNAVAILABLE`, no assumed exit; 5i no separate slippage model if D15 = all-in; 5j per-trade risk 0.25% (design proposal); per-name cap, gross cap, max concurrent, daily loss limit, participation cap: NO VALUE PROPOSED. |
| Spec keys | `signal.or_completeness_rule`, `signal.min_or_width_ticks`, `exit.halfday_offset_min`, `fill.slippage_model`, `fill.halt_policy`, `risk.per_trade_pct`, `risk.per_name_cap`, `risk.gross_cap`, `risk.max_concurrent`, `risk.daily_loss_limit`, `risk.max_participation`, `risk.fill_risk_tolerance` |
| Evidence required | Return-blind OR-width distribution (ticks, % of price), minute-class counts, half-day calendar, tick bands. No post-entry paths. |
| Dependencies / blocks | Read with D18 (limits can bind G1) and D15 (5i). Needs F3/F4 for broker semantics. Blocks PR 6, 8, 12A, 13. |
| Decision authority | Owner decides numeric limits; trading-expert reviewer reviews trade logic and execution limits (design s10.3). |
| Required signatures | Owner; trading-expert reviewer. |
| Status | UNSIGNED |

### D06 - Baselines, bootstrap parameters, confidence level, seeds

| Item | Content |
|---|---|
| Governing text | Design decision 06, s5.3 (day-clustered block resampling; repetitions, interval type, confidence level, tail convention fixed in P0; random baseline matched on eligible symbols, window, trade count, capital, risk budget). Plan WP2.5, WP2.7A, WP3.3, ruling C11. Code: `stats.bootstrap.cluster = trading_day` fixed; all other bootstrap keys open |
| What is proposed (values) | PROPOSED / NOT APPROVED (Sheets D06): stationary bootstrap over trading days; one-sided; alpha 0.05; percentile of the recentered null; fixed seeds; repetitions at least 10,000; random-entry invalid draws counted `NOT_EXECUTABLE` with the denominator preserved. Mean block length: NO VALUE PROPOSED (the repo's daily `BLOCK_LEN = 10` is a precedent only; the validator confirms or replaces; it must not be estimated from RANGE-002 data). Seeds: NO VALUE PROPOSED (fixed, owner/validator state). |
| Spec keys | `stats.bootstrap.{method,block_len,ci_type,confidence_level,reps,seed}`, `stats.alpha_one_sided`, `controls.random_entry.{repetitions,seed,invalid_draw_policy}` |
| Evidence required | Synthetic size/power calibration by the validator. No RANGE-002 data. |
| Dependencies / blocks | First in the statistics block. Blocks D19 score, D17 STOP test, D02; PR 9, 11, 12, 12A. |
| Decision authority | Owner decides; independent validator confirms numbers (not the developer). |
| Required signatures | Owner; independent validator. |
| Status | UNSIGNED |

### D07 - P5 contract: paper-account policy, tolerances, cost-ratio contract

| Item | Content |
|---|---|
| Governing text | Design decision 07, s9.1-9.2 (>= 60 trading days, >= 100 trades, realized cost <= 1.5x model, tolerances frozen in advance). Plan WP5.1, WP5.6, App. A. Code: `p5.min_days 60`, `p5.min_trades 100`, `p5.max_cost_ratio 1.5` locked; `p5.account_id`, `degradation_tolerance`, `cost_ratio_contract` open and mandatory |
| What is proposed (values) | PROPOSED / NOT APPROVED: record the account POLICY (new, dedicated, not user 2) at P0 and the ID at WP5.1; cost ratio = sum(realized shortfall)/sum(modeled cost) over trades with positive modeled cost, others `UNDEFINED`. Degradation and drawdown tolerances, maximum number and length of extensions: NO VALUE PROPOSED. CONFLICT C-P5: the schema requires a non-null `p5.account_id` at freeze. |
| Spec keys | `p5.account_id`, `p5.degradation_tolerance`, `p5.cost_ratio_contract` |
| Evidence required | None return-blind; owner ruling on the `p5.account_id` timing. |
| Dependencies / blocks | Blocks PR 15; freeze (T). |
| Decision authority | Owner. |
| Required signatures | Owner. |
| Status | UNSIGNED |

### D08 - Roles and sole P6 approver

| Item | Content |
|---|---|
| Governing text | Design decision 08, s10.3. A1 s10. Plan R9 (no AI role). Signing design s9 (SoD-A..D). Owner ruling 5 (R1-L1b). Code: `governance.roles` open; `signoff.*` three strings and date |
| What is proposed (values) | PROPOSED / NOT APPROVED: four distinct humans; at minimum the independent validator is neither the research lead nor the engine author; flag if the owner is also the trading-expert reviewer. NO NAMES PROPOSED. |
| Spec keys | `governance.roles`, `signoff.owner`, `signoff.trading_expert`, `signoff.independent_validator` |
| Evidence required | Names; separation-of-duties option; independence confirmation (section 15). |
| Dependencies / blocks | Precedes every reviewer sign-off. Owner ruling 5: genuinely independent validator required before P0 approval or freeze. |
| Decision authority | Owner. |
| Required signatures | Owner (names the roles); each named person signs their own role row. |
| Status | UNSIGNED |

### D09 - ADR 0037 statement and ORM-001 relationship (with C2 open items)

| Item | Content |
|---|---|
| Governing text | Design decision 09, s3.4. Ruling C2 (ATP v0.14 s3A.2 three criteria; no non-equivalence code until the specification is approved). Plan WP0.5, s2.3. Sheets D09. Code: `registration.related_programs` open; no non-equivalence code exists |
| What is proposed (values) | PROPOSED / NOT APPROVED: ORM-001 option (b) shared trial ledger and multiplicity family, separate specs; history for criterion 1: exposed RNG-001 IEX 5-minute archive (alternatives (b) reorder with an A1 amendment, (c) owner-authorized early return-blind SIP pull). Numeric overlap limit: NO VALUE PROPOSED (owner states; lower is more conservative). Criteria 2/3 reviewers: NO NAMES PROPOSED. Gate-clause handling while no tool exists: proposed as signed reviewer findings on all three criteria. |
| Spec keys | `registration.related_programs` |
| Evidence required | Versioned records of both programs' entry/exit/universe/granularity/falsification condition; signal-timestamp overlap on the chosen history (no returns). |
| Dependencies / blocks | D13 mechanism text; D08. Blocks PR 4 and P0 exit; Plan stop 9.1. |
| Decision authority | Owner; trading-expert reviewer (criterion 2/3); independent validator (criteria 2/3). |
| Required signatures | Owner; trading-expert reviewer; independent validator. |
| Status | UNSIGNED |

### D10 - Win-rate gate and drawdown comparator

| Item | Content |
|---|---|
| Governing text | Design s6 (platform formal gate: trades > 100, PF > 1.2, win rate > 50%, drawdown no worse than baseline, positive expectancy, bootstrap CI > 0; deviation must be signed in P0). Ruling C3. Plan s5.1 G8 and D10 alert; RNG-001 report s3.5. Code: `gates.win_rate` mandatory, no default; `gates.max_dd` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: platform > 50% gate stays and promotion is blocked until the owner signs a written deviation; both evaluations displayed. Drawdown comparator: random-entry portfolio under identical capital, costs, equity sampling and exposure as primary, SPY buy-and-hold as reported reference. No deviation proposed. |
| Spec keys | `gates.win_rate`, `gates.max_dd` |
| Evidence required | Comparator definition and equity-sampling rule only. |
| Dependencies / blocks | Feeds PR 12, 14, any P6 promotion. |
| Decision authority | Owner. |
| Required signatures | Owner. |
| Status | UNSIGNED |

### D11 - Loader approach and `data.fetch_mode`

| Item | Content |
|---|---|
| Governing text | Design decision 11 (writer meets ADR 0033 points 1-3 or approved monthly-chunk rebuild). Ruling C5. Plan WP1.1, s10 D11. Recon s0 item 2. Code: `data.fetch_mode` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: confirm ruling C5 (new monthly-chunked, fail-closed RANGE-002 SIP loader; shared `BarCache` not modified). The enumeration string for `data.fetch_mode`: no value proposed in these documents. |
| Spec keys | `data.fetch_mode` |
| Evidence required | WP1.1 finding on `bar_cache.py` (in recon). |
| Dependencies / blocks | C12, D03. Blocks PR 5-7. |
| Decision authority | Owner. |
| Required signatures | Owner. |
| Status | UNSIGNED |

### D12 - Regime definition and single-regime criterion

| Item | Content |
|---|---|
| Governing text | Design decision 12, s5.3, Plan G7, `splits.py`. Code: `stats.regime.*` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: regime = SPY prior close vs 200-day SMA (causal); criterion (a) both regimes and both halves have positive net mean R with a minimum trades-per-cell, plus (b) a share cap on P&L from one regime/half. Minimum trades-per-cell and share cap: NO VALUE PROPOSED. |
| Spec keys | `stats.regime.definition`, `stats.regime.criterion` |
| Evidence required | Counts of sessions per regime and per half over 2022-2025 (calendar and SPY daily close only). |
| Dependencies / blocks | Define before returns exist. Blocks PR 11, G7. |
| Decision authority | Owner; independent validator reviews. |
| Required signatures | Owner; independent validator. |
| Status | UNSIGNED |

### D13 - Economic thesis, naive-ORB definition, binding vs non-binding diagnostics

| Item | Content |
|---|---|
| Governing text | Design s10.3, s3.3, s5.3. Plan s2.4, WP0.9, WP2.5, App. A. Code: `governance.economic_thesis_sha`, `controls.naive_orb.definition` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: thesis written and signed by humans (not authored by an agent); naive ORB = 'OR-high touch, no tick offset, same exits' (Plan WP2.5 example); binding = G0-G10 only, all other diagnostics non-binding. |
| Spec keys | `governance.economic_thesis_sha`, `controls.naive_orb.definition` |
| Evidence required | `economic_thesis.md` and its SHA-256; return-blind price-geometry distributions. |
| Dependencies / blocks | Blocks PR 4 criterion 3, PR 4A, PR 9. |
| Decision authority | Research lead and trading-expert reviewer author/verify; owner accepts. |
| Required signatures | Research lead; trading-expert reviewer; owner. |
| Status | UNSIGNED |

### D14 - Execution contract

| Item | Content |
|---|---|
| Governing text | Design decision 05, s5.2. A1 D14. Plan WP0.12, WP2.1, WP2.1A, WP2.2, WP2.9-2.11, R15, App. A. Code: ten `execution.*` keys open |
| What is proposed (values) | PROPOSED / NOT APPROVED (Sheets D14): crossed-before-arm = SKIP; stop protection only after the entry fill is acknowledged and sized; reservation at submission, released on cancel/expiry/fill. Order type: decide after F3 (no value proposed). Bar timestamp convention and vendor delay: verify with F4 (no value proposed). Submit/ack latency, EOD lead (seconds): NO VALUE PROPOSED. Tie-break: seeded hash order or permaticker ascending, owner picks. |
| Spec keys | `execution.{bar_timestamp_convention,vendor_delay_ms,submit_latency_ms,ack_latency_ms,crossed_before_arm_policy,order_type,stop_protection_policy,tie_break,eod_lead_s,order_reservation_policy}` |
| Evidence required | F3 broker capability report (any probe order needs separate written owner authorization, R14); F4; F10. F11 must not be started. |
| Dependencies / blocks | Blocks WP0.12 fixtures, PR 4A, 8, 12A, 15. |
| Decision authority | Owner decides; trading-expert reviewer reviews execution limits; validator reviews F3. |
| Required signatures | Owner; trading-expert reviewer. |
| Status | UNSIGNED |

### D15 - Cost accounting mode and components

| Item | Content |
|---|---|
| Governing text | Design s4 cost row (5 bps base / 15 bps stress per side; itemize spread, fees, impact, slippage). Plan s2.5, D15. Code: base 5 and stress 15 bps fixed; `costs.accounting_mode` (all_in | itemized_additive) and `costs.components` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: all-in bps as a P&L debit with fills at the modeled price and no extra slippage (Plan recommendation); G3 stays binding. Component breakdown: NO VALUE PROPOSED. |
| Spec keys | `costs.accounting_mode`, `costs.components` |
| Evidence required | None return-blind. |
| Dependencies / blocks | Blocks PR 8, 11. Interacts with D05 5i. |
| Decision authority | Owner. |
| Required signatures | Owner. |
| Status | UNSIGNED |

### D16 - Diagnosis taxonomy, shadow-run acceptance, execution-quality evidence

| Item | Content |
|---|---|
| Governing text | Design decision 07, s9.2. Plan WP3.4, WP5.9-5.11. Code: `diagnostics.taxonomy`, `p5.shadow_acceptance` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: adopt the eight labels (`NO_DEMONSTRATED_EDGE`, `EXECUTION_COST_DOMINATES`, `INSUFFICIENT_SAMPLE`, `REGIME_FRAGILITY`, `CAPACITY_OR_RISK_CONSTRAINT`, `DATA_OR_ENGINE_DEFECT`, `PAPER_OPERATION_FAILURE`, `UNCLASSIFIED`) as explanatory only; shadow acceptance zero orphan signals/duplicate intents/look-ahead discrepancies over N sampled days: N NO VALUE PROPOSED. |
| Spec keys | `diagnostics.taxonomy`, `p5.shadow_acceptance` |
| Evidence required | None. |
| Dependencies / blocks | Blocks PR 12B, 15A. |
| Decision authority | Owner. |
| Required signatures | Owner. |
| Status | UNSIGNED |

### D17 - P3a eligibility and STOP level; P3b criteria

| Item | Content |
|---|---|
| Governing text | Design s7 P3 row ('pre-approved development-period criteria', none given: a gap). A1 s3, s4 D17. Plan s2.2, WP4.1, s10 D17. Code: `p3.criteria` open; `exits.selection.eligibility.{min_trades,min_pf}` open; gates locked at 300 / 1.30 |
| What is proposed (values) | PROPOSED / NOT APPROVED (Sheets D17): P3a minimum 300 trades (P4 rate of 300 per 4 years over the 4-year P3a window); PF > 1.0 at base cost; STOP test one-sided alpha 0.05 on the max-statistic over K (alternatives 0.10, 0.20). P3b: same thresholds as P4 with G1 scaled to two years, 150 trades (alternatives: looser screen; significance only). 300 and 150 are scaling proposals, NOT attempt limits. |
| Spec keys | `p3.criteria`, `exits.selection.eligibility.min_trades`, `exits.selection.eligibility.min_pf` |
| Evidence required | None return-blind; the attainable trade count cannot be verified return-blind. Depends on D06 and D18. |
| Dependencies / blocks | D06 -> D18 -> D17 with D19. Blocks PR 11, 12, 13, 13B; guard refuses P3 while null. |
| Decision authority | Owner decides; independent validator reviews the STOP test. |
| Required signatures | Owner; independent validator. |
| Status | UNSIGNED |

### D18 - Gate computation basis and trade unit

| Item | Content |
|---|---|
| Governing text | Design s6 (silent: gap). A1 D18. Plan s5.1, WP2.2A. Code: `gates.basis` (portfolio_constrained | signal_level), `gates.trade_unit` open |
| What is proposed (values) | PROPOSED / NOT APPROVED: portfolio-constrained filled trades; signal-level as diagnostic; one entry = one trade including all exit fills; net R = total net P&L of all exit fills / (entry qty x R_fill). |
| Spec keys | `gates.basis`, `gates.trade_unit` |
| Evidence required | None. |
| Dependencies / blocks | Read with D05 5j. Precedes D17. Blocks PR 12, 13, 13B, 14. |
| Decision authority | Owner; independent validator reviews. |
| Required signatures | Owner; independent validator. |
| Status | UNSIGNED |

### D19 - Exit candidate set and selection rule

| Item | Content |
|---|---|
| Governing text | A1 Amendment 1 (replaces design s3.1 A/B). Plan s2.2, WP4.1, WP3. Code: `exits.*` open; candidates 1..8, four families (time, fixed_r, trailing, scale_out) |
| What is proposed (values) | PROPOSED / NOT APPROVED (Plan s2.2): K = 7: E1 time exit; E2a/E2b fixed target k in {2, 3} R; E3a/E3b breakeven after +1R then trail t in {1.0, 1.5} R; E4a/E4b sell 50% at +1R, remainder (a) EOD flat, (b) trail 1.0. Complexity rank E1=1, E2=2, E3=3, E4=4. Score = one-sided lower bound of mean net R per trade (D06 bootstrap). Tie tolerance delta: 0.05 R is an ILLUSTRATIVE PLACEHOLDER only (Sheets D19: 'I have no basis to set it'); owner and validator confirm or replace. Eligibility from D17; STOP test from D17. |
| Spec keys | `exits.candidates`, `exits.complexity_order`, `exits.selection.{score,tie_tolerance_r,eligibility.min_trades,eligibility.min_pf,stop_test}` |
| Evidence required | Trading-expert review; validator review of `select_exit` and the max-statistic test; no outcome data; fixtures synthetic. |
| Dependencies / blocks | D06, D17 (eligibility values), D18. Blocks A1, PR 8, 11, 13; stop 9.16-17. |
| Decision authority | Owner signs; trading expert proposes/reviews the set; validator reviews selection rule. |
| Required signatures | Owner; trading-expert reviewer; independent validator. |
| Status | UNSIGNED |

### Other formal decisions (summary blocks)

| ID | Decision | Decision authority | Required signatures | Source | Status |
|---|---|---|---|---|---|
| C2-overlap | Numeric maximum signal-overlap (criterion 1) | Owner (value); validator confirms the metric | Owner | Ruling C2; Sheets D09; Plan WP0.5. NO VALUE PROPOSED. | UNSIGNED |
| C2-reviewers | Reviewers for criteria 2 and 3 of the ATP v0.14 s3A.2 framework | Owner names; reviewers sign findings | Owner; named reviewers | Ruling C2; Sheets D09. NO NAMES PROPOSED. | UNSIGNED |
| D09-hist | History used for criterion 1 and handling of the P0 clause 'the non-equivalence check passes' | Owner | Owner | Sheets D09 / Plan WP0.5 options (a)/(b)/(c). PROPOSED: (a) exposed IEX 5-minute archive. | UNSIGNED |
| C10 | Custody of the authoritative design DOCX and recording its SHA-256 | Owner | Owner | Ruling C10; Sheets C10. PROPOSED: wait for S3 manifest tooling; record DOCX SHA-256 in the packet. | UNSIGNED |
| C12 | Name of the approved isolated non-production research environment and the accountable person | Owner | Owner | Ruling C12; Sheets C12. NO ENVIRONMENT PROPOSED. | UNSIGNED |
| D08-SoD | Separation-of-duties option (SoD-A/B/C/D) and any recorded waiver | Owner | Owner; independent validator (acknowledges) | Signing design s9. PROPOSED: SoD-A target, SoD-C minimum. | UNSIGNED |
| M-loc | Canonical registry location (absolute path, host) | Owner | Owner | Part I section 2.2. NO LOCATION PROPOSED. | UNSIGNED |
| M-ops | Ceremony operator and witness (humans); written authorization to enroll | Owner | Owner | Part I section 2.2. NO NAMES PROPOSED. | UNSIGNED |
| M-lim-p3a | `p3_attempt_limits.p3a` (and spec `p3.max_p3a_attempts`) | Owner | Owner | Acceptance record 'one-run policy remains a recommendation'; Part I section 3. PROPOSED: 1. | UNSIGNED |
| M-lim-p3b | `p3_attempt_limits.p3b` (and spec `p3.max_p3b_attempts`) | Owner | Owner | Same. PROPOSED: 1. | UNSIGNED |
| M-gen | `approved_registry_genesis_id`, `approved_by`, `approved_on` (filled after enrollment only) | Owner | Owner; reviewer of the manifest PR | Part I section 2.4. No value may be pre-supplied. | UNSIGNED |
| C-DR | Ruling on defect-only reruns versus the attempt limit | Owner | Owner | Part I section 3.5; Plan R3, WP4.0, WP4.1 versus `run_registry.py`. | UNSIGNED |
| C-P5 | How `p5.account_id` is satisfied at freeze | Owner | Owner | Part I section 8.2; Sheets D07; schema `p5.account_id`. | UNSIGNED |

---

## 11. DRAFT APPROVAL RECORDS (BLANK, READY TO SIGN)

One record per formal decision. **Every value, signature and date field is blank; the preparer has filled nothing and no AI agent may fill them.** A record binds a signer to the exact bytes of the pinned document, so the SHA-256 field is completed at signing time (Part I section 7.3). A record is invalid if the pinned document's bytes differ from the hash. A signature here is a typed attestation, not an authenticated signature (H4 deferred). Sign either here or in the Sheets block, not both with different wording.

**Update (Part III):** the proposed value, evidence, approver roles and documents to pin for every record are in section 25; the value shown there is PROPOSED / NOT APPROVED. All SHA-256 fields stay BLANK until signing.

Common fields on every record: Pinned document (file, git commit SHA): ________ ; SHA-256 of the pinned document: ________ (BLANK) ; Value field: BLANK ; Signer role: as stated ; Signer name: ________ ; Date (ISO): ________ (BLANK).

**Record A1 - Governing-Design Addendum A1**

- Decision text: Governing-Design Addendum A1.
- Value / choice (owner states): BLANK  [ Approve / Reject / Amend A1 (state which). Amendments, if any, listed here: ________ ]
- Signer role(s): Owner; trading-expert reviewer; independent validator (three rows, A1 s10).
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D01 - Registration, exposure conclusions, holdout applicability**

- Decision text: Registration, exposure conclusions, holdout applicability.
- Value / choice (owner states): BLANK  [ Sign option (a) 2022-2025 independent / (b) bounded exposure with ruling / (c) contaminated, holdout to be replaced. Chosen: ____ ]
- Signer role(s): Owner (required); independent validator (recommended).
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D02 - Hypothesis family and multiplicity adjustment**

- Decision text: Hypothesis family and multiplicity adjustment.
- Value / choice (owner states): BLANK  [ Option (a) / (b) / (c); number of confirmatory hypotheses: ____ ]
- Signer role(s): Owner; independent validator.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D03 - Universe N, PIT timing, SIP vendor and licence, data budget**

- Decision text: Universe N, PIT timing, SIP vendor and licence, data budget.
- Value / choice (owner states): BLANK  [ N = ____; PIT timing = ____; vendor/plan = ____; data budget cap = ____ ]
- Signer role(s): Owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D04 - Yearly consistency gate**

- Decision text: Yearly consistency gate.
- Value / choice (owner states): BLANK  [ Confirm as designed / alter to ____; per-year minimum trades ____ ]
- Signer role(s): Owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D05 - Fill, risk and exit-mechanics values (5a-5j)**

- Decision text: Fill, risk and exit-mechanics values (5a-5j).
- Value / choice (owner states): BLANK  [ Values for 5a-5j: ____ (per sub-item) ]
- Signer role(s): Owner; trading-expert reviewer.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D06 - Baselines, bootstrap parameters, confidence level, seeds**

- Decision text: Baselines, bootstrap parameters, confidence level, seeds.
- Value / choice (owner states): BLANK  [ Method ____; block length ____ days; reps ____; CI type ____; confidence ____; alpha ____; seeds ____; random-entry reps/invalid-draw policy ____ ]
- Signer role(s): Owner; independent validator.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D07 - P5 contract: paper-account policy, tolerances, cost-ratio contract**

- Decision text: P5 contract: paper-account policy, tolerances, cost-ratio contract.
- Value / choice (owner states): BLANK  [ Account policy ____; account_id at freeze ____; tolerances ____; extension rule ____ ]
- Signer role(s): Owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D08 - Roles and sole P6 approver**

- Decision text: Roles and sole P6 approver.
- Value / choice (owner states): BLANK  [ Research lead ____; trading-expert reviewer ____; independent validator ____; P6 approver ____ ]
- Signer role(s): Owner (names the roles); each named person signs their own role row.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D09 - ADR 0037 statement and ORM-001 relationship (with C2 open items)**

- Decision text: ADR 0037 statement and ORM-001 relationship (with C2 open items).
- Value / choice (owner states): BLANK  [ ORM-001 relation a/b/c ____; overlap limit ____; reviewers ____; history option ____; gate-clause handling ____ ]
- Signer role(s): Owner; trading-expert reviewer; independent validator.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D10 - Win-rate gate and drawdown comparator**

- Decision text: Win-rate gate and drawdown comparator.
- Value / choice (owner states): BLANK  [ Win-rate: keep >50% gate / sign deviation (reason ____); comparator ____ ]
- Signer role(s): Owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D11 - Loader approach and `data.fetch_mode`**

- Decision text: Loader approach and `data.fetch_mode`.
- Value / choice (owner states): BLANK  [ C5 satisfies decision 11: yes/no; fetch_mode ____ ]
- Signer role(s): Owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D12 - Regime definition and single-regime criterion**

- Decision text: Regime definition and single-regime criterion.
- Value / choice (owner states): BLANK  [ Regime definition ____; criterion ____; min trades per cell ____; share cap ____ ]
- Signer role(s): Owner; independent validator.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D13 - Economic thesis, naive-ORB definition, binding vs non-binding diagnostics**

- Decision text: Economic thesis, naive-ORB definition, binding vs non-binding diagnostics.
- Value / choice (owner states): BLANK  [ Thesis accepted/returned; naive-ORB definition ____; diagnostics ____ ]
- Signer role(s): Research lead; trading-expert reviewer; owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D14 - Execution contract**

- Decision text: Execution contract.
- Value / choice (owner states): BLANK  [ Each sub-item value: ____ ]
- Signer role(s): Owner; trading-expert reviewer.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D15 - Cost accounting mode and components**

- Decision text: Cost accounting mode and components.
- Value / choice (owner states): BLANK  [ Mode all_in / itemized_additive; components ____ ]
- Signer role(s): Owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D16 - Diagnosis taxonomy, shadow-run acceptance, execution-quality evidence**

- Decision text: Diagnosis taxonomy, shadow-run acceptance, execution-quality evidence.
- Value / choice (owner states): BLANK  [ Taxonomy adopted/modified ____; sampled days ____ ]
- Signer role(s): Owner.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D17 - P3a eligibility and STOP level; P3b criteria**

- Decision text: P3a eligibility and STOP level; P3b criteria.
- Value / choice (owner states): BLANK  [ P3a min trades ____; P3a PF ____; STOP alpha ____; P3b option a/b/c ____; P3b min trades ____ ]
- Signer role(s): Owner; independent validator.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D18 - Gate computation basis and trade unit**

- Decision text: Gate computation basis and trade unit.
- Value / choice (owner states): BLANK  [ Basis ____; trade unit ____ ]
- Signer role(s): Owner; independent validator.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D19 - Exit candidate set and selection rule**

- Decision text: Exit candidate set and selection rule.
- Value / choice (owner states): BLANK  [ Candidate set (<= 8): ____; complexity order ____; score ____; tie tolerance ____ R; eligibility ____; STOP test ____ ]
- Signer role(s): Owner; trading-expert reviewer; independent validator.
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record C2-overlap - Numeric maximum signal-overlap (criterion 1)**

- Decision text: Numeric maximum signal-overlap (criterion 1).
- Value / choice (owner states): BLANK  [ Numeric maximum overlap: ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record C2-reviewers - Reviewers for criteria 2 and 3 of the ATP v0.14 s3A.2 framework**

- Decision text: Reviewers for criteria 2 and 3 of the ATP v0.14 s3A.2 framework.
- Value / choice (owner states): BLANK  [ Criterion 2 reviewer ____; criterion 3 reviewer ____ ]
- Signer role(s): Owner; named reviewers
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D09-hist - History used for criterion 1 and handling of the P0 clause 'the non-equivalence check passes'**

- Decision text: History used for criterion 1 and handling of the P0 clause 'the non-equivalence check passes'.
- Value / choice (owner states): BLANK  [ History option a/b/c ____; gate-clause handling ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record C10 - Custody of the authoritative design DOCX and recording its SHA-256**

- Decision text: Custody of the authoritative design DOCX and recording its SHA-256.
- Value / choice (owner states): BLANK  [ Custody location ____; DOCX SHA-256 ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record C12 - Name of the approved isolated non-production research environment and the accountable person**

- Decision text: Name of the approved isolated non-production research environment and the accountable person.
- Value / choice (owner states): BLANK  [ Environment name ____; accountable person ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record D08-SoD - Separation-of-duties option (SoD-A/B/C/D) and any recorded waiver**

- Decision text: Separation-of-duties option (SoD-A/B/C/D) and any recorded waiver.
- Value / choice (owner states): BLANK  [ Option SoD-A/B/C/D ____; waiver (if any) ____ ]
- Signer role(s): Owner; independent validator (acknowledges)
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record M-loc - Canonical registry location (absolute path, host)**

- Decision text: Canonical registry location (absolute path, host).
- Value / choice (owner states): BLANK  [ Absolute path ____; host ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record M-ops - Ceremony operator and witness (humans); written authorization to enroll**

- Decision text: Ceremony operator and witness (humans); written authorization to enroll.
- Value / choice (owner states): BLANK  [ Operator ____; witness ____; authorization to enroll: yes/no ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record M-lim-p3a - `p3_attempt_limits.p3a` (and spec `p3.max_p3a_attempts`)**

- Decision text: `p3_attempt_limits.p3a` (and spec `p3.max_p3a_attempts`).
- Value / choice (owner states): BLANK  [ p3a limit ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record M-lim-p3b - `p3_attempt_limits.p3b` (and spec `p3.max_p3b_attempts`)**

- Decision text: `p3_attempt_limits.p3b` (and spec `p3.max_p3b_attempts`).
- Value / choice (owner states): BLANK  [ p3b limit ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record M-gen - `approved_registry_genesis_id`, `approved_by`, `approved_on` (filled after enrollment only)**

- Decision text: `approved_registry_genesis_id`, `approved_by`, `approved_on` (filled after enrollment only).
- Value / choice (owner states): BLANK  [ Genesis id (copied from the read-back after enrollment) ____; approved_by ____; approved_on ____ ]
- Signer role(s): Owner; reviewer of the manifest PR
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record C-DR - Ruling on defect-only reruns versus the attempt limit**

- Decision text: Ruling on defect-only reruns versus the attempt limit.
- Value / choice (owner states): BLANK  [ Option (i)/(ii)/(iii) ____; Plan text to be conformed: ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

**Record C-P5 - How `p5.account_id` is satisfied at freeze**

- Decision text: How `p5.account_id` is satisfied at freeze.
- Value / choice (owner states): BLANK  [ Resolution ____ ]
- Signer role(s): Owner
- Signer name(s): BLANK
- Signature: BLANK
- Date: BLANK
- Pinned document and commit: BLANK
- SHA-256 of pinned document: BLANK

---

## 12. THE ONE-RUN POLICY RECONCILED WITH THE REAL WINDOWS AND VALIDATION RULES

Recommendation (not a decision) restated: `p3a = 1`, `p3b = 1` per lineage. Source for what a run must contain: Plan WP4.0, WP4.1, s6, s7; merged `results_guard.py`, `run_registry.py`.

| Phase | Partition (fixed in schema) | Window | What the single governed run contains | Authorized and counted at |
|---|---|---|---|---|
| P3a | `DEVELOPMENT_SELECTION` | 2016-01-01 .. 2019-12-31 | Open registry row first (R8); authorize; stage-1 controls (time-shuffle, no-information trigger, engine sanity: no entry before 10:00, flat at close, ledger reconciliation) with strategy results sealed; **all K candidates** run through the full portfolio simulation with identical entries, sizing, costs and constraints; with results still sealed `select_exit` and the max-statistic test run and a `SelectionRecord` (selected id or STOP, scores, eligibility, tie decision, selection-aware p-value, input hashes) is written and hashed **before unsealing**; audit pack written; close row | `capability_issued` row (written before the capability is returned); attempt counted for (genesis, P3A) |
| P3b | `DEVELOPMENT_CONFIRMATION` | 2020-01-01 .. 2021-12-31 | Selected exit only; code hashes and spec hash equal P3a's; same sealed two-stage protocol; gates against the D17 P3b criteria; pass gives `ADVANCE_TO_P4`, fail gives `STOP` | `capability_issued` row; attempt counted for (genesis, P3B) |
| P4 | `HOLDOUT` | 2022-01-01 .. 2025-12-31 | Selected exit only, once; holdout token; two-phase durable consume | `holdout_authorized` row; no manifest limit, window consumed whatever happens after |

Reconciliation points:

1. **Budget scope.** One budget per (registry genesis, phase) across all protected windows, spec hashes, code versions and worktrees. A different window, a P0 edit or a re-freeze does not reset it (NF7). The windows above are therefore not independent budgets.
2. **What P3b needs from P3a** (guard rule g): a P3A run for the same spec hash that is COMPLETED, carries a `capability_issued` row and a recorded selection record; the guard re-reads the P3A audit pack and selection record, recomputes their SHA-256 (must equal the registry digests) and checks the embedded run and spec. A P3A that is authorized and then aborted can never be COMPLETED, so P3B is unreachable. P4 additionally needs a COMPLETED P3B.
3. **K candidates in one run.** Consistent with a limit of 1 (K is accounted for by the selection-aware test and the ledger, not by K attempts). Under v0.4 (two fixed variants) the same semantics would apply but the merged schema cannot express v0.4's single 2016-2021 P3 (conflict C-SCHEMA).
4. **Consume-at-`capability_issued`.** Refusals before that row, and a merely opened run, consume nothing. After it, anything counts. The row is written before the capability object is returned, so a crash between the two also consumes the attempt.

Hazards for the owner (escalated, not resolved):

- **H1 Defect after authorization ends the phase for the lineage** (conflict C-DR): a crash, data defect or failed stage-1 control after authorization consumes the only attempt; Plan R3/WP4.0/WP4.1 promise a defect-only rerun the code does not provide. Mitigation available without new code: validate the engine on synthetic fixtures and `REPLAY_RNG001` (never citable) before any P3 authorization.
- **H2 The single P3a run is a four-year, K-candidate, sealed run.** Any engine fault only surfaces inside it. The same applies to P3b over two years.
- **H3 Trade-minimum feasibility** (C-P3B-N): 300 (P3a) and 150 (P3b) cannot be tested return-blind; if unattainable the one run ends in a terminal STOP. These are D17 numbers, not attempt limits.
- **H4 Torn-tail lockout** (accepted Level 1 behaviour): an interrupted registry write fails closed and recovery is a separate owner-authorized procedure that does not exist in code.
- **H5 The manifest is read from the executing checkout** (NF3): P3a and P3b should run from checkouts whose manifest is identical; the manifest SHA-256 is recorded on each `capability_issued` row but not compared across rows.
- **H6 A STOP is a correct completed outcome** and terminal for the registered candidate (Plan WP4.1); validator to confirm the guard refuses P3B after a recorded STOP and that a STOP run can complete.
- **H7 Holdout** has no manifest limit but is stricter in effect: authorization consumes the window for any overlapping window of any spec hash.

---

## 13. STATISTICAL VALIDATION DECISION MATRIX

All "implications" below are the preparer's analysis of the options in the Sheets, Plan and merged code, not decisions. Values are UNSET and are not proposed beyond what the documents already state.

### 13.1 D02 hypothesis family (options as in section 4.2)

| Option | Family size m | Procedure | Consequence for G4/G5 | Reporting / schema |
|---|---|---|---|---|
| (a) | 2 | Holm over {G4, G5} at one-sided 0.05 | Smaller p-value must clear alpha/2, larger alpha; strictest | `adjustment = holm`; `hypothesis_family` lists both |
| (b) | 1 for G4; G5 separate | G4 Holm (trivial, m = 1); G5 required gate at its own declared one-sided alpha; both must pass | No cross-adjustment; less strict than (a) | needs a stated G5 alpha; representation of a mixed procedure to be confirmed by the validator |
| (c) | 2 sequential | Fixed sequence G4 then G5, each 0.05, G5 only if G4 passes | Same pass condition as (b) | `adjustment = fixed_sequence`; reports only G4 when it fails |

P3a is separate: selection-aware max-statistic over all K candidates (day-clustered resampling, null that no candidate has positive mean net R) at the D17 alpha. K does not enter the P4 family (one exit configuration); K and the family are recorded in the ledger and P4 report. ADR 0037's BH-FDR is scoped to EAD programs (ruling C6) and is not an option for RANGE-002 unless an ADR changes that.

### 13.2 D06 bootstrap configuration (every value UNSET)

| Parameter | Owner choices (from the documents) | Implications |
|---|---|---|
| Method | stationary block bootstrap over trading days (geometric blocks); circular fixed-block over days; iid day-clusters | Stationary and circular preserve serial dependence between days; iid day-clusters assume independence between days and can understate uncertainty if returns cluster in time. Existing code is a design reference only |
| Mean block length | fixed a priori, in days (no value proposed; daily `BLOCK_LEN = 10` is the only repo precedent) | Too short understates dependence; too long reduces effective resamples (3-4 independent years in P4). Must not be derived from RANGE-002 data |
| Repetitions | at least 10,000 recommended (Sheets) | Monte Carlo error on a p-value near 0.05 and on a max-statistic tail falls with reps |
| CI type | e.g. percentile of the recentered null | Percentile is simplest; a bias-corrected type is more complex and needs validator sign-off. Tests and intervals must not be conflated (Plan s5.1A) |
| Confidence level / alpha | one-sided 0.05 recommended; D17 STOP alpha options 0.05 / 0.10 / 0.20 | A looser STOP alpha passes noise-selected exits to P3b/P4; a stricter one risks a false STOP (a correct platform outcome per Sheets) |
| Seed | fixed | Reproducibility; seed recorded; one seed per purpose |
| Cluster | `trading_day` (fixed by schema) | Day-level resampling for both strategy and baseline series (G5 pairing) |

### 13.3 Multiple-testing correction

| Layer | Correction | Notes |
|---|---|---|
| P3a selection over K | maximum statistic over all K, day-clustered resampling | selection-aware; candidates are highly correlated (shared entries) so the correction is mild |
| P4 family | Holm (ruling C6) over the D02 family; or fixed sequence | Holm is uniformly at least as powerful as Bonferroni while controlling family-wise error; BH-FDR controls a different error rate and is out of scope for RANGE-002 |
| Gate function | implements the declared procedure exactly and labels it | uncorrected significance is never promotion evidence |

### 13.4 Baselines and controls

| Item | Role | Binding? | Open parameters |
|---|---|---|---|
| Random-entry baseline | G5 paired comparison; matched on eligible symbols, time window, trade count, capital, risk budget; not conditioned on future breakout | Binding (G5) | repetitions, seed, invalid-draw policy (D06); invalid draws counted, denominator preserved (R16) |
| Naive ORB | comparison control ('OR-high touch, no tick offset, same exits', Plan WP2.5 example) | diagnostic unless P0 makes it binding | definition (D13) |
| SPY buy-and-hold | reported reference; candidate drawdown comparator | non-binding reference (proposed) | comparator choice (D10) |
| Time-shuffle control | stage-1 engine control (WP4.0) | its failure voids the run (`INCONCLUSIVE_ENGINE`) | none |
| No-information trigger | stage-1 engine control | same | none |

### 13.5 Win-rate gate (D10): show both

| Evaluation | Rule | Effect |
|---|---|---|
| Platform formal gate | win rate > 50% (with trades > 100, PF > 1.2, drawdown no worse than baseline, positive expectancy, bootstrap CI > 0) | Applies until a formal D10 deviation is signed; promotion blocked meanwhile (ruling C3) |
| Design diagnostic | win rate diagnostic only because breakout strategies typically win under half the time | Takes effect only if the owner signs a written deviation with reasons |

Both evaluations are displayed. The design's claim that the 50% gate rejects 'for the wrong reason' is an assertion, not evidence from RANGE-002 data.

### 13.6 Gates G0-G10

Thresholds and open items: section 4.1. Locked in code by equality validators: G1 300, G2 1.30, G3 stress mean positive, G10 0.85; free in the spec: G6 (D04), G7 (D12), G8 (D10), basis (D18).

---

## 14. FREEZE-FIELD TRACE

> **Superseded in part (Part VI, s48):** this trace is the list at `main` `d61f313a`. The local schema candidate `5bc2b493` replaces `p5.account_id` with `p5.account_binding` and adds mandatory paths; s49 lists them with owners. The `p5.account_id` flag below is resolved by option B once that candidate is approved and merged.

Source: `draft_skeleton()` executed with `python -I` from the merged code (no real values, no file written). Result: 107 leaf values, 72 null, 35 fixed. Every null is listed below with its owning decision. "Unowned" fields: none. Fields needing attention are flagged in the last column.

| # | Dotted path (null in skeleton) | Owning decision | Note |
|---|---|---|---|
| 1 | `registration.trial_ledger_id` | WP0.7 / registry (exempt from P0 check) | Set by the run registry, not an owner value; no decision owns a value. Flag: confirm WP0.7 sets it before freeze |
| 2 | `registration.related_programs` | D09 |  |
| 3 | `universe.n` | D03 |  |
| 4 | `data.vendor` | D03 |  |
| 5 | `data.fetch_mode` | D11 | enumeration string not stated in the documents |
| 6 | `signal.or_completeness_rule` | D05 5a |  |
| 7 | `signal.min_or_width_ticks` | D05 5b | number only after return-blind distribution |
| 8 | `exits.candidates` | D19 (A1) |  |
| 9 | `exits.complexity_order` | D19 |  |
| 10 | `exits.selection.score` | D19 |  |
| 11 | `exits.selection.tie_tolerance_r` | D19 | 0.05 R placeholder only |
| 12 | `exits.selection.eligibility.min_trades` | D19 + D17 | dual owner: value comes from D17 |
| 13 | `exits.selection.eligibility.min_pf` | D19 + D17 | dual owner |
| 14 | `exits.selection.stop_test` | D19 + D17 | dual owner |
| 15 | `exit.halfday_offset_min` | D05 5g |  |
| 16 | `fill.slippage_model` | D05 5i | coupled to D15 |
| 17 | `fill.halt_policy` | D05 5h |  |
| 18 | `costs.accounting_mode` | D15 |  |
| 19 | `costs.components` | D15 |  |
| 20 | `risk.per_trade_pct` | D05 5j | 0.25 proposed in design s4 |
| 21 | `risk.per_name_cap` | D05 5j |  |
| 22 | `risk.gross_cap` | D05 5j |  |
| 23 | `risk.max_concurrent` | D05 5j |  |
| 24 | `risk.daily_loss_limit` | D05 5j |  |
| 25 | `risk.max_participation` | D05 5j |  |
| 26 | `risk.fill_risk_tolerance` | D05 5c | tolerance in the R_fill rule |
| 27 | `controls.random_entry.repetitions` | D06 |  |
| 28 | `controls.random_entry.seed` | D06 |  |
| 29 | `controls.random_entry.invalid_draw_policy` | D06 |  |
| 30 | `controls.naive_orb.definition` | D13 |  |
| 31 | `stats.bootstrap.method` | D06 |  |
| 32 | `stats.bootstrap.block_len` | D06 |  |
| 33 | `stats.bootstrap.ci_type` | D06 |  |
| 34 | `stats.bootstrap.confidence_level` | D06 |  |
| 35 | `stats.bootstrap.reps` | D06 |  |
| 36 | `stats.bootstrap.seed` | D06 |  |
| 37 | `stats.hypothesis_family` | D02 | depends on D06 |
| 38 | `stats.alpha_one_sided` | D06 | schema comment assigns D06; D02/D17 use it |
| 39 | `stats.regime.definition` | D12 |  |
| 40 | `stats.regime.criterion` | D12 |  |
| 41 | `execution.bar_timestamp_convention` | D14 (F4) |  |
| 42 | `execution.vendor_delay_ms` | D14 (F4) |  |
| 43 | `execution.submit_latency_ms` | D14 (F3/F4) |  |
| 44 | `execution.ack_latency_ms` | D14 (F3/F4) |  |
| 45 | `execution.crossed_before_arm_policy` | D14 |  |
| 46 | `execution.order_type` | D14 (F3) |  |
| 47 | `execution.stop_protection_policy` | D14 |  |
| 48 | `execution.tie_break` | D14 |  |
| 49 | `execution.eod_lead_s` | D14 |  |
| 50 | `execution.order_reservation_policy` | D14 |  |
| 51 | `p3.criteria` | D17 |  |
| 52 | `p3.max_p3a_attempts` | M-lim-p3a | must equal manifest |
| 53 | `p3.max_p3b_attempts` | M-lim-p3b | must equal manifest |
| 54 | `gates.basis` | D18 |  |
| 55 | `gates.trade_unit` | D18 |  |
| 56 | `gates.yearly` | D04 |  |
| 57 | `gates.win_rate` | D10 |  |
| 58 | `gates.max_dd` | D10 |  |
| 59 | `p5.account_id` | D07 | FLAG C-P5: mandatory at freeze but account cannot exist before WP5.1 |
| 60 | `p5.degradation_tolerance` | D07 |  |
| 61 | `p5.cost_ratio_contract` | D07 |  |
| 62 | `p5.shadow_acceptance` | D16 |  |
| 63 | `diagnostics.taxonomy` | D16 |  |
| 64 | `governance.economic_thesis_sha` | D13 (WP0.9) | SHA-256 of the signed thesis |
| 65 | `governance.roles` | D08 |  |
| 66 | `governance.exposure_signed` | D01 | shape of the value is open (signing design: ledger sha256 + statement id) |
| 67 | `governance.registry_genesis_id` | M-gen | must equal manifest and registry |
| 68 | `signoff.owner` | D08 (owner) | not counted as a P0 field; required present by `freeze_spec` |
| 69 | `signoff.trading_expert` | D08 | same |
| 70 | `signoff.independent_validator` | D08 / R1-L1b | same; independence procedural |
| 71 | `signoff.date` | D08 | same; not in the future |
| 72 | `signoff.spec_sha256` | computed by `freeze_spec` | never entered by hand |

Count check: 72 rows = 72 nulls (66 P0 fields + `registration.trial_ledger_id` + 5 `signoff.*`). **No null field is unowned.** Fields with a weak or split owner: the three `exits.selection.*` D17-derived fields (D19 and D17 must be signed together), `p5.account_id` (conflict C-P5), `signal.min_or_width_ticks` and `exit.halfday_offset_min` (value needs return-blind evidence or an owner number), `governance.exposure_signed` (value shape), `stats.alpha_one_sided` (assigned to D06 by the schema, used by D02/D17), and `registration.trial_ledger_id` (owned by WP0.7, not a decision). Fields that are **not** null but are pre-set and therefore never force a decision: `stats.adjustment = holm` (D02), `stats.bootstrap.cluster`, and the locked gate and P5 thresholds.

---

## 15. VALIDATOR INDEPENDENCE AND SIGNATURE MATRIX

### 15.1 Roles (D08)

| Role | Function (design s10.3, A1 s10) | May sign |
|---|---|---|
| Research lead | technical team lead: data, engine, evidence; authors the thesis with the trading expert | thesis (WP0.9), engineering attestations; D13 |
| Trading-expert reviewer | hypothesis, trade logic, execution limits | A1 (D19 candidate set), D05, D13, D14, D09 criteria 2/3 |
| Independent validator | test scope; statistics; selection rule | A1 (selection rule, P3a test), D02, D06, D12, D17, D18, D19 selection rule, D09 criteria 2/3, F3 capability report review |
| Owner | decides; signs every formal decision; approves manifest | all formal decisions |
| Sole P6 approver | later, separate human decision (no P0 purpose) | P6 only |

### 15.2 Signature matrix (Recommendation (not a decision); only A1's three rows are fixed by the documents)

| Artefact | Owner | Trading expert | Independent validator | Research lead |
|---|---|---|---|---|
| A1 | sign | sign (D19) | sign (selection rule, P3a test) | |
| D01 exposure | sign | | recommended co-sign | contact audit author |
| D02, D06, D12, D17, D18 | sign | | sign | |
| D03, D11, D15, D16, D04, D07, D10 | sign | | | |
| D05, D14 | sign | sign | review F3 | |
| D13 thesis | sign | sign | | sign (author) |
| D19 | sign | sign | sign (selection rule) | |
| D09 / C2 | sign | sign (criteria 2/3) | sign (criteria 2/3) | |
| Spec freeze | sign | sign | sign | |
| Manifest PR / genesis | sign (`approved_by`) | | reviewer recommended | |

### 15.3 Separation-of-duties options (Approval Signing design s9, none selected)

> **Superseded in part (Part VI, s48):** the owner's proposed policy is SoD-A plus SoD-C (s27, s43); SoD-B is removed. The design text below is kept for history. Nothing is signed.

| Option | Rule | Weakness |
|---|---|---|
| SoD-A | three distinct humans, distinct keys, for owner / trading expert / validator | a technical check cannot prove two keys are two people |
| SoD-B | owner and trading expert may coincide; validator distinct; recorded waiver | D19 review is then not independent of the final approver |
| SoD-C | validator also distinct from the research lead and from whoever wrote the engine | needs a recorded engineer list |
| SoD-D | any overlap | defeats independent review |

Recommendation (not a decision): SoD-A target, SoD-C minimum, any SoD-B waiver recorded explicitly.

### 15.4 How independence is confirmed outside the string-distinctness safeguard

The merged tool checks only that three strings are present; the local follow-up (`57dadd52`) will reject identical or trivially variant identifier strings. Neither proves independence. Procedural confirmation proposed (Recommendation (not a decision)); the validator signs an attestation covering each line, and the owner countersigns:

1. Distinct natural persons, identified in a record kept outside the repository; not the same person as the owner, the research lead or the trading expert.
2. Separate accounts and credentials (repository, cloud, signing keys when H4 exists); no shared login.
3. Organisational separation where possible (different reporting line or organisation); if the validator reports to the owner or the research lead, say so in the record.
4. No code authorship: the validator wrote none of the spec, engine, loader, selection code or gates under review, and the engineer list is recorded (SoD-C).
5. No prior result exposure: the validator has seen no RANGE-002 returns, P&L, win rates or profit factors (the program has none yet) and no 2016-2025 intraday results from related programs (links to the D01 contact audit).
6. No financial or compensation dependence on the outcome; declared conflicts recorded.
7. No AI agent holds a role, signs or authors the validator's findings (R9). An AI summary does not substitute for the validator's own review.
8. The validator reviews the exact pinned bytes (SHA-256) and records the review date.

### 15.5 Validator-independence requirements (cross-reference to Workstream B)

The software safeguard for sign-off roles (R1-L1b follow-up, local commit `3f05d17a` on `fix/range002-signoff-distinct-roles-rebased`, base `d61f313a`, **not merged**) checks only that the three role identifier strings are pairwise distinct after Unicode normalisation. It does **not** establish that the signers are different humans, and it does not authenticate identity (homoglyphs, aliases, email-versus-display-name and, until the open finding F1 is resolved, invisible characters are not caught).

Real independence confirmation is a procedural requirement, specified in `RANGE-002_Validator_Independence_Requirements_v0.1.md` (local branch `docs/range002-validator-independence`, commit `7421ca62`, **not merged**). Cite these sections of that document:

- **V-1** what the string check proves and does not prove.
- **V-2** (V-2.1 to V-2.10) the ten procedural confirmations the owner could require: named natural persons, attestations of no authorship of the engine or spec code, no prior exposure to RANGE-002 results, separate accounts and credentials, separate key custody, a recorded conflicts statement, and who verifies.
- **V-3** who verifies; **V-4** what software can and cannot check.
- **V-5** mapping to the D08 separation-of-duties options SoD-A to SoD-D. Note: the all-pairs distinctness rule rejects owner == trading_expert, so SoD-B (same person as owner and expert, with a recorded waiver) cannot be expressed without amending the safeguard (Workstream B finding F4); the owner must confirm that is intended.
- **V-6** what is deferred to Level 2 signing; **V-7** Level 1 gaps; **V-8** the blank owner selection table; **V-9** open questions.

Open owner decisions arising from the independent review of the safeguard (Workstream B): F1 (strip zero-width and other format/control code points before comparison: recommended before the first real freeze), F4 (SoD-B expressibility), and whether to add two test ids to the required Linux manifest. The safeguard must receive separate merge authorization before any real freeze. Nothing in this section is a decision, signature or approval.

---

## 16. ORDERED P0 BLOCKER LIST

> **Superseded in part (Part VI, s48):** the current list is s37 as refreshed by s47 and s50.

Each item blocks everything below it that depends on it; items 1-3 and 5 can run in parallel.

1. D08 roles named and SoD option selected; independent validator named and attested (R1-L1b). Blocks every reviewer sign-off.
2. Owner ruling C-DR (defect-only reruns vs the attempt limit) and the two limit values.
3. Long-lead externals: C12 environment; D03 vendor/licence/history (F1, F2, F5); C10 custody; F3/F4 checks.
4. M-loc, M-ops and written authorization; enrollment ceremony (Part I section 2); manifest change (genesis triple + both limits).
5. WP0.6 contact audit; D01; D09/C2 decisions; PR 4 non-equivalence record; D13 thesis (human-written).
6. Statistics block: D06, D18, D19 with D17, D02; then A1 (after validator review).
7. Fill/execution block: D05, D14, D15 (after F3/F4); D12, D04, D10, D16, D07 (including C-P5).
8. WP0.8-0.12 artefacts signed (provenance, thesis, feasibility, lineage, order contract).
9. Real spec drafted; genesis and limits equal the manifest; sign-off fields filled by named humans; SHA-256 of every signed document pinned; the optional `57dadd52` follow-up merged if the owner so instructs.
10. Real `freeze_spec`; P0 exit; then P1.

---

## 17. P0 GO / NO-GO RECOMMENDATION (recommendation only)

> **Superseded in part (Part VI, s48):** the standing recommendation is NO-GO (s37, s47, s50).

**NO-GO.** P0 is **not ready**. On the evidence of the repository at `d61f313a` plus the acceptance records: no signature required by this register exists (A1, D01-D19, C2, C10, C12, D08 roles, the separation rule, the registry location, the genesis triple and the attempt limits are all unsigned or blank); the governance manifest is entirely unset; no registry is enrolled; the non-equivalence check does not exist; WP0.5-WP0.12 artefacts are not done; an independent validator has not been named; and six escalated conflicts (C-DR, C-SCHEMA, C-P3B-N, C-P5, C-D02-REPR, C-ENROLL-CLI) await the owner. The merge of PR #739 is infrastructure only and authorizes none of these.

P0 becomes GO only when every record in section 11 is signed against pinned SHA-256 hashes, the manifest change has merged, the spec has passed the real `freeze_spec`, and the independent validator has attested under section 15.4. This is a recommendation; the decision is the owner's.

---

# PART III - RECOMMENDED RULINGS INCORPORATED (added on the owner directive; all NOT APPROVED)

Part III updates Parts I and II. Where it differs from an earlier section, Part III controls for the owner's reading, and the earlier text is not silently deleted. Every ruling is labelled **RECOMMENDED / PROPOSED -- NOT APPROVED**.

## 18. D08 - FOUR NAMED ROLE SLOTS AND THE SEPARATION-OF-DUTIES OPTIONS

**RECOMMENDED / PROPOSED -- NOT APPROVED.** Create four named role slots: research lead, trading-expert reviewer, independent validator, sole P6 approver. Naming a slot does not make a person independent. **Actual independent human validation (section 15.4 and the Workstream B document cited in 15.5) and a formal, signed SoD selection are still required** before any P0 approval or real freeze (owner ruling 5, R1-L1b). No AI agent holds a slot.

### 18.1 The SoD options, verbatim

Source: `git show d1406ec2:docs/implementation/evidence/range_002/RANGE-002_Approval_Signing_and_Verification_Design_v0.1.md`, section 9 ("Role design for D08"). Line numbers are those of that file at `d1406ec2`. The same text is at lines 293-296 of the copy in `79e072d7`. The table header is at line 288, the "none selected" sentence at line 285.

| Line | Option | Rule (verbatim) | Enforced by (verbatim) | Weakness (verbatim) |
|---|---|---|---|---|
| 289 | SoD-A | Three distinct humans, three distinct keys, for owner / trading expert / validator | Distinct `key_id` and `person_id` (technical) + identity attestation (procedural) | Technical check cannot prove two keys are two people |
| 290 | SoD-B | Owner and trading expert may be the same person; validator must be a different person | Same, with explicit recorded waiver | Per D08 sheet: D19 candidate review is then not independent of the final approver |
| 291 | SoD-C | Validator must also be distinct from the research lead and from whoever wrote the engine | Procedural + signed attestation by the validator | Needs a recorded engineer list |
| 292 | SoD-D | Any role overlap permitted | n/a | Defeats independent review; shown only for completeness |

The design's own recommendation (line 294, quoted): "the owner and the independent validator are **distinct individuals with distinct keys and distinct IAM principals**, with SoD-A as the target and SoD-C as the minimum acceptable ... If the owner is also the trading-expert reviewer (SoD-B), the design records that explicitly as a waiver in the requirement set rather than leaving it implicit. No AI agent may hold a role, a key or a principal (R9)." The design states (line 281) that the role assignments and the rule are UNSELECTED and UNSIGNED.

### 18.2 Interaction with the distinct-role safeguard

> **Superseded in part (Part VI, s48):** under the proposed SoD-A + SoD-C policy (s27) SoD-B is not a candidate, so the amendment question for SoD-B is moot.

The safeguard is the R1-L1b follow-up (commit `57dadd52` on `fix/range002-signoff-distinct-roles`; rebased as `3f05d17a` on `fix/range002-signoff-distinct-roles-rebased`, base `d61f313a`). It is **not merged**; `main` at `d61f313a` has no distinctness check. As prepared, `freeze_spec` refuses (`SignoffRolesNotDistinctError`) when `signoff.owner`, `signoff.trading_expert` and `signoff.independent_validator` are not **pairwise** distinct after NFKC / casefold / strip / whitespace-collapse; `load_frozen` reports `unusable_reasons`. It compares identifier strings only, over exactly those three fields (`SIGNOFF_ROLE_FIELDS`).

| Option | Expressible under the all-pairs safeguard? | Note |
|---|---|---|
| SoD-A | Yes | The strings can be distinct; the safeguard does not prove three humans |
| SoD-B | **No, not without amending the safeguard.** The all-pairs rule rejects `owner == trading_expert` | This is Workstream B finding F4. The safeguard has no waiver mechanism, so a recorded SoD-B waiver could not be frozen. Choosing SoD-B therefore requires an owner-approved safeguard amendment (or a different identifier convention that would defeat the purpose of the check). The owner must confirm which is intended |
| SoD-C | Yes (for the three signed fields) | The research lead and engine author are not among the three fields, so SoD-C is procedural only: signed validator attestation and a recorded engineer list |
| SoD-D | No | Would be rejected; and it contradicts owner ruling 5 |

Until the safeguard is merged (only on explicit owner instruction, and per Workstream B before any real freeze), none of the options is enforced in software.

### 18.3 Slots

| Slot | Name | Independent human validation evidence | SoD option | Signature / date |
|---|---|---|---|---|
| Research lead | BLANK | n/a | | BLANK |
| Trading-expert reviewer | BLANK | | | BLANK |
| Independent validator | BLANK | required (section 15.4) | | BLANK |
| Sole P6 approver | BLANK | | | BLANK |

## 19. P3a / P3b ATTEMPT LIMITS 1 / 1

**RECOMMENDED / PROPOSED -- NOT APPROVED.** `p3_attempt_limits.p3a = 1` and `.p3b = 1`: one authorized P3a attempt and one authorized P3b attempt per research lineage, each evaluating all frozen candidates together. Semantics, windows and hazards are in sections 3 and 12 and are unchanged. The limits are not to be written into the manifest until the owner has ruled on C-DR (section 20).

## 20. C-DR - NO AUTOMATIC DEFECT-ONLY RETRIES

**RECOMMENDED / PROPOSED -- NOT APPROVED.** Automatic defect-only retries are not allowed. The only path to another run after authorization is a **separate recovery authorization** under a recovery procedure that is **design-only (Level 2)** today (Hardening design section 1; Registry Recovery Procedure v0.1, `1d06024e`; Execution Boundary design Part D) and an **owner-approved incident process**. Neither is implemented. Until both exist and are approved, no rerun is available.

### 20.1 The conflict, quoted from Plan v0.5 (`RANGE-002_Implementation_Plan_v0.5.md`)

| Line | Section | Text (verbatim) |
|---|---|---|
| 101 | s0 rule R3 | "**The P4 holdout (2022-2025) is opened at most once per frozen spec.** Defect-only reruns need a logged defect record and owner approval." |
| 584 | WP4.0 step 2 | "**Control check.** If a control fails, the run verdict is `INCONCLUSIVE_ENGINE` and the sealed strategy outputs are **never opened** for this run. The defect goes through the defect-only rerun protocol." |
| 606 | WP4.1 | "**Defect-only reruns.** Allowed only for a bug in code or data. They need a defect record (symptom, root cause, fix commit, and why the fix does not encode knowledge of results) and owner approval. Each rerun is a ledger row." |
| 848 | s11.1 diagnosis table | "Document defect and obtain governed defect-only rerun authorization" |

(The Plan's dash characters are rendered here as hyphens.) Against the merged code: `run_registry.attempts_consumed` counts every run whose `capability_issued` row exists "whatever their protected window, spec hash, code version or final status"; `results_guard` states "There is no automatic retry, no counter reset and no recovery code (recovery would need a documented incident, independent review, owner authorization and a permanent audit record: design-only)"; a `budget_reset_authorization` argument is refused by name; a holdout authorization consumes the window with "no automatic restoration, no reissue, no reset". The attempt is consumed when the capability is issued, which precedes the stage-1 controls of WP4.0 step 2, so a control failure always happens after consumption. With limits 1 / 1 the Plan's protocol therefore describes a rerun the code cannot give.

### 20.2 Options (none selected)

| Option | Description | Effect | Risk |
|---|---|---|---|
| (i) | Limits 1 / 1; amend the Plan so defect reruns are explicitly unavailable until a separate recovery authorization exists; reduce technical-failure risk by validating the engine only on synthetic fixtures and `REPLAY_RNG001` (never citable) before any P3 authorization | Preserves the one-run discipline; matches the code | A defect in the real run ends the phase for the lineage; a new lineage needs an independently approved registration and exposure review |
| (ii) | Limits above 1 | Allows another authorization | The code cannot distinguish a defect rerun from an outcome-driven retry, so any value above 1 also permits outcome-driven retries; weakens the discipline the policy exists to enforce |
| (iii) | Implement and approve the recovery design first (sealed store WP4.0, owner key, incident record) | Permits a governed, evidenced rerun | Large Level 2 work; not available before P3a; Level 2 is deferred |

The recommendation combines (i) with (iii) as the only legitimate route to any rerun: limits 1 / 1 now, no automatic retry, and a separate recovery authorization if and when (iii) exists and the owner approves an incident. A recovery is an additional run row, both runs are reported, and it is not a new test of a different idea (Hardening section 1 describes this; design-only).

### 20.3 Proposed Plan wording amendments (PROPOSALS for the owner; nothing is edited)

> **Superseded in part (Part VI, s48):** the final proposed wording is s39 (AR-2). Where s20.3, s28 and s39 differ, s39 controls.

1. **R3 (line 101)**, replace the second sentence with: "Defect-only reruns are not automatic and are not available under the Level 1 registry. A run after authorization requires a separate recovery authorization under the owner-approved recovery procedure (incident record, independent review, owner approval and a permanent audit record). Until that procedure is implemented and approved, no rerun exists and the phase is ended for the lineage."
2. **WP4.0 step 2 (line 584)**, replace the last sentence with: "The run is closed `INCONCLUSIVE_ENGINE`, its attempt stays consumed, and any further run requires the separate recovery authorization described in WP4.1."
3. **WP4.1 (line 606)**, replace the bullet with: "**Defect-only reruns.** None is automatic. After `capability_issued` a rerun is possible only under a separate recovery authorization (design-only Level 2 procedure). Its request needs a defect record (symptom, root cause, fix commit, and why the fix does not encode knowledge of results), an independent review and owner approval, and it is recorded as an additional registry row; both runs are reported."
4. **s11.1 table (line 848)**, replace "obtain governed defect-only rerun authorization" with "request a separate recovery authorization (design-only until approved)".
5. **WP0.7**, add: "attempt limits P3a = 1 and P3b = 1 from the governance manifest; P4 is limited by the holdout once-per-window rule."

## 21. CANONICAL REGISTRY ENROLLMENT - PENDING

**Status: PENDING.** No ceremony is authorized or performed; no genesis id exists or is recorded; no registry location, host, operator or witness is decided; the manifest remains entirely unset. The description in section 2 is a plan only. Preconditions for ever running it include the owner's ruling on C-DR (section 20), the registry location, named operator and witness, and written authorization.

## 22. `p5.account_id` - MANDATORY-FIELD CONFLICT AND DESIGN OPTIONS

> **Superseded in part (Part VI, s48):** option B is now the owner's proposed direction (s31, s42). The marker literal `deferred_to_p5_activation` matches the local schema candidate `5bc2b493` (read-only cross-check, s49).

### 22.1 The conflict (escalated)

`schema.py` line 436 declares `account_id: str | None  # P0: D07`, the skeleton sets it to `None`, and `FrozenSpec.from_draft` raises `UnsetP0FieldsError` naming every unset P0 field, so a spec cannot freeze with it null. D07 and Plan WP5.1 create the dedicated paper account only in P5, after P4. Hash scope matters: `spec_sha256` covers everything except `signoff` (`DraftSpec.hashable_payload`), so the account id is inside the hash, and a later change to it changes `spec_sha256`, which every governed run, the holdout token and the frozen-file round-trip bind to.

### 22.2 Options compared (design only; nothing is implemented)

| | Option A: phase-conditional (nullable at freeze) | Option B: freeze-time marker plus separate P5 activation record | Option C: move the account block out of the hash |
|---|---|---|---|
| Idea | Make `p5.account_id` exempt from the P0-unset check (like `registration.trial_ledger_id`), required only when phase is P5 | Replace `p5.account_id` in the spec by a P0 field `p5.account_binding` with a closed value such as `deferred_to_p5_activation` (owner decision D07); a separate P5 activation record binds the real account id to the same `spec_sha256` later | Put the account id in an unhashed block like `signoff` |
| `schema.py` | Add `p5.account_id` to `_NON_P0_NULLABLE`; a validator rule | Remove or demote `account_id`; add the marker field and its closed vocabulary; skeleton and tests updated | Add an unhashed block; change `hashable_payload` |
| `freeze_spec.py` | None beyond the exemption | None (marker is an ordinary P0 value) | Must write and verify the unhashed block |
| `hashing` / `spec_sha256` | Hash covers `null`; later change of the id would change the hash unless stored elsewhere, so the id must still live outside the spec | Hash covers the marker, stable forever; the account id lives only in the activation record | Hash scope is widened by exclusion |
| Guard | P5 is already refused outright (`PaperApprovalNotImplementedError`); a later P5 PR must add the account binding check | The later P5 PR requires the activation record to name the same `spec_sha256`, the account id, and an owner approval reference | Guard must trust an unhashed value |
| Audit trail | Weak: a null cannot be distinguished from a forgotten value | Strong: the deferral is a deliberate, hashed, owner-signed choice | Weak: an editable block outside the hash |
| PR size | Small | Small to medium (schema, skeleton, tests, plan App. A wording) plus the later P5 PR | Medium; widens the unhashed surface |
| Risks | Silent null | The activation record needs a home (registry row or signed file) designed with the P5 work | Weakens immutability of the frozen spec; contradicts the principle that sign-off alone sits outside the hash |

**RECOMMENDED / PROPOSED -- NOT APPROVED: Option B.** It keeps `spec_sha256` stable, makes the deferral an explicit hashed owner decision, and requires no change to the freeze tool. It must be implemented and reviewed **before** any real freeze, because the schema defines the hash. A fourth course, the owner stating a value for the field now, is not recommended: the account cannot exist, and a placeholder would be an invented value.

### 22.3 Option B: PROPOSED / NOT APPROVED (owner direction, unsigned)

**PROPOSED / NOT APPROVED (owner direction, unsigned):** option B. `p5.account_id` is REPLACED by the P0 field `p5.account_binding`, a closed single-value literal `deferred_to_p5_activation` (D07), null until the owner sets it. The real account id lives only in a separate P5 activation record that names the same `spec_sha256`, the account id and an owner approval reference. The spec's free-form (OpenValue) fields, for example `p5.cost_ratio_contract`, `p5.shadow_acceptance`, `p5.degradation_tolerance` and `governance.roles`, are not meant to be an account source: they accept arbitrary JSON, and the schema proposal (Agent C's batch proposal s5, commit `9574d484`) therefore proposes that the activation record be the sole account authority. That is the proposal's wording, not settled register text. Plan v0.5 Appendix A wording on Agent C's docs branch: `account_binding: null  # P0: D07 (closed marker "deferred_to_p5_activation"; the account id is NOT in the spec: it is bound to this spec_sha256 by the separate P5 activation record, WP5.1)`. The register counts this as an owner **direction**, still NOT APPROVED, until a signed record exists.

## 23. A1 VS DESIGN v0.4 VS THE MERGED SCHEMA - UNRESOLVED INCONSISTENCY

### 23.1 What the documents say

Plan v0.5 header ("Precedence"): until A1 is signed "the design's fixed variants A/B remain the governing exit rule: build the schema and engine so they support the A1 exit-candidate set, but **do not freeze a spec** under either form." A1 header: "DRAFT - not in force until signed. Until signed, design v0.4 governs unchanged, including the fixed A/B exits." Design v0.4 s7 (via A1 s2-s3): one P3 run over 2016-2021 with pre-approved criteria (none given).

### 23.2 Everywhere the merged code hard-codes A1

| Place | A1 assumption |
|---|---|
| `spec/schema.py` `Partitions` (lines 160-163) | `development_selection`, `development_confirmation`, `holdout`, `exposed` fixed by equality validators to the A1 windows; no single 2016-2021 window |
| `spec/schema.py` `Exits` and `ExitCandidate` | 1..8 candidates, four families, `selection` block required |
| `spec/schema.py` `P3` | `criteria`, `max_p3a_attempts`, `max_p3b_attempts` |
| `spec/schema.py` `draft_skeleton()` | emits the A1 layout and the exits block |
| `spec/manifest.py` | `_LIMIT_KEYS = {p3a, p3b}`; `GovernanceManifest.max_p3a_attempts` / `max_p3b_attempts`; `check_limits` |
| `governance/model.py` lines 21-47 | `Partition.DEVELOPMENT_SELECTION` / `DEVELOPMENT_CONFIRMATION`, `Phase.P3A` / `P3B`, `PHASE_PARTITIONS` |
| `governance/results_guard.py` | lines 53-54 and 684: refusal while `p3_criteria` / `exits_candidates` / `exits_selection` unset; lines 426-427: phase order P3B after P3A, P4 after both; line 217: selection record is P3A only; lines 548-570: attempt-budget check for P3A / P3B |
| `governance/run_registry.py` | line 226 `_ATTEMPT_PHASES`; lines 627-628: a SelectionRecord belongs to a P3A run; attempt accounting at `mark_capability_issued` |
| `governance/verdict.py` | line 23 `EXIT_SELECTED`; lines 44-55: stage transitions `(UNTESTED, P3A) -> STOP or EXIT_SELECTED`, `(EXIT_SELECTED, P3B) -> STOP or ADVANCE_TO_P4` |
| `governance/spec_view.py`, `spec_adapter.py`, `spec/loader.py` | `exits_candidates`, `exits_selection`, `max_p3a_attempts`, `max_p3b_attempts`, `selection` / `confirmation` ranges |
| `scripts/research/range002/freeze_spec.py` | `check_limits(p3a, p3b)` |
| Tests | the range002 suite (882 tests in CI run 1822) and the CI manifest of required tests encode these shapes |

### 23.3 What a v0.4-style single P3 or fixed A/B would require changing

- Single P3: replace the two development partitions by one 2016-01-01..2021-12-31 window; collapse `Phase.P3A` / `P3B` and the partitions in `model.py`; rewrite the phase order and the predecessor rules (P4 after one P3); rewrite verdict transitions; change the manifest to one limit (and `schema_version`); change spec, view, adapter, loader and `freeze_spec` accordingly; revise tests and the CI required-test manifest.
- Fixed A/B: v0.4 has no selection rule (A primary, B secondary). The schema requires a non-null `exits.selection` and the guard refuses without it, so the exits block would need a "fixed variants, no selection" form, and the G4/G5 family would revert to the v0.4 A/B ordering that A1 replaced (D02).
- Either way this is a Level 1 infrastructure change of the size of PR #738 / #739 touching their reviewed, accepted surface.

### 23.4 The inconsistency, plainly

The documents say v0.4 governs until A1 is signed, but the merged tooling can only express the A1 form. Under v0.4 a spec cannot be frozen at all without code changes, and A1's P3a/P3b split is baked into the registry and the guard. "Reject A1 and fall back to v0.4" is therefore not a cheap option, and any amendment of A1's windows or phases would also require code changes. This is for the owner's adjudication.

**RECOMMENDED / PROPOSED -- NOT APPROVED:** A1 and v0.4 must be reconciled **in writing first** (a statement of which form is intended, that the infrastructure is built to A1, and what fallback costs), and only then submitted for signature. A1's three signature rows should not be collected before that.

## 24. PENDING STATISTICAL PARAMETERS - NO DEFAULTS

All of the following stay **PENDING decisions**; no default is substituted by this package:

- D02: hypothesis family option, count, adjustment (and the skeleton preset `stats.adjustment = holm`, which must be confirmed or overridden explicitly, not inherited).
- D06: `stats.bootstrap.method`, `block_len`, `ci_type`, `confidence_level`, `reps`, `seed`; `stats.alpha_one_sided`; `controls.random_entry.repetitions`, `seed`, `invalid_draw_policy`.
- D12 regime definition and criterion; D17 P3a/P3b criteria and STOP alpha; D19 selection score, tie tolerance, eligibility, STOP test; D04 yearly rule; D10 win-rate and drawdown values; D18 basis and trade unit.

Values quoted from the documents (alpha 0.05, 10,000 repetitions, 300/150 trades, 0.05 R) are **PROPOSED / NOT APPROVED** and appear only in the labelled proposal text of section 10, never as defaults.

**New evidence-timing finding (C-EVID):** D05 5a (minute-class counts) and 5b (minimum OR width in ticks, "chosen from the return-blind distribution") need intraday bars, but SIP data arrives only in P1, after the P0 gate and after the spec is frozen with `signal.min_or_width_ticks` set. The Sheets list this as return-blind evidence without noting that it cannot exist before freeze. The owner must rule: an early return-blind pull limited to these distributions (needs C12, D03 licence, F1, F5; resembles D09-hist option (c)), a value chosen without data, or a plan/A1 amendment adding a return-blind step before freeze. No option is selected here. (D12's regime session counts use the calendar and SPY daily close only and do not have this problem.)

## 25. INDIVIDUAL OWNER-DECISION RECORDS (UPDATES TO SECTION 11)

These records supersede the blank forms in section 11 for content; section 11 remains the plain signature form. Each shows the exact proposed value from the documents (**PROPOSED / NOT APPROVED**) or **NO VALUE PROPOSED**, the evidence, the approver roles, and the documents to pin. **Every SHA-256 field is BLANK until signing**, and every signature and date field is BLANK. Commit SHAs below are the last commits touching each path on `main` or the named local commit; the register's own pin is the commit that contains the final text.

### 25.1 Documents to pin (paths, commits)

| Key | Path | Commit |
|---|---|---|
| DOC-A1 | `docs/implementation/evidence/range_002/RANGE-002_Design_Addendum_A1.md` | `c7ebaf71` |
| DOC-PLAN | `docs/implementation/evidence/range_002/RANGE-002_Implementation_Plan_v0.5.md` | `c7ebaf71` |
| DOC-SHEETS | `docs/implementation/evidence/range_002/RANGE-002_P0_Decision_Sheets_v0.1.md` | `c7ebaf71` |
| DOC-RECON | `docs/implementation/evidence/range_002/governing_reconciliation.md` and `recon.md` | `c7ebaf71` |
| DOC-RNG | `docs/implementation/evidence/range_002/RNG-001_Rejection_Summary_Report_2026-10-09.md` | `c7ebaf71` |
| DOC-HARD | `docs/implementation/evidence/range_002/RANGE-002_Governance_Hardening_Design_v0.1.md` | `c7ebaf71` |
| DOC-REG | `docs/implementation/evidence/range_002/RANGE-002_P0_Decision_Register_v0.2.md` | commit containing the final text (BLANK until signing) |
| DOC-MAN | `docs/implementation/evidence/range_002/RANGE-002_governance_manifest.json` | `b31b5f7b` now; the commit of the manifest change after fill (BLANK) |
| DOC-DOCX | research design v0.4 DOCX (not in git; C10) | n/a |
| DOC-SIGN | `RANGE-002_Approval_Signing_and_Verification_Design_v0.1.md` | `d1406ec2` (local only) |
| DOC-L2 | Level 2 design index, Execution Boundary, Recovery Procedure, Acceptance plan | `79e072d7` (local only) |
| DOC-IND | `RANGE-002_Validator_Independence_Requirements_v0.1.md` | `7421ca62` (local only) |
| DOC-SAFE | distinct-role safeguard | `57dadd52` / `3f05d17a` (local only, not merged) |
| DOC-THESIS | `economic_thesis.md` (WP0.9) | does not exist yet |
| DOC-LEDGER | signed exposure ledger | does not exist yet |

### 25.2 Records

**Record A1 - Governing-Design Addendum A1**

- Decision: Governing-Design Addendum A1.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: A1 proposes (DRAFT, unsigned): exit chosen from a frozen closed set of <= 8 configurations by a frozen selection rule; P3a 2016-01-01..2019-12-31 (all K), P3b 2020-01-01..2021-12-31 (selected exit), P4 unchanged; P0 list D01-D19. PROPOSED / NOT APPROVED. No numeric parameter is set by A1 itself (values live in D17/D19).
- Evidence required: Owner review of A1 plus Sheets s5 wording items; D19/D17/D02 sheets seen first (Sheets rec.). No data.
- Approver(s) by role: Owner; trading-expert reviewer; independent validator (three rows, A1 s10).
- Documents to pin: DOC-A1, DOC-PLAN, DOC-SHEETS, DOC-RECON, DOC-DOCX, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D01 - Registration, exposure conclusions, holdout applicability**

- Decision: Registration, exposure conclusions, holdout applicability.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: No numeric value. Recommendation: do not sign until the WP0.6 contact audit (incl. AI-session history on 2016-2025 intraday data) is complete; unknown contact is reported as unknown. Owner rules whether other programs' use of the 2022-2025 daily layer is material for an intraday hypothesis. NO VALUE PROPOSED for the ruling.
- Evidence required: Signed WP0.6 contact audit; exposure ledger; `hypothesis_lineage.yaml` (WP0.11).
- Approver(s) by role: Owner (required); independent validator (recommended).
- Documents to pin: DOC-LEDGER, DOC-RNG, DOC-PLAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D02 - Hypothesis family and multiplicity adjustment**

- Decision: Hypothesis family and multiplicity adjustment.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: option (a) one Holm family over {G4, G5}, hypothesis count 2, one-sided alpha 0.05 (Sheets D02). PF >= 1.30 and stress mean > 0 are fixed gate thresholds, not open. Count under (b)/(c) is 1 for G4 with G5 separate.
- Evidence required: D06 decided first; validator confirms the statistics and the representation of the chosen option in the spec.
- Approver(s) by role: Owner; independent validator.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D03 - Universe N, PIT timing, SIP vendor and licence, data budget**

- Decision: Universe N, PIT timing, SIP vendor and licence, data budget.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: N = 100 (design s4 / Sheets D03). PIT timing: universe built after the prior trading day's close, effective from the first session of each month (Sheets rec.). Vendor: Alpaca SIP only if F1, F2, F5 pass. Data budget: NO VALUE PROPOSED (owner states a cap).
- Evidence required: F1 (history to 2016-01-01), F2 (delisted coverage), F5 (licence for stored research use), vendor plan confirmation, cost and storage figures.
- Approver(s) by role: Owner.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D04 - Yearly consistency gate**

- Decision: Yearly consistency gate.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: >= 3 of 4 calendar years 2022-2025 with PF > 1.0 (design s6); undefined or too-few-trade year does not pass; per-year minimum trade count: NO VALUE PROPOSED.
- Evidence required: None return-blind (count rule).
- Approver(s) by role: Owner.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D05 - Fill, risk and exit-mechanics values (5a-5j)**

- Decision: Fill, risk and exit-mechanics values (5a-5j).
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED (Sheets D05): 5a day eligible only if every minute 09:30-09:59 is present or `NO_TRADE_MINUTE`, any `DATA_GAP` minute makes it ineligible; 5b min OR width in ticks: NO VALUE PROPOSED (owner chooses after seeing the return-blind distribution); 5c qty = floor(risk_budget / R_pre), reduce/protect if actual risk > budget x (1 + tolerance), tolerance value NO VALUE PROPOSED, R_fill <= 0 means immediate exit; 5d gap fills at bar open plus adverse slippage; 5e entry-then-stop, stop before target, path_ambiguous = True; 5f tick by price band, sub-$1 excluded; 5g half-day exit 5 minutes before the 13:00 ET early close, i.e. 12:55 ET; 5h `EXIT_UNAVAILABLE`, no assumed exit; 5i no separate slippage model if D15 = all-in; 5j per-trade risk 0.25% (design proposal); per-name cap, gross cap, max concurrent, daily loss limit, participation cap: NO VALUE PROPOSED.
- Evidence required: Return-blind OR-width distribution (ticks, % of price), minute-class counts, half-day calendar, tick bands. No post-entry paths.
- Approver(s) by role: Owner; trading-expert reviewer.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D06 - Baselines, bootstrap parameters, confidence level, seeds**

- Decision: Baselines, bootstrap parameters, confidence level, seeds.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED (Sheets D06): stationary bootstrap over trading days; one-sided; alpha 0.05; percentile of the recentered null; fixed seeds; repetitions at least 10,000; random-entry invalid draws counted `NOT_EXECUTABLE` with the denominator preserved. Mean block length: NO VALUE PROPOSED (the repo's daily `BLOCK_LEN = 10` is a precedent only; the validator confirms or replaces; it must not be estimated from RANGE-002 data). Seeds: NO VALUE PROPOSED (fixed, owner/validator state).
- Evidence required: Synthetic size/power calibration by the validator. No RANGE-002 data.
- Approver(s) by role: Owner; independent validator.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D07 - P5 contract: paper-account policy, tolerances, cost-ratio contract**

- Decision: P5 contract: paper-account policy, tolerances, cost-ratio contract.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: record the account POLICY (new, dedicated, not user 2) at P0 and the ID at WP5.1; cost ratio = sum(realized shortfall)/sum(modeled cost) over trades with positive modeled cost, others `UNDEFINED`. Degradation and drawdown tolerances, maximum number and length of extensions: NO VALUE PROPOSED. CONFLICT C-P5: the schema requires a non-null `p5.account_id` at freeze.
- Evidence required: None return-blind; owner ruling on the `p5.account_id` timing.
- Approver(s) by role: Owner.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D08 - Roles and sole P6 approver**

- Decision: Roles and sole P6 approver.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: four distinct humans; at minimum the independent validator is neither the research lead nor the engine author; flag if the owner is also the trading-expert reviewer. NO NAMES PROPOSED.
- Evidence required: Names; separation-of-duties option; independence confirmation (section 15).
- Approver(s) by role: Owner (names the roles); each named person signs their own role row.
- Documents to pin: DOC-SIGN, DOC-IND, DOC-SAFE, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D09 - ADR 0037 statement and ORM-001 relationship (with C2 open items)**

- Decision: ADR 0037 statement and ORM-001 relationship (with C2 open items).
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: ORM-001 option (b) shared trial ledger and multiplicity family, separate specs; history for criterion 1: exposed RNG-001 IEX 5-minute archive (alternatives (b) reorder with an A1 amendment, (c) owner-authorized early return-blind SIP pull). Numeric overlap limit: NO VALUE PROPOSED (owner states; lower is more conservative). Criteria 2/3 reviewers: NO NAMES PROPOSED. Gate-clause handling while no tool exists: proposed as signed reviewer findings on all three criteria.
- Evidence required: Versioned records of both programs' entry/exit/universe/granularity/falsification condition; signal-timestamp overlap on the chosen history (no returns).
- Approver(s) by role: Owner; trading-expert reviewer; independent validator.
- Documents to pin: DOC-RECON, DOC-PLAN, DOC-SHEETS, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D10 - Win-rate gate and drawdown comparator**

- Decision: Win-rate gate and drawdown comparator.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: platform > 50% gate stays and promotion is blocked until the owner signs a written deviation; both evaluations displayed. Drawdown comparator: random-entry portfolio under identical capital, costs, equity sampling and exposure as primary, SPY buy-and-hold as reported reference. No deviation proposed.
- Evidence required: Comparator definition and equity-sampling rule only.
- Approver(s) by role: Owner.
- Documents to pin: DOC-RNG, DOC-PLAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D11 - Loader approach and `data.fetch_mode`**

- Decision: Loader approach and `data.fetch_mode`.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: confirm ruling C5 (new monthly-chunked, fail-closed RANGE-002 SIP loader; shared `BarCache` not modified). The enumeration string for `data.fetch_mode`: no value proposed in these documents.
- Evidence required: WP1.1 finding on `bar_cache.py` (in recon).
- Approver(s) by role: Owner.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D12 - Regime definition and single-regime criterion**

- Decision: Regime definition and single-regime criterion.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: regime = SPY prior close vs 200-day SMA (causal); criterion (a) both regimes and both halves have positive net mean R with a minimum trades-per-cell, plus (b) a share cap on P&L from one regime/half. Minimum trades-per-cell and share cap: NO VALUE PROPOSED.
- Evidence required: Counts of sessions per regime and per half over 2022-2025 (calendar and SPY daily close only).
- Approver(s) by role: Owner; independent validator.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D13 - Economic thesis, naive-ORB definition, binding vs non-binding diagnostics**

- Decision: Economic thesis, naive-ORB definition, binding vs non-binding diagnostics.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: thesis written and signed by humans (not authored by an agent); naive ORB = 'OR-high touch, no tick offset, same exits' (Plan WP2.5 example); binding = G0-G10 only, all other diagnostics non-binding.
- Evidence required: `economic_thesis.md` and its SHA-256; return-blind price-geometry distributions.
- Approver(s) by role: Research lead; trading-expert reviewer; owner.
- Documents to pin: DOC-THESIS, DOC-PLAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D14 - Execution contract**

- Decision: Execution contract.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED (Sheets D14): crossed-before-arm = SKIP; stop protection only after the entry fill is acknowledged and sized; reservation at submission, released on cancel/expiry/fill. Order type: decide after F3 (no value proposed). Bar timestamp convention and vendor delay: verify with F4 (no value proposed). Submit/ack latency, EOD lead (seconds): NO VALUE PROPOSED. Tie-break: seeded hash order or permaticker ascending, owner picks.
- Evidence required: F3 broker capability report (any probe order needs separate written owner authorization, R14); F4; F10. F11 must not be started.
- Approver(s) by role: Owner; trading-expert reviewer.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D15 - Cost accounting mode and components**

- Decision: Cost accounting mode and components.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: all-in bps as a P&L debit with fills at the modeled price and no extra slippage (Plan recommendation); G3 stays binding. Component breakdown: NO VALUE PROPOSED.
- Evidence required: None return-blind.
- Approver(s) by role: Owner.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D16 - Diagnosis taxonomy, shadow-run acceptance, execution-quality evidence**

- Decision: Diagnosis taxonomy, shadow-run acceptance, execution-quality evidence.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: adopt the eight labels (`NO_DEMONSTRATED_EDGE`, `EXECUTION_COST_DOMINATES`, `INSUFFICIENT_SAMPLE`, `REGIME_FRAGILITY`, `CAPACITY_OR_RISK_CONSTRAINT`, `DATA_OR_ENGINE_DEFECT`, `PAPER_OPERATION_FAILURE`, `UNCLASSIFIED`) as explanatory only; shadow acceptance zero orphan signals/duplicate intents/look-ahead discrepancies over N sampled days: N NO VALUE PROPOSED.
- Evidence required: None.
- Approver(s) by role: Owner.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D17 - P3a eligibility and STOP level; P3b criteria**

- Decision: P3a eligibility and STOP level; P3b criteria.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED (Sheets D17): P3a minimum 300 trades (P4 rate of 300 per 4 years over the 4-year P3a window); PF > 1.0 at base cost; STOP test one-sided alpha 0.05 on the max-statistic over K (alternatives 0.10, 0.20). P3b: same thresholds as P4 with G1 scaled to two years, 150 trades (alternatives: looser screen; significance only). 300 and 150 are scaling proposals, NOT attempt limits.
- Evidence required: None return-blind; the attainable trade count cannot be verified return-blind. Depends on D06 and D18.
- Approver(s) by role: Owner; independent validator.
- Documents to pin: DOC-A1, DOC-PLAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D18 - Gate computation basis and trade unit**

- Decision: Gate computation basis and trade unit.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED: portfolio-constrained filled trades; signal-level as diagnostic; one entry = one trade including all exit fills; net R = total net P&L of all exit fills / (entry qty x R_fill).
- Evidence required: None.
- Approver(s) by role: Owner; independent validator.
- Documents to pin: DOC-PLAN, DOC-SHEETS, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D19 - Exit candidate set and selection rule**

- Decision: Exit candidate set and selection rule.
- Value (owner states; BLANK): ____
- Proposed value, PROPOSED / NOT APPROVED, from the documents: PROPOSED / NOT APPROVED (Plan s2.2): K = 7: E1 time exit; E2a/E2b fixed target k in {2, 3} R; E3a/E3b breakeven after +1R then trail t in {1.0, 1.5} R; E4a/E4b sell 50% at +1R, remainder (a) EOD flat, (b) trail 1.0. Complexity rank E1=1, E2=2, E3=3, E4=4. Score = one-sided lower bound of mean net R per trade (D06 bootstrap). Tie tolerance delta: 0.05 R is an ILLUSTRATIVE PLACEHOLDER only (Sheets D19: 'I have no basis to set it'); owner and validator confirm or replace. Eligibility from D17; STOP test from D17.
- Evidence required: Trading-expert review; validator review of `select_exit` and the max-statistic test; no outcome data; fixtures synthetic.
- Approver(s) by role: Owner; trading-expert reviewer; independent validator.
- Documents to pin: DOC-A1, DOC-PLAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record C2-overlap - Numeric maximum signal-overlap (criterion 1)**

- Decision: Numeric maximum signal-overlap (criterion 1).
- Value (owner states; BLANK): ____
- Proposed value: NO VALUE PROPOSED (owner states the number)
- Evidence required: Signal-timestamp overlap on the chosen history; no returns
- Approver(s) by role: Owner; independent validator confirms the metric
- Documents to pin: DOC-RECON, DOC-SHEETS, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record C2-reviewers - Reviewers for criteria 2 and 3 of the ATP v0.14 s3A.2 framework**

- Decision: Reviewers for criteria 2 and 3 of the ATP v0.14 s3A.2 framework.
- Value (owner states; BLANK): ____
- Proposed value: NO NAMES PROPOSED
- Evidence required: D13 thesis; D08 roles
- Approver(s) by role: Owner; the two named reviewers
- Documents to pin: DOC-RECON, DOC-SHEETS, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D09-hist - History used for criterion 1 and handling of the P0 clause 'the non-equivalence check passes'**

- Decision: History used for criterion 1 and handling of the P0 clause 'the non-equivalence check passes'.
- Value (owner states; BLANK): ____
- Proposed value: PROPOSED / NOT APPROVED: option (a), the exposed RNG-001 IEX 5-minute archive, timestamps and direction only; alternatives (b), (c) in Sheets D09; gate-clause handling proposed as signed reviewer findings on all three criteria
- Evidence required: Owner statement; if (b), an A1 amendment
- Approver(s) by role: Owner
- Documents to pin: DOC-SHEETS, DOC-PLAN, DOC-A1, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record C10 - Custody of the authoritative design DOCX and recording its SHA-256**

- Decision: Custody of the authoritative design DOCX and recording its SHA-256.
- Value (owner states; BLANK): ____
- Proposed value: PROPOSED / NOT APPROVED: wait for the S3 manifest tooling; DOCX stays local and untracked; record its SHA-256 and version in the packet
- Evidence required: SHA-256 of the DOCX bytes
- Approver(s) by role: Owner
- Documents to pin: DOC-DOCX, DOC-SHEETS, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record C12 - Name of the approved isolated non-production research environment and the accountable person**

- Decision: Name of the approved isolated non-production research environment and the accountable person.
- Value (owner states; BLANK): ____
- Proposed value: NO ENVIRONMENT PROPOSED (requirements in Sheets C12)
- Evidence required: Metadata-only reachability test from the named host
- Approver(s) by role: Owner
- Documents to pin: DOC-SHEETS, DOC-RECON, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record D08-SoD - Separation-of-duties option (SoD-A/B/C/D) and any recorded waiver**

- Decision: Separation-of-duties option (SoD-A/B/C/D) and any recorded waiver.
- Value (owner states; BLANK): ____
- Proposed value: NO OPTION SELECTED. Recommendation (not a decision) in the signing design: SoD-A target, SoD-C minimum; SoD-B needs a safeguard amendment (section 18.2)
- Evidence required: Owner statement; validator attestation (15.4); Workstream B document
- Approver(s) by role: Owner; independent validator acknowledges
- Documents to pin: DOC-SIGN, DOC-IND, DOC-SAFE, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record M-loc - Canonical registry location (absolute path, host)**

- Decision: Canonical registry location (absolute path, host).
- Value (owner states; BLANK): ____
- Proposed value: NO LOCATION PROPOSED
- Evidence required: Owner statement of path and host
- Approver(s) by role: Owner
- Documents to pin: DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record M-ops - Ceremony operator and witness (humans); written authorization to enroll**

- Decision: Ceremony operator and witness (humans); written authorization to enroll.
- Value (owner states; BLANK): ____
- Proposed value: NO NAMES PROPOSED; authorization to enroll: PENDING
- Evidence required: Names; written authorization
- Approver(s) by role: Owner
- Documents to pin: DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record M-lim-p3a - `p3_attempt_limits.p3a` (and spec `p3.max_p3a_attempts`)**

- Decision: `p3_attempt_limits.p3a` (and spec `p3.max_p3a_attempts`).
- Value (owner states; BLANK): ____
- Proposed value: PROPOSED / NOT APPROVED: 1 (blocked on the C-DR ruling)
- Evidence required: Owner decision after sections 3, 12, 20
- Approver(s) by role: Owner
- Documents to pin: DOC-MAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record M-lim-p3b - `p3_attempt_limits.p3b` (and spec `p3.max_p3b_attempts`)**

- Decision: `p3_attempt_limits.p3b` (and spec `p3.max_p3b_attempts`).
- Value (owner states; BLANK): ____
- Proposed value: PROPOSED / NOT APPROVED: 1 (blocked on the C-DR ruling)
- Evidence required: Same
- Approver(s) by role: Owner
- Documents to pin: DOC-MAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record M-gen - `approved_registry_genesis_id`, `approved_by`, `approved_on` (filled after enrollment only)**

- Decision: `approved_registry_genesis_id`, `approved_by`, `approved_on` (filled after enrollment only).
- Value (owner states; BLANK): ____
- Proposed value: NO VALUE EXISTS (no registry enrolled; no id may be supplied before enrollment)
- Evidence required: Enrollment evidence record (section 2.7)
- Approver(s) by role: Owner; reviewer of the manifest PR
- Documents to pin: DOC-MAN, genesis evidence file (not in git). SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record C-DR - Ruling on defect-only reruns versus the attempt limit**

- Decision: Ruling on defect-only reruns versus the attempt limit.
- Value (owner states; BLANK): ____
- Proposed value: PROPOSED / NOT APPROVED: no automatic defect-only retries; separate recovery authorization; option (i) with (iii) as the only route; wording in section 20.3
- Evidence required: Owner decision after section 20
- Approver(s) by role: Owner
- Documents to pin: DOC-PLAN, DOC-HARD, DOC-L2, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

**Record C-P5 - How `p5.account_id` is satisfied at freeze**

- Decision: How `p5.account_id` is satisfied at freeze.
- Value (owner states; BLANK): ____
- Proposed value: PROPOSED / NOT APPROVED (owner direction, unsigned): option B (section 22.3): `p5.account_id` replaced by `p5.account_binding` = `deferred_to_p5_activation`; the account id is held only in a separate P5 activation record (the schema proposal s5 proposes that record as the sole account authority and that free-form spec fields not be an account source)
- Evidence required: Owner decision; implementation PR reviewed before any freeze
- Approver(s) by role: Owner; independent validator reviews the schema change
- Documents to pin: DOC-SHEETS, DOC-PLAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

## 26. REFRESHED P0 STATUS

> **Superseded in part (Part VI, s48):** s37, s47 and s50 are the current status.

### 26.1 Ordered P0 blocker list (supersedes section 16)

1. Name the four D08 role slots; select the SoD option formally; obtain the independent validator's attestation (15.4 / Workstream B). If SoD-B is wanted, decide the safeguard amendment first (18.2).
2. Rule on C-DR (section 20) and, in the same ruling, the two limit values (proposed 1 / 1).
3. Reconcile A1 with v0.4 and the merged schema in writing (section 23) before A1 goes for signature.
4. Rule on `p5.account_id` (section 22) and rule on the C-EVID timing question (section 24); implement the approved schema change before any real freeze.
5. Long-lead externals in parallel: C12, D03 with F1/F2/F5, C10, F3/F4.
6. Decide the registry location, operator, witness and give written authorization; only then the enrollment ceremony (still PENDING); then the single manifest change.
7. WP0.6 contact audit then D01; D09 / C2 and the non-equivalence record; D13 thesis (human-written).
8. Statistics in order: D06, D18, D19 with D17, D02, then A1.
9. D05, D14, D15; D12, D04, D10, D16, D07.
10. WP0.8-0.12 signed; real spec drafted; SHA-256 of every pinned document recorded; independent-validator attestation filed; safeguard merged if the owner so instructs; real `freeze_spec`; P0 exit; P1.

### 26.2 P0 decisions READY FOR OWNER APPROVAL (documented evidence complete, no design change needed; not approved)

D04 (yearly gate), D10 (win-rate gate and comparator), D11 (loader approach and `data.fetch_mode` string, which the owner states), D15 (cost accounting mode), D16 (taxonomy; the owner states the shadow-day count), D18 (gate basis and trade unit), C10 (DOCX custody), and D06 (bootstrap and baselines; the validator's synthetic calibration is recommended, not required). Naming the D08 slots is also ready as a step, but approval of the separation rule needs the choice in 26.4.

### 26.3 Ready once a predecessor is signed or a review exists (no design change)

D02 (after D06); D17 and D19 (after D06 and D18, signed together, D19 after trading-expert review); D13 (after the human-written thesis); D14 and D05 (after F3/F4 and, for D05 5a/5b, the C-EVID ruling); D03 (after F1/F2/F5); D01 (after the WP0.6 audit); D09 / C2 (after D13 and a history ruling); D12 (after the session counts); C12; M-lim (after C-DR).

### 26.4 Decisions REQUIRING DESIGN CHANGES or rulings that change documents or code

- **C-DR**: Plan wording amendments (20.3) and, for any rerun, an unbuilt Level 2 recovery procedure.
- **`p5.account_id`**: schema change under proposed option B (PROPOSED / NOT APPROVED; owner direction, unsigned) before any freeze; implemented in a local, unpushed schema candidate only; the merged schema still requires `p5.account_id`.
- **A1 / v0.4 / merged schema**: written reconciliation; code changes if anything other than the A1 form is intended.
- **SoD-B**, if chosen: amendment of the distinct-role safeguard.
- **C-EVID**: a plan / A1 amendment or an owner-authorized early return-blind pull, if D05 5a/5b are to be evidence-based.
- Safeguard hygiene from Workstream B (F1: strip zero-width and control characters; test-id manifest) before any real freeze.

### 26.5 Final P0 GO / NO-GO (recommendation only)

**NO-GO.** P0 is not ready. Zero decisions are formally approved; the manifest is unset; no registry is enrolled (PENDING); three items require design changes or written reconciliation (C-DR, `p5.account_id`, A1 versus schema) plus a data-timing ruling (C-EVID); no independent validator is named or attested. P0 may move to GO only when the records in sections 11 and 25 are signed against pinned SHA-256 hashes, the schema and plan changes above are reviewed and merged, the manifest change has merged after an authorized enrollment, the real `freeze_spec` has passed, and the independent validator has attested. The decision is the owner's.

---

# PART IV - OWNER PROVISIONAL POLICY DIRECTIONS INCORPORATED (ALL NOT SIGNED)

Every item in Part IV is **PROVISIONAL POLICY DIRECTION -- NOT SIGNED** or **PROPOSED -- NOT APPROVED**. The proposed 10,000 repetitions, alpha 0.05, 300 / 150 trades, delta placeholder and every other numeric value quoted from the documents remain recommendations until a signed record exists. Nothing in Part IV signs, approves, enrolls or freezes anything, and no data was accessed.

## 27. D08 - SoD-A PLUS SoD-C (PROVISIONAL POLICY DIRECTION -- NOT SIGNED)

**Direction.** Apply SoD-A (three distinct humans, three distinct keys or identifiers, for owner / trading expert / validator) **plus** the additional validator-independence requirements of SoD-C (the validator is also distinct from the research lead and from whoever wrote the engine). Section 18.1 quotes the option text verbatim from the signing design (lines 289 and 291 of the `d1406ec2` file).

**Consequences.**
- **SoD-B is removed** as a policy candidate. The distinct-role safeguard (PR #740, commit `8792e043`, branch `fix/range002-signoff-distinct-roles`; earlier forms `57dadd52`, `3f05d17a`) enforces **all-pairs** distinctness of `signoff.owner`, `signoff.trading_expert` and `signoff.independent_validator`, so `owner == trading_expert` is **not permitted**. Section 18.2's note that SoD-B needed a safeguard amendment is therefore moot under this direction. The safeguard is not on `main` at the base of this branch (`d61f313a`); its merge needs the owner's separate instruction.
- The software checks identifier strings only. SoD-A's "distinct humans" and SoD-C's extra requirements (validator not the research lead, not the engine author, a recorded engineer list) are **procedural** and are evidenced by the independent attestation of section 15.4 and the Workstream B document cited in section 15.5, obtained separately.
- If the owner is also the person best placed to review trade logic, a different person must hold the trading-expert slot; the owner may not hold two of the three signing slots.

**Still pending (all BLANK):** the four names (research lead, trading-expert reviewer, independent validator, sole P6 approver), the independent validator's attestation, the engineer list, and the signed D08 and SoD records.

| Slot | Name | Attestation on file | Signature / date |
|---|---|---|---|
| Research lead | BLANK | n/a | BLANK |
| Trading-expert reviewer | BLANK | | BLANK |
| Independent validator | BLANK | BLANK | BLANK |
| Sole P6 approver | BLANK | n/a | BLANK |
| Engineer list (engine, spec and gate authors) | BLANK | | BLANK |

## 28. C-DR - OPTION (i), NO AUTOMATIC DEFECT-ONLY RERUNS (PROVISIONAL POLICY DIRECTION -- NOT SIGNED)

**Direction (owner's statements, restated).**
1. There are **no automatic defect-only reruns**.
2. **One** authorized P3a attempt and **one** authorized P3b attempt per research lineage, **consumed at `capability_issued`**, counted across **all spec versions and windows in the lineage** (matches the merged code: one budget per genesis and phase, section 3.2).
3. A technical defect after authorization **may permanently end that phase** under the current implementation.
4. A separate recovery authorization **cannot actually enable a rerun** until a compatible recovery mechanism is implemented and approved. Recovery is design-only (Level 2) today.
5. **Do not raise the attempt limits to 2 or 3** to make failures recoverable: the registry cannot tell a defect rerun from an outcome-driven retry, so a higher limit would permit outcome-driven retries.

**The governing Plan must be corrected** to state this limitation. The wording below is **PROPOSED -- NOT APPLIED**; nothing in the Plan or A1 has been edited. Section 20.3 gave earlier proposals; the texts below replace them, in the owner's terms. Quoted lines are from `RANGE-002_Implementation_Plan_v0.5.md` at `c7ebaf71`.

| Plan location | Current text (verbatim, abbreviated where marked) | PROPOSED replacement text (NOT APPLIED) |
|---|---|---|
| s0 R3, line 101 | "Defect-only reruns need a logged defect record and owner approval." | "There are no automatic defect-only reruns. Each of P3a and P3b has exactly one authorized attempt per research lineage, consumed when authorization is issued; the holdout window is consumed on authorization. Under the current implementation a technical defect after authorization may permanently end that phase for the lineage. A separate recovery authorization is not a rerun: it cannot enable one until a compatible recovery mechanism has been implemented and approved." |
| WP4.0 step 2, line 584 | "...The defect goes through the defect-only rerun protocol." | "...The run is closed `INCONCLUSIVE_ENGINE`; its attempt stays consumed; no rerun is available under the current implementation. The defect is documented, and any further run requires a recovery mechanism that has been implemented and approved separately." |
| WP4.1, line 606 | "**Defect-only reruns.** Allowed only for a bug in code or data. They need a defect record (symptom, root cause, fix commit, and why the fix does not encode knowledge of results) and owner approval. Each rerun is a ledger row." | "**No automatic defect-only reruns.** The attempt limits are one authorized P3a attempt and one authorized P3b attempt per lineage, across all spec versions and windows. A technical defect after authorization may permanently end the phase. A defect record (symptom, root cause, fix commit, why the fix does not encode knowledge of results) is still required for the permanent record. Raising an attempt limit to permit a retry is not permitted, because outcome-driven retries cannot be distinguished from defect retries." |
| s5.2, line 698 | "`INCONCLUSIVE` is not a soft pass. A repair and retest goes through a separate governance decision." | "`INCONCLUSIVE` is not a soft pass. No repair-and-retest mechanism is implemented; any retest needs a separately designed, approved and implemented recovery mechanism, or a new owner-approved registration with inherited exposure." |
| s6 step 6, line 710 | "A crash between steps 1 and 5 leaves the row `ABORTED`. The run still counts in the ledger." | add: "It also consumes the attempt if `capability_issued` was written, and under limits of 1 this ends the phase for the lineage." |
| s11.1 diagnosis table, line 848 | "Document defect and obtain governed defect-only rerun authorization" | "Document the defect; a rerun is not available unless a compatible recovery mechanism has been implemented and approved" |
| WP0.7 | planned runs "P3a x1 covering all K, P3b x1, P4 x1" | add: "attempt limits P3a = 1 and P3b = 1 are the pre-registered values in the governance manifest; P4 is limited by the holdout once-per-window rule" |
| New R19 (proposed) | none | "R19. Attempt-limit limitation notice: a technical failure after authorization may permanently end a phase; do not authorize a P3 or P4 run until engine validation on synthetic fixtures and `REPLAY_RNG001` (never citable) has been completed." |

Corresponding note for A1 s3 (proposal): add one sentence that the P3a and P3b attempts are single and non-recoverable under the current implementation.

Mitigation inside the policy (no code needed): complete engine validation on synthetic fixtures and `REPLAY_RNG001` before any P3 authorization; do not authorize on a code state that has not passed the full required-test manifest.

## 29. A1 - TWO-DEVELOPMENT-STAGE ARCHITECTURE, SUBJECT TO RECONCILIATION AND INDEPENDENT REVIEW (PROVISIONAL POLICY DIRECTION -- NOT SIGNED)

**Direction.** Proceed with P3a selection (2016-01-01..2019-12-31) and P3b confirmation (2020-01-01..2021-12-31), **subject to** (1) a written reconciliation of A1 with design v0.4 and the merged schema, and (2) independent review of the exit-selection methodology. **A1 must not be signed merely because the code assumes it** (section 23.4).

### 29.1 Reconciliation memo outline (PROPOSED; the memo is not written)

1. Purpose, status and authority: which documents govern (design v0.4 as the owner's baseline, A1 as the amendment) and the standing statement "v0.4 governs until A1 is signed".
2. Side-by-side table, one row per topic: exit rule (A/B vs candidate set), P3 structure and windows, phases and verdicts, hypothesis family (D02), decision list (12 vs 19), gate thresholds (unchanged), sample-size treatment (D17 gap), attempt budgeting.
3. Merged-schema inventory: the table of section 23.2, re-verified at the commit used, with an explicit statement that the code expresses only the A1 form.
4. Cost of the fallback: section 23.3 restated and estimated (files, tests, required-test manifest, re-review).
5. Intended form: a plain statement that the infrastructure is built to A1 and that rejecting A1 requires a re-plan, so that signing A1 is a methodological choice, not a consequence of existing code.
6. Required wording corrections in A1 and the Plan (Sheets s5 items, the C-DR amendments of section 28, the P5 marker of section 31, the C-EVID amendment of section 32).
7. Effects on the sign-off packet (documents pinned) and on the Plan header "Precedence" paragraph.
8. Open questions and the decision requested of the owner.
9. Signature block: author, independent reviewer, owner (all BLANK).

### 29.2 Independent review of the exit-selection methodology: requirements (PROPOSED)

**Reviewer:** the independent validator (D08), meeting SoD-C: not the research lead, not an author of the engine, spec, selection or gate code, no exposure to RANGE-002 results.

**Scope.** The selection score (one-sided bootstrap lower bound of mean net R per trade), eligibility (trade minimum, PF > 1.0 at base cost), the tie tolerance delta and complexity order, the pure function `select_exit`, the selection-aware max-statistic test over K, the sealed protocol (selection record hashed before unsealing), the interaction of P3a, P3b and P4 as sequential data uses, and the K-candidate set including the correlation of candidates that share one entry stream.

**Required evidence (synthetic only):**
- Size of the full P3a-then-P3b pipeline under a null with no edge, including correlated candidates (K = 7) and variable trade counts per day.
- Power and selection accuracy under planted edges the validator specifies (which candidate is best, by how much).
- Selection bias: the optimism of the selected candidate's P3a score relative to its P3b score under the null.
- Sensitivity to delta, block length, repetitions and the STOP alpha.
- Determinism and reproducibility under fixed seeds; fixtures for tie cases.
- A written conclusion on whether the methodology is adequate to support signing A1, with any required amendments.

**Outputs:** a methodology review report, the calibration report, commit SHAs and SHA-256 values; sign-off fields BLANK.

## 30. REGISTRY GENESIS - UNENROLLED (PROVISIONAL POLICY DIRECTION -- NOT SIGNED)

The registry remains **unenrolled**. No ceremony, no genesis id, no manifest values. Pending items, all BLANK: host, registry path, operator, witness, written authorization to enroll, the decided attempt limits (provisionally 1 / 1), and the manifest change. Section 2 remains a description only.

## 31. P5 OPTION B - HASHED DEFERRAL MARKER AND ACTIVATION RECORD (PROVISIONAL POLICY DIRECTION -- NOT SIGNED; PROPOSAL, NOT IMPLEMENTED)

**Direction.** Option B of section 22: a hashed deferral marker `p5.account_binding` in the frozen spec and a separate P5 activation record that binds the account id to the same `spec_sha256`. The specification below is a **proposal for a future implementation PR**; nothing is implemented.

### 31.1 Schema change (`spec/schema.py`)

- Remove the free field `p5.account_id` (currently `str | None`, a P0 field).
- Add `p5.account_binding`, a P0 field with a closed vocabulary. Proposed single permitted value: `"deferred_to_p5_activation"`; the owner's D07 signature selects it. (The marker value text is a proposal.)
- Skeleton: `"account_binding": None`; Plan Appendix A and the D07 sheet updated; tests for "unset refuses", "unknown value refuses" and "account id in the spec refuses" (unknown keys are already rejected).
- All other `p5.*` keys unchanged (`min_days 60`, `min_trades 100`, `max_cost_ratio 1.5` locked; `degradation_tolerance`, `cost_ratio_contract`, `shadow_acceptance` open).

### 31.2 `freeze_spec` behaviour

No change to the tool: the marker is an ordinary P0 field, so a draft with it unset is refused by name (`UnsetP0FieldsError`) and a draft with the permitted value freezes. Add a test that a draft carrying an account id is refused. Output, `--verify` and the round-trip are unchanged.

### 31.3 Hash impact

`spec_sha256` covers everything except `signoff` (`DraftSpec.hashable_payload`). The marker is inside the hash and is stable for the life of the spec. The account id never enters the spec, so binding it later does not change `spec_sha256`. Because the schema defines the hash, the change must merge **before any real freeze**; no spec has been frozen, so no existing hash is invalidated.

### 31.4 Activation-record format (PROPOSED)

A strict-JSON record (canonical hashing as in `spec/hashing.py`), kept as a hash-chained registry row of kind `p5_activation` (requires a small registry extension designed with the P5 work) or an equivalent append-only file. Fields:

| Field | Content |
|---|---|
| `schema_version` | 1 |
| `kind` | `range002_p5_activation` |
| `spec_sha256` | the frozen spec's hash (must equal) |
| `registry_genesis_id` | the lineage's genesis id |
| `account_provider`, `account_id` | the new, dedicated paper account identifier (not the RNG-001 / user 2 account) |
| `p4_run_id`, `p4_verdict`, `p4_audit_pack_sha256` | the completed P4 run, verdict `PASS_HISTORICAL_PENDING_PROSPECTIVE`, and its audit pack hash |
| `manifest_sha256` | manifest hash at activation |
| `owner_approval_ref` | reference and SHA-256 of the owner's written P5 approval |
| `created_utc`, `created_by` | unauthenticated at Level 1 |
| `prev_hash`, `row_hash` | chain fields |

### 31.5 Guard check (future P5 PR; today P5 is refused outright)

P5 authorization would require: (1) a frozen spec whose `p5.account_binding` equals the permitted value; (2) exactly one activation record for the lineage whose `spec_sha256` equals the spec's and whose genesis id equals the registry's; (3) a non-blank `account_id` different from any account on a deny list that includes the RNG-001 / user 2 account; (4) a COMPLETED P4 with a `holdout_authorized` row, the same spec hash and the recorded verdict; (5) the owner approval reference present; (6) no rebinding (a second record for the lineage is refused). Level 1 limitations apply: identifiers are unauthenticated text. Until the P5 PR exists, behaviour is unchanged: `PaperApprovalNotImplementedError`.

PR size (proposal): schema, skeleton, tests and Plan Appendix A wording for the marker (small); the registry extension and guard check belong with the later P5 PR.

## 32. C-EVID - CONTROLLED PRE-FREEZE RETURN-BLIND FEASIBILITY AMENDMENT (DRAFT; PROVISIONAL POLICY DIRECTION -- NOT SIGNED)

**Direction.** The owner's direction is a **pre-freeze feasibility amendment**, **not** an unrestricted early data pull. The amendment must first approve the permitted data fields, summaries, independent oversight, exposure logging and isolated environment. Only a **subsequent, explicit authorization** may permit acquisition. No strategy outcomes, P&L, candidate selection or backtesting may be exposed.

**Why it exists (C-EVID).** D05 5a (minute-class counts) and 5b (minimum OR width in ticks, "chosen from the return-blind distribution", Sheets D05) need intraday bars that the Plan acquires only in P1, after the freeze. Plan R1 already permits return-blind coverage and data-quality reports; Plan s2.5 permits validating "authorized non-return information" before P1; the gap is that nothing authorizes a pull before the freeze.

### 32.1 Draft amendment text (PROPOSED -- NOT APPROVED; not applied to A1 or the Plan)

**Amendment E1 - controlled pre-freeze return-blind feasibility step.**

1. *Status and effect.* This amendment, if signed, adds one step between WP0.10 and the P0 exit gate. It authorizes **nothing by itself**: it fixes the rules under which a later, separate, signed acquisition authorization may be issued.
2. *Permitted data fields.* Only: symbol identifier, bar timestamp, bar `high`, bar `low`, bar `volume` and a bar-present flag, for bars with timestamps from 09:30:00 through 09:59:59 America/New_York on regular sessions. The fields `open` and `close` are dropped in memory at ingestion and never persisted. **No bar at or after 10:00:00 is requested, fetched or stored.** No quote, trade or news data.
3. *Permitted period and universe (proposal).* Dates within 2016-01-01..2021-12-31 only. The holdout window 2022-01-01..2025-12-31 and the exposed window 2026-01-01..2026-07-31 are **excluded** unless the owner rules in writing (under D01) that pre-entry opening-range bars from those windows are acceptable. The sampling design (symbols, dates, sample size): **NO VALUE PROPOSED**; the acquisition authorization states it.
4. *Permitted computations (the only outputs).* (a) Opening-range width = OR high minus OR low, in ticks and as a percent of the OR midpoint, reported as quantiles per year and per price band; (b) counts of minutes in 09:30-09:59 that are present, `NO_TRADE_MINUTE` or `DATA_GAP` per symbol-day class, aggregated; (c) coverage against the 98% threshold of Plan 9.3; (d) half-day calendar and tick-size band checks. Cells smaller than a stated minimum count are suppressed (minimum count: NO VALUE PROPOSED).
5. *Prohibited.* Any bar at or after 10:00:00; any post-entry price path; any breakout hit, trigger, signal, trigger frequency or crossed-before-arm share (F11 stays unstarted); any return, P&L, win rate, profit factor, MFE or MAE; any exit-candidate evaluation, selection, backtest or replay of RANGE-002 rules; any join between pulled data and trade outcomes; any per-symbol-day record exported outside the isolated environment; any agent or analyst reading raw rows (agents see only the approved summaries).
6. *Oversight.* The independent validator (SoD-C) or a person the owner designates who did not write the extraction code: reviews and signs the extraction and summary code before acquisition; confirms the acquisition matches the authorization; reviews and signs the summary release. The developer cannot release outputs.
7. *Exposure ledger.* Before acquisition, a ledger entry of kind `return_blind_feasibility_pull` is written and signed under the D01 process: dates, symbols source, fields, tool commit SHA, environment, operator, overseer, authorization reference. After release the entry records the output summary SHA-256. Pre-entry opening-range bars from any period are recorded as contact (not as outcome exposure); the D01 contact audit lists them.
8. *Environment (C12).* A named isolated non-production environment: no broker credentials, not `ec2-paper`, not the standby laptop stack, storage sized to the D03 budget, manifest-producing, network reachability established by a metadata-only check, licence for stored research use confirmed (F5), raw data not committed to git (GITHUB-OPS-001; controlled storage with a manifest if retained) and a stated retention and deletion rule.
9. *Stop conditions.* Stop and report if: any fetched row has a timestamp at or after 10:00:00; any field outside the permitted list is received and persisted; any computation yields a return-like quantity; the code review or the authorization is unsigned; the exposure-ledger entry was not written first; coverage is below 98%; the licence or the environment condition is unmet; any raw row is viewed outside the approved summaries; or the owner withdraws the authorization.
10. *Sequence.* Step 0: owner approves this policy direction. Step 1: signed approval of Amendment E1 (owner, independent validator, trading-expert reviewer). Step 2: a **separate** acquisition authorization (period, sampling design, host, operator, overseer, budget). Step 3: summary release signed by the overseer. Step 4: D05 5a and 5b are decided from the released summaries.
11. *Relationship to other documents.* Needs a Plan amendment (WP0.10 and the P0 exit gate sequence) and a statement in A1. It does not touch the results guard (no returns are computed); the extraction tool must live outside the engine and statistics packages and pass the import lint.

**Status of C-EVID.** PROVISIONAL POLICY DIRECTION -- NOT SIGNED. No acquisition is authorized. D05 5a / 5b stay PENDING.

## 33. INDIVIDUAL APPROVAL SHEETS (OWNER-READY, BLANK SIGNATURE): D04, D10, D11, D15, D16, C10

Content is the existing recommendation from the Sheets. Every proposed value is **PROPOSED -- NOT APPROVED**. Signature, date and SHA-256 fields are BLANK. Documents to pin for each: Decision Sheets v0.1 (`c7ebaf71`), Plan v0.5 (`c7ebaf71`), A1 (`c7ebaf71`), this register (commit containing the final text); SHA-256 of each: BLANK.

### 33.1 D04 - Yearly consistency gate

- **Statement.** Confirm "at least 3 of the 4 calendar years 2022-2025 with PF > 1.0".
- **Source.** Design s6 (proposed, pending approval; applies only to this holdout window); Plan G6 and s5.1A; Sheets D04.
- **Options.** (a) Confirm as designed. (b) A different count or definition. (c) Drop (not recommended).
- **Recommendation (PROPOSED -- NOT APPROVED).** (a), plus the Plan s5.1A rule that a year with too few trades for a meaningful PF is reported with its count and does not pass. The per-year minimum trade count: NO VALUE PROPOSED (owner or validator states).
- **Spec key.** `gates.yearly`. **Evidence.** None return-blind. **Blocks.** PR 12, 14.
- **Approver.** Owner. **Owner choice / value:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256 (pinned documents):** BLANK

### 33.2 D10 - Win-rate gate and drawdown comparator

- **Statement.** (i) Keep the platform win-rate > 50% gate or sign a formal deviation (win rate diagnostic only). (ii) Fix the drawdown comparator.
- **Source.** Design s6; ruling C3; Plan s5.1 G8 and the D10 alert; RNG-001 report s3.5; Sheets D10.
- **Options.** (i) Keep > 50%, or sign a deviation with or without a compensating requirement. (ii) SPY buy-and-hold; naive ORB portfolio; random-entry portfolio under identical capital, costs and sizing; the RNG-001 baseline (not comparable).
- **Recommendation (PROPOSED -- NOT APPROVED).** (i) The platform gate applies and promotion is blocked until the owner signs a deviation; both evaluations are displayed (platform gate and design diagnostic). No deviation is proposed. (ii) Random-entry portfolio under identical capital, costs, equity sampling and exposure as primary; SPY as a reported reference.
- **Spec keys.** `gates.win_rate`, `gates.max_dd`. **Evidence.** Comparator definition and equity-sampling rule only. **Blocks.** PR 12, 14, any P6 promotion.
- **Approver.** Owner. **Win-rate choice:** ________ **Deviation reason (if any):** ________ **Comparator:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 33.3 D11 - Loader approach and `data.fetch_mode`

- **Statement.** Record that ruling C5 (a new monthly-chunked, fail-closed RANGE-002 SIP loader; the shared `BarCache` is not modified) satisfies design decision 11, and record `data.fetch_mode`.
- **Source.** Design decision 11; ruling C5; Plan WP1.1 and s10 D11; recon s0 item 2 and s2.7; Sheets D11. The schema types `data.fetch_mode` as a free string; no enumeration is defined in the documents.
- **Options.** (a) New loader (ruled). (b) Fix the shared cache (touches live-box code; its own ADR review).
- **Recommendation (PROPOSED -- NOT APPROVED).** Confirm (a) satisfies decision 11. The `fetch_mode` enumeration: OWNER MUST DEFINE (no source defines it; loader requirements: explicit SIP, no IEX fallback, monthly chunks, truncation detection, idempotent resume, SHA-256 manifest, delisted coverage where licensed).
- **Spec key.** `data.fetch_mode`. **Evidence.** WP1.1 finding on `bar_cache.py` (in recon). **Blocks.** PR 5, 6, 7.
- **Approver.** Owner. **C5 satisfies decision 11 (yes/no):** ________ **`fetch_mode`:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 33.4 D15 - Cost accounting mode

- **Statement.** Decide whether the 5 bps (base) and 15 bps (stress) per side are all-in or additive to fill-price slippage, and the itemized components.
- **Source.** Design s4 cost row; Plan s2.5 and D15; Sheets D15. The 5 / 15 bps values are fixed in the schema and are not open.
- **Options.** (a) All-in debit. (b) Additive, with a separate slippage model.
- **Recommendation (PROPOSED -- NOT APPROVED).** (a) as the Plan recommends: all-in bps as a P&L debit, fills at the modeled price, no extra slippage, gap-through fills stay adverse as price events. Caveat: (b) is the more conservative base case; under (a) the conservatism rests on the 15 bps stress gate G3, which must stay binding. Components: NO VALUE PROPOSED.
- **Spec keys.** `costs.accounting_mode`, `costs.components`. **Evidence.** None return-blind. **Blocks.** PR 8, 11; couples to D05 5i.
- **Approver.** Owner. **Mode:** ________ **Components:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 33.5 D16 - Diagnosis taxonomy, shadow-run acceptance, execution-quality evidence

- **Statement.** Approve the explanatory diagnosis labels, the shadow-run acceptance rule and the minimum broker execution-quality evidence.
- **Source.** Design decision 07 and s9.2; Plan WP3.4, WP5.9-5.11; Sheets D16.
- **Options.** Adopt the labels as listed or modify; shadow run length and tolerance.
- **Recommendation (PROPOSED -- NOT APPROVED).** Adopt the eight labels (`NO_DEMONSTRATED_EDGE`, `EXECUTION_COST_DOMINATES`, `INSUFFICIENT_SAMPLE`, `REGIME_FRAGILITY`, `CAPACITY_OR_RISK_CONSTRAINT`, `DATA_OR_ENGINE_DEFECT`, `PAPER_OPERATION_FAILURE`, `UNCLASSIFIED`) as explanatory only, never an override of REJECT. Shadow acceptance: zero orphan signals, zero duplicate intents, zero look-ahead discrepancies over a number of sampled days: NO VALUE PROPOSED (owner states).
- **Spec keys.** `diagnostics.taxonomy`, `p5.shadow_acceptance`. **Evidence.** None. **Blocks.** PR 12B, 15A.
- **Approver.** Owner. **Taxonomy adopted / modified:** ________ **Sampled days:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 33.6 C10 - Custody of the authoritative design DOCX

- **Statement.** Decide where and how the authoritative design DOCX is held while the S3 manifest tooling is absent.
- **Source.** Ruling C10; `governing_reconciliation.md` C10; Sheets C10; GITHUB-OPS-001 (Office binaries go to controlled S3 with a Version ID and SHA-256 manifest).
- **Options.** (a) Wait for the manifest tooling; the DOCX stays local and untracked. (b) Owner directs an interim custody. (c) Commit a Markdown extraction now.
- **Recommendation (PROPOSED -- NOT APPROVED).** (a) plus recording the DOCX SHA-256 and version in the sign-off packet so the governing text is pinned before S3; (c) only with the owner's explicit permission for a derived, non-authoritative copy.
- **Evidence.** SHA-256 of the DOCX bytes (owner or developer computes locally). **Blocks.** Traceability of the governing document at sign-off.
- **Approver.** Owner. **Option chosen:** ________ **DOCX SHA-256:** BLANK **Version:** ________ **Signature:** BLANK **Date:** BLANK

## 34. VALIDATOR-FACING REVIEW PACKET: D06, D02, D17, D19

**Audience:** the independent validator (D08 slot; SoD-A plus SoD-C; name BLANK). **Rule:** the validator confirms, amends or rejects; the values below are **recommendations only (PROPOSED -- NOT APPROVED)** and the proposed 10,000 repetitions and alpha 0.05 stay recommendations until a signed record exists. **Data rule:** calibration is **synthetic only**: simulated series from generators the validator specifies. No RANGE-002 data, no data from the exposed windows and no real historical prices from related programs may be used for calibration without a D01 exposure-ledger entry. No agent author's output substitutes for the validator's own review.

### 34.1 D06 - bootstrap, baselines, seeds

| Item to confirm | What the validator must establish | Recommendation in the documents (NOT APPROVED) |
|---|---|---|
| Day-block length | A mean block length, in days, fixed a priori and justified without RANGE-002 data; sensitivity across a grid on synthetic series with several dependence structures | NO VALUE PROPOSED. The repo's daily-layer `BLOCK_LEN = 10` is a precedent only; confirm or replace |
| Bootstrap method | Stationary (geometric blocks) vs circular fixed-block vs iid day-clusters, over trading days | Stationary over days |
| Test statistic | The exact statistic: mean net R per trade, defined at trade level or as a day-level aggregate (ratio of sums vs mean of day means; matters when trades per day vary); the estimand for G5 (day-level pairing, days with no valid random draw counted and reported) | Mean net R per trade; G5 per Plan WP3.3 |
| Null-distribution procedure | How the null is imposed (recentering at zero for G4; recentering the paired difference for G5; the max-statistic null across K for P3a with the same resampled days applied to every candidate to preserve cross-candidate dependence) | Percentile of the recentered null |
| Repetitions | Monte Carlo precision at the chosen B. For a tail probability near 0.05 the standard error is about sqrt(p(1-p)/B); at B = 10,000 that is about 0.0022. State the precision required at the decision boundary and confirm B is adequate; check stability across B on synthetic data | At least 10,000 |
| Interval type and tail | One-sided lower bound; percentile; relation between the p-value test and the reported bound (no unadjusted interval labelled "Holm-adjusted") | One-sided percentile |
| Alpha / confidence | One-sided alpha and the matching confidence level | 0.05 |
| Seeds | One fixed seed per purpose (bootstrap, random-entry baseline, max-statistic), recorded in the spec, independent of one another, reproducibility test | NO VALUE PROPOSED |
| Random-entry baseline | Repetitions, seed, invalid-draw policy (`NOT_EXECUTABLE` counted, denominator preserved), matching on eligible symbols, window, trade count, capital and risk budget, no conditioning on future breakout | Per Plan WP2.5 / WP2.7A |
| Naive ORB, SPY reference, time-shuffle | Definitions and roles (naive ORB diagnostic unless made binding; SPY non-binding reference; time-shuffle a stage-1 control) | Per section 13.4 |

**Synthetic calibration requirements.** (1) Empirical size of the G4 test at nominal alpha under a null, for each candidate block length and several dependence structures (serial correlation in day means, volatility clustering, variable trades per day). (2) Power under planted effects the validator specifies. (3) Coverage of the lower bound. (4) Family-wise error of the max-statistic over K = 7 correlated candidates. (5) Stability of p-values across B in {1,000; 10,000; 50,000}. (6) Reproducibility under fixed seeds. Report with commit SHA and SHA-256.

**Validator sign-off (BLANK).** Block length ____; method ____; statistic ____; null procedure ____; B ____; alpha ____; seeds ____; calibration report SHA-256 ____; Name BLANK; Signature BLANK; Date BLANK.

### 34.2 D02 - hypothesis family

Confirm or amend:
1. The P4 confirmatory family is exactly {G4, G5}: G4 = mean net R > 0 with an adjusted bound; G5 = paired difference vs the random-entry baseline > 0 with an adjusted bound. Family size m = 2 under option (a) (recommended; NOT APPROVED).
2. Holm step-down at one-sided alpha 0.05: the smaller p-value is compared with alpha/2 and the other with alpha; the adjusted lower-bound quantile follows Plan WP3.3 (`1 - alpha/(m - k + 1)`). Holm controls the family-wise error under arbitrary dependence, so the positive dependence between G4 and G5 is permitted.
3. G6-G10 are gates, not hypotheses in the family; the P3a selection-aware test is separate; K is recorded in the ledger and the P4 report; no hypothesis may be added after P0.
4. Representation: `stats.adjustment = holm` and a `stats.hypothesis_family` value stating the two members and m = 2; the preset in the skeleton must be explicitly confirmed, not inherited.
5. If the validator prefers option (b) or (c), the consequences are in section 13.1.
Synthetic requirement: family-wise error and power of the two-test Holm procedure under correlated null statistics. **Sign-off (BLANK):** family confirmed ____; m ____; Name BLANK; Signature BLANK; Date BLANK.

### 34.3 D17 - P3 criteria

Confirm or amend (values from the Sheets, PROPOSED -- NOT APPROVED): P3a minimum 300 trades per eligible candidate, PF > 1.0 at base cost, selection-aware STOP test one-sided alpha 0.05 (alternatives 0.10 and 0.20); P3b = P4 thresholds with G1 scaled to two years (150 trades), single hypothesis, one-sided alpha per D06. The validator must establish: (a) the trade unit and basis (D18, signed first) so that counts mean the same in P3a, P3b and P4; (b) that 300 / 150 are proportional (75 per year) and what they imply for power; (c) the consequence of a trade-count miss under a single attempt (a terminal STOP, section 3.5 C-P3B-N); (d) the false-STOP and false-advance rates of the STOP alpha choices. Synthetic requirement: power of the P3b test at 150 trades for validator-specified effect sizes; false-advance rate of the P3a-to-P3b pipeline under the null. **Sign-off (BLANK):** P3a minimum ____; P3a PF ____; STOP alpha ____; P3b option ____; P3b minimum ____; Name BLANK; Signature BLANK; Date BLANK.

### 34.4 D19 - exit candidates and selection rule

Confirm or amend (values from Plan s2.2, PROPOSED -- NOT APPROVED): the K = 7 set (E1; E2a/b targets 2R and 3R; E3a/b breakeven at +1R then trail 1.0R or 1.5R; E4a/b 50% scale-out at +1R with the remainder to EOD or trailing 1.0R), complexity order 1 to 4, score = one-sided lower bound of mean net R per trade, tie tolerance delta (0.05 R is an illustrative placeholder with no basis in the documents), eligibility from D17, STOP test from D17. The validator must establish: (a) completeness and closure of the set (at most 8, four families, parameters in R units, no extra features); (b) the complexity order is a total, documented order; (c) delta is fixed a priori on a cost scale and its effect on selection stability; (d) the score's behaviour (lower bound penalizes variance; ties resolved deterministically); (e) `select_exit` is a pure function with fixtures for ties, ineligibility and STOP; (f) all candidates share one entry stream, are resampled on common days, and the max-statistic correction is correct; (g) the selection record is written and hashed before unsealing. Synthetic requirement: selection accuracy and selection bias under planted best candidates and under the null; sensitivity to delta. **Sign-off (BLANK):** set ____; order ____; score ____; delta ____; eligibility ____; STOP test ____; Name BLANK; Signature BLANK; Date BLANK.

## 35. SIGNING ORDER (the owner's recommended order; nothing is signed)

| Step | Items | Why this order | Gate before the step |
|---|---|---|---|
| 1 | D08 (names, SoD-A + SoD-C, attestation), C-DR (option (i) and Plan amendments), A1 (after the reconciliation memo and independent methodology review), P5 option B (and the schema PR), C-EVID policy and Amendment E1 | Policy choices and amendments that define the rest; roles are needed for every later reviewer | none; but A1 only after section 29 is complete |
| 2 | D06 validator bootstrap specification and synthetic calibration | Everything statistical depends on it | step 1 roles; validator attested |
| 3 | D02 | Depends on D06 | step 2 signed |
| 4 | D18, D17, D19 | D17 depends on D18 and D06; D19 eligibility uses D17 | steps 2 and 3 |
| 5 | D04, D10, D11, D15, D16, C10 | Ready decisions with complete documented evidence (sheets in section 33) | none beyond step 1 roles |
| 6 | D01, D03, D05, D09, D12, D13, D14 | Need audits, feasibility, F1/F2/F5/F3/F4, the C-EVID summaries (D05 5a/5b), the human-written thesis and C2 inputs | evidence listed in section 10 |
| 7 | Genesis registration and freeze readiness | Enrollment needs location, host, operator, witness and written authorization; the manifest change; spec draft; SHA-256 pins; safeguard merged | steps 1-6; `freeze_spec` last |

## 36. REMAINING OWNER SIGNATURES AND EXACT AUTHORIZATION REQUESTS

No signed record exists. The following are **requests to the owner**, not actions taken.

### 36.1 Signatures still needed (all BLANK)

A1 (three rows); D01-D19 (one record each); C2 overlap and reviewers; D09-hist; C10; C12; D08 roles and SoD selection; C-DR; P5 option B; C-EVID Amendment E1; M-loc, M-ops and authorization to enroll; the two attempt limits; the genesis triple (after enrollment only); the validator attestation; the validator sign-offs in section 34.

### 36.2 Exact authorization requests

1. **AR-1 (D08).** "Authorize the preparer to circulate for signature the D08 record naming the four role slots, with SoD-A plus SoD-C selected. Provide the four names and the engineer list."
2. **AR-2 (C-DR).** "Sign C-DR option (i): no automatic defect-only reruns; one authorized P3a attempt and one authorized P3b attempt; no attempt limit above 1. Authorize drafting of the Plan amendments of section 28 as an edit for review (not applied until you instruct)."
3. **AR-3 (A1).** "Authorize preparation of the A1 / v0.4 / merged-schema reconciliation memo (section 29.1) and commission the independent review of the exit-selection methodology (section 29.2). Do not collect A1 signatures until both exist."
4. **AR-4 (P5).** "Authorize an implementation PR for option B (section 31), to be reviewed and merged before any real freeze. Confirm the permitted marker value text."
5. **AR-5 (C-EVID).** "Approve in principle the controlled pre-freeze feasibility amendment E1 (section 32), step 1 only. A separate acquisition authorization will be requested later and is not requested now."
6. **AR-6 (safeguard).** "State whether PR #740 (commit `8792e043`) is to be merged, and when."
7. **AR-7 (genesis).** "Provide: host, registry path, operator, witness, and a separate written authorization to enroll. Not requested to be executed now."
8. **AR-8 (validator packet).** "Name the independent validator and authorize delivery of the section 34 packet."
9. **AR-9 (ready decisions).** "Review the section 33 sheets for D04, D10, D11, D15, D16 and C10 and sign, amend or reject each."

## 37. REFRESHED BLOCKER STATUS AND GO / NO-GO (supersedes sections 16, 17 and 26 where different)

1. Names and attestation for the four role slots (BLANK); the engineer list.
2. C-DR option (i) signed and Plan amendments approved for application.
3. A1 reconciliation memo and independent methodology review completed; then A1 considered.
4. P5 option B and the C-EVID amendment E1 approved; the P5 schema PR implemented, reviewed and merged before any freeze.
5. D06 validator specification and synthetic calibration; D02; D18, D17, D19.
6. D04, D10, D11, D15, D16, C10 (sheets ready).
7. D01, D03, D05 (after Amendment E1 summaries), D09, D12, D13, D14.
8. Genesis: still unenrolled; host, path, operator, witness and authorization pending; manifest change after enrollment.
9. Spec draft, SHA-256 pins, safeguard merged, real freeze, P0 exit, P1.

**Recommendation: NO-GO.** No decision is approved (0), the manifest is unset, no registry is enrolled, no independent validator is named or attested, no methodology review exists, and the P5 schema change, Plan amendments and Amendment E1 are unapproved proposals.

---

# PART V - OWNER RULINGS AR-1 TO AR-9 AS PROPOSED POLICY AND DRAFTING DIRECTION (NOTHING SIGNED)

These rulings are **technical direction for drafting**, not signatures. Every item remains **PROPOSED -- NOT APPROVED** until a signed record exists against pinned SHA-256 hashes. Values were re-verified against the sources named in each section; where no document gives a value the text says **NO VALUE PROPOSED**. No data, provider, broker, enrollment or freeze was involved.

## 38. RULINGS RECEIVED AND HOW THEY ARE RECORDED

| Ruling | Owner direction | Recorded as | Where |
|---|---|---|---|
| AR-1 | Adopt SoD-A + SoD-C as proposed policy; names stay blank | PROPOSED POLICY (not a signed record). Names, attestations and the engineer list remain BLANK | s27, s43 |
| AR-2 | Recommend C-DR option (i), limits 1/1, no automatic defect-only retry. The Plan amendment must say plainly that recovery is unavailable without a separately designed and approved mechanism, that an owner authorization alone cannot reset the attempt budget, and state the consequence of an unrecoverable defect | PROPOSED Plan wording (final form in s39); not applied | s39 |
| AR-3 | Proceed with the A1 P3a / P3b architecture; finish the written A1 vs v0.4 vs merged-schema reconciliation memo and the independent-methodology-review requirements; no signature before both | DRAFT memo and requirements; A1 stays unsigned | s40, s41 |
| AR-4 | Prepare P5 option B amendment text (implementation is Workstream C) | PROPOSED amendment text; nothing implemented | s42 |
| AR-5 | Draft the pre-freeze return-blind feasibility amendment: E1 step 1 only, no acquisition authorization | DRAFT (s32 text, restated as a step-1 approval record) | s44 |
| AR-6, AR-7 | Deferred | Merge of the distinct-role safeguard and genesis enrollment stay pending | s45 |
| AR-8 | Independent validator required before formal P0 approval | Name and attestation BLANK | s43 |
| AR-9 | Prepare six individual owner-review sheets: D04, D10, D11, D15, D16, C10 | Sheets with verified values and the owner-stated open items | s46 |

## 39. C-DR - FINAL PROPOSED PLAN WORDING (AR-2) (PROPOSED -- NOT APPLIED)

This section supersedes the wording tables of s20.3 and s28 where it differs. It states, in plain terms:
1. there is **no automatic defect-only rerun**;
2. there is exactly **one authorized P3a attempt and one authorized P3b attempt** per research lineage, consumed when authorization is issued (`capability_issued`), across all spec versions and windows;
3. **recovery is unavailable** unless a recovery mechanism has been **separately designed, implemented and approved**; no such mechanism exists (design-only, Level 2);
4. **an owner authorization alone cannot reset the attempt budget**: the merged code has no reset parameter, and an attempted `budget_reset_authorization` argument is refused by name; editing the committed manifest to a higher limit is a process control that this policy forbids for the purpose of a retry;
5. the **consequence of an unrecoverable defect**: the affected phase is permanently ended for the lineage.

| Plan location (v0.5 line) | PROPOSED replacement text (NOT APPLIED) |
|---|---|
| s0 R3 (101), second sentence | "There is no automatic defect-only rerun. P3a and P3b each have exactly one authorized attempt per research lineage, consumed when the authorization is issued, across all spec versions and windows, and the holdout window is consumed when it is authorized. Recovery is unavailable unless a recovery mechanism has been separately designed, implemented and approved; an owner authorization alone cannot reset or restore an attempt budget. A technical defect after authorization is unrecoverable under the current implementation and permanently ends that phase for the lineage." |
| WP4.0 step 2 (584), last sentence | "The run is closed `INCONCLUSIVE_ENGINE` and its attempt stays consumed. No rerun is available. The defect is documented, and the phase is ended for the lineage unless a separately designed and approved recovery mechanism exists." |
| WP4.1 (606), defect-only bullet | "**No defect-only reruns.** One authorized P3a attempt and one authorized P3b attempt per lineage. Recovery is unavailable without a separately designed and approved mechanism, and an owner authorization alone cannot reset the attempt budget. If a technical defect occurs after authorization, the phase is permanently ended: P3b (after a P3a failure) and P4 cannot run for this lineage, the program verdict is recorded as `INCONCLUSIVE_TECHNICAL`, and continuation requires a new, independently approved research registration with all prior exposure inherited and recorded. A defect record (symptom, root cause, fix commit, why the fix does not encode knowledge of results) is still written for the permanent record." |
| WP4.1 (605) and A1 s3 | Add: "The P3a and P3b attempts are single and non-recoverable under the current implementation." |
| s5.2 (698) | "`INCONCLUSIVE` is not a soft pass. No repair-and-retest mechanism is implemented. A retest needs a separately designed, approved and implemented recovery mechanism, or a new owner-approved registration with inherited exposure." |
| s6 step 6 (710) | Add: "If `capability_issued` was written, the run also consumes the attempt, and with a limit of 1 this ends the phase for the lineage." |
| s11.1 table (848) | "Document the defect; no rerun is available unless a separately designed and approved recovery mechanism exists" |
| WP0.7 | Add: "attempt limits P3a = 1 and P3b = 1 (governance manifest); P4 is limited by the holdout once-per-window rule" |
| New R19 | "R19. Attempt-limit notice: a technical failure after authorization is unrecoverable and may permanently end a phase. Do not authorize a P3 or P4 run until engine validation on synthetic fixtures and `REPLAY_RNG001` (never citable) is complete and the full required-test manifest passes on the code state to be used." |

Caveat on the "new registration" route, stated for the owner: a new lineage means a new genesis and a new registry, whose rows do not contain the earlier lineage's holdout consumption. The code therefore cannot carry the earlier consumption forward; the exposure ledger and the independent approval and exposure review must carry it. This is why the continuation route is a governance decision and not an operational one.

## 40. A1 vs v0.4 vs MERGED SCHEMA - WRITTEN RECONCILIATION MEMO (DRAFT; AR-3)

| Field | Value |
|---|---|
| Title | A1 / design v0.4 / merged-schema reconciliation memo |
| Status | **DRAFT. Not reviewed, not signed.** A1 is not to be signed before this memo and the section 41 review both exist |
| Prepared by | the preparer (an AI-assisted draft; it holds no role). Reviewer and owner rows are BLANK |
| Sources | A1 (`c7ebaf71`); Plan v0.5 (`c7ebaf71`); Sheets v0.1; `governing_reconciliation.md`; design v0.4 **only as quoted in those documents** (the DOCX is not in the repository, ruling C10); merged code at `d61f313a` |
| Data accessed | None |

### 40.1 Purpose and authority

A1 amends design v0.4 and is not in force until signed; until then v0.4 governs unchanged, including the fixed A/B exits (A1 header). The Plan header says to build the schema so it supports the A1 candidate set but not to freeze under either form. This memo records, in writing, what that arrangement means for the merged code, and what is required before A1 is submitted.

### 40.2 Side-by-side comparison

| Topic | Design v0.4 (as quoted in A1, Plan, Sheets) | A1 | Merged code (`d61f313a`) |
|---|---|---|---|
| Exit rule | s3.1: variant A (time exit, primary) and variant B (2R target, secondary), fixed | Amendment 1: closed set of at most 8 configurations from four families; frozen selection rule; no addition after P0 | `Exits`: 1..8 candidates, four families, `selection` block required |
| P3 structure | s7: one 2016-2021 development run against "pre-approved development-period criteria" (none given) | Amendment 2: P3a 2016-01-01..2019-12-31 (all K, selection) and P3b 2020-01-01..2021-12-31 (selected exit, confirmation) | Partitions locked by equality validators; phases `P3A` / `P3B`; verdict `EXIT_SELECTED` |
| Holdout | 2022-2025, opened once | Unchanged | Locked; one opening per window in the registry |
| Exposed data | 2026-01..07 exposed | Unchanged | `partitions.exposed` locked |
| Hypothesis family | Decision 02: A primary, B secondary, Holm | Amendment 3: exit-configuration count 1; hypothesis count is the D02 owner value | `stats.adjustment` in {holm, fixed_sequence}; `hypothesis_family` open |
| Decision list | s10.2: decisions 01-12 | D01-D19 | spec keys per decision (s14) |
| Gates G0-G10 | s6 | Unchanged | thresholds locked by equality validators |
| Verdict states | s6.1 | Plus `EXIT_SELECTED` | `verdict.py` |
| Sample-size criteria | s7 gap | D17 adds P3a / P3b criteria | `p3.criteria` open |
| Attempt budgeting | not in the quoted v0.4 text | not stated in A1 | manifest `p3_attempt_limits` (p3a, p3b); consumption at `capability_issued` |
| Plan precedence | v0.4 + A1 wins | "Until signed, v0.4 governs" | no v0.4 form can be frozen |

### 40.3 Findings

1. **Tooling asymmetry.** "v0.4 governs until A1 is signed" cannot be exercised: the merged tooling expresses only the A1 form (inventory in s23.2).
2. **Fallback cost.** A v0.4 single P3 or fixed A/B form needs changes across schema, manifest, models, guard, registry, verdicts, adapters, freeze tool, tests and the required-test manifest (s23.3).
3. **Methodology, not code, must justify A1.** Existing code is not evidence that the selection design is sound; that is the subject of the independent review (s41).
4. **Attempt policy.** A1 leaves attempt counts unstated; the owner direction is 1 / 1 with no recoverable defect (s39). A1 s3 should say so.
5. **P3b power.** P3b is half the sample of the design's single run; D17 must state the P3b trade minimum and its consequence under a single attempt (C-P3B-N).
6. **Wording items** already listed in Sheets s5 (D13-D16 treatment, D01-D19 numbering, hypothesis-family wording, A1 s7 D11 wording) are to be settled in the same edit.

### 40.4 Required conditions before A1 is submitted for signature

(a) This memo reviewed by the owner and the independent validator; (b) the section 41 methodology review completed with a written conclusion; (c) the s39 C-DR wording and the s42 P5 wording incorporated or consciously deferred; (d) A1 s3 amended to state the single, non-recoverable attempts; (e) the Plan header updated to say the infrastructure is built to A1.

### 40.5 Decision requested

The owner chooses: proceed with A1 as amended; amend further; or fall back to v0.4 with the cost in 40.3 item 2. Recommendation (not a decision): proceed with the A1 architecture, subject to 40.4.

### 40.6 Signature block (BLANK)

| Role | Name | Conclusion | Signature | Date |
|---|---|---|---|---|
| Memo author | BLANK | n/a | BLANK | BLANK |
| Independent validator | BLANK | | BLANK | BLANK |
| Owner | BLANK | | BLANK | BLANK |

## 41. INDEPENDENT REVIEW OF THE EXIT-SELECTION METHODOLOGY - REQUIREMENTS (AR-3) (PROPOSED)

1. **Reviewer.** The independent validator under SoD-A + SoD-C: not the owner, the trading expert or the research lead; not an author of the engine, spec, selection or gate code; no exposure to any RANGE-002 result. Independent attestation filed first (s43). Name BLANK.
2. **Inputs given to the reviewer.** A1, Plan s2.2 / WP3 / WP4.1, the D06, D17, D18 and D19 sheets, the schema description, this memo. No RANGE-002 data and no outputs of related programs on 2016-2025 intraday data.
3. **Scope.** (a) Selection score (one-sided lower bound of mean net R per trade) and the choice of estimand; (b) eligibility (trade minimum, PF at base cost); (c) tie tolerance delta and the complexity order; (d) the selection-aware max-statistic test over K, including resampling of common days across candidates; (e) the sealed protocol (selection record hashed before unsealing; R18); (f) the sequential use of data across P3a, P3b and P4 and the resulting error rates; (g) completeness and closure of the candidate set; (h) behaviour under a single attempt (a failed run cannot be repeated).
4. **Required evidence (synthetic only).** Pipeline size under the null with correlated candidates (K = 7) and variable trades per day; power and selection accuracy under validator-specified planted edges; optimism of the selected candidate's P3a score relative to P3b; sensitivity to delta, block length, repetitions and STOP alpha; determinism under fixed seeds; tie fixtures. Real market data may not be used without a D01 ledger entry.
5. **Deliverables.** A written report with a clear conclusion (adequate / adequate with amendments / inadequate), the calibration outputs, the commit SHA and SHA-256 of the code and report, the conflicts statement, and a list of required amendments to A1 or D17 / D19 / D06 values.
6. **Acceptance criteria for proceeding to A1 signature.** A written "adequate" or "adequate with amendments" conclusion with the amendments made; no unresolved finding about leakage between P3a, P3b and P4; the pipeline's null false-advance rate stated and accepted by the owner.
7. **Sign-off (BLANK).** Reviewer ____; conclusion ____; report SHA-256 BLANK; signature BLANK; date BLANK.

## 42. P5 OPTION B - AMENDMENT TEXT (AR-4) (PROPOSED -- NOT APPLIED; implementation is Workstream C)

This section prepares document wording only. The schema, tests and later guard changes of s31 are Workstream C and are not done here.

| Document and location | Current text | PROPOSED text |
|---|---|---|
| Plan App. A, line 1000 | "`account_id: null  # D07 policy at P0; the ID is recorded in the P5 execution manifest (WP5.1) unless the owner rules otherwise`" | "`account_binding: null  # P0: D07; the only permitted value is the deferral marker; the account id is not part of the frozen spec and is bound by a separate P5 activation record to the same spec_sha256`" |
| Plan s10 D07 (line 811) | "...(the account ID cannot exist before WP5.1 unless the owner rules otherwise)..." | "...the account policy is frozen at P0 and the account id is bound later by the P5 activation record; the frozen spec carries the hashed deferral marker `p5.account_binding`" |
| Plan WP5.1 (line 622) | "The account ID is recorded in the signed execution manifest." | "The account ID is recorded in the signed P5 activation record, which names the frozen `spec_sha256`, the genesis id, the completed P4 run and the owner's approval; one activation per lineage; no rebinding." |
| A1 s4, D07 row | "Unchanged (v0.4 decision 07)" | Add: "D07 refined: the spec carries the hashed deferral marker; the account id is bound later without changing `spec_sha256`." |
| Sheets D07 and s5 item 4 | "Inconsistency: App. A makes `p5.account_id` a P0 value but WP5.1 provisions it in P5" | Mark resolved by option B once approved |
| Spec key list (s14, row `p5.account_id`) | `p5.account_id`, owner D07 | `p5.account_binding`, owner D07 |

Schema, `freeze_spec`, hash, activation-record and guard specifics: s31. The marker's exact permitted value text is for the owner to confirm.

## 43. D08 - SoD-A + SoD-C AS PROPOSED POLICY (AR-1, AR-8) (PROPOSED POLICY -- NOT A SIGNED RECORD)

Adopted as the proposed policy for the D08 record: SoD-A for the three signers, plus SoD-C's validator-independence requirements (the validator is also distinct from the research lead and from whoever wrote the engine), with the procedural confirmations of s15.4 and the Workstream B document of s15.5. The all-pairs safeguard (PR #740, `8792e043`) is consistent with the policy and does not permit owner == trading_expert. Its merge is deferred (AR-6).

An **independent validator is required before formal P0 approval** (AR-8). Identity, attestation and engineer list: BLANK. No AI agent holds a slot.

| Slot | Name | Attestation | Signature | Date |
|---|---|---|---|---|
| Research lead | BLANK | n/a | BLANK | BLANK |
| Trading-expert reviewer | BLANK | BLANK | BLANK | BLANK |
| Independent validator | BLANK | BLANK | BLANK | BLANK |
| Sole P6 approver | BLANK | n/a | BLANK | BLANK |

## 44. E1 STEP 1 - APPROVAL RECORD ONLY (AR-5) (DRAFT; NO ACQUISITION AUTHORIZATION)

The text of Amendment E1 is in s32.1. This section restates what the owner would sign at **step 1 only**: approval of the permitted data fields, the permitted and prohibited computations, independent oversight, exposure logging, the isolated-environment requirements and the stop conditions. It does **not** authorize any acquisition, name a period or symbol set, name a host, or release any data. A **separate, later** acquisition authorization (period, sampling design, host, operator, overseer, budget) would be requested separately and is **not requested now**. D05 5a and 5b stay PENDING.

| Record | Content |
|---|---|
| Decision | Approve Amendment E1 step 1 (rules only; no acquisition) |
| Value | BLANK |
| Evidence | s32.1 text; Plan R1, s2.5 and WP0.10 (return-blind feasibility already permitted in principle); C12 requirements |
| Approvers | Owner; independent validator; trading-expert reviewer |
| Pinned documents | this register (commit containing the final text); Plan v0.5 (`c7ebaf71`); A1 (`c7ebaf71`); SHA-256 BLANK |
| Signatures / dates | BLANK |

## 45. DEFERRED ITEMS (AR-6, AR-7)

Merge of the distinct-role safeguard (PR #740) and the genesis enrollment ceremony are deferred. The registry stays unenrolled; the manifest stays entirely unset; host, registry path, operator, witness and written authorization are BLANK.

## 46. INDIVIDUAL OWNER-REVIEW SHEETS (AR-9): D04, D10, D11, D15, D16, C10

Technical direction for drafting; **not signatures**. "Verified against" names the sources checked in this session. Where the sources give no value, the sheet says NO VALUE PROPOSED and lists the item as an open owner item. Documents to pin for every sheet (SHA-256 BLANK): Decision Sheets v0.1, Plan v0.5, A1 (all `c7ebaf71`) and this register (commit containing the final text).

### 46.1 D04 - Yearly consistency

- **Direction.** Confirm the yearly-consistency gate as designed.
- **Verified against.** Plan line 661 (G6): "Yearly consistency | >= 3 of 4 calendar years with profit factor > 1.0 | Proposed (D04)"; line 808 (D04, spec key `gates.yearly`, "if 2022-2025 is used"); Plan s5.1A ("when a calendar year has too few trades for meaningful PF, report its count and the P0-specified validity rule; do not count undefined years as passing"); Sheets D04 (design s6 "proposed, pending approval"; applies only to this holdout window; a changed window needs a new yearly gate). The values 3 of 4 and PF > 1.0 are the design's proposal, PROPOSED -- NOT APPROVED.
- **Open owner item.** The minimum number of trades per year for a meaningful PF: **NO VALUE PROPOSED** in any document. Any per-year trigger-frequency expectation is return-derived and stays inside the results guard.
- **Evidence / dependencies.** None return-blind. Blocks PR 12, 14.
- **Approver.** Owner. **Choice and minimum trades per year:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 46.2 D10 - Win-rate gate and drawdown comparator

- **Direction.** Keep the platform win-rate > 50% gate absent a signed deviation; both evaluations displayed.
- **Verified against.** Plan s5.1 table row "Win rate: Platform > 50% gate applies until a formal D10 deviation is signed; display both evaluations" and the D10 governance alert (platform formal gate: trades > 100, PF > 1.2, win rate > 50%, drawdown no worse than baseline, positive expectancy, bootstrap CI > 0); ruling C3; G8 row ("comparator, equity sampling and account sizing require D10 sign-off"); s5.1A ("identical capital, costs, equity sampling and exposure"); Sheets D10. Schema: `gates.win_rate` mandatory without a default, `gates.max_dd` open.
- **Proposed (NOT APPROVED).** No deviation. Comparator proposal in the Sheets: random-entry portfolio under identical capital, costs, equity sampling and exposure as primary, SPY buy-and-hold as reported reference.
- **Open owner items (NO VALUE PROPOSED).** The exact comparator definition and the equity-sampling definition (sampling frequency and mark basis); account sizing for the comparator.
- **Evidence / dependencies.** Definitions only; no return-bearing evidence. Blocks PR 12, 14 and any P6 promotion.
- **Approver.** Owner. **Win-rate: keep >50% gate (default) / deviation with reason:** ________ **Comparator:** ________ **Equity sampling:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 46.3 D11 - Dedicated monthly fail-closed SIP loader

- **Direction.** Record that ruling C5 (dedicated RANGE-002 monthly-chunked, fail-closed SIP loader; no change to the shared `BarCache`) satisfies design decision 11.
- **Verified against.** `governing_reconciliation.md` C5 (loader attributes: explicit SIP, monthly chunks, pagination and truncation detection, completeness checks, idempotent resume, manifests, delisted coverage); Plan WP1.1 (written ADR 0033 finding; test: a simulated 10,000-row page triggers continuation or failure), WP1.2 (loader runs only in the approved isolated environment, C12; feed asserted `sip`; `data_manifest.json` with per-file SHA-256), WP1.3 (history to 2016-01-01 and delisted coverage, else stop), WP1.8 (coverage >= 98%), R6 (no silent IEX fallback); Plan line 815 (D11); schema `data.fetch_mode: str | None`.
- **Finding to flag.** The Sheets D11 say the `fetch_mode` enumeration string "is defined in PR 2". The merged schema defines **no** enumeration (a free string, null in the skeleton); the test fixture uses a synthetic placeholder only. The enumeration is therefore **undefined in every source**.
- **Open owner items.** (1) The `data.fetch_mode` value and its allowed vocabulary: **OWNER MUST DEFINE** (no document or schema defines it). This register proposes no value. Agent C's batch proposal s4.3 offers, as a proposal only and not in the schema candidate, the single value `monthly_chunked_sip` (or, as an alternative, two values that split research and broker custody); `bar_cache` and `auto` are never valid. Any enumeration needs the owner's approval. (2) Prerequisites to record before the loader is built: C12 environment named; D03 vendor, licence and budget; F1 (history), F2 (delisted), F5 (licence for stored research use), F6 (pagination and rate limits); P0 exit before PR 5. The WP1.1 finding already exists in `recon.md`.
- **Approver.** Owner. **C5 satisfies decision 11 (yes/no):** ________ **`fetch_mode` value / vocabulary:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 46.4 D15 - All-in cost accounting with binding stress test

- **Direction.** All-in cost accounting; stress testing remains binding.
- **Verified against.** Plan s2.5 (decide before returns whether 5 / 15 bps per side is all-in or additive; if all-in, do not add spread or slippage again), Plan s10.1 D15 (recommended: all-in bps applied as a P&L debit, fills at the modeled price, no extra slippage; gap-through fills stay adverse because they are price events), G3 (mean net return > 0 at 15 bps per side); Sheets D15. Schema: `costs.base_bps_per_side = 5` and `stress_bps_per_side = 15` locked; `accounting_mode` in {all_in, itemized_additive}; `components` open.
- **Proposed (NOT APPROVED).** `accounting_mode = all_in`; G3 binding. Caveat recorded in the Sheets: the itemized-additive mode is the more conservative base case, so under all-in the conservatism rests on G3 and adverse gap fills.
- **Open owner item.** Component definitions for `costs.components` (design s4 requires itemizing spread, commission and fees, impact and slippage so nothing is duplicated or omitted): **NO VALUE PROPOSED**; the cost bridge must label price adjustments versus P&L debits.
- **Evidence / dependencies.** None return-blind. Couples to D05 5i (no separate slippage model if all-in). Blocks PR 8, 11.
- **Approver.** Owner. **Mode:** ________ **Components:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 46.5 D16 - Diagnostic labels

- **Direction.** Diagnostic labels cannot override rejection.
- **Verified against.** Plan WP3.4: "A label is explanatory, not a license to override REJECT"; the eight labels `NO_DEMONSTRATED_EDGE`, `EXECUTION_COST_DOMINATES`, `INSUFFICIENT_SAMPLE`, `REGIME_FRAGILITY`, `CAPACITY_OR_RISK_CONSTRAINT`, `DATA_OR_ENGINE_DEFECT`, `PAPER_OPERATION_FAILURE`, `UNCLASSIFIED`; WP5.9 (shadow run: "Compare timestamps, active signal set and predicted order payloads against deterministic historical replay for sampled days"; "no orphan signals, duplicate intents, or look-ahead discrepancies"; "an operational dry-run, not an extra profitability screen"), WP5.10, WP5.11; line 830 (D16 spec keys); Sheets D16. The fixed `p5.min_days = 60` and `p5.min_trades = 100` are P5 minimums and are separate from the shadow run.
- **Proposed (NOT APPROVED).** Adopt the eight labels as explanatory only.
- **Open owner item.** The shadow-validation sample duration (number of sampled days, and which days): **NO VALUE PROPOSED** in any document.
- **Evidence / dependencies.** None. Blocks PR 12B, 15A.
- **Approver.** Owner. **Taxonomy adopted / modified:** ________ **Shadow sample duration:** ________ **Signature:** BLANK **Date:** BLANK **SHA-256:** BLANK

### 46.6 C10 - Design DOCX custody

- **Direction.** Pin the design DOCX by version and SHA-256.
- **Verified against.** Ruling C10 and `governing_reconciliation.md` C10 (authoritative DOCX in controlled S3 with a versioned SHA-256 manifest; non-authoritative Markdown extraction allowed; not done because the S3 manifest tooling `manifests/s3/` and its scripts are not in the repository and the policy forbids a hand-rolled scheme; the DOCX remains local and untracked); A1 s7 and Plan P0 exit gate (the sign-off packet pins the SHA-256 of the design DOCX and every signed document); CLAUDE.md / GITHUB-OPS-001 (Office binaries in controlled S3, pinned by Version ID and SHA-256, never unpinned).
- **Proposed (NOT APPROVED).** Record the DOCX version and SHA-256 in the sign-off packet now; keep the DOCX where it is until the manifest tooling exists; a derived Markdown copy only with the owner's explicit permission.
- **Open owner items (NO VALUE PROPOSED).** Custody location and retention period; who holds the file; whether a derived Markdown copy is permitted.
- **Approver.** Owner. **Version:** ________ **SHA-256 of the DOCX bytes:** BLANK **Custody / retention:** ________ **Signature:** BLANK **Date:** BLANK

## 47. REMAINING BLANKS AND OPEN ITEMS

### 47.1 Remaining blanks (nothing in this package fills them)

- All signatures and dates for A1 (3 rows), D01-D19, C2 overlap and reviewers, D09-hist, C10, C12, D08 roles and SoD selection, C-DR, P5 option B, E1 step 1, registry location, operator and witness, enrollment authorization, the two attempt limits and the genesis triple.
- Names: research lead, trading-expert reviewer, independent validator, sole P6 approver; the validator attestation; the engineer list.
- All SHA-256 pin fields and the commit SHA of the final register text.
- The independent methodology review report and the A1 memo review.
- The validator sign-offs of s34.
- Genesis id, registry path, host: nothing exists.

### 47.2 Open items

1. Plan and A1 amendments (s39, s40.4, s42) are drafts, not applied.
2. Per-year minimum trades (D04); comparator and equity-sampling definitions (D10); `fetch_mode` vocabulary and prerequisites (D11, with the finding that no source defines it); cost components (D15); shadow sample duration (D16); DOCX custody and retention (C10).
3. C-EVID: E1 step 1 not approved; no acquisition authorization exists, so D05 5a / 5b are undecided.
4. C-P5 implementation (Workstream C) must merge before any real freeze.
5. D06 specification and synthetic calibration; D02; D18, D17, D19; D01, D03, D05, D09, D12, D13, D14.
6. C-P3B-N: trade-minimum feasibility under a single attempt.
7. The safeguard (PR #740) merge and the Workstream B items (F1 control-character stripping, test-id manifest) are deferred.
8. Genesis enrollment and the manifest change are deferred.

**Final recommendation: NO-GO.** No decision is approved (0).

---

# PART VI - RECONCILIATION, CANDIDATE SCHEMA CROSS-CHECK AND SIGN-OFF REQUIREMENTS

Nothing in Part VI is a decision or a signature. All items are **PROPOSED -- NOT APPROVED**; every signature, name and SHA-256 field stays BLANK.

## 48. INTERNAL RECONCILIATION OF THE REGISTER AGAINST THE PROPOSED RULINGS

The register grew in layers. This table records, for each ruling, the sections that state it, which controls, and the corrections made in this commit (inline "Superseded in part" notes). No contradiction was left between the controlling sections.

| Ruling | Sections that mention it | Controlling section | Reconciliation result |
|---|---|---|---|
| D08 | s1.2 rows D08 and D08-SoD, s10 D08 block, s15, s18, s27, s43 | s27 / s43 | Earlier text recommended "SoD-A target, SoD-C minimum" and discussed SoD-B. The proposed policy is SoD-A + SoD-C; SoD-B removed. Inline notes added to s15.3 and s18.2. Names, attestations and the engineer list are BLANK everywhere |
| C-DR | s3.3, s3.5, s12, s20, s28, s39 | s39 | s20.3 and s28 wording tables are superseded by s39 (recovery unavailable without a separately designed, implemented and approved mechanism; an owner authorization alone cannot reset the budget; an unrecoverable defect permanently ends the phase). Inline note added to s20.3. The limits 1 / 1 are consistent throughout |
| A1 | s1.2 row A1, s10 A1 block, s23, s29, s40, s41 | s40 / s41 | Consistent: proceed with the P3a / P3b architecture; no signature before the reconciliation memo and the independent methodology review exist |
| P5 | s1.2 row D07, s10 D07 block, s14, s22, s31, s42 | s31 / s42 | `p5.account_id` conflict has a proposed resolution on paper: option B (PROPOSED / NOT APPROVED; owner direction, unsigned). Inline notes added to s14 and s22. The local schema candidate (reviewed, fix commit 76730911; the original `5bc2b493` is superseded by it) implements option B for review only and is not merged. The D07 text in s10 still cites the old conflict as history |
| E1 | s24, s32, s44 | s44 (step 1 only) | Consistent: Amendment E1 step 1 approves rules only; no acquisition authorization is requested or exists; D05 5a / 5b stay undecided |
| Genesis | s2, s21, s30, s45 | s45 | Unenrolled everywhere; no id exists |
| Go / no-go | s17, s26, s37, s47 | s50 | NO-GO throughout; 0 decisions approved |
| D11 | s1.2, s10 D11, s33.3, s46.3 | s46.3 | Corrected in this commit: the `data.fetch_mode` enumeration is **owner must define** (no source defines it) |

## 49. READ-ONLY CROSS-CHECK OF THE AGENT C SCHEMA CANDIDATE `5bc2b493`

Source: local commit `5bc2b493` on `feat/range002-schema-batch` ("local candidate", not pushed, not approved), its schema diff and its review checklist, read with `git show` only. Nothing was changed. **Update:** Agent C's later independent review produced fix commit `76730911` (branch `feat/range002-schema-batch`) and docs commit `9574d484` (branch `docs/range002-p1-p2-backlog`, read-only here). Where this section and those commits differ, the later commits control: the per-candidate `rank` was withdrawn, and the OD mappings were corrected as stated below.

### 49.1 Consistent with the register

- Marker literal `deferred_to_p5_activation` and the field name `p5.account_binding` replace `p5.account_id`, as in s31 / s42; the candidate cites "register section 22".
- Hash scope unchanged (`hashable_payload` pops only `signoff`); `freeze_spec` and `governance/` unchanged; the new keys enter the hash (matches s31.3). No real spec has been frozen and the manifest is unset, so no migration is needed (matches the register).
- Gate and design thresholds are not loosened (`coverage_min` may only confirm 0.98; `Stage1Criteria.on_fail` fixed to `INCONCLUSIVE_ENGINE`, matching Plan WP4.0).
- The closed exit-parameter vocabulary (`time {}`, `fixed_r {k_r}`, `trailing {trail_r}`, `scale_out {remainder eod | trail (+ trail_r)}`) matches the Plan s2.2 candidate rules; the +1R activation and the 50% scale quantity are plan-fixed, not parameters.
- The checklist itself says the Plan Appendix A, decision sheet D07 and the register section 22 / Record C-P5 need matching wording in a docs change; s42 supplies that wording.

### 49.2 Findings requiring owner attention

1. **Mandatory-field count changes.** The candidate adds **20 owner-valued new leaf paths** and replaces `p5.account_id` with `p5.account_binding` (the per-candidate `rank` was withdrawn and is not counted). After it merges, the P0 fields the freeze tool requires are no longer the 66 listed in s4.5 / s14 (arithmetic: 66 - 1 + 1 + 20 = 86, to be re-verified on the merged schema). Section 49.3 maps every new path to an owning decision so nothing is unowned. Two fixed, non-owner members (`stage1_criteria.invariants`, `.on_fail`) are not owner values.
2. **Within-family tie-break (escalated, unset).** Plan s2.2 orders complexity by **family** (E1 = 1, E2a / E2b = 2, E3a / E3b = 3, E4a / E4b = 4). The first candidate draft added a unique per-candidate `rank`; that was **withdrawn** after review, because it would silently add a within-family tie-break rule. Complexity stays family-level (`exits.complexity_order`). The within-family tie-break (for example E2a vs E2b) is therefore an **unset owner-approval item at D19**; the options named in Agent C's proposal are an unresolved tie is `INCONCLUSIVE`, first in candidate-list order, or smaller parameter. No option is selected here. Fail-closed requirement: `select_exit` must refuse an unresolved within-family tie. The independent validator reviews it (s34.4).
3. **Name clash: "adjustment".** `data.adjustment` is the corporate-action price basis (Plan WP1.6), whereas the "adjustment" in the A1 D06 row and `stats.adjustment` mean multiplicity adjustment. Different decisions; keep them distinct in the sign-off records.
4. **New D06 controls need individual definition and independent statistical review.** The candidate gives the stage-1 control (`time_shuffle`, `no_information`, `stage1_criteria` including an optional negative-control test with an alpha) and the random-entry `population` a hashed definition. The Plan describes the controls (WP4.0, WP2.5) but fixes none of these parameters. Each is a D06 owner decision (the candidate labels one "OD-2"). Before any value is entered, each control needs an **individual written definition**, its **acceptance behaviour** (what passes, what fails, what the run does on failure) and **independent statistical review by the D08 validator**. A value in a frozen spec shows that the owner chose it, not that the choice is sound; hashing approves nothing. The validator packet (s34.1) is extended accordingly.

5. **Six owner decisions with no spec field (corrected mapping).** Agent C's batch proposal lists them as O-1 budget cap, O-7 lineage constants ("OD-1"), O-13 redundancy comparison set ("OD-3"), O-15 diagnostic windows, O-16 halt evidence ("OD-4") and O-17 risk units. They have no spec field, so the freeze tool will not require them; each needs a signed record under its decision before it becomes binding. Owners as proposed below. O-1, O-13, O-15, O-16 and O-17 were checked against the Sheets and Plan; **OD-1 was not**: the D03 Sheet contains no lineage sub-item.

| Item | Corrected owner | Note |
|---|---|---|
| O-1 budget cap | D03 | unchanged |
| O-7 lineage refusal constants (OD-1) | **PROPOSED D03 sub-item** (source: backlog O-7 / OD-1; D09 is the alternative home); the sub-item wording is a proposal: lineage refusal constants adopted as-is, with the values echoed in the data manifest. **Owner to rule D03 vs D09** | not in the D03 Sheet; mapped to D03 only if the sub-item is added |
| O-13 redundancy comparison set for G10 (OD-3) | **UNRESOLVED** | G10 (correlation with approved strategies <= 0.85) is a **binding** promotion constraint (Plan s5.1). D13 covers only the thesis, naive ORB and non-binding diagnostics; D10 covers only win rate and the drawdown comparator; no Sheet mentions redundancy. Authority is not preserved by mapping it to D13. Kept visible as an unowned item for the owner to assign. The backlog also suggested D08 or D10 as possible homes for OD-3; none was adopted |
| O-15 diagnostic windows | D13 | unchanged |
| O-16 halt evidence source (OD-4) | **D05 5h** (halt rule), plus the feasibility items for data availability | not 5j |
| O-17 risk units | D05 5j | unchanged |

6. **PR #740 overlap.** The candidate and PR #740 both touch `schema.py` / fixtures; sequencing is in the checklist s5 (not repeated here). Both must land before any real freeze.

### 49.3 New mandatory paths in the candidate and their owning decisions

| New path | Owning decision | Value status |
|---|---|---|
| `data.adjustment` | D03 / D05 (corporate-action basis, Plan WP1.6) | owner must define: {raw, split_adjusted, split_dividend_adjusted}; no value proposed |
| `data.minute_reconciliation.volume_tolerance_frac`, `.reference` | D05 5a | owner must define; no value proposed |
| `data.coverage_min` | D03 | may only confirm the design threshold 0.98 (design v0.4 as quoted in the Plan, WP1.8) |
| `data.exclusion_bound` | D03 | owner must define; no value proposed |
| `risk.initial_equity`, `risk.equity_basis` | D05 5j | owner must define; no value proposed |
| `risk.over_budget_rule` | D05 5c | owner must define {reduce_to_budget, protective_exit}; no value proposed |
| `controls.random_entry.population.{unit,instants,matching}` | D06 | owner must define; no value proposed |
| `controls.time_shuffle.{method,min_shift_days,reps}` | D06 | owner must define; no value proposed |
| `controls.no_information.{kind,lo,hi,reps}` | D06 | owner must define; no value proposed |
| `controls.stage1_criteria.{negative_control_mode,negative_control_alpha}` | D06 (candidate label "OD-2") | owner must define; no value proposed |
| (no field) within-family tie-break | D19 | unset escalation; owner approval required; `select_exit` fails closed on an unresolved tie; per-candidate `rank` withdrawn |
| `p5.account_binding` | D07 | single permitted value `deferred_to_p5_activation`; the owner confirms |

Result: every new path has an owning decision (20 owner-valued leaf paths plus the P5 marker). The six no-field decisions are mapped in 49.2 item 5; **OD-3 (G10 redundancy set) remains unowned.**

## 50. OWNER-READY SHEET COMPLETENESS CHECK (D04, D10, D11, D15, D16, C10)

The sheets are in s33 (statement, source, options, recommendation) and s46 (verified values, open items, blank approval fields). Nothing is signed; no role holder, threshold or enumeration was invented.

| Sheet | Complete as far as sources allow? | Owner must define (no source gives it) | Approver / signature |
|---|---|---|---|
| D04 | Yes | Minimum meaningful trades per year | Owner; BLANK |
| D10 | Yes | Comparator definition; equity-sampling definition; account sizing for the comparator; (optional) deviation reason | Owner; BLANK |
| D11 | Yes | `data.fetch_mode` enumeration and vocabulary (no source defines it); prerequisites C12, D03 / F1 / F2 / F5 / F6 to be recorded | Owner; BLANK |
| D15 | Yes | Component definitions for `costs.components` | Owner; BLANK |
| D16 | Yes | Shadow-validation sample duration (number and choice of sampled days) | Owner; BLANK |
| C10 | Yes | Custody location, retention period, holder, whether a derived Markdown copy is permitted | Owner; BLANK |

## 51. HUMAN DECISIONS AND SUPPORTING EVIDENCE NEEDED FOR FORMAL SIGN-OFF

All items are unsigned. "Decides" names the role with authority (design s10.3, A1 s10, Sheets); "reviews" names the role whose review is needed. Signing order follows s35.

**Step 1 - policy choices and amendments**
1. **D08 role holders and separation of duties.** Decides: owner. Evidence: four names (research lead, trading-expert reviewer, independent validator, sole P6 approver); the independent validator's attestation under s15.4 / the Workstream B document; the engineer list; confirmation of SoD-A + SoD-C.
2. **C-DR option (i).** Decides: owner. Evidence: the s39 Plan wording approved for application; confirmation that limits stay 1 / 1 and that no recovery is available without a separately designed, implemented and approved mechanism.
3. **A1.** Decides: owner; trading-expert reviewer signs on D19; independent validator signs on the selection rule and P3a test. Evidence: the s40 reconciliation memo reviewed; the s41 methodology review report with an "adequate" conclusion; A1 s3 amended; the DOCX version and SHA-256.
4. **P5 option B.** Decides: owner; validator reviews the schema change. Evidence: s42 wording approved; schema candidate `5bc2b493` reviewed and merged before any freeze; the permitted marker text confirmed.
5. **E1 step 1.** Decides: owner (with trading-expert reviewer and independent validator). Evidence: the s32.1 text; Plan R1 / s2.5 basis. No acquisition authorization is part of this item.

**Step 2 - statistics specification**
6. **D06.** Decides: owner; independent validator confirms. Evidence: validator's synthetic calibration report; the day-block length, bootstrap method and test statistic, null procedure, repetitions, alpha, interval type, seeds; for each of the random-entry population, time-shuffle, no-information and stage-1 criteria: an individual written definition, its acceptance behaviour and independent statistical review by the validator (49.2 item 4).

**Step 3**
7. **D02.** Decides: owner; validator confirms. Evidence: D06 signed; family-wise error check of the Holm family; choice of option and the hypothesis count (recommended option (a), count 2, NOT APPROVED).

**Step 4**
8. **D18** (gate basis and trade unit). Decides: owner; validator reviews. Evidence: none return-blind; read with D05 5j.
9. **D17** (P3a eligibility, STOP level; P3b criteria and minimum). Decides: owner; validator reviews. Evidence: D06 and D18 signed; the validator's power and false-advance analysis; an owner statement on the consequence of an unattainable trade minimum under a single attempt.
10. **D19** (exit set, complexity order at family level, the within-family tie-break, selection score, tie tolerance, eligibility, STOP test). Decides: owner; trading expert reviews the set; validator reviews the selection rule. Evidence: D17 minimum; trading-expert review; validator review of `select_exit` and the max-statistic test; the within-family tie-break, which is an unset owner-approval item (49.2 item 2; `select_exit` must fail closed on an unresolved tie).

**Step 5 - ready sheets**
11. **D04.** Decides: owner. Evidence: choice of confirm / alter; the minimum trades per year.
12. **D10.** Decides: owner. Evidence: win-rate gate kept or a written deviation; comparator and equity-sampling definitions.
13. **D11.** Decides: owner. Evidence: the `data.fetch_mode` enumeration (owner must define; `monthly_chunked_sip` is a proposal only); C12 named; D03 licence and F1 / F2 / F5 / F6.
14. **D15.** Decides: owner. Evidence: accounting mode; component definitions.
15. **D16.** Decides: owner. Evidence: taxonomy adopted; shadow sample duration.
16. **C10.** Decides: owner. Evidence: DOCX version and SHA-256; custody location and retention; derived-copy permission.

**Step 6 - audits, feasibility and thesis**
17. **D01.** Decides: owner; validator co-sign recommended. Evidence: the signed WP0.6 contact audit including AI-session history; the exposure ledger; the owner's ruling on daily-layer contact; `hypothesis_lineage.yaml`.
18. **D03.** Decides: owner. Evidence: F1, F2, F5; vendor plan and licence; budget cap; N and PIT timing statement; `data.adjustment`, `coverage_min`, `exclusion_bound`; the PROPOSED D03 sub-item for lineage refusal constants (source: backlog O-7 / OD-1; D09 is the alternative home; owner to rule D03 vs D09).
19. **D05** (5a-5j, including 5h the halt rule and halt evidence source (OD-4), and the new paths). Decides: owner; trading expert reviews. Evidence: the E1 summaries (if E1 step 2 is later authorized) or an owner ruling to decide 5a / 5b without data; F3 / F4; numeric risk limits, initial equity and basis, over-budget rule, minute-reconciliation parameters.
20. **D09 / C2 overlap limit, reviewers, history and gate-clause handling.** Decides: owner; trading expert and validator review criteria 2 and 3. Evidence: records of both programs; the overlap computed on the chosen history (no returns); the D13 mechanism text.
21. **D12.** Decides: owner; validator reviews. Evidence: calendar and SPY daily-close session counts per regime and half; minimum trades per cell; share cap.
22. **D13.** Decides: owner; research lead and trading expert author and verify. Evidence: the human-written economic thesis and its SHA-256; naive-ORB definition; diagnostics classification.
23. **D14.** Decides: owner; trading expert reviews; validator reviews F3. Evidence: F3 broker capability report (documentation; a probe order needs separate written owner authorization); F4; numeric latencies and EOD lead; tie-break choice.
24. **D07.** Decides: owner. Evidence: account policy; tolerances; extension rule; marker confirmation (item 4).

**Step 7 - genesis and freeze readiness**
25. **C12 research environment.** Decides: owner. Evidence: environment name and accountable person; reachability metadata check; no broker credentials.
26. **Registry location, host, operator and witness; written authorization to enroll.** Decides: owner. Evidence: path and host statement; named humans; the s2.2 preconditions. (Deferred; nothing is enrolled.)
27. **Attempt limits p3a and p3b.** Decides: owner. Evidence: item 2 signed; values (proposed 1 / 1, NOT APPROVED).
28. **Genesis triple in the manifest.** Decides: owner (after enrollment only). Evidence: the enrollment evidence record; a single reviewed manifest change.
29. **Merge of the distinct-role safeguard (PR #740).** Decides: owner. Evidence: CI results and review; Workstream B items F1 and the test-id manifest.
30. **Merge of the schema candidate** (after item 4). Decides: owner; validator reviews. Evidence: the candidate's checklist ticked; rebase on #740.
31. **Remaining P0 artefacts** (WP0.8 provenance, WP0.10 feasibility report, WP0.11 lineage, WP0.12 order contract, non-equivalence record). Decides: owner with the named reviewers. Evidence: the signed artefacts.
32. **Sign-off packet.** Decides: owner. Evidence: SHA-256 of every pinned document at named commits (s25.1); the validator attestations; the final spec draft with the genesis id and limits equal to the manifest; then the real `freeze_spec`.

Unnumbered, unresolved mapping (does not change the 32-item sequence): **OD-3, the G10 redundancy comparison set, has no owning decision.** The owner assigns it (for example by extending a named decision) before any freeze; until then it stays visible.

**Standing recommendation: NO-GO.** No decision is approved (0).

## 52. EFFECT OF THESE CORRECTIONS (limited reconciliation)

| Question | Answer | Reasons |
|---|---|---|
| Do the corrections change **decision authority**? | **No**, with one gap made visible | The deciding roles for D03, D05, D06, D07, D11, D13 and D19 are unchanged (owner decides; trading expert, validator review as before). OD-4 moves within D05 (5j to 5h) inside existing authority, and OD-1 is proposed for a D03 sub-item (D09 is the alternative home; owner to rule), which would also sit inside existing authority. OD-3 (G10 redundancy set) has **no** owning decision: that is a pre-existing gap now stated, not a change |
| Do they change **dependencies**? | **Yes, in three places** | (a) D19 depends on an owner approval of the within-family tie-break (previously described as a unique rank field); (b) each new D06 control needs a written definition, acceptance behaviour and validator review before a value is entered; (c) D05 5h now also carries the halt evidence source and the feasibility items for data availability. The 32-item sequence and the step order are unchanged |
| Do they change **freeze fields**? | **Yes, relative to the earlier text of this register; no change in what the owner must decide** | The per-candidate `rank` is not a field (withdrawn), so the earlier "20 leaf paths plus rank" is corrected to 20 owner-valued leaf paths plus `p5.account_binding` replacing `p5.account_id`. Relative to `main` the required P0 set grows from 66 to 86 (66 - 1 + 1 + 20; re-verify on the merged schema). The six no-field decisions add no freeze field |

Verdict: **materially changed** in four places (the `rank` withdrawal and the resulting D19 tie-break escalation; the unresolved OD-3 ownership; the OD-4 move to D05 5h with the OD-1 PROPOSED D03 sub-item pending the D03-vs-D09 ruling; the new D06 definition-before-value gate for each control) and **editorial** elsewhere (Plan Appendix A and D07 wording, the s22 / Record C-P5 text, the D11 proposal-only value). Terminology was aligned with Agent C's documents ("owner choice", "deferral marker", "activation record", "owner approval", "unset"); the register still labels owner choices recorded here as directions, not approvals.

Invariants preserved: **0 formally approved decisions**; every signature, name, date and SHA-256 field remains BLANK; the 32-item sequence in s51 is unchanged; the standing recommendation is NO-GO; no enrollment, freeze, data access or signing occurred.
