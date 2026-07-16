Overall assessment

v0.3 is a major improvement and is now close to freeze-ready. It successfully resolves the earlier S1–S4 issues: the sector factor is properly orthogonalized, portfolio constraints are more deterministic, regime definitions are frozen, and the two-stage implementation governance is strong.

I would rate it approximately 92–95% ready.

I do not recommend another broad redesign. Keep the hypothesis, thresholds, holding period, universe and pass gates unchanged. However, I found two remaining freeze-level issues and several smaller implementation clarifications that should be incorporated before v1.0.

Recommended disposition

Conditionally approve v0.3.
Make a targeted v0.4 or v0.3.1 addressing the items below, complete V1–V4, freeze exact dates and data snapshots, and then proceed to Research-Design Freeze.

Two remaining freeze-level issues
1. Move the Data Availability Gate before Research-Design Freeze

The current lifecycle says:

Complete V1–V4
Research-Design Freeze
Run the Data Availability Gate
Determine the realized data window
Split it 50% / 25% / 25%

This creates a governance weakness. The exact development, validation and sealed-OOS dates are not known when the research design is frozen. If data availability changes the start or end date afterward, it also changes the sealed period.

Required correction

Run the Data Availability Gate before Research-Design Freeze, but do not calculate signals or strategy results.

Before v1.0 is signed, record:

Exact first and last eligible trading dates
Exact development start and end dates
Exact validation start and end dates
Exact sealed-OOS start and end dates
Trading calendar
Treatment of partial first and last calendar years
Stock-data snapshot hash
ETF-data snapshot hash
Corporate-event snapshot hash
Earnings-calendar snapshot hash
Sector-history or mapping-table hash

Recommended sequence:

V1–V4 verification
→ Data Availability Gate
→ Freeze exact data window and sample boundaries
→ Research-Design Freeze v1.0
→ Development implementation
→ Implementation Freeze
→ Validation
→ Sealed OOS

The data snapshot should be pinned before development, not first pinned at Implementation Freeze. Otherwise vendor revisions could cause development and validation to use different historical values.

2. Define incremental portfolio allocation with existing positions

Section 5 is much more deterministic, but the allocation rule still reads partly like a new portfolio is created every day:

Long gross = short gross = minimum feasible side, capped at 50% of NAV.

However, existing positions remain at fixed shares for up to five sessions. New orders must therefore be sized relative to:

Existing long gross
Existing short gross
Existing sector exposure
Existing beta
Remaining gross-exposure headroom

Without an incremental formula, two valid implementations could produce materially different trades.

Recommended formula

At each execution open, after exits:

current_gross = current_long_gross + current_short_gross
gross_headroom = max(0, 100% NAV - current_gross)

long_increment_capacity =
    min(candidate_long_capacity,
        long-side constraint headroom,
        gross_headroom / 2)

short_increment_capacity =
    min(candidate_short_capacity,
        short-side constraint headroom,
        gross_headroom / 2)

matched_increment =
    min(long_increment_capacity, short_increment_capacity)

New long and short orders are each limited to matched_increment.

Also register that:

Candidate weights are normalized to the incremental matched amount, not 50% of NAV.
The 1.5%-of-NAV position cap applies after combining an order with any existing exposure, although pyramiding is prohibited.
Unused incremental capacity remains cash.
Existing positions are not increased to consume unused headroom.
Constraint-reduction targeting

The current “remove the smallest |z| candidate” rule may not fix the actual constraint.

Use targeted removal:

Sector-cap breach: remove the least-extreme candidate in the offending sector.
Beta breach: remove the candidate whose exclusion produces the largest reduction in absolute normalized beta; tie-break by smallest |z|.
Gross breach: remove the globally least-extreme candidate.
Net-exposure drift: reduce the larger side according to the registered entry-z ordering.

This makes the algorithm executable without discretionary interpretation.

Important implementation clarifications
3. Clarify the nested point-in-time sector residual

The orthogonalized sector factor is conceptually correct, but its historical construction should be explicit.

For every historical session s, the value u_sector,s used in the stock regression must be generated from a sector regression estimated using data ending at s−1.

In other words, the stock model estimated at t should use a stored PIT sequence:

u_sector,t-60, u_sector,t-59, ..., u_sector,t-1

Each value must have been calculated using only information available before its own session.

Do not estimate one sector regression at t−1 and apply those coefficients retrospectively across all prior 60 observations. That would produce an internally inconsistent factor history.

Recommended wording:

Each historical sector-factor observation is generated recursively and point-in-time. For every session s, coefficients estimated through s−1 are applied to session s. The stock regression at t uses these previously generated PIT sector residuals for sessions t−60 … t−1.

Also specify:

OLS includes an intercept.
No ridge regularization is used.
If the regression is singular or sector-factor variance is zero, the observation is unavailable and the stock is ineligible.
4. Handle late earnings-calendar revisions

The earnings rule works when the event schedule is known early enough. It does not explicitly address a schedule revision announced after the registered “last executable open.”

Example:

Earnings is moved to before market open Tuesday.
The revision becomes known Monday afternoon.
The stated last executable open was Monday morning, which has already passed.

The backtest must not exit retroactively.

Add:

If an earnings schedule or revision becomes known after the registered last pre-event open, exit at the first executable open after the information becomes available. Record the unavoidable event exposure as an earnings-calendar exception. No retroactive fill is permitted.

Report:

Number of late revisions
Positions affected
P&L attributable to unavoidable event exposure
5. Restore the corporate-action exit rule

Section 4 blocks entries after announced corporate actions, but the exit list does not clearly say what happens when a merger, delisting or other prohibited action is announced while a position is already open.

Add to the exit rules:

A newly announced prohibited corporate action forces exit at the next available official open.

This preserves the original intention that the strategy measures liquidity reversion rather than merger, delisting or restructuring outcomes.

6. Define missing-signal behavior for open positions

The document says a stock with a missing observation is ineligible for signal calculation, but it does not specify what happens if the stock is already held.

Recommended rule:

A missing z-score does not itself trigger an immediate exit.
The time stop continues to advance.
Earnings and corporate-action exits remain active.
If a valid official open exists, the scheduled time-stop exit still executes.
If the official open is missing, the exit remains pending under the existing missing-open rule.
Missing z-score days are counted and reported.

This prevents a vendor-data gap from either silently extending or prematurely closing the position.

Metric and verdict clarifications
7. Define “profitable” consistently

Several gates use the word “profitable”:

Cost stress
A and C parameter stability
Capacity
Regime results

Define it once:

“Profitable” means cumulative net return greater than zero over the named evaluation sample, after all registered execution, transaction-cost and borrow assumptions.

For parameter stability, consider requiring both:

Positive cumulative validation return
No configuration has validation Sharpe below −0.25

This avoids declaring a configuration stable because of a tiny positive result driven by one trade. The additional Sharpe condition is optional; do not add it if you want to avoid changing the existing gate.

8. Define the regime-loss denominator

“No trend regime contributes more than 60% of total losses” remains ambiguous.

Use:

loss_contribution_regime =
    sum(abs(negative daily net P&L in that regime))
    /
    sum(abs(negative daily net P&L across all trend regimes))

This should use:

Net daily P&L
All evaluation trading days
Each day assigned to exactly one trend regime
Zero-exposure days retained in the daily return series but contributing no loss

For the volatility-regime Sharpe gate, define “60 sessions of exposure” as:

At least 60 trading sessions with nonzero gross exposure in the applicable volatility regime.

9. Freeze the standard performance formulas

Add a short metrics appendix or reference a versioned canonical platform metrics specification.

At minimum, define:

Sharpe annualization factor: sqrt(252)
Risk-free rate: zero or registered cash rate
Standard deviation convention
CAGR formula
Calmar denominator
Maximum-drawdown calculation
Treatment of zero-exposure days
Whether returns are calculated on prior-day or current NAV
Whether borrow cost accrues on calendar days or trading days

Recommended:

Include every exchange trading session in the daily return series, including zero-exposure days.
Accrue borrow cost daily using a declared annual rate / 360 or annual rate / 365 convention.
Calculate transaction costs against traded notional at execution.
Data-verification comments
V1

Well specified. Approve after verifying that the source contains genuinely historical known-at timestamps and revisions—not merely current/final event dates.

V2

