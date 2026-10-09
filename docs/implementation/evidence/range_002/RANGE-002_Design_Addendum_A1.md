# RANGE-002 — Governing-Design Addendum A1

| Field | Value |
|---|---|
| Amends | Research design v0.4, `RANGE-002_开盘区间突破延续策略_验证与实施方案_v0.4.docx` (Chinese, 2026-10-09) |
| Addendum | A1 |
| Date | 2026-10-09 |
| Authority | Owner ruling C7 (prepare a governing-design addendum covering D13–D18 before P0 sign-off), extended to the exit-rule change accepted after the fund-manager review of 2026-10-09 |
| Status | **DRAFT — not in force until signed (§10).** Until signed, design v0.4 governs unchanged, including the fixed A/B exits |
| Companion | Implementation Plan v0.5; `governing_reconciliation.md` (C1–C13); `recon.md` |
| Data accessed | None. No RANGE-002 returns have been computed. |

## 1. Purpose

This addendum changes one strategy rule (how the exit is defined), one phase (P3 is split), and the P0 decision list (D13–D19). It also records the citation and scope corrections from the WP0.1 reconciliation. Everything not named here is unchanged in design v0.4.

## 2. Amendment 1 — the exit is selected from a frozen candidate set

**Replaces:** design §3.1 "主方案 A / 次方案 B"; the §4 rule row "方案 A / B"; the A/B references in §5.3 (A/B 多重检验) and decision 02.

**New rule.**

1. The entry rule, the initial stop (OR low), and the end-of-day flat (15:55 ET; half-day per decision 05) are unchanged.
2. The take-profit is **not** fixed by hand. In P0, the trading expert proposes, and the owner signs, a closed set of at most 8 exit configurations drawn from four families: time exit (no target), fixed-R target, trailing exit, and scale-out. Parameters are expressed in R units. Proposed set: E1 time exit; E2 fixed target at 2R and 3R; E3 breakeven at +1R then trail at 1.0R or 1.5R; E4 50% scale-out at +1R with the remainder held to EOD or trailed at 1.0R.
3. A **selection rule**, frozen in P0, chooses exactly one configuration on the P3a data: highest one-sided bootstrap lower bound of mean net R per trade among eligible candidates; ties within a pre-registered tolerance go to the simpler family. The selection is computed by code on sealed results and recorded before anyone views candidate results.
4. No configuration may be added, removed or re-parameterized after P0 freeze. An adaptive exit that switches rules day by day is a different strategy and is outside RANGE-002.

**Why.** A fixed 2R target is an arbitrary hand-set number. Choosing the exit from data is better, provided the data that chooses it is not the data that confirms it (RNG-001: the VWAP fix showed PF 1.53 on the full sample and 0.68 on its first half).

## 3. Amendment 2 — P3 is split into selection and confirmation

**Replaces:** design §7 P3 row and §3.2 "2016—2021 开发与规则确认".

| Phase | Data | Runs | Exit condition |
|---|---|---|---|
| P3a selection | 2016-01-01 → 2019-12-31 | All K candidates; deterministic selection | One exit selected, or STOP if no candidate is eligible or the selection-aware test (maximum statistic over all K, day-clustered resampling) fails at the D17 level |
| P3b confirmation | 2020-01-01 → 2021-12-31 | Selected exit only | D17 P3b criteria met, else STOP |
| P4 holdout | 2022-01-01 → 2025-12-31 | Selected exit only, once | Design §6 gates, unchanged. One exit configuration is tested (exit-configuration count = 1); the number of confirmatory hypotheses in the Holm family is the D02 owner value (see Amendment 3, D02); the ledger records K |

P3b covers two of the design's six development years and runs the selected exit only, so its sample is smaller than the design's single 2016–2021 run; D17 therefore needs an explicit P3b trade minimum.

Exposure: P3a exposes 2016–2019 for all K candidates; P3b exposes 2020–2021 for the selected exit. The 2022–2025 holdout and the 2026-01 → 2026-07 exclusion are unchanged.

