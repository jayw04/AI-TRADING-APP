# `DISCOVERY-BATCH-2026-09-A` — trial-ledger entries D1 … D6

| Field | Value |
|---|---|
| Version | **v1.0 — P0 OUTPUT, created at batch acceptance** |
| Status | **LEDGER OF RECORD for the batch's prior-exposure accounting.** Not a frozen research specification; not a census output; not a verdict. |
| Created | 2026-09-03, on completion of the P0 barrier (§18.1 of the batch baseline) |
| Governing procedure | `docs/design/Lifecycle/Strategy_Lifecycle_and_Research_Operating_Model_v1_0.md` §5.2 (trial ledger and multiplicity), §6.1 (lifecycle states), §12 (in-sample rule) |
| Batch baseline | `docs/design/NewStrategy/Strategy_Factory_DISCOVERY-BATCH-2026-09-A_v1_0_OFFICIAL.md` — owner-accepted design baseline, custodied verbatim alongside this record |
| Prerequisite discharged | **PR #732 MERGED** — squash `3bc28fd67910198e6a929d5fac56f302cc800e4c`, 2026-09-03T02:50:51Z. The closure record and its in-sample declaration are on `main` (§5) |
| Research authority | **None.** No candidate return series, backtest, or diagnostic comparison is authorised by this record |
| Purpose | Record, at hypothesis creation and before any census, the prior exposure of the same history to related tests — so that multiplicity is disclosed rather than reconstructed later |

⛔ **This record creates no research capital, no freeze, no engineering admission, no PAPER authority, and no candidate return series.** It is the accounting artifact the Operating Model requires to exist *before* census.

---

## 0. P0 discharge record

| P0 step (§18.1) | Result |
|---|---|
| 1. Verify PR #732 merged; record exact merge SHA | **DONE** — MERGED 2026-09-03T02:50:51Z, squash commit **`3bc28fd67910198e6a929d5fac56f302cc800e4c`**. Closure record present on `origin/main` at `docs/design/NewStrategy/NewStrategy_TrancheClosure_and_TrialLedger_2026-09-02_v1_0.md`, 15,676 B, sha256 `1f15c5de1a08be256c9cb33590c582bbe7c7ef03558a9721542a559a89ea5fd3` |
| 2. Verify closure record contains C1/C2/C3 dispositions, the C3 in-sample declaration, Attempt-1/Attempt-2 history, and prior trial-ledger entries | **DONE** — all four present and verified against the merged blob, not against a branch copy |
| 3. Create D1/D2/D3/D5/D6 HYPOTHESIS ledger entries with predecessor exposure | **DONE** — §2 below |
| 4. Record D4 as `HYPOTHESIS — BLOCKED`; record exact ledger IDs, never placeholders | **DONE** — §1 and §2.4 |

## 1. Ledger identifiers — bound

The repository holds no prior identifier convention for research trial-ledger entries. Governed identifiers here take the form `SCOPE-TOPIC-NNN`. The following are **bound at creation** and are the exact IDs a frozen specification must cite. They are not placeholders and carry no economic content; they may be replaced only by an owner ruling issued before a frozen specification cites them.

| Ledger ID | Candidate | Lifecycle state (Operating Model §6.1) |
|---|---|---|
| `TL-2026-09-A-001` | D1 — Residual Defensive Equity | HYPOTHESIS |
| `TL-2026-09-A-002` | D2 — Defensive Quality / Balance-Sheet Resilience | HYPOTHESIS |
| `TL-2026-09-A-003` | D3 — Trend / Defensive Regime Complement | HYPOTHESIS |
| `TL-2026-09-A-004` | D4 — Explicit Tail / Crash-Response Overlay | **HYPOTHESIS — BLOCKED** |
| `TL-2026-09-A-005` | D5 — Anti-Crowding / Valuation-Aware Defensive | HYPOTHESIS |
| `TL-2026-09-A-006` | D6 — Cross-Sectional Diversifier Outside the Defensive Family | HYPOTHESIS (search space; operative line binds at family selection) |

