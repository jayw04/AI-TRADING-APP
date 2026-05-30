---
name: session-doc
description: Use when drafting, revising, or reviewing per-session implementation documents. This includes documents named TradingWorkbench_P<N>_Session<M>_v<X>.md, P<N>_SessionZero_v<X>.md, P<N>_Checklist_v<X>.md, P<N>_ImplementationPlan_v<X>.md, and similar phase planning artifacts. Also invoke this skill when asked to "draft a session" or "create an implementation plan" for upcoming work.
---

# Session Document Conventions

Per-session implementation documents are the artifact that turns "we should do X" into "we shipped X." They sit between the high-level design (master design doc, ADRs) and the actual code (PRs, commits). They are read at multiple moments:

- By the developer at the start of a session, to know what to do
- By the developer at the end of a session, to confirm what was shipped
- By future-self months later, reconstructing why a particular PR exists
- By a code reviewer pairing the PR against the documented intent

A session doc that does its job well is read three or four times by the developer (over a multi-week execution arc) and at least once by someone reviewing the PR. That readership shapes what the document should contain.

## What a session document is for

The session document is the *plan* for one session of work, written before the work begins and kept frozen during execution. It is *not* a postmortem, a status update, or a marketing pitch. Its job is to make the work executable without further design conversation.

If a developer can read the session doc, do the work, write the PR, and merge — without coming back to the design author with questions — the doc has done its job. If the developer needs to negotiate any decisions mid-session, the doc has failed at planning.

The mental model: the session doc is a contract between the design author and the executor (often the same person, separated by time). The contract is explicit, complete, and reviewable.

## Required structure

Every session doc starts with a metadata table:

```markdown
| Field | Value |
|---|---|
| Document version | v0.1 (or v1.0 once executed) |
| Date | YYYY-MM-DD |
| Phase | P5 — Live Trading Toggle (or whichever) |
| Session | §7 of 8 (or whichever) |
| Predecessor | TradingWorkbench_P5_Session6_v1.0.md (tag p5-session6-complete) |
| Successor | TradingWorkbench_P5_Session8_v0.1.md |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | One- or two-sentence summary of what this session ships |
| Estimated wall time | 4-6 hours (or whatever the realistic range is) |
| Tag on completion | p5-session7-complete |
| Out of scope | Bullets listing things this session is intentionally NOT doing |
```

Then the body sections, in this order:

1. **Why this session exists** — the problem this session solves, framed in terms of the phase's goals. One or two paragraphs. If you cannot articulate why, the session probably isn't well-defined yet.

2. **What this session ships** — bulleted list of concrete deliverables. Each bullet should be something the developer can point to after the session and say "this is now in the repo."

3. **Prerequisites** — what must be true before starting this session. Usually the predecessor session is complete; sometimes specific external state (a broker account configured, a credential rotated). If a prerequisite isn't satisfiable from the previous session, that's a planning bug.

4. **Detailed work** — section by section, the actual implementation plan. This is the longest part of the document. Each subsection should:
   - State what it adds (a service, a table, an endpoint, a UI component)
   - Show the schema / signature / structure
   - Explain the design choices in inline comments or sidebars
   - Reference the ADRs that govern the choices
   - Identify the tests required

5. **Manual smoke** — the end-of-session verification. A short script of curl commands or UI steps that confirm the session's work actually functions. The smoke ends with the load-bearing assertion (typically: submit a paper order, confirm structurally consistent with the baseline).

6. **Walk-away discipline** — explicitly stated minimum walk-away time for this session's PR. P5 §5 (risk gates), P5 §7 (live path), P5 §8 (production hardening) are ≥2 hours. Routine sessions are ≥1 hour. Sessions that touch the audit subsystem are ≥2 hours.

7. **What this session does NOT do** — explicit list. The session is bounded by what's in scope; everything else (even things "obviously needed eventually") goes here.

8. **Notes & gotchas** — numbered list of things that have tripped up similar work, lessons from related sessions, hand-off notes to future-self. This section accumulates wisdom over the document's life.

## Conventions that have proven valuable

### State estimated wall time as a range

"3-5 hours" is more honest than "4 hours" and gives the developer permission to take the longer end without feeling like the plan was wrong. Sessions consistently taking the upper end of estimates is a signal the estimates are too aggressive; sessions consistently coming in under estimates is a signal they're too conservative. Calibrate.

### Reference predecessor tags explicitly

The metadata table includes the predecessor session's tag (`p5-session6-complete`). When the developer runs `git checkout p5-session6-complete && git diff main` they get exactly the work the new session builds on. This prevents the "I think I'm building on the latest, but actually session 6 had a PR that didn't merge" failure mode.

### Show, don't tell, for schemas and APIs

When the session adds a database column or an API endpoint, the document should show the exact column definition or endpoint signature. Don't write "add a column for tracking activation initiation"; write:

```sql
ALTER TABLE strategies ADD COLUMN live_activation_initiated_at TIMESTAMP NULL;
```