Well specified. A frozen historical SIC/NAICS mapping is an acceptable fallback, provided:

The historical classification itself is effective-dated.
The mapping does not use future company information.
Mapping exceptions are logged.
The mapping hash is frozen before development.
V3

The four-series policy is correct, but register the exact gap formula. For a cash distribution D effective at the t+1 open, use a defined economic adjustment such as:

economic_gap =
    (split_adjusted_open_t+1 + known_cash_distribution_t+1)
    /
    split_adjusted_close_t
    - 1

Confirm the exact vendor field semantics before adopting the formula.

V3 should not require vendor delisting consideration in every case because §4 already defines a fallback. Its acceptance rule should instead be:

Verify which delisting fields are available and apply the registered priority order without discretionary substitution.

V4

The fallback is reasonable and appropriately conservative. Clarify that short-signal denial is applied:

Among otherwise eligible short entries
Each entry date
Before portfolio sizing
Beginning with the most extreme positive z-scores
Delisting fallback comment

The long fallback of zero is conservative.

The short fallback of covering at the last available close is not necessarily conservative. It may understate losses when a short security disappears during an acquisition or reorganization.

A safer fallback is:

Short fallback cover price = the greater of the last available close and any identifiable announced cash or exchange consideration. If neither can be verified, use the last close plus a registered punitive markup, such as 25%.

Because true delisting proceeds should normally be available through the higher-priority rules, this fallback should be rare. The number and P&L impact of fallback cases must be reported.

Final recommendation

Make one targeted revision containing these items:

Must resolve before freeze
Move the Data Availability Gate and exact sample-date freeze before Research-Design Freeze.
Freeze all data snapshot identifiers before development.
Define incremental allocation around existing positions.
Define targeted constraint reductions.
Clarify PIT construction of historical sector residuals.
Add as deterministic edge-case rules
Late earnings-calendar revisions.
Corporate-action announcements affecting open positions.
Missing z-scores for open positions.
Exact metric and regime-loss formulas.
V3 and delisting fallback details.

After those corrections and successful V1–V4 verification, I would support Research-Design Freeze v1.0. The strategy no longer needs another conceptual redesign; the remaining work is implementation determinism and data provenance.

Decision

I approve both proposed resolutions, with one important correction to V1.

The verification is well executed and the raw findings support the report: Sharadar EVENTS has no forward rows or known-at timestamps, TICKERS is a current snapshot, SEP’s close and volume share a consistent split-adjusted basis, and no PIT borrow source exists in the current stack.

V1 — Approve Option 1, with a corrected blackout rule

Approve the EDGAR-derived PIT estimated earnings exclusion.

However, do not freeze the proposed 80–100 trading sessions window. Eighty to one hundred trading sessions is approximately four to five months, not one quarter. It would often begin after the next quarterly earnings release and therefore fail its purpose.

Recommended frozen rule

For each stock, the most recently confirmed earnings release derived from an EDGAR 8-K Item 2.02 filing becomes the PIT anchor. Beginning 70 calendar days after that release, the stock becomes ineligible for new entry and any existing position exits at the first available official open. The stock remains ineligible until the next confirmed earnings release resets the anchor.

This one-sided blackout is preferable to a finite 80–100 window because:

It uses only information known at the time.
It does not assume the next release will occur by a fixed ending date.
A delayed earnings release cannot become tradable again accidentally.
It remains conservative without requiring a paid calendar.
It allows EDGAR coverage to extend the research window before Sharadar EVENTS’ approximately 2016 floor.

Register these additional rules:

A stock without a prior confirmed earnings anchor is ineligible.
Use the SEC filing acceptance timestamp to assign the event session.
Acceptance before the regular-session open is treated as BMO.
Acceptance after the regular-session close is treated as AMC.
Ambiguous or in-session acceptance is treated conservatively as BMO.
No retroactive exit is permitted.
If an earnings filing is discovered after an expected exit should have occurred, exit at the first executable open after the filing becomes known and record an exception.
Validate that the selected EDGAR form/item consistently represents earnings releases; do not assume every 8-K is an earnings event.

This is not a true forward calendar, so the evidence report should call it:

PIT estimated earnings-risk blackout

It should not be described as a PIT earnings schedule.

Optional diagnostic

