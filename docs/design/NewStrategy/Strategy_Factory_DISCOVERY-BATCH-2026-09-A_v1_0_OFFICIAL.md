# Strategy Factory — New Discovery Batch `DISCOVERY-BATCH-2026-09-A`

## Incremental Portfolio Value Beyond Strategy 8

| Field | Value |
|---|---|
| Version | **v1.0 — OWNER-ACCEPTED DESIGN / IMPLEMENTATION BASELINE** — supersedes v0.2 FINAL REVIEW DRAFT; acceptance binds BD-1…BD-9 subject to §17 |
| Status | **OWNER ACCEPTED / OFFICIAL DESIGN BASELINE — NOT A FROZEN RESEARCH SPEC.** BD-1…BD-9 are accepted as clarified in §17. Acceptance authorises HYPOTHESIS creation and result-blind census only where no new engineering is required; new tooling/enablers still require ATP §1 admission |
| Lifecycle state (Operating Model §6.1) | Batch: **DISCOVER → HYPOTHESIS** on acceptance (ledger entries written, §4.0). No candidate is at CENSUS until authorised; none is at FREEZE |
| Research authority | **None.** No return series may be computed for any D-candidate under this document |
| PAPER authority | None |
| Governing procedure | `Strategy_Lifecycle_and_Research_Operating_Model` (accepted) — states, census gate, trial ledger, in-sample rule, promotion gates |
| Admission | ATP §1 governs any engineering this batch needs (census tooling, data accrual, comparator artifacts). This document requests admission; it does not grant it |
| Evidence source for §1 | `docs/design/NewStrategy/NewStrategy_TrancheClosure_and_TrialLedger_2026-09-02_v1_0.md` — **PR #732, NOT YET MERGED.** ⛔ This batch may not advance past HYPOTHESIS until #732 is merged: the in-sample declaration and the C1/C2/C3 ledger entries it contains are prerequisites, not background |
| Purpose | Generate successor hypotheses from the closed C1/C2/C3 tranche and specify, before any data is read, how successors will be validated given that **no untouched historical window exists** for this candidate class (§9) |

---

## Review 1 findings applied (v0.1 → v0.2)

| # | Finding | Change |
|---|---|---|
| F1 | v0.1 §9.2 forbade reuse of C3's decisive period as untouched validation, but C3's decisive window was the **entire** `sep` tape (1997-12-31 → 2026-07-02), as were LOW-001's and MOM-001's. Taken literally, the rule makes historical decisive validation impossible for every D-candidate; taken loosely, it is decoration. v0.1 deferred the question to R7 | §9 now states the exhaustion plainly and binds a validation design that is honest about it (BD-7): historical decisive run with in-sample disclosure and a **verdict ceiling**, plus a pre-registered prospective confirmation inside the PAPER observation protocol |
| F2 | Census (read-only, zero backtests) was conflated with "discovery diagnostics" (§8 "the discovery phase may compare approaches diagnostically") that necessarily compute return series on the same exhausted tape | Exploration backtests are **prohibited** for this batch (§9.3). Allocation rule, residualisation set, and comparator are chosen by inheritance or economic argument, not by diagnostic comparison |
| F3 | §6 "correlation alone should no longer automatically define redundancy" is a loosening of the acceptance rule, adopted immediately after that rule produced a REJECT. The doc correctly says C3 is unchanged, but the motivation for the loosening is the result, which is the pattern the frozen spec exists to prevent | Redundancy retained as a pre-registered classifier with a **bound threshold and a changed consequence** (§6): it no longer REJECTs a candidate whose frozen hypothesis is incremental value, but it removes the diversification claim and routes any PASS to a JOIN-vs-REPLACE owner question. Types A/B/C converted from adjectives to numeric bounds to be owner-bound (OP-style) before the run |
| F4 | No prior-exposure accounting. Four of six hypotheses have direct predecessor programs: D2/D6 ← MF-001 V1/V2 (C2 NOT EVALUABLE), D3 ← TREND-001/TREND-003 (HOLD, MOM↔TREND corr ~0.90), D4 ← CAP-020/CAP-022/FI-003 (C1 NOT EVALUABLE; CAP-020 previously rejected as a Sharpe/Calmar improver), D1/D5 ← LOW-001/LOW-002. The Operating Model requires a ledger entry citing prior exposure at HYPOTHESIS creation | §4.0 ledger table added; each D-candidate must show which prior shots it inherits and, where a predecessor was NOT EVALUABLE, that it does not inherit the cause |
| F5 | Comparator "Strategy 8" was used as if operating. Under ATP §2.4/§5.2 Strategy 8 is IDLE / HOLD, its historical B3a proof UNPROVEN. The frozen spec's portfolio test used **Strategy 8 and Range Trader** | Comparator is the **frozen LOW-001 definition** bound by artifact (B-3 precedent), not the paper book. Range Trader retained unless it has no bindable artifact (BD-4) |
| F6 | Seven Level-B "core measures" and five §7 hypotheses with no primary named. Frozen spec §0.5.4: only named primary metrics decide | One primary, one defensive, everything else diagnostic (§7); the frozen spec's existing "decisive portfolio improvement" definition is inherited rather than re-invented |
| F7 | §8 reopened the allocation rule the spec already bound (OP-7 = equal-capital sleeves; risk-parity a named sensitivity) | OP-7 inherited by default (BD-5); a change requires an economic reason stated before any candidate data is read |
| F8 | No power consideration. The C3 standalone ΔSharpe of +0.24 could not exclude zero on 28 years; a marginal-Sharpe effect on top of a ~0.9-correlated incumbent is a smaller target | Census must produce a result-blind **minimum detectable effect** (§10 Stage 1); a candidate whose MDE exceeds any economically plausible effect is `NOT EVALUABLE — UNDERPOWERED` at census, and is not funded |
| F9 | Vocabulary drift from the accepted Operating Model (`CENSUS_WAIT`; "working disposition: HIGH PRIORITY"; decisions labelled R1–R8, colliding with review-finding numbering) | Aligned to §6.1/§5.1 of the model; priorities restated as *census-order proposals* subject to ATP §1; decisions renumbered BD-1…BD-9 with proposed defaults |
| F10 | D5's "PIT-safe crowding proxies" name data the platform does not hold; D2/D5/D6 depend on SF1, which is PIT-usable only from `datekey ≥ 2016-01-29` (~10.4 years) — the constraint that shaped C2 | Stated as census expectations (§4, §10), not verdicts, so the census is not surprised by them |

