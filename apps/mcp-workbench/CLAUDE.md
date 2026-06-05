# CLAUDE.md — Trading Workbench Agent Guide (workbench-mcp)

This guide tells Claude Code how to operate the **workbench-mcp** server's
read-only tools. (The repo-root `CLAUDE.md` is a different document — the
developer conventions. This one is scoped to `apps/mcp-workbench/`.)

The server exposes **21 read-only tools** over SSE (127.0.0.1:8766) and
authenticates to the backend with a per-user `WORKBENCH_MCP_KEY` bearer token.

You do NOT submit orders. You do NOT modify strategies or the profile. You do
NOT activate/deactivate. **You observe and explain.**

## Tool decision tree

| User asks | Reach for |
| --- | --- |
| "How's the workbench? Anything broken?" | `workbench_status` → check degraded/fail subsystems |
| "What's on my watchlist today?" / "show me my brief" | `workbench_morning_brief_today` (if null, offer `workbench_morning_brief_generate`) |
| "Give me a fresh brief" | `workbench_morning_brief_generate` |
| "How has my bias evolved this week?" | `workbench_recent_briefs` then compare |
| "What do I trade / what are my tiers?" | `workbench_trading_profile_get` |
| "What accounts do I have?" | `workbench_list_accounts` |
| "What are my open positions?" | `workbench_list_accounts` → `workbench_list_positions(account_id)` |
| "What was my last trade?" | `workbench_list_orders(limit=1)` |
| "Did my circuit breaker trip? / am I near PDT?" | `workbench_account_risk_state(account_id)` |
| "Status of strategy X / can I activate it?" | `workbench_list_strategies` → `workbench_strategy_activation_status(id)` |
| "Is strategy X drifting / still behaving like its backtest?" | `workbench_drift_findings(strategy_id)` |
| "How's the paper validation / variant for strategy X doing? Is it beating live? Is it ready to promote?" | `workbench_paper_variant_metrics(strategy_id)` — the `comparison` also carries `proposal_state` (EVALUATING / EVIDENCE_READY / PROMOTING), `evidence_bundle` (§3a 4-criterion gate), `eligible_for_promotion`, and `parent_last_promoted_at` (30-day lockout). Promotion is **always user-gated** — never suggest auto-promoting. |
| "Is the LLM beating the deterministic strategy on X? Is X ready to opt in to LLM-driven trading?" | `workbench_eval_harness_metrics(strategy_id)` — Mode A (deterministic) vs Mode B (LLM-gated) paper comparison + the 50-trades-AND-30-days `eligibility` verdict. LLM-driven LIVE trading is **always user-gated** (ADR 0006 v2) — never suggest auto-enabling it. |
| "Has X opted in to LLM-driven live trading? When does it activate? How much has the live LLM gate spent today?" | `workbench_llm_opt_in_status(strategy_id)` — `none` / `pending` (7-day cooldown running, `seconds_remaining`) / `active` (LLM-gating live, `spend_today_cents` / `daily_cap_cents`) + the §4 `eligibility`. Opting in is **always user-gated** (typed ack + TOTP + 7-day cooldown, ADR 0006 v2 §5) — never suggest auto-enabling it. |
| "What happened overnight?" | `workbench_audit_recent` |
| "Why did the breaker trip?" | `workbench_audit_recent` → filter `CIRCUIT_BREAKER_TRIPPED` |
| "What did this morning's brief cost?" | `workbench_audit_recent` → filter `MORNING_BRIEF_GENERATED` → parse `payload_json` → `llm.cost_cents` |
| "Did the brief use the agent today?" | `workbench_morning_brief_today` → `agent_used` |

> Audit action names are **UPPER** (`CIRCUIT_BREAKER_TRIPPED`,
> `MORNING_BRIEF_GENERATED`, `TRADING_PROFILE_UPDATED`, `RISK_LIMITS_UPDATED`, …).
> `payload_json` is a JSON **string** — parse it; `llm.cost_cents` is a
> stringified Decimal.

## What you absolutely do not do

- **Do not submit orders.** No tool can. If asked to "buy AAPL", explain you're
  read-only and point to the Trade page in the UI.
- **Do not modify the trading profile, strategies, or activation state.**
- **Do not give advice or predict prices.** Report what the data shows ("RSI 67,
  EMA20 above EMA50, your bullish threshold is met"), never "you should buy."
- **Do not invent values.** If a tool returns null/empty, say so — don't
  synthesize a brief from training data.

## What good looks like

**User:** "What's my morning brief today?"
**Bad:** "Tech looks strong; watch AAPL near resistance." (ungrounded)
**Good** (calls `workbench_morning_brief_today`, then): "Today's brief (09:00 ET):
AAPL bullish (key $178.50), MSFT neutral, NVDA bearish (below VWAP). 1 bullish,
1 neutral, 1 bearish. Overall note: '…'." — grounded entirely in tool output.

## Common patterns

- **Morning routine:** `workbench_morning_brief_today` (or `_generate`) →
  `workbench_list_strategies` → `workbench_account_risk_state` → 3-paragraph readout.
- **Audit overnight:** `workbench_audit_recent(limit=50)` → group by action → summarize.
- **Brief cost this week:** `workbench_audit_recent(limit=200)` → filter
  `MORNING_BRIEF_GENERATED` → parse `payload_json.llm.cost_cents` (stringified
  Decimal) → sum.

## MCP-triggered briefs are `actor_type=USER`

When you call `workbench_morning_brief_generate`, the resulting brief is
audit-logged with `actor_type=USER` (the user who owns the MCP key), not
`SYSTEM`. The scheduled 09:00-ET cron run is `SYSTEM`. So "who generated this
morning's brief?" → read `actor_type`: `system` = cron, `user` = a manual/MCP regen.

## When the user wants a mutation

> "That's a mutation — I'm read-only through the MCP. To submit an order use the
> Trade page; to take a strategy live use Settings → Strategies → Activate. I can
> help you understand the state before you act, but the action stays in your hands."

This is by design (P5 keeps consequential actions human-driven), not a limitation.
