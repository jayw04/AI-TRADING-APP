# MR-002 / SPQ-1 Development Plan After Phase 2B

> **Historical (v1.0).** Superseded by [`MR002_Development_Plan_Next_Phases_v1.3.md`](MR002_Development_Plan_Next_Phases_v1.3.md) (v1.3.1, 2026-08-09) via v1.1 → v1.1.1 → v1.2. Retained for lineage; do not use for status or planning.

**Program:** MR-002 — Sector-Neutral Residual Reversion  
**Workstream:** SPQ-1  
**Current status:** Phase 2B COMPLETE and CLOSED  
**Purpose:** Define the remaining governed development and research phases required to reach a final research verdict and, only if justified, a paper-trading strategy.

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
- Validation and OOS data remain sealed until separately authorized.
- The primary promoted research configuration is **Config B**.
- Configurations A and C are neighboring robustness configurations only.
- DSR multiplicity remains **N = 5**, unless the governing preregistration explicitly says otherwise.
- Close-`t` decision records must remain structurally separate from `t+1` execution-enrichment records.
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

---

# 4. Phase 3 — Validation

## 4.1 Goal

Determine whether the frozen MR-002 signal generalizes beyond the development sample strongly enough to justify consuming the single sealed OOS opportunity.

## 4.2 Phase 3A — Validation Authorization Package

### Development tasks

Prepare a governance package that freezes the complete validation contract before any validation partition is opened.

The package must specify:

1. Validation partition identity and date range.
2. Proof that validation and OOS have not previously been opened.
3. Exact Config A, B, and C parameter identities.
4. Config B as the only candidate eligible for sealed OOS.
5. Forward-return definitions.
6. Execution-enrichment rules.
7. Official next-open price source and identity.
8. Cost, spread, slippage, and borrow assumptions.
9. Portfolio construction and constraint identities.
10. Primary metric and secondary metrics.
11. DSR methodology with `N = 5`.
12. Pass, fail, inconclusive, and integrity-failure criteria.
13. Allowed validation artifacts.
14. Prohibited changes after validation is viewed.
15. Explicit confirmation that OOS remains sealed.

### Required deliverables

- `ValidationAuthorization_v1.0.json`
- `ValidationRunSpecification_v1.0.json`
- `ValidationInputIdentityManifest_v1.0.json`
- `ValidationMetricSpecification_v1.0.json`
- `ValidationCostExecutionSpecification_v1.0.json`
- `ValidationAuthorizationSubmission_v1.0.md`

### Acceptance target

No validation execution is authorized until the package is reviewed and accepted.

---

## 4.3 Phase 3B — Validation Opening and Enrichment

### Goal

Open only the authorized validation partition and attach preregistered future-return and execution facts without mutating any close-`t` decision record.

### Development tasks

- Open the validation partition under an opened-object ledger.
- Produce immutable execution-enriched candidate records.
- Bind every enrichment to the original decision-record SHA-256.
- Preserve the decision cutoff and schema identity.
- Attach only registered `t+1` execution facts.
- Detect and stop on future-information contamination.
- Reconcile every opened validation unit.
- Prove OOS reads remain zero.

### Integrity gates

| Gate | Required result |
|---|---:|
| Decision-record mutations | 0 |
| Missing decision/enrichment bindings | 0 |
| Duplicate enrichment identities | 0 |
| Future-information violations | 0 |
| OOS reads | 0 |
| Unregistered data-source reads | 0 |
| Unreconciled validation units | 0 |

### Required deliverables

- `ValidationOpenedObjectLedger_v1.0.json`
- `ValidationExecutionEnrichmentManifest_v1.0.json`
- `ValidationDecisionExecutionBindingReport_v1.0.json`
- `ValidationUnitReconciliation_v1.0.json`

---

## 4.4 Phase 3C — Validation Portfolio Replay and Metrics

### Goal

Run the frozen portfolio and execution machinery for Configs A, B, and C and calculate only preregistered metrics.

### Required analyses

- Annualized return
- Annualized volatility
- Sharpe ratio
- Deflated Sharpe Ratio
- Maximum drawdown
- Calmar ratio
- Turnover
- Cost sensitivity
- Long-side contribution
- Short-side contribution
- Sector exposure
- Normalized beta exposure
- Holding-period behavior
- Win rate
- Tail loss
- Calendar-year stability
- Market-regime stability
- Capacity and ADV usage
- Correlation to Momentum
- Correlation to Low Volatility
- A/B/C directional consistency

### Required controls

