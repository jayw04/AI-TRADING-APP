# MR-002 / SPQ-1 Development Plan After Phase 2B — v1.1

**Program:** MR-002 — Sector-Neutral Residual Reversion
**Workstream:** SPQ-1
**Current status:** Phase 2B COMPLETE and CLOSED
**Supersedes:** v1.0 (planning document only; not a binding authorization)
**Purpose:** Define the remaining governed development and research phases required to reach a final research verdict and, only if justified, a paper-trading strategy.

> **v1.1 note.** This revision folds in six accepted additions and three structural clarifications from the v1.0 review. All changes are **planning-level**; none opens data, computes performance, or authorizes execution. See **§0 Amendments from v1.0**. The executable Phase 3A authorization package is **not** drafted here and remains **NOT YET AUTHORIZED**.

---

## 0. Amendments from v1.0

Every amendment below was classified against the multiplicity question. **No amendment affects the trial count; DSR multiplicity remains N = 5.**

| Amendment | Classification | Affects trial count? | Must resolve before validation? |
|---|---|---|---|
| Degrees-of-freedom attestation (§4.2 A1) | Governance | No | Yes |
| Conservative short model (§4.2 A2, §4.4) | Methodology | No new signal trial | Yes |
| Technical validation/OOS seal (§4.2 A3, §4.3, §5) | Integrity | No | Yes |
| Enrichment edge-case contract (§4.2 A4, §4.3) | Integrity/execution | No | Yes |
| OOS consumption rule (§5.3a) | Governance | No | Before OOS; define in 3A |
| Structural coverage preflight (§4.2 A6) | Integrity | No | Yes |
| Numeric runtime binding (§4.2 A6) | Reproducibility | No | Yes |
| Primary/diagnostic classification (§4.4a) | Governance | No | Yes |
| Null-model report (§4.4b) | Evidence | Uses existing N=5 | Yes |
| Phase 6 audit/ADR hooks (§7.6) | Product architecture | No | Conditional |

Items **A2 (conservative short), A3 (technical seal), A4 (enrichment edge-case contract), and A5/§5.3a (OOS consumption rule)** shape the validation/OOS contract itself and must be resolved **before** the Phase 3A package is accepted; they are expensive to retrofit after data is opened.

---

## 1. Executive summary

Phase 2B completed the deterministic, point-in-time governed signal-production foundation for MR-002. It established reproducible development signal production, evidence integrity, collision handling, restart safety, and deterministic replay across the full 425,000-unit development population.

Phase 2B did **not** establish profitability, statistical significance, portfolio usefulness, or production readiness.

The remaining work is divided into decision gates:

1. Validation authorization and validation run
2. Single sealed out-of-sample run
3. Research verdict and product-viability assessment
4. Standalone paper strategy, only after research success
5. Optional multi-sleeve portfolio study
6. Possible live-money readiness review, much later

The immediate development target is **Phase 3A: Validation Authorization Package**. No validation or OOS data should be opened until that package is accepted.

---

## 2. Governing principles

The following controls remain mandatory throughout all future phases:

- The frozen MR-002 signal logic must not be changed after observing validation or OOS results.
- Validation and OOS data remain sealed until separately authorized; the seal is **technically enforced and evidenced**, not asserted (§4.2 A3).
- The primary promoted research configuration is **Config B**. Configurations A and C are neighboring robustness configurations only and may **never** substitute for B on the basis of observed performance.
- DSR multiplicity remains **N = 5**, unless the governing preregistration explicitly says otherwise.
- Close-`t` decision records must remain structurally separate from `t+1` execution-enrichment records; enrichment is **fail-closed** (§4.2 A4).
- The **governing economic interpretation** of any long/short result uses the conservative short model; frictionless short results are diagnostic only (§4.2 A2).
- Metrics carry an explicit `metric_role`; only preregistered primary gates decide the verdict (§4.4a).
- Product code must consume immutable published records and must not recompute MR-002 signal economics.
- MR-002 must not be grafted into Momentum, Range Trader, or other existing signal logic.
- Any portfolio integration must occur through a separately preregistered multi-sleeve study.
- No paper or live promotion follows automatically from a research pass.

