# P7 Session 8 — Cost surfacing + presets — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-07 |
| Phase | P7 — NL → Python strategy authoring (§8 of 8 — **closes P7**) |
| Plan doc | `TradingWorkbench_P7_Session8_polish_v0_1.md` |
| Predecessor | `p7-session7-edit-detection-complete` |
| Tag | **`p7-session8-polish-complete`** (`1d78f3e` squash → moved to the §8 todo commit) |
| Shipped as | PR **#73** — branch `feat/p7-session8-polish`; squash-merged `1d78f3e` |
| Verdict | **GO. P7 COMPLETE.** Cost is surfaced, presets lower the barrier, templates deferred to P8. Full backend + frontend suites + 3 coverage gates + all 10 invariants green; no migration. |

## What shipped

- **`GET /strategies/author/budget`** `{daily_cap_usd, spent_today_usd, remaining_usd}` via `service.authoring_budget(session, *, user_id, now=None)` — reuses the agent daily cap (`AGENT_DAILY_BUDGET_USD`, $2 default); `spent_today` = `DailyBudgetResolver.spent_today` (agent) + `_authoring_spent_today_usd` (P7); `remaining` floored at 0. Surfacing only — no new knob.
- **Frontend** — `AuthorWithAI` gains a budget header (*"Today: $0.40 / $2.00 · this session $0.13"*; session total = client-side sum of per-turn `cost_usd`, re-fetched after each generate/refine) + a `PRESETS` library (Moving-average crossover / RSI mean reversion / Breakout) whose buttons pre-fill the editable description box (canned text, all using supported indicators).

## Decisions settled (owner, 2026-06-07 — AskUserQuestion)

1. **Template integration (Q6): defer to P8** — no range template exists yet; `authoring_method = "template"` is reserved for then.
2. **Cost surfacing (Q7): budget headroom + session total.**
3. **Preset library (Q4): include a small set** (frontend-only canned descriptions).

## Verification

- 3 backend budget tests (zero spend; reflects a seeded `STRATEGY_GENERATED` cost; `remaining` floored at 0 when over) + 1 frontend test (budget header renders `spent/cap`; a preset pre-fills the description). The frontend test's mock preserves the real `PRESETS` export (partial mock).
- Full backend suite **1037 passed / 9 skipped / 0 failed**; ruff + mypy(187) clean; 3 coverage gates (risk 0.904 / P2 / P3); all 10 shell invariants. Frontend **vitest 136** + tsc + eslint clean. **No migration.**
- One PR-CI infra flake — the `Build image (workbench-mcp)` job hit a Docker Hub registry timeout while booting buildkit (`registry-1.docker.io … Client.Timeout`), before any code build; re-running the job passed (24s). All test jobs + other image builds were green first try. Merged on the owner's "merge on green."

## P7 is complete

| § | Capability |
|---|---|
| §1 | System prompts (generation / revision / debug, versioned, tool-use schema) |
| §2 | Generation service (Sonnet tool-use, budget-gated, audited) |
| §3 | Auto-backtest + AST safety validation of generated code |
| §4 | "Author with AI" UI + save flow + `authoring_method` (**P7a complete**) |
| §5 | `strategy_revisions` authoring history (persist-on-save) |
| §6 | Refinement chat + auto-debug-once |
| §7 | Manual-edit detection ("AI out of sync") |
| §8 | Cost surfacing + presets (**P7b complete**) |

A trader can describe a strategy in plain English, see the generated Python with a backtest and the AI's assumptions, refine it in conversation (with one auto-debug retry on a hard failure), and save it into the standard backtest → paper → activation lifecycle — with the authoring history preserved read-only, manual edits flagged, and the daily AI cost surfaced.

## Next

**P8** — Discovery screener + Range Insight (Direction docs exist) — the next phase, which also picks up the deferred **template integration** (Q6) against P8's real range template. Open P7 items left for later/never: conversation pruning (Q3, only relevant at large turn counts), logic-bug mitigation (Q5), the §5b raise-cap endpoint, and the still-pending P6 live cross-session verification (non-Norton).
