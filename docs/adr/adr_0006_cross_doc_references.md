# Cross-Doc References to ADR 0006 — Update PR

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-28 |
| Scope | Three small additions referencing ADR 0006 from existing project docs, so the architectural decision surfaces in the places developers and operators actually look. Single PR. ~30 minutes of work. |
| Related | `docs/adr/0006-llm-not-in-order-path.md`, `check_no_llm_in_order_path.sh` |

---

## Why this PR exists

ADR 0006 is the durable record of the LLM-not-in-order-path decision. But ADRs sit in `docs/adr/` and are read at architectural-review time — not at debugging time, not when an operator is paging through the runbook at 3am, not when a developer is reading P3's agent runtime code wondering "wait, why doesn't B3 exist?"

Three docs are read in those moments and would benefit from a brief reference to ADR 0006:

1. **P3 agent runtime documentation** (or the in-code module docstring if no separate doc) — answers "why is the agent advisory only?"
2. **P5 §7 activation wizard explainer** (in the existing runbook) — answers "why doesn't the agent get its own activation flow?"
3. **P5 §8 on-call playbook** — answers "why does the agent suggest rather than submit?"

Each addition is one or two sentences. The substance is in ADR 0006; these references just make the substance findable.

---

## Update 1 — P3 agent runtime docs

### Where

`apps/backend/app/agent/runtime.py` — the module docstring at the top of the file. If a separate doc exists at `docs/agent/runtime.md`, update both.

### Change

Find the existing module docstring. It probably reads something like:

```python
"""Agent runtime. Manages chat sessions, MCP tool calls, and response streaming.

Two modes shipped in P3:
- B1: read-only Q&A. The agent answers questions using read tools.
- B2: suggest. The agent proposes orders; the user approves before submission.
"""
```

Append a paragraph:

```python
"""Agent runtime. Manages chat sessions, MCP tool calls, and response streaming.

Two modes shipped in P3:
- B1: read-only Q&A. The agent answers questions using read tools.
- B2: suggest. The agent proposes orders; the user approves before submission.

A third mode (B3 — autonomous order submission) was originally on the
roadmap but is paused per ADR 0006 (docs/adr/0006-llm-not-in-order-path.md).
The CI invariant `check_no_llm_in_order_path.sh` enforces that LLM calls
stay in the user-initiated and scheduled-advisory paths; the order
routing path does not call the Anthropic API. P6 will add advisory
capabilities (strategy review, parameter tuning proposals, drift
detection) that build on B1/B2 patterns rather than reviving B3.
"""
```

### Why this matters

A developer reading this file is the most likely person to wonder "why isn't B3 here?" or "could I add an autonomous mode for this use case?" Without the reference, they may either:
- Reinvent the reasoning (and possibly reach a different conclusion).
- Add a partial B3 implementation thinking it was just an oversight.

The two-sentence reference points them to the full decision.

---

## Update 2 — P5 §7 activation wizard explainer

### Where

`docs/runbook/activation.md` — the runbook section explaining the activation lifecycle. Specifically, the "Overview" section that describes how a strategy moves IDLE → PENDING_LIVE → LIVE.

### Change

Find the introductory paragraph that explains strategy activation. It probably reads something like:

```markdown
## Overview

A strategy can be in one of these statuses:

| Status | Can submit orders? | ... |
| --- | --- | --- |
| IDLE | No | ... |
| PAPER | Yes (paper only) | ... |
| ...
```

Add a new paragraph immediately *before* the status table:

```markdown
## Overview

The activation flow exists because a strategy that submits real orders
needs to pass the same level of human attention as the trader's own
manual orders. The five prerequisites and 24-hour cooldown gate that
attention. This is the path for deterministic strategy code (Python
files that emit orders on bar dispatch).

**The agent (Claude) does not have its own activation flow.** Per
ADR 0006 (docs/adr/0006-llm-not-in-order-path.md), the agent operates
in advisory modes only — B1 (read-only Q&A) and B2 (suggest orders
the user approves). LLM calls are confined to user-initiated and
scheduled-advisory paths; the order routing path itself never calls
the Anthropic API. If you find yourself thinking "we should let the
agent activate its own strategy," that's a flag to re-read ADR 0006
before changing anything.

A strategy can be in one of these statuses:

| Status | Can submit orders? | ... |
| --- | --- | --- |
| ...
```

### Why this matters

The activation runbook is read by operators preparing to go live. It's the natural place for someone to think "what about the agent? does the agent activate the same way?" The reference prevents them from guessing or from raising the question as a feature request later.

---

## Update 3 — On-call playbook

### Where

`docs/runbook/on-call.md` — add a new entry under the existing scenarios.

### Change

Find a logical place in the playbook — between "Live order rejected with CONFIRMATION_MISMATCH" and "Orders are slow" is a good spot. Add:

