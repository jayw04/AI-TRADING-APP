# CLAUDE.md — Trading Workbench Repository Conventions

This file is read by Claude Code at the start of every session in this repository. It captures the architectural invariants, development conventions, and discipline practices that govern all work on the codebase. Sessions that violate these conventions produce work that has to be redone, so reading this carefully and operating within it is not optional — it is how the codebase stays coherent across many sessions and many months.

When in doubt about anything not covered here, ask the developer rather than guess. Inferring intent from related code is acceptable for stylistic choices but not for architectural ones.

---

## What this project is

Trading Workbench is a local-first systematic trading platform for individual traders. Owner: Jay Wang (GlobalComplyAI, LLC). The platform is a desktop application that runs entirely on the user's hardware, with the only external dependencies being the Alpaca brokerage API (for execution) and the Anthropic API (for AI assistance). Strategies are deterministic Python files. Manual trading and automated trading share a single OrderRouter, risk engine, and audit log.

The target user is an experienced trader without deep development background. The product's competitive position is not "fastest" or "most features"; it is "most disciplined" — every layer of friction, every gate, every audit chain exists because experienced traders know that the mistakes that destroy accounts happen under emotional pressure, and friction is the feature that prevents them.

---

## Architectural invariants (non-negotiable)

These properties are enforced by code where possible, by CI invariants where code-level enforcement is infeasible, and by convention everywhere else. Violating any of these is a stop-the-PR event, not a "we'll fix it later" event.

### Single OrderRouter (ADR 0002)

Every order — manual, strategy-generated, agent-suggested — flows through exactly one dispatch point: `OrderRouter.submit()` in `apps/backend/app/services/order_router.py`. No code path may call a broker adapter directly. CI invariant `check_adr0002.sh` enforces this.

When working on order-related code, reflexively ask: "does this go through the router?" If the answer is unclear or no, that's a design issue to surface, not a tactical issue to work around.

### Hash-chained immutable audit log (P5 §8)

The `audit_log` table is append-only at the database level via SQL triggers (`audit_log_no_update`, `audit_log_no_delete`). Every entry includes `row_hash` and `prev_hash` columns; integrity is verifiable with `scripts/verify_audit_integrity.py`. Every consequential action — orders, strategy state changes, risk-limit edits, credential rotations, breaker trips — must be audit-logged via the typed `AuditLogger` API.

When adding a new action that is "consequential" in the everyday sense, audit-log it. When in doubt, lean toward logging.

### No LLM in the order path by default (ADR 0006 v2)

The order path — `OrderRouter`, the risk engine, broker adapters, strategy execution code — must not import or call `anthropic` (the Anthropic SDK) in default product configurations. LLM calls live in `app/llm/`, `app/services/morning_brief.py`, and future `app/services/strategy_review.py` and `app/services/drift_detection.py`. CI invariant `check_no_llm_in_order_path.sh` enforces the allowlist.

A user opt-in mechanism (per ADR 0006 v2 and ADR 0007) permits LLM calls in the order path for a specific user and a specific strategy, gated by a `LLM_OPT_IN_ALLOWED` database flag, a 7-day activation cooldown, and a typed user acknowledgment. This is the *only* way LLM calls reach the order path. There are no other exceptions.

### Risk gates are non-bypassable

Every order, regardless of origin, passes through the risk engine. Risk limits (position size, daily loss cap, exposure caps, order-rate caps, circuit breaker) are checked at submission time. Strategies cannot "self-police" their own risk by design; the centralized engine is the single point of truth.

### Local-first, with explicit external dependencies

The platform runs on the user's machine. The two external dependencies — Alpaca (execution) and Anthropic (LLM assistance) — are explicit, audited at the connection layer, and configurable. Credentials are Fernet-encrypted at rest (ADR 0003). Adding a new external dependency requires an ADR.

### Activation cooldowns are real (ADR 0005, extended in ADR 0006 v2)

Moving a strategy from idle to live requires a 24-hour cooldown for deterministic strategies, 7 days for LLM-driven variants. Cancellation during the cooldown is frictionless; activation is the expensive direction. Do not add code paths that bypass cooldowns "for testing" — testing happens against the cooldown system, not around it.

### The fourteen CI invariants are load-bearing

