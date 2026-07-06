# Range Strategy — Implementation Review (pre-Monday overview) — v1.1

| | |
|---|---|
| **Date** | 2026-06-27 |
| **Author** | Claude (implementation) — for owner final overview |
| **Purpose** | Document the *completed* Range-trading research implementation so the owner can verify it matches the plan and flag missing elements **before Monday 2026-06-29 market open** (first live auto-select fire = Mon 09:00 ET). |
| **Source of truth (plan)** | `Docs/design/RangeTrading_Logic_and_Research_v0.1.md` (frozen v0.3); `docs/adr/0028-scheduled-strategy-universe-refresh.md` (**Accepted**); `docs/adr/0029-opportunity-registry-and-discovery-lab-engine-separation.md` (**Proposed**); owner reviews in `docs/review/comments.md` + this folder. |
| **Deployed on** | branch `docs/combined-book-port001` → backend image rebuilt + restarted (healthy). |
| **Changes since v1.0** | Folds the owner review (`docs/review/comments.md`, 9.8/10). See §0. |

> How to use this doc: §12 is the **verification checklist** (plan item → status → where). §13 is the **Monday runbook**. §11 lists what's **deferred/planned** (intentionally not done yet). §14 lists **things to confirm**.

---

## 0. What changed in v1.1 (owner-review fold)

The owner review of v1.0 scored 9.8/10 and made one architectural recommendation plus several
refinements. Each is folded here; the **architectural** recommendation is also captured as a
decision in **ADR 0029** (Proposed).

| # | Owner comment | How it's folded |
|---|---------------|-----------------|
| 1 | Separate **qualification**, **ranking**, and **opportunity assignment** explicitly (headline rec) | §2 / §5 now name the **Qualification Engine**, **Ranking Engine**, **Opportunity Assignment Engine** as three responsibilities the shipped code already performs → **ADR 0029** |
| 2 | Insert an **Opportunity Registry** layer; it becomes Discovery Lab's official output that strategies consume | §2 pipeline + §15 long-term architecture; formalized as a persisted read-model in **ADR 0029** (Phase 1) |
| 3 | "Evidence-**weighted**", not "Evidence-first" | Renamed throughout (§3, §5, §7) — it's a *weighting* of historical evidence + structural score, not a binary precedence |
| 4 | Standardize on **"Opportunity Set"** (not Top-N / Today's universe / Today's range universe) | Adopted as canonical term; old terms marked deprecated synonyms (§2, §5, §8) |
| 5 | Note: **hard filters are structural** (change infrequently); **ranking models evolve** through research | Added to §5 |
| 6 | Per-position budget: **unused budget stays in cash** (not redistributed) | §4 made explicit |
| 7 | Monday runbook: add an **expected-outcome table** incl. "0 qualified = normal (no opportunity)" | §13 new outcome table |
| 8 | §14 NVDA concern: don't let one backtest dominate → **composite ranking** transitioning over ~60 days | §14.2 expanded with the composite-weighting plan (ADR 0029 §6) |
| 9 | Calibration: produce a **rolling weekly report**, don't wait until day 40 | §11.3 + §14 — weekly Friday rollup |
| 10 | Add **Selection Precision** metric (selected → actually traded) | §16 new metrics section |
| 11 | Add **Opportunity Conversion** funnel (Qualified → Selected → Triggered → Filled → Exited) | §16 |

---

## 1. Shipped PRs (all merged to `main`)

| PR | What |
|----|------|
| #281 | **H1** — evidence-weighted candidate ranker + Top-N (Opportunity Set) selection |
| #282 | **H2** — entry: support-zone, VWAP gate, ATR-scaled zone |
| #283 | **Multi-symbol-safe** Range Trader (per-symbol state) + per-position budget |
| #287 | **H3** — scale-out partial profit-take (first exit lever) |
| #288 | **Daily Opportunity-Set auto-select job** + "Today's range universe" UI |
| #289 | Auto-select **pre-flight guards** (#6) + ADR 0028 review fold (Accepted) |
| #290 | **#4** minimum-quality gate (initial) + **#3** richer selection evidence |
| #291 | **Two-step hard-filter screen** (Qualified Universe) + research-phase no score cutoff |
| #286 | **ADR 0028** (the governing decision) |
| #285 | Orders **"Today"** tab (buy/sell history with fill prices) — supporting evidence view |
| #280 | Dispatch-liveness health check (detect silently-inert strategies) — **still OPEN**, related but not part of the range stack |

