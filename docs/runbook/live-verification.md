# Live Cross-Session Verification Runbook

> The single ordered checklist for the live-verification items deferred across
> P3 / P6 / P6b / P8 because the dev machine's Norton SSL inspection blocks
> `data.alpaca.markets` + the agent sandbox has no outbound egress. Run this on a
> **non-Norton machine with real credentials and the stack up**. Each task ends
> with the exact verification + the tag to push once it passes.
>
> Author it as you go: fill the per-task "Result" lines, commit the filled smoke
> logs, and push the tags. Nothing here is automatable from the agent sandbox —
> a human (you) on a credentialed stack drives every live step.

---

## 0. Pre-flight (do once, top of session)

1. **Non-Norton network.** Disable Norton SSL inspection (or run on WSL / another box). Confirm raw egress works:
   ```bash
   curl -s -o /dev/null -w "alpaca %{http_code}\n"   --max-time 8 https://data.alpaca.markets/v2/stocks/AAPL/bars?timeframe=1Day&limit=1 -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
   curl -s -o /dev/null -w "anthropic %{http_code}\n" --max-time 8 https://api.anthropic.com/v1/models -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01"
   ```
   Expect Alpaca `200` and Anthropic `200`. A `000`/`CERTIFICATE_VERIFY_FAILED` means Norton is still inspecting — stop and fix it (the P6b §3 rollup saw the SSL path go *intermittent* with Norton only half-off).
2. **Credentials.** `apps/backend/.env` has real `ANTHROPIC_API_KEY`, `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_API_SECRET`, `AGENT_DAILY_BUDGET_USD=2.0`. For the live-trading tasks (P6b §4.5) also `WORKBENCH_TRADING_MODE`, `WORKBENCH_LIVE_ACK=I_UNDERSTAND`, `ALPACA_LIVE_API_KEY/SECRET` — see `docs/runbook/live-mode.md`.
3. **Stack up.** `./scripts/dev.sh` (or `docker compose up -d`). Wait for health:
   ```bash
   curl -fsS http://127.0.0.1:8000/healthz && echo OK     # backend
   ```
   Frontend → `http://localhost:5173`, backend → `:8000`, chart-MCP `:8765`, workbench-MCP `:8766`.

| # | Task | One session? | Needs |
|---|---|---|---|
| 1 | **P3 → `p3-complete`** | ✅ | browser (`/agent`), Anthropic key, `.env` edit (step 5) |
| 2 | **P6 §1b.12 → `p6-session1-complete`** | ✅ | live SSE + Anthropic + compose |
| 3 | **P6 §2-variant smoke** | ✅ | compose + a **paper** order + the equity chart (browser) |
| 4 | **P6b §4.5 live submission** | ✅ | **REAL-MONEY order** — explicit, tiny, human-confirmed |
| 5 | **P6b §5 live LLM opt-in** | ❌ **multi-day** | a real **7-day** cooldown |
| 6 | **P8 §4 scheduled-scan** | ❌ **day-spanning** | the 7:30 ET cron firing on a real trading day |
| 7 | **P8 §5/§6/§7 vs real bars** | ✅ | one script, no browser/orders |

---

## 1. P3 → `p3-complete`

Walk **`docs/runbook/p3-smoke-log.md`** end to end against `http://localhost:5173/agent` with the live Anthropic key. It is 6 steps (fact-find, multi-tool, suggestion, refused-trade, **force-cost-cap**, B1-no-suggestions).

