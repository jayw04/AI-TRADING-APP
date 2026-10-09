# RANGE-002 — Governing-Document Reconciliation (P0 pre-sign-off)

| Field | Value |
|---|---|
| Date | 2026-10-09 |
| Work package | WP0.1 completion; owner instruction 5 (reconcile before P0 sign-off) |
| Documents compared | (1) Research design v0.4 (`Teams/Strategies/RANGE-002_开盘区间突破延续策略_验证与实施方案_v0.4.docx`, read in full, Chinese), (2) Implementation Plan v0.4 (`docs/implementation/evidence/range_002/RANGE-002_Implementation_Plan_v0.4.md`), (3) ADR 0014 (v1.1), (4) ADR 0033, (5) ADR 0037, (6) the RNG-001 Rejection Summary Report (`docs/implementation/evidence/range_002/RNG-001_Rejection_Summary_Report_2026-10-09.md`) and the primary evidence it cites |
| Data accessed | None. Document review only. |
| Status | **Conflicts listed for owner approval. No code, spec value or gate has been changed to resolve any of them.** Updated 2026-10-09 with C13 (exit-rule change) and the Addendum A1 draft. |

Precedence stated in the plan: research design v0.4 wins over the plan. ADR texts were not available when the plan was written; they have now been read.

## 0. Owner rulings (2026-10-09)

The owner reviewed this document and approved WP0.1 for the normal documentation-only review and merge process. Rulings, recorded verbatim in substance:

| ID | Ruling | Recorded effect |
|---|---|---|
| C1 | Correct the ADR 0014 attribution; **preserve the existing gates** | No gate changes. The design docx and the RNG-001 evidence are the owner's documents and are not edited here; the correction is carried into the governing-design addendum (C7) |
| C2 | **Approve the ATP three-criterion non-equivalence framework.** The numeric overlap limit and reviewer sign-offs **stay open under D09**. **No non-equivalence code until the full specification is approved** | WP0.5 and PR 4 stay blocked on the written specification |
| C3 | The platform's >50% win-rate gate **remains applicable until a formal D10 deviation is signed** | Plan §5.1 row reworded accordingly |
| C4 | **Approve a dedicated RANGE-002 SIP intraday coverage validator**, separate from daily `dataset_health` | Part of P1 loader design (PR 5) |
| C5 | **D11 = a new monthly-chunked, fail-closed SIP loader.** Do not modify the shared production cache | Plan D11 and WP1.1 wording updated |
| C6 | **Holm for RANGE-002.** ADR 0037's BH-FDR framework remains scoped to EAD programs | No plan change needed (already Holm) |
| C7 | **Retain D01–D18** and **prepare a governing-design addendum covering D13–D18 before P0 sign-off** | **Drafted 2026-10-09** as `RANGE-002_Design_Addendum_A1.md` (markdown addendum to design v0.4), extended to D19 and the exit change (C13). Awaiting owner signature |
| C8 | Implement the funnel from the CAP-025 charter; **do not claim an existing wrapper** | Plan `funnel.py` row reworded |
| C9 | Include **simulated order evidence in P3/P4 audit packs** | Plan §7 `orders.csv` row updated |
| C10 | Store the authoritative research-design DOCX in **controlled S3 with a versioned SHA-256 manifest**; a **non-authoritative Markdown extraction** is allowed | **Not done.** The S3 manifest tooling (`manifests/s3/`, publish/verify scripts) is not in the repository, and the github-ops policy forbids a hand-rolled manifest scheme. The DOCX remains local and untracked until that tooling lands or the owner directs otherwise. No Markdown extraction is committed yet |
| C11 | Correct the bootstrap provenance statement; **statistical parameters unresolved** | Plan `bootstrap.py` row reworded; no value chosen |
| C12 | **Approved, isolated, non-production research environment** for future data pulls and replay. **No production-host data workload is authorized** | The specific environment is still to be named and approved before PR 5 or WP2.6 |

Wording changes made to the plan under these rulings (text only, no gate or strategy value touched): C3 row, C5 (D11 and WP1.1), C8, C9, C11, plus the earlier path mapping. Nothing was changed in the design docx.

Still needing owner action after these rulings: signature of Addendum A1 (C7, C13), the D09 numeric limit and sign-offs (C2), the DOCX custody mechanism given the missing S3 tooling (C10), and naming the research environment (C12).

## 1. Summary