After the primary design is frozen, report—but do not use for selection—a diagnostic using blackout starts at 60 and 80 calendar days. The primary verdict must remain based on 70 calendar days only.

V2 — Approve the EDGAR-SIC build

Approve the EDGAR-derived effective-dated SIC history and frozen mapping-table implementation.

This is the correct resolution because Sharadar TICKERS demonstrably contains only current classification values and would introduce historical look-ahead.

However, the mapping table must be effective-dated, not merely a single static SIC-to-sector lookup.

A static table may still mishandle historical sector reorganizations. For example, a company’s SIC may remain unchanged while its market-sector classification or appropriate ETF proxy changes.

Required implementation

For each security:

Join EDGAR filings to the permanent security identifier through a frozen CIK/permaticker crosswalk.
Extract the SIC from each accepted filing.
Make the SIC effective at the filing acceptance timestamp.
Forward-fill it only until the next accepted filing supplies a new SIC.
Map the PIT SIC through an effective-dated SIC-to-sector-ETF table.
Exclude unresolved or conflicting records; never silently fall back to the current TICKERS sector.
Freeze the mapping-table SHA-256 and crosswalk SHA-256 before development.

The mapping table should therefore contain fields similar to:

sic_start
sic_end
effective_from
effective_to
research_sector
sector_etf
mapping_rationale

For historical taxonomy changes, the date ranges must be explicit. If a valid proxy did not exist during a period, follow the registered rule and exclude the stock for that period.

Required validation sample

Before freeze, manually verify a representative group containing:

Known historical sector reclassifications
Ticker changes
Acquisitions and spin-offs
Dual-class companies
Companies whose SIC changed
Companies whose market sector changed without a SIC change

META should be one of the mandatory test cases because the verification already demonstrated its current classification cannot safely be applied to its complete history.

V3 — Accept with the registered amendment

Approve:

Dollar volume = SEP close × SEP volume

The vendor evidence shows that both fields are consistently split-adjusted, whereas closeunadj × volume would mix adjustment bases. The revised pair remains economically split-invariant.

Also fold these into v0.4:

Add the ACTIONS dividend-value basis check to Implementation Freeze.
Freeze the exact distribution-adjusted gap formula after confirming whether ACTIONS dividend values are expressed on the same split basis as SEP close.
Mark vendor delisting return as unavailable in the current data profile, rather than leaving it as an apparently active first-priority source.
Use transaction consideration, final executable price, and the registered conservative fallback in that order.
V4 — Approve the fallback

The registered borrow fallback is acceptable:

Primary test assumes borrow availability within the top-150 short universe.
Mandatory denial diagnostics remove the most extreme 10% and 25% of otherwise eligible short signals.
Mandatory borrow-cost stress uses 300 bps.
Severe diagnostic uses 1,000 bps.
The limitation must appear in every result artifact.

The live checks support the conclusion that Sharadar has no applicable PIT borrow table, FMP access is gated, and Alpaca’s flag is current-only.

Required v0.4 amendments

In addition to the five amendments already identified, v0.4 should include:

Replace the 80–100 sessions V1 proposal with the 70-calendar-day one-sided blackout.
Describe V1 as an estimated earnings-risk blackout, not a forward calendar.
Make the SIC-to-sector mapping table explicitly effective-dated.
Add the CIK/permaticker crosswalk to the frozen and hashed artifacts.
Move the full Data Availability Gate before Research-Design Freeze.
Freeze the exact development, validation and sealed-OOS dates in v1.0.
Pin the stock, ETF, filing and mapping data snapshots before development begins.
Report EDGAR coverage rates and the percentage of universe-months excluded because no PIT earnings anchor or sector mapping exists.
Freeze recommendation

Proceed as follows:

Build V1 EDGAR earnings anchors
→ Build V2 EDGAR SIC history and effective-dated mapping
→ Re-run V1/V2 verification
→ Run the full Data Availability Gate
→ Freeze exact data window and sample dates
→ Issue v0.4 for owner sign-off
→ Research-Design Freeze v1.0

With these conditions, V1 option 1 and the V2 build are approved. The strategy should not be frozen until the resulting coverage, exclusion rates, hashes and exact sample boundaries are documented.