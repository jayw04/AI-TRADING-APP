# MR-002 Pre-Registration v0.2 Review and Recommendations

**Reviewed document:** `TradingWorkbench_MR002_PreRegistration_v0.2.md`  
**Review date:** 2026-07-11  
**Overall assessment:** Strong revision, but not yet ready to freeze.

---

## Overall Assessment

**v0.2 is materially stronger and incorporates nearly all of the prior review correctly.** The signal normalization, testing sequence, cost model, capacity assumptions, sealed-OOS governance, PBO treatment, breadth gates, and Q1-Q5 decisions are much clearer.

I would rate it **about 85-90% ready**, but I would **not freeze v1.0 yet**.

The statement that freeze is blocked by “exactly two items” is too optimistic. V1 and V2 are genuine blockers, but several remaining specifications could still change trading results materially.

## Recommended Disposition

> **Advance to Draft v0.3. Do not freeze.**  
> Retain V1 and V2 and add three specification blockers: execution-price integrity, deterministic portfolio-risk calculations, and regime definitions.

---

# What v0.2 Fixed Well

The following changes are strong and should be preserved:

- Sector-relative return replaced the original raw sector factor.
- The residual z-score is now mean-adjusted and uses normalization data through `t-1`.
- Missing-data, `ddof`, lookback and winsorization rules are explicit.
- Config B remains the only sealed-OOS verdict configuration.
- A and C are properly restricted to development and validation.
- PBO is correctly demoted to a diagnostic.
- DSR uses a trial ledger instead of assuming three trials.
- Gross exposure is now a maximum rather than a forced target.
- The volatility overlay is secondary and cannot improve the primary verdict.
- Capacity is attached to a real reference NAV.
- The earnings and historical-sector data risks are correctly elevated to freeze blockers.
- The strategy remains independent from RNG-001.

These changes significantly improve the credibility of any eventual result.

---

# Remaining Freeze Blockers

## 1. V1 — PIT Earnings Calendar

V1 is correctly identified as a blocker, but the eventual rule needs to cover more than the historical event date.

The verified data must include:

- The date and timestamp when the earnings schedule became known
- Subsequent schedule revisions
- Whether the announcement was before market open, during the session, or after market close
- The exchange trading session associated with the event

A calendar containing the final realized earnings date is **not** sufficient.

### Recommended Entry Exclusion

Rather than only using calendar dates, define the prohibited exposure interval operationally:

- An earnings event before market open on `t+1` prohibits an entry at the `t+1` open.
- An event after market close on `t+1` may permit entry at the `t+1` open but must force exit before that close, unless overnight earnings exposure is intentionally permitted.
- Schedule changes are recognized only when their revised timestamp becomes available.

Because the strategy can hold for five sessions, the rule should test whether an earnings event falls anywhere within the **expected remaining holding period**, not merely whether it is within two sessions of initial entry.

The current `[t-2, t+2]` window may allow a position entered at `t+1` to remain exposed to earnings on `t+3`, `t+4`, or `t+5`.

### Better Rule

> Do not open a position when a PIT-known earnings announcement falls between the proposed execution time and the maximum possible exit time. An existing position exits at the last executable open before the event.

This more directly prevents earnings contamination.

---

## 2. V2 — PIT Sector History

V2 is also correctly identified.

The historical sector record must establish:

- Effective date
- Previous classification
- New classification
- Timestamp when the classification became available
- Mapping to the registered ETF proxy

Using today’s sector classification across the full history would contaminate both the residual model and the eligibility universe.

A documented approximation with “measured reclassification rates” should not automatically be accepted. Because sector identity enters the actual trading signal, an approximation could materially affect entries.

### Recommended Rule

Accept only:

1. A genuinely point-in-time sector or industry history; or
2. A historically effective SIC/NAICS classification converted through a frozen mapping table.

The second option should include a mapping-table hash in the evidence package.

---

## 3. Add V3 — Execution-Price and Adjustment Integrity

The strategy uses:

- Dividend-adjusted returns for the signal
- Next-session open for executions
- Prior close and next open for the gap filter
- Final prices or consideration for delistings

These data series must not be mixed without a registered adjustment policy.

### Principal Problem

An ex-dividend event can appear as an overnight price gap even though it is not an economic loss. A stock split can also distort the relationship between the prior close and next open when differently adjusted fields are used.

Register separate series:

- **Signal returns:** total-return-adjusted series
- **Execution prices:** split-adjusted, non-dividend-adjusted open and close
- **Gap calculation:** economically adjusted for splits and known cash distributions
- **Dollar volume:** a price-and-volume pair using mutually consistent split adjustments

The monthly dollar-volume ranking should explicitly use either:

```text
raw close × raw volume
```

or an equivalent consistently split-adjusted price and volume pair.

### Halt Rule Is Not Implementable with the Declared Data