Listed in roughly order of merge: ADR 0002 single-router, strategy isolation, risk coverage ≥95%, P2 module coverage, P3 module coverage, MCP read-only, broker isolation, no env credentials, audit immutability, workbench-MCP read-only, no-LLM-in-order-path, eval-harness-paper-only (P6b §4 — the LLM eval harness never routes orders to a live account, ADR 0006 v2), llm-opt-in-bypass-gated (P6b §5 — the only sanctioned LLM-in-order-path fires only behind an `active` `llm_opt_in` DB row + version pin + per-user cap, ADR 0006 v2 §5), and altdata-order-path-isolation (ADR 0037 — the EAD alt-data / Security-Master / opportunity-report packages import no order-path module; `check_altdata_order_path_isolation.sh`, lands with Phase 1 EAD ingestion). Each enforces a property that cannot be re-introduced without breaking trust the platform has spent years earning. Disabling an invariant requires an ADR.

---

## Development conventions

### Phase and session structure

Work is organized into phases (P0, P1, P2, P3, P4, P5, P5.5, P6, P7) and sessions within phases. Each session ships as one or more PRs and is tagged when complete (`p5-session3-complete`, `p5-complete`, etc.). The phase docs in `docs/implementation/` are the authoritative plan; `tasks/todo.md` tracks current status.

Do not pivot phases mid-session without explicit developer instruction. If a session reveals that the phase plan is wrong, surface that as a finding; do not rewrite the plan unilaterally.

### Walk-away discipline

PRs sit open for at least 1 hour between "ready for review" and "merge" (longer for consequential PRs — P5 §5 risk gates, P5 §7 live path, P5 §8 production hardening minimum 2 hours). This is not a code-review duration target; it is a deliberate friction designed to catch issues that surface only when the author steps away from the work.

Honor this even when the change feels obviously safe. Especially when it feels obviously safe.

### Conservative defaults, configurable extremes

When introducing a new configurable parameter (risk limit, cooldown duration, evaluation threshold), the default is the conservative value. Users who need looser settings can configure them; users who use defaults are protected. Reverse the polarity (loose defaults, tight optional) and the platform's trust story breaks.

### Coverage gates

`apps/backend/app/risk/` requires ≥95% test coverage (enforced by `check_risk_coverage.py`). P2 and P3 modules have their own coverage requirements (enforced by `check_p2_coverage.py` and `check_p3_coverage.py`). New high-stakes modules added in P5+ should aim for the same bar.

### Database migrations

Use Alembic. Auto-generated migrations require manual review — ruff-clean imports, proper down-revision, no destructive operations without explicit confirmation. The `script.py.mako` template is configured to produce clean output; don't bypass it.

### Audit-logging the AI

LLM calls themselves are audit-logged (P3 introduced the pattern, P5+ extends it). Every Anthropic API call records the prompt, the response, the cost in cents, the model used, the session ID. The hash chain extends naturally to these entries. For agent-influenced decisions (proposals, suggestions, advisory outputs that the user acts on), the full context is preserved so a future audit can reconstruct what the agent saw and said.

### Documentation lives with the code

Per-session implementation docs in `docs/implementation/` are first-class artifacts, not afterthoughts. Runbooks in `docs/runbook/` are tested by being followed. ADRs in `docs/adr/` capture decisions that future-you will need to relitigate. When in doubt about whether to write something down, write it down.

---

## Skills loaded for this project

The `.claude/skills/` directory contains skill packages that Claude loads automatically when the task matches. The current set:

- **`risk-engine`** — invoked when working on risk gates, the order router, or risk-related code in `apps/backend/app/risk/` or `apps/backend/app/services/order_router.py`.
- **`audit-log`** — invoked when working on the audit log, the hash chain, the `AuditLogger` API, or audit-related migrations.
- **`session-doc`** — invoked when drafting or revising per-session implementation documents.
- **`adr`** — invoked when writing or revising Architecture Decision Records.

Each skill's `SKILL.md` contains the detailed conventions for its domain. You don't need to read them all preemptively; the skill system loads them when the task matches.

If a task spans domains, multiple skills load. If a task doesn't match any skill, the conventions in this CLAUDE.md govern.

---

## Patterns that have proven costly

A short list of things that have caused rework. Avoid them.

### "Just for this one case" risk-engine bypasses

The risk engine is a centralized choke point. Every time a developer has tried to bypass it "for this one case" (testing, a migration script, a debugging tool), the bypass has either grown into a real attack surface or required a refactor to remove. Do not introduce bypass paths.