---

## 3. Current accepted baseline

| Item | Accepted value |
|---|---|
| Phase 2 status | COMPLETE |
| Development sessions | 1,700 |
| Monthly shards | 82 |
| Request units | 425,000 |
| Signal records emitted | 320,771 |
| Ineligible outcomes | 40,457 |
| Integrity stops | 50,399 |
| Code/data identity refusals | 13,373 |
| Missing outcomes | 0 |
| Orphan outcomes | 0 |
| Duplicate request keys | 0 |
| Duplicate resolved security/session keys | 0 |
| Collision groups | 35 |
| Collision-affected requests | 70 |
| Deterministic replay | PASS |
| Restart invariance | PASS |
| Validation/OOS reads | 0 |

The frozen governing interpretation is:

> Phase 2B establishes deterministic, PIT-governed development signal production and evidence integrity only. It makes no claim regarding profitability, statistical significance, robustness, portfolio utility, or production readiness.

### 3.1 Preregistration facts Phase 3A must BIND (not redesign)

Phase 3A binds each value below **by content hash and machine-readable diff** against governing preregistration **v1.0.3** (commit `c7a2e4b`). It must not reselect or reinterpret them.

| Preregistered fact | Value |
|---|---|
| Validation window | 2020-01-13 → 2023-02-08 |
| OOS window | 2023-05-30 → 2026-07-01 |
| Walk-forward folds | 5 |
| Primary Sharpe gate | S_min = 0.70 |
| Cost stresses | 20 bps and 300 bps |
| Moving-block bootstrap | block length = 21, replications = 2,000, seed = 42 |
| DSR multiplicity | N = 5 |
| DSR trial ledger identity | `deda5cec…` (`MR002_DSR_TrialLedger_v1.0.json`) |
| DSR trial set | A, B, C, RNG-001, RNG-EntryLogic |
| Diagnostics | PBO, regime concentration |
| Execution endpoint | −5/−6 endpoint = next-open exit |
| Current authorization | `validation_authorization = false` |

---

# 4. Phase 3 — Validation

## 4.1 Goal

Determine whether the frozen MR-002 signal generalizes beyond the development sample strongly enough to justify consuming the single sealed OOS opportunity.

## 4.2 Phase 3A — Validation Authorization Package

### Development tasks

Prepare a governance package that freezes the complete validation contract before any validation partition is opened.

The package must specify:

1. Validation partition identity and date range.
2. Proof that validation and OOS have not previously been opened — **evidenced technically** (§4.2 A3).
3. Exact Config A, B, and C parameter identities — **bound by hash from prereg v1.0.3, diff-proven unchanged**.
4. Config B as the only candidate eligible for sealed OOS.
5. Forward-return definitions.
6. Execution-enrichment rules — including the **edge-case contract** (§4.2 A4).
7. Official next-open price source and identity.
8. Cost, spread, slippage, and borrow assumptions — including the **conservative short model** (§4.2 A2).
9. Portfolio construction and constraint identities.
10. Primary metric and secondary metrics — with `metric_role` classification (§4.4a).
11. DSR methodology with `N = 5` — plus the **degrees-of-freedom attestation** (§4.2 A1).
12. Pass, fail, inconclusive, and integrity-failure criteria.
13. Allowed validation artifacts.
14. Prohibited changes after validation is viewed.
15. Explicit confirmation that OOS remains sealed.
16. **Structural coverage preflight and numeric-runtime binding** (§4.2 A6).

### Baseline required deliverables (v1.0)

- `ValidationAuthorization_v1.0.json`
- `ValidationRunSpecification_v1.0.json`
- `ValidationInputIdentityManifest_v1.0.json`
- `ValidationMetricSpecification_v1.0.json`
- `ValidationCostExecutionSpecification_v1.0.json`
- `ValidationAuthorizationSubmission_v1.0.md`

### Acceptance target

No validation execution is authorized until the package is reviewed and accepted.

