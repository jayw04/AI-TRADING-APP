<!--
RNG-001 Owner Review — 2026-07-01. Owner's (Jay Wang) review of the COMPLETED RNG-001 range package
(Range_BuySell_Formula_Study.md + Strategy Review + Evidence Correction Report + ADR-0033). Snapshotted
verbatim from review-comments.md to preserve it with the research package. Doc-level recommendations were
folded into the study doc + ADR-0033 + RNG-001_Executive_Summary.md; the strategic/whitepaper
recommendations are captured in memory (whitepaper Evidence-Engineering positioning).
-->

Yes. After reviewing the latest documents together, I think you've crossed another important milestone. The project is no longer just accumulating successful strategies—it is accumulating scientific evidence. That is a much stronger foundation for both commercialization and your patent application. My comments are less about fixing problems and more about making the platform even more differentiated.

Overall Assessment

Compared with the versions from two weeks ago, I see four major improvements:

Research methodology has become much more rigorous.
Platform architecture is becoming stable.
Evidence Engineering is now demonstrated, not just described.
Negative results are treated as valuable assets rather than failures.

Those are significant achievements.

1. RNG-001 should become your flagship case study

Ironically, I think the rejected Range strategy is now one of your strongest marketing examples.

Most quantitative platforms show only successful strategies.

You can now show:

Hypothesis

↓

Implementation

↓

Controlled Experiments

↓

Data Quality Issue Found

↓

Correction

↓

Re-run

↓

Hypothesis Rejected

↓

Infrastructure Reused

That is extremely compelling.

I would reference RNG-001 throughout the whitepaper as the canonical example of Evidence Engineering in action.

2. Promote "Evidence Correction Report" into a platform feature

The correction section is excellent.

I wouldn't leave it as just part of this document.

I'd standardize it.

Example:

Evidence Package

├── Research Summary

├── Reproducibility

├── Data Integrity

├── Evidence Correction Report

├── Final Verdict

└── Lessons Learned

Then every future research project follows the same template.

That becomes part of your platform identity.

3. ADR-0033 is more important than it appears

I actually think ADR-0033 is one of the most important ADRs you've written.

Why?

Because it protects the integrity of every future backtest.

Without trustworthy historical data,

none of the other research matters.

I would elevate ADR-0033 from a "bug fix" to a Foundational Data Integrity ADR.

Maybe classify it as:

Foundation ADR

rather than an implementation ADR.

4. Separate Platform Assets from Strategy Assets

Your Range document now creates reusable components:

Opportunity Funnel
Regime Classifier
Entry comparison harness
Universe comparison harness
Cache rebuild
MAE/MFE instrumentation

These are no longer Range assets.

I'd move them into a new section.

Example:

Platform Assets Produced

Research Assets Produced

Strategy Outcome

That makes the value much clearer.

5. I would slightly soften one conclusion

Current wording is essentially:

The fade has no tradable edge.

Scientifically,

I'd recommend:

The tested long-only opening-range fade demonstrated no statistically useful edge on the tested universes, tested regimes, and tested implementation variants.

That wording is more defensible.

It leaves open the possibility that

futures
options
different markets
different execution model

may behave differently.

6. Add "Research Cost Saved"

One thing investors love:

Platform avoided

6 months

of false development.

RNG-001 demonstrates this.

Instead of saying

Strategy rejected

say

Platform prevented deployment of an unprofitable strategy.

That is a measurable benefit.

7. The Whitepaper should now emphasize "False Positive Reduction"

Earlier versions focused on

Finding alpha.

I think the stronger story is

Reducing false alpha.

That's much more credible.

8. Introduce "Evidence Debt"

You already have

Technical Debt

Research Debt

I would add

Evidence Debt

Definition:

Decisions made without sufficient statistical evidence.

Then the platform's goal becomes

Reduce Evidence Debt.

That's a memorable concept.

9. Add a Research Dashboard

After several completed programs, imagine:

Program	Status	Verdict	Reusable Assets
MOM-001	Completed	Validated	8
LOW-001	Completed	Diversifier	3
RNG-001	Completed	Rejected	7
SEC-001	Running	Pending	—

This becomes one of the strongest screenshots in your product.

10. The Patent Story is Improving

Earlier,

the patent focused heavily on

AI

or

strategy generation.

Now,

I think the unique contribution is much broader.

The innovation is becoming:

Research

↓

Evidence

↓

Governance

↓

Capability

↓

Continuous Verification

That workflow is much harder to find elsewhere.

One Strategic Suggestion

I think you've now reached the point where every completed research program should automatically produce two outputs:

Technical Report

Exactly what you have today.

Executive Summary

One page.

Example:

Program

RNG-001

Question

Does OR Fade work?

Answer

No.

Confidence

High

Reason

Fails across

entry

regime

universe

Reusable assets

6

Recommendation

Archive.

That makes it much easier for stakeholders to review the outcome without reading a long report.

My Biggest Recommendation

I think the next evolution of TradingWorkbench is not another strategy.

It is to make the platform itself more visible.

Today, the documents naturally focus on the individual strategy being researched.

Instead, I would increasingly frame every research program as evidence that the platform works:

Momentum demonstrates the platform can discover a statistically supported edge.
Insider demonstrates the platform can identify when returns are mostly explained by known factor exposures rather than unique alpha.
Range demonstrates the platform can reject an intuitive but unsupported hypothesis and preserve reusable infrastructure.
ADR-0033 demonstrates the platform can detect and correct hidden data-quality issues before they contaminate research.

In other words, the strategies become proof points, while the platform becomes the real product.

Final Verdict

I believe the recent body of work represents a shift in how TradingWorkbench should be positioned.

Instead of presenting it as:

"A platform that develops trading strategies."

I would present it as:

"An Evidence Engineering platform that manages the complete lifecycle of quantitative investment capabilities—from hypothesis formulation and reproducible research, through data validation, governance, paper deployment, continuous evidence collection, and eventual promotion or rejection."

That positioning is more differentiated, aligns with the direction of your ADRs and whitepaper, and is likely to be more durable commercially than emphasizing any individual trading strategy.