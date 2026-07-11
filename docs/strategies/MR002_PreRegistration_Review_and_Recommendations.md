# MR-002 Pre-Registration Review and Recommendations

**Reviewed document:** `TradingWorkbench_MR002_PreRegistration_v0.1.md`  
**Review date:** 2026-07-11  
**Reviewer assessment:** Strong draft, but not yet ready to freeze.

---

## Overall Assessment

This is a strong, governance-ready pre-registration draft and substantially better than a typical strategy specification. It correctly separates MR-002 from rejected RNG-001, preserves a sealed out-of-sample test, limits parameter searching, requires realistic costs, and defines a reproducible evidence package.

However, I recommend **not freezing v1.0 yet**. Several ambiguities could materially change the result or accidentally introduce look-ahead bias.

---

## Freeze Blockers

| Priority | Issue | Recommended correction |
|---|---|---|
| Critical | Signal standardization and factor collinearity | Redefine the sector factor and z-score precisely |
| Critical | Point-in-time event and sector data | Prove future earnings and historical sector labels are genuinely PIT |
| Critical | Portfolio construction is not fully executable | Register a deterministic allocation and rebalance algorithm |
| High | Testing sequence contains contradictions | Clarify where A/C configurations run and what remains sealed |
| High | PBO with only three configurations | Remove it as a mandatory gate or classify it as diagnostic |
| High | Bootstrap and power rules are underspecified | Register block method, block length, confidence and power |
| High | Capacity lacks a reference capital amount | Register test NAV and capacity calculation |
| Medium | Execution and corporate-action edge cases | Define gaps, adjusted opens, halts, delistings and re-entry rules |

---

# 1. Correct the Residual Signal Definition

The present model uses both SPY and the full sector ETF return:

```text
r_i = alpha + beta_m * r_SPY + beta_s * r_Sector + epsilon
```

Because sector ETFs are highly correlated with SPY, the two coefficients may be unstable. The residual can change significantly from small estimation differences.

Use a **sector-relative factor** instead:

```text
f_Sector,t = r_Sector,t - r_SPY,t
```

Then estimate:

```text
r_i,t = alpha_i
      + beta_m,i * r_SPY,t
      + beta_s,i * f_Sector,t
      + epsilon_i,t
```

This more clearly separates:

- Broad-market movement
- Sector-relative movement
- Company-specific movement

## Fix the z-score

The current signal divides the five-day residual by its standard deviation but does not subtract its historical mean. Even when residuals theoretically average zero, the rolling five-day residual series may not.

Use:

```text
R_resid_5,i,t = sum(epsilon_i,t-k), k = 0...4
```

```text
z_i,t = (R_resid_5,i,t - mu_i,t-1) / sigma_i,t-1
```

Register that:

- Mean and standard deviation use only windows ending through `t-1`.
- Exactly 60 complete five-day observations are required.
- Standard deviation uses `ddof=1`.
- Returns are arithmetic total returns.
- Missing observations make the stock ineligible that day.
- No winsorization is performed unless frozen in advance.

Without the `t-1` statement, the current-day signal may enter its own normalization denominator.

---

# 2. Resolve Point-in-Time Leakage Risks

## Earnings exclusions

Excluding earnings within `[t-2, t+2]` is valid only when the future earnings schedule was known on date `t`.

A historical table containing the final actual earnings date is not automatically point-in-time. Dates can be rescheduled.

Register one of these rules:

1. Use a historical earnings calendar containing the publication timestamp and only use schedules known at `t`; or
2. Acknowledge that upcoming-date availability is not PIT and restrict the exclusion to events that occurred through `t`.

The first option is preferable.

## Corporate actions

Do not exclude a stock because it eventually merged, delisted or reorganized. Exclusion must begin only after the public announcement became available.

Also specify:

- How trading halts are handled
- What happens when the expected next-session open is unavailable
- How delisting proceeds are valued
- That delisted securities are never silently dropped from the P&L series

## Sector classification

The availability audit must verify **historical point-in-time sector classifications**. Mapping historical returns using a company’s current sector can create classification look-ahead.

This should be a freeze blocker rather than only a manifest disclosure.

---

