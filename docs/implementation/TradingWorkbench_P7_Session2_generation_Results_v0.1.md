# P7 Session 2 — Strategy-generation service — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§2 of 8 — P7a) |
| Plan doc | `TradingWorkbench_P7_Session2_generation_v0_1.md` |
| Predecessor | `p7-session1-prompts-complete` |
| Tag | **`p7-session2-generation-complete`** (`e260404` squash → moved to the §2 todo commit) |
| Shipped as | PR **#67** — branch `feat/p7-session2-generation`; squash-merged `e260404` |
| Verdict | **GO.** The generation service + endpoint. Generate-and-return only; no migration, no order path, no UI. Full backend suite green; all 10 invariants + 3 coverage gates. |

## What shipped

- **`create_message(..., tools=None, tool_choice=None)`** — the only `app/llm` change (backward-compatible; only sent when provided). The `AnthropicCall.content_blocks` wrapper already normalized `tool_use.input`, so no other plumbing was needed. `strategy_authoring` imports `create_message` → stays **out** of the no-LLM allowlist (SDK usage centralized in `app/llm/`).
- **`app/services/strategy_authoring/service.py`** — `generate_strategy(session, *, user_id, description)`: budget pre-gate (reuse the agent cap — agent-session spend + prior P7 `STRATEGY_GENERATED` spend vs `settings.agent_daily_budget_usd`; `BudgetExceededError` **before** any Anthropic call) → resolve the user's key (`NoApiKeyError`) → Sonnet tool-use call (force `emit_strategy`) → `_parse_emit_strategy` (no/malformed tool block → `GenerationError`, never fabricate) → `estimate_cost` → audit `STRATEGY_GENERATED` → `GenerationResult`. `_authoring_spent_today_usd` sums `cost_usd` from the audit rows (calendar-day UTC, matching `DailyBudgetResolver`).
- **`AuditAction.STRATEGY_GENERATED`** (forensic: description + prompt_version + model + code + assumptions + explanation + `cost_usd`) + on-call runbook scenario.
- **`POST /api/v1/strategies/author`** — `200 {code, assumptions, explanation, cost_usd, prompt_version, model}`; `429` budget / `400` no-key / `502` generation-failure.

## Decisions settled (owner, 2026-06-05/06 — AskUserQuestion)

1. **SDK call:** extend the allowlisted `create_message` — no new allowlist entry.
2. **Scope:** generate-and-return only — persistence, the `authoring_method` field, and its migration land in §4.
3. **Cost (Direction Q7):** reuse the agent daily budget (`AGENT_DAILY_BUDGET_USD`); audit + return `cost_usd`.

## Notes

- **Shared budget pool:** the gate counts agent-session spend + P7 generation spend against the one cap, so P7 respects it from its side. The agent's own gate still counts only agent spend (slight under-count now that P7 also spends); fully unifying the resolver is a low-priority follow-up, not §2.
- **No code validation/execution in §2** — parsing only. Compile + isolation-validate + backtest is §3.

## Verification

- 8 new §2 tests (create_message tools passthrough; parse/audit; no-tool → error; no-key; **budget-exceeded doesn't call the LLM**; endpoint 200/429/400). Full backend suite **992 passed / 9 skipped / 0 failed**; ruff + mypy(184) clean.
- All 10 shell invariants (no-LLM confirms `strategy_authoring` un-allowlisted) + 3 coverage gates (risk 0.904 / P2 / P3). **No migration.**
- PR CI all green (Python-backend 5m4s). Merged on the owner's "merge on green."

## Next

**§3** — auto-backtest after every generation: compile the generated code, validate it passes strategy isolation, run it against the cached bar data, and return the metrics (return / Sharpe / max drawdown / win rate / trade record) alongside the code. Then **§4** — the "Author with AI" UI + the save flow (write the `.py` → `POST /strategies` → set the new `authoring_method` field; the migration lands here). That completes **P7a** (single-shot generation, independently shippable). Open Qs for §3/§4: backtest window (Q2), logic-bug mitigation (Q5).
