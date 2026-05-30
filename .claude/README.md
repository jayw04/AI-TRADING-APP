# Claude Code Kit for Trading Workbench

This kit contains the repo-root `CLAUDE.md` and the initial set of `.claude/skills/` directories that turn the Trading Workbench repository into a properly-configured Claude Code workspace.

## Contents

```
CLAUDE.md                                    Repo-root conventions; loaded every session
.claude/
  skills/
    risk-engine/SKILL.md                     Auto-loads when working on risk gates
    audit-log/SKILL.md                       Auto-loads when working on the audit chain
    session-doc/SKILL.md                     Auto-loads when drafting session docs
    adr/SKILL.md                             Auto-loads when writing ADRs
0008-flexibility-principle-ai-tooling.md     ADR to file at docs/adr/
```

## Installation

```bash
# From the Trading Workbench repo root
cp /path/to/CLAUDE.md ./CLAUDE.md
mkdir -p .claude/skills/{risk-engine,audit-log,session-doc,adr}
cp /path/to/.claude/skills/risk-engine/SKILL.md   .claude/skills/risk-engine/SKILL.md
cp /path/to/.claude/skills/audit-log/SKILL.md     .claude/skills/audit-log/SKILL.md
cp /path/to/.claude/skills/session-doc/SKILL.md   .claude/skills/session-doc/SKILL.md
cp /path/to/.claude/skills/adr/SKILL.md           .claude/skills/adr/SKILL.md

# File the ADR
cp /path/to/0008-flexibility-principle-ai-tooling.md \
   docs/adr/0008-flexibility-principle-ai-tooling.md
```

Commit everything as one PR:

```bash
git checkout -b feat/claude-code-kit
git add CLAUDE.md .claude/skills/ docs/adr/0008-flexibility-principle-ai-tooling.md
git commit -m "feat: Claude Code kit + ADR 0008 (flexibility principle)

Adds CLAUDE.md at repo root capturing architectural invariants,
development conventions, and discipline practices that govern all
Claude Code sessions in the repository.

Adds initial set of .claude/skills/ directories with SKILL.md files
that auto-load when relevant tasks are detected:
- risk-engine: risk gates, OrderRouter, risk checks
- audit-log: hash chain, AuditLogger, audit_log table
- session-doc: per-session implementation documents
- adr: Architecture Decision Records

Adds ADR 0008 capturing the flexibility principle for AI tooling
absorption — separates the runtime architecture (stable, ADR-gated)
from the development surface (composable, convention-based).

Walk-away: 30 minutes (conventions and documentation only; no code
behavior changes)."
git push -u origin feat/claude-code-kit

gh pr create --title "feat: Claude Code kit + ADR 0008" --body "..."
```

## What this enables

After installation, every Claude Code session in the repo will:

1. **Load CLAUDE.md automatically.** Architectural invariants, development conventions, and patterns to avoid are in context for every session — no need to re-explain them in each prompt.

2. **Progressively load relevant skills.** When the developer starts working on a risk gate, the `risk-engine` skill loads. When drafting an ADR, the `adr` skill loads. The session has the right detailed context without paying the token cost of all skills always being loaded.

3. **Maintain consistent conventions across sessions.** Multiple developers (or one developer across many months) work within the same set of constraints. The repo's institutional knowledge becomes Claude-readable, not just human-readable.

4. **Stay tool-portable.** The same files work with Cursor, OpenAI Codex CLI, Windsurf, and any other tool that adopts the `CLAUDE.md` + `SKILL.md` conventions (which the ecosystem has been converging on as the open standard).

## Tested compatibility

- Claude Code (CLI and VS Code extension)
- Claude Code SDK (Python and TypeScript)
- Cursor (uses the same `CLAUDE.md` + `.claude/skills/` conventions)
- OpenAI Codex CLI (adopted the SKILL.md standard in late 2025)

## Maintenance

The kit is a starting point. As the codebase grows, add new skills for new high-frequency work patterns:

- A new `broker-adapter/SKILL.md` when adding the second broker
- A new `frontend-component/SKILL.md` when frontend conventions stabilize
- A new `runbook/SKILL.md` when on-call procedures need standardization

Update `CLAUDE.md` when new architectural invariants are established (via ADR).

The four initial skills are chosen because they cover the work patterns that are *already* well-established in the design corpus and the most likely to recur across the upcoming P5 and P5.5 execution sessions. Other skills can be added when need arises; don't pre-emptively add skills for hypothetical future work.
