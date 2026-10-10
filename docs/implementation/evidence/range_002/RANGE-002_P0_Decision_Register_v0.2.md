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
| D11 | Loader approach recorded; `data.fetch_mode` | UNSIGNED; RECOMMENDED | Confirm ruling C5 (new monthly-chunked fail-closed SIP loader; shared `BarCache` untouched) satisfies design decision 11 and record the enumeration string | WP1.1 written finding on `bar_cache.py` (already in `recon.md`) | FRZ (T: `data.fetch_mode`), P1 | |
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

1. **R3 (line 101)**, replace the second sentence with: "Defect-only reruns are not automatic and are not available under the Level 1 registry. A run after authorization requires a separate recovery authorization under the owner-approved recovery procedure (incident record, independent review, owner approval and a permanent audit record). Until that procedure is implemented and approved, no rerun exists and the phase is ended for the lineage."
2. **WP4.0 step 2 (line 584)**, replace the last sentence with: "The run is closed `INCONCLUSIVE_ENGINE`, its attempt stays consumed, and any further run requires the separate recovery authorization described in WP4.1."
3. **WP4.1 (line 606)**, replace the bullet with: "**Defect-only reruns.** None is automatic. After `capability_issued` a rerun is possible only under a separate recovery authorization (design-only Level 2 procedure). Its request needs a defect record (symptom, root cause, fix commit, and why the fix does not encode knowledge of results), an independent review and owner approval, and it is recorded as an additional registry row; both runs are reported."
4. **s11.1 table (line 848)**, replace "obtain governed defect-only rerun authorization" with "request a separate recovery authorization (design-only until approved)".
5. **WP0.7**, add: "attempt limits P3a = 1 and P3b = 1 from the governance manifest; P4 is limited by the holdout once-per-window rule."

## 21. CANONICAL REGISTRY ENROLLMENT - PENDING

**Status: PENDING.** No ceremony is authorized or performed; no genesis id exists or is recorded; no registry location, host, operator or witness is decided; the manifest remains entirely unset. The description in section 2 is a plan only. Preconditions for ever running it include the owner's ruling on C-DR (section 20), the registry location, named operator and witness, and written authorization.

## 22. `p5.account_id` - MANDATORY-FIELD CONFLICT AND DESIGN OPTIONS

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
- Proposed value: PROPOSED / NOT APPROVED: option B (section 22)
- Evidence required: Owner decision; implementation PR reviewed before any freeze
- Approver(s) by role: Owner; independent validator reviews the schema change
- Documents to pin: DOC-SHEETS, DOC-PLAN, DOC-REG. SHA-256 of each: BLANK
- Signature: BLANK. Date: BLANK

## 26. REFRESHED P0 STATUS

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
- **`p5.account_id`**: schema change (option B recommended) before any freeze.
- **A1 / v0.4 / merged schema**: written reconciliation; code changes if anything other than the A1 form is intended.
- **SoD-B**, if chosen: amendment of the distinct-role safeguard.
- **C-EVID**: a plan / A1 amendment or an owner-authorized early return-blind pull, if D05 5a/5b are to be evidence-based.
- Safeguard hygiene from Workstream B (F1: strip zero-width and control characters; test-id manifest) before any real freeze.

### 26.5 Final P0 GO / NO-GO (recommendation only)

**NO-GO.** P0 is not ready. Zero decisions are formally approved; the manifest is unset; no registry is enrolled (PENDING); three items require design changes or written reconciliation (C-DR, `p5.account_id`, A1 versus schema) plus a data-timing ruling (C-EVID); no independent validator is named or attested. P0 may move to GO only when the records in sections 11 and 25 are signed against pinned SHA-256 hashes, the schema and plan changes above are reviewed and merged, the manifest change has merged after an authorized enrollment, the real `freeze_spec` has passed, and the independent validator has attested. The decision is the owner's.