---

### A1 — Multiplicity & degrees-of-freedom attestation *(v1.1 amendment)*

Phase 3A must prove that **nothing after preregistration v1.0.3 created a new trial, configuration, model choice, or performance-dependent researcher degree of freedom.** The attestation must cover at least: the Phase 2B calendar verification-harness correction; the non-injective identity collision amendment; runner-side collision detection; the terminal-key clarification; and artifact/schema corrections.

**Required conclusion** — each true: no signal threshold changed · no holding period changed · no universe-selection rule changed · no portfolio or execution rule changed · no metric gate changed · no Config A/B/C definition changed · no performance result was observed · no additional trial was introduced. **Therefore DSR multiplicity remains N = 5.**

Requires a **machine-generated diff proof** against the preregistered identities and a human-readable classification of **every** post-preregistration change as one of `INTEGRITY_ONLY` / `EVIDENCE_ONLY` / `GOVERNANCE_ONLY` / `SIGNAL_OR_TRIAL_AFFECTING`. **The last category must have count zero.**

- `MR002_Phase3A_MultiplicityAndDegreesOfFreedomAttestation_v1.0.json`

### A2 — Borrow, locate & short-sale realism *(v1.1 amendment; required before validation authorization)*

A long/short validation result may not be presented as economically tradeable while assuming frictionless shorting without clear qualification. Phase 3A preregisters **two parallel views**, and the model must be decided **before validation values are opened**.

**Governing economic view** — a conservative short implementation accounting for at least: borrow availability or an explicitly conservative availability proxy; borrow cost; locate failure; short-not-allowed outcomes; Regulation SHO / SSR handling where reconstructable; no-open or rejected-short handling; pending-exit and ghost-position prevention. **This view governs the principal economic interpretation of the validation result.**

**Frictionless research view** — the unconstrained short-side result may still be reported to measure the underlying hypothesis, labeled `FRICTIONLESS_SHORT_RESEARCH_DIAGNOSTIC` / `NOT AN IMPLEMENTABLE PERFORMANCE ESTIMATE`.

3C must report **both** frictionless long/short metrics **and** conservative-borrow long/short metrics. Do **not** invent historical locate facts that cannot be reconstructed; where PIT borrow availability is unavailable, preregister a conservative proxy or refusal model and disclose its limitations.

- `ShortBorrowLocateModelSpecification_v1.0.json`
- `ShortAvailabilityLimitationsStatement_v1.0.md`

### A3 — Technical validation/OOS seal *(v1.1 amendment)*

"Sealed and unread" must be **technically evidenced**, not operator-asserted. The package requires: separate validation and OOS storage boundaries; read credentials unavailable to ordinary development execution; append-only access audit; content commitments for the sealed partitions; hash-chained or otherwise tamper-evident access events; an explicit authorization event before credentials are released; an opened-object ledger for the authorized run; and post-run reconciliation against the store-level access log.

Two distinct records are **both** required:

- `OpenedObjectLedger` = what the authorized program opened (per-run).
- `SealedStoreAccessLog` = whether **anything** opened the partition across program history.

Gates — **before validation:** validation access events before authorization = 0; OOS access events = 0. **Before OOS:** OOS access events before authorization = 0.

The roadmap mandates the **properties** — separate access control, append-only history, content commitment, tamper evidence — not a specific cloud service (unless already governed).

- `SealedPartitionContentCommitment_v1.0.json`
- `SealedPartitionAccessHistory_v1.0.json`
- `SealVerificationReport_v1.0.json`

### A4 — `t+1` execution-enrichment edge-case contract *(v1.1 amendment; preregistered before validation opens)*

Terminal treatment must be defined for at least: no official open; trading halt; delisting; symbol or permanent-security transition; split between close-`t` and open-`t+1`; dividend or distribution treatment; merger consideration; cash-only acquisition; stock-and-cash acquisition; missing or conflicting open prices; adjusted-vs-unadjusted open identity; calendar mismatch; execution session ≠ registered next session.

