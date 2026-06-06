# Trading Workbench — P7 §2: Strategy-Generation Service

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-05 |
| Phase | P7 — NL → Python strategy authoring (§2 of 8 — P7a) |
| Predecessor | `p7-session1-prompts-complete` (§1 prompts) |
| Successor | `TradingWorkbench_P7_Session3_*` (auto-backtest after generation) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The `strategy_authoring` generation service: the Sonnet tool-use call, output parsing, cost-gating + audit, and the `POST /strategies/author` endpoint. **Generate-and-return only — no persistence.** |
| Estimated wall time | 4–6 hours |
| Tag on completion | `p7-session2-generation-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

§1 froze the prompts; §2 turns them into a working generation call. A trader sends a description, the platform calls Sonnet forcing the `emit_strategy` tool, parses `{code, assumptions, explanation}`, audits the full request/response with its cost, and returns the artifact for the trader to review. Nothing is persisted — the save flow (write the `.py`, register the strategy, set `authoring_method`) is §4. §2 is the LLM-generation mechanics, gated by the platform's existing per-user daily LLM budget so a flurry of Sonnet generations can't run up an unbounded bill.

## Decisions settled for §2 (owner, 2026-06-05)

- **SDK call:** extend the **allowlisted** `app.llm.anthropic_client.create_message` with backward-compatible `tools` + `tool_choice` kwargs (the `AnthropicCall.content_blocks` wrapper already normalizes `tool_use.input`). `strategy_authoring` imports `create_message`, so it stays **out** of the no-LLM allowlist — all Anthropic SDK usage stays centralized in `app/llm/`.
- **§2 scope:** **generate-and-return only.** No file write, no `strategies` row, no `authoring_method` field, **no migration**. Persistence is §4.
- **Cost (Direction Q7):** **reuse the agent daily budget.** Gate generation on the user's combined daily LLM spend (agent sessions + prior P7 generations) against `settings.agent_daily_budget_usd`; refuse (HTTP 429) if the next call would exceed it. Audit the real cost and return it so the UI can surface "$X".

## What this session ships

1. `create_message(..., tools=None, tool_choice=None)` — the only `app/llm/` change.
2. `app/services/strategy_authoring/service.py` — `generate_strategy(...)` + the combined-budget pre-check + tool-output parse + the generation audit.
3. `AuditAction.STRATEGY_GENERATED` (+ on-call runbook scenario).
4. `app/api/v1/strategy_authoring.py` — `POST /strategies/author`.
5. Tests.

## Detailed work

### §2.1 — Extend `create_message`

```python
async def create_message(*, api_key, model, system, messages,
                         mcp_server_url=None, max_tokens=4096,
                         tools=None, tool_choice=None) -> AnthropicCall:
    ...
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    ...
```

Purely additive — existing callers (morning_brief, eval_harness, the agent runtime) are unaffected because the new kwargs default to `None` and are only added to the request when set.

### §2.2 — `generate_strategy`

`app/services/strategy_authoring/service.py`:

```python
GEN_EST_INPUT_TOKENS = 4000   # system prompt (~2-3k) + description, for the pre-call gate
GEN_EST_OUTPUT_TOKENS = 2000  # a ≤~150-line strategy + assumptions + explanation

@dataclass(frozen=True)
class GenerationResult:
    code: str
    assumptions: list[str]
    explanation: str
    cost_usd: Decimal
    prompt_version: str
    model: str

async def generate_strategy(session, *, user_id, description) -> GenerationResult:
    # 1. Budget pre-gate (reuse the agent cap): refuse if agent_spent + p7_spent +
    #    estimated > settings.agent_daily_budget_usd  → raise BudgetExceededError.
    # 2. Resolve the user's Anthropic key (CredentialStore) → raise NoApiKeyError if missing.
    # 3. create_message(model=GENERATION_MODEL, system=GENERATION_SYSTEM,
    #      messages=[{role:user, content: build_generation_user_message(description)}],
    #      tools=[STRATEGY_OUTPUT_TOOL], tool_choice={"type":"tool","name":"emit_strategy"},
    #      max_tokens=4096).
    # 4. Parse the tool_use block from content_blocks → {code, assumptions, explanation}.
    #      Missing/malformed tool block → raise GenerationError (the model didn't emit the tool).
    # 5. cost_usd = estimate_cost(GENERATION_MODEL, input_tokens, output_tokens).
    # 6. Audit STRATEGY_GENERATED (forensic): {description, prompt_version, model, cost_usd,
    #      assumptions, explanation, code}. Commit.
    # 7. return GenerationResult.
