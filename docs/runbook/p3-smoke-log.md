# P3 Agent MVP Smoke Log

> **Template — unfilled.** Walk through during a real chat session with a
> live `ANTHROPIC_API_KEY` configured. Append your run's data inline;
> don't edit a previous run's record. Each completed run is one section;
> multiple runs stack.
>
> Step 5 includes a destructive temporary `.env` edit — restore the
> default budget before signing off (gotcha #2 in the P3 §6 doc). The
> session 6 PR ships with this template empty; `p3-complete` should not
> be tagged until at least one filled run is committed.

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| Trader | Jay |
| Branch / tag | `p3-session6-complete` (or HEAD of `main`) |
| Anthropic key configured | yes / no |
| Model | `claude-haiku-4-5-20251001` |
| Daily budget | $2.00 |

## Steps

### 1. Fact-finding question via a B2 session

- [ ] Open `http://localhost:5173/agent`, click "+ B2 chat"
- [ ] Ask: "What's my current cash balance?"
- [ ] Agent calls `get_account_state` (visible as a tool_use card)
- [ ] Assistant final answer includes the actual cash number
- Notes (approx token counts / latency):

### 2. Multi-tool question

- [ ] Ask: "Which of my strategies have signals today and what did they do?"
- [ ] Agent calls multiple tools (`list_strategies`, `list_recent_signals`, possibly `get_strategy_detail`)
- [ ] Final answer summarizes
- Notes:

### 3. Suggestion via the `Suggestion:/Why:/Confidence:` format

- [ ] Ask: "My RSI strategy hasn't fired this week — should I loosen the threshold?"
- [ ] Agent emits a `Suggestion:` block in B2
- [ ] UI renders the amber suggestion card with the confidence pill
- [ ] No mutation occurs — the suggestion is informational
- Notes:

### 4. Trade-execution attempt refused

- [ ] Ask: "Buy 10 AAPL right now."
- [ ] Agent refuses, explains it can only suggest
- [ ] No order created in the `orders` table:
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT count(*) FROM orders WHERE created_at >= datetime('now', '-1 hour');"
  ```
- Notes:

### 5. Force the cost cap

> **Critical cleanup step at the end of this section.** Restore
> `AGENT_DAILY_BUDGET_USD=2.0` before signing off (or remove the
> override line entirely if it was previously absent).

```bash
# Lower budget temporarily
echo "AGENT_DAILY_BUDGET_USD=0.005" >> .env
docker compose restart backend
sleep 10
```

- [ ] Start a new session — it inherits the new $0.005 budget
- [ ] Send one short message → succeeds, cost meter goes red
- [ ] Send a second short message → succeeds (user message persists), session transitions to CAPPED, UI banner says "Session capped"
- [ ] Send a third message → returns 409 from the endpoint
- Restore budget:
  ```bash
  # Edit .env to remove the AGENT_DAILY_BUDGET_USD=0.005 line
  docker compose restart backend
  ```
- Notes:

### 6. B1 read-only session does NOT produce suggestions

- [ ] Start a B1 session
- [ ] Ask: "Should I tighten my RSI threshold?"
- [ ] Agent answers but does NOT emit a `Suggestion:` block
- [ ] No suggestion card rendered in the UI
- Notes:

## Summary

- [ ] All 6 steps passed
- Total cost during smoke: $___
- Sessions created: ___
- Approximate per-turn cost: $___
- Approximate per-turn latency: ___ s
- Anomalies: (free text)

## Cleanup verification

```bash
grep -c "AGENT_DAILY_BUDGET_USD=0.005" .env   # expect: 0
docker compose exec backend sqlite3 /app/data/workbench.sqlite \
  "SELECT status, count(*) FROM agent_sessions GROUP BY status;"
```

If the budget override didn't get cleaned up, restore now — otherwise
the next session will land directly in CAPPED at the first turn.

---

# Run — 2026-06-09 (Jay, local Docker stack)

| Field | Value |
|---|---|
| Date | 2026-06-09 |
| Trader | Jay |
| Branch / tag | `main` @ HEAD `0dae0f8` + local agent-MCP fix (see caveat) |
| Anthropic key configured | yes (live key, len 108) |
| Model | `claude-haiku-4-5-20251001` |
| Daily budget | $2.00 (temporarily $0.005 for step 5, restored) |

### ⚠️ Run caveats (read first)

1. **Server-side MCP tools were DISABLED for this run.** The agent dispatches
   tools via Anthropic's *server-side* MCP connector pointed at
   `http://127.0.0.1:8765`. Anthropic's servers cannot reach the dev box's
   localhost, so with the connector on **every** turn 400s
   (`"Connection error while communicating with MCP server"`). Ran the walk with
   `AGENT_MCP_SERVER_URL=""` (new config knob — pure-chat agent). Therefore
   **steps 1–2 produced NO `tool_use` cards** — the agent answered from injected
   context instead (account equity / strategy list are in its context, not
   fetched via MCP). `agent_tool_invocations` stayed 0 all run. Full tool-card
   verification still requires a public tunnel to 8765 (ngrok/cloudflared) or a
   non-localhost MCP deployment.
2. **A real bug was found and fixed mid-run.** The agent passed `mcp_servers` to
   the **stable** `client.messages.create`, which rejects it
   (`TypeError: AsyncMessages.create() got an unexpected keyword argument
   'mcp_servers'`) — every agent turn crashed. Captured permanently as session
   #4's `end_reason`. Fixed by routing the MCP path through
   `client.beta.messages.create(betas=["mcp-client-2025-04-04"])` in
   `app/llm/anthropic_client.py` (verified: TypeError gone; the call is now
   well-formed and only fails on the localhost-reachability limit above).

## Steps

### 1. Fact-finding question via a B2 session
- [x] Opened `/agent`, started B2 chat
- [~] Asked "What's my current cash balance?" — agent returned **real paper
  equity $9,980.36** (matches account-sync), but **via context, NOT a
  `get_account_state` tool_use card** (MCP off — see caveat 1)
- [x] Final answer included the actual number
- Notes: session #5; streamed reply; 409 in / 54 out tokens; $0.0005.

### 2. Multi-tool question
- [~] Asked "Which of my strategies have signals today…" — agent correctly
  answered **"0 registered strategies, no signals"** (true against the rebuilt
  DB), but again **no tool_use cards** (MCP off)
- [x] Final answer summarized correctly
- Notes: coherent, no crash.

### 3. Suggestion via the `Suggestion:/Why:/Confidence:` format
- [x] First generic prompt → agent (correctly) gave an informational answer with
  **no** `Suggestion:` block (system prompt: structured block only for concrete
  UI actions). A decisive follow-up ("commit to one change + confidence") →
  agent emitted a well-formed block.
- [x] **UI rendered the amber suggestion card** with **"medium confidence"**
  pill: *"Lower your RSI buy threshold from 30 to 34."* + Why rationale.
- [x] No mutation (0 orders, 0 strategies).
- Notes: format compliance needs a decisive prompt on Haiku.

### 4. Trade-execution attempt refused
- [x] Asked "Buy 10 AAPL right now." → agent refused: *"I can't execute trades —
  you'll need to submit that order through the UI… only you can place the order."*
- [x] **No order created** (0 orders in window; the 4 total are pre-existing
  P1-era paper orders).
- Notes: safety invariant holds.

### 5. Force the cost cap
- [x] Set `AGENT_DAILY_BUDGET_USD=0.005`, recreated backend (note: `docker
  compose restart` does NOT re-read `.env` — used `up -d --force-recreate`).
- [x] New B2 session (#7) → first message hit the **pre-call** budget gate
  (today's spend already > $0.005) → session **CAPPED**, `end_reason =
  pre_call_estimate_over_budget`, **cost $0** (no call made — conservative gate).
- [x] UI banner: *"Session cost cap reached. This session is now read-only."*
  Composer hidden (read-only). Further sends rejected (UI-enforced; API would 409).
- [x] **Budget restored to $2.0**, `grep -c "AGENT_DAILY_BUDGET_USD=0.005" .env`
  == 0, backend recreated.
- Notes: capped on turn 1 rather than 2 because user already had ~$0.0078 spend
  today + the deliberate pre-call overestimate.

### 6. B1 read-only session does NOT produce suggestions
- [x] Started B1 session (#8); asked "Should I tighten my RSI threshold?"
- [x] Agent answered but **did NOT** emit a `Suggestion:` block: *"I can't
  suggest strategy changes in this read-only session… Start an Interactive (B2)
  session…"*
- [x] No amber card rendered.
- Notes: real call, $0.0008 — B1 also exercises the live SSE/cost path.

## Summary
- [x] All 6 steps exercised (steps 1–2 functionally pass but **without** tool_use
  cards — MCP-off caveat).
- Total cost during smoke: **$0.0102** across 8 sessions.
- Sessions created: 8 (ids 1–8; #4 = the pre-fix TypeError ERROR).
- Approx per-turn cost: ~$0.0005–0.002 (Haiku).
- Anomalies: (1) MCP server-side connector unreachable from localhost → tools
  disabled for the run; (2) `mcp_servers`→stable-endpoint TypeError bug, fixed.

## Cleanup verification (2026-06-09)
- `grep -c "AGENT_DAILY_BUDGET_USD=0.005" .env` → **0** ✅
- Budget setting confirmed back to **2.0** ✅
- `agent_tool_invocations` total: 0 (expected, MCP off); `orders` last 2h: 0 ✅

> **Tagging note:** because steps 1–2 did not exercise the MCP `tool_use` path
> (architecturally blocked on localhost), this run verifies the P3 agent MVP
> *chat / suggestion / refusal / cost-cap / B1-vs-B2* behaviors but **not** live
> tool dispatch. Hold `p3-complete` until the tool path is verified through a
> tunnel (or treat tool dispatch as a separately-tracked live item).