**Default = fail closed.** No silent price substitution, previous-close fallback, later-open fallback, or post-hoc security winner. Each enrichment record binds: `ExecutionEnrichmentDisposition`, `ExecutionEnrichmentCode`, `decision_record_sha256`, requested execution session, actual source session, corporate-action identity, official-open source identity, terminal treatment.

An **enrichment edge-case census** (analogous to the CollisionCensus), recomputed from the authorized partition — known cases may be registered in advance but must **not** become a fixed expected-count gate — separately reports: successful enrichment · no-open · halt · delisting · corporate-action transition · identity conflict · missing source · future-information stop · other registered disposition.

- `ExecutionEnrichmentEdgeCaseCensus_v1.0.json`

### A6 — Partition coverage & numeric-environment preflight *(v1.1 amendment)*

**Structural coverage preflight** verifies **only** structural properties, value-blind: partition identity; date range; session count; required table presence; row counts; symbol/security coverage; required factor-series coverage; schema identity; null-count summaries where value-blind; latest available source date; no rows outside the registered partition. It must **not** calculate returns, signals, rankings, or performance, and must distinguish `STRUCTURAL_PREFLIGHT` from `PERFORMANCE_OBSERVATION`. **Only the former is authorized before the validation run.**

**Numeric-environment binding** freezes: Python version; NumPy; SciPy; pandas; BLAS vendor+version; LAPACK vendor+version; LAPACK/solver driver; threading settings; floating-point type; random generator; bootstrap seed; OS and architecture — retaining the already-frozen solver settings (numpy.linalg.lstsq, gelsd/SVD, float64, rcond=1e-10).

- `ValidationPartitionStructuralPreflight_v1.0.json`
- `NumericRuntimeIdentityManifest_v1.0.json`

---

## 4.3 Phase 3B — Validation Opening and Enrichment

### Goal

Open only the authorized validation partition and attach preregistered future-return and execution facts without mutating any close-`t` decision record.

### Development tasks

- Release sealed-store read credentials **only** after the explicit authorization event (§4.2 A3).
- Open the validation partition under an opened-object ledger **and** reconcile it against the sealed-store access log.
- Produce immutable execution-enriched candidate records under the **fail-closed enrichment edge-case contract** (§4.2 A4).
- Bind every enrichment to the original decision-record SHA-256.
- Preserve the decision cutoff and schema identity.
- Attach only registered `t+1` execution facts.
- Detect and stop on future-information contamination.
- Reconcile every opened validation unit; produce the enrichment edge-case census.
- Prove OOS reads remain zero (opened-object ledger **and** OOS access-log = 0).

### Integrity gates

| Gate | Required result |
|---|---:|
| Decision-record mutations | 0 |
| Missing decision/enrichment bindings | 0 |
| Duplicate enrichment identities | 0 |
| Future-information violations | 0 |
| OOS reads (run ledger and store access log) | 0 |
| Unregistered data-source reads | 0 |
| Unreconciled validation units | 0 |
| Validation access events before authorization | 0 |

### Required deliverables

- `ValidationOpenedObjectLedger_v1.0.json`
- `ValidationExecutionEnrichmentManifest_v1.0.json`
- `ValidationDecisionExecutionBindingReport_v1.0.json`
- `ValidationUnitReconciliation_v1.0.json`
- `ExecutionEnrichmentEdgeCaseCensus_v1.0.json` *(v1.1)*
- `SealVerificationReport_v1.0.json` *(v1.1; validation partition)*

---

## 4.4 Phase 3C — Validation Portfolio Replay and Metrics

### Goal

Run the frozen portfolio and execution machinery for Configs A, B, and C and calculate only preregistered metrics.

### Required analyses

Reported under **both** the governing conservative-borrow view and the frictionless research diagnostic view *(v1.1)*:

- Annualized return · Annualized volatility · Sharpe ratio · Deflated Sharpe Ratio · Maximum drawdown · Calmar ratio · Turnover · Cost sensitivity · Long-side contribution · Short-side contribution · Sector exposure · Normalized beta exposure · Holding-period behavior · Win rate · Tail loss · Calendar-year stability · Market-regime stability · Capacity and ADV usage · Correlation to Momentum · Correlation to Low Volatility · A/B/C directional consistency