The developer copies this directly into the Alembic migration. If the column name turns out to be wrong, the design conversation happens before code is written.

### Inline the rationale next to the decision

A design choice in a session doc looks like:

```markdown
The activation cooldown is 24 hours, not 12 or 48.

- 12 hours is too short — a user activating at 9 PM has the strategy live before
  they wake up, defeating the "sleep on it" purpose.
- 48 hours is too long — the user has lost momentum and may forget they
  initiated activation.
- 24 hours threads the needle: the activation persists across exactly one
  sleep cycle, which is the threshold for "did I really mean to do this."

See ADR 0005 for the full reasoning.
```

The rationale is here because the developer reading the doc deserves to know *why*, not just *what*. The ADR has the canonical reasoning; the session doc has the practical justification next to the actual implementation.

### Out-of-scope is its own section, not buried

The "what this session does NOT do" list is often the most-read part of the document. It answers questions like "wait, shouldn't this session also handle live order modification?" The answer is "no, that's session 8" — and the explicit out-of-scope list makes that answer findable.

### Notes & gotchas grows over time

When a session has executed and something tripped up the developer, that lesson goes into the notes section of the session doc. Future sessions in the same phase inherit the wisdom. The notes section can grow long; that's fine. Better to overspecify a known gotcha than to have it bite again.

### Manual smoke is real, not aspirational

Every session doc ends with a smoke procedure. The smoke procedure must actually work — if you cannot run it locally, it shouldn't be in the doc. A smoke that "looks right" but doesn't run is worse than no smoke at all because it lets the session ship without verification.

## Patterns to avoid

- **Re-explaining the master design**. The session doc references the master design; it does not duplicate it. If the developer needs the master design to understand the session, they can read both documents. Duplicating leads to drift.

- **Vague verbs**. "Implement the activation flow" is not a session task; it's a phase. A session task is "add the `Activation.initiate()` method that writes `STRATEGY_ACTIVATION_INITIATED` to the audit log, sets `strategies.live_activation_initiated_at`, and schedules the cooldown completion job."

- **Skipping prerequisites because "they should be obvious"**. Prerequisites are the contract between the previous session and this one. Writing them down forces verification that the contract holds. Omitting them assumes the developer (often future-you) remembers exactly what the previous session shipped, which they do not.

- **Optimistic estimates**. A session that touches the risk engine is not a 2-hour session. A session that adds a new database table is not a 3-hour session if it includes migration, model, service, REST endpoint, and tests. Estimate the work that will actually be done, including the tests, the runbook updates, and the walk-away time.

- **Burying open questions**. If the design has unresolved decisions, they go in their own section ("Open questions to resolve before starting this session"), not woven into the implementation text where they might be missed. Open questions block execution; they should be glaringly visible.

- **Documenting after the fact**. The session doc is the plan, written before the work. A document written after the work has happened is a postmortem, not a plan. Both have value, but they're different documents. Don't conflate.

## Versioning

Session docs go through versions:

- **v0.1** — first draft, may have open questions, scope may still shift
- **v0.2 / v0.3** — revisions during design review
- **v1.0** — frozen for execution; this is the version the developer follows
- **v1.1+** — post-execution updates, typically the "notes & gotchas" section growing

The transition from v0.9-ish to v1.0 is the moment the document is "ready to execute." The developer should not start writing code against v0.x; that's a signal the doc isn't done.

## What "good" looks like in this domain

A session doc that lands cleanly typically:

- Has every metadata field filled in
- Has a clear "why this session exists" paragraph
- Lists ≤8 concrete deliverables
- Shows exact schemas, signatures, endpoint shapes for every new artifact
- References ADRs by number for governing decisions
- Has a smoke procedure that runs locally
- States its walk-away discipline explicitly
- Has a substantive "out of scope" list (5+ items)
- Estimates 3-6 hours for routine sessions, 5-8 for substantial sessions
- Has a notes & gotchas section even if initially empty

The character count usually lands between 2,000 and 4,000 lines for substantial sessions (P5 §7, §8) and 600-1,500 lines for lighter sessions. Lighter is better when the work fits; padding for length signals lack of confidence in the plan.

## A note on the P-numbering convention

Phase numbering: P0 (scaffolding), P1 (manual MVP), P2 (strategy MVP), P3 (agent MVP), P4 (polish & extend), P5 (live trading), P5.5 (workbench-MCP + trading profile + morning brief), P6 (strategy intelligence), P7 (NL → Python).

Session numbering within a phase is §1, §2, etc. Use the section sign `§` consistently — it differentiates phase sections from numbered lists in the text.

"Session Zero" of a phase is the pre-flight check that verifies the prerequisite state before §1 begins. Not all phases have a Session Zero; P5 and P5.5 do because they introduce significant new state. Session Zero documents are shorter (300-800 lines) and don't ship new code — they produce a go/no-go signal.