- No parameter changes after results are viewed.
- No substitution of A or C for B because they performed better.
- No removal of difficult years, names, sectors, or the short side.
- No unregistered metrics may become decision metrics.
- Results must be reproducible from immutable inputs and frozen code.

### Required deliverables

- `ValidationPortfolioReplayManifest_v1.0.json`
- `ValidationMetricsReport_v1.0.json`
- `ValidationDSRReport_v1.0.json`
- `ValidationConfigurationComparison_v1.0.json`
- `ValidationRegimeAndConcentrationReport_v1.0.json`
- `ValidationDeterminismReport_v1.0.json`
- `ValidationVerdict_v1.0.md`

---

## 4.5 Phase 3 decision gate

| Verdict | Meaning | Next step |
|---|---|---|
| `VALIDATION_PASS` | Config B clears all preregistered gates | Prepare sealed OOS authorization |
| `VALIDATION_INCONCLUSIVE` | Evidence is insufficient | Stop; do not consume OOS |
| `VALIDATION_FAIL` | Config B fails a governing gate | Reject/archive MR-002 |
| `INTEGRITY_FAILURE` | Results are not interpretable | Repair integrity issue without performance interpretation |

A sealed OOS run may be requested only when:

- every validation integrity gate passes;
- Config B passes the preregistered primary gate;
- results are not concentrated in one year, sector, side, or small issuer group;
- realistic execution and costs do not remove the effect;
- A/B/C behavior is directionally coherent;
- no post-validation tuning is requested.

---

# 5. Phase 4 — Single Sealed OOS Run

## 5.1 Goal

Obtain the final unbiased research verdict for Config B through exactly one sealed OOS run.

## 5.2 Authorization package

Before OOS is opened, freeze:

- Config B parameters
- Signal and portfolio code identities
- Data-source identities
- Portfolio constraints
- Execution and cost assumptions
- Metric definitions
- Pass/fail criteria
- OOS partition identity
- Exact output artifact list
- Proof that OOS has never been read

## 5.3 Execution rules

- Open OOS exactly once.
- Evaluate Config B only.
- No parameter or code changes after opening.
- No switching to Config A or C.
- No change to costs, holding period, universe, sides, or constraints.
- No new market filter.
- No revised primary metric.
- No selective exclusion of unfavorable periods or names.

## 5.4 Required deliverables

- `OOSOpeningAuthorization_v1.0.json`
- `OOSOpenedObjectLedger_v1.0.json`
- `OOSExecutionManifest_v1.0.json`
- `OOSMetricsReport_v1.0.json`
- `OOSValidationComparison_v1.0.json`
- `OOSDeterminismReport_v1.0.json`
- `FinalResearchVerdict_v1.0.md`
- `MR002ProgramDisposition_v1.0.json`

## 5.5 Final research verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | Proceed to product-viability assessment |
| `INCONCLUSIVE` | Archive as research; no product strategy |
| `FAIL` | Reject and archive |
| `INTEGRITY_FAILURE` | Adjudicate without interpreting performance |

---

# 6. Phase 5 — Product-Viability Assessment

## 6.1 Goal

Determine whether a research-passing signal is operationally and economically suitable for paper trading.

A successful OOS result does not automatically authorize product implementation.

## 6.2 Required assessment areas

### Economic viability

- Net return after realistic costs
- Sharpe and Calmar after costs
- Capacity
- ADV participation
- Spread and slippage sensitivity
- Delayed-open sensitivity
- Long/short contribution
- Borrow and locate assumptions
- Borrow-cost sensitivity
- Turnover
- Exposure during pending exits

### Operational viability

- Short-order rejection behavior
- Partial fills
- Pending exits
- Account lock behavior
- Circuit-breaker behavior
- Risk-reducing closes
- Publication availability
- Stale or partial publication handling
- Position and order reconciliation
- Restart safety
- Multi-user isolation

### Diversification value

- Correlation with Momentum
- Correlation with Low Volatility
- Stress-period correlation
- Drawdown contribution
- Marginal Sharpe
- Marginal Calmar
- Capital efficiency
- Tail-risk interaction

## 6.3 Allowed decisions

- `PROMOTE_STANDALONE_PAPER`
- `PROMOTE_REFERENCE_ONLY`
- `RESEARCH_VALID_BUT_NOT_OPERABLE`
- `REJECT`

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

The product strategy must not recompute:

- sector factors;
- OLS residuals;
- return normalization;
- z-scores;
- candidate beta;
- PIT sector mapping;
- eligibility;
- ADV;
- official next-open price.

