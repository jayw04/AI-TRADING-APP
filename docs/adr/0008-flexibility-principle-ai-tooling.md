# ADR 0008 — Flexibility Principle for AI Tooling Absorption

| Field | Value |
|---|---|
| Date | 2026-05-29 |
| Status | Accepted |
| Phase | Cross-phase architectural principle; governs all phases including new tooling absorption |
| Supersedes | (none) |
| Related | ADR 0006 v2 (LLM in order path gated), ADR 0007 (auto-promotion), the CLAUDE.md repo conventions |

## Context

The AI tooling landscape is moving faster than any single design horizon. In the last six months alone:

- Claude Code (Anthropic's terminal-based agentic coding tool) became the dominant pattern for AI-assisted trading bot development across the YouTube and Medium ecosystems
- The Skills mechanism (`SKILL.md` files with YAML frontmatter for progressive disclosure) was released as an open standard, adopted by Anthropic, OpenAI Codex, and other coding assistants
- MCP (Model Context Protocol) became the standard for connecting AI assistants to external services; the same configuration now works across Claude Code, Cursor, Windsurf, Antigravity, VS Code, and JetBrains
- The Anthropic Agent SDK shipped with first-class support for filesystem-backed skills, allowing programmatic agents to load capability progressively
- Claude Code Routines (scheduled tasks running inside Claude Code) emerged as a viable alternative to traditional cron-based scheduling for AI-driven workflows

Each of these developments could plausibly change what the "right" architecture is for an AI-assisted trading platform. None of them invalidate the current architecture, but several offer capabilities the current architecture cannot directly use. A decision is needed about how Trading Workbench relates to this moving target.

Two failure modes are possible. The first is rigid commitment to the current architecture — refusing to absorb new capabilities because they don't fit the existing shape. This guarantees the platform falls behind as the ecosystem evolves. The second failure mode is constant pivoting — restructuring the architecture every time a new tool ships, never reaching execution because the design keeps shifting under the developer's feet.

This ADR establishes the principle for navigating between those failure modes.

## Decision

Trading Workbench treats AI tooling as a *layered* capability: the platform's core architectural invariants (single OrderRouter, immutable audit log, no-LLM-in-order-path by default, risk gates) are stable and govern the runtime; AI tooling at the development surface and the user surface is composable, swappable, and explicitly versioned per integration.

Three concrete sub-decisions follow from the principle:

**1.** The platform's runtime architecture is independent of any specific AI tool's surface. The backend uses the Anthropic API directly via the `anthropic` Python SDK; this choice serves the end user (a trader who is not a Claude Code user) and is governed by the existing ADRs 0006 v2 and 0007. Changes to this layer require ADRs.

**2.** The platform's development surface — how the developer (Jay, today) interacts with the codebase — uses Claude Code as the primary tool, with `CLAUDE.md` at the repo root and `SKILL.md` files in `.claude/skills/` providing progressive context. This surface evolves freely with the Claude Code ecosystem; switching tools (to Cursor, to a future Anthropic CLI, to a successor product) does not require an ADR because the surface is conventional, not architectural.

**3.** Future capabilities from the AI tooling ecosystem are absorbed via a "*compatible-by-default, integrated-by-decision*" stance. The platform's repo structure follows open conventions (`CLAUDE.md`, `.claude/skills/`, `mcp.json`) that work across multiple tools. Specific integrations into the platform's runtime (a new MCP tool, a new agent capability, a new scheduled-job pattern) are evaluated case-by-case and gated through ADRs when they touch architectural properties.

## Rationale

### Why separate the layers

A trading platform has at least three distinct "AI surfaces":

| Surface | Audience | Examples |
|---|---|---|
| **Runtime** | End user (trader) | The agent chat panel, the morning brief, strategy review jobs |
| **Development** | Developer (Jay) | Claude Code sessions writing new strategies, editing the codebase |
| **Operations** | Operator (also Jay, in this case) | Runbook execution, on-call response, deployment |

Conflating these layers leads to architectural confusion. Architecture C from the YouTube ecosystem (Claude Code Routines running the trading bot) is appropriate if your runtime surface and your development surface are the same person; it is wrong for Trading Workbench because the runtime surface is a non-developer trader. Architecture A (Claude Code as IDE for the developer) is correct for our development surface but irrelevant to our runtime. Separating the layers explicitly prevents one layer's appropriate pattern from contaminating another layer where it would be wrong.

### Why open conventions over vendor lock-in

The conventions used at the development surface — `CLAUDE.md`, `SKILL.md` with YAML frontmatter, `.claude/skills/` directory structure — are open standards. They work with Claude Code today; they work with OpenAI Codex CLI today; they will work with future tools that adopt the same standard. By using these conventions, the platform avoids tying its developer surface to any single vendor's tool. If Anthropic discontinues Claude Code (unlikely but possible), the conventions still work. If a better tool emerges, the developer can switch without rewriting the platform's documentation structure.

This is genuine forward compatibility, not aspirational vendor neutrality. The convention files are useful *today* for the developer using Claude Code; their portability is a free side effect.

### Why architectural decisions still require ADRs

The flexibility principle does not mean "all changes are free." Changes that touch architectural properties — the order path, the audit log's structure, the risk engine's interface, the introduction of new external dependencies — still require ADRs. The flexibility is at the *conventional* layer (file structure, naming, developer ergonomics), not at the *architectural* layer (invariants, dependencies, trust properties).

A useful test: "if this change were silently reverted, would the platform's behavior be visibly different?" If yes, it touches architecture and needs an ADR. If no (a convention change, a documentation reorganization, a developer-ergonomic improvement), the flexibility principle applies and the change can ship under ordinary review.

### Why competitive advantage flows from disciplined absorption, not first-mover adoption

The YouTube ecosystem has many traders racing to adopt every new AI capability the moment it ships. Most of those traders are operating Architecture A or C with no audit log, no risk gates, no centralized routing — the very properties Trading Workbench is built around. Absorbing new capabilities into Trading Workbench means absorbing them *within* the discipline, not around it.

The competitive position is not "we use the latest Claude Code features." The competitive position is "we use Claude Code features that survive contact with our audit and risk discipline." A new feature that cannot be integrated without breaking an invariant is a feature Trading Workbench will not integrate — and that constraint is the differentiator. Other platforms will integrate first; Trading Workbench will integrate correctly.

This is a slower posture than the YouTube ecosystem's. It is the right posture for a platform that asks users to trust it with real money.

## Implementation notes

### The CLAUDE.md and .claude/skills/ structure

At the repo root, `CLAUDE.md` captures the architectural invariants, development conventions, and discipline practices. Every Claude Code session in the repo loads this automatically. Updates go through PR like any other change.

At `.claude/skills/`, a directory per skill with a `SKILL.md` file containing YAML frontmatter and markdown content. Initial skills:

- `risk-engine/SKILL.md` — invoked when working on risk gates
- `audit-log/SKILL.md` — invoked when working on the audit chain
- `session-doc/SKILL.md` — invoked when drafting per-session implementation documents
- `adr/SKILL.md` — invoked when writing or revising ADRs

Additional skills can be added as the codebase grows. The naming convention is descriptive (the skill name matches the area of work); the YAML frontmatter description is the trigger for auto-invocation.

### The MCP configuration

The platform's two MCP servers (chart-data MCP and workbench-MCP) are configured via the standard `mcp.json` at the repo root. This file is portable across Claude Code, Cursor, Windsurf, and other MCP-compatible tools. The configuration does not assume any single tool.

The MCP servers themselves are part of the platform's runtime architecture and governed by their own design (P3 §2 for chart-data MCP, P5.5 §3 for workbench-MCP). Their interfaces follow the MCP standard; new clients that speak MCP can connect without platform-side changes.

### What is and is not portable

| Layer | Portable | Vendor-coupled |
|---|---|---|
| Repo conventions (`CLAUDE.md`, `SKILL.md`, `mcp.json`) | ✅ | — |
| MCP server protocol | ✅ | — |
| Anthropic API client in backend | — | ✅ (anthropic SDK) |
| Specific Claude model selection | — | ✅ (default: Haiku 4.5) |
| LLM prompt structure | Partial | Partial — written for Claude but largely model-agnostic |

The vendor coupling on the backend is a real cost — switching to a different LLM provider would require rewriting the backend's agent code. This is acceptable because (a) the abstraction layer for "swap out the LLM" is rarely useful in practice without significant adapter work anyway, and (b) the current Claude family is the right tool for the platform's specific needs (long-context reasoning, tool-use, code generation, MCP integration). If circumstances change such that a different provider becomes preferred, that's an ADR-level decision.

### How new tooling gets evaluated

When a new AI tool, capability, or convention appears in the ecosystem:

1. **Categorize it by layer.** Runtime? Development? Operations?

2. **Check whether it requires architectural changes.** Does it touch the order path, the audit log, the risk engine, or introduce a new external dependency? If yes, it needs an ADR before adoption.

3. **Check whether it requires only convention changes.** Does it just affect how the developer writes code or runs the platform? If yes, adopt it under the flexibility principle — try it, evaluate, keep what works.

4. **Document the evaluation outcome.** Whether you adopt or reject, write down the reasoning. This becomes the institutional memory that prevents revisiting the same decision repeatedly.

## Consequences

**Positive:**

- The platform can absorb new AI tooling capabilities as they emerge without architectural drift
- The developer surface stays current with the best tools available, improving execution velocity
- The runtime architecture stays stable, preserving the audit and trust properties that differentiate the platform
- The platform's value proposition does not depend on any single AI tool's continued existence or quality
- Documentation structure (`CLAUDE.md`, `SKILL.md`) is useful today and remains useful as the ecosystem evolves

**Negative:**

- The cognitive overhead of explicitly categorizing every new capability by layer is real, especially when the categorization is ambiguous (e.g., a new MCP feature that affects both development and runtime)
- The development surface evolves on a different cadence than the runtime, which can create temporary mismatches (e.g., a new Claude Code feature the developer uses but the documentation hasn't been updated to reflect)
- The "compatible-by-default" stance requires ongoing convention maintenance — `CLAUDE.md`, `SKILL.md` files, and `mcp.json` need to stay current
- The strict ADR gate on runtime changes can feel slow when an attractive new capability emerges; the discipline is the point, but the friction is real

**Neutral:**

- Skills authored for this project (`risk-engine`, `audit-log`, `session-doc`, `adr`) are repo-specific. They do not naturally transfer to other projects unless their content is generalized. This is a trade-off, not a problem.

## Alternatives considered (not chosen)

- **Tightly couple the runtime to Claude Code (Architecture C).** Rejected because (a) it makes the end user dependent on Claude Code, which is wrong for the platform's target audience of non-developer traders, and (b) it would move the audit log out of the platform's control and into Claude Code session storage. Both unacceptable.

- **Use only the Anthropic API and ignore the Claude Code ecosystem entirely.** Rejected because the developer surface is where execution velocity matters most. Refusing to use Claude Code for development would leave significant productivity gains on the table for no architectural benefit.

- **Build an abstraction layer that allows swapping LLM providers at runtime.** Considered seriously. Rejected because (a) the abstraction is more work than the benefit justifies given the current single-provider reality, (b) prompts written for Claude do not naturally work as well on other models without rewriting, and (c) the abstraction layer itself becomes a source of bugs and complexity. If multi-provider becomes a real requirement, build it then with concrete requirements driving the design.

- **Adopt every new AI tooling convention as it emerges.** Rejected because the cost of constant churn exceeds the benefit of being current. The flexibility principle establishes that we *can* absorb new conventions; it does not require that we *must* absorb every one immediately.

## Re-evaluation triggers

This ADR should be revisited if:

- **A specific new AI tooling capability genuinely changes the trade-offs.** If, for example, an AI-driven order-decision capability emerges that solves the audit-reproducibility problem (deterministic LLM outputs, provable forensic reconstruction), the no-LLM-in-order-path default may warrant revisiting. Currently no such capability exists.
- **The Claude Code ecosystem fragments.** If conventions diverge such that `CLAUDE.md` and `SKILL.md` no longer work across multiple tools, the portability argument weakens and the convention layer may need to be vendor-coupled.
- **The platform's user base substantially shifts toward developer-traders.** If users start being primarily developers themselves, Architecture C (Claude Code as the user surface) becomes more viable and the layer separation argued here becomes less compelling.
- **The Anthropic API or Claude family stops being the best tool for the runtime layer.** Provider preference is a real concern; if circumstances change (pricing, model quality, availability), the backend's LLM provider may need to change. This is a runtime architecture decision and would warrant its own ADR.

None of these triggers are expected in the near term. The principle is designed to be stable across the next several years of ecosystem evolution.

## Closing observation

The flexibility principle is not about being maximally responsive to the AI ecosystem. It is about being deliberate. The platform absorbs new capabilities when they fit the discipline; it refuses them when they would erode the discipline; and it documents the difference. This is what allows the platform to be both *modern* (using current best tools for development) and *trustworthy* (preserving the audit and risk properties that the user actually needs).

The competitive advantage flows from the discipline. The flexibility is what allows the discipline to scale.

*ADR 0008. The architectural principle that defines how Trading Workbench relates to a moving AI tooling landscape.*