---

## 2. Architecture (the pipeline)

The day's selection is produced by **three responsibilities** — eligibility, quality, and
assignment — which the shipped code already performs and which **ADR 0029** names as distinct
capabilities. The owner-recommended **Opportunity Registry** is the official, persisted output of
this stage (a frozen, dated, audited record of "the names selected for a program on a session, and
why"); strategies *consume* it rather than re-deriving selection. (Registry persistence is ADR 0029
Phase 1 — see §11.7; today the same content lives in the audit `selection` payload.)

```
DEFAULT_CANDIDATE_UNIVERSE (~19 liquid large-caps)        ← Docs/design plan §10 "Candidate Engine"
        │
        ▼   QUALIFICATION ENGINE — HARD FILTERS  (price > $10 · ADV > $50M · ATR% > 3%)   ← #291 / ADR 0028 §4
   Qualified Universe                                       (structural; change infrequently)
        │
        ▼   RANKING ENGINE — RANGE SCORE  (evidence-weighted: win rate → Sharpe → atr20_pct × oscillation)
   Ranked candidates                                        (research model; expected to evolve)
        │
        ▼   OPPORTUNITY ASSIGNMENT ENGINE — TOP-N  (N=5; research phase: NO absolute score cutoff)
   Today's Opportunity Set  ──write──▶  OPPORTUNITY REGISTRY  ──audit──▶  STRATEGY_UPDATED (selection evidence)
        │
        ▼   stop → set symbols_json → start   (pre-open, guarded; frozen for the session)
   Range Trader (one strategy, multi-symbol, per-symbol state)  ──reads── the Opportunity Set
        │
        ▼
   OrderRouter → risk engine → broker (paper)   ← ADR 0002 single router; no LLM in path
        │
        ▼
   Signals / Orders / Fills  ──▶  evidence for the rolling calibration report (§16) + 40–60 day threshold
```

Files: `app/services/range_insight.py` (Qualification + Ranking — to be split per ADR 0029 Phase 2),
`app/services/range_auto_select.py` (Assignment Engine — the daily job),
`strategies_user/templates/range_trader.py` (the strategy), `app/lifespan.py` (cron wiring).

---

## 3. Research hypotheses (H1 / H2 / H3)

All hypothesis knobs are **opt-in and default-OFF** → live behavior is unchanged until set; each is meant to be backtested and evaluated independently, in order (H1 freeze → H2 → H3).