| # | Finding | Type | Severity |
|---|---|---|---|
| C1 | ADR 0014 does not say what the design, the plan and the RNG-001 evidence attribute to it | Citation conflict | High |
| C2 | ADR 0037 contains no non-equivalence test. The design and the plan both say it does, and both assume an automated check exists | Governing-text gap | High (blocks WP0.5 as written) |
| C3 | Win-rate gate: design says the platform gate applies until the deviation is signed; the plan lists win rate as "diagnostic only" | Plan vs design | Medium |
| C4 | ADR 0033 point 4's named primitive `dataset_health` covers only the daily Sharadar table, not 1-minute bars | Tooling gap | High (blocks the P1 acceptance rule as written) |
| C5 | Design D11 offers two options; the owner approved a third (new loader). ADR 0033 points 1–3 remain open for the shared cache | Decision variance | Medium |
| C6 | ADR 0037's BH-FDR / hypothesis-budget regime vs the plan's Holm at α=0.05 | Scope ambiguity | Medium |
| C7 | The plan's decision list (D01–D18) is larger than the design's (12). D13–D18 are not in the design | Plan vs design | Medium |
| C8 | The design assumes CAP-025 tooling exists; it is a charter only | Assumption gap | Low |
| C9 | The audit-pack file list differs between design §8.3 and plan §7 | Plan vs design | Low |
| C10 | Plan action 11.3.2 says to commit the design `.docx` to Git; repo policy sends Office binaries to S3 with a manifest | Plan vs repo policy | Low |
| C11 | Bootstrap "platform convention adopted from MR-002" is not supported by the design or by code | Plan claim | Medium (owner item 3 already addresses) |
| C12 | RNG-001 replay (chain 1) needs IEX 5-minute data and the code state of git `9e43abe`; environment constraints are unstated | Feasibility | Medium |
| C13 | Exit rule changed after review: design v0.4 fixes variants A/B; plan v0.5 selects one exit from a frozen candidate set and splits P3 | Strategy-rule change (owner-accepted direction) | High (needs Addendum A1 signature before P0) |

Details below. Items marked **OWNER** need a ruling.

## 2. Detailed findings

### C1 — ADR 0014 vs how it is cited