### Required controls

- No parameter changes after results are viewed.
- No substitution of A or C for B because they performed better.
- No removal of difficult years, names, sectors, or the short side.
- No unregistered metrics may become decision metrics.
- Results must be reproducible from immutable inputs and frozen code under the bound numeric runtime.

### 4.4a — Primary gates versus diagnostics *(v1.1 amendment; required)*

Metrics are **not** equivalent decision criteria. Every metric specification carries `metric_role ∈ {PRIMARY_GATE, SECONDARY_GATE, DIAGNOSTIC_ONLY, INTEGRITY_ONLY}`, **bound by hash from preregistration v1.0.3.**

- **Primary validation gate:** Config B Sharpe ≥ **0.70** (subject to the exact preregistration language and cost treatment).
- **Diagnostics** (examples): PBO · regime concentration · maximum drawdown · Calmar · year-by-year behavior · side contribution · sector concentration · capacity · correlation · tail behavior. Diagnostics may qualify or contextualize the verdict only to the extent preregistration already permits; they must **not** become substitute success criteria after results are observed.

### 4.4b — Null model and randomization report *(v1.1 amendment; required)*

Add a Phase 3C deliverable binding the already-registered DSR trial ledger (Config A, Config B, Config C, RNG-001, RNG-EntryLogic; N = 5; ledger identity `deda5cec…`). **Do not create new null models or additional trials** unless preregistration already authorizes them.

- `ValidationNullModelAndRandomizationReport_v1.0.json`

### Required deliverables

- `ValidationPortfolioReplayManifest_v1.0.json`
- `ValidationMetricsReport_v1.0.json` (conservative + frictionless views)
- `ValidationDSRReport_v1.0.json`
- `ValidationConfigurationComparison_v1.0.json`
- `ValidationRegimeAndConcentrationReport_v1.0.json`
- `ValidationDeterminismReport_v1.0.json`
- `ValidationNullModelAndRandomizationReport_v1.0.json` *(v1.1)*
- `ValidationVerdict_v1.0.md`

---

## 4.5 Phase 3 decision gate

| Verdict | Meaning | Next step |
|---|---|---|
| `VALIDATION_PASS` | Config B clears all preregistered gates | Prepare sealed OOS authorization |
| `VALIDATION_INCONCLUSIVE` | Evidence is insufficient | Stop; do not consume OOS |
| `VALIDATION_FAIL` | Config B fails a governing gate | Reject/archive MR-002 |
| `INTEGRITY_FAILURE` | Results are not interpretable | Repair integrity issue without performance interpretation |

A sealed OOS run may be requested only when: every validation integrity gate passes; Config B passes the preregistered **primary** gate (Sharpe ≥ 0.70) **under the governing conservative-borrow view**; results are not concentrated in one year, sector, side, or small issuer group; realistic execution and costs do not remove the effect; A/B/C behavior is directionally coherent; and no post-validation tuning is requested.

---

# 5. Phase 4 — Single Sealed OOS Run

## 5.1 Goal

Obtain the final unbiased research verdict for Config B through exactly one sealed OOS run.

## 5.2 Authorization package

Before OOS is opened, freeze: Config B parameters; signal and portfolio code identities; data-source identities; portfolio constraints; execution and cost assumptions (conservative short model governing); metric definitions with `metric_role`; pass/fail criteria; OOS partition identity; exact output artifact list; and **technically-evidenced proof that OOS has never been read** (`SealedStoreAccessLog` OOS access events = 0).

## 5.3 Execution rules

- Open OOS exactly once. Evaluate Config B only.
- No parameter or code changes after opening. No switching to Config A or C.
- No change to costs, holding period, universe, sides, or constraints. No new market filter. No revised primary metric.
- No selective exclusion of unfavorable periods or names.

## 5.3a — OOS consumption rule *(v1.1 amendment; required before OOS authorization)*