The document says a halted position executes at the first available regular-session print after resumption. Sharadar daily data will generally not identify that print or its exact time.

Replace this with:

> Entries without a valid official opening price are cancelled. Exits without a valid official opening price remain pending and execute at the next available official regular-session open.

Do not assume an intraday first-print fill unless intraday data is added to the frozen data plan.

### Delisting Treatment

“Final available price or announced cash consideration” remains too flexible. Register a priority order:

1. Vendor-provided delisting return or cash consideration
2. Verified transaction consideration
3. Final executable market price
4. Conservative fallback defined in advance

The fallback must handle bankruptcies and securities that disappear without a valid final quote.

---

## 4. Portfolio Construction Remains Partly Ambiguous

The revised construction is much better, but several formulas are still not executable without interpretation.

### Position Cap

“1.5% of gross” is recursive because gross exposure is itself determined by the feasible positions.

Use:

> Maximum position market value = 1.5% of current portfolio NAV.

This is simpler and deterministic.

### Projected Risk Cap

The rule that no position may exceed 3% of projected portfolio risk lacks:

- Covariance estimator
- Lookback
- Minimum observations
- Shrinkage rule
- Treatment of missing values
- Risk-contribution formula

Since inverse residual-volatility weighting already controls individual risk, I recommend **removing the 3% projected-risk-contribution cap from MR-002** rather than introducing a new covariance-model degree of freedom.

It can be evaluated later as a post-verdict portfolio overlay.

### Beta Limit

Define it mathematically:

```text
portfolio_beta = Σ(weight_i × beta_i)
normalized_beta = |portfolio_beta| / gross_exposure
normalized_beta <= 0.10
```

Specify whether weights are signed fractions of NAV.

### Fixed Shares Versus Maintained Neutrality

The document says:

- Existing positions remain at fixed shares.
- Long and short books are dollar neutral.
- Mandatory reductions can occur daily.

Price changes will naturally destroy dollar neutrality even when shares remain fixed.

Register one of these policies:

1. **Entry-neutral:** books are matched when orders are opened, but normal price drift is allowed until an actual limit is breached; or
2. **Daily-neutral:** the larger side is reduced every day to match the smaller side.

I recommend **entry-neutral with tolerance bands**, because daily-neutral rebalancing will materially increase turnover and costs.

Suggested limits:

- No rebalance while net dollar exposure remains within ±5% of gross.
- Reduce only when the limit is exceeded.
- Reduce the least extreme or oldest positions first according to one frozen rule.

### Candidate Removal Ambiguity

“Remove the least extreme candidate and re-apply” conflicts with “freed capacity goes to cash, not redistribution.”

Clarify that removal does not cause the remaining positions to be renormalized upward. Otherwise the same removal can increase all other weights.

---

## 5. Regime Gates Need Frozen Definitions

Regime concentration is a mandatory gate, but the document does not define:

- Bull
- Bear
- Sideways
- High volatility
- Low volatility

This creates a post-hoc classification opportunity and must be resolved before freeze.

### Suggested Trend-Axis Definition

Using information through the prior session:

- **Bull:** SPY trailing 126-session total return greater than +5%
- **Bear:** trailing 126-session total return below -5%
- **Sideways:** between -5% and +5%

### Suggested Volatility-Axis Definition

- **High volatility:** SPY trailing 21-session annualized realized volatility >= 20%
- **Low volatility:** below 20%

Treat trend and volatility as **separate regime axes**. Do not combine their P&L shares into one denominator because the categories overlap.

### Reconsider the 60% Concentration Gate

A mean-reversion strategy may legitimately earn most of its return during high-volatility liquidity disruptions. Profit concentration in that regime may support rather than contradict the hypothesis.

A better mandatory gate would be:

- Positive net P&L in at least two of the three trend regimes
- No trend regime contributes more than 60% of total losses
- Neither volatility regime has Sharpe below -0.50, subject to adequate observations

Keep positive-P&L regime concentration as a diagnostic rather than an automatic rejection criterion.

---

# Additional High-Priority Clarifications

## 6. The Sector-Relative Factor Does Not Fully Remove Collinearity

The current definition is:

```text
f_sector = r_sector - r_SPY
```

This generally **reduces** market correlation but does not guarantee orthogonality because a sector ETF’s market beta is rarely exactly 1.0.

Change the wording from “removes SPY collinearity” to “reduces SPY collinearity.”

A more rigorous factor would be:

```text
r_sector,t = a + beta_sector × r_SPY,t + u_sector,t
```

Then use `u_sector,t` as the sector-specific factor.

My preference is to orthogonalize the sector factor using a rolling regression ending at `t-1`. It gives the stock regression a clearer interpretation:

- SPY factor: broad market
- Orthogonal sector factor: sector-specific movement
- Residual: stock-specific movement

This should be decided before freeze because it changes the signal.

