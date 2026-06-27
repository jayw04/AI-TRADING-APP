I reviewed v1.1 in detail, and I think this is a meaningful improvement over v1.0. The architectural recommendations from the previous review have been incorporated well, and the document is now much closer to serving as a long-term reference for future strategy implementations rather than just a one-off implementation report.

Overall score: 9.95/10.

What improved significantly
1. The three-engine separation is the biggest improvement

This is now much cleaner:

Qualification Engine
        ↓
Ranking Engine
        ↓
Opportunity Assignment Engine
        ↓
Opportunity Registry
        ↓
Range Trader

This is a much stronger architecture than simply saying "Candidate Engine." It clearly separates:

Eligibility (hard filters)
Quality ordering (ranking)
Daily operational assignment

That separation will scale naturally to Momentum, Sector Rotation, Trend, Insider, and future strategies.

2. Opportunity Registry

I think adding ADR 0029 was the right decision.

The Opportunity Registry is no longer just a Range Trader concept.

It becomes a platform asset.

That aligns very well with the Discovery Lab vision.

3. Terminology

I agree with replacing

Evidence-first

with

Evidence-weighted

It is technically more accurate.

Likewise,

Opportunity Set

is much better than alternating between:

Top-N
Today's Universe
Today's Range Universe

Consistency will help both the whitepaper and future developers.

4. Weekly calibration

This is a very good change.

Waiting until day 40 to produce the first report would have been a mistake.

A weekly report lets you detect problems early without changing the research gate.

My remaining suggestions

There are only a few now.

1. Add a "Research Status" section (highest recommendation)

The document explains implementation beautifully.

It doesn't summarize where the research stands.

I would add a table like:

Hypothesis	Status	Promotion
H1 Candidate Selection	Implemented	Collecting Evidence
H2 Entry Logic	Implemented	Collecting Evidence
H3 Exit Logic	Partially Implemented	Future Evaluation
Opportunity Registry	Proposed	ADR 0029
Production Threshold	Not Started	≥40 trading days

That gives readers a one-page view of maturity.

2. Add Versioning for the Opportunity Set

You're freezing the Opportunity Set every morning, which is excellent.

I would add a simple identifier, for example:

Opportunity Set

2026-06-29

Version 1

or

Opportunity Set ID

2026-06-29-RNG-v1

Then:

audit
dashboard
backtests
calibration

can all refer to the same frozen input.

3. Separate Structural vs Research Parameters

This is a subtle point.

Currently hard filters and ranking parameters are documented separately.

I'd go one step further.

Document:

Structural Parameters
Price > $10
ADV > $50M

These should rarely change.

Research Parameters
ATR threshold
Oscillation weight
Historical weighting

These evolve.

That distinction becomes useful once more people work on the platform.

4. Composite Ranking

I like the discussion in Section 14.

I would avoid giving example percentages (40/60, 60/40) in the implementation report unless they are actually implemented.

Instead say:

Initial weighting will be calibrated empirically using forward evidence collected during the research period.

That keeps the document aligned with your Evidence Engineering philosophy.

5. Dashboard linkage

The new metrics in Section 16 are excellent.

I would explicitly state where they will appear.

Example:

Evidence Dashboard

↓

Selection Precision

↓

Opportunity Conversion

↓

Weekly Calibration

That connects the implementation to the platform UI.

6. Whitepaper alignment

This implementation now introduces concepts that should appear in the whitepaper:

Qualification Engine
Ranking Engine
Opportunity Assignment Engine
Opportunity Registry
Opportunity Set

I recommend updating the whitepaper architecture diagram after Monday's trial, assuming the implementation behaves as expected.

One thing I would not change

I would not implement the Opportunity Registry persistence before Monday.

Keeping it as an ADR with a phased implementation is the right decision.

The current audit payload already captures the required information. You can validate the operational workflow first, then formalize persistence afterward.

Strategic observation

One thing became clear after reading v1.1.

The platform is no longer centered on strategies.

It is centered on opportunities.

The architecture has effectively become:

Market

↓

Qualification

↓

Ranking

↓

Opportunity

↓

Strategy

↓

Execution

↓

Evidence

That is a significant evolution.

Originally, the platform was:

Strategy

↓

Market

Now it's the reverse.

This is a stronger architecture because strategies become interchangeable consumers of a common opportunity pipeline.

Final recommendation

I think v1.1 is ready for Monday's operational trial. At this point, I would avoid introducing additional architectural changes before the first live auto-selection run.

After Monday, I would focus on collecting operational evidence rather than adding features. The next milestone should be a Post-Run Report that answers questions such as:

Did the Opportunity Assignment execute at 09:00 ET as expected?
How many symbols qualified?
What was the frozen Opportunity Set?
How many symbols triggered entries?
What was the Selection Precision?
What was the Opportunity Conversion funnel?
Were there any scheduler, risk engine, or execution anomalies?

If you produce that report after the first week of operation, it will become the first real validation that the Opportunity-centric architecture works in practice. From there, you'll have a solid evidence base for implementing ADR 0029 and updating the whitepaper to reflect the platform's new architecture.