# 3. Make Portfolio Construction Deterministic

The present constraints cannot always produce 100% gross exposure.

With 250 stocks and the top/bottom 10% rule, there can be at most approximately 50 candidates. At a 1.5% position cap:

```text
50 x 1.5% = 75%
```

Absolute z-score and event filters will usually reduce this further.

Therefore, change **“100% gross exposure” to “100% maximum gross exposure.”** The strategy should hold cash rather than force marginal trades.

Register the following rules:

- One position per symbol; no pyramiding.
- Process exits before new entries.
- A symbol exited at `t+1` open cannot be re-entered at the same open.
- Existing positions remain at fixed shares until exit, except mandatory portfolio-risk reductions.
- Long and short gross exposures are matched to the smaller available side.
- Unused capital remains cash.
- No return is credited to unused cash in the primary strategy result; a cash-yield version can be reported separately.
- If constraints are infeasible, remove the least extreme candidate first.
- Define whether sector neutrality is dollar exposure, beta exposure or both.
- Define the exact order for reductions: position cap, sector cap, beta limit, volatility limit.

Recommended construction:

- Dollar-neutral long and short books
- Sector net exposure no greater than 5% of gross per sector
- Portfolio beta exposure no greater than 0.10 per unit of gross
- No forced trade solely to satisfy neutrality

## Volatility overlay

The 8% volatility target also needs clarification. It conflicts with the fixed 100% gross statement if leverage is not allowed.

Use:

> The 8% target is a scale-down overlay only. Exposure may never exceed 1.0x gross. The scale factor is calculated from returns through the prior session and is capped at 1.0.

Also define whether the scale factor rebalances all existing positions daily. Every such rebalance must incur transaction costs.

A cleaner alternative is to evaluate the unscaled strategy as the primary result and report the 8% overlay as a secondary portfolio transformation.

---

# 4. Correct the Test Sequence

The document says that all three configurations run in development “only,” but later requires A and C for the parameter-stability gate.

Recommended sequence:

1. **Development 50%:** A, B and C for implementation verification; no winner selection.
2. **Validation 25%:** A, B and C; B remains primary, while A/C determine neighborhood stability.
3. **Sealed OOS 25%:** B only, exactly once.
4. All OOS diagnostics use B unless explicitly defined otherwise.

Define the walk-forward validation as **five contiguous, non-overlapping folds**. Then “60% positive folds” has a clear interpretation: at least three of five folds must have positive net returns.

Also clarify:

- Parameter stability applies to validation, not development.
- “Full-test maximum drawdown” means validation plus sealed OOS, excluding development.
- Sealed-OOS maximum drawdown must still be reported separately.
- Universe sizes 200 and 300 should either be removed or designated as post-verdict diagnostics that cannot affect the verdict.

---

# 5. Reconsider PBO and DSR

## PBO

PBO is not reliable with only three configurations. There are too few alternatives for a stable combinatorially symmetric cross-validation estimate.

Recommendation:

- Remove `PBO < 20%` as a mandatory pass gate.
- Retain PBO as a clearly labelled diagnostic with a warning that `N=3` is underpowered.
- Rely primarily on pre-registration, sealed OOS, parameter neighbors and block-bootstrap evidence.

Adding many more configurations solely to make PBO calculable would be worse because it would create additional selection opportunities.

## Deflated Sharpe

Do not automatically declare `N_trials=3`. The effective trial count should account for related strategies and material variants already examined within the mean-reversion research family.

A/C may count conservatively, but RNG-001 and any informal MR variants should also be considered when calculating the effective multiple-testing burden. Document the trial ledger in the evidence package.

---

# 6. Specify the Bootstrap and Power Rule

“Date-clustered bootstrap” is insufficient for daily book returns. Resampling individual days independently would fail to preserve serial dependence created by five-day holdings.

Use a stationary or moving-block bootstrap:

- 10,000 replications
- Fixed registered random seed
- Expected block length: 5 trading days
- Additional 10-day block-length sensitivity
- 95% one-sided lower confidence bound for mean daily return
- Bootstrap performed on net daily portfolio returns

## Fix the power-limited rule

The current comparison of the observed effect with `MDE95` is not enough. Register an economically relevant effect before testing.