### H1 — which symbols (candidate selection) — PR #281
- **Range Score** = `atr20_pct × oscillation`, where `oscillation = 1 − Kaufman efficiency ratio` (net/path). Rewards a wide range that genuinely *oscillates* rather than trends.
- **Evidence-weighted ranking**: realized-backtest evidence (win rate → Sharpe) is **weighted alongside** the structural Range Score, rather than a non-backtested name always losing to a backtested one. (v1.0 called this "evidence-first"; renamed per owner review — see §14.2 for the composite direction that removes the current backtested-name anchoring.)
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
- **Unused budget stays in cash; it is not redistributed** (owner review #6). If only 3 of 5 names trigger, the other ~$8,000 simply stays uninvested rather than being concentrated into the names that did trigger. This keeps **per-day comparability** intact (each name has the same sizing opportunity every day) and avoids silently increasing single-name exposure on thin days.
- Strategy-level risk (gross exposure, concurrent caps) stays in the central risk engine — **not** re-implemented in the template (ADR 0002 / risk-engine invariant).
- Footgun fixed: the per-symbol state holder is a **plain class, not `@dataclass`** (the StrategyLoader execs templates without `sys.modules` registration, which crashes `@dataclass`).

---

## 5. Candidate Engine — the three engines (qualification · ranking · assignment)

Per ADR 0029 the "Candidate Engine" is three responsibilities. They already exist in shipped code;
naming them keeps the architecture legible and is the precondition for other programs reusing them.

### 5a. Qualification Engine — hard filters → Qualified Universe (#291)
`HardFilters` (defaults, overridable):

| Filter | Default | Status |
|--------|---------|--------|
| Price | > $10 | ✅ enforced (`last_close`) |
| Avg daily $ volume (ADV) | > $50M | ✅ enforced (new `adv` = mean(close×volume)) |
| ATR% | > 3% | ✅ enforced (`atr20_pct`) |
| RVOL | > 1.5 | ⏸ **deferred** — needs intraday volume (not available at a 09:00 ET pre-open run) |
| Avg spread | < 0.10% | ⏸ **deferred** — needs quote data the bar cache does not carry |

Only names passing **all enforced** filters enter the **Qualified Universe** and become selectable.
Each candidate is tagged `qualified` + `qualify_reason`. **Range-boundness is a *score* factor, not a
hard filter** — a qualified trender can be selected but ranks low.

> **Hard filters are structural constraints and should change infrequently; ranking models are
> expected to evolve through research** (owner review #5). The two are deliberately separated so that
> tightening eligibility (a rare, governance-weight change) is never conflated with tuning the ranking
> (a frequent research activity).

### 5b. Ranking Engine — evidence-weighted Range Score
Scores and orders the Qualified Universe (realized win rate → Sharpe → structural
`atr20_pct × oscillation`). Described as **evidence-weighted** (§3). The composite direction that
prevents stale-backtest anchoring is in §14.2 / ADR 0029 §6.

### 5c. Opportunity Assignment Engine — freeze Top-N Opportunity Set (research phase: NO absolute cutoff)
- Selects the **Top-N Opportunity Set** from the Qualified Universe **regardless of absolute Range
  Score**, to collect calibration evidence (owner: "the score is a ranking, not pass/fail").
- `auto_select_min_score` exists (default **0 = off**) as a *future production* threshold, to be
  **derived empirically after ≥40 trading days** — not assumed now.
- No silent padding: a thin/weak day yields **fewer than N**, or zero (which skips the day).
- Freezes the set pre-open and is **immutable for the session** (ADR 0028 §3).

> Note on scale: the owner's example threshold "70" is on an illustrative 0–100 scale; the implemented
> Range Score is **0–1** (e.g. AMD ≈ 0.063), so a numeric cutoff is intentionally **not** applied yet —
> hard filters are the gate.

---

## 6. Daily auto-select job — PR #288 (+ guards #289, filters #291)

`app/services/range_auto_select.py` → `run_daily_range_universe`. (This *is* the Opportunity
Assignment Engine of §5c.)

- **Opt-in (per strategy)**: `params_json.auto_select_top_n > 0` (optional `auto_select_universe`, `auto_select_min_score`). A strategy without the marker is **never touched**.
- **Schedule**: APScheduler cron **mon–fri 09:00 ET** (scheduler tz is ET), `max_instances=1`, `coalesce=True`. No-op until a strategy opts in.
- **Mechanism**: a running strategy's symbols can't change at runtime, so per opted-in strategy: **stop (`engine.unregister`) → set `symbols_json` = today's Opportunity Set → audit → start (`engine.register`)**. Idempotent (no-op when unchanged); IDLE strategies are updated but not started (activation stays a user action); per-strategy fail-soft; **no order path**.
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
  ranking_version: "evidence-weighted-v1",   # (the algorithm; "evidence-first-v1" string retained in code until a versioned rename)
  n_requested, min_score, universe_size, qualified_size,
  selected: [{symbol, rank, score, win_rate, sharpe, backtested}],
  excluded: [{symbol, reason}]   # insufficient_data | price_below_min | adv_below_min |
}                                #          atr_below_min | below_min_score | rank_beyond_n
```
→ each daily pick is a reproducible Evidence-Engineering artifact (scores + why each name was in/out),
not just a symbol diff. Verifiable hash-chained (audit log immutability). This `selection` payload is
the content that **ADR 0029 Phase 1** persists into the **Opportunity Registry** read-model (the audit
log stays the source of truth; the Registry is the queryable derivation the metrics in §16 read).

---

## 8. UI surfaces

- **Strategies page**: "Today's range universe" banner (lists each auto-select strategy's current symbols + Top-N + last-updated) and an "Auto·N" badge on the row. — PR #288. *(Terminology: migrates to "Today's Opportunity Set" per ADR 0029 §4 as the surface is touched.)*
- **Orders page → "Today" tab**: flat buy/sell history with fill prices (time · symbol · side · qty · price · value · source). — PR #285
- *Not yet surfaced in UI (planned): the `qualified`/`adv` fields + per-candidate selection evidence on the candidates panel; the Opportunity Conversion funnel (§16).*

---

## 9. ADRs governing the decision

- **ADR 0028 — "Scheduled Pre-Open Opportunity Assignment" (Accepted).** Owner-approved 2026-06-26 (9.7/10), all six review items folded. `docs/adr/0028-…`; copy in this folder.
- **ADR 0029 — "Opportunity Registry & the Qualification / Ranking / Assignment separation" (Proposed).** Captures this review's headline architectural recommendation (the three engines + the Opportunity Registry + evidence-weighted/Opportunity-Set vocabulary + the composite-ranking direction). `docs/adr/0029-…`.

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
3. **Rolling calibration report (weekly)** — a per-score-band rollup (trades/day, win rate, avg P&L, Sharpe, opening-range touch rate, score distribution) refreshed **every Friday**, so the day-40 threshold decision reads a report that already exists rather than being a one-shot at day 40 (owner review #9). Not built — the raw evidence (selection audit + signals/orders/fills) is being collected now. **▶ scheduled 2026-06-28**.
4. **UI**: expose `qualified`/`adv`/selection-evidence on the candidates panel; surface the Opportunity Conversion funnel (§16).
5. **Further H3 levers**: trailing stop, VWAP/ATR-target exit, time-decayed target.
6. **LIVE auto-rotation** — out of scope (own ADR + stronger controls required).
7. **Opportunity Registry persistence + engine split + composite ranking** — ADR 0029 Phases 1–3, sequenced **after** Monday's trial so the live sleeve isn't destabilized. Phase 1 (persist the `selection` payload as a queryable read-model) unblocks the §16 metrics.

---

## 12. Verification checklist (plan → status)

| # | Planned (design / ADR / owner reviews) | Status | Evidence |
|---|----------------------------------------|--------|----------|
| 1 | One Range Trader on Top-3–5 candidates (not N strategies) | ✅ | #283 multi-symbol + #288 job |
| 2 | Candidate Engine ranks a universe; daily Opportunity Set | ✅ | #281 + #288 |
| 3 | Evidence-weighted ranking (win rate → Sharpe → score) | ✅ | #281 |
| 4 | H1 Range Score = ATR% × oscillation (Range Efficiency) | ✅ | #281 |
| 5 | H2 support zone | ✅ | #282 |
| 6 | H2 VWAP gate (below support zone) | ✅ | #282 |
| 7 | H2 ATR-scaled zone width = f(ATR%) | ✅ | #282 |
| 8 | H3 better exits (first lever) | ✅ (scale-out) | #287 |
| 9 | Per-symbol independent state | ✅ | #283 |
| 10 | Strategy-level capital budget ($20k / $4k each); unused stays in cash | ✅ | #283 `per_position_budget` + #1=4000; §4 |
| 11 | Pre-open job assigns the day's set; frozen for session | ✅ | #288 + RTH gate #289 |
| 12 | Hard filters → Qualified Universe → score → Opportunity Set | ✅ (price/ADV/ATR%) | #291 |
| 13 | RVOL / spread hard filters | ⏸ deferred (data) | §11.1 |
| 14 | Research phase: NO absolute score cutoff | ✅ | #291; #1 min_score=0 |
| 15 | Empirical threshold after ≥40 days | ⏳ planned | §11.2 |
| 16 | Record calibration metrics (trades, win rate, P&L, Sharpe, OR-touch) | ◑ raw evidence collected; rolling weekly rollup planned | §11.3 / §16 |
| 17 | LIVE excluded; PAPER only | ✅ | #289 |
| 18 | Pre-flight guards (no position / no order / pre-RTH / PAPER) | ✅ | #289 |
| 19 | Audit every refresh + rich selection evidence | ✅ | #290/#291 |
| 20 | No order path / single router / no LLM in path | ✅ | by construction (services only) |
| 21 | ADR governing the decision (Accepted) | ✅ | #286 / ADR 0028 |
| 22 | UI shows today's traded symbols | ✅ | #288 banner |
| 23 | Order/trade activity visible (buy/sell + prices) | ✅ | #285 |
| 24 | Three engines named (Qualification / Ranking / Assignment) | ◑ named in docs; code split planned | ADR 0029 / §5 |
| 25 | Selection Precision + Opportunity Conversion metrics | ⏳ planned (needs Registry read-model) | §16 / ADR 0029 Phase 1 |

Legend: ✅ done · ◑ partial · ⏳ planned · ⏸ deferred.

---

## 13. Monday 2026-06-29 runbook (first live fire)

**~09:00 ET** the job runs for #1:
1. **Qualify** the default universe (~19 names): apply hard filters (price/ADV/ATR%).
2. **Rank** the Qualified Universe evidence-weighted.
3. **Assign**: pick the Top-5 Opportunity Set by rank (no absolute cutoff).
4. If #1 is PAPER, flat (no open position), has no working order, and it's pre-RTH → **stop → set symbols=Opportunity Set → start**; else skip + WARN.
5. Write the selection evidence to the audit log (→ Opportunity Registry once Phase 1 lands).

**Expected outcomes (this is the table to read before assuming a failure — owner review #7):**

| Outcome | Qualified candidates | Selected (Opportunity Set) | Trades | Interpretation |
|---|---|---|---|---|
| **A** | ≥5 | 5 | some (e.g. 3) | **Normal** — opportunities found and several triggered |
| **B** | ≥5 | 5 | 0 | **Normal** — names selected but none reached the support zone today (no falling-knife entries) |
| **C** | 0 | 0 (day skipped) | 0 | **Normal — no opportunity.** A trending/quiet tape simply offers no range setups; an empty set is a *valid result*, not a malfunction |
| **D** | 1–4 | <5 | any | **Normal** — thin day; no silent padding to N |

> Zero trades does **not** indicate a failure. The Range edge is conditional on oscillating tape; on a
> trending day the correct behavior is to trade little or nothing.

**How to verify it ran (after 09:00 ET):**
- Strategies page → "Today's range universe" banner shows #1's 5 symbols (no longer just NVDA).
- `docker compose logs backend | grep range_autoselect` → `range_autoselect_applied` (or a `skipped_*` reason).
- Audit log → latest `STRATEGY_UPDATED` (actor SYSTEM, `source=daily_preopen_auto_select`) with the `selection` evidence.
- Intraday: Orders → "Today" tab shows fills as they occur across the 5 symbols.

**Expected today's qualified Opportunity Set** (from a 2026-06-27 dry run, will differ Monday): NVDA, INTC, AMD, MU, QQQ.

---

## 14. Things to confirm before Monday

1. **AAPL evidence anomaly** — AAPL's *latest* range backtest in the DB shows **win_rate = 0.0** (not the +0.46 / 62% cited earlier), and AAPL currently classifies "mixed" (so it may not qualify/rank). The evidence loader uses the most-recent backtest per symbol. **Confirm whether to re-backtest AAPL** so its rank reflects real performance. *(Owner: agreed — resolve before using AAPL in calibration; one inconsistent backtest can distort confidence in the ranker.)*
2. **NVDA ranks #1 today** purely because it's the only *backtested + qualified* name (evidence-weighted), despite ~27% win rate. Acceptable for research **now** (we want to observe it), but the **fix is a composite ranking** so a single historical backtest cannot dominate for long (owner review #8; ADR 0029 §6):
   - Move from "a backtested name outranks any non-backtested name" to
     `rank = w·HistoricalEvidence + (1−w)·CurrentOpportunityScore`.
   - Start weighted **toward live/current evidence** while forward samples are thin (e.g. ~0.4 historical / 0.6 current), then **shift toward historical** as a name's own forward sample grows (e.g. ~0.6 / 0.4 after ≈60 trading days) — *weights derived from the calibration data, not assumed*.
   - This removes the stale-anchor risk without discarding the historical evidence. Confirm you're comfortable NVDA leads **for the research window** until the composite lands.
3. **Budget**: `per_position_budget = $4,000` × 5 ≈ $20k of the paper account deployed/day, **unused stays in cash** (§4) — confirm sizing vs the account equity.
4. **Deploy branch**: the running stack is `docs/combined-book-port001` (range stack + INSIDER-001 code), not bare `main`. Confirm that's the intended deploy lineage.
5. **#280** (dispatch-liveness health check) is still an open PR — independent of range, but it's the safety net that would catch a silently-inert sleeve. Consider merging before relying on the live trial.
6. **Backend uptime before the open** — the job only fires if the stack is up at 09:00 ET (see the MarketHours Healthcheck scheduled task). Confirm it's active so Monday's fire isn't missed.

---

## 15. Long-term architecture (owner review)

The owner's target architecture — stronger than the one currently in the whitepaper — is a single
opportunity pipeline that every program consumes (captured in **ADR 0029** and folded into the
whitepaper Ch2 drop-in v0.2):

```
Discovery Lab
     │
     ▼
Candidate Engine  =  Qualification Engine → Ranking Engine → Opportunity Assignment Engine
     │
     ▼
Opportunity Registry            ← the official, persisted output of Discovery Lab
     │
     ▼
Strategy  (Range now; Momentum · Sector Rotation · Trend · Breakout later — same Registry)
     │
     ▼
Execution  (OrderRouter → risk → broker)
     │
     ▼
Evidence  (audit · signals · orders · fills)
     │
     ▼
Continuous Verification  (rolling calibration · Operating Envelope)
```

The point of the Registry is reuse: Momentum, Sector Rotation, Trend, and Breakout consume the **same**
Opportunity Set contract (each parameterized with its own filters/ranking/N), instead of each program
re-implementing "filter → rank → pick today's names."

---

## 16. Calibration metrics (owner review #10/#11)

Two metrics are added to the calibration program. Both require joining the frozen Opportunity Set to
subsequent signals/orders/fills, which is exactly what the **Opportunity Registry** read-model (ADR
0029 Phase 1) makes cheap.

**Selection Precision** — *of the names we selected, how many actually traded?*
```
Selection Precision = (selected names that produced an entry) / (names selected)
e.g. Top-5 = {AMD, TSLA, PLTR, MU, INTC}; only AMD entered → 1/5 = 20%
```
Lets us improve the **Ranking Engine** (pick names that actually trigger) **without changing the Range
Trader**.

**Opportunity Conversion funnel** — *where is opportunity lost?*
```
Qualified Universe → Selected → Triggered → Filled → Exited
e.g.  120 → 12 → 5 → 3 → 2 → 2
```
A per-session funnel that becomes a dashboard; each drop-off points at a different lever (qualification
too tight? ranking picking non-triggering names? entries too strict? exits failing?).

These join the existing per-band rollup (trades/day, win rate, avg P&L, Sharpe, opening-range touch
rate) in the **rolling weekly report** (§11.3) — produced every Friday rather than waiting for day 40.

---

*End of review (v1.1). Please annotate any remaining gaps; I can correct before Monday open.*