Distinguish a **non-consumptive integrity failure** from an OOS run whose information content has already been observed.

**Non-consumptive integrity failure** — a corrected rerun may be *considered* only when **all** are proven: failure is orthogonal to performance; no portfolio return series was materialized; no metric was calculated; no metric was logged; no metric artifact was written; no metric was displayed to an operator; no configuration comparison was produced; no directional performance fact was observed; the failure and repair are fully audit-bound. This does **not** automatically authorize a rerun — it permits an **adjudication request** for one clean rerun.

**Consumptive failure** — OOS is consumed when any performance-sensitive output exists or was observed (returns, PnL, Sharpe, drawdown, win rate, config comparison, partial-period performance, or a directional statement such as profitable/unprofitable). After consumption, **no** repair-and-rerun is allowed under the same preregistration.

**Staged execution boundary:**

- Stage O1 — seal verification and input preflight
- Stage O2 — enrichment and integrity reconciliation
- Stage O3 — portfolio replay
- Stage O4 — metric materialization
- Stage O5 — human-visible release

Failures in **O1/O2** may qualify as non-consumptive if the no-metric proof holds. Failures in **O3 or later** presumptively **consume** OOS unless the artifact chain proves no return or performance information was produced.

- `OOSConsumptionStateAttestation_v1.0.json`

## 5.4 Required deliverables

- `OOSOpeningAuthorization_v1.0.json`
- `OOSOpenedObjectLedger_v1.0.json`
- `OOSExecutionManifest_v1.0.json`
- `OOSMetricsReport_v1.0.json`
- `OOSValidationComparison_v1.0.json`
- `OOSDeterminismReport_v1.0.json`
- `OOSConsumptionStateAttestation_v1.0.json` *(v1.1)*
- `SealVerificationReport_v1.0.json` *(v1.1; OOS partition)*
- `FinalResearchVerdict_v1.0.md`
- `MR002ProgramDisposition_v1.0.json`

## 5.5 Final research verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | Proceed to product-viability assessment |
| `INCONCLUSIVE` | Archive as research; no product strategy |
| `FAIL` | Reject and archive |
| `INTEGRITY_FAILURE` | Adjudicate without interpreting performance (subject to §5.3a) |

---

# 6. Phase 5 — Product-Viability Assessment

## 6.1 Goal

Determine whether a research-passing signal is operationally and economically suitable for paper trading. A successful OOS result does not automatically authorize product implementation.

> **v1.1 note.** Borrow/locate realism is no longer *entirely* deferred here — the **governing** conservative short model is decided in Phase 3A (§4.2 A2). Phase 5 deepens operational borrow handling (real locate workflow, borrow-cost sensitivity under the actual broker) but inherits, and may not loosen, the Phase 3A governing economic assumptions.

## 6.2 Required assessment areas

### Economic viability
Net return after realistic costs · Sharpe and Calmar after costs · Capacity · ADV participation · Spread and slippage sensitivity · Delayed-open sensitivity · Long/short contribution · Borrow and locate assumptions · Borrow-cost sensitivity · Turnover · Exposure during pending exits.

### Operational viability
Short-order rejection behavior · Partial fills · Pending exits · Account lock behavior · Circuit-breaker behavior · Risk-reducing closes · Publication availability · Stale or partial publication handling · Position and order reconciliation · Restart safety · Multi-user isolation.

### Diversification value
Correlation with Momentum · Correlation with Low Volatility · Stress-period correlation · Drawdown contribution · Marginal Sharpe · Marginal Calmar · Capital efficiency · Tail-risk interaction.

## 6.3 Allowed decisions

- `PROMOTE_STANDALONE_PAPER` · `PROMOTE_REFERENCE_ONLY` · `RESEARCH_VALID_BUT_NOT_OPERABLE` · `REJECT`

---

# 7. Phase 6 — Standalone Paper Strategy

## 7.1 Goal

Prove that MR-002 can operate safely in the application and broker environment before any portfolio blending or live-capital consideration.