- **What ADR 0014 says (v1.1):** backtests on a holdout window are the primary *research* ground truth for evaluating **agent proposals** against a baseline; at least 5 backtested proposals per strategy; a 10% human-review sample; and the v1.1 amendment adds that evaluations with insufficient evidence are `INSUFFICIENT_EVIDENCE`, never PASS or FAIL. Backtest is the gate to enter paper, not final truth.
- **What the design says (§2.1, "判定依据"):** "ADR 0014: only a strategy with a robust, statistically significant edge may enter paper or live trading."
- **What the RNG-001 evidence says** (`range_evidence.md`): "Per ADR 0014: a strategy earns paper/live only with a robust, statistically-significant edge." The Rejection Summary Report repeats it.
- **Conflict:** the significance requirement is not in ADR 0014. It is a platform practice (owner's promotion gate in `range_strategy_research_program`, Evidence Engineering). What ADR 0014 does support is the evidence-sufficiency principle, which maps cleanly onto the plan's `INCONCLUSIVE_*` states.
- **Effect:** none on the gates. The citation is wrong, and a reviewer who opens ADR 0014 will not find the rule.
- **OWNER:** (a) approve correcting the citation in the design and plan (cite the owner's promotion gate and ADR 0014's INSUFFICIENT_EVIDENCE amendment separately), or (b) direct a short ADR amendment recording the significance requirement. I recommend (a). I have not edited the design docx, which is the owner's document.

### C2 — ADR 0037 has no non-equivalence test

- **What ADR 0037 says:** its subject is Event & Alternative-Data Discovery (Quiver, Security Master, Daily Opportunity Report). Governance principle 5 is the single relevant sentence: "Previously rejected patterns are auto-checked before a research line reopens (RNG-001, early INSIDER-001 must not resurface unflagged)." It specifies no algorithm, inputs, thresholds or outcome states.
- **What the design says (§3.4, decision 09):** ADR 0037 requires a "non-equivalence test" in pre-registration, and it "must be confirmed by the ADR 0037 automated check, not self-declaration".
- **What the code has** (recon §2.8): only a string-literal CI check for rejected EAD event labels (`check_reference_only_invariant.sh`). Nothing compares a new research spec with RNG-001.
- **The only documented test criteria in the repo** are in the ATP plan v0.14, §3A.2 ("Non-equivalence test, new at v0.8"). A candidate must settle in pre-registration, before backtest: (1) signal-level distinctness (correlation with the rejected predecessor's signal on overlapping history, with a pre-declared maximum); (2) a materially different reject condition (falsifiable in a way the old one was not); (3) an economic mechanism that does not reduce to the rejected one (better measurement of the same effect is not a new edge). Failing any, the proposal is a reopening that needs an owner ruling.
- **Consequence:** WP0.5 ("run the platform's rejected-pattern auto-check") cannot be executed as written. Stop condition §9.1 cannot be evaluated by a tool today.
- **Direction already approved (your instruction 4):** build a deterministic check with explicit evidence and documented review outcomes. I propose to base it on the three ATP criteria, with the following design constraints, all for **OWNER** approval before any code:
  1. Inputs are explicit, versioned records of each program's entry rule, exit rule, universe, data granularity and falsification condition, taken from the frozen specs, not from names or parameter values.
  2. Criterion 1 (signal overlap) is computed on **signal timestamps and direction only**, never on returns, and needs a pre-declared maximum. Note the structural difference RNG-001 (buys the dip at OR low, 5-minute IEX bars) vs RANGE-002 (buys the break above OR high, 1-minute SIP bars). A direction-opposed signal is a candidate "distinct" result, but the check must test it rather than assume it.
  3. Criteria 2 and 3 are reviewer-judged and recorded as signed findings with the evidence cited. The tool records the verdict and the reviewer; it does not infer economic mechanism.
  4. Output states are a closed set (for example `DISTINCT`, `EQUIVALENT_REOPENING`, `NEEDS_OWNER_RULING`). The tool fails closed on missing inputs.
  5. Suspicious overlap with RNG-001 evidence is stated up front: the RANGE-002 idea was **generated from RNG-001's "target hit before entry 49%" finding**. That origin is itself part of the non-equivalence record and the exposure ledger.
- **OWNER:** approve the three-criterion basis (or supply another), the overlap maximum, and who signs criteria 2–3. Also decide whether an ADR amendment is wanted, since a check that the ADR names but does not define will otherwise be defined by a PR.

### C3 — Win-rate gate default

- **Design §6:** the platform's formal gate has win rate > 50%. The design treats win rate as diagnostic only because breakout strategies typically win less than half the time. It says the deviation must be signed in P0, and "**before it is signed, the platform formal gate applies**".
- **Plan §5.1:** the G-table row reads "Win rate: Diagnostic only, unless D10 restores the platform's > 50% gate", status "Open (D10)". The alert paragraph then says both evaluations are displayed and promotion is blocked until resolved.
- **Conflict:** the row's wording implies the deviation is the default. The design's default is the opposite. The alert paragraph is consistent with the design; the table row is not.
- **Proposed correction (no gate value changes):** reword the row to "Platform gate (> 50%) applies until D10 is signed; display both evaluations". Pending **OWNER** approval of the wording, and in any case the schema must have `gates.win_rate` required with no default (already so in Appendix A).
- Related platform-gate elements the plan should keep visible: trades > 100, PF > 1.2, drawdown not worse than baseline, positive expectancy, bootstrap CI > 0. The design's gates are stricter on PF (≥1.30) and sample (≥300), so these are subsumed, except win rate and the drawdown comparator.

### C4 — ADR 0033 point 4 tooling does not reach 1-minute bars

- **ADR 0033 point 4 and design §5.1:** acceptance of data is by the `dataset_health` coverage assertion.
- **Code** (`apps/backend/app/factor_data/evidence.py:356`): `dataset_health(store, start, end)` queries the DuckDB `sep` table (Sharadar daily bars) and the `tickers` table. It checks date bounds, row count, ticker count, and delisted count. It has no concept of intraday bars, minutes, sessions or symbol-day completeness.
- **Effect:** `dataset_health` can validate the daily PIT universe inputs (ADV, price, delistings). It **cannot** assert the ≥98% symbol-day coverage and 09:30–10:00 completeness the design requires for the SIP minute bars.
- **Proposed path (consistent with your D11 requirements):** the new RANGE-002 loader ships its own intraday completeness assertion (symbol-day coverage against the PIT population, per-year/month/first-30-minute coverage, truncation detection, `NO_TRADE_MINUTE` vs `DATA_GAP` classification, fail-closed). Use `dataset_health` for the daily layer only. Record in the WP1.1 finding that point 4's canonical primitive is daily-only.
- **OWNER:** confirm that a RANGE-002-specific intraday coverage check satisfies ADR 0033 point 4 for this program, or direct a generalization ADR note. This does not need to be settled before PR 2.

### C5 — D11 variance

- **Design decision 11:** confirm the writer meets ADR 0033 points 1–3, **or** approve a monthly-chunk **rebuild script** as the P1 data source.
- **Owner ruling (2026-10-09):** build a new RANGE-002 SIP loader (explicit SIP, monthly chunks, pagination and truncation detection, completeness checks, idempotent resume, manifests, delisted coverage), and do not modify `BarCache`.
- **Reading:** this is within the spirit of the second option. Two clarifications for the record: (a) ADR 0033 points 1–3 stay **unimplemented in the shared cache**, and RANGE-002 does not fix that; (b) the cited rebuild script (`scripts/research/rebuild_5min_cache.py`) does not exist in the repo.
- **OWNER:** confirm that recording D11 as "monthly-chunk, new loader" satisfies decision 11. If so, I will record it in `recon.md` as D11 = resolved, subject to the spec value `data.fetch_mode`. The plan's wording "monthly-chunk rebuild" (WP1.1, D11) should say "monthly-chunk loader".

### C6 — ADR 0037's statistical regime vs the plan

- ADR 0037 governance principles 3–4 and the MVP gates set Benjamini–Hochberg FDR (q ≤ 0.10), hypothesis budgets (1–3 per week), matched-control excess-return bootstrap, and held-out confirmation. ADR 0037 says these are "the regime every **EAD program** inherits".
- RANGE-002 is not an EAD program, and the plan uses Holm at α = 0.05 (one-sided) with a day-clustered bootstrap, as the design requires.
- **Conflict:** none if ADR 0037's regime is scoped to EAD programs. But the design cites ADR 0037 as RANGE-002's governing ADR, so the scope should be stated.
- **OWNER:** confirm that ADR 0037 governs RANGE-002 for the rejected-pattern check (principle 5) only, and that Holm per the design applies, not BH-FDR.

### C7 — Decision list size

- The design's P0 sign-off list has decisions 01–12. The plan adds D13–D16 (economic thesis, order/latency contract, cost accounting, diagnostics/shadow acceptance) and D17–D18 (P3 criteria, gate basis).
- The plan argues D13–D16 refine design decisions 05–07 and the §4 cost row, and that D17/D18 fill gaps the design leaves open. I agree with D17/D18: the design §7 says P3 needs "pre-approved development-period criteria" and never gives them, and §6 does not state the trade set the gates are computed on.
- **OWNER:** confirm the sign-off sheet is D01–D18, and that D13–D16 need no design addendum. Nothing in this reconciliation is a P0 decision.

### C8 — CAP-025

- The design says to "plug into CAP-025 funnel diagnostics". CAP-025 exists as a charter (`docs/implementation/evidence/cap_025/…Charter_v0.1.md`), with no library module. RANGE-002 builds its own engine and funnel (plan `stats/funnel.py`).
- No conflict with the plan, which already says "wraps CAP-025". The word "wraps" is inaccurate. **No owner action**, but `funnel.py` should be described as a new implementation of the CAP-025 charter.

### C9 — Audit-pack list

- Design §8.3 lists `strategy_spec.md`, `engine_version.txt`, `validation_report.pdf`, `orders.csv` for every P3/P4/P5 run, and says the filenames are recommendations ("final per repo conventions").
- Plan §7 uses `strategy_spec.yaml`, `validation_report.md`, puts the engine SHA in `research_manifest.yaml`, and lists `orders.csv` for P5 only (plus `order_event_log.parquet`).
- **Proposed:** keep the plan's structure, and produce `orders.csv` (simulated orders) for P3/P4 as well. Needs no gate change. **Owner** may confirm.

### C10 — Committing the docx

- Plan 11.3.2 says to commit the design `.docx` and the RNG-001 report to the range_002 docs folder. Repo policy (CLAUDE.md, GITHUB-OPS-001, `github-ops` skill) says large Office binaries live in controlled S3 pinned by a manifest (Version ID + SHA-256).
- **Proposed:** commit the RNG-001 report (markdown) and a manifest entry for the docx, plus the extracted text of the design as markdown, if the owner permits a derived copy. The docx itself goes to S3. **OWNER** to confirm, and to say whether a derived markdown copy of the design is acceptable. I have not copied the docx anywhere.

### C11 — Bootstrap convention

- The design requires day-clustered block resampling and fixes repetitions, interval type, confidence level and tail conventions in P0. It does not say "stationary" and does not mention MR-002.
- The plan says "stationary block bootstrap … platform convention adopted from MR-002; confirm in WP0.1". Recon found no MR-002 module, and no day-clustered stationary bootstrap anywhere in the repo.
- Per your instruction 3, the plan wording should not claim the implementation exists. Proposed edit: "block-bootstrap design reference: `factor_data/evidence.py` (circular block, cluster) and `market_projection/validate.py` (stationary)". Method, block length, repetitions, confidence level and adjustment remain open under D06.

### C12 — RNG-001 replay feasibility

- Design §5.2 chain 1 and plan WP2.6 require reproducing `range_evidence.json` (102 trades, PF 1.271, CI [−$19.74, +$57.53]) using the old engine and rules on the rebuilt IEX 5-minute archive.
- `range_evidence.md` records `git 9e43abe` as the code state that produced it. The current scripts have since changed (`eee53a06`, `0fe8ad24`, `296f4f02`). Reproduction should state which commit it ran, and whether the old state is a checkout or the current code.
- Environment: the repo's working notes say Norton SSL inspection blocks `data.alpaca.markets` on the developer laptop, so data pulls must run on a non-Norton host (the AWS box, WSL or CI). Runtime guidance also says the laptop is warm standby and the local stack must not be started. Any backfill needs an agreed host and a record of where the cache lives.
- **OWNER:** confirm the host for data work (P1 SIP pulls, WP2.6 replay). Not needed for PR 2.

## 3. Agreement (no conflict)

The following were checked and agree between the design and the plan:

- Strategy rules: OR 09:30:00–09:59:59 frozen at 10:00:00; entry window 10:00:00–14:59:59; buy-stop at OR high + 1 valid tick; first trigger only; no add-on or re-entry; long only; stop at OR low; variants A and B (target fill + 2R); flat at 15:55 ET, half-day offset fixed in P0.
- Universe: monthly PIT rebuild from the prior day's 20-day average dollar volume, top N (N = 100 proposal), prior close > $10, delisted names included; SIP 1-minute bars.
- Costs: 5 bps base and 15 bps stress per side, itemized.
- Risk: 0.25% per trade proposal, with R_pre / R_fill separation; limits fixed in P0.
- Partitions: development 2016–2021, holdout 2022–2025, 2026-01 to 2026-07 exposed and excluded from decisive runs.
- Gates G0–G10 (independence, ≥300 trades, PF ≥ 1.30, stress mean > 0, corrected significance, paired random baseline, yearly 3-of-4 (proposed), regime robustness, drawdown comparator, reliability, redundancy 0.85).
- Four verdict states and their mapping; P5 minimum 60 trading days and 100 trades, cost ratio ≤ 1.5×; P6 human decision, no automatic promotion.
- ADR 0033 points 1–5 as described (and the pre-fetch acceptance rule; with the C4 and C5 notes).

Also consistent: ADR 0014's `INSUFFICIENT_EVIDENCE` principle and the plan's `INCONCLUSIVE_*` states.

## 4. What this means for the next steps

| Next step | Blocked by this reconciliation? |
|---|---|
| WP0.1 review and merge | No. This document and the updated `recon.md` are the package. |
| PR 2: spec schema, canonical hashing, freeze tool | **No.** It only needs required fields and named validation errors. Contested items (C2, C4–C7) only affect later PRs. |
| PR 3 (results guard, ledgers) | No |
| PR 4 (WP0.5 non-equivalence, WP0.8 AI provenance) | **Yes**, on C2 owner approvals |
| P1 loader design (PR 5) | C4, C5 and the host decision in C12 |
| P0 sign-off | C1–C3, C5–C7, C10 rulings. No signature is implied by this document. |

No conflict found here changes a gate threshold or a strategy rule, and none was resolved by changing code or the frozen-spec skeleton.

## 5. Post-ruling change C13 — exit selection (2026-10-09)

- **Source.** Fund-manager review of the investment-committee version: the take-profit should be chosen from historical price behaviour (trailing, scale-out) rather than a hand-set 2R. The owner accepted the direction.
- **Conflict.** Design v0.4 fixes variants A (time exit) and B (2R target), and the plan defers to the design. The plan therefore cannot adopt the change on its own authority.
- **Resolution path.** Addendum A1 Amendments 1–3: a frozen candidate set of ≤ 8 exits (time, fixed-R, trailing, scale-out, in R units); P3a selection on 2016–2019 by a pre-frozen rule executed on sealed results; P3b confirmation on 2020–2021; P4 tests the selected exit once (m = 1). New decision D19; D02 and D17 rewritten. Plan v0.5 implements this.
- **Until A1 is signed:** design v0.4 governs. PR 2 builds the schema to accept the A1 `exits` block with all values unset; no spec is frozen under either form.
- **Effect on gates:** none. G0–G10 thresholds are unchanged.
- **Integrity note.** No RANGE-002 data or results were seen by the reviewer, the owner or the agent. The proposal is recorded in the hypothesis-lineage (WP0.11) and AI-provenance (WP0.8) records.