No numeric threshold, allocation weight, correlation bound, or decisive window is selected in this document. Where a value is inherited from the frozen spec it is cited, not restated as new.

---

## 1. Why this batch exists

The prior tranche closed (closure record above; #732 pending merge) with:

- **C1 (FI-003 / CAP-022 crash-insurance overlay):** NOT EVALUABLE — cause per closure record ⟨cite⟩
- **C2 (MF-001 V2 value + quality):** NOT EVALUABLE — cause per closure record ⟨cite⟩
- **C3 (LOW-002 broader-universe low volatility):** REJECT — Attempt 1 interrupted result-blind (zero credit); Attempt 2 conforming, verdict credit, bound to `3cdde216`

C3 produced discovery observations that are useful despite the REJECT. **As recorded in the closure record and not re-derived here:**

- Standalone ΔSharpe vs the OP-6-screened equal-weight benchmark was small and non-decisive.
- Drawdown protection persisted but was materially weaker than the LOW-001 record.
- Daily-return correlation with the frozen Strategy-8 reference book ≈ **0.904** → `RETURN-REDUNDANCY` under the frozen falsifier.
- Mean holdings-weight overlap ≈ **0.079** — i.e. *different stocks, same factor*.
- Tighter liquidity/price screens modestly improved the point estimate (named sensitivity).
- The unscreened full tape performed materially worse (named sensitivity).

**All of the above is in-sample discovery evidence for every successor** (closure record §4; Operating Model §12 in-sample rule). It may motivate a hypothesis. It may not supply decisive validation evidence, and — decisively — it may not be used to *choose among* mechanism variants, thresholds, or allocation rules for a successor (§9.3).

The central question for the batch:

> **Can a strategy provide measurable incremental portfolio value when the LOW-001 mechanism is already owned, even if some common-factor exposure remains?**

The objective is not to eliminate correlation with Strategy 8. It is to determine whether another strategy earns its place *after* accounting for that correlation — and to say so under rules bound before any candidate return series exists.

---

## 2. Research principle — the unit of evaluation changes

| | Framing | Decides |
|---|---|---|
| Prior tranche | Does candidate X perform well standalone? (portfolio test secondary) | Standalone primary metric |
| This batch | Does adding X to a portfolio that already holds the LOW-001 mechanism improve it enough to justify capital, complexity, turnover and risk? | **Portfolio-level primary metric under a frozen allocation rule** |

A candidate may be useful with meaningful Strategy-8 correlation if the *combined* book shows improved risk-adjusted return, lower maximum drawdown, better crash/recovery behaviour, different regime behaviour, or better capital efficiency. A candidate with an attractive standalone Sharpe can fail if it adds nothing at the portfolio level.

**This is not a new evaluation — it is the frozen spec's existing portfolio test promoted from secondary to primary.** The spec already defined *decisive portfolio improvement* (portfolio ΔSharpe CI excludes zero, **or** portfolio maxDD improves with no Sharpe degradation, under OP-7, stable across walk-forward segments) and already ruled *no promotion on standalone Sharpe alone*. This batch inherits that definition (§7) rather than inventing a parallel one.

---

## 3. Batch identity

- **Batch ID:** `DISCOVERY-BATCH-2026-09-A`
- **Theme:** Incremental portfolio value / LOW-001 complementarity
- **Family for ledger purposes:** *defensive-equity complement* (D1, D2, D4, D5) and *outside-family diversifier* (D3, D6). Multiplicity is disclosed per family and across the batch (§4.0).
- Candidate identities `D1–D6` are provisional discovery labels. They become candidate IDs (`C4…`) only inside a frozen specification, which will cite this batch and the ledger entries.

---

## 4. Candidate funnel

### 4.0 Trial-ledger entries (written at acceptance — Operating Model §5.2)

Every hypothesis below receives a ledger entry **on acceptance of this document**, before census, recording prior exposure of the same history. ⟨ledger-id⟩ fields are bound at acceptance; do not guess.

| D | Predecessor programs on the same tape | Prior shots inherited | Predecessor status | Inherited constraint the census must clear |
|---|---|---|---|---|
| D1 | LOW-001 (H1, CI [−0.03, +0.53]), LOW-002 / C3 (REJECT) | 2 | C3 REJECT on redundancy; motivating data is the C3 result itself | Residualisation set bound by economics, not by C3 diagnostics (§9.3) |
| D2 | MF-001 V1 (inconclusive), MF-001 V2 / C2 (NOT EVALUABLE); LOW-001 | 3 | C2 NOT EVALUABLE — ⟨cause⟩ | SF1 PIT floor `datekey ≥ 2016-01-29`; must show it does not inherit C2's NOT EVALUABLE cause |
| D3 | MOM-001 (approved, same tape), TREND-001, TREND-003 (HOLD, MOM↔TREND corr ~0.90) | 2–3 | TREND-003 HOLD on redundancy with MOM | Must state what distinguishes it from TREND-003; redundancy with **both** MOM-001 and LOW-001 is in scope |
| D4 | CAP-020 (rejected as Sharpe/Calmar improver), FI-003 / CAP-022 / C1 (NOT EVALUABLE) | 2 | C1 NOT EVALUABLE — ⟨cause⟩ | ATP §12: no reopening without a genuinely new prospective mechanism. "Portfolio role rather than rejected implementation" **was C1's framing**; D4 must name a mechanism C1 did not test, or it does not advance |
| D5 | LOW-001, C3 | 2 | — | Crowding / valuation proxies must exist PIT in the deepen store; expectation: `CENSUS_STOP — NO PIT SOURCE` for crowding, valuation-only variant possible on SF1 from 2016 |
| D6 | MF-001 V1/V2 (value-quality, quality), MOM-001 (momentum) for the overlapping families | 1–3 per family | as above | Each family sketched under D6 is its own ledger line; D6 is a *search space*, not one shot |

Family-wise disclosure at the batch's frozen spec: prior shots on this tape in the defensive family = LOW-001 + C3 (+ any D funded); in the trend family = MOM-001 + TREND-003 (+D3); in the fundamentals family = MF-001 V1 + C2 (+D2/D6).

### D1 — Residual Defensive Equity

**Hypothesis.** C3 recreated the broad defensive factor Strategy 8 already owns. A defensive signal built from the component that remains after neutralising a **pre-declared** set of exposures associated with Strategy 8 may retain defensive behaviour with less dependence on the owned mechanism.

**Residualisation set.** One set, bound in the frozen spec by economic argument before any candidate return is computed — e.g. market beta, sector, size, and realised-volatility rank (Strategy 8's own ranking variable). ⛔ v0.1 listed six possible neutralisations "for discovery"; choosing among them by looking at which reduces correlation most *is* fitting to the C3 result. Alternative sets are named sensitivities, not candidates.

**Economic thesis.** Defensive return earned through a channel other than the low-realised-vol ranking already owned.

**Falsifiers (to be numerically bound).** Residualisation destroys the defensive drawdown advantage; residual signal has no cross-sectional return spread; or the residual book's marginal contribution under the frozen allocation is indistinguishable from zero.

**Census expectation.** Data-feasible (all inputs derive from `sep`); the risk is signal, not data. MDE must be computed.

**Census-order proposal:** 1st.

### D2 — Defensive Quality / Balance-Sheet Resilience

**Hypothesis.** Low-volatility behaviour is most valuable when it identifies economically resilient firms rather than merely low realised volatility. A quality-resilience book may share defensive beta while earning through a company-level mechanism.

**Measures (one set, bound before the run):** profitability, earnings stability, leverage, interest coverage, cash generation, margin durability — drawn from SF1 under the frozen PIT rules (`datekey` key; `ARQ/ART` dimensions; never `MR*`).

**Inherited constraint.** SF1 PIT floor `datekey ≥ 2016-01-29`, ~10.4 years — the window that left C2 under-powered/NOT EVALUABLE. Census must show the marginal test is resolvable on that window; if not, `CENSUS_WAIT — UNDERPOWERED` is correct when governed accrual can plausibly cure the deficiency; otherwise `CENSUS_STOP`.

**Census-order proposal:** 4th.

### D3 — Trend / Defensive Regime Complement

**Hypothesis.** A trend mechanism (persistence, regime adaptation) complements cross-sectional defensiveness because its return source is different; its value is concentrated in periods where Strategy 8 is weak.

**Direction (one, bound before the run):** medium-term trend with an explicit whipsaw control. ⛔ v0.1's six directions are a search space; the spec freezes one and names the rest as sensitivities or future ledger lines.

**Inherited constraint.** TREND-003 was held because its correlation with MOM-001 was ~0.90. D3 must state what distinguishes it from TREND-003 and is tested for redundancy against **both** MOM-001 (B-5 artifact) and LOW-001. A candidate that is redundant with MOM-001 but complementary to LOW-001 is a legitimate finding — it is a portfolio question about MOM-001, and must be recorded as such rather than argued away.

**Census-order proposal:** 2nd.

### D4 — Explicit Tail / Crash-Response Overlay

**Hypothesis.** Crash response as a *portfolio* overlay on the incumbent set.

**Blocking condition.** This is the C1 framing. C1 was NOT EVALUABLE; CAP-020 was previously rejected as a return improver. ATP §12 prohibits reopening a rejected strategy without a genuinely new prospective mechanism. D4 advances to census only if (a) the C1 NOT EVALUABLE cause is identified in the closure record and shown not to apply, **and** (b) the spec names a mechanism C1/CAP-020 did not test (e.g. a cross-sectional crash-resilience ranking rather than a market-level trend gate). Otherwise D4 is `HYPOTHESIS — BLOCKED` and stays in the ledger.

**Census-order proposal:** none until unblocked.

### D5 — Anti-Crowding / Valuation-Aware Defensive Strategy

**Hypothesis.** A valuation-aware defensive book retains defensiveness while avoiding the most expensive or crowded members of the factor.

**Census expectation.** The platform holds no PIT holdings, flow, or positioning data; "crowding proxies" therefore have no PIT source and that component is expected to fail census. A valuation-only variant is feasible on SF1 from 2016 with the D2 power caveat. Stated here so the census is not surprised, and so the census cannot be quietly widened into an exploration to find a proxy that "works".

**Census-order proposal:** 5th (valuation-only variant), crowding component `CENSUS_STOP` expected.

### D6 — Cross-Sectional Diversifier Outside the Defensive Family

**Hypothesis.** The best complement to Strategy 8 may not be defensive at all.

**Structure.** D6 is a search space (profitability/quality, earnings revision, idiosyncratic momentum, capital efficiency, cash-flow quality, conservative investment, multi-factor residual ranking). Each family is a ledger line with its own predecessor exposure (§4.0). The frozen spec may take **at most one** D6 family per batch, chosen by economic argument and prior-ledger status — not by scanning the families on the tape (§9.3).

**Census-order proposal:** 3rd, one family only.

---

## 5. Two-level evaluation framework

### Level A — candidate economics (diagnostic)

Net return, Sharpe, maxDD, turnover, cost sensitivity, walk-forward stability, concentration, implementation feasibility. **Necessary diagnostics; never sufficient; never the primary.**

### Level B — incremental portfolio economics (decisive)

Compare, under one prospectively frozen allocation rule (§8):

- **Portfolio A:** incumbent set (BD-4) alone
- **Portfolio B:** incumbent set + candidate

Diagnostic measures (all reported, none decisive unless named primary/defensive in §7): marginal Sharpe; marginal maxDD; downside complementarity in incumbent drawdowns; conditional correlation (normal / falling / high-vol / incumbent-losing regimes, regime definitions frozen); recovery contribution (time-to-recovery, drawdown duration); capital efficiency; concentration effects.

---

## 6. Redundancy policy for the batch (retained, with a changed consequence)

Correlation stays in the contract. What changes is what it *does*.

| Class | Definition (bounds to be owner-bound before the run; OP-style) | Consequence |
|---|---|---|
| **SAME-FACTOR** | Unconditional daily-return correlation with the LOW-001 reference book **> θ_corr** *(proposed inheritance: 0.85, the frozen C3 value; a different value needs an economic argument stated before any candidate data is read)* | Recorded as `RETURN-REDUNDANCY`. No independent-diversification claim may be made. A PASS on the §7 primary is still a PASS, but it is routed at PROMOTE as a **JOIN-vs-REPLACE** owner question (Operating Model §13) rather than as an additional sleeve |
| **BENIGN OVERLAP** | Correlation between **θ_low** and **θ_corr** *and* the §7 defensive hypothesis is met | Diversification claim limited to the defensive/tail dimension actually demonstrated |
| **COMPLEMENT** | Correlation **≤ θ_low** *and* §7 primary met | Full diversification claim |

⛔ **"Different timing", "different conditional behaviour", "meaningful benefit"** are adjectives. The frozen spec converts each to a number (frozen-spec R4 precedent) or drops it. Conditional-correlation regimes are defined by frozen rules (e.g. incumbent trailing-63-day drawdown > x%), not by inspection.

**This does not change C3.** C3 remains REJECT under its frozen specification and its `> 0.85` falsifier. The consequence change applies only to candidates whose *frozen* hypothesis is incremental value, and it is adopted here — before any successor exists — precisely so that it cannot be adopted later in response to a successor's result.

---

## 7. Hypothesis structure for the frozen specification

Inherited from the frozen spec's portfolio test; one primary, one defensive, everything else diagnostic (spec §0.5.4).

| Role | Statement | Estimator |
|---|---|---|
| **Primary** | Portfolio ΔSharpe (B − A) under the frozen allocation rule has a CI that excludes zero | B-4 `paired_sharpe_diff_ci`, same artifact + SHA as the prior tranche, so results are comparable |
| **Defensive** | Portfolio maxDD improves by **≥ OP-x** (to be bound) with no Sharpe degradation, stable across the frozen walk-forward segments | frozen |
| Complementarity | The candidate's contribution is not explained by duplicating the incumbent — operationalised by §6 classification, not by narrative | frozen classifier |
| Cost | Primary/defensive survive the frozen cost sweep (through the incumbent's demonstrated cost-robustness level, 50 bps precedent) | frozen |
| Stability | Contribution sign preserved in the leave-one-segment-out set | frozen |

**Verdict set:** PASS · REVISE · REJECT · NOT EVALUABLE — with the **ceiling in §9.2**.

Exact thresholds are bound after census and before any decisive output is read (§14). The census may inform *feasibility* of a threshold (power), never its *value* from candidate data.

---

## 8. Allocation rule — inherited, not shopped

**Default (BD-5): inherit OP-7** — equal-capital sleeves at each rebalance, risk-parity as a named sensitivity. It is already owner-bound, already used for the prior tranche's portfolio test, and comparability across tranches is worth more than a marginally better rule.

A different decisive rule (equal-risk contribution, fixed core/satellite, volatility-targeted) may be proposed **only with an economic reason stated before any candidate return series is computed**, and becomes an owner parameter bound in the spec.

⛔ **No diagnostic comparison of allocation rules on candidate data.** Comparing rules on the tape and picking the one that makes Portfolio B look best is weight fitting; it is exactly the overfitting risk v0.1 §8 named, and the only mechanism that prevents it is not doing it.

---

## 9. The in-sample problem — stated, not deferred

### 9.1 The tape is exhausted for this candidate class

The C3 decisive window was 1997-12-31 → 2026-07-02 — the full `sep` history in the deepen store. So were LOW-001's and MOM-001's. The incumbent comparator (LOW-001) was validated on the same history, and the C3 result that motivates D1 was observed on it. **There is no untouched historical window in `sep` for any cross-sectional equity candidate evaluated against Strategy 8.** For SF1-dependent candidates the usable history is shorter (2016→), and all of it was read by C2.

The only untouched data is what accrues after 2026-07-02. The live store is refreshed daily, carries no SF1, and is not a research dataset. A governed accrual mechanism for the research store is therefore a **REQUIRED ENABLER** to be admitted through ATP §1 if prospective research-plane validation is ever wanted (§13).

### 9.2 Validation design (BD-7) — governed historical in-sample adjudication run with a verdict ceiling, then prospective confirmation in PAPER

Rather than pretend an untouched historical holdout exists, the batch binds this structure:

1. **The frozen spec declares the decisive window in-sample** for the family, cites the ledger entries and the number of prior shots, and states the family-wise disclosure.
2. **One governed historical in-sample adjudication run per candidate** under the one-run rule. Verdicts available: REJECT, REVISE, NOT EVALUABLE, or **PASS-IN-SAMPLE**. There is no unqualified PASS from this run; that is the ceiling.
3. **PASS-IN-SAMPLE earns exactly one thing:** eligibility to enter PROMOTE-gate evaluation (Operating Model §8), which then require a frozen PAPER observation protocol containing a **pre-registered prospective confirmation**: the marginal-contribution sign and the thesis-health envelope (Operating Model §9.1) over the observation window, measured against the frozen incumbent reference, with the disposition set (KEEP / PAUSE / RETIRE) pre-declared. Capital scaling beyond the initial PAPER allocation is not available until that confirmation is recorded.
4. **Honesty about power.** A one-quarter PAPER window cannot make a marginal-Sharpe CI exclude zero. The prospective confirmation tests sign, envelope conformance, and no-blow-up; it does not upgrade the in-sample verdict, and nothing in this design pretends otherwise. The in-sample historical run remains the economic verdict of record, labelled as such.

**Alternative considered (stricter):** a governed research-store accrual holdout, frozen before it exists (MR-002 Validation-2 / VA-3 pattern), with no historical decisive run. Rejected as the default because (a) the accrual mechanism does not exist, (b) it delays every candidate by the accrual length, and (c) at plausible effect sizes a 1–2 year accrual is under-powered for the same reason as (4). It remains available as an owner choice under BD-7.

### 9.3 Anti-overfitting controls — mechanisms

| # | Control | Mechanism (what enforces it) |
|---|---|---|
| 1 | C3 outputs are in-sample only | Closure record §4 in-sample declaration (merged #732); ledger entries cite it |
| 2 | No exploration backtests in this batch | Census computes **no return series**; the first candidate return series is the decisive run. Any earlier computation is a ledgered shot and disqualifies the run from PASS-IN-SAMPLE |
| 3 | C3 sensitivity winners may motivate, not set, thresholds | Thresholds are bound as owner parameters with an economic rationale recorded; the spec states none was derived from C3 sensitivities |
| 4 | Candidate definitions frozen before outputs are read | Frozen-spec custody gate (MERGED, not local/PR) + execution-input freeze (parameter artifact SHA-256, seeds, code commit) |
| 5 | Allocation rule frozen | OP-7 inheritance (§8); any change bound before data |
| 6 | Redundancy classifier frozen | §6 bounds bound as OP-style parameters |
| 7 | Every failure stays in the ledger | Ledger entries exist from acceptance, before census (§4.0) |
| 8 | No candidate must PASS because the prior tranche produced zero PAPER candidates | Scorecard is PASS-neutral (Operating Model §16); the batch's success definition is §12 |
| 9 | Standalone metrics rescue nothing | Level A is diagnostic by construction (§5) |
| 10 | Modest standalone may PASS if the frozen role is valuable | Role declared in the spec before the run (Operating Model §13) |
| 11 | **Search spaces are not candidates** | D1 residualisation set, D3 direction, D6 family — one each, chosen by argument and ledger status; alternatives are sensitivities or future ledger lines |

---

## 10. Discovery sequence

### Stage 1 — Census (result-blind; NO-START)

Authorised by acceptance of this document, in the census order of §4, subject to ATP §1 admission of any tooling it needs. For each candidate, measure **without computing any candidate return series**:

- required PIT fields and their sources; PIT keys and floors; available history; universe coverage; survivorship controls;
- comparator availability: the incumbent reference book(s) reconstructable from bound artifacts (BD-4);
- execution feasibility (tradability under OP-6 or a stated successor screen);
- **minimum detectable effect** for the §7 primary under the B-4 estimator, computed from the incumbent's own return series and an assumed-correlation grid — no candidate data is needed for this, so it is result-blind by construction;
- whether the candidate inherits a predecessor's NOT EVALUABLE cause (§4.0).

Outputs use the Operating Model census vocabulary only: `CENSUS_PASS` · `CENSUS_WAIT — <reason>` · `CENSUS_STOP — <reason>`. `NOT EVALUABLE` remains a research-verdict term. An underpowered candidate that governed accrual can plausibly cure is `CENSUS_WAIT — UNDERPOWERED`; no admissible remedy is `CENSUS_STOP`.

### Stage 2 — Mechanism sketches (CENSUS_PASS candidates only)

Economic mechanism; expected portfolio role; expected failure mode; relationship to each incumbent; falsifier; implementation burden; **the one** residualisation set / direction / family the spec will freeze, with its economic argument.

### Stage 3 — Candidate ranking for freeze

Ranked for research priority — explicitly **not** for expected PASS probability — on mechanism independence from the incumbents, potential portfolio contribution, MDE vs plausible effect, PIT data quality, implementation practicality, cost realism, and stakeholder explanatory value.

### Stage 4 — Freeze

Select **2–3 candidates on census evidence, not desired survivor count.** Author the frozen specification in the v1.2 format: dataset identities re-measured, inherited-mechanism binding table (incumbent books, estimator, screens — artifact + SHA-256), owner parameters (θ_corr, θ_low, OP-x, allocation rule) with proposed defaults, in-sample declaration and family-wise disclosure, one primary + one defensive, verdict ceiling per §9.2. Owner acceptance; MERGED custody; only then decisive research authorised.

### Stage 5 — Decisive validation

One decisive run per candidate; result recorded whatever it is; adjudication package in the v1.2 §11 format, with rank **#1 PAPER PROMOTION CANDIDATE / #2 NEXT / #3 RESEARCH-ONLY, REVISE, OR REJECT** — where "promotion candidate" means eligible for the §9.2 prospective confirmation, not promoted.

---

## 11. Census-order proposal

Subject to census and to ATP §1 admission of any required tooling:

1. **D1 Residual Defensive Equity** — direct scientific successor to C3; feasible on `sep` alone.
2. **D3 Trend / Defensive Regime Complement** — materially different mechanism; must clear the TREND-003 redundancy question against MOM-001 as well.
3. **D6 Outside-family diversifier — one family** — prevents anchoring on the defensive family.
4. **D2 Defensive Quality** — strong rationale; SF1 window/power caveat.
5. **D5 valuation-only variant** — crowding component expected to STOP at census.
- **D4** — `HYPOTHESIS — BLOCKED` until the two §4 conditions are met.

---

## 12. What success means for this batch

Success is **not** "produce three PASS strategies."

Success means the Strategy Factory can answer credibly: *we already own the LOW-001 mechanism; what additional strategy deserves capital, and why — or why none currently does?*

A candidate may retain common defensive exposure if, under the frozen allocation rule, it improves the incumbent portfolio's risk-adjusted return or downside behaviour with acceptable costs and stable contribution, and the frozen classifier says what kind of claim that supports. A candidate with strong standalone performance and no marginal contribution is rejected. A census that stops four of six candidates before any code is written is a success. **All of these are successful outputs.**

---

## 13. What this batch asks ATP to admit (§1 admission test applies to each)

| Item | Class | Serves | Stop rule |
|---|---|---|---|
| Census tooling: PIT field inventory, MDE calculator on incumbent returns (B-4 estimator), comparator reconstruction from bound artifacts | REQUIRED ENABLER | D1–D6 census | Zero candidate return series; time-boxed; read-only against the deepen store |
| Incumbent reference books as bound artifacts (LOW-001 per B-3; Range Trader if bindable; MOM-001 per B-5 for D3 redundancy) | REQUIRED ENABLER | BD-4 | If an incumbent cannot be bound by artifact + SHA-256 it is not a comparator |
| Research-store accrual snapshots (governed, sealed, periodic) | REQUIRED ENABLER — **only if** BD-7 selects the accrual-holdout alternative | prospective validation | Otherwise DEFER; do not build accrual infrastructure without a named consumer |

Nothing here is admitted by this document.

---

## 14. Owner decisions before freeze (BD-1 … BD-9)

Owner-accepted defaults. They govern this batch as design decisions subject to §17; they do not freeze a candidate or authorise a candidate return series.

| # | Decision | Proposed default | Rationale |
|---|---|---|---|
| BD-1 | Theme | **Incremental portfolio value beyond the LOW-001 mechanism** | Inherits the spec's portfolio test as primary (§2) |
| BD-2 | Funnel | **D1, D2, D3, D5 (valuation-only), D6 (one family) to HYPOTHESIS with ledger entries; D4 HYPOTHESIS — BLOCKED** | §4.0 prior-exposure accounting; ATP §12 |
| BD-3 | Census order | **D1 → D3 → D6 → D2 → D5** | §11 |
| BD-4 | Incumbent comparator set | **Frozen LOW-001 definition (B-3 artifact) as primary incumbent; Range Trader included iff bindable by artifact + SHA-256; MOM-001 (B-5) as redundancy comparator for D3 only.** The Strategy-8 *paper book* is not the comparator | Strategy 8 is IDLE/HOLD with unproven historical proof (ATP §2.4); the spec's prior portfolio test used S8 + Range Trader |
| BD-5 | Allocation rule | **Inherit OP-7** (equal-capital sleeves; risk-parity a named sensitivity) | Comparability; no rule shopping (§8) |
| BD-6 | Redundancy classifier | **Retain θ_corr = 0.85 by inheritance with the §6 consequence change; θ_low proposed at census with economic argument, bound before the run** | Loosening the threshold after it fired is the pattern to avoid; changing the *consequence* prospectively is defensible |
| BD-7 | Validation design | **Historical decisive run with in-sample declaration and PASS-IN-SAMPLE ceiling, plus pre-registered prospective confirmation in the PAPER observation protocol (§9.2).** Accrual-holdout alternative available at owner's election | No untouched history exists; this design is honest about it and reuses existing machinery |
| BD-8 | Power gate at census | **Candidate is `CENSUS_WAIT — UNDERPOWERED` if the MDE exceeds the largest prospectively claimed plausible effect and governed accrual could cure the deficiency; otherwise `CENSUS_STOP`. The plausible effect is written before MDE is computed** | Don't fund shots that cannot resolve; F8 |
| BD-9 | Freeze count | **2–3, on census evidence; zero is an acceptable outcome** | §10 Stage 4; §12 |

⛔ No numeric PASS threshold, allocation weight, `θ_low`, defensive threshold, or decisive window is selected until census and mechanism review are complete — and none is ever derived from candidate data. `θ_corr = 0.85` is the sole correlation bound accepted now, by explicit inheritance under BD-6.

---

## 15. Proposed stakeholder narrative

*Prior tranche:* "We tested whether simply expanding the low-volatility universe creates another independent strategy. It does not: the book held different stocks but behaved like the same factor, so we rejected it rather than adding redundant paper capital."

*This batch:* "We now judge candidates by their marginal contribution to the portfolio we already hold, under rules fixed before we look — including an honest statement that the historical record is already in-sample for this family, and what that means for how much a historical result can claim."

---

## 16. What this document does NOT authorise

- Any candidate return series, backtest, or diagnostic comparison on the deepen store or any research store.
- Any change to the frozen C1/C2/C3 specification, the closure record, or the C3 verdict.
- Freezing any successor specification; research capital for any D-candidate.
- Engineering of census tooling, comparator artifacts, or accrual snapshots — each is an ATP §1 admission.
- Implementation, account binding, scheduler change, deployment, PAPER activation, or orders.
- Reading any post-2026-07-02 accrued data for any research purpose.
- Reopening CAP-020 / C1 (D4) without the two §4 conditions.

---

## Current proposed state

```
DISCOVERY-BATCH-2026-09-A  = OWNER ACCEPTED / OFFICIAL DESIGN BASELINE / NO CANDIDATE RETURN-SERIES AUTHORITY
THEME                      = INCREMENTAL PORTFOLIO VALUE BEYOND THE LOW-001 MECHANISM
C3 RESULTS                 = MOTIVATING / IN-SAMPLE FOR SUCCESSORS / ZERO SUCCESSOR VERDICT CREDIT
HISTORICAL TAPE            = IN-SAMPLE FOR THIS CANDIDATE CLASS (DECLARED, §9.1)
PREREQUISITE               = PR #732 MERGED (closure record + ledger entries)
NEXT GATE                  = PR #732 MERGED → D-LEDGER ENTRIES WRITTEN → RESULT-BLIND CENSUS (D1 first), subject to ATP §1 admission for any new tooling
```

---

## 17. Review 2 acceptance clarifications

The owner accepts **BD-1 through BD-9** with these authority/vocabulary clarifications:

1. Census uses only `CENSUS_PASS`, `CENSUS_WAIT — <reason>`, and `CENSUS_STOP — <reason>`. `PASS / REVISE / REJECT / NOT EVALUABLE` is reserved for research adjudication after a frozen specification authorises a run.
2. BD-6 binds `θ_corr = 0.85` now by inheritance. `θ_low` remains unbound until post-census freeze; candidate data may not choose it.
3. The historical run is explicitly in-sample. It may produce `PASS-IN-SAMPLE`, never unqualified PASS. That permits PROMOTE-gate evaluation only; it is not PAPER authority.
4. Acceptance does not admit engineering. Existing read-only capabilities may support census after #732 and D-ledger creation. New tooling, comparator reconstruction, or accrual machinery requires ATP §1 admission.
5. D4 remains blocked and receives no census execution until both §4 conditions are satisfied.
6. No post-2026-07-02 data may be read for candidate research under this baseline.

---

## 18. Official implementation and parallel-execution plan

### 18.1 P0 — hard prerequisite, serialized

1. Verify PR #732 is merged and record its exact merge SHA.
2. Verify the closure record contains C1/C2/C3 dispositions, C3 in-sample declaration, Attempt-1/Attempt-2 history, and prior trial-ledger entries.
3. Create D1/D2/D3/D5/D6 HYPOTHESIS ledger entries with predecessor exposure; record D4 as `HYPOTHESIS — BLOCKED`.
4. Record exact ledger IDs; never invent placeholders.

**P0 barrier:** no census starts before #732 proof and D-ledger creation.

### 18.2 Parallel result-blind census lanes after P0

**Lane A — D1:** inventory `sep`/PIT inputs for one pre-declared residualisation set; prove LOW-001 comparator reconstruction; compute MDE using incumbent returns plus assumed-correlation grid only; no D1 return series.

**Lane B — D3:** state its distinction from TREND-003 before returns; bind LOW-001 and MOM-001 reference artifacts; inventory PIT trend/whipsaw inputs; compute incumbent-only MDE; no D3 return series.

**Lane C — D6:** choose exactly one outside-family mechanism by economic argument and ledger status before returns; inventory PIT/history and predecessor exposure; compute incumbent-only MDE; do not scan families for historical winners.

**Lane D — D2/D5:** D2 verifies SF1 `ARQ/ART`, `datekey`, PIT floor, inherited C2 cause, and MDE feasibility. D5 tests source availability only; no proxy shopping. Missing PIT crowding source → `CENSUS_STOP — NO PIT SOURCE` for crowding; valuation-only assessed separately.

**Lane E — ATP enabler admission:** identify missing census/comparator/MDE capabilities. Each missing capability gets its own ATP §1 admission statement with named candidate, benefit, time-box/stop, and next gate. Do not implement unadmitted tooling. Accrual remains DEFER unless separately selected under BD-7.

### 18.3 Census convergence barrier

Assemble one evidence matrix for D1, D3, D6, D2, D5 and blocked D4. Prove zero candidate return series were computed; MDE used only incumbent/reference data plus assumed-correlation inputs; predecessor exposures are ledgered; comparator artifacts are bound by artifact identity + SHA-256.

**No mechanism freeze or candidate backtest before owner review of the complete census matrix.**

### 18.4 Post-census — parallel preparation, serialized authority

Mechanism sketches, artifact remeasurement, parameter rationale, and implementation-burden analysis may be prepared in parallel for `CENSUS_PASS` candidates. Candidate selection (2–3), `θ_low`, defensive threshold, any allocation-rule change, decisive window, frozen-spec acceptance, and custody are serialized owner decisions.

### 18.5 Research execution

After a frozen spec is merged and execution authority exists, candidate runs may execute in parallel only with isolated immutable inputs and output namespaces and no shared mutable state. Seal each result before interpretation. One candidate's result may not alter another's frozen parameters. Economic disappointment never authorises a rerun.

### 18.6 Promotion / PAPER

Promotion, JOIN-vs-REPLACE rulings, account allocation, deployment, scheduler changes, PAPER activation, and orders are serialized. `PASS-IN-SAMPLE` is not activation authority. Separate PAPER authority plus the pre-registered prospective confirmation protocol is required.

---

## 19. Immediate execution directive

```text
DISCOVERY-BATCH-2026-09-A = OWNER ACCEPTED / DESIGN BASELINE
RETURN SERIES              = NOT AUTHORIZED
P0                         = VERIFY #732 -> WRITE D-LEDGER ENTRIES
THEN PARALLEL              = D1 CENSUS || D3 CENSUS || D6 CENSUS || D2/D5 CENSUS || ATP ENABLER ADMISSION
D4                         = HYPOTHESIS — BLOCKED
CENSUS OUTPUT              = CENSUS_PASS | CENSUS_WAIT — reason | CENSUS_STOP — reason
NEXT OWNER GATE            = COMPLETE CENSUS MATRIX REVIEW
NO BACKTEST BEFORE         = FROZEN SPEC MERGED + EXECUTION AUTHORITY
```