## 7.2 Required architecture

```text
SPQ-1 signal producer
    -> immutable daily publication package
    -> product adapter
    -> close-t portfolio target and intended orders
    -> t+1 official-open enrichment
    -> strategy template
    -> OrderRouter
    -> central risk engine
    -> paper broker
```

## 7.3 Mandatory implementation rules

The product strategy must not recompute: sector factors; OLS residuals; return normalization; z-scores; candidate beta; PIT sector mapping; eligibility; ADV; official next-open price.

The product adapter must fail closed when: a publication is missing; a publication is partial; a manifest identity is stale or mismatched; record counts do not reconcile; the official-open enrichment is unavailable; a required source identity changes.

## 7.4 Paper strategy deliverables

Product-adapter specification · Immutable-publication consumer · Standalone strategy template · Activation script · Risk-limit configuration · Short/borrow operating policy · Paper runbook · Incident runbook · Walk-away criteria · Daily reconciliation report · Position/order/fill audit · Paper-observation report.

## 7.5 Suggested operational targets

The exact observation period must be preregistered during promotion planning.

| Metric | Suggested target |
|---|---:|
| Observation period | 60–90 trading sessions |
| Publication availability | at least 99% |
| Duplicate submissions | 0 |
| Order-path bypasses | 0 |
| Identity mismatches | 0 |
| Future-information events | 0 |
| Unexplained position drift | 0 |
| Unreconciled orders/fills | 0 |

## 7.6 Platform-integration requirements *(v1.1 amendment; conditional on research + promotion success)*

Because the product path crosses the platform's architectural invariants, Phase 6 must add:

- New `AuditAction` enum entries for: publication receipt; publication refusal; enrichment; intended-order creation; submission; partial fill; exit pending; reconciliation failure; and fail-closed hold. **Exact enum names are governed in the Phase 6 design package, not invented in this roadmap.**
- Matching on-call and incident-runbook scenarios for each new action type (per the "new audit action ⇒ runbook scenario" convention).
- A `check_no_llm_in_order_path` assertion (MR-002 is deterministic — trivially true — but stated, since the product path enters the order path).
- A CI rule prohibiting product-template imports of research signal math.
- An ADR for the immutable signal-publication → product-adapter contract.
- An ADR (or extension) covering shorting, borrow/locate behavior, pending exits, and risk-reducing closes under account locks.

---

# 8. Phase 7 — Optional Multi-Sleeve Interaction Study

## 8.1 Goal
Determine whether MR-002 should remain standalone or become a portfolio sleeve alongside Momentum and possibly Low Volatility.

## 8.2 Governing restriction
This is a separate research study. MR-002 must not be inserted directly into existing Momentum or Range Trader signal logic.

## 8.3 Candidate comparisons
Momentum alone · Existing Combined Book · Momentum + MR-002 · Momentum + Low Volatility + MR-002.

## 8.4 Required metrics
Marginal Sharpe · Marginal Calmar · Maximum drawdown reduction · Worst-year impact · Stress-period correlation · Gross exposure efficiency · Turnover increase · Capacity interaction · Tail-loss contribution.

## 8.5 Allowed decisions
`STANDALONE_ONLY` · `ADD_AS_FIXED_WEIGHT_SLEEVE` · `REFERENCE_ONLY` · `REJECT_PORTFOLIO_INTEGRATION`. Any sleeve weights must be preregistered before evaluation.

---

# 9. Phase 8 — Live-Money Readiness

## 9.1 Goal
Determine whether the complete research, paper, operational, and risk record justifies a limited real-capital canary.

## 9.2 Minimum prerequisites
Sealed OOS pass · Product-viability pass · Standalone paper observation completed · Borrow/short handling proven · Risk-reducing closes proven under locks · Publication SLA proven · Order/fill/position reconciliation proven · Multi-user isolation proven · Incident and walk-away runbooks approved · Explicit owner capital and loss limits · Required ADRs accepted · Separate live authorization.