⛔ **No candidate is at CENSUS by virtue of this record.** Census execution for D1/D2/D3/D5/D6 is authorised separately by the owner directive of 2026-09-03 upon discharge of P0, and remains subject to ATP §1 admission for any tooling it requires. D4 receives no census.

## 2. Entries

Every "decisive shot" below is a completed pre-registered decisive run whose result was recorded, per Operating Model §5.2. Tape is stated because prior exposure is exposure *of the same history*; a predecessor on a different tape is disclosed but is not the same-history shot.

### 2.1 `TL-2026-09-A-001` — D1 Residual Defensive Equity

**Hypothesis.** A defensive signal built from the component remaining after neutralising a pre-declared set of exposures associated with the owned low-volatility mechanism may retain defensive behaviour with less dependence on that mechanism.
**Family.** Defensive-equity complement.

| Predecessor | Decisive shots | Tape | Status | Custody |
|---|---|---|---|---|
| LOW-001 | 1 | `sep` equity, 2000-01-01 → 2026-06-12, n=200 | **inconclusive**; verdict of record "B — Diversifier / Defensive"; H1 ΔSharpe **+0.241**, CI **[−0.029, +0.53]** | `docs/implementation/evidence/low_001_low_volatility/low_volatility.json` |
| LOW-002 / C3 | 1 conforming (Attempt 1 interrupted, result-blind, **zero verdict credit**) | `sep` equity via the OP-6 screen, 2017-01-09 → 2026-06-12 | **REJECT** — CI spans zero; DD advantage 0.0367 < 0.3024; S8 return correlation 0.904 > 0.85 | closure record §2, §3 |

**Same-history shots inherited: 2.**

**Inherited constraint the census must clear.** The residualisation set is bound in the frozen specification by economic argument before any candidate return series exists. ⛔ Choosing among candidate neutralisations by observing which most reduces correlation with the incumbent would be fitting to the C3 result, which is in-sample. Alternative sets are named sensitivities, never candidates.
**Census order.** 1st.

### 2.2 `TL-2026-09-A-002` — D2 Defensive Quality / Balance-Sheet Resilience

**Hypothesis.** Low-volatility behaviour is most valuable when it identifies economically resilient firms rather than merely low realised volatility.
**Family.** Defensive-equity complement, fundamentals-dependent.

| Predecessor | Decisive shots | Tape | Status | Custody |
|---|---|---|---|---|
| MF-001 V1 | 1 (`EXP-20260621-155951-sf1mf`) | SF1 + `sep`, 2017-01-01 → 2026-03-31, n=200 | **inconclusive** — ΔSharpe +0.04, CI [−0.35, +0.48] | `docs/implementation/TradingWorkbench_P14_Session1_MultiFactorRetest_Results_v0.1.md`; `apps/backend/app/research/programs.py` |
| MF-001 V2 / C2 | 1 (spent; **zero primary verdict credit**) | SF1 `ARQ`/`ART` + `sep` | **NOT EVALUABLE** | Amendment A §3.6, §3.7, §3.8 |
| LOW-001 | 1 | `sep` equity | **inconclusive** (defensive-family overlap) | as §2.1 |

**Same-history shots inherited: 3.**

**Inherited constraint the census must clear.** D2 must show it does not inherit C2's not-evaluable cause. That cause is, per Amendment A:
- `C2-RETURN-ALIGNMENT-001` — the bound estimator computes `n = min(len(a), len(b))` and slices **positionally**, while the two inputs began 125 trading days apart; the registered ΔSharpe and CI therefore carry zero primary verdict credit, and "no rerun fixes it";
- `C2-DIVERSIFICATION-COMPARATOR-001` — the frozen diversification clause required comparator series that do not exist for the period.