Recommended rule:

- Minimum relevant Sharpe: **0.40**
- Required power: **80%**
- Confidence level: **95%**

Then:

- Positive Sharpe, CI spanning zero, and power below 80% to detect Sharpe 0.40 -> **Power-Limited · Inconclusive**
- CI spanning zero with at least 80% power to detect Sharpe 0.40 -> **Rejected**
- Negative observed Sharpe -> **Rejected**, regardless of power label

---

# 7. Add Breadth and Economic-Significance Gates

The hypothesis explicitly says the edge comes from breadth and repeatability. The pass gates should test that claim.

Suggested minimum OOS requirements:

| Gate | Proposed requirement |
|---|---:|
| Completed trades | >= 500 |
| Distinct entry dates | >= 100 |
| Long trades | >= 100 |
| Short trades | >= 100 |
| Top 10 trades’ contribution | <= 20% of total positive trade P&L |
| Single stock contribution | <= 10% of total positive P&L |
| Net annualized return | >= 3% at the registered gross cap |

The annual-return gate prevents a very low-return strategy from passing solely because it exhibits low volatility and an acceptable Sharpe ratio.

For yearly concentration, define the denominator as:

> Maximum positive annual P&L divided by the sum of all positive annual P&L.

Otherwise, negative years or a small total P&L can make the 35% calculation misleading. Apply annual and regime concentration gates to **validation plus sealed OOS**, since the sealed OOS alone may contain only about two or three calendar years.

---

# 8. Register Capacity at a Specific NAV

“Positive under the 2% participation cap” is not testable without a portfolio size.

Recommendation:

- Reference backtest NAV: **$10 million**
- Order size capped at 2% of trailing 20-day median dollar volume
- Orders above the limit are clipped, not delayed
- Unfilled notional remains cash
- Report the maximum scalable NAV at which 95% of orders remain below the cap
- Produce capacity results at $10M, $25M, $50M and $100M as diagnostics

---

# Recommended Q1-Q5 Decisions

## Q1 — ID and revisions

Keep **MR-002**.

A substantive change after seeing sealed OOS should become **MR-003**, not MR-002-v2. This makes the additional research trial unmistakable.

Use MR-002 document versions only for:

- Corrections made before OOS
- Non-substantive documentation changes
- Reproduction of the identical frozen strategy

## Q2 — Costs

Keep:

- 10 bps per side base
- 20 bps per side mandatory stress
- 2% ADV participation cap

Add:

- 30 bps per side severe diagnostic
- 50 bps/year base borrow
- 300 bps/year borrow-uncertainty stress
- Long-only and short-only P&L attribution

## Q3 — Execution

Confirm **next-session open**.

The gap filter must specify which gap it examines. Use the **execution-day gap**:

```text
abs(Open_t+1 / Close_t - 1) < 6%
```

The order is cancelled at `t+1` open when this condition fails. The next-close implementation should remain diagnostic only.

## Q4 — Hard-to-borrow

Use:

- Top 250 universe for longs
- Top 150 by median dollar volume for shorts
- Exclude any available hard-to-borrow flags
- Apply the 300-bps annual borrow sensitivity

This is more defensible than assuming unrestricted general-collateral availability across the entire historical universe.

## Q5 — Sector history

Do **not** map XLC and XLRE mechanically to historical parent ETFs. That introduces a subjective and potentially unstable factor definition.

Preferred rule:

> Exclude stocks in a sector before that sector’s registered ETF proxy exists.

For a roughly ten-year test window, this mainly affects Communication Services before XLC inception. Historical PIT sector classification still must be verified.

---

# Final Recommendation

Move the document to **v0.2, not frozen**, and resolve the items above.

The strategy hypothesis itself should remain unchanged. Do not add momentum, volatility, RSI or market-regime filters before the first test. Those additions might make the development backtest look better but would weaken the evidentiary value.

The strongest elements to preserve are:

- Clean separation from RNG-001
- Fixed primary configuration B
- Sealed OOS run
- Cost stress
- No post-OOS adjustment
- Comprehensive evidence package

After the statistical and execution ambiguities are removed, MR-002 will be ready for a defensible freeze.
