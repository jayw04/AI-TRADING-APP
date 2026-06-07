# Trading Workbench — P7 §8: Cost Surfacing + Presets (closes P7)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-07 |
| Phase | P7 — NL → Python strategy authoring (§8 of 8 — **closes P7**) |
| Predecessor | `p7-session7-edit-detection-complete` |
| Successor | — (P7 complete; P8 = Discovery screener + Range Insight) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` (open Q4, Q6, Q7) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Surface the authoring cost (daily budget headroom + session total) and add a small preset library to lower the barrier. Template integration deferred to P8. |
| Estimated wall time | 2–3 hours |
| Tag on completion | `p7-session8-polish-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

§8 closes P7 with the two pieces of polish that make single-shot + refinement comfortable to use day-to-day: the trader can **see what authoring costs** (Sonnet per turn is real money — Direction Q7) and can **start from a preset** instead of a blank box (Q4). Template integration (Q6) is deferred: it needs P8's range template, which doesn't exist yet, so wiring P7 to "use template defaults" now would be speculative — the `authoring_method = "template"` value is already reserved for when P8 lands.

## Decisions settled for §8 (owner, 2026-06-07)

- **Template integration (Q6): defer to P8.** No template code in §8.
- **Cost surfacing (Q7): budget headroom + session total.** A `GET /strategies/author/budget` (reusing the existing per-user daily cap) shown in the Author page header, plus the conversation's cumulative cost (client-side sum of per-turn `cost_usd`).
- **Preset library (Q4): include a small set.** A few preset-description buttons that pre-fill the (editable) description box. Frontend-only, canned text.

## What this session ships

1. `GET /strategies/author/budget` → `{daily_cap_usd, spent_today_usd, remaining_usd}`.
2. Frontend: a budget/session-cost line in the Author page header + preset buttons in the empty state.
3. Tests.

## Detailed work

### §8.1 — Budget endpoint

`service.py` — a clean public helper (so the endpoint doesn't reach into the private spend fn):

```python
async def authoring_budget(session, *, user_id, now=None) -> dict[str, Decimal]:
    cap = Decimal(str(get_settings().agent_daily_budget_usd))
    now = now or datetime.now(UTC)
    spent = (await DailyBudgetResolver(cap).spent_today(session, user_id=user_id, now=now)
             + await _authoring_spent_today_usd(session, user_id, now))   # agent + P7
    remaining = cap - spent if cap > spent else Decimal("0")
    return {"daily_cap_usd": cap, "spent_today_usd": spent, "remaining_usd": remaining}
```

`strategy_authoring.py` — `GET /strategies/author/budget` → floats of the above. (A literal 3-segment path; no clash with `/strategies/{id}/...` or the POST author routes.)

### §8.2 — Frontend: cost surfacing

- `strategyAuthoring.ts` — `budget() → {daily_cap_usd, spent_today_usd, remaining_usd}`.
- `AuthorWithAI` — fetch the budget on mount and **re-fetch after each generate/refine** (spend changed). Header line: *"Today: $0.41 / $2.00 · this session $0.13"*, where the session total is the client-side sum of `turns[*].result.cost_usd`. A near/over-cap state is already enforced server-side (429); the header is the heads-up.

### §8.3 — Frontend: presets

In the empty state (before the first generation), a row of preset buttons that pre-fill the description box (still editable):

- **Moving-average crossover** — "Buy when the 20-period EMA crosses above the 50-period EMA; exit when it crosses back below or a 2x ATR stop is hit."
- **RSI mean reversion** — "Buy when RSI(14) drops below 30; exit when it rises above 55. Risk 1% of equity per trade with a 2x ATR stop."
- **Breakout** — "Buy when price closes above the highest high of the last 20 bars; exit on a close below the 10-bar low or a 2x ATR stop."

All use supported indicators (EMA/RSI/ATR). Clicking sets the description; the trader edits and clicks Generate.

### §8.4 — Tests

- **Backend** (`test_strategy_authoring_budget.py`): `GET /strategies/author/budget` returns the cap, the spent (a seeded `STRATEGY_GENERATED` cost is reflected), and `remaining = cap − spent` (floored at 0 when over).
- **Frontend**: a preset button pre-fills the description; the budget line renders `spent / cap`; the session total updates after a generation.

## What this session does NOT do

- **No template integration** — deferred to P8 (no range template exists yet).
- **No new budget knob / cap change** — reuses `AGENT_DAILY_BUDGET_USD`; surfacing only.
- **No pre-generation cost estimate** — the header headroom covers "am I near the cap."
- **No backend preset storage** — presets are canned frontend text.
- **No schema change / migration / order-path / new CI invariant.**

## Notes & gotchas

1. **Re-fetch the budget after each turn** — spend changes per generate/refine (and an auto-fix is two calls); a stale header understates spend.
2. **Session total is client-side** (sum of returned `cost_usd`) — it resets on Discard / page reload; the *daily* figure (server) is the durable one.
3. **The cap is the agent's daily cap** ($2 default), shared across chat + authoring — the header shows the combined `spent_today`, matching the 429 the endpoints already enforce.
4. **Presets are a starting point, not a template** — they only pre-fill text; the AI still generates from scratch (no special path), so nothing here presupposes P8.