The product adapter must fail closed when:

- a publication is missing;
- a publication is partial;
- a manifest identity is stale or mismatched;
- record counts do not reconcile;
- the official-open enrichment is unavailable;
- a required source identity changes.

## 7.4 Paper strategy deliverables

- Product-adapter specification
- Immutable-publication consumer
- Standalone strategy template
- Activation script
- Risk-limit configuration
- Short/borrow operating policy
- Paper runbook
- Incident runbook
- Walk-away criteria
- Daily reconciliation report
- Position/order/fill audit
- Paper-observation report

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

---

# 8. Phase 7 — Optional Multi-Sleeve Interaction Study

## 8.1 Goal

Determine whether MR-002 should remain standalone or become a portfolio sleeve alongside Momentum and possibly Low Volatility.

## 8.2 Governing restriction

This is a separate research study. MR-002 must not be inserted directly into existing Momentum or Range Trader signal logic.

## 8.3 Candidate comparisons

- Momentum alone
- Existing Combined Book
- Momentum + MR-002
- Momentum + Low Volatility + MR-002

## 8.4 Required metrics

- Marginal Sharpe
- Marginal Calmar
- Maximum drawdown reduction
- Worst-year impact
- Stress-period correlation
- Gross exposure efficiency
- Turnover increase
- Capacity interaction
- Tail-loss contribution

## 8.5 Allowed decisions

- `STANDALONE_ONLY`
- `ADD_AS_FIXED_WEIGHT_SLEEVE`
- `REFERENCE_ONLY`
- `REJECT_PORTFOLIO_INTEGRATION`

Any sleeve weights must be preregistered before evaluation.

---

# 9. Phase 8 — Live-Money Readiness

## 9.1 Goal

Determine whether the complete research, paper, operational, and risk record justifies a limited real-capital canary.

## 9.2 Minimum prerequisites

- Sealed OOS pass
- Product-viability pass
- Standalone paper observation completed
- Borrow/short handling proven
- Risk-reducing closes proven under locks
- Publication SLA proven
- Order/fill/position reconciliation proven
- Multi-user isolation proven
- Incident and walk-away runbooks approved
- Explicit owner capital and loss limits
- Required ADRs accepted
- Separate live authorization

## 9.3 Initial live target

- Dedicated account
- Small fixed capital allocation
- Low gross cap
- Strict per-name cap
- No multi-sleeve integration initially
- Daily operator review
- Automatic hold on evidence or reconciliation mismatch

No automatic progression from paper to live is permitted.

---

# 10. Recommended immediate developer assignment

The developer should work only on **Phase 3A — Validation Authorization Package**.

## Immediate tasks

1. Locate and review the governing preregistration v1.0.3.
2. Extract the exact validation and OOS partition definitions.
3. Extract the preregistered primary metric and thresholds.
4. Confirm DSR `N = 5`.
5. Define Config A/B/C roles without changing parameters.
6. Define the forward-return enrichment schema.
7. Define the execution-enriched candidate schema.
8. Bind official-open and cost-source identities.
9. Define pass/fail/inconclusive/integrity-failure rules.
10. Produce proof that OOS remains sealed and unread.
11. Prepare the Phase 3A artifacts.
12. Commit and stop for authorization before reading validation data.

## Explicitly prohibited during the immediate assignment

- Opening validation data
- Opening OOS data
- Computing returns
- Computing performance
- Ranking configurations
- Changing signal thresholds
- Changing holding period
- Modifying the frozen universe
- Modifying portfolio constraints
- Building a product strategy
- Integrating with a broker
- Adding MR-002 to Momentum, Range Trader, or Combined Book
- Starting UI work

---

# 11. Overall completion targets

## Research target

Establish whether Config B demonstrates reproducible, after-cost residual-reversion evidence in validation and one sealed OOS run.

## Product target

If research passes, operate a standalone paper strategy that consumes immutable signal publications without identity drift, future information, duplicate economics, risk bypass, or unreconciled orders.

## Portfolio target

Only through a separately preregistered interaction study, determine whether MR-002 improves portfolio drawdown and risk-adjusted behavior as an independent sleeve.

## Honest failure target

If validation or OOS fails, archive MR-002 without modifying existing live strategies or creating a post-hoc replacement configuration.

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

## Final instruction to the development team

Do not treat this roadmap as blanket authorization for all phases.

Only the specifically authorized phase may be implemented. Each phase must produce its evidence package, stop, and receive formal adjudication before the next phase begins.