Accordingly the census must demonstrate, before any freeze, an explicit date-alignment contract, a persisted return-series contract, actual-curve window reporting, and comparator identities with the histories they require.

⚠ **Correction of record (§4.2).** The SF1 point-in-time floor `datekey ≥ 2016-01-29` is a genuine **data** constraint on D2 and is inherited as such. It is **not** C2's not-evaluable cause. Amendment A §1 records that "SF1 `datekey` coverage is 88–97 % of the eligible universe throughout 2017+, **so C2 is not further constrained**", and the binding window limit was the `sep` price-ingest defect boundary 2017-01-06 → 2026-06-12 (≈9.43 years), not SF1.

**PIT rules inherited.** Key on `datekey`, never `calendardate`; dimensions `ARQ`/`ART` only, never `MR*`; a row becomes usable at the first rebalance strictly after its `datekey`.
**Census order.** 4th.

### 2.3 `TL-2026-09-A-003` — D3 Trend / Defensive Regime Complement

**Hypothesis.** A trend mechanism complements cross-sectional defensiveness because its return source is different, with value concentrated where the incumbent is weak.
**Family.** Outside-family diversifier (trend).

| Predecessor | Decisive shots | Tape | Status | Custody |
|---|---|---|---|---|
| MOM-001 | 1 (`EXP-20260620-193645`) | `sep` equity — **same tape as the incumbent** | **validated / production** — Sharpe 0.48, CI [0.13, 0.85], p=0.003 | `apps/backend/app/research/programs.py`; `docs/implementation/TradingWorkbench_P12_Session1_EdgeEvidence_Results_v0.1.md` |
| TREND-001 | 1 pre-registered | multi-asset, 10-ETF, monthly, 2007 → 2026 | **inconclusive — POWER-limited**, explicitly not an ordinary rejection | `apps/backend/app/research/programs.py`; `docs/implementation/evidence/trend_001/` |
| TREND-002 | 1 pre-registered | equity + bond core-6, ~24 years | **inconclusive — power failure** | `apps/backend/app/research/programs.py`; `docs/implementation/evidence/trend_002/` |
| TREND-003 | **0** | — | **HOLD — never chartered, never run.** A proposed candidate (`C4`) in the Candidate Inventory only; absent from the program registry and from `factor_lab/configs.py` | `NewStrategy_CandidateInventory_2026-09-01_v1_0.md`; `NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL.md` |

**Same-history shots inherited: 3** (MOM-001, TREND-001, TREND-002). TREND-003 contributes none.

**Redundancy prior — inherited, not measured on any D3 construction.** FI-001 Phase 1 measured MOM ↔ TREND full-period correlation **0.90**, stress correlation 0.89, rolling-63-day range **0.60 … 0.99**, holdings overlap 18.7%. It was measured on **TREND-001's equity per-name 200-day-SMA book** over **2019 → 2026 at n=150**, and the source records that its absolute correlations run higher than full-cycle priors so that only the sign and ordering transfer. TREND-003 is proposed as a multi-asset ETF time-series-momentum book, a different construction. ⛔ This figure may be cited as a prior; it may not be presented as a measurement of D3 or of TREND-003.

**Inherited constraint the census must clear.** D3 must state what distinguishes it from TREND-003's proposed construction, and is tested for redundancy against **both** MOM-001 (B-5 artifact) and LOW-001 (B-3 artifact). A candidate redundant with MOM-001 but complementary to LOW-001 is a legitimate finding and is recorded as a portfolio question about MOM-001, not argued away.

⚠ **Comparator-reconstruction lead for the census (not a determination).** No `MOM_001` program specification exists in `factor_lab/configs.py`, which defines only `LOW_001`, `TREND_001`, `SEC_001`, `PORT_001`. MOM-001 is bound by the B-5 file blob plus prose; universe size and turnover cost are not recorded in that binding. Whether the redundancy comparator is reconstructable from bound artifacts is a Stage-1 census question.
**Census order.** 2nd.

