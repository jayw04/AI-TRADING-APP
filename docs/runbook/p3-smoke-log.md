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
