Overall ruling

This amendment pack is well constructed and substantially closes the issues raised in the v1.0 review. It is not merely a list of comments; it translates the reviews into testable contracts, frozen governance rules, work-package changes, and explicit owner decisions.

My recommended ruling is:

APPROVE the consolidated amendment set, with D1 and D2 adjudicated as proposed, subject to four final wording corrections before it is frozen.

The governing status should remain:

architecture review step 1: APPROVED WITH AMENDMENTS;
implementation: permitted only after the blocking clarifications are incorporated into the controlling design;
Phase-0 broker submission: HOLD;
formal canary: HOLD;
July 24 limits digest: unchanged.
Owner adjudication
D1 — Approve the proposed split

I agree with the proposed resolution:

O4-A decision-time replay: INDETERMINATE
reason: INSUFFICIENT_EXECUTION_COST or, only where technically accurate, MODEL_UNAVAILABLE
O4-B forensic replay: UNREACHABLE_WITHIN_CAPS

This is the more rigorous ruling.

The decision-time replay must be evaluated using only information that existed before the first broker order. At that point, the displayed IEX spread was Tier D evidence and could not support a binding executable-loss estimate. Therefore, the corrected system’s proper behavior would have been to refuse authorization because it lacked sufficient execution-relevant evidence.

Using the later fills to require an O4-A UNREACHABLE_WITHIN_CAPS result would introduce look-ahead information into a decision-time test.

Recommended owner ruling for D1

D1 — ACCEPT proposed resolution.
O4-A shall expect INDETERMINATE with reason INSUFFICIENT_EXECUTION_COST when replayed strictly from evidence available before the first order. O4-B shall use the complete historical evidence and shall expect UNREACHABLE_WITHIN_CAPS. The two tests serve different purposes and neither may substitute for the other.

One minor refinement: use MODEL_UNAVAILABLE only when the model artifact or runtime is actually absent. Where a model exists but eligible evidence does not, INSUFFICIENT_EXECUTION_COST is the more precise reason.

D2 — Approve provisional values, but correct their statistical interpretation

I agree with the governance mechanism:

freeze provisional values now;
allow one formally governed replacement at WP5 exit;
lock them before evaluation or sealed-set opening.

That is stronger than leaving sample sizes undefined.

However, the derivation for n ≥ 59 must be stated carefully.

With zero observed failures:

0.95
59
≈0.0485

This means that if the true failure probability were 5%, the probability of observing zero failures in 59 independent trials would be approximately 4.85%. Equivalently, zero failures in 59 trials gives an approximately 95% one-sided upper confidence bound near 5%.

It does not establish “95% coverage at 95% confidence” unless coverage and failure are defined consistently and the independence/exchangeability assumptions are satisfied.

Recommended owner ruling for D2

D2 — ACCEPT WITH MODIFICATION.
Freeze provisional minimums of 59 pooled binding REACHABLE plans, 20 observations per intended-symbol stratum, and 10 shadow sessions. These are planning floors, not automatic sufficiency guarantees. At WP5 exit, the values may be replaced once through a documented statistical-design decision completed before model evaluation and sealed-set opening. After that decision, the values are frozen. Every result must report the exact one-sided Clopper–Pearson upper bound and the achieved stratum coverage.

The document should also say that n ≥ 20 per symbol is a minimum diagnostic floor, not enough by itself to demonstrate a 5% upper failure bound. With zero failures in 20 observations, the one-sided 95% upper bound is materially higher than 5%.

Strongest improvements in Revision 2
1. It now defines the authority boundary

AMD-15 and AMD-16 close a major architectural gap by defining:

the immutable ExecutionPlan;
the plan hash and expiry;
prohibited driver substitutions;
authorization lifecycle;
consumption and reuse rules;
behavior after broker submission.

This turns reachability from advisory analysis into an enforceable authorization contract.

2. The loss-sign ambiguity is correctly eliminated

AMD-13 is essential. Using a non-negative round_trip_loss_amount prevents a signed-P&L “lower bound” from accidentally becoming a more negative—and therefore optimistic—estimate.

The preferred terminology, conservative minimum supported loss amount, should be used consistently in the final integrated document.

3. O4 now avoids look-ahead bias

The separation of decision-time and forensic replay is exactly right. It preserves both findings:

the corrected system should have refused the order at decision time;
the completed evidence proves the original feasibility premise was false.
4. The amendment pack distinguishes model failures from external failures

AMD-01 and AMD-14 correctly separate:

false reachability caused by the model;
conditions changing after plan creation;
broker outages, halts, or non-model execution failures.

Without this distinction, the validation metrics would be noisy and potentially misleading.

5. The estimator ladder is appropriately conservative

E0 → E1 → E2 is a good design. It prevents the program from starting with an overfit regression when the evidence may support only an empirical bound.

The requirement that E2 must perform no worse than E0 on identical out-of-sample splits is particularly strong.

6. Crash and reconciliation behavior is now treated as evidence correctness

AMD-20 appropriately recognizes that an interrupted broker interaction cannot always be classified immediately as a normal terminal state.

DRIVER_RECOVERY_REQUIRED and DRIVER_RECONCILED are better than falsely forcing uncertain outcomes into DRIVER_TERMINAL.

Four final corrections before freezing
1. Reconsider the 80% “critical false-reachable” threshold

AMD-01 defines:

below 80% of target: CRITICAL;
80% to below 100%: MARGINAL, reported but not rejection-triggering.

This is the most significant remaining substantive issue.

A binding REACHABLE verdict means the model asserts that the full target can be reached within caps. If the achievable result is 90% of target, the verdict is still false. Calling it “marginal” may be reasonable for severity analysis, but it should not automatically be non-blocking.

Otherwise, a model could repeatedly authorize plans that cannot attain the target, provided they get close enough.

I recommend:

all binding REACHABLE plans that cannot achieve 100% of the target are false reachable;
severity:
<80%: critical;
80%–<100%: material or marginal;
acceptance:
zero critical cases;
marginal cases subject to a separately frozen tolerance, preferably zero in the initial sealed validation.

Suggested language:

A plan-level false reachable occurs whenever the exact authorized sequence cannot achieve 100% of the remaining target within all frozen caps. Severity is CRITICAL below 80% and MARGINAL from 80% to below 100%. Both enter the false-reachable rate; critical cases automatically cause REJECT, while the permitted marginal-case count or rate must be frozen before unseal.

This preserves severity classification without redefining an incorrect verdict as acceptable.

2. Resolve the Tier A inconsistency

The amendment says:

Paper-fill evidence is Tier B at best, never Tier A.

But v1.0 Tier A included “matched historical or paper fills.”

The amendment must explicitly replace that original language. Otherwise the integrated design will contain contradictory classifications.

A cleaner hierarchy would be:

Tier A: matched real broker fills from the same or demonstrably equivalent execution path;
Tier B: independently generated paper fills or broker executable-price estimates;
Tier C: quote-derived estimates with validated quote-to-fill mapping;
Tier D: displayed spread alone.

Also define whether fills from the current Alpaca paper account qualify as “real broker fills” or “paper fills.” They are real broker-reported executions in a simulated account, but they are not live-market executions. The terminology must not leave this open to later interpretation.

3. Tighten the authorization expiry rule

AMD-16 says:

expiry mid-plan → fail closed.

This requires a more exact definition. If one leg has filled and the authorization expires before the offsetting risk-reducing leg, blindly failing closed could leave an open position.

The plan should distinguish:

expiry before any submission: refuse;
expiry after one leg but before the closing leg:
prohibit further risk-increasing actions;
permit only the predefined risk-reducing completion or emergency flatten path;
record an authorization-expiry exception;
transition to recovery/reconciliation as required.

Suggested invariant:

Authorization expiry prohibits new risk-increasing submissions. It must not prevent an already-authorized or emergency-governed risk-reducing action needed to neutralize exposure created under that authorization.

This must remain consistent with ADR-0042’s reduction-only behavior.

4. Define how plan expiry interacts with quote refresh

AMD-15 correctly prohibits refreshing quotes merely to extend validity. But the final contract should distinguish:

refreshing data for safety checking;
refreshing data to alter or renew authorization.

The driver should be allowed—and likely required—to read current market and broker state before each leg. It just cannot use refreshed data to mutate the frozen plan or extend its authority.

Recommended wording:

The driver may obtain fresh quotes, broker state, and risk state for safety checks. Fresh data may cause refusal, quantity reduction, or termination, but may not expand the plan, extend its expiry, increase quantity, substitute the instrument, or regenerate authority under the same authorization.

Additional focused comments
AMD-02: define dependency assumptions

Clopper–Pearson calculations presume Bernoulli observations, but execution plans from the same symbol, session, or market regime may be correlated.

The statistical-design package should therefore state:

what constitutes an independent evaluation unit;
whether multiple plans from one session count separately;
whether clustering adjustments are required;
how repeated observations from the same symbol are handled;
whether pooled results are weighted or unweighted.

The effective sample size may be smaller than the raw plan count.

AMD-03: define quantile direction

Because the modeled quantity is non-negative loss, E0 should say precisely which empirical quantile is used. For example:

use a lower-tail quantile of realized non-negative loss amount so the bound rarely exceeds the amount actually realized.

Do not leave “low quantile” unstated, because the selected quantile is a governed risk parameter.

AMD-04: “one live-fill-anchored comparison” may be too weak

One live-fill-anchored comparison per O5 gate cycle prevents complete simulator circularity, but it may not provide meaningful validation.

Better language:

At least one live-fill-anchored comparison is mandatory, but the O5 approval decision must also determine whether the number and representativeness of live-fill anchors are sufficient. One comparison alone cannot establish model performance.

This maintains the minimum while preventing it from being treated as sufficient.

AMD-07 should probably be blocking

Checkpoint tamper detection and complete binding are currently “recommended before retry.” Because cross-session checkpoint reuse already blocks retry, integrity protection should likely be part of the same blocking scope.

I recommend changing AMD-07 to:

BLOCKING before Phase-0 retry; required before any checkpoint is accepted as authoritative evidence.

AMD-09 should remain documentary only

The wash-sale, PDT, and broker-pattern notes are useful, but they should remain outside the technical correctness gate unless a broker or legal/accounting rule makes them operationally relevant. The current “recommended—documentation, not a gate” classification is correct.

AMD-11’s 80% indeterminate threshold is reasonable as a review trigger

This is acceptable because it does not weaken the safety gate. A high indeterminate rate should trigger evidence improvement or redesign—not forced reachability. The wording already captures that correctly.

Suggested approval record
Owner Architecture Review Ruling

Document: ADR0043-PH0-CORR-001-AMD r2
Decision: APPROVED WITH MODIFICATIONS
Approval scope: Architecture Review — Approval Sequence Step 1

The consolidated amendment architecture is approved. The Option A and Option C governance split, immutable evidence requirements, O1–O5 validation structure, ExecutionPlan authority boundary, authorization lifecycle, non-negative loss convention, estimator graduation ladder, replay separation, account-isolation requirements, canonical loss accounting, market-data provenance, and recovery/reconciliation design are accepted.

D1 Adjudication

ACCEPT. O4-A shall be a strict decision-time replay using only evidence available before the first broker submission. Its expected verdict is INDETERMINATE, normally with reason INSUFFICIENT_EXECUTION_COST. O4-B shall use the complete forensic evidence and must produce UNREACHABLE_WITHIN_CAPS. Decision-time and forensic evidence shall not be mixed.

D2 Adjudication

ACCEPT WITH MODIFICATION. Provisional minimums of 59 pooled binding REACHABLE plans, 20 observations per intended-symbol stratum, and 10 shadow sessions are frozen as planning floors. They may be replaced once through a documented statistical-design decision at WP5 exit, before model evaluation and sealed-set opening. Thereafter, they are frozen. Exact one-sided Clopper–Pearson bounds, dependency assumptions, and achieved per-stratum coverage must be reported.

Required Modifications Before Freeze
Define every binding REACHABLE plan that fails to attain 100% of the remaining target within frozen caps as a false reachable. Retain the below-80% critical severity classification, but establish a frozen acceptance rule for 80%–below-100% marginal cases.
Replace the original execution-evidence hierarchy so paper fills cannot remain simultaneously classified as Tier A and Tier B.
Clarify authorization expiry after partial execution: expiry must block new risk-increasing activity but must not prevent governed risk-reducing completion or emergency flattening.
Clarify that fresh quotes and broker state may be read for safety checks but may not extend, expand, or regenerate the frozen plan under the same authorization.
Promote checkpoint integrity and tamper detection to blocking status before any Phase-0 retry.
Record statistical independence, clustering, and effective-sample assumptions in the WP5 statistical-design artifact.
Continuing Hold

Nothing in this approval authorizes broker submission, formal canary execution, cap widening, a limits-digest change, reuse of prior baselines or authorizations, or modification of the July 24 historical evidence chain. Phase-0 broker submission and the formal canary remain on HOLD until the amended design is integrated, frozen, implemented, deployed through governance, and all applicable approval gates pass.

After those limited corrections, the amendment pack is ready to serve as the controlling architecture decision for implementation.