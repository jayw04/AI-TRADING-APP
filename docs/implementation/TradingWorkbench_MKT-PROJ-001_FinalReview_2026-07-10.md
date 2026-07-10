My recommendation: approve the updated package as “nearly freeze-ready,” but make a few final edits before allowing §1 dataset/model work to start.

Overall score: 9.5/10.

The v0.2 implementation plan now correctly folds the previous review: §0 only, explicit owner gate before §1, primary SPY / PRE_CLOSE_TOMORROW configuration, calibrated logistic as primary, separate Move-Risk and Direction gates, shadow-only SCAN/GAPPER, time-respecting calibration, train/serve diagnostics, run-status tracking, and §2 baseline checkpoint.

The pre-registration is also strong: it freezes the primary configuration, label rule, baselines, feature manifest, models, validation, display policy, shadow policy, and stopping rules before any training row or validation run.

Executive decision

Proceed with:

Finalize pre-registration v0.1 → freeze
Then start §1 Dataset + Labels

But first apply the edits below.

Required edits before freeze
1. Pick one primary Move-Risk metric

The Move-Risk Gate currently says improvement in Brier or log-loss versus the best baseline. That creates a small multiple-testing loophole. Pick one primary metric.

My recommendation:

Primary Move-Risk metric = Brier score improvement vs best pre-registered magnitude baseline.
Secondary = log-loss, ECE, reliability curve.

Reason: Brier is safer for probability quality and avoids log-loss problems when baselines assign near-zero probability.

Update the gate to:

Validated Move-Risk Projection requires Brier score improvement versus the best pre-registered magnitude baseline, with block-bootstrap CI excluding zero.

Keep log-loss as secondary.

2. Make “meaningful coverage” numeric

The Move-Risk Gate says “meaningful coverage of elevated-move-risk calls,” but does not define it. That should be frozen before results.

Suggested rule:

Move-risk elevated-call coverage must be between 10% and 60% of OOS days, or the Move-Risk verdict is Inconclusive / insufficient coverage.

This prevents a trivial model that almost never calls risk, or always calls risk, from passing.

3. Clarify calibration guardrail

The gate says calibration must be acceptable, with ECE reported and reliability curve reviewed. That is directionally right, but still subjective.

Add either a numeric guardrail or downgrade it to a reviewed diagnostic.

Recommended:

Calibration guardrail:
ECE must not be worse than the best pre-registered magnitude baseline by more than 0.02.
Reliability curve is reviewed as a diagnostic.

The exact threshold can be adjusted before freeze, but it should be frozen before validation.

4. Align capability ID

The implementation plan still says:

Capability = CAP-TBD

The pre-registration says:

Capability = CAP-027 — Market Projection Engine

Reconcile this before freeze. Either:

Implementation plan = CAP-027

or keep both as:

CAP-TBD until registry entry is merged

My preference: use CAP-027 if CAP-026 is already reserved for Insider Reference Monitor.

5. Move pandas_market_calendars earlier

The implementation plan notes one gap: prod image lacks pandas_market_calendars, so MarketSession falls back to curated half-day logic.

Because labels and half-day handling matter starting in §1, do not wait until §4 jobs to add it.

Recommended change:

Add pandas_market_calendars in §0 or §1 before dataset/label construction.

Otherwise the historical labeler may not be using the same authoritative calendar as production inference.

Strong points to keep
Primary configuration is now right

The pre-registration correctly freezes:

SPY
PRE_CLOSE_TOMORROW
close(t+1) vs close(t)
historically validated PIT features only
calibrated logistic regression
walk-forward validation
best pre-registered baseline

This is exactly the right primary design.

Pre-open leakage is fixed

The pre-registration correctly treats PRE_OPEN_TODAY as secondary and defines it as:

close(t) vs regular-session open(t)

not close-to-close. That resolves the original leakage/triviality problem.

SCAN/GAPPER shadow policy is correct

The shadow policy is now clean: SCAN/GAPPER features live in shadow_features_json, never affect displayed probabilities, and require a separate forward-evidence gate before any user-facing use.

Baseline-only checkpoint is excellent

The updated plan adds a real owner gate after §2:

After baseline-only evidence, owner decides whether to continue into ML.

This is important. If the target is pure noise, the program can stop early without wasting effort on ML/UI.

Additional suggestions
Add a §3 → §4 owner checkpoint

The plan has:

§0 → §1 owner gate
§2 → §3 owner gate
§4 compliance merge gate

I recommend adding one more:

§3 → §4:
After full ML evidence and model card, owner decides whether to build the API/card surface.

Even if the card is labelled Research Preview, we should not automatically build a daily projection UI if §3 shows no useful signal.

Clarify partial-volume feature

For spy_volume_vs_20d, specify whether it means:

volume through close−15m / average full-day volume

or:

volume through close−15m / average volume through the same time of day

The second is cleaner, if available. The first is acceptable, but must be named clearly.

Clarify intraday range features are as-of only

For fade_recovery and spy_hl_range_pct, explicitly say:

computed using high/low/price data available only through close−15m

No final-session high/low should leak into the pre-close feature set.

Handle log-loss clipping

If log-loss remains in secondary reporting, define probability clipping:

clip probabilities to [1e-6, 1 - 1e-6] before log-loss

This avoids infinite log-loss for Always-Neutral or other deterministic baselines.

Go / no-go
Go
Approve §0 as effectively complete after the minor edits above.
Freeze pre-registration v0.1.
Start §1 Dataset + Labels.
Hold
Do not start §2 validation until §1 PIT/leakage tests pass.
Do not start §3 ML until §2 baseline-only evidence is reviewed.
Do not start §4 API/UI until §3 model card is reviewed.
Suggested message to developers
The updated MKT-PROJ-001 package is approved pending minor pre-freeze edits.

Before §1 starts, please update:
1. Make Brier score the single primary Move-Risk metric; log-loss secondary.
2. Define numeric coverage requirement for elevated-move-risk calls.
3. Add a calibration guardrail or explicitly mark calibration as diagnostic.
4. Reconcile CAP-TBD vs CAP-027.
5. Add pandas_market_calendars before §1 label/dataset construction.
6. Add a §3→§4 owner checkpoint before API/UI build.
7. Clarify partial-volume and intraday range features are computed strictly as-of forecast time.

After those edits, freeze the pre-registration and proceed to §1.

Final assessment: this is ready to move forward after small tightening. The updated docs now protect against the major evidence traps and keep the product honest as Research Preview until the evidence says otherwise.