```

The combined-budget helper (kept in `service.py`, self-contained):

```python
async def _authoring_spent_today_usd(session, user_id, now) -> Decimal:
    # sum cost_usd from STRATEGY_GENERATED audit rows for the user since start-of-day (UTC),
    # via func.json_extract(AuditLog.payload_json, "$.cost_usd") — mirrors the §5 audit-sum.
```

> **Note on the shared pool:** the gate counts agent-session spend (`DailyBudgetResolver.spent_today`) **plus** P7 generation spend against the one `agent_daily_budget_usd`, so P7 respects the shared daily cap from its side. The agent's own pre-call gate still counts only agent spend (it slightly under-counts now that P7 also spends the pool); fully unifying the resolver to count both is a low-priority follow-up, not §2.

### §2.3 — Audit + runbook

`AuditAction.STRATEGY_GENERATED` — `actor_type=USER`, `target_type="strategy_authoring"`, payload carries the full prompt context (description + prompt_version + model) and the response (code + assumptions + explanation) + `cost_usd` (ADR-style forensic capture; the budget sums `cost_usd` from these rows). On-call runbook scenario: "a strategy generation failed / what did authoring cost today" → read `STRATEGY_GENERATED`.

### §2.4 — Endpoint

`app/api/v1/strategy_authoring.py` (off the P2 gate):

- `POST /strategies/author` — body `{description: str}` → `200 {code, assumptions, explanation, cost_usd, prompt_version, model}`. `BudgetExceededError → 429`, `NoApiKeyError → 400`, `GenerationError → 502`. Register in `app/api/v1/__init__.py`.

### §2.5 — Tests

- `create_message` passes `tools` / `tool_choice` only when provided (and not otherwise) — a mocked client asserts the kwargs.
- `generate_strategy` parses a mocked tool_use response → `GenerationResult`; audits `STRATEGY_GENERATED` with the cost; a response with no tool_use block → `GenerationError`.
- Budget: with `spent_today + estimate > cap` → `BudgetExceededError` (no Anthropic call made). The P7 audit-sum counts prior `STRATEGY_GENERATED` cost.
- No Anthropic key → `NoApiKeyError`.
- Endpoint: success 200 shape; budget 429; no-key 400.
- The no-LLM invariant still passes (`strategy_authoring` not allowlisted — it imports `create_message`, never `anthropic`).

## What this session does NOT do

- **No persistence** — no file write to `strategies_user/`, no `strategies` row, no `authoring_method` field, **no migration**. (§4 save flow.)
- **No backtest** — §3 runs the auto-backtest after generation.
- **No UI** — §4.
- **No refinement / revision / debug calls** — §6 (P7b) wires `REVISION_SYSTEM` / `DEBUG_SYSTEM`; §2 only uses `GENERATION_SYSTEM`.
- **No new budget knob** — reuses `agent_daily_budget_usd`.
- **No order-path / risk-engine touch / new CI invariant.**

## Notes & gotchas

1. **`tool_choice` forces the tool** — `{"type": "tool", "name": "emit_strategy"}` makes the model emit the structured output rather than prose; the parse looks for the `tool_use` block whose `name == "emit_strategy"`.
2. **Defensive parse** — if the model returns no tool_use block (or malformed input), raise `GenerationError`; do NOT fabricate code. §3's debug loop is the recovery path once it exists; for §2 the endpoint surfaces the failure.
3. **Budget is calendar-day UTC** to match `DailyBudgetResolver.spent_today` (start-of-day), not a 24h rolling window.
4. **Cost in USD** (the agent budget is USD) — store `cost_usd` in the audit and sum that; the UI shows dollars.
5. **The generated code is NOT validated/executed in §2** — parsing only. Isolation/compile/backtest validation is §3. (The prompt is the first line of defense; §3 is the real one.)
6. **`strategy_authoring` stays out of the no-LLM allowlist** — it must call `create_message`, never import `anthropic`. A test/invariant run confirms this.
