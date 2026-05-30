---
name: adr
description: Use when writing, revising, or reviewing Architecture Decision Records. This includes any document named docs/adr/NNNN-<slug>.md, requests to "draft an ADR for X," or revisions to existing ADRs. Also invoke this skill when a code change touches an area governed by an ADR (single OrderRouter, credential encryption, circuit breaker, activation cooldown, LLM-in-order-path, auto-promotion) — the ADR's content is the source of truth for what that area must look like.
---

# Architecture Decision Record Conventions

ADRs are the platform's institutional memory for consequential design decisions. They exist because:

- The reasoning behind a decision is more valuable than the decision itself
- Future maintainers (including future-you) will want to relitigate decisions and need to know what was already considered
- The CI invariants, runbooks, session docs, and product overview all reference ADRs as the source of truth for *why* something is the way it is

An ADR is not a feature spec, not a status report, and not marketing copy. It is a record of a decision, the alternatives considered, and the trade-offs accepted. Done right, an ADR is read once when written and many times over the project's life.

## The current ADR catalog

| ADR | Title | Status |
|---|---|---|
| 0001 | (reserved / not yet written) | — |
| 0002 | Single OrderRouter entry point | Accepted (P1) |
| 0003 | Fernet credential encryption | Accepted (P5 §4) |
| 0004 | Daily-loss circuit breaker as hard halt | Accepted (P5 §5) |
| 0005 | 24-hour activation cooldown | Accepted (P5 §7) |
| 0006 v2 | LLM in order path gated behind evaluation + opt-in | Accepted (supersedes v1) |
| 0007 | Auto-promotion of LLM-proposed strategy updates | Accepted |
| 0008 | (Flexibility principle for AI tooling — forthcoming) | Draft |

Numbering is sequential; do not skip numbers or back-fill. If a planned ADR (like 0001 above) is never written, the number stays reserved.

## Required structure

Every ADR uses this template:

```markdown
# ADR NNNN — <Concise Title>

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| Status | Draft | Accepted | Superseded by ADR NNNN | Deprecated |
| Phase | When this decision affects the codebase (P5 §5, P6, cross-phase, etc.) |
| Supersedes | NNNN if applicable |
| Related | Comma-separated ADR numbers that bear on this decision |

## Context

One to three paragraphs. What is the situation that demands a decision? What
constraints apply? What problem are we trying to solve? Frame this as the
*question*, not yet the answer.

## Decision

The decision itself. State it as crisply as possible. Often a single sentence
or short paragraph. If the decision has sub-parts, structure them as a
numbered list.

## Rationale

Why this decision and not others. This is usually the longest section. Walk
through the considerations:

- What alternatives were considered?
- Why was each rejected?
- What trade-offs does the chosen approach accept?
- What constraints (technical, business, user-facing) drove the choice?

Be specific. "We chose A over B because A is better" is not a rationale; it's
a restatement. "We chose A over B because B requires synchronous coordination
across services and the deployment story for that is unproven, while A's
asynchronous shape matches the existing event loop" is a rationale.

## Implementation notes

Concrete details a developer will need:

- Schema changes (with exact column definitions)
- API signatures
- File locations
- CI invariants introduced (if any)
- Migration considerations
- Default values and how they can be overridden

## Consequences

The honest accounting of what this decision causes downstream:

- **Positive**: what improves
- **Negative**: what gets harder
- **Neutral**: what changes shape without obviously being better or worse

The "negative" subsection is the truth-teller. If you cannot identify
negative consequences, the decision is probably not real (it's just an
unopposed default) or the rationale is incomplete.

## Alternatives considered (not chosen)

For each major alternative:
- Brief description
- Why it was rejected
- Conditions under which we'd reconsider it

## Re-evaluation triggers

Conditions under which this ADR should be revisited:
- Specific operational signals (failure rates, user feedback, performance)
- External changes (regulatory, dependency, market)
- Time-based reviews (rare; usually triggers are condition-based)

This section is what prevents the ADR from being treated as immutable. We
do not pretend decisions are forever; we name the conditions under which
they should change.
```

Not every section needs to be long. Some ADRs have a one-paragraph context, a one-sentence decision, and four lines of rationale because that's all the decision warrants. Others (like ADR 0006 v2) have substantial sections because the decision is substantial. Match the depth to the consequence.

## Conventions

### Title is a noun phrase, not a verb

"Single OrderRouter entry point" (ADR 0002), not "Use a single OrderRouter."
"24-hour activation cooldown" (ADR 0005), not "Wait 24 hours before activating."

The title names the artifact or property the ADR establishes.

### Status is honest

If an ADR is a draft, mark it draft. If it's superseded, mark it superseded and link to the successor. If it's still nominally accepted but everyone knows it's wrong, that's a "should be superseded but hasn't been yet" state — and the right answer is to draft the successor, not to leave the bad ADR in place.

A common mistake: drafting an ADR before the decision is actually made, calling it "Accepted." The status should reflect the actual decision state.

### Cross-reference liberally