### 2.4 `TL-2026-09-A-004` — D4 Explicit Tail / Crash-Response Overlay — **HYPOTHESIS — BLOCKED**

**Blocking authority.** ATP §12, verbatim: "Reopening rejected strategies without a genuinely new prospective economic mechanism."

| Predecessor | Decisive shots | Status | Custody |
|---|---|---|---|
| CAP-020 | capability validation arc (v1.0 → deepen Option A → deepen Option B, survivorship-free, 10,492 tickers) | **REJECTED (Evidenced)** as a Calmar / Sharpe / return improver — ΔCalmar negative in all nine grid cells, failed Sharpe guardrail, 0/9 robustness. Retained finding: reproducible crash-insurance behaviour, spun out to CAP-022 | `docs/implementation/evidence/cap_020/CAP020_Validation_v1.2.md` |
| CAP-022 / FI-003 / C1 | **0 completed decisive economic runs** — an execution defect produced no artifact, then the conformance finding became terminal | **NOT EVALUABLE / insufficient governed crisis history**; C1 "has not spent its decisive economic run" | Amendment A §5.1, §5.2, §5.3, §5.4 |

**Same-history shots inherited: 0 decisive economic runs**, against one rejected capability.

**Unblocking conditions — both required (batch baseline §4).**
1. *The C1 not-evaluable cause is identified and shown not to apply.* Recorded cause: OP-2 requires a ≥8 pp maximum-drawdown reduction in **at least 3 of the 4 named crises with none worsened**; only COVID (33 days) and the 2022 drawdown (282 days) fall inside any conformant price history, while dot-com and the global financial crisis have zero days of overlap; independently, the bound B-1 artifact defines environments containing neither. The owner ruled Option B: OP-2 is **not** weakened.
2. *A mechanism is named that C1 and CAP-020 did not test.* Recorded fact: C1, CAP-022 and FI-003 all tested **one mechanism — a market-level 200-day-SMA trend gate scaling book gross exposure from 1.0 to 0.5**, evaluated on a market proxy and shifted one day. It is neither cross-sectional nor a selection rule. It follows that a cross-sectional crash-resilience ranking would be a mechanism not previously tested, whereas a depth or parameter variant would not qualify: OP-4 makes overlay depth a named sensitivity only, and the frozen specification forbids re-tuning the trend window.

⛔ **No census execution for D4.** The entry remains in the ledger while blocked.

### 2.5 `TL-2026-09-A-005` — D5 Anti-Crowding / Valuation-Aware Defensive

**Hypothesis.** A valuation-aware defensive book retains defensiveness while avoiding the most expensive or crowded members of the factor.
**Family.** Defensive-equity complement.

| Predecessor | Decisive shots | Tape | Status |
|---|---|---|---|
| LOW-001 | 1 | `sep` equity | inconclusive |
| LOW-002 / C3 | 1 | `sep` equity via OP-6 | REJECT |

**Same-history shots inherited: 2.**

**Inherited constraint the census must clear.** The platform holds no point-in-time holdings, flow, or positioning data, so the crowding component is expected to return `CENSUS_STOP — NO PIT SOURCE`. The valuation-only variant is assessed separately against SF1 from `datekey ≥ 2016-01-29`, carrying D2's power caveat. ⛔ The census tests source availability only; it may not be widened into a search for a proxy that works.
**Census order.** 5th, valuation-only variant.

### 2.6 `TL-2026-09-A-006` — D6 Cross-Sectional Diversifier Outside the Defensive Family

**Hypothesis.** The best complement to the owned defensive mechanism may not be defensive at all.
**Structure.** A search space, not a single shot. The frozen specification may take **at most one** family, chosen by economic argument and ledger status. ⛔ Families may not be scanned on the tape to find a historical winner.

**Prior exposure is family-dependent and binds when the one family is named, before that family's census.** Known exposure per sketched family:

| Sketched family | Predecessor exposure | Shots | Status |
|---|---|---|---|
| Profitability / quality · cash-flow quality · conservative investment | MF-001 V1, MF-001 V2 / C2 | 2 | inconclusive; NOT EVALUABLE |
| Idiosyncratic momentum | MOM-001, MOM-002 | 2 | validated; **MOM-002 REJECTED** — rejection of an *enhancement*, whose load-bearing lesson is that widening the same factor does not create independent evidence |
| Earnings revision | none located in custody | 0 | — |
| Capital efficiency | none located in custody | 0 | — |
| Multi-factor residual ranking | MF-001 V1, C2 (construction overlap) | 2 | as above |

**Census order.** 3rd, one family only.

## 3. Family-wise prior-exposure disclosure

To be restated in the batch's frozen specification. Counts are decisive shots recorded whatever their verdict.

| Family | Prior shots on the tape | Detail |
|---|---|---|
| Defensive equity (`sep`) | **2** | LOW-001 (inconclusive) + LOW-002 / C3 (REJECT), plus any D funded |
| Trend | **3** | MOM-001 (validated, `sep` — same tape) + TREND-001 (power-limited, multi-asset) + TREND-002 (power failure, equity+bond). **TREND-003 = 0 shots, HOLD proposal**, plus D3 |
| Fundamentals (SF1 `ARQ`/`ART` + `sep`) | **2** | MF-001 V1 (inconclusive) + MF-001 V2 / C2 (NOT EVALUABLE), plus D2 and D6 if a fundamentals family is chosen |
| Tail / crash | **0 decisive economic runs** | against one rejected capability, CAP-020; C1 never spent its run |

Batch-wide, the prior tranche contributed three frozen candidates of which one reached a conforming decisive run. The promotion decision must weigh shots taken in the family, not the individual verdict alone.

## 4. Discrepancies with the batch design baseline — recorded, baseline not amended

The batch baseline is owner-accepted and is custodied here **verbatim and unmodified**. The four items below are differences between its §4.0 / §11 prior-exposure table and the custodied evidence, found while creating these entries. Where they differ, **the entries in §2 carry the custodied value**, because recording prior exposure accurately is the ledger's function. Amending the baseline is an owner decision and would be a successor version of that document.

**4.1 — LOW-001 confidence interval.** The baseline records `[−0.03, +0.53]`. The custodied value is **`[−0.029, +0.53]`**. The figure `−0.03` is SEC-001's lower bound. Cosmetic; §2.1 carries the custodied value.

**4.2 — D2's inherited constraint names a cause that is not C2's cause.** The baseline states the SF1 window is "the window that left C2 under-powered/NOT EVALUABLE". Amendment A attributes C2's disposition to the estimator alignment defect and comparator unavailability, and states that SF1 coverage of 88–97 % means C2 "is not further constrained". As written, D2 would be required to clear a constraint that was not the operative one. §2.2 records both: the SF1 floor as a real data constraint, and the alignment plus comparator defects as the cause D2 must show it does not inherit. **This is the correction with consequences.**

**4.3 — Trend-family shot accounting is inverted.** The baseline's family disclosure reads "trend family = MOM-001 + TREND-003". TREND-003 has consumed **zero** shots and is not a chartered program; TREND-001 and TREND-002 each consumed one decisive pre-registered shot and are omitted. §2.3 and §3 record the corrected accounting. The baseline's D3 row also gives "2–3" as a range; the custodied count is **3**.

**4.4 — The 0.90 correlation is an inherited prior.** The baseline attributes it to TREND-003. It was measured on TREND-001's equity book over a 2019–2026 window at n=150, with a rolling range of 0.60 to 0.99, and no TREND-003 return series exists. §2.3 records the provenance and the qualifications.

## 5. Custody identities at creation

All measured from `origin/main` at `3bc28fd67910198e6a929d5fac56f302cc800e4c`.