## 9.3 Initial live target
Dedicated account · Small fixed capital allocation · Low gross cap · Strict per-name cap · No multi-sleeve integration initially · Daily operator review · Automatic hold on evidence or reconciliation mismatch. **No automatic progression from paper to live is permitted.**

---

# 10. Recommended immediate developer assignment

The developer should work only on **Phase 3A — Validation Authorization Package** *(and only once §11 authorizes it — v1.1 authorizes the roadmap update, not the Phase 3A package)*.

## Immediate tasks

1. Locate and review the governing preregistration v1.0.3 (`c7a2e4b`).
2. Extract the exact validation and OOS partition definitions (bind, do not reselect — §3.1).
3. Extract the preregistered primary metric and thresholds; assign `metric_role` (§4.4a).
4. Confirm DSR `N = 5`; produce the degrees-of-freedom attestation (§4.2 A1).
5. Define Config A/B/C roles without changing parameters (bind by hash, diff-proven).
6. Define the forward-return enrichment schema and the **fail-closed enrichment edge-case contract** (§4.2 A4).
7. Define the execution-enriched candidate schema.
8. Bind official-open and cost-source identities; preregister the **conservative short/borrow model** (§4.2 A2).
9. Specify the **technical seal** properties + access-log/content-commitment design (§4.2 A3).
10. Define the **structural coverage preflight** and **numeric-runtime binding** (§4.2 A6).
11. Define pass/fail/inconclusive/integrity-failure rules and the **OOS consumption rule** (§5.3a).
12. Produce proof that validation and OOS remain sealed and unread (store-level access log = 0).
13. Prepare the Phase 3A artifacts.
14. Commit and stop for authorization before reading any validation data.

## Explicitly prohibited during the immediate assignment

Opening validation data · Opening OOS data · Computing returns · Computing performance · Ranking configurations · Changing signal thresholds · Changing holding period · Modifying the frozen universe · Modifying portfolio constraints · Building a product strategy · Integrating with a broker · Adding MR-002 to Momentum, Range Trader, or Combined Book · Starting UI work.

---

# 11. Overall completion targets

**Research target.** Establish whether Config B demonstrates reproducible, after-cost residual-reversion evidence in validation and one sealed OOS run — under the **governing conservative-borrow** interpretation.

**Product target.** If research passes, operate a standalone paper strategy that consumes immutable signal publications without identity drift, future information, duplicate economics, risk bypass, or unreconciled orders.

**Portfolio target.** Only through a separately preregistered interaction study, determine whether MR-002 improves portfolio drawdown and risk-adjusted behavior as an independent sleeve.

**Honest failure target.** If validation or OOS fails, archive MR-002 without modifying existing live strategies or creating a post-hoc replacement configuration.

---

# 12. Recommended execution order

```text
Phase 3A — Validation authorization package
    STOP FOR REVIEW

Phase 3B/C — Validation opening, replay, and verdict
    STOP FOR REVIEW

Phase 4 — Single sealed OOS run
    STOP FOR FINAL RESEARCH VERDICT

Phase 5 — Product-viability assessment
    STOP FOR PROMOTION DECISION

Phase 6 — Standalone paper strategy
    STOP FOR PAPER REVIEW

Phase 7 — Optional multi-sleeve study
    ONLY IF separately authorized

Phase 8 — Live-money readiness
    ONLY IF separately authorized
```

---

## 13. Authorized next action (this revision)

| Action | Status |
|---|---|
| Update roadmap from v1.0 to v1.1 | AUTHORIZED (this document) |
| Draft executable Phase 3A authorization package | NOT YET AUTHORIZED |
| Open validation data | NOT AUTHORIZED |
| Open OOS data | NOT AUTHORIZED |
| Compute returns or performance | NOT AUTHORIZED |

---

## Final instruction to the development team

Do not treat this roadmap as blanket authorization for all phases.

Only the specifically authorized phase may be implemented. Each phase must produce its evidence package, stop, and receive formal adjudication before the next phase begins. After v1.1 is accepted, the next authorization can cover **drafting** the binding Phase 3A package — which itself stops for review before any validation data is opened.
