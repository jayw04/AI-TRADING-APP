# Agent Runbook (P3)

The Trading Workbench ships an in-app agent powered by Claude. It
answers questions about the user's state and (in B2 mode) proposes
parameter changes or position adjustments via structured suggestion
cards. **The agent never executes trades by default.** See
[ADR 0006 v2](../adr/0006-llm-in-order-path-gated.md) for the architectural
commitment behind that boundary — and for the gated opt-in (evaluation
harness + typed acknowledgment + 7-day cooldown) that P6 adds.

## What the agent can and can't do

**Can:**

- Read account state, positions, orders, fills.
- Read registered strategies, their runs, signals they've emitted, past
  backtest results.
- Pull quotes, bars, and computed technical indicators for any symbol.
- In B2 (Interactive) mode: suggest parameter changes or position
  adjustments via a structured `Suggestion:` block.

**Can NOT:**

- Execute trades — submit, cancel, or modify orders.
- Start, stop, or modify strategies.
- Change risk limits.
- Write to any persistent state.

The above is enforced at multiple layers:

1. The MCP tool catalog ships read-only tools only (see
   [`mcp-tools.md`](mcp-tools.md)). The CI invariant
   `apps/backend/scripts/check_mcp_readonly.sh` rejects any tool whose
   name implies mutation.
2. The CI invariant `apps/backend/scripts/check_no_llm_in_order_path.sh`
   refuses any reference to the Anthropic SDK outside the explicitly
   allowlisted modules. `OrderRouter`, the risk engine, broker adapters,
   and strategy execution code are off-limits.
3. `AgentSessionMode.B3_AUTONOMOUS` is rejected at three layers — the
   Pydantic validator on `POST /api/v1/agent/sessions`, the runtime's
   `start_session`, and the system prompt builder. All three rejections
   reference ADR 0006.

Suggestions are informational. The trader always executes via the UI.

## B1 (Read-only) vs B2 (Interactive)

| Mode | Tool catalog | Suggestion cards |
|---|---|---|
| **B1_READONLY** | Same read-only tool catalog | System prompt instructs the model not to produce `Suggestion:` blocks |
| **B2_INTERACTIVE** | Same read-only tool catalog | System prompt instructs the model to produce `Suggestion:` blocks for actionable advice |

Switch via the "+ B1 read" / "+ B2 chat" buttons on the `/agent` page.

B1 enforcement is system-prompt-only. A determined model could still
emit a suggestion despite the prompt. If that ever becomes a real
issue, the UI could strip suggestion cards from B1 sessions; so far
it hasn't happened in practice with the current model.

## Daily cost cap

Each user has a daily budget (default `$2.00`, configurable via
`AGENT_DAILY_BUDGET_USD` in `.env`). The total resets at UTC midnight.

The cap counts *all* sessions started today — `ACTIVE`, `ENDED`,
`CAPPED`, `ERROR` — not just the current one. When the user's
running total plus the next call's pre-call estimate would exceed the
budget, the runtime refuses the call and transitions the session to
`CAPPED`. Capped sessions are read-only; start a new session to
continue.

`AgentSession.daily_budget_usd` is stamped at session start, so a
mid-day config change doesn't shrink an in-flight session.

The cap is bilateral:

- **Pre-call** — the runtime estimates the next call's cost
  (deliberate overestimate of 4000 input + 1000 output tokens) and
  refuses before sending if it would push the user over budget.
- **Post-call** — the runtime charges real usage from the response
  and may transition to `CAPPED` if the running total now exceeds
  the budget, even if the pre-call gate passed.