ADRs that govern overlapping areas should reference each other. ADR 0005 (activation cooldown) is referenced by ADR 0006 v2 (which extends the cooldown to 7 days for LLM-driven activation). When you write an ADR, search the existing catalog for related decisions and link them.

### One decision per ADR

If you find yourself making multiple decisions in one ADR, split them. The exception is when the decisions are genuinely coupled — ADR 0006 v2 covers both "LLM not in order path by default" and "user opt-in mechanism" because the second decision only exists in service of the first. But "LLM not in order path" and "auto-promotion of strategy updates" are separate decisions and live in separate ADRs (0006 and 0007).

### The decision is testable

The "Decision" section should be precise enough that a code reviewer can ask "does this change comply with ADR NNNN?" and the answer is unambiguous. If reasonable readers disagree about what the ADR requires, the ADR is too vague.

### The "alternatives considered" section is the credibility section

This section is what differentiates a real ADR from a rationalization. Listing alternatives we considered and rejected — with honest reasoning — shows that the chosen path was selected, not just defaulted to. Skipping this section is the most common ADR failure mode.

### "Re-evaluation triggers" prevents ossification

Decisions made under one set of constraints can become wrong when the constraints change. The triggers section names the signals that should prompt revisiting. This protects against the failure mode where an old ADR is treated as immutable when its underlying assumptions no longer hold.

## When you are asked to draft a new ADR

Walk through this:

1. **Confirm an ADR is the right artifact.** Not every decision needs an ADR. The bar is: "would a future developer need to know *why* this is the way it is?" If yes, ADR. If the decision is obvious from the code, an inline comment is enough.

2. **Search the existing catalog.** A new ADR may relate to or supersede an existing one. If you're not sure, ask the developer rather than guess.

3. **Take the next available number.** Do not skip numbers. Do not back-fill numbers below the current maximum.

4. **Write the Context first.** If you cannot articulate the problem in 1-3 paragraphs, the decision probably isn't ripe yet.

5. **Write the Decision next.** Try to fit it in a sentence; if it requires more, structure it as a numbered list.

6. **Write the Rationale third.** This is where the work is. Include the alternatives considered and the trade-offs accepted.

7. **Write the remaining sections.** Implementation notes, consequences, alternatives, re-evaluation triggers.

8. **Send for review at status `Draft`.** Do not mark it `Accepted` until it has been read and explicitly accepted. If you're the one accepting (the developer reviewing their own ADR), note the explicit acceptance in commit history or PR description.

## When you are asked to revise an existing ADR

Two cases:

**Case 1: minor edits (typos, clarifications, link fixes).** Edit in place; commit with a clear message. Status stays Accepted.

**Case 2: substantive changes to the decision itself.** Do not edit in place. The old ADR represents a real decision that was made; rewriting it erases that history. Instead:

- Draft a *new* ADR that supersedes the old one (incrementing the version number, like 0006 v2)
- Mark the old ADR as `Superseded by ADR NNNN`
- The new ADR's Context section explains what changed and why the supersession is needed
- The new ADR's Rationale references the old ADR's reasoning, naming what's preserved and what's revised

This pattern was used for ADR 0006 v1 → v2. The v1 file remains in the repo; readers can see both versions and understand how the thinking evolved.

## Patterns to avoid

- **The "Status: Pending" non-decision**. An ADR that doesn't actually decide anything ("we'll decide later when we have more information") is not an ADR. If you cannot make the decision, what you're writing is a design exploration, not a record. Different artifact, different home.

- **The Context section as marketing copy**. The context is the *problem*, not the *opportunity*. "Trading Workbench is the most disciplined trading platform on the market" is not context for an ADR; it's marketing. Context is "we have multiple paths that could submit orders, and we need to decide whether to centralize."

- **Decisions hiding in the rationale**. Sometimes ADRs make additional decisions in the rationale section ("Also, we decided to use UTC timestamps") that should be their own ADRs or shouldn't be there at all. Keep the Decision section the source of truth for what was decided; rationale explains why.

- **Re-evaluation triggers that never fire**. "We'll revisit if business needs change" is not a trigger; it's a non-statement. Triggers should be specific enough that a future reader can check whether they've fired. "If LLM auto-trade users systematically underperform across the six comparison metrics over a sustained period, revisit" is a real trigger.

- **Excessive length for routine decisions**. An ADR is the length the decision warrants. ADR 0002 (single OrderRouter) is short because the decision is binary and the rationale is straightforward. ADR 0007 (auto-promotion) is long because the decision is structured with many trade-offs. Match the length to the substance.

## What "good" looks like

A solid ADR:

- Has all sections present (none labeled "TBD")
- Has a Context that frames the problem honestly
- Has a Decision precise enough to be testable
- Has a Rationale that walks through alternatives
- Lists negative consequences in the Consequences section (not just positive)
- Names at least one re-evaluation trigger
- Is cross-referenced from related ADRs and from code comments where appropriate
- Is no longer than it needs to be

ADR 0002 (single OrderRouter) is the canonical example of a short ADR done right. ADR 0006 v2 (LLM in order path gated) is the canonical example of a long ADR done right. Read both before writing a new one.