```markdown
## "The agent suggested an order but didn't submit it"

**Symptom**: A user opens the agent chat, asks something like "buy 10
shares of AAPL," and the agent responds with a suggestion (B2 mode)
rather than submitting the order.

**This is the correct behavior, not a bug.** The agent is intentionally
advisory. See ADR 0006 (docs/adr/0006-llm-not-in-order-path.md) for the
full architectural reasoning. The short version:

- LLM outputs are non-deterministic; the audit log needs reproducible
  trade reasoning.
- LLM prompts are susceptible to social engineering in ways human
  gates aren't.
- Per-bar LLM calls don't fit the latency or cost profile of
  systematic trading.
- We can't backtest LLM-driven decisions the way we can backtest code.

**What to tell the user**: the agent helps you think about trading;
the user (or a deterministic strategy) submits the actual orders.
This is by design — the same design that gates manual LIVE orders
behind typed-ticker confirmation. The agent's suggestions can be
accepted via the standard order form, which routes through the same
risk gates as any other manual order.

**When to escalate**: if a user is asking for B3 (autonomous
submission) repeatedly, that's a product-decision conversation, not
an operations issue. The decision lives in ADR 0006; re-opening it
requires a successor ADR.
```

### Why this matters

The on-call playbook is read at the moment a user is asking "why didn't this work?" Without this entry, the operator either has to guess at the answer or look it up by reading the ADR cold. Including the entry means the answer is in front of them in skim format, which is the playbook's whole purpose.

---

## Implementation steps

```bash
# From repo root, on a fresh branch
git checkout main
git pull
git checkout -b docs/adr-0006-cross-references

# Update 1 — agent runtime docstring
$EDITOR apps/backend/app/agent/runtime.py
# (Append the paragraph to the module docstring)

# Update 2 — activation runbook
$EDITOR docs/runbook/activation.md
# (Insert the new paragraph before the status table in Overview)

# Update 3 — on-call playbook
$EDITOR docs/runbook/on-call.md
# (Add the new scenario in the appropriate place)

# Verify nothing broke
cd apps/backend
uv run pytest -q --tb=short    # full suite still green
cd ../..

# Verify CI invariants still pass (nothing in this PR should affect them)
bash apps/backend/scripts/check_adr0002.sh
bash apps/backend/scripts/check_strategy_isolation.sh
# ... (the rest)
# Plus, if shipped: bash apps/backend/scripts/check_no_llm_in_order_path.sh

# Stage
git add apps/backend/app/agent/runtime.py
git add docs/runbook/activation.md
git add docs/runbook/on-call.md

git commit -m "docs: surface ADR 0006 in agent runtime + runbooks

Three small additions referencing ADR 0006 from the places developers
and operators actually look:

- apps/backend/app/agent/runtime.py — module docstring explains why B3
  is paused and points at the CI invariant.
- docs/runbook/activation.md — Overview paragraph explains that the
  agent does not have its own activation flow.
- docs/runbook/on-call.md — new scenario covering 'the agent suggested
  but didn't submit,' which is by design.

ADR 0006 itself is the source of truth; these are pointers to it from
contexts where the question naturally arises."

git push -u origin docs/adr-0006-cross-references

gh pr create \
  --title "docs: surface ADR 0006 in agent runtime + runbooks" \
  --body "Three small cross-references to ADR 0006 (LLM not in order path).

No code change. No invariant change. Just doc updates that make the
architectural decision findable in the places developers and operators
naturally look:

1. Agent runtime module docstring — answers 'why isn't B3 here?'
2. Activation runbook — answers 'why doesn't the agent activate its own
   strategy?'
3. On-call playbook — answers 'the agent suggested but didn't submit'

Walk-away: not required (doc-only changes, no semantics modified).
15-minute review sufficient."

# After review
gh pr merge --merge --delete-branch
git checkout main && git pull
```

No tag required — these are documentation updates, not session work.

---

## What this PR does NOT do

- Does not change any code semantics.
- Does not add any tests (doc changes don't need new tests; existing tests still pass).
- Does not change CI invariants.
- Does not modify ADR 0006 itself.
- Does not draft the P6 Direction doc into the repo (that's a separate
  PR if/when you decide to commit it to `docs/phases/` or wherever).

## Optional fourth update — if a separate `docs/agent/runtime.md` exists

If the project has separate documentation at `docs/agent/runtime.md` (or similar), apply the same paragraph addition there as Update 1. The module docstring and the standalone doc should stay in sync.

If no such standalone doc exists, that's fine — the module docstring is sufficient. Developers read code; the docstring will surface during IDE hover, `git grep`, and source-file inspection.

## Optional fifth update — if a frontend "Agent" page or modal exists

If the frontend has a help text or info icon on the agent chat page explaining what the agent can and can't do, that's another natural place for a brief mention. Something like:

```tsx
<HelpText>
  The agent helps you think about trading — answering questions,
  suggesting orders for you to review. It does not submit orders
  on its own. <Link to="/docs/architecture#adr-0006">Why?</Link>
</HelpText>
```

This is optional because (a) the frontend may or may not have user-facing help text on the agent surface, and (b) the link target depends on how the project surfaces docs to end users. If your frontend has the surface and you want to wire it up, do it; if not, skip.

---

*End of cross-doc references update notes v0.1.*
