# Range Strategy — Implementation Review (pre-Monday overview)

| | |
|---|---|
| **Date** | 2026-06-27 |
| **Author** | Claude (implementation) — for owner final overview |
| **Purpose** | Document the *completed* Range-trading research implementation so the owner can verify it matches the plan and flag missing elements **before Monday 2026-06-29 market open** (first live auto-select fire = Mon 09:00 ET). |
| **Source of truth (plan)** | `Docs/design/RangeTrading_Logic_and_Research_v0.1.md` (frozen v0.3); `docs/adr/0028-scheduled-strategy-universe-refresh.md` (**Accepted**); owner reviews in `docs/review/comments.md` + this folder. |
| **Deployed on** | branch `docs/combined-book-port001` → backend image rebuilt + restarted (healthy). |

> How to use this doc: §12 is the **verification checklist** (plan item → status → where). §13 is the **Monday runbook**. §11 lists what's **deferred/planned** (intentionally not done yet). §14 lists **things to confirm**.

---

## 1. Shipped PRs (all merged to `main`)

| PR | What |
|----|------|
| #281 | **H1** — evidence-first candidate ranker + Top-N selection |
| #282 | **H2** — entry: support-zone, VWAP gate, ATR-scaled zone |
| #283 | **Multi-symbol-safe** Range Trader (per-symbol state) + per-position budget |
| #287 | **H3** — scale-out partial profit-take (first exit lever) |
| #288 | **Daily Top-N auto-select job** + "Today's range universe" UI |
| #289 | Auto-select **pre-flight guards** (#6) + ADR 0028 review fold (Accepted) |
| #290 | **#4** minimum-quality gate (initial) + **#3** richer selection evidence |
| #291 | **Two-step hard-filter screen** (qualified universe) + research-phase no score cutoff |
| #286 | **ADR 0028** (the governing decision) |
| #285 | Orders **"Today"** tab (buy/sell history with fill prices) — supporting evidence view |
| #280 | Dispatch-liveness health check (detect silently-inert strategies) — **still OPEN**, related but not part of the range stack |

---

## 2. Architecture (the pipeline)

```
DEFAULT_CANDIDATE_UNIVERSE (~19 liquid large-caps)        ← Docs/design plan §10 "Candidate Engine"
        │
        ▼   HARD FILTERS  (price > $10 · ADV > $50M · ATR% > 3%)     ← two-step screen (ADR 0028 §4)
   Qualified Universe
        │
        ▼   RANGE SCORE  (evidence-first: win rate → Sharpe → atr20_pct × oscillation)
   Ranked candidates
        │
        ▼   TOP-N  (N=5; research phase: NO absolute score cutoff)
   Today's opportunity set  ──audit──▶  STRATEGY_UPDATED (selection evidence)
        │
        ▼   stop → set symbols_json → start   (pre-open, guarded)
   Range Trader (one strategy, multi-symbol, per-symbol state)
        │
        ▼
   OrderRouter → risk engine → broker (paper)   ← ADR 0002 single router; no LLM in path
        │
        ▼
   Signals / Orders / Fills  ──▶  evidence for the 40–60 day calibration
```

Files: `app/services/range_insight.py` (Candidate Engine), `app/services/range_auto_select.py` (daily job), `strategies_user/templates/range_trader.py` (the strategy), `app/lifespan.py` (cron wiring).

---

## 3. Research hypotheses (H1 / H2 / H3)

All hypothesis knobs are **opt-in and default-OFF** → live behavior is unchanged until set; each is meant to be backtested and evaluated independently, in order (H1 freeze → H2 → H3).

### H1 — which symbols (candidate selection) — PR #281
- **Range Score** = `atr20_pct × oscillation`, where `oscillation = 1 − Kaufman efficiency ratio` (net/path). Rewards a wide range that genuinely *oscillates* rather than trends.
- **Evidence-first ranking**: a symbol with a realized range backtest ranks by **win rate → Sharpe** *above* any non-backtested name; the rest fall back to the structural Range Score.
- Outputs: `rank_candidates` / `rank_range_candidates` → `top_range_symbols` / `select_top_range_symbols`.

### H2 — entry/trigger logic — PR #282
- `entry_zone_pct` — support **zone** (buy the lowest fraction of the day's range, not an exact touch).
- `vwap_gate_pct` — **VWAP gate** (skip a fade when price is far below session VWAP — don't catch a falling knife).
- `entry_zone_atr_mult` × `atr20_pct` — **ATR-scaled zone** (zone width scales to the symbol's volatility; cross-symbol robust), clamped to resistance.

### H3 — exits (first lever) — PR #287
- `scale_out_pct` / `scale_out_target_pct` — **scale-out partial profit-take** at a nearer target, remainder runs to resistance. Evaluated after the full exit-at-resistance check (so at/above resistance the full exit wins). Per-symbol `scaled_out` flag fires it once/day.
- *Future H3 levers (not built): trailing stop, VWAP/ATR-target exit, time-decayed target.*

---

## 4. Multi-symbol execution — PR #283

- One Range Trader trades a universe of symbols. **All per-day state is per-symbol** (`_SymState` in `self._sym[symbol]`): opening range, session VWAP, trade counter, stop-out halt, in-flight flag, scale-out flag. `on_bar` fires once per symbol and touches only that symbol's state — they never collide.
- `per_position_budget` — caps each symbol's notional so a fixed sleeve spreads across the universe (#1 = $4,000/position × 5 = $20k intent).
- Strategy-level risk (gross exposure, concurrent caps) stays in the central risk engine — **not** re-implemented in the template (ADR 0002 / risk-engine invariant).
- Footgun fixed: the per-symbol state holder is a **plain class, not `@dataclass`** (the StrategyLoader execs templates without `sys.modules` registration, which crashes `@dataclass`).

---

## 5. Candidate Engine — hard filters, qualified universe, Top-N

### Hard filters (two-step screen, ADR 0028 §4 / owner guidance) — PR #291
`HardFilters` (defaults, overridable):

| Filter | Default | Status |
|--------|---------|--------|
| Price | > $10 | ✅ enforced (`last_close`) |
| Avg daily $ volume (ADV) | > $50M | ✅ enforced (new `adv` = mean(close×volume)) |
| ATR% | > 3% | ✅ enforced (`atr20_pct`) |
| RVOL | > 1.5 | ⏸ **deferred** — needs intraday volume (not available at a 09:00 ET pre-open run) |
| Avg spread | < 0.10% | ⏸ **deferred** — needs quote data the bar cache does not carry |

Only names passing **all enforced** filters enter the **qualified universe** and become selectable. Each candidate is tagged `qualified` + `qualify_reason`. **Range-boundness is a *score* factor, not a hard filter** — a qualified trender can be selected but ranks low.

### Top-N selection (research phase: NO absolute cutoff)
- Selects the Top-N from the qualified universe **regardless of absolute Range Score**, to collect calibration evidence (owner: "the score is a ranking, not pass/fail").
- `auto_select_min_score` exists (default **0 = off**) as a *future production* threshold, to be **derived empirically after ≥40 trading days** — not assumed now.
- No silent padding: a thin/weak day yields **fewer than N**, or zero (which skips the day).

> Note on scale: the owner's example threshold "70" is on an illustrative 0–100 scale; the implemented Range Score is **0–1** (e.g. AMD ≈ 0.063), so a numeric cutoff is intentionally **not** applied yet — hard filters are the gate.

---

## 6. Daily auto-select job — PR #288 (+ guards #289, filters #291)

`app/services/range_auto_select.py` → `run_daily_range_universe`.

- **Opt-in (per strategy)**: `params_json.auto_select_top_n > 0` (optional `auto_select_universe`, `auto_select_min_score`). A strategy without the marker is **never touched**.
- **Schedule**: APScheduler cron **mon–fri 09:00 ET** (scheduler tz is ET), `max_instances=1`, `coalesce=True`. No-op until a strategy opts in.
- **Mechanism**: a running strategy's symbols can't change at runtime, so per opted-in strategy: **stop (`engine.unregister`) → set `symbols_json` = today's Top-N → audit → start (`engine.register`)**. Idempotent (no-op when unchanged); IDLE strategies are updated but not started (activation stays a user action); per-strategy fail-soft; **no order path**.
- **Pre-flight guards (review #6)** — the stop→start runs only when safe, else skip + WARN (no partial stop/start):
  - `skipped_live` — LIVE excluded (the stop→start cycle would downgrade LIVE→PAPER; live rotation needs its own ADR).
  - `skipped_after_open` — **before-RTH gate** (skip at/after 09:30 ET) → the day's set is **frozen** once the session opens (review #2).
  - `skipped_open_position` — a held position in any symbol the sleeve trades (its PAPER account).
  - `skipped_pending_order` — any non-terminal order from the strategy.
- **Cooldown exemption** (ADR 0005): narrowly, a system-initiated, pre-open, same-strategy, PAPER-only universe reassignment with no open position/pending order is **not** a (re)activation → no 24h cooldown.

---

## 7. Audit & selection evidence (review #3) — PR #290/#291

Every applied assignment writes `AuditAction.STRATEGY_UPDATED`, `actor_type=SYSTEM`, with `payload`:
```
changed.symbols, previous, source="daily_preopen_auto_select", n,
selection: {
  ranking_version: "evidence-first-v1",
  n_requested, min_score, universe_size, qualified_size,
  selected: [{symbol, rank, score, win_rate, sharpe, backtested}],
  excluded: [{symbol, reason}]   # insufficient_data | price_below_min | adv_below_min |
}                                #          atr_below_min | below_min_score | rank_beyond_n
```
→ each daily pick is a reproducible Evidence-Engineering artifact (scores + why each name was in/out), not just a symbol diff. Verifiable hash-chained (audit log immutability).

---

## 8. UI surfaces

- **Strategies page**: "Today's range universe" banner (lists each auto-select strategy's current symbols + Top-N + last-updated) and an "Auto·N" badge on the row. — PR #288
- **Orders page → "Today" tab**: flat buy/sell history with fill prices (time · symbol · side · qty · price · value · source). — PR #285
- *Not yet surfaced in UI (planned): the `qualified`/`adv` fields + per-candidate selection evidence on the candidates panel.*

---

## 9. ADR 0028 — "Scheduled Pre-Open Opportunity Assignment" (Accepted)

`docs/adr/0028-scheduled-strategy-universe-refresh.md`; copy in this folder: `ADR-0028-scheduled-strategy-universe-refresh.md`. Owner-approved 2026-06-26 (9.7/10), all six review items folded (#1 rename, #2 frozen input, #3 evidence, #4 hard filters + research no-threshold, #5 narrowed cooldown wording, #6 pre-flight guards).

---

## 10. Deployment state + live config

- Deployed from branch `docs/combined-book-port001` (carries `main`'s range stack **and** the INSIDER-001 altdata code). Backend **image rebuilt** (app code is baked, not bind-mounted) + restarted; **healthy**; `range_autoselect_scheduled` registered.
- **Live config (the one enabled sleeve):**

| Strategy | Status | Symbols (today) | auto_select_top_n | per_position_budget | auto_select_min_score | level_mode |
|---|---|---|---|---|---|---|
| **#1 Range Trader NVDA** (user2, PAPER) | enabled | `[NVDA]` (will rotate Mon) | **5** | **4000** | **0** (off, research) | opening_range |
| #3 Range Trader AAPL (user2, IDLE) | untouched | `[AAPL]` | — (no marker) | — | — | — |

- Hard filters apply via engine defaults ($10 / $50M / 3%). With `min_score=0`, the **hard filters are the only gate** (research phase).

---

## 11. Deferred / planned (intentionally NOT done yet)

1. **RVOL > 1.5** and **avg spread < 0.10%** hard filters — need intraday volume + quote data not available at pre-open; join when that data is wired. **▶ scheduled 2026-06-28** (data-source decisions first — see `range_followups_next_session` memory).
2. **Empirical production threshold** — after **≥40 trading days**, derive the minimum Range Score (and/or per-band rule) from observed outcomes, then set `auto_select_min_score`. The threshold becomes a *research result*.
3. **Calibration report** — a per-score-band rollup (trades/day, win rate, avg P&L, Sharpe, opening-range touch rate) that the empirical threshold will read. Not built — the raw evidence (selection audit + signals/orders/fills) is being collected now. **▶ scheduled 2026-06-28**.
4. **UI**: expose `qualified`/`adv`/selection-evidence on the candidates panel.
5. **Further H3 levers**: trailing stop, VWAP/ATR-target exit, time-decayed target.
6. **LIVE auto-rotation** — out of scope (own ADR + stronger controls required).

---

## 12. Verification checklist (plan → status)

| # | Planned (design / ADR / owner reviews) | Status | Evidence |
|---|----------------------------------------|--------|----------|
| 1 | One Range Trader on Top-3–5 candidates (not N strategies) | ✅ | #283 multi-symbol + #288 job |
| 2 | Candidate Engine ranks a universe; Top-N daily | ✅ | #281 + #288 |
| 3 | Evidence-first ranking (win rate → Sharpe → score) | ✅ | #281 |
| 4 | H1 Range Score = ATR% × oscillation (Range Efficiency) | ✅ | #281 |
| 5 | H2 support zone | ✅ | #282 |
| 6 | H2 VWAP gate (below support zone) | ✅ | #282 |
| 7 | H2 ATR-scaled zone width = f(ATR%) | ✅ | #282 |
| 8 | H3 better exits (first lever) | ✅ (scale-out) | #287 |
| 9 | Per-symbol independent state | ✅ | #283 |
| 10 | Strategy-level capital budget ($20k / $4k each) | ✅ | #283 `per_position_budget` + #1=4000 |
| 11 | Pre-open job assigns the day's set; frozen for session | ✅ | #288 + RTH gate #289 |
| 12 | Hard filters → qualified universe → score → Top-N | ✅ (price/ADV/ATR%) | #291 |
| 13 | RVOL / spread hard filters | ⏸ deferred (data) | §11.1 |
| 14 | Research phase: NO absolute score cutoff | ✅ | #291; #1 min_score=0 |
| 15 | Empirical threshold after ≥40 days | ⏳ planned | §11.2 |
| 16 | Record calibration metrics (trades, win rate, P&L, Sharpe, OR-touch) | ◑ raw evidence collected; rollup report planned | §11.3 |
| 17 | LIVE excluded; PAPER only | ✅ | #289 |
| 18 | Pre-flight guards (no position / no order / pre-RTH / PAPER) | ✅ | #289 |
| 19 | Audit every refresh + rich selection evidence | ✅ | #290/#291 |
| 20 | No order path / single router / no LLM in path | ✅ | by construction (services only) |
| 21 | ADR governing the decision (Accepted) | ✅ | #286 / ADR 0028 |
| 22 | UI shows today's traded symbols | ✅ | #288 banner |
| 23 | Order/trade activity visible (buy/sell + prices) | ✅ | #285 |

Legend: ✅ done · ◑ partial · ⏳ planned · ⏸ deferred.

---

## 13. Monday 2026-06-29 runbook (first live fire)

**~09:00 ET** the job runs for #1:
1. Rank the default universe (~19 names) evidence-first; apply hard filters (price/ADV/ATR%).
2. Pick the Top-5 qualified by rank (no absolute cutoff).
3. If #1 is PAPER, flat (no open position), has no working order, and it's pre-RTH → **stop → set symbols=Top-5 → start**; else skip + WARN.
4. Write the selection evidence to the audit log.

**How to verify it ran (after 09:00 ET):**
- Strategies page → "Today's range universe" banner shows #1's 5 symbols (no longer just NVDA).
- `docker compose logs backend | grep range_autoselect` → `range_autoselect_applied` (or a `skipped_*` reason).
- Audit log → latest `STRATEGY_UPDATED` (actor SYSTEM, `source=daily_preopen_auto_select`) with the `selection` evidence.
- Intraday: Orders → "Today" tab shows fills as they occur across the 5 symbols.

**Expected today's qualified Top-5** (from a 2026-06-27 dry run, will differ Monday): NVDA, INTC, AMD, MU, QQQ.

---

## 14. Things to confirm before Monday

1. **AAPL evidence anomaly** — AAPL's *latest* range backtest in the DB shows **win_rate = 0.0** (not the +0.46 / 62% cited earlier), and AAPL currently classifies "mixed" (so it may not qualify/rank). The evidence loader uses the most-recent backtest per symbol. **Confirm whether to re-backtest AAPL** so its rank reflects real performance.
2. **NVDA ranks #1 today** purely because it's the only *backtested + qualified* name (evidence-first), despite ~27% win rate. Acceptable for research (we want to observe it), but confirm you're comfortable it leads.
3. **Budget**: `per_position_budget = $4,000` × 5 ≈ $20k of the paper account deployed/day — confirm sizing vs the account equity.
4. **Deploy branch**: the running stack is `docs/combined-book-port001` (range stack + INSIDER-001 code), not bare `main`. Confirm that's the intended deploy lineage.
5. **#280** (dispatch-liveness health check) is still an open PR — independent of range, but it's the safety net that would catch a silently-inert sleeve. Consider merging before relying on the live trial.
6. **Backend uptime before the open** — the job only fires if the stack is up at 09:00 ET (see the MarketHours Healthcheck scheduled task). Confirm it's active so Monday's fire isn't missed.

---

*End of review. Please annotate gaps; I can correct before Monday open.*
