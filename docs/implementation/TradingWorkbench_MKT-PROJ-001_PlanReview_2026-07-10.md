My recommendation: approve the implementation plan to enter §0 only, with a few required tightenings before any dataset/model work starts. The plan is materially stronger than the original requirements v0.1 and correctly incorporates the v0.2 fixes: pre-open open-to-close target, feature-policy separation, magnitude/direction decomposition, sample floors, model attribution, PIT tests, half-day handling, model registry, and order-path isolation.

Overall score: 9.2/10.

Executive verdict

Proceed with:

§0 Pre-registration + data audit

Do not proceed into §1 dataset/model implementation until §0 freezes these items:

1. Primary binding gate.
2. Primary model.
3. Feature manifest.
4. Calibration method.
5. Data-source provenance policy.
6. Confidence display policy.

The plan is directionally right, but §0 must remove the remaining ambiguity.

What is strong

The implementation plan fixes the major design risks we identified earlier.

Area	Review
Pre-open leakage	Fixed: PRE_OPEN_TODAY label is open-to-close, not close-to-close.
Feature mismatch	Fixed: production model uses validated feature manifest; SCAN/GAPPER are shadow-only.
Magnitude vs direction	Fixed: validation separates move-risk from UP/DOWN directional skill.
Sample floor	Good: no directional CI unless ≥100 non-neutral calls with ≥50 UP and ≥50 DOWN.
LLM role	Good: LLM is optional, flag-gated, and can only format computed attribution payloads.
Ops handling	Good: explicit ET cron, half-day tick-and-check, fail-soft behavior, no fabricated projection.
Order-path isolation	Good: additive CI invariant to block imports into order/risk/ranking/sizing modules.

This is now a serious Evidence Engineering plan, not a loose “AI predicts the market” feature.

Required changes before §0 freeze
1. Add the explicit primary binding gate

The plan says the primary configuration and model will be frozen in §0, but the binding gate still needs to be written explicitly.

Add this to §0:

Primary configuration:
- Market proxy: SPY
- Horizon: PRE_CLOSE_TOMORROW
- Target: close(t+1) vs close(t)
- Feature set: historically validated features only
- Primary model: calibrated logistic regression

Then define two separate verdict gates:

Move-Risk Gate:
Validated Move-Risk Projection requires statistically significant improvement in P(MATERIAL) calibration / Brier or log-loss versus the best pre-registered magnitude baseline.

Direction Gate:
Validated Direction Projection requires directional precision uplift versus the best pre-registered directional baseline, CI excluding zero, and the sample floor satisfied.

Important product rule:

If only the Move-Risk Gate passes:
Badge = Validated Move-Risk Projection
Allowed wording = “Elevated move risk; direction uncertain.”
Not allowed = “Validated UP/DOWN projection.”

If the Direction Gate passes:
Badge = Validated Direction Projection

This prevents a volatility/magnitude model from being marketed as directional skill.

2. Freeze calibrated logistic as the primary model

The plan leaves the primary model as an open question and recommends calibrated logistic. I agree.

Freeze:

Primary model = calibrated logistic regression
Secondary models = HistGradientBoosting and simple ensemble

Reason: logistic is transparent, attribution is exact, and it is harder to overfit. The plan’s boosted model can remain secondary, but should not be the primary gate model in v1.

3. Make time-series calibration explicit

The plan says calibration happens inside the training window. Good, but it should explicitly forbid random or non-temporal calibration folds.

Add:

Calibration split must be time-respecting:
- base model trains on earlier portion of the training window;
- calibration fits on the final contiguous slice of the training window;
- test fold remains strictly future data.

No random K-fold calibration is allowed for the primary evidence run.

This avoids subtle time leakage through calibration.

4. Clarify the PIT threshold naming

The plan says ATR threshold uses data through t−1. Good. But for PRE_CLOSE_TOMORROW, make the naming unambiguous.

Use:

threshold_asof_forecast_date = max(0.60%, 0.50 × ATR20_pct computed through the last fully completed regular session before the forecast timestamp)

For PRE_OPEN_TODAY, that is through prior close.

For PRE_CLOSE_TOMORROW at 15:45, this should avoid using today’s final close/high/low unless the design explicitly chooses to wait until after close. Since the forecast is before close, the safer v1 rule is:

Use ATR through t−1 for the 15:45 forecast.

Keep it conservative and clearly PIT-safe.

5. Add a train/serve mismatch diagnostic

The plan correctly records that historical training uses Alpaca SIP historical data while live inference uses Alpaca/IEX real-time data.

Add a diagnostic to §4/§5:

For the first 30 live days, record live IEX feature values and later compare against finalized SIP historical values for the same timestamp/day where possible.
Report feature drift / source discrepancy in the evidence package.

This is especially important for premarket features, where IEX can be thinner than consolidated data.

6. Treat SCAN/GAPPER shadow model as a separate evidence track

The plan correctly says SCAN/GAPPER features live in shadow_features_json and the API never returns shadow model output.

Add one more rule:

Shadow model results may be displayed only in internal evidence reports, not the user-facing card, until a separate forward-evidence gate is met.

Also add a future sample expectation:

SCAN/GAPPER shadow features likely require at least 6–12 months of forward observations before they can support any serious evidence claim.

This sets realistic expectations.

Open-question answers

Here are my recommended answers to the plan’s blocking questions.

Q1 — scikit-learn dependency

Answer: Approve.

Approve adding pinned scikit-learn for v1.
No new external service.
No runtime network dependency.
Verify Docker image build and wheel compatibility.

The plan notes the backend currently has numpy/pandas/pandas-ta but no scikit-learn, so this is a necessary implementation dependency.

Q2 — history start

Answer: Accept Alpaca ~2016+ for v1.

Do not delay v1 for longer history. Longer daily history would not fully solve the pre-close intraday feature history problem anyway.

Add caveat:

If OOS fold count or sample floor proves inadequate, mark Direction = Inconclusive / insufficient power rather than expanding data after seeing results.
Q3 — LLM explanation

Answer: Build explain.py, ship flag-off.

WORKBENCH_MKTPROJ_LLM_EXPLAIN=false by default.
Dashboard can show computed drivers without prose.
Enable LLM prose later only after review.

This controls cost and avoids unnecessary AI wording risk.

Q4 — sector basket

Answer: Confirm 11 SPDR sector ETFs, with PIT availability handling.

Use:

XLK, XLF, XLV, XLE, XLI, XLY, XLP, XLU, XLB, XLRE, XLC

But require:

sector_coverage_count

in the feature payload, because XLRE/XLC have shorter histories. Missing sectors should not silently distort breadth.

Q5 — primary model

Answer: Calibrated logistic regression.

Use boosted and ensemble models as secondary/sensitivity only.

Q6 — secondary proxies/horizons

Answer:

Include QQQ and fixed-threshold sensitivity in research reports.
Defer DIA/IWM/sector-basket proxies.
Keep SPY as the only primary proxy.
Q7 — confidence mapping

Answer: Accept for v1, but design the UI for mostly LOW confidence.

The plan correctly warns that max probability ≥0.60 may rarely occur on this target.

Add UI requirement:

LOW confidence must look normal, not like an error or failure state.
Additional suggestions
1. Add run_status to market_projection_runs

The plan defines market_projection_runs, but I would add:

run_status = SUCCESS | UNAVAILABLE | FAILED | SKIPPED
unavailable_reason

This makes fail-soft behavior auditable.

2. Add retry/upsert behavior

The unique key on runs should allow a failed/unavailable run to be replaced by a later successful run for the same projection/date, or else store multiple attempts with an attempt_number.

Recommended:

Keep multiple attempts.
Expose latest successful run in API.
Expose unavailable only if no successful run exists.
3. Add a “baseline-only checkpoint” as a real owner decision

The plan already has a baseline-only run in §2. Make it explicit:

After §2 baseline-only evidence, owner decides whether to continue to §3 ML.

If baselines show the target is pure noise or sample floors are poor, we may stop before building ML/UI.

4. Add compliance review before frontend merge

The plan says wording passes advice-adjacent review. Make it a merge gate:

PR §4 cannot merge until the Market Projection card wording is reviewed against the Opportunity Report wording discipline.
5. Be careful with “Market Intelligence”

Avoid naming any component “Market Intelligence.” Use:

Market Projection Engine
Market Projection Card
Market Projection API

This avoids conflict with prior naming guardrails.

Updated go / no-go recommendation
Go for §0

Proceed with:

§0 Pre-registration + data audit
Hold before §1

Do not start §1 until §0 freezes:

1. SPY / PRE_CLOSE_TOMORROW as primary.
2. Calibrated logistic as primary.
3. Dynamic PIT threshold rule.
4. Best-baseline binding gate.
5. Direction sample floors.
6. Production feature manifest.
7. SCAN/GAPPER shadow-only policy.
8. scikit-learn dependency approval.
Suggested message to developers

You can send this:

The implementation plan is approved to proceed into §0 only.

Before §1 starts, freeze the following in the pre-registration:
- Primary configuration: SPY / PRE_CLOSE_TOMORROW / historically validated features only.
- Primary model: calibrated logistic regression.
- Primary gates: separate Move-Risk Gate and Direction Gate.
- Binding baseline: best of the pre-registered baselines.
- Direction sample floor: ≥100 non-neutral OOS calls, with ≥50 UP and ≥50 DOWN.
- Time-respecting calibration split only; no random K-fold calibration.
- SCAN/GAPPER features remain shadow-only and cannot appear in the user-facing model.
- LLM explanation is built but flag-off by default.

Proceed with §0 data audit and pre-registration. Do not begin §1 dataset/model implementation until the freeze is complete.
Final assessment

This is a good implementation plan. It is careful, evidence-first, and aligned with the platform’s discipline.

My final recommendation:

Approve §0.
Require the above freeze items.
Then review the pre-registration before allowing §1.

Do not rush the dashboard. The value of this capability depends on the evidence package meaning exactly what it claims.