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
- Result: ____________

---

## 2. P6 §1b.12 → `p6-session1-complete`

Strictly **tag-and-verify** now (§2/§2b already shipped; Rec #10's "don't speculate against §2" no longer applies).

- **Live SSE handshake + real Anthropic call** via the `/agent` chat (see `docs/runbook/agent.md` for the streaming details). Confirm a B2 turn streams tokens over SSE and an `agent_sessions` row records a real `total_cost_usd > 0`:
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT id, mode, status, total_cost_usd FROM agent_sessions ORDER BY id DESC LIMIT 3;"
  ```
- **Done when:** a real streamed agent turn with non-zero cost is recorded. Then:
  ```bash
  git tag p6-session1-complete && git push origin p6-session1-complete
  ```
- Result: ____________

---

## 3. P6 §2-variant live cross-session smoke

- **Paper order (byte-identical smoke):** submit a manual paper order through the OrderRouter and confirm it persists with a real broker id (per `docs/runbook/local-dev.md`'s paper-smoke). Paper — **not real money**.
- **Spawn a paper variant** for a LIVE/active parent and let it accumulate ≥1 fill; open the variant's equity-curve chart in the UI (`/strategies/{id}` → Variant card). The chart code shipped in §2c but only ran with **mocked** curves — confirm it now renders from **real** `BarCache → data.alpaca.markets` daily closes against the real fills.
  ```bash
  docker compose exec backend sqlite3 /app/data/workbench.sqlite \
    "SELECT id, harness_role, status FROM strategies WHERE status='paper_variant';"
  ```
- **Done when:** the paper order is byte-identical to the baseline + the equity chart renders from real bars+fills (browser). Record in this file (no separate tag — closes the §2-variant live caveat).
- Result: ____________

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
- Result: ____________

---

## Sign-off

- [ ] §0 pre-flight green (egress + creds + stack)
- [ ] 1 P3 → `p3-complete` pushed (+ budget restored, `grep -c …=0.005 .env` == 0)
- [ ] 2 P6 §1b.12 → `p6-session1-complete` pushed
- [ ] 3 P6 §2-variant equity chart from real bars+fills
- [ ] 4 P6b §4.5 real-money order confirmed + switch returned OFF
- [ ] 5 P6b §5 opt-in → active + live Haiku decision audited (week-long)
- [ ] 6 P8 §4 cron fired once at time + idempotent (day-spanning)
- [ ] 7 P8 §5/§6/§7 validation script `RESULT: PASS`

> When all single-session items (1,2,3,4,7) are green and the two long-running
> items (5,6) are scheduled/observed, the live-verification backlog is closed.