> **✅ RESOLVED (2026-06-11) — `p3-complete` TAGGED at `83a55de`.** The transport
> mismatch that blocked MCP `tool_use` was fixed: the chart-MCP moved to
> **Streamable HTTP** at `/mcp` (ADR 0016, PR #89, merged `ba99565`), and a
> follow-on fix let the chart-MCP authenticate its backend reads with the
> `WORKBENCH_MCP_KEY` bearer (PR #90, merged `83a55de`). The full chain was then
> verified live — Anthropic connector → chart-MCP (Streamable HTTP) → backend
> (bearer) → real Alpaca → model — see the Result line below. The 2026-06-09 walk
> further down remains the record for the non-tool steps (3–6).
>
> *Historical (2026-06-10) root-cause note, kept for context:* the tunnel test
> disproved the earlier "Anthropic can't reach localhost:8765" theory — Anthropic
> *did* reach the MCP over a cloudflared tunnel but still 400'd
> *"Connection error while communicating with MCP server"* (opened `/sse`, then
> cancelled the stream), because FastMCP's legacy SSE transport can't complete a
> handshake with Anthropic's `mcp-client-2025-04-04` url-connector (it expects
> Streamable HTTP). That diagnosis drove the ADR-0016 fix above.

- **⚠ Step 5 gotcha:** it appends `AGENT_DAILY_BUDGET_USD=0.005` to `.env` + restarts. **Restore `AGENT_DAILY_BUDGET_USD=2.0` (or delete the line) + restart before signing off**, or the next session opens directly in `CAPPED`. The smoke log has the cleanup check:
  ```bash
  grep -c "AGENT_DAILY_BUDGET_USD=0.005" .env   # MUST be 0
  ```
- **Verify (no leftover orders from the refused-trade step):**
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT count(*) FROM orders WHERE created_at >= datetime('now','-1 hour');"   # expect 0
  ```
- **Done when:** all 6 steps pass + the budget is restored. **Append the filled run to `p3-smoke-log.md`, commit it**, then:
  ```bash
  git tag p3-complete && git push origin p3-complete
  ```
- Result (2026-06-11): ✅ **PASS — `p3-complete` pushed at `83a55de`.** Live MCP `tool_use` dispatch verified through the production agent path (HTTP API — byte-identical to the `/agent` UI, which is a blocking POST, per §2's criterion correction): **session #14**, `claude-haiku-4-5`, `mcp_tool_use get_account_state` → `mcp_tool_result` returned **real paper-account data** (cash $9,690.53 / equity $9,983.78 / BP $39,583.22), not a 401 — confirming both the ADR-0016 transport fix and the #90 bearer-auth fix. Driven via local-only `apps/backend/scripts/p3_tool_dispatch_live.py` (hardcoded dev creds, not committed). Post-tag cleanup done: cloudflared tunnel torn down + `AGENT_MCP_SERVER_URL` reset to empty (pure-chat) + backend recreated. Steps 3–6 (suggestion / refused-trade / cost-cap / B1) were verified in the 2026-06-09 browser walk recorded in `p3-smoke-log.md`.

---

## 2. P6 §1b.12 → `p6-session1-complete`

Strictly **tag-and-verify** now (§2/§2b already shipped; Rec #10's "don't speculate against §2" no longer applies).

> **⚠ Criterion correction (2026-06-10):** the "streams tokens over SSE" wording
> below is **inaccurate for the P3 agent path**. The P3 `/agent` UI sends messages
> via a plain blocking `POST /api/v1/agent/sessions/{id}/messages` (`apiFetch` in
> `frontend/src/api/agent.ts`) — there is **no browser SSE / EventSource / WebSocket**.
> The streaming `app.llm.stream_message` surface exists only server-side. So the
> real, substantive criterion is simply: **a real agent turn records an
> `agent_sessions` row with `total_cost_usd > 0`** through that endpoint. An API-driven
> turn is byte-identical to what the browser does.

- **Real Anthropic turn via the agent endpoint.** Confirm a B2 turn records a real `total_cost_usd > 0`:
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT id, mode, status, total_cost_usd FROM agent_sessions ORDER BY id DESC LIMIT 3;"
  ```
- **Done when:** a real streamed agent turn with non-zero cost is recorded. Then:
  ```bash
  git tag p6-session1-complete && git push origin p6-session1-complete
  ```
- **Anthropic-call half — ✅ verified standalone (2026-06-08, Norton SSL scanning off).** `apps/backend/scripts/validate_live_anthropic_call.py` (run from the host backend venv, no stack) drove the runtime's actual `app.llm.create_message` path **and** the `app.llm.stream_message` SSE-backing surface against the live key (`claude-haiku-4-5-20251001`, key len 108). Both made real calls (34 in / 25 out tokens, coherent stop-loss answer), the stream yielded text deltas + saw `message_stop`, and the real `app.llm.pricing.estimate_cost` path returned a non-zero `$0.0001` — i.e. a real session's `total_cost_usd` would be > 0. All 9 hard checks green, `RESULT: PASS`.
- **✅ RESOLVED — agent-turn + cost half VERIFIED LIVE (2026-06-10), tag pushed.** Drove a real B2 turn through the **production endpoint the UI uses** (`POST /api/v1/agent/sessions` → `.../messages`, authenticated via the API): session **#9**, model `claude-haiku-4-5-20251001`, coherent reply, and **`total_cost_usd = $0.0004 > 0`** recorded on the `agent_sessions` row (confirmed via `GET /api/v1/agent/sessions/9`). Today's budget moved from $0.0000 accordingly. Because the P3 agent path is a blocking POST (no browser SSE — see the correction note above), this API turn **is** the UI path; no separate browser-SSE step exists to observe. Combined with the Anthropic-call half above, `p6-session1-complete` is satisfied → **tag pushed.**
- Result (agent-turn + cost half): ✅ PASS (2026-06-10) — session #9, $0.0004, real Haiku turn recorded.

---

## 3. P6 §2-variant live cross-session smoke

- **Paper order (byte-identical smoke):** submit a manual paper order through the OrderRouter and confirm it persists with a real broker id (per `docs/runbook/local-dev.md`'s paper-smoke). Paper — **not real money**.
- **Spawn a paper variant** for a LIVE/active parent and let it accumulate ≥1 fill; open the variant's equity-curve chart in the UI (`/strategies/{id}` → Variant card). The chart code shipped in §2c but only ran with **mocked** curves — confirm it now renders from **real** `BarCache → data.alpaca.markets` daily closes against the real fills.
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT id, harness_role, status FROM strategies WHERE status='paper_variant';"
  ```
- **Done when:** the paper order is byte-identical to the baseline + the equity chart renders from real bars+fills (browser). Record in this file (no separate tag — closes the §2-variant live caveat).
- Result (2026-06-11): **PAPER-ORDER SMOKE ✅ PASS** (first half). Manual MARKET BUY 1 AAPL via `POST /api/v1/orders` → `OrderRouter.submit` → risk check `pass` (`OK`) → Alpaca paper broker → **real `broker_order_id=dfc51bb9-baa3-4149-8fe6-8fed9addcbf5`**, order id=6, `status=submitted`; canceled clean afterward (`status=canceled`, 0 fills — market was closed, no position acquired). Path is byte-identical to the baseline manual-order flow. (Driven via local-only `apps/backend/scripts/paper_order_smoke_live.py`, hardcoded dev creds, not committed.) **VARIANT EQUITY-CHART HALF ⏳ DEFERRED** — needs a **LIVE parent** (`PaperVariantService.spawn()` raises `parent_not_live`) which requires the **24h activation cooldown** (ADR 0005), plus a paper variant accumulating ≥1 fill during market hours. The dev DB is a cold start (one IDLE strategy "Range Trader NVDA", no proposals/variants), so this half spans ≥2 sessions: backtest → paper-validate → activate (24h) → LIVE → ACCEPTED proposal → spawn variant → fill → open `/strategies/{id}` Variant card → confirm real-bars+fills curve.

---

## 4. P6b §4.5 live Alpaca submission — ⚠ REAL MONEY

> **Do not automate. Do not let an agent drive this.** This is the one place a
> real LIVE strategy places a **real-money order**. Use the smallest possible
> size, confirm each order by hand, and follow `docs/runbook/live-order-safety.md`.

- Enable the master switch (TOTP-gated): `POST /api/v1/system/live-autodispatch` `{enabled:true}` (or the Settings → Live Trading toggle). Confirm:
  ```bash
  curl -fsS http://127.0.0.1:8000/api/v1/system/live-autodispatch -H "Authorization: Bearer $TOK"   # enabled:true
  ```
- Bring one LIVE strategy to produce a single tiny order; confirm a **real-money** order reaches Alpaca and the audit chain records it:
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT id, account_id, qty, status, broker_order_id FROM orders WHERE source_type='strategy' ORDER BY id DESC LIMIT 3;"
  ```
- **Then turn the master switch back OFF** and verify suppression returns (an off-flip → ephemeral rejected order, reason `LIVE_AUTODISPATCH_DISABLED`).
- **Done when:** one real LIVE auto-dispatched order is confirmed + suppression verified with the switch off. Record here.
- Result: ____________

---

## 5. P6b §5 end-to-end live LLM opt-in — ⏳ SPANS ≥7 DAYS

> Not a single-session task: the activation cooldown is a real **7 days** and
> bypassing it is forbidden. Plan this as a start-now / finish-next-week item.

- **Day 0:** `POST /api/v1/strategies/{id}/llm-opt-in` (typed ack + TOTP) on an eligible LIVE strategy → a `pending` `llm_opt_in` row. Confirm:
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT id, strategy_id, state, strategy_version FROM llm_opt_in ORDER BY id DESC LIMIT 3;"
  ```
- **Day 7:** the `llm_opt_in_completion` cron flips `pending → active`. With a real `ANTHROPIC_API_KEY`, drive the live Haiku gate end-to-end and confirm a `LLM_LIVE_DECISION` audit row (full prompt+response, `cost_cents`) lands on the hash chain + the per-user $5/day cap counts it.
- **Done when:** a real opt-in reaches `active` and the live Haiku gate makes (and audits) at least one act/skip decision. Record here.
- Result: ____________

---

## 6. P8 §4 scheduled-scan live verification — ⏳ DAY-SPANNING

> The 15-min cron only fires meaningfully across a real trading day; the
> idempotency-per-(user,date) guarantee needs an actual day-spanning observation.

- Create a `scheduled` scan (Discovery → tick "Run automatically pre-market"); set `discovery_scan_time` in `trading_profile.session_preferences_json` to just-ahead-of-now for a first observation, then to 7:30 ET for the real cadence.
- After the due time passes on a weekday, confirm exactly **one** `trigger='scheduled'` run for the day, and that a second 15-min tick does **not** create another:
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT id, trigger, run_at, matched_count FROM scanner_runs WHERE trigger='scheduled' AND run_at >= date('now') ORDER BY id DESC;"
  ```
- Confirm the matches surface in the Opportunities "Discovery matches" widget (browser).
- **Done when:** the cron fires once at the configured time against real bars, is idempotent across ticks, and the widget shows the matches. Record here.
- Result: ____________

---

## 7. P8 §5/§6/§7 — Range Insight + template vs real daily bars

The most automatable item — **no browser, no orders**. Run the validation script
inside the backend container (real bars via the production BarCache path):

```bash
docker compose exec backend python scripts/validate_range_insight_live.py AAPL MSFT NVDA SPY
# Add a thin/young symbol to exercise the low-confidence / insufficient path, e.g. a recent IPO ticker.
```

- It prints, per symbol, the ATR / typical moves / support-resistance / 80% bands / classification computed from **real** daily bars + a PASS/FAIL battery (ATR>0, support<resistance, bands ordered, ER∈[0,1], …). Exit code is non-zero on any hard failure.
- **§6/§7 spot-check (browser, optional):** open a symbol in Charts → the Range Insight panel shows the same numbers; click "Apply range template" → the new IDLE strategy's `params_json` has `entry_price`/`exit_price`/`stop_price` derived from those real-bar values.
- **Done when:** the script returns `RESULT: PASS` for a basket of real symbols (and a thin symbol degrades to `insufficient_data`, not an error). Record the output here.
- **Result: ✅ PASS (2026-06-08, Norton SSL scanning off).** `validate_range_insight_live.py AAPL MSFT NVDA SPY` → all four fetched ~135 real daily bars, `status=ok`, `bars_used=20`, all 15 hard checks green. Sample: NVDA ATR20 $8.62 (4.2%), S/R $204.35/$236.54, high-band $209.86–$217.51, range_bound (ER 0.11); SPY ATR20 $7.12 (1.0%), S/R $731.57/$760.40, range_bound (ER 0.00). `RESULT: PASS`, exit 0. Degradation path confirmed: unknown ticker `ZZZZ` → `insufficient_data` gracefully (no crash). Run via the host backend venv (`apps/backend/.venv/Scripts/python.exe`) — Docker not required; the daemon was wedged that day. The earlier failure was `CERTIFICATE_VERIFY_FAILED` (Norton SSL MITM) until SSL scanning was disabled.

---

## Sign-off

- [ ] §0 pre-flight green (egress + creds + stack)
- [x] 1 P3 → `p3-complete` pushed (2026-06-11 @ `83a55de`; tool dispatch verified via the API/verifier — real account data, session #14; ADR 0016 transport #89 + bearer #90 both merged; budget restored, `.env` `=0.005` count 0)
- [x] 2 P6 §1b.12 → `p6-session1-complete` pushed (2026-06-10; agent-turn+cost via the production endpoint, session #9 $0.0004; "browser SSE" criterion corrected — P3 agent is a blocking POST)
- [ ] 3 P6 §2-variant equity chart from real bars+fills
- [ ] 4 P6b §4.5 real-money order confirmed + switch returned OFF
- [ ] 5 P6b §5 opt-in → active + live Haiku decision audited (week-long)
- [ ] 6 P8 §4 cron fired once at time + idempotent (day-spanning)
- [x] 7 P8 §5/§6/§7 validation script `RESULT: PASS` (2026-06-08, real bars)

> When all single-session items (1,2,3,4,7) are green and the two long-running
> items (5,6) are scheduled/observed, the live-verification backlog is closed.