---

## 7. Add an Implementation-Freeze Stage

The document freezes the strategy specification before development, but development is where code defects will be discovered.

Add two distinct freezes:

### Research-Design Freeze

Occurs before development data is inspected. This freezes:

- Hypothesis
- Parameters
- Data rules
- Gates
- Samples

### Implementation Freeze

Occurs after the development sample is used for harness verification but before validation begins. This freezes:

- Source-code commit
- Dependency lockfile
- Data transformation code
- Unit and synthetic tests
- Configuration hash
- Data snapshot identifiers

After implementation freeze:

- Validation may run.
- Only genuine implementation defects may be corrected.
- Any correction requires a documented defect report and a complete validation rerun.
- No economic-rule change is permitted.
- The sealed OOS remains unopened until the corrected implementation is frozen again.

This distinction is essential. Otherwise the strategy can be conceptually frozen while its implementation continues to change.

---

## 8. Register a Sealed-Run Defect Policy

Define what happens when a bug is discovered after sealed OOS.

Recommended rule:

> A material implementation or data defect invalidates the sealed result. The result remains archived but cannot support a verdict. The corrected strategy requires MR-003 or a newly identified untouched test period. Typographical, display-only, and non-calculation reporting corrections may be applied without creating a new program.

Also define “material” as anything capable of changing:

- Orders
- Position size
- Cost
- Daily return
- Sample membership
- Any pass/fail statistic

---

## 9. Borrow Availability Remains an Unresolved Limitation

Top-150 liquidity and 300-bps borrow stress improve realism, but they do not address a stock that simply could not be borrowed.

“Exclude any available HTB flag” is not a complete rule unless the historical flag source is registered and PIT.

Either add borrow availability to the data-verification stage or explicitly state:

> No reliable PIT historical borrow-availability data is available. The primary backtest assumes availability in the top-150 universe. Mandatory diagnostics deny the most extreme 10% and 25% of short signals and apply 300-bps and 1,000-bps annual borrow costs.

The denial test should remove the strongest short opportunities, not random positions, because unavailable borrow frequently affects crowded or extreme names.

This does not necessarily need to block freeze, but it must be clearly disclosed.

---

## 10. Annual Concentration Gate May Be Structurally Too Strict

Validation plus sealed OOS represents approximately five years if the full sample is ten years.

With only two positive years, the largest positive year must contribute at least 50%. With three positive years, it must contribute at least 33.3%. Therefore, the 35% threshold nearly requires four or five similarly profitable years.

A more practical rule is:

- At least three positive calendar years across validation plus OOS
- Largest positive year <= 50% of total positive annual P&L
- Annual P&L Herfindahl concentration reported as a diagnostic

The present 35% gate may reject a genuine strategy because of a single strong year rather than because of a fragile handful of trades.

---

# Smaller Corrections

1. **Monthly universe timing:** define whether reconstitution is calculated after the prior month-end close and effective on the first session, or after the first session close and effective on the second session.

2. **Percentile universe:** state that long percentiles are calculated among long-eligible names and short percentiles among short-eligible names.

3. **Tie-breaking:** sort by z-score, then by ticker or permanent security identifier.

4. **Five-session hold:** specify whether the entry session counts as session 1.

5. **Fold construction:** divide validation into five nearly equal contiguous trading-session blocks, with any remainder assigned according to a fixed rule.

6. **DSR implementation:** freeze the formula, software implementation, treatment of skew/kurtosis and exact trial-ledger count before development results are reviewed.

7. **MOM-001 correlation:** freeze the MOM-001 artifact hash and calculate correlation using aligned net daily returns, with no volatility rescaling.

8. **Capacity execution:** acknowledge that filling up to 2% of full-day ADV at the official opening price assumes adequate opening-auction capacity. Report this as a modeling limitation unless opening-auction volume is available.

---

# Revised Blocker List

I recommend replacing the “exactly two” statement with:

## Mandatory Data Blockers

- V1 — PIT earnings schedule
- V2 — PIT historical sector classification
- V3 — Consistent signal, open, gap, dollar-volume and delisting price series
- V4 — Historical borrow/HTB source or an explicitly approved no-data fallback

## Mandatory Specification Blockers

- S1 — Sector-factor orthogonalization decision
- S2 — Portfolio constraint formulas and fixed-share neutrality policy
- S3 — Frozen market-regime definitions and revised regime gate
- S4 — Implementation-freeze and sealed-run defect protocol

---

# Final Recommendation

Move to **v0.3 DRAFT**, resolve the blocker list, and then freeze v1.0.

Do not change the core hypothesis, z-entry levels, five-day holding period, universe breadth, or sealed-OOS structure. The remaining work is principally about eliminating implementation discretion—not trying to improve the anticipated backtest result.

Once those definitions are closed, MR-002 will be suitable for a credible first run.
