# ADR 0007 — Auto-Promotion of LLM-Proposed Strategy Updates

| Field | Value |
|---|---|
| Date | 2026-05-29 |
| Status | Accepted |
| Phase | Cross-phase architectural decision; governs P6 (strategy intelligence) |
| Related | ADR 0002 (single OrderRouter), ADR 0005 (24-hour activation cooldown), ADR 0006 (LLM in order path gated), ADR 0008 (will document the audit-trail extension for AI-influenced decisions) |

## Context

ADR 0006 (revised) establishes that LLMs may participate in the order path only behind a user opt-in, after a defined paper-trading evaluation. That ADR governs the *execution* of LLM-driven decisions.

This ADR governs a different question, which arises in the strategy intelligence layer planned for P6: **when the LLM proposes a parameter update to an existing strategy, what is the path from proposal to live deployment?**

The original P6 direction document had this path entirely human-mediated: LLM proposes a change, the user reads the proposal and clicks accept or reject, and accepted changes route through the standard 24-hour activation cooldown of ADR 0005. That works, but it has a problem at scale. A trader running 8 active strategies, each reviewed daily, can produce dozens of proposals per week. The user either reads each one carefully (expensive) or skims them and clicks accept without real engagement (worse, because the audit trail then implies review that didn't happen).

The proposal we're absorbing here is to **automate the validation step** while keeping the **promotion step** under user control. Specifically:

1. LLM proposes a parameter change.
2. The platform automatically clones the strategy with the proposed parameters and runs it on a paper account, in parallel with the unchanged live variant.
3. Both run for a defined minimum window with a defined minimum trade count.
4. If the paper variant meets a defined promotion threshold, the platform packages the comparison evidence and presents it to the user.
5. The user reviews the evidence and approves or rejects promotion. Approval routes through the standard 24-hour cooldown.

The user remains in the loop at the promotion step. What changes is that the evidence the user is reviewing is no longer "Claude thinks this might be better" — it is "Claude proposed this change 47 days ago, the paper variant has run 73 trades since then, here are the comparison metrics, do you want to promote?"

The trade-off is real. We gain a more rigorous evidence base. We add architectural complexity (parallel variant management, automated comparison, evidence-bundle generation). We move closer to a system that updates itself, which is a more demanding posture than a system that only assists.

## Decision

The platform implements an **auto-validation-with-manual-promotion** loop for LLM-proposed strategy updates, with the following structure:

### The lifecycle

A strategy under LLM oversight can be in one of these states:

| State | Meaning |
|---|---|
| **STABLE** | Strategy is running normally; LLM has no pending proposal. |
| **PROPOSED** | LLM has identified a potential improvement; proposal exists but evaluation has not started. |
| **EVALUATING** | Paper variant is running in parallel with live variant; metrics are accumulating. |
| **EVIDENCE_READY** | Evaluation window has completed; comparison evidence is packaged for user review. |
| **PROMOTING** | User approved promotion; standard 24-hour activation cooldown is in progress. |
| **PROMOTED** | New variant is live; old variant is archived (audit log preserved). |

Transitions: STABLE → PROPOSED → EVALUATING → EVIDENCE_READY → PROMOTING → PROMOTED, or back to STABLE if rejected at any step.

### The promotion criteria

A proposal becomes EVIDENCE_READY (i.e., presented to the user) when **all four** of the following are true:

| Criterion | Threshold | Why |
|---|---|---|
| **Window** | ≥30 calendar days OR ≥50 trades in the paper variant, whichever is later | Statistical meaningfulness — either floor alone is misleading |
| **Margin** | Paper variant's Sharpe ratio exceeds live variant's by ≥5% | Meaningful but not punishing — small deltas are noise; large deltas are rare |
| **Absolute floor** | Paper variant's absolute return over the window is positive | A less-bad-losing variant is not promoted; the bar is profitable, not just "better" |
| **No worst-case divergence** | Paper variant has not exceeded the live variant's maximum drawdown by more than 20% in any rolling 7-day sub-window | Catches the scenario where average performance is fine but tail risk has gotten worse |

If all four are met, the proposal advances to EVIDENCE_READY automatically. If any fails, the proposal remains in EVALUATING; the evaluation continues; the user sees a "still evaluating" status with the current metrics.

The thresholds are configurable per-user in trading_profile (added in P5.5 §1). The defaults above are the conservative middle position. Users who want more aggressive auto-validation can raise the trade count requirement or lower the margin; users who want more conservative validation can do the opposite. The platform refuses to lower the absolute floor below "positive return" — that one is not user-configurable, by design.

### What evidence the user sees

When a proposal reaches EVIDENCE_READY, the user receives a structured evidence bundle. The bundle is not a "click here to approve" toast — it is a substantive document the user is expected to read. It includes:

- **The proposed change**: parameter-by-parameter diff between the live and paper variants
- **The LLM's stated rationale**: what change was proposed and why, in plain language
- **The evaluation window**: start date, end date, calendar days, trade count for each variant
- **The four-criterion outcome**: each criterion's actual value vs. its threshold, with all four reported even when only one was the deciding factor
- **The performance comparison**: side-by-side metrics including the six metrics from ADR 0006's evaluation framework (win rate, Sharpe, max drawdown, decision agreement, disagreement asymmetry, worst single divergence)
- **The trade-by-trade record**: every trade taken by each variant during the window, with timestamps and P&L impact, available as a downloadable CSV
- **The audit excerpt**: the relevant audit-log entries for the evaluation period, with the hash chain verified

The user approves, rejects, or requests an extended evaluation (which doubles the window and re-checks). Rejection is logged with a reason field (optional but encouraged); future LLM proposals can read the rejection history to inform future suggestions.

### What promotion actually does

Approval triggers:

1. The proposed parameter set becomes the new "live" variant.
2. The old "live" variant is archived as a strategy version with its full history preserved.
3. The new live variant enters the standard P5 §7 activation cooldown (24 hours).
4. During the cooldown, the new variant submits no orders. The old variant continues submitting orders (the strategy did not stop; only the upgrade is paused).
5. After 24 hours elapse, the new variant takes over.
6. The audit log records every step of the transition.

The user can cancel during the 24-hour cooldown with no friction; that reverts the variant to its prior state and the proposal returns to a "rejected" terminal state.

### Failure modes the design protects against

**Failure mode: random walk wins.** Over noisy windows, a paper variant beating a live variant can be statistical noise. *Mitigation*: the 5% Sharpe margin filters out small deltas; the 30-day-or-50-trade window provides statistical meaningfulness; the absolute floor prevents promoting on relative-only signals.

**Failure mode: local optima / regime overfitting.** Short windows reward strategies that fit recent market conditions. *Mitigation*: the 30-day calendar floor catches at least some regime variation; the 7-day rolling sub-window check prevents promotion if the variant had a bad week even in an overall good window.

**Failure mode: parameter churn.** Successive proposals chasing each other across regime changes. *Mitigation*: after a promotion, the strategy is locked in STABLE for at least 30 days before a new proposal can be initiated. The LLM may identify potential improvements during this lockout but cannot start a new evaluation cycle.

**Failure mode: user rubber-stamps proposals.** The evidence bundle is designed to be substantive enough that skimming-and-accepting is uncomfortable; the user is asked to do meaningful work to evaluate it. We cannot prevent rubber-stamping, but we can make the audit log preserve enough detail that a future auditor (or future you) can see whether the approval was thoughtful. The full evidence bundle at the moment of approval is preserved in the audit log.

**Failure mode: LLM proposals systematically biased toward action.** If the LLM tends to propose changes regardless of whether a change is actually needed, the system generates noise. *Mitigation*: the LLM is explicitly prompted to propose changes only when it has identified a specific underperformance pattern; "no change recommended" is a valid LLM response. The platform's metrics on "proposals generated per strategy per month" are surfaced to the user; a strategy with proposals every week is a strategy whose LLM oversight may need to be paused or tuned.

### What this ADR does NOT enable

This ADR does **not** authorize:

- **Auto-promotion without user approval.** Promotion is always user-gated.
- **Auto-rollback if the new variant underperforms.** Once promoted, the new variant runs until the user deactivates it or the next proposal goes through the same loop.
- **Cross-strategy proposals.** Each strategy is evaluated independently. The LLM cannot propose "deactivate strategy A and reallocate its capital to strategy B" — that's a portfolio decision, not a parameter update, and lives outside this loop.
- **LLM-authored new strategies entering live trading via this path.** A net-new strategy must go through the standard P5 §7 activation flow (which itself requires a recent backtest as a prerequisite). The auto-validation loop is for parameter updates to existing live strategies, not for net-new strategies.

These exclusions are not permanent. Each could be revisited via a future ADR if and when the simpler version of this loop has been operating successfully for a sustained period.

## Implementation notes

### Schema additions (P6)

A new `strategy_proposals` table tracks the lifecycle:

| Column | Notes |
|---|---|
| `id` | PK |
| `strategy_id` | FK to live strategy |
| `proposed_params_json` | Full parameter set being proposed |
| `state` | One of: PROPOSED, EVALUATING, EVIDENCE_READY, PROMOTING, PROMOTED, REJECTED, EXPIRED |
| `state_changed_at` | Timestamp of last state transition |
| `paper_variant_started_at` | When the paper run began (set on EVALUATING) |
| `evidence_bundle_json` | Generated on transition to EVIDENCE_READY; immutable thereafter |
| `user_decision` | Approve / reject / extend (null until user acts) |
| `user_decision_reason` | Optional free-text from user |
| `llm_session_id` | FK to the agent session that generated the proposal |

### Audit actions

New audit actions:

- `STRATEGY_PROPOSAL_GENERATED` — LLM created a proposal
- `STRATEGY_PROPOSAL_EVALUATION_STARTED` — paper variant began running
- `STRATEGY_PROPOSAL_CRITERIA_MET` — automatic transition to EVIDENCE_READY
- `STRATEGY_PROPOSAL_APPROVED` — user approved (with evidence-bundle hash)
- `STRATEGY_PROPOSAL_REJECTED` — user rejected
- `STRATEGY_PROPOSAL_EXTENDED` — user requested extended evaluation
- `STRATEGY_PROMOTED` — new variant became live after cooldown

### CI invariants

This ADR does not require a new CI invariant. The auto-validation loop respects all existing invariants — the LLM call to generate proposals is in the existing `app/services/strategy_review.py` allowlist (from ADR 0006), the paper variant submits through `OrderRouter` with paper credentials (ADR 0002), and promotion routes through the existing P5 §7 activation flow.

### Pacing

The first version of this loop is intentionally narrow: parameter updates only, one proposal per strategy at a time, 30-day cooldown between proposals on the same strategy. As the loop demonstrates reliability, the constraints can be relaxed via subsequent ADRs.

## Consequences

**Positive:**

- The user is presented with evidence-rich proposals rather than raw LLM suggestions. The bar for the user's attention is raised; the value of the user's attention is preserved.
- Parameter tuning becomes a continuous, low-friction part of strategy operation rather than an occasional manual chore.
- The platform's audit trail captures the full reasoning chain: LLM proposal → paper validation → user approval → live transition. Future-you (or a future auditor) can reconstruct exactly why a strategy is running with the parameters it has.
- The system "learns" in the operationally-meaningful sense: it gets better at proposing changes the user actually wants, because the rejection history feeds future proposals.

**Negative:**

- Significant architectural complexity. Parallel variant management, automated metric comparison, evidence bundle generation, and the state machine all add code and tests.
- The user's mental model of "I control every change" shifts subtly to "I approve every change, but the system proposes more changes than I would have." Users uncomfortable with this shift may experience the system as noisy.
- The 5% margin and 30-day floor will sometimes produce false negatives — genuinely good proposals that don't quite clear the bar. The cost of false negatives (missed opportunities) is, by design, lower than the cost of false positives (promoted bad changes).
- A user who systematically approves every proposal without reading the evidence has effectively given the LLM live control of strategy parameters. The platform cannot fully prevent this. We mitigate by making the evidence substantive (uncomfortable to skim) and by audit-logging the full approval context.

## Alternatives considered (not chosen)

- **No automation: every proposal manually reviewed without paper validation.** Rejected because it underutilizes the platform's paper trading capability and asks the user to evaluate proposals on Claude's word rather than on evidence.
- **Full automation: validated proposals auto-promote without user review.** Rejected because it removes the user from a consequential decision, weakens the audit story, and contradicts the spirit of ADR 0006 (which says the user is the deciding entity for AI-influenced changes).
- **Notify-then-act with a 24-hour revert window.** Considered seriously. Rejected because it shifts the default from "ask the user" to "tell the user," which is a meaningful trust shift that the platform's discipline doesn't warrant yet. May be reconsidered in a future ADR once the manual-approval version has demonstrated stable operation.
- **Aggressive criteria (small margin, short window, relative-only).** Rejected because the failure modes (random walk wins, regime overfitting, permanent underperformance disguised as improvement) are too easy to fall into.

## Re-evaluation triggers

This ADR should be revisited if any of these happen:

- The proposal-rejection rate exceeds 50% over a sustained period — that would indicate the LLM is generating noise the user doesn't want.
- The proposal-approval rate exceeds 90% — that would indicate either the LLM is exceptionally good (possible) or users are rubber-stamping (more likely). Either way, the calibration of the system needs review.
- A promoted variant catastrophically underperforms within the first 30 days of going live. We pause new promotions, audit the evaluation that allowed it, and consider tightening the criteria.
- Users report that the 30-day-or-50-trade window feels too long for fast-moving market regimes. We consider regime-specific windows.

*ADR 0007. The architectural decision that defines how AI-proposed changes get from suggestion to deployment.*
