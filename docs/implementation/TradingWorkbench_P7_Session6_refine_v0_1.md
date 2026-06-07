# Trading Workbench — P7 §6: Refinement Chat

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§6 of 8 — P7b core) |
| Predecessor | `p7-session5-revisions-complete` (authoring-history data layer) |
| Successor | `TradingWorkbench_P7_Session7_*` (manual-edit detection) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` (Decisions 2/3) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Interactive refinement: request a change → revised code + re-backtest → accept/revert. The refine endpoint (`REVISION_SYSTEM`), auto-debug-on-failure (`DEBUG_SYSTEM`), and the conversation UI. |
| Estimated wall time | 4–6 hours |
| Tag on completion | `p7-session6-refine-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

P7a generates once; §6 makes it a conversation. The trader requests a change in plain English ("add a 2× ATR stop instead of the fixed 8%"), the platform revises the *complete* file, re-backtests, and shows it next to the prior version. The turns accumulate into the `strategy_revisions` history §5 captures on save. The §1 prompts (`REVISION_SYSTEM`, `DEBUG_SYSTEM`) and the tool-use call (§2) already exist, so §6 is the refine endpoint, the auto-debug loop, and the chat UI — built on a shared authoring-call core.

## Decisions settled for §6 (owner, 2026-06-06)

- **Auto-debug:** on a **hard** backtest failure (`syntax_error` / `runtime_error` — not `no_trades`, a legitimate result), the server calls `DEBUG_SYSTEM` **once** with the failure, re-backtests, and returns the fixed version flagged `auto_fixed`. Bounded to one retry; one extra LLM call only on a hard failure (budget-capped).
- **Diff display:** **before/after + revert** — each turn shows its code + backtest; the trader can Revert to a prior turn. No line-level highlighter (zero-dep, Norton).

## What this session ships

1. Refactor: `generate_strategy` / `refine_strategy` / `debug_strategy` over a shared `_call_authoring_model` core.
2. `_backtest_with_autofix` endpoint helper (backtest → debug-once-on-hard-failure → re-backtest).
3. `POST /strategies/author/refine`; `POST /strategies/author` gains auto-fix + `auto_fixed`.
4. Frontend: AuthorWithAI becomes a conversation (refine input + turns + revert + save full history).
5. Tests.

## Detailed work

### §6.1 — Shared authoring-call core (`service.py`)

Extract the budget-gate + key + tool-use call + parse + cost + audit into one helper, so all three call kinds share it (and the per-user budget naturally covers all of them — every call audits `STRATEGY_GENERATED` with `cost_usd` + a `kind`):

```python
async def _call_authoring_model(session, *, user_id, system, user_message, audit_extra) -> GenerationResult:
    # budget pre-gate (agent + prior P7 spend vs cap) → BudgetExceededError
    # CredentialStore key → NoApiKeyError
    # create_message(system, user_message, tools=[STRATEGY_OUTPUT_TOOL], tool_choice=emit_strategy)
    # _parse_emit_strategy → GenerationError; estimate_cost
    # audit STRATEGY_GENERATED {prompt_version, model, cost_usd, assumptions, explanation, code, **audit_extra}
    # commit; return GenerationResult

generate_strategy(... description)  → _call(GENERATION_SYSTEM, build_generation_user_message(description), {"kind":"generation","description":...})
refine_strategy(... prior_code, request) → _call(REVISION_SYSTEM, build_revision_user_message(prior_code, request), {"kind":"refinement","request":...})
debug_strategy(... prior_code, error)    → _call(DEBUG_SYSTEM,    build_debug_user_message(prior_code, error),     {"kind":"debug","error":...})
```

Audit stays `STRATEGY_GENERATED` (the `kind` distinguishes them) — **no new audit action**, and `_authoring_spent_today_usd` already sums every authoring call's cost.

### §6.2 — Auto-debug orchestration (`strategy_authoring.py`)

```python
async def _backtest_with_autofix(session, *, user_id, result, bar_cache, indicator_computer):
    outcome = await backtest_generated_code(code=result.code, bar_cache=..., indicator_computer=...)
    auto_fixed = False
    if outcome.status in ("syntax_error", "runtime_error"):
        try:
            fixed = await debug_strategy(session, user_id=user_id, prior_code=result.code, error=outcome.error or "")
        except AuthoringError:
            return result, outcome, False   # debug unavailable (budget/key) → keep the original failure
        outcome = await backtest_generated_code(code=fixed.code, bar_cache=..., indicator_computer=...)
        result, auto_fixed = fixed, True
    return result, outcome, auto_fixed
```

Bounded to **one** debug attempt (it does not recurse on the re-backtest). Used by both the author and refine endpoints.

### §6.3 — Endpoints

- `POST /strategies/author` — generate → `_backtest_with_autofix` → response gains `auto_fixed: bool`.
- `POST /strategies/author/refine` — body `{prior_code, request}` → `refine_strategy` → `_backtest_with_autofix` → same response shape (`{code, assumptions, explanation, cost_usd, model, prompt_version, backtest, auto_fixed}`). `429`/`400`/`502` like generate.

### §6.4 — Frontend: the conversation

`AuthorWithAI` becomes a turn list:
- State `turns: Turn[]` where `Turn = {kind, userMessage, result}` (`result.auto_fixed` carried).
- Empty → the description box + **Generate** → first turn (`kind: generation`).
- Non-empty → a **"Request a change"** box + **Refine** → `refine(prior_code = current turn's code, request)` appends a `refinement` turn.
- Each turn renders the user message, the read-only code, the backtest panel, and an **"auto-fixed"** badge when `result.auto_fixed`. Prior turns get **Revert to here** (truncate `turns` to that index — later refinements branch from the reverted point).
- **Save** (name) → `history = turns.map(...)`, `saveAuthored(currentCode, name, history)` → navigate. The current code is the last turn's.
- Errors (429/400/502) surfaced per call.

### §6.5 — Tests

- **Backend** (`test_strategy_authoring_refine.py`): `refine_strategy` parses + audits with `kind="refinement"`; `_backtest_with_autofix` — a runtime-failing code → `debug_strategy` is called once, re-backtested, `auto_fixed=True` (mocked LLM + bar_cache); a clean backtest → no debug call, `auto_fixed=False`; debug unavailable (budget) → original failure kept. The refine endpoint returns the new shape.
- **Frontend**: refine appends a turn (calls `refine` with the prior code); revert truncates; save sends the multi-turn history. The existing generate/save tests still pass.

## What this session does NOT do

- **No manual-edit detection / "AI out of sync"** — §7.
- **No template integration / cost-surfacing UI** — §8.
- **No multi-retry debug** — exactly one auto-debug attempt; a still-failing result is shown for the trader to address via a refinement.
- **No conversation pruning / summarization** (Q3) — turns are sent whole; relevant only at large turn counts, deferred.
- **No new audit action, no migration, no order-path.**

## Notes & gotchas

1. **Auto-debug is best-effort and bounded** — one attempt, and a budget/key failure on the debug call silently keeps the original failure (never crashes the request).
2. **`no_trades` is not a failure** — it's a legitimate backtest result; never auto-debugged.
3. **Refine is stateless** (like generate) — the client sends `prior_code` each turn; the server holds nothing. Consistent with §5's persist-on-save.
4. **Each LLM call commits its own audit row** (generate, refine, debug) — one row per commit (the hash-chain contract); an auto-fixed generation produces two rows + two costs, both counted by the budget.
5. **Reverting branches the conversation** — truncating `turns` means the next refinement starts from the reverted code; the discarded turns simply aren't sent on save.