### Drift between strategy code and strategy schema

Strategies declare their parameters via `params_schema`. The frontend derives its form from the schema. When the strategy code uses parameters not in the schema, or the schema lists parameters the code doesn't use, the form is broken and the user is confused. Keep them in sync. The P4 §7 typed-param-form work assumes this invariant.

### Adding a new audit action type without updating the runbook

`AuditAction` enum values are referenced by the on-call playbook. When a new action type is added, the playbook needs the corresponding scenario added — otherwise an operator paging through the playbook will not find guidance for a real production event.

### Re-running Alembic auto-generate without reviewing the result

`alembic revision --autogenerate` is a powerful tool that occasionally produces incorrect migrations (especially around index renaming and column type changes). Always review the generated migration; never merge without reading the up and down functions.

### Editing the audit log "just to clean up test data"

The audit log immutability triggers will block direct modification. If you find yourself wanting to bypass the trigger to clean up test data, the right answer is to recreate the test environment, not to disable the trigger. The trigger is the production invariant; protecting it in test environments preserves muscle memory.

---

## When the conventions and the request conflict

If the developer asks for something that violates one of the architectural invariants above, treat it as a question first ("are you intending to relax invariant X?"), not as an instruction to execute. The invariants exist precisely because they protect against decisions that look reasonable in isolation but compound badly. The conversation that catches the mistake is cheaper than the rework that follows the merge.

If the developer confirms the request is intentional, the next step is usually an ADR, not a code change. ADRs capture *why* invariants change; without that record, the next developer (including future you) has no way to evaluate whether the change was correct.

---

## Working environment notes

- **⚠️ RUNTIME IS AWS — NEVER RUN THE LOCAL STACK.** The live paper application runs **only** on the AWS EC2 box `ec2-paper` (ADR 0032 cutover 2026-06-30/07-02). The developer's laptop is **warm standby**: the local Docker stack must **not** be started. Running it dual-arms the Alpaca data websocket (conflicts with AWS) and any operational change lands on a **dead standby DB**, not the live book. The laptop autostart is guard-disabled (`scripts/workbench-autostart.bat` no-ops unless `WORKBENCH_ALLOW_LOCAL=1`) and its scheduler tasks are disabled. **Operate the live app on the box via SSH** (`ssh workbench` → `sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml …`; app ports are loopback + SSH-only SG, so `curl` the EIP times out by design — that is NOT "down"). Deploy code changes to the box per the recipe in the `aws_migration_phase1` memory. Only `docker compose` *build/config* checks and offline tests belong on the laptop.
- **Repo**: `github.com/jayw04/AI-TRADING-APP`
- **Default branch**: `main`
- **Tagging convention**: `p<N>-session<M>-complete` for sessions; `p<N>-complete` for phase completions; descriptive tags like `p4-tv-webhooks-complete` for out-of-order P4 items.
- **Local Docker stack** (⚠ standby only — see the RUNTIME note above; do not start it to trade): `docker compose` builds backend, MCP server, frontend; used for build/config verification, not for running the live app.
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2.x async + Alembic + SQLite (WAL mode). Tooling: `uv`, `ruff`, `pytest`.
- **Frontend**: React 19 + TypeScript + Vite + Tailwind + React Query + Zustand. Tooling: `pnpm`.
- **Two MCP servers**: chart-data MCP at `127.0.0.1:8765` (read-only, P3), workbench-MCP at `127.0.0.1:8766` (read-only, P5.5 §3 — `apps/mcp-workbench/`; SSE; per-user `WORKBENCH_MCP_KEY` bearer auth; agent guide in `apps/mcp-workbench/CLAUDE.md`).
- **Networking note**: Norton SSL inspection on the developer's machine blocks `data.alpaca.markets`. Live smoke and parquet fixtures require running on a non-Norton environment (WSL, CI, or another machine).

---

## How this file evolves

This CLAUDE.md is itself a living document. It updates when:

- A new architectural invariant is established (typically via ADR).
- A development convention proves consistently useful or consistently broken.
- A new external dependency is added.
- A new pattern joins the "proven costly" list.

Edits go through PR like any other code change. The PR description should explain *why* the convention changed, not just *that* it changed.

*Last meaningful update: 2026-05-29 (post ADR 0006 v2 and ADR 0007 acceptance; pre P5 execution).*