## 4. Amendment 3 — P0 decision list is D01–D19

Design v0.4 §10.2 lists decisions 01–12. The P0 sign-off list becomes D01–D19. The table lists all 19 in numeric order. D01 and D03–D12 are the design v0.4 decisions with the same numbers, unchanged by this addendum (subject to §5–§7); they are listed so the sign-off packet carries one list. D13–D16 refine v0.4 decisions and are recorded here under ruling C7. D17–D19 are gaps or new items. Plan v0.5 §10 and §10.1 use the same numbering.

| ID | Decision | Relation to design v0.4 |
|---|---|---|
| D01 | Register RANGE-002; sign data-exposure conclusions and holdout applicability | Unchanged (v0.4 decision 01) |
| D02 | Hypothesis family: P3a selection-aware test over K; P4 tests the selected exit (exit-configuration count = 1, K recorded in the ledger). **The number of confirmatory hypotheses in the Holm family is a D02 owner value:** design §5.3 and §6 require both a mean net R > 0 test (G4) and a paired-difference-vs-random-baseline test (G5), each with a corrected bound, so "m = 1" counts exit configurations and is not by itself the family size. Options: Holm over {G4, G5}; G4 alone as the Holm family with G5 as a separate required gate at its own declared alpha; fixed sequence. Recommendation (not a decision): Holm over {G4, G5}, the stricter reading. PF ≥ 1.30 and stress > 0 confirmed | **Replaces** decision 02's A/B ordering |
| D03 | N, PIT timing, SIP vendor and licence, data budget | Unchanged (v0.4 decision 03) |
| D04 | Yearly gate (≥ 3 of 4 years PF > 1.0) | Unchanged (v0.4 decision 04) |
| D05 | R_pre / R_fill, gap fills, same-bar order, tick size, half-day exit | Unchanged (v0.4 decision 05) |
| D06 | Baselines, bootstrap, adjustment, confidence level, seeds | Unchanged (v0.4 decision 06) |
| D07 | New paper account policy, P5 tolerances, extension rules | Unchanged (v0.4 decision 07) |
| D08 | Roles and the sole P6 approver | Unchanged (v0.4 decision 08) |
| D09 | ADR 0037 non-equivalence statement; ORM-001 relationship | Unchanged (v0.4 decision 09); see §6 for scope and open items |
| D10 | Win-rate gate vs signed deviation; drawdown comparator | Unchanged (v0.4 decision 10); see §5 and §8 |
| D11 | Data writer / loader approach | Unchanged (v0.4 decision 11); approach ruled (§7) |
| D12 | Regime definition and single-regime criterion | Unchanged (v0.4 decision 12) |
| D13 | Economic thesis, competing explanations, which diagnostics are non-binding | Refines §10.3 roles |
| D14 | Bar timestamps, latency, simulated order arming and crossed-before-arm policy, order type, EOD protocol, tie-break | Refines decision 05 and §5.2 |
| D15 | Cost accounting mode (all-in vs additive) and components | Refines the §4 cost row |
| D16 | Diagnosis taxonomy, P5 shadow run, execution-quality evidence | Refines decision 07 |
| D17 | P3a eligibility and STOP level; P3b criteria (recommended: P4 thresholds, trade minimum scaled to two years) | **Fills a gap**: §7 requires pre-approved development criteria but gives none |
| D18 | Gate computation basis (portfolio-constrained fills vs signal level) and the trade unit (one entry = one trade, including scale-outs) | **Fills a gap** in §6 |
| D19 | Exit candidate set, parameters, complexity order, selection score, tie tolerance, eligibility | **New**, from Amendment 1 |

Decisions 01, 03–12 are unchanged, subject to the rulings in §5–§7.

## 5. Citation correction (ruling C1)

Design §2.1 "判定依据" and the RNG-001 evidence attribute to ADR 0014 the rule that only a robust, statistically significant edge may enter paper or live trading. ADR 0014 (v1.1) does not contain that rule. Read instead:

- The significance requirement comes from the **owner's platform promotion gate** (trades > 100, PF > 1.2, win rate > 50%, drawdown no worse than baseline, positive expectancy, bootstrap CI > 0) and Evidence Engineering practice.
- ADR 0014 v1.1 supplies the **evidence-sufficiency principle** (`INSUFFICIENT_EVIDENCE`, never PASS or FAIL), which maps to the design's "证据不足 / 技术阻断" state.

No gate changes. Per ruling C3, the platform's > 50% win-rate gate applies until a D10 deviation is signed; both evaluations are displayed.

## 6. ADR 0037 scope (rulings C2, C6)

- ADR 0037 defines no non-equivalence test. RANGE-002 uses the ATP v0.14 §3A.2 three-criterion framework (signal distinctness measured on timestamps and direction only; a materially different reject condition; an economic mechanism that does not reduce to the rejected one). The overlap limit and reviewer sign-offs are open under D09. The design's phrase "ADR 0037 自动检查" reads as this check once specified and approved. That check does not exist yet (C2: specification pending, no code until approved), so the P0 exit-gate clause "the non-equivalence check passes" cannot be met by a tool until it does. Criterion 1 also needs signal history: SIP data arrives only in P1, after the P0 gate, and before it only the exposed RNG-001 IEX 5-minute archive exists. Which history is used, and how the gate clause is satisfied, are D09 owner decisions (options in plan v0.5 WP0.5 and the D09 sheet); none is selected here.
- ADR 0037 governs RANGE-002 only through governance principle 5 (rejected patterns are checked before a line reopens). Its BH-FDR regime is scoped to EAD programs. RANGE-002 uses Holm; the family size at P4 is the D02 value (one exit configuration, with the number of confirmatory hypotheses per D02).

## 7. Data and environment (rulings C4, C5, C10, C12)

- Decision 11: the approach is resolved by ruling C5 as a **new monthly-chunked, fail-closed RANGE-002 SIP loader** (the spec value `data.fetch_mode` and the D11 signature are still required at P0); the shared `BarCache` is not modified; ADR 0033 points 1–3 remain open for the shared cache.
- ADR 0033 point 4 for RANGE-002 intraday data is met by a **dedicated SIP intraday coverage validator**; `dataset_health` covers the daily layer only.
- The authoritative design DOCX is stored in controlled S3 with a versioned SHA-256 manifest (the S3 manifest tooling does not yet exist, ruling C10 is not yet implemented); a non-authoritative Markdown extraction may be committed. The sign-off packet pins the SHA-256 of every document signed: the design DOCX, this addendum, plan v0.5, the decision sheets, `governing_reconciliation.md` and `recon.md`.
- Data pulls and replays run only in an approved, isolated, non-production research environment (to be named before PR 5 or WP2.6).

## 8. Unchanged

Entry rule; OR definition; initial stop; EOD flat; universe and PIT rules; SIP data; costs (5 / 15 bps per side); risk proposals; holdout 2022–2025 opened once; the 2026-01 → 2026-07 exclusion; gates G0–G10 and their thresholds (win rate: the platform > 50% gate applies until a D10 deviation is signed, and both evaluations are displayed, ruling C3; this addendum does not change that); verdict states (plus the intermediate `EXIT_SELECTED`); P5 minimums (60 trading days, 100 trades, cost ratio ≤ 1.5×); P6 human decision with no automatic promotion.

## 9. Provenance

The exit change originated in a fund-manager review of the investment-committee version of the plan on 2026-10-09. No RANGE-002 data or results were seen by anyone involved. The proposal is recorded in the hypothesis-lineage file (WP0.11) and the AI-provenance record (WP0.8).

## 10. Signature

| Role | Name | Decision | Date |
|---|---|---|---|
| Owner | | Approve / Reject / Amend | |
| Trading-expert reviewer (D08) | | Candidate set reviewed (D19) | |
| Independent validator (D08) | | Selection rule and P3a test reviewed | |