| Artifact | Bytes | sha256 |
|---|---|---|
| `docs/design/NewStrategy/NewStrategy_TrancheClosure_and_TrialLedger_2026-09-02_v1_0.md` | 15,676 | `1f15c5de1a08be256c9cb33590c582bbe7c7ef03558a9721542a559a89ea5fd3` |
| `docs/design/NewStrategy/NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL.md` | 25,279 | `47a2e26201b6c68ab8105ee08f0169fe64cdd3bca67f63d864b4efa85af34998` |
| `docs/design/NewStrategy/NewStrategy_ResearchAmendment_A_2026-09-01_v1_0.md` | 32,188 | `273800beef0624922ed65970aa099b137f409ba2261a686fe423b1b029c3e648` |
| `docs/design/NewStrategy/NewStrategy_CandidateInventory_2026-09-01_v1_0.md` | 12,427 | `19d9b6e381b70a1b018a0dcc73c77115d6ccfb03acc3524665bbd3512a29ab20` |
| `docs/design/Lifecycle/Strategy_Lifecycle_and_Research_Operating_Model_v1_0.md` | 61,993 | `4ee9b83d46d6ebc035657ac87d2a51c65584b31281f4e659cb6edcf230533391` |
| `docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v1_0_3.md` | 64,591 | `10043a1bc6e8aafecca9dfd46c0547b75fe6eaf763506d31dca9a8189de95605` |
| `docs/implementation/evidence/low_001_low_volatility/low_volatility.json` | 2,721 | `74dfe4ec6f5d9faf063a301e64512908c8c3566bffb08b1c59e295da1860e6e0` |
| `docs/implementation/evidence/fi_001_phase1_measurement/measurement.md` | 5,074 | `c00d7c242047acc3dfb757c6551c10296a623783250587a85b4e85b7aac8a6fb` |
| `apps/backend/app/research/factor_lab/configs.py` (B-3 binding) | 10,417 | `65521ae18014d0c5a588a56ffd72b3e7bbea615b67984e2218ab815f21922212` |
| `apps/backend/app/research/programs.py` | 26,775 | `657e8726da9aab74c58aff2f399ff0c7314890fa64c1ce208732dc17012c6536` |
| `docs/design/NewStrategy/Strategy_Factory_DISCOVERY-BATCH-2026-09-A_v1_0_OFFICIAL.md` (custodied with this record, verbatim) | 41,708 | `6d688737b559979033c0f595929011ba709ae7209515fb3ab4b7f6a1df389888` |

**Comparator artifacts named by the batch (BD-4).** B-3, the frozen LOW-001 definition, is bound and was re-verified byte-identical at this commit. B-5, the pre-seam momentum construction, is bound at `apps/backend/app/factor_data/backtest.py` blob sha256 `f02a90fa5c56d14990868bfd2d618d46e1e9141760a477142e838ef3ad4eb42f`, 29,396 B. No artifact binds a Range Trader reference book; under BD-4's "included iff bindable by artifact + SHA-256" clause that is a census determination, recorded here as a lead.

**Ledger separation.** These entries are a new artifact. The pre-existing `docs/review/momentum_daily/equal_weight_validation/TrialLedger_v1.0.json` belongs to forward validation and is pinned by hash in `apps/backend/app/validation/forward_window.py`; it is unrelated to this batch and must not be modified.

## 6. What this record does not authorise

- Any candidate return series, backtest, exploration, or diagnostic comparison, for any D-candidate, on any store.
- Any change to the frozen C1/C2/C3 specification, Amendment A, the closure record, the C3 verdict, or the owner-accepted batch baseline.
- Freezing any successor specification, or research capital for any D-candidate.
- Engineering of census tooling, comparator artifacts, or accrual snapshots — each remains an ATP §1 admission.
- Implementation, account binding, scheduler change, deployment, PAPER activation, or orders.
- Reading any post-2026-07-02 accrued data for any research purpose.
- Advancing D4, or any census execution for it.