See `apps/backend/app/agent/pricing.py` for the rate table and
`DailyBudgetResolver`. The per-model rates are placeholders until
verified against [anthropic.com/pricing](https://www.anthropic.com/pricing)
at deploy time.

## Inspecting a session

Each session writes to three tables: `agent_sessions`, `agent_messages`,
and `agent_tool_invocations`. The cascade on `agent_sessions` is
ORM-level (`cascade="all, delete-orphan"` on both relationships) since
SQLite doesn't enforce `ondelete=CASCADE`.

```bash
# Session metadata (last 5)
docker compose exec backend sqlite3 /app/data/workbench.sqlite \
  "SELECT id, mode, status, total_cost_usd,
          total_input_tokens, total_output_tokens
   FROM agent_sessions ORDER BY id DESC LIMIT 5;"

# Conversation messages for one session (replace 42)
docker compose exec backend sqlite3 /app/data/workbench.sqlite \
  "SELECT id, role, substr(content_json, 1, 100),
          input_tokens, output_tokens
   FROM agent_messages WHERE session_id=42 ORDER BY ts;"

# Tool invocations for one session
docker compose exec backend sqlite3 /app/data/workbench.sqlite \
  "SELECT tool_name, latency_ms, ts
   FROM agent_tool_invocations WHERE session_id=42 ORDER BY ts;"
```

Anthropic's MCP connector handles tool dispatch server-side; the
backend never sees the tool result, so `AgentToolInvocation.output_json`
is intentionally `NULL`. If forensic auditing of tool outputs becomes
necessary, that's a Session 4+ revisit.

## REST and WS surface

REST endpoints (full schemas in `apps/backend/app/api/v1/schemas/agent.py`):

| Method + path | Purpose |
|---|---|
| `POST /api/v1/agent/sessions` | Start session (rejects B3 with 422) |
| `GET /api/v1/agent/sessions` | List user's sessions; optional `?status=` filter |
| `GET /api/v1/agent/sessions/{id}` | Session detail + ordered conversation |
| `POST /api/v1/agent/sessions/{id}/messages` | Append user message; 409 if session is terminal |
| `POST /api/v1/agent/sessions/{id}/end` | Mark session ENDED |
| `GET /api/v1/agent/budget` | Today's spend / remaining / pct_used |

WS topic `agent` carries five bus events with a 128-event replay
window: `agent.session_started`, `agent.session_ended`,
`agent.session_capped`, `agent.session_error`, `agent.message_appended`.
The frontend chat panel subscribes to this topic and uses incoming
events as re-fetch triggers (not as the source of truth) — that way
the UI sees exactly what the server has, including SYSTEM messages
emitted during the same turn.

## API key

`ANTHROPIC_API_KEY` is read from `.env` at boot. An empty value disables
the agent: `AgentRuntime` constructs fine, but `start_session` raises
`AnthropicClientNotConfigured` with a clear message rather than crashing
on the first API call.

Per-user encrypted keys are P5+ work alongside multi-user auth. For now
the key is process-global.

Get a key at [console.anthropic.com](https://console.anthropic.com/).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `"ANTHROPIC_API_KEY is not configured"` on session start | Key not set in `.env`; restart backend after setting |
| `422` on `POST /sessions` with body `{"mode":"b3_autonomous"}` | By design — B3 is rejected by default per ADR 0006 v2 |
| Session transitions to `ERROR` mid-conversation | Anthropic API error (rate limit, network, model unavailable). Check backend logs for `anthropic_call_failed`. |
| Cost meter shows 0 after several calls | Mocked Anthropic? Or the model returned 0 usage. Check `agent_sessions.total_input_tokens` in DB. |
| Suggestion card doesn't render despite agent's text | Parser didn't match the exact `Suggestion:/Why:/Confidence:` format. Strict on the confidence enum — case-insensitive `low|medium|high` only. |
| Tool result truncated in UI | Hardcoded 4000-char cap in `MessageList.tsx`. The agent saw the full content; the UI hides the rest. |
| `503` on `POST /sessions` with `"Agent runtime not initialized"` | `app.state.agent_runtime` is `None` — the lifespan didn't construct it. Check `lifespan.py`. |

## What's deferred to later phases

- **B3 autonomous trading** — rejected by default; gated opt-in per ADR 0006 v2
  (paper-trading evaluation + typed acknowledgment + 7-day cooldown).
- **Per-user encrypted API keys** — P5 alongside multi-user auth.
- **Streaming text deltas** — the runtime uses non-streaming and the
  `stream_message` surface is unused. P4+ polish if the UX warrants it.
- **Multi-session concurrency** — one ACTIVE session per user;
  `start_session` supersedes any prior ACTIVE. Multi-session UX is
  P4+ if it ever becomes a real ask.
- **Tool result expand-to-modal** — replaces the 4000-char truncation
  with a full view. P4+ polish.

## Forward-looking allowlist

The CI invariant's allowlist already names two future modules that
don't exist yet:

- `app/services/morning_brief.py` (P5.5 §2 — scheduled narration).
- `app/services/strategy_review.py` and `drift_detection.py` (P6 —
  periodic advisory reports).

When those land they get to import the Anthropic SDK directly.
Mutating agent capabilities require a successor ADR; the current
allowlist is deliberately conservative